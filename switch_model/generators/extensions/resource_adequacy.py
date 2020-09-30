"""
Determines the resource adequacy value for built resources and adds RA open position cost to the objective function

"""

#input: list of regions, period, and cost
#input: ELCC value for resources
#input: from generation projects: which RA region contributes to
#input: RA requirement by month
#param: months

#expression: calculate RA value by generator, month
#total RA value
#calculate open position for each category for each month
#calculate cost of open position and add to objective function

# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
This module defines planning reserves margins to support resource adequacy
requirements. These requirements are sometimes called capacity reserve margins.

Planning reserve margins have been an industry standard for decades that are
roughly defined as: (GenerationCapacity - Demand) / Demand. The idea was that
if you have 15% generation capacity above and beyond demand, the grid could
maintain high reliability. Generation capacity typically includes local
capacity and scheduled imports, while demand typically accounts for demand
response and other distributed energy resources.

This simple definition is problematic for energy-constrained resources such as
hydro, wind, solar, or storage. It also fails to account whether a resource
will be available when it is needed. As this problem became more recognized,
people shifted terminology from "planning reserve margin" to "resource
adequacy requirements" which had more dynamic rules based on time of day,
weather conditions, season, etc.

The "correct" treatment of energy constrained resources is still being debated.
This module implements a simple and flexible treatment, where the user can
specify capacity_value timeseries for any generator, so the available capacity
will be: GenCapacity[g] * capacity_value[g,t]. For renewable resources, this
capacity value timeseries will default to their capacity factor timeseries.

By default, storage and transmission will be credited with their expected
net power delivery.

References:

North American Electric Reliability Corporation brief definition and
discussion of planning reserve margins.
http://www.nerc.com/pa/RAPA/ri/Pages/PlanningReserveMargin.aspx

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
    'switch_model.energy_sources.properties',
    'switch_model.generators.core.build',
    'switch_model.generators.core.dispatch',
    'switch_model.generators.storage'
)


