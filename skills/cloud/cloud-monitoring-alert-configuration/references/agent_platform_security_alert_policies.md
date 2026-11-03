# Configure Security Alert Policies

These alert policies help users detect unusually high rates of permission denied
errors in their deployed agents.

## Table of Contents

-   [Verify Prerequisites](#verify-prerequisites): Lines 17-76
    -   [Enable Cloud Audit Logs and Cloud Logging](#enable-cloud-audit-logs-and-cloud-logging): Lines 19-26
    -   [Retrieve the Log Scope Observability Analytics Table](#retrieve-the-log-scope-observability-analytics-table): Lines 27-33
    -   [Link the BigQuery Dataset](#link-the-bigquery-dataset): Lines 34-76
-   [Follow Critical Rules](#follow-critical-rules): Lines 77-182
    -   [Configure High IAM Permission Denied Trigger Rate](#configure-high-iam-permission-denied-trigger-rate): Lines 86-182
-   [Run Tooling Scripts](#run-tooling-scripts): Lines 183-190
-   [Validate and Finalize](#validate-and-finalize): Lines 191-197

## Verify Prerequisites

### Enable Cloud Audit Logs and Cloud Logging

Security alert policies rely on Cloud Audit Logs and Cloud Logging to detect
high trigger rates of IAM permission denied errors. Display a note to the user
letting them know that Cloud Audit Logs and Cloud Logging export must be enabled
for all applicable services that their agent interacts with for Security alert
policies to work.

### Retrieve the Log Scope Observability Analytics Table

Retrieve the Observability Analytics table where all the Cloud Logging entries
are stored. See the `list_log_scope_table_names` entry in
[Run Tooling Scripts](#run-tooling-scripts) below for instructions on running
the retrieval tool.

### Link the BigQuery Dataset

A linked BigQuery dataset instance is required to configure alert policies
depending on Observability Analytics and Cloud Logging data. This dataset MUST
hold views for the `_Default` Cloud Logging bucket of the target Google Cloud
project.

Applicable BigQuery datasets have a `"type": "LINKED"` attribute and reference
the `_Default` bucket in their description. To list all existing BigQuery
datasets in a project, run the following command:

```bash
bq ls --format=prettyjson --project_id=$PROJECT_ID
```

Where:

*   `PROJECT_ID`: The target Google Cloud project ID.

If the Google Cloud project does not have a linked BigQuery dataset for the
Cloud Logging bucket, you MUST EXPLICITLY ask the user for confirmation before
proceeding to create one. If the user does not approve, you MUST skip creating
security alert policies. Otherwise, create a linked Cloud Logging dataset by
running the following command:

```bash
gcloud logging links create $LINK_ID \
  --bucket=$BUCKET_ID \
  --location=$LOCATION \
  --project=$PROJECT_ID
```

Where:

*   `PROJECT_ID`: The target Google Cloud project ID.
*   `LOCATION`: The location of the observability buckets. If unknown, the
    location is included in the Observability Analytics table name retrieved in
    [Retrieve the Log Scope Observability Analytics Table](#retrieve-the-log-scope-observability-analytics-table).
*   `BUCKET_ID`: The ID of the observability bucket. By default, this ID is
    `_Default`.
*   `LINK_ID`: The name of the new BigQuery dataset. Use
    `all_logs_bq_linked_dataset` as the default.

## Follow Critical Rules

*   **Alert policy configuration**: You MUST configure the following Security
    alerting policy. Proceed to the **Validate and Finalize** section below:
    1.  **High IAM Permission Denied Trigger Rate** (15-Minute window)
*   **SQL format**: Configure all Security alert policies using SQL queries. Do
    **NOT** use any other language such as PromQL or Monitoring Query Language
    (MQL).

### Configure High IAM Permission Denied Trigger Rate

#### Define the Security Telemetry Query

Use this query to configure the alert policy. Replace each variable enclosed in
curly braces (for example, `{placeholder}`) with the corresponding values
provided below:

```sql
WITH
  iam_agent_audit_logs AS (
    SELECT
      severity,
      proto_payload.audit_log.status.code AS status_code,
      proto_payload.audit_log.authentication_info.principal_email AS principal_email,
      proto_payload.audit_log.service_name AS service_name,
      proto_payload.audit_log.method_name AS method_name
    FROM
      `{log_scope_table_name}`
    WHERE
      proto_payload.type = "type.googleapis.com/google.cloud.audit.AuditLog"
  )
SELECT
  severity,
  status_code,
  principal_email,
  service_name,
  method_name,
  COUNT(*) AS trigger_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(PARTITION BY principal_email, method_name), 2) AS permission_denied_rate_percentage
FROM
  `iam_agent_audit_logs`
GROUP BY
  severity,
  status_code,
  principal_email,
  service_name,
  method_name
QUALIFY
  severity = "ERROR"
    AND
  status_code = 7
    AND
  principal_email LIKE '%gcp-sa-aiplatform-re.iam.gserviceaccount.com'
    AND
  permission_denied_rate_percentage >= 25
ORDER BY
  permission_denied_rate_percentage DESC
```

Where:

*   `{log_scope_table_name}`: The Observability Analytics table name for the
    Cloud Logging scope retrieved in
    [Verify Prerequisites](#verify-prerequisites).

#### Define Terraform HCL for Security Alerts

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` condition:

```terraform
resource "google_monitoring_alert_policy" "high_iam_permission_denied_trigger_rate" {
  project      = var.project_id
  display_name = "Agent Security - High IAM Permission Denied Trigger Rate"
  combiner     = "OR"

  conditions {
    display_name = "High IAM Permission Denied Trigger Rate Exceeds 25%"
    condition_sql {
      query =  {iam_high_permission_denied_rate_telemetry_query}

      # Run evaluation periodically
      minutes {
        periodicity = 5
      }

      # Test triggers when one or more models violate the threshold (returning rows)
      row_count_test {
        comparison = "COMPARISON_GT"
        threshold  = 0
      }
    }
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

Where:

*   `{iam_high_permission_denied_rate_telemetry_query}`: The SQL alert query
    configured in [Define the Security Telemetry Query](#define-the-security-telemetry-query)
    above.

## Run Tooling Scripts

1.  **list_log_scope_table_names (Fallback)**: Use this script ONLY if
    `gather_agent_info.py` fails to retrieve the associated Observability
    Analytics SQL table name for the Cloud Logging scope:
    *   Command: `python3 scripts/agent_platform/list_log_scope_table_names.py
        --project_id={gcp_project}`

## Validate and Finalize

*   **Handle Script Failures**: If `list_log_scope_table_names.py` fails
    unexpectedly, verify the project ID. Ensure you have permissions to list
    Cloud Logging scopes and linked datasets. If no table is found, verify
    whether a linked BigQuery dataset exists as described in
    [Verify Prerequisites](#verify-prerequisites).
