
-------------------------------------------------------------------------------
Commmit 2021.10.06 (Version 0.7.1)
-------------------------------------------------------------------------------

Squashes some bugs

- Removes `switch_model.balancing.demand_response.iterative` module
- Removes functions in `switch_model.utilities` and `switch_model.financials` that are not used
- Fixes a bug where variable capacity factors for different generic resources with the same lat/long coordinates were not being generated correctly.
- Adds blank notes header row in `model_inputs.xlsx` for the user to take notes about the data represented in each column
- updates color coding of cells in `model_inputs.xlsx`
- Bug fixes to reporting functions to address errors when certain types of resources are not in the scenario portfolio
- Re-implements the functionality to export a summary csv table based on the summary_report results and aggregate these outputs together across all scenarios so that they can be easily compared.

-------------------------------------------------------------------------------
Commmit 2021.10.01 (Version 0.7.0)
-------------------------------------------------------------------------------

## Closes #21 (Integrate duals and reduced costs)

Integrates the reduced costs for the BuildGen variable and the dual values for the load constraint into the summary report.
Fixes bug where duals were not being retrieved from the CPLEX solver.

-------------------------------------------------------------------------------
Commmit 2021.09.30 (Version 0.6.0)
-------------------------------------------------------------------------------

## Closes #18 
Allows the REC value of excess generation to be included in the objective function as an option, using `--sell_excess_RECs sell`

Combines the modules `switch_model.generators.core.dispatch` and `switch_model.generators.core.no_commit` into a single module `switch_model.generators.core.dispatch`.
Removes `switch_model.generators.core.no_commit` from the model.

-------------------------------------------------------------------------------
Commmit 2021.09.29 (Version 0.5.0)
-------------------------------------------------------------------------------

Implements updates to the calculation of resource adqueacy

## Closes #1 (Update RA QC/EFC calculations)

Updates the calculation of NQC based on resource type, including new calculations for how NQC must be split between the components of a hybrid generator. 

The formulae for calculating hybrid NQC include a term for storage energy capacity. However, because this is now a decision variable itself (rather than a fixed ratio based on the generator capacity), due to changes made in commit 2021.09.22 (version 0.3.0), we cannot include this term in the calculation without making the model non-linear.
Our way around this is to take the average value of the minimum and maximum hybrid storage capacity ratio parameters, and assume that to be the storage capacity. While this will not be exactly correct, it minimizes potential error. 

There is no longer a requirement for local RA, so this update removes all references to local ra, including removing references to local reliability areas. the ra requirement is now indexed to a period and month, and not an area.

Adds the ability to add the sale value of excess RA to the objective function, using the option `--sell_excess_RA sell`

## Notes on #14 (align RA calcualtions in model and report)

In the summary_report, the calculation of the value of excess RA takes into account the fact that flex RA must be bundled with system RA, and that you cannot double count local RA and system RA. However, the calculation of this value in the model does not account for this. If including this resale value in the objective function, using the sell ra option, it is important to calculate this value correctly. However, the CPUC is also eliminating the requirement for each LSE to procure local RA, so we do not have to worry about updating the calculation for local RA. Additionaly, for now, we're not going to fix the flex RA calculation unless we start seeing during validation that 

## Midterm reliability constraint
The CPUC recently issued an order for all LSEs to procure a certain quantity of baseload resources. This model update includes a new parameter `midterm_reliability_requirement` and constraint that requires the amount of baseload capacity to be greater or equal to the requirement.

There is a new requirement to procure a certain number of MW from baseload resources 


Other fixes:
 - introduced parameter `gen_is_hybrid` and updated how the set `HYBRID_STORAGE_GENS` is built
 - fixes bug that prevented the `select_variants` option from being implemented

-------------------------------------------------------------------------------
Commmit 2021.09.29 (Version 0.4.0)
-------------------------------------------------------------------------------

Implements changes that allow for dispatchable generators to be modeled, and for the GHG emissions from generation to be accounted for.
Addresses #23, #27
Closes #38

## Emissions Accounting

