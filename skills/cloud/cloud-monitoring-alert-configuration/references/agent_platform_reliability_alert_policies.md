# Configure Reliability Alert Policies

These alert policies help users pinpoint the root cause of ongoing increased
agent latency and high error rates with model and tool requests.

> [!IMPORTANT]
> **Full Production Agent Configuration Requirements**: When configuring full production alerts for an AI agent, you **MUST** read all five policy references ([Reliability](agent_platform_reliability_alert_policies.md), [Quality](agent_platform_quality_alert_policies.md), [Cost](agent_platform_cost_alert_policies.md), [Safety](agent_platform_safety_alert_policies.md), and [Security](agent_platform_security_alert_policies.md)) and:
> 1. Generate **11 alerting policies** (5 reliability, 3 quality, 1 cost, 1 safety, and 1 security including High IAM Permission Denied Trigger Rate).
> 2. Always include all four pre-populated supporting script commands with all parameter values filled in (even if a fallback table name is provided):
>    * **Streamlined Discovery**: `python3 scripts/agent_platform/gather_agent_info.py --project-id "<project_id>" --agent-name "<agent_name>"`
>    * **Telemetry Verification**: `python3 scripts/agent_platform/check_telemetry.py --project-id "<project_id>" --location "us-central1" --agent-resource-name "projects/<project_id>/locations/us-central1/reasoningEngines/<agent_id>" --query-monitoring-metadata`
>    * **Online Monitor Provisioning**: `python3 scripts/agent_platform/create_online_monitor.py --project-id "<project_id>" --agent-resource-name "projects/<project_id>/locations/us-central1/reasoningEngines/<agent_id>"`
>    * **Duplicate Policy Scanner**: `python3 scripts/agent_platform/scan_duplicates.py monitoring/`
> 3. If Online Monitor provisioning or Telemetry enablement is not pre-approved in the prompt, you **MUST** warn the user about the potential billing costs of **both** the **Online Monitor** and **Telemetry (Cloud Trace/Logging export)** and include an explicit direct question asking the user for approval before configuring or provisioning them.
> 4. Always prompt the user to ask whether they would like to configure notification channels if none were provided.
> 5. Include a `user_labels` block with `created-with-google-skill = "cloud-monitoring-alert-configuration"` on every `google_monitoring_alert_policy` resource.

## Table of Contents

