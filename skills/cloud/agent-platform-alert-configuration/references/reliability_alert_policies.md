# Reliability Alert Policies

These alert policies will help users pinpoint the root cause of ongoing
increased agent latency and high error rates with model and tool requests.

## Table of Contents

-   [Prerequisites](#prerequisites) (~Line 21)
    -   [Alert Policies with SQL Metrics](#alert-policies-with-sql-metrics) (~Line 23)
    -   [Alert Policies with PromQL Metrics](#alert-policies-with-promql-metrics) (~Line 67)
-   [Critical Rules](#critical-rules) (~Line 89)
-   [Policy Specifications](#policy-specifications) (~Line 127)
    -   [Latency](#latency) (~Line 129)
    -   [Error Rate Fast Burn SLO](#error-rate-fast-burn-slo-1-hour-and-5-minute-windows) (~Line 261)
    -   [Error Rate Slow Burn SLO](#error-rate-slow-burn-slo-3-day-and-6-hour-windows) (~Line 317)
    -   [Model Call Error Rate](#model-call-error-rate) (~Line 374)
    -   [Tool Call Error Rate](#tool-call-error-rate) (~Line 447)
-   [Tooling Scripts](#tooling-scripts) (~Line 519)
-   [Gotchas & Behavioral Corrections](#gotchas-behavioral-corrections) (~Line 526)

## Prerequisites

### Alert Policies with SQL Metrics

#### Trace Scope Observability Analytics table

You will need to retrieve the Observability Analytics table where all the Trace
scope spans are stored for the SQL based alerts.

#### BigQuery dataset

A linked BigQuery dataset instance is required to configure SQL alert policies
depending on Observability Analytics trace data. This dataset MUST hold views
for the `_Trace` trace bucket of the target GCP project.

Applicable BigQuery datasets have a `"type": "LINKED"` attribute and reference
the `_Trace` bucket in their description. To list all existing BigQuery datasets
in a project run the following command:

```bash
bq ls --format=prettyjson --project_id={project_id}
```

Where:

*   `{project_id}`: The target GCP project id.

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

*   `{project_id}`: Target GCP project ID.
*   `{location}`: Observability bucket location (found in analytics table name).
*   `{bucket_id}`: Bucket ID (default: `_Trace`).
*   `{dataset_id}`: Dataset ID (default: `Spans`).
*   `{link_id}`: New BQ dataset name (default: `trace_bq_linked_dataset`).

### Alert Policies with PromQL Metrics

#### Algorithm Selection & Policy Mapping Process

Alerting policies for agents MUST map to the correct algorithms
to ensure statistical stability and prevent alert noise or blind spots based on
data classes:

*   **Latency**: Follows workload traffic pattern (Steady -> Z-Score; Seasonal
    -> Seasonal Decomposition; Bursty -> Moving Averages).
*   **Error Rate**: ALWAYS use **Multi-Window Multi-Burn Rate SLOs** (or
    ratio-based static thresholds). Error rate is naturally sparse (`0`). If
    standard deviation is `0`, Z-scores are mathematically unstable
    (division-by-zero), causing false alerts.

To resolve the workload traffic pattern (Seasonal, Steady, or Bursty), follow
the instructions corresponding to the availability of historical metrics data:

*   **Case 1: No historical metrics data available (e.g., brand new agent)**:
    You MUST read and follow:
    [no_historical_traffic_data.md](references/no_historical_traffic_data.md)
*   **Case 2: Historical metrics data available (e.g., active agent with
    traffic)**: You MUST read and follow:
    [has_historical_traffic_data.md](references/has_historical_traffic_data.md)

## Critical Rules

*   **Brand New Agents (No Traffic History)**: When setting up alerts for a
    brand new agent, you MUST explicitly ask the user what traffic pattern they
    expect (Steady, Seasonal, or Bursty) in your response. If immediate setup is
    requested, ask the question but proceed using the default Steady/Consistent
    (Short-Window Z-Score) pattern. Follow
    [no_historical_traffic_data.md](references/no_historical_traffic_data.md).
*   **Query Types for Reliability (No MQL or Threshold Filters)**:
    *   For latency and container SLO error rate metrics, you MUST use
        `condition_prometheus_query_language` with PromQL.
    *   For the downstream model call and tool call error rate metrics, you MUST
        use `condition_sql` with GoogleSQL querying `_Trace.Spans._AllSpans`.
    *   Do **NOT** use MQL or standard `condition_threshold` for these
        reliability metrics.
*   **Critical alert thresholds**: We recommend configuring alerts with a **5%
    critical threshold** (aligned with the Vertex AI SLA uptime definition). For
    warning alerts, you may optionally configure a **1% threshold** to catch
    downstream degradation or quota exhausting before it affects user
    experience.
*   **For Metrics using PromQL**: ALWAYS use grouping aggregations. Group by
    `gen_ai_agent_name` (e.g., `by (gen_ai_agent_name)`). Avoid filtering to a
    single ID/Name unless requested. Metrics are emitted via OpenTelemetry.

### Telemetry Metrics

All raw telemetry metrics for the Agent Platform container runtime are
cumulative **counters** monitored via PromQL. Downstream model calls are tracked
via Open Telemetry Trace Spans exported to Log Analytics and monitored via SQL
queries.

Signal                    | Source / Raw Metric                                                                                      | Type        | Description
:------------------------ | :------------------------------------------------------------------------------------------------------- | :---------- | :----------
**Latency**               | `gen_ai_invoke_agent_duration_bucket` | Counter     | Histogram bucket of agent request latencies
**Error Rate**            | `gen_ai_invoke_agent_duration_count`  | Counter     | Cumulative count of agent requests
**Model Call Error Rate** | `global._Trace.Spans._AllSpans` view                                                                     | Trace Spans | Downstream LLM API call traces (status.code = 2 is error)
**Tool Call Error Rate**  | `global._Trace.Spans._AllSpans` view                                                                     | Trace Spans | Downstream tool execution traces (status.code = 2 is error)

## Policy Specifications

### Latency

#### Telemetry query

##### Z-Score (Recommended for Steady Traffic)

**Long-Window Z-Score (For Established Agents - >1 week history)**

Compares the 5-minute 95th percentile latency to the 1-week baseline.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "long_window_zscore"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Long-Window Z-Score"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "Z-Score > 3"

```
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

**Short-Window Z-Score (For Newer Agents - >1 hour history)**

Compares the 1-minute 95th percentile latency to the 1-hour baseline. Useful for
quick activation on new agents.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "short_window_zscore"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Short-Window Z-Score"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "Z-Score > 3"

```
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

##### Moving Averages (Recommended for Bursty Traffic)

Compares the 5-minute latency to the 1-hour average.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "moving_average"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Moving Average"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "5m Above 1h Average"

```
histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[5m])) by (le, gen_ai_agent_name))
>
1.5 * histogram_quantile(0.95, sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_bucket{monitored_resource="generic_node"}[1h])) by (le, gen_ai_agent_name))
```

##### Seasonal Decomposition (Recommended for traffic with seasonal or time-of-day component)

> [!NOTE] For the Latency alert policy, ONLY use seasonal decomposition to track
> Latency spikes. Alert policies using seasonal decomposition tracking both
> spikes and drops can falsely trigger alerts.

> [!CRITICAL] The numerator (current latency) MUST NOT have any offset. Offsets
> (`offset 1d`, `offset 1w`) MUST only be applied to the denominator to
> construct the historical baseline for comparison. Never apply an offset to the
> first numerator.

Compares the 5-minute latency to the average of 1-week and 1-day lookback
baselines.

*   `LATENCY_ALGORITHM_NAME_SHORT`: "seasonal_decomposition"
*   `LATENCY_ALGORITHM_NAME_LONG`: "Seasonal Decomposition"
*   `LATENCY_ALGORITHM_CONDITION_DESCRIPTION`: "Seasonal Decomposition > 2"

```
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

#### Terraform HCL

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

Where:

*   `{latency_algorithm_name_short}`: Short algorithm name.
*   `{latency_algorithm_name_long}`: Long algorithm name.
*   `{latency_algorithm_condition_description}`: Condition description.
*   `{latency_telemetry_query}`: PromQL query from above.

### Error Rate Fast Burn SLO (1-Hour and 5-Minute Windows)

#### Telemetry query

Always use Multi-Window Multi-Burn Rate SLOs. Z-score is not recommended due to
sparsity.

```
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

#### Terraform HCL

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

Where:

*   `{error_rate_fast_slo_telemetry_query}`: The PromQL alert query configured
    in the `Telemetry query` section above.

### Error Rate Slow Burn SLO (3-Day and 6-Hour Windows)

#### Telemetry query

Always use Multi-Window Multi-Burn Rate SLOs. Z-score is not recommended due to
sparsity.

```
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

#### Terraform HCL

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

Where:

*   `{error_rate_slow_slo_telemetry_query}`: The PromQL alert query configured
    in the `Telemetry query` section above.

### Model Call Error Rate

#### Telemetry query

When configuring a SQL-based alerting condition (`condition_sql`) in Google
Cloud Monitoring for an agent, use the following template to query trace spans
exported to Log Analytics:

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

*   `{trace_scope_table_name}`: The Trace scope observability analytics table
    name retrieved in the `Prerequisites` section.

#### Terraform HCL

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` check:

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }

  notification_channels = [google_monitoring_notification_channel.email.name]
}
```

Where:

*   `{model_call_high_error_rate_telemetry_query}`: The SQL alert query
    configured in the `Telemetry query` section above.

### Tool Call Error Rate

#### Telemetry query

When configuring a SQL-based alerting condition (`condition_sql`) in Google
Cloud Monitoring for an agent to monitor tool call error rates, use the
following template to query trace spans exported to Log Analytics:

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

*   `{trace_scope_table_name}`: The Trace scope observability analytics table
    name retrieved in the `Prerequisites` section.

#### Terraform HCL

Implement the alert policy resource using a `condition_sql` block with a
`row_count_test` check:

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }

  notification_channels = [google_monitoring_notification_channel.email.name]
}
```

Where:

*   `{tool_call_high_error_rate_telemetry_query}`: The SQL alert query
    configured in the `Telemetry query` section above.

## Tooling Scripts

*   **list_trace_scope_table_names (Fallback)**: Use this script ONLY if `gather_agent_info.py` failed to retrieve the associated Trace scope observability SQL table name.
    *   Command: `python3 scripts/list_trace_scope_table_names.py
        --project_id={gcp_project}`

## Gotchas & Behavioral Corrections

*   **SQL Alert Constraints**:
    1.  **No manual timestamp filters** or temporal groupings.
    2.  **Group by agent identifier**: Use `cloud.resource_id` (Reasoning Engine
        ID or Cloud Run service) to monitor dynamically. Do NOT filter for
        specific agents unless requested.
    3.  **Aggregate failures**: Group by agent or tool name, the ratio of failed
        requests (status code `2` indicating ERROR) to total requests.
    4.  **Use `HAVING` clause** to filter out healthy tools/models.
    5.  **Pinning (Optional)**: Use `ENDS_WITH(JSON_VALUE(resource.attributes,
        '$."cloud.resource_id"'), 'AGENT_IDENTIFIER')` with string identifier
        (e.g., `'support-bot'`), not numeric, unless instructed.
*   **Duration Buffers (Transient Glitches)**: To avoid alerts firing on
    transient spikes, use duration/retest window buffers appropriately:
    *   **Reliability Metrics (PromQL / Cloud Monitoring)**:
        *   For short-lookback alerts querying data under 25 hours (e.g.,
            Short-Window Z-Score, Moving Averages, Fast Burn SLO), ALWAYS use a
            `duration = "300s"` (5 minutes) buffer to filter out transient cold
            start/deployment spikes.
        *   For long-lookback alerts querying data longer than 25 hours (e.g.,
            Long-Window Z-Score, Seasonal Decomposition, Slow Burn SLO),
            duration/retest windows are disabled by the platform. You must **not
            set a duration** (omit it entirely).
*   **Dynamic Baseline Adaptation Blind Spot**: Explain to users that dynamic
    statistical Z-score thresholds compare current rates to a moving statistical
    baseline. If a system degrades slowly over days, the standard baseline curve
    adapts to this slow drift, making standard Z-score alerts blind to
    persistent slow errors. Recommend a hard static threshold alert in parallel
    for strict SLA enforcement.
*   **Seasonal Decomposition Double Alerting**: The agent MUST ONLY configure
    seasonal decomposition alert policies to track spikes (e.g., latency spikes)
    OR drops AND MUST NOT use dual-direction checks (like absolute deviation).
    Explain this limitation to the user: comparing to a historical offset (e.g.,
    `offset 1w`) the alert policy triggers twice if tracking both directions
    (once for the anomaly, and once 1 week later when the anomaly becomes the
    baseline). To prevent this, the generated policy MUST only track either
    spikes (using `>`) or drops (using `<`), avoiding using `abs()`.
*   **Script Failures**: If `list_trace_scope_table_names.py` fails
    unexpectedly, verify the project ID and ensure you have permissions to view
    trace scopes and linked datasets.
