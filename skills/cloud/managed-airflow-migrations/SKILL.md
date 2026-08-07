---
name: managed-airflow-migrations
description: Provides guidance for migrating Apache Airflow DAGs in Managed Service for Apache Airflow (MSAA; formerly Cloud Composer). Covers migration to Airflow 2.11.1 (MSAA Gen 2 and 3) and Airflow 3 (MSAA Gen 3), including environment inspection, GCS download/upload and scanning patterns for breaking changes. Use when migrating the DAG code to newer Airflow version. Don't use when checking DAG run failures unrelated to code migration.
metadata:
  category: BigDataAndAnalytics
---

# Managed Service for Apache Airflow (formerly Cloud Composer) Migration Guide

This skill guides you through the process of adjusting Airflow DAGs from an
existing Managed Service for Apache Airflow (formerly Cloud Composer)
environment (or available locally) to make them compatible with **Airflow
2.11.1** (MSAA Gen 2 or 3) or **Airflow 3** (MSAA Gen 3).

--------------------------------------------------------------------------------

## Phase 1: Discovery & Download

Before making any changes, download the existing DAG files if explicitly
requested. Inspect the source environment to confirm source version only if
explicitly requested. For detailed instructions about environment inspection and
downloading files check
[references/environment-inspection.md](references/environment-inspection.md).

--------------------------------------------------------------------------------

## Phase 2: Target Version & Dependency Mapping

### 2.1 Airflow 2.11.1+ Dependency Mapping

If migrating to Airflow 2.11.1 (MSAA Gen 2) or Airflow 3, use the list below to
trace the version progression of key dependencies. The list covers changes
needed to get to Airflow 2.11.1. Take them into account when migrating from
Airflow 2 (earlier than 2.11.1) to Airflow 3.

### Composer 2.10.0 (Airflow 2.10.2)

-   **Google Provider**: `10.26.0`
-   **SSH Provider**: `3.14.0`
-   **HTTP Provider**: `4.13.3`
-   **Breaking Changes**: *Baseline for oldest fully documented source.*

### Composer 2.15.3 (Airflow 2.10.5)

-   **Google Provider**: `18.0.0`
-   **SSH Provider**: `4.1.4`
-   **HTTP Provider**: `5.3.4`
-   **Breaking Changes**:
    -   **SSH Provider 4.0.0:** Hook `timeout` removed; `get_conn()` context
        manager.
    -   **HTTP Provider 5.0.0:** `SimpleHttpOperator` -> `HttpOperator`.
    -   **Google Provider 11.0.0:** `BigQueryExecuteQueryOperator` removed.
    -   **Google Provider 12.0.0:** Legacy Data Pipeline operators removed.
    -   **Google Provider 13.0.0:** `AutoMLBatchPredictOperator` removed.
    -   **Google Provider 17.0.0:** `BigQueryCreateEmptyTableOperator` and
        `BigQueryCreateExternalTableOperator` removed; Life Sciences operators
        removed.
    -   **Google Provider 18.0.0:** Legacy DV360 operators removed.

### Composer 2.16.1 (Airflow 2.10.5)

-   **Google Provider**: `19.0.0`
-   **SSH Provider**: `4.1.6`
-   **HTTP Provider**: `5.5.0`
-   **Breaking Changes**: **Google Provider 19.0.0:** AutoML operators removed
    (use Vertex AI).

### Composer 2.17.0 (Target Airflow 2.11.1)

-   **Google Provider**: **`20.0.0`**
-   **SSH Provider**: **`5.0.0`**
-   **HTTP Provider**: **`6.0.2`**
-   **Breaking Changes**:
    -   **SSH Provider 5.0.0:** `sshtunnel` removed (native tunneling).
    -   **HTTP Provider 6.0.0:** JSON serialization.
    -   **Google Provider 20.0.0:** ADLS Gen2 migration.

### 2.2 Airflow 3 Migration

If migrating to Airflow 3 (MSAA Gen 3), note that this is a major version
upgrade with significant changes, including:

*   Decoupled Task SDK (imports change from `airflow` to `airflow.sdk`).
*   Removal of direct metadata DB access.
*   Renaming of `Dataset` to `Asset`.
*   Removal of SubDAGs and SLAs.
*   Changes to context variables availability.

