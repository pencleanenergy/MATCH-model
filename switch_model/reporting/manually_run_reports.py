#%%
# Copyright (c) 2021 The MATCH Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This script is used for testing and debugging the process of running and saving the summary report jupyter notebooks
"""

import os
import shutil
import pandas as pd

# modify the file path to the name of the scenario for which you want to re-run the reporting
run_folder = '../../MODEL_RUNS/historical_validation'
#run_folder = '../../../../Box/Supply/24x7 Time-Coincident Work/MODEL_RUNS/test'

scenarios = os.listdir(f'{run_folder}/outputs')

#scenarios = ['base_100']

for s in scenarios:
    inputs_dir = f'{run_folder}/inputs/{s}'
    outdir = f'{run_folder}/outputs/{s}'
    print(s)

    shutil.copy('summary_report.ipynb', inputs_dir)
    #shutil.copy('summary_report_public.ipynb', inputs_dir)

    os.system(f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb')
    os.system(f'jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir} --output summary_report_{s}')
    os.system(f'jupyter nbconvert --clear-output --inplace {inputs_dir}/summary_report.ipynb')



#%%
# TODO: Add this code to the end of the solve-scenarios script
#merge all of the scenario reports together
import os
import shutil
import pandas as pd

# modify the file path to the name of the scenario for which you want to re-run the reporting
run_folder = '../../MODEL_RUNS/smoothing_validation'

scenarios = os.listdir(f'{run_folder}/outputs')

i = 0
for s in scenarios:
    summary_file = f'{run_folder}/outputs/{s}/scenario_summary.csv'
    #buildgen_file = f'{run_folder}/outputs/{s}/BuildGen.csv'

    if i == 0:
        df = pd.read_csv(summary_file, index_col=0)
        """
        df_build = pd.read_csv(buildgen_file, usecols=['GEN_BLD_YRS_1','BuildGen'])
        df_build = df_build.rename(columns={'GEN_BLD_YRS_1':'generation_project','BuildGen':s})
        """
        i += 1
    else:
        df2 = pd.read_csv(summary_file, index_col=0)
        df = df.merge(df2, how='outer', left_index=True, right_index=True, sort=False)
        """
        df_build2 = pd.read_csv(buildgen_file, usecols=['GEN_BLD_YRS_1','BuildGen'])
        df_build2 = df_build2.rename(columns={'GEN_BLD_YRS_1':'generation_project','BuildGen':s})
        df_build = df_build.merge(df_build2, how='outer', on='generation_project')
        """

#df = df.reset_index()
#df['index'] = [i.split('~')[1] for i in df['index']]
#df = df.set_index('index')

df.to_csv(f'{run_folder}/outputs/scenario_comparison.csv')
#df_build = df_build.fillna('N/A')
#df_build.to_csv(f'../../{run_folder}/outputs/portfolio_comparison.csv', index=False)



# %%
