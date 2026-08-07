# Airflow 3 migration

## 1. Airflow 3 Migration checks

Use these checks if migrating to Airflow 3.

### 1.1 Direct Metadata Database Access (migration to Airflow 3)

*   **Change:** Direct access to the Airflow metadata database is not allowed.
    Internal DB sessions and direct SQLAlchemy queries against Airflow internals
    must be removed.
*   **Scan Command:**

    ```bash
    grep -rn -E "provide_session|airflow\.utils\.session" ./dags
    ```

*   **Remediation:**

    *   You MUST remove `@provide_session` decorators and internal ORM queries.
    *   You MUST inspect localized task runtime state via `get_current_context()`.
    *   For interaction with Airflow metadata resources, you MUST use the **Airflow
        Python Client**.

### 1.2 Reorganized Imports (migration to Airflow 3)

*   **Change:** Core authoring primitives are migrated to the decoupled SDK
    interface, and standard operators are moved to the standard provider bundle.
*   **Scan Command:**

    ```bash
    grep -rn -E "airflow\.models\.dag|airflow\.DAG|airflow\.models\.baseoperator|airflow\.utils\.task_group|airflow\.datasets\.Dataset|airflow\.models\.variable|airflow\.operators\.bash|airflow\.operators\.python" ./dags
    ```

*   **Remediation:** You MUST update imports according to the following mapping:

    *   `airflow.models.dag.DAG` / `airflow.DAG` -> `airflow.sdk.DAG`
    *   `airflow.models.baseoperator.BaseOperator` -> `airflow.sdk.BaseOperator`
    *   `airflow.utils.task_group.TaskGroup` -> `airflow.sdk.TaskGroup`
    *   `airflow.datasets.Dataset` -> `airflow.sdk.Asset`
    *   `airflow.models.variable.Variable` -> `airflow.sdk.Variable`
    *   `airflow.operators.bash.BashOperator` -> `airflow.providers.standard.operators.bash.BashOperator`
    *   `airflow.operators.python.PythonOperator` -> `airflow.providers.standard.operators.python.PythonOperator`

    *Note: You SHOULD prefer standard decorators (e.g. `@dag`, `@task`) unless it is not
    feasible.*

### 1.3 Asset Transition: Dataset to Asset (migration to Airflow 3)

*   **Change:** Data-aware scheduling targets are renamed from `Dataset` to
    `Asset`.
*   **Scan Command:**

    ```bash
    grep -rn "Dataset(" ./dags
    ```

*   **Remediation:**

    *   You MUST update `schedule=[Dataset(...)]` to `schedule=[Asset(...)]`.
    *   You MUST update task parameter endpoints (`outlets`/`inlets`) accordingly.
    *   You MUST update imports to `from airflow.sdk import Asset`.

### 1.4 Deprecated Features: SubDAGs & SLAs (migration to Airflow 3)

*   **Change:** `SubDagOperator` and `sla` parameters are removed.
*   **Scan Command (SubDAGs):**

    ```bash
    grep -rn "SubDagOperator" ./dags
    ```

*   **Scan Command (SLAs):**

    ```bash
    grep -rn "sla=" ./dags
    ```

*   **Remediation:**

    *   **SubDAGs:** You MUST refactor `SubDagOperator` uses into nested `TaskGroup`s.
    *   **SLAs:** You MUST delete the `sla` parameter from operator calls and DAG
        `default_args`.

### 1.5 Deprecated Context Variables (migration to Airflow 3)

*   **Change:** Several context variables are deprecated or removed.
*   **Scan Command:**

    ```bash
    grep -rn -E "\bexecution_date\b|\bnext_execution_date\b|\bnext_ds\b|\bnext_ds_nodash\b|\bprev_execution_date\b|\bprev_ds\b|\bprev_ds_nodash\b|\byesterday_ds\b|\byesterday_ds_nodash\b|\btomorrow_ds\b|\btomorrow_ds_nodash\b|\bprev_execution_date_success\b|\bconf\b|\btriggering_dataset_events\b" ./dags
    ```