-   [Verify Prerequisites](#verify-prerequisites): Lines 34-110
    -   [Prepare SQL Metric Prerequisites](#prepare-sql-metric-prerequisites): Lines 36-82
    -   [Prepare PromQL Metric Prerequisites](#prepare-promql-metric-prerequisites): Lines 83-110
-   [Follow Critical Rules](#follow-critical-rules): Lines 111-149
    -   [Review Telemetry Metrics](#review-telemetry-metrics): Lines 136-149
-   [Configure Policy Specifications](#configure-policy-specifications): Lines 150-587
    -   [Configure Latency Alerts](#configure-latency-alerts): Lines 152-286
    -   [Configure Error Rate Fast Burn SLO (1-Hour and 5-Minute Windows)](#configure-error-rate-fast-burn-slo-1-hour-and-5-minute-windows): Lines 287-382
    -   [Configure Error Rate Slow Burn SLO (3-Day and 6-Hour Windows)](#configure-error-rate-slow-burn-slo-3-day-and-6-hour-windows): Lines 383-440
    -   [Configure Model Call Error Rate Alerts](#configure-model-call-error-rate-alerts): Lines 441-514
    -   [Configure Tool Call Error Rate Alerts](#configure-tool-call-error-rate-alerts): Lines 515-587
-   [Run Tooling Scripts](#run-tooling-scripts): Lines 588-610
-   [Validate and Finalize](#validate-and-finalize): Lines 611-663

## Verify Prerequisites

### Prepare SQL Metric Prerequisites

#### Retrieve the Trace Scope Observability Analytics Table

Retrieve the Observability Analytics table where all the Trace scope spans are
stored for the SQL-based alerts.

#### Link the BigQuery Dataset

A linked BigQuery dataset instance is required to configure SQL alert policies
depending on Observability Analytics trace data. This dataset MUST hold views
for the `_Trace` trace bucket of the target Google Cloud project.

Applicable BigQuery datasets have a `"type": "LINKED"` attribute and reference
the `_Trace` bucket in their description. To list all existing BigQuery datasets
in a project, run the following command:

```bash
bq ls --format=prettyjson --project_id={project_id}
```

Where:

*   `{project_id}`: The target Google Cloud project ID.

If missing, you MUST get user confirmation before creating it. If denied, skip
SQL reliability alerts. Otherwise, create it using:

```bash
gcloud beta observability buckets datasets links create \
  projects/{project_id}/locations/{location}/buckets/{bucket_id}/datasets/{dataset_id}/links/{link_id} \
 --dataset={dataset_id} \
 --bucket={bucket_id} \
 --location={location} \
 --project={project_id}
```

Where:

*   `{project_id}`: Target Google Cloud project ID.
*   `{location}`: Observability bucket location (found in the Observability
    Analytics table name).
*   `{bucket_id}`: Bucket ID (default: `_Trace`).
*   `{dataset_id}`: Dataset ID (default: `Spans`).
*   `{link_id}`: New BigQuery dataset name (default:
    `trace_bq_linked_dataset`).

### Prepare PromQL Metric Prerequisites

#### Select Algorithms and Map Policies

Alerting policies for agents MUST map to the appropriate algorithms to ensure
statistical stability and prevent alert noise or blind spots based on data
classes:

*   **Latency**: Follows the workload traffic pattern (Steady / Consistent ->
    `1w Z-Score Baseline` or `Short-Window Z-Score (1h baseline)`; Seasonal /
    Cyclical -> `Seasonal Decomposition (average 1w and 1d)`; Bursty /
    Inconsistent -> `Moving Averages`).
*   **Error Rate**: ALWAYS use **Multi-Window Multi-Burn Rate SLOs** (or
    ratio-based static thresholds). Error rate is naturally sparse (`0`). If
    standard deviation is `0`, Z-scores are mathematically unstable
    (division-by-zero), causing false alerts.

To resolve the workload traffic pattern (Seasonal / Cyclical, Steady /
Consistent, or Bursty / Inconsistent), follow the instructions corresponding to
the availability of historical metrics data:

*   **Case 1: No historical metrics data available (for example, brand new agent)**:
    You MUST read and follow:
    [agent_platform_no_historical_traffic_data.md](agent_platform_no_historical_traffic_data.md)
*   **Case 2: Historical metrics data available (for example, active agent with
    traffic)**: You MUST read and follow:
    [agent_platform_has_historical_traffic_data.md](agent_platform_has_historical_traffic_data.md)

## Follow Critical Rules

*   **Brand New Agents (No Traffic History)**: When setting up alerts for a
    brand new agent, you MUST explicitly ask the user what traffic pattern they
    expect (Steady / Consistent, Seasonal / Cyclical, or Bursty / Inconsistent)
    in your response. If immediate setup is requested, ask the question but
    proceed using the default Steady/Consistent (`Short-Window Z-Score (1h
    baseline)`) pattern. Follow
    [agent_platform_no_historical_traffic_data.md](agent_platform_no_historical_traffic_data.md).
*   **Query Types for Reliability (No MQL or Threshold Filters)**:
    *   For latency and container SLO error rate metrics, you MUST use
        `condition_prometheus_query_language` with PromQL.
    *   For the downstream model call and tool call error rate metrics, you MUST
        use `condition_sql` with GoogleSQL querying `_Trace.Spans._AllSpans`.
    *   Do **NOT** use Monitoring Query Language (MQL) or standard
        `condition_threshold` for these reliability metrics.
*   **Critical alert thresholds**: Configure alerts with a **5% critical
    threshold** (aligned with the Vertex AI SLA uptime definition). For warning
    alerts, optionally configure a **1% threshold** to catch downstream
    degradation or quota exhaustion before it affects user experience.
*   **For Metrics using PromQL**: ALWAYS use grouping aggregations. Group by
    `gen_ai_agent_name` (for example, `by (gen_ai_agent_name)`). Avoid filtering
    to a single ID or name unless requested. Metrics are emitted through
    OpenTelemetry.

### Review Telemetry Metrics

All raw telemetry metrics for the Agent Platform container runtime are
cumulative **counters** monitored using PromQL. Downstream model calls are
tracked through OpenTelemetry Trace Spans exported to Observability Analytics
and monitored using SQL queries.

| Signal | Source / Raw Metric | Type | Description |
| :--- | :--- | :--- | :--- |
| **Latency** | `gen_ai_invoke_agent_duration_bucket` | Counter | Histogram bucket of agent request latencies |
| **Error Rate** | `gen_ai_invoke_agent_duration_count` | Counter | Cumulative count of agent requests |
| **Model Call Error Rate** | `global._Trace.Spans._AllSpans` view | Trace Spans | Downstream LLM API call traces (`status.code = 2` is error) |
| **Tool Call Error Rate** | `global._Trace.Spans._AllSpans` view | Trace Spans | Downstream tool execution traces (`status.code = 2` is error) |

## Configure Policy Specifications

### Configure Latency Alerts

#### Select the Latency Telemetry Query

##### Configure Z-Score for Steady Traffic

**Long-Window Z-Score (`1w Z-Score Baseline`, for established agents with more than 1 week of history)**

Compares the 5-minute 95th percentile latency to the 1-week baseline.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "long_window_zscore"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Long-Window Z-Score"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "Z-Score > 3"

```promql
abs(
  histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m])) by (le, gen_ai_agent_name))
  -
  histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[1w])) by (le, gen_ai_agent_name))
)
/
stddev_over_time(
  (histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m])) by (le, gen_ai_agent_name)))[1w:5m]
) > 3
```

*Note: The denominator uses a subquery `[1w:5m]` to calculate standard deviation
of the 5-minute latency over 1 week. The numerator uses `[1w]` rate directly to
avoid a second subquery for the mean.*

**Short-Window Z-Score (`Short-Window Z-Score (1h baseline)`, for newer agents with more than 1 hour of history)**

Compares the 1-minute 95th percentile latency to the 1-hour baseline for rapid
activation on new agents.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "short_window_zscore"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Short-Window Z-Score"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "Z-Score > 3"

```promql
abs(
  histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[1m])) by (le, gen_ai_agent_name))
  -
  histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[1h])) by (le, gen_ai_agent_name))
)
/
stddev_over_time(
  (histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[1m])) by (le, gen_ai_agent_name)))[1h:1m]
) > 3
```

##### Configure Moving Averages for Bursty Traffic

Compares the 5-minute latency to the 1-hour `Moving Averages` baseline.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "moving_average"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Moving Average"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "5m Above 1h Average"

```promql
histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m])) by (le, gen_ai_agent_name))
>
1.5 * histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[1h])) by (le, gen_ai_agent_name))
```

##### Configure Seasonal Decomposition for Cyclical Traffic

> [!NOTE]
> For the Latency alert policy, ONLY use seasonal decomposition (`Seasonal
> Decomposition (average 1w and 1d)`) to track latency spikes. Alert policies
> using seasonal decomposition tracking both spikes and drops can falsely
> trigger alerts.

Compares the 5-minute latency to the average of 1-week and 1-day lookback
baselines.

> [!CAUTION]
> The numerator (current latency) MUST NOT have any offset. Offsets
> (`offset 1d`, `offset 1w`) MUST only be applied to the denominator to
> construct the historical baseline for comparison. Never apply an offset to the
> first numerator.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "seasonal_decomposition"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Seasonal Decomposition"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "Seasonal Decomposition > 2"

```promql
histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m])) by (le, gen_ai_agent_name))
/
(
  (
    histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m] offset 1d)) by (le, gen_ai_agent_name))
    +
    histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m] offset 1w)) by (le, gen_ai_agent_name))
  ) / 2
)
> 2
```

#### Define Terraform HCL for Latency

```terraform
resource "google_monitoring_alert_policy" "latency_{latency_algorithm_name_short}" {
  project      = var.project_id
  display_name = "Agent Reliability - Latency {latency_algorithm_name_long}"
  combiner     = "OR"

  conditions {
    display_name = "Latency {latency_algorithm_condition_description}"
    condition_prometheus_query_language {
      query    = <<EOT
{latency_telemetry_query}
EOT
    }
  }

  documentation {
    content   = "High latency detected for the agent."
    mime_type = "text/markdown"
    subject   = "Agent Reliability - Latency {latency_algorithm_name_long} on $${metric.label.gen_ai_agent_name}"
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

Where:

*   `{latency_algorithm_name_short}`: Short algorithm name.
*   `{latency_algorithm_name_long}`: Long algorithm name.
*   `{latency_algorithm_condition_description}`: Condition description.
*   `{latency_telemetry_query}`: PromQL query from above.

### Configure Error Rate Fast Burn SLO (1-Hour and 5-Minute Windows)

> [!IMPORTANT] **SLO standard alignment.** The Fast Burn (factor `14.4`, `1h` &
> `5m` windows, `duration = "300s"`) and Slow Burn (factor `1.0`, `3d` & `6h`
> windows, **no `duration`** because the lookback exceeds 25h) policies below
> are the Agent Platform implementation of the standard SRE burn-rate contract,
> and remain the authoritative templates for agent reliability alerts.
>
> This is a deliberate **exception** to the skill-wide delegation rule: Agent
> Platform is the one resource whose burn-rate policies live in this skill. If
> the user asks to **customize the SLO** — a different target, a latency SLO,
> window-based "good minutes" evaluation, or App Hub scoping — delegate to the
> `google-cloud-slo-alert-configuration` skill, which owns the SLO wizard, the
> burn-rate templates (`references/promql_templates.md`), the SLI mapping
> (`references/service_metrics.md`), and the App Hub scoping labels
> (`references/app_hub_labels.md`).
>
> **Context to hand off** (so the SLO skill does not repeat discovery):
>
> *   **Resource type**: an OpenTelemetry-instrumented AI agent. This is
>     **runtime-agnostic** — the agent may run on Vertex AI Agent Engine, Cloud
>     Run, or any other OpenTelemetry-instrumented host. Do **not** hand off a
>     Vertex-specific monitored resource: these are generic OpenTelemetry
>     workload metrics, which land under `generic_node`, and every query in this
>     file filters `monitored_resource="generic_node"`.
> *   **Grouping labels**: `gen_ai_agent_name`.
> *   **Error rate SLI**:
>     `workload_googleapis_com:gen_ai_invoke_agent_duration_count`; bad =
>     `error_type!=""`.
> *   **Latency SLI**:
>     `workload_googleapis_com:gen_ai_invoke_agent_duration_bucket`; percentile
>     using `histogram_quantile(q, sum(rate(...)) by (le, gen_ai_agent_name))`.
> *   **SLO target**: `slo_target` (default `0.999`).
>
> Model call and tool call error rates are **not** available as SLIs: they are
> derived from trace spans in `global._Trace.Spans._AllSpans` using SQL, not
> PromQL, so the SLO skill cannot build burn-rate queries from them.
>
> Define `variable "slo_target"` (default `0.999`) in the generated Terraform so
> the burn-rate thresholds stay parameterized.

#### Define the Fast Burn Telemetry Query

Always use Multi-Window Multi-Burn Rate SLOs. Z-score is not recommended due to
sparsity.

```promql
(
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node",error_type!=""}[5m])) by (gen_ai_agent_name)
  /
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node"}[5m])) by (gen_ai_agent_name)
  > (1 - ${var.slo_target}) * 14.4
)
and
(
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node",error_type!=""}[1h])) by (gen_ai_agent_name)
  /
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node"}[1h])) by (gen_ai_agent_name)
  > (1 - ${var.slo_target}) * 14.4
)
```

#### Define Terraform HCL for Fast Burn SLO

```terraform
resource "google_monitoring_alert_policy" "error_rate_fast_burn" {
  project      = var.project_id
  display_name = "Agent Reliability - Error Rate Fast Burn SLO"
  combiner     = "OR"

  conditions {
    display_name = "Error Rate Fast Burn (1h/5m)"
    condition_prometheus_query_language {
      query    = {error_rate_fast_slo_telemetry_query}
      duration = "300s" # 5m buffer
    }
  }

  documentation {
    content   = "Fast Burn error rate SLO violation detected."
    mime_type = "text/markdown"
    subject   = "Error Rate Fast Burn (1h/5m) on $${metric.label.gen_ai_agent_name}"
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

Where:

*   `{error_rate_fast_slo_telemetry_query}`: The PromQL alert query configured
    in [Define the Fast Burn Telemetry Query](#define-the-fast-burn-telemetry-query)
    above.

### Configure Error Rate Slow Burn SLO (3-Day and 6-Hour Windows)

#### Define the Slow Burn Telemetry Query

Always use Multi-Window Multi-Burn Rate SLOs. Z-score is not recommended due to
sparsity.

```promql
(
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node",error_type!=""}[6h])) by (gen_ai_agent_name)
  /
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node"}[6h])) by (gen_ai_agent_name)
  > (1 - ${var.slo_target}) * 1.0
)
and
(
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node",error_type!=""}[3d])) by (gen_ai_agent_name)
  /
  sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{monitored_resource="generic_node"}[3d])) by (gen_ai_agent_name)
  > (1 - ${var.slo_target}) * 1.0
)
```

#### Define Terraform HCL for Slow Burn SLO

```terraform
resource "google_monitoring_alert_policy" "error_rate_slow_burn" {
  project      = var.project_id
  display_name = "Agent Reliability - Error Rate Slow Burn SLO"
  combiner     = "OR"

  conditions {
    display_name = "Error Rate Slow Burn (3d/6h)"
    condition_prometheus_query_language {
      query = <<EOT
{error_rate_slow_slo_telemetry_query}
EOT
    }
  }

  documentation {
    content   = "Slow Burn error rate SLO violation detected."
    mime_type = "text/markdown"
    subject   = "Error Rate Slow Burn (3d/6h) on $${metric.label.gen_ai_agent_name}"
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

Where:

*   `{error_rate_slow_slo_telemetry_query}`: The PromQL alert query configured
    in [Define the Slow Burn Telemetry Query](#define-the-slow-burn-telemetry-query)
    above.

### Configure Model Call Error Rate Alerts

#### Define the Model Call Error Rate Query

When configuring a SQL-based alerting condition (`condition_sql`) in Google
Cloud Monitoring for an agent, use the following template to query trace spans
exported to Observability Analytics:

```sql
SELECT
  JSON_VALUE(resource.attributes, '$."cloud.resource_id"') as agent_id,
  JSON_VALUE(attributes, '$."gen_ai.request.model"') as model,
  (COUNTIF(status.code = 2) * 100.0) / COUNT(*) AS model_error_rate
FROM
  `${TRACE_SCOPE_TABLE_NAME}`
WHERE
  JSON_VALUE(attributes, '$."gen_ai.request.model"') IS NOT NULL
GROUP BY
  agent_id,
  model
HAVING
  model_error_rate > 5.0
```

Where:

*   `{trace_scope_table_name}`: The Trace scope Observability Analytics table
    name retrieved in [Verify Prerequisites](#verify-prerequisites).

#### Define Terraform HCL for Model Call Error Rate

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` condition:

```terraform
resource "google_monitoring_alert_policy" "model_call_error_rate" {
  project      = var.project_id
  display_name = "Agent Reliability - High Model Call Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "Agent Model Call Error Rate Exceeds 5%"
    condition_sql {
      query = <<EOT
{model_call_high_error_rate_telemetry_query}
EOT

      # Run evaluation periodically (periodicity value must be between 5 and 1440 minutes)
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

  notification_channels = [google_monitoring_notification_channel.email.name]
}
```

Where:

*   `{model_call_high_error_rate_telemetry_query}`: The SQL alert query
    configured in [Define the Model Call Error Rate Query](#define-the-model-call-error-rate-query)
    above.

### Configure Tool Call Error Rate Alerts

#### Define the Tool Call Error Rate Query

When configuring a SQL-based alerting condition (`condition_sql`) in Google
Cloud Monitoring for an agent to monitor tool call error rates, use the
following template to query trace spans exported to Observability Analytics:

```sql
SELECT
  JSON_VALUE(resource.attributes, '$."cloud.resource_id"') as agent_id,
  JSON_VALUE(attributes, '$."gen_ai.tool.name"') as tool_name,
  (COUNTIF(status.code = 2) * 100.0) / COUNT(*) AS tool_error_rate
FROM
  `${TRACE_SCOPE_TABLE_NAME}`
WHERE
  JSON_VALUE(attributes, '$."gen_ai.operation.name"') = 'execute_tool'
  AND JSON_VALUE(attributes, '$."gen_ai.tool.name"') IS NOT NULL
GROUP BY
  agent_id,
  tool_name
HAVING
  tool_error_rate > 5.0
```

Where:

*   `{trace_scope_table_name}`: The Trace scope Observability Analytics table
    name retrieved in [Verify Prerequisites](#verify-prerequisites).

#### Define Terraform HCL for Tool Call Error Rate

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` condition:

```terraform
resource "google_monitoring_alert_policy" "tool_call_error_rate" {
  project      = var.project_id
  display_name = "Agent Reliability - High Tool Call Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "Agent Tool Call Error Rate Exceeds 5%"
    condition_sql {
      query = <<EOT
{tool_call_high_error_rate_telemetry_query}
EOT

      minutes {
        periodicity = 5
      }

      row_count_test {
        comparison = "COMPARISON_GT"
        threshold  = 0
      }
    }
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }

  notification_channels = [google_monitoring_notification_channel.email.name]
}
```

Where:

*   `{tool_call_high_error_rate_telemetry_query}`: The SQL alert query
    configured in [Define the Tool Call Error Rate Query](#define-the-tool-call-error-rate-query)
    above.

## Run Tooling Scripts

1.  **gather_agent_info (Primary Streamlined Discovery — REQUIRED)**: Always run
    (or print when execution is disabled) this streamlined discovery command
    first with all parameter values filled in, even if a fallback table name is
    provided:
    *   Command: `python3 scripts/agent_platform/gather_agent_info.py --project-id="{gcp_project}" --agent-name="{agent_name}"`
2.  **scan_duplicates (Required Duplicate Policy Verification)**: Always run (or
    print when execution is disabled) this command to verify that no duplicate
    alert policy blocks exist:
    *   Command: `python3 scripts/agent_platform/scan_duplicates.py monitoring/`
3.  **lint_syntax (HCL and PromQL Syntax Validation)**: When reviewing,
    validating, or correcting an existing or draft `.tf` file for an AI agent,
    run (or print when execution is disabled) this linter to check for balanced
    parentheses/braces, valid PromQL time windows (`[5m]`, `[1w:5m]`), agent
    identifier grouping (`gen_ai_agent_name`), and duration buffer rules:
    *   Command: `python3 scripts/agent_platform/lint_syntax.py <path_to_tf_file>`
4.  **list_trace_scope_table_names (Fallback)**: Use this script ONLY if
    `gather_agent_info.py` fails to retrieve the associated Trace scope
    Observability Analytics SQL table name:
    *   Command: `python3 scripts/agent_platform/list_trace_scope_table_names.py
        --project_id={gcp_project}`

## Validate and Finalize

*   **Lint Draft HCL and PromQL Queries**: When asked to validate or fix draft
    agent alert configurations (for example, in `draft_invalid_query.tf` or
    `monitoring/alerts.tf`), run `python3 scripts/agent_platform/lint_syntax.py
    <path_to_tf_file>` to detect and auto-correct unbalanced parentheses or
    braces, invalid time window units, missing `gen_ai_agent_name` grouping, and
    invalid `duration` buffers on long-lookback (>25h) queries.

*   **Enforce SQL Alert Constraints**:
    1.  **No manual timestamp filters** or temporal groupings.
    2.  **Group by agent identifier**: Use `cloud.resource_id` (Reasoning Engine
        ID or Cloud Run service) to monitor dynamically. Do NOT filter for
        specific agents unless requested.
    3.  **Aggregate failures**: Group by agent or tool name, calculating the
        ratio of failed requests (status code `2` indicating ERROR) to total
        requests.
    4.  **Use `HAVING` clause** to filter out healthy tools and models.
    5.  **Pinning (Only if explicitly requested)**: Use
        `ENDS_WITH(JSON_VALUE(resource.attributes, '$."cloud.resource_id"'),
        'AGENT_IDENTIFIER')` with a string identifier (for example,
        `'support-bot'`), not numeric, unless instructed. Customize this filter
        only when explicitly requested; otherwise avoid pinning in favor of
        dynamic grouping as described in the main skill instructions.
*   **Configure Duration Buffers (Transient Glitches)**: To avoid alerts firing
    on transient spikes, use duration and retest window buffers appropriately:
    *   **Reliability Metrics (PromQL / Cloud Monitoring)**:
        *   For short-lookback alerts querying data under 25 hours (such as
            `Short-Window Z-Score (1h baseline)`, `Moving Averages`, and Fast
            Burn SLO), ALWAYS use a `duration = "300s"` (5 minutes) buffer to
            filter out transient cold start or deployment spikes.
        *   For long-lookback alerts querying data longer than 25 hours (such as
            `1w Z-Score Baseline`, `Seasonal Decomposition (average 1w and 1d)`,
            and Slow Burn SLO), duration and retest windows are disabled by the
            platform. Do **not set a duration** (omit it entirely).
*   **Explain the Dynamic Baseline Adaptation Blind Spot**: Explain to users
    that dynamic statistical Z-score thresholds compare current rates to a
    moving statistical baseline. If a system degrades slowly over days, the
    standard baseline curve adapts to this slow drift, making standard Z-score
    alerts blind to persistent slow errors. Recommend a hard static threshold
    alert in parallel for strict SLA enforcement.
*   **Prevent Seasonal Decomposition Double Alerting**: Configure seasonal
    decomposition alert policies ONLY to track spikes (for example, latency
    spikes) OR drops, and NEVER use dual-direction evaluations (such as absolute
    deviation). Explain this limitation to the user: when comparing to a
    historical offset (for example, `offset 1w`), the alert policy triggers
    twice if tracking both directions (when the anomaly first occurs, and again
    after 1 week when the anomaly becomes the baseline). To prevent this, the
    generated policy MUST only track either spikes (using `>`) or drops (using
    `<`), avoiding `abs()`.
*   **Handle Script Failures**: If `list_trace_scope_table_names.py` fails
    unexpectedly, verify the project ID and ensure you have permissions to view
    trace scopes and linked datasets.
