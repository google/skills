---
name: bigquery-udfs
metadata:
  version: "1.0.2"
  category: BigDataAndAnalytics
description: >-
  Creates, deploys, and troubleshoots BigQuery User-Defined Functions (UDFs)
  and Remote Functions across SQL, JavaScript, Python, and Cloud Run endpoints.
  Use when writing custom scalar or aggregate functions in BigQuery, installing
  PyPI packages or Cloud Storage libraries in a Python or JavaScript UDF, or
  calling Google Cloud and external APIs from a Python UDF (WITH CONNECTION) or
  Remote Function. Don't use for standard BigQuery table/dataset CRUD (use
  bigquery-basics), DataFrames client workflows (use bigquery-bigframes), or
  BigQuery ML models (use bigquery-ai-ml).
---

# BigQuery User-Defined Functions (UDFs)

BigQuery User-Defined Functions (UDFs) extend GoogleSQL with custom logic
written in SQL, JavaScript, managed Python (`python-3.11`), or hosted externally
as Remote Functions on Cloud Run and Cloud Run functions.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Choosing the Right UDF Type

Always select the lightest-weight runtime that satisfies the requirement,
because BigQuery optimizes native SQL expressions inline while external runtimes
incur serialization and container startup overhead:

UDF Type                                       | Connection Required?       | When to Use                                                                                                                                                                     | Key Constraints
:--------------------------------------------- | :------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :--------------
**SQL UDF** (Default)                          | No                         | Composable expressions, regex, struct/array manipulation, aggregate functions (`CREATE AGGREGATE FUNCTION`), or polymorphic `ANY TYPE` parameters.                              | Lowest latency; zero external dependencies; supports `TEMP` or persistent functions.
**JavaScript UDF**                             | No                         | Custom string/JSON logic or bundling `.js` libraries from Cloud Storage (`gs://`).                                                                                              | Runs in V8 sandbox; `INT64` unsupported as input (pass as `FLOAT64` or `STRING`). Max 32 KB inline code, 1 MB per external resource. Supports `TEMP` or persistent functions.
**Managed Python UDF (Offline)**               | **No**                     | Pure compute using Python 3.11, PyPI wheels (`packages=[...]`), Cloud Storage `.py` modules (`library=[...]`), or vectorized Pandas/PyArrow batches.                            | Persistent functions only (`CREATE TEMP FUNCTION` unsupported). Outbound network blocked. Max container size: 4 vCPU / 16 GiB. `JSON`, `RANGE`, `INTERVAL`, `GEOGRAPHY` unsupported.
**Managed Python UDF (`WITH CONNECTION`)**     | **Yes** (`CLOUD_RESOURCE`) | Invoking Google Cloud APIs (e.g., Cloud Translation, Gemini Enterprise Agent Platform) or online HTTP endpoints directly from Python inside BigQuery containers.                | Requires `WITH CONNECTION`. Outbound traffic restricted to `restricted.googleapis.com` in VPC-SC perimeters (VPC networks unsupported). Max container size: 4 vCPU / 16 GiB.
**Remote Function (`REMOTE WITH CONNECTION`)** | **Yes** (`CLOUD_RESOURCE`) | Calling external APIs or microservices when you need non-Python runtimes (Go, Java, Node.js), private VPC network access, GPUs, or custom Cloud Run scaling.                    | Requires Cloud Run HTTPS endpoint implementing BigQuery JSON batch contract and `roles/run.invoker`. Max input 5 MB per row; response limit 15 MB (Cloud Run) / 10 MB (1st gen).

## Prerequisites & Setup

