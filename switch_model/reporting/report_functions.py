# Copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px
import math
import os

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

def build_hourly_emissions_heatmap(grid_emissions, emissions, emissions_unit):
    """
    """
    # get the maximum grid emissions factor
    grid_max_ef = grid_emissions['grid_emission_factor'].max()

    # rearrange data in a grid
    emissions_heatmap_data = emissions.copy()[['timestamp','Delivered Emission Factor']]
    emissions_heatmap_data.index = pd.to_datetime(emissions_heatmap_data['timestamp']) 
    emissions_heatmap_data['Date'] = emissions_heatmap_data.index.date
    emissions_heatmap_data['Hour of Day'] = emissions_heatmap_data.index.hour
    emissions_heatmap_data = emissions_heatmap_data.pivot(index='Hour of Day', columns='Date', values='Delivered Emission Factor')
    emissions_heatmap_data = emissions_heatmap_data.round(4)

    emissions_heatmap = px.imshow(emissions_heatmap_data, 
            x=emissions_heatmap_data.columns, 
            y=emissions_heatmap_data.index, 
            color_continuous_scale='rdylgn_r', 
            range_color=[0,grid_max_ef], 
            title=f'Hourly Emisission Intensity of Delivered Energy ({emissions_unit})').update_yaxes(dtick=3)
    
    return emissions_heatmap



def generator_portfolio(gen_cap, gen_build_predetermined):
    """
    Calculates the generator portfolio mix to be used as an input for a suburst chart
    """
    # only keep generators that were built
    capacity = gen_cap.copy()
    capacity = capacity[capacity['GenCapacity'] > 0]

    # only keep certain columns
    capacity = capacity[['generation_project','gen_tech','GenCapacity']]

    # rename the GenCapacity column to MW
    capacity = capacity.rename(columns={'GenCapacity':'MW'})

    # change the column name to lower case to match the column in capacity
    predetermined = gen_build_predetermined.copy()[['GENERATION_PROJECT']].rename(columns={'GENERATION_PROJECT':'generation_project'})

    # add column indicating which generators are contracted or additional builds
    predetermined['Status'] = 'Contracted'
    capacity = capacity.merge(predetermined, how='left', on='generation_project').fillna('Additional')

    # check if any of the contracted projects had additional capacity added and split out as separate projects
    for gen in list(capacity.loc[capacity['Status'] == 'Contracted','generation_project']):
        built_mw = capacity.loc[capacity['generation_project'] == gen,'MW'].item()
        predetermined_mw = gen_build_predetermined.loc[gen_build_predetermined['GENERATION_PROJECT'] == gen,'gen_predetermined_cap'].item()
        if built_mw > predetermined_mw:
            # set the contracted quantity equal to the predetermined value
            capacity.loc[capacity['generation_project'] == gen,'MW'] = predetermined_mw
            # create a new row for the additional quantity
            capacity = capacity.append({'generation_project':gen,	'gen_tech':capacity.loc[capacity['generation_project'] == gen,'gen_tech'].item(), 'MW':(built_mw - predetermined_mw),'Status':'Additional'}, ignore_index=True)
        else:
            pass

    # if there are any hybrid projects, add hybrid to the gen tech
    capacity.loc[capacity.generation_project.str.contains('HYBRID'), 'gen_tech'] = 'Hybrid ' + capacity.loc[capacity.generation_project.str.contains('HYBRID'), 'gen_tech'].astype(str)

    # replace underscores in the gen tech name with spaces
    capacity.gen_tech = capacity.gen_tech.str.replace('_',' ')

    # change the name of the column from gen_tech to Technology
    capacity = capacity.rename(columns={'gen_tech':'Technology'})

    # round all of the values to a single decimal point
    capacity['MW'] = capacity['MW'].round(1)

    # sort the values
    capacity = capacity.sort_values(by=['Status','Technology'])

    # extract the name of the generator
    #capacity['generation_project'] = [' '.join(i.split('_')[1:]) for i in capacity['generation_project']]

    return capacity

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

    # calculate the amount of load served by portfolio generation (less storage losses)
    load_from_dispatch = load_balance.zone_demand_mw.sum() - load_balance.SystemPower.sum()
    
    # get the list of technologies
    generator_technology_dict = generation_projects_info[['GENERATION_PROJECT','gen_tech']]
    generator_technology_dict = dict(zip(generator_technology_dict.GENERATION_PROJECT, generator_technology_dict.gen_tech))

    # add a generator technology column to the dispatch data
    dispatch['gen_tech'] = dispatch['generation_project'].map(generator_technology_dict)

    # calculate the mix of dispatched energy
    dispatch_mix = dispatch.groupby('gen_tech').sum().reset_index()[['gen_tech','DispatchGen_MW']]

    # calculate scaling factor for dispatched generation
    generation_scaling_factor = load_from_dispatch / dispatch_mix.DispatchGen_MW.sum()
    
    # discount generation by this scaling factor
    dispatch_mix['DispatchGen_MW'] = dispatch_mix['DispatchGen_MW'] * generation_scaling_factor

    dispatch_mix = dispatch_mix.append({'gen_tech':'Grid Energy','DispatchGen_MW': load_balance.SystemPower.sum()}, ignore_index=True)

    dispatch_mix = dispatch_mix.rename(columns={'gen_tech':'Source','DispatchGen_MW':'MWh'})

    # replace underscores in the gen tech name with spaces
    dispatch_mix.Source = dispatch_mix.Source.str.replace('_',' ')

    # round to no decimal places
    dispatch_mix = dispatch_mix.round(0)

    # drop any rows with zero generation
    dispatch_mix = dispatch_mix[dispatch_mix['MWh'] > 0]

    return dispatch_mix

