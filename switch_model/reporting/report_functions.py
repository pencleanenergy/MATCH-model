# Copyright (c) 2021 *****************. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

from pathlib import Path
import pandas as pd
import numpy as np

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
    storage_costs = storage_costs.merge(gen_cap[['generation_project','Annual_PPA_Capacity_Cost']], how='left', on='generation_project').fillna(0)

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
                                          'Annual_PPA_Capacity_Cost':'Capacity Contract Cost',
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




    