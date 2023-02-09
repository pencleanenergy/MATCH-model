# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px
import math
import os

from pyomo.core import util

"""
This module contains a collection of functions that are called from the summary_report.ipynb, used for reporting final outputs
"""


def fv_to_pv(financials):
    """
    Calculates a factor to discount future values in the model year to present value in the base year.

    Inputs:
        financials: dataframe loaded from inputs/financials.csv
        year: the model year, as an integer (YYYY)

    Outputs:
        future value to present value conversion factor
    """
    return (1 + financials.loc[0, "discount_rate"]) ** -(
        financials.loc[0, "dollar_year"] - financials.loc[0, "base_financial_year"]
    )


def format_currency(x):
    """
    Formats a number as currency in the format '$ 0.00'

    Inputs:
        x: float number
    Returns:
        formatted: formatted number as a string
    """
    try:
        formatted = "$ {:,.2f}".format(x)
    except ValueError:
        formatted = x
    return formatted


def format_percent(x):
    """
    Formats a number as percentage in the format '99.99%'

    The input number must be a percentage on a 0-100 scale

    Inputs:
        x: float number
    Returns:
        formatted: formatted number as a string
    """
    try:
        formatted = "{:,.2f}%".format(x)
    except ValueError:
        formatted = x
    return formatted


def hybrid_pair_dict(generation_projects_info):
    """
    Creates a dictionary matching the name of the storage portion of a hybrid project to the generator portion

    Inputs:
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
    Returns:
        hybrid_pair: a dictionary matching the names of generators (keys) to paired storage project names (values)
    """
    hybrid_pair = generation_projects_info[
        ["GENERATION_PROJECT", "storage_hybrid_generation_project"]
    ]
    hybrid_pair = hybrid_pair[hybrid_pair["storage_hybrid_generation_project"] != "."]
    hybrid_pair = dict(
        zip(
            hybrid_pair.GENERATION_PROJECT,
            hybrid_pair.storage_hybrid_generation_project,
        )
    )
    return hybrid_pair


def annual_renewable_percentage(load_balance):
    """
    Calculates the percent of delivered energy from renewable sources, using an annual volumetric method

    The renewable percentage is net generation / load, where net generation is total generation less storage losses

    NOTE: this will need to be modified to calculate net load if DSR is used

    Inputs:
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
    Returns:
        percent: float number representing the annual renewable percentage on the 100-point scale
    """

    if "ZoneTotalStorageCharge" in load_balance.columns:
        storage_losses = (
            load_balance.ZoneTotalStorageCharge.sum()
            - load_balance.ZoneTotalStorageDischarge.sum()
        )
    else:
        storage_losses = 0
    net_generation = (
        load_balance.ZoneTotalGeneratorDispatch.sum()
        + load_balance.ZoneTotalExcessGen.sum()
        - storage_losses
    )
    load = load_balance.zone_demand_mw.sum()

    percent = net_generation / load * 100

    return percent


def hourly_renewable_percentage(load_balance):
    """
    Calculates the percent of delivered energy from renewable sources, using a time-coincident hourly method

    Because system power must be used to fill in any gaps that dispatch and storage discharge cannot provide,
    we can calculate the time-coincident renewable percentage as the inverse of the system power percentage

    NOTE: this will need to be modified to calculate net load if DSR is used

    Inputs:
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
    Returns:
        percent: float number representing the time-coincident renewable percentage on the 100-point scale
    """

    system_power = load_balance.SystemPower.sum()
    load = load_balance.zone_demand_mw.sum()

    percent = (1 - (system_power / load)) * 100

    return percent


def build_hourly_emissions_heatmap(total_emissions, emissions_unit, cambium_scenario):
    """
    Creates a heatmap showing delivered emissions intensity of each hour of the year

    Inputs:
        total_emissions: a dataframe containing hourly emissions data, calculated from calculate_emissions()
        emissions_unit: a string identifying the unit of measure used for emission rates, loaded from inputs/ghg_emissions_unit.txt
    Returns:
        emissions_heatmap: a plotly image plot representing a heatmap of hourly emissions intensity of delivered electricity
    """
    # get the maximum grid emissions factor
    grid_max_ef = total_emissions["residual_ef"].max()

    # rearrange data in a grid
    emissions_heatmap_data = total_emissions.copy()[["Delivered Emission Factor"]]
    max_ef = max(grid_max_ef, emissions_heatmap_data["Delivered Emission Factor"].max())
    emissions_heatmap_data["Date"] = emissions_heatmap_data.index.date
    emissions_heatmap_data["Hour of Day"] = emissions_heatmap_data.index.hour
    emissions_heatmap_data = emissions_heatmap_data.pivot(
        index="Hour of Day", columns="Date", values="Delivered Emission Factor"
    )
    emissions_heatmap_data = emissions_heatmap_data.round(4)

    emissions_heatmap = px.imshow(
        emissions_heatmap_data,
        x=emissions_heatmap_data.columns,
        y=emissions_heatmap_data.index,
        color_continuous_scale="rdylgn_r",
        range_color=[0, max_ef],
        labels={"color": "Emissions Intensity"},
        title=f"Hourly Emisission Intensity of Delivered Energy ({emissions_unit}) using Cambium {cambium_scenario} scenario",
    ).update_yaxes(dtick=3)

    return emissions_heatmap


def generator_portfolio(
    gen_cap, gen_build_predetermined, generation_projects_info, year
):
    """
    Calculates the generator portfolio mix to be used as an input for a suburst chart

    Inputs:
        gen_cap: a dataframe containing data on built generator capacity loaded from outputs/gen_cap.csv
        gen_build_predetermined: a dataframe containing predetermined build capacity data for generators, loaded from inputs/gen_build_predetermined.csv
        generation_projects_info
    Returns:
        capacity: a dataframe summarizing the built capacity of each generator, formatted for a plotly sunburst plot
    """
    # only keep generators that were built
    capacity = gen_cap.copy()
    capacity = capacity[capacity["GenCapacity"] > 0]

    # only keep certain columns
    capacity = capacity[["generation_project", "gen_tech", "GenCapacity"]]

    # rename the GenCapacity column to MW
    capacity = capacity.rename(columns={"GenCapacity": "MW"})

    # change the column name to lower case to match the column in capacity
    predetermined = gen_build_predetermined.copy()[["GENERATION_PROJECT"]].rename(
        columns={"GENERATION_PROJECT": "generation_project"}
    )

    # add column indicating which generators are contracted or additional builds
    predetermined["Contract Status"] = "Contracted"
    capacity = capacity.merge(
        predetermined, how="left", on="generation_project"
    ).fillna("New")

    # check if any of the contracted projects had additional capacity added and split out as separate projects
    split_projects = []
    for gen in list(
        capacity.loc[capacity["Contract Status"] == "Contracted", "generation_project"]
    ):
        built_mw = capacity.loc[capacity["generation_project"] == gen, "MW"].item()
        predetermined_mw = gen_build_predetermined.loc[
            gen_build_predetermined["GENERATION_PROJECT"] == gen,
            "gen_predetermined_cap",
        ].item()
        if built_mw > predetermined_mw:
            # set the contracted quantity equal to the predetermined value
            capacity.loc[capacity["generation_project"] == gen, "MW"] = predetermined_mw
            # create a new row for the additional quantity
            split_projects.append(
                {
                    "generation_project": gen,
                    "gen_tech": capacity.loc[
                        capacity["generation_project"] == gen, "gen_tech"
                    ].item(),
                    "MW": (built_mw - predetermined_mw),
                    "Contract Status": "New",
                }
            )

        else:
            pass
    # append all projects to dataframe
    capacity = pd.concat(
        [capacity, pd.DataFrame.from_records(split_projects)],
        axis="index",
        ignore_index=True,
    )

    # if there are any hybrid projects, add hybrid to the gen tech
    # merge gen is hybrid indicator
    capacity = capacity.merge(
        generation_projects_info[["GENERATION_PROJECT", "gen_is_hybrid", "cod_year"]],
        how="left",
        left_on="generation_project",
        right_on="GENERATION_PROJECT",
    ).drop(columns=["GENERATION_PROJECT"])
    capacity.loc[capacity.gen_is_hybrid == 1, "gen_tech"] = "Hybrid " + capacity.loc[
        capacity.gen_is_hybrid == 1, "gen_tech"
    ].astype(str)
    capacity = capacity.drop(columns=["gen_is_hybrid"])

    # replace underscores in the gen tech name with spaces
    capacity.gen_tech = capacity.gen_tech.str.replace("_", " ")

    # change the name of the column from gen_tech to Technology
    capacity = capacity.rename(columns={"gen_tech": "Technology"})

    # round all of the values to a single decimal point
    capacity["MW"] = capacity["MW"].round(1)

    # add a column for operating status
    capacity["Build Status"] = "Existing"
    capacity.loc[capacity["cod_year"] > year, "Build Status"] = "Future"
    capacity = capacity.drop(columns=["cod_year"])

    # sort the values
    capacity = capacity.sort_values(
        by=["Contract Status", "Build Status", "Technology"]
    )

    # extract the name of the generator
    # capacity['generation_project'] = [' '.join(i.split('_')[1:]) for i in capacity['generation_project']]

    return capacity


def generator_costs(
    costs_by_gen,
    storage_dispatch,
    hybrid_pair,
    gen_cap,
    generation_projects_info,
    storage_exists,
):
    """
    Calculates the cost components for each generator in real $

    Inputs:
        costs_by_gen: a dataframe containing hourly contract, pnode, and delivery costs for each generator, loaded from outputs/costs_by_gen.csv
        storage_dispatch: a dataframe containing hourly charge, discharge, state of charge, and nodal cost data for storage assets, loaded from outputs/storage_dispatch.csv
        hybrid_pair: a dictionary matching the names of generators (keys) to paired storage project names (values), created from the hybrid_pair_dict() function
        gen_cap: a dataframe containing data on built generator capacity loaded from outputs/gen_cap.csv
    Returns:
        gen_costs: a dataframe summarizing all of the cost components for each built generator
    """
    gen_costs = costs_by_gen.copy()

    # drop rows where generation is 0
    gen_costs = gen_costs[gen_costs.Generation_MW > 0]

    gen_costs = gen_costs.groupby("generation_project").sum().reset_index()

    # rename columns
    if storage_exists:
        storage_costs = storage_dispatch.copy().drop(columns=["StateOfCharge"])
        storage_costs = storage_costs.groupby("generation_project").sum().reset_index()

        # add storage contract costs
        storage_costs = storage_costs.merge(
            gen_cap[["generation_project", "PPA_Capacity_Cost"]],
            how="left",
            on="generation_project",
        ).fillna(0)

        # replace hybrid storage names with the name of the paired generator
        storage_costs["generation_project"] = storage_costs[
            "generation_project"
        ].replace(hybrid_pair)

        # drop rows where generation is 0
        storage_costs = storage_costs[storage_costs.DischargeMW > 0]

        # merge the two dfs together
        gen_costs = gen_costs.merge(storage_costs, how="outer", on="generation_project")

        # add capacity costs for any non-storage generators
        gen_cap_cost = gen_cap.copy()[
            ["generation_project", "PPA_Capacity_Cost"]
        ].rename(columns={"PPA_Capacity_Cost": "Gen_Capacity_Cost"})
        gen_costs = gen_costs.merge(gen_cap_cost, how="left", on="generation_project")
        gen_costs["PPA_Capacity_Cost"] = gen_costs["PPA_Capacity_Cost"].fillna(
            gen_costs["Gen_Capacity_Cost"]
        )
        gen_costs = gen_costs.drop(columns=["Gen_Capacity_Cost"])
    else:
        # add capacity costs for any non-storage generators
        gen_cap_cost = gen_cap.copy()[["generation_project", "PPA_Capacity_Cost"]]
        gen_costs = gen_costs.merge(
            gen_cap_cost, how="left", on="generation_project"
        ).fillna(0)

    # fill any missing values with zero
    gen_costs = gen_costs.fillna(0)

    # combine Delivery Cost columns
    del_cost_columns = ["Delivery_Cost", "StorageDispatchDeliveryCost"]
    gen_costs["Delivery_Cost"] = gen_costs[
        [col for col in gen_costs.columns if col in del_cost_columns]
    ].sum(axis=1)

    # combine Generation and Discharge columns
    generation_columns = ["Generation_MW", "DischargeMW"]
    gen_costs["Generation_MW"] = gen_costs[
        [col for col in gen_costs.columns if col in generation_columns]
    ].sum(axis=1)
    # for hybrid generators, subtract out the charging MW
    if storage_exists:
        hybrid_gens = list(
            generation_projects_info.loc[
                (
                    (generation_projects_info["gen_is_hybrid"] == 1)
                    & (generation_projects_info["gen_is_storage"] == 0)
                ),
                "GENERATION_PROJECT",
            ]
        )
        gen_costs.loc[
            gen_costs["generation_project"].isin(hybrid_gens), "Generation_MW"
        ] = (
            gen_costs.loc[
                gen_costs["generation_project"].isin(hybrid_gens), "Generation_MW"
            ]
            - gen_costs.loc[
                gen_costs["generation_project"].isin(hybrid_gens), "ChargeMW"
            ]
        )

    # calculate congestion cost from pnode revenue and delivery cost
    gen_costs["Congestion Cost"] = (
        gen_costs["Delivery_Cost"] + gen_costs["Pnode_Revenue"]
    )
    # gen_costs = gen_costs.drop(columns=['Delivery_Cost','Pnode_Revenue'])

    # rename columns
    gen_costs = gen_costs.rename(
        columns={
            "Contract_Cost": "Energy Contract Cost",
            "PPA_Capacity_Cost": "Capacity Contract Cost",
            "Curtailed_Energy_Cost": "Curtailed Energy Cost",
            "Pnode_Revenue": "Pnode Revenue",
            "StorageDispatchPnodeCost": "Storage Arbitrage Revenue",
            "Delivery_Cost": "Delivery Cost",
            "Generation_MW": "Generation MWh",
        }
    )

    # calculate per MWh costs
    gen_costs["Energy Contract Cost"] = (
        gen_costs["Energy Contract Cost"] / gen_costs["Generation MWh"]
    )
    gen_costs["Capacity Contract Cost"] = (
        gen_costs["Capacity Contract Cost"] / gen_costs["Generation MWh"]
    )
    gen_costs["Curtailed Energy Cost"] = (
        gen_costs["Curtailed Energy Cost"] / gen_costs["Generation MWh"]
    )
    gen_costs["Congestion Cost"] = (
        gen_costs["Congestion Cost"] / gen_costs["Generation MWh"]
    )
    gen_costs["Pnode Revenue"] = (
        gen_costs["Pnode Revenue"] / gen_costs["Generation MWh"]
    )
    gen_costs["Delivery Cost"] = (
        gen_costs["Delivery Cost"] / gen_costs["Generation MWh"]
    )
    try:
        gen_costs["Storage Arbitrage Revenue"] = (
            gen_costs["Storage Arbitrage Revenue"] / gen_costs["Generation MWh"]
        )
    except KeyError:
        pass
    cost_columns = [
        "Energy Contract Cost",
        "Capacity Contract Cost",
        "Pnode Revenue",
        "Delivery Cost",
        "Storage Arbitrage Revenue",
    ]
    gen_costs["Total Cost"] = gen_costs[
        [col for col in gen_costs.columns if col in cost_columns]
    ].sum(axis=1)

    gen_costs = gen_costs.sort_values(by="Total Cost", ascending=True)

    gen_costs = gen_costs.round(decimals=2)

    # only keep relevant columns
    relevant_columns = [
        "generation_project",
        "Energy Contract Cost",
        "Capacity Contract Cost",
        "Curtailed Energy Cost",
        "Pnode Revenue",
        "Delivery Cost",
        "Congestion Cost",
        "Storage Arbitrage Revenue",
        "Total Cost",
    ]
    gen_costs = gen_costs[[col for col in gen_costs.columns if col in relevant_columns]]

    return gen_costs