def hourly_cost_of_power(system_power, costs_by_tp, ra_open, gen_cap, storage_dispatch, fixed_costs, rec_value, load_balance):
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
    if hourly_costs['hedge_contract_cost_per_MWh'].mean() == 0.0000001:
        hourly_costs['hedge_contract_cost'] = 0

    hourly_costs = hourly_costs.drop(columns=['hedge_contract_cost_per_MWh'])

    # add generator timepoint costs next
    hourly_costs = hourly_costs.merge(costs_by_tp, how='left', on='timestamp')

    # set the excess RA value as a negative cost
    ra_open['Excess_RA_Value'] = - ra_open['Excess_RA_Value']

    # calculate annual ra costs
    ra_open = ra_open[['RA_Open_Position_Cost','Excess_RA_Value']].sum()

    # divide these costs by the number of timepoints
    ra_open = ra_open / len(hourly_costs.index)

    # add the RA costs to the hourly costs
    hourly_costs['ra_open_position_cost'] = ra_open['RA_Open_Position_Cost']
    hourly_costs['excess_ra_value'] = ra_open['Excess_RA_Value']

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

    # calculate hedge market costs


    # parse dates
    hourly_costs = hourly_costs.set_index(pd.to_datetime(hourly_costs['timestamp'])).drop(columns=['timestamp'])

    # rename columns
    hourly_costs = hourly_costs.rename(columns={'DLAP Cost':'DLAP Load Cost',
                                                'hedge_contract_cost': 'Hedge Contract Cost',
                                                'hedge_market_revenue':'Hedge Market Revenue',
                                                'Capacity Contract Cost':'Storage Capacity PPA Cost',
                                                'ra_open_position_cost':'RA Open Position Cost',
                                                'StorageDispatchPnodeCost':'Storage Wholesale Price Arbitrage',
                                                'excess_ra_value':'Excess RA Value'})

    return hourly_costs

def build_hourly_cost_plot(hourly_costs, load_balance):
    """
    """
    costs = hourly_costs.copy()
    load = load_balance.copy().set_index(pd.to_datetime(load_balance['timestamp'])).drop(columns=['timestamp'])

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
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 1, 'hour'], y=costs.loc[costs['quarter'] == 1, 'Total Cost'], row=1, col=1, line=dict(color='black', width=4), name='Q1 Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 2, 'hour'], y=costs.loc[costs['quarter'] == 2, 'Total Cost'], row=1, col=2, line=dict(color='black', width=4), name='Q2 Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 3, 'hour'], y=costs.loc[costs['quarter'] == 3, 'Total Cost'], row=1, col=3, line=dict(color='black', width=4), name='Q3 Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 4, 'hour'], y=costs.loc[costs['quarter'] == 4, 'Total Cost'], row=1, col=4, line=dict(color='black', width=4), name='Q4 Total')

    return hourly_cost_plot

def construct_cost_and_resale_tables(hourly_costs, load_balance, ra_summary):
    """
    Constructs tables that break down costs by component
    """
    # calculate total cost 
    cost_table = hourly_costs.sum(axis=0).reset_index().rename(columns={'index':'Cost Component',0:'Annual Real Cost'})

    # calculate the total demand
    load = load_balance['zone_demand_mw'].sum()

    # calculate the cost per MWh consumed
    cost_table['Cost Per MWh'] = cost_table['Annual Real Cost'] / load

    # TODO: START HERE
    # remove resale costs to a separate table
    resale_components = ['Excess RA Value', 'Excess REC Value']
    resale_table = cost_table.copy()[cost_table['Cost Component'].isin(resale_components)]

    # add a total column
    resale_table = resale_table.append({'Cost Component':'Total', 'Annual Real Cost':resale_table['Annual Real Cost'].sum(), 'Cost Per MWh': resale_table['Cost Per MWh'].sum()}, ignore_index=True)

    # remove resale data from cost table
    cost_table = cost_table[~cost_table['Cost Component'].isin(resale_components)]

    # create a column that categorizes all of the costs
    cost_category_dict = {'Hedge Contract Cost':'Contract', 
                        'Dispatched Generation PPA Cost':'Contract',
                        'Excess Generation PPA Cost':'Contract',
                        'Dispatched Generation Pnode Revenue':'Wholesale Market',
                        'Excess Generation Pnode Revenue':'Wholesale Market', 
                        'DLAP Load Cost':'Wholesale Market',
                        'RA Open Position Cost':'Resource Adequacy', 
                        'Storage Capacity PPA Cost': 'Contract',
                        'Storage Wholesale Price Arbitrage':'Wholesale Market'}
    cost_table['Cost Category'] = cost_table['Cost Component'].map(cost_category_dict).fillna('Fixed')

    # sort the values by category and cost
    cost_table = cost_table.sort_values(by=['Cost Category', 'Annual Real Cost'], ascending=[True,False])

    # re-order the columns
    cost_table = cost_table[['Cost Category','Cost Component', 'Annual Real Cost', 'Cost Per MWh']]

    # add a total column
    cost_table = cost_table.append({'Cost Category':'Total','Cost Component':'Total', 'Annual Real Cost':cost_table['Annual Real Cost'].sum(), 'Cost Per MWh': cost_table['Cost Per MWh'].sum()}, ignore_index=True)

    return cost_table, resale_table

