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
 ┣ 📂notebooks
 ┃ ┣ 📜run_scenarios.ipynb: Used to populate inputs and run scenarios
 ┃ ┣ 📜manually_run_summary_reports.ipynb: Used to manually re-run summary reports for solved model run
 ┃ ┗ 📜explore_model_instance.ipynb: Used to explore model instance for debugging
 ┣ 📂balancing
 ┃ ┣ 📜load_zones.py: defines load zones, including the supply/demand balancing constraint
 ┃ ┣ 📜system_power.py: defines system power use and cost
 ┃ ┣ 📜excess_generation.py: defines limits on excess generation  
 ┃ ┗ 📜renewable_target.py: defines renewable energy % goals
 ┣ 📂generators
 ┃ ┣ 📜build.py: defines how to build/select projects
 ┃ ┣ 📜dispatch.py: defines how to dispatch generators in each timepoint
 ┃ ┣ 📜gen_discrete_build.py: forces discrete increments of a project to be built (e.g. 1 MW chunks) (optional)
 ┣ 📂optional
 ┃ ┣ 📜emissions_optimization.py: co-optimizes the consequential emissions impact of the portfolio
 ┃ ┣ 📜wholesale_pricing.py: adds nodal pricing dynamics to the model
 ┃ ┣ 📜resource_adequacy.py: defines RA requirements and positions according to the current rules in CA
 ┗ ┗ 📜storage.py: defines how to build and dispatch energy storage 
 ┣ 📂reporting
 ┃ ┣ 📜generate_report.py: runs the summary reports as part of the model post-solve
 ┃ ┣ 📜report_functions.py: defines the functions that are run in summary_report.ipynb
 ┃ ┣ 📜summary_report.ipynb: jupyter notebook template for interactive summary of results
 ┣ 📜financials.py: defines financial parameters and the objective function
 ┣ 📜generate_input_files.py: creates input files from model_inputs excel spreadsheet
 ┣ 📜main.py: Allows the model to be used via the command line
 ┣ 📜solve.py: solves each model run
 ┣ 📜solve_scenarios.py: defines functions for solving multiple scenarios in parallel
 ┣ 📜timescales.py: defines the timescales used in the model
 ┣ 📜utilities.py: utility functions for MATCH
 ┗ 📜version.py: defines the current model version number
```

# CONFIGURING MODEL RUNS


1. Determine where you want all of your model runs to be stored.
Your can use the default `MODEL_RUNS` folder in your github repository, or you can create a folder somewhere else on your computer. 
We do not recommend creating this folder within Box Drive or similar cloud storage location.

2. Create a folder to store your model run files.
Create a new subfolder within `MODEL_RUNS` or your other local folder for storing model runs. This can be named whatever you would like,
for example `model_1`. Copy the `model_inputs.xlsx` template into this model folder.

2. Enter your data inputs into the spreadsheet
In the `model_inputs` excel spreadsheet, you will find tabs for different types of input data. 
The spreadsheet contains some placeholder data that you can write over. You can configure multiple scenarios within a single inputs spreadsheet. 

3. Generate model input files
Open the `run_scenarios` jupyter notebook from the `match_model/notebooks` directory in your preferred jupyter notebook viewer.
Follow the directions for each cell. You will need to input the file location of your model run folder into one of the cells.
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

