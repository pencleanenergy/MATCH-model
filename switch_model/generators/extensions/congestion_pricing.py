# Copyright (c) 2021 Gregory J. Miller. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This module adds the 
"""

import os
from pyomo.environ import *
import pandas as pd

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties', \
    'switch_model.generators.core.build', 'switch_model.generators.core.dispatch', \
    'switch_mode.generators.extensions.storage'
    
def define_components(mod):
    """
    If the average Pnode revenue is higher than the contract cost, the model will try to overbuild
    """

    # Costs for objective function
    ##############################
    
    # Calculate the cost we pay for load at the DLAP
    mod.DLAPLoadCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(m.zone_demand_mw[z,t] * m.nodal_price[z,t] for z in m.LOAD_ZONES))
    mod.Cost_Components_Per_TP.append('DLAPLoadCostInTP')

    mod.DispatchedGenPnodeRevenue = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g,t] * m.nodal_price[m.gen_pricing_node[g],t]))

    mod.DispatchedGenPnodeRevenueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: - sum(m.DispatchedGenPnodeRevenue[g,t] for g in m.NON_STORAGE_GENS))
    mod.Cost_Components_Per_TP.append('DispatchedGenPnodeRevenueInTP')

    # Other calculations for post-solve
    ###################################

    mod.ExcessGenPnodeRevenue = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.ExcessGen[g,t]) * m.nodal_price[m.gen_pricing_node[g],t])
    mod.ExcessGenPnodeRevenueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.ExcessGenPnodeRevenue[g,t] for g in m.NON_STORAGE_GENS))

    mod.GenDeliveryCost = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: m.DispatchGen[g,t] * m.nodal_price[m.gen_load_zone[g],t])
    mod.GenDeliveryCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.GenDeliveryCost[g,t] for g in m.NON_STORAGE_GENS))

    mod.ExcessGenDeliveryCost = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.ExcessGen[g,t] * m.nodal_price[m.gen_load_zone[g],t]))
    mod.ExcessGenDeliveryCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.ExcessGenDeliveryCost[g,t] for g in m.NON_STORAGE_GENS))

    mod.GenCongestionCost = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: m.GenDeliveryCost[g,t] + m.ExcessGenDeliveryCost[g,t] - m.DispatchedGenPnodeRevenue[g,t] - m.ExcessGenPnodeRevenue[g,t])
    mod.CongestionCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.GenCongestionCost[g,t] for g in m.NON_STORAGE_GENS))


def post_solve(instance, outdir):
    congestion_data = [{
        "generation_project": g,
        "timestamp": instance.tp_timestamp[t],
        "DispatchGen_MW": value(instance.DispatchGen[g, t]),
        "Excess_Gen_MW": value(instance.ExcessGen[g,t]),
        "Contract Cost": value(
            (instance.DispatchGen[g,t] + instance.ExcessGen[g,t]) * instance.ppa_energy_cost[g] *
            instance.tp_weight_in_year[t]),
        "Dispatched Pnode Revenue": value(instance.DispatchedGenPnodeRevenue[g,t]),
        "Dispatched Delivery Cost": value(instance.GenDeliveryCost[g,t]),
        "Excess Pnode Revenue": value(instance.ExcessGenPnodeRevenue[g,t]),
        "Excess Delivery Cost": value(instance.ExcessGenDeliveryCost[g,t]),
        "Congestion Cost": value(instance.GenCongestionCost[g,t]),
    } for (g, t) in instance.NON_STORAGE_GEN_TPS]
    congestion_df = pd.DataFrame(congestion_data)
    congestion_df.set_index(["generation_project", "timestamp"], inplace=True)
    congestion_df.to_csv(os.path.join(outdir, "congestion_costs_by_gen.csv"))

    


    
