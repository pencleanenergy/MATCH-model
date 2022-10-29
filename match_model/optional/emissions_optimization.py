# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
This module allows for optimizing the consequential grid emissions impact of the portfolio
"""

from ast import Expr
import os
from pyomo.environ import *
import pandas as pd

dependencies = (
    "match_model.timescales",
    "match_model.balancing.load_zones",
    "match_model.financials",
    "match_model.generators.build",
    "match_model.generators.dispatch",
    "match_model.generators.optional.storage",
)


def define_components(mod):

    # Define Parameters
    ###################

    # TODO: Load this data
    mod.internal_carbon_price = Param(mod.PERIODS, within=NonNegativeReals, default=0)

    mod.gen_is_additional = Param(mod.GENERATION_PROJECTS, within=Boolean)

    mod.CAMBIUM_REGIONS = Set(dimen=1)

    mod.ADDITIONAL_GENS = Set(
        initialize=mod.NON_STORAGE_GENS, filter=lambda m, g: m.gen_is_additional[g]
    )

    mod.ADDITIONAL_STORAGE_GENS = Set(
        initialize=mod.STORAGE_GENS, filter=lambda m, g: m.gen_is_additional[g]
    )

    mod.CCS_EQUIPPED_GENS = Set(within=mod.NON_STORAGE_GENS)

    mod.gen_emission_factor = Param(mod.NON_STORAGE_GENS)
    mod.gen_cambium_region = Param(mod.GENERATION_PROJECTS, within=Any)

    mod.gen_ccs_capture_efficiency = Param(
        mod.CCS_EQUIPPED_GENS, within=PercentFraction
    )

    mod.gen_ccs_energy_load = Param(mod.CCS_EQUIPPED_GENS, within=PercentFraction)

    mod.lrmer = Param(mod.CAMBIUM_REGIONS, mod.TIMEPOINTS)

    # Calculate CCS Load
    ####################

    mod.ZoneTotalCCSLoad = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: -sum(
            m.DispatchGen[g, t] * m.gen_ccs_energy_load[g]
            for g in m.NON_STORAGE_GENS_IN_ZONE[z]
            if (g, t) in m.NON_STORAGE_GEN_TPS and g in m.CCS_EQUIPPED_GENS
        ),
        doc="Net power from grid-tied generation projects.",
    )
    mod.Zone_Power_Injections.append("ZoneTotalCCSLoad")

    # Calculate Direct Emissions
    ############################

    # Caclulate direct emissions from each generator
    def GeneratorEmissions_rule(m, g, t):
        if g not in m.CCS_EQUIPPED_GENS:
            return m.TotalGen[g, t] * m.gen_emission_factor[g]
        else:
            ccs_emission_frac = 1 - m.gen_ccs_capture_efficiency[g]
            return m.TotalGen[g, t] * m.gen_emission_factor[g] * ccs_emission_frac

    mod.GenDirectConsequentialEmissionsInTP = Expression(
        mod.ADDITIONAL_GENS, mod.TIMEPOINTS, rule=GeneratorEmissions_rule
    )

    # Calculate Avoided Emissions
    #############################

    mod.GenIndirectConsequentialEmissionsInTP = Expression(
        mod.ADDITIONAL_GENS,
        mod.TIMEPOINTS,
        rule=lambda m, g, t: -1
        * (m.TotalGen[g, t] * m.lrmer[m.gen_cambium_region[g], t]),
    )

    mod.StorageIndirectConsequentialEmissionsInTP = Expression(
        mod.ADDITIONAL_STORAGE_GENS,
        mod.TIMEPOINTS,
        rule=lambda m, g, t: (m.ChargeStorage[g, t] - m.DischargeStorage[g, t])
        * m.lrmer[m.gen_cambium_region[g], t],
    )

    # Calculate total emissions
    def TotalEmissions_rule(m, g, t):
        totalemissions = 0
        if g in m.ADDITIONAL_GENS:
            totalemissions = (
                totalemissions
                + m.GenDirectConsequentialEmissionsInTP[g, t]
                + m.GenIndirectConsequentialEmissionsInTP[g, t]
            )
        if g in m.ADDITIONAL_STORAGE_GENS:
            totalemissions = (
                totalemissions + m.StorageIndirectConsequentialEmissionsInTP[g, t]
            )
        return totalemissions

    mod.GenTotalConsequentialEmissionsInTP = Expression(
        mod.GEN_TPS, rule=TotalEmissions_rule
    )

    # Costs for objective function
    ##############################

    mod.GenEmissionsCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.internal_carbon_price[m.tp_period[t]]
            * m.GenTotalConsequentialEmissionsInTP[g, t]
            for g in m.GENERATION_PROJECTS
        ),
    )
    mod.Cost_Components_Per_TP.append("GenEmissionsCostInTP")


def load_inputs(mod, match_data, inputs_dir):
    """ """
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "generation_projects_info.csv"),
        auto_select=True,
        optional_params=["gen_ccs_energy_load", "gen_ccs_capture_efficiency"],
        index=mod.GENERATION_PROJECTS,
        param=[
            mod.gen_emission_factor,
            mod.gen_is_additional,
            mod.gen_ccs_energy_load,
            mod.gen_ccs_capture_efficiency,
            mod.gen_cambium_region,
        ],
    )

    # construct set of CCS equipped gens based on whether the CCS capture efficiency is specified
    if "gen_ccs_capture_efficiency" in match_data.data():
        match_data.data()["CCS_EQUIPPED_GENS"] = {
            None: list(match_data.data(name="gen_ccs_capture_efficiency").keys())
        }

    match_data.load_aug(
        filename=os.path.join(inputs_dir, "internal_carbon_price.csv"),
        autoselect=True,
        param=[mod.internal_carbon_price],
    )

    match_data.load_aug(
        filename=os.path.join(inputs_dir, "cambium_regions.csv"),
        set=mod.CAMBIUM_REGIONS,
    )

    match_data.load_aug(
        filename=os.path.join(inputs_dir, "lrmer.csv"),
        autoselect=True,
        param=[mod.lrmer],
    )


def post_solve(instance, outdir):
    emissions_data = [
        {
            "generation_project": g,
            "timestamp": instance.tp_timestamp[t],
            "lrmer": instance.lrmer[instance.gen_cambium_region[g], t],
            "Generation_MW": value(
                instance.TotalGen[g, t] if g in instance.NON_STORAGE_GENS else 0
            )
            + value(
                instance.DischargeStorage[g, t] - instance.ChargeStorage[g, t]
                if g in instance.STORAGE_GENS
                else 0
            ),
            "Consequential_Emissions_Impact": value(
                instance.GenTotalConsequentialEmissionsInTP[g, t]
            ),
        }
        for (g, t) in instance.GEN_TPS
    ]
    emissions_data_df = pd.DataFrame(emissions_data)
    emissions_data_df.set_index(["generation_project", "timestamp"], inplace=True)
    emissions_data_df.to_csv(os.path.join(outdir, "gen_emissions.csv"))
