# No Historical Traffic Data Available

Use these instructions if there is no historical metrics data available for the
agent (e.g., brand new agent):

## 1. Ask the User for the Metric Pattern and Handle Defaults

-   Because no historical metrics data is available and we do NOT perform
    pattern inference based on the name, description, or context of the agent,
    you MUST explicitly ask the user directly in your response what pattern they
    expect for their agent.
-   **Direct Question Format**: You MUST write a direct question in your
    response (e.g., "What traffic/usage pattern do you expect for your agent?")
    and explicitly present the following three options for customization:
    -   **Steady/Consistent**: Maps the alert policy to **Short-Window Z-Score
        Baseline (1-hour lookback)**.
    -   **Bursty/Inconsistent**: Maps alert policy to **Moving Averages (1-hour
        baseline)**.
    -   **Seasonal/Cyclical**: Maps alert policy to **Seasonal Decomposition**
        (requires offsets `1d` and `1w`).
-   Inform the user that the default pattern is **Steady/Consistent** (which
    maps to Short-Window Z-Score Baseline), and that you will use this default
    if they do not specify one.
-   **Handling Automated or Immediate Setup Requests**: If the user's prompt
    asks you to configure or write the alerting policies immediately (e.g., "Set
    up its alerting policies in 'monitoring/alerts.tf'"), or if you are running
    in an automated/non-interactive script, you MUST NOT pause to wait for their
    response. Instead, ask the question in your response, state that you are
    deploying the default Steady/Consistent pattern because no choice was
    specified yet, and **immediately proceed to generate and write the default
    configuration (Steady / Consistent -> Short-Window Z-Score)**.
-   Regardless of the selected pattern, the other policies MUST use their
    correct data-class defaults:
    -   **Error Rate**: ALWAYS use **Multi-Window Multi-Burn Rate SLO Alerting**
        (or ratio-based static limits).

*   **Short-Window Z-Score / Moving Averages**: Require **1 hour** of metric
    history.

*   **SLO Burn Rate (Error Rate)**: Requires up to **3 days** for the slow burn
    component, though the fast burn component (1h/5m) will work after 1 hour.

*   **Seasonal Decomposition**: Requires **1 week** of history (due to the `1w`
    offset). **WARNING:** If the user switches to Seasonal Decomposition, warn
    them that they will have a 1-week blind spot, and suggest starting with
    **Short-Window Z-Score** or **Static Thresholds** as a temporary guard.

## 2. User Notification

Clearly communicate the lack of historical data, explain the options, and detail
the immediate actions taken at the start of your response:

1.  Explain that since the agent has no historical data, you cannot
    automatically analyze the traffic pattern.
2.  Ask the user directly what traffic pattern they expect (Steady, Seasonal, or
    Bursty), detailing the mapping differences and the 1-week blind spot risk if
    they choose Seasonal.
3.  Inform the user that the default is **Steady / Consistent** (Short-Window
    Z-Score algorithm for Latency) and you will proceed with this default if
    they don't have a good idea or do not choose.
4.  If the user accepts the default, explain that you have deployed the
    Steady/Consistent default to ensure the files are configured immediately,
    but they can request an update if they prefer another pattern.
5.  Explain the warm-up periods (1 hour for Latency, up to 3 days for SLOs).
6.  Propose the rest of the configuration mapping: Error Rate (SLO Burn Rate).
7.  Provide a brief plain-English explanation of what each of the proposed
    alerts measures and how the underlying algorithms work and what they
    actually measure.
