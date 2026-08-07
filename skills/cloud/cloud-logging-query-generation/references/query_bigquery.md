# BigQuery LQL queries

## Table of contents

- [Base schema and structural patterns](#base-schema-and-structural-patterns) (L25-L54)
- [Core resource types](#core-resource-types) (L31-L39)
- [The metadata abstraction](#the-metadata-abstraction) (L41-L54)
- [Example queries](#example-queries) (L56-L203)
- [BigQuery audit logs related to datasets or projects](#bigquery-audit-logs-related-to-datasets-or-projects) (L58-L65)
- [Logs for queries that billed more than 1GB (1073741824 bytes)](#logs-for-queries-that-billed-more-than-1gb-1073741824-bytes) (L67-L74)
- [BigQuery audit logs for a project](#bigquery-audit-logs-for-a-project) (L76-L83)
- [BigQuery audit logs for a dataset](#bigquery-audit-logs-for-a-dataset) (L85-L92)
- [BigQuery audit logs for BI Engine model](#bigquery-audit-logs-for-bi-engine-model) (L94-L101)
- [BigQuery audit logs for a Data Transfer Service run.](#bigquery-audit-logs-for-a-data-transfer-service-run) (L103-L110)
- [BigQuery audit logs for a Data Transfer Service configuration.](#bigquery-audit-logs-for-a-data-transfer-service-configuration) (L112-L119)
- [BigQuery Data Transfer Service jobs](#bigquery-data-transfer-service-jobs) (L121-L131)
- [BigQuery transfer run logs](#bigquery-transfer-run-logs) (L133-L141)
- [BigQuery dataset updates](#bigquery-dataset-updates) (L143-L151)
- [BigQuery jobs completed](#bigquery-jobs-completed) (L153-L162)
- [BigQuery quota exceeded](#bigquery-quota-exceeded) (L164-L173)
- [BigQuery query started](#bigquery-query-started) (L175-L182)
- [BigQuery concurrent load/extract jobs](#bigquery-concurrent-loadextract-jobs) (L184-L193)
- [BigQuery audit logs for row access policy](#bigquery-audit-logs-for-row-access-policy) (L195-L203)

## Base schema and structural patterns

BigQuery telemetry fundamentally operates through Google Cloud Audit Logs.
Unlike standard application logs, BigQuery execution telemetry relies on
`protoPayload.metadata` structures rather than `jsonPayload`.

### Core resource types

*   **Projects (`bigquery_project`)**: The high-level anchor. This captures
    top-level job operations, project-wide auditing, and overarching query
    telemetry.
*   **Datasets (`bigquery_dataset`)**: Captures table/data access operations and
    dataset configuration telemetry.
*   **Data Transfer Service (`bigquery_dts_run`, `bigquery_dts_config`)**:
    Captures telemetry for scheduled data movement pipelines.

### The metadata abstraction

When searching for "query execution", "query costs", "bytes billed", or "table
data access", you must target the `metadata` object within the Audit Log
`protoPayload`. Do NOT use `jsonPayload` or `textPayload` for BigQuery execution
tracking.

*   **Targeting Jobs / Executions:** Search within
    `protoPayload.metadata.jobChange.job` (for example:
    `protoPayload.metadata.jobChange.job.jobStats.queryStats.totalBilledBytes`).
*   **Targeting Data Reads:** Search within
    `protoPayload.metadata.tableDataRead`.
*   **Targeting Identity:** All actors issuing BigQuery jobs will be recorded in
    `protoPayload.authenticationInfo.principalEmail`.

## Example queries

### BigQuery audit logs related to datasets or projects

**Variables to replace:** None

```lql
resource.type=("bigquery_dataset" OR "bigquery_project")
logName:"cloudaudit.googleapis.com"
```

### Logs for queries that billed more than 1GB (1073741824 bytes)

**Variables to replace:** None

```lql
resource.type="bigquery_project"
protoPayload.metadata.jobChange.job.jobStats.queryStats.totalBilledBytes > 1073741824
```

### BigQuery audit logs for a project

**Variables to replace:** None

```lql
resource.type="bigquery_project" AND
logName:"cloudaudit.googleapis.com"
```

### BigQuery audit logs for a dataset

**Variables to replace:** None

```lql
resource.type="bigquery_dataset" AND
logName:"cloudaudit.googleapis.com"
```

### BigQuery audit logs for BI Engine model

**Variables to replace:** None

```lql
resource.type="bigquery_biengine_model" AND
logName:"cloudaudit.googleapis.com"
```

### BigQuery audit logs for a Data Transfer Service run.

**Variables to replace:** None

```lql
resource.type="bigquery_dts_run" AND
logName:"cloudaudit.googleapis.com"
```

### BigQuery audit logs for a Data Transfer Service configuration.

**Variables to replace:** None

```lql
resource.type="bigquery_dts_config" AND
logName:"cloudaudit.googleapis.com"
```

### BigQuery Data Transfer Service jobs

**Variables to replace:** None

```lql
resource.type="bigquery_project" AND
protoPayload.requestMetadata.callerSuppliedUserAgent=
"BigQuery Data Transfer Service" AND
protoPayload.methodName=("google.cloud.bigquery.v2.JobService.InsertJob" OR
"google.cloud.bigquery.v2.JobService.Query")
```

### BigQuery transfer run logs

**Variables to replace:** `<CONFIG_ID>`, `<RUN_ID>`

```lql
resource.type="bigquery_dts_config" AND
labels.run_id="<RUN_ID>" AND
resource.labels.config_id="<CONFIG_ID>"
```

### BigQuery dataset updates

**Variables to replace:** None

```lql
resource.type="bigquery_dataset" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="google.cloud.bigquery.v2.DatasetService.UpdateDataset"
```

### BigQuery jobs completed

**Variables to replace:** None

```lql
resource.type="bigquery_project" AND
log_id("cloudaudit.googleapis.com/data_access") AND
protoPayload.methodName=("google.cloud.bigquery.v2.JobService.InsertJob"
OR "google.cloud.bigquery.v2.JobService.Query")
```

### BigQuery quota exceeded

**Variables to replace:** None

```lql
resource.type=("bigquery_dataset" OR "bigquery_project")
AND
protoPayload.status.code=8 AND
severity>=WARNING
```

### BigQuery query started

**Variables to replace:** None

```lql
resource.type="bigquery_project" AND
protoPayload.metadata.jobInsertion.reason:*
```

### BigQuery concurrent load/extract jobs

**Variables to replace:** None

```lql
resource.type="bigquery_resource" AND
protoPayload.methodName="jobservice.insert" AND
protoPayload.serviceData.jobInsertRequest.resource.jobConfiguration.query.query:
"extract"
```

### BigQuery audit logs for row access policy

**Variables to replace:** None

```lql
resource.type="bigquery_resource" AND
protoPayload.methodName="jobservice.insert" AND
protoPayload.serviceData.jobInsertRequest.resource.jobConfiguration.query.query:"ROW ACCESS POLICY"
```
