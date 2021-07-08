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

All model runs, including input and output data, should be contained in the `MODEL_RUNS` directory. You may optionally specify to store your model run files in a separate directory.

1. Create a directory to store your model run files.
To get started, create a new folder within `MODEL_RUNS`. This can be named whatever you would like,
for example `model_1`. Copy the `model_inputs.xlsx` template into this model folder.

2. Enter your data inputs into the spreadsheet
In the `model_inputs` excel spreadsheet, you will find tabs for different types of input data. Any cells highlighted in yellow can be updated. 
The spreadsheet contains some placeholder data that you can write over. You can configure multiple scenarios within a single inputs spreadsheet. 

3. Generate model input files
Open `run_scenarios.ipynb` and follow any directions listed.
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
	┃ ┃ ┣ 📜nodal_costs_by_gen.csv
	┃ ┃ ┣ 📜costs_itemized.csv
	┃ ┃ ┣ 📜cost_components.csv
	┃ ┃ ┣ 📜dispatch-wide.csv
	┃ ┃ ┣ 📜dispatch.csv
	┃ ┃ ┣ 📜DispatchBaseloadByPeriod.csv
	┃ ┃ ┣ 📜DispatchGen.csv
	┃ ┃ ┣ 📜DischargeStorage.csv
	┃ ┃ ┣ 📜dispatch_annual_summary.csv
	┃ ┃ ┣ 📜dispatch_zonal_annual_summary.csv
	┃ ┃ ┣ 📜electricity_cost.csv
	┃ ┃ ┣ 📜generation.csv
	┃ ┃ ┣ 📜GenFuelUseRate.csv
	┃ ┃ ┣ 📜gen_cap.csv
	┃ ┃ ┣ 📜load_balance.csv
	┃ ┃ ┣ 📜nodal_costs.csv	
	┃ ┃ ┣ 📜nodal_costs_by_gen.csv
	┃ ┃ ┣ 📜results.pickle
	┃ ┃ ┣ 📜scenario_summary.csv
	┃ ┃ ┣ 📜StateOfCharge.csv
	┃ ┃ ┣ 📜storage_builds.csv
	┃ ┃ ┣ 📜storage_cycle_count.csv
	┃ ┃ ┣ 📜storage_dispatch.csv
	┃ ┃ ┣ 📜summary_report_annual_goal.html		   } interactive summary report
	┃ ┃ ┣ 📜summary_report_annual_goal_public.html }
	┃ ┃ ┣ 📜SystemPower.csv
	┃ ┃ ┣ 📜system_power.csv
	┃ ┃ ┗ 📜total_cost.txt
	┃ ┣ 📂scenario_name_2
	┃ ┣ 📜portfolio_comparison.csv: side-by-side comparison of portfolios chosen for each scenario
	┗ ┗ 📜scenario_comparison.csv: side-by-side comparison of outputs for each scenario

# KEEPING THE CODE UPDATED
From time to time, the code will be updated on GitHub. To ensure that you are keeping your local version of the code up to date, open git bash and follow these steps:
	
	# change the directory to whereever your local git repository is saved
	# after hitting enter, it should show the name of the git branch (e.g. "(master)")
	cd GitHub/SWITCH247  

	# save any changes that you might have made locally to your copy of the code
	git add .

	# fetch and merge the updated code from github
	git pull origin master

Your local copy of the code should now be up to date. 
NOTE: If you've pulled updates to the summary reports that you want to re-run for existing model runs, you will need to use `manually_run_reports.py` in `switch_model/reporting`

# COLLABORATING
If you plan on contributing edits to the codebase that will be merged into the master branch, please follow these best practices:

1. Please do not make edits directly to the master branch. Any new features or edits should be completed in a new branch. To do so, open git bash, navigate to your local repo (e.g. `cd GitHub/SWITCH247`), and create a new branch, giving it a descriptive name related to the edit you will be doing:

	`git checkout -b branch_name`

2. As you code, it is a good practice to 'save' your work frequently by opening git bash, navigating to your local repo (`cd GitHub/SWITCH247`), making sure that your current feature branch is active (you should see the feature name in parentheses next to the command line), and running 
	
	`git add .`

3. You should commit your work to the branch whenever you have working code or whenever you stop working on it using:

	`git add .`  
	`git commit -m "short message about updates"`

4. Once you are done with your edits, you should update `CHANGELOG.md` with a description of your updates before committing your final changes. To do so, copy the most recent entry and replace the date with the date that you will be pushing your changes, and replace the text with a description of the changes you made. Once you have updated the changelog, save and commit your code using step #3 and then push your changes:

	`git push`

5. Now open the GitHub repo web page. You should see the branch you pushed up in a yellow bar at the top of the page with a button to "Compare & pull request". 
	- Click "Compare & pull request". This will take you to the "Open a pull request" page. 
	- From here, you should write a brief description of what you actually changed (you can copy and paste this from the changelog). 
	- Click the "Reviewers" tab and select Greg as a reviewer. 
	- Click "Create pull request"
	- Greg will then review the edit and merge it into the master branch, which will then delete the feature branch.

