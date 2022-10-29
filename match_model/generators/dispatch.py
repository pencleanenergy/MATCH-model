# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which can be found at http://www.apache.org/licenses/LICENSE-2.0.

# Modifications copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
Defines model components to describe generation projects build-outs for
the MATCH model.

"""
from __future__ import division

import os
import collections
from pyomo.environ import *
from match_model.reporting import write_table
import pandas as pd

dependencies = (
    "match_model.timescales",
    "match_model.balancing.load_zones",
    "match_model.financials",
    "match_model.generators.build",
)


def define_arguments(argparser):
    argparser.add_argument(
        "--sell_excess_RECs",
        choices=["none", "sell"],
        default="none",
        help="Whether or not to consider the resale value of excess RECs in the objective function. "
        "Specify 'none' to disable.",
    )


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

    gen_forced_outage_rate[g] and baseload_gen_scheduled_outage_rate[g]
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

    Adds components to a Pyomo abstract model object to constrain
    dispatch decisions subject to available capacity, renewable resource
    availability, and baseload restrictions. Unless otherwise stated,
    all power capacity is specified in units of MW and all sets and
    parameters are mandatory. This module estimates project dispatch
    limits and fuel consumption without consideration of unit
    commitment. This can be a useful approximation if fuel startup
    requirements are a small portion of overall fuel consumption, so
    that the aggregate fuel consumption with respect to energy
    production can be approximated as a line with a 0 intercept. This
    estimation method has been known to result in excessive cycling of
    Combined Cycle Gas Turbines in the Switch-WECC model.

    DispatchUpperLimit[(g, t) in GEN_TPS] is an
    expression that defines the upper bounds of dispatch subject to
    installed capacity, average expected outage rates, and renewable
    resource availability.

    DispatchLowerLimit[(g, t) in GEN_TPS] in an
    expression that defines the lower bounds of dispatch, which is 0
    except for baseload plants where is it the upper limit.

    Enforce_Dispatch_Lower_Limit[(g, t) in GEN_TPS] and
    Enforce_Dispatch_Upper_Limit[(g, t) in GEN_TPS] are
    constraints that limit DispatchGen to the upper and lower bounds
    defined above.

        DispatchLowerLimit <= DispatchGen <= DispatchUpperLimit

    """

    def period_active_gen_rule(m, period):
        if not hasattr(m, "period_active_gen_dict"):
            m.period_active_gen_dict = collections.defaultdict(set)
            for (_g, _period) in m.GEN_PERIODS:
                m.period_active_gen_dict[_period].add(_g)
        result = m.period_active_gen_dict.pop(period)
        if len(m.period_active_gen_dict) == 0:
            delattr(m, "period_active_gen_dict")
        return result

    mod.GENS_IN_PERIOD = Set(
        mod.PERIODS,
        initialize=period_active_gen_rule,
        ordered=False,
        doc="The set of projects active in a given period.",
    )

    mod.TPS_FOR_GEN = Set(
        mod.GENERATION_PROJECTS,
        within=mod.TIMEPOINTS,
        initialize=lambda m, g: (
            tp for p in m.PERIODS_FOR_GEN[g] for tp in m.TPS_IN_PERIOD[p]
        ),
    )

    mod.GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.GENERATION_PROJECTS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.VARIABLE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.VARIABLE_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.BASELOAD_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.BASELOAD_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.NON_STORAGE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.NON_STORAGE_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )

    mod.rec_resale_value = Param(mod.PERIODS, within=NonNegativeReals, default=0)

    mod.GenCapacityInTP = Expression(
        mod.GEN_TPS, rule=lambda m, g, t: m.GenCapacity[g, m.tp_period[t]]
    )

    def init_gen_availability(m, g):
        if m.gen_is_baseload[g]:
            return (1 - m.gen_forced_outage_rate[g]) * (
                1 - m.baseload_gen_scheduled_outage_rate[g]
            )
        elif m.gen_tech[g] == "Solar_PV":
            year = sum(m.period_start[p] for p in m.PERIODS_FOR_GEN[g])
            project_age = year - m.cod_year[g]
            if project_age < 0:
                project_age = 0
            # calculate solar degredation assuming 0.5% per year linear panel degredation
            return (1 - m.gen_forced_outage_rate[g]) * (1 - (0.005 * (project_age)))
        else:
            return 1 - m.gen_forced_outage_rate[g]

    mod.gen_availability = Param(
        mod.NON_STORAGE_GENS, within=NonNegativeReals, initialize=init_gen_availability
    )

    mod.VARIABLE_GEN_TPS_RAW = Set(dimen=2, within=mod.VARIABLE_GENS * mod.TIMEPOINTS)
    mod.variable_capacity_factor = Param(
        mod.VARIABLE_GEN_TPS_RAW,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2,
    )
    # Validate that a variable_capacity_factor has been defined for every
    # variable gen / timepoint that we need. Extra cap factors (like beyond an
    # existing plant's lifetime) shouldn't cause any problems.
    mod.have_minimal_variable_capacity_factors = BuildCheck(
        mod.VARIABLE_GEN_TPS, rule=lambda m, g, t: (g, t) in m.VARIABLE_GEN_TPS_RAW
    )

    mod.BASELOAD_GEN_TPS_RAW = Set(dimen=2, within=mod.BASELOAD_GENS * mod.TIMEPOINTS)

    mod.baseload_capacity_factor = Param(
        mod.BASELOAD_GEN_TPS_RAW,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2,
    )

    mod.DispatchGen = Var(mod.NON_STORAGE_GEN_TPS, within=NonNegativeReals)

    mod.ZoneTotalGeneratorDispatch = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: sum(
            m.DispatchGen[g, t]
            for g in m.GENS_IN_ZONE[z]
            if (g, t) in m.NON_STORAGE_GEN_TPS
        ),
        doc="Generation from generation projects.",
    )
    mod.Zone_Power_Injections.append("ZoneTotalGeneratorDispatch")

    mod.GenPPACostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.DispatchGen[g, t] * (m.ppa_energy_cost[g])
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
            if g in m.NON_STORAGE_GENS
        ),
        doc="Summarize costs for the objective function",
    )
    mod.Cost_Components_Per_TP.append("GenPPACostInTP")

    # ECONOMIC CURTAILMENT
    ######################
    mod.curtailment_capacity_factor = Param(
        mod.VARIABLE_GEN_TPS_RAW,
        within=NonNegativeReals,
    )
    mod.CurtailmentUpperLimit = Expression(
        mod.VARIABLE_GEN_TPS,
        rule=lambda m, g, t: m.GenCapacityInTP[g, t]
        * m.gen_availability[g]
        * m.curtailment_capacity_factor[g, t],
    )

    mod.CurtailGen = Var(mod.VARIABLE_GEN_TPS, within=NonNegativeReals)

    mod.Enforce_Curtailment_Only_When_LMP_negative = Constraint(
        mod.VARIABLE_GEN_TPS,
        rule=lambda m, g, t: m.CurtailGen[g, t] <= m.CurtailmentUpperLimit[g, t],
    )

    mod.GenCurtailedEnergyCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.CurtailGen[g, t] * (m.ppa_energy_cost[g])
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
            if g in m.VARIABLE_GENS
        ),
        doc="Summarize costs for the objective function",
    )
    mod.Cost_Components_Per_TP.append("GenCurtailedEnergyCostInTP")

    mod.ZoneTotalCurtailmentDispatch = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: sum(
            m.CurtailGen[g, t]
            for g in m.GENS_IN_ZONE[z]
            if (g, t) in m.VARIABLE_GEN_TPS
        ),
        doc="Curtailment from variable generation projects.",
    )

    # DISPATCH UPPER LIMITS
    #######################

    def DispatchUpperLimit_expr(m, g, t):
        if g in m.VARIABLE_GENS:
            return (
                m.GenCapacityInTP[g, t]
                * m.gen_availability[g]
                * m.variable_capacity_factor[g, t]
            )
        elif g in m.BASELOAD_GENS:
            return (
                m.GenCapacityInTP[g, t]
                * m.gen_availability[g]
                * m.baseload_capacity_factor[g, t]
            )
        else:
            return m.GenCapacityInTP[g, t] * m.gen_availability[g]

    mod.DispatchUpperLimit = Expression(
        mod.NON_STORAGE_GEN_TPS, rule=DispatchUpperLimit_expr
    )

    def EnforceDispatchUpperLimit_rule(m, g, t):
        if g in m.VARIABLE_GENS:
            return (
                m.DispatchGen[g, t] + m.CurtailGen[g, t] <= m.DispatchUpperLimit[g, t]
            )
        elif g in m.BASELOAD_GENS:
            return m.DispatchGen[g, t] == m.DispatchUpperLimit[g, t]
        else:
            return m.DispatchGen[g, t] <= m.DispatchUpperLimit[g, t]

    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.NON_STORAGE_GEN_TPS, rule=EnforceDispatchUpperLimit_rule
    )

    # EXCESS GENERATION
    ###################
    def ExcessGen_rule(m, g, t):
        if g in m.VARIABLE_GENS:
            return m.DispatchUpperLimit[g, t] - m.DispatchGen[g, t] - m.CurtailGen[g, t]
        else:
            return m.DispatchUpperLimit[g, t] - m.DispatchGen[g, t]

    mod.ExcessGen = Expression(mod.VARIABLE_GEN_TPS, rule=ExcessGen_rule)

    mod.TotalGen = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g, t] + m.ExcessGen[g, t])
        if m.gen_is_variable[g]
        else m.DispatchGen[g, t],
    )

    mod.AnnualTotalGen = Expression(
        mod.NON_STORAGE_GENS,
        mod.PERIODS,
        rule=lambda m, g, p: sum(
            m.TotalGen[g, t] for t in m.TIMEPOINTS if m.tp_period[t] == p
        ),
    )

    mod.ZoneTotalExcessGen = Expression(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: sum(
            m.ExcessGen[g, t] for g in m.GENS_IN_ZONE[z] if (g, t) in m.VARIABLE_GEN_TPS
        ),
    )

    # calculate the total excess energy for each variable generator in each period
    def Calculate_Annual_Excess_Energy_By_Gen(m, g, p):
        excess = sum(
            m.ExcessGen[g, t]
            for t in m.TIMEPOINTS  # for each timepoint
            if m.tp_period[t]
            == p  # if the timepoint is in the current period and the generator is variable
        )
        return excess

    mod.AnnualExcessGen = Expression(
        mod.VARIABLE_GENS,
        mod.PERIODS,  # for each variable generator in each period
        rule=Calculate_Annual_Excess_Energy_By_Gen,
    )  # calculate a value according to the rule

    mod.ExcessGenPPACostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.ExcessGen[g, t] * (m.ppa_energy_cost[g])
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
            if g in m.VARIABLE_GENS
        ),
        doc="Summarize costs for the objective function",
    )
    mod.Cost_Components_Per_TP.append("ExcessGenPPACostInTP")

    if mod.options.sell_excess_RECs == "sell":
        mod.ExcessRECValue = Expression(
            mod.PERIODS,
            rule=lambda m, p: sum(m.AnnualExcessGen[g, p] for g in m.VARIABLE_GENS)
            * -m.rec_resale_value[p],
        )

        # add to objective function
        mod.Cost_Components_Per_Period.append("ExcessRECValue")