def build_ra_open_position_plot(ra_summary):
    """
    """
    ra_open = ra_summary.copy()
    #where RA Position is negative, it indicates an open position
    ra_open['Position'] = np.where(ra_open["RA_Position_MW"]<0, 'Open Position', 'Excess RA')

    #create a plot of monthly RA position
    monthly_ra_open_fig = px.bar(ra_open, 
                                    x='Month', 
                                    y='RA_Position_MW', 
                                    facet_col='RA_Requirement', 
                                    color='Position', 
                                    color_discrete_map={'Excess RA':'green', 'Open Position':'red'}, 
                                    title='Monthly RA position by requirement').update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor='black')
    monthly_ra_open_fig.for_each_annotation(lambda a: a.update(text=a.text.replace("RA_Requirement=", "")))

    return monthly_ra_open_fig

def build_dispatch_plot(generation_projects_info, dispatch, storage_dispatch, load_balance, system_power, technology_color_map):
    """
    """
    # get the list of technologies
    generator_technology_dict = generation_projects_info[['GENERATION_PROJECT','gen_tech']]
    generator_technology_dict = dict(zip(generator_technology_dict.GENERATION_PROJECT, generator_technology_dict.gen_tech))

    dispatch_data = dispatch.copy()

    # add a generator technology column to the dispatch data
    dispatch_data['Technology'] = dispatch_data['generation_project'].map(generator_technology_dict)

    # replace underscores in the gen tech name with spaces
    dispatch_data.Technology = dispatch_data.Technology.str.replace('_',' ')

    # drop the curtailment column
    dispatch_data = dispatch_data.drop(columns=['CurtailGen_MW','generation_project'])

    # rename the columns
    dispatch_data = dispatch_data.rename(columns={'DispatchGen_MW':'Consumed','ExcessGen_MW':'Excess'})

    # melt the data
    dispatch_data = dispatch_data.melt(id_vars=['Technology','timestamp'], value_vars=['Consumed','Excess'], var_name='Generation Type', value_name='MWh')

    # concatenate the technology and type columns
    dispatch_data['Technology'] = dispatch_data['Generation Type'] + ' ' + dispatch_data['Technology']

    # group the data by technology type
    dispatch_by_tech = dispatch_data.groupby(['Technology','timestamp']).sum().reset_index()

    #append storage 
    storage_discharge = storage_dispatch.copy()[['timestamp','DischargeMW']].rename(columns={'DischargeMW':'MWh'})
    # group the data
    storage_discharge = storage_discharge.groupby('timestamp').sum().reset_index()
    # add a technology column
    storage_discharge['Technology'] = 'Storage Discharge'
    dispatch_by_tech = dispatch_by_tech.append(storage_discharge)

    # append grid energy
    grid_energy = system_power.copy()[['timestamp','system_power_MW']].groupby('timestamp').sum().reset_index().rename(columns={'system_power_MW':'MWh'})
    grid_energy['Technology'] = 'Grid Energy'
    dispatch_by_tech = dispatch_by_tech.append(grid_energy)

    #only keep observations greater than 0
    dispatch_by_tech = dispatch_by_tech[dispatch_by_tech['MWh'] > 0]

    dispatch_by_tech['timestamp'] = pd.to_datetime(dispatch_by_tech['timestamp'])

    # prepare demand data
    load_line = load_balance.copy()[['timestamp','zone_demand_mw']]
    load_line['timestamp'] = pd.to_datetime(load_line['timestamp'])

    # prepare storage charging data
    storage_charge = storage_dispatch.copy()[['timestamp','ChargeMW']]
    # group the data
    storage_charge = storage_charge.groupby('timestamp').sum().reset_index()
    storage_charge['timestamp'] = pd.to_datetime(storage_charge['timestamp'])
    storage_charge['Load+Charge'] = load_line['zone_demand_mw'] + storage_charge['ChargeMW']

    # Build Figure

    dispatch_fig = px.area(dispatch_by_tech, 
                        x='timestamp', 
                        y='MWh', 
                        color='Technology', 
                        color_discrete_map=technology_color_map, 
                        category_orders={'Technology':['Consumed Geothermal','Consumed Small Hydro', 'Consumed Onshore Wind','Consumed Offshore Wind','Consumed Solar PV',
                                                        'Storage Discharge', 'Grid Energy','Excess Solar PV', 'Excess Onshore Wind','Excess Offshore Wind']},
                        labels={'timestamp':'Datetime','Technology':'Key'})
    dispatch_fig.update_traces(line={'width':0})
    dispatch_fig.layout.template = 'plotly_white'
    # add load and storage charging lines
    dispatch_fig.add_scatter(x=storage_charge.timestamp, y=storage_charge['Load+Charge'], text=storage_charge['ChargeMW'], line=dict(color='green', width=3), name='Storage Charge')
    dispatch_fig.add_scatter(x=load_line.timestamp, y=load_line.zone_demand_mw, line=dict(color='black', width=3), name='Demand')

    dispatch_fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1d", step="day", stepmode="backward"),
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(step="all")
            ])))

    return dispatch_by_tech, load_line, storage_charge, dispatch_fig

def build_nodal_prices_plot(nodal_prices, timestamps, generation_projects_info):
    """
    Builds a timeseries plot of all nodal prices used in the model
    """
    # merge the timestamp data
    nodal_data = nodal_prices.copy().merge(timestamps, how='left', left_on='timepoint', right_on='timepoint_id')

    # create a dictionary mapping nodes to projects
    node_map = dict()
    for node in generation_projects_info.gen_pricing_node.unique():
        node_map[node] = list(generation_projects_info.loc[generation_projects_info['gen_pricing_node'] == node, 'GENERATION_PROJECT'].unique())

    nodal_data['Generators'] = nodal_data['pricing_node'].map(node_map)

    nodal_fig = px.line(nodal_data, 
                        x='timestamp', 
                        y='nodal_price', 
                        color='pricing_node', 
                        hover_data=nodal_data[['Generators']],
                        labels={'nodal_price':'$/MWh','timestamp':'Datetime','pricing_node':'Node'}, 
                        title='Nodal Prices', 
                        template='plotly_white').update_layout(hovermode="x").update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor='black')
    nodal_fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1d", step="day", stepmode="backward"),
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(step="all")
            ])))
    
    return nodal_fig