def calculate_generator_utilization(dispatch):
    """
    Calculates the percent of generation from each generator that was dispatched, excess, or curtailed

    Inputs:
        dispatch: a dataframe containing hourly generator dispatch data contained in outputs/dispatch.csv
    Returns:
        utilization: a dataframe displaying the percent of each generator's generation utilized for each purpose
    """

    # calculate total annual generation in each category
    utilization = (
        dispatch.copy().drop(columns="Nodal_Price").groupby("generation_project").sum()
    )

    # sum all rows
    utilization["Total"] = utilization.sum(axis=1)

    # drop rows with zero generation
    utilization = utilization[utilization["Total"] > 0]

    # calculate the percentages
    utilization = (
        utilization[["DispatchGen_MW", "ExcessGen_MW", "CurtailGen_MW"]].div(
            utilization["Total"], axis=0
        )
        * 100
    )

    utilization = utilization.sort_values(by="DispatchGen_MW", ascending=False)

    # rename columns
    utilization = utilization.rename(
        columns={
            "DispatchGen_MW": "Dispatched %",
            "ExcessGen_MW": "Excess %",
            "CurtailGen_MW": "Curtailed %",
        }
    )

    return utilization


def power_content_label(load_balance, dispatch, generation_projects_info):
    """
    Calculates the mix of delivered energy.
    First, calculate the percentage of energy from system power
    Then, assign the remaineder the mix of dispatchgen

    Inputs:
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
        dispatch: a dataframe containing hourly generator dispatch data contained in outputs/dispatch.csv
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
    Returns:
        dispatch_mix: a dataframe containing the total MWh of generation delivered to meet load or charge storage
    """

    # get the list of technologies
    generator_technology_dict = generation_projects_info[
        ["GENERATION_PROJECT", "gen_tech"]
    ]
    generator_technology_dict = dict(
        zip(
            generator_technology_dict.GENERATION_PROJECT,
            generator_technology_dict.gen_tech,
        )
    )

    # add a generator technology column to the dispatch data
    dispatch["gen_tech"] = dispatch["generation_project"].map(generator_technology_dict)

    # calculate the mix of dispatched energy
    dispatch_mix = (
        dispatch.groupby("gen_tech")
        .sum()
        .reset_index()[["gen_tech", "DispatchGen_MW", "ExcessGen_MW"]]
    )

    # add the system power amount
    dispatch_mix = pd.concat(
        [
            dispatch_mix,
            pd.DataFrame(
                {
                    "gen_tech": ["Grid Energy"],
                    "DispatchGen_MW": [load_balance.SystemPower.sum()],
                    "ExcessGen_MW": [0],
                }
            ),
        ],
        ignore_index=True,
    )

    # rename the columns
    dispatch_mix = dispatch_mix.rename(
        columns={
            "gen_tech": "Source",
            "DispatchGen_MW": "Dispatched_MWh",
            "ExcessGen_MW": "Excess_MWh",
        }
    )

    dispatch_mix["Total_MWh"] = (
        dispatch_mix["Dispatched_MWh"] + dispatch_mix["Excess_MWh"]
    )

    # replace underscores in the gen tech name with spaces
    dispatch_mix.Source = dispatch_mix.Source.str.replace("_", " ")

    # round to no decimal places
    dispatch_mix = dispatch_mix.round(0)

    # drop any rows with zero generation
    dispatch_mix = dispatch_mix[dispatch_mix["Total_MWh"] > 0]

    return dispatch_mix


def calculate_buyer_curtailment_credit(costs_by_gen, generation_projects_info, gen_cap):
    """
    Calculates the total value of buyer curtailment as allowed by the PPA contract
    """
    # identify the projects that allow free curtailment
    gens_with_curtailment = list(
        generation_projects_info.loc[
            ~generation_projects_info["buyer_curtailment_allowance"].isin([".", "0"]),
            "GENERATION_PROJECT",
        ]
    )

    curtailment_credit = 0

    for gen in gens_with_curtailment:
        # calculate the value of the allowed curtailment
        curtailment_limit = float(
            generation_projects_info.loc[
                generation_projects_info["GENERATION_PROJECT"] == gen,
                "buyer_curtailment_allowance",
            ].item()
        )
        ppa_cost = float(
            generation_projects_info.loc[
                generation_projects_info["GENERATION_PROJECT"] == gen, "ppa_energy_cost"
            ].item()
        )
        gen_capacity = gen_cap.loc[
            gen_cap["generation_project"] == gen, "GenCapacity"
        ].item()
        curtailment_allowance = curtailment_limit * ppa_cost * gen_capacity

        # calculate the total curtailment cost
        curtailment_cost = costs_by_gen.loc[
            costs_by_gen["generation_project"] == gen, "Curtailed_Energy_Cost"
        ].sum()

        # calculate the curtailed energy cost to credit back
        curtailment_credit = curtailment_credit - min(
            curtailment_cost, curtailment_allowance
        )

    return curtailment_credit


def hourly_cost_of_power(
    system_power,
    costs_by_tp,
    ra_summary,
    gen_cap,
    storage_dispatch,
    fixed_costs,
    storage_exists,
):
    """
    Calculates the cost of power for each hour of the year in real $

    Hourly costs include: energy contract costs, nodal costs/revenues, hedge costs, DLAP cost
    Annual costs include: capacity contract costs, RA costs, fixed costs
    Sellable costs include: excess RA, RECs

    We will need to calculate costs for dispatched energy, and for all generated energy

    Inputs:
        system_power: a dataframe containing hourly system power and hedge costs, loaded from outputs/system_power.csv
        costs_by_tp: a dataframe containing hourly generation and load costs by timepoint, loaded from outputs/costs_by_tp.csv
        ra_summary: a dataframe containing resource adequacy summary data by requirement and month, loaded from outputs/RA_summary.csv
        gen_cap: a dataframe containing data on built generator capacity loaded from outputs/gen_cap.csv
        storage_dispatch: a dataframe containing hourly charge, discharge, state of charge, and nodal cost data for storage assets, loaded from outputs/storage_dispatch.csv
        fixed_costs: a dataframe containing a list of fixed annual costs, loaded from inputs/fixed_costs.csv
        rec_value: a float value representing the REC market resell value, loaded from inputs/rec_value.csv
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
    Returns:
        hourly_costs: a dataframe with all cost components broken out by hour, including fixed costs
    """

    # start with system power hedge cost and build from there
    hourly_costs = system_power.copy().drop(columns=["load_zone", "system_power_MW"])

    # if the hedge cost was set as the default value, remove the hedge cost
    if system_power["system_power_MW"].sum() != 0:
        mean_hedge_cost = (
            system_power["hedge_premium_cost"].sum()
            / system_power["system_power_MW"].sum()
        )
        if mean_hedge_cost == 1.00:
            hourly_costs["hedge_premium_cost"] = 0

    # drop the curtailed energy value from cost_by_tp
    costs_by_tp = costs_by_tp.drop(columns=["Curtailed Generation Pnode Value"])

    # add generator timepoint costs next
    hourly_costs = hourly_costs.merge(costs_by_tp, how="left", on="timestamp")

    # if the RA data exists
    if len(ra_summary) > 0:
        ra_open = ra_summary.copy()

        # set the excess RA value as a negative cost
        ra_open["Excess_RA_Value"] = -ra_open["Excess_RA_Value"]

        # calculate annual ra costs
        ra_open = ra_open[["RA_Open_Position_Cost", "Excess_RA_Value"]].sum()

        # divide these costs by the number of timepoints
        ra_open = ra_open / len(hourly_costs.index)

        # add the RA costs to the hourly costs
        hourly_costs["ra_open_position_cost"] = ra_open["RA_Open_Position_Cost"]
        hourly_costs["excess_ra_value"] = ra_open["Excess_RA_Value"]

    # calculate annual capacity costs
    gen_cap = gen_cap[["PPA_Capacity_Cost"]].sum()

    # divide these costs by the number of timepoints
    gen_cap = gen_cap / len(hourly_costs.index)

    # add the capacity costs to the hourly costs
    hourly_costs["Capacity Contract Cost"] = gen_cap["PPA_Capacity_Cost"]

    if storage_exists:
        # add storage nodal costs
        storage_cost = storage_dispatch[
            ["timestamp", "StorageDispatchPPACost", "StorageDispatchPnodeCost"]
        ]
        # sum for each timestamp
        storage_cost = storage_cost.groupby("timestamp").sum()
        # merge the data
        hourly_costs = hourly_costs.merge(storage_cost, how="left", on="timestamp")

    # calculate the hourly value for annual fixed costs
    fixed_cost_component = fixed_costs.copy()
    fixed_cost_component["annual_cost"] = fixed_cost_component["annual_cost"] / len(
        hourly_costs.index
    )

    # create new columns in the hourly cost for each of these fixed costs
    for val in fixed_cost_component["cost_name"]:
        hourly_costs[val] = fixed_cost_component.loc[
            fixed_cost_component["cost_name"] == val, "annual_cost"
        ].item()

    # parse dates
    hourly_costs = hourly_costs.set_index(
        pd.to_datetime(hourly_costs["timestamp"])
    ).drop(columns=["timestamp"])

    # rename columns
    hourly_costs = hourly_costs.rename(
        columns={
            "DLAP Cost": "DLAP Load Cost",
            "hedge_premium_cost": "Hedge Premium Cost",
            "Capacity Contract Cost": "Storage Capacity PPA Cost",
            "ra_open_position_cost": "RA Open Position Cost",
            "StorageDispatchPPACost": "Storage Energy PPA Cost",
            "StorageDispatchPnodeCost": "Storage Wholesale Price Arbitrage",
            "excess_ra_value": "Excess RA Value",
        }
    )

    return hourly_costs


def build_hourly_cost_plot(hourly_costs, load_balance, year):
    """
    Configures a plot summarizing average hourly costs in each quarter of the year

    Inputs:
        hourly_costs: a dataframe with all cost components broken out by hour, including fixed costs, calculated from the hourly_cost_of_power() function
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
        year: the model year as an integer (YYYY)
    Returns:
        hourly_cost_plot: a plotly stacked bar plot with quarter-hour averages of hourly costs
    """
    costs = hourly_costs.copy()
    load = (
        load_balance.copy()
        .set_index(pd.to_datetime(load_balance["timestamp"]))
        .drop(columns=["timestamp"])
    )

    # drop columns that include resale values
    costs = costs.drop(columns=["Excess RA Value", "Excess REC Value"])

    # specify the names and order of cost columns
    cost_columns = costs.columns

    # calculate the cost per MWh
    for col in cost_columns:
        costs[col] = costs[col] / load["zone_demand_mw"]

    # add a column for total cost
    costs["Total Cost"] = costs.sum(axis=1)

    # average by season-hour
    costs = costs.groupby([costs.index.quarter, costs.index.hour]).mean()
    costs.index = costs.index.set_names(["quarter", "hour"])
    costs = costs.reset_index().rename(columns={0: "cost"})

    # build the cost plot
    hourly_cost_plot = px.bar(
        costs,
        x="hour",
        y=cost_columns,
        facet_col="quarter",
        title=f"Hourly Average Cost of Power ({year}$)",
    ).update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    hourly_cost_plot.add_scatter(
        x=costs.loc[costs["quarter"] == 1, "hour"],
        y=costs.loc[costs["quarter"] == 1, "Total Cost"],
        row=1,
        col=1,
        line=dict(color="black", width=4),
        name="Q1 Total",
    )
    hourly_cost_plot.add_scatter(
        x=costs.loc[costs["quarter"] == 2, "hour"],
        y=costs.loc[costs["quarter"] == 2, "Total Cost"],
        row=1,
        col=2,
        line=dict(color="black", width=4),
        name="Q2 Total",
    )
    hourly_cost_plot.add_scatter(
        x=costs.loc[costs["quarter"] == 3, "hour"],
        y=costs.loc[costs["quarter"] == 3, "Total Cost"],
        row=1,
        col=3,
        line=dict(color="black", width=4),
        name="Q3 Total",
    )
    hourly_cost_plot.add_scatter(
        x=costs.loc[costs["quarter"] == 4, "hour"],
        y=costs.loc[costs["quarter"] == 4, "Total Cost"],
        row=1,
        col=4,
        line=dict(color="black", width=4),
        name="Q4 Total",
    )

    return hourly_cost_plot


