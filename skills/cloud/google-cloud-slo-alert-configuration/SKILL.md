---
name: google-cloud-slo-alert-configuration
metadata:
  category: CloudObservabilityAndMonitoring
description: >-
  Configures PromQL-based Service Level Objective (SLO) alerting policies for Google Cloud
  resources registered in App Hub or individually specified. Generates Terraform output.
  Use when the user asks to configure an SLO or Service Level Objective.
  Don't use for standard alerting policies.
---

# SLO Alert Configuration Setup Wizard

This skill guides the user through a structured conversation to configure
PromQL-based Service Level Objective (SLO) alerting policies in Terraform. Your
role is to act as a setup wizard that conceptually models the 4 key components
of an SLO API (Service Scope, Service Level, SLI, and Alert Condition), gathers
the requirements, and outputs a Terraform configuration.

## CRITICAL RULES

*   **Structured Conversation**: You **MUST** follow the 4-step wizard workflow
    below.

*   **Gather Missing Information**: Evaluate all 4 steps below first. Ask the
    user for all missing information across all steps in a single response.

    -   **DO NOT** stop after finding the first missing piece of information.

    -   **DO NOT** use the `ask_question` tool. You must ask questions using
        plain text in your response and end your turn to wait for the user to
        reply.

    -   **DO NOT** write the Terraform configuration if information is missing.

*   **Skip What Is Known**: If the user has already provided information for a
    step in their previous messages or initial prompt **DO NOT** ask them for
    it. Move to the next missing piece of information. If ALL information for
    Steps 1-4 is provided, call `write_to_file` to generate the Terraform
    configuration without asking for permission to proceed.

*   **Provide Best Practices**: Whenever you ask the user a question, you
    **MUST** explicitly state the recommended "Best Practice".

*   **Best Practice Shortcut**: If the user asks for "best practices" or
    similar, do not overwrite their explicit inputs. **SKIP** all remaining data
    gathering and keep any specific targets or custom metrics they provided. For
    all fields left blank, apply the recommended defaults defined in the "SRE
    Best Practice Suggestion" of each step.

*   **Terraform Output**: Write the generated observability configuration ONLY
    as Terraform (`.tf`) files using the `google_monitoring_alert_policy`
    resource and `condition_prometheus_query_language` resources.

*   **Alert Strategy**: **ALWAYS** include an `alert_strategy` block with an
    `auto_close` setting. Leave `notification_channels` empty unless the user
    provides one. Provide plain-English explanations of the PromQL math before
    finalizing the conversation.

--------------------------------------------------------------------------------

## SETUP WIZARD WORKFLOW

### Step 1: Define `ServiceScope`

1.  **Check Context**: Identify target resource, service, workload, or
    application the user wants to monitor. If you already know, proceed.
    Otherwise ask the user to identify it.

2.  **Autonomous Investigation**: If the user specified a project or general
    service name without providing specifics, autonomously use `gcloud` to
    discover the target services in their environment. If multiple services or
    workloads are discovered, list all of them and suggest applying SLO **ONLY**
    to the most critical backend services as a best practice.

    If you struggle to identify potential resources, ask the user to specify.

3.  **Identify Underlying Infrastructure**: To resolve the correct PromQL
    metric, you **MUST** know the underlying Google Cloud resource type.

    *   If the user only provides a logical name or an App Hub Service/Workload
        name such as `projects/.../services/frontend` or
        `projects/.../workloads/backend`, you still need to know the underlying
        infrastructure.
    *   If the prompt provides the underlying infrastructure, use that
        information. Do **NOT** attempt to discover it.
    *   If you don't know the underlying infrastructure but have a resource
        identified, you **MUST** proactively use `gcloud` to discover the
        infrastructure. If you struggle to identify the resource type, ask the
        user to specify.

4.  **Label Scoping**:

    *   If the user explicitly mentions the resource is in App Hub or provides
        an App Hub URI like `projects/.../locations/.../applications/...`, use
        App Hub labels and consult `references/app_hub_labels.md` to identify
        the correct group-by fields.
    *   Otherwise, assume it is a standard Google Cloud resource and use
        standard grouping labels such as `project_id, location, service_name`
        for Cloud Run.

    Example gcloud commands:

    -   `gcloud --quiet apphub applications services list --application=-
        --location=-`
    -   `gcloud --quiet apphub applications workloads list --application=-
        --location=-`
    -   `gcloud --quiet asset search-all-resources`
    -   `gcloud --quiet run services list`
    -   `gcloud --quiet apphub applications services describe <service>
        --application=<app> --location=<loc>`
    -   `gcloud --quiet apphub applications workloads describe <workload>
        --application=<app> --location=<loc>`
    -   `gcloud --quiet asset search-all-resources --query=<name>`

    **Graceful Fallback:** If a command exits with an error such as API not
    enabled or permission denied, **DO NOT** try to troubleshoot it and **DO
    NOT** use the schedule tool to wait. Immediately fall back to asking the
    user to provide the missing information.

