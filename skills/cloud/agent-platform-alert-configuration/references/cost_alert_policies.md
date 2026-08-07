# Cost Alert Policies

These alert policies will help alert users when their agents are using an
unusually high rate of tokens based on their historical metrics.

## Table of Contents

-   [Preconditions](#preconditions) (~Line 15)
    -   [Token Usage Workload Pattern](#token-usage-workload-pattern) (~Line 17)
-   [Critical Rules](#critical-rules) (~Line 48)
    -   [Telemetry Metrics](#telemetry-metrics) (~Line 64)
-   [Policy Specifications](#policy-specifications) (~Line 71)
    -   [Rapid Token Burn Rate](#rapid-token-burn-rate) (~Line 73)

## Preconditions

### Token Usage Workload Pattern

It is required to resolve the workload token usage pattern (Seasonal, Steady, or
Bursty), to configure policies monitoring token usage. If you have not done it
already, you MUST run the `check_telemetry` tool with the flag
`--query-monitoring-metadata` enabled to retrieve all namespaces available for
the token usage metric and match the closest one to the target agent:

```bash
python3 scripts/check_telemetry.py \
  --project_id={gcp_project} \
  --location={location} \
  --agent-resource-name "projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}" \
  --query-monitoring-metadata \
```

*   If the user provides a namespace to use in their prompt, you DO NOT need to
    run this tool to retrieve existing namespaces.
*   If the tool does not return a relevant namespace entry, there isn't
    historical metric data available for this agent.

Follow the instructions corresponding to the availability of historical metrics
data:

*   **Case 1: No historical metrics data available (e.g., brand new agent) or no
    monitoring namespaces found**: You MUST read and follow:
    [no_historical_traffic_data.md](references/no_historical_traffic_data.md)
*   **Case 2: Historical metrics data available (e.g., active agent with
    traffic)**: You MUST read and follow:
    [has_historical_traffic_data.md](references/has_historical_traffic_data.md)

## Critical Rules

*   **Brand New Agents (No Token Usage History)**: When setting up alerts for a
    brand new agent, you MUST explicitly ask the user what token usage pattern
    they expect (Steady, Seasonal, or Bursty) in your response. If immediate
    setup is requested, ask the question but proceed using the default
    Steady/Consistent (Short-Window Z-Score) pattern. Follow
    [no_historical_traffic_data.md](references/no_historical_traffic_data.md).
*   **Alert policy configuration**: You MUST configure exactly the following
    Cost alerting policies. See the `Telemetry Metrics` to get the required
    metrics and read the descriptions for each signal:
    1.  **Rapid Token Burn Rate** (15-Minute window)
*   **PromQL format**: All Cost alert policies must be configured using a PromQL
    query. Do **NOT** use any other language like MQL. See the `PromQL Queries`
    below to learn which queries to use for each signal.
    *   **Disclaimer**: You will need to group by a different field depending on
        what the underlying resource is; for example, `generic_node` uses
        `namespace`. The examples below assume `generic_node`.

### Telemetry Metrics

| Signal        | Raw Metric                  | Type    | Description        |
| :------------ | :-------------------------- | :------ | :----------------- |
| **Rapid Token | `gen_ai.client.token.usage` | Counter | Amount of tokens   |
: Burn Rate**   :                             :         : used by the agent. :

## Policy Specifications

### Rapid Token Burn Rate

#### Telemetry Queries

##### Z-Score (Recommended for Steady Traffic)

**Long-Window Z-Score (For Established Agents - >1 week history)**

Compares the 5-minute 95th percentile token usage to the 1-week baseline.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "long_window_zscore"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Long-Window Z-Score"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Rapid Token Burn
    Rate Long-Window Z-Score > 3"

```
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

**Short-Window Z-Score (For Newer Agents with >1 hour history)**

Compares the 1-minute 95th percentile token usage to the 1-hour baseline. Useful
for quick activation on new agents.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "short_window_zscore"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Short-Window Z-Score"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Rapid Token Burn
    Rate Short-Window Z-Score > 3"

```
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

##### Moving Averages (Recommended for Bursty Traffic)

Compares the 5-minute token usage to the 1-hour average.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "moving_average"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Moving Average"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Rapid Token Burn
    Rate 5m window > 1h avg"

```
histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[5m])))
>
1.5 * histogram_quantile(0.95,sum by ("namespace","le")(increase({"__name__"="workload_googleapis_com:gen_ai_client_token_usage_bucket","monitored_resource"="generic_node"}[1h])))
```

##### Seasonal Decomposition (Recommended for traffic with seasonal or time-of-day component)

> [!NOTE] ONLY use seasonal decomposition to track Token usage spikes. Alert
> policies using seasonal decomposition to track both spikes and drops can
> falsely trigger alerts.

> [!CRITICAL] The numerator (current token usage) MUST NOT have any offset.
> Offsets (`offset 1d`, `offset 1w`) MUST only be applied to the denominator to
> construct the historical baseline for comparison. Never apply an offset to the
> first numerator.

Compares the 5-minute token usage to the average of 1-week and 1-day lookback
baselines.

*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_SHORT`: "seasonal_decomposition"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_NAME_LONG`: "Seasonal Decomposition"
*   `RAPID_TOKEN_BURN_RATE_ALGORITHM_CONDITION_DESCRIPTION`: "Seasonal
    Decomposition > 2"

```
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

#### Terraform HCL

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

Where:

*   `{rapid_token_burn_rate_algorithm_name_short}`: The short name version of
    the algorithm chosen in the `Telemetry query` section above.
*   `{rapid_token_burn_rate_algorithm_name_long}`: The long name version of the
    algorithm chosen in the `Telemetry query` section above.
*   `{rapid_token_burn_rate_algorithm_condition_description}`: A description for
    the alert condition chosen in the `Telemetry query` section above.
*   `{rapid_token_burn_rate_telemetry_query}`: The PromQL alert query chosen and
    configured in the previous `Telemetry query` section above.

## Gotchas

*   **Script Failures**: If `check_telemetry.py` fails unexpectedly, verify
    parameters (project ID, location, agent resource name). Ensure you have
    permissions to view metrics and reasoning engines.
