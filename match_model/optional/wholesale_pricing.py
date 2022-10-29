# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
This module adds the capability to track nodal prices at both the generation node and delivery node. 
"""

import os
from pyomo.environ import *
import pandas as pd

dependencies = (
    "match_model.timescales",
    "match_model.balancing.load_zones",
    "match_model.financials",
    "match_model.generators.build",
    "match_model.generators.dispatch",
    "match_model.generators.optional.storage",
)


def define_components(mod):
    """
    If the average Pnode revenue is higher than the contract cost, the model will try to overbuild
    """

    mod.PRICING_NODES = Set()
    mod.NODE_TIMEPOINTS = Set(
        dimen=2,
        initialize=lambda m: m.PRICING_NODES * m.TIMEPOINTS,
        doc="The cross product of trading hubs and timepoints, used for indexing.",
    )

    mod.gen_pricing_node = Param(
        mod.GENERATION_PROJECTS,
        validate=lambda m, val, g: val in m.PRICING_NODES,
        within=Any,
    )
    mod.nodal_price = Param(mod.NODE_TIMEPOINTS, within=Reals)

    # Costs for objective function
    ##############################

    # Calculate the cost we pay for load at the DLAP
    mod.DLAPLoadCostInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.zone_demand_mw[z, t] * m.nodal_price[z, t] for z in m.LOAD_ZONES
        ),
    )
    mod.Cost_Components_Per_TP.append("DLAPLoadCostInTP")

    # Pnode Revenue is earned from injecting power into the grid
    mod.GenPnodeRevenue = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: -1
        * (
            m.DispatchGen[g, t] * m.nodal_price[m.gen_pricing_node[g], t]
            if g in m.NON_STORAGE_GENS
            else 0
        ),
    )

    mod.GenPnodeRevenueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(m.GenPnodeRevenue[g, t] for g in m.NON_STORAGE_GENS),
    )
    # add Pnode revenue to objective function
    mod.Cost_Components_Per_TP.append("GenPnodeRevenueInTP")

    mod.ExcessGenPnodeRevenue = Expression(
        mod.VARIABLE_GEN_TPS,
        rule=lambda m, g, t: -1
        * ((m.ExcessGen[g, t]) * m.nodal_price[m.gen_pricing_node[g], t]),
    )
    mod.ExcessGenPnodeRevenueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(m.ExcessGenPnodeRevenue[g, t] for g in m.VARIABLE_GENS),
    )
    mod.Cost_Components_Per_TP.append("ExcessGenPnodeRevenueInTP")

    # Other Costs for Reporting
    ###########################
    mod.GenCurtailedEnergyValueInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            (m.CurtailGen[g, t] * m.nodal_price[m.gen_pricing_node[g], t])
            for g in m.VARIABLE_GENS
        ),
    )

    # The delivery cost is the cost of offtaking the generated energy at the demand node
    mod.GenDeliveryCost = Expression(
        mod.NON_STORAGE_GEN_TPS,
        rule=lambda m, g, t: (m.TotalGen[g, t] * m.nodal_price[m.gen_load_zone[g], t]),
    )


def load_inputs(mod, match_data, inputs_dir):

    match_data.load_aug(
        filename=os.path.join(inputs_dir, "pricing_nodes.csv"), set=mod.PRICING_NODES
    )

    # load wholesale market node data
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "nodal_prices.csv"),
        select=("pricing_node", "timepoint", "nodal_price"),
        param=[mod.nodal_price],
    )


def post_solve(instance, outdir):
    congestion_data = [
        {
            "generation_project": g,
            "timestamp": instance.tp_timestamp[t],
            "Generation_MW": value(instance.TotalGen[g, t]),
            "Contract_Cost": value(
                instance.TotalGen[g, t] * instance.ppa_energy_cost[g]
            ),
            "Curtailed_Energy_Cost": value(
                instance.CurtailGen[g, t] * instance.ppa_energy_cost[g]
            )
            if instance.gen_is_variable[g]
            else 0,
            "Pnode_Revenue": value(
                instance.GenPnodeRevenue[g, t] + instance.ExcessGenPnodeRevenue[g, t]
            )
            if instance.gen_is_variable[g]
            else value(instance.GenPnodeRevenue[g, t]),
            "Delivery_Cost": value(instance.GenDeliveryCost[g, t]),
        }
        for (g, t) in instance.NON_STORAGE_GEN_TPS
    ]
    nodal_by_gen_df = pd.DataFrame(congestion_data)
    nodal_by_gen_df.set_index(["generation_project", "timestamp"], inplace=True)
    nodal_by_gen_df.to_csv(os.path.join(outdir, "costs_by_gen.csv"))

    nodal_data = [
        {
            "timestamp": instance.tp_timestamp[t],
            "Dispatched Generation PPA Cost": value(instance.GenPPACostInTP[t]),
            "Excess Generation PPA Cost": value(instance.ExcessGenPPACostInTP[t]),
            "Dispatched Generation Pnode Revenue": value(
                instance.GenPnodeRevenueInTP[t]
            ),
            "Excess Generation Pnode Revenue": value(
                instance.ExcessGenPnodeRevenueInTP[t]
            ),
            "Curtailed Generation PPA Cost": value(
                instance.GenCurtailedEnergyCostInTP[t]
            ),
            "Curtailed Generation Pnode Value": value(
                instance.GenCurtailedEnergyValueInTP[t]
            ),
            "DLAP Cost": value(instance.DLAPLoadCostInTP[t]),
        }
        for t in instance.TIMEPOINTS
    ]
    nodal_df = pd.DataFrame(nodal_data)
    nodal_df.set_index(["timestamp"], inplace=True)
    nodal_df.to_csv(os.path.join(outdir, "costs_by_tp.csv"))