### Step 2: Define `ServiceLevel` Target

1.  **Check Context**: If the user has already provided a Service Level Target
    percentage, an SLI condition/threshold, and a measurement period proceed to
    the next step. Otherwise, if any are missing, you **MUST** ask for them.
    -   Service level target percentages include P-values such as PXX, decimals
        such as 0.XX, and percentages like XX%.

    -   Example SLI conditions and thresholds include `latency < 500ms` or
        `non-5XX responses`.

*   **Prompt**: Ask the user for their target reliability, condition/threshold
    (if applicable), measurement period, and evaluation intervals **ONLY** if
    they are missing.

*   **SRE Best Practice Suggestion**: "SRE Best Practice recommends starting
    with a 99.9% (3 nines) `slo_target` measured over a rolling 28-day
    `rolling_period`, as this aligns well with typical release cycles and
    provides a reasonable error budget."

### Step 3: Define `ServiceLevelIndicator` / SLI

1.  **Check Context**: Has the user specified the exact metric name such as
    `run.googleapis.com/request_count`? If yes, proceed to the next step.
    Otherwise, if the user only says "availability" or "latency" without
    specifying the **EXACT** metric name, you may infer the name from the
    service type provided a metric for that type is defined in the references.
    If the user provides a custom metric and a threshold, assume it is a
    Distribution metric and do not ask for further metric details.

    -   You **MUST** output valid metrics defined in
        `references/service_metrics.md`. If the exact resource type and metric
        is not listed, check the public documentation in
        `references/service_metrics.md` to find the exact metric. If you still
        cannot find it, you **MUST** stop and ask the user to provide the custom
        metric.

2.  **Prompt**: Ask the user what specific metric they want to use. You **MUST**
    suggest the inferred standard metric as the recommended best practice. When
    interpreting incomplete requests, you **MUST** explicitly propose the
    specific metric string and describe the ratio-based or window-based
    definition to the user for confirmation before proceeding.

3.  **Metric Mapping**: Consult `references/service_metrics.md` to find the
    exact PromQL metric string for the Resource Type identified in Step 1
    section 3. If the requested metric type does not exist for the resource in
    the references or the primary public documentation, you **MUST** explicitly
    inform the user that there is no default metric and ask them to provide the
    specific custom metric name. You **MUST** provide guidance on how a custom
    latency metric might be structured.

    -   **CRITICAL:** If the primary documentation does not list a default
        metric, you **MUST NOT** try to piece together advanced metrics. Ask the
        user to provide the custom metric.

4.  **Evaluation Method**: Default the `EvaluationType` to `REQUEST_BASED`
    unless the user specifically describes a `window-based` requirement,
    typically denoted by "good minutes" or "bad minutes".

    *   **Window-Based Lookback Period**: If the user indicates a window-based
        evaluation, you need to know the duration of the lookback windows and
        the evaluation interval for each window. You **MUST** ask the user to
        specify both the lookback duration and the evaluation interval if they
        have not already provided them. You **CANNOT** generate an alerting
        policy without this configuration.

5.  **SRE Best Practice Suggestion**: SRE Best Practice recommends starting with
    two SLIs:

    -   **Availability**: a `Ratio SLI` comparing successful requests typically
        defined as `non-5XX` responses, to total requests evaluated as
        `REQUEST_BASED`.
    -   **Latency**: a `Distribution SLI` evaluated as `WINDOW_BASED` such as
        99% of 5-minute windows must meet a 300ms threshold.

### Step 4: Define Alerting Policy

1.  **Check Context**: Has the user specified burn rates? If yes, proceed to the
    next step. Otherwise, ask the user to specify a burn rate strategy and
    provide a best practice suggestion.

2.  **SRE Best Practice Suggestion**: SRE Best Practice recommends both a
    multi-window fast burn and multi-window slow burn.

    -   **Multi-Window Fast Burn**: Factor 14.4 over 1h and 5m windows, catching
        severe outages quickly without false positives.

    -   **Multi-Window Slow Burn**: Factor 1 over 3d and 6h windows, catching
        system degradation.

### Step 5: Generate Configuration

1.  Look up the corresponding PromQL template from
    `references/promql_templates.md` based on the user's choices. Use a
    `Window-Based` template for window-based SLOs.
2.  Populate the template with the `ServiceScope` labels, `ServiceLevel`
    targets, and `ServiceLevelIndicator` metrics.
3.  Wrap it in Terraform (`google_monitoring_alert_policy`).
4.  Present the `.tf` block with a plain English explanation of the math.
5.  **CRITICAL:** Explicitly warn the user in the final summary if no
    notification channels are configured. Inform them that you can assist with
    setting those up if they would like.

--------------------------------------------------------------------------------

## Supporting Links

*   [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
*   [Google Cloud Operations: SLO Monitoring](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring.md.txt)
*   [Prometheus: PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

## Reporting Issues

Report bugs or improvements for this skill at
[Google Skills Issues](https://github.com/google/skills/issues).
