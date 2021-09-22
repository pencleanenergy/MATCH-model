# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Modifications copyright (c) 2021 *****************. All rights reserved.
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


    """
    
    # BASELOAD GENERATOR DISPATCH
    #############################
    # baseload generators must be dispatched at their full capacity factor, and cannot have any excessgen
    mod.Enforce_Full_Dispatch_Baseload = Constraint(
        mod.BASELOAD_GEN_TPS,
        rule=lambda m, g, t:
            m.DispatchGen[g, t] == m.GenCapacityInTP[g, t] * m.gen_availability[g] *
                    m.gen_max_capacity_factor[g, t])
    
    # ECONOMIC CURTAILMENT
    ######################
    mod.CurtailGen = Var(
        mod.VARIABLE_GEN_TPS,
        within=NonNegativeReals)

    #limit curtailment to below the cap
    mod.Maximum_Annual_Curtailment = Constraint(
        mod.VARIABLE_GENS, mod.PERIODS,
        rule=lambda m, g, p: sum(m.CurtailGen[g,t] for t in m.TPS_IN_PERIOD[p]) <= (m.gen_curtailment_limit[g] * m.GenCapacity[g, p]))

    # DISPATCH UPPER LIMITS
    #######################

    def DispatchUpperLimit_expr(m, g, t):
        if g in m.VARIABLE_GENS:
            return (m.GenCapacityInTP[g, t] * m.gen_availability[g] *
                    m.gen_max_capacity_factor[g, t])
        else:
            return m.GenCapacityInTP[g, t] * m.gen_availability[g]
    mod.DispatchUpperLimit = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=DispatchUpperLimit_expr)

    # TODO: Add CurtailGen back in
    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: 
            (m.DispatchGen[g, t] + m.CurtailGen[g,t] <= m.DispatchUpperLimit[g, t]) if g in m.VARIABLE_GENS 
            else (m.DispatchGen[g, t] <= m.DispatchUpperLimit[g, t]))

    # EXCESS GENERATION
    ###################
    #TODO: Add CurtailGen back in
    mod.ExcessGen = Expression(
        mod.VARIABLE_GEN_TPS, #for each variable generator in each period
        rule=lambda m, g, t: m.DispatchUpperLimit[g, t] - m.DispatchGen[g, t] - m.CurtailGen[g,t] if g in m.VARIABLE_GENS else 0 #calculate a value according to the rule 
    )

    mod.ZoneTotalExcessGen = Expression(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: \
            sum(m.ExcessGen[g, t]
                for g in m.GENS_IN_ZONE[z]
                if (g, t) in m.VARIABLE_GEN_TPS),
    )
    
    #calculate the total excess energy for each variable generator in each period
    def Calculate_Annual_Excess_Energy_By_Gen(m, g, p):
        excess = sum(m.ExcessGen[g, t] 
            for t in m.TIMEPOINTS #for each timepoint
            if m.tp_period[t] == p #if the timepoint is in the current period and the generator is variable
        )
        return excess
    mod.AnnualExcessGen = Expression(
        mod.VARIABLE_GENS, mod.PERIODS, #for each variable generator in each period
        rule=Calculate_Annual_Excess_Energy_By_Gen #calculate a value according to the rule 
    )

    mod.ExcessGenPPACostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.ExcessGen[g, t] * (m.ppa_energy_cost[g])
            for g in m.GENS_IN_PERIOD[m.tp_period[t]] if g in m.VARIABLE_GENS),
        doc="Summarize costs for the objective function")
    mod.Cost_Components_Per_TP.append('ExcessGenPPACostInTP')
