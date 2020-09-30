"""
Defines components to allow for some load to be served by system power rather than time-coincident
renewables. 

"""

import os
from pyomo.environ import *
import pandas as pd

dependencies = 'switch_model.timescales', 'switch_model.generators.core.dispatch', \
    'switch_model.balancing.load_zones', 'switch_model.financials'

def define_components(mod):
    """
    renewable_target[p] is a parameter that describes how much of load (as a percentage) must be served by GENERATION_PROJECTS

    system_power_cost[z,t] is a parameter that describes the cost of system power ($/MWh) for each timepoint in each load zone. 
    This could describe wholesale prices of electricity or your utility rate structure (whereever you will be buying energy from if not procuring from PPAs)

    SystemPower[z, t] is an expression that represents the difference between demand and PPA generation in each zone in each timeperiod,
    or in other words, how much power would be required from the system.

    SystemPowerCost[t] is an expression that summarizes the total cost of consuming system power at a given timepoint

    AnnualSystemPower[z,p] is an expression that describes the total system power used in each zone in each period

    Enforce_Renewable_Target[z,p] is a contraint that requires time coincident renewable generation from GENERATION_PROJECTS to meet or exceed the renewable_target.
    Defined as AnnualSystemPower <= (1 - renewable_target) * zone_total_demand_in_period_mwh

    """
    #set the renewable target
    mod.renewable_target = Param(
        mod.PERIODS,
        default=1,
        within=PercentFraction)
    
    #change this to be a price by timepoint
    mod.system_power_cost = Param(
        mod.ZONE_TIMEPOINTS,
        within=Reals)
    
    #Calculate the system power required to balance load in each timepoint in each load zone
    """
    #implementation of system power as an expression
    mod.SystemPower = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS, #for each timepoint in each load zone
        rule=lambda m, z, t: (m.zone_demand_mw[z, t] - m.ZoneTotalCentralDispatch[z,t])
    )
    """
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
    mod.Cost_Components_Per_TP.append('SystemPowerCost')

    #calculate annual system power
    mod.AnnualSystemPower = Expression(
        mod.LOAD_ZONES, mod.PERIODS,
        rule=lambda m, z, p: sum(m.SystemPower[z,t] for t in m.TIMEPOINTS)
    )

    #constrain the use of system power to the renewable target
    mod.Enforce_Renewable_Target = Constraint(
        mod.PERIODS, mod.LOAD_ZONES, # for each zone in each period
        rule=lambda m, p, z: (
            m.AnnualSystemPower[z,p] <= ((1 - m.renewable_target[p]) * m.zone_total_demand_in_period_mwh[z,p]))
    )

def load_inputs(mod, switch_data, inputs_dir):
    """
    The cost penalty of unserved load in units of $/MWh is the only parameter
    that can be inputted. The following file is not mandatory, because the
    parameter defaults to a value of 500 $/MWh. This file contains one header
    row and one data row.

    optional input files:
        lost_load_cost.csv
            unserved_load_penalty

    """
    #load inputs which include costs for each timepoint in each zone
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'system_power_cost.csv'),
        select=('load_zone','timepoint','system_power_cost'),
        index=mod.ZONE_TIMEPOINTS,
        param=[mod.system_power_cost]
    )

    #load the renewable target
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'renewable_target.csv'),
        autoselect=True,
        index=mod.PERIODS,
        param=(mod.renewable_target,))

def post_solve(instance, outdir):
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

    system_power_summary = SP_df.groupby(['load_zone','period']).sum()
    system_power_summary.to_csv(
        os.path.join(outdir, "system_power_summary.csv"),
        columns=["System_Power_GWh_per_year", "Annual_System_Power_Cost"])