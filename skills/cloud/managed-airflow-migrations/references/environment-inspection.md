# Environment inspection & downloading files

## 1. List and Inspect Source Environment (Only when requested)

*Perform this step only if explicitly requested to do so.* Run the following
commands to list environments, get detailed configuration, and identify the
starting versions of your source environment (`<SOURCE_ENV>`) in region
`<SOURCE_REGION>`.

1.  **List Environments:** Identify the available Composer environments in your
    project.

    ```bash
    gcloud composer environments list \
        --locations=<SOURCE_REGION> \
        --format="table(name,location,state)"
    ```

    *Note: Always use the `--locations` flag (plural) for listing. You can omit
    `--locations` to list across all regions.*

2.  **Describe Environment:** Get the complete configuration details for a
    specific environment.

    ```bash
    gcloud composer environments describe <SOURCE_ENV> \
        --location <SOURCE_REGION>
    ```

    *Note: Always use the `--location` flag (singular) for describing a specific
    environment.*

3.  **Get Specific Configuration Details:** Extract specific fields from the
    environment description.

    *   **Get Image Version:**

        ```bash
        gcloud composer environments describe <SOURCE_ENV> \
            --location <SOURCE_REGION> \
            --format="value(config.softwareConfig.imageVersion)"
        ```

    *   **Get PyPI Packages:**

        ```bash
        gcloud composer environments describe <SOURCE_ENV> \
            --location <SOURCE_REGION> \
            --format="value(config.softwareConfig.pypiPackages)"
        ```

    *   **Get GCS Bucket Path:**

        ```bash
        gcloud composer environments describe <SOURCE_ENV> \
            --location <SOURCE_REGION> \
            --format="value(config.dagGcsPrefix)"
        ```

        *Expected Output:* `gs://<source-bucket-name>/dags`

4.  **List Active DAGs:** Identify which DAGs are currently registered and
    active in the source environment.

    ```bash
    gcloud composer environments run <SOURCE_ENV> \
        --location <SOURCE_REGION> \
        dags list
    ```

## 2. Download DAGs and Bucket Dependencies (only when requested)

*Perform this step only if explicitly requested to do so.* Download DAG files
and any other dependency files/folders from the source environment GCS bucket to
a local workspace directory (`./migration_workspace`).

1.  **Download DAGs:**

    ```bash
    mkdir -p ./migration_workspace/dags
    gcloud storage cp -r gs://<source-bucket-name>/dags/* ./migration_workspace/dags/
    ```

2.  **Download Other Bucket Dependencies (if applicable):**

    ```bash
    gcloud storage cp -r gs://<source-bucket-name>/<dependency-folder> ./migration_workspace/<dependency-folder>
    ```

> [!IMPORTANT] **Additional Environment Dependencies:** DAGs may also depend on
> Airflow Connections, Variables, or custom PyPI packages. Ensure these are
> identified and documented for the target environment setup.