The old switch model tracked emissions based on fuel consumption of each generator. However, since this model focuses on contracted generation (for which fuel costs and combustion are not direct concerns of the off-taker), we remove variables that track fuels and fuel costs. The newly-implemented emissions tracking assigns an emission factor (unit of emissions / MWh) to each generator. Grid emissions are assigned an emission factor for each hour (timepoint). Our implementation does not require a specific unit for the emission factor, as long as these units are consistent across all of the model inputs. For example, this allows the flexibility for the user to use their preferred mass unit (lb, kg, metric tonnes), GHG gas (CO2, CO2eq), and scope (direct emissions vs lifecycle emissions). In the `model_inputs.xlsx` spreadsheet, the user specifies which unit they are using in the "general" tab, and this unit will be pulled into the output reports.

This current implementation is meant to track attributional emissions using a market-based accounting method. This implementation does not track avoided or marginal emissions from the portfolio.


- Removes non_fuel_energy_sources, fuel, and fuel_cost inputs
- Removes `switch_model.energy_sources.properties` as a required module
- Creates `switch_model.energy_sources.emissions` as a new module that can track emissions from each generator and from any system power consumed
- small changes to `generate_input_files` to allow for dispatchable, non-variable, non-baseload generators to be modeled. 
- Moves the parameters for CCS-equipped generators to the emissions module from `switch_model.generators.extensions.gen_fuel_costs`
- Removes the following modules from the model: `switch_model.energy_sources.properties`, `switch_model.generators.extensions.gen_fuel_costs`, `switch_model.energy_sources.fuel_costs`
- Removed the interest rate from the financials, since it is not used
- Adds emissions data to summary report

-------------------------------------------------------------------------------
Commmit 2021.09.28 (Version 0.3.1)
-------------------------------------------------------------------------------

This commit fixes and streamlines the post_solve and reporting process. 

We have updated `summary_report.ipynb` with the main/essential reporting outputs for model validation. Other output tables/plots still need to be added, but are less critical. 
In updating the summary report, we moved all of the functions that manipulate the output data to a separate file `report_functions`, which is imported into `summary_report.ipynb`. This reduces the amount of actual code found in the summary report, makes the code more modular, and eliminates duplicate `pd.read_csv()` functions within the file.

### Closes #22 and #37
- Updates post-solve functions to reduce output file size and unneccesary output files
- removes `switch_model.reporting` from the default/required modules for each model run. This module exported csvs for each decision variable, which duplicated data exported as part of other post solve functions. Removing this module also gets rid of the `total_cost.txt` and `cost_components.csv` outputs, and also removes the "--sorted-output" option from the `options.txt` file
- `model_inputs.xlsx` has been updated to remove `switch_model.reporting` from teh scenarios tab, and `sorted-output` from the solver options tab.

Other updates
- updated README
- Disabled the functionality to generate scenario comparison reports until we have completed updates on the summary_report
- Updated how the annual renewable target was calculated to take storage losses into account
- Adds a calculation of hedge market revenue to the `system_power.csv` output, based on a new input `hedge_settlement_node`, which specifies at which wholesale pricing node the hedge contract should be settled. This hedge market revenue is not included in the objective function, in order to prevent over-reliance on system power if the hedge is in the money.

-------------------------------------------------------------------------------
Commmit 2021.09.22 (Version 0.3.0)
-------------------------------------------------------------------------------
This commit includes many major updates to how generation and storage is dispatched in the model, and which costs are being optimized. 

## Closes #4
Wholesale costs
- changes the name of `congestion_pricing.py` to `wholesale_pricing.py`
- We remove `CongestionCostInTP` from the objective function, and instead only optimize for `GenPnodeRevenue` and `DLAPLoadCostInTP`

