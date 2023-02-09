# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
This takes data from an input excel file and formats into individual csv files for inputs
"""
import ast
from collections import defaultdict
from datetime import datetime
import pandas as pd
import pytz
import numpy as np
import os
import requests
import shutil
import zipfile
import warnings

# Import the PySAM modules for simulating solar, CSP, and wind power generation
import PySAM.ResourceTools as tools
import PySAM.Pvwattsv8 as pv
import PySAM.TcsmoltenSalt as csp_tower
import PySAM.Windpower as wind

warnings.filterwarnings(
    "ignore", message="Data Validation extension is not supported and will be removed"
)


def validate_cost_inputs(xl_gen, df_vcf, nodal_prices, output_dir):
    xl_gen_validated = xl_gen.copy()

    # add a column for ppa penalty
    xl_gen_validated["ppa_penalty"] = 0

    # remove any generation projects that are not variable or baseload
    gens_to_check = xl_gen_validated.copy().loc[
        (xl_gen_validated["gen_is_variable"] == 1)
        | (xl_gen_validated["gen_is_baseload"] == 1),
        :,
    ]
    # create a list of unique generators
    gens_to_check = list(gens_to_check["GENERATION_PROJECT"].unique())

    # for each generator
    for gen in gens_to_check:
        # check if the generator has a predetermined build capacity
        predetermined_cap = xl_gen_validated.loc[
            xl_gen_validated["GENERATION_PROJECT"] == gen, "gen_predetermined_cap"
        ].values[0]
        max_cap = xl_gen_validated.loc[
            xl_gen_validated["GENERATION_PROJECT"] == gen, "gen_capacity_limit_mw"
        ].values[0]
        # if the generator already is capped at a predetermined build limit, don't set a limit
        if predetermined_cap == ".":
            set_limit = True
        elif max_cap == ".":
            set_limit = True
        elif predetermined_cap < max_cap:
            set_limit = True
        elif predetermined_cap == max_cap:
            set_limit = False

        if set_limit is True:
            ppa_price = xl_gen_validated.loc[
                xl_gen_validated["GENERATION_PROJECT"] == gen, "ppa_energy_cost"
            ].values[0]
            node = xl_gen_validated.loc[
                xl_gen_validated["GENERATION_PROJECT"] == gen, "gen_pricing_node"
            ].values[0]
            nodal_price = nodal_prices.copy()[[node]].reset_index(drop=True)
            profile = df_vcf.copy()[[gen]].reset_index(drop=True)

            # calculate PPA cost
            mean_ppa_cost = (profile[gen] * ppa_price).sum() / profile[gen].sum()

            # caclulate nodal revenue
            mean_nodal_revenue = (profile[gen] * nodal_price[node]).sum() / profile[
                gen
            ].sum()

            # if the mean nodal revenue is greater than the mean PPA cost
            if mean_nodal_revenue >= mean_ppa_cost:
                ppa_penalty = round(mean_nodal_revenue - mean_ppa_cost + 0.01, 3)
                print(f"WARNING: {gen} nodal revenue greater than PPA cost")
                print("This may lead to over-procurement of this resource")
                print(f"Mean PPA cost = ${mean_ppa_cost.round(3)} per MWh")
                print(f"Mean nodal revenue = ${mean_nodal_revenue.round(3)} per MWh")
                xl_gen_validated.loc[
                    xl_gen_validated["GENERATION_PROJECT"] == gen, "ppa_penalty"
                ] = ppa_penalty

    xl_gen_validated = xl_gen_validated[
        ["GENERATION_PROJECT", "gen_pricing_node", "ppa_energy_cost", "ppa_penalty"]
    ]
    # drop where no penalty
    xl_gen_validated = xl_gen_validated[xl_gen_validated["ppa_penalty"] != 0]

    xl_gen_validated.to_csv(
        output_dir / "projects_with_overbuild_risk.csv", index=False
    )


def download_cambium_data(cambium_region_list, model_workspace):
    """
    Downloads cambium data from the 2021 Standard Scenarios
    """
    # specify the file ids for the five scenarios
    file_ids = [32096, 32098, 32103, 32110, 32104]
    regions_to_download = []
    for region in cambium_region_list:
        # if data has already been downloaded for this region, remove it from the region list
        if os.path.exists(f"{model_workspace}/../nrel_cambium_{region}"):
            pass
        else:
            regions_to_download.append(region)
    # if there are no regions in the region list, skip this, otherwise download the data
    if len(regions_to_download) > 0:

        print(
            f"Downloading Cambium data for the following GEA Regions: {regions_to_download}"
        )

        for file_id in file_ids:

            # specify the file information
            body = {
                "project_uuid": "a3e2f719-dd5a-4c3e-9bbf-f24fef563f45",
                "file_ids": f"{file_id}",
            }

            # download and save the data to a zip file
            with open(
                f"{model_workspace}/../cambium_download.zip", "wb"
            ) as output_file:
                output_file.write(
                    requests.post(
                        "https://scenarioviewer.nrel.gov/api/download/",
                        data=body,
                        stream=True,
                    ).content
                )

            # extract the files for each region, saving to a different directory
            with zipfile.ZipFile(
                f"{model_workspace}/../cambium_download.zip", "r"
            ) as z:
                for file in z.infolist():
                    for region in regions_to_download:
                        if region in file.filename:
                            file.filename = os.path.basename(file.filename)
                            z.extract(
                                file, f"{model_workspace}/../nrel_cambium_{region}"
                            )

            # delete the downloaded zip file
            os.remove(f"{model_workspace}/../cambium_download.zip")


def load_cambium_data(model_workspace, scenario, year, region):
    """
    loads a single year of cambium data for a single scneario and region
    """

    # specify the location of the directory where the NREL cambium data is downloaded
    cambium_dir = f"{model_workspace}/../nrel_cambium_{region}"

    # if the year is an even number, load the file corresponding to the year
    if year % 2 == 0:
        year_to_load = year
    else:
        year_to_load = year + 1

    cambium = pd.read_csv(
        f"{cambium_dir}/StdScen21_{scenario}_hourly_{region}_{year_to_load}.csv",
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


def calculate_levelized_lrmer(
    start_year, period, discount, emissions_unit, region_list, model_workspace
):
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
    levelized_lrmers = pd.DataFrame(
        columns=[
            "cambium_scenario",
            "cambium_region",
            "timepoint",
            "timestamp",
            "lrmer",
        ]
    )

    # for each scenario, load all years and calculate a levelized value
    for scenario in scenarios:

        for region in region_list:

            # create a blank dataframe to hold the lrmers for each year
            lrmer_scenario = pd.DataFrame()

            # start a variable to track the discounted number of years for the levelization
            denominator = 0

            for year in range(start_year, start_year + period + 1):

                # load the data and only keep the lrmer value
                lrmer = load_cambium_data(model_workspace, scenario, year, region)[
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

            # calculate the levelized lrmer for the region
            region_data = pd.DataFrame(
                columns=[
                    "cambium_scenario",
                    "cambium_region",
                    "timepoint",
                    "timestamp",
                    "lrmer",
                ],
                index=range(8760),
            )
            region_data["timepoint"] = region_data.index + 1
            region_data["cambium_scenario"] = scenario
            region_data["cambium_region"] = region
            region_data["lrmer"] = lrmer_scenario.sum(axis=1) / denominator

            # create a datetime index, skipping leap days
            dates = pd.date_range(
                start=f"01/01/{start_year} 00:00",
                end=f"12/31/{start_year} 23:00",
                freq="H",
                name="timestamp",
            )
            region_data["timestamp"] = pd.DatetimeIndex(
                data=(t for t in dates if ((t.month != 2) | (t.day != 29)))
            )

            # add the data to the dataframe
            levelized_lrmers = pd.concat([levelized_lrmers, region_data], axis=0)

    # convert the unit from kgCO2/MWh to the appropriate unit
    unit_conversion = {
        f"lb{ghg_unit}/MWh": 2.20462,
        f"kg{ghg_unit}/MWh": 1,
        f"mT{ghg_unit}/MWh": 0.001,
        f"ton{ghg_unit}/MWh": (2.20462 / 2000),
    }
    levelized_lrmers["lrmer"] = (
        levelized_lrmers["lrmer"] * unit_conversion[emissions_unit]
    )

    return levelized_lrmers


def generate_inputs(model_workspace):

    model_inputs = model_workspace / "model_inputs.xlsx"

    print("Setting up model directory...")
    # Load all of the data from the excel file

    xl_general = pd.read_excel(io=model_inputs, sheet_name="general").dropna(
        axis=1, how="all"
    )

    year = int(xl_general.loc[xl_general["Parameter"] == "Model Year", "Input"].item())
    timezone = xl_general.loc[xl_general["Parameter"] == "Timezone", "Input"].item()
    nrel_api_key = xl_general.loc[
        xl_general["Parameter"] == "NREL API key", "Input"
    ].item()
    nrel_api_email = xl_general.loc[
        xl_general["Parameter"] == "NREL API email", "Input"
    ].item()
    emissions_unit = xl_general.loc[
        xl_general["Parameter"] == "GHG Emissions Unit", "Input"
    ].item()
    td_losses = xl_general.loc[
        xl_general["Parameter"] == "Transmission & Distribution Losses", "Input"
    ].item()

    tz_offset = np.round(
        datetime(year=2020, month=1, day=1, tzinfo=pytz.timezone(timezone))
        .utcoffset()
        .total_seconds()
        / 3600
    )

    xl_options = pd.read_excel(io=model_inputs, sheet_name="solver_options").dropna(
        axis=1, how="all"
    )

    # write options.txt
    options_txt = open(model_workspace / "options.txt", "w+")
    for index, row in xl_options.iterrows():
        if row["Value"] == "None" or row["Value"] == False or row["Value"] == None:
            pass
        elif row["Value"] == True:
            options_txt.write(f'--{row["Option"]}\n')
        else:
            options_txt.write(f'--{row["Option"]} {row["Value"]}\n')
    options_txt.close()

    solver = xl_options.loc[xl_options["Option"] == "solver", "Value"].item().lower()
    if solver == "cbc":
        print("Copying CBC solver to model run directory...")
        # copy the cbc solver to the model workspace
        shutil.copy("../../cbc.exe", model_workspace)

    # create the scenario folders in the input and output directories
    try:
        os.mkdir(model_workspace / "inputs")
        os.mkdir(model_workspace / "outputs")
        os.mkdir(model_workspace / "summary_reports")
    except FileExistsError:
        pass

    # Scenarios
    xl_scenarios = pd.read_excel(
        io=model_inputs, sheet_name="scenarios", skiprows=1
    ).dropna(axis=1, how="all")

    # if there are any spaces in the scenario names, replace with underscore
    xl_scenarios.columns = xl_scenarios.columns.str.replace(" ", "_")

    scenario_list = list(xl_scenarios.iloc[:, 3:].columns)

    # determine if there are any modules that are not used by any scenarios
    modules_used = (
        xl_scenarios[xl_scenarios["Input_Type"] == "Optional Modules"]
        .drop(columns=["Input_Type", "Description"])
        .set_index("Parameter")
        .sum(axis=1)
    )
    unused_modules = list(modules_used[modules_used == 0].index)

    # create input and output directories for each scenario
    for scenario in scenario_list:
        try:
            os.mkdir(model_workspace / f"inputs/{scenario}")
        except FileExistsError:
            pass
        try:
            os.mkdir(model_workspace / f"outputs/{scenario}")
        except FileExistsError:
            pass

    # create scenarios.txt
    # write scenario configuration to scenarios.txt
    scenarios = open(model_workspace / "scenarios.txt", "a+")
    for scenario in scenario_list:
        # get configuration options
        option_list = list(
            xl_scenarios.loc[
                (xl_scenarios["Input_Type"] == "Options")
                & (xl_scenarios[scenario] != 0),
                "Parameter",
            ]
        )
        renewable_target_type = xl_scenarios.loc[
            (xl_scenarios["Parameter"] == "goal_type"), scenario
        ].item()
        select_variants = xl_scenarios.loc[
            (xl_scenarios["Parameter"] == "select_variants"), scenario
        ].item()
        excess_generation_limit_type = xl_scenarios.loc[
            (xl_scenarios["Parameter"] == "excess_generation_limit_type"), scenario
        ].item()

        if select_variants != 0:
            variant_option = f" --select_variants {select_variants}"
        else:
            variant_option = ""

        if renewable_target_type == "annual":
            target_option = " --goal_type annual"
        else:
            target_option = ""

        if excess_generation_limit_type not in ["None", "."]:
            excess_option = (
                f" --excess_generation_limit_type {excess_generation_limit_type}"
            )
        else:
            excess_option = ""

        if "sell_excess_RA" in option_list:
            ra_option = " --sell_excess_RA sell"
        else:
            ra_option = ""

        if "sell_excess_RECs" in option_list:
            rec_option = " --sell_excess_RECs sell"
        else:
            rec_option = ""

        if "include_RA_MTR_requirement" in option_list:
            mtr_option = " --include_RA_MTR_requirement True"
        else:
            mtr_option = ""

        if "storage_binary_dispatch_constraint" in option_list:
            storage_option = " --storage_binary_dispatch_constraint True"
        else:
            storage_option = ""

        scenarios.write(
            f"--scenario-name {scenario} --outputs-dir outputs/{scenario} --inputs-dir inputs/{scenario}{variant_option}{target_option}{excess_option}{ra_option}{mtr_option}{rec_option}{storage_option}"
        )
        scenarios.write("\n")
    scenarios.close()

    print("Loading data from model_inputs.xlsx")

    # periods.csv
    df_periods = pd.DataFrame(
        columns=["INVESTMENT_PERIOD", "period_start", "period_end"],
        data=[[year, year, year]],
    )

    # timeseries.csv
    df_timeseries = pd.DataFrame(
        data={
            "TIMESERIES": [f"{year}_timeseries"],
            "ts_period": [year],
            "ts_duration_of_tp": [1],  # duration (hour) of each timepoint
            "ts_num_tps": [8760],  # number of timepoints in the timeseries
            "ts_scale_to_period": [1],
        }  # number of timeseries in period
    )

    # financials
    df_financials = pd.DataFrame(
        data={
            "base_financial_year": [
                int(
                    xl_general.loc[
                        xl_general["Parameter"] == "Base Year", "Input"
                    ].item()
                )
            ],
            "dollar_year": [
                int(
                    xl_general.loc[
                        xl_general["Parameter"] == "Financial Year", "Input"
                    ].item()
                )
            ],
            "discount_rate": [
                xl_general.loc[
                    xl_general["Parameter"] == "Discount Rate", "Input"
                ].item()
            ],
        }
    )

    # Read data from the excel file

    xl_gen = pd.read_excel(io=model_inputs, sheet_name="generators", skiprows=3).dropna(
        axis=1, how="all"
    )
    if xl_gen.isnull().values.any():
        raise ValueError("The generation tab contains a missing value. Please fix")
    # add default values
    xl_gen["gen_is_storage"] = 0
    # ensure that baseload_gen_scheduled_outage_rate is '.' for non baseload gens
    xl_gen.loc[
        xl_gen["gen_is_baseload"] == 0, "baseload_gen_scheduled_outage_rate"
    ] = "."

    # calculate the solar degredation discount for the model year, assuming a 0.5% annual degredation rate
    xl_gen["solar_age_degredation"] = 1
    xl_gen.loc[xl_gen["gen_tech"] == "Solar_PV", "solar_age_degredation"] = (
        1 - 0.005
    ) ** (year - xl_gen.loc[xl_gen["gen_tech"] == "Solar_PV", "cod_year"])

    if "match_model.optional.storage" in unused_modules:
        pass
    else:
        xl_storage = pd.read_excel(
            io=model_inputs, sheet_name="storage", skiprows=3
        ).dropna(axis=1, how="all")
        if xl_storage.isnull().values.any():
            raise ValueError("The storage tab contains a missing value. Please fix")
        # add defaults for storage
        xl_storage["gen_tech"] = "Storage"
        xl_storage["gen_is_storage"] = 1
        xl_storage["gen_is_variable"] = 0
        xl_storage["gen_is_baseload"] = 0
        xl_storage["solar_age_degredation"] = "."

        # validate that variants are not specified for hybrid storage
        for g in list(xl_storage["GENERATION_PROJECT"].unique()):
            # if the generator is a hybrid and a variant group is specified, raise an error
            if (
                xl_storage.loc[
                    xl_storage["GENERATION_PROJECT"] == g, "gen_is_hybrid"
                ].item()
                == 1
            ):
                if (
                    xl_storage.loc[
                        xl_storage["GENERATION_PROJECT"] == g, "gen_variant_group"
                    ].item()
                    != "."
                ):
                    raise ValueError(
                        f"Variants cannot be specified for the storage portion of a hybrid project ({g}). Instead specify different variants for the generator portion of the project, each of which has a unique hybrid storage project linked to it."
                    )

        # concat xl_gen and xl_storage, and fill missing values with '.'
        xl_gen = pd.concat([xl_gen, xl_storage], sort=False, ignore_index=True).fillna(
            "."
        )

    xl_load = pd.read_excel(
        io=model_inputs, sheet_name="load", header=[1, 2], index_col=0
    ).dropna(axis=1, how="all")
    if xl_load.isnull().values.any():
        raise ValueError("Nodal prices contain a missing value. Please check")

    if "match_model.optional.resource_adequacy" in unused_modules:
        pass
    else:
        # ra_requirement.csv
        xl_ra_req = pd.read_excel(
            io=model_inputs, sheet_name="RA_requirements", skiprows=1
        ).dropna(axis=1, how="all")
        ra_requirement = xl_ra_req.copy()[xl_ra_req["RA_RESOURCE"] != "flexible_RA"]
        ra_requirement["period"] = year
        ra_requirement = ra_requirement[
            ["period", "month", "ra_requirement", "ra_cost", "ra_resell_value"]
        ]

        # flexible_ra_requirement.csv
        flexible_ra_requirement = xl_ra_req.copy()[
            xl_ra_req["RA_RESOURCE"] == "flexible_RA"
        ]
        flexible_ra_requirement["period"] = year
        flexible_ra_requirement = flexible_ra_requirement.drop(columns=["RA_RESOURCE"])
        flexible_ra_requirement = flexible_ra_requirement.rename(
            columns={
                "ra_requirement": "flexible_ra_requirement",
                "ra_cost": "flexible_ra_cost",
                "ra_resell_value": "flexible_ra_resell_value",
            }
        )
        flexible_ra_requirement = flexible_ra_requirement[
            [
                "period",
                "month",
                "flexible_ra_requirement",
                "flexible_ra_cost",
                "flexible_ra_resell_value",
            ]
        ]

        # ra_capacity_value.csv
        ra_capacity_value = pd.read_excel(
            io=model_inputs, sheet_name="RA_capacity_value"
        ).dropna(axis=1, how="all")
        ra_capacity_value["period"] = year
        ra_capacity_value = ra_capacity_value[
            ["period", "gen_energy_source", "month", "elcc", "ra_production_factor"]
        ]

        # midterm_reliability_requirement.csv
        xl_midterm_ra = pd.read_excel(
            io=model_inputs, sheet_name="midterm_RA_requirement", skiprows=1
        ).dropna(axis=1, how="all")

    xl_nodal_prices = pd.read_excel(
        io=model_inputs, sheet_name="nodal_prices", index_col="Datetime", skiprows=2
    ).dropna(axis=1, how="all")
    if xl_nodal_prices.isnull().values.any():
        raise ValueError("Nodal prices contain a missing value. Please check")
    # check that a nodal price exists for each node specified with an MCF in the generation tab
    nodes_to_check = list(xl_gen["gen_pricing_node"].unique())
    for node in nodes_to_check:
        if node not in list(xl_nodal_prices.columns):
            raise ValueError(
                f"The nodal price timeseries for {node} is missing. Please add."
            )
        else:
            pass

    xl_cambium_region = pd.read_excel(
        io=model_inputs, sheet_name="cambium_region"
    ).dropna(axis=1, how="all")

    # get a list of unique cambium regions
    cambium_region_list = list(xl_gen["gen_cambium_region"].unique())

    # download the cambium data if needed
    download_cambium_data(cambium_region_list, model_workspace)

    # calculate marginal emissions factors - these will be used in the summary report no matter what, and potentially in the emissions optimization module
    # calculate for all regions and scenarios
    lrmer_data = calculate_levelized_lrmer(
        year, 20, 0, emissions_unit, cambium_region_list, model_workspace
    )

    xl_hedge_premium_cost = pd.read_excel(
        io=model_inputs, sheet_name="hedge_premium_cost", skiprows=2
    ).dropna(axis=1, how="all")

    # rec_value.csv
    xl_rec_value = pd.read_excel(
        io=model_inputs, sheet_name="rec_value", skiprows=1
    ).dropna(axis=1, how="all")

    # fixed_costs.csv
    xl_fixed_costs = pd.read_excel(
        io=model_inputs, sheet_name="fixed_costs", skiprows=1
    )

    # create a dataframe that contains the unique combinations of resource years and generator sets, and the scenarios associated with each
    vcf_sets = (
        xl_scenarios[
            xl_scenarios["Input_Type"].isin(["Resource year(s)", "Generator Set"])
        ]
        .drop(columns=["Input_Type", "Parameter", "Description"])
        .transpose()
        .reset_index()
    )
    vcf_sets.columns = ["scenario", "years", "gen_set"]
    vcf_sets = (
        vcf_sets.groupby(["years", "gen_set"])["scenario"].apply(list).reset_index()
    )

    # for each of these unique combinations, get the variable capacity factor data
    for index, row in vcf_sets.iterrows():
        gen_set = row["gen_set"]
        resource_years = ast.literal_eval(row["years"])
        set_scenario_list = row["scenario"]

        print(f"Generating capacity factor timeseries for {gen_set}")

        # get the gen set data
        # subset the generation data for the set of generators that are part of the active set
        set_gens = xl_gen[xl_gen[gen_set] == 1]
        set_gen_list = list(set_gens["GENERATION_PROJECT"])

        # variable_capacity_factors.csv
        vcf_inputs = set_gens[
            [
                "GENERATION_PROJECT",
                "capacity_factor_input",
                "SAM_template",
                "latitude",
                "longitude",
            ]
        ]

        vcf_input_types = list(vcf_inputs.capacity_factor_input.unique())

        # create a blank dataframe with a datetimeindex for variable capacity factors
        df_vcf = pd.DataFrame(data=range(1, 8761), columns=["timepoint"]).set_index(
            "timepoint"
        )

        if "manual" in vcf_input_types:
            manual_vcf = (
                pd.read_excel(
                    io=model_inputs,
                    sheet_name="manual_capacity_factors",
                    index_col="Datetime",
                    skiprows=2,
                )
                .dropna(axis=1, how="all")
                .reset_index(drop=True)
            )
            if manual_vcf.isnull().values.any():
                raise ValueError(
                    "The manual_capacity_factor tab contains a missing value. Please fix"
                )
            # check that a capacity factor exists for each generator specified with an MCF in the generation tab
            manual_gens = list(
                set_gens.loc[
                    set_gens["capacity_factor_input"] == "manual", "GENERATION_PROJECT"
                ]
            )
            for gen in manual_gens:
                if gen not in list(manual_vcf.columns):
                    raise ValueError(
                        f"The manual capacity factor timeseries for {gen} is missing. Please add."
                    )
                else:
                    pass
            # only keep columns for the current scenario
            manual_vcf = manual_vcf.loc[:, manual_vcf.columns.isin(set_gen_list)]
            manual_vcf["timepoint"] = manual_vcf.index + 1
            manual_vcf = manual_vcf.set_index("timepoint")

            # merge manual vcf into df
            df_vcf = df_vcf.merge(
                manual_vcf, how="left", left_index=True, right_index=True
            )

        if "SAM" in vcf_input_types:
            # get SAM template data
            sam_templates = pd.read_excel(
                io=model_inputs, sheet_name="SAM_templates"
            ).dropna(axis=1, how="all")

            # get the information for the relevant generators
            sam_inputs = vcf_inputs[vcf_inputs["capacity_factor_input"] == "SAM"]

            # get list of templates
            template_list = list(sam_inputs.SAM_template.unique())

            # check that templates match
            available_templates = list(sam_templates.Template_Name.unique())
            for template in template_list:
                if template not in available_templates:
                    raise ValueError(f"SAM template for {template} not specified")

            # For each template, get the list of generators and simulate
            for template in template_list:
                # get the list of generators that use the current template
                gen_inputs = vcf_inputs.copy()[vcf_inputs["SAM_template"] == template]

                # get lat/long coordinates of all resources using this template
                gen_inputs["long/lat"] = gen_inputs.apply(
                    lambda row: f"({row.longitude},{row.latitude})", axis=1
                )
                gen_inputs["long/lat"] = gen_inputs["long/lat"].apply(ast.literal_eval)
                resource_dict = defaultdict(list)
                zipped_list = zip(
                    gen_inputs["long/lat"], gen_inputs["GENERATION_PROJECT"]
                )
                for key, value in zipped_list:
                    resource_dict[key].append(value)

                # get the parameter info for this template
                resource_template = sam_templates[
                    sam_templates["Template_Name"] == template
                ]

                # create a dictionary for the parameter values
                config_dict = {}
                for group in resource_template["Group"].unique():
                    # create a dict of parameters for this group
                    parameters = resource_template.loc[
                        resource_template["Group"] == group, ["Parameter", "Value"]
                    ]
                    parameter_dict = {}
                    for index, row in parameters.iterrows():
                        try:
                            parameter_dict[row.Parameter] = ast.literal_eval(row.Value)
                        except ValueError:
                            parameter_dict[row.Parameter] = row.Value
                    # dict(zip(parameters.Parameter, ast.literal_eval(parameters.Value)))

                    config_dict[group] = parameter_dict

                # get the name of the PySAM function
                sam_function = resource_template.iloc[0, 0]

                pysam_dir = model_workspace / gen_set

                if sam_function == "Pvwattsv8":
                    # run PySAM to simulate the solar outputs
                    solar_vcf = simulate_solar_generation(
                        nrel_api_key,
                        nrel_api_email,
                        resource_dict,
                        config_dict,
                        resource_years,
                        pysam_dir,
                        tz_offset,
                    )

                    # add the data to the dataframe
                    df_vcf = df_vcf.merge(
                        solar_vcf, how="left", left_index=True, right_index=True
                    )

                elif sam_function == "csp_tower":
                    # run PySAM to simulate the solar outputs
                    csp_vcf = simulate_csp_generation(
                        nrel_api_key,
                        nrel_api_email,
                        resource_dict,
                        config_dict,
                        resource_years,
                        pysam_dir,
                        tz_offset,
                    )

                    # add the data to the dataframe
                    df_vcf = df_vcf.merge(
                        csp_vcf, how="left", left_index=True, right_index=True
                    )

                elif sam_function == "windpower":
                    # run PySAM to simulate the solar outputs
                    wind_vcf = simulate_wind_generation(
                        nrel_api_key,
                        nrel_api_email,
                        resource_dict,
                        config_dict,
                        resource_years,
                        pysam_dir,
                        tz_offset,
                    )

                    # add the data to the dataframe
                    df_vcf = df_vcf.merge(
                        wind_vcf, how="left", left_index=True, right_index=True
                    )
                else:

                    class UnrecognizedSAMModule(Exception):
                        pass

                    raise UnrecognizedSAMModule(
                        f" The {sam_function} SAM module is not configured to work with MATCH. Must be either 'windpower' or 'Pvwattsv8'"
                    )

            for vcf_year in resource_years:
                if os.path.exists(
                    model_workspace
                    / gen_set
                    / f"{vcf_year}_variable_capacity_factors.csv"
                ):
                    pass
                else:
                    # split the data for the single resource year into a new df
                    df_vcf_year = df_vcf.copy()[
                        [col for col in df_vcf.columns if str(vcf_year) in col]
                    ]

                    # remove year from column name
                    df_vcf_year.columns = [i.split("~")[0] for i in df_vcf_year.columns]

                    # export the data to a csv in the set folder
                    df_vcf_year.to_csv(
                        model_workspace
                        / gen_set
                        / f"{vcf_year}_variable_capacity_factors.csv"
                    )

        # remove year from column name
        df_vcf.columns = [i.split("~")[0] for i in df_vcf.columns]

        # average all of the resource years together for each resource
        df_vcf = df_vcf.groupby(df_vcf.columns, axis=1).mean()

        # replace all negative capacity factors with 0
        df_vcf[df_vcf < 0] = 0

        df_vcf = df_vcf.reset_index()

        # validate cost inputs
        try:
            validate_cost_inputs(set_gens, df_vcf, xl_nodal_prices, pysam_dir)
        except UnboundLocalError:
            validate_cost_inputs(set_gens, df_vcf, xl_nodal_prices, model_workspace)

        # filter the marginal emissions data to match the current gen set
        set_cambium_region_list = list(set_gens["gen_cambium_region"].unique())
        lrmer_for_gen_set = lrmer_data.loc[
            lrmer_data["cambium_region"].isin(set_cambium_region_list), :
        ]

        # iterate for each scenario and save outputs to csv files
        for scenario in set_scenario_list:

            print(f"Writing inputs for {scenario} scenario...")

            input_dir = model_workspace / f"inputs/{scenario}"
            output_dir = model_workspace / f"outputs/{scenario}"

            # modules.txt
            required_module_list = [
                "match_model",
                "match_model.timescales",
                "match_model.financials",
                "match_model.balancing.load_zones",
                "match_model.generators.build",
                "match_model.generators.dispatch",
            ]
            module_list = list(
                xl_scenarios.loc[
                    (xl_scenarios["Input_Type"] == "Optional Modules")
                    & (xl_scenarios[scenario] == 1),
                    "Parameter",
                ]
            )
            if "match_model.optional.wholesale_pricing" in module_list:
                module_list.remove("match_model.optional.wholesale_pricing")
                required_module_list.append("match_model.optional.wholesale_pricing")
            if "match_model.optional.storage" in module_list:
                module_list.remove("match_model.optional.storage")
                required_module_list.append("match_model.optional.storage")
            module_list = (
                required_module_list
                + [
                    "match_model.balancing.system_power",
                    "match_model.balancing.renewable_target",
                    "match_model.balancing.excess_generation",
                ]
                + module_list
                + ["match_model.reporting.generate_report"]
            )
            modules = open(input_dir / "modules.txt", "w+")
            for module in module_list:
                modules.write(module)
                modules.write("\n")
            modules.close()

            # renewable_target.csv
            renewable_target_value = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "renewable_target"), scenario
            ].item()
            renewable_target_type = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "goal_type"), scenario
            ].item()
            select_variants = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "select_variants"), scenario
            ].item()
            renewable_target = pd.DataFrame(
                data={"period": [year], "renewable_target": [renewable_target_value]}
            )
            renewable_target.to_csv(input_dir / "renewable_target.csv", index=False)

            # excessgen_penalty.csv
            excessgen_penalty = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "excessgen_penalty"), scenario
            ].item()
            excess_generation_limit = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "excess_generation_limit"), scenario
            ].item()
            excess_generation_limit_type = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "excess_generation_limit_type"), scenario
            ].item()
            excessgen_penalty = pd.DataFrame(
                data={
                    "period": [year],
                    "excess_generation_limit": [excess_generation_limit],
                    "excessgen_penalty": [excessgen_penalty],
                }
            )
            excessgen_penalty.to_csv(input_dir / "excessgen_limits.csv", index=False)

            # save lrmer data for summary reports
            lrmer_for_gen_set.to_csv(input_dir / "lrmer_for_summary.csv", index=False)

            # load scenario name to use
            cambium_scenario = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "cambium_scenario"), scenario
            ].item()
            # write the name of the cambium scenario to a text file
            cambium_scenario_file = open(input_dir / "cambium_scenario.txt", "w+")
            cambium_scenario_file.write(cambium_scenario)
            cambium_scenario_file.close()

            # if emissions optimization module in use, generate inputs for module
            if "match_model.optional.emissions_optimization" in module_list:
                # social cost of carbon
                internal_carbon_price = xl_scenarios.loc[
                    (xl_scenarios["Parameter"] == "internal_carbon_price"), scenario
                ].item()
                internal_carbon_price = pd.DataFrame(
                    data={
                        "period": [year],
                        "internal_carbon_price": [internal_carbon_price],
                    }
                )
                internal_carbon_price.to_csv(
                    input_dir / "internal_carbon_price.csv", index=False
                )

                # filter the lrmer data for the module
                lrmer = lrmer_for_gen_set.loc[
                    lrmer_for_gen_set["cambium_scenario"] == cambium_scenario,
                    ["cambium_region", "timepoint", "lrmer"],
                ]
                lrmer.to_csv(input_dir / "lrmer.csv", index=False)

                cambium_regions = pd.DataFrame(
                    data={"CAMBIUM_REGIONS": set_cambium_region_list}
                )
                cambium_regions.to_csv(input_dir / "cambium_regions.csv", index=False)

            # summary_report.ipynb
            shutil.copy("../reporting/summary_report.ipynb", input_dir)

            # generator set name
            set_name = open(input_dir / "gen_set.txt", "w+")
            set_name.write(gen_set)
            set_name.close()

            df_periods.to_csv(input_dir / "periods.csv", index=False)
            df_timeseries.to_csv(input_dir / "timeseries.csv", index=False)

            # get configuration options
            option_list = list(
                xl_scenarios.loc[
                    (xl_scenarios["Input_Type"] == "Options")
                    & (xl_scenarios[scenario] != 0),
                    "Parameter",
                ]
            )

            # timepoints.csv
            df_timepoints = pd.DataFrame(
                index=pd.date_range(
                    start=f"01/01/{year} 00:00", end=f"12/31/{year} 23:00", freq="1H"
                )
            )
            df_timepoints = df_timepoints[
                ~((df_timepoints.index.month == 2) & (df_timepoints.index.day == 29))
            ]  # remove leap day if a leap year
            df_timepoints["timeseries"] = f"{year}_timeseries"
            df_timepoints["timestamp"] = df_timepoints.index.strftime("%m/%d/%Y %H:%M")
            df_timepoints["tp_month"] = df_timepoints.index.month
            df_timepoints["tp_day"] = df_timepoints.index.dayofyear
            df_timepoints = df_timepoints.reset_index(drop=True)
            df_timepoints["timepoint_id"] = df_timepoints.index + 1
            df_timepoints.to_csv(input_dir / "timepoints.csv", index=False)

            df_financials.to_csv(input_dir / "financials.csv", index=False)

            # rec_value.csv
            xl_rec_value.to_csv(input_dir / "rec_value.csv", index=False)

            # emission unit.txt
            ghg_emissions_unit = open(input_dir / "ghg_emissions_unit.txt", "w+")
            ghg_emissions_unit.write(emissions_unit)
            ghg_emissions_unit.close()

            # td_losses.txt
            td_loss = open(input_dir / "td_losses.txt", "w+")
            td_loss.write(str(td_losses))
            td_loss.close()

            # fixed_costs.csv
            xl_fixed_costs.to_csv(input_dir / "fixed_costs.csv", index=False)

            # gen_build_years.csv
            gen_build_years = set_gens.copy()[["GENERATION_PROJECT"]]
            gen_build_years["build_year"] = year
            gen_build_years.to_csv(input_dir / "gen_build_years.csv", index=False)

            # gen_build_predetermined.csv
            gen_build_predetermined = set_gens[
                ["GENERATION_PROJECT", "gen_predetermined_cap"]
            ]
            gen_build_predetermined = gen_build_predetermined[
                (gen_build_predetermined["gen_predetermined_cap"] != ".")
            ]
            gen_build_predetermined = gen_build_predetermined[
                (gen_build_predetermined["gen_predetermined_cap"] > 0)
            ]
            gen_build_predetermined["build_year"] = year
            if "ignores_existing_contracts" in option_list:
                gen_build_predetermined = gen_build_predetermined[0:0]
            gen_build_predetermined = gen_build_predetermined[
                ["GENERATION_PROJECT", "build_year", "gen_predetermined_cap"]
            ]
            gen_build_predetermined.to_csv(
                input_dir / "gen_build_predetermined.csv", index=False
            )

            # generation_projects_info.csv
            gpi_columns = [
                "GENERATION_PROJECT",
                "gen_load_zone",
                "gen_tech",
                "gen_emission_factor",
                "gen_cambium_region",
                "gen_is_additional",
                "gen_is_variable",
                "gen_is_hybrid",
                "gen_is_storage",
                "gen_is_baseload",
                "gen_variant_group",
                "gen_capacity_limit_mw",
                "gen_min_build_capacity",
                "cod_year",
                "ppa_energy_cost",
                "ppa_capacity_cost",
                "gen_pricing_node",
                "gen_is_ra_eligible",
                "gen_energy_source",
                "storage_roundtrip_efficiency",
                "storage_charge_to_discharge_ratio",
                "storage_energy_to_power_ratio",
                "storage_max_annual_cycles",
                "storage_leakage_loss",
                "storage_hybrid_generation_project",
                "storage_hybrid_min_capacity_ratio",
                "storage_hybrid_max_capacity_ratio",
                "solar_age_degredation",
                "baseload_gen_scheduled_outage_rate",
                "gen_forced_outage_rate",
                "buyer_curtailment_allowance",
            ]

            generation_projects_info = set_gens[
                [col for col in set_gens.columns if col in gpi_columns]
            ]

            if "is_price_agnostic" in option_list:
                generation_projects_info["ppa_energy_cost"] = 10

            if "ignores_capacity_limit" in option_list:
                generation_projects_info["gen_capacity_limit_mw"] = "."

            if "select_variants" not in option_list:
                generation_projects_info = generation_projects_info.drop(
                    columns=["gen_variant_group"]
                )

            generation_projects_info.to_csv(
                input_dir / "generation_projects_info.csv", index=False
            )

            # energy_sources.csv
            energy_sources = (
                set_gens[["gen_energy_source"]]
                .drop_duplicates(ignore_index=True)
                .rename(columns={"gen_energy_source": "energy_source"})
            )
            energy_sources.to_csv(input_dir / "energy_sources.csv", index=False)

            # LOAD DATA #

            # load_zones.csv
            load_list = list(set_gens.gen_load_zone.unique())
            load_zones = pd.DataFrame(data={"LOAD_ZONE": load_list})
            load_zones.to_csv(input_dir / "load_zones.csv", index=False)

            # get the load type that should be used
            load_scenario = xl_scenarios.loc[
                (xl_scenarios["Parameter"] == "load_scenario"), scenario
            ].item()

            loads = xl_load.iloc[
                :, xl_load.columns.get_level_values(0) == load_scenario
            ]
            loads.columns = loads.columns.droplevel()

            loads = loads.reset_index(drop=True)
            loads["timepoint"] = loads.index + 1
            loads = loads.melt(
                id_vars=["timepoint"], var_name="load_zone", value_name="zone_demand_mw"
            )
            loads = loads[["load_zone", "timepoint", "zone_demand_mw"]]
            loads.to_csv(input_dir / "loads.csv", index=False)

            # get the name of the load zone
            load_zone_name = load_list[0]

            # save the name of the cambium region
            cambium_region = xl_cambium_region.loc[
                xl_cambium_region["load_zone"] == load_zone_name, "GEA_region"
            ].item()

            # cambium_region.txt
            cambium_region_file = open(input_dir / "cambium_region.txt", "w+")
            cambium_region_file.write(cambium_region)
            cambium_region_file.close()

            # RA data
            if "match_model.optional.resource_adequacy" in module_list:

                ra_requirement.to_csv(input_dir / "ra_requirement.csv", index=False)
                flexible_ra_requirement.to_csv(
                    input_dir / "flexible_ra_requirement.csv", index=False
                )
                energy_source_list = list(
                    generation_projects_info["gen_energy_source"].unique()
                )
                ra_capacity_value_scenario = ra_capacity_value[
                    ra_capacity_value["gen_energy_source"].isin(energy_source_list)
                ]
                ra_capacity_value_scenario.to_csv(
                    input_dir / "ra_capacity_value.csv", index=False
                )

                # midterm_reliability_requirement.csv
                xl_midterm_ra.to_csv(
                    input_dir / "midterm_reliability_requirement.csv", index=False
                )

            # pricing_nodes.csv
            node_list = list(set_gens.gen_pricing_node.unique())
            node_list = node_list + load_list
            node_list = [i for i in node_list if i not in [".", np.nan]]
            node_list = list(set(node_list))  # only keep unique values
            pricing_nodes = pd.DataFrame(data={"PRICING_NODE": node_list})
            pricing_nodes.to_csv(input_dir / "pricing_nodes.csv", index=False)

            # nodal_prices.csv
            nodal_prices = xl_nodal_prices.reset_index(drop=True)
            nodal_prices = nodal_prices.astype(float)
            nodal_prices = nodal_prices[node_list]
            nodal_prices["timepoint"] = nodal_prices.index + 1
            nodal_prices = nodal_prices.melt(
                id_vars=["timepoint"], var_name="pricing_node", value_name="nodal_price"
            )
            nodal_prices = nodal_prices[["pricing_node", "timepoint", "nodal_price"]]
            # round all nodal prices to the nearest whole cent
            nodal_prices["nodal_price"] = nodal_prices["nodal_price"].round(2)
            # add system power / demand node prices to df
            nodal_prices.to_csv(input_dir / "nodal_prices.csv", index=False)

            # hedge_cost.csv
            if not xl_hedge_premium_cost.empty:
                # create a list to hold the data
                hedge_cost = []
                # for each load zone, calculate a month-hour average hedge cost and add it to the list
                for zone in list(xl_hedge_premium_cost["load_zone"].unique()):
                    hedge_node = xl_hedge_premium_cost.loc[
                        xl_hedge_premium_cost["load_zone"] == zone, "hedge_node"
                    ].item()
                    hedge_percent = xl_hedge_premium_cost.loc[
                        xl_hedge_premium_cost["load_zone"] == zone,
                        "hedge_premium_percent",
                    ].item()

                    # get the hedge node data
                    nodal_data = xl_nodal_prices.copy()[[hedge_node]]
                    nodal_data.index = pd.to_datetime(nodal_data.index)
                    nodal_data.loc[:, "month"] = nodal_data.index.month
                    nodal_data.loc[:, "hour"] = nodal_data.index.hour

                    # calculate the month-hour average
                    nodal_data_mh = (
                        nodal_data.groupby(["month", "hour"]).mean().reset_index()
                    )

                    # multiply the average by the premium percent
                    nodal_data_mh[hedge_node] = (
                        nodal_data_mh[hedge_node] * hedge_percent
                    )

                    # set a floor of 0.01 if prices are ever negative
                    nodal_data_mh.loc[nodal_data_mh[hedge_node] < 0, hedge_node] = 0.01

                    # drop the original 8760 data and merge in the month-hour average data
                    nodal_data_mh = nodal_data_mh.rename(columns={hedge_node: zone})
                    nodal_data = nodal_data.merge(
                        nodal_data_mh, how="left", on=["month", "hour"]
                    )

                    hedge_cost.append(nodal_data[[zone]])

                # concat all zone data together
                hedge_cost = pd.concat(hedge_cost, axis=1)
                # add a timepoint column
                hedge_cost.loc[:, "timepoint"] = hedge_cost.index + 1
                # pivot the data to long form
                hedge_cost = hedge_cost.melt(
                    id_vars="timepoint",
                    var_name="load_zone",
                    value_name="hedge_premium_cost",
                )
                # change the column order
                hedge_cost = hedge_cost[
                    ["load_zone", "timepoint", "hedge_premium_cost"]
                ]
                # round to the nearest cent
                hedge_cost["hedge_premium_cost"] = round(
                    hedge_cost["hedge_premium_cost"], 2
                )
            else:
                hedge_cost = pd.DataFrame(
                    columns=["load_zone", "timepoint", "hedge_premium_cost"]
                )

            hedge_cost.to_csv(input_dir / "hedge_premium_cost.csv", index=False)

            # round all prices to the nearest whole cent
            try:
                hedge_cost["hedge_premium_cost"] = hedge_cost[
                    "hedge_premium_cost"
                ].round(2)
            except TypeError:
                pass
            # only keep data for the relevant load zones
            hedge_cost = hedge_cost[hedge_cost["load_zone"].isin(load_list)]
            hedge_cost.to_csv(input_dir / "hedge_premium_cost.csv", index=False)

            # variable_capacity_factors.csv
            df_vcf_scenario = df_vcf.copy()

            # melt the data and save as csv
            df_vcf_scenario = df_vcf_scenario.melt(
                id_vars="timepoint",
                var_name="GENERATION_PROJECT",
                value_name="variable_capacity_factor",
            )

            # reorder the columns
            df_vcf_scenario = df_vcf_scenario[
                ["GENERATION_PROJECT", "timepoint", "variable_capacity_factor"]
            ]

            # split any baseload generators into a separate capacity factor dataframe
            df_bcf_scenario = df_vcf_scenario.copy()
            # get a list of all baseload generation projects
            baseload_list = generation_projects_info.loc[
                generation_projects_info["gen_is_baseload"] == 1, "GENERATION_PROJECT"
            ].tolist()
            # keep baseload generators
            df_bcf_scenario = df_bcf_scenario[
                df_bcf_scenario["GENERATION_PROJECT"].isin(baseload_list)
            ]
            # change param name
            df_bcf_scenario = df_bcf_scenario.rename(
                columns={"variable_capacity_factor": "baseload_capacity_factor"}
            )
            # drop baseload generators from vcf dataframe
            df_vcf_scenario = df_vcf_scenario[
                ~df_vcf_scenario["GENERATION_PROJECT"].isin(baseload_list)
            ]

            # add a curtailment capacity factor
            # merge in the pricing node
            df_vcf_scenario = df_vcf_scenario.merge(
                generation_projects_info[["GENERATION_PROJECT", "gen_pricing_node"]],
                how="left",
                on="GENERATION_PROJECT",
                validate="m:1",
            ).rename(columns={"gen_pricing_node": "pricing_node"})
            # merge in the price
            df_vcf_scenario = df_vcf_scenario.merge(
                nodal_prices,
                how="left",
                on=["pricing_node", "timepoint"],
                validate="m:1",
            )
            # create a binary variable if the price is negative or zero
            df_vcf_scenario = df_vcf_scenario.assign(
                negative_price=lambda x: np.where((x.nodal_price <= 0), 1, 0)
            )
            # create the curtailment capacity factor colunn
            df_vcf_scenario["curtailment_capacity_factor"] = (
                df_vcf_scenario["variable_capacity_factor"]
                * df_vcf_scenario["negative_price"]
            )
            # ensure the capacity factor is greater than zero
            df_vcf_scenario.loc[
                df_vcf_scenario["curtailment_capacity_factor"] < 0,
                "curtailment_capacity_factor",
            ] = 0
            # remove intermediate columns
            df_vcf_scenario = df_vcf_scenario.drop(
                columns=["pricing_node", "nodal_price", "negative_price"]
            )

            # save data to csv
            df_vcf_scenario.to_csv(
                input_dir / "variable_capacity_factors.csv", index=False
            )
            df_bcf_scenario.to_csv(
                input_dir / "baseload_capacity_factors.csv", index=False
            )

    # write the inputs version once all inputs have been successfully generated
    # Get the version number. Strategy #3 from https://packaging.python.org/single_source_version/
    version_path = os.path.join(os.path.dirname(__file__), "version.py")
    version = {}
    with open(version_path) as f:
        exec(f.read(), version)
    version = version["__version__"]

    # inputs_version.txt
    inputs_version = open(model_workspace / "inputs_version.txt", "w+")
    inputs_version.write(version)
    inputs_version.close()


def simulate_solar_generation(
    nrel_api_key,
    nrel_api_email,
    resource_dict,
    config_dict,
    resource_years,
    input_dir,
    tz_offset,
):

    # initiate the default PV setup
    system_model_PV = pv.default("PVWattsNone")

    # specify non-default system design factors
    systemDesign = config_dict["SystemDesign"]

    # assign the non-default system design specs to the model
    system_model_PV.SystemDesign.assign(systemDesign)

    lon_lats = list(resource_dict.keys())

    # this is the df that will hold all of the data for all years
    df_resource = pd.DataFrame(data=range(1, 8761), columns=["timepoint"]).set_index(
        "timepoint"
    )
    df_index = df_resource.index

    for year in resource_years:

        # download resource files
        # https://github.com/NREL/pysam/blob/master/Examples/FetchResourceFileExample.py
        # https://nrel-pysam.readthedocs.io/en/master/Tools.html?highlight=download#files.ResourceTools.FetchResourceFiles

        nsrdbfetcher = tools.FetchResourceFiles(
            tech="solar",
            workers=4,  # thread workers if fetching multiple files
            nrel_api_key=nrel_api_key,
            resource_type="psm3",
            resource_year=str(year),
            nrel_api_email=nrel_api_email,
            resource_dir=(input_dir / "PySAM Downloaded Weather Files/PV"),
            verbose=False,
        )

        # fetch resource data from the dictionary
        nsrdbfetcher.fetch(lon_lats)

        # get a dictionary of all of the filepaths
        nsrdb_path_dict = nsrdbfetcher.resource_file_paths_dict

        for filename in nsrdb_path_dict:
            solarResource = tools.SAM_CSV_to_solar_data(nsrdb_path_dict[filename])

            # assign the solar resource input file to the model
            system_model_PV.SolarResource.solar_resource_data = solarResource

            # execute the system model
            system_model_PV.execute()

            # access sytem power generated output
            output = system_model_PV.Outputs.gen
            df_output = pd.DataFrame(output)

            # roll the data to get into pacific time
            roll = int(tz_offset - system_model_PV.Outputs.tz)
            df_output = pd.DataFrame(np.roll(df_output, roll))

            # calculate capacity factor by dividing generation by the nameplate AC capacity
            df_output = df_output / (
                systemDesign["system_capacity"] / systemDesign["dc_ac_ratio"]
            )

            # name the column based on resource name
            # check if the resource name is a list, meaning the profile belongs to several resources
            if isinstance(resource_dict[filename], list):
                # merge each resource
                for gen in resource_dict[filename]:
                    df_output_gen = df_output.copy().rename(
                        columns={0: f"{gen}~{year}"}
                    )

                    # merge into the resource
                    df_output_gen.index = df_index
                    df_resource = df_resource.merge(
                        df_output_gen, how="left", left_index=True, right_index=True
                    )
            else:
                df_output = df_output.rename(
                    columns={0: f"{resource_dict[filename]}~{year}"}
                )

                # merge into the resource
                df_output.index = df_index
                df_resource = df_resource.merge(
                    df_output, how="left", left_index=True, right_index=True
                )

    # remove year from column name
    # df_resource.columns = [i.split('~')[0] for i in df_resource.columns]

    # groupby column name
    # df_resource = df_resource.groupby(df_resource.columns, axis=1).mean()

    return df_resource


def simulate_wind_generation(
    nrel_api_key,
    nrel_api_email,
    resource_dict,
    config_dict,
    resource_years,
    input_dir,
    tz_offset,
):

    # initiate the default wind power model
    system_model_wind = wind.default("WindPowerNone")

    # specify non-default system design factors
    turbine = config_dict["Turbine"]
    farm = config_dict["Farm"]
    resource = config_dict["Resource"]

    if "Losses" in config_dict:
        losses = config_dict["Losses"]
        system_model_wind.Losses.assign(losses)

    # assign the non-default system design specs to the model
    system_model_wind.Turbine.assign(turbine)
    system_model_wind.Farm.assign(farm)

    def default_powercurve_value(dict, key):
        """
        Checks if user provided value, otherwise returns default value
        """
        try:
            return dict[key]
        except KeyError:
            if key == "elevation":
                return 0
            elif key == "max_cp":
                return 0.45
            elif key == "max_tip_speed":
                return 80
            elif key == "max_tip_sp_ratio":
                return 8
            elif key == "drive_train":
                return 0
            else:

                class MissingData(Exception):
                    pass

                raise MissingData(f"missing required input for power curve: {key}")

    # calculate the powercurve if power curve parameters are specified
    if "Powercurve" in config_dict:
        powercurve = config_dict["Powercurve"]
        system_model_wind.Turbine.calculate_powercurve(
            elevation=default_powercurve_value(powercurve, "elevation"),
            turbine_size=default_powercurve_value(powercurve, "turbine_size"),
            rotor_diameter=int(default_powercurve_value(powercurve, "rotor_diameter")),
            max_cp=default_powercurve_value(powercurve, "max_cp"),
            max_tip_speed=default_powercurve_value(powercurve, "max_tip_speed"),
            max_tip_sp_ratio=default_powercurve_value(powercurve, "max_tip_sp_ratio"),
            cut_in=default_powercurve_value(powercurve, "cut_in"),
            cut_out=default_powercurve_value(powercurve, "cut_out"),
            drive_train=int(default_powercurve_value(powercurve, "drive_train")),
        )

    lon_lats = list(resource_dict.keys())

    # this is the df that will hold all of the data for all years
    df_resource = pd.DataFrame(data=range(1, 8761), columns=["timepoint"]).set_index(
        "timepoint"
    )
    df_index = df_resource.index

    for year in resource_years:

        # specify wind data input
        wtkfetcher = tools.FetchResourceFiles(
            tech="wind",
            workers=4,  # thread workers if fetching multiple files
            nrel_api_key=nrel_api_key,
            nrel_api_email=nrel_api_email,
            resource_year=str(year),
            resource_height=resource["resource_height"],
            resource_dir=(input_dir / "PySAM Downloaded Weather Files/Wind"),
            verbose=False,
        )

        # fetch resource data from the dictionary
        wtkfetcher.fetch(lon_lats)

        # get a dictionary of all of the filepaths
        wtk_path_dict = wtkfetcher.resource_file_paths_dict

        for filename in wtk_path_dict:
            windResource = tools.SRW_to_wind_data(wtk_path_dict[filename])

            # assign the wind resource input data to the model
            system_model_wind.Resource.wind_resource_data = windResource

            # execute the system model
            system_model_wind.execute()

            # access sytem power generated output
            output = system_model_wind.Outputs.gen

            df_output = pd.DataFrame(output)

            # calculate capacity factor
            df_output = df_output / farm["system_capacity"]

            # name the column based on resource name
            # check if the resource name is a list, meaning the profile belongs to several resources
            if isinstance(resource_dict[filename], list):
                # merge each resource
                for gen in resource_dict[filename]:
                    df_output_gen = df_output.copy().rename(
                        columns={0: f"{gen}~{year}"}
                    )

                    # merge into the resource
                    df_output_gen.index = df_index
                    df_resource = df_resource.merge(
                        df_output_gen, how="left", left_index=True, right_index=True
                    )
            else:
                df_output = df_output.rename(
                    columns={0: f"{resource_dict[filename]}~{year}"}
                )

                # merge into the resource
                df_output.index = df_index
                df_resource = df_resource.merge(
                    df_output, how="left", left_index=True, right_index=True
                )

    # remove year from column name
    # df_resource.columns = [i.split('~')[0] for i in df_resource.columns]

    # groupby column name
    # df_resource = df_resource.groupby(df_resource.columns, axis=1).mean()

    return df_resource


def simulate_csp_generation(
    nrel_api_key,
    nrel_api_email,
    resource_dict,
    config_dict,
    resource_years,
    input_dir,
    tz_offset,
):

    # initiate the default PV setup
    system_model_MSPT = csp_tower.default("MSPTSingleOwner")

    # specify non-default system design factors
    systemDesign = config_dict["SystemDesign"]
    timeOfDeliveryFactors = config_dict["TimeOfDeliveryFactors"]
    systemControl = config_dict["SystemControl"]

    # assign the non-default system design specs to the model
    system_model_MSPT.SystemControl.assign(systemControl)
    system_model_MSPT.TimeOfDeliveryFactors.assign(timeOfDeliveryFactors)
    system_model_MSPT.SystemDesign.assign(systemDesign)

    lon_lats = list(resource_dict.keys())

    # this is the df that will hold all of the data for all years
    df_resource = pd.DataFrame(data=range(1, 8761), columns=["timepoint"]).set_index(
        "timepoint"
    )
    df_index = df_resource.index

    for year in resource_years:

        # download resource files
        # https://github.com/NREL/pysam/blob/master/Examples/FetchResourceFileExample.py
        # https://nrel-pysam.readthedocs.io/en/master/Tools.html?highlight=download#files.ResourceTools.FetchResourceFiles

        nsrdbfetcher = tools.FetchResourceFiles(
            tech="solar",
            workers=4,  # thread workers if fetching multiple files
            nrel_api_key=nrel_api_key,
            resource_type="psm3",
            resource_year=str(year),
            nrel_api_email=nrel_api_email,
            resource_dir=(input_dir / "PySAM Downloaded Weather Files/CSP"),
            verbose=False,
        )

        # fetch resource data from the dictionary
        nsrdbfetcher.fetch(lon_lats)

        # get a dictionary of all of the filepaths
        nsrdb_path_dict = nsrdbfetcher.resource_file_paths_dict

        for filename in nsrdb_path_dict:
            # convert TMY data to be used in SAM
            # solarResource = tools.SAM_CSV_to_solar_data(nsrdb_path_dict[filename])

            # assign the solar resource input file to the model
            # system_model_MSPT.SolarResource.solar_resource_data = solarResource
            system_model_MSPT.SolarResource.solar_resource_file = nsrdb_path_dict[
                filename
            ]

            # execute the system model
            system_model_MSPT.execute()

            # access sytem power generated output
            output = system_model_MSPT.Outputs.gen

            # roll the data to get into pacific time
            df_output = pd.DataFrame(output)

            # calculate capacity factor
            df_output = df_output / (systemDesign["P_ref"] * 1000)

            # name the column based on resource name
            # check if the resource name is a list, meaning the profile belongs to several resources
            if isinstance(resource_dict[filename], list):
                # merge each resource
                for gen in resource_dict[filename]:
                    df_output_gen = df_output.copy().rename(
                        columns={0: f"{gen}~{year}"}
                    )

                    # merge into the resource
                    df_output_gen.index = df_index
                    df_resource = df_resource.merge(
                        df_output_gen, how="left", left_index=True, right_index=True
                    )
            else:
                df_output = df_output.rename(
                    columns={0: f"{resource_dict[filename]}~{year}"}
                )

                # merge into the resource
                df_output.index = df_index
                df_resource = df_resource.merge(
                    df_output, how="left", left_index=True, right_index=True
                )

    # remove year from column name
    # df_resource.columns = [i.split('~')[0] for i in df_resource.columns]

    # groupby column name
    # df_resource = df_resource.groupby(df_resource.columns, axis=1).mean()

    return df_resource
