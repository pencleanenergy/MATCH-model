# Copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px

"""
This module contains a collection of functions that are called from the summary_report.ipynb, used for reporting final outputs
"""

def format_currency(x):
    """
    Formats a number as currency in the format '$ 0.00'
    """ 
    try:
        formatted = '$ {:,.2f}'.format(x)
    except ValueError:
        formatted = x
    return formatted

def format_percent(x): 
    """
    Formats a number as percentage in the format '99.99%'

    The input number must be a percentage on a 0-100 scale
    """ 
    try:
        formatted = '{:,.2f}%'.format(x)
    except ValueError:
        formatted = x
    return formatted

def hybrid_pair_dict(generation_projects_info):
    """
    Creates a dictionary matching the name of the storage portion of a hybrid project to the generator portion
    """
    hybrid_pair = generation_projects_info[['GENERATION_PROJECT','storage_hybrid_generation_project']]
    hybrid_pair = hybrid_pair[hybrid_pair['storage_hybrid_generation_project'] != "."]
    hybrid_pair = dict(zip(hybrid_pair.GENERATION_PROJECT, hybrid_pair.storage_hybrid_generation_project))
    return hybrid_pair

def annual_renewable_percentage(load_balance):
    """
    Calculates the percent of delivered energy from renewable sources, using an annual volumetric method

    The renewable percentage is net generation / load, where net generation is total generation less storage losses
    
    NOTE: this will need to be modified to calculate net load if DSR is used
    """

    if 'ZoneTotalStorageCharge' in load_balance.columns:
        storage_losses = load_balance.ZoneTotalStorageCharge.sum() - load_balance.ZoneTotalStorageDischarge.sum()
    else:
        storage_losses = 0
    net_generation = load_balance.ZoneTotalGeneratorDispatch.sum() + load_balance.ZoneTotalExcessGen.sum() - storage_losses
    load = load_balance.zone_demand_mw.sum()

    percent = net_generation / load * 100

    return percent

def hourly_renewable_percentage(load_balance):
    """
    Calculates the percent of delivered energy from renewable sources, using a time-coincident hourly method

    Because system power must be used to fill in any gaps that dispatch and storage discharge cannot provide,
    we can calculate the time-coincident renewable percentage as the inverse of the system power percentage

    NOTE: this will need to be modified to calculate net load if DSR is used
    """

    system_power = load_balance.SystemPower.sum()
    load = load_balance.zone_demand_mw.sum()

    percent = (1 - (system_power / load)) * 100

    return percent


def generator_portfolio(gen_cap, gen_build_predetermined):
    """
    Calculates the generator portfolio mix to be used as an input for a suburst chart
    """
    # only keep generators that were built
    gen_cap = gen_cap[gen_cap['GenCapacity'] > 0]

    # only keep certain columns
    gen_cap = gen_cap[['generation_project','gen_tech','GenCapacity']]

    # rename the GenCapacity column to MW
    gen_cap = gen_cap.rename(columns={'GenCapacity':'MW'})

    # change the column name to lower case to match the column in gen_cap
    gen_build_predetermined = gen_build_predetermined.rename(columns={'GENERATION_PROJECT':'generation_project'})

    # add column indicating which generators are contracted or additional builds
    gen_build_predetermined['Status'] = 'Contracted'
    gen_cap = gen_cap.merge(gen_build_predetermined, how='left', on='generation_project').fillna('Additional')

    # if there are any hybrid projects, add hybrid to the gen tech
    gen_cap.loc[gen_cap.generation_project.str.contains('HYBRID'), 'gen_tech'] = 'Hybrid ' + gen_cap.loc[gen_cap.generation_project.str.contains('HYBRID'), 'gen_tech'].astype(str)

    # replace underscores in the gen tech name with spaces
    gen_cap.gen_tech = gen_cap.gen_tech.str.replace('_',' ')

    # change the name of the column from gen_tech to Technology
    gen_cap = gen_cap.rename(columns={'gen_tech':'Technology'})

    # round all of the values to a single decimal point
    gen_cap['MW'] = gen_cap['MW'].round(1)

    # sort the values
    gen_cap = gen_cap.sort_values(by=['Status','Technology'])

    # extract the name of the generator
    gen_cap['generation_project'] = [' '.join(i.split('_')[1:]) for i in gen_cap['generation_project']]

    return gen_cap

