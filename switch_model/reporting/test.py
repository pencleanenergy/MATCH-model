#%%
import os

#scenarios = os.listdir('C:/Users/gmiller/switch/time_coincident_scenarios/inputs/')

scenarios = ['100_technology']

for s in scenarios:
    inputs_dir = f'C:/Users/gmiller/switch/time_coincident_scenarios/inputs/{s}'
    outdir = f'C:/Users/gmiller/switch/time_coincident_scenarios/outputs/{s}'
    print(s)

    os.system(f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb')
    os.system(f'jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir}')
    os.system(f'jupyter nbconvert --clear-output --inplace {inputs_dir}/summary_report.ipynb')

# need to specify outdir folder
# %%
import os

inputs_dir = f'C:/Users/gmiller/switch/time_coincident/inputs'
outdir = f'C:/Users/gmiller/switch/time_coincident/outputs'

os.system(f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb')
os.system(f'jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir}')
os.system(f'jupyter nbconvert --clear-output --inplace {inputs_dir}/summary_report.ipynb')
# %%
