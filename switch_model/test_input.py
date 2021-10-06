# %%

import multiprocessing as mp
import os
from pathlib import Path
import generate_input_files
import shutil


model_runs_folder = '../MODEL_RUNS'

model_run_name = 'smoothing_validation'

model_workspace = Path.cwd() / f'{model_runs_folder}/{model_run_name}'

# check if the directory exists
if os.path.exists(model_workspace / 'inputs'):
    # check that an inputs version file exists
    if os.path.exists(model_workspace / 'inputs_version.txt'):
        # get the version number
        with open(model_workspace / 'inputs_version.txt', 'r') as i:
            inputs_version = i.read()
        # get the current version number
        version_path = Path.cwd() / 'version.py'
        version = {}
        with open(version_path) as f:
            exec(f.read(), version)
        version = version['__version__']
        # check if the versions match
        if version == inputs_version:
            print(f'Input files already generated with current software version ({version})')
        else:
            print(f'Inputs were generated using version {inputs_version}. Current version is {version}')
            print('Removing old files and re-generating inputs with current version. Please wait...')
            old_files = os.listdir(model_workspace)
            old_files.remove('model_inputs.xlsx')
            for f in old_files:
                try:
                    os.remove(model_workspace / f)
                except PermissionError:
                    shutil.rmtree(model_workspace / f)
            generate_input_files.generate_inputs(model_workspace)
    else: 
        print('Inputs were generated prior to version 0.1.0. Re-generating inputs now...')
        """
        old_files = os.listdir(model_workspace)
        old_files.remove('model_inputs.xlsx')
        for f in old_files:
            try:
                os.remove(model_workspace / f)
            except PermissionError:
                shutil.rmtree(model_workspace / f)
        """
        generate_input_files.generate_inputs(model_workspace)
# if the directory does not exist, generate the input files
else:
    print('Generating inputs now...')
    generate_input_files.generate_inputs(model_workspace)
