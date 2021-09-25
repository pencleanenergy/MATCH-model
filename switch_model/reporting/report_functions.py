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
    if hourly_costs['hedge_cost_per_MWh'].mean() == 0.0000001:
        hourly_costs['hedge_cost'] = 0

    hourly_costs = hourly_costs.drop(columns=['hedge_cost_per_MWh'])

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
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 1, 'hour'], y=costs.loc[costs['quarter'] == 1, 'Total Cost'], row=1, col=1, line=dict(color='black', width=4), name='Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 2, 'hour'], y=costs.loc[costs['quarter'] == 2, 'Total Cost'], row=1, col=2, line=dict(color='black', width=4), name='Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 3, 'hour'], y=costs.loc[costs['quarter'] == 3, 'Total Cost'], row=1, col=3, line=dict(color='black', width=4), name='Total')
    hourly_cost_plot.add_scatter(x=costs.loc[costs['quarter'] == 4, 'hour'], y=costs.loc[costs['quarter'] == 4, 'Total Cost'], row=1, col=4, line=dict(color='black', width=4), name='Total')

    return hourly_cost_plot

def construct_cost_and_resale_tables(hourly_costs, load_balance, ra_summary):
    """
    Constructs tables that break down costs by component
    """
    # calculate total cost 
    cost_table = hourly_costs.sum(axis=0).reset_index().rename(columns={'index':'Cost Component',0:'Annual Real Cost'})

    # calculate the total demand
    load = load_balance['zone_demand_mw'].sum()

    # replace the Excess RA Value with the actual value
    cost_table.loc[cost_table['Cost Component'] == 'Excess RA Value', 'Annual Real Cost'] = -1 * calculate_sellable_excess_RA(ra_summary)

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
                                    title='Monthly RA position by requirement')
    monthly_ra_open_fig.for_each_annotation(lambda a: a.update(text=a.text.replace("RA_Requirement=", "")))

    return monthly_ra_open_fig

def calculate_sellable_excess_RA(ra_summary):
    """
    The total value of excess RA cannot be calculated as the simple product of the excess RA and the resale value.
    Flex RA must be paired with system RA to sell. 
    Because local RA also contributes to system RA, we cannot sell it as both.
    """
    sellable_flex = ra_summary.copy()
    sellable_flex = sellable_flex[(sellable_flex['RA_Requirement'] == 'flexible_RA') & (sellable_flex['RA_Position_MW'] > 0)]

    #flex RA must be paired with regular RA to sell, so we need to limit it
    def calculate_sellable_flex(row, ra_summary):
        # get the month number
        month = row['Month']
        #get the amount of excess system RA
        system_ra_summary_MW = ra_summary.loc[(ra_summary['RA_Requirement'] == 'system_RA') & (ra_summary['Month'] == month), 'Excess_RA_MW'].item()
        # find the minimum of the excess system RA and excess flex RA
        sellable = min(row['RA_Position_MW'], system_ra_summary_MW)
        return sellable   

    sellable_flex.loc[:,'Sellable_Flex_MW'] = sellable_flex.apply(lambda row: calculate_sellable_flex(row, ra_summary), axis=1)

    #re-calculate the sellable position of flex RA
    sellable_flex['Excess_RA_Value'] = sellable_flex['RA_Value'] * sellable_flex['Sellable_Flex_MW']

    #calculate how much system could be sold for subtracting the local
    sellable_system = ra_summary[(ra_summary['RA_Requirement'] == 'system_RA')]

    local_RA = ra_summary[(ra_summary['RA_Requirement'] != 'system_RA') & (ra_summary['RA_Requirement'] != 'flexible_RA')][['Month','Excess_RA_MW']]
    local_RA = local_RA.groupby('Month').sum().reset_index().rename(columns={'Excess_RA_MW':'Local_RA_MW'})

    #merge local RA data into system data
    sellable_system = sellable_system.merge(local_RA, how='left', on='Month').fillna(0)
    sellable_system['Sellable_System_MW'] = sellable_system['Excess_RA_MW'] - sellable_system['Local_RA_MW']

    sellable_system['Excess_RA_Value'] = sellable_system['RA_Value'] * sellable_system['Sellable_System_MW']

    #calculate total RA costs and value
    excess_flex_RA_value = sellable_flex['Excess_RA_Value'].sum()
    excess_local_RA_value = ra_summary.loc[(ra_summary['RA_Requirement'] != 'system_RA') & (ra_summary['RA_Requirement'] != 'flexible_RA'), 'Excess_RA_Value'].sum()
    excess_system_RA_value = sellable_system['Excess_RA_Value'].sum()

    sellable_ra = excess_flex_RA_value + excess_local_RA_value + excess_system_RA_value

    return sellable_ra

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
                        category_orders={'Technology':['Consumed Geothermal','Consumed Small Hydro', 'Consumed Onshore Wind','Consumed Solar PV',
                                                        'Storage Discharge', 'Grid Energy','Excess Solar PV', 'Excess Onshore Wind']},
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

    return dispatch_fig