Ensure the Google Cloud project has an active billing account attached (see
[BigQuery Pricing](https://docs.cloud.google.com/bigquery/pricing)):

1.  **Install and Authenticate Google Cloud SDK**: Install the
    [Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install)
    and authenticate:

    ```bash
    gcloud auth login
    ```

    Pass `--project={project_id}` and `--region={region}` (or `--location` for
    `bq`) explicitly on each command instead of running `gcloud config set`,
    which persists beyond the task. Default to `us-central1` when the user has
    not specified a region (see
    [BigQuery Locations](https://docs.cloud.google.com/bigquery/docs/locations.md.txt)).

2.  **Enable Required APIs**:

    -   For SQL, JavaScript, and offline Python UDFs: `bigquery.googleapis.com`
    -   Additionally for Python UDFs calling APIs (`WITH CONNECTION`) and Remote
        Functions: `bigqueryconnection.googleapis.com` (and `run.googleapis.com`
        for Remote Functions)

    ```bash
    CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-udfs)" \
    gcloud services enable bigquery.googleapis.com \
      bigqueryconnection.googleapis.com \
      run.googleapis.com --quiet
    ```

3.  **Verify Required IAM Roles**:

    -   **All UDFs**: `roles/bigquery.dataEditor` on the dataset and
        `roles/bigquery.jobUser` on the project.
    -   **When using `WITH CONNECTION` (API-calling Python UDFs & Remote
        Functions)**:
        -   UDF Creator: `roles/bigquery.connectionAdmin` on the project (plus
            `resourcemanager.projects.setIamPolicy`, e.g.,
            `roles/resourcemanager.projectIamAdmin`, when granting project-level
            IAM roles to the connection service account via `GRANT ... ON
            PROJECT`).
        -   UDF Caller: `roles/bigquery.connectionUser` on the connection.

--------------------------------------------------------------------------------

## Core Implementation Patterns

### 1. SQL UDFs (Scalar & Templated)

Use `CREATE OR REPLACE FUNCTION` for persistent UDFs or `CREATE TEMP FUNCTION`
for query-scoped functions. Use `ANY TYPE` for polymorphic parameters:

```sql
CREATE OR REPLACE FUNCTION `{project_id}.{dataset_id}.normalize_phone`(
  raw_phone STRING,
  country_code ANY TYPE
)
RETURNS STRING
AS (
  CONCAT('+', CAST(country_code AS STRING), '-', REGEXP_REPLACE(raw_phone, r'[^0-9]', ''))
);
```

See [SQL and JavaScript UDFs](references/sql-and-js-udfs.md) for aggregate UDFs
(`CREATE AGGREGATE FUNCTION`) and JavaScript Cloud Storage library loading.

### 2. JavaScript UDFs

Use raw triple-quoted strings (`r"""..."""`) to avoid escaping backslashes:

```sql
CREATE OR REPLACE FUNCTION `{project_id}.{dataset_id}.extract_url_query_keys`(
  url_str STRING
)
RETURNS ARRAY<STRING>
DETERMINISTIC
LANGUAGE js
OPTIONS (
  library = ['gs://{bucket_name}/libs/uri-parser.js']
)
AS r"""
  if (!url_str) return [];
  try {
    return URIParser.getQueryKeys(url_str);
  } catch (err) {
    return [];
  }
""";
```

### 3. Managed Python UDFs (With and Without Connection)

Python UDFs must be persistent (do not use `TEMP`), specify `runtime_version =
'python-3.11'`, and define an `entry_point`. `numpy`, `pandas`, and `pyarrow`
are pre-installed in the `python-3.11` base image.

BigQuery defaults to `container_memory = '512Mi'`, `container_cpu = 1.0`, and
`container_request_concurrency = 80`. Omit these options when the defaults are
sufficient, and configure them explicitly only when a workload requires custom
container sizing or concurrency (see [Python UDFs](references/python-udfs.md)).

Top-level Python statements (`import`, helper functions, classes, and `def
{entry_point}(...)`) inside `AS r'''...'''` must have **zero leading
indentation** (flush to the left margin). Indenting top-level Python definitions
to align with surrounding SQL causes an `IndentationError` when BigQuery loads
the container module.

#### A. Offline / Vectorized Python UDF (No Connection Needed)

Omit `WITH CONNECTION` when the UDF only performs computation or uses PyPI
packages (`packages=[...]`) / Cloud Storage libraries (`library=['gs://...']`).
To vectorize execution over batches of rows, annotate the parameter with
`pd.DataFrame` (or `pyarrow.RecordBatch`) and return a `pd.Series`:

> [!WARNING] **Vectorized operations must be row-independent**: BigQuery calls
> vectorized UDFs on arbitrary row batches (up to `max_batching_rows`). Do NOT
> compute global column statistics (such as z-scores, dataset mean/std, or rank)
> across `df`, because each batch only sees an arbitrary slice of rows. Use SQL
> window functions (`(val - AVG(val) OVER()) / NULLIF(STDDEV(val) OVER(), 0)`)
> for dataset-wide statistics. Vectorized Python UDFs should perform
> row-independent calculations (e.g. geometric distances or multi-column math).

```sql
CREATE OR REPLACE FUNCTION `{project_id}.{dataset_id}.vectorized_distance`(
  x1 FLOAT64, y1 FLOAT64, x2 FLOAT64, y2 FLOAT64
)
RETURNS FLOAT64
LANGUAGE python
OPTIONS (
  runtime_version = 'python-3.11',
  entry_point = 'compute_distance'
)
AS r'''
import numpy as np
import pandas as pd

def compute_distance(df: pd.DataFrame) -> pd.Series:
    return pd.Series(
        np.hypot(df['x2'] - df['x1'], df['y2'] - df['y1']),
        index=df.index,
    )
''';
```

#### B. Online Python UDF Calling an External / Cloud API (`WITH CONNECTION`)

Include `WITH CONNECTION` **only** when the Python code makes outbound network
or API calls at runtime.

Always configure explicit timeouts, logging, and prescriptive exception handling
in the `try...except` block:

-   **Transient errors only → `NULL`**: Catch retryable exceptions
    (`google.api_core.exceptions.TooManyRequests`, `ServiceUnavailable`,
    `DeadlineExceeded`, `InternalServerError`, and `RetryError`), log them with
    `logging.warning`, and return `None` so a transient blip does not abort the
    query. Do **not** catch the base class `GoogleAPICallError` here: it also
    matches `PermissionDenied`, `Unauthenticated`, and `InvalidArgument`.
-   **Fatal errors → raise**: Let auth, permission, and invalid-argument errors
    propagate (or log and re-raise as `RuntimeError`) so they surface as a user
    error on the query instead of silently producing `NULL`s.
-   **Never log row values**: Anyone with Cloud Logging access can read UDF logs
    regardless of BigQuery table permissions. Log exception types and messages,
    not input or output data. Logs are only emitted when the session sets `SET
    @@udf.properties = JSON '{"enableDebugOutput": true}';`.
-   **Set a per-request `timeout`**: `Retry(timeout=...)` only caps the total
    retry duration; also pass `timeout=` on each client call.

1.  **Create a Cloud Resource Connection and Retrieve its Service Account**:

    ```bash
    bq mk --connection --connection_type=CLOUD_RESOURCE \
      --location={region} --project_id={project_id} {connection_id}

    bq show --connection {project_id}.{region}.{connection_id}
    ```
2.  **Grant Permissions to the Connection Service Account**: Grant
    `roles/serviceusage.serviceUsageConsumer` on `{project_id}` plus the
    required API role (e.g., `roles/cloudtranslate.user`) on the target project.
    Running `GRANT ... ON PROJECT` modifies the project's IAM policy and
    requires `resourcemanager.projects.setIamPolicy` (for example,
    `roles/resourcemanager.projectIamAdmin`); **confirm with the user before
    running project-level IAM grants**. The DCL `connection:` grantee takes the
    connection path (`[project_id.]location.connection_id`), not the service
    account email; BigQuery resolves the connection's service account
    automatically (use `"serviceAccount:{connection_sa_email}"` to grant by
    email instead):

    ```sql
    GRANT `roles/serviceusage.serviceUsageConsumer`
    ON PROJECT `{project_id}`
    TO "connection:{project_id}.{region}.{connection_id}";

    GRANT `roles/cloudtranslate.user`
    ON PROJECT `{project_id}`
    TO "connection:{project_id}.{region}.{connection_id}";
    ```
3.  **Create the Python UDF with `WITH CONNECTION`** (keep top-level Python
    statements flush-left at column 0):

```sql
CREATE OR REPLACE FUNCTION `{project_id}.{dataset_id}.translate_to_es`(
  text STRING
)
RETURNS STRING
LANGUAGE python
WITH CONNECTION `{project_id}.{region}.{connection_id}`
OPTIONS (
  entry_point = 'do_translate',
  runtime_version = 'python-3.11',
  packages = ['google-cloud-translate>=3.11', 'google-api-core']
)
AS r'''
import logging
from google.api_core import exceptions
from google.api_core.retry import Retry
from google.cloud import translate

client = translate.TranslationServiceClient()

TRANSIENT_ERRORS = (
    exceptions.TooManyRequests,
    exceptions.ServiceUnavailable,
    exceptions.DeadlineExceeded,
    exceptions.InternalServerError,
    exceptions.RetryError,
)

def do_translate(text: str) -> str:
    if not text:
        return None
    try:
        # Note: Replace {project_id} with your Google Cloud Project ID
        response = client.translate_text(
            request={
                "parent": "projects/{project_id}/locations/us-central1",
                "contents": [text],
                "target_language_code": "es",
                "mime_type": "text/plain",
            },
            retry=Retry(timeout=30.0),  # Total retry budget.
            timeout=10.0,  # Per-attempt deadline.
        )
        return response.translations[0].translated_text
    except TRANSIENT_ERRORS as e:
        # Log the error type only; never log row values.
        logging.warning("Transient Translation API error: %s", type(e).__name__)
        return None
    except exceptions.GoogleAPICallError as e:
        # PermissionDenied, Unauthenticated, InvalidArgument, etc. are fatal.
        logging.error("Fatal Translation API error: %s: %s", type(e).__name__, e)
        raise RuntimeError(f"Translation failed: {type(e).__name__}") from e
''';
```

See [Python UDFs](references/python-udfs.md) for container sizing
(`container_cpu`, `container_memory`, `container_request_concurrency`), Cloud
Logging (`SET @@udf.properties = JSON '{"enableDebugOutput": true}';`), and
checking container build status via `INFORMATION_SCHEMA.ROUTINES`.

### 4. Remote Functions (Cloud Run Endpoints)

Use Remote Functions when the endpoint is hosted on Cloud Run or Cloud Run
functions (for non-Python languages, VPC networking, or custom hardware):

1.  **Grant `roles/run.invoker` to the Connection Service Account** (confirm
    with the user before modifying the Cloud Run service IAM policy):

    ```bash
    CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-udfs)" \
    gcloud run services add-iam-policy-binding {cloud_run_service} \
      --region={region} \
      --member="serviceAccount:{connection_sa_email}" \
      --role="roles/run.invoker"
    ```
2.  **Register the Remote Function**: The endpoint must accept `{"calls":
    [[arg1, ...], ...]}` and return `{"replies": [res1, ...]}` with matching
    element count:

    ```sql
    CREATE OR REPLACE FUNCTION `{project_id}.{dataset_id}.enrich_address`(
      street STRING, postal_code STRING
    )
    RETURNS JSON
    REMOTE WITH CONNECTION `{project_id}.{region}.{connection_id}`
    OPTIONS (
      endpoint = 'https://{cloud_run_service_url}',
      max_batching_rows = 1000
    );
    ```

See [Remote Functions](references/remote-functions.md) for Cloud Run handler
templates, batch limits (`max_batching_rows`, 5 MB max input per row, 15 MB max
response on Cloud Run / 10 MB on 1st gen functions), and error/retry semantics
(BigQuery automatically retries a batch only on HTTP `408`, `429`, `500`, `503`,
or `504`; any other non-200 status or JSON `{"errorMessage": "..."}` fails the
query without retrying).

--------------------------------------------------------------------------------

## Validation Checklist

After generating or modifying a UDF, follow this validate→fix→repeat loop:

-   [ ] **Step 1 — Validate Python code before BigQuery DDL**: For Python UDFs,
    validate the Python function and `packages` dependencies *before* submitting
    the BigQuery DDL—either locally with `python3` test inputs (`None`, edge
    cases, `pd.DataFrame` batches) or in a containerized Cloud Run Job (`gcloud
    run jobs deploy {job_name} --source . --region={region}` and `gcloud run
    jobs execute {job_name} --region={region} --wait`; see
    [Python UDFs Validation](references/python-udfs.md#validation-workflow)).
-   [ ] **Step 2 — Execute DDL and poll container build status**: Run `CREATE OR
    REPLACE FUNCTION`. Because the DDL statement returns *before* the Python
    container image finishes building, poll `INFORMATION_SCHEMA.ROUTINES` until
    `build_state` transitions from `IN_PROGRESS` to `SUCCEEDED` (or fix and
    re-run if `FAILED`):

    ```sql
    SELECT build_status.*
    FROM `{project_id}.{dataset_id}`.INFORMATION_SCHEMA.ROUTINES
    WHERE routine_name = '{udf_name}';
    ```
-   [ ] **Step 3 — Test the UDF with SQL `SELECT`**: Once `build_state =
    'SUCCEEDED'` (or immediately after DDL for SQL/JS UDFs), run a test `SELECT`
    query covering `NULL` and valid inputs.

## Cleanup & Teardown

Delete unused routines, connections, Cloud Run services, and staged Cloud
Storage artifacts (note that the size of all Python UDF containers per project
and per region is restricted to a sum total of 10 GiB):

```bash
bq query --use_legacy_sql=false "DROP FUNCTION IF EXISTS \`{project_id}.{dataset_id}.{udf_name}\`;"
bq rm --connection --location={region} {connection_id}
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-udfs)" \
gcloud run services delete {cloud_run_service} --region={region} --project={project_id}
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-udfs)" \
gcloud storage rm gs://{bucket_name}/udf_libs/bundle.js
```

## Reference Directory

-   [SQL and JavaScript UDFs](references/sql-and-js-udfs.md): Templated SQL
    parameters (`ANY TYPE`), aggregate UDFs, JavaScript type mappings, and Cloud
    Storage library loading
    (`https://docs.cloud.google.com/bigquery/docs/user-defined-functions.md.txt`).
-   [Python UDFs](references/python-udfs.md): Offline vs. `WITH CONNECTION`
    online service access, Pandas/PyArrow vectorization, container resource
    limits (`container_cpu`/`container_memory`), and Cloud Logging debugging
    (`https://docs.cloud.google.com/bigquery/docs/user-defined-functions-python.md.txt`).
-   [Remote Functions](references/remote-functions.md): Cloud Run HTTP request
    and response JSON schema, batch sizing, retry semantics, and VPC egress
    (`https://docs.cloud.google.com/bigquery/docs/remote-functions.md.txt`).
-   [IAM, Authorized Routines, and Quotas](references/iam-and-quotas.md):
    Sharing routines across datasets (`Authorized Routines`), container quotas,
    and troubleshooting errors.

## Related Skills

-   **BigQuery Basics** (`bigquery-basics`): Dataset, table, and job management.
-   The `bigquery-bigframes` skill: Creating Python UDFs from Python via
    `@bpd.udf`.
-   The `bigquery-ai-ml` skill: Built-in `AI.GENERATE_TEXT` and
    `AI.GENERATE` functions.