# TESTING
NOTE: The run_tests.py module has not been tested with SWITCH247  
To test the entire codebase, run this command from the root directory:

	python run_tests.py

# Development TODO

## Bug Fixes / Model performance
- [ ] Model is not always finding the optimal solution. For example, it will identify an optimal portfolio but if you constrain one of the selected resources and re-run the model, the new solution will be a lower cost than the original. There could be a few potential sources of this issue:
	- The costs being optimized in the model are not the same that are being reported in the summary report (look at the raw model outputs to see if the constrained results are still better)
	- Could be related to how congestion costs are being optimized in the model - perhaps we should only optimize for ppa costs
	- Model may be finding a local minimum rather than the global minimum. Will need to consult with others to determine how one might fix.
- [ ] Validate model results by modeling historical year and comparing to actual data
- [ ] If solving scenarios in parallel, scenario summary reports should only be run once all scenarios are finished solving
- [ ] Investigate why miniscule amounts of certain resources are built (rounding issues?)
- [ ] Figure out how to deal with scenarios where nodal revenues > PPA cost, leading to unbounded problems
- [x] Address FileNotFoundError when running NbConvertApp during post-solve (issue with subprocess.py?)
	- This was an issue with a local environment related to this issue: https://github.com/jupyter/notebook/issues/2301

## Renewable Goal definitions
- [ ] Configure target that maximizes time-coincidence with 100% volumetric matching, or which matches shape 
	- (maximize correlation coefficient?)
	- (minimize abolute error between load and generation?)
	- (assign a cost penalty to over-procurement? Set constraint on maximum over-procurement?)
- [ ] Allow grid power to help meet renewable goal
	- [ ] Input for hourly grid carbon intensities
- [ ] Allow model to run with monthly TOD average values (probably need month-day of week-hour average - 12x7x24)

## Resource Adequacy
- [ ] Update calculation of Qualifying Capacity for Hydro and Geothermal
- [ ] Update calculation of Qualifying capacity for Hybrid resources

## Storage 
- [ ] Investigate whether hybrid generators can be modeled as a single resource
- [ ] Investigate implementing opportunitistic/greedy storage charging
- [ ] Determine how to deal with perfect foresight problem - can we implement day-ahead or week-ahead foresight?
- [ ] Investigate implementing storagedispatch as single decision variable
- [ ] In report plots, show battery charging AND discharging as green line modifying demand?

## Generic Resources
- [ ] Check for updated/newer wind resource data from wind toolkit
- [x] Check for integration of tidal/wave energy
	- Wave model timeseries data to be integrated fall 2021 per https://github.com/NREL/SAM/pull/645 using data from https://developer.nrel.gov/docs/wave/


## Demand-side resources
- [ ] Allow for load shift to have costs
- [ ] Allow for multiple demand-side projects, each with capital costs
- [ ] Allow for different types of DSR, like efficiency, curtailment, and load shifting
- [ ] Improve visualization/reporting of load shift in summary report
- [ ] Investigate whether we can access model shadow prices for each hour as a metric to value demand response

## Supply-Demand Balance Constraint
- [x] Figure out how to prevent storage from charging and discharging in same timepoint
- [x] Only allow grid power consumption if not enough storage/generation (and/or investigate cost incentives)
	- both of these seem to be addressed by the 2021.03.24 update

## Generation dispatch
- [x] Only make DispatchGen a decision variable for dispatchable generators (not variable renewables)
- [x] Configure sets of dispatchable vs non-dispatchable generators
- [x] Remove all components related to variable fuel costs, or move to a separate module to be used in rare cases that you a) have a fuel-based generator and b) are responsible for the variable fuel costs
- [ ] Allow baseload generation

## Cost Vector/Objective Function
- [x] Investigate why annual goal is not leading to just buying the cheapest generator
	- issue was cost incentives
- [x] Re-write cost components for objective function
- [ ] Determine whether we need to account for congestion costs with storage resources
- [ ] Allow resale value of excess RECs/generation to be considered in objective function
- [ ] Test contract-only cost optimization, rather than optimizing for congestion as well
- [ ] Implement pre-model check to determine if Pnode revenues exceed contract cost to catch overbuild situations

## Reporting
- [ ] Report which capacity limits are binding
- [ ] Update counting/valuation of RECs
- [ ] Separate reporting of committed costs (existing contracts) and future costs - provide some level of understanding of uncertainty
- [ ] Report cost of lost storage energy?

## Future edits for non-PCE scenarios
- [ ] Investigate hydro dispatch implementation
- [ ] Allow for "Standard Delivery" (Grid-mix) renewables to count
- [ ] Set up capability for both physical and virtual PPAs, including contracts for difference

## Cleanup
- [ ] Combine no_commit.py with dispatch.py
- [ ] Remove unused modules (especially in reporting directory)
	- removed commit
- [ ] Eliminate option to select required modules in the input spreadsheet
- [ ] Update code for newer versions of Pyomo / Python
- [ ] Create inputs directory where cbc executable can be saved
- [ ] Rename SystemPower as GridPower
- [ ] Rename from switch?
- [ ] Update run_tests.py
- [ ] Get run_tests.py working