def define_components(mod):
    """
    MONTHS

    RA_REQUIREMENT_CATEGORIES

    LOCAL_RELIABILITY_AREAS

    RAR_AREAS
    
    tp_month[t] defines which month (1-12) each timepoint belongs to
    
    """
    #set of months
    mod.MONTHS = Set(ordered=True, initialize=[1,2,3,4,5,6,7,8,9,10,11,12])

    #set of RA resource (RAR) types
    mod.RA_REQUIREMENT_CATEGORIES = Set(
        doc="Types of RA for which a requirement is specified")

    #set of local reliability areas (LRA)
    mod.LOCAL_RELIABILITY_AREAS = Set()

    #link between RAR and LRA
    mod.RAR_AREAS = Set(
        dimen=2,
        doc="A set of (r, a) that describes which local reliability areas contribute to each RA Requirement.")

    #describe the local reliability area that each generator is in
    mod.gen_reliability_area = Param (
        mod.GENERATION_PROJECTS, 
        within=mod.LOCAL_RELIABILITY_AREAS)


    mod.RA_MONTHS = Set(dimen=2,
        initialize=lambda m: m.RA_REQUIREMENT_CATEGORIES * m.MONTHS,
        doc="The cross product of RA requirements and Months, used for indexing.")

    def GENS_IN_AREA_init(m, a):
        if not hasattr(m, 'GENS_IN_AREA_dict'):
            m.GENS_IN_AREA_dict = {_a: [] for _a in m.LOCAL_RELIABILITY_AREAS}
            for g in m.GENERATION_PROJECTS:
                m.GENS_IN_AREA_dict[m.gen_reliability_area[g]].append(g)
        result = m.GENS_IN_AREA_dict.pop(a)
        if not m.GENS_IN_AREA_dict:
            del m.GENS_IN_AREA_dict
        return result
    mod.GENS_IN_AREA = Set(
        mod.LOCAL_RELIABILITY_AREAS,
        initialize=GENS_IN_AREA_init)


    #specify which month each timepoint is associated with
    # mod.tp_month = Param(mod.TIMEPOINTS, within=mod.MONTHS)

    #specify the ra requirement for each resource type and month
    mod.ra_requirement = Param(
        mod.PERIODS, mod.RA_MONTHS,
        within=NonNegativeReals)

    #specify the flexible RA requirement
    mod.flexible_ra_requirement = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    #specify the market cost of RA
    mod.ra_cost = Param(
        mod.PERIODS, mod.RA_MONTHS,
        within=NonNegativeReals)

    #specify the market cost of flexible RA
    mod.flexible_ra_cost = Param(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals)

    mod.gen_capacity_value = Param(
        mod.PERIODS, mod.ENERGY_SOURCES, mod.MONTHS,
        within=NonNegativeReals)
    
    ## NEED TO CONSIDER WHAT ZONE THE GENERATOR IS IN

    #calculate monthly RA of all generators in each LRA
    
    mod.RAValueByArea = Expression (
        mod.PERIODS, mod.LOCAL_RELIABILITY_AREAS, mod.MONTHS,
        rule=lambda m, p, a, mo: sum(
            m.GenCapacity[g,p] * m.gen_capacity_value[p, m.gen_energy_source[g], mo]
            for g in m.GENS_IN_AREA[a]))

    def areas_for_rar(m,r):
        return [a for (_r, a) in m.RAR_AREAS if _r == r]
    
    #calculate total RA available to meet requirement
    def AvailableRACapacity_rule(m,p,r,mo):
        AREAS = areas_for_rar(m,r)
        capacity = sum(m.RAValueByArea[p,a,mo] for a in AREAS)
        return capacity
    mod.AvailableRACapacity = Expression ( #was called RAValueByRequirement
        mod.PERIODS, mod.RA_MONTHS,
        rule=AvailableRACapacity_rule)

    #calculate RA open position
    mod.RAOpenPosition = Expression(
        mod.PERIODS, mod.RA_MONTHS,
        rule=lambda m, p, r, mo: m.ra_requirement[p,r,mo] - m.AvailableRACapacity[p,r,mo])

    """
    COST_DOMAIN_PTS = [-999999999.,0.,0.,999999999.]
    #TODO: allow user to specify discount for selling RA
    COST_RANGE_PTS = [0.,0.,1.,1.]

    #setup a piecewise expression to only optimize for RA open position, but not excess RA
    mod.RACostDiscount = Var(
        mod.PERIODS, mod.RA_MONTHS,
        within=NonNegativeReals
    )

    # https://github.com/Pyomo/pyomo/tree/master/examples/pyomo/piecewise
    mod.Cost_Discount_Constraint = Piecewise(
        mod.PERIODS, mod.RA_MONTHS, #indexing sets
        mod.RACostDiscount, mod.RAOpenPosition, #range and domain vaiables
        pw_pts=COST_DOMAIN_PTS,
        pw_constr_type='EQ',
        f_rule=COST_RANGE_PTS,
        pw_repn='INC'
    )
    """

    #calculate cost of RA open position
    mod.AnnualRAOpenPositionCostByRequirement = Expression (
        mod.PERIODS, mod.RA_REQUIREMENT_CATEGORIES,
        rule=lambda m, p, r: sum(m.RAOpenPosition[p,r,mo] * m.ra_cost[p,r,mo] for mo in m.MONTHS))

    #calculate total RA open position cost for the year
    mod.AnnualRAOpenPositionCost = Expression (
        mod.PERIODS, 
        rule=lambda m, p: sum(m.AnnualRAOpenPositionCostByRequirement[p,r] for r in m.RA_REQUIREMENT_CATEGORIES))


    #create separate function to calculate flex RA

    #calculate monthly flexible RA value of portfolio
    def AvailableFlexRACapacity_rule(m,p):
        storage = sum(
            m.GenCapacity[g,p] * (1 + m.storage_charge_to_discharge_ratio[g]) 
            for g in m.STORAGE_GENS 
            if m.gen_reliability_area[g] != "Ineligible")
        #in the future if other non-storage renewables can provide flexible capacity, rules can be added here
        other = 0
        total_flex = storage + other
        return total_flex
    mod.AvailableFlexRACapacity = Expression (
        mod.PERIODS,
        rule=AvailableFlexRACapacity_rule)

    #calculate flexible RA open position
    mod.FlexRAOpenPosition = Expression (
        mod.PERIODS, mod.MONTHS,
        rule=lambda m, p, mo: m.flexible_ra_requirement[p,mo] - m.AvailableFlexRACapacity[p])

    #calculate cost of RA open position
    """
    def AnnualFlexRAOpenPositionCost_rule(m,p):
        cost = sum(m.FlexRAOpenPosition[p,mo] * m.flexible_ra_cost[p,mo] 
            for mo in m.MONTHS 
            if ((value(m.FlexRAOpenPosition[p,mo]) >= 0) or ((value(m.FlexRAOpenPosition[p,mo]) < 0) and (value(m.FlexRAOpenPosition[p,mo]) > value(m.RAOpenPosition[p,"system_RA",mo])))))
        sell_bundled = sum(m.RAOpenPosition[p,"system_RA",mo] * m.flexible_ra_cost[p,mo] 
            for mo in m.MONTHS 
            if ((value(m.FlexRAOpenPosition[p,mo]) < 0) and (value(m.FlexRAOpenPosition[p,mo]) < value(m.RAOpenPosition[p,"system_RA",mo]))))
        total_cost = cost + sell_bundled
        return total_cost
    """
   
    """
    #setup a piecewise expression to only optimize for RA open position, but not excess RA
    mod.FlexRACostDiscount = Var(
        mod.PERIODS, mod.MONTHS,
        within=NonNegativeReals
    )

    # https://github.com/Pyomo/pyomo/tree/master/examples/pyomo/piecewise
    mod.Flex_Cost_Discount_Constraint = Piecewise(
        mod.PERIODS, mod.MONTHS, #indexing sets
        mod.FlexRACostDiscount, mod.FlexRAOpenPosition, #range and domain vaiables
        pw_pts=COST_DOMAIN_PTS,
        pw_constr_type='EQ',
        f_rule=COST_RANGE_PTS,
        pw_repn='INC'
    )
    """
    mod.AnnualFlexRAOpenPositionCost = Expression (
        mod.PERIODS,
        rule=lambda m,p: sum(m.FlexRAOpenPosition[p,mo] * m.flexible_ra_cost[p,mo] for mo in m.MONTHS))

    #add RA and flex RA costs together
    mod.TotalRAOpenPositionCost = Expression (
        mod.PERIODS, 
        rule=lambda m, p: m.AnnualRAOpenPositionCost[p] + m.AnnualFlexRAOpenPositionCost[p])

    #add to objective function
    #mod.Cost_Components_Per_Period.append('TotalRAOpenPositionCost')



