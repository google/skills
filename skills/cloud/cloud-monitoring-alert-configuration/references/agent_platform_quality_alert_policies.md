# Configure Quality Alert Policies

> [!IMPORTANT]
> Quality alerting policies are specific to **Vertex AI Agent Engine**
> deployments and rely on metrics exported by **Vertex AI Online Monitors**.

These alert policies help users diagnose drops in response quality (intent
drift) or hallucination rates from their agents. They also help identify when
an agent gets stuck in an infinite reasoning or tool call loop.

## Table of Contents

-   [Verify Prerequisites](#verify-prerequisites): Lines 25-117
    -   [Warn About Billing Costs and Provision the Online Monitor](#warn-about-billing-costs-and-provision-the-online-monitor): Lines 27-117
-   [Follow Critical Rules](#follow-critical-rules): Lines 118-161
    -   [Review Telemetry Metrics](#review-telemetry-metrics): Lines 134-146
    -   [Construct the Metric Filter](#construct-the-metric-filter): Lines 147-161
-   [Configure Policy Specifications](#configure-policy-specifications): Lines 162-263
    -   [Configure Final Response Quality](#configure-final-response-quality): Lines 164-196
    -   [Configure Tool Use Quality](#configure-tool-use-quality): Lines 197-229
    -   [Configure Hallucination Alerts](#configure-hallucination-alerts): Lines 230-263
-   [Run Tooling Scripts](#run-tooling-scripts): Lines 264-281
-   [Validate and Finalize](#validate-and-finalize): Lines 282-292

## Verify Prerequisites

### Warn About Billing Costs and Provision the Online Monitor

Quality alerting policies rely on metrics exported by Online Monitors. If
telemetry is disabled on the reasoning engine, no traces are sent, and the
quality metrics remain empty. Ensure the Online Monitor is provisioned for the
agent and telemetry is enabled:

-   [ ] **Ask for Approval with Billing Warning**: Both Online Monitors and
    Telemetry incur separate billing charges. If not pre-approved in the prompt:
    -   Your response MUST warn the user about the potential billing costs of
        **Online Monitor** and explicitly ask the user for approval before
        configuring or provisioning it.
    -   Your response MUST warn the user about the potential billing costs of
        **Telemetry (Cloud Trace/Logging export)** and explicitly ask the user
        for approval before configuring or enabling it.
    -   **Important**: Even when printing draft Terraform HCL or CLI commands
        without executing them, do not merely list billing warnings as passive
        bullet points — you MUST include a direct question asking the user to
        confirm and approve both Online Monitor and Telemetry billing costs
        before configuring them (for example, *"Do you approve enabling
        Telemetry (Cloud Trace/Logging export) and provisioning the Vertex AI
        Online Monitor, given the additional billing costs they incur?"*).
-   [ ] **Verify Telemetry First**: Before generating any alerting policy plan
    or provisioning Online Monitors, you MUST always verify the telemetry status
    of the Reasoning Engine first using the `check_telemetry.py` script as
    detailed in [Verify Telemetry Status](#verify-telemetry-status) below.

#### Verify Telemetry Status

Before generating any alerting policies, proposing a plan, or provisioning
Online Monitors, you MUST always verify whether the agent is ready to export
traces by running the telemetry verification script:

*   **Mandatory Command**: `python3 scripts/agent_platform/check_telemetry.py
    --project-id "{project_id}" --agent-resource-name "{agent_resource_name}"`
    *   **Note on Parameters**: The `{agent_resource_name}` parameter MUST be
        the full resource path format
        `projects/<project_id>/locations/<location>/reasoningEngines/<agent_id>`
        (for example,
        `projects/gcp-prod/locations/us-central1/reasoningEngines/556677`) and
        not just the agent ID itself.
    *   **Dependency Failures**: If package imports or dependency installation
        fails, resolve the issues (for example, by verifying package
        installation) and run the script again with the specific `project-id`
        and `agent-resource-name` parameters. If you cannot run the script
        successfully due to missing dependencies, you MUST still attempt to run
        it first and then include the complete, pre-populated execution command
        in your final response as a verification plan (this applies even if the
        user has pre-approved provisioning).
*   **Detailed Enablement Instructions**: For details on the required
    environment variables, Terraform setups, and project dependencies, you MUST
    read and follow:
    [agent_platform_telemetry_enablement.md](agent_platform_telemetry_enablement.md).

#### Provision the Online Monitor

Because Online Monitors cannot be configured using Terraform, follow the
instructions in [Run Tooling Scripts](#run-tooling-scripts) to run the
`create_online_monitor` provisioning script and generate the required metrics.
Proceed to the **Validate and Finalize** section below.

#### Format the Execution Plan

If execution fails (for example, due to sandbox restrictions or permissions),
you MUST provide a clear, actionable plan for the user to follow as a next
step. Your response MUST explicitly include a section containing the exact
Python execution command with all parameter values (such as project ID, region,
and agent resource name) fully populated. Do not merely state that the user must
run it.

Format the plan as follows:

#### Provide the Online Monitor Provisioning Plan

**Online Monitor Provisioning Command:**

```bash
python3 scripts/agent_platform/create_online_monitor.py \
  --project-id "{project_id}" \
  --agent-resource-name "projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}" \
  --sampling-percentage {percentage}
```

**Verify Telemetry Command (Optional fallback):**

```bash
python3 scripts/agent_platform/check_telemetry.py \
  --project-id "{project_id}" \
  --agent-resource-name "projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"
```

## Follow Critical Rules

*   **Alert policy configuration**: You MUST configure the following Quality
    alerting policies (single-metric degradation policies, also referred to as
    `Quality - Metric Degradation (Single Metric)`). See
    [Review Telemetry Metrics](#review-telemetry-metrics) to get the required
    metrics and read the descriptions for each signal:
    1.  **Final Response Quality** (5-Minute window)
    2.  **Tool Use Quality** (5-Minute window)
    3.  **Hallucination** (5-Minute window)
*   **Standard Threshold Filters for Agent Quality**: For the 3 agent quality
    metrics, you MUST use standard `condition_threshold` filters matching the
    monitored resource type `aiplatform.googleapis.com/OnlineEvaluator` and
    metric type `aiplatform.googleapis.com/online_evaluator/scores`. Do **NOT**
    use PromQL or `condition_sql`.

### Review Telemetry Metrics

Because the scores metric is of value type `DISTRIBUTION`, standard mean-based
PromQL or arithmetic `ALIGN_MEAN` aligners are unsupported. You MUST use a
percentile aligner (typically `ALIGN_PERCENTILE_50` to evaluate the median
score) within the `aggregations` block of your `condition_threshold`.

| Signal | Metric Name (`evaluation_metric_name`) | Target Threshold | Recommended Aligner |
| :--- | :--- | :--- | :--- |
| **Final Response Quality** | `final_response_quality_v1` | `< 0.8` (or custom) | `ALIGN_PERCENTILE_50` |
| **Tool Use Quality** | `tool_use_quality_v1` | `< 0.8` (or custom) | `ALIGN_PERCENTILE_50` |
| **Hallucination (Groundedness)** | `hallucination_v1` | `< 0.9` (or custom) | `ALIGN_PERCENTILE_50` |

### Construct the Metric Filter

All agent quality evaluation metrics are exported by Online Monitors to the
monitored resource type `aiplatform.googleapis.com/OnlineEvaluator` under the
metric type `aiplatform.googleapis.com/online_evaluator/scores`.

When configuring a quality alert policy in Terraform, use the following filter
expression structure:

```promql
resource.type="aiplatform.googleapis.com/OnlineEvaluator"
AND metric.type="aiplatform.googleapis.com/online_evaluator/scores"
AND metric.labels.evaluation_metric_name="{metric_name}"
```

## Configure Policy Specifications

### Configure Final Response Quality

#### Define Terraform HCL for Final Response Quality

```terraform
resource "google_monitoring_alert_policy" "final_response_quality" {
  project      = var.project_id
  display_name = "Agent Quality - Final Response Quality Low"
  combiner     = "OR"
  conditions {
    display_name = "Final Response Quality Score < 0.8"
    condition_threshold {
      filter                  = "resource.type=\"aiplatform.googleapis.com/OnlineEvaluator\" AND metric.type=\"aiplatform.googleapis.com/online_evaluator/scores\" AND metric.labels.evaluation_metric_name=\"final_response_quality_v1\""
      comparison              = "COMPARISON_LT"
      threshold_value         = 0.8
      duration                = "300s" # 5m buffer
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "300s" # Aligned with duration
        per_series_aligner = "ALIGN_PERCENTILE_50"
      }
    }
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

### Configure Tool Use Quality

#### Define Terraform HCL for Tool Use Quality

```terraform
resource "google_monitoring_alert_policy" "tool_use_quality" {
  project      = var.project_id
  display_name = "Agent Quality - Tool Use Quality Low"
  combiner     = "OR"
  conditions {
    display_name = "Tool Use Quality Score < 0.8"
    condition_threshold {
      filter                  = "resource.type=\"aiplatform.googleapis.com/OnlineEvaluator\" AND metric.type=\"aiplatform.googleapis.com/online_evaluator/scores\" AND metric.labels.evaluation_metric_name=\"tool_use_quality_v1\""
      comparison              = "COMPARISON_LT"
      threshold_value         = 0.8
      duration                = "300s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_PERCENTILE_50"
      }
    }
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

### Configure Hallucination Alerts

#### Define Terraform HCL for Hallucination Alerts

```terraform
resource "google_monitoring_alert_policy" "hallucination" {
  project      = var.project_id
  display_name = "Agent Quality - Hallucination (Groundedness) Low"
  combiner     = "OR"

  conditions {
    display_name = "Groundedness Score < 0.9"
    condition_threshold {
      filter                  = "resource.type=\"aiplatform.googleapis.com/OnlineEvaluator\" AND metric.type=\"aiplatform.googleapis.com/online_evaluator/scores\" AND metric.labels.evaluation_metric_name=\"hallucination_v1\""
      comparison              = "COMPARISON_LT"
      threshold_value         = 0.9
      duration                = "300s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_PERCENTILE_50"
      }
    }
  }

  user_labels = {
    created-with-google-skill = "cloud-monitoring-alert-configuration"
  }
}
```

## Run Tooling Scripts

1.  **create_online_monitor**: Use this script to provision the required Online
    Monitor and generate the telemetry metrics:
    *   Command: `python3 scripts/agent_platform/create_online_monitor.py
        --project-id={gcp_project_id}
        --agent-resource-name={agent_resource_name}
        [--sampling-percentage={percentage}]`
    *   Sampling Rate Recommendation: For production agents, configure a
        conservative sampling percentage (default: **10%**) to control LLM
        evaluation costs. For details, refer to
        [Continuous evaluation with online monitors](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-online.md.txt).
2.  **check_telemetry**: Verify whether telemetry is enabled on a Vertex AI
    Reasoning Engine using this script:
    *   Command: `python3 scripts/agent_platform/check_telemetry.py
        --project-id={gcp_project_id}
        --agent-resource-name="projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"`

## Validate and Finalize

*   **Apply Duration Buffers (Transient Glitches)**: To avoid alerts firing on
    transient spikes, always use a `duration = "300s"` (5 minutes) buffer to
    filter out transient scoring dips or evaluation outliers caused by temporary
    LLM judge congestion or edge-case query outliers.
*   **Handle Script Failures**: If `check_telemetry.py` or
    `create_online_monitor.py` fails unexpectedly, analyze the error message.
    Common issues include an invalid `agent-resource-name` format (must be the
    full path), missing permissions, or an unenabled API. Dynamically correct
    parameters and retry.
