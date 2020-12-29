#%%
import os
import shutil

scenarios = os.listdir('../../input_test/inputs/')

#scenarios = ['base_100']

for s in scenarios:
    inputs_dir = f'../../input_test/inputs/{s}'
    outdir = f'../../input_test/outputs/{s}'
    print(s)

    shutil.copy('summary_report.ipynb', inputs_dir)

    os.system(f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb')
    os.system(f'jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir} --output summary_report_{s}')
    os.system(f'jupyter nbconvert --clear-output --inplace {inputs_dir}/summary_report.ipynb')

# need to specify outdir folder
# %%
import os

inputs_dir = f'../../MODEL_RUNS/input_test/inputs/base_100_variant'
outdir = f'../../MODEL_RUNS/input_test/outputs/base_100_variant'

os.system(f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb')
os.system(f'jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir}')
os.system(f'jupyter nbconvert --clear-output --inplace {inputs_dir}/summary_report.ipynb')
# %%

scenarios = ['base_100_variant']

for s in scenarios:
    inputs_dir = f'C:/Users/gmiller/switch/input_test/inputs/{s}'
    outdir = f'C:/Users/gmiller/switch/input_test/outputs/{s}'

    test = str(outdir).split('/')[-1]
    print(test)
# %%

#merge all of the scenario reports together
import pandas as pd

scenarios = os.listdir('C:/Users/gmiller/switch/time_coincident_scenarios/outputs/')

i = 0
for s in scenarios:
    output_file = f'C:/Users/gmiller/switch/time_coincident_scenarios/outputs/{s}/scenario_summary.csv'

    if i == 0:
        df = pd.read_csv(output_file, index_col=0)
        i += 1
    else:
        df2 = pd.read_csv(output_file, index_col=0)
        df = df.merge(df2, how='left', left_index=True, right_index=True)

df.to_csv('C:/Users/gmiller/switch/time_coincident_scenarios/outputs/scenario_comparison.csv')
# %%