def build_state_of_charge_plot(storage_dispatch, storage_builds, generation_projects_info):
    """
    """
    soc = storage_dispatch.copy()[['generation_project','timestamp','StateOfCharge']]

    soc['timestamp'] = pd.to_datetime(soc['timestamp'])

    #soc = storage.pivot(index='timestamp', columns='generation_project', values='StateOfCharge')

    # identify which projects are hybrids
    hybrid_list = list(generation_projects_info.loc[generation_projects_info['storage_hybrid_generation_project'] != '.', 'GENERATION_PROJECT'].unique())


    #load storage capacity
    storage_energy_capacity = storage_builds.copy()[['generation_project','OnlineEnergyCapacityMWh']]
    # add a column specifying the storage type
    storage_energy_capacity['Type'] = 'Standalone Storage'
    storage_energy_capacity.loc[storage_energy_capacity['generation_project'].isin(hybrid_list),'Type'] = 'Hybrid Storage'
    # groupby type
    storage_energy_capacity = storage_energy_capacity.groupby('Type').sum()
    #create another dictionary of storage energy capacity summed by storage type
    grouped_storage_energy_capacity_dict = storage_energy_capacity.to_dict()['OnlineEnergyCapacityMWh']

    # add a column specifying the storage type
    soc['Type'] = 'Standalone Storage'
    soc.loc[soc['generation_project'].isin(hybrid_list),'Type'] = 'Hybrid Storage'
    # groupby type
    soc = soc.groupby(['timestamp','Type']).sum().reset_index()

    soc = soc.pivot(index='timestamp', columns='Type', values='StateOfCharge')

    #divide by the total capacity to get state of charge
    soc = soc.div(soc.assign(**grouped_storage_energy_capacity_dict))

    # get a list of the columns in case there is only standalone or only hybrid storage
    type_columns = list(soc.columns)

    #soc.index = pd.to_datetime(soc.index)
    soc = soc.reset_index()

    soc_fig = px.line(soc, x='timestamp', y=type_columns, color_discrete_map={'Standalone Storage':'green','Hybrid Storage':'yellowgreen'}, labels={'timestamp':'Datetime','value':'%'}, title='Storage State of Charge')

    soc_fig.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1d", step="day", stepmode="backward"),
            dict(count=7, label="1w", step="day", stepmode="backward"),
            dict(count=1, label="1m", step="month", stepmode="backward"),
            dict(step="all")
        ])))


    return soc_fig

def build_month_hour_dispatch_plot(dispatch_by_tech, load_line, storage_charge, technology_color_map):
    """
    Under construction
    """

    mh_dispatch = dispatch_by_tech.copy()
    mh_dispatch = mh_dispatch.set_index('timestamp')

    #groupby month and hour
    mh_dispatch = mh_dispatch.groupby(['Technology', mh_dispatch.index.month, mh_dispatch.index.hour], axis=0).mean()
    mh_dispatch.index = mh_dispatch.index.rename(['Technology','Month','Hour'])
    mh_dispatch = mh_dispatch.reset_index()

    mh_load_line = load_line.copy()
    mh_load_line = mh_load_line.set_index('timestamp')
    mh_load_line = mh_load_line.groupby([mh_load_line.index.month, mh_load_line.index.hour], axis=0).mean()
    mh_load_line.index = mh_load_line.index.rename(['Month','Hour'])
    mh_load_line = mh_load_line.reset_index()

    mh_storage_charge = storage_charge.copy()
    mh_storage_charge = mh_storage_charge.set_index('timestamp')
    mh_storage_charge = mh_storage_charge.groupby([mh_storage_charge.index.month, mh_storage_charge.index.hour], axis=0).mean()
    mh_storage_charge.index = mh_storage_charge.index.rename(['Month','Hour'])
    mh_storage_charge = mh_storage_charge.reset_index()


    mh_fig = px.area(mh_dispatch, 
                            x='Hour', 
                            y='MWh', 
                            facet_col='Month',
                            facet_col_wrap=6,
                            color='Technology', 
                            color_discrete_map=technology_color_map, 
                            category_orders={'Technology':['Consumed Geothermal','Consumed Small Hydro', 'Consumed Onshore Wind','Consumed Offshore Wind','Consumed Solar PV',
                                                            'Storage Discharge', 'Grid Energy','Excess Solar PV', 'Excess Onshore Wind','Excess Offshore Wind']},
                            labels={'timestamp':'Datetime','Technology':'Key'})
    mh_fig.update_traces(line={'width':0})
    mh_fig.layout.template = 'plotly_white'
    mh_fig.update_xaxes(dtick=3)

    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 1, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 1, 'Load+Charge'], line=dict(color='green', width=4), row=2, col=1, name='Storage Charge', showlegend=True, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 1, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 2, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 2, 'Load+Charge'], line=dict(color='green', width=4), row=2, col=2, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 2, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 3, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 3, 'Load+Charge'], line=dict(color='green', width=4), row=2, col=3, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 3, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 4, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 4, 'Load+Charge'], line=dict(color='green', width=4), row=2, col=4, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 4, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 5, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 5, 'Load+Charge'], line=dict(color='green', width=4), row=2, col=5, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 5, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 6, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 6, 'Load+Charge'], line=dict(color='green', width=4), row=2, col=6, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 6, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 7, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 7, 'Load+Charge'], line=dict(color='green', width=4), row=1, col=1, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 7, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 8, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 8, 'Load+Charge'], line=dict(color='green', width=4), row=1, col=2, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 8, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 9, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 9, 'Load+Charge'], line=dict(color='green', width=4), row=1, col=3, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 9, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 10, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 10, 'Load+Charge'], line=dict(color='green', width=4), row=1, col=4, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 10, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 11, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 11, 'Load+Charge'], line=dict(color='green', width=4), row=1, col=5, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 11, 'ChargeMW'])
    mh_fig.add_scatter(x=mh_storage_charge.loc[mh_storage_charge['Month'] == 12, 'Hour'], y=mh_storage_charge.loc[mh_storage_charge['Month'] == 12, 'Load+Charge'], line=dict(color='green', width=4), row=1, col=6, name='Storage Charge', showlegend=False, text=mh_storage_charge.loc[mh_storage_charge['Month'] == 12, 'ChargeMW'])

    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 1, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 1, 'zone_demand_mw'], line=dict(color='black', width=4), row=2, col=1, name='Demand', showlegend=True)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 2, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 2, 'zone_demand_mw'], line=dict(color='black', width=4), row=2, col=2, name='Demand',showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 3, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 3, 'zone_demand_mw'], line=dict(color='black', width=4), row=2, col=3, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 4, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 4, 'zone_demand_mw'], line=dict(color='black', width=4), row=2, col=4, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 5, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 5, 'zone_demand_mw'], line=dict(color='black', width=4), row=2, col=5, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 6, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 6, 'zone_demand_mw'], line=dict(color='black', width=4), row=2, col=6, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 7, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 7, 'zone_demand_mw'], line=dict(color='black', width=4), row=1, col=1, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 8, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 8, 'zone_demand_mw'], line=dict(color='black', width=4), row=1, col=2, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 9, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 9, 'zone_demand_mw'], line=dict(color='black', width=4), row=1, col=3, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 10, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 10, 'zone_demand_mw'], line=dict(color='black', width=4), row=1, col=4, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 11, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 11, 'zone_demand_mw'], line=dict(color='black', width=4), row=1, col=5, name='Demand', showlegend=False)
    mh_fig.add_scatter(x=mh_load_line.loc[mh_load_line['Month'] == 12, 'Hour'], y=mh_load_line.loc[mh_load_line['Month'] == 12, 'zone_demand_mw'], line=dict(color='black', width=4), row=1, col=6, name='Demand', showlegend=False)

    month_names = ['July', 'August', 'September', 'October', 'November', 'December','January', 'February', 'March', 'April', 'May', 'June']
    for i, a in enumerate(mh_fig.layout.annotations):
        a.text = month_names[i]

    return mh_fig

