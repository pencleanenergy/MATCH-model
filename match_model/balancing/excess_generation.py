# Copyright (c) 2021 The MATCH Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This module defines limits on the amount of excess generation that is allowed as part of the optimal portfolio.
These limits can take the form of a hard limit on total generation as a percent of load, or as a financial penalty on any excess generation.

"""

import os
from sys import modules
from pyomo.environ import *
import pandas as pd

dependencies = 'match_model.timescales', 'match_model.generators.dispatch', \
    'match_model.balancing.load_zones', 'match_model.balancing.system_power', 'match_model.balancing.renewable_target',


def define_arguments(argparser):
    argparser.add_argument('--excess_generation_limit_type', choices=['annual', 'hourly', None], default=None,
        help="If specified, whether the limit on excess generation is applied to each hour, or to the entire year"
    )

def define_components(mod):

    # Hard limit on excess generation
    #################################
    # define limit, set the default at 1000% of load (arbitrarily high value)
    mod.excess_generation_limit = Param(mod.PERIODS, within=PercentFraction)

    #Enforce limit on excess generation
    if mod.options.excess_generation_limit_type == "annual":
        

        mod.Enforce_Annual_Excess_Generation_Limit = Constraint(
            mod.PERIODS,
            rule = lambda m, p: (m.total_generation_in_period[p] - m.total_storage_losses_in_period[p]) <= (sum(m.zone_total_demand_in_period_mwh[z,p] for z in m.LOAD_ZONES)) * (1 + m.excess_generation_limit[p])
        )

    elif mod.options.excess_generation_limit_type == "hourly":

        mod.Enforce_Hourly_Excess_Generation_Limit = Constraint(
            mod.LOAD_ZONES, mod.TIMEPOINTS,
            rule = lambda m, z, t: m.ZoneTotalExcessGen[z,t] <= m.zone_demand_mw[z,t] * m.excess_generation_limit[m.tp_period[t]]
        )

    # Financial penalty for excess generation
    ##########################################
    # For generators that have a net negative cost, add a constraint on the amount of excess generation
    # so that they are not overbuilt

    mod.excessgen_penalty = Param(mod.PERIODS,
        within=NonNegativeReals,
        default=0)

    if mod.options.goal_type == "hourly":

        mod.ExcessGenPenaltyInTP = Expression(
            mod.TIMEPOINTS,
            rule=lambda m, t: sum(m.ZoneTotalExcessGen[z,t] * m.excessgen_penalty[m.tp_period[t]] for z in m.LOAD_ZONES),
            doc="Summarize costs for the objective function")
        mod.Cost_Components_Per_TP.append('ExcessGenPenaltyInTP')
    
    elif mod.options.goal_type == "annual":
        # assign a penalty for any generation in excess of the target
        mod.ExcessGenPenalty = Expression(
            mod.PERIODS,
            rule=lambda m, p: (m.total_generation_in_period[p] - (m.renewable_target[p] * m.total_demand_in_period[p])) * m.excessgen_penalty[p])
        mod.Cost_Components_Per_Period.append('ExcessGenPenalty')

def load_inputs(mod, match_data, inputs_dir):

    match_data.load_aug(
        filename=os.path.join(inputs_dir, 'excessgen_limits.csv'),
        autoselect=True,
        param=[mod.excess_generation_limit, mod.excessgen_penalty])