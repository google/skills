# Configure Alerts Without Historical Traffic Data

Follow these instructions when no historical metrics data is available for the
agent (for example, a brand new agent).

## Ask the User for the Metric Pattern and Handle Defaults

-   Because no historical metrics data is available and we do NOT perform
    pattern inference based on the name, description, or context of the agent,
    you MUST explicitly ask the user directly in your response what pattern they
    expect for their agent.
-   **Direct Question Format**: You MUST write a direct question in your
    response (for example, "What traffic or usage pattern do you expect for your
    agent?") and explicitly present the following three options for
    customization:
    -   **Steady / Consistent**: Maps the alert policy to **Short-Window Z-Score
        (`Short-Window Z-Score (1h baseline)`, 1-hour lookback)**.
    -   **Bursty / Inconsistent**: Maps the alert policy to **Moving Averages
        (1-hour baseline)**.
    -   **Seasonal / Cyclical**: Maps the alert policy to **Seasonal
        Decomposition (`Seasonal Decomposition (average 1w and 1d)`, requires
        offsets `1d` and `1w`)**.
-   Inform the user that the default pattern is **Steady / Consistent** (which
    maps to `Short-Window Z-Score (1h baseline)`), and that you will use this
    default if they do not specify one.
-   **Handling Automated or Immediate Setup Requests**: If the user's prompt
    asks you to configure or write the alerting policies immediately (for
    example, "Set up its alerting policies in 'monitoring/alerts.tf'"), or if
    you are running in an automated or non-interactive script, you MUST NOT
    pause to wait for their response. Instead, ask the question in your
    response, state that you are deploying the default Steady / Consistent
    pattern because no choice was specified yet, and **immediately proceed to
    generate and write the default configuration (Steady / Consistent ->
    `Short-Window Z-Score (1h baseline)`)**.
-   Regardless of the selected pattern, the other policies MUST use their
    correct data-class defaults:
    -   **Error Rate**: ALWAYS use **Multi-Window Multi-Burn Rate SLO Alerting**
        (or ratio-based static limits).

*   **Short-Window Z-Score (`Short-Window Z-Score (1h baseline)`) / Moving
    Averages**: Require **1 hour** of metric history.

*   **SLO Burn Rate (Error Rate)**: Requires up to **3 days** for the slow burn
    component, though the fast burn component (`1h`/`5m`) works after 1 hour.

*   **Seasonal Decomposition (`Seasonal Decomposition (average 1w and 1d)`)**:
    Requires **1 week** of history (due to the `1w` offset). **WARNING:** If the
    user switches to Seasonal Decomposition, warn them that they will have a
    1-week blind spot, and suggest starting with **Short-Window Z-Score
    (`Short-Window Z-Score (1h baseline)`)** or **Static Thresholds** as a
    temporary guard.

## Notify the User

Clearly communicate the lack of historical data, explain the options, and detail
the immediate actions taken at the start of your response:

1.  Explain that because the agent has no historical data, you cannot
    automatically analyze the traffic pattern.
2.  Ask the user directly what traffic pattern they expect (Steady / Consistent,
    Seasonal / Cyclical, or Bursty / Inconsistent), detailing the mapping
    differences and the 1-week blind spot risk if they choose Seasonal.
3.  Inform the user that the default is **Steady / Consistent** (`Short-Window
    Z-Score (1h baseline)` algorithm for Latency) and you will proceed with this
    default if they do not choose another option.
4.  If the user accepts the default, explain that you have deployed the Steady /
    Consistent default to ensure the files are configured immediately, and that
    they can request an update if they prefer another pattern.
5.  Explain the warm-up periods (1 hour for Latency, up to 3 days for SLOs).
6.  Propose the rest of the configuration mapping: Error Rate (SLO Burn Rate).
7.  Provide a brief plain-English explanation of what each of the proposed
    alerts measures and how the underlying algorithms work.