def build_open_position_plot(load_balance):
    """
    """
    #merge mismatch data
    mismatch = load_balance.copy()
    mismatch['timestamp'] = pd.to_datetime(mismatch['timestamp'])

    mismatch['Net generation'] = mismatch['ZoneTotalGeneratorDispatch'] + mismatch['ZoneTotalExcessGen'] - mismatch['zone_demand_mw']
    mismatch['Net position with storage'] = mismatch['Net generation'] + mismatch['ZoneTotalStorageDischarge'] - mismatch['ZoneTotalStorageCharge']

    mismatch = mismatch.set_index('timestamp')

    mismatch = mismatch.groupby([mismatch.index.month, mismatch.index.hour], axis=0).mean()
    mismatch.index = mismatch.index.rename(['Month','Hour'])
    mismatch = mismatch.reset_index()

    # set month numbers to names
    month_names = {1:'January',2:'February',3:'March', 4:'April', 5:'May', 6:'June',7:'July', 8:'August', 9:'September', 10:'October', 11:'November', 12:'December'}
    mismatch['Month'] = mismatch['Month'].replace(month_names)

    mh_mismatch_fig = px.line(mismatch, 
                            x='Hour', 
                            y=['Net generation','Net position with storage'], 
                            facet_col='Month', 
                            facet_col_wrap=3, 
                            width=1000, 
                            height=1000,
                            labels={'variable':'Position','value':'MW'}).update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor='black')
    mh_mismatch_fig.update_xaxes(dtick=3)
    mh_mismatch_fig.for_each_annotation(lambda a: a.update(text=a.text.replace("Month=", "")))
    mh_mismatch_fig.update_traces(fill='tozeroy')

    return mh_mismatch_fig

def construct_storage_stats_table(storage_cycle_count, storage_builds, storage_dispatch):

    cycles = storage_cycle_count.copy()[['generation_project','storage_max_annual_cycles','Battery_Cycle_Count']]
    cycles = cycles.round(decimals=2)
    cycles = cycles[cycles['Battery_Cycle_Count'] > 0]

    # merge average state of charge data
    soc = storage_dispatch.copy()[['generation_project','StateOfCharge']]
    soc = soc.groupby('generation_project').mean().reset_index()
    cycles = cycles.merge(soc, how='left', on='generation_project')

    # merge energy capacity data
    storage_energy_capacity = storage_builds.copy()[['generation_project','OnlineEnergyCapacityMWh']]
    cycles = cycles.merge(storage_energy_capacity, how='left', on='generation_project')

    # calculate the number of cycles
    cycles['Battery_Cycle_Count'] = cycles['Battery_Cycle_Count'] / cycles['OnlineEnergyCapacityMWh']

    # calculate the average state of charge
    cycles['Average SOC Percent'] = cycles['StateOfCharge'] / cycles['OnlineEnergyCapacityMWh'] * 100

    # drop unused columns
    cycles = cycles.drop(columns=['OnlineEnergyCapacityMWh','StateOfCharge']).set_index('generation_project')
    cycles['Battery_Cycle_Count'] = cycles['Battery_Cycle_Count'].astype(int)

    cycles = cycles.rename(columns={'Battery_Cycle_Count':'Annual Cycles', 'storage_max_annual_cycles':'Maximum Annual Cycle Limit'})

    return cycles

