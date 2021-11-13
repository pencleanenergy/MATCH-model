# Copyright (c) 2021 The MATCH Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines the type of renewable energy goal and allows for load to be served by grid/system power.

"""

import os
from sys import modules
from pyomo.environ import *
import pandas as pd

dependencies = 'switch_model.timescales', 'switch_model.generators.core.dispatch', \
    'switch_model.balancing.load_zones', 'switch_model.financials'

def define_arguments(argparser):
    argparser.add_argument('--goal_type', choices=['annual', 'hourly'], default='hourly',
        help="Whether generators must be dispatched to meet an annual or hourly renewable target"
        "An annual goal requires the total annual volume of renewable generation to be greater than the percentage of total annual load"
        "Generation can be located in any LOAD_ZONE to meet an annual target"
        "An hourly goal requires renewable generation to be greater than the percentage of hourly time- and location-coincident load"
        "Generation must be located in the same LOAD_ZONE as load to be counted toward an hourly goal"
    )

    argparser.add_argument('--excess_generation_limit_type', choices=['annual', 'hourly', None], default=None,
        help="If specified, whether the limit on excess generation is applied to each hour, or to the entire year"
    )

def define_components(mod):
    """
    renewable_target[p] is a parameter that describes how much of load (as a percentage) must be served by GENERATION_PROJECTS.
    This assumes that all GENERATION_PROJECTS are renewable generators that count toward the goal.

    hedge_contract_cost[z,t] is a parameter that describes the cost of system/grid power ($/MWh) for each timepoint in each load zone. 
    This could describe wholesale prices of electricity at the demand node or your utility rate structure 
    (whereever you will be buying energy from if not procuring from one of the GENERATION_PROJECTS)

    SystemPower[z, t] is a decision variable for how many average MW of grid power to use to meet demand in each timepoint in each zone. 
    This decision variable is considered a power injection in the load balance equation. 

    SystemPowerCost[t] is an expression that summarizes the total cost of consuming system power at a given timepoint

    AnnualSystemPower[z,p] is an expression that describes the total system power used in each zone in each period (year)

    Enforce_Hourly_Renewable_Target[z,p] is a contraint that requires time coincident renewable generation from GENERATION_PROJECTS to 
    meet or exceed the renewable_target. It is defined by requiring the percentage of system power used to be less than 1 - the target.


    total_demand_in_period[p] is an expression that sums the annual energy demand across all load zones for each period

    total_generation_in_period[p] is an expression that sums the annual renewable generation from all generators for each period

    Enforce_Annual_Renewable_Target[p] is a constraint that requires the total annual  renewable generation to be greater or equal to the percentage
    of total annual load equal to the target.

    """

    mod.renewable_target = Param(
        mod.PERIODS,
        default=0,
        within=PercentFraction)

    mod.excess_generation_limit = Param(
        mod.PERIODS,
        within=PercentFraction)

    # if no hedge cost is specified, set the cost to a very small amount
    # This discourages use of system power 
    mod.hedge_contract_cost = Param(
        mod.ZONE_TIMEPOINTS,
        within=Reals,
        default=0.001)

    mod.hedge_settlement_node = Param(
        mod.LOAD_ZONES,
        within=Any
    )
    
    #implementation of system power as a decision variable
    mod.SystemPower = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonNegativeReals
    )
    #add system power to the power balance equation
    mod.Zone_Power_Injections.append('SystemPower')

    #calculate the cost of using system power for the objective function
    mod.HedgeContractCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(m.SystemPower[z, t] * m.hedge_contract_cost[z, t] for z in m.LOAD_ZONES) 
    )
    mod.Cost_Components_Per_TP.append('HedgeContractCostInTP')
    

    if mod.options.goal_type == "hourly":
        

        #calculate annual system power
        mod.AnnualSystemPower = Expression(
            mod.LOAD_ZONES, mod.PERIODS,
            rule=lambda m, z, p: sum(m.SystemPower[z,t] for t in m.TIMEPOINTS)
        )

        mod.Enforce_Hourly_Renewable_Target = Constraint(
            mod.PERIODS, mod.LOAD_ZONES, # for each zone in each period
            rule=lambda m, p, z: (
                m.AnnualSystemPower[z,p] <= ((1 - m.renewable_target[p]) * m.zone_total_demand_in_period_mwh[z,p]))
        )

        
    elif mod.options.goal_type == "annual":

        # Calculate the total demand in all zones
        mod.total_demand_in_period = Expression(
            mod.PERIODS,
            rule=lambda m, p: sum(m.zone_total_demand_in_period_mwh[z, p]
                for z in m.LOAD_ZONES))

        # Calculate the total generation in the period
        mod.total_generation_in_period = Expression(
            mod.PERIODS,
            rule=lambda m, p: sum(m.ZoneTotalGeneratorDispatch[z,t] + m.ZoneTotalExcessGen[z,t] for (z,t) in m.ZONE_TIMEPOINTS if m.tp_period[t] == p)
        )

        # if there are any storage generators in the model
        try:
            mod.total_storage_losses_in_period = Expression(
                mod.PERIODS,
                rule=lambda m, p: sum(m.ZoneTotalStorageCharge[z,t] - m.ZoneTotalStorageDischarge[z,t] for (z,t) in m.ZONE_TIMEPOINTS if m.tp_period[t] == p)
            )
        except:
            mod.total_storage_losses_in_period = Param(
                mod.PERIODS,
                default=0
            )

        mod.Enforce_Annual_Renewable_Target = Constraint(
            mod.PERIODS, # for each zone in each period
            rule=lambda m, p: (m.total_generation_in_period[p] - m.total_storage_losses_in_period[p] >= m.renewable_target[p] * m.total_demand_in_period[p]))

    #Enforce limit on excess generation
    if mod.options.excess_generation_limit_type == "annual":
        mod.Enforce_Annual_Excess_Generation_Limit = Constraint(
            mod.LOAD_ZONES, mod.PERIODS,
            rule = lambda m, z, p: sum(m.ZoneTotalExcessGen[z,t] for t in m.TPS_IN_PERIOD[p]) <= sum(m.zone_demand_mw[z,t] for t in m.TPS_IN_PERIOD[p]) * m.excess_generation_limit[p]
        )
    elif mod.options.excess_generation_limit_type == "hourly":
        mod.Enforce_Hourly_Excess_Generation_Limit = Constraint(
            mod.LOAD_ZONES, mod.TIMEPOINTS,
            rule = lambda m, z, t: m.ZoneTotalExcessGen[z,t] <= m.zone_demand_mw[z,t] * m.excess_generation_limit[m.tp_period[t]]
        )

        

def load_inputs(mod, switch_data, inputs_dir):
    """
    Import renewable target, system power data parameters

    renewable_target.csv
        period, renewable_target

    hedge_contract_cost.csv
        load_zone, timepoint, hedge_contract_cost

    """

    #load the renewable target
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'renewable_target.csv'),
        autoselect=True,
        param=[mod.renewable_target, mod.excess_generation_limit])

    #load inputs which include costs for each timepoint in each zone
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'hedge_contract_cost.csv'),
        select=('load_zone','timepoint','hedge_contract_cost'),
        param=[mod.hedge_contract_cost])

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'hedge_settlement_node.csv'),
        select=('load_zone','hedge_settlement_node'),
        param=[mod.hedge_settlement_node])


def post_solve(instance, outdir):
    """
    Exported files:

    system_power.csv: the amount and cost of system power dispatched in each timepoint
    """

    system_power_dat = [{
        "timestamp": instance.tp_timestamp[t],
        "load_zone": z,
        "system_power_MW":value(instance.SystemPower[z,t]),
        "hedge_contract_cost_per_MWh":instance.hedge_contract_cost[z,t],
        "hedge_contract_cost": value(
            instance.SystemPower[z,t] * instance.hedge_contract_cost[z,t] *
            instance.tp_weight_in_year[t]),
        "hedge_market_revenue": value(instance.SystemPower[z,t] * - instance.nodal_price[instance.hedge_settlement_node[z],t]),
    } for z, t in instance.ZONE_TIMEPOINTS ]
    SP_df = pd.DataFrame(system_power_dat)
    SP_df.set_index(["load_zone","timestamp"], inplace=True)
    SP_df.to_csv(os.path.join(outdir, "system_power.csv"))