def generator_costs(costs_by_gen, storage_dispatch, hybrid_pair, gen_cap):
    """
    Calculates the cost components for each generator
    """
    gen_costs = costs_by_gen.copy()

    # drop rows where generation is 0
    gen_costs = gen_costs[gen_costs.Generation_MW > 0]

    gen_costs = gen_costs.groupby('generation_project').sum().reset_index()

    # rename columns

    storage_costs = storage_dispatch.copy().drop(columns=['StateOfCharge'])
    storage_costs = storage_costs.groupby('generation_project').sum().reset_index()

    # add storage contract costs
    storage_costs = storage_costs.merge(gen_cap[['generation_project','PPA_Capacity_Cost']], how='left', on='generation_project').fillna(0)

    # replace hybrid storage names with the name of the paired generator
    storage_costs['generation_project'] = storage_costs['generation_project'].replace(hybrid_pair)

    # drop rows where generation is 0
    storage_costs = storage_costs[storage_costs.DischargeMW > 0]

    # merge the two dfs together
    gen_costs = gen_costs.merge(storage_costs, how='outer', on='generation_project').fillna(0)

    # combine Delivery Cost columns
    gen_costs['Delivery_Cost'] = gen_costs['Delivery_Cost'] + gen_costs['StorageDispatchDeliveryCost']

    # combine Generation and Discharge columns
    gen_costs['Generation_MW'] = gen_costs['Generation_MW'] + gen_costs['DischargeMW']
    # for hybrid generators, subtract out the charging MW
    gen_costs.loc[gen_costs['generation_project'].str.contains('HYBRID'), 'Generation_MW'] = gen_costs.loc[gen_costs['generation_project'].str.contains('HYBRID'), 'Generation_MW'] - gen_costs['ChargeMW']

    # rename columns
    gen_costs = gen_costs.rename(columns={'Contract_Cost':'Energy Contract Cost',
                                          'PPA_Capacity_Cost':'Capacity Contract Cost',
                                          'Pnode_Revenue':'Pnode Revenue',
                                          'StorageDispatchPnodeCost':'Storage Arbitrage Revenue',
                                          'Delivery_Cost':'Delivery Cost',
                                          'Generation_MW':'Generation MWh'})

    # calculate per MWh costs
    gen_costs['Energy Contract Cost'] = gen_costs['Energy Contract Cost'] / gen_costs['Generation MWh']
    gen_costs['Capacity Contract Cost'] = gen_costs['Capacity Contract Cost'] / gen_costs['Generation MWh']
    gen_costs['Pnode Revenue'] = gen_costs['Pnode Revenue'] / gen_costs['Generation MWh']
    gen_costs['Delivery Cost'] = gen_costs['Delivery Cost'] / gen_costs['Generation MWh']
    gen_costs['Storage Arbitrage Revenue'] = gen_costs['Storage Arbitrage Revenue'] / gen_costs['Generation MWh']
    gen_costs['Total Cost'] = gen_costs['Energy Contract Cost'] + gen_costs['Capacity Contract Cost'] + gen_costs['Pnode Revenue'] + gen_costs['Delivery Cost'] + gen_costs['Storage Arbitrage Revenue']

    gen_costs = gen_costs.sort_values(by='Total Cost', ascending=True)

    gen_costs = gen_costs.round(decimals=2)

    # only keep relevant columns
    gen_costs = gen_costs[['generation_project', 'Energy Contract Cost', 'Capacity Contract Cost', 'Pnode Revenue', 'Delivery Cost','Storage Arbitrage Revenue','Total Cost']]

    return gen_costs


def power_content_label(load_balance, dispatch, generation_projects_info):
    """
    Calculates the mix of delivered energy.
    First, calculate the percentage of energy from system power
    Then, assign the remaineder the mix of dispatchgen
    """

    # calculate the percent of energy from grid power
    percent_from_grid = load_balance.SystemPower.sum() / load_balance.zone_demand_mw.sum()
    
    # get the list of technologies
    generator_technology_dict = generation_projects_info[['GENERATION_PROJECT','gen_tech']]
    generator_technology_dict = dict(zip(generator_technology_dict.GENERATION_PROJECT, generator_technology_dict.gen_tech))

    # add a generator technology column to the dispatch data
    dispatch['gen_tech'] = dispatch['generation_project'].map(generator_technology_dict)

    # calculate the mix of dispatched energy
    dispatch_mix = dispatch.groupby('gen_tech').sum().reset_index()[['gen_tech','DispatchGen_MW']]

    # discount by the inverse of the system power percentage
    dispatch_mix['DispatchGen_MW'] = dispatch_mix['DispatchGen_MW'] * (1 - percent_from_grid)

    dispatch_mix = dispatch_mix.append({'gen_tech':'Grid Energy','DispatchGen_MW': load_balance.SystemPower.sum()}, ignore_index=True)

    dispatch_mix = dispatch_mix.rename(columns={'gen_tech':'Source','DispatchGen_MW':'MWh'})

    # replace underscores in the gen tech name with spaces
    dispatch_mix.Source = dispatch_mix.Source.str.replace('_',' ')

    # round to no decimal places
    dispatch_mix = dispatch_mix.round(0)

    # drop any rows with zero generation
    dispatch_mix = dispatch_mix[dispatch_mix['MWh'] > 0]

    return dispatch_mix