def export_scenario_summary():
    """
    """
    summary = pd.DataFrame(columns=['Scenario Name'], data=['test'])

    summary['Scenario Name'] = scenario_name

    #Goal Data
    summary['Time-coincident Delivered %'] = tc_percent_renewable
    summary['Time-coincident Generation %'] = tc_no_storage_percent_renewable
    summary['Annual Volumetric Renewable %'] = annual_percent_renewable

    unformatted_cost = unformatted_cost.rename(columns={'Annual Real Cost': ' (Annual)',	'Delivered Cost per MWh': ' (per MWh)'}).melt(id_vars=['Cost Component'], var_name='type', value_name=0)
    unformatted_cost['col_name'] = unformatted_cost['Cost Component'] + unformatted_cost['type']


    summary = pd.concat([summary, unformatted_cost[['col_name',0]].set_index('col_name').T], axis=1)

    #Portfolio Mix
    portfolio_summary = portfolio[['MW','Status','Technology']].groupby(['Status','Technology']).sum().reset_index()
    portfolio_summary['Description'] = portfolio_summary['Status'] + " " + portfolio_summary['Technology']
    portfolio_summary = portfolio_summary.drop(columns=['Status','Technology'])
    portfolio_summary = portfolio_summary.set_index('Description').transpose().reset_index(drop=True).add_prefix('MW Capacity from ')

    summary = pd.concat([summary, portfolio_summary], axis=1)

    #Load
    summary['Customer Load GWh'] = load['zone_demand_mw'].sum(axis=0) / 1000
    try:
        summary['Total Load with Storage GWh'] = (load['zone_demand_mw'].sum(axis=0) + storage_charge['ChargeMW'].sum(axis=0)) / 1000
    except (KeyError, NameError):
        summary['Total Load with Storage GWh'] = summary['Customer Load GWh']

    #Generation Mix
    generation_summary = generation_mix.set_index('Source').transpose().reset_index(drop=True).add_prefix('GWh Generation from ')
    summary = pd.concat([summary, generation_summary], axis=1)

    summary = summary.transpose()
    summary.columns = [f'{scenario_name}']

    summary.to_csv(data_dir / 'scenario_summary.csv')

def calculate_BuildGen_reduced_costs(results, generation_projects_info, variable_capacity_factors, baseload_capacity_factors, dispatch):
    """
    """
    # load results into dataframe and reset index
    rc = pd.DataFrame.from_dict(results.solution.Variable, orient='index')
    rc = rc.reset_index()

    # split the index column into the variable name and index value
    rc[['Variable','index']] = rc['index'].str.split('[', expand=True)
    rc['index'] = rc['index'].str.strip(']')

    rc = rc[rc['Variable'] == 'BuildGen']

    # split the index into the load zone and timepoint components
    rc[['generation_project','period']] = rc['index'].str.split(',', expand=True)
    rc = rc.drop(columns=['period','index'])

    # merge in generator characteristic data
    rc = rc.merge(generation_projects_info[['GENERATION_PROJECT','gen_is_variable','gen_is_baseload','gen_is_storage','ppa_energy_cost','ppa_capacity_cost']], how='left', left_on='generation_project', right_on='GENERATION_PROJECT').drop(columns=['GENERATION_PROJECT'])

    # sum capacity factors by generator
    vcf = variable_capacity_factors.copy().groupby('GENERATION_PROJECT').sum()[['variable_capacity_factor']].reset_index()
    try:
        bcf = baseload_capacity_factors.copy().groupby('GENERATION_PROJECT').sum()[['baseload_capacity_factor']].reset_index()
    # if there are no baseload generators
    except KeyError:
        bcf = baseload_capacity_factors.copy()

    gen_list = list(rc['generation_project'].unique())


    for g in gen_list:
        # if the reduced cost is negative, ignore it
        if  (rc.loc[rc['generation_project'] == g, 'Rc'].item() < 0):
            pass
        # if the generator is variable 
        elif (rc.loc[rc['generation_project'] == g, 'gen_is_variable'].item() == 1):
            # calculate the reduced cost per MW capacity
            rc.loc[rc['generation_project'] == g, 'Rc'] = rc.loc[rc['generation_project'] == g, 'Rc'].item() / vcf.loc[vcf['GENERATION_PROJECT'] == g, 'variable_capacity_factor'].item()
        # otherwise if the generator is baseload
        elif (rc.loc[rc['generation_project'] == g, 'gen_is_baseload'].item() == 1):
            # calculate the reduced cost per MW capacity
            rc.loc[rc['generation_project'] == g, 'Rc'] = rc.loc[rc['generation_project'] == g, 'Rc'].item() / bcf.loc[bcf['GENERATION_PROJECT'] == g, 'baseload_capacity_factor'].item()
        # otherwise if the generator is storage
        elif (rc.loc[rc['generation_project'] == g, 'gen_is_storage'].item() == 1):
            pass
        # otherwise the generator is dispatchable and we need to calculate how much it actually dispatched
        else:
            # calculate the total dispatch
            total_dispatch = dispatch[dispatch['generation_project'] == g].sum()[['DispatchGen_MW','ExcessGen_MW']].sum()
            # convert to a capacity factor total
            total_cf = total_dispatch / rc.loc[rc['generation_project'] == g, 'Value'].item()
            # calculate reduced cost per MW capacity
            rc.loc[rc['generation_project'] == g, 'Rc'] = rc.loc[rc['generation_project'] == g, 'Rc'] / total_cf


    # drop unneccessary columns
    rc = rc.drop(columns=['Variable','gen_is_variable','gen_is_baseload','gen_is_storage'])
    rc = rc.rename(columns={'Value':'built_MW','Rc':'reduced_cost'})

    rc = rc[['generation_project', 'built_MW','ppa_energy_cost','ppa_capacity_cost','reduced_cost']].set_index('generation_project')

    # negative reduced costs apply to upper bounds
    neg_rc = rc.copy()[rc['reduced_cost'] < 0]
    neg_rc = neg_rc.sort_values(by='reduced_cost')
    # positive reduced costs apply to lower bounds
    pos_rc = rc.copy()[rc['reduced_cost'] > 0]
    pos_rc['Cost to be built'] = pos_rc['ppa_energy_cost'] + pos_rc['ppa_capacity_cost'] - pos_rc['reduced_cost']
    # zero reduced cost with a value of zero means that there is another optimal solution
    alternate_optima = rc.copy()[(rc['reduced_cost'] == 0) & (rc['built_MW'] == 0)]

    # the positive reduced costs can be split into two groups
    pos_rc_lower = pos_rc.copy()[pos_rc['built_MW'] == 0]
    pos_rc_upper = pos_rc.copy()[pos_rc['built_MW'] > 0]


    return pos_rc_lower, pos_rc_upper, neg_rc, alternate_optima

