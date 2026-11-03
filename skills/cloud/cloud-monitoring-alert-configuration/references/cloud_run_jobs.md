# Configure Cloud Run Job Alerts

Best-practice observability for scheduled or on-demand Cloud Run Jobs.

## Table of Contents

* [Configure the Fast-Path Job Execution Failure Alert](#configure-the-fast-path-job-execution-failure-alert): Lines 16-25
* [Apply Default Constants and Parameterization](#apply-default-constants-and-parameterization): Lines 26-36
* [Delegate SLOs and Apply the Fallback Rule](#delegate-slos-and-apply-the-fallback-rule): Lines 37-71
* [Configure PromQL and Terraform Policies](#configure-promql-and-terraform-policies): Lines 72-133
  * [Configure the Immediate Job Failure Alert](#configure-the-immediate-job-failure-alert): Lines 74-133
* [Map Telemetry Data Sources](#map-telemetry-data-sources): Lines 134-139

---

## Configure the Fast-Path Job Execution Failure Alert

For Cloud Run Jobs (scheduled cron, on-demand batch processing, or ETL workflows),
every execution failure represents direct user or system impact.

The standard observability strategy for Cloud Run Jobs is to **alert immediately
on any failed job execution (`result="failed"`)**.

---

## Apply Default Constants and Parameterization

All generated Terraform alert policies use explicit default constants. Override
any parameter using HCL variables or prompt instructions:

| Constant / Parameter | Explicit Default | HCL Variable Name | Description & Override Option |
| :--- | :--- | :--- | :--- |
| `single_failure_lookback` | `"15m"` | `var.single_failure_lookback` | Lookback window for detecting single job execution failures. |

---

## Delegate SLOs and Apply the Fallback Rule

**Execution success rate SLOs are owned by the
`google-cloud-slo-alert-configuration` skill.** Delegate to it whenever the user
asks for an SLO, an error budget, or burn-rate alerting on a Cloud Run job. That
skill owns the SLO wizard, the burn-rate templates
(`references/promql_templates.md`), the SLI mapping
(`references/service_metrics.md`), and the App Hub scoping labels
(`references/app_hub_labels.md`).

> [!NOTE] For most Cloud Run Jobs the immediate `result="failed"` alert is the
> correct primary signal. An execution success rate SLO is worth adding **in
> addition** only when the job runs frequently (for example every few minutes) —
> a low-frequency nightly job does not produce enough samples for a meaningful
> error budget.

**Context to hand off** (so the SLO skill does not repeat discovery):

*   **Resource type**: Cloud Run job.
*   **Grouping labels**: `job_name`, `location`.
*   **Execution SLI**: `run_googleapis_com:job_completed_execution_count`; bad =
    `result="failed"`, total = all completed executions.
*   **SLO target**: `0.999` (99.9%) by default; confirm with the user.

Delegate the SLO policies and continue generating the immediate
execution-failure policy from this reference in the same response.

**Fallback** — only if `google-cloud-slo-alert-configuration` is not installed:
this reference intentionally carries **no** burn-rate templates. Say that
execution success rate SLOs require that skill, and continue with the immediate
execution-failure policy. Do **NOT** author burn-rate PromQL here, and never
silently present SLO policies as if this skill owned them.

---

## Configure PromQL and Terraform Policies

### Configure the Immediate Job Failure Alert

Monitors any single execution failure (`result="failed"`). Evaluates with
`duration = "0s"` to page immediately upon task/job failure.

#### Write the PromQL Query

```promql
sum(
  increase(run_googleapis_com:job_completed_execution_count{result="failed", job_name="[JOB_NAME]"}[15m])
) by (job_name, location) > 0
```

#### Define the Terraform Policy

```hcl
variable "monitored_jobs" {
  description = "List of Cloud Run job names to monitor for execution failures"
  type        = list(string)
  default     = ["data-ingest", "nightly-sync"]
}

variable "single_failure_lookback" {
  description = "Lookback window for detecting single execution failures"
  type        = string
  default     = "15m"
}

resource "google_monitoring_alert_policy" "job_execution_failure" {
  for_each     = toset(var.monitored_jobs)
  project      = var.scoping_project_id
  display_name = "[Cloud Run Job] Execution Failure - ${each.value}"
  combiner     = "OR"

  conditions {
    display_name = "Job Execution Failed - ${each.value}"
    condition_prometheus_query_language {
      query = <<-EOT
        sum(
          increase(run_googleapis_com:job_completed_execution_count{result="failed", job_name="${each.value}"}[${var.single_failure_lookback}])
        ) by (job_name, location) > 0
      EOT
      duration = "0s"
    }
  }

  user_labels = {
    severity                    = "critical"
    job                         = each.value
    tier                        = "failure"
    "created-with-google-skill" = "cloud-monitoring-alert-configuration"
  }

  alert_strategy { auto_close = "604800s" }
  notification_channels = var.notification_channels
}
```

---

## Map Telemetry Data Sources

| Signal Indicator | Native Metric | SRE Strategy |
| :--- | :--- | :--- |
| **Job Execution Failure** | `run.googleapis.com/job/completed_execution_count` | **Immediate Failure Alert**: Alert immediately on any failed execution (`result="failed"`) |
| **Execution Success SLO** | `run.googleapis.com/job/completed_execution_count` | **Delegate to `google-cloud-slo-alert-configuration`**: multi-window burn rate, Fast Burn (1h/5m, 14.4x) & Slow Burn (3d/6h, 1.0x) |
