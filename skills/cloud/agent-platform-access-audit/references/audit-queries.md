# Agent Access Audit SQL Queries Reference

## Table of contents

- [1. Query parameters and table conventions](#1-query-parameters-and-table-conventions): Lines 14-60
- [2. Scenario 1: Successful data access audit logs (individual operations)](#2-scenario-1-successful-data-access-audit-logs-individual-operations): Lines 62-107
- [3. Scenario 2: Blast radius traversal (top services, originating principals, and activity)](#3-scenario-2-blast-radius-traversal-top-services-originating-principals-and-activity): Lines 109-238
- [4. Scenario 4: Blocked data access attempt logs (VPC-SC vs. IAM denials)](#4-scenario-4-blocked-data-access-attempt-logs-vpc-sc-vs-iam-denials): Lines 240-304
- [5. Cloud Audit Logs (_AllLogs) schema dictionary](#5-cloud-audit-logs-_alllogs-schema-dictionary): Lines 306-335
- [6. Supporting Google Cloud documentation](#6-supporting-google-cloud-documentation): Lines 337-359

--------------------------------------------------------------------------------

## 1. Query parameters and table conventions

All queries execute against the Google Cloud project's Log Analytics view using
GoogleSQL with parameterized inputs (`bq query --use_legacy_sql=false
--format=json --parameter="principal_subject:STRING:{PRINCIPAL_SUBJECT}"`):

*   **Table Path:** `` `{PROJECT_ID}.global._Default._AllLogs` ``

    *   If the project's `_Default` log bucket is accessed via a linked BigQuery
        dataset (`gcloud logging links list --bucket=_Default --location=global
        --project={PROJECT_ID}`), or if the user specifies a custom
        dataset/table path, substitute `global._Default._AllLogs` with
        `{LINK_ID}._AllLogs`.

*   **Required Variables and Query Parameters:**

    *   `{PROJECT_ID}` and `{LINK_ID}`: The Google Cloud project ID
        and linked dataset ID hosting the log bucket. Because BigQuery does not
        support `@` query parameters for table or dataset identifiers in `FROM`
        clauses, validate that both values match `^[a-z0-9_-]+$` before
        substituting into `` `{PROJECT_ID}.{LINK_ID}._AllLogs` ``. If
        `{PROJECT_ID}` is omitted in the user prompt, resolve it first by
        running `gcloud config get-value project`. Never leave `{PROJECT_ID}` as
        a literal placeholder in an executed query.
    *   `@principal_subject` (`{PRINCIPAL_SUBJECT}`): The exact SPIFFE/principal
        identity string of the agent (the only supported format is a
        `principal://...` URI, never an agent display name). Never interpolate
        `{PRINCIPAL_SUBJECT}` directly into the SQL query string. Always keep
        `@principal_subject` in the SQL `WHERE` clause and bind the value via
        `bq query`'s `--parameter` flag:
        `--parameter="principal_subject:STRING:{PRINCIPAL_SUBJECT}"`

*   **Identity Matching Rule:** Every query filtering by `@principal_subject`
    **must** check direct identity:
    `logs.proto_payload.audit_log.authentication_info.principal_subject =
    @principal_subject`

*   **Time-Window Filter:** By default, retrieve queries from the last 7 days
    and inform the user of this default. When the user specifies a time window
    (for example, "last 24 hours", "last 7 days", or "last 30 days"), append the
    following predicate to the `WHERE` clause:

    ```sql
    AND logs.timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL <N> <HOUR|DAY>)
    ```

--------------------------------------------------------------------------------

## 2. Scenario 1: Successful data access audit logs (individual operations)

Use this query when the user asks to:

*   Inspect the data access history or recent operations of an agent.
*   Determine whether an agent performed `DATA_READ`, `DATA_WRITE`,
    `ADMIN_READ`, or `ADMIN_WRITE` operations.
*   Identify which originating principal, API method (`method_name`), or agent
    accessed a specific `target_resource` (such as a BigQuery table or Cloud
    Storage bucket).

### SQL Template: Successful Data Access Logs

```sql
SELECT
  -- Timestamp
  logs.timestamp AS log_time,

  -- Principal Subject
  logs.proto_payload.audit_log.authentication_info.principal_subject AS original_principal,

  -- Authorization Info
  IF(
    COALESCE(logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted, TRUE),
    COALESCE(
      logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type,
      IF(logs.proto_payload.audit_log.method_name LIKE '%Insert%' OR logs.proto_payload.audit_log.method_name LIKE '%Write%', 'DATA_WRITE', 'DATA_READ')
    ),
    'BLOCKED_READ'
  ) AS operation,

  -- Method Name
  logs.proto_payload.audit_log.method_name AS method_name,

  -- Resource Name
  logs.proto_payload.audit_log.resource_name AS target_resource

FROM `{PROJECT_ID}.global._Default._AllLogs` AS logs
WHERE logs.proto_payload.audit_log IS NOT NULL
  AND IFNULL(logs.proto_payload.audit_log.status.code, 0) = 0
  AND logs.proto_payload.audit_log.authentication_info.principal_subject = @principal_subject

ORDER BY logs.timestamp DESC
```

--------------------------------------------------------------------------------

## 3. Scenario 2: Blast radius traversal (top services, originating principals, and activity)

Use these queries when the user asks to assess the blast radius of an agent:
which Google Cloud services it touches most frequently, its read vs. write
volume, who is invoking/delegating to it, or its access activity breakdown.

### Query 2A: Top 5 Google Cloud Services Accessed (Read vs. Write Counts)

Extracts the short service prefix (e.g., `storage`, `bigquery`, `cloudkms`,
`iam`) from `service_name` and aggregates granted read (`DATA_READ`,
`ADMIN_READ`) and write (`DATA_WRITE`, `ADMIN_WRITE`) counts.

```sql
SELECT
  -- Google Cloud service name (e.g. 'storage', 'bigquery', 'cloudkms')
  REGEXP_EXTRACT(logs.proto_payload.audit_log.service_name, r'^([^.]+)') AS service,

  -- Sum Read Operations
  COUNTIF(
    logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted = TRUE
    AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type IN ('DATA_READ', 'ADMIN_READ')
  ) AS read_value,

  -- Sum Write Operations
  COUNTIF(
    logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted = TRUE
    AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type IN ('DATA_WRITE', 'ADMIN_WRITE')
  ) AS write_value

FROM `{PROJECT_ID}.global._Default._AllLogs` AS logs
WHERE logs.proto_payload.audit_log IS NOT NULL
  AND logs.proto_payload.audit_log.service_name IS NOT NULL
  AND IFNULL(logs.proto_payload.audit_log.status.code, 0) = 0
  AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type IS NOT NULL
  AND logs.proto_payload.audit_log.authentication_info.principal_subject = @principal_subject

GROUP BY service
HAVING (read_value > 0 OR write_value > 0)
ORDER BY read_value DESC, write_value DESC
LIMIT 5
```

### Query 2B: Top 5 Originating Principals

Identifies the top 5 callers triggering or delegating to the agent; for this
release, only agent identity via `principal_subject` is supported.

```sql
WITH raw_principals AS (
  SELECT
    COALESCE(
      NULLIF(logs.proto_payload.audit_log.authentication_info.principal_email, ''),
      NULLIF(logs.proto_payload.audit_log.authentication_info.principal_subject, '')
    ) AS raw_principal
  FROM `{PROJECT_ID}.global._Default._AllLogs` AS logs
  WHERE logs.proto_payload.audit_log IS NOT NULL
  AND IFNULL(logs.proto_payload.audit_log.status.code, 0) = 0
  AND logs.proto_payload.audit_log.authentication_info.principal_subject = @principal_subject
)

SELECT
  -- Automatically prefixes identity based on principal format
  CASE
    WHEN raw_principal LIKE 'urn:agent:%'
      OR raw_principal LIKE 'principal://%'
      OR raw_principal LIKE '%/reasoningEngines/%'
      THEN CONCAT('agent: ', raw_principal)
    WHEN raw_principal LIKE '%.gserviceaccount.com'
      OR raw_principal LIKE '%@cloudservices.gserviceaccount.com'
      OR raw_principal LIKE 'service-%'
      THEN CONCAT('serviceAccount: ', raw_principal)
    ELSE CONCAT('human: ', raw_principal)
  END AS formatted_principal,

  -- Count total agent executions triggered by principal
  COUNT(1) AS invocation_count

FROM raw_principals
WHERE raw_principal IS NOT NULL
GROUP BY formatted_principal
ORDER BY invocation_count DESC
LIMIT 5
```

### Query 2C: Access Activity Over Time (`DATA_READ`, `DATA_WRITE`, `ADMIN_READ`, `ADMIN_WRITE`)

Use this query when the user asks to break down granted access events by
permission category (`DATA_READ`, `DATA_WRITE`, `ADMIN_READ`, `ADMIN_WRITE`)
over time.

```sql
SELECT
  -- Timestamp
  logs.timestamp AS timestamp,

  -- Data Read Count
  IF(
    logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted = TRUE
    AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type = 'DATA_READ',
    1, 0
  ) AS DATA_READ,

  -- Data Write Count
  IF(
    logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted = TRUE
    AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type = 'DATA_WRITE',
    1, 0
  ) AS DATA_WRITE,

  -- Admin Read Count
  IF(
    logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted = TRUE
    AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type = 'ADMIN_READ',
    1, 0
  ) AS ADMIN_READ,

  -- Admin Write Count
  IF(
    logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted = TRUE
    AND logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type = 'ADMIN_WRITE',
    1, 0
  ) AS ADMIN_WRITE

FROM `{PROJECT_ID}.global._Default._AllLogs` AS logs
WHERE logs.proto_payload.audit_log IS NOT NULL
  AND IFNULL(logs.proto_payload.audit_log.status.code, 0) = 0
  AND logs.proto_payload.audit_log.authentication_info.principal_subject = @principal_subject
```

--------------------------------------------------------------------------------

## 4. Scenario 4: Blocked data access attempt logs (VPC-SC vs. IAM denials)

Use this query when the user asks:

*   Why an agent is receiving `PERMISSION_DENIED` (`status.code = 7`) errors.
*   What operations (`BLOCKED_READ` vs. `BLOCKED_WRITE`) were denied.
*   Whether an access attempt was blocked by a **VPC Service Controls (VPC-SC)
    perimeter violation** or a standard **IAM permission denial**.
*   What specific method was invoked (`method_name`) and on which target
    resource (`resource_name`) for a blocked access attempt.

### SQL Template: Blocked Data Access Attempts (`status.code = 7`)

```sql
SELECT
  -- 1. Timestamp
  logs.timestamp AS log_time,

  -- 2. Block Reason
  CASE
    WHEN
      JSON_VALUE(logs.proto_payload.audit_log.metadata.vpcServiceControlsUniqueId) IS NOT NULL
      OR JSON_VALUE(logs.proto_payload.audit_log.metadata.vpcServiceControlsTroubleshootToken)
        IS NOT NULL
      OR JSON_VALUE(logs.proto_payload.audit_log.metadata.vpc_service_controls_unique_id)
        IS NOT NULL
      OR logs.proto_payload.audit_log.status.message LIKE '%vpcServiceControlsUniqueIdentifier%'
      OR logs.proto_payload.audit_log.status.message LIKE '%prohibited by organization%policy%'
      OR logs.proto_payload.audit_log.status.message LIKE '%VPC Service Controls%'
  THEN 'VPC service controls violation'
  ELSE 'IAM permission denied'
END AS block_reason,

  -- 3. Attempted Operation (BLOCKED_READ / BLOCKED_WRITE)
  CASE
    WHEN logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission LIKE '%create%'
      OR logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission LIKE '%update%'
      OR logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission LIKE '%delete%'
      OR logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission LIKE '%write%'
      OR logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission LIKE '%set%'
      OR logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission LIKE '%insert%'
      OR logs.proto_payload.audit_log.method_name LIKE '%Create%'
      OR logs.proto_payload.audit_log.method_name LIKE '%Insert%'
      OR logs.proto_payload.audit_log.method_name LIKE '%Write%'
      OR logs.proto_payload.audit_log.method_name LIKE '%Update%'
      OR logs.proto_payload.audit_log.method_name LIKE '%Delete%'
    THEN 'BLOCKED_WRITE'
    ELSE 'BLOCKED_READ'
  END AS attempted_operation,

  -- 4. Attempted Method Name
  logs.proto_payload.audit_log.method_name AS attempted_method_name,

  -- 5. Attempted Target Resource
  logs.proto_payload.audit_log.resource_name AS attempted_target_resource

FROM `{PROJECT_ID}.global._Default._AllLogs` AS logs
WHERE logs.proto_payload.audit_log IS NOT NULL
  AND logs.proto_payload.audit_log.status.code = 7
  AND logs.proto_payload.audit_log.authentication_info.principal_subject = @principal_subject

ORDER BY log_time DESC
```

--------------------------------------------------------------------------------

## 5. Cloud Audit Logs (`_AllLogs`) schema dictionary

Use this dictionary when constructing custom `WHERE` clauses or follow-up
queries against `` `{PROJECT_ID}.global._Default._AllLogs` ``. When adding a
custom `WHERE` filter on any `STRING` column from user-supplied input (such as
filtering by `resource_name` or `method_name`), bind the value using a named
query parameter (for example, `= @target_resource` with
`--parameter="target_resource:STRING:<value>"`) rather than concatenating raw
strings into the SQL query:

| Field Concept | `_AllLogs` SQL Column Path | Type | Description / Example Values |
| :--- | :--- | :--- | :--- |
| **Timestamp** | `logs.timestamp` | `TIMESTAMP` | Time the audit event was recorded (`2026-10-14T15:28:41Z`). |
| **Log ID / Name** | `logs.log_id` / `logs.log_name` | `STRING` | Audit log stream (`cloudaudit.googleapis.com/data_access`, `cloudaudit.googleapis.com/activity`, `cloudaudit.googleapis.com/policy`). |
| **Severity** | `logs.severity` | `STRING` | Log severity (`INFO`, `NOTICE`, `WARNING`, `ERROR`). |
| **Direct Principal Email** | `logs.proto_payload.audit_log.authentication_info.principal_email` | `STRING` | Email of the authenticated caller; empty for 3P/federated `principal://` identities. |
| **Direct Principal Subject** | `logs.proto_payload.audit_log.authentication_info.principal_subject` | `STRING` | String representation of the caller identity (`principal://...`). |
| **Service Name** | `logs.proto_payload.audit_log.service_name` | `STRING` | API service name (`storage.googleapis.com`, `bigquery.googleapis.com`, `iam.googleapis.com`). |
| **Method Name** | `logs.proto_payload.audit_log.method_name` | `STRING` | API method invoked (`google.storage.buckets.list`, `google.cloud.bigquery.v2.JobService.InsertJob`). |
| **Target Resource** | `logs.proto_payload.audit_log.resource_name` | `STRING` | Target Google Cloud resource URI (`projects/my-proj/datasets/ds/tables/tbl`). |
| **Status Code** | `logs.proto_payload.audit_log.status.code` | `INT64` | gRPC status code (`7` = `PERMISSION_DENIED`). |
| **Status Message** | `logs.proto_payload.audit_log.status.message` | `STRING` | Error message; contains `vpcServiceControlsUniqueIdentifier: <id>` on VPC-SC denials. |
| **Auth Granted** | `logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].granted` | `BOOL` | `TRUE` if the permission check succeeded; `FALSE` if denied. |
| **Permission Type** | `logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission_type` | `STRING` | `DATA_READ`, `DATA_WRITE`, `ADMIN_READ`, or `ADMIN_WRITE`. |
| **IAM Permission** | `logs.proto_payload.audit_log.authorization_info[SAFE_OFFSET(0)].permission` | `STRING` | Checked IAM permission string (`storage.buckets.list`, `bigquery.tables.updateData`). |
| **VPC-SC Unique ID** | `JSON_VALUE(logs.proto_payload.audit_log.metadata.vpcServiceControlsUniqueId)` | `STRING` | Unique identifier for a VPC Service Controls violation (`null` for standard IAM denials). |
| **VPC-SC Troubleshoot Token** | `JSON_VALUE(logs.proto_payload.audit_log.metadata.vpcServiceControlsTroubleshootToken)` | `STRING` | Encrypted troubleshooting token populated on VPC Service Controls violations. |
| **VPC-SC Violation Reason** | `JSON_VALUE(logs.proto_payload.audit_log.metadata.violationReason)` | `STRING` | Reason for VPC-SC block (e.g., `RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER`). |

--------------------------------------------------------------------------------

## 6. Supporting Google Cloud documentation

All SQL templates and column paths in this reference are grounded in Google
Cloud's publicly documented **Log Analytics (`_AllLogs`)** view schema and the
standard **Cloud Audit Logs (`google.cloud.audit.AuditLog`)** protobuf
definition. When constructing custom queries, interpreting agent caller
identities (`principal_subject`), or troubleshooting VPC Service Controls
perimeter blocks (`VpcServiceControlAuditMetadata`), refer to the official
public documentation below:

*   **Log Analytics & `_AllLogs` Schema:**
    *   [Query and analyze logs with Log Analytics](https://docs.cloud.google.com/logging/docs/analyze/query-and-view.md.txt)
    *   [Query a linked BigQuery dataset (`_AllLogs` view)](https://docs.cloud.google.com/logging/docs/analyze/query-linked-dataset.md.txt)
    *   [Sample SQL queries for Log Analytics](https://docs.cloud.google.com/logging/docs/analyze/examples.md.txt)
*   **Cloud Audit Logs (`AuditLog` Schema & Identities):**
    *   [`AuditLog` REST & Protobuf reference (`AuthenticationInfo`, `AuthorizationInfo`)](https://docs.cloud.google.com/logging/docs/reference/audit/auditlog/rest/Shared.Types/AuditLog.md.txt)
    *   [Open-source `audit_log.proto` definition (`googleapis/googleapis`)](https://github.com/googleapis/googleapis/blob/master/google/cloud/audit/audit_log.proto)
    *   [Understanding Cloud Audit Logs & caller identities (`principalEmail` vs. `principalSubject`)](https://docs.cloud.google.com/logging/docs/audit/understanding-audit-logs.md.txt)
*   **VPC Service Controls Audit Metadata:**
    *   [`VpcServiceControlAuditMetadata` schema reference (`vpcServiceControlsUniqueId`, `violationReason`)](https://docs.cloud.google.com/vpc-service-controls/docs/audit-logging.md.txt)
    *   [Troubleshoot VPC Service Controls violations using `vpcServiceControlsUniqueId`](https://docs.cloud.google.com/vpc-service-controls/docs/troubleshooting.md.txt)
*   **CLI Execution (`bq` & `gcloud`):**
    *   [BigQuery `bq query` CLI reference](https://docs.cloud.google.com/bigquery/docs/reference/bq-cli-reference#bq_query)
