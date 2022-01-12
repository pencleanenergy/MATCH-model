This contains "MATCH", a time-coincident renewable energy portfolio
planning model that is derived from version 2 of the Switch electricity planning model.

To generate documentation, go to the doc folder and run ./make_doc.sh.
This will build html documentation files from python doc strings which
will include descriptions of each module, their intentions, model
components they define, and what input files they expect.

# INSTALLATION

See "INSTALL.md" for instructions on how to download and install MATCH on your machine. 

# DIRECTORY STRUCTURE
```
📦match_model
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

4. Run the model
In the same `run_scenarios.ipynb`, follow the directions under the "Solve Model Scenarios" heading to run the scenarios.

5. Examine the results
Results for each scenario will be saved to the `outputs` directory. The main output files to examine are the inteactive HTML output reports, 
but tabular output data is also saved to individual csv files in the output folder. There are also csv files in the main outputs directory that
provide quick side-by-side comparisons of all scenarios. 

# KEEPING THE CODE UPDATED
From time to time, the code will be updated on GitHub. To ensure that you are keeping your local version of the code up to date, open git bash and follow these steps:
	
	# change the directory to whereever your local git repository is saved
	# after hitting enter, it should show the name of the git branch (e.g. "(master)")
	cd GitHub/match_model  

	# save any changes that you might have made locally to your copy of the code
	git add .

	# fetch and merge the updated code from github
	git pull origin master

Your local copy of the code should now be up to date. 
NOTE: If you've pulled updates to the summary reports that you want to re-run for existing model runs, you will need to use `manually_run_reports.py` in `match_model/reporting`

# COLLABORATING
If you plan on contributing edits to the codebase that will be merged into the master branch, please follow these best practices:

1. Please do not make edits directly to the master branch. Any new features or edits should be completed in a new branch. To do so, open git bash, navigate to your local repo (e.g. `cd GitHub/match_model`), and create a new branch, giving it a descriptive name related to the edit you will be doing:

	`git checkout -b branch_name`

2. As you code, it is a good practice to 'save' your work frequently by opening git bash, navigating to your local repo (`cd GitHub/match_model`), making sure that your current feature branch is active (you should see the feature name in parentheses next to the command line), and running 
	
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
NOTE: The run_tests.py module has not been tested with MATCH
To test the entire codebase, run this command from the root directory:

	python run_tests.py