def construct_cost_table(
    hourly_costs,
    load_balance,
    rec_value,
    financials,
    year,
    curtailment_credit,
    td_losses,
):
    """
    Constructs tables that break down costs by component

    Inputs:
        hourly_costs: a dataframe with all cost components broken out by hour, including fixed costs, calculated from the hourly_cost_of_power() function
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
        financials: dataframe loaded from inputs/financials.csv
        year: the model year, as an integer (YYYY)
        curtailment_credit: the $ value of contractually allowed curtailment, as calculated by calculate_curtailment_credit()
    Returns:
        cost_table: a dataframe summarizing delivered costs by total and cost per MWh
    """
    # calculate total cost
    cost_table = (
        hourly_costs.sum(axis=0)
        .reset_index()
        .rename(columns={"index": "Cost Component", 0: "Annual Real Cost"})
    )

    # Add REC Costs

    # get rec cost and value
    rec_resale_value = rec_value["rec_resale_value"].item()
    rec_cost = rec_value["rec_cost"].item()

    # calculate net rec balance
    storage_losses = (
        load_balance.sum()["ZoneTotalStorageCharge"]
        - load_balance.sum()["ZoneTotalStorageDischarge"]
    )
    loss_adj_load = load_balance.sum()["zone_demand_mw"] + storage_losses
    retail_load = (
        load_balance.sum()["zone_demand_mw"] / (1 + td_losses)
    ) + storage_losses
    total_recs = (
        load_balance.sum()["ZoneTotalGeneratorDispatch"]
        + load_balance.sum()["ZoneTotalExcessGen"]
    )

    # calculate cost based on net rec position
    if total_recs < retail_load:
        net_rec_cost = (retail_load - total_recs) * rec_cost
        net_rec_resale = 0
    elif total_recs > loss_adj_load:
        net_rec_cost = 0
        net_rec_resale = (total_recs - loss_adj_load) * rec_resale_value * -1
    else:
        net_rec_cost = 0
        net_rec_resale = 0

    cost_table = pd.concat(
        [
            cost_table,
            pd.DataFrame.from_dict(
                data={
                    "Cost Component": [
                        "REC Net Position Cost",
                        "REC Net Position Resale",
                    ],
                    "Annual Real Cost": [net_rec_cost, net_rec_resale],
                }
            ),
        ],
        ignore_index=True,
    )

    # add credit for curtailed energy
    cost_table = pd.concat(
        [
            cost_table,
            pd.DataFrame.from_dict(
                data={
                    "Cost Component": ["Buyer Curtailment Credit"],
                    "Annual Real Cost": [curtailment_credit],
                }
            ),
        ],
        ignore_index=True,
    )

    # calculate the total demand
    load = load_balance["zone_demand_mw"].sum()

    # calculate the cost per MWh consumed
    cost_table["Cost Per MWh"] = cost_table["Annual Real Cost"] / load

    # get financial parameters
    to_pv = fv_to_pv(financials)
    base_year = financials.loc[0, "base_financial_year"]

    # create a column that categorizes all of the costs
    cost_category_dict = {
        "Hedge Premium Cost": "Contract",
        "Dispatched Generation PPA Cost": "Contract",
        "Storage Energy PPA Cost": "Contract",
        "Excess Generation PPA Cost": "Contract",
        "Buyer Curtailment Credit": "Contract",
        "Curtailed Generation PPA Cost": "Contract",
        "Dispatched Generation Pnode Revenue": "Wholesale Market",
        "Excess Generation Pnode Revenue": "Wholesale Market",
        "DLAP Load Cost": "Wholesale Market",
        "RA Open Position Cost": "Resource Adequacy",
        "Excess RA Value": "Resource Adequacy",
        "REC Net Position Cost": "RECs",
        "REC Net Position Resale": "RECs",
        "Storage Capacity PPA Cost": "Contract",
        "Storage Wholesale Price Arbitrage": "Wholesale Market",
    }
    cost_table["Cost Category"] = (
        cost_table["Cost Component"].map(cost_category_dict).fillna("Fixed")
    )

    # sort the values by category and cost
    cost_table = cost_table.sort_values(
        by=["Cost Category", "Annual Real Cost"], ascending=[True, False]
    )

    # re-order the columns
    cost_table = cost_table[
        ["Cost Category", "Cost Component", "Annual Real Cost", "Cost Per MWh"]
    ]

    # add a total column
    cost_table = pd.concat(
        [
            cost_table,
            pd.DataFrame(
                {
                    "Cost Category": ["Total"],
                    "Cost Component": ["Total"],
                    "Annual Real Cost": [cost_table["Annual Real Cost"].sum()],
                    "Cost Per MWh": [cost_table["Cost Per MWh"].sum()],
                }
            ),
        ],
        ignore_index=True,
    )
    # add a total with no resale
    if "Excess RA Value" in list(cost_table["Cost Component"]):
        total_rows = pd.DataFrame(
            {
                "Cost Category": ["Total"],
                "Cost Component": ["Total without REC/RA Resale"],
                "Annual Real Cost": [
                    (
                        cost_table.loc[
                            cost_table["Cost Component"] == "Total",
                            "Annual Real Cost",
                        ].item()
                        - cost_table.loc[
                            cost_table["Cost Component"] == "REC Net Position Resale",
                            "Annual Real Cost",
                        ].item()
                        - cost_table.loc[
                            cost_table["Cost Component"] == "Excess RA Value",
                            "Annual Real Cost",
                        ].item()
                    )
                ],
                "Cost Per MWh": [
                    (
                        cost_table.loc[
                            cost_table["Cost Component"] == "Total", "Cost Per MWh"
                        ].item()
                        - cost_table.loc[
                            cost_table["Cost Component"] == "REC Net Position Resale",
                            "Cost Per MWh",
                        ].item()
                        - cost_table.loc[
                            cost_table["Cost Component"] == "Excess RA Value",
                            "Cost Per MWh",
                        ].item()
                    )
                ],
            }
        )
    else:
        total_rows = pd.DataFrame(
            {
                "Cost Category": ["Total"],
                "Cost Component": ["Total without REC Resale"],
                "Annual Real Cost": [
                    (
                        cost_table.loc[
                            cost_table["Cost Component"] == "Total",
                            "Annual Real Cost",
                        ].item()
                        - cost_table.loc[
                            cost_table["Cost Component"] == "REC Net Position Resale",
                            "Annual Real Cost",
                        ].item()
                    )
                ],
                "Cost Per MWh": [
                    (
                        cost_table.loc[
                            cost_table["Cost Component"] == "Total", "Cost Per MWh"
                        ].item()
                        - cost_table.loc[
                            cost_table["Cost Component"] == "REC Net Position Resale",
                            "Cost Per MWh",
                        ].item()
                    )
                ],
            }
        )
    cost_table = pd.concat(
        [cost_table, total_rows],
        ignore_index=True,
    )

    if to_pv != 1:
        # rename the columns
        cost_table = cost_table.rename(
            columns={
                "Annual Real Cost": f"Annual Cost ({year}$)",
                "Cost Per MWh": f"Cost Per MWh ({year}$)",
            }
        )

        # add columns for present value
        cost_table[f"Annual Cost ({base_year}$)"] = (
            cost_table[f"Annual Cost ({year}$)"] * to_pv
        )
        cost_table[f"Cost Per MWh ({base_year}$)"] = (
            cost_table[f"Cost Per MWh ({year}$)"] * to_pv
        )
    else:
        cost_table = cost_table.rename(
            columns={
                "Annual Real Cost": f"Annual Cost ({base_year}$)",
                "Cost Per MWh": f"Cost Per MWh ({base_year}$)",
            }
        )

    return cost_table


def build_ra_open_position_plot(ra_summary):
    """
    Description

    Inputs:
        ra_summary: a dataframe containing resource adequacy summary data by requirement and month, loaded from outputs/RA_summary.csv
    Returns:
        monthly_ra_open_fig: a plotly bar chart showing the net monthly RA position for system and flex RA
    """
    ra_open = ra_summary.copy()
    # where RA Position is negative, it indicates an open position
    ra_open["Position"] = np.where(
        ra_open["RA_Position_MW"] < 0, "Open Position", "Excess RA"
    )

    # create a plot of monthly RA position
    monthly_ra_open_fig = px.bar(
        ra_open,
        x="Month",
        y="RA_Position_MW",
        facet_col="RA_Requirement",
        color="Position",
        color_discrete_map={"Excess RA": "green", "Open Position": "red"},
        title="Monthly RA position by requirement",
    ).update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    monthly_ra_open_fig.for_each_annotation(
        lambda a: a.update(text=a.text.replace("RA_Requirement=", ""))
    )

    return monthly_ra_open_fig


def build_dispatch_plot(
    generation_projects_info,
    dispatch,
    storage_dispatch,
    load_balance,
    system_power,
    technology_color_map,
    storage_exists,
):
    """
    Description

    Inputs:
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
        dispatch: a dataframe containing hourly generator dispatch data contained in outputs/dispatch.csv
        storage_dispatch: a dataframe containing hourly charge, discharge, state of charge, and nodal cost data for storage assets, loaded from outputs/storage_dispatch.csv
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
        system_power: a dataframe containing hourly system power and hedge costs, loaded from outputs/system_power.csv
        technology_color_map: a dictionary that maps generation technologies to colors for use in plots
    Returns:
        dispatch_by_tech: a dataframe with hourly generator dispatch grouped by generator technology
        load_line: a dataframe with hourly load data matched to a datetime
        storage_charge: a dataframe with hourly storage charging data formatted for the dispatch plot
        dispatch_fig: a plotly area chart showing hourly load, generation, and storage dispatch for all 8760 hours
    """
    # get the list of technologies
    generator_technology_dict = generation_projects_info[
        ["GENERATION_PROJECT", "gen_tech"]
    ]
    generator_technology_dict = dict(
        zip(
            generator_technology_dict.GENERATION_PROJECT,
            generator_technology_dict.gen_tech,
        )
    )

    dispatch_data = dispatch.copy().drop(columns="Nodal_Price")

    # add a generator technology column to the dispatch data
    dispatch_data["Technology"] = dispatch_data["generation_project"].map(
        generator_technology_dict
    )

    # replace underscores in the gen tech name with spaces
    dispatch_data.Technology = dispatch_data.Technology.str.replace("_", " ")

    # drop the curtailment column
    dispatch_data = dispatch_data.drop(columns=["CurtailGen_MW", "generation_project"])

    # rename the columns
    dispatch_data = dispatch_data.rename(
        columns={"DispatchGen_MW": "Consumed", "ExcessGen_MW": "Excess"}
    )

    # melt the data
    dispatch_data = dispatch_data.melt(
        id_vars=["Technology", "timestamp"],
        value_vars=["Consumed", "Excess"],
        var_name="Generation Type",
        value_name="MWh",
    )

    # concatenate the technology and type columns
    dispatch_data["Technology"] = (
        dispatch_data["Generation Type"] + " " + dispatch_data["Technology"]
    )

    # group the data by technology type
    dispatch_by_tech = (
        dispatch_data.groupby(["Technology", "timestamp"]).sum().reset_index()
    )

    if storage_exists:
        # append storage
        storage_discharge = storage_dispatch.copy()[
            ["timestamp", "DischargeMW"]
        ].rename(columns={"DischargeMW": "MWh"})
        # group the data
        storage_discharge = storage_discharge.groupby("timestamp").sum().reset_index()
        # add a technology column
        storage_discharge["Technology"] = "Storage Discharge"
        dispatch_by_tech = pd.concat([dispatch_by_tech, storage_discharge])

    # append grid energy
    grid_energy = (
        system_power.copy()[["timestamp", "system_power_MW"]]
        .groupby("timestamp")
        .sum()
        .reset_index()
        .rename(columns={"system_power_MW": "MWh"})
    )
    grid_energy["Technology"] = "Grid Energy"
    dispatch_by_tech = pd.concat([dispatch_by_tech, grid_energy])

    # only keep observations greater than 0
    dispatch_by_tech = dispatch_by_tech[dispatch_by_tech["MWh"] > 0]

    dispatch_by_tech["timestamp"] = pd.to_datetime(dispatch_by_tech["timestamp"])

    # prepare demand data
    load_line = load_balance.copy()[["timestamp", "zone_demand_mw"]]
    load_line["timestamp"] = pd.to_datetime(load_line["timestamp"])

    if storage_exists:
        # prepare storage charging data
        storage_charge = storage_dispatch.copy()[["timestamp", "ChargeMW"]]
        # group the data
        storage_charge = storage_charge.groupby("timestamp").sum().reset_index()
        storage_charge["timestamp"] = pd.to_datetime(storage_charge["timestamp"])
        storage_charge["Load+Charge"] = (
            load_line["zone_demand_mw"] + storage_charge["ChargeMW"]
        )
    else:
        storage_charge = pd.DataFrame()

    # Build Figure

    dispatch_fig = px.area(
        dispatch_by_tech,
        x="timestamp",
        y="MWh",
        color="Technology",
        color_discrete_map=technology_color_map,
        category_orders={
            "Technology": [
                "Consumed Geothermal",
                "Consumed Small Hydro",
                "Consumed Onshore Wind",
                "Consumed Offshore Wind",
                "Consumed Solar PV",
                "Consumed Shaped",
                "Consumed Solar Thermal",
                "Storage Discharge",
                "Grid Energy",
                "Excess Solar PV",
                "Excess Onshore Wind",
                "Excess Offshore Wind",
                "Excess Shaped",
                "Excess Solar Thermal",
            ]
        },
        labels={"timestamp": "Datetime", "Technology": "Key"},
    )
    dispatch_fig.update_traces(line={"width": 0})
    dispatch_fig.layout.template = "plotly_white"
    # add load and storage charging lines
    if storage_exists:
        dispatch_fig.add_scatter(
            x=storage_charge.timestamp,
            y=storage_charge["Load+Charge"],
            text=storage_charge["ChargeMW"],
            line=dict(color="green", width=3),
            name="Storage Charge",
        )
    dispatch_fig.add_scatter(
        x=load_line.timestamp,
        y=load_line.zone_demand_mw,
        line=dict(color="black", width=3),
        name="Demand",
    )

    dispatch_fig.update_traces(line_shape="hv")

    dispatch_fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list(
                [
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all"),
                ]
            )
        ),
    )

    return dispatch_by_tech, load_line, storage_charge, dispatch_fig


