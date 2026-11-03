# Configure Generic Alert Policies for Other Resources

This reference provides best-practice alerting patterns for **arbitrary Google Cloud
resources, custom workloads, or service types** that do not have dedicated
resource-specific alert references in this skill (such as Cloud Run or GKE).

To maintain **consistency across all alerting policies in this skill**, we
prioritize **PromQL (`condition_prometheus_query_language`)** where supported by
Cloud Monitoring (through managed Prometheus or Cloud Monitoring PromQL
evaluation). Note that **Monitoring Query Language (MQL) is deprecated in favor
of PromQL** — whenever a user requests an MQL alert policy, explicitly inform
them that MQL is deprecated in favor of PromQL and provide the equivalent PromQL
configuration.

## Follow Mandatory Requirements for Generic Resource Alerts

When configuring alerts for any generic, custom, or fallback Google Cloud resource (such
as Cloud SQL, Spanner, Memorystore Redis, Pub/Sub, custom processing pipelines,
MQL migration, or **adding alerts to `monitoring/alerts.tf` / HCL review and
deduplication**), follow the patterns in this reference directly. **Do not search the workspace for additional reference files, scripts, or unrelated `.tf` files.** Only inspect an existing `.tf` file (such as `monitoring/alerts.tf`) when the user asks to add to, review, or deduplicate that file. Run `python3
scripts/discover_metric_schema.py --project <project_id> --resource-type
<resource_type>` to verify exact PromQL metric names (including `_bucket`),
units (for example, `us` versus `ms`), resource grouping labels, and documented label enum
values before writing HCL. **When responding to these requests, you MUST**:

1.  **Run schema & metric discovery commands**: Run `python3
    scripts/discover_metric_schema.py` and `gcloud monitoring metric-descriptors
    list` when configuring alerts for custom or unsupported resources, and
    include the exact commands in your response.
2.  **Run PromQL validation commands**: Run `python3 scripts/lint_promql.py`
    and/or `python3 scripts/discover_metric_schema.py --promql` (and `grep`/`diff`
    for HCL review) when generating, fixing, validating, or deduplicating
    HCL/PromQL queries, and include the exact commands in your response.
3.  **Perform in-place HCL deduplication**: For HCL review or deduplication
    requests, explicitly describe inspecting existing HCL policies for
    duplicates and performing an **in-place update** rather than appending
    duplicate blocks.
4.  **Use explicit grouping**: Use `sum by (<label>)` (for example, `sum by (service)`)
    or `group_by_fields` for fleet-wide aggregation (never ungrouped scalar
    `sum(...)`).
5.  **Explicitly note MQL deprecation**: State that MQL is deprecated in favor
    of PromQL if MQL is requested.
6.  **Prompt for Notification Channels**: Always ask the user at the end of your
    response if they would like to configure notification channels if none were
    provided.
