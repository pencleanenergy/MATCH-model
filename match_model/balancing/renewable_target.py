# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
Defines the type of renewable energy goal (annual or time-coincident) and the goal percentage (0-100%)

"""

import os
from sys import modules
from pyomo.environ import *

dependencies = (
    "match_model.timescales",
    "match_model.generators.dispatch",
    "match_model.balancing.load_zones",
    "match_model.balancing.system_power",
)


def define_arguments(argparser):
    argparser.add_argument(
        "--goal_type",
        choices=["annual", "hourly"],
        default="hourly",
        help="Whether generators must be dispatched to meet an annual or hourly renewable target"
        "An annual goal requires the total annual volume of renewable generation to be greater than the percentage of total annual load"
        "Generation can be located in any LOAD_ZONE to meet an annual target"
        "An hourly goal requires renewable generation to be greater than the percentage of hourly time- and location-coincident load"
        "Generation must be located in the same LOAD_ZONE as load to be counted toward an hourly goal",
    )


def define_components(mod):
    """
    renewable_target[p] is a parameter that describes how much of load (as a percentage) must be served by GENERATION_PROJECTS.
    This assumes that all GENERATION_PROJECTS are renewable generators that count toward the goal.

    hedge_premium_cost[z]

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

    mod.renewable_target = Param(mod.PERIODS, default=0, within=PercentFraction)

    # Calculate the total demand in all zones
    mod.total_demand_in_period = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.zone_total_demand_in_period_mwh[z, p] for z in m.LOAD_ZONES
        ),
    )

    # Calculate the total generation in the period
    mod.total_generation_in_period = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.ZoneTotalGeneratorDispatch[z, t] + m.ZoneTotalExcessGen[z, t]
            for (z, t) in m.ZONE_TIMEPOINTS
            if m.tp_period[t] == p
        ),
    )

    # if there are any storage generators in the model
    try:
        mod.total_storage_losses_in_period = Expression(
            mod.PERIODS,
            rule=lambda m, p: sum(
                m.ZoneTotalStorageCharge[z, t] - m.ZoneTotalStorageDischarge[z, t]
                for (z, t) in m.ZONE_TIMEPOINTS
                if m.tp_period[t] == p
            ),
        )
    except ValueError:
        mod.total_storage_losses_in_period = Param(mod.PERIODS, default=0)

    if mod.options.goal_type == "hourly":

        # calculate annual system power
        mod.AnnualSystemPower = Expression(
            mod.LOAD_ZONES,
            mod.PERIODS,
            rule=lambda m, z, p: sum(m.SystemPower[z, t] for t in m.TIMEPOINTS),
        )

        mod.Enforce_Hourly_Renewable_Target = Constraint(
            mod.PERIODS,
            mod.LOAD_ZONES,  # for each zone in each period
            rule=lambda m, p, z: (
                m.AnnualSystemPower[z, p]
                <= (
                    (1 - m.renewable_target[p])
                    * m.zone_total_demand_in_period_mwh[z, p]
                )
            ),
        )

    elif mod.options.goal_type == "annual":
        mod.Enforce_Annual_Renewable_Target = Constraint(
            mod.PERIODS,  # for each zone in each period
            rule=lambda m, p: (
                m.total_generation_in_period[p] - m.total_storage_losses_in_period[p]
                >= m.renewable_target[p] * m.total_demand_in_period[p]
            ),
        )


def load_inputs(mod, match_data, inputs_dir):
    """
    Import renewable target, system power data parameters

    renewable_target.csv
        period, renewable_target

    hedge_premium_cost.csv
        load_zone, timepoint, hedge_premium_cost

    """

    # load the renewable target
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "renewable_target.csv"),
        autoselect=True,
        param=[mod.renewable_target],
    )
