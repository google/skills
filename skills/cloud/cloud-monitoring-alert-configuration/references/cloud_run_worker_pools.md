# Configure Cloud Run Worker Pool Alerts

Best-practice observability for Cloud Run Worker Pools.

## Table of Contents

* [Apply Fast-Path Defaults](#apply-fast-path-defaults): Lines 21-33
* [Apply Default Constants and Override Parameters](#apply-default-constants-and-override-parameters): Lines 34-47
* [Delegate SLOs and Apply Fallback Templates](#delegate-slos-and-apply-fallback-templates): Lines 48-85
* [Discover Workload Targets](#discover-workload-targets): Lines 86-98
  * [Discover Parameters Autonomously](#discover-parameters-autonomously): Lines 88-98
* [Apply PromQL and Terraform Query Templates](#apply-promql-and-terraform-query-templates): Lines 99-280
  * [Configure Task Success Rate SLO Burn Rate Queries](#configure-task-success-rate-slo-burn-rate-queries): Lines 101-160
  * [Monitor Queue Backlog Drain Time (ETD)](#monitor-queue-backlog-drain-time-etd): Lines 161-230
  * [Monitor Oldest Unacked Message Age](#monitor-oldest-unacked-message-age): Lines 231-238
  * [Configure Health Probe Success Rate SLO Burn Rate Queries](#configure-health-probe-success-rate-slo-burn-rate-queries): Lines 239-280
* [Map Telemetry Data Sources](#map-telemetry-data-sources): Lines 281-288

---

## Apply Fast-Path Defaults
When standard alerting is requested or thresholds are unspecified, **always generate the following 4-policy standard suite**. Delegate the Task Success Rate SLO burn-rate policies (Policies 1–2) to the `google-cloud-slo-alert-configuration` skill when it is installed; generate Policies 1–2 from the local fallback templates in this file only when `google-cloud-slo-alert-configuration` is unavailable (while still surfacing the referral to `google-cloud-slo-alert-configuration` as described in [Delegate SLOs and Apply Fallback Templates](#delegate-slos-and-apply-fallback-templates)):

1. **Task Success Rate SLO (Fast Burn)**: 99.9% target, 1h & 5m windows, $14.4\times$ burn rate, `duration = "300s"` (Critical/Paging).
2. **Task Success Rate SLO (Slow Burn)**: 99.9% target, 3d & 6h windows, $1.0\times$ burn rate, **omit `duration`** (Warning/Ticket).
3. **Queue Backlog Drain Time (ETD)**: Estimated time to drain queue exceeds processing SLA threshold (for example, >30m) with `duration = "300s"` retest buffer (Warning/Paging).
4. **Oldest Unacked Message Age**: Oldest unacknowledged message age exceeds SLA threshold (Critical/Paging).

> [!NOTE]
> Unlike HTTP Services (where container saturation directly causes HTTP 504 errors), Worker Pools operating at `max_instances` are operating at maximum efficiency. As long as Queue Drain Time (ETD) and Message Age remain within SLA, instance saturation is expected and does not trigger alerts.

---

## Apply Default Constants and Override Parameters

All generated Terraform alert policies use explicit default constants. Override any parameter using HCL variables or prompt instructions:

| Constant / Parameter | Explicit Default | HCL Variable Name | Description & Override Option |
| :--- | :--- | :--- | :--- |
| `task_success_slo_target` | `0.999` (99.9%) | `var.task_success_slo_target` | Task processing success rate target. Override to 0.99 or 0.9999. |
| `health_probe_slo_target` | `0.999` (99.9%) | `var.health_probe_slo_target` | Process health probe attempt success target. |
| `max_drain_time_second` | `1800` (30m) | `var.max_drain_time_second` | Maximum allowed Queue Estimated Time to Drain (ETD) SLA. |
| `oldest_message_age_second`| `1800` (30m) | `var.oldest_message_age_second`| Maximum allowed unacknowledged message age SLA. |
| `retest_duration_buffer` | `"300s"` (5m) | `var.retest_duration_buffer` | Retest window for lookbacks $\le 25$h. Omitted for lookbacks $>25$h. |

---

## Delegate SLOs and Apply Fallback Templates

**Task success rate and health probe SLOs are owned by the
`google-cloud-slo-alert-configuration` skill.** Delegate to it whenever the user
asks for an SLO, an error budget, or burn-rate alerting on a worker pool. That
skill owns the SLO wizard, the burn-rate templates
(`references/promql_templates.md`), the SLI mapping
(`references/service_metrics.md`), and the App Hub scoping labels
(`references/app_hub_labels.md`).

**Context to hand off** (so the SLO skill does not repeat discovery):

*   **Resource type**: Cloud Run worker pool (plus the bound Pub/Sub
    subscription, if any).
*   **Grouping labels**: `subscription_id` for queue SLIs; `service_name`,
    `location` for probe SLIs.
*   **Task success SLI**: bad =
    `pubsub_googleapis_com:subscription_nack_requests`, total = nacks +
    `pubsub_googleapis_com:subscription_ack_message_count`.
*   **Health probe SLI**: bad = failed attempts of
    `run_googleapis_com:container_completed_probe_attempt_count`, total = all
    attempts.
*   **SLO target**: `task_success_slo_target` / `health_probe_slo_target`
    (default `0.999`).

Delegate the SLO policies and continue generating the queue-health policies
(Backlog Drain Time / ETD and Oldest Unacked Message Age) from this reference in
the same response.

**Fallback** — only if `google-cloud-slo-alert-configuration` is not installed:
use the standalone burn-rate templates in this reference, which are a complete
solution on their own. Even then, your response MUST name
`google-cloud-slo-alert-configuration` as the owner of SLO configuration, state
that what you emitted is a local fallback, and list the handoff context above.
Never silently present SLO policies as if this skill owned them.

---

## Discover Workload Targets

### Discover Parameters Autonomously
Before proposing alerts, discover worker pool telemetry and queue bindings:

* **Queue Integration (Direct API & Config Scan)**:
  1. **Worker Pool API**: Run `gcloud beta run worker-pools describe [NAME] --format="json"` to inspect container environment variables (`spec.template.spec.containers[].env`) for `PUBSUB_SUBSCRIPTION`, `SUBSCRIPTION_ID`, or `TOPIC_ID`.
  2. **Service Account IAM Binding**: Extract `serviceAccountName` from the worker pool description and run `gcloud pubsub subscriptions list --format="json"` to verify which subscriptions grant `roles/pubsub.subscriber` to that service account.
  3. **Terraform Scan**: Search `.tf` files for `google_pubsub_subscription` resources associated with the worker pool module.
  * *Outcome*: If a Pub/Sub subscription is identified, apply Task Success SLOs, Backlog Drain Time (ETD), and Message Age alerts. If no queue is bound, apply Health Probe Success Rate SLOs.

---

## Apply PromQL and Terraform Query Templates

### Configure Task Success Rate SLO Burn Rate Queries

#### Configure Task Success Fast Burn (1h and 5m Windows)

```promql
(
  (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[5m])) or vector(0))
  /
  (
    (sum(rate(pubsub_googleapis_com:subscription_ack_message_count{subscription_id="[SUBSCRIPTION_ID]"}[5m])) or vector(0))
    +
    (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[5m])) or vector(0))
    + 0.001
  )
  > (1 - [SLO_TARGET]) * 14.4
)
and
(
  (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[1h])) or vector(0))
  /
  (
    (sum(rate(pubsub_googleapis_com:subscription_ack_message_count{subscription_id="[SUBSCRIPTION_ID]"}[1h])) or vector(0))
    +
    (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[1h])) or vector(0))
    + 0.001
  )
  > (1 - [SLO_TARGET]) * 14.4
)
```

#### Configure Task Success Slow Burn (3d and 6h Windows)
> [!WARNING]
> Lookback windows >25h (like `[3d]`) require **omitting `duration`** in HCL.

```promql
(
  (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[6h])) or vector(0))
  /
  (
    (sum(rate(pubsub_googleapis_com:subscription_ack_message_count{subscription_id="[SUBSCRIPTION_ID]"}[6h])) or vector(0))
    +
    (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[6h])) or vector(0))
    + 0.001
  )
  > (1 - [SLO_TARGET]) * 1.0
)
and
(
  (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[3d])) or vector(0))
  /
  (
    (sum(rate(pubsub_googleapis_com:subscription_ack_message_count{subscription_id="[SUBSCRIPTION_ID]"}[3d])) or vector(0))
    +
    (sum(rate(pubsub_googleapis_com:subscription_nack_requests{subscription_id="[SUBSCRIPTION_ID]"}[3d])) or vector(0))
    + 0.001
  )
  > (1 - [SLO_TARGET]) * 1.0
)
```

### Monitor Queue Backlog Drain Time (ETD)
Monitors estimated queue drain processing time in seconds.
> [!IMPORTANT]
> PromQL conditions for ETD MUST specify `duration = "300s"` (5-minute retest buffer) in HCL. This buffer absorbs temporary ETD spikes caused by autoscaler scale-up lag during sudden bursty traffic.

#### Write the ETD PromQL Query

```promql
(
  (sum(pubsub_googleapis_com:subscription_num_undelivered_messages{subscription_id="[SUBSCRIPTION_ID]"}) or vector(0))
  /
  clamp_min((sum(rate(pubsub_googleapis_com:subscription_ack_message_count{subscription_id="[SUBSCRIPTION_ID]"}[5m])) or vector(0)), 0.05)
) > [MAX_DRAIN_TIME_SECONDS]
```

#### Define the ETD Terraform Policy

```hcl
variable "worker_pools_etd" {
  description = "Map of worker pools to subscription IDs and maximum drain time SLAs (in seconds)"
  type = map(object({
    subscription_id       = string
    max_drain_time_second = number
  }))
  default = {
    "order-processor" = {
      subscription_id       = "order-topic-sub"
      max_drain_time_second = 1800 # 30 minutes SLA
    }
  }
}

variable "retest_duration_buffer" {
  description = "Retest duration buffer for lookbacks <= 25h"
  type        = string
  default     = "300s"
}

resource "google_monitoring_alert_policy" "queue_backlog_etd" {
  for_each     = var.worker_pools_etd
  project      = var.scoping_project_id
  display_name = "[Worker Pool] Queue Backlog Estimated Time to Drain (ETD) Exceeded - ${each.key}"
  combiner     = "OR"

  conditions {
    display_name = "Estimated drain time on ${each.value.subscription_id} exceeds ${each.value.max_drain_time_second}s"
    condition_prometheus_query_language {
      query = <<-EOT
        (
          (sum(pubsub_googleapis_com:subscription_num_undelivered_messages{subscription_id="${each.value.subscription_id}"}) or vector(0))
          /
          clamp_min((sum(rate(pubsub_googleapis_com:subscription_ack_message_count{subscription_id="${each.value.subscription_id}"}[5m])) or vector(0)), 0.05)
        ) > ${each.value.max_drain_time_second}
      EOT
      duration = var.retest_duration_buffer # 5m retest buffer to absorb autoscaling scale-up lag
    }
  }

  user_labels = {
    severity                    = "warning"
    worker                      = each.key
    tier                        = "saturation"
    "created-with-google-skill" = "cloud-monitoring-alert-configuration"
  }

  alert_strategy { auto_close = "604800s" }
  notification_channels = var.notification_channels
}
```

### Monitor Oldest Unacked Message Age

```promql
(
  (pubsub_googleapis_com:subscription_oldest_unacked_message_age{subscription_id="[SUBSCRIPTION_ID]"} or vector(0))
) > [AGE_THRESHOLD_SECONDS]
```

### Configure Health Probe Success Rate SLO Burn Rate Queries

#### Configure Health Probe Fast Burn (1h and 5m Windows)

```promql
(
  (sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]", is_healthy="false"}[5m])) or vector(0))
  /
  sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]"}[5m]))
  > (1 - [SLO_TARGET]) * 14.4
)
and
(
  (sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]", is_healthy="false"}[1h])) or vector(0))
  /
  sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]"}[1h]))
  > (1 - [SLO_TARGET]) * 14.4
)
```

#### Configure Health Probe Slow Burn (3d and 6h Windows)
> [!WARNING]
> Lookback windows >25h (like `[3d]`) require **omitting `duration`** in HCL.

```promql
(
  (sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]", is_healthy="false"}[6h])) or vector(0))
  /
  sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]"}[6h]))
  > (1 - [SLO_TARGET]) * 1.0
)
and
(
  (sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]", is_healthy="false"}[3d])) or vector(0))
  /
  sum(rate(run_googleapis_com:container_completed_probe_attempt_count{monitored_resource="cloud_run_worker_pool", worker_pool_name="[WORKER_POOL_NAME]"}[3d]))
  > (1 - [SLO_TARGET]) * 1.0
)
```

---

## Map Telemetry Data Sources

| Signal Indicator | Native Metric | SRE Strategy |
| :--- | :--- | :--- |
| **Task Availability** | `pubsub.googleapis.com/subscription/nack_message_count` | **SLO Skill (`google-cloud-slo-alert-configuration`)**: Fast Burn (1h/5m) & Slow Burn (3d/6h) |
| **Process Health SLO** | `run.googleapis.com/container/completed_probe_attempt_count` | **SLO Skill (`google-cloud-slo-alert-configuration`)**: Probe Failure Ratio (`is_healthy="false"`) Fast & Slow Burn |
| **Queue Backlog ETD** | `pubsub.googleapis.com/subscription/num_undelivered_messages` & `pubsub.googleapis.com/subscription/ack_message_count` | **Estimated Time to Drain (ETD)**: Drain time > SLA threshold with `duration = "300s"` retest buffer |
| **Message Age** | `pubsub.googleapis.com/subscription/oldest_unacked_message_age` | **Threshold Alert**: Message age > SLA limit (for example, 30m) |
