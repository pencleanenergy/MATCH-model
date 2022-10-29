# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
Defines the cost of any system power that the model relies on to meet load. System power will be used to serve any load that is not served by contracted generation.

"""

import os
from sys import modules
from pyomo.environ import *
import pandas as pd

dependencies = (
    "match_model.timescales",
    "match_model.generators.dispatch",
    "match_model.balancing.load_zones",
    "match_model.financials",
)


def define_components(mod):
    # if no hedge cost is specified, set the cost to a very small amount
    # This discourages use of system power
    mod.hedge_premium_cost = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS, within=Reals, default=1.00
    )

    # implementation of system power as a decision variable
    mod.SystemPower = Var(mod.LOAD_ZONES, mod.TIMEPOINTS, within=NonNegativeReals)
    # add system power to the power balance equation
    mod.Zone_Power_Injections.append("SystemPower")

    # calculate the cost of using system power for the objective function
    mod.HedgePremiumCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.SystemPower[z, t] * m.hedge_premium_cost[z, t] for z in m.LOAD_ZONES
        ),
    )
    mod.Cost_Components_Per_TP.append("HedgePremiumCostInTP")


def load_inputs(mod, match_data, inputs_dir):
    # load inputs which include costs for each timepoint in each zone
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "hedge_premium_cost.csv"),
        select=("load_zone", "timepoint", "hedge_premium_cost"),
        param=[mod.hedge_premium_cost],
    )


def post_solve(instance, outdir):
    """
    Exported files:

    system_power.csv: the amount and cost of system power dispatched in each timepoint
    """

    system_power_dat = [
        {
            "timestamp": instance.tp_timestamp[t],
            "load_zone": z,
            "system_power_MW": value(instance.SystemPower[z, t]),
            "hedge_premium_cost": value(
                instance.SystemPower[z, t]
                * instance.hedge_premium_cost[z, t]
                * instance.tp_weight_in_year[t]
            ),
        }
        for z, t in instance.ZONE_TIMEPOINTS
    ]
    SP_df = pd.DataFrame(system_power_dat)
    SP_df.set_index(["load_zone", "timestamp"], inplace=True)
    SP_df.to_csv(os.path.join(outdir, "system_power.csv"))