*   **Remediation:** You MUST replace deprecated variables. You SHOULD be defensive and secure the
    code to handle cases where variables MIGHT be `None` (e.g., in manual or
    asset-triggered runs).

    *   **`execution_date`**:
        *   **Replacement/Workaround:** `logical_date`
        *   **Advice:** You MUST replace with `logical_date`. You SHOULD use
            `dag_run.run_id` for asset-triggered runs. Manual runs also do not
            have `logical_date` populated, so a fallback is needed if those
            cases are expected to be supported.
    *   **`next_execution_date`**:
        *   **Replacement/Workaround:** `data_interval_end`
        *   **Advice:** You MUST replace with `data_interval_end`. This defaults to trigger time on manual runs.
    *   **`next_ds`**:
        *   **Replacement/Workaround:** `{{ data_interval_end | ds }}`
        *   **Advice:** You MUST replace with `{{ data_interval_end | ds }}`.
    *   **`next_ds_nodash`**:
        *   **Replacement/Workaround:** `{{ data_interval_end | ds_nodash }}`
        *   **Advice:** You MUST replace with `{{ data_interval_end | ds_nodash }}`.
    *   **`prev_execution_date`**:
        *   **Replacement/Workaround:** `prev_data_interval_start_success`
        *   **Advice:** You SHOULD use `logical_date` for manual run fallback, or `prev_data_interval_start_success` for actual prior success.
    *   **`prev_ds`**:
        *   **Replacement/Workaround:** `{{ prev_data_interval_start_success | ds }}`
        *   **Advice:** You SHOULD use `ds` for manual fallback, or `{{ prev_data_interval_start_success | ds }}`.
    *   **`prev_ds_nodash`**:
        *   **Replacement/Workaround:** `{{ prev_data_interval_start_success | ds_nodash }}`
        *   **Advice:** You SHOULD use `ds_nodash` for manual fallback, or `{{ prev_data_interval_start_success | ds_nodash }}`.
    *   **`yesterday_ds`**:
        *   **Replacement/Workaround:** `{{ macros.ds_add(ds, -1) }}`
        *   **Advice:** You MUST replace with `{{ macros.ds_add(ds, -1) }}`.
    *   **`yesterday_ds_nodash`**:
        *   **Replacement/Workaround:** `{{ macros.ds_format(macros.ds_add(ds, -1), "%Y-%m-%d", "%Y%m%d") }}`
        *   **Advice:** You MUST replace with the formatted `ds_add` macro.
    *   **`tomorrow_ds`**:
        *   **Replacement/Workaround:** `{{ macros.ds_add(ds, 1) }}`
        *   **Advice:** You MUST replace with `{{ macros.ds_add(ds, 1) }}`.
    *   **`tomorrow_ds_nodash`**:
        *   **Replacement/Workaround:** `{{ macros.ds_format(macros.ds_add(ds, 1), "%Y-%m-%d", "%Y%m%d") }}`
        *   **Advice:** You MUST replace with the formatted `ds_add` macro.
    *   **`prev_execution_date_success`**:
        *   **Replacement/Workaround:** `prev_data_interval_start_success`
        *   **Advice:** You MUST replace with `prev_data_interval_start_success`.
    *   **`conf`**:
        *   **Replacement/Workaround:** None / Env Vars / Variables
        *   **Advice:** This has been removed for Task SDK isolation. You MUST use env vars or Airflow Variables. User run config is in `dag_run.conf`.
    *   **`triggering_dataset_events`**:
        *   **Replacement/Workaround:** `triggering_asset_events`
        *   **Advice:** You MUST replace with `triggering_asset_events`.

### 1.6 Default Configurations

*   **Change:** Default behavior for `catchup` is now `False`.
*   **Scan Command:**

    ```bash
    grep -rn "DAG(" ./dags | grep -v "catchup"
    ```

*   **Remediation:** You MUST set `catchup=False` explicitly unless historical runs are
    strictly required, in which case you SHOULD explicitly set `catchup=True`.

--------------------------------------------------------------------------------

## 2. Airflow 3.0 Conversion Examples

### Example 1: Basic DAG Imports & Assets

**Legacy Airflow 2 Code:**

```python
from airflow import DAG
from airflow.datasets import Dataset
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="example_dag",
    start_date=datetime(2023, 1, 1),
    schedule=[Dataset("gcs://my-bucket/data.csv")],
    catchup=True,
) as dag:
    task1 = BashOperator(
        task_id="run_script",
        bash_command="echo hello",
        sla=datetime.timedelta(hours=1),
    )
```

**Converted Airflow 3 Code:**

```python
from airflow.sdk import dag, task, Asset
from datetime import datetime

@dag(
    dag_id="example_dag",
    start_date=datetime(2023, 1, 1),
    schedule=[Asset("gcs://my-bucket/data.csv")],
    catchup=True,
)
def example_dag():
    @task.bash(task_id="run_script")
    def run_script():
        return "echo hello"

    run_script()

example_dag()
```