def build_nodal_prices_plot(nodal_prices, timestamps, generation_projects_info, year):
    """
    Builds a timeseries plot of all nodal prices used in the model

    Inputs:
        nodal_prices: a dataframe with hourly wholesale prices at each node, loaded from inputs/nodal_prices.csv
        timestamps: a dataframe that maps timepoints to datetimes, loaded from inputs/timepoints.csv
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
        year: the model year as an integer (YYYY)
    Returns:
        nodal_fig: a plotly line chart showing wholesale prices at each node for all 8760 hours
    """
    # merge the timestamp data
    nodal_data = nodal_prices.copy().merge(
        timestamps, how="left", left_on="timepoint", right_on="timepoint_id"
    )

    # create a dictionary mapping nodes to projects
    node_map = dict()
    for node in generation_projects_info.gen_pricing_node.unique():
        node_map[node] = list(
            generation_projects_info.loc[
                generation_projects_info["gen_pricing_node"] == node,
                "GENERATION_PROJECT",
            ].unique()
        )

    nodal_fig = (
        px.line(
            nodal_data,
            x="timestamp",
            y="nodal_price",
            color="pricing_node",
            labels={
                "nodal_price": "$/MWh",
                "timestamp": "Datetime",
                "pricing_node": "Node",
            },
            title=f"Nodal Prices ({year}$)",
            template="plotly_white",
        )
        .update_layout(hovermode="x")
        .update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    )
    nodal_fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list(
                [
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all"),
                ]
            )
        ),
    )

    return nodal_fig


def build_state_of_charge_plot(
    storage_dispatch, storage_builds, generation_projects_info
):
    """
    Description

    Inputs:
        storage_dispatch: a dataframe containing hourly charge, discharge, state of charge, and nodal cost data for storage assets, loaded from outputs/storage_dispatch.csv
        storage_builds: a dataframe containing data on built storage power and energy capacity loaded from outputs/storage_builds.csv
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
    Returns:
        soc_fig: a plotly line plot showing the aggregated hourly state of charge for all hybrid storage and all standalone storage
    """
    soc = storage_dispatch.copy()[["generation_project", "timestamp", "StateOfCharge"]]

    soc["timestamp"] = pd.to_datetime(soc["timestamp"])

    # soc = storage.pivot(index='timestamp', columns='generation_project', values='StateOfCharge')

    # identify which projects are hybrids
    hybrid_list = list(
        generation_projects_info.loc[
            generation_projects_info["storage_hybrid_generation_project"] != ".",
            "GENERATION_PROJECT",
        ].unique()
    )

    # load storage capacity
    storage_energy_capacity = storage_builds.copy()[
        ["generation_project", "OnlineEnergyCapacityMWh"]
    ]
    # add a column specifying the storage type
    storage_energy_capacity["Type"] = "Standalone Storage"
    storage_energy_capacity.loc[
        storage_energy_capacity["generation_project"].isin(hybrid_list), "Type"
    ] = "Hybrid Storage"
    # groupby type
    storage_energy_capacity = storage_energy_capacity.groupby("Type").sum()
    # create another dictionary of storage energy capacity summed by storage type
    grouped_storage_energy_capacity_dict = storage_energy_capacity.to_dict()[
        "OnlineEnergyCapacityMWh"
    ]

    # add a column specifying the storage type
    soc["Type"] = "Standalone Storage"
    soc.loc[soc["generation_project"].isin(hybrid_list), "Type"] = "Hybrid Storage"
    # groupby type
    soc = soc.groupby(["timestamp", "Type"]).sum().reset_index()

    soc = soc.pivot(index="timestamp", columns="Type", values="StateOfCharge")

    # divide by the total capacity to get state of charge
    soc = soc.div(soc.assign(**grouped_storage_energy_capacity_dict))

    # get a list of the columns in case there is only standalone or only hybrid storage
    type_columns = list(soc.columns)

    # soc.index = pd.to_datetime(soc.index)
    soc = soc.reset_index()

    soc_fig = px.line(
        soc,
        x="timestamp",
        y=type_columns,
        color_discrete_map={
            "Standalone Storage": "green",
            "Hybrid Storage": "yellowgreen",
        },
        labels={"timestamp": "Datetime", "value": "%"},
        title="Storage State of Charge",
    )

    soc_fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list(
                [
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all"),
                ]
            )
        ),
    )

    return soc_fig


def build_month_hour_dispatch_plot(
    dispatch_by_tech, load_line, storage_charge, technology_color_map, storage_exists
):
    """
    Creates a month-hour average version of the dispatch plot created by build_dispatch_plot()

    Inputs:
        dispatch_by_tech: a dataframe with hourly generator dispatch grouped by generator technology, created by the function build_dispatch_plot()
        load_line: a dataframe with hourly load data matched to a datetime, created by the function build_dispatch_plot()
        storage_charge: a dataframe with hourly storage charging data formatted for the dispatch plot, created by the function build_dispatch_plot()
        technology_color_map: a dictionary that maps generation technologies to colors for use in plots
    Returns:
        mh_fig: a plotly area plot showing the month-hour average dispatch, load, and storage dispatch
    """

    mh_dispatch = dispatch_by_tech.copy()
    mh_dispatch = mh_dispatch.set_index("timestamp")

    # groupby month and hour
    mh_dispatch = mh_dispatch.groupby(
        ["Technology", mh_dispatch.index.month, mh_dispatch.index.hour], axis=0
    ).mean()
    mh_dispatch.index = mh_dispatch.index.rename(["Technology", "Month", "Hour"])
    mh_dispatch = mh_dispatch.reset_index()

    mh_load_line = load_line.copy()
    mh_load_line = mh_load_line.set_index("timestamp")
    mh_load_line = mh_load_line.groupby(
        [mh_load_line.index.month, mh_load_line.index.hour], axis=0
    ).mean()
    mh_load_line.index = mh_load_line.index.rename(["Month", "Hour"])
    mh_load_line = mh_load_line.reset_index()

    if storage_exists:
        mh_storage_charge = storage_charge.copy()
        mh_storage_charge = mh_storage_charge.set_index("timestamp")
        mh_storage_charge = mh_storage_charge.groupby(
            [mh_storage_charge.index.month, mh_storage_charge.index.hour], axis=0
        ).mean()
        mh_storage_charge.index = mh_storage_charge.index.rename(["Month", "Hour"])
        mh_storage_charge = mh_storage_charge.reset_index()

    mh_fig = px.area(
        mh_dispatch,
        x="Hour",
        y="MWh",
        facet_col="Month",
        facet_col_wrap=6,
        color="Technology",
        color_discrete_map=technology_color_map,
        category_orders={
            "Technology": [
                "Consumed Geothermal",
                "Consumed Small Hydro",
                "Consumed Onshore Wind",
                "Consumed Offshore Wind",
                "Consumed Solar PV",
                "Consumed Shaped",
                "Consumed Solar Thermal",
                "Storage Discharge",
                "Grid Energy",
                "Excess Solar PV",
                "Excess Onshore Wind",
                "Excess Offshore Wind",
                "Excess Shaped",
                "Excess Solar Thermal",
            ]
        },
        labels={"timestamp": "Datetime", "Technology": "Key"},
    )
    mh_fig.update_traces(line={"width": 0})
    mh_fig.layout.template = "plotly_white"
    mh_fig.update_xaxes(dtick=3)

    if storage_exists:
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 1, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 1, "Load+Charge"],
            line=dict(color="green", width=4),
            row=2,
            col=1,
            name="Storage Charge",
            showlegend=True,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 1, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 2, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 2, "Load+Charge"],
            line=dict(color="green", width=4),
            row=2,
            col=2,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 2, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 3, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 3, "Load+Charge"],
            line=dict(color="green", width=4),
            row=2,
            col=3,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 3, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 4, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 4, "Load+Charge"],
            line=dict(color="green", width=4),
            row=2,
            col=4,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 4, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 5, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 5, "Load+Charge"],
            line=dict(color="green", width=4),
            row=2,
            col=5,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 5, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 6, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 6, "Load+Charge"],
            line=dict(color="green", width=4),
            row=2,
            col=6,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 6, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 7, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 7, "Load+Charge"],
            line=dict(color="green", width=4),
            row=1,
            col=1,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 7, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 8, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 8, "Load+Charge"],
            line=dict(color="green", width=4),
            row=1,
            col=2,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 8, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 9, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 9, "Load+Charge"],
            line=dict(color="green", width=4),
            row=1,
            col=3,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 9, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 10, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 10, "Load+Charge"],
            line=dict(color="green", width=4),
            row=1,
            col=4,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 10, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 11, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 11, "Load+Charge"],
            line=dict(color="green", width=4),
            row=1,
            col=5,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 11, "ChargeMW"],
        )
        mh_fig.add_scatter(
            x=mh_storage_charge.loc[mh_storage_charge["Month"] == 12, "Hour"],
            y=mh_storage_charge.loc[mh_storage_charge["Month"] == 12, "Load+Charge"],
            line=dict(color="green", width=4),
            row=1,
            col=6,
            name="Storage Charge",
            showlegend=False,
            text=mh_storage_charge.loc[mh_storage_charge["Month"] == 12, "ChargeMW"],
        )

    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 1, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 1, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=2,
        col=1,
        name="Demand",
        showlegend=True,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 2, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 2, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=2,
        col=2,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 3, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 3, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=2,
        col=3,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 4, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 4, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=2,
        col=4,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 5, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 5, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=2,
        col=5,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 6, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 6, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=2,
        col=6,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 7, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 7, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=1,
        col=1,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 8, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 8, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=1,
        col=2,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 9, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 9, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=1,
        col=3,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 10, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 10, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=1,
        col=4,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 11, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 11, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=1,
        col=5,
        name="Demand",
        showlegend=False,
    )
    mh_fig.add_scatter(
        x=mh_load_line.loc[mh_load_line["Month"] == 12, "Hour"],
        y=mh_load_line.loc[mh_load_line["Month"] == 12, "zone_demand_mw"],
        line=dict(color="black", width=4),
        row=1,
        col=6,
        name="Demand",
        showlegend=False,
    )

    mh_fig.update_traces(line_shape="hv")

    month_names = [
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
    ]
    for i, a in enumerate(mh_fig.layout.annotations):
        a.text = month_names[i]

    return mh_fig


def build_open_position_plot(load_balance, storage_exists):
    """
    Builds a plot showing the average open position and excess generation for each month-hour

    Inputs:
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
    Returns:
        mh_mismatch_fig: a plotly area chart showing the net generation position, both with and without storage dispatch
    """
    # merge mismatch data
    mismatch = load_balance.copy()
    mismatch["timestamp"] = pd.to_datetime(mismatch["timestamp"])

    mismatch["Net generation"] = (
        mismatch["ZoneTotalGeneratorDispatch"]
        + mismatch["ZoneTotalExcessGen"]
        - mismatch["zone_demand_mw"]
    )
    if storage_exists:
        mismatch["Net position with storage"] = (
            mismatch["Net generation"]
            + mismatch["ZoneTotalStorageDischarge"]
            - mismatch["ZoneTotalStorageCharge"]
        )
    else:
        mismatch["Net position with storage"] = 0

    mismatch = mismatch.set_index("timestamp")

    mismatch = mismatch.groupby(
        [mismatch.index.month, mismatch.index.hour], axis=0
    ).mean()
    mismatch.index = mismatch.index.rename(["Month", "Hour"])
    mismatch = mismatch.reset_index()

    # set month numbers to names
    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    mismatch["Month"] = mismatch["Month"].replace(month_names)

    mh_mismatch_fig = px.line(
        mismatch,
        x="Hour",
        y=["Net generation", "Net position with storage"],
        facet_col="Month",
        facet_col_wrap=6,
        labels={"variable": "Position", "value": "MW"},
    ).update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    mh_mismatch_fig.update_xaxes(dtick=3)
    mh_mismatch_fig.for_each_annotation(
        lambda a: a.update(text=a.text.replace("Month=", ""))
    )
    mh_mismatch_fig.update_traces(fill="tozeroy", line_shape="hv")

    return mh_mismatch_fig


def construct_storage_stats_table(
    storage_cycle_count, storage_builds, storage_dispatch
):
    """
    Calculates key stats for all built storage assets, including annual average state of charge, cycle limits, and total number of cycles

    Inputs:
        storage_cycle_count: a dataframe containing storage cycle count data, loaded from outputs/storage_cycle_count.csv
        storage_builds: a dataframe containing data on built storage power and energy capacity loaded from outputs/storage_builds.csv
        storage_dispatch: a dataframe containing hourly charge, discharge, state of charge, and nodal cost data for storage assets, loaded from outputs/storage_dispatch.csv
    Returns:
        cycles: a dataframe summarizing annual storage cycles and average state of charge for each storage asset
    """

    cycles = storage_cycle_count.copy()[
        ["generation_project", "storage_max_annual_cycles", "Battery_Cycle_Count"]
    ]
    cycles = cycles.round(decimals=2)
    cycles = cycles[cycles["Battery_Cycle_Count"] > 0]

    # merge average state of charge data
    soc = storage_dispatch.copy()[["generation_project", "StateOfCharge"]]
    soc = soc.groupby("generation_project").mean().reset_index()
    cycles = cycles.merge(soc, how="left", on="generation_project")

    # merge energy capacity data
    storage_energy_capacity = storage_builds.copy()[
        ["generation_project", "OnlineEnergyCapacityMWh"]
    ]
    cycles = cycles.merge(storage_energy_capacity, how="left", on="generation_project")

    # calculate the number of cycles
    cycles["Battery_Cycle_Count"] = (
        cycles["Battery_Cycle_Count"] / cycles["OnlineEnergyCapacityMWh"]
    )

    # calculate the average state of charge
    cycles["Average SOC Percent"] = (
        cycles["StateOfCharge"] / cycles["OnlineEnergyCapacityMWh"] * 100
    )

    # drop unused columns
    cycles = cycles.drop(
        columns=["OnlineEnergyCapacityMWh", "StateOfCharge"]
    ).set_index("generation_project")
    cycles["Battery_Cycle_Count"] = cycles["Battery_Cycle_Count"].astype(int)

    cycles = cycles.rename(
        columns={
            "Battery_Cycle_Count": "Annual Cycles",
            "storage_max_annual_cycles": "Maximum Annual Cycle Limit",
        }
    )

    return cycles


