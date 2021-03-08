This contains "Switch 24x7", a time-coincident renewable energy portfolio
planning model that is based on version 2 of the Switch electricity planning model.

To generate documentation, go to the doc folder and run ./make_doc.sh.
This will build html documentation files from python doc strings which
will include descriptions of each module, their intentions, model
components they define, and what input files they expect.

# INSTALLATION

See "INSTALL.md" for instructions on how to download and install switch 24x7 on your machine. 

# DIRECTORY STRUCTURE
```
📦switch_model
 ┣ 📂balancing
 ┃ ┣ 📂demand_response
 ┃ ┃ ┣ 📂iterative: not currently in use
 ┃ ┃ ┣ 📜simple.py: defines DR/load shift resources
 ┃ ┣ 📜load_zones.py: defines load zones, including the supply/demand balancing constraint
 ┃ ┗ 📜renewable_target.py: defines renewable energy % goals and grid power supply
 ┣ 📂energy_sources
 ┃ ┣ 📂fuel_costs: not currently used since there are no fuel-based generators
 ┃ ┗ 📜properties.py: defines properties of energy sources
 ┣ 📂generators
 ┃ ┣ 📂core
 ┃ ┃ ┣ 📂commit: Not used because unit commitment is not modeled
 ┃ ┃ ┣ 📜build.py: defines how to build/select projects
 ┃ ┃ ┣ 📜dispatch.py: defines how to dispatch generators in each timepoint
 ┃ ┃ ┣ 📜gen_discrete_build.py: forces discrete increments of a project to be built (optional)
 ┃ ┃ ┗ 📜no_commit.py: defines limits on generator dispatch in the absence of unit commitment constraints (TODO: combine with dispatch.py)
 ┃ ┣ 📂extensions
 ┃ ┃ ┣ 📜congestion_pricing.py: adds nodal pricing dynamics to the model
 ┃ ┃ ┣ 📜hydro_simple.py: not used (for dispatching hydro facilities)
 ┃ ┃ ┣ 📜resource_adequacy.py: defines RA requirements and positions
 ┃ ┗ ┗ 📜storage.py: defines how to build and dispatch energy storage 
 ┣ 📂reporting
 ┃ ┣ 📜basic_exports.py: not used?
 ┃ ┣ 📜dump.py: not used?
 ┃ ┣ 📜example_export.py: not used?
 ┃ ┣ 📜generate_report.py: used to execute jupyter notebooks for summary reports
 ┃ ┣ 📜summary_report.ipynb: jupyter notebook template for interactive summary of results
 ┃ ┣ 📜summary_report_public.ipynb: public version of report with data about individual generators scrubbed
 ┃ ┗ 📜test.py: testing function used for development
 ┣ 📂upgrade: not used
 ┣ 📜financials.py
 ┣ 📜generate_input_files.py: creates input files from model_inputs excel spreadsheet
 ┣ 📜main.py
 ┣ 📜run_scenarios.ipynb: Used to populate inputs and run scenarios
 ┣ 📜solve.py
 ┣ 📜solve_scenarios.py
 ┣ 📜test.py
 ┣ 📜timescales.py
 ┣ 📜utilities.py
 ┗ 📜version.py
```

# CONFIGURING MODEL RUNS

All model runs, including input and output data, should be contained in the `MODEL_RUNS` directory.

1. Create a directory to store your model run files.
To get started, create a new folder within `MODEL_RUNS`. This can be named whatever you would like,
for example `model_1`. Copy the `model_inputs.xlsx` template into this model folder.

2. Enter your data inputs into the spreadsheet
In the `model_inputs` excel spreadsheet, you will find tabs for different types of input data. Any cells highlighted in yellow can be updated. 
The spreadsheet contains some placeholder data that you can write over. You can configure multiple scenarios within a single inputs spreadsheet. 

3. Generate model input files
Open `run_scenarios.ipynb` and complete steps 1 and 2 under the "Generate Model Inputs" heading, following any directions listed.
This step will take the data entered into the excel spreadsheet and format it for use in the model. 

