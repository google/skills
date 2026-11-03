# Analyze Historical Traffic Data

Follow these instructions when the agent has historical metrics data available.

## Table of Contents

-   [Follow Critical Instructions](#follow-critical-instructions): Lines 13-89
    -   [Run the Traffic Analyzer Script](#run-the-traffic-analyzer-script): Lines 15-57
    -   [Map Metrics to Algorithms](#map-metrics-to-algorithms): Lines 58-89
-   [Notify the User](#notify-the-user): Lines 90-106
-   [Avoid Common Pitfalls](#avoid-common-pitfalls): Lines 107-112

## Follow Critical Instructions

### Run the Traffic Analyzer Script

-   Run the `analyze_traffic.py` script to classify the metrics traffic pattern
    profile:

    -   **Gather arguments**: Use different arguments in your call depending on
        the target policy you are running the tool for:
        -   **Latency**: Use
            `workload.googleapis.com/gen_ai.invoke_agent.duration` as the
            `--metric-type` and assign the value of the agent's
            `metric.labels.gen_ai_agent_name` as the
            `--reasoning-engine-id`.
        -   **Rapid Token Burn Rate**: Use
            `workload.googleapis.com/gen_ai.client.token.usage` as the
            `--metric-type` and assign the value of the agent's
            `resource.labels.namespace` as the `--reasoning-engine-id`.
    -   **Running the tool**: Use one of the following commands (adjust the
        script path if running from a parent directory):
        -   **Live Query**: `python3 scripts/agent_platform/analyze_traffic.py --live
            --project-id {project_id} --reasoning-engine-id
            {reasoning_engine_id} --metric-type={metric_type}`
        -   **Metrics File**: `python3 scripts/agent_platform/analyze_traffic.py --metrics-file
            {path_to_json} --metric-type={metric_type}`
    -   **Parallel Traffic Analysis**: If you need to run live traffic analysis
        for both latency and token usage, call the tool for each case
        concurrently using background tasks.
    -   **Handling Tool Failures**:
        -   If the `--live` command fails with `CredentialsMissingError` (exit
            code 1), report the error and instruct the user to run `gcloud auth
            application-default login` on their terminal.
        -   For other unexpected failures, analyze the error message (such as
            connection timeouts, invalid permissions, or missing resources).
            Attempt to dynamically correct parameters (such as verifying or
            correcting the region, project ID, or metric type) and retry
            execution before escalating.

-   Map the traffic pattern profile classified by the script to the
    corresponding policy:
    -   **Steady / Consistent**: Maps to **Long-Window Z-Score Baseline (`1w Z-Score Baseline`, 1-week lookback)**
        (safe since the script verified at least 14 days of history).
    -   **Seasonal / Cyclical**: Maps to **Seasonal Decomposition (average 1w and 1d)**.
    -   **Bursty / Inconsistent**: Maps to **Moving Averages** (1h baseline).

### Map Metrics to Algorithms

| Variance Ratio (`std_dev / mean`) | Autocorrelation (1-week lag) | Traffic Classification | Assigned Latency Algorithm and Baseline |
| :--- | :--- | :--- | :--- |
| `≤ 2.0` | `≤ 0.75` | **Steady / Consistent** | Long-Window Z-Score (`1w Z-Score Baseline`, 1-week lookback) |
| `≤ 2.0` | `> 0.75` | **Seasonal / Cyclical** | Seasonal Decomposition (average 1w and 1d) |
| `> 2.0` | Any / Not Applicable | **Bursty / Inconsistent** | Moving Averages (1-hour window) |

*Example classifications:*

-   *Steady / Consistent*: Low variance data (such as steady queries per second)
    with little or no weekly cyclical pattern.
-   *Seasonal / Cyclical*: Clear daily or weekly repeating patterns with high
    weekly correlation (such as daily peak traffic).
-   *Bursty / Inconsistent*: Highly volatile data with rapid spikes and quiet
    periods (such as batch job workloads).

-   **Fallback for Insufficient Data / No Traffic**:

    -   If the script fails with a `ValueError` indicating insufficient data
        points (less than 14 days of history), or if it outputs "New Agent / No
        Traffic" (inactive agent), you MUST fall back to the user inquiry
        instructions in
        [agent_platform_no_historical_traffic_data.md](agent_platform_no_historical_traffic_data.md)
        to ask the user for the expected traffic pattern.

-   Regardless of the script's output profile, the other policies MUST use their
    correct data-class defaults:

    -   **Error Rate**: ALWAYS use **Multi-Window Multi-Burn Rate SLO Alerting**
        (or ratio-based static limits).

## Notify the User

Clearly communicate the findings and selection at the start of your response:

1.  Explain the classified profile (Seasonal / Cyclical, Steady / Consistent, or
    Bursty / Inconsistent) output by the metrics analysis script (citing
    indicators such as standard deviation, autocorrelation, or zero-ratio from
    the script output). If falling back to user inquiry due to zero metrics or
    insufficient data, explain that.
2.  Propose the corresponding alerting policy mapping (Latency matching the
    traffic profile, Error Rate using SLO Burn Rate).
3.  Ask the user whether this expected profile mapping is correct or if they
    would like to customize standard deviation thresholds.
4.  Provide a brief plain-English explanation of what each of the proposed
    alerts measures and how the underlying algorithms work. Keep this
    explanation in the conversational response text.

## Avoid Common Pitfalls

*   **Sparse Traffic Guidance**: If `zero_ratio > 0.95` (even if the profile is
    "Steady / Consistent"), warn the user that Z-score alerts may be unstable.
    Recommend using `Short-Window Z-Score (1h baseline)` or Static Thresholds
    instead of Long-Window Z-Score (`1w Z-Score Baseline`).