def calculate_BuildGen_reduced_costs(
    results,
    generation_projects_info,
    variable_capacity_factors,
    baseload_capacity_factors,
    dispatch,
):
    """
    Calculates the reduced costs of all modeled generators and splits the results into separate tables for interpretation

    Inputs:
        results: raw model results, loaded from outputs/results.pickle
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
        variable_capacity_factors: a dataframe containing hourly capacity factors for each variable generator, loaded from inputs/variable_capacity_factors.csv
        baseload_capacity_factors: a dataframe containing hourly capacity factors for each baseload generator, loaded from inputs/baseload_capacity_factors.csv
        dispatch: a dataframe containing hourly generator dispatch data contained in outputs/dispatch.csv
    Returns:
        pos_rc_lower: a dataframe containing reduced costs for all generators that were not selected (BuildGen = 0 with reduced cost > 0)
        pos_rc_upper: a dataframe containing reduced costs for all generators that were forced to be built but otherwise would not have been selected (BuildGen > 0 with reduced cost > 0)
        neg_rc: a dataframe containing reduced costs for all generators that were built at maximum capacity but constrained (BuildGen = gen_max_capacity_limit with reduced cost < 0)
        alternate_optima: a dataframe containing reduced costs for any generators that represent an alternate optimal point (BuildGen = 0 and reduced cost = 0)
    """
    # load results into dataframe and reset index
    rc = pd.DataFrame.from_dict(results.solution.Variable, orient="index")
    rc = rc.reset_index()

    # split the index column into the variable name and index value
    rc[["Variable", "index"]] = rc["index"].str.split("[", expand=True)
    rc["index"] = rc["index"].str.strip("]")

    rc = rc[rc["Variable"] == "BuildGen"]

    # split the index into the load zone and timepoint components
    rc[["generation_project", "period"]] = rc["index"].str.split(",", expand=True)
    rc = rc.drop(columns=["period", "index"])

    # merge in generator characteristic data
    rc = rc.merge(
        generation_projects_info[
            [
                "GENERATION_PROJECT",
                "gen_is_variable",
                "gen_is_baseload",
                "gen_is_storage",
                "ppa_energy_cost",
                "ppa_capacity_cost",
            ]
        ],
        how="left",
        left_on="generation_project",
        right_on="GENERATION_PROJECT",
    ).drop(columns=["GENERATION_PROJECT"])

    # sum capacity factors by generator
    vcf = (
        variable_capacity_factors.copy()
        .groupby("GENERATION_PROJECT")
        .sum()[["variable_capacity_factor"]]
        .reset_index()
    )
    try:
        bcf = (
            baseload_capacity_factors.copy()
            .groupby("GENERATION_PROJECT")
            .sum()[["baseload_capacity_factor"]]
            .reset_index()
        )
    # if there are no baseload generators
    except KeyError:
        bcf = baseload_capacity_factors.copy()

    gen_list = list(rc["generation_project"].unique())

    for g in gen_list:
        # if the reduced cost is negative, ignore it
        if rc.loc[rc["generation_project"] == g, "Rc"].item() < 0:
            pass
        # if the generator is variable
        elif rc.loc[rc["generation_project"] == g, "gen_is_variable"].item() == 1:
            # calculate the reduced cost per MW capacity
            rc.loc[rc["generation_project"] == g, "Rc"] = (
                rc.loc[rc["generation_project"] == g, "Rc"].item()
                / vcf.loc[
                    vcf["GENERATION_PROJECT"] == g, "variable_capacity_factor"
                ].item()
            )
        # otherwise if the generator is baseload
        elif rc.loc[rc["generation_project"] == g, "gen_is_baseload"].item() == 1:
            # calculate the reduced cost per MW capacity
            rc.loc[rc["generation_project"] == g, "Rc"] = (
                rc.loc[rc["generation_project"] == g, "Rc"].item()
                / bcf.loc[
                    bcf["GENERATION_PROJECT"] == g, "baseload_capacity_factor"
                ].item()
            )
        # otherwise if the generator is storage
        elif rc.loc[rc["generation_project"] == g, "gen_is_storage"].item() == 1:
            pass
        # otherwise the generator is dispatchable and we need to calculate how much it actually dispatched
        else:
            # calculate the total dispatch
            total_dispatch = (
                dispatch[dispatch["generation_project"] == g]
                .sum()[["DispatchGen_MW", "ExcessGen_MW"]]
                .sum()
            )
            # convert to a capacity factor total
            total_cf = (
                total_dispatch / rc.loc[rc["generation_project"] == g, "Value"].item()
            )
            # calculate reduced cost per MW capacity
            rc.loc[rc["generation_project"] == g, "Rc"] = (
                rc.loc[rc["generation_project"] == g, "Rc"] / total_cf
            )

    # drop unneccessary columns
    rc = rc.drop(
        columns=["Variable", "gen_is_variable", "gen_is_baseload", "gen_is_storage"]
    )
    rc = rc.rename(columns={"Value": "built_MW", "Rc": "reduced_cost"})

    rc = rc[
        [
            "generation_project",
            "built_MW",
            "ppa_energy_cost",
            "ppa_capacity_cost",
            "reduced_cost",
        ]
    ].set_index("generation_project")

    # negative reduced costs apply to upper bounds
    neg_rc = rc.copy()[rc["reduced_cost"] < 0]
    neg_rc = neg_rc.sort_values(by="reduced_cost")
    # positive reduced costs apply to lower bounds
    pos_rc = rc.copy()[rc["reduced_cost"] > 0]
    pos_rc["Cost to be built"] = (
        pos_rc["ppa_energy_cost"] + pos_rc["ppa_capacity_cost"] - pos_rc["reduced_cost"]
    )
    # zero reduced cost with a value of zero means that there is another optimal solution
    alternate_optima = rc.copy()[(rc["reduced_cost"] == 0) & (rc["built_MW"] == 0)]

    # the positive reduced costs can be split into two groups
    pos_rc_lower = pos_rc.copy()[pos_rc["built_MW"] == 0]
    pos_rc_upper = pos_rc.copy()[pos_rc["built_MW"] > 0]

    return pos_rc_lower, pos_rc_upper, neg_rc, alternate_optima


def calculate_load_shadow_price(results, timestamps, year):
    """
    Using the dual values from the load balance constraint, identifies the shadow price of load

    Inputs:
        results: raw model results, loaded from outputs/results.pickle
        timestamps: a dataframe that maps timepoints to datetimes, loaded from inputs/timepoints.csv
        year: the model year as an integer (YYYY)
    Returns:
        dual_plot: a plotly plot showing the month-hour average of all positive shadow prices
    """
    # load the duals into a dataframe and reset the index
    duals = pd.DataFrame.from_dict(results.solution.Constraint, orient="index")
    duals = duals.reset_index()

    # split the index into columns for the constraint name and the index value
    duals[["Constraint", "index"]] = duals["index"].str.split("[", expand=True)
    # duals['index'] = '[' + duals['index']
    duals["index"] = duals["index"].str.strip("]")

    # filter the constraints to the zone energy balance
    duals = duals[duals["Constraint"] == "Zone_Energy_Balance"]

    # split the index into the load zone and timepoint components
    duals[["load_zone", "timepoint"]] = duals["index"].str.split(",", expand=True)
    duals["timepoint"] = duals["timepoint"].astype(int)
    duals = duals.drop(columns=["index"])

    # merge the timestamp data
    duals = duals.copy().merge(
        timestamps, how="left", left_on="timepoint", right_on="timepoint_id"
    )

    # sort the values
    duals = duals.sort_values(by=["load_zone", "timepoint"])

    # re-order columns
    # duals = duals[['Constraint', 'load_zone','timepoint','Dual']]

    # Calculate the month-hour average
    duals = duals.set_index("timestamp")
    duals = duals.groupby([duals.index.month, duals.index.hour]).mean()
    duals.index = duals.index.rename(["Month", "Hour"])
    duals = duals.reset_index()

    # set month numbers to names
    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    duals["Month"] = duals["Month"].replace(month_names)

    dual_plot = px.line(
        duals,
        x="Hour",
        y="Dual",
        facet_col="Month",
        title=f"Shadow Price of Load ({year}$)",
        facet_col_wrap=6,
        labels={"Dual": "Shadow Price ($/MW)"},
    )

    dual_plot.for_each_annotation(lambda a: a.update(text=a.text.replace("Month=", "")))
    dual_plot.update_xaxes(dtick=3)
    dual_plot.update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    dual_plot.update_traces(line_shape="hv")

    return dual_plot


def construct_summary_output_table(
    scenario_name,
    cost_table,
    load_balance,
    portfolio,
    sensitivity_table,
    lr_impact,
    total_emissions,
    peaks,
    ramps,
    emissions_unit,
    base_year,
    financial_year,
    dispatch,
):
    """
    Creates a csv file output of key metrics from the summary report to compare with other scenarios.

    These metrics include:
        - Scenario Name
        - Time-coincident %
        - Annual volumetric %
        - Delivered Cost per MWh
        - Sensitivity performance results
        - Portfolio mix by generation technology
        - Annual Emissions Footprint
        - Annual average delivered emission factor
        - Avoided emissions impact

    Inputs:
        scenario_name: string identifying the name of the scenario, loaded from the output file name
        cost_table:a dataframe summarizing delivered costs by total and cost per MWh, calculated by the construct_cost_and_resale_tables() function
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
        portfolio: a dataframe summarizing the built portfolio, created as an output of the generator_portfolio() function
        sensitivity_table: a dataframe summarizing the time-coincident % performance in each weather year tested, calculated by the run_sensitivity_analysis() function
        avoided_emissions: a dataframe containing the total annual avoided emissions from additional generators under each Cambium case, calculated byt the calculate_avoided_emissions() function
        emissions: a dataframe containing hourly output emissions from dispatched generation and grid power, loaded from outputs/emissions.csv
        emissions_unit: a string identifying the unit of measure used for emission rates, loaded from inputs/ghg_emissions_unit.txt
    Returns:
        summary: a dataframe containing key metrics from this scenario
    """

    summary = pd.DataFrame(columns=["Scenario Name"], data=["test"])

    summary["Scenario Name"] = scenario_name

    # Goal Data
    summary["Annual Volumetric %"] = annual_renewable_percentage(load_balance)
    summary["Time-coincident %"] = hourly_renewable_percentage(load_balance)

    # if no sensitivity table was created, skip this
    try:
        for year in list(sensitivity_table["Weather Year"]):
            summary[f"Sensitivity Performance Year {year}"] = sensitivity_table.loc[
                sensitivity_table["Weather Year"] == year, "Time-Coincident %"
            ].item()
    except (AttributeError, TypeError) as e:
        pass

    # portfolio cost per MWh
    summary[f"Portfolio Cost per MWh ({base_year}$)"] = cost_table.loc[
        cost_table["Cost Component"] == "Total", f"Cost Per MWh ({base_year}$)"
    ].item()
    summary[f"Portfolio Cost per MWh No Resale ({base_year}$)"] = cost_table.loc[
        (
            (cost_table["Cost Component"] == "Total without REC/RA Resale")
            | (cost_table["Cost Component"] == "Total without REC Resale")
        ),
        f"Cost Per MWh ({base_year}$)",
    ].item()
    summary[f"Portfolio Cost per MWh ({financial_year}$)"] = cost_table.loc[
        cost_table["Cost Component"] == "Total", f"Cost Per MWh ({financial_year}$)"
    ].item()
    summary[f"Portfolio Cost per MWh No Resale ({financial_year}$)"] = cost_table.loc[
        (
            (cost_table["Cost Component"] == "Total without REC/RA Resale")
            | (cost_table["Cost Component"] == "Total without REC Resale")
        ),
        f"Cost Per MWh ({financial_year}$)",
    ].item()
    # total portfolio cost
    summary[f"Total Portfolio Cost ({base_year}$)"] = cost_table.loc[
        cost_table["Cost Component"] == "Total", f"Annual Cost ({base_year}$)"
    ].item()
    summary[f"Total Portfolio Cos No Resale ({base_year}$)"] = cost_table.loc[
        (
            (cost_table["Cost Component"] == "Total without REC/RA Resale")
            | (cost_table["Cost Component"] == "Total without REC Resale")
        ),
        f"Annual Cost ({base_year}$)",
    ].item()
    summary[f"Total Portfolio Cost ({financial_year}$)"] = cost_table.loc[
        cost_table["Cost Component"] == "Total", f"Annual Cost ({financial_year}$)"
    ].item()
    summary[f"Total Portfolio Cost No Resale ({financial_year}$)"] = cost_table.loc[
        (
            (cost_table["Cost Component"] == "Total without REC/RA Resale")
            | (cost_table["Cost Component"] == "Total without REC Resale")
        ),
        f"Annual Cost ({financial_year}$)",
    ].item()

    # Portfolio Mix
    portfolio_summary = (
        portfolio[["MW", "Contract Status", "Technology"]]
        .groupby(["Contract Status", "Technology"])
        .sum()
        .reset_index()
    )
    portfolio_summary["Description"] = (
        portfolio_summary["Contract Status"] + " " + portfolio_summary["Technology"]
    )
    portfolio_summary = portfolio_summary.drop(
        columns=["Contract Status", "Technology"]
    )
    portfolio_summary = (
        portfolio_summary.set_index("Description")
        .transpose()
        .reset_index(drop=True)
        .add_prefix("MW Capacity from ")
    )
    portfolio_summary["Total MW Capacity"] = portfolio_summary.sum(axis=1)

    summary = pd.concat([summary, portfolio_summary], axis=1)

    summary[f'Annual Emissions Footprint ({emissions_unit.split("/")[0]})'] = round(
        total_emissions["Total Emission Rate"].sum(), 1
    )
    summary[f"Delivered Emissions Factor ({emissions_unit})"] = round(
        total_emissions["Delivered Emission Factor"].mean(), 3
    )

    for index in lr_impact.index:
        summary[
            f"Long-run Marginal Impact ({emissions_unit}) [{index}]"
        ] = lr_impact.loc[index, f"Total {emissions_unit}"]
        summary[
            f'Long-run Marginal Impact ({emissions_unit.split("/")[0]}) [{index}]'
        ] = lr_impact.loc[index, f'Total {emissions_unit.split("/")[0]}']

    summary["Impact on System Peak No Storage"] = peaks.loc[
        "Average", "portfolio_impact_no_storage"
    ]
    summary["Impact on System Peak With Storage"] = peaks.loc[
        "Average", "portfolio_impact_with_storage"
    ]

    summary["Impact on System Ramp No Storage"] = ramps.loc[
        "Average", "portfolio_impact_no_storage"
    ]
    summary["Impact on System Ramp With Storage"] = ramps.loc[
        "Average", "portfolio_impact_with_storage"
    ]

    summary["Curtailment"] = dispatch["CurtailGen_MW"].sum()

    summary = summary.transpose()
    summary.columns = [f"{scenario_name}"]

    return summary


