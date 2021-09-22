# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Modifications copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe generation projects build-outs for
the Switch model. This module requires either generators.core.unitcommit or
generators.core.no_commit to constrain project dispatch to either committed or
installed capacity.

"""
from __future__ import division

import os, collections
from pyomo.environ import *
from switch_model.reporting import write_table
import pandas as pd
try:
    from ggplot import *
    can_plot = True
except:
    can_plot = False

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties', \
    'switch_model.generators.core.build'
optional_dependencies = 'switch_model.transmission.local_td'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe the
    dispatch decisions and constraints of generation and storage
    projects. Unless otherwise stated, all power capacity is specified
    in units of MW and all sets and parameters are mandatory.

    GEN_TPS is a set of projects and timepoints in which
    they can be dispatched. A dispatch decisions is made for each member
    of this set. Members of this set can be abbreviated as (g, t) or
    (g, t).

    TPS_FOR_GEN[g] is a set array showing all timepoints when a
    project is active. These are the timepoints corresponding to
    PERIODS_FOR_GEN. This is the same data as GEN_TPS,
    but split into separate sets for each project.

    TPS_FOR_GEN_IN_PERIOD[g, period] is the same as
    TPS_FOR_GEN, but broken down by period. Periods when
    the project is inactive will yield an empty set.

    GenCapacityInTP[(g, t) in GEN_TPS] is the same as
    GenCapacity but indexed by timepoint rather than period to allow
    more compact statements.

    DispatchGen[(g, t) in GEN_TPS] is the set
    of generation dispatch decisions: how much average power in MW to
    produce in each timepoint. This value can be multiplied by the
    duration of the timepoint in hours to determine the energy produced
    by a project in a timepoint.

    gen_forced_outage_rate[g] and gen_scheduled_outage_rate[g]
    describe the forces and scheduled outage rates for each project.
    These parameters can be specified for individual projects via an
    input file (see load_inputs() documentation), or generically for all
    projects of a given generation technology via
    g_scheduled_outage_rate and g_forced_outage_rate. You will get an
    error if any project is missing values for either of these
    parameters.

    gen_availability[g] describes the fraction of a time a project is
    expected to be available. This is derived from the forced and
    scheduled outage rates of the project. For baseload or flexible
    baseload, this is determined from both forced and scheduled outage
    rates. For all other types of generation technologies, we assume the
    scheduled outages can be performed when the generators were not
    scheduled to produce power, so their availability is only derated
    based on their forced outage rates.

    variable_capacity_factor[g, t] is defined for variable renewable
    projects and is the ratio of average power output to nameplate
    capacity in that timepoint. Most renewable capacity factors should
    be in the range of 0 to 1. Some solar capacity factors will be above
    1 because the nameplate capacity is based on solar radiation of 1.0
    kW/m^2 and solar radiation can exceed that value on very clear days
    or on partially cloudy days when light bounces off the bottom of
    clouds onto a solar panel. Some solar thermal capacity factors can
    be less than 0 because of auxillary loads: for example, parts of
    those plants need to be kept warm during winter nights to avoid
    freezing. Those heating loads can be significant during certain
    timepoints.

    gen_variable_om[g] is the variable Operations and Maintenance
    costs (O&M) per MWh of dispatched capacity for a given project.


    --- Delayed implementation, possibly relegated to other modules. ---

    Flexible baseload support for plants that can ramp slowly over the
    course of days. These kinds of generators can provide important
    seasonal support in high renewable and low emission futures.

    Parasitic loads that make solar thermal plants consume energy from
    the grid on cold nights to keep their fluids from getting too cold.

    Storage support.

    Hybrid project support (pumped hydro & CAES) will eventually get
    implemented in separate modules.

    """

    def period_active_gen_rule(m, period):
        if not hasattr(m, 'period_active_gen_dict'):
            m.period_active_gen_dict = collections.defaultdict(set)
            for (_g, _period) in m.GEN_PERIODS:
                m.period_active_gen_dict[_period].add(_g)
        result = m.period_active_gen_dict.pop(period)
        if len(m.period_active_gen_dict) == 0:
            delattr(m, 'period_active_gen_dict')
        return result
    mod.GENS_IN_PERIOD = Set(mod.PERIODS, initialize=period_active_gen_rule, ordered=False,
        doc="The set of projects active in a given period.")

    mod.TPS_FOR_GEN = Set(
        mod.GENERATION_PROJECTS,
        within=mod.TIMEPOINTS,
        initialize=lambda m, g: (
            tp for p in m.PERIODS_FOR_GEN[g] for tp in m.TPS_IN_PERIOD[p]
        )
    )


    mod.GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp)
                for g in m.GENERATION_PROJECTS
                    for tp in m.TPS_FOR_GEN[g]))
    mod.VARIABLE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp)
                for g in m.VARIABLE_GENS
                    for tp in m.TPS_FOR_GEN[g]))
    mod.BASELOAD_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp)
                for g in m.BASELOAD_GENS
                    for tp in m.TPS_FOR_GEN[g]))
    mod.NON_STORAGE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp)
                for g in m.NON_STORAGE_GENS
                    for tp in m.TPS_FOR_GEN[g]))


    #TODO: Move pricing nodes to a different module
    mod.PRICING_NODES = Set()
    mod.NODE_TIMEPOINTS = Set(dimen=2,
        initialize=lambda m: m.PRICING_NODES * m.TIMEPOINTS,
        doc="The cross product of trading hubs and timepoints, used for indexing.")

    mod.gen_pricing_node = Param(
        mod.GENERATION_PROJECTS, 
        validate=lambda m,val,g: val in m.PRICING_NODES,
        within=Any)
    mod.nodal_price = Param(
        mod.NODE_TIMEPOINTS,
        within=Reals)

    mod.GenCapacityInTP = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: m.GenCapacity[g, m.tp_period[t]])

    def init_gen_availability(m, g):
        if m.gen_is_baseload[g]:
            return (
                (1 - m.gen_forced_outage_rate[g]) *
                (1 - m.gen_scheduled_outage_rate[g]))
        else:
            return (1 - m.gen_forced_outage_rate[g])
    mod.gen_availability = Param(
        mod.GENERATION_PROJECTS,
        within=NonNegativeReals,
        initialize=init_gen_availability)

    mod.VARIABLE_GEN_TPS_RAW = Set(
        dimen=2,
        within=mod.VARIABLE_GENS * mod.TIMEPOINTS
    )
    mod.variable_capacity_factor = Param(
        mod.VARIABLE_GEN_TPS_RAW,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2)
    # Validate that a variable_capacity_factor has been defined for every
    # variable gen / timepoint that we need. Extra cap factors (like beyond an
    # existing plant's lifetime) shouldn't cause any problems.
    mod.have_minimal_variable_capacity_factors = BuildCheck(
        mod.VARIABLE_GEN_TPS,
        rule=lambda m, g, t: (g,t) in m.VARIABLE_GEN_TPS_RAW)

    mod.BASELOAD_GEN_TPS_RAW = Set(
        dimen=2,
        within=mod.BASELOAD_GENS * mod.TIMEPOINTS)

    mod.baseload_capacity_factor = Param(
        mod.BASELOAD_GEN_TPS_RAW,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2)
    
    mod.DispatchGen = Var(
        mod.NON_STORAGE_GEN_TPS,
        within=NonNegativeReals)
    
    mod.ZoneTotalGeneratorDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t: \
            sum(m.DispatchGen[g, t]
                for g in m.GENS_IN_ZONE[z]
                if (g, t) in m.NON_STORAGE_GEN_TPS),
        doc="Generation from generation projects.")
    mod.Zone_Power_Injections.append('ZoneTotalGeneratorDispatch')

    mod.GenPPACostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.DispatchGen[g, t] * (m.ppa_energy_cost[g]) 
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
            if g in m.NON_STORAGE_GENS),
        doc="Summarize costs for the objective function")
    mod.Cost_Components_Per_TP.append('GenPPACostInTP')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import project-specific data from an input directory.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.csv
        GENERATION_PROJECT, timepoint, variable_capacity_factor

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'variable_capacity_factors.csv'),
        autoselect=True,
        index=mod.VARIABLE_GEN_TPS_RAW,
        param=[mod.variable_capacity_factor])

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'baseload_capacity_factors.csv'),
        autoselect=True,
        index=mod.BASELOAD_GEN_TPS_RAW,
        param=[mod.baseload_capacity_factor])

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'pricing_nodes.csv'),
        set=mod.PRICING_NODES)
    
    #load wholesale market node data
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'nodal_prices.csv'),
        select=('pricing_node','timepoint','nodal_price'),
        index=mod.NODE_TIMEPOINTS,
        param=[mod.nodal_price]
    )