Take into account all applicable changes within Airflow 2 (e.g. when migrating
from Airflow 2.10.2, apply changes needed to move to Airflow 2.11.1 and Airflow
3 migration changes on top of that).

--------------------------------------------------------------------------------

## Phase 3: Analysis & Remediation (Scanning Downloaded Files)

Run the scan commands from the root of your local workspace
(`./migration_workspace` unless indicated otherwise).

--------------------------------------------------------------------------------

### 3.1 Airflow 2.11.1 Core & Dependency checks

Use these scans if migrating to Airflow 2.11.1+ (intermediate step when
migrating to Airflow 3).

#### 3.1.1 Dataset Scheduling (Airflow 2.11.0)

*   **Change:** DAGs scheduled on datasets only trigger if events occur while
    the DAG is unpaused.
*   **Scan Command:** `grep -rn "Dataset(" ./dags`
*   **Remediation:** You MUST document that these DAGs must remain unpaused to
    catch events, or plan manual triggers for catch-up.

#### 3.1.2 HTML in Descriptions (Airflow 2.11.0)

*   **Change:** Raw HTML in DAG docs / params is escaped by default.
*   **Scan Command:**

    ```bash
    grep -rn -E "doc_md.*<|doc_md.*>|description.*<|description.*>" ./dags
    ```

*   **Remediation:** Convert HTML to Markdown, or set
    `AIRFLOW__WEBSERVER__ALLOW_RAW_HTML_DESCRIPTIONS=True` in target.

#### 3.1.3 Teardown Tasks (Airflow 2.10.5)

*   **Change:** Teardowns always run when a DAG is marked failed.
*   **Scan Command:** `grep -rn "as_teardown" ./dags`
*   **Remediation:** Ensure teardown tasks are idempotent.

#### 3.1.4 Pendulum 3 Upgrade (Airflow 2.11.0)

*   **Change:** `Period` renamed to `Interval`, testing helpers removed.
*   **Scan Command (Code):**

    ```bash
    grep -rn -E "pendulum\.Period|pendulum\.period" ./dags
    ```

*   **Scan Command (Tests):**

    ```bash
    grep -rn -E "\.test\(|set_test_now\(" ./tests 2>/dev/null || true
    ```

*   **Remediation:** Replace `Period` with `Interval`, and `period(...)` with
    `interval(...)`.

--------------------------------------------------------------------------------

### 3.2 Path A: Airflow 2.11.1 Provider Package Scan

#### 3.2.1 SSH Provider (SSH 4.0.0 & 5.0.0)

*   **Scan Command (Timeout):** `grep -rn "SSHHook" ./dags | grep "timeout"`
*   **Scan Command (Context Manager):** `grep -rn "with SSHHook" ./dags`
*   **Scan Command (Tunnel Attributes):** `grep -rn "\.get_tunnel" ./dags`
*   **Remediation:**
    *   Replace `timeout` with `conn_timeout` in `SSHHook`.
    *   Replace `with hook as conn:` with `with hook.get_conn() as conn:`.
    *   Use `get_tunnel()` as context manager: `with hook.get_tunnel(...) as
        tunnel:`.

#### 3.2.2 HTTP Provider (HTTP 5.0.0 & 6.0.0)

*   **Scan Command:** `grep -rn "SimpleHttpOperator" ./dags`
*   **Remediation:** Replace `SimpleHttpOperator` with `HttpOperator`.

#### 3.2.3 Google Provider (v11 to v20)

*   **Scan Command (BigQuery query):**

    ```bash
    grep -rn "BigQueryExecuteQueryOperator" ./dags
    ```

    *   *Remediation:* Replace with `BigQueryInsertJobOperator` (use
        `configuration` dict).
*   **Scan Command (BigQuery table):**

    ```bash
    grep -rn -E "BigQueryCreateEmptyTableOperator|BigQueryCreateExternalTableOperator" ./dags
    ```

    *   *Remediation:* Replace with `BigQueryCreateTableOperator` (use
        `table_resource` dict).
*   **Scan Command (AutoML):**

    ```bash
    grep -rn -E "AutoMLTrainModelOperator|AutoMLPredictOperator|AutoMLCreateDatasetOperator|AutoMLBatchPredictOperator" ./dags
    ```

    *   *Remediation:* Migrate to Vertex AI operators.