### Over-building issue
- In some cases, the weighted average Pnode revenue is greater than the weighted average PPA cost for a generator, meaning that the model would try to build as much as possible, leading to an unbounded problem if the generator capacity was not constrained. 
- To identify these issues, we added a validation calculation to `generate_input_files.py` to warn us when the Pnode revenue would exceed PPA cost.
- To fix this, we needed to add a disincentive for increasing ExcessGen, so we removed the `ExcessGenPnodeRevenue` term from the objective function. In order to calculate the total cost, we will need to add this term back in to the summary_report
- This essentially puts an economic penalty on excess_generation, equivalent to the financial reprecussions of curtailing all excess generation (must pay PPA cost, but don't earn Pnode revenue)

## Closes #9
Adds a decision variable for renewable curtailment, limited by the cap on curtailment. This should lead to economic curtailment during times when wholesale prices are low or negative. 

## Closes #10
Adds option to limit excess generation through a hard constraint. This can be implemented as an annual limit on excess generation, or a limit on the amount of excess generation in each hour. The limit is expressed as percentage of DispatchGen, so a limit of 0.10 would mean that ExcessGen could be no more than 10% of DispatchGen, either on an annual or hourly basis

## Closes #17
We wanted to ensure that storage was only charging from renewable generation, rather than grid power.
To do this, we implemented a new constraint that requires total storage charging to be less than total generator dispatch. 
This may mean that at some times, grid power is being consumed when batteries are charging. To get around this, we will simply
adjust our accounting such that grid power is only ever assigned to load, and the charging reduces the net renewable generation
available to meet load.

## Closes #19
Previously, we had allowed power injections to be >= withdrawals, because we had specified that the full renewable capacity would be dispatched.
We have changed the accounting so that generator dispatch is split into DispatchGen (the amount of dispatch needed to meet load and storage charging) 
and ExcessGen (the amount of generation available that is not used in that hour). This means that the load balance constraint is now an equality constraint, where
Power injections == power withdrawals in all hours. 

## Closes #34
Allows the storage portion of hybrid projects to be built in any ratio with the generator portion, between a minimum and maximum ratio.
- Split `storage_hybrid_capacity_ratio` into `storage_hybrid_min_capacity_ratio` and `storage_hybrid_max_capacity_ratio`
- Replaced the `Enforce_Hybrid_Build` constraint with two two constraints: `Enforce_Minimum_Hybrid_Build` and `Enforce_Maximum_Hybrid_Build`

## Closes #35
Adds hedge contract premiums to the objective function
- Replaced `system_power_cost` with `hedge_cost`
- Set a default value of $0.0000001 to disincentivize using grid power even if hedge cost is not specified

## Simultaneous Storage Charging and Discharging
- In some instances (especially when wholesale prices are negative), there is an incentive for storage to simultaneously charge and discharge, which is not physically realistic.
- To prevent this, we introduced a constraint that uses a binary indicator variable that indicates when each storage asset is charging, and prevents simultaneous discharging (and vise versa)
- Adding this binary variable makes the problem into a mixed-integer linear program (MILP), which increases solve time
- An alternative approach which seems to limit the amount of simultaneous charging and discharging that occurs is to add a $1 penalty to every MWh discharged. This approach can be accessed by using the `storage_nonbinary.py` module.

## Re-implements baseload generation functionality
Previously, baseload generators (like geothermal) were implemented as variable generators. However, now that we have allowed variable generators to have `ExcessGen` and `CurtailGen`, it makes sense to separate baseload resources out. In this implementation, baseload resources are still given a capacity factor for each timepoint (like variable generators), but baseload generators must dispatch at this capacity factor, and are not allowed to have excess gen. For baseload generators, this requires using all of their output, which either must be matched to load, or charged in a battery.
- replaced `gen_max_capacity_factor` with `variable_capacity_factor`, which is indexed to `VARIABLE_GENS`
- created an equivalent `baseload_capacity_factor`, which is indexed to `BASELOAD_GENS`
- there are now two separate input files for these factors: `variable_capacity_factors.csv` and `baseload_capacity_factors.csv`

## Other fixes:
- Fixed issue where Generator Pnode revenue was being optimized as a positive cost, rather than a revenue (negative cost)
- Adds a "solver_options" tab to the model inputs spreadsheet, which allows the user to specify solver options

-------------------------------------------------------------------------------
Commmit 2021.08.26 (Version 0.2.0)
-------------------------------------------------------------------------------
Fixes #25
Updates the code to work with Pyomo 6.1, from Pyomo 5.6.8, so that the code is compatible with CPLEX as a solver.
The environment.yml file has been updated to require use of Pyomo>=6.0.0 and pyutilib>=6.0.0, so continued use will require updating your environment. 

Specific updates include:
 - pyomo elements with "Simple" in their name were renamed to "Scalar"
 - For any params with string elements, needed to manually specify `within=Any` when defining the param in order to silence a deprecation warning
 - Needed to manually specify `dimen=1` for Sets that are used to index parameters when loading data
 - When loading data, you can no longer specify the index as a cross product of multiple sets (e.g. `index=mod.PERIODS*mod.MONTHS`). Instead, they must be specified as a list of Sets (e.g. `index=[mod.PERIODS, mod.MONTHS]`)

Other cleanup included:
 - when loading data, replaced specifying multiple parameters as tuples with specifying them as lists, to speed the data loading process
 - Removed `PERIODS_FOR_GEN_BLD_YR`, and `TPS_FOR_GEN_IN_PERIOD` because they are not used in the model
 - changed the `gen_capacity_value` to `elcc` for Effective Load Carrying Capacity


-------------------------------------------------------------------------------
Commmit 2021.08.11
-------------------------------------------------------------------------------
Fixes #4, #6, #7, #12

Updates to how costs are calculated in the model.
 - Updates the `uniform_series_to_present_value` function in `financials.py` to use the formula for the present value of an annuity due (#12)
 - In `generators.extensions.storage`, removes the PPA cost discount for hybrid energy storage dispatch (#6)
 - Updates the `summary_report.ipynb` to show a plot of nodal costs, and display hybrid storage charging/discharging as part of storage, rather than the paired resource
 - In summary_report, fixes the generator cost per MWh table. For hybrid resources, the congestion cost of the ES component nets out the congestion cost of the RE component, so there is no energy arbitrage cost associated with hybrids anymore. Energy arbitrage could be shown if the calculation is reconfigured, but it seems that this is not important.

-------------------------------------------------------------------------------
Commmit 2021.08.10
-------------------------------------------------------------------------------
Closes #13 and #16

This update sets us up to be able to validate the model by exploring the model instance.
It also allows us to access the dual, slack, and reduced cost values so that these can be integrated into the summary reports in the future.
Allows the model instance to be exported as a `.pickle` file so that it can be explored for validation purposes
Adds a jupyter notebook `explore_model_instance.ipynb` to explore these files
Sets the default suffixes to ['dual','rc'] so that the dual values and reduced costs are included by default

Other updates:
- changes the default solver from glpk to cbc


-------------------------------------------------------------------------------
Commmit 2021.08.09 (Version 0.1.0)
-------------------------------------------------------------------------------
Fixes #5
Implements a new semantic versioning scheme that replaces the versioning used by the original Switch model. 

Updates:
 - Sets the new version number at 0.1.0
 - updates `generate_inputs_file.py` to read the version number from `version.py` and use to generate the `switch_inputs_version.txt` file
 - removes all of the modules in `switch_model.upgrade` and any references to these modules in other scripts
 - updates `run_scenarios.ipynb` to validate that the version number used to generate the input files matches the version number used to run the model. Also removes the requirement to specify the timezone (instead read from the model_inputs.xlsx file)


-------------------------------------------------------------------------------
Commmit 2021.07.08
-------------------------------------------------------------------------------
Fixes #2
Character decode error when installing switch was due to right double quotation mark character copied and pasted from internet
in README.md file. Replaced with a normal " character. 

-------------------------------------------------------------------------------
Commmit 2021.07.07
-------------------------------------------------------------------------------
Updated README to include collaboration instructions.
Added functionality and documentation to be able store the MODEL_RUNS directory outside of the repository (in Box for example)

-------------------------------------------------------------------------------
Commmit 2021.07.02
-------------------------------------------------------------------------------
Added a generic example scenario to the MODEL_RUNS directory for testing model functionality.
Update development TODO.

-------------------------------------------------------------------------------
Commmit 2021.06.22
-------------------------------------------------------------------------------
Updated how excess renewable energy (RECs) are calculated. 

-------------------------------------------------------------------------------
Commmit 2021.06.10
-------------------------------------------------------------------------------
Updated how excess generation and the annual renewable energy percentage are 
calculated in `summary_report.ipynb`

Previously, excess generation was calculated as:

  Total Generation (excluding storage dispatch) - (Total Load + Total Storage Charging)

However, in certain cases, this would result in no excess generation, even if 
generation exceeded load both in a time-coincident manner and an annual volumetric manner.

Now, there are two excess generation metrics implemented:

  Excess Time-coincident generation = Total Generation and storage discharge - Total time-coincident generation and storage discharge

  and

  Excess Volumetric Generation = Total Generation and storage discharge - Total Load and storage charging

This also lead to a realization about how the annual volumetric % renewable was being calculated.
Previously, it had been:

 Annual % Renewable = Total Renewable Generation / Total Load (excluding storage charging and discharging)

However, if storage is part of the energy mix, it should be counted somewhere. I realized, however, that there
are multiple ways to treat storage in this calculation, which could lead to different results. For now, I have settled
on treating storage as a supply-side resource that affects net generation where:

  Net Generation = Renewable Generation - Storage Charging + Storage Discharging

  and thus

  Annual % renewable = Net Renewable Generation / Total Load

-------------------------------------------------------------------------------
Commmit 2021.06.02
-------------------------------------------------------------------------------
Fixed indentation error in summary_report.ipynb that was preventing the report from running.

Added `Model_Formation.pdf` which describes the mathematical formulation of the model for reference.

-------------------------------------------------------------------------------
Commmit 2021.05.24
-------------------------------------------------------------------------------
Fixed an issue where the summary_report.ipynb was not generating the cost summary table.

summary_report.ipynb will now export a csv file into each output folder called total_cost_of_energy.csv
This file summarizes the cost components and total cost of energy for the scenario.

Fixed the scenario_summary.csv output so that all outputs are correct.

Added `manually_run_reports.py` to switch_model/reporting. If you have already run a scenario and need 
to manually re-run all of the reporting, run this python file from your IDE, replacing the filepath with
the filepath of the scenario for which you want to re-run the reports. This will re-copy summary_report.ipynb
from the reporting directory to the input folder, which is useful in cases when the summary report template has 
been updated from GitHub. 


-------------------------------------------------------------------------------
Commmit 2021.03.26
-------------------------------------------------------------------------------
Addressed errors in summary_report.ipynb and summary_report_public.ipynb that were
preventing report completion. 

-------------------------------------------------------------------------------
Commmit 2021.03.24
-------------------------------------------------------------------------------

This update addresses issues with the costs included in the objective function and how generation is dispatched

In order to reduce the model dimensionality and to align better with actual generator
operations, we do not want to dispatch variable generation. Instead, generation should
be a function of built capacity and the variable capacity factor. This means that there
will no longer be a distinction between DispatchGen and ExcessGen.

However, in the future, if we want to be able to model dispatchable generation, we still want
to keep DispatchGen as a decision variable for dispatchable generation

This means that we created a new set of generators DISPATCHABLE_GENS, which will continue
to use the DispatchGen decision variable. Additionally, we will track generation from VARIABLE_GENS
with a new expression VariableGen, which will also be considered a zone power injection.

We will deleted ExcessGen, which has several impacts:
  - Previously we constrained that total storage charging had to be less than excess gen. However,
    now we can still achieve the same outcome through the load balance constraint (although technically
    storage charging could be met by storage discharging, which we will need to watch).
  - We also said that the hybrid storage charging would need to be less than the excess generation from the 
    paired generator. However, as long as the charging isn't greater than the overall variable generation
    from the paired generation and the load balance constraint still holds, we should be okay
  - The way that we track the cost of excess generation will also need to change. Going forward, the cost of excess
    generation will be not be tracable to a specific generator. Instead, re-selling excess generation would have to be
    a shaped product that represents a mix of different carbon-free sources

We also updated the load balance constraint to allow for generation to exceed load in each time period. 
Instead of Injections == Withdrawals, the load balance constraint is now Injections >= Withdrawals

With regards to nodal costs, we had previously been including the DLAP load cost and the Pnode revenue from dispatched
generation (not excess generation) in the objective function. We only included revenue from dispatched generation as
a disincentive to overbuild generation. Instead of DLAP load cost and Dispatched Pnode Revenue, we now include a term for 
congestion costs, which is defined as teh difference between the Pnode price and hte DLAP price. Although this term is optimized
for, it does not appear in the final delivered cost of energy, because in the case of excess generation, the buyer would not actually
pay the delivery cost for excess generation. For the purposes of calculating the delivered cost of energy, we still included the DLAP 
load cost (for consumed energy) and the Pnode revenue for all generation. 

Other Updates
- Rename variable "DispatchStorage" with "DischargeStorage"
- Remove generators.core.commit modules
- Update generators.extensions.congestion_pricing.py
  - Remove "DLAPLoadCostInTP" from objective function
  - Add congestion costs to objective function
  - Add output for nodal costs in each timepoint, including overprocured load cost
- Moved all fuel-based dispatch parameters (including CCS) to a new module generators.extensions.gen_fuel_costs
- Updated summary reports to reflect updated output files
- Fixed bug where model failed to construct RA parameters due to missing index information

-------------------------------------------------------------------------------
Switch 2.0.5
-------------------------------------------------------------------------------
This release standardizes all inputs and outputs as .csv files.

As usual, when  you first solve an older model, Switch will prompt to backup and
upgrade the  inputs directory. If you accept, it will convert the existing
tab-delimited *.tab files and most ampl-format *.dat files to comma-delimited
*.csv files. It is recommended that you update your model data preparation
scripts to create .csv files directly. Note that non-indexed parameters should
now be stored in .csv files with a header row listing the parameter names and a
single data row showing their values.

All multi-value outputs from Switch are also now in comma-delimited .csv files,
instead of a mix of .csv, .tab and .txt files. (total_cost.txt is unchanged)

This release also includes includes the following minor updates:

- Updated installation instructions
- Switch version number and website are now shown in the startup banner when
  running with --verbose flag; solve messages have also been improved slightly
- Some parsing errors for *.tab files have been fixed in the upgrade scripts;
  this may cause errors during the upgrade process for input files that use
  spaces instead of tabs and were previously upgraded by Switch, producing
  malformed files.
- Fixed several bugs in the documentation and execution of the stochastic
  examples that use the PySP module of the Pyomo package

-------------------------------------------------------------------------------
Switch 2.0.4
-------------------------------------------------------------------------------

This release introduces compatibility with Python 3. As of version 2.0.4, Switch
can now be run with either Python 2.7 or Python 3 (likely to work with 2.7.10+;
has been tested on 2.7.16 and 3.7.3).

This release will prompt to upgrade your model inputs directory, but the only
change it makes is to update switch_inputs_version.txt to 2.0.4.

This release includes the following updates:

- Code has been updated in many places to achieve Python 2/3
  cross-compatibility. Future contributors should ensure that their code is
  compatible with both Python 2 and 3 (e.g., use
  switch_model.utilities.iteritems(dict) instead of dict.iteritems(), be
  prepared for results from dict.keys(), dict.vars(), map(), range(), zip(),
  etc., to be either generators or lists, and use `from __future__ import
  division` whenever doing division).
- Installation instructions in INSTALL have been updated. We now recommend that
  users install dependencies using the conda command first, then install Switch
  using pip. This follows practices recommended in
  https://www.anaconda.com/using-pip-in-a-conda-environment/ and should minimize
  problems caused by incompatibilities between conda and pip.
- Output files (.csv, .tab, .tsv, and .txt) are now consistently written using
  the local system's line endings (LF on Mac or Linux, CRLF on Windows).
  Previously, most of these were written with only LF line endings on Windows.
- A bug was fixed in switch_model.transmission.local_td that prevented the
  carrying cost of Legacy local T&D capacity from being included in the
  objective function. As a result, users of this module will find that Switch
  now reports higher total costs than previously. However, this should not
  affect any of the decisions that Switch makes.
- To make switch_model.transmission.local_td module compatible with Python 3,
  "Legacy" was removed from the list of build years for local T&D capacity
  (Pyomo sorts index keys when solving the model, and Python 3 cannot sort lists
  that mix strings and numbers). Legacy capacity is now read directly from the
  existing_local_td[z] parameter when needed. This does not change the behavior
  of Switch, but "Legacy" rows are no longer written to the BuildLocalTD.tab
  output file. The LOCAL_TD_BLD_YRS set has also been removed. LOAD_ZONES *
  PERIODS can be used instead.
- A new indexed set, CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p] has been added.
  This is useful for simple online capacity calculations for assets that cannot
  be retired during the study (e.g., AssetCapacity[p] = sum(BuildCapacity[v] for
  v in CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]))
- Code has been cleaned up a bit internally (e.g., removed trailing whitespace,
  changed "SWITCH" or "SWITCH-Pyomo" to "Switch")

-------------------------------------------------------------------------------
Switch 2.0.3
-------------------------------------------------------------------------------

- Users can now provide data in variable_capacity_factors.tab and
  hydro_timeseries.tab for times before projects are built or after they are
  retired without raising an error. However, the extra datapoints will be
  ignored.
- Various parts of the code have better formatting, documentation and
  performance.
- switch_model.hawaii.smooth_dispatch is now compatible with Pyomo 5.6 and
  later.
- A new '--exact' option in switch_model.hawaii.rps forces the system to
  exactly meet the RPS target and no more. This is useful for studying the cost
  of adopting various levels of renewable power, including levels below the
  least-cost system design (i.e., cases where low shares of renewable power
  cause higher system costs).
- A bug was fixed when calculating the cost of water spillage in
  switch_model.generators.extensions.hydro_system.
- Final reservoir level in switch_model.generators.extensions.hydro_system
  is now stored in a varaible called ReservoirFinalVol. The ReservoirSurplus
  variable has been eliminated.
- Bounds on a number of inputs have been relaxed to allow unusual or edge cases.
  In particular, a number of variables can now be zero instead of strictly
  positive. This allows zero costs, zero capacity limits, zero-based year
  counting, etc.
- The  gen_is_baseload parameter is now optional, with a default value of False
  (0).
- NEW_TRANS_BLD_YRS has been renamed to TRANS_BLD_YRS.
- setup.py now lists an optional dependency on rpy2<3.9 instead of rpy2, because
  later versions of rpy2 require Python 3, which Switch doesn't support yet.
  This only affects the iterative demand response module.
- A new GENS_BY_ENERGY_SOURCE set can be used to identify all the generators
  that use any energy source, either a fuel or a non-fuel energy source.
  GENS_BY_FUEL and GENS_BY_NON_FUEL_ENERGY_SOURCE also still exist.
- We have begun migrating toward using `initialize` instead of `rule` when
  initializing Pyomo components, and recommend that users do the same in their
  custom modules. This matches the current Pyomo API documentation. `rule` also
  works for now, but `initialize` should be more future proof.
- The discrete-build requirement is now enforced on generators with
  predetermined build quantities, in addition to optimized generators.
- The optional psycopg2 dependency has been changed to psycopg2-binary.
- The --debug option now uses the ipdb debugger if available; otherwise it falls
  back to pdb.

-------------------------------------------------------------------------------
Switch 2.0.2
-------------------------------------------------------------------------------

- General
    - Added --assign-current-version argument to `switch upgrade`. This is
      useful for updating version number in example directories to match
      current version of Switch, even if the data files don't need an upgrade.

- Hawaii regional package
    - Fixed bug in hawaii.rps that would crash `switch solve --help`.

-------------------------------------------------------------------------------
Switch 2.0.1
-------------------------------------------------------------------------------

- General
    - Switch is now compatible with Pyomo 5.6+ (in addition to earlier
      versions).
    - A new --no-post-solve option prevents all post-solve actions (e.g., saving
      variable results).
    - If the user specifies --reload-prior-solution, Switch now behaves as if it
      had just solved the model, i.e., after loading the solution, it runs post-
      solve code unless --no-post-solve is specified (useful for re-running
      reporting code), and it only drops to an interactive Python prompt if the
      user also specifies --interact.
    - A new --no-save-solution disables automatic solution-saving. This saves
      time and disk space for models that won't need to be reloaded later.
    - New --quiet and --no-stream-solver arguments cancel --verbose and
      --stream-solver.
    - A new "--save-expression[s] <name1> <name2> ..." argument can be used to
      save values for any Pyomo Expression object to a .tab file after the model
      is solved (similar to the automatic saving of variable values). This also
      works for Param objects.
    - The --include-module(s), --exclude-module(s), --save-expression(s),
      --suffix(es) and --scenario(s) flags can now be used repeatedly on the
      command line, in options.txt or in scenarios.txt. The include and exclude
      options will be applied in the order they are encountered, in options.txt,
      then scenarios.txt, then the command line.
    - A new --retrieve-cplex-mip-duals flag can be used to support retrieving
      duals for a MIP program from the cplex solver (users must also turn on the
      "duals") suffix. This flag patches the Pyomo-generated cplex command
      script to pass the "change problem fix" command to the solver and then
      solve a second time. This fixes integer variables at their final values,
      then re-solves to obtain duals. This flag is not needed with the cplexamp
      solver.
    - A new balancing.demand_response.iterative module has been added. This was
      formerly in the Hawaii regional package. This module performs iterative
      solutions with any convex demand system, based on a bid-response process.
    - New indexed sets have been added to allow efficient selection of groups of
      generators that use a particular technology, fuel or non-fuel energy
      source: GENS_BY_TECHNOLOGY, GENS_BY_FUEL, GENS_BY_NON_FUEL_ENERGY_SOURCE.
    - Generator capacity data is saved to gen_cap.tab instead of gen_cap.txt and
      rows are sorted if user specifies --sorted-output.
    - Even if a model has solver warnings, results will be reported and
      post-solve will be performed if a valid solution is available.
    - A more descriptive warning is given when switch_model.reporting finds an
      uninitialized variable.
    - A warning is given about potential errors parsing arguments in the form
      "--flag=value". Python's argument parsing module can make mistakes with
      these, so "--flag value" is a safer choice.
    - Switch now monkeypatches Pyomo to accelerate reloading prior solutions.
      Previously Pyomo 5.1.1 (and maybe others) took longer to load prior
      solutions than solving the model.
    - At startup, "switch solve-scenarios" will restart jobs that were
      previously interrupted after being started by the same worker (same
      --job-id argument or SWITCH_JOB_ID environment variable). Note that
      workers automatically pull scenarios from the scenario list file until
      there are none left to solve, and avoid solving scenarios that have been
      pulled by other workers. Each worker should be given a unique job ID, and
      this ID should be reused if the worker is terminated and restarted. The
      new behavior ensures that jobs are not abandoned if a worker is restarted.

- Upgrade scripts
    - The upgrade scripts now report changes in module behavior or renamed
      modules while upgrading an inputs directory. This only reports changes to
      modules used in the current model.
    - The hawaii.reserves module is automatically replaced by
      balancing.operating_reserves.areas and
      balancing.operating_reserves.spinning_reserves in the module  list.
    - The hawaii.demand_response module is replaced by
      balancing.demand_response.iterative and hawaii.r_demand_system is replaced
      by balancing.demand_response.iterative.r_demand_system in the module list.
    - "switch_mod" will not be changed to "switch_modelel" if a module file is
      upgraded from 2.0.0b1 to 2.0.0b2 twice.

- Hawaii regional package
    - The hawaii.reserves module has been deprecated and the
      hawaii.demand_response module has been moved (see upgrade scripts)
    - Switch now places limits on down-reserves from pumped-storage hydro.
    - A new --rps-prefer-dist-pv option for hawaii.rps will prevent construction
      of new large PV until 90% of distributed PV potential has been developed.
    - Limits on load-shifting between hours in hawaii.demand_response_simple
      have been formalized.
    - The Hawaii storage energy cost calculation has been fixed.
    - Total production by energy source is reported by hawaii.save_results,
      ad-hoc technologies are added to production_by_technology.tsv, and
      hourly dispatch is disaggregated by non-fuel technologies.
    - Bugs have been fixed in reserve calculation for EVs and in
      hawaii.smooth_dispatch and hawaii.scenario_data.
    - hawaii.smooth_dispatch minimizes total inter-hour change instead of square
      of levels. The old quadratic smoothing method has been moved to
      hawaii.smooth_dispatch.quadratic (slow and possibly buggy).
    - The must-run requirement in hawaii.kalaeloa is turned off when RPS or EV
      share is above 75% (can be overridden by --run-kalaeloa-even-with-high-rps)
    - Support for nominal-dollar fuel price forecasts has been dropped from
      hawaii.scenario_data
    - A new --no-hydrogen flag can be used to deactivate the hydrogen module.
    - The hawaii.ev_advanced module now calculates vehicle fleet emissions.

-------------------------------------------------------------------------------
Switch 2.0.0
-------------------------------------------------------------------------------

First public release of Switch 2. This uses a similar framework to Switch 1,
but with numerous improvements. The most significant are:

- Written in Python instead of AMPL language
- Modular approach, so components can be easily added or removed from model
- Modeling of unit commitment and part load heat rates (optional)
- Generalization of sample timeseries to have arbitrary length instead of single
  days
- Standardized reporting, e.g., automatic export of all variable values