def run_sensitivity_analysis(
    gen_set,
    gen_cap,
    dispatch,
    generation_projects_info,
    load_balance,
    storage_builds,
    storage_exists,
):
    """
    Assesses the portfolio's time-coincident performance based on variable generation in different weather years, utilizing a simplified greedy storage algorithm to dispatch storage assets.

    Inputs:
        gen_set: a string identifying the name of the generator set used for this scenario, loaded from inputs/gen_set.txt
        gen_cap: a dataframe containing data on built generator capacity loaded from outputs/gen_cap.csv
        dispatch: a dataframe containing hourly generator dispatch data loaded from outputs/dispatch.csv
        generation_projects_info: a dataframe containing generator parameters loaded from inputs/generation_project_info.csv
        load_balance: a dataframe containing hourly supply and demand balance data loaded from outputs/load_balance.csv
        storage_builds: a dataframe containing data on built storage power and energy capacity loaded from outputs/storage_builds.csv
    Returns:
        sensitivity_table: a dataframe summarizing the time-coincident % performance in each weather year tested
    """
    # specify the path to the folder than contains the SAM weather data
    set_folder = Path.cwd() / f"../../{gen_set}/"

    try:
        # get a list of all weather year file names in this folder
        weather_years = [
            filename for filename in os.listdir(set_folder) if ".csv" in filename
        ]
        if "projects_with_overbuild_risk.csv" in weather_years:
            weather_years.remove("projects_with_overbuild_risk.csv")
    except FileNotFoundError:
        return None

    # get dataframe of all generators that were built
    built_gens = gen_cap.copy()[gen_cap["GenCapacity"] > 0]

    # remove storage generators from the list of built generators
    built_gens = built_gens[built_gens["gen_tech"] != "Storage"]

    # create a blank dataframe to hold the results
    sensitivity_table = pd.DataFrame(columns=["Weather Year", "Time-Coincident %"])

    # get a list of all hybrid generators
    hybrid_gens = list(
        generation_projects_info.loc[
            (
                (generation_projects_info["gen_is_hybrid"] == 1)
                & (generation_projects_info["gen_is_storage"] == 0)
            ),
            "GENERATION_PROJECT",
        ]
    )

    # get a list of all hybrid storage projects
    hybrid_storage = list(
        generation_projects_info.loc[
            (
                (generation_projects_info["gen_is_hybrid"] == 1)
                & (generation_projects_info["gen_is_storage"] == 1)
            ),
            "GENERATION_PROJECT",
        ]
    )

    # for each weather year
    for weather_year in weather_years:
        # get the year number from the file name
        year = weather_year.split("_")[0]

        # load weather year data
        vcf_for_year = pd.read_csv(set_folder / weather_year)

        # create a blank dataframe
        balance = pd.DataFrame(index=range(8760))
        generation = pd.DataFrame(index=range(8760))

        # for each generator
        for gen in list(built_gens["generation_project"]):
            # get the built MW capacity
            built_capacity = float(
                built_gens.loc[
                    built_gens["generation_project"] == gen, "GenCapacity"
                ].item()
            )
            # if the generator is solar, calculate the solar age degredation
            if (
                generation_projects_info.loc[
                    generation_projects_info["GENERATION_PROJECT"] == gen, "gen_tech"
                ].item()
                == "Solar_PV"
            ):
                model_year = gen_cap.loc[0, "PERIOD"].item()
                degredation_factor = (1 - 0.005) ** (
                    model_year
                    - generation_projects_info.loc[
                        generation_projects_info["GENERATION_PROJECT"] == gen,
                        "cod_year",
                    ].item()
                )
            else:
                degredation_factor = 1

            try:
                # if the generator is represented in the SAM weather data, calculate the new dispatch profile
                vcf = vcf_for_year[gen]
                generation[gen] = built_capacity * vcf * degredation_factor
            except KeyError:
                # otherwise, if the generator had a manually-inputted capacity factor, get the dispatch profile from the model outputs
                generation[gen] = (
                    dispatch.copy()
                    .loc[
                        dispatch["generation_project"] == gen,
                        ["DispatchGen_MW", "ExcessGen_MW", "CurtailGen_MW"],
                    ]
                    .reset_index(drop=True)
                    .sum(axis=1)
                )

        # sum to get total generation from hybrid generators and all other generators
        balance["hybrid_generation"] = generation[
            [gen for gen in generation.columns if gen in hybrid_gens]
        ].sum(axis=1)
        balance["generation"] = generation[
            [gen for gen in generation.columns if gen not in hybrid_gens]
        ].sum(axis=1)

        # add load
        balance["load"] = load_balance["zone_demand_mw"]

        # add a placeholder column for grid power
        balance["grid_power"] = 0
        # add placeholder columns for hybrid storage dynamics
        balance["hybrid_charge"] = 0
        balance["hybrid_discharge"] = 0
        balance["hybrid_soc"] = 0
        # add placeholder columns for storage dynamics
        balance["charge"] = 0
        balance["discharge"] = 0
        balance["soc"] = 0

        if storage_exists:
            # filter the storage data to only include storage assets that were built
            built_storage = storage_builds.copy()[
                storage_builds["OnlinePowerCapacityMW"] > 0
            ]

            # get storage parameters for hybrid and standalone storage
            hybrid_storage_power = built_storage.loc[
                built_storage["generation_project"].isin(hybrid_storage),
                "OnlinePowerCapacityMW",
            ].sum()
            hybrid_storage_energy = built_storage.loc[
                built_storage["generation_project"].isin(hybrid_storage),
                "OnlineEnergyCapacityMWh",
            ].sum()
            storage_power = built_storage.loc[
                ~built_storage["generation_project"].isin(hybrid_storage),
                "OnlinePowerCapacityMW",
            ].sum()
            storage_energy = built_storage.loc[
                ~built_storage["generation_project"].isin(hybrid_storage),
                "OnlineEnergyCapacityMWh",
            ].sum()

            # get the hybrid interconnection limit based on nameplate capacity of the generator portion
            hybrid_interconnect_limit = built_gens.loc[
                built_gens["generation_project"].isin(hybrid_gens), "GenCapacity"
            ].sum()

            # calculate an energy capacity weighted average of RTE for all storage
            rte_calc = built_storage.copy().merge(
                generation_projects_info[
                    ["GENERATION_PROJECT", "storage_roundtrip_efficiency"]
                ],
                how="left",
                left_on="generation_project",
                right_on="GENERATION_PROJECT",
            )
            rte_calc["product"] = rte_calc["OnlineEnergyCapacityMWh"] * rte_calc[
                "storage_roundtrip_efficiency"
            ].astype(float)

            # if there are any hybrid storage assets
            if hybrid_storage_energy > 0:
                # calculate the RTE
                hybrid_storage_rte = (
                    rte_calc.loc[
                        rte_calc["generation_project"].isin(hybrid_storage), "product"
                    ].sum()
                    / hybrid_storage_energy
                )
                # calculate the one-way conversion loss from RTE
                hybrid_conversion_loss = math.sqrt(hybrid_storage_rte)
                # set the initial state of change as 50% of the total energy capacity
                hybrid_initial_soc = hybrid_storage_energy / 2

            # if there are any standalone storage assets
            if storage_energy > 0:
                # calculate the RTE
                storage_rte = (
                    rte_calc.loc[
                        ~rte_calc["generation_project"].isin(hybrid_storage), "product"
                    ].sum()
                    / storage_energy
                )
                # calculate the one-way conversion loss from RTE
                conversion_loss = math.sqrt(storage_rte)
                # set the initial state of change as 50% of the total energy capacity
                initial_soc = storage_energy / 2

            # greedy storage charging algorithm
            for t in range(len(balance)):
                # get the generation and load for the current timepoint
                hybrid_generation_t = balance.loc[t, "hybrid_generation"]
                generation_t = balance.loc[t, "generation"]
                total_generation_t = hybrid_generation_t + generation_t
                load_t = balance.loc[t, "load"]

                # for the first timepoint, use the initial values
                if t == 0:
                    # first dispatch hybrid batteries
                    if hybrid_storage_energy > 0:
                        # charge or discharge the battery based on the current load balance
                        balance.loc[t, "hybrid_charge"] = (
                            0
                            if (total_generation_t < load_t)
                            else min(
                                (
                                    total_generation_t - load_t
                                ),  # total excess generation
                                hybrid_generation_t,  # total hybrid generation
                                hybrid_storage_power,  # power limit
                                (
                                    (hybrid_storage_energy - hybrid_initial_soc)
                                    / hybrid_conversion_loss
                                ),
                            )
                        )  # available energy capacity
                        balance.loc[t, "hybrid_discharge"] = (
                            0
                            if (total_generation_t > load_t)
                            else min(
                                (load_t - total_generation_t),  # total open position
                                hybrid_interconnect_limit
                                - hybrid_generation_t,  # available interconnect capacity
                                hybrid_storage_power,  # power limit
                                (hybrid_initial_soc * hybrid_conversion_loss),
                            )
                        )  # available energy capacity
                        # calculate the ending state of charge after charging/discharging
                        balance.loc[t, "hybrid_soc"] = (
                            hybrid_initial_soc
                            + balance.loc[t, "hybrid_charge"] * hybrid_conversion_loss
                            - balance.loc[t, "hybrid_discharge"]
                            / hybrid_conversion_loss
                        )
                    # then dispatch standalone batteries
                    if storage_energy > 0:
                        generation_net_hybrid_t = (
                            total_generation_t
                            + balance.loc[t, "hybrid_discharge"]
                            - balance.loc[t, "hybrid_charge"]
                        )
                        # charge or discharge the battery based on the current load balance
                        balance.loc[t, "charge"] = (
                            0
                            if (generation_net_hybrid_t < load_t)
                            else min(
                                (generation_net_hybrid_t - load_t),
                                storage_power,
                                ((storage_energy - initial_soc) / conversion_loss),
                            )
                        )
                        balance.loc[t, "discharge"] = (
                            0
                            if (generation_net_hybrid_t > load_t)
                            else min(
                                (load_t - generation_net_hybrid_t),
                                storage_power,
                                (initial_soc * conversion_loss),
                            )
                        )
                        # calculate the ending state of charge after charging/discharging
                        balance.loc[t, "soc"] = (
                            initial_soc
                            + balance.loc[t, "charge"] * conversion_loss
                            - balance.loc[t, "discharge"] / conversion_loss
                        )

                # for all other timepoints, use the previous timepoint value
                else:
                    # first dispatch hybrid batteries
                    if hybrid_storage_energy > 0:
                        hybrid_soc_prev = balance.loc[t - 1, "hybrid_soc"]
                        # charge or discharge the battery based on the current load balance
                        balance.loc[t, "hybrid_charge"] = (
                            0
                            if (total_generation_t < load_t)
                            else min(
                                (
                                    total_generation_t - load_t
                                ),  # total excess generation
                                hybrid_generation_t,  # total hybrid generation
                                hybrid_storage_power,  # power limit
                                (
                                    (hybrid_storage_energy - hybrid_soc_prev)
                                    / hybrid_conversion_loss
                                ),
                            )
                        )  # available energy capacity
                        balance.loc[t, "hybrid_discharge"] = (
                            0
                            if (total_generation_t > load_t)
                            else min(
                                (load_t - total_generation_t),  # total open position
                                hybrid_interconnect_limit
                                - hybrid_generation_t,  # available interconnect capacity
                                hybrid_storage_power,  # power limit
                                (hybrid_soc_prev * hybrid_conversion_loss),
                            )
                        )  # available energy capacity
                        # calculate the ending state of charge after charging/discharging
                        balance.loc[t, "hybrid_soc"] = (
                            hybrid_soc_prev
                            + balance.loc[t, "hybrid_charge"] * hybrid_conversion_loss
                            - balance.loc[t, "hybrid_discharge"]
                            / hybrid_conversion_loss
                        )
                    # then dispatch standalone batteries
                    if storage_energy > 0:
                        soc_prev = balance.loc[t - 1, "soc"]
                        generation_net_hybrid_t = (
                            total_generation_t
                            + balance.loc[t, "hybrid_discharge"]
                            - balance.loc[t, "hybrid_charge"]
                        )
                        # charge or discharge the battery based on the current load balance
                        balance.loc[t, "charge"] = (
                            0
                            if (generation_net_hybrid_t < load_t)
                            else min(
                                (generation_net_hybrid_t - load_t),
                                storage_power,
                                ((storage_energy - soc_prev) / conversion_loss),
                            )
                        )
                        balance.loc[t, "discharge"] = (
                            0
                            if (generation_net_hybrid_t > load_t)
                            else min(
                                (load_t - generation_net_hybrid_t),
                                storage_power,
                                (soc_prev * conversion_loss),
                            )
                        )
                        # calculate the ending state of charge after charging/discharging
                        balance.loc[t, "soc"] = (
                            soc_prev
                            + balance.loc[t, "charge"] * conversion_loss
                            - balance.loc[t, "discharge"] / conversion_loss
                        )

                # after dispatching the battery, fill any remaining open position with grid power
                balance.loc[t, "grid_power"] = (
                    0
                    if (
                        (
                            total_generation_t
                            + balance.loc[t, "hybrid_discharge"]
                            + balance.loc[t, "discharge"]
                        )
                        >= load_t
                    )
                    else (
                        load_t
                        - (
                            total_generation_t
                            + balance.loc[t, "hybrid_discharge"]
                            + balance.loc[t, "discharge"]
                        )
                    )
                )
        else:
            for t in range(len(balance)):
                generation_t = balance.loc[t, "generation"]
                load_t = balance.loc[t, "load"]
                # fill any remaining open position with grid power
                balance.loc[t, "grid_power"] = (
                    0 if ((generation_t) >= load_t) else (load_t - (generation_t))
                )

        tc_performance = (1 - (balance.grid_power.sum() / balance.load.sum())) * 100

        print(
            f"Time-coincident performance using year {year} weather data: {tc_performance.round(2)}%"
        )
        sensitivity_table = pd.concat(
            [
                sensitivity_table,
                pd.DataFrame(
                    {"Weather Year": [year], "Time-Coincident %": [tc_performance]}
                ),
            ],
            ignore_index=True,
        )

    return sensitivity_table


