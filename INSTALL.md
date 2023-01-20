# Introduction

This repository contains code and example files for the Switch power system
planning model. Switch is written in the Python language and several other
open-source projects (notably Pyomo, Pandas and glpk). The instructions below
show you how to install  these components on a Linux, Mac or Windows computer.

We recommend that you use the Anaconda scientific computing environment to
install and run Switch. This provides an easy, cross-platform way to install
most of the resources that Switch needs, and it avoids interfering with your
system's built-in Python installation (if present). The instructions below
assume you will use the Anaconda distribution. If you prefer to use a different
distribution, you will need to adjust the instructions accordingly. In
particular, it is possible to install Switch and most of its dependencies using
the pip package manager if you have that installed and working well, but you
will need to do additional work to install glpk or coincbc, and possibly git.

# Install Conda and Python

Download and install Miniconda from
https://docs.conda.io/en/latest/miniconda.html or Anaconda from
https://www.anaconda.com/distribution . We recommend using the 64-bit version
with Python >3.7. Anaconda and Miniconda install a similar environment, but
Anaconda installs more packages by default and Miniconda installs them as
needed.

Note that you do not need administrator privileges to install the Windows Conda
environment or add packages to it if you select the option to install "just for
me".

# Install a code editor

A code editor, also known as an integrated development environment (IDE) will 
be required to open and run the Jupyter Notebooks used in this model.

We use Visual Studio Code (download: https://code.visualstudio.com/), because it
allows you to open Jupyter notebooks, and it is free, but most IDEs will work. 

NOTE: If you only plan on running models and never modifying the source code, you
can just use jupyter notebook instead of installing an IDE. If you installed the full
Anaconda installation, Jupyter Notebook should come installed. If you are using miniconda,
you will need to manually install jupyter notebook by opening Anaconda prompt and typing:

    conda install jupyter
    
To launch the jupyter notebook app in your browser, you would just open anaconda and type

    jupyter notebook

# Install and setup git software manager
After installing Anaconda or Miniconda, open an Anaconda Command Prompt
(Windows) or Terminal.app (Mac) and type the following command:

    conda install git
    
Or you can install Git Bash from https://git-scm.com/downloads

Then you will need to open Git Bash and set up git following these instructions: https://docs.github.com/en/get-started/quickstart/set-up-git

# Download the codebase to a local repository
Then, in a terminal window or Anaconda command prompt Anaconda command prompt,
use the `cd` and `mkdir` commands to create and/or enter the directory (e.g. "Users/myusername/GitHub") where you
would like to store the MATCH model code and examples.

    git clone https://github.com/grgmiller/MATCH-model.git

# Setup the conda environment
This will install all of the package dependencies needed to run MATCH. Use `cd` to navigate to the directory where your local files are stored (e.g. "GitHub/MATCH-model")

    conda env create -f environment.yml

Activate the new environment

    conda activate match_model

# Install the match_model package
This will install the local codebase as match_model
    
    pip install --upgrade --editable .

# Download your solver
For open-source solvers, we recommend using CBC.

You can download the CBC solver executable from https://ampl.com/products/solvers/open-source/. You will need to create an account to download the file.

Once the CBC is downloaded and unzipped, move cbc.exe to the "MATCH-model" directory. 

# Install a Proprietary Solver (Optional)

To solve larger models, you will need to install the cplex or gurobi solvers,
which are an order of magnitude faster than glpk or coincbc. Both of these have
free trials available, and are free long-term for academics. You can install
one of these now or after you install MATCH. More information on these solvers
can be found at the following links:

Professional:
- https://www.gurobi.com/products/gurobi-optimizer/
- https://www.ibm.com/products/ilog-cplex-optimization-studio/pricing

Academic:
- https://www.gurobi.com/academia/
- https://developer.ibm.com/docloud/blog/2019/07/04/cplex-optimization-studio-for-students-and-academics/

For any meaningful-sized problem, you will need the unlimited-size versions of
these solvers, which will require either purchasing a license, using a
time-limited trial version, or using an academic-licensed version. The
small-size free or community versions (typically 1000 variables and constraints)
will not be enough for any realistic model.
