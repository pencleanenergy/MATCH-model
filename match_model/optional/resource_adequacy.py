# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

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
    "match_model.timescales",
    "match_model.financials",
    "match_model.balancing.load_zones",
    "match_model.generators.build",
    "match_model.generators.dispatch",
    "match_model.generators.storage",
)


def define_arguments(argparser):
    argparser.add_argument(
        "--sell_excess_RA",
        choices=["none", "sell"],
        default="none",
        help="Whether or not to consider sold excess RA in the objective function. "
        "Specify 'none' to disable.",
    )
    argparser.add_argument(
        "--include_RA_MTR_requirement",
        choices=["True", "False"],
        default="False",
        help="Whether or not to include the midterm reliability requirement constraints in the model.",
    )


def define_components(mod):
    """
    MONTHS

    RA_REQUIREMENT_CATEGORIES

    LOCAL_RELIABILITY_AREAS

    RAR_AREAS

    tp_month[t] defines which month (1-12) each timepoint belongs to

    """

    # Define Parameters
    ###################

    mod.gen_is_ra_eligible = Param(mod.GENERATION_PROJECTS, within=Boolean)

    # specify the ra requirement for each resource type and month
    mod.ra_requirement = Param(mod.PERIODS, mod.MONTHS, within=NonNegativeReals)

    # specify the flexible RA requirement
    mod.flexible_ra_requirement = Param(
        mod.PERIODS, mod.MONTHS, within=NonNegativeReals
    )

    # specify the market cost of RA
    mod.ra_cost = Param(mod.PERIODS, mod.MONTHS, within=NonNegativeReals)

    # specify the resell value of RA
    mod.ra_resell_value = Param(
        mod.PERIODS, mod.MONTHS, within=NonNegativeReals, default=0
    )

    # specify the market cost of flexible RA
    mod.flexible_ra_cost = Param(mod.PERIODS, mod.MONTHS, within=NonNegativeReals)

    # specify the resell value of flexible RA
    mod.flexible_ra_resell_value = Param(
        mod.PERIODS, mod.MONTHS, within=NonNegativeReals, default=0
    )

    mod.elcc = Param(
        mod.PERIODS, mod.ENERGY_SOURCES, mod.MONTHS, within=NonNegativeReals
    )

    mod.ra_production_factor = Param(
        mod.PERIODS, mod.ENERGY_SOURCES, mod.MONTHS, within=NonNegativeReals
    )

    mod.midterm_firm_requirement = Param(
        mod.PERIODS, within=NonNegativeReals, default=0
    )

    mod.midterm_ldes_requirement = Param(
        mod.PERIODS, within=NonNegativeReals, default=0
    )

    # calculate monthly RA of all generators in each LRA
    def CalculateEffectiveELCC(m, g, p, mo):
        effective_elcc = 0
        if m.gen_is_ra_eligible[g]:
            if m.gen_is_variable[g] and not m.gen_is_hybrid[g]:
                # NQC = Pmax * ELCC
                effective_elcc = m.elcc[p, m.gen_energy_source[g], mo]
            elif m.gen_is_baseload[g] and not m.gen_is_hybrid[g]:
                # NQC = average production during hours of 4-9pm in each month
                # We will use the alternate method of using published technology factors
                effective_elcc = m.elcc[p, m.gen_energy_source[g], mo]
            elif m.gen_is_storage[g] and not m.gen_is_hybrid[g]:
                # standalone storage
                effective_elcc = m.elcc[p, m.gen_energy_source[g], mo]
            elif m.gen_is_storage[g] and m.gen_is_hybrid[g]:
                # energy storage portion of hybrid
                # the minimum functions work because they are calculating the minumum of static parameters, not variables
                # however, since implementing min and max hybrid capacity ratios, the actual capacity ratio is no longer static
                # to fix this, we take the average of the min and max ratio to minimize error in the calcukation
                storage_hybrid_capacity_ratio = (
                    m.storage_hybrid_min_capacity_ratio[g]
                    + m.storage_hybrid_max_capacity_ratio[g]
                ) / 2
                effective_elcc = min(
                    storage_hybrid_capacity_ratio
                    * m.elcc[p, m.gen_energy_source[g], mo],
                    (
                        min(
                            storage_hybrid_capacity_ratio
                            * m.storage_energy_to_power_ratio[g],
                            m.ra_production_factor[
                                p,
                                m.gen_energy_source[
                                    m.storage_hybrid_generation_project[g]
                                ],
                                mo,
                            ],
                        )
                        / 4
                    ),
                )
            elif m.gen_is_hybrid[g] and not m.gen_is_storage[g]:
                for s in m.HYBRID_STORAGE_GENS:
                    if g == m.storage_hybrid_generation_project[s]:
                        hybrid_gen_storage_component = s
                storage_hybrid_capacity_ratio = (
                    m.storage_hybrid_min_capacity_ratio[hybrid_gen_storage_component]
                    + m.storage_hybrid_max_capacity_ratio[hybrid_gen_storage_component]
                ) / 2
                effective_elcc = m.elcc[p, m.gen_energy_source[g], mo] * (
                    (
                        m.ra_production_factor[p, m.gen_energy_source[g], mo]
                        - min(
                            storage_hybrid_capacity_ratio
                            * m.storage_energy_to_power_ratio[
                                hybrid_gen_storage_component
                            ],
                            m.ra_production_factor[p, m.gen_energy_source[g], mo],
                        )
                    )
                    / m.ra_production_factor[p, m.gen_energy_source[g], mo]
                )
            else:
                # dispatchable generators
                effective_elcc = 1
        return effective_elcc

    mod.GeneratorELCC = Expression(
        mod.GENERATION_PROJECTS, mod.PERIODS, mod.MONTHS, rule=CalculateEffectiveELCC
    )

    def CalculateAvailableRACapacity(m, p, mo):
        system_ra_capacity = 0
        for g in m.GENERATION_PROJECTS:
            # for the storage portion of a hybrid project
            if m.gen_is_hybrid[g] and m.gen_is_storage[g]:
                storage_hybrid_capacity_ratio = (
                    m.storage_hybrid_min_capacity_ratio[g]
                    + m.storage_hybrid_max_capacity_ratio[g]
                ) / 2
                system_ra_capacity = system_ra_capacity + (
                    m.GeneratorELCC[g, p, mo]
                    * (m.GenCapacity[g, p] / storage_hybrid_capacity_ratio)
                )
            else:
                system_ra_capacity = system_ra_capacity + (
                    m.GeneratorELCC[g, p, mo] * m.GenCapacity[g, p]
                )
        return system_ra_capacity

    mod.AvailableRACapacity = Expression(
        mod.PERIODS, mod.MONTHS, rule=CalculateAvailableRACapacity
    )

    # calculate RA open position
    mod.RAOpenPosition = Var(mod.PERIODS, mod.MONTHS, within=NonNegativeReals)

    # specify that the open position should be 0 if the available capacity > the requirement. and otherwise should make up the difference
    mod.RA_Purchase_Constraint = Constraint(
        mod.PERIODS,
        mod.MONTHS,
        rule=lambda m, p, mo: m.RAOpenPosition[p, mo] + m.AvailableRACapacity[p, mo]
        >= m.ra_requirement[p, mo],
    )

    # calculate cost of RA open position
    mod.AnnualRAOpenPositionCost = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.RAOpenPosition[p, mo] * m.ra_cost[p, mo] for mo in m.MONTHS
        ),
    )

    # calculate excess RA by category
    mod.RAExcess = Expression(
        mod.PERIODS,
        mod.MONTHS,
        rule=lambda m, p, mo: m.AvailableRACapacity[p, mo]
        - m.ra_requirement[p, mo]
        + m.RAOpenPosition[p, mo],
    )

    # calculate the resell value of excess RA
    mod.AnnualRAExcessValue = Expression(
        mod.PERIODS,
        rule=lambda m, p: -sum(
            m.RAExcess[p, mo] * m.ra_resell_value[p, mo] for mo in m.MONTHS
        ),
    )

    # Flexible RA
    #############

    # calculate monthly flexible RA value of portfolio
    def CalculateEffectiveFlexibleCapacity(m, g, p):
        efc = 0
        if m.gen_is_ra_eligible[g]:
            if g in m.STORAGE_GENS:
                efc = m.GenCapacity[g, p] * (1 + m.storage_charge_to_discharge_ratio[g])
        return efc

    mod.GeneratorFlexRAValue = Expression(
        mod.GENERATION_PROJECTS, mod.PERIODS, rule=CalculateEffectiveFlexibleCapacity
    )

    mod.AvailableFlexRACapacity = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.GeneratorFlexRAValue[g, p] for g in m.GENERATION_PROJECTS
        ),
    )

    # calculate flexible RA open position
    mod.FlexRAOpenPosition = Var(mod.PERIODS, mod.MONTHS, within=NonNegativeReals)

    mod.FlexRA_Purchase_Constraint = Constraint(
        mod.PERIODS,
        mod.MONTHS,
        rule=lambda m, p, mo: m.FlexRAOpenPosition[p, mo] + m.AvailableFlexRACapacity[p]
        >= m.flexible_ra_requirement[p, mo],
    )

    # calculate the cost of the flex RA open position
    mod.AnnualFlexRAOpenPositionCost = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.FlexRAOpenPosition[p, mo] * m.flexible_ra_cost[p, mo] for mo in m.MONTHS
        ),
    )

    # calculate excess flex RA
    mod.FlexRAExcess = Expression(
        mod.PERIODS,
        mod.MONTHS,
        rule=lambda m, p, mo: m.AvailableFlexRACapacity[p]
        - m.flexible_ra_requirement[p, mo]
        + m.FlexRAOpenPosition[p, mo],
    )

    mod.SellableExcessFlexRA = Var(mod.PERIODS, mod.MONTHS, within=NonNegativeReals)

    mod.SellableExcessFlexRAConstraint_1 = Constraint(
        mod.PERIODS,
        mod.MONTHS,
        rule=lambda m, p, mo: m.SellableExcessFlexRA[p, mo] <= m.RAExcess[p, mo],
    )

    mod.SellableExcessFlexRAConstraint_2 = Constraint(
        mod.PERIODS,
        mod.MONTHS,
        rule=lambda m, p, mo: m.SellableExcessFlexRA[p, mo] <= m.FlexRAExcess[p, mo],
    )

    # calculate the resell value of excess RA
    mod.AnnualFlexRAExcessValue = Expression(
        mod.PERIODS,
        rule=lambda m, p: -sum(
            m.SellableExcessFlexRA[p, mo] * m.flexible_ra_resell_value[p, mo]
            for mo in m.MONTHS
        ),
    )

    # Calculate total RA Open Position Cost
    #######################################

    # add RA and flex RA costs together
    mod.TotalRAOpenPositionCost = Expression(
        mod.PERIODS,
        rule=lambda m, p: m.AnnualRAOpenPositionCost[p]
        + m.AnnualFlexRAOpenPositionCost[p],
    )

    # add to objective function
    mod.Cost_Components_Per_Period.append("TotalRAOpenPositionCost")

    # TODO: test if I need to do anything else for inputs
    if mod.options.sell_excess_RA == "sell":
        mod.TotalRAExcessValue = Expression(
            mod.PERIODS,
            rule=lambda m, p: m.AnnualRAExcessValue[p] + m.AnnualFlexRAExcessValue[p],
        )

        # add to objective function
        mod.Cost_Components_Per_Period.append("TotalRAExcessValue")

    # Midterm reliability order
    ###########################

    if mod.options.include_RA_MTR_requirement == "True":

        def MidtermReliability_Rule(m, p):
            eligible_MTR_capacity = 0
            for g in m.BASELOAD_GENS:
                if m.gen_is_ra_eligible[g]:
                    if m.cod_year[g] > m.base_financial_year:
                        eligible_MTR_capacity += m.GenCapacity[g, p]
            return eligible_MTR_capacity >= m.midterm_firm_requirement[p]

        mod.MidtermReliabilityRequirement_Constraint = Constraint(
            mod.PERIODS, rule=MidtermReliability_Rule
        )

        # another part of the rule is a certain amount of long-duration energy storage is required in the portfolio
        # long-duration energy storage is defined as storage with an energy-to-power ratio >= 8 hours
        mod.LONG_DURATION_STORAGE = Set(
            initialize=mod.STORAGE_GENS,
            filter=lambda m, g: m.storage_energy_to_power_ratio[g] >= 8,
        )

        mod.LDESCapacity = Expression(
            mod.PERIODS,
            rule=lambda m, p: sum(
                m.GenCapacity[g, p]
                for g in m.LONG_DURATION_STORAGE
                if m.gen_is_ra_eligible[g]
            ),
        )

        mod.MidtermLDESRequirement_Constraint = Constraint(
            mod.PERIODS,
            rule=lambda m, p: m.LDESCapacity[p] >= m.midterm_ldes_requirement[p],
        )