def load_inputs(mod, switch_data, inputs_dir):
    """
    reserve_capacity_value.csv
        GEN, TIMEPOINT, gen_capacity_value

    planning_reserve_requirement_zones.csv
        PLANNING_RESERVE_REQUIREMENTS, prr_cap_reserve_margin, prr_enforcement_timescale

    generation_projects_info.csv
        ..., gen_can_provide_cap_reserves

    planning_reserve_requirement_zones.csv
        PRR, ZONE

    """

    """
    # don't need tp month b/c RA is not indexed by tp
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'months.csv'),
        auto_select=True,
        param=(mod.tp_month))
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        index=mod.GENERATION_PROJECTS,
        param=(mod.gen_reliability_area))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ra_requirement_categories.csv'),
        set=mod.RA_REQUIREMENT_CATEGORIES)
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'local_reliability_areas.csv'),
        set=mod.LOCAL_RELIABILITY_AREAS)
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ra_requirement_areas.csv'),
        set=mod.RAR_AREAS)
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ra_requirement.csv'),
        auto_select=True,
        param=(mod.ra_requirement, mod.ra_cost))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'flexible_ra_requirement.csv'),
        auto_select=True,
        param=(mod.flexible_ra_requirement, mod.flexible_ra_cost))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ra_capacity_value.csv'),
        auto_select=True,
        param=(mod.gen_capacity_value))



def post_solve(instance, outdir):
    """
    Export storage build information to storage_builds.csv, and storage
    dispatch info to storage_dispatch.csv
    """
    ra_dat = [{
        "Period": p,
        "RA_Requirement": r,
        "Month": mo,
        "RA_Requirement_Need_MW": value(instance.ra_requirement[p,r,mo]),
        "Available_RA_Capacity_MW": value(instance.AvailableRACapacity[p,r,mo]),
        "Open_Position_MW": value(instance.RAOpenPosition[p,r,mo]),
        "Open_Position_Cost": value(instance.RAOpenPosition[p,r,mo] * instance.ra_cost[p,r,mo]),
    } for (r, mo) in instance.RA_MONTHS for p in instance.PERIODS]
    RA_df = pd.DataFrame(ra_dat)
    RA_df.set_index(["Period","RA_Requirement","Month"], inplace=True)

    flex_dat = [{
        "Period": p,
        "RA_Requirement": "flexible_RA",
        "Month": mo,
        "RA_Requirement_Need_MW": value(instance.flexible_ra_requirement[p,mo]),
        "Available_RA_Capacity_MW": value(instance.AvailableFlexRACapacity[p]),
        "Open_Position_MW": value(instance.FlexRAOpenPosition[p,mo]),
        "Open_Position_Cost": value(instance.FlexRAOpenPosition[p,mo] * instance.flexible_ra_cost[p,mo]),
    } for mo in instance.MONTHS for p in instance.PERIODS]
    FRA_df = pd.DataFrame(flex_dat)
    FRA_df.set_index(["Period","RA_Requirement","Month"], inplace=True)

    RA_df = pd.concat([RA_df,FRA_df])

    RA_df.to_csv(os.path.join(outdir, "RA_open_position.csv"))

    RA_summary = RA_df.groupby(['Period',"Month"]).sum()
    RA_summary.to_csv(
        os.path.join(outdir, "RA_monthly_cost.csv"), columns=["Open_Position_Cost"])

    def areas_for_rar(instance,r):
        return [a for (_r, a) in instance.RAR_AREAS if _r == r]

    gen_dat = [{
        "Period": p,
        "Month": mo,
        "Generation_Project": g,
        "Local_Reliability_Area": value(instance.gen_reliability_area[g]),
        "RA_Requirement": r,
        "RA_Value": value(instance.GenCapacity[g,p] * instance.gen_capacity_value[p, instance.gen_energy_source[g], mo])
            if instance.gen_reliability_area[g] in areas_for_rar(instance,r) else 0
    } for g in instance.GENERATION_PROJECTS for (r,mo) in instance.RA_MONTHS for p in instance.PERIODS]
    gen_df = pd.DataFrame(gen_dat)

    gen_flex_dat = [{
        "Period": p,
        "Month": mo,
        "Generation_Project": g,
        "Local_Reliability_Area": value(instance.gen_reliability_area[g]),
        "RA_Requirement": "flexible_RA",
        "RA_Value": value(instance.GenCapacity[g,p] * (1 + instance.storage_charge_to_discharge_ratio[g]))
            if instance.gen_reliability_area[g] != "Ineligible" else 0
    } for g in instance.STORAGE_GENS for mo in instance.MONTHS for p in instance.PERIODS]
    gen_flex_df = pd.DataFrame(gen_flex_dat)

    gen_df = pd.concat([gen_df,gen_flex_df], ignore_index=True)

    #gen_df = gen_df.pivot(index=["Period","Month","Generation_Project","Local_Reliability_Area"], columns=["RA_Requirement"], values=["RA_Value"]).fillna(0)

    gen_df.to_csv(os.path.join(outdir, "RA_value_by_generator.csv"), index=False)