def calculate_load_shadow_price(results, timestamps):
    """
    """
    # load the duals into a dataframe and reset the index
    duals = pd.DataFrame.from_dict(results.solution.Constraint, orient='index')
    duals = duals.reset_index()

    # split the index into columns for the constraint name and the index value
    duals[['Constraint','index']] = duals['index'].str.split('[', expand=True)
    #duals['index'] = '[' + duals['index']
    duals['index'] = duals['index'].str.strip(']')

    # filter the constraints to the zone energy balance
    duals = duals[duals['Constraint'] == 'Zone_Energy_Balance']

    # split the index into the load zone and timepoint components
    duals[['load_zone','timepoint']] = duals['index'].str.split(',', expand=True)
    duals['timepoint'] = duals['timepoint'].astype(int)
    duals = duals.drop(columns=['index'])

    # merge the timestamp data
    duals = duals.copy().merge(timestamps, how='left', left_on='timepoint', right_on='timepoint_id')

    # sort the values
    duals = duals.sort_values(by=['load_zone','timepoint'])

    #re-order columns
    #duals = duals[['Constraint', 'load_zone','timepoint','Dual']]

    # replace all negative values with zero since interpretation is complicated by the fact that the nodal revenue of excess generation is not part of the objective function

    duals.loc[duals['Dual'] < 0, 'Dual'] = 0

    # Calculate the month-hour average
    duals = duals.set_index('timestamp')
    duals = duals.groupby([duals.index.month, duals.index.hour]).mean()
    duals.index = duals.index.rename(['Month','Hour'])
    duals = duals.reset_index()

    # set month numbers to names
    month_names = {1:'January',2:'February',3:'March', 4:'April', 5:'May', 6:'June',7:'July', 8:'August', 9:'September', 10:'October', 11:'November', 12:'December'}
    duals['Month'] = duals['Month'].replace(month_names)

    dual_plot = px.line(duals, 
                        x='Hour', 
                        y='Dual', 
                        facet_col='Month', 
                        facet_col_wrap=6,
                        labels={'Dual':'Shadow Price ($/MW)'})

    dual_plot.for_each_annotation(lambda a: a.update(text=a.text.replace("Month=", "")))
    dual_plot.update_xaxes(dtick=3)
    dual_plot.update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor='black')

    return dual_plot

def construct_summary_output_table(scenario_name, cost_table, load_balance, portfolio, sensitivity_table, avoided_emissions, emissions, emissions_unit):
    """
    Creates a csv file output of key metrics to compare with other scenarios
    """

    summary = pd.DataFrame(columns=['Scenario Name'], data=['test'])

    summary['Scenario Name'] = scenario_name

    #Goal Data
    summary['Time-coincident %'] = hourly_renewable_percentage(load_balance)
    summary['Annual Volumetric %'] = annual_renewable_percentage(load_balance)

    summary['Portfolio Cost per MWh'] = cost_table.loc[cost_table['Cost Category'] == 'Total', 'Cost Per MWh'].item()

    for year in list(sensitivity_table['Weather Year']):
        summary[f'Sensitivity Performance Year {year}'] = sensitivity_table.loc[sensitivity_table['Weather Year'] == year, 'Time-Coincident %'].item()

    #Portfolio Mix
    portfolio_summary = portfolio[['MW','Status','Technology']].groupby(['Status','Technology']).sum().reset_index()
    portfolio_summary['Description'] = portfolio_summary['Status'] + " " + portfolio_summary['Technology']
    portfolio_summary = portfolio_summary.drop(columns=['Status','Technology'])
    portfolio_summary = portfolio_summary.set_index('Description').transpose().reset_index(drop=True).add_prefix('MW Capacity from ')
    portfolio_summary['Total MW Capacity'] = portfolio_summary.sum(axis=1)

    summary = pd.concat([summary, portfolio_summary], axis=1)

    summary[f'Annual Emissions Footprint ({emissions_unit.split("/")[0]})'] = emissions["Emission Rate"].sum().round(1)
    summary[f'Delivered Emissions Factor ({emissions_unit})'] = emissions["Delivered Emission Factor"].mean().round(3)


    summary['Low Case Avoided Emissions'] = avoided_emissions.low_case
    summary['Mid Case Avoided Emissions'] = avoided_emissions.mid_case
    summary['High Case Avoided Emissions'] = avoided_emissions.high_case

    summary = summary.transpose()
    summary.columns = [f'{scenario_name}']

    return summary