def hourly_cost_of_power(system_power, costs_by_tp, RA_summary, gen_cap, storage_dispatch, fixed_costs, rec_value, load_balance):
    """
    Calculates the cost of power for each hour of the year

    Hourly costs include: energy contract costs, nodal costs/revenues, hedge costs, DLAP cost
    Annual costs include: capacity contract costs, RA costs, fixed costs
    Sellable costs include: excess RA, RECs

    We will need to calculate costs for dispatched energy, and for all generated energy
    """

    # start with system power hedge cost and build from there 
    hourly_costs = system_power.copy().drop(columns=['load_zone','system_power_MW'])

    # if the hedge cost was set as the default value, remove the hedge cost
    if hourly_costs['hedge_cost_per_MWh'].mean() == 0.0000001:
        hourly_costs['hedge_cost'] = 0

    hourly_costs = hourly_costs.drop(columns=['hedge_cost_per_MWh'])

    # add generator timepoint costs next
    hourly_costs = hourly_costs.merge(costs_by_tp, how='left', on='timestamp')

    # set the excess RA value as a negative cost
    RA_summary['Excess_RA_Value'] = - RA_summary['Excess_RA_Value']

    # calculate annual ra costs
    RA_summary = RA_summary[['RA_Open_Position_Cost','Excess_RA_Value']].sum()

    # divide these costs by the number of timepoints
    RA_summary = RA_summary / len(hourly_costs.index)

    # add the RA costs to the hourly costs
    hourly_costs['ra_open_position_cost'] = RA_summary['RA_Open_Position_Cost']
    hourly_costs['excess_ra_value'] = RA_summary['Excess_RA_Value']

    # calculate annual capacity costs
    gen_cap = gen_cap[['PPA_Capacity_Cost']].sum()

    # divide these costs by the number of timepoints
    gen_cap = gen_cap / len(hourly_costs.index)

    # add the capacity costs to the hourly costs
    hourly_costs['Capacity Contract Cost'] = gen_cap['PPA_Capacity_Cost']

    # add storage nodal costs
    storage_cost = storage_dispatch[['timestamp','StorageDispatchPnodeCost']]
    # sum for each timestamp
    storage_cost = storage_cost.groupby('timestamp').sum()
    # merge the data
    hourly_costs = hourly_costs.merge(storage_cost, how='left', on='timestamp')

    # calculate the hourly value for annual fixed costs
    fixed_cost_component = fixed_costs.copy()
    fixed_cost_component['annual_cost'] = fixed_cost_component['annual_cost'] / len(hourly_costs.index)

    # create new columns in the hourly cost for each of these fixed costs
    for val in fixed_cost_component['cost_name']:
        hourly_costs[val] = fixed_cost_component.loc[fixed_cost_component['cost_name'] == val, 'annual_cost'].item()

    # calculate value of excess recs
    excess_generation = load_balance.copy()[['timestamp', 'ZoneTotalExcessGen']]
    excess_generation['Excess REC Value'] = excess_generation['ZoneTotalExcessGen'] * -rec_value

    # merge the REC sale value
    hourly_costs = hourly_costs.merge(excess_generation[['timestamp', 'Excess REC Value']], how='left', on='timestamp')

    # parse dates
    hourly_costs = hourly_costs.set_index(pd.to_datetime(hourly_costs['timestamp'])).drop(columns=['timestamp'])

    # rename columns
    hourly_costs = hourly_costs.rename(columns={'DLAP Cost':'DLAP Load Cost',
                                                'hedge_cost': 'Hedge Contract Cost',
                                                'Capacity Contract Cost':'Storage Capacity PPA Cost',
                                                'ra_open_position_cost':'RA Open Position Cost',
                                                'StorageDispatchPnodeCost':'Storage Wholesale Price Arbitrage',
                                                'excess_ra_value':'Excess RA Value'})

    return hourly_costs

def build_hourly_cost_plot(hourly_costs, load):
    """
    """
    costs = hourly_costs.copy()

    # drop columns that include resale values
    costs = costs.drop(columns=['Excess RA Value', 'Excess REC Value'])

    # specify the names and order of cost columns
    cost_columns = costs.columns

    # calculate the cost per MWh
    for col in cost_columns:
        costs[col] = costs[col] / load['zone_demand_mw']

    # add a column for total cost
    costs['Total Cost'] = costs.sum(axis=1)

    # average by season-hour
    costs = costs.groupby([costs.index.quarter, costs.index.hour]).mean()
    costs.index = costs.index.set_names(['quarter','hour'])
    costs = costs.reset_index().rename(columns={0:'cost'})

    # build the cost plot
    hourly_cost_plot = px.bar(costs, x='hour',y=cost_columns,facet_col='quarter').update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor='black')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 1, 'hour'], y=costs.loc[costs['quarter'] == 1, 'Total Cost'], row=1, col=1, line=dict(color='black', width=4), name='Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 2, 'hour'], y=costs.loc[costs['quarter'] == 2, 'Total Cost'], row=1, col=2, line=dict(color='black', width=4), name='Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 3, 'hour'], y=costs.loc[costs['quarter'] == 3, 'Total Cost'], row=1, col=3, line=dict(color='black', width=4), name='Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 4, 'hour'], y=costs.loc[costs['quarter'] == 4, 'Total Cost'], row=1, col=4, line=dict(color='black', width=4), name='Total')

    return hourly_cost_plot