This will generate:  

	📂model_run_name
	┣ 📂generator_set_1: holds solar and wind resource data for each set of generators
	┃ ┗ 📂PySAM Downloaded Weather Files
	┃ ┃ ┣ 📂PV
	┃ ┃ ┗ 📂Wind
	┣ 📂inputs: holds input files for each scenario
	┃ ┣ 📂scenario_name_1
	┃ ┃ ┣ 📜days.csv
	┃ ┃ ┣ 📜financials.csv
	┃ ┃ ┣ 📜fuels.csv
	┃ ┃ ┣ 📜fuel_cost.csv
	┃ ┃ ┣ 📜generation_projects_info.csv
	┃ ┃ ┣ 📜gen_build_predetermined.csv
	┃ ┃ ┣ 📜gen_build_years.csv
	┃ ┃ ┣ 📜loads.csv
	┃ ┃ ┣ 📜load_zones.csv
	┃ ┃ ┣ 📜modules.txt
	┃ ┃ ┣ 📜nodal_prices.csv
	┃ ┃ ┣ 📜non_fuel_energy_sources.csv
	┃ ┃ ┣ 📜periods.csv
	┃ ┃ ┣ 📜pricing_nodes.csv
	┃ ┃ ┣ 📜renewable_target.csv
	┃ ┃ ┣ 📜summary_report.ipynb
	┃ ┃ ┣ 📜summary_report_public.ipynb
	┃ ┃ ┣ 📜switch_inputs_version.txt
	┃ ┃ ┣ 📜system_power_cost.csv
	┃ ┃ ┣ 📜timepoints.csv
	┃ ┃ ┣ 📜timeseries.csv
	┃ ┃ ┗ 📜variable_capacity_factors.csv
	┃ ┗ 📂scenario_name_2
	┣ 📂outputs: placeholder folders for outputs
	┃ ┣ 📂scenario_name_1
	┃ ┗ 📂scenario_name_2
	┣ 📜cbc.exe
	┣ 📜coin-license.txt
	┣ 📜model_inputs.xlsx
	┣ 📜options.txt: list of options for the command line
	┗ 📜scenarios.txt: list of all of the scenarios to run

4. Run the model
In the same `run_scenarios.ipynb`, follow the directions under the "Solve Model Scenarios" heading to run the scenarios.

5. Examine the results
Results for each scenario will be saved to the `outputs` directory. The main output files to examine are the inteactive HTML output reports, 
but tabular output data is also saved to individual csv files in the output folder. There are also csv files in the main outputs directory that
provide quick side-by-side comparisons of all scenarios. 

Typical outputs will look like:

	📂model_run_name
	┣ 📂outputs: 
	┃ ┣ 📂scenario_name_1
	┃ ┃ ┣ 📜BuildGen.csv
	┃ ┃ ┣ 📜BuildMinGenCap.csv
	┃ ┃ ┣ 📜BuildStorageEnergy.csv
	┃ ┃ ┣ 📜ChargeStorage.csv
	┃ ┃ ┣ 📜congestion_costs_by_gen.csv
	┃ ┃ ┣ 📜costs_itemized.csv
	┃ ┃ ┣ 📜cost_components.csv
	┃ ┃ ┣ 📜dispatch-wide.csv
	┃ ┃ ┣ 📜dispatch.csv
	┃ ┃ ┣ 📜DispatchBaseloadByPeriod.csv
	┃ ┃ ┣ 📜DispatchGen.csv
	┃ ┃ ┣ 📜DispatchStorage.csv
	┃ ┃ ┣ 📜dispatch_annual_summary.csv
	┃ ┃ ┣ 📜dispatch_zonal_annual_summary.csv
	┃ ┃ ┣ 📜electricity_cost.csv
	┃ ┃ ┣ 📜generation.csv
	┃ ┃ ┣ 📜GenFuelUseRate.csv
	┃ ┃ ┣ 📜gen_cap.csv
	┃ ┃ ┣ 📜load_balance.csv
	┃ ┃ ┣ 📜results.pickle
	┃ ┃ ┣ 📜scenario_summary.csv
	┃ ┃ ┣ 📜StateOfCharge.csv
	┃ ┃ ┣ 📜storage_builds.csv
	┃ ┃ ┣ 📜storage_cycle_count.csv
	┃ ┃ ┣ 📜storage_dispatch.csv
	┃ ┃ ┣ 📜summary_report_annual_goal.html		} interactive summary report
	┃ ┃ ┣ 📜summary_report_annual_goal_public.html }
	┃ ┃ ┣ 📜SystemPower.csv
	┃ ┃ ┣ 📜system_power.csv
	┃ ┃ ┗ 📜total_cost.txt
	┃ ┣ 📂scenario_name_2
	┃ ┣ 📜portfolio_comparison.csv: side-by-side comparison of portfolios chosen for each scenario
	┗ ┗ 📜scenario_comparison.csv: side-by-side comparison of outputs for each scenario



# TESTING
To test the entire codebase, run this command from the root directory:
	python run_tests.py

# Development TODO
- [ ] Combine no_commit.py with dispatch.py
- [ ] Remove unused modules (especially in reporting directory)
- [ ] Create inputs directory where cbc executable can be saved
- [ ] Update code for newer versions of Pyomo / Python
- [ ] Figure out how to prevent storage from charging and discharging in same timepoitn
- [ ] Remove DispatchGen as a decision variable for renewable generators to improve solve time
- [ ] Eliminate option to select required modules in the input spreadsheet
