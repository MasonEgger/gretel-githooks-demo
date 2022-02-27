from getpass import getpass
import os
import glob
import json
import hashlib
import pandas as pd
from gretel_client import configure_session, ClientConfig, get_project
from gretel_client.helpers import poll

PROJECT_NAME = os.getenv("GRETEL_PROJECT_NAME", None)
if PROJECT_NAME is None:
    PROJECT_NAME = getpass("Gretel Project Name: ")

MODEL_ID = os.getenv("GRETEL_MODEL_ID")
if PROJECT_NAME is None:
    PROJECT_NAME = getpass("Gretel Model ID: ")

GRETEL_TOKEN = os.getenv("GRETEL_TOKEN")
if PROJECT_NAME is None:
    PROJECT_NAME = getpass("Gretel API Token: ")


def write_gretel_transform(csvs):
    with open(".gretel_transforms.json", "w") as fh:
        fh.write(json.dumps(csvs))


def find_csvs(excluded_dirs=["./venv", "./conda"]):
    """
    Use glob to find all csv files recursively, then remove any csvs found
    within the excluded directories.

    numpy includes csvs in their tests in the venv. We don't commit the venv
    and we don't want to mess with thos files, so  ignore them.
    """
    directory = "./"
    pathname = directory + "/**/*.csv"
    files = glob.glob(pathname, recursive=True)
    valid_files = []
    for file in files:
        exclude_count = 0
        for dir in excluded_dirs:
            if file.startswith(dir):
                exclude_count += 1
        if exclude_count == 0:
            valid_files.append(file)

    return valid_files


def sha256_large_file(filename, BUF_SIZE=65536):
    """
    Get the SHA of a large file so we can detect when the file changes.

    First, we have to use a binary string for the hashlib libraries, hence
    opening the file as "rb". Also, in an attempt to not overload the resources
    of our workstations, set a reasonable buffer size. Currently set to 64k.
    """

    sha256 = hashlib.sha256()
    with open(csv, "rb") as fh:
        while True:
            data = fh.read(BUF_SIZE)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()


def transform_csv(csv, project):
    """
    Use a pre-trained model in Gretel to transform and redact any PII found in
    any CSV file in the repository.
    """
    model = project.get_model(model_id=MODEL_ID)
    record_handler = model.create_record_handler_obj()
    record_handler.submit(
        action="transform",
        data_source=csv,
        upload_data_source=True,
    )
    poll(record_handler)

    # use pandas to read the CSV since it can easily handle compression
    transformed = pd.read_csv(
        record_handler.get_artifact_link("data"), compression="gzip"
    )
    transformed.to_csv(f"{csv}", index=False)


if __name__ == "__main__":
    # Initial Setup for Gretel. Check the environment for our token, otherwise prompt
    configure_session(
        ClientConfig(api_key=GRETEL_TOKEN, endpoint="https://api.gretel.cloud")
    )

    # Get the gretel project we've already created
    project = get_project(name=PROJECT_NAME, display_name=PROJECT_NAME, create=True)

    # Find CSVs in our repo
    csvs = find_csvs()

    # Define dict for CSVs to write
    csvs_to_write = {}

    # Check and see if we alrady have run the precommit once.
    if os.path.exists(".gretel_transforms.json"):
        # Keeping track of how many files we've acted on.
        num_csvs = 0
        with open(".gretel_transforms.json", "r") as fh:
            prior_csvs = json.loads(fh.read())

        for csv in csvs:
            current_sha256 = sha256_large_file(csv)
            stored_csv = prior_csvs.get(csv, None)

            # If we don't have a record of the CSV, then it's new and we should
            # transform
            if stored_csv is None:

                print(f"{csv} has not been previously transformed. Running...")

                transform_csv(csv, project)

                print(f"{csv} transform done.")

                csvs_to_write[csv] = sha256_large_file(csv)
                num_csvs += 1
            elif stored_csv != current_sha256:
                # If the SHA we have doesn't match the newly computed SHA,
                # then the file has changed and we need to re-run transform

                print(
                    f"{csv} has changed since the last commit, re-running transform to prevent accidental leak of PII"
                )

                transform_csv(csv, project)

                print(f"{csv} transform done.")

                csvs_to_write[csv] = sha256_large_file(csv)
                num_csvs += 1
            else:
                # If the files haven't been changed, we don't need to do anything
                # but ensure it is still in the file.
                csvs_to_write[csv] = current_sha256
        if num_csvs > 0:
            print(
                f"{num_csvs} csvs were detected and transformed to prevent accidental leak of PII. \nThe current commit has been canceled. \nYou will need to commit again."
            )
            write_gretel_transform(csvs_to_write)
            exit(1)

    else:
        # This will be run if no config is detected, meaning we've never run
        # this before.
        csv_shas = {}
        for csv in csvs:
            transform_csv(csv, project)
            csv_shas[csv] = sha256_large_file(csv)

        if len(csvs) > 0:

            print(
                f"{len(csvs)} csvs were detected and transformed to prevent accidental leak of PII. \nThe current commit has been canceled. \nYou will need to commit again and add .gretel.transforms.json to the commit"
            )

            write_gretel_transform(csv_shas)
            exit(1)
