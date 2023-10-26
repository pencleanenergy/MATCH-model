import os, shutil


def refresh_folder(model_workspace, keep_files):
    # loop through all files and folders in model_workspace
    for file in os.listdir(model_workspace):
        # if the file is not in the keep_files list
        if file not in keep_files:
            # if the file is a folder
            if os.path.isdir(os.path.join(model_workspace, file)):
                # remove the folder and all its contents
                shutil.rmtree(os.path.join(model_workspace, file))
            # if the file is a file
            else:
                # remove the file
                os.remove(os.path.join(model_workspace, file))