def load_inputs(mod, match_data, inputs_dir):
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

    match_data.load_aug(
        filename=os.path.join(inputs_dir, "generation_projects_info.csv"),
        auto_select=True,
        index=mod.GENERATION_PROJECTS,
        param=[mod.gen_is_ra_eligible],
    )
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "ra_requirement.csv"),
        select=("period", "month", "ra_requirement", "ra_cost", "ra_resell_value"),
        optional_params=["ra_resell_value"],
        param=[mod.ra_requirement, mod.ra_cost, mod.ra_resell_value],
    )
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "flexible_ra_requirement.csv"),
        select=(
            "period",
            "month",
            "flexible_ra_requirement",
            "flexible_ra_cost",
            "flexible_ra_resell_value",
        ),
        optional_params=["flexible_ra_resell_value"],
        param=[
            mod.flexible_ra_requirement,
            mod.flexible_ra_cost,
            mod.flexible_ra_resell_value,
        ],
    )
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "ra_capacity_value.csv"),
        select=("period", "gen_energy_source", "month", "elcc", "ra_production_factor"),
        param=[mod.elcc, mod.ra_production_factor],
    )
    match_data.load_aug(
        filename=os.path.join(inputs_dir, "midterm_reliability_requirement.csv"),
        select=("period", "midterm_firm_requirement", "midterm_ldes_requirement"),
        param=[mod.midterm_firm_requirement, mod.midterm_ldes_requirement],
    )


