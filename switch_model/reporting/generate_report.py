# Copyright (c) 2021 Gregory J. Miller. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

import os

def post_solve(instance, outdir, inputs_dir):

    print(outdir)
    s = str(outdir).split('/')[-1]
    os.system(f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb')
    os.system(f'jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir} --output summary_report_{s}')
    os.system(f'jupyter nbconvert --clear-output --inplace {inputs_dir}/summary_report.ipynb')