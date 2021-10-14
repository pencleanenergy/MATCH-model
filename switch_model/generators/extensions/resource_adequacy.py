# Copyright (c) 2021 The MATCH Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Determines the resource adequacy value for built resources and adds RA open position cost to the objective function

California Independent System Operator Issue paper on Resource Adequacy which
includes both capacity and flexibility requirements. Capacity reserve
requirements can be both system-wide and local, and can potentially accomodate
anything that injects, withdraws or reshapes power. Note that the flexibility
requirements finally includes an energy component, not just ramping capabilities.
http://www.caiso.com/Documents/IssuePaper-RegionalResourceAdequacy.pdf

CA ISO comments filed with the Public Utilities Commission on resource adequacy
rules (and the need to improve them)
https://www.caiso.com/Documents/Jan29_2016_Comments_2017Track1Proposals_ResourceAdequacyProgram_R14-10-010.pdf

"""

import os 
from pyomo.environ import *
import pandas as pd

dependencies = (
    'switch_model.timescales',
    'switch_model.financials',
    'switch_model.balancing.load_zones',
    'switch_model.generators.core.build',
    'switch_model.generators.core.dispatch',
    'switch_model.generators.storage'
)

def define_arguments(argparser):
    argparser.add_argument('--sell_excess_RA', choices=['none', 'sell'], default='none',
        help=
            "Whether or not to consider sold excess RA in the objective function. "
            "Specify 'none' to disable."
    )

def define_components(mod):
    """
    MONTHS

    RA_REQUIREMENT_CATEGORIES

    LOCAL_RELIABILITY_AREAS

    RAR_AREAS
    
    tp_month[t] defines which month (1-12) each timepoint belongs to
    
    """
    
    # Define Sets
    #############
    
    #set of months
    mod.MONTHS = Set(ordered=True, initialize=[1,2,3,4,5,6,7,8,9,10,11,12], dimen=1)


    #specify which month each timepoint is associated with
    # mod.tp_month = Param(mod.TIMEPOINTS, within=mod.MONTHS)

    # Define Parameters
    ###################

    mod.gen_is_ra_eligible = Param(mod.GENERATION_PROJECTS, within=Boolean)

    #specify the ra requirement for each resource type and month
    mod.ra_requirement = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    #specify the flexible RA requirement
    mod.flexible_ra_requirement = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    #specify the market cost of RA
    mod.ra_cost = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    #specify the resell value of RA
    mod.ra_resell_value = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals,
        default=0) 

    #specify the market cost of flexible RA
    mod.flexible_ra_cost = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    #specify the resell value of flexible RA
    mod.flexible_ra_resell_value = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals,
        default=0)

    mod.elcc = Param(
        mod.PERIODS, mod.ENERGY_SOURCES, mod.MONTHS,
        within=NonNegativeReals)

    mod.ra_production_factor = Param(
        mod.PERIODS, mod.ENERGY_SOURCES, mod.MONTHS,
        within=NonNegativeReals)

    mod.midterm_reliability_requirement = Param(
        mod.PERIODS,
        within=NonNegativeReals,
        default=0)
    
    #calculate monthly RA of all generators in each LRA
    def CalculateNetQualifyingCapacity(m,p,mo):
        total_nqc = 0
        for g in m.GENERATION_PROJECTS:
            if m.gen_is_ra_eligible[g]:
                if m.gen_is_variable[g]:
                    # NQC = Pmax * ELCC
                    nqc = m.GenCapacity[g,p] * m.elcc[p, m.gen_energy_source[g], mo]
                    total_nqc = total_nqc + nqc
                elif m.gen_is_baseload[g]:
                    # NQC = average production during hours of 4-9pm in each month
                    # We will use the alternate method of using published technology factors
                    nqc = m.GenCapacity[g,p] * m.elcc[p, m.gen_energy_source[g], mo]
                    total_nqc = total_nqc + nqc
                elif m.gen_is_storage[g] and not m.gen_is_hybrid[g]:
                    # standalone storage
                    nqc = m.GenCapacity[g,p] * m.elcc[p, m.gen_energy_source[g], mo]
                    total_nqc = total_nqc + nqc
                elif m.gen_is_storage[g] and m.gen_is_hybrid[g]:
                    # energy storage portion of hybrid
                    # the minimum functions work because they are calculating the minumum of static parameters, not variables
                    # however, since implementing min and max hybrid capacity ratios, the actual capacity ratio is no longer static
                    # to fix this, we take the average of the min and max ratio to minimize error in the calcukation
                    storage_hybrid_capacity_ratio = (m.storage_hybrid_min_capacity_ratio[g] + m.storage_hybrid_max_capacity_ratio[g]) / 2
                    nqc = m.GenCapacity[g,p] * min(storage_hybrid_capacity_ratio, (min(storage_hybrid_capacity_ratio * m.storage_energy_to_power_ratio[g],m.ra_production_factor[p, m.gen_energy_source[g], mo]))/4)
                    total_nqc = total_nqc + nqc
                elif m.gen_is_hybrid[g] and not m.gen_is_storage[g]:
                    # renewable energy portion of hybrid
                    storage_hybrid_capacity_ratio = (m.storage_hybrid_min_capacity_ratio[g] + m.storage_hybrid_max_capacity_ratio[g]) / 2
                    nqc = m.GenCapacity[g,p] * (m.elcc[p, m.gen_energy_source[g], mo] * ((m.ra_production_factor[p, m.gen_energy_source[g], mo] - min(storage_hybrid_capacity_ratio * m.storage_energy_to_power_ratio[g],m.ra_production_factor[p, m.gen_energy_source[g], mo]))/m.ra_production_factor[p, m.gen_energy_source[g], mo]))
                    total_nqc = total_nqc + nqc
                else:
                    # dispatchable generators
                    nqc = m.GenCapacity[g,p]
                    total_nqc = total_nqc + nqc
        return total_nqc

    mod.AvailableRACapacity = Expression (
        mod.PERIODS, mod.MONTHS,
        rule=CalculateNetQualifyingCapacity)

    #calculate RA open position
    mod.RAOpenPosition = Var(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    #specify that the open position should be 0 if the available capacity > the requirement. and otherwise should make up the difference
    mod.RA_Purchase_Constraint = Constraint(
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.RAOpenPosition[p,mo] + m.AvailableRACapacity[p,mo] >= m.ra_requirement[p,mo])

    #calculate cost of RA open position
    mod.AnnualRAOpenPositionCost = Expression (
        mod.PERIODS, 
        rule=lambda m, p: sum(m.RAOpenPosition[p,mo] * m.ra_cost[p,mo] for mo in m.MONTHS))
    
    #calculate excess RA by category
    mod.RAExcess = Expression(
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.AvailableRACapacity[p,mo] - m.ra_requirement[p,mo] + m.RAOpenPosition[p,mo])

    #calculate the resell value of excess RA
    mod.AnnualRAExcessValue = Expression (
        mod.PERIODS, 
        rule=lambda m, p: - sum(m.RAExcess[p,mo] * m.ra_resell_value[p,mo] for mo in m.MONTHS))

    # Flexible RA
    #############

    #calculate monthly flexible RA value of portfolio
    def AvailableFlexRACapacity_rule(m,p):
        storage = sum(
            m.GenCapacity[g,p] * (1 + m.storage_charge_to_discharge_ratio[g]) 
            for g in m.STORAGE_GENS 
            if m.gen_is_ra_eligible[g])
        #in the future if other non-storage renewables can provide flexible capacity, rules can be added here
        other = 0
        total_flex = storage + other
        return total_flex
    mod.AvailableFlexRACapacity = Expression (
        mod.PERIODS,
        rule=AvailableFlexRACapacity_rule)

    #calculate flexible RA open position
    mod.FlexRAOpenPosition = Var(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    mod.FlexRA_Purchase_Constraint = Constraint(
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.FlexRAOpenPosition[p,mo] + m.AvailableFlexRACapacity[p] >= m.flexible_ra_requirement[p,mo]
    )

    #calculate the cost of the flex RA open position
    mod.AnnualFlexRAOpenPositionCost = Expression (
        mod.PERIODS,
        rule=lambda m,p: sum(m.FlexRAOpenPosition[p,mo] * m.flexible_ra_cost[p,mo] for mo in m.MONTHS))

    #calculate excess flex RA
    mod.FlexRAExcess = Expression(
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.AvailableFlexRACapacity[p] - m.flexible_ra_requirement[p,mo] + m.FlexRAOpenPosition[p,mo])

    mod.SellableExcessFlexRA = Var(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    mod.SellableExcessFlexRAConstraint_1 = Constraint(
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.SellableExcessFlexRA[p, mo] <= m.RAExcess[p,mo])

    mod.SellableExcessFlexRAConstraint_2 = Constraint(
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.SellableExcessFlexRA[p, mo] <= m.FlexRAExcess[p,mo])

    #calculate the resell value of excess RA
    mod.AnnualFlexRAExcessValue = Expression (
        mod.PERIODS, 
        rule=lambda m, p: - sum(m.SellableExcessFlexRA[p,mo] * m.flexible_ra_resell_value[p,mo] for mo in m.MONTHS))


    # Calculate total RA Open Position Cost
    #######################################

    #add RA and flex RA costs together
    mod.TotalRAOpenPositionCost = Expression (
        mod.PERIODS, 
        rule=lambda m, p: m.AnnualRAOpenPositionCost[p] + m.AnnualFlexRAOpenPositionCost[p])

    #add to objective function
    mod.Cost_Components_Per_Period.append('TotalRAOpenPositionCost')

    #TODO: test if I need to do anything else for inputs
    if mod.options.sell_excess_RA == 'sell':
        mod.TotalRAExcessValue = Expression(
            mod.PERIODS,
            rule=lambda m, p: m.AnnualRAExcessValue[p] + m.AnnualFlexRAExcessValue[p]
        )

        #add to objective function
        mod.Cost_Components_Per_Period.append('TotalRAExcessValue')

    # Midterm reliability order
    ###########################

    def MidtermReliability_Rule(m,p):
        if not any(m.GenCapacity[g,p] for g in m.BASELOAD_GENS):
            return Constraint.Skip
        return sum(m.GenCapacity[g,p] for g in m.BASELOAD_GENS) >= m.midterm_reliability_requirement[p]

    mod.MidtermReliabilityRequirement_Constraint = Constraint(
        mod.PERIODS,
        rule=MidtermReliability_Rule)



def load_inputs(mod, switch_data, inputs_dir):
    """
    reserve_capacity_value.csv
        GEN, TIMEPOINT, elcc

    planning_reserve_requirement_zones.csv
        PLANNING_RESERVE_REQUIREMENTS, prr_cap_reserve_margin, prr_enforcement_timescale

    generation_projects_info.csv
        ..., gen_can_provide_cap_reserves

    planning_reserve_requirement_zones.csv
        PRR, ZONE

    """


    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        index=mod.GENERATION_PROJECTS,
        param=[mod.gen_is_ra_eligible])
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ra_requirement.csv'),
        select=('period','tp_month', 'ra_requirement', 'ra_cost', 'ra_resell_value'),
        index=[mod.PERIODS, mod.MONTHS],
        optional_params=['ra_resell_value'],
        param=[mod.ra_requirement, mod.ra_cost, mod.ra_resell_value])
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'flexible_ra_requirement.csv'),
        select=('period','tp_month', 'flexible_ra_requirement','flexible_ra_cost','flexible_ra_resell_value'),
        index=[mod.PERIODS, mod.MONTHS],
        optional_params=['flexible_ra_resell_value'],
        param=[mod.flexible_ra_requirement, mod.flexible_ra_cost, mod.flexible_ra_resell_value])
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ra_capacity_value.csv'),
        select=('period','gen_energy_source', 'tp_month','elcc','ra_production_factor'),
        index=[mod.PERIODS, mod.ENERGY_SOURCES, mod.MONTHS],
        param=[mod.elcc, mod.ra_production_factor])
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'midterm_reliability_requirement.csv'),
        auto_select=True,
        index=mod.PERIODS,
        param=[mod.midterm_reliability_requirement])



def post_solve(instance, outdir):
    """

    """
    ra_dat = [{
        "Period": p,
        "RA_Requirement": 'system_RA',
        "Month": mo,
        "RA_Requirement_Need_MW": value(instance.ra_requirement[p,mo]),
        "Available_RA_Capacity_MW": value(instance.AvailableRACapacity[p,mo]),
        "RA_Position_MW": value(instance.AvailableRACapacity[p,mo] - instance.ra_requirement[p,mo]),
        "Open_Position_MW": value(instance.RAOpenPosition[p,mo]),
        "Excess_RA_MW":  value(instance.RAExcess[p,mo]),
        "RA_Cost": value(instance.ra_cost[p,mo]),
        "RA_Value": value(instance.ra_resell_value[p,mo]),
        "RA_Open_Position_Cost": value(instance.RAOpenPosition[p,mo] * instance.ra_cost[p,mo]),
        "Excess_RA_Value": value(instance.RAExcess[p,mo] * instance.ra_resell_value[p,mo])
    } for mo in instance.MONTHS for p in instance.PERIODS]
    RA_df = pd.DataFrame(ra_dat)
    RA_df.set_index(["Period","RA_Requirement","Month"], inplace=True)

    flex_dat = [{
        "Period": p,
        "RA_Requirement": "flexible_RA",
        "Month": mo,
        "RA_Requirement_Need_MW": value(instance.flexible_ra_requirement[p,mo]),
        "Available_RA_Capacity_MW": value(instance.AvailableFlexRACapacity[p]),
        "RA_Position_MW": value(instance.AvailableFlexRACapacity[p] - instance.flexible_ra_requirement[p,mo]),
        "Open_Position_MW": value(instance.FlexRAOpenPosition[p,mo]),
        "Excess_RA_MW": value(instance.FlexRAExcess[p,mo]),
        "RA_Cost": value(instance.flexible_ra_cost[p,mo]),
        "RA_Value": value(instance.flexible_ra_resell_value[p,mo]),
        "RA_Open_Position_Cost": value(instance.FlexRAOpenPosition[p,mo] * instance.flexible_ra_cost[p,mo]),
        "Excess_RA_Value": value(instance.FlexRAExcess[p,mo] * instance.flexible_ra_resell_value[p,mo])
    } for mo in instance.MONTHS for p in instance.PERIODS]
    FRA_df = pd.DataFrame(flex_dat)
    FRA_df.set_index(["Period","RA_Requirement","Month"], inplace=True)

    RA_df = pd.concat([RA_df,FRA_df])

    RA_df.to_csv(os.path.join(outdir, "RA_summary.csv"))


    gen_dat = [{
        "Period": p,
        "Month": mo,
        "Generation_Project": g,
        "RA_Requirement": "system_RA",
        "RA_Value": value(instance.GenCapacity[g,p] * instance.elcc[p, instance.gen_energy_source[g], mo])
    } for g in instance.GENERATION_PROJECTS for mo in instance.MONTHS for p in instance.PERIODS]
    gen_df = pd.DataFrame(gen_dat)

    gen_flex_dat = [{
        "Period": p,
        "Month": mo,
        "Generation_Project": g,
        "RA_Requirement": "flexible_RA",
        "RA_Value": value(instance.GenCapacity[g,p] * (1 + instance.storage_charge_to_discharge_ratio[g]))
            if instance.gen_is_ra_eligible[g] else 0
    } for g in instance.STORAGE_GENS for mo in instance.MONTHS for p in instance.PERIODS]
    gen_flex_df = pd.DataFrame(gen_flex_dat)

    gen_df = pd.concat([gen_df,gen_flex_df], ignore_index=True)

    gen_df.to_csv(os.path.join(outdir, "RA_value_by_generator.csv"), index=False)