*   **Scan Command (Dataflow):**

    ```bash
    grep -rn -E "CreateDataPipelineOperator|RunDataPipelineOperator" ./dags
    ```

    *   *Remediation:* Replace with
        `DataflowCreatePipelineOperator`/`DataflowRunPipelineOperator`.
*   **Scan Command (Life Sciences):**

    ```bash
    grep -rn "LifeSciencesRunPipelineOperator" ./dags`
    ```

    *   *Remediation:* Migrate to Google Cloud Batch operators
        (`BatchCreateJobOperator`).
*   **Scan Command (ADLS to GCS):** `grep -rn "ADLSToGCSOperator" ./dags`
    *   *Remediation:* Ensure `file_system_name` is provided.

--------------------------------------------------------------------------------

### 3.3 Airflow 3 Migration checks

Use instructions from [references/airflow-3.md](references/airflow-3.md) when
migrating to Airflow 3.

--------------------------------------------------------------------------------

## Phase 4: Deployment & Verification

*Perform deployment and verification steps only if explicitly requested to do
so.*

### 4.1 Static Verification (when migrating to Airflow 3)

After applying code changes for Airflow 3, verify syntax correctness. If
available in the development environment, run static lint checks:

```bash
ruff check {target_dag_file} --select AIR30
```

Resolve any reported deprecation warnings before finalization. If ruff is not
available, recommend installing one.

### 4.2 Deployment to MSAA

#### 4.2.1 Get Target GCS Bucket Path (only when requested)

```bash
gcloud composer environments describe <TARGET_ENV> \
    --location <TARGET_REGION> \
    --format="value(config.dagGcsPrefix)"
```

*Expected Output:* `gs://<target-bucket-name>/dags`

### 4.2 Upload Modified DAGs and Bucket Dependencies (Only when requested)

*Perform this step only if explicitly requested to do so.* Copy the modified
DAGs and any backed-up bucket dependencies from your local workspace to the
target GCS bucket. *If you skipped the inspection step, ensure you have the
correct `<target-bucket-name>`.*

1.  **Upload DAGs:**

    ```bash
    gcloud storage cp -r ./dags/* gs://<target-bucket-name>/dags/
    ```

2.  **Upload Other Bucket Dependencies (If applicable):**

    ```bash
    gcloud storage cp -r ./migration_workspace/<dependency-folder> gs://<target-bucket-name>/<dependency-folder>
    ```

### 4.3 Verify DAGs via Airflow CLI

*Perform this step only if explicitly requested to upload modified DAGS to a
target environment (and after uploading).*

You can verify that your DAGs have been successfully uploaded, parsed, and
registered by the Airflow scheduler in the target environment using the Airflow
CLI.

1.  **List Registered DAGs:** Run the following command to list all DAGs
    registered in the target environment. Verify that your migrated DAGs appear
    in this list.

    ```bash
    gcloud composer environments run <TARGET_ENV> \
        --location <TARGET_REGION> \
        dags list
    ```

2.  **Check for Import Errors:** If some DAGs are missing from the list, or to
    ensure there are no parsing issues, check for import errors:

    ```bash
    gcloud composer environments run <TARGET_ENV> \
        --location <TARGET_REGION> \
        dags list-import-errors
    ```

    *Expected Output:*

    *   If there are no errors, the command will output `No data found`.
    *   If there are errors, it will list the file path and the traceback of the
        error.

*Note: It may take a couple of minutes for the Airflow scheduler to parse the
new files and for changes to reflect in these commands.*

### 4.4 Verify in Cloud Logging

*Perform this step only if explicitly requested to upload modified DAGS to a
target environment (and after uploading).* Monitor Cloud Logging for the target
environment to detect any runtime errors or import errors.

Run the following query in the **GCP Cloud Logging Console** (or via `gcloud
logging read`):

```query
resource.type="cloud_composer_environment"
resource.labels.environment_name="<TARGET_ENV>"
log_id("airflow-scheduler")
severity>=ERROR
```

--------------------------------------------------------------------------------

## Appendix: Local Environment Verification

If you want to verify your changes locally before deploying to the target
environment, you can use the Composer Local Development CLI tool
(`composer-dev`). Use
[references/local-development-environment.md](references/local-development-environment.md)
as a reference for interactions with local development environments.
