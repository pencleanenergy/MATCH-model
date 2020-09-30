# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines simple limitations on project dispatch without considering unit
commitment. This module is mutually exclusive with the operations.unitcommit
module which constrains dispatch to unit commitment decisions.
"""
import os
from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties.properties', \
    'switch_model.generators.core.build', 'switch_model.generators.core.dispatch'

def define_components(mod):
    """

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

    GenFuelUseRate_Calculate[(g, t) in GEN_TPS]
    calculates fuel consumption for the variable GenFuelUseRate as
    DispatchGen * gen_full_load_heat_rate. The units become:
    MW * (MMBtu / MWh) = MMBTU / h

    DispatchGenByFuel[(g, t, f) in GEN_TP_FUELS]
    calculates power production by each project from each fuel during
    each timepoint.

    """

    # NOTE: DispatchBaseloadByPeriod should eventually be replaced by
    # an "ActiveCapacityDuringPeriod" decision variable that applies to all
    # projects. This should be constrained
    # based on the amount of installed capacity each period, and then
    # DispatchUpperLimit and DispatchLowerLimit should be calculated
    # relative to ActiveCapacityDuringPeriod. Fixed O&M (but not capital
    # costs) should be calculated based on ActiveCapacityDuringPeriod.
    # This would allow mothballing (and possibly restarting) projects.

    # Choose flat operating level for baseload plants during each period
    # (not necessarily running all available capacity)
    # Note: this is unconstrained, because other constraints limit project
    # dispatch during each timepoint and therefore the level of this variable.
    # TODO: this should be harmonized with the treatment of baseload generators
    # in generators.core.commit, where baseload just means they will all be
    # committed all the time, but not required to run at a constant output
    # level. That's the definition of baseload used in the Hawaii power system,
    # while the definition used here is more like common usage (run at a flat level
    # or don't run). Since there are multiple meanings, we should probably
    # have separate parameters for constant_output and always_commit. Or
    # we could implement those via time-varying values for min/max commitment
    # and dispatch. 
    mod.BASELOAD_GEN_PERIODS = Set(
        dimen=2,
        rule=lambda m:
            [(g, p) for g in m.BASELOAD_GENS for p in m.PERIODS_FOR_GEN[g]])
    mod.BASELOAD_GEN_TPS = Set(
        dimen=2,
        rule=lambda m:
            [(g, t) for g, p in m.BASELOAD_GEN_PERIODS for t in m.TPS_IN_PERIOD[p]])

    mod.DispatchBaseloadByPeriod = Var(mod.BASELOAD_GEN_PERIODS)

    def DispatchUpperLimit_expr(m, g, t):
        if g in m.VARIABLE_GENS:
            return (m.GenCapacityInTP[g, t] * m.gen_availability[g] *
                    m.gen_max_capacity_factor[g, t])
        else:
            return m.GenCapacityInTP[g, t] * m.gen_availability[g]
    mod.DispatchUpperLimit = Expression(
        mod.GEN_TPS,
        rule=DispatchUpperLimit_expr)

    
    
    mod.ExcessByGen = Expression(
        mod.VARIABLE_GENS, mod.TIMEPOINTS, #for each variable generator in each period
        rule=lambda m, g, t: (m.DispatchUpperLimit[g, t] - m.DispatchGen[g, t]) #calculate a value according to the rule 
    )
    
    #calculate the total excess energy for each variable generator in each period
    def Calculate_Annual_Excess_Energy_By_Gen(m, g, p):
        excess = sum(
            (m.ExcessByGen[g, t]) #subtract dispatched generation from the upper limit
            for t in m.TIMEPOINTS #for each timepoint
            if m.tp_period[t] == p and m.gen_is_variable[g] #if the timepoint is in the current period and the generator is variable
        )
        return excess
    mod.AnnualExcessByGen = Expression(
        mod.VARIABLE_GENS, mod.PERIODS, #for each variable generator in each period
        rule=Calculate_Annual_Excess_Energy_By_Gen #calculate a value according to the rule 
    )

    #define the input parameter for the annual number of hours of curtialment/excess gen allowed
    mod.gen_excess_max = Param(mod.VARIABLE_GENS, within=NonNegativeReals, default=float("inf"))

    #limit curtailment to below the cap
    mod.max_AnnualExcessByGen = Constraint(
        mod.VARIABLE_GENS, mod.PERIODS, #for each variable generator in each period
        rule=lambda m, g, p: Constraint.Skip if m.gen_excess_max[g] == float("inf")
        else
        (m.AnnualExcessByGen[g,p] <= (m.gen_excess_max[g] * m.GenCapacity[g, p]))
    )
    """
    #calculate the total amount of free curtailment that a variable generator is allowed per year
    def Calculate_Free_Curtailment(m, g, p):
        if m.gen_is_variable[g]:
            return (m.curtailment_cap[g] * m.GenCapacity[g, p]) #multiply the curtailment cap (hours) by built capacity (MW) to get MWh of curtailment
    mod.FreeCurtailmentCap = Expression(
        mod.VARIABLE_GENS, mod.PERIODS, #for each variable generator in each period
        rule=Calculate_Free_Curtailment  #for each variable generator
    )

    #calculate the cost of each generator exceeding its free curtailment limit

    def Calculate_Curtailment_Cost_By_Gen(m, g, p):
        if m.gen_is_variable[g]: #if the generator is variable

            if m.AnnualExcessByGen[g,p] > m.FreeCurtailmentCap[g,p]:
                excess_curtailment = m.AnnualExcessByGen[g,p] - m.FreeCurtailmentCap[g,p]
            else:
                excess_curtailment = 0

            return (m.AnnualExcessByGen[g,p] * m.gen_ppa_cost[g]) #calculate each generator's curtailment over its free limit and multiply by variable_om cost

    mod.GenCurtailmentCosts = Expression(
        mod.VARIABLE_GENS, mod.TIMEPOINTS, #for each variable generator in each period
        rule=lambda m, g, t: (m.ExcessByGen[g,t] * m.gen_ppa_cost[g,p] for p in m.GENS_IN_PERIOD[m.tp_period[t]])) #calculate curtailment costs
    )

    #sum up the total curtailment costs for all generators in the year
    mod.TotalGenCurtailmentCosts = Expression(
        mod.PERIODS,
        rule = lambda m, p: sum(
            m.GenCurtailmentCosts[g,t]
            for g in m.VARIABLE_GENS for t in m.TIMEPOINTS
        )
    )
    #add this total curtailment cost to the total costs to be minimized in the objective function
    mod.Cost_Components_Per_Period.append('TotalGenCurtailmentCosts')
    """
    mod.ExcessGenCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.ExcessByGen[g, t] * m.ppa_energy_cost[g]
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
            if m.gen_is_variable[g]),
        doc="Summarize costs for the objective function")
    mod.Cost_Components_Per_TP.append('ExcessGenCostInTP')

    mod.Enforce_Dispatch_Baseload_Flat = Constraint(
        mod.BASELOAD_GEN_TPS,
        rule=lambda m, g, t:
            m.DispatchGen[g, t] == m.DispatchBaseloadByPeriod[g, m.tp_period[t]])

    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (
            m.DispatchGen[g, t] <= m.DispatchUpperLimit[g, t]))

    mod.GenFuelUseRate_Calculate = Constraint(
        mod.FUEL_BASED_GEN_TPS,
        rule=lambda m, g, t: (
            sum(m.GenFuelUseRate[g, t, f] for f in m.FUELS_FOR_GEN[g])
            == m.DispatchGen[g, t] * m.gen_full_load_heat_rate[g]))

"""
def load_inputs(mod, switch_data, inputs_dir):
 
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        index=mod.GENERATION_PROJECTS,
        param=(mod.curtailment_cap))
"""
