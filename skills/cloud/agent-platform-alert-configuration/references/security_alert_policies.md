# Security Alert Policies

These alert policies will help users detect unusually high rates of permission
denied errors in their deployed agents.

## Table of Contents

-   [Prerequisites](#prerequisites) (~Line 23)
    -   [Audit logging](#audit-logging) (~Line 25)
    -   [Log Scope Observability Analytics table](#log-scope-observability-analytics-table)
        (~Line 32)
    -   [BigQuery dataset](#bigquery-dataset) (~Line 38)
-   [Critical Rules](#critical-rules) (~Line 80)
    -   [High IAM Permission Denied Trigger Rate](#high-iam-permission-denied-trigger-rate)
        (~Line 89)
-   [Tooling Scripts](#tooling-scripts) (~Line 181)

## Prerequisites

### Audit logging

Security alert policies rely on Cloud Audit Logs to detect high trigger rates of
IAM permission denied errors. You MUST display a note to the user letting them
know that audit logging must be enabled for all applicable services that their
agent interacts with for Security alert policies to work.

### Log Scope Observability Analytics table

You will need to retrieve the Observability Analytics table where all the log
entries are stored. See the `list_log_scope_table_names` entry in the `Tooling
Scripts` section below for more information on how to run the retrieval tool.

### BigQuery dataset

A linked BigQuery dataset instance is required to configure alert policies
depending on Observability Analytics logging data. This dataset MUST hold views
for the `_Default` log bucket of the target GCP project.

Applicable BigQuery datasets have a `"type": "LINKED"` attribute and reference
the `_Default` bucket in their description. To list all existing BigQuery
datasets in a project run the following command:

```bash
bq ls --format=prettyjson --project_id=$PROJECT_ID
```

Where:

*   `PROJECT_ID`: The target GCP project id.

If the GCP project does not have a linked BQ dataset to the Log bucket, you MUST
EXPLICITLY ask the user for confirmation before proceeding to create one. If the
user does not approve, you MUST skip creating security alert policies.
Otherwise, you can create a linked logging dataset by running the following
command:

```bash
gcloud logging links create $LINK_ID \
  --bucket=$BUCKET_ID \
  --location=$LOCATION \
  --project=$PROJECT_ID
```

Where:

*   `PROJECT_ID`: The target GCP project id.
*   `LOCATION`: The location of the observability buckets. If unknown, the
    location is included in the Observability Analytics table name retrieved in
    the previous section `Log Scope Observability Analytics table`.
*   `BUCKET_ID`: The ID of the observability bucket. By default, this ID will be
    `_Default`.
*   `LINK_ID`: The name of the new BigQuery dataset. Use
    `all_logs_bq_linked_dataset` as the default.

## Critical Rules

*   **Alert policy configuration**: You MUST configure exactly the following
    Security alerting policies. See the `Telemetry Metrics` to get the required
    metrics and read the descriptions for each signal:
    1.  **High IAM Permission Denied Trigger Rate** (15-Minute window)
*   **SQL format**: All Security alert policies must be configured using SQL
    queries. Do **NOT** use any other language like PromQL or MQL.

### High IAM Permission Denied Trigger Rate

#### Telemetry query

Use this script to configure the alert policy. Replace each variable enclosed
in curly braces (e.g., `{placeholder}`) with the corresponding values
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

*   `{log_scope_table_name}`: The Log scope observability analytics table name
    retrieved in the `Prerequisites` section.

#### Terraform HCL

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` check:

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

Where:

*   `{iam_high_permission_denied_rate_telemetry_query}`: The SQL alert query
    configured in the `Telemetry query` section above.

## Tooling Scripts

1.  **list_log_scope_table_names (Fallback)**: Use this script ONLY if `gather_agent_info.py` failed to retrieve the associated Log scope observability SQL table name.
    *   Command: `python3 scripts/list_log_scope_table_names.py
        --project_id={gcp_project}`

## Gotchas and Behavioral Corrections

*   **Script Failures**: If `list_log_scope_table_names.py` fails unexpectedly,
    verify the project ID. Ensure you have permissions to list log scopes and
    linked datasets. If no table is found, verify if a linked BigQuery dataset
    exists as per prerequisites.