7.  **Delegate SLOs**: Whenever an availability, latency, or throughput SLO (or
    an error-budget / burn-rate alert) is requested, follow
    [Delegate SLOs and Apply the Fallback Rule](#delegate-slos-and-apply-the-fallback-rule) below:
    discover the exact SLI metric with `scripts/discover_metric_schema.py`, then
    delegate the SLO policy generation to the
    `google-cloud-slo-alert-configuration` skill — never emit a single static
    error ratio as an SLO.

---

## Review the Table of Contents

1.  [Discover and Select Metrics](#discover-and-select-metrics): Lines 75-113
2.  [Apply the Four Golden Signals Framework (PromQL)](#apply-the-four-golden-signals-framework-promql): Lines 114-159
    -   [Monitor Error Rate](#monitor-error-rate): Lines 116-127
    -   [Monitor Latency and Duration](#monitor-latency-and-duration): Lines 128-137
    -   [Monitor Traffic and Throughput](#monitor-traffic-and-throughput): Lines 138-147
    -   [Monitor Saturation and Utilization](#monitor-saturation-and-utilization): Lines 148-159
3.  [Apply Terraform Configuration Templates (PromQL)](#apply-terraform-configuration-templates-promql): Lines 160-242
    -   [Use Template A for PromQL-Based Alert Policies (Recommended)](#use-template-a-for-promql-based-alert-policies-recommended): Lines 162-197
    -   [Use Template B for Legacy Threshold-Based Alert Policies (Fallback)](#use-template-b-for-legacy-threshold-based-alert-policies-fallback): Lines 198-242
4.  [Configure Cloud Logging Log-Based Metric Alerts](#configure-cloud-logging-log-based-metric-alerts): Lines 243-313
5.  [Delegate SLOs and Apply the Fallback Rule](#delegate-slos-and-apply-the-fallback-rule): Lines 314-378
6.  [Validate PromQL Syntax and Metric Schemas](#validate-promql-syntax-and-metric-schemas): Lines 379-403
7.  [Review and Deduplicate HCL Configurations](#review-and-deduplicate-hcl-configurations): Lines 404-412
8.  [Follow Best Practices and Validation Rules](#follow-best-practices-and-validation-rules): Lines 413-444

---

## Discover and Select Metrics

Before configuring alerts for an unfamiliar or generic Google Cloud resource, discover
its available metrics, metric types, units, and label enum values:

1.  **Run Universal Schema & Metric Discovery (`discover_metric_schema.py`)**:
    Run the schema discovery script to automatically inspect
    `monitoredResourceDescriptors` and `metricDescriptors` through the Cloud
    Monitoring v3 API. This script outputs exact PromQL metric names (including
    `_bucket` suffixes for distributions), unit scaling warnings (for example,
    microseconds `us` versus milliseconds `ms`), grouping keys (`sum by (...)`), and
    documented label enum values (for example, `response_class="success"`):

    ```bash
    python3 scripts/discover_metric_schema.py \
        --project="<project_id>" \
        --resource-type="<monitored_resource_type>" \
        --metric-prefix="<metric_prefix_or_domain>"
    ```

2.  **List Metric Descriptors with the `gcloud` CLI**:

    ```bash
    gcloud monitoring metric-descriptors list \
        --filter="resource.type=\"<monitored_resource_type>\""
    ```

3.  **Map to PromQL**: Cloud Monitoring automatically translates Google
    Cloud metric types (`<domain>/<path>`) into Prometheus format by replacing
    dots (`.`) with underscores (`_`), replacing the **first slash (`/`) after
    the domain with a colon (`:`)**, and replacing remaining slashes with
    underscores (`_`). For example,
    `serviceruntime.googleapis.com/api/request_count` maps to
    `serviceruntime_googleapis_com:api_request_count` (append `_bucket` for
    distributions). Always verify `.unit` (`us` versus `ms`) and documented label
    values before writing thresholds or label matchers.

---

## Apply the Four Golden Signals Framework (PromQL)

### Monitor Error Rate

Monitor the ratio of failed requests or error status codes over total requests.

*   **PromQL Query**:

    ```promql
    sum by (service) (rate(serviceruntime_googleapis_com:api_request_count{response_code_class="5xx"}[5m]))
    /
    sum by (service) (rate(serviceruntime_googleapis_com:api_request_count[5m])) > 0.01
    ```

### Monitor Latency and Duration

Monitor 95th or 99th percentile request duration.

*   **PromQL Query**:

    ```promql
    histogram_quantile(0.95, sum by (service, le) (rate(serviceruntime_googleapis_com:api_request_latencies_bucket[5m]))) > 2000
    ```

### Monitor Traffic and Throughput

Monitor total request volume or transaction rate.

*   **PromQL Query**:

    ```promql
    sum by (service) (rate(serviceruntime_googleapis_com:api_request_count[5m]))
    ```

### Monitor Saturation and Utilization

Monitor CPU, memory, or resource capacity utilization percentage.

*   **PromQL Query**:

    ```promql
    avg(rate(container_cpu_usage_seconds_total[5m])) by (instance) > 0.85
    ```

---

## Apply Terraform Configuration Templates (PromQL)

### Use Template A for PromQL-Based Alert Policies (Recommended)

This is the standard alerting pattern used across Cloud Run, GKE, and Agent
Platform in this skill.

```terraform
resource "google_monitoring_alert_policy" "generic_promql_error_rate" {
  display_name = "Generic High Error Rate (PromQL)"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Error rate exceeds 1% over 5m"

    condition_prometheus_query_language {
      query    = <<-EOT
        sum by (service) (rate(serviceruntime_googleapis_com:api_request_count{response_code_class="5xx"}[5m]))
        /
        sum by (service) (rate(serviceruntime_googleapis_com:api_request_count[5m])) > 0.01
      EOT
      duration = "300s"
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }

  user_labels = {
    "created-with-google-skill" = "cloud-monitoring-alert-configuration"
    "alert-category"          = "reliability"
    "query-language"          = "promql"
  }
}
```

### Use Template B for Legacy Threshold-Based Alert Policies (Fallback)

Use this only if PromQL is unsupported for the specific metric backend.

```terraform
resource "google_monitoring_alert_policy" "generic_threshold_error_rate" {
  display_name = "Generic High Error Rate (Threshold)"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Error count exceeds threshold"

    condition_threshold {
      filter          = "metric.type=\"serviceruntime.googleapis.com/api/request_count\" resource.type=\"global\" metric.label.response_code_class=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.project_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }

  user_labels = {
    "created-with-google-skill" = "cloud-monitoring-alert-configuration"
    "alert-category"          = "reliability"
  }
}
```

---

## Configure Cloud Logging Log-Based Metric Alerts

For applications or services that output text or structured logs rather than
native metrics, configure Cloud Logging log-based metrics (`google_logging_metric`)
and alert on them using Cloud Monitoring.

### Define a Cloud Logging Log-Based Metric (`google_logging_metric`)

Extracts a counter or distribution metric from log entries matching a filter
(for example, application crashes or unhandled exceptions).

```terraform
resource "google_logging_metric" "app_error_log_metric" {
  name        = "app-error-log-count"
  project     = var.project_id
  description = "Count of application error log entries"
  filter      = "resource.type=\"global\" severity>=ERROR"

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "Application Error Log Count"
  }
}
```

### Create an Alert Policy on a Cloud Logging Log-Based Metric

Create an alert policy tracking the Cloud Logging log-based metric using threshold conditions:

```terraform
resource "google_monitoring_alert_policy" "log_metric_alert" {
  display_name = "High Application Error Log Rate"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Error log rate exceeds threshold"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.app_error_log_metric.name}\" resource.type=\"global\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }

  user_labels = {
    "created-with-google-skill" = "cloud-monitoring-alert-configuration"
    "alert-category"          = "reliability"
  }
}
```

---

## Delegate SLOs and Apply the Fallback Rule

**Availability, latency, and throughput SLOs are owned by the
`google-cloud-slo-alert-configuration` skill.** Delegate to it whenever the user
asks for an SLO, an error budget, or burn-rate alerting on a generic resource.
That skill owns the SLO wizard, the burn-rate templates
(`references/promql_templates.md`), the SLI mapping
(`references/service_metrics.md`), and the App Hub scoping labels
(`references/app_hub_labels.md`).

Never emit a single static threshold or a bare error ratio as an "SLO". Unlike
the Cloud Run and GKE references, generic resources have **no documented default
SLI**, so this reference **must** resolve the SLI first and hand that context
over.

**Context to hand off** (so the SLO skill does not repeat discovery):

*   **Resource type**: the monitored resource type you confirmed with discovery.
*   **Grouping labels**: the resource identity labels returned by discovery (the
    `sum by (...)` clause).
*   **SLI**: the discovered metric name, its good/bad filter, and its unit.
*   **SLO target**: the user's target, or `0.999` (99.9%) if they did not give
    one.

### Discover the Exact SLI Metric and Hand It to the SLO Skill

Generic resources (Cloud SQL, Spanner, Memorystore, Pub/Sub, custom pipelines)
rarely have a documented default SLI. Run the schema discovery script and
include the exact command in your response:

```bash
python3 scripts/discover_metric_schema.py \
    --project="<project_id>" \
    --resource-type="<monitored_resource_type>" \
    --metric-prefix="<metric_prefix_or_domain>"
```

Use its output to resolve the four things a burn-rate query cannot be written
without:

| Discovery Output | Why the SLO Needs It |
| :--- | :--- |
| Exact PromQL metric name | `{GOOD_METRIC}` / `{BAD_METRIC}` / `{TOTAL_METRIC}` substitution (for example, `serviceruntime_googleapis_com:api_request_count`) |
| `_bucket` distribution series | Latency SLIs need the `_bucket` series for `histogram_fraction` / `histogram_quantile` |
| Unit (`us`, `ms`, or `s`) | A 500 ms target is `500` for `ms` metrics but `500000` for `us` metrics (`us` versus `ms`) — the wrong unit silently produces an alert that never fires |
| Documented label enum values | The failure filter must use real values (for example, `response_class="success"` or `response_code_class="5xx"`); an invalid enum yields an always-empty series |
| Resource grouping labels | The `sum by (...)` clause that keeps the burn rate per-service instead of fleet-averaged |

Hand the resolved SLI to `google-cloud-slo-alert-configuration` as the
`ServiceLevelIndicator` input, along with the SLO target and window if the user
supplied them.

**Fallback** — only if `google-cloud-slo-alert-configuration` is not installed:
this reference intentionally carries **no** burn-rate templates. Say that SLO
alerting requires that skill, report the SLI you discovered, and continue with
the non-SLO golden-signal policies. Never silently present SLO policies as if
this skill owned them.

> [!IMPORTANT] Your response MUST say, in plain text, that you will **not invent
> or guess a metric name** and that you will **ask the user for the custom
> metric name and failure filter** if schema discovery does not resolve one. Say
> this even when you believe you have identified the right metric — the SLO is
> only as correct as the SLI it is built on, and a guessed metric silently
> produces an alert that never fires.

## Validate PromQL Syntax and Metric Schemas

When fixing, validating, or generating PromQL alert queries (such as diagnosing
and fixing unbalanced parentheses or invalid time windows), **never search the
workspace or directory tree for a query file if no file path was
provided**. If the user describes a syntax error (such as unbalanced
parentheses) without pasting the query, demonstrate the fix using a concrete
before-and-after example (for example, fixing missing closing parenthesis in
`sum by (service) (rate(serviceruntime_googleapis_com:api_request_count{response_code_class="5xx"}[5m]) > 0.01`
to
`sum by (service) (rate(serviceruntime_googleapis_com:api_request_count{response_code_class="5xx"}[5m])) > 0.01`).
Always run or print both the static syntax linter (`lint_promql.py`) and the
schema-aware validator (`discover_metric_schema.py`), and include the exact
commands in your response:

```bash
# 1. Static PromQL syntax & bracket/window validation
python3 scripts/lint_promql.py "<promql_expression>"

# 2. Live Google Cloud schema, metric existence, unit scaling ('us' versus 'ms'), & label enum validation
python3 scripts/discover_metric_schema.py \
    --project="<project_id>" \
    --promql '<promql_expression>'
```

## Review and Deduplicate HCL Configurations

When adding new alerts to `monitoring/alerts.tf`, inspect existing HCL policies
(for example, using `grep` or file inspection) to prevent duplicate alert blocks, perform
in-place updates when modifying existing policies, and always prompt the user
regarding notification channel configuration.

---

## Follow Best Practices and Validation Rules

1.  **Prioritize PromQL & Note MQL Deprecation**: Always use
    `condition_prometheus_query_language` where supported to maintain
    consistency with Cloud Run, GKE, and Agent Platform alert definitions. If a
    user requests an MQL policy, explicitly note that **MQL is deprecated in
    favor of PromQL** and provide PromQL instead.
2.  **Cover Golden Signals (Error Rate + Saturation/Latency)**: When configuring
    production alerts for any generic or unsupported resource (such as Cloud
    SQL, Spanner, Memorystore Redis, or custom workloads), always provide
    alert policies covering **at least Error Rate** (or failed operations,
    evictions, or rejected connections) **and Saturation/Latency**.
3.  **Evaluation Window**: Ensure PromQL queries specify an evaluation duration
    of at least `300s` (5 minutes) to avoid flapping.
4.  **SLOs**: Delegate dedicated Service Level Objective tracking and error
    budget burn-rate alerting to the `google-cloud-slo-alert-configuration`
    skill, handing off the SLI metric resolved by schema discovery (see
    [Delegate SLOs and Apply the Fallback Rule](#delegate-slos-and-apply-the-fallback-rule)).
5.  **Notification Channels**: Attach notification channels using the
    `cloud-monitoring-notification-channels-configuration` skill. **Always
    prompt the user to ask if they would like to configure notification channels
    if none were provided.**
6.  **Run & Include CLI Commands for Reproducibility**: Always run the `python3
    scripts/discover_metric_schema.py`, `gcloud monitoring metric-descriptors
    list`, and `python3 scripts/lint_promql.py "<promql_expression>"` commands
    to discover schemas and validate PromQL expressions, and include the exact
    commands in your response so users can reproduce your validation.
7.  **Fleet-Wide Aggregation (`sum by` / `group_by_fields`)**: For fleet-wide
    scaling or multi-instance alerts, **always** include explicit grouping: use
    `sum by (service, instance_id)` (or `sum by (service)`) in PromQL queries,
    or `aggregations { group_by_fields = [...] }` in threshold queries — never
    use ungrouped scalar `sum(...)`.