def load_cambium_data(scenario, year, region):

    # specify the location of the directory where the NREL cambium data is downloaded
    cambium_dir = Path.cwd() / f"../../../nrel_cambium_{region}"

    # if the year is an even number, load the file corresponding to the year
    if year % 2 == 0:
        year_to_load = year
    else:
        year_to_load = year + 1

    cambium = pd.read_csv(
        cambium_dir / f"StdScen21_{scenario}_hourly_{region}_{year_to_load}.csv",
        skiprows=4,
    )

    cambium = cambium.drop(columns=["timestamp", "timestamp_local"])

    # create a datetime index, skipping leap days
    dates = pd.date_range(
        start=f"01/01/{year} 00:00",
        end=f"12/31/{year} 23:00",
        freq="H",
        name="timestamp_local",
    )
    cambium.index = pd.DatetimeIndex(
        data=(t for t in dates if ((t.month != 2) | (t.day != 29)))
    )

    cambium.index = cambium.index.rename("timestamp")

    return cambium


def calculate_residual_mix(cambium, emissions_unit):
    """
    This function estimates an hourly residual mix emission rate using data from Cambium.
    Because Cambium does not report residual mix, we must estimate it as the emission factor of all fossil generation in the region
    """
    if "CO2e" in emissions_unit:
        ghg = "co2e"
        ghg_unit = "CO2e"
    else:
        ghg = "co2"
        ghg_unit = "CO2"

    resid_mix = cambium.copy()[
        [
            "enduse_load",
            "busbar_load",
            "distloss_rate_avg",
            f"aer_load_{ghg}_c",
            "generation",
            "coal_MWh",
            "coal-ccs_MWh",
            "o-g-s_MWh",
            "gas-cc_MWh",
            "gas-cc-ccs_MWh",
            "gas-ct_MWh",
        ]
    ]

    # calculate total busbar emissions
    resid_mix["total_emissions"] = (
        resid_mix[f"aer_load_{ghg}_c"]
        * resid_mix["enduse_load"]
        * (1 - resid_mix["distloss_rate_avg"])
    )

    # calculate imports and exports
    resid_mix["zero"] = 0
    resid_mix["imports"] = resid_mix["busbar_load"] - resid_mix["generation"]
    resid_mix["imports"] = resid_mix[["imports", "zero"]].max(axis=1)
    resid_mix["exports"] = resid_mix["generation"] - resid_mix["busbar_load"]
    resid_mix["exports"] = resid_mix[["exports", "zero"]].max(axis=1)

    # calculate total residual generation, assuming exported energy comes from all generation equally
    resid_mix["residual_generation"] = resid_mix[
        [
            "coal_MWh",
            "coal-ccs_MWh",
            "o-g-s_MWh",
            "gas-cc_MWh",
            "gas-cc-ccs_MWh",
            "gas-ct_MWh",
            "imports",
        ]
    ].sum(axis=1) - (
        resid_mix["exports"]
        * (
            resid_mix[
                [
                    "coal_MWh",
                    "coal-ccs_MWh",
                    "o-g-s_MWh",
                    "gas-cc_MWh",
                    "gas-cc-ccs_MWh",
                    "gas-ct_MWh",
                ]
            ].sum(axis=1)
            / resid_mix["generation"]
        )
    )

    # calculate the residual EF, adjusting for distribution losses
    resid_mix["residual_ef"] = (
        resid_mix["total_emissions"] / resid_mix["residual_generation"]
    ) / (1 - resid_mix["distloss_rate_avg"])

    resid_mix = resid_mix[["residual_ef"]]

    # convert the unit from kgCO2/MWh to the appropriate unit
    unit_conversion = {
        f"lb{ghg_unit}/MWh": 2.20462,
        f"kg{ghg_unit}/MWh": 1,
        f"mT{ghg_unit}/MWh": 0.001,
        f"ton{ghg_unit}/MWh": (2.20462 / 2000),
    }
    resid_mix = resid_mix * unit_conversion[emissions_unit]

    return resid_mix


def calculate_emissions(
    dispatch,
    generation_projects_info,
    system_power,
    load_balance,
    cambium,
    emissions_unit,
):

    # merge data about generation and generator-specific emission factors
    generator_emissions = (
        dispatch.copy()
        .drop(columns="Nodal_Price")
        .merge(
            generation_projects_info[["GENERATION_PROJECT", "gen_emission_factor"]],
            how="left",
            left_on="generation_project",
            right_on="GENERATION_PROJECT",
        )
    )
    # calculate the generator emission rate
    generator_emissions["Generator Emission Rate"] = (
        generator_emissions["DispatchGen_MW"] + generator_emissions["ExcessGen_MW"]
    ).astype(float) * (generator_emissions["gen_emission_factor"]).astype(float)
    # sum by timestamp
    generator_emissions = generator_emissions.groupby("timestamp").sum()
    # convert the index to a datetimeindex
    generator_emissions.index = pd.to_datetime(generator_emissions.index)

    # load the residual mix data from cambium
    residual_mix = calculate_residual_mix(cambium, emissions_unit)

    # copy system power info and set the index as a datetimeindex
    grid_emissions = system_power.copy()[["timestamp", "system_power_MW"]]
    grid_emissions.index = pd.to_datetime(grid_emissions.timestamp)
    grid_emissions = grid_emissions.drop(columns="timestamp")
    # merge system power and residual mix data together
    grid_emissions = grid_emissions.merge(
        residual_mix, how="left", left_index=True, right_index=True
    )
    # calculate the grid emission rate
    grid_emissions["Grid Emission Rate"] = (
        grid_emissions["system_power_MW"] * grid_emissions["residual_ef"]
    )

    # merge the generator and grid emission data together and calculate a total emission rate
    total_emissions = generator_emissions[["Generator Emission Rate"]].merge(
        grid_emissions[["residual_ef", "Grid Emission Rate"]],
        how="left",
        left_index=True,
        right_index=True,
    )
    total_emissions["Total Emission Rate"] = (
        total_emissions["Generator Emission Rate"]
        + total_emissions["Grid Emission Rate"]
    )
    # get load timeseries data and merge into total emissions data
    load = load_balance.copy()[["timestamp", "zone_demand_mw"]].set_index("timestamp")
    load.index = pd.to_datetime(load.index)
    total_emissions = total_emissions.merge(
        load, how="left", left_index=True, right_index=True
    )
    # calculate teh delivered emission factor
    total_emissions["Delivered Emission Factor"] = (
        total_emissions["Total Emission Rate"] / total_emissions["zone_demand_mw"]
    )

    return total_emissions


def calculate_levelized_lrmer(start_year, period, discount, emissions_unit, region):
    """
    Calculates a levelized LRMER from the Cambium data

    Inputs:
        start_year: the start year for the levelization (should be the model year)
        period: the number of years of expected project lifetime
        discount: the social discount rate as a percent fraction for discounting emission damages in future years
        emissions_unit: the desired unit for the emissions factor
    Returns:
        levelized_lrmers: a dataframe containing levelized LRMER timeseries for each scenario
    """

    if "CO2e" in emissions_unit:
        ghg = "co2e"
        ghg_unit = "CO2e"
    else:
        ghg = "co2"
        ghg_unit = "CO2"

    # load data

    scenarios = [
        "LowRECost",
        "MidCase",
        "MidCase95by2035",
        "MidCase95by2050",
        "HighRECost",
    ]

    # create an empty df to hold all of the levelized lrmers
    levelized_lrmers = pd.DataFrame()

    # for each scenario, load all years and calculate a levelized value
    for scenario in scenarios:

        # create a blank dataframe to hold the lrmers for each year
        lrmer_scenario = pd.DataFrame()

        # start a variable to track the discounted number of years for the levelization
        denominator = 0

        for year in range(start_year, start_year + period + 1):

            # load the data and only keep the lrmer value
            lrmer = load_cambium_data(scenario, year, region)[
                [f"lrmer_{ghg}_c", "distloss_rate_marg"]
            ]

            # convert to busbar values
            lrmer[f"lrmer_{ghg}_c"] = lrmer[f"lrmer_{ghg}_c"] * (
                1 - lrmer["distloss_rate_marg"]
            )

            # calculate the weighting factor for the year
            weight = 1 / ((1 + discount) ** (year - start_year))
            denominator += weight

            # discount the data
            lrmer[f"lrmer_{ghg}_c"] = lrmer[f"lrmer_{ghg}_c"] * weight

            # reset the index
            lrmer = lrmer.reset_index()

            # add the data to the containing df
            lrmer_scenario[year] = lrmer[f"lrmer_{ghg}_c"]

        # calculate the levelized lrmer for the scenario
        levelized_lrmers[scenario] = lrmer_scenario.sum(axis=1) / denominator

    # convert the unit from kgCO2/MWh to the appropriate unit
    unit_conversion = {
        f"lb{ghg_unit}/MWh": 2.20462,
        f"kg{ghg_unit}/MWh": 1,
        f"mT{ghg_unit}/MWh": 0.001,
        f"ton{ghg_unit}/MWh": (2.20462 / 2000),
    }
    levelized_lrmers = levelized_lrmers * unit_conversion[emissions_unit]

    # create a datetime index, skipping leap days
    dates = pd.date_range(
        start=f"01/01/{start_year} 00:00",
        end=f"12/31/{start_year} 23:00",
        freq="H",
        name="timestamp_local",
    )
    levelized_lrmers.index = pd.DatetimeIndex(
        data=(t for t in dates if ((t.month != 2) | (t.day != 29)))
    )

    return levelized_lrmers


def load_srmer_data(model_year, emissions_unit, region):
    """
    Loads short run marginal emission data from Cambium
    """

    if "CO2e" in emissions_unit:
        ghg = "co2e"
        ghg_unit = "CO2e"
    else:
        ghg = "co2"
        ghg_unit = "CO2"

    # load data

    scenarios = [
        "LowRECost",
        "MidCase",
        "MidCase95by2035",
        "MidCase95by2050",
        "HighRECost",
    ]

    srmer_data = pd.DataFrame()

    for scenario in scenarios:
        # load the data
        temp = load_cambium_data(scenario=scenario, year=model_year, region=region)[
            [f"srmer_{ghg}_c", "distloss_rate_marg"]
        ]
        # convert to busbar values
        temp[f"srmer_{ghg}_c"] = temp[f"srmer_{ghg}_c"] * (
            1 - temp["distloss_rate_marg"]
        )

        srmer_data[scenario] = temp[[f"srmer_{ghg}_c"]]

    # convert the unit from kgCO2/MWh to the appropriate unit
    unit_conversion = {
        f"lb{ghg_unit}/MWh": 2.20462,
        f"kg{ghg_unit}/MWh": 1,
        f"mT{ghg_unit}/MWh": 0.001,
        f"ton{ghg_unit}/MWh": (2.20462 / 2000),
    }
    srmer_data = srmer_data * unit_conversion[emissions_unit]

    # create a datetime index, skipping leap days
    dates = pd.date_range(
        start=f"01/01/{model_year} 00:00",
        end=f"12/31/{model_year} 23:00",
        freq="H",
        name="timestamp_local",
    )
    srmer_data.index = pd.DatetimeIndex(
        data=(t for t in dates if ((t.month != 2) | (t.day != 29)))
    )

    return srmer_data