def post_solve(instance, outdir):
    """ """
    ra_dat = [
        {
            "Period": p,
            "RA_Requirement": "system_RA",
            "Month": mo,
            "RA_Requirement_Need_MW": value(instance.ra_requirement[p, mo]),
            "Available_RA_Capacity_MW": value(instance.AvailableRACapacity[p, mo]),
            "RA_Position_MW": value(
                instance.AvailableRACapacity[p, mo] - instance.ra_requirement[p, mo]
            ),
            "Open_Position_MW": value(instance.RAOpenPosition[p, mo]),
            "Excess_RA_MW": value(instance.RAExcess[p, mo]),
            "RA_Cost": value(instance.ra_cost[p, mo]),
            "RA_Value": value(instance.ra_resell_value[p, mo]),
            "RA_Open_Position_Cost": value(
                instance.RAOpenPosition[p, mo] * instance.ra_cost[p, mo]
            ),
            "Excess_RA_Value": value(
                instance.RAExcess[p, mo] * instance.ra_resell_value[p, mo]
            ),
        }
        for mo in instance.MONTHS
        for p in instance.PERIODS
    ]
    RA_df = pd.DataFrame(ra_dat)
    RA_df.set_index(["Period", "RA_Requirement", "Month"], inplace=True)

    flex_dat = [
        {
            "Period": p,
            "RA_Requirement": "flexible_RA",
            "Month": mo,
            "RA_Requirement_Need_MW": value(instance.flexible_ra_requirement[p, mo]),
            "Available_RA_Capacity_MW": value(instance.AvailableFlexRACapacity[p]),
            "RA_Position_MW": value(
                instance.AvailableFlexRACapacity[p]
                - instance.flexible_ra_requirement[p, mo]
            ),
            "Open_Position_MW": value(instance.FlexRAOpenPosition[p, mo]),
            "Excess_RA_MW": value(instance.FlexRAExcess[p, mo]),
            "RA_Cost": value(instance.flexible_ra_cost[p, mo]),
            "RA_Value": value(instance.flexible_ra_resell_value[p, mo]),
            "RA_Open_Position_Cost": value(
                instance.FlexRAOpenPosition[p, mo] * instance.flexible_ra_cost[p, mo]
            ),
            "Excess_RA_Value": value(
                instance.FlexRAExcess[p, mo] * instance.flexible_ra_resell_value[p, mo]
            ),
        }
        for mo in instance.MONTHS
        for p in instance.PERIODS
    ]
    FRA_df = pd.DataFrame(flex_dat)
    FRA_df.set_index(["Period", "RA_Requirement", "Month"], inplace=True)

    RA_df = pd.concat([RA_df, FRA_df])

    RA_df.to_csv(os.path.join(outdir, "RA_summary.csv"))

    gen_dat = [
        {
            "Period": p,
            "Month": mo,
            "Generation_Project": g,
            "Built Capacity": value(instance.GenCapacity[g, p]),
            "ELCC": value(instance.GeneratorELCC[g, p, mo]),
            "System_RA_Value": value(
                (
                    instance.GeneratorELCC[g, p, mo]
                    * (
                        instance.GenCapacity[g, p]
                        / (
                            (
                                instance.storage_hybrid_min_capacity_ratio[g]
                                + instance.storage_hybrid_max_capacity_ratio[g]
                            )
                            / 2
                        )
                    )
                )
                if g in instance.HYBRID_STORAGE_GENS
                else (instance.GeneratorELCC[g, p, mo] * instance.GenCapacity[g, p])
            ),
            "Flex_RA_Value": value(instance.GeneratorFlexRAValue[g, p]),
        }
        for p in instance.PERIODS
        for mo in instance.MONTHS
        for g in instance.GENERATION_PROJECTS
    ]
    gen_df = pd.DataFrame(gen_dat)

    gen_df.to_csv(os.path.join(outdir, "RA_value_by_generator.csv"), index=False)
