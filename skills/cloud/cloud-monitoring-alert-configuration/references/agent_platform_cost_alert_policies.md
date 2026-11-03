# Configure Cost Alert Policies

These alert policies help alert users when their agents use an unusually high
rate of tokens based on historical metrics.

## Table of Contents

-   [Verify Preconditions](#verify-preconditions): Lines 16-49
    -   [Resolve the Token Usage Workload Pattern](#resolve-the-token-usage-workload-pattern): Lines 18-49
-   [Follow Critical Rules](#follow-critical-rules): Lines 50-77
    -   [Review Telemetry Metrics](#review-telemetry-metrics): Lines 72-77
-   [Configure Policy Specifications](#configure-policy-specifications): Lines 78-211
    -   [Configure Rapid Token Burn Rate](#configure-rapid-token-burn-rate): Lines 80-211
-   [Validate and Finalize](#validate-and-finalize): Lines 212-217

## Verify Preconditions

### Resolve the Token Usage Workload Pattern

Resolve the workload token usage pattern (Seasonal / Cyclical, Steady /
Consistent, or Bursty / Inconsistent) to configure policies monitoring token
usage. If you have not done so already, you MUST run the `check_telemetry` tool
with the flag `--query-monitoring-metadata` enabled to retrieve all namespaces
available for the token usage metric and match the closest one to the target
agent:

```bash
python3 scripts/agent_platform/check_telemetry.py \
  --project-id={gcp_project} \
  --location={location} \
  --agent-resource-name "projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}" \
  --query-monitoring-metadata
```

*   If the user provides a namespace to use in their prompt, you DO NOT need to
    run this tool to retrieve existing namespaces.
*   If the tool does not return a relevant namespace entry, historical metric
    data is not available for this agent.

Follow the instructions corresponding to the availability of historical metrics
data:

*   **Case 1: No historical metrics data available (for example, brand new agent) or no
    monitoring namespaces found**: You MUST read and follow:
    [agent_platform_no_historical_traffic_data.md](agent_platform_no_historical_traffic_data.md)
*   **Case 2: Historical metrics data available (for example, active agent with
    traffic)**: You MUST read and follow:
    [agent_platform_has_historical_traffic_data.md](agent_platform_has_historical_traffic_data.md)

## Follow Critical Rules

*   **Brand New Agents (No Token Usage History)**: When setting up alerts for a
    brand new agent, you MUST explicitly ask the user what token usage pattern
    they expect (Steady / Consistent, Seasonal / Cyclical, or Bursty /
    Inconsistent) in your response. If immediate setup is requested, ask the
    question but proceed using the default Steady/Consistent (`Short-Window
    Z-Score (1h baseline)`) pattern. Follow
    [agent_platform_no_historical_traffic_data.md](agent_platform_no_historical_traffic_data.md).
*   **Alert policy configuration**: You MUST configure the following Cost
    alerting policy. See [Review Telemetry Metrics](#review-telemetry-metrics)
    for the required metrics and descriptions for each signal:
    1.  **Rapid Token Burn Rate** (5-Minute window)
*   **PromQL format**: Configure all Cost alert policies using a PromQL query.
    Do **NOT** use any other language such as Monitoring Query Language (MQL).
    See [Select Telemetry Queries](#select-telemetry-queries) below for the
    queries to use for each signal. Proceed to the **Validate and Finalize**
    section below.
    *   **Disclaimer**: Group by the appropriate field for the underlying
        monitored resource; for example, `generic_node` uses `namespace`. The
        examples below assume `generic_node`.

### Review Telemetry Metrics

| Signal | Raw Metric | Type | Description |
| :--- | :--- | :--- | :--- |
| **Rapid Token Burn Rate** | `gen_ai.client.token.usage` | Counter | Amount of tokens used by the agent. |

## Configure Policy Specifications

### Configure Rapid Token Burn Rate

#### Select Telemetry Queries

##### Configure Z-Score for Steady Traffic

**Long-Window Z-Score (`1w Z-Score Baseline`, for established agents with more than 1 week of history)**

Compares the 5-minute 95th percentile token usage to the 1-week baseline.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "long_window_zscore"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Long-Window Z-Score"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Rapid Token Burn
    Rate Long-Window Z-Score > 3"

```promql
abs(
  histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m])))
  -
  histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[1w])))
)
/
stddev_over_time(
  (histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m]))))[1w:5m]
) > 3
```

**Short-Window Z-Score (`Short-Window Z-Score (1h baseline)`, for newer agents with more than 1 hour of history)**

Compares the 1-minute 95th percentile token usage to the 1-hour baseline for
rapid activation on new agents.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "short_window_zscore"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Short-Window Z-Score"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Rapid Token Burn
    Rate Short-Window Z-Score > 3"

```promql
abs(
  histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[1m])))
  -
  histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[1h])))
)
/
stddev_over_time(
  (histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[1m]))))[1h:1m]
) > 3
```

##### Configure Moving Averages for Bursty Traffic

Compares the 5-minute token usage to the 1-hour `Moving Averages` baseline.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "moving_average"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Moving Average"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Rapid Token Burn
    Rate 5m window > 1h avg"

```promql
histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m])))
>
1.5 * histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[1h])))
```

##### Configure Seasonal Decomposition for Cyclical Traffic

> [!NOTE]
> ONLY use seasonal decomposition (`Seasonal Decomposition (average 1w and 1d)`)
> to track token usage spikes. Alert policies using seasonal decomposition to
> track both spikes and drops can falsely trigger alerts.

Compares the 5-minute token usage to the average of 1-week and 1-day lookback
baselines.

> [!CAUTION]
> The numerator (current token usage) MUST NOT have any offset. Offsets
> (`offset 1d`, `offset 1w`) MUST only be applied to the denominator to
> construct the historical baseline for comparison. Never apply an offset to the
> first numerator.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "seasonal_decomposition"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Seasonal Decomposition"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Seasonal
    Decomposition > 2"

```promql
histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m])))
/
(
  (
    histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m] offset 1d)))
    +
    histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m] offset 1w)))
  ) / 2
)
> 2
```

#### Define Terraform HCL

```terraform
resource "google_monitoring_alert_policy" "rapid_token_burn_rate_{rapid_token_burn_rate_algorithm_name_short}" {
  project      = var.project_id
  display_name = "Agent Cost - Rapid Token Burn Rate {rapid_token_burn_rate_algorithm_name_long}"
  combiner     = "OR"

  conditions {
    display_name = "{rapid_token_burn_rate_algorithm_condition_description}"
    condition_prometheus_query_language {
      # Using __name__ for metric with special characters.
      query    = {rapid_token_burn_rate_telemetry_query}
      duration = "300s" # 5m buffer
    }
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

Where:

*   `{rapid_token_burn_rate_algorithm_name_short}`: The short name version of
    the algorithm chosen in [Select Telemetry Queries](#select-telemetry-queries).
*   `{rapid_token_burn_rate_algorithm_name_long}`: The long name version of the
    algorithm chosen in [Select Telemetry Queries](#select-telemetry-queries).
*   `{rapid_token_burn_rate_algorithm_condition_description}`: A description for
    the alert condition chosen in [Select Telemetry Queries](#select-telemetry-queries).
*   `{rapid_token_burn_rate_telemetry_query}`: The PromQL alert query chosen and
    configured in [Select Telemetry Queries](#select-telemetry-queries).

## Validate and Finalize

*   **Handle Script Failures**: If `check_telemetry.py` fails unexpectedly,
    verify the parameters (project ID, location, and agent resource name).
    Ensure you have permissions to view Cloud Monitoring metrics and Vertex AI
    Reasoning Engines.
