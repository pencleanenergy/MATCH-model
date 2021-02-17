# Copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines the type of renewable energy goal and allows for load to be served by grid/system power.

"""

import os
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

def define_components(mod):
    """
    renewable_target[p] is a parameter that describes how much of load (as a percentage) must be served by GENERATION_PROJECTS.
    This assumes that all GENERATION_PROJECTS are renewable generators that count toward the goal.

    system_power_cost[z,t] is a parameter that describes the cost of system/grid power ($/MWh) for each timepoint in each load zone. 
    This could describe wholesale prices of electricity at the demand node or your utility rate structure 
    (whereever you will be buying energy from if not procuring from one of the GENERATION_PROJECTS)

    SystemPower[z, t] is a decision variable for how many average MW of grid power to use to meet demand in each timepoint in each zone. 
    This decision variable is considered a power injection in the load balance equation. 

    SystemPowerCost[t] is an expression that summarizes the total cost of consuming system power at a given timepoint

    AnnualSystemPower[z,p] is an expression that describes the total system power used in each zone in each period (year)

    Enforce_Hourly_Renewable_Target[z,p] is a contraint that requires time coincident renewable generation from GENERATION_PROJECTS to 
    meet or exceed the renewable_target. It is defined by requiring the percentage of system power used to be less than 1 - the target.

    tp_in_subset[t] is a parameter that defines whether a timepoint happens during a subset period, during which all load must be met with
    time-coincident dispatch from GENERATION_PROJECTS.

    SUBSET_TIMEPOINTS is the set of all timepoints in the subset period.

    Enforce_Time_Coincidence_During_Subset[z,t] is a constraint that requires time-coincident dispatch from all generators in a zone to be 
    greater or equal to the amount of load in each timepoint. This is useful if you only want to achieve time-coincident generation on a 
    specific peak day or during a specific season.

    total_demand_in_period[p] is an expression that sums the annual energy demand across all load zones for each period

    total_generation_in_period[p] is an expression that sums the annual renewable generation from all generators for each period

    Enforce_Annual_Renewable_Target[p] is a constraint that requires the total annual  renewable generation to be greater or equal to the percentage
    of total annual load equal to the target.

    """

    mod.renewable_target = Param(
        mod.PERIODS,
        default=1,
        within=PercentFraction)

    mod.system_power_cost = Param(
        mod.ZONE_TIMEPOINTS,
        within=Reals)

    mod.tp_in_subset = Param(mod.TIMEPOINTS, within=Boolean, default=False)
    
    #implementation of system power as a decision variable
    mod.SystemPower = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonNegativeReals
    )
    #add system power to the power balance equation
    mod.Zone_Power_Injections.append('SystemPower')

    #calculate the cost of using system power for the objective function
    mod.SystemPowerCost = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(m.SystemPower[z, t] * m.system_power_cost[z, t] for z in m.LOAD_ZONES) 
    )
    
    # add system power cost to objective function so that its cost can be balanced against generator cost
    mod.Cost_Components_Per_TP.append('SystemPowerCost')

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

        # OPTIONAL: Force time coincidence on subset of days
        ####################################################


        # specify the timepoints that are in the subset days
        mod.SUBSET_TIMEPOINTS = Set(
            initialize=mod.TIMEPOINTS,
            filter=lambda m, t: m.tp_in_subset[t]
        )

        # On the representative day(s), DispatchGen >= Load for each timepoint
        mod.Enforce_Time_Coincidence_During_Subset = Constraint(
            mod.LOAD_ZONES, mod.SUBSET_TIMEPOINTS,
            rule = lambda m, z, t: m.ZoneTotalGeneratorDispatch[z,t] >= m.zone_demand_mw[z,t]
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

        mod.Enforce_Annual_Renewable_Target = Constraint(
            mod.PERIODS # for each zone in each period
            rule=lambda m, p: (m.total_generation_in_period[p] >= m.renewable_target[p] * m.total_demand_in_period[p]))
        

def load_inputs(mod, switch_data, inputs_dir):
    """
    Import renewable target, system power data, and subset parameters

    renewable_target.csv
        period, renewable_target

    system_power_cost.csv
        load_zone, timepoint, system_power_cost

    days.csv
        timepoint_id, tp_day, tp_in_subset
    """

    #load the renewable target
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'renewable_target.csv'),
        autoselect=True,
        index=mod.PERIODS,
        param=(mod.renewable_target,))

    #load inputs which include costs for each timepoint in each zone
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'system_power_cost.csv'),
        select=('load_zone','timepoint','system_power_cost'),
        index=mod.ZONE_TIMEPOINTS,
        param=[mod.system_power_cost])

    # load optional data specifying subset days
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'days.csv'),
        select=('timepoint_id','tp_in_subset'),
        index=mod.TIMEPOINTS,
        param=(mod.tp_in_subset))

def post_solve(instance, outdir):
    """
    Exported files:

    system_power.csv: the amount and cost of system power dispatched in each timepoint
    """

    system_power_dat = [{
        "timestamp": instance.tp_timestamp[t],
        "period": instance.tp_period[t],
        "load_zone": z,
        "System_Power_MW":value(instance.SystemPower[z,t]),
        "System_Power_Cost_per_MWh":instance.system_power_cost[z,t],
        "System_Power_GWh_per_year": value(
            instance.SystemPower[z,t] * instance.tp_weight_in_year[t] / 1000),
        "Annual_System_Power_Cost": value(
            instance.SystemPower[z,t] * instance.system_power_cost[z,t] *
            instance.tp_weight_in_year[t])
    } for z, t in instance.ZONE_TIMEPOINTS ]
    SP_df = pd.DataFrame(system_power_dat)
    SP_df.set_index(["load_zone","timestamp"], inplace=True)
    SP_df.to_csv(os.path.join(outdir, "system_power.csv"))
