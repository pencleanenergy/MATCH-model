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
with Python 3.7. Anaconda and Miniconda install a similar environment, but
Anaconda installs more packages by default and Miniconda installs them as
needed.

Note that you do not need administrator privileges to install the Windows Conda
environment or add packages to it if you select the option to install "just for
me".

If you want, this is a good point to create an Conda environment specifically
for using or testing Switch. See here for more details:
https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html


# Install git software manager.
After installing Anaconda or Miniconda, open an Anaconda Command Prompt
(Windows) or Terminal.app (Mac) and type the following command:
    conda install git

# Download the codebase to a local repository
Then, in a terminal window or Anaconda command prompt Anaconda command prompt,
use the `cd` and `mkdir` commands to create and/or enter the directory where you
would like to store the Switch model code and examples.

    git clone https://github.com/grgmiller/SWITCH247.git

# Setup the conda environment
This will install all of the package dependencies needed to run Switch 24x7. Use `cd` to navigate to the directory where your local files are stored

    conda env create -f environment.yml

Activate the new environment

    conda activate switch_247

# Install the switch package
This will install the local codebase as switch
    
    pip install --upgrade --editable .

# Download your solver
For open-source solvers, we recommend using COIN CBC.

You can download the CBC solver executable from https://ampl.com/products/solvers/open-source/

Once the CBC is downloaded and unzipped, move cbc.exe and coin-license.txt to the "switch_model" directory. 



# Install Switch and its Dependencies





# Install a Proprietary Solver (Optional)

To solve larger models, you will need to install the cplex or gurobi solvers,
which are an order of magnitude faster than glpk or coincbc. Both of these have
free trials available, and are free long-term for academics. You can install
one of these now or after you install Switch. More information on these solvers
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



