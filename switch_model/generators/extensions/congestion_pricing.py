# Copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This module adds the capability to track nodal prices at both the generation node and delivery node. 
Currently, this is configured to track costs related to physical PPAs, in which the buyer is responsible
for scheduling the energy in the wholesale market, and thus earns any wholesale market revenue. 
This is in contrast to a virtual power purchase agreement, which are often set up as contracts for difference (CFD)
in which the buyer pays the contract price and also settles the difference between the contract price and wholesale market price.
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

    # Pnode Revenue is earned from injecting power into the grid 
    mod.GenPnodeRevenue = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g,t] * m.nodal_price[m.gen_pricing_node[g],t] if g in m.NON_STORAGE_GENS else 0))
        
    mod.GenPnodeRevenueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.GenPnodeRevenue[g,t]  for g in m.NON_STORAGE_GENS))
    # add Pnode revenue to objective function
    mod.Cost_Components_Per_TP.append('GenPnodeRevenueInTP')

    # TODO: Add if statement to remove this in case of full curtailment
    mod.ExcessGenPnodeRevenue = Expression(
        mod.VARIABLE_GEN_TPS,
        rule=lambda m, g, t: ((m.ExcessGen[g, t]) * m.nodal_price[m.gen_pricing_node[g],t]))
    mod.ExcessGenPnodeRevenueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.ExcessGenPnodeRevenue[g,t] for g in m.VARIABLE_GENS))

    # TODO: Delete commented code
    """
    # The delivery cost is the cost of offtaking the generated energy at the demand node
    mod.GenDeliveryCost = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g,t] * m.nodal_price[m.gen_load_zone[g],t] if g in m.DISPATCHABLE_GENS else 0) +\
            (m.VariableGen[g,t] * m.nodal_price[m.gen_load_zone[g],t] if g in m.VARIABLE_GENS else 0))
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
        rule=lambda m, g, t: m.GenDeliveryCost[g,t] - m.GenPnodeRevenue[g,t])
    mod.CongestionCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m,t: sum(m.GenCongestionCost[g,t] for g in m.NON_STORAGE_GENS))
    """

def post_solve(instance, outdir):
    congestion_data = [{
        "generation_project": g,
        "timestamp": instance.tp_timestamp[t],
        "DispatchGen_MW": value(instance.DispatchGen[g, t]),
        "Contract Cost": value(instance.DispatchGen[g,t] * instance.ppa_energy_cost[g] *
            instance.tp_weight_in_year[t]),
        "Generator Pnode Revenue": value(instance.GenPnodeRevenue[g,t]),
        #"Generator Delivery Cost": value(instance.GenDeliveryCost[g,t]),
        #"Congestion Cost": value(instance.GenCongestionCost[g,t]),
    } for (g, t) in instance.NON_STORAGE_GEN_TPS]
    nodal_by_gen_df = pd.DataFrame(congestion_data)
    nodal_by_gen_df.set_index(["generation_project", "timestamp"], inplace=True)
    nodal_by_gen_df.to_csv(os.path.join(outdir, "nodal_costs_by_gen.csv"))

    nodal_data = [{
        "timestamp": instance.tp_timestamp[t],
        "Generator Pnode Revenue": value(instance.GenPnodeRevenueInTP[t]),
        #"Generator Delivery Cost": value(instance.GenDeliveryCostInTP[t]),
        #"Congestion Cost": value(instance.CongestionCostInTP[t]),
        "DLAP Cost": value(instance.DLAPLoadCostInTP[t]),
    } for t in instance.TIMEPOINTS]
    nodal_df = pd.DataFrame(nodal_data)
    nodal_df.set_index(["timestamp"], inplace=True)
    nodal_df.to_csv(os.path.join(outdir, "nodal_costs.csv"))



    


    
