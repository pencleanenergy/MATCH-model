# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Modifications copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe generation projects build-outs for
the Switch model. This module requires either generators.core.unitcommit or
generators.core.no_commit to constrain project dispatch to either committed or
installed capacity.

"""
import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf
from switch_model.reporting import write_table

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties.properties',\
    'switch_model.generators.core.build'

def define_components(mod):
    """
    Adds components to a Pyomo abstract model object to describe
    generation from fuel-based generators.

    gen_uses_fuel[g]

    NON_FUEL_BASED_GENS

    FUEL_BASED_GENS

    gen_full_load_heat_rate

    MULTIFUEL_GENS

    FUELS_FOR_MULTIFUEL_GEN

    FUELS_FOR_GEN

    GENS_BY_NON_FUEL_ENERGY_SOURCE

    GENS_BY_FUEL

    gen_full_load_heat_rate[g] is the full load heat rate in units
    of MMBTU/MWh that describes the thermal efficiency of a project when
    running at full load. This optional parameter overrides the generic
    heat rate of a generation technology. In the future, we may expand
    this to be indexed by fuel source as well if we need to support a
    multi-fuel generator whose heat rate depends on fuel source.

    Proj_Var_Costs_Hourly[t in TIMEPOINTS] is the sum of all variable
    costs associated with project dispatch for each timepoint expressed
    in $base_year/hour in the future period (rather than Net Present
    Value).

    FUEL_BASED_GEN_TPS is a subset of GEN_TPS
    showing all times when fuel-consuming projects could be dispatched
    (used to identify timepoints when fuel use must match power production).

    GEN_TP_FUELS is a subset of GEN_TPS * FUELS,
    showing all the valid combinations of project, timepoint and fuel,
    i.e., all the times when each project could consume a fuel that is
    limited, costly or produces emissions.

    GenFuelUseRate[(g, t, f) in GEN_TP_FUELS] is a
    variable that describes fuel consumption rate in MMBTU/h. This
    should be constrained to the fuel consumed by a project in each
    timepoint and can be calculated as Dispatch [MW] *
    effective_heat_rate [MMBTU/MWh] -> [MMBTU/h]. The choice of how to
    constrain it depends on the treatment of unit commitment. Currently
    the project.no_commit module implements a simple treatment that
    ignores unit commitment and assumes a full load heat rate, while the
    project.unitcommit module implements unit commitment decisions with
    startup fuel requirements and a marginal heat rate.

    DispatchEmissions[(g, t, f) in GEN_TP_FUELS] is the
    emissions produced by dispatching a fuel-based project in units of
    metric tonnes CO2 per hour. This is derived from the fuel
    consumption GenFuelUseRate, the fuel's direct carbon intensity, the
    fuel's upstream emissions, as well as Carbon Capture efficiency for
    generators that implement Carbon Capture and Sequestration. This does
    not yet support multi-fuel generators.

    AnnualEmissions[p in PERIODS]:The system's annual emissions, in metric
    tonnes of CO2 per year.

    GenFuelUseRate_Calculate[(g, t) in GEN_TPS]
    calculates fuel consumption for the variable GenFuelUseRate as
    DispatchGen * gen_full_load_heat_rate. The units become:
    MW * (MMBtu / MWh) = MMBTU / h

    DispatchGenByFuel[(g, t, f) in GEN_TP_FUELS]
    calculates power production by each project from each fuel during
    each timepoint. 

    CCS_EQUIPPED_GENS

    gen_ccs_capture_efficiency[g]

    gen_ccs_energy_load[g]

    """

    mod.gen_uses_fuel = Param(
        mod.GENERATION_PROJECTS,
        initialize=lambda m, g: (
            m.gen_energy_source[g] in m.FUELS
                or m.gen_energy_source[g] == "multiple"))
    mod.NON_FUEL_BASED_GENS = Set(
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: not m.gen_uses_fuel[g])
    mod.FUEL_BASED_GENS = Set(
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: m.gen_uses_fuel[g])

    mod.gen_full_load_heat_rate = Param(
        mod.FUEL_BASED_GENS,
        within=NonNegativeReals)
    mod.MULTIFUEL_GENS = Set(
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: m.gen_energy_source[g] == "multiple")
    mod.FUELS_FOR_MULTIFUEL_GEN = Set(mod.MULTIFUEL_GENS, within=mod.FUELS)
    mod.FUELS_FOR_GEN = Set(mod.FUEL_BASED_GENS,
        initialize=lambda m, g: (
            m.FUELS_FOR_MULTIFUEL_GEN[g]
            if g in m.MULTIFUEL_GENS
            else [m.gen_energy_source[g]]))

    def GENS_BY_ENERGY_SOURCE_init(m, e):
        if not hasattr(m, 'GENS_BY_ENERGY_dict'):
            m.GENS_BY_ENERGY_dict = {_e: [] for _e in m.ENERGY_SOURCES}
            for g in m.GENERATION_PROJECTS:
                if g in m.FUEL_BASED_GENS:
                    for f in m.FUELS_FOR_GEN[g]:
                        m.GENS_BY_ENERGY_dict[f].append(g)
                else:
                    m.GENS_BY_ENERGY_dict[m.gen_energy_source[g]].append(g)
        result = m.GENS_BY_ENERGY_dict.pop(e)
        if not m.GENS_BY_ENERGY_dict:
            del m.GENS_BY_ENERGY_dict
        return result
    mod.GENS_BY_ENERGY_SOURCE = Set(
        mod.ENERGY_SOURCES,
        initialize=GENS_BY_ENERGY_SOURCE_init
    )
    mod.GENS_BY_NON_FUEL_ENERGY_SOURCE = Set(
        mod.NON_FUEL_ENERGY_SOURCES,
        initialize=lambda m, s: m.GENS_BY_ENERGY_SOURCE[s]
    )
    mod.GENS_BY_FUEL = Set(
        mod.FUELS,
        initialize=lambda m, f: m.GENS_BY_ENERGY_SOURCE[f]
    )

    mod.FUEL_BASED_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp)
                for g in m.FUEL_BASED_GENS
                    for tp in m.TPS_FOR_GEN[g]))
    
    mod.GEN_TP_FUELS = Set(
        dimen=3,
        initialize=lambda m: (
            (g, t, f)
                for (g, t) in m.FUEL_BASED_GEN_TPS
                    for f in m.FUELS_FOR_GEN[g]))

    mod.GenFuelUseRate = Var(
        mod.GEN_TP_FUELS,
        within=NonNegativeReals,
        doc=("Other modules constraint this variable based on DispatchGen and "
             "module-specific formulations of unit commitment and heat rates."))

    def DispatchEmissions_rule(m, g, t, f):
        if g not in m.CCS_EQUIPPED_GENS:
            return (
                m.GenFuelUseRate[g, t, f] *
                (m.f_co2_intensity[f] + m.f_upstream_co2_intensity[f]))
        else:
            ccs_emission_frac = 1 - m.gen_ccs_capture_efficiency[g]
            return (
                m.GenFuelUseRate[g, t, f] *
                (m.f_co2_intensity[f] * ccs_emission_frac +
                 m.f_upstream_co2_intensity[f]))
    mod.DispatchEmissions = Expression(
        mod.GEN_TP_FUELS,
        rule=DispatchEmissions_rule)
    mod.AnnualEmissions = Expression(mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period),
        doc="The system's annual emissions, in metric tonnes of CO2 per year.")

    mod.GenFuelUseRate_Calculate = Constraint(
        mod.FUEL_BASED_GEN_TPS,
        rule=lambda m, g, t: (
            sum(m.GenFuelUseRate[g, t, f] for f in m.FUELS_FOR_GEN[g])
            == m.DispatchGen[g, t] * m.gen_full_load_heat_rate[g]))

    mod.CCS_EQUIPPED_GENS = Set(within=mod.GENERATION_PROJECTS)
    mod.gen_ccs_capture_efficiency = Param(
        mod.CCS_EQUIPPED_GENS, within=PercentFraction)
    mod.gen_ccs_energy_load = Param(
        mod.CCS_EQUIPPED_GENS, within=PercentFraction)

    mod.ZoneTotalCCSLoad = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t: \
            - sum(m.DispatchGen[p, t] * m.gen_ccs_energy_load[p]
                for p in m.GENS_IN_ZONE[z]
                if (p, t) in m.NON_STORAGE_GEN_TPS and p in m.CCS_EQUIPPED_GENS),
        doc="Net power from grid-tied generation projects.")
    mod.Zone_Power_Injections.append('ZoneTotalCCSLoad')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import data describing fuels. 
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        optional_params=['gen_ccs_energy_load', 'gen_ccs_capture_efficiency'],
        index=mod.GENERATION_PROJECTS,
        param=(mod.gen_ccs_energy_load, mod.gen_ccs_capture_efficiency, mod.gen_full_load_heat_rate))
    # Construct sets of ccs-capable projects.
    if 'gen_ccs_capture_efficiency' in switch_data.data():
        switch_data.data()['CCS_EQUIPPED_GENS'] = {
            None: list(switch_data.data(name='gen_ccs_capture_efficiency').keys())}
    # read FUELS_FOR_MULTIFUEL_GEN from gen_multiple_fuels.dat if available
    multi_fuels_path = os.path.join(inputs_dir, 'gen_multiple_fuels.csv')
    if os.path.isfile(multi_fuels_path):
        switch_data.load(filename=multi_fuels_path)

def post_solve(instance, outdir):
    """
    """

    fuel_data = [{
        "generation_project": g,
        "gen_energy_source": instance.gen_energy_source[g],
        "timestamp": instance.tp_timestamp[t],
        "DispatchGen_MW": value(instance.DispatchGen[g, t]),
        "DispatchEmissions_tCO2_per_typical_yr": value(sum(
            instance.DispatchEmissions[g, t, f] * instance.tp_weight_in_year[t]
              for f in instance.FUELS_FOR_GEN[g]
        )) if instance.gen_uses_fuel[g] else 0
    } for g, t in instance.FUEL_BASED_GEN_TPS]
    fuel_df = pd.DataFrame(fuel_data)
    fuel_df.set_index(["generation_project", "timestamp"], inplace=True)
    fuel_df.to_csv(os.path.join(outdir, "fuels.csv"))