def run_sensitivity_analysis(gen_set, gen_cap, dispatch, generation_projects_info, load_balance, storage_builds):
    """
    """
    set_folder = Path.cwd() / f'../../{gen_set}/'
    weather_years = [filename for filename in os.listdir(set_folder) if '.csv' in filename]

    # get dataframe of all generators that were built
    built_gens = gen_cap.copy()[gen_cap['GenCapacity'] > 0]

    # separate out the storage generators
    built_gens = built_gens[built_gens['gen_energy_source'] != 'Electricity']

    sensitivity_table = pd.DataFrame(columns=['Weather Year', 'Time-Coincident %'])

    for weather_year in weather_years:
        year = weather_year.split('_')[0]

        # load weather year data
        vcf_for_year = pd.read_csv(set_folder / weather_year)

        # create a blank dataframe
        balance = pd.DataFrame(index=range(8760))
        generation = pd.DataFrame(index=range(8760))

        # for each generator
        for gen in list(built_gens['generation_project']):
            built_capacity = built_gens.loc[built_gens['generation_project'] == gen, 'GenCapacity'].item()
            try:
                vcf = vcf_for_year[gen]
                generation[gen] = built_capacity * vcf
            except KeyError:
                generation[gen] = dispatch.copy().loc[dispatch['generation_project'] == gen,['DispatchGen_MW','ExcessGen_MW','CurtailGen_MW']].reset_index(drop=True).sum(axis=1)

        # sum to get total generation
        balance['generation'] = generation.sum(axis=1)

        # add load
        balance['load'] = load_balance['zone_demand_mw']

        # add blank columns for storage dynamics
        balance['charge'] = 0
        balance['discharge'] = 0
        balance['soc'] = 0
        balance['grid_power'] = 0

        built_storage = storage_builds.copy()[storage_builds['OnlinePowerCapacityMW'] > 0]

        # get storage parameters
        storage_power = built_storage['OnlinePowerCapacityMW'].sum()
        storage_energy = built_storage['OnlineEnergyCapacityMWh'].sum()
        # calculate an energy capacity weighted average of RTE
        rte_calc = built_storage.copy().merge(generation_projects_info[['GENERATION_PROJECT','storage_roundtrip_efficiency']], how='left', left_on='generation_project', right_on='GENERATION_PROJECT')
        rte_calc['product'] = rte_calc['OnlineEnergyCapacityMWh'] * rte_calc['storage_roundtrip_efficiency'].astype(float)
        storage_rte = rte_calc['product'].sum() / rte_calc['OnlineEnergyCapacityMWh'].sum()
        conversion_loss = math.sqrt(storage_rte)
        initial_soc = storage_energy / 2
        # greedy storage charging algorithm
        for t in range(len(balance)):
            generation_t = balance.loc[t,'generation']
            load_t = balance.loc[t,'load']
            if t == 0:
                balance.loc[t,'charge'] = 0 if (generation_t < load_t) else min((generation_t - load_t), storage_power, ((storage_energy - initial_soc)/conversion_loss) )
                balance.loc[t,'discharge'] = 0 if (generation_t > load_t) else min((load_t - generation_t), storage_power, (initial_soc*conversion_loss) )
                balance.loc[t,'soc'] = initial_soc + balance.loc[t,'charge']*conversion_loss - balance.loc[t,'discharge']*conversion_loss
            else:
                soc_prev = balance.loc[t - 1,'soc']
                balance.loc[t,'charge'] = 0 if (generation_t < load_t) else min((generation_t - load_t), storage_power, ((storage_energy - soc_prev)/conversion_loss) )
                balance.loc[t,'discharge'] = 0 if (generation_t > load_t) else min((load_t - generation_t), storage_power, (soc_prev*conversion_loss) )
                balance.loc[t,'soc'] = soc_prev + balance.loc[t,'charge']*conversion_loss - balance.loc[t,'discharge']/conversion_loss
            balance.loc[t,'grid_power'] = 0 if ((generation_t + balance.loc[t,'discharge']) > load_t) else (load_t - (generation_t + balance.loc[t,'discharge']))
            

        tc_performance = (1 - (balance.grid_power.sum() / balance.load.sum())) * 100
                
        print(f'Time-coincident performance using year {year} weather data: {tc_performance.round(2)}%')
        sensitivity_table = sensitivity_table.append({'Weather Year':year, 'Time-Coincident %':tc_performance}, ignore_index=True)

    return sensitivity_table

def calculate_avoided_emissions(portfolio, dispatch, marginal_emissions):
    """
    """
    # get a list of all of the additional gens
    additional_gens = list(portfolio.loc[portfolio['Status'] == 'Additional','generation_project'])

    #filter the dispatch data to the additional gens
    addl_dispatch = dispatch.copy()[dispatch['generation_project'].isin(additional_gens)]

    # groupby timestamp
    addl_dispatch = addl_dispatch.groupby('timestamp').sum()

    # calculate total generation in each timestamp
    addl_dispatch['TotalGen_MW'] = addl_dispatch['DispatchGen_MW'] + addl_dispatch['ExcessGen_MW']

    # calculate the avoided emissions in each timepoint
    avoided_emissions = marginal_emissions.copy().drop(columns='timepoint')
    for col in avoided_emissions.columns:
        avoided_emissions[col] = avoided_emissions[col] * addl_dispatch['TotalGen_MW'].reset_index(drop=True)

    # get the total for the entire year
    avoided_emissions = avoided_emissions.sum()

    return avoided_emissions