# Safety Alert Policies

These alert policies will help users detect high trigger rates of Model Armor
policy violations in their deployed agents caused by prompt injections, false
positives, or hallucinations.

## Table of Contents

-   [Prerequisites](#prerequisites) (~Line 24)
    -   [Trace Scope Observability Analytics table](#trace-scope-observability-analytics-table)
        (~Line 26)
    -   [BigQuery dataset](#bigquery-dataset) (~Line 33)
-   [Critical Rules](#critical-rules) (~Line 78)
    -   [High Model Armor Safety Policy Trigger Rate](#high-model-armor-safety-policy-trigger-rate)
        (~Line 87)
-   [Tooling Scripts](#tooling-scripts) (~Line 198)

## Prerequisites

### Trace Scope Observability Analytics table

You will need to retrieve the Observability Analytics table where all the Trace
scope spans are stored. See the `list_trace_scope_table_names` entry in the
`Tooling Scripts` section below for more information on how to run the retrieval
tool.

### BigQuery dataset

A linked BigQuery dataset instance is required to configure alert policies
depending on Observability Analytics trace data. This dataset MUST hold views
for the `_Trace` trace bucket of the target GCP project.

Applicable BigQuery datasets have a `"type": "LINKED"` attribute and reference
the `_Trace` bucket in their description. To list all existing BigQuery datasets
in a project run the following command:

```bash
bq ls --format=prettyjson --project_id=$PROJECT_ID
```

Where:

*   `PROJECT_ID`: The target GCP project id.

If the GCP project does not have a linked BQ dataset to the Trace bucket, you
MUST EXPLICITLY ask the user for confirmation before proceeding to create one.
If the user does not approve, you MUST skip creating safety alert policies.
Otherwise, you can create a linked dataset by running the following command:

```bash
gcloud beta observability buckets datasets links create \
  projects/$PROJECT_ID/locations/$LOCATION/buckets/$BUCKET_ID/datasets/$DATASET_ID/links/$LINK_ID \
 --dataset=$DATASET_ID \
 --bucket=$BUCKET_ID \
 --location=$LOCATION \
 --project=$PROJECT_ID
```

Where:

*   `PROJECT_ID`: The target GCP project id.
*   `LOCATION`: The location of the observability buckets. If unknown, the
    location is included in the Observability Analytics table name retrieved in
    the previous section `Trace Scope Observability Analytics table`.
*   `BUCKET_ID`: The ID of the observability bucket. By default, this ID will be
    `_Trace`.
*   `DATASET_ID`: The ID of the dataset. By default, the trace data is stored in
    a dataset named `Spans`.
*   `LINK_ID`: The name of the new BigQuery dataset. Use
    `trace_bq_linked_dataset` as the default.

## Critical Rules

*   **Alert policy configuration**: You MUST configure exactly the following
    Safety alerting policies. See the `Telemetry Metrics` to get the required
    metrics and read the descriptions for each signal:
    1.  **High Model Armor Safety Policy Trigger Rate** (15-Minute window)
*   **SQL format**: All Safety alert policies must be configured using SQL
    queries. Do **NOT** use any other language like PromQL or MQL.

### High Model Armor Safety Policy Trigger Rate

#### Telemetry query

Use this script to configure the alert policy. Replace each variable enclosed
in curly braces (e.g., `{placeholder}`) with the corresponding values provided
below:

```sql
WITH
  trace_to_agent AS (
  SELECT
    DISTINCT trace_id,
    JSON_VALUE(resource.attributes, '$."cloud.platform"') AS cloud_platform,
    JSON_VALUE(resource.attributes, '$."cloud.resource_id"') AS agent_id,
    JSON_VALUE(attributes, '$."gen_ai.agent.name"') AS agent_name
  FROM
    `{trace_scope_table_name}`
  WHERE
    JSON_VALUE(resource.attributes, '$."cloud.platform"') = "gcp.agent_engine"
      AND
    JSON_VALUE(resource.attributes, '$."cloud.resource_id"') IS NOT NULL
      AND
    JSON_VALUE(attributes, '$."gen_ai.agent.name"') IS NOT NULL
),
  all_model_armor_spans AS (
  SELECT
    s.*,
    t2a.agent_name,
    t2a.agent_id
  FROM
    `{trace_scope_table_name}` s
  FULL JOIN
    `trace_to_agent` t2a ON s.trace_id = t2a.trace_id
  WHERE
    JSON_VALUE(resource.attributes, '$."service.name"') = "modelarmor"
      AND
    name IN ('Request Path', 'Response Path')
      AND
    t2a.agent_name IS NOT NULL
      AND
    t2a.agent_id IS NOT NULL
)
SELECT
  agent_id,
  agent_name,
  violation,
  JSON_VALUE(attributes, '$."gen_ai.security.policy.id"') AS policy_id,
  COUNT(*) AS trigger_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(PARTITION BY agent_id), 2) AS trigger_rate_percentage
FROM
  `all_model_armor_spans`
  LEFT JOIN
    UNNEST(JSON_VALUE_ARRAY(attributes, '$."gcp.modelarmor.violations"')) AS violation
GROUP BY
  agent_id,
  agent_name,
  violation,
  policy_id
QUALIFY
  violation IS NOT NULL
    AND
  trigger_rate_percentage >= 25
ORDER BY
  trigger_rate_percentage DESC
```

Where:

*   `{trace_scope_table_name}`: The Trace scope observability analytics table
    name retrieved in the `Prerequisites` section.

#### Terraform HCL

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` check:

```terraform
resource "google_monitoring_alert_policy" "high_model_armor_safety_policy_trigger_rate" {
  project      = var.project_id
  display_name = "Agent Safety - High Model Armor Safety Policy Trigger Rate"
  combiner     = "OR"

  conditions {
    display_name = "Agent High Model Armor Safety Policy Trigger Rate Exceeds 25%"
    condition_sql {
      query =  {model_armor_trigger_high_rate_telemetry_query}


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

*   `{model_armor_trigger_high_rate_telemetry_query}`: The SQL alert query
    configured in the `Telemetry query` section above.

## Tooling Scripts

1.  **list_trace_scope_table_names (Fallback)**: Use this script ONLY if `gather_agent_info.py` failed to retrieve the associated Trace scope observability SQL table name.
    *   Command: `python3 scripts/list_trace_scope_table_names.py
        --project_id={gcp_project}`

## Gotchas and Behavioral Corrections

*   **Script Failures**: If `list_trace_scope_table_names.py` fails
    unexpectedly, verify the project ID. Ensure you have permissions to list
    trace scopes and linked datasets. If no table is found, verify if a linked
    BigQuery dataset exists as per prerequisites.
