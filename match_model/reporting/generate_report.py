# Copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

import os
import shutil


def post_solve(instance, outdir, inputs_dir):
    """
    Runs the summary report
    """
    # get the name of the scenario
    scenario = str(outdir).split("/")[-1]

    # shutil.copy('../reporting/summary_report.ipynb', inputs_dir)

    # run the notebook
    try:
        os.system(
            f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb'
        )
    # if the kernel doesnt respond, try re-running the notebook
    except RuntimeError:
        print("Jupyter Kernel did not respond, retrying running the notebook")
        os.system(
            f'jupyter nbconvert --ExecutePreprocessor.kernel_name="python3" --to notebook --execute --inplace {inputs_dir}/summary_report.ipynb'
        )
    # convert the notebook to html and save it to the output directory
    os.system(
        f"jupyter nbconvert --to html --no-input --no-prompt {inputs_dir}/summary_report.ipynb --output-dir {outdir}/../../summary_reports --output summary_report_{scenario}"
    )
    # delete the notebook from the inputs directory
    os.remove(f"{inputs_dir}/summary_report.ipynb")