def determine_additional_dispatch(
    generation_projects_info, dispatch, storage_dispatch, storage_exists
):
    """
    Calculates the dispatch that was additional, using a load sign convention (generation is negative, demand is positive)
    """

    generation_projects_info = generation_projects_info.rename(
        columns={"GENERATION_PROJECT": "generation_project"}
    )

    # get a list of all of the additional gens
    additional_gens = list(
        generation_projects_info.loc[
            generation_projects_info["gen_is_additional"] == 1, "generation_project"
        ]
    )

    if len(additional_gens) > 0:

        # calculate dispatch from additional generators for long run marginal
        # filter the dispatch data to the additional gens
        addl_dispatch = dispatch.copy().drop(columns="Nodal_Price")[
            dispatch["generation_project"].isin(additional_gens)
        ]

        # add information about the generator cabmium region
        addl_dispatch = addl_dispatch.merge(
            generation_projects_info[["generation_project", "gen_cambium_region"]],
            how="left",
            on="generation_project",
        )

        # groupby timestamp and region
        addl_dispatch = (
            addl_dispatch.groupby(["gen_cambium_region", "timestamp"])
            .sum()
            .reset_index()
        )

        # calculate total generation in each timestamp
        addl_dispatch["Generator_Dispatch"] = -1 * (
            addl_dispatch["DispatchGen_MW"] + addl_dispatch["ExcessGen_MW"]
        )

        # pivot the data
        addl_dispatch = addl_dispatch.pivot(
            index="timestamp", columns="gen_cambium_region", values="Generator_Dispatch"
        )

        # convert the index to a datetime
        addl_dispatch.index = pd.to_datetime(addl_dispatch.index)

        ### STORAGE ###
        if storage_exists:
            # calculate dispatch from additional storage for short-run marginal
            addl_storage_dispatch = storage_dispatch.copy()[
                storage_dispatch["generation_project"].isin(additional_gens)
            ]

            # add information about the generator cabmium region
            addl_storage_dispatch = addl_storage_dispatch.merge(
                generation_projects_info[["generation_project", "gen_cambium_region"]],
                how="left",
                on="generation_project",
            )

            # groupby timestamp and region
            addl_storage_dispatch = (
                addl_storage_dispatch.groupby(["gen_cambium_region", "timestamp"])
                .sum()
                .reset_index()
            )

            # calculate total generation in each timestamp
            addl_storage_dispatch["Storage_Dispatch"] = (
                addl_storage_dispatch["ChargeMW"] - addl_storage_dispatch["DischargeMW"]
            )

            # pivot the data
            addl_storage_dispatch = addl_storage_dispatch.pivot(
                index="timestamp",
                columns="gen_cambium_region",
                values="Storage_Dispatch",
            )

            addl_storage_dispatch.index = pd.to_datetime(addl_storage_dispatch.index)

            return addl_dispatch, addl_storage_dispatch

        else:

            addl_storage_dispatch = pd.DataFrame()

            return addl_dispatch, addl_storage_dispatch

    else:
        addl_dispatch = pd.DataFrame()
        addl_storage_dispatch = pd.DataFrame()

        return addl_dispatch, addl_storage_dispatch


def determine_additional_variable_dispatch(
    generation_projects_info, portfolio, dispatch, storage_dispatch, storage_exists
):
    """
    Calculates the dispatch that was additional, using a load sign convention (generation is negative, demand is positive)
    """

    generation_projects_info = generation_projects_info.rename(
        columns={"GENERATION_PROJECT": "generation_project"}
    )

    # get a list of all of the additional gens
    additional_gens = list(
        generation_projects_info.loc[
            generation_projects_info["gen_is_additional"] == 1, "generation_project"
        ]
    )

    if len(additional_gens) > 0:

        # calculate dispatch from additional generators for long run marginal
        # filter the dispatch data to the additional gens
        addl_dispatch = dispatch.copy()[
            dispatch["generation_project"].isin(additional_gens)
        ]

        addl_dispatch = addl_dispatch.merge(
            portfolio[["generation_project", "Technology"]],
            how="left",
            on="generation_project",
        )

        # add a column for variable resources
        addl_dispatch["Type"] = "Nonvariable_Dispatch"
        addl_dispatch.loc[
            (addl_dispatch["Technology"].str.contains("Wind"))
            | (addl_dispatch["Technology"].str.contains("Solar")),
            "Type",
        ] = "Variable_Dispatch"

        # groupby timestamp and type (variable and nonvariable resources)
        addl_dispatch = addl_dispatch.groupby(["Type", "timestamp"]).sum().reset_index()

        # calculate total generation in each timestamp
        addl_dispatch["Generator_Dispatch"] = -1 * (
            addl_dispatch["DispatchGen_MW"] + addl_dispatch["ExcessGen_MW"]
        )

        # pivot the data
        addl_dispatch = addl_dispatch.pivot(
            index="timestamp", columns="Type", values="Generator_Dispatch"
        )
        if "Variable_Dispatch" not in list(addl_dispatch.columns):
            addl_dispatch["Variable_Dispatch"] = 0

        # calculate a total column and drop the nonvariable data
        addl_dispatch["Total_Dispatch"] = addl_dispatch.sum(axis=1)
        addl_dispatch = addl_dispatch[["Variable_Dispatch", "Total_Dispatch"]]

        # convert the index to a datetime
        addl_dispatch.index = pd.to_datetime(addl_dispatch.index)

        ### STORAGE ###
        if storage_exists:
            # calculate dispatch from additional storage for short-run marginal
            addl_storage_dispatch = storage_dispatch.copy()[
                storage_dispatch["generation_project"].isin(additional_gens)
            ]

            # groupby timestamp
            addl_storage_dispatch = addl_storage_dispatch.groupby("timestamp").sum()

            # calculate total generation in each timestamp
            addl_storage_dispatch["Storage_Dispatch"] = (
                addl_storage_dispatch["ChargeMW"] - addl_storage_dispatch["DischargeMW"]
            )

            addl_storage_dispatch = addl_storage_dispatch[["Storage_Dispatch"]]
            addl_storage_dispatch.index = pd.to_datetime(addl_storage_dispatch.index)

            return addl_dispatch, addl_storage_dispatch

        else:

            addl_storage_dispatch = pd.DataFrame()

            return addl_dispatch, addl_storage_dispatch

    else:
        addl_dispatch = pd.DataFrame()
        addl_storage_dispatch = pd.DataFrame()

        return addl_dispatch, addl_storage_dispatch


def calculate_system_ramp(net_load, ramp_length):

    ramp = net_load.shift(-ramp_length, fill_value=0) - net_load
    ramp.index = pd.to_datetime(ramp.index)
    max_ramp = ramp.groupby([ramp.index.date]).max()
    max_ramp.index = pd.to_datetime(max_ramp.index)
    max_ramp = max_ramp.groupby(max_ramp.index.month).mean()

    # find the hour of each day when net load peaks
    max_ramp_hour = ramp.groupby([ramp.index.date]).idxmax()
    max_ramp_hour["net_load_busbar"] = max_ramp_hour["net_load_busbar"].dt.hour

    # find the average hour during which net load peaks in each quarter
    max_ramp_hour.index = pd.to_datetime(max_ramp_hour.index)
    max_ramp_hour = max_ramp_hour.groupby(max_ramp_hour.index.month).mean()
    max_ramp_hour["max_ramp_hour"] = max_ramp_hour["net_load_busbar"].apply(
        lambda row: f"{int(row)}:{int((row*60)%60):02d}"
    )

    # combine the data together
    ramp = max_ramp.rename(columns={"net_load_busbar": f"max_{ramp_length}_hr_ramp_MW"})
    ramp["ramp_start_hour"] = max_ramp_hour["max_ramp_hour"]

    return ramp


def compare_system_ramps(cambium, addl_dispatch, addl_storage_dispatch, ramp_length):
    """ """
    pre_net_load = cambium.copy()[["net_load_busbar"]]
    pre_net_load_storage = cambium.copy()[
        ["net_load_busbar", "storage_charging", "phs_MWh", "battery_MWh"]
    ]
    pre_net_load_storage["net_load_busbar"] = (
        pre_net_load_storage["net_load_busbar"]
        + pre_net_load_storage["storage_charging"]
        - pre_net_load_storage["phs_MWh"]
        - pre_net_load_storage["battery_MWh"]
    )
    post_net_load = pre_net_load.copy()

    # change the index of the dispatch data to match the net load data
    addl_dispatch.index = post_net_load.index
    addl_storage_dispatch.index = post_net_load.index

    post_net_load = post_net_load.merge(
        addl_dispatch[["Variable_Dispatch"]],
        how="left",
        left_index=True,
        right_index=True,
    )
    post_net_load_storage = post_net_load.merge(
        addl_storage_dispatch[["Storage_Dispatch"]],
        how="left",
        left_index=True,
        right_index=True,
    )

    # calculate the new net load value and drop the variable dispatch data
    post_net_load["net_load_busbar"] = (
        post_net_load["net_load_busbar"] + post_net_load["Variable_Dispatch"]
    )
    post_net_load = post_net_load.drop(columns="Variable_Dispatch")

    # calculate the new net load value and drop the variable dispatch data
    post_net_load_storage["net_load_busbar"] = (
        post_net_load_storage["net_load_busbar"]
        + post_net_load_storage["Variable_Dispatch"]
        + post_net_load_storage["Storage_Dispatch"]
    )
    post_net_load_storage = post_net_load_storage.drop(
        columns=["Variable_Dispatch", "Storage_Dispatch"]
    )

    pre_ramp = calculate_system_ramp(pre_net_load, ramp_length)
    post_ramp = calculate_system_ramp(post_net_load, ramp_length)
    post_ramp_storage = calculate_system_ramp(post_net_load_storage, ramp_length)

    delta_ramp = pre_ramp.copy()
    delta_ramp["portfolio_impact_no_storage"] = (
        post_ramp["max_3_hr_ramp_MW"] - pre_ramp["max_3_hr_ramp_MW"]
    )
    delta_ramp["portfolio_impact_with_storage"] = (
        post_ramp_storage["max_3_hr_ramp_MW"] - pre_ramp["max_3_hr_ramp_MW"]
    )
    delta_ramp.index = delta_ramp.index.rename("Month")
    delta_ramp = pd.concat(
        [
            delta_ramp,
            pd.DataFrame(
                delta_ramp[
                    [
                        "max_3_hr_ramp_MW",
                        "portfolio_impact_no_storage",
                        "portfolio_impact_with_storage",
                    ]
                ]
                .mean(axis=0)
                .rename("Average")
            ).T,
        ]
    )

    return delta_ramp


def calculate_system_peak(net_load):

    # find the maximum net load on each day
    peak_demand = net_load.groupby(net_load.index.date).max()

    # find the average daily peak load in each quarter
    peak_demand.index = pd.to_datetime(peak_demand.index)
    peak_demand = peak_demand.groupby(peak_demand.index.month).mean()

    # find the hour of each day when net load peaks
    peak_hour = net_load.groupby(net_load.index.date).idxmax()
    peak_hour["net_load_busbar"] = peak_hour["net_load_busbar"].dt.hour

    # find the average hour during which net load peaks in each quarter
    peak_hour.index = pd.to_datetime(peak_hour.index)
    peak_hour = peak_hour.groupby(peak_hour.index.month).mean()
    peak_hour["peak_hour"] = peak_hour["net_load_busbar"].apply(
        lambda row: f"{int(row)}:{int((row*60)%60):02d}"
    )

    # combine the data together
    peak = peak_demand.rename(columns={"net_load_busbar": "net_load_peak_MW"})
    peak["peak_hour"] = peak_hour["peak_hour"]

    return peak


def compare_system_peaks(cambium, addl_dispatch, addl_storage_dispatch):
    """ """
    pre_net_load = cambium.copy()[["net_load_busbar"]]
    # net out storage
    pre_net_load_storage = cambium.copy()[
        ["net_load_busbar", "storage_charging", "phs_MWh", "battery_MWh"]
    ]
    pre_net_load_storage["net_load_busbar"] = (
        pre_net_load_storage["net_load_busbar"]
        + pre_net_load_storage["storage_charging"]
        - pre_net_load_storage["phs_MWh"]
        - pre_net_load_storage["battery_MWh"]
    )
    post_net_load = pre_net_load.copy()

    # change the index of the dispatch data to match the net load data
    addl_dispatch.index = post_net_load.index
    addl_storage_dispatch.index = post_net_load.index

    post_net_load = post_net_load.merge(
        addl_dispatch[["Variable_Dispatch"]],
        how="left",
        left_index=True,
        right_index=True,
    )
    post_net_load_storage = post_net_load.merge(
        addl_storage_dispatch[["Storage_Dispatch"]],
        how="left",
        left_index=True,
        right_index=True,
    )

    # calculate the new net load value and drop the variable dispatch data
    post_net_load["net_load_busbar"] = (
        post_net_load["net_load_busbar"] + post_net_load["Variable_Dispatch"]
    )
    post_net_load = post_net_load.drop(columns="Variable_Dispatch")

    # calculate the new net load value and drop the variable dispatch data
    post_net_load_storage["net_load_busbar"] = (
        post_net_load_storage["net_load_busbar"]
        + post_net_load_storage["Variable_Dispatch"]
        + post_net_load_storage["Storage_Dispatch"]
    )
    post_net_load_storage = post_net_load_storage.drop(
        columns=["Variable_Dispatch", "Storage_Dispatch"]
    )

    pre_peak = calculate_system_peak(pre_net_load)
    post_peak = calculate_system_peak(post_net_load)
    post_peak_storage = calculate_system_peak(post_net_load_storage)

    delta_peak = pre_peak.copy()
    delta_peak["portfolio_impact_no_storage"] = (
        post_peak["net_load_peak_MW"] - pre_peak["net_load_peak_MW"]
    )
    delta_peak["portfolio_impact_with_storage"] = (
        post_peak_storage["net_load_peak_MW"] - pre_peak["net_load_peak_MW"]
    )
    delta_peak.index = delta_peak.index.rename("Month")
    delta_peak = pd.concat(
        [
            delta_peak,
            pd.DataFrame(
                delta_peak[
                    [
                        "net_load_peak_MW",
                        "portfolio_impact_no_storage",
                        "portfolio_impact_with_storage",
                    ]
                ]
                .mean(axis=0)
                .rename("Average")
            ).T,
        ]
    )

    return delta_peak