def post_solve(instance, outdir):
    """
    Exported files:

    dispatch-wide.csv - Dispatch results timepoints in "wide" format with
    timepoints as rows, generation projects as columns, and dispatch level
    as values

    dispatch.csv - Dispatch results in normalized form where each row
    describes the dispatch of a generation project in one timepoint.

    dispatch_annual_summary.csv - Similar to dispatch.csv, but summarized
    by generation technology and period.

    dispatch_zonal_annual_summary.csv - Similar to dispatch_annual_summary.csv
    but broken out by load zone.

    dispatch_annual_summary.pdf - A figure of annual summary data. Only written
    if the ggplot python library is installed.
    """

    gen_data = [{
        "generation_project": g,
        "timestamp": instance.tp_timestamp[t],
        "DispatchGen_MW": value(instance.DispatchGen[g, t]),
        "ExcessGen_MW":value(instance.ExcessGen[g, t]) if instance.gen_is_variable[g] else 0,
        "CurtailGen_MW":value(instance.CurtailGen[g, t]) if instance.gen_is_variable[g] else 0
    } for g, t in instance.NON_STORAGE_GEN_TPS]
    dispatch_full_df = pd.DataFrame(gen_data)
    dispatch_full_df.set_index(["generation_project", "timestamp"], inplace=True)
    dispatch_full_df.to_csv(os.path.join(outdir, "dispatch.csv"))