def load_inputs(mod, match_data, inputs_dir):
    """

    Import project-specific data from an input directory.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.csv
        GENERATION_PROJECT, timepoint, variable_capacity_factor

    """

    match_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "variable_capacity_factors.csv"),
        autoselect=True,
        index=mod.VARIABLE_GEN_TPS_RAW,
        param=[mod.variable_capacity_factor, mod.curtailment_capacity_factor],
    )

    match_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "baseload_capacity_factors.csv"),
        autoselect=True,
        index=mod.BASELOAD_GEN_TPS_RAW,
        param=[mod.baseload_capacity_factor],
    )

    match_data.load_aug(
        filename=os.path.join(inputs_dir, "rec_value.csv"),
        select=("period", "rec_resale_value"),
        param=[mod.rec_resale_value],
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

    gen_data = [
        {
            "generation_project": g,
            "timestamp": instance.tp_timestamp[t],
            "DispatchGen_MW": value(instance.DispatchGen[g, t]),
            "ExcessGen_MW": value(instance.ExcessGen[g, t])
            if instance.gen_is_variable[g]
            else 0,
            "CurtailGen_MW": value(instance.CurtailGen[g, t])
            if instance.gen_is_variable[g]
            else 0,
            "Nodal_Price": value(instance.nodal_price[instance.gen_pricing_node[g], t]),
        }
        for g, t in instance.NON_STORAGE_GEN_TPS
    ]
    dispatch_full_df = pd.DataFrame(gen_data)
    dispatch_full_df.set_index(["generation_project", "timestamp"], inplace=True)
    dispatch_full_df.to_csv(os.path.join(outdir, "dispatch.csv"))
