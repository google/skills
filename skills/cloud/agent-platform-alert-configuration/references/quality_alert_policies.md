# Quality Alert Policies

> [!IMPORTANT]
> Quality alerting policies are specific to **Vertex AI Agent Engine**
> deployments and rely on metrics exported by **Vertex AI Online Monitors**.

These alert policies will help users diagnose drops in response quality (intent
drift) or hallucination rates from their agents. They can also help identify
when an agent gets stuck in an infinite reasoning or tool call loop.

## Table of Contents

-   [Prerequisites](#prerequisites) (~Line 22)
    -   [Online Monitor Provisioning and Cost Warning](#online-monitor-provisioning-and-cost-warning)
        (~Line 24)
-   [Critical Rules](#critical-rules) (~Line 104)
    -   [Telemetry Metrics](#telemetry-metrics) (~Line 118)
-   [Policy Specifications](#policy-specifications) (~Line 146)
    -   [Final Response Quality](#final-response-quality) (~Line 148)
    -   [Tool Use Quality](#tool-use-quality) (~Line 181)
    -   [Hallucination](#hallucination) (~Line 215)
-   [Tooling Scripts](#tooling-scripts) (~Line 249)
-   [Gotchas and Behavioral Corrections](#gotchas-and-behavioral-corrections)
    (~Line 267)

## Prerequisites

### Online Monitor Provisioning and Cost Warning

Quality alerting policies rely on metrics exported by Online Monitors. If
telemetry is disabled on the reasoning engine, no traces are sent, and the
quality metrics will remain empty. You MUST ensure the Online Monitor is
provisioned for the agent and telemetry is enabled:

-   [ ] **Ask for Approval**: Both Online Monitors and Telemetry incur separate
    billing charges. Before provisioning them, you MUST warn the user about
    these extra costs. If not pre-approved in the prompt, you MUST ask a direct
    question in your response requesting confirmation/approval to proceed (e.g.,
    "Please confirm if you approve the extra billing costs for the Online
    Monitor and Telemetry to proceed.").
-   [ ] **Verify Telemetry First**: Before generating any alerting policy plan
    or provisioning Online Monitors, you MUST always verify the telemetry status
    of the Reasoning Engine first using the `check_telemetry.py` script as
    detailed in [Verify Telemetry Status](#verify-telemetry-status) below.

#### Verify Telemetry Status

Before generating any alerting policies, proposing a plan, or provisioning
Online Monitors, you MUST always check if the agent is ready to export traces by
running the telemetry checking script:

*   **Mandatory Command**: `python3 scripts/check_telemetry.py --project-id
    "{project_id}" --agent-resource-name "{agent_resource_name}"`
    *   **Note on Parameters**: The `{agent_resource_name}` parameter MUST be
        the full resource path format
        `projects/<project_id>/locations/<location>/reasoningEngines/<agent_id>`
        (e.g. `projects/gcp-prod/locations/us-central1/reasoningEngines/556677`)
        and not just the agent ID itself.
    *   **Dependency Failures**: If package imports or dependency installation
        fails, try your best to resolve the issues (e.g., by verifying package
        installation) and run the script again with the specific project-id and
        agent-resource-name parameters. If you cannot run the script
        successfully due to missing dependencies, you MUST still attempt to run
        it first and then include the complete, pre-populated execution command
        in your final response as a verification plan (this applies even if the
        user has pre-approved provisioning).
*   **Detailed Enablement Instructions**: For details on the required
    environment variables, Terraform setups, and project dependencies, you MUST
    read and follow:
    [telemetry_enablement.md](references/telemetry_enablement.md).

#### Provision the Online Monitor

Because Online Monitors cannot be configured via Terraform, follow the
instructions in the `Tooling & Scripts` section to run the
`create_online_monitor` provisioning script and generate the required metrics.

#### Formatting the Execution Plan

If execution fails (e.g. due to sandbox restrictions or permissions), you MUST
provide a clear, actionable plan for the user to follow as a next step. Your
response MUST explicitly include a section containing the exact python execution
command with all parameter values (such as project ID, region, and agent
resource name) fully populated. Do not merely state that the user should run it.

You MUST format the plan exactly as follows:

### Execution Plan: Online Monitor Provisioning

**Online Monitor Provisioning Command:**

```bash
python3 scripts/create_online_monitor.py \
  --project-id "{project_id}" \
  --agent-resource-name "projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}" \
  --sampling-percentage {percentage}
```

**Verify Telemetry Command (Optional fallback):**

```bash
python3 scripts/check_telemetry.py \
  --project-id "{project_id}" \
  --agent-resource-name "projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"
```

## Critical Rules

*   **Alert policy configuration**: You MUST configure exactly the following
    Quality alerting policies. See the `Telemetry Metrics` section to get the
    required metrics and read the descriptions for each signal:
    1.  **Final Response Quality** (5-Minute window)
    2.  **Tool Use Quality** (5-Minute window)
    3.  **Hallucination** (5-Minute window)
*   **Standard Threshold Filters for Agent Quality**: For the 3 agent quality
    metrics, you MUST use standard `condition_threshold` filters matching the
    monitored resource type `aiplatform.googleapis.com/OnlineEvaluator` and
    metric type `aiplatform.googleapis.com/online_evaluator/scores`. Do **NOT**
    use PromQL or condition_sql.

### Telemetry Metrics

Because the scores metric is of value type `DISTRIBUTION`, standard mean-based
PromQL or arithmetic `ALIGN_MEAN` aligners are unsupported. You MUST use a
percentile aligner (typically `ALIGN_PERCENTILE_50` to evaluate the median
score) within the `aggregations` block of your `condition_threshold`.

Signal                           | Metric Name (`evaluation_metric_name`) | Target Threshold    | Recommended Aligner
:------------------------------- | :------------------------------------- | :------------------ | :------------------
**Final Response Quality**       | `final_response_quality_v1`            | `< 0.8` (or custom) | `ALIGN_PERCENTILE_50`
**Tool Use Quality**             | `tool_use_quality_v1`                  | `< 0.8` (or custom) | `ALIGN_PERCENTILE_50`
**Hallucination (Groundedness)** | `hallucination_v1`                     | `< 0.9` (or custom) | `ALIGN_PERCENTILE_50`

### Metric Filter Example

All agent quality evaluation metrics are exported by Online Monitors to the
monitored resource type `aiplatform.googleapis.com/OnlineEvaluator` under the
metric type `aiplatform.googleapis.com/online_evaluator/scores`.

When configuring a quality alert policy in Terraform, use the following filter
expression structure:

```
resource.type="aiplatform.googleapis.com/OnlineEvaluator"
AND metric.type="aiplatform.googleapis.com/online_evaluator/scores"
AND metric.labels.evaluation_metric_name="{metric_name}"
```

## Policy Specifications

### Final Response Quality

#### Terraform HCL

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
      duration                = "300s" # 5m buffer as per gotchas
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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

### Tool Use Quality

#### Terraform HCL

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

### Hallucination

#### Terraform HCL

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
    created-with-google-skill = "agent-platform-alert-configuration"
  }
}
```

## Tooling Scripts

1.  **create_online_monitor**: Use this script to provision the required Online
    Monitor and generate the telemetry metrics:
    *   Command: `python3 scripts/create_online_monitor.py
        --project-id={gcp_project_id}
        --agent-resource-name={agent_resource_name}
        [--sampling-percentage={percentage}]`
    *   Sampling Rate Recommendation: For production agents, configure a
        conservative sampling percentage (default: **10%**) to control LLM
        evaluation costs. For details, refer to
        [Continuous evaluation with online monitors](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-online).
2.  **check_telemetry**: Use this script to check the telemetry status on a
    Vertex AI Reasoning Engine:
    *   Command: `python3 scripts/check_telemetry.py
        --project-id={gcp_project_id}
        --agent-resource-name="projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"`

## Gotchas and Behavioral Corrections

*   **Duration Buffers (Transient Glitches)**: To avoid alerts firing on
    transient spikes, always use a `duration = "300s"` (5 minutes) buffer to
    filter out transient scoring dips or evaluation outliers caused by temporary
    LLM judge congestion, or edge-case query outliers.
*   **Script Failures**: If `check_telemetry.py` or `create_online_monitor.py`
    fail unexpectedly, analyze the error message. Common issues include invalid
    `agent-resource-name` format (must be full path), missing permissions, or
    API not enabled. Attempt to dynamically correct parameters and retry.
