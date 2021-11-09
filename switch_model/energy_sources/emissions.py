# Copyright (c) 2021 The MATCH Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe GHG emissions from generation and grid power

"""

import os
from pyomo.environ import *
import pandas as pd

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones', 'switch_model.generators.core.build'

def define_components(mod):
    """
    ghg_emission_factor[g] is a parameter specifying the emission rate per MWh of generation from each generator
    """
    # Sets
    mod.CCS_EQUIPPED_GENS = Set(within=mod.NON_STORAGE_GENS)
    
    # Parameters

    mod.gen_emission_factor = Param(mod.NON_STORAGE_GENS)

    mod.grid_emission_factor = Param(mod.ZONE_TIMEPOINTS)

    mod.gen_ccs_capture_efficiency = Param(
        mod.CCS_EQUIPPED_GENS, within=PercentFraction)

    mod.gen_ccs_energy_load = Param(
        mod.CCS_EQUIPPED_GENS, within=PercentFraction)

    # Expressions
    def GeneratorEmissions_rule(m, g, t):
        if g not in m.CCS_EQUIPPED_GENS:
            return (m.TotalGen[g,t] * m.gen_emission_factor[g])
        else:
            ccs_emission_frac = 1 - m.gen_ccs_capture_efficiency[g]
            return (m.TotalGen[g,t] * m.gen_emission_factor[g] * ccs_emission_frac)
    mod.GeneratorEmissions = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=GeneratorEmissions_rule
    )

    mod.ZoneTotalGeneratorEmissions = Expression(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m,z,t: sum(m.GeneratorEmissions[g,t] for g in m.NON_STORAGE_GENS_IN_ZONE[z])
    )

    mod.ZoneTotalGridEmissions = Expression(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m,z,t: m.SystemPower[z,t] * m.grid_emission_factor[z,t]
    )
    
    mod.ZoneTotalCCSLoad = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t: \
            - sum(m.DispatchGen[g, t] * m.gen_ccs_energy_load[g]
                for g in m.NON_STORAGE_GENS_IN_ZONE[z]
                if (g, t) in m.NON_STORAGE_GEN_TPS and g in m.CCS_EQUIPPED_GENS),
        doc="Net power from grid-tied generation projects.")
    mod.Zone_Power_Injections.append('ZoneTotalCCSLoad')


def load_inputs(mod, switch_data, inputs_dir):
    """
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        optional_params=['gen_ccs_energy_load', 'gen_ccs_capture_efficiency'],
        index=mod.GENERATION_PROJECTS,
        param=[mod.gen_emission_factor, mod.gen_ccs_energy_load, mod.gen_ccs_capture_efficiency])

    # construct set of CCS equipped gens based on whether the CCS capture efficiency is specified
    if 'gen_ccs_capture_efficiency' in switch_data.data():
        switch_data.data()['CCS_EQUIPPED_GENS'] = {
            None: list(switch_data.data(name='gen_ccs_capture_efficiency').keys())}

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'grid_emissions.csv'),
        select=('load_zone','timepoint','grid_emission_factor'),
        param=[mod.grid_emission_factor])

def post_solve(instance, outdir):
    """
    """
    data = [{
        "load_zone": z,
        "timestamp": instance.tp_timestamp[t],
        "Emission Rate":value(instance.ZoneTotalGeneratorEmissions[z,t] + instance.ZoneTotalGridEmissions[z,t]),
        "Delivered Emission Factor":value((instance.ZoneTotalGeneratorEmissions[z,t] + instance.ZoneTotalGridEmissions[z,t]) / instance.zone_demand_mw[z,t])
    } for z,t in instance.ZONE_TIMEPOINTS]
    emissions_df = pd.DataFrame(data)
    emissions_df.set_index(["load_zone","timestamp"], inplace=True)
    emissions_df.to_csv(os.path.join(outdir, "emissions.csv"))