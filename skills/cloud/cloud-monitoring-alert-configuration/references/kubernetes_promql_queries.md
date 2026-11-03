# Write PromQL Queries for Kubernetes Alerting

This document provides best-practice PromQL queries for monitoring Kubernetes
clusters and services, organized by the Golden Signals and key Cluster Health
metrics.

All queries are designed to be used with **Google Cloud Managed Service for
Prometheus (GMP)** and can be deployed through Cloud Monitoring alerting
policies using `condition_prometheus_query_language`.

# Table of Contents

- [Enforce Mandatory Kubernetes and GKE Alerting Guardrails](#enforce-mandatory-kubernetes-and-gke-alerting-guardrails): Lines 32-133
- [Alert on Latency](#alert-on-latency): Lines 134-177
  - [Query Standard Prometheus HTTP Latency Metrics](#query-standard-prometheus-http-latency-metrics): Lines 139-153
  - [Query OpenTelemetry HTTP Latency Metrics](#query-opentelemetry-http-latency-metrics): Lines 154-177
- [Alert on Traffic Rate and Outages](#alert-on-traffic-rate-and-outages): Lines 178-250
  - [Query Request Rate](#query-request-rate): Lines 183-195
  - [Detect Traffic Drops and Outages](#detect-traffic-drops-and-outages): Lines 196-250
  - [Compare Historical Traffic Using Default Zero](#compare-historical-traffic-using-default-zero): Lines 207-235
  - [Detect Missing Series Using Absent](#detect-missing-series-using-absent): Lines 236-250
- [Alert on Multi Window Multi Burn Rate SLO Errors](#alert-on-multi-window-multi-burn-rate-slo-errors): Lines 251-481
  - [Configure a Fast Burn Rate Alert](#configure-a-fast-burn-rate-alert): Lines 315-370
  - [Configure a Medium Burn Rate Alert](#configure-a-medium-burn-rate-alert): Lines 371-424
  - [Configure a Slow Burn Rate Alert](#configure-a-slow-burn-rate-alert): Lines 425-481
- [Alert on Memory Saturation](#alert-on-memory-saturation): Lines 482-522
  - [Calculate Memory Utilization Against Limits](#calculate-memory-utilization-against-limits): Lines 491-522
- [Monitor Cluster Health and Infrastructure](#monitor-cluster-health-and-infrastructure): Lines 523-562
  - [Alert on Pod CrashLooping and Container Restarts](#alert-on-pod-crashlooping-and-container-restarts): Lines 527-547
  - [Alert on Unready Kubernetes Nodes](#alert-on-unready-kubernetes-nodes): Lines 548-562

## Enforce Mandatory Kubernetes and GKE Alerting Guardrails

For all Kubernetes and GKE requests, read the relevant
`references/kubernetes_*.md` files and respond directly. Do not search the
workspace for additional files before answering. **Do NOT search the codebase
for external Terraform modules or extra reference files, and do NOT write `.tf`
files to disk unless the user explicitly specifies a target file path.** When
configuring Kubernetes alerts, you MUST:

1.  **Mandatory KSM Permission Guardrail (Tier 2 `kube_*` metrics)**: If the
    requested alert uses `kube-state-metrics (KSM)` metrics
    (`kube_deployment_*`, `kube_statefulset_*`, `kube_daemonset_*`,
    `kube_cronjob_*`, `kube_job_*`, `kube_persistentvolume_*`,
    `kube_pod_status_phase`, `kube_pod_container_resource_limits`), you **MUST
    NOT assume KSM is enabled or write or apply any Terraform files** (see
    [kubernetes_metrics_and_alerts_catalog.md](kubernetes_metrics_and_alerts_catalog.md)).
    At the very top of your response, you MUST: (a) alert the user that the
    policy requires `kube-state-metrics (KSM)`, (b) explain that KSM incurs
    billable Managed Service for Prometheus (GMP) sample ingestion costs (see
    [Cloud Monitoring pricing](https://docs.cloud.google.com/stackdriver/pricing.md.txt)),
    (c) **ask the user a direct question in second-person asking for explicit
    permission** (literally include: **"Do you grant explicit permission to
    enable and ingest kube-state-metrics (KSM) in your cluster for this
    alert?"** — never phrase this as a passive statement such as "ensure you
    have approved KSM"), and (d) recommend a filtered `PodMonitoring` allowlist
    (`metricRelabeling` with `action: keep`) that keeps only the required
    metrics (along with any conditional draft HCL clearly marked as pending
    approval).
2.  **Tier 1 Native Metrics (Zero KSM Surcharge)**: For native cAdvisor,
    Kubelet, or Control Plane metrics (`container_memory_working_set_bytes`,
    `container_spec_memory_limit_bytes`,
    `kube_pod_container_status_restarts_total`,
    `kubernetes.io/container/restart_count`, `kube_node_status_condition`,
    `kubelet_volume_stats_available_bytes`, `apiserver_*`, `rest_client_*`),
    explicitly state that the metric is a **Tier 1 native/standard metric with
    zero KSM cost surcharge** (a **Tier 1 Kubelet/cAdvisor metric that does not
    require kube-state-metrics** or a **Tier 1 Control Plane metric with zero
    KSM cost surcharge**), explain that container resource limits
    (`resources.limits`) must be defined in pod specs for saturation alerts to
    resolve, and provide a clear plain-English explanation of the alert and
    thresholds.
3.  **Mandatory Terraform Variables (`project_id`, `cluster_name`, `namespace`)
    and `user_labels`**: In EVERY Kubernetes Terraform HCL configuration
    (including cluster-wide and multi-service latency and SLO alerts), you
    **MUST** define `variable "project_id"`, `variable "cluster_name"`, and
    `variable "namespace"` blocks, interpolate all three (`var.project_id`,
    `${var.cluster_name}`, `${var.namespace}`), and include `user_labels = {
    "created-with-google-skill" = "cloud-monitoring-alert-configuration" }` in
    every `google_monitoring_alert_policy` resource:

```hcl
variable "project_id" {
  type    = string
  default = "my-gcp-project"
}

variable "cluster_name" {
  type    = string
  default = "my-gke-cluster"
}

variable "namespace" {
  type    = string
  default = "default"
}

variable "slo_target" {
  type    = number
  default = 0.99
}

resource "google_monitoring_alert_policy" "k8s_alert_example" {
  project      = var.project_id
  display_name = "[K8s] ${var.cluster_name} - Example Alert"
  combiner     = "OR"

  conditions {
    display_name = "PromQL Condition"
    condition_prometheus_query_language {
      query                     = <<-EOT
        # Insert PromQL query filtering by cluster="${var.cluster_name}" and namespace="${var.namespace}"
      EOT
      duration                  = "300s"
      disable_metric_validation = true
    }
  }

  user_labels = {
    "created-with-google-skill" = "cloud-monitoring-alert-configuration"
  }
}
```

4.  **Validate Kubernetes HCL and PromQL Configurations**: When validating or
    deduplicating existing Kubernetes `.tf` files on disk, run `python3
    scripts/kubernetes/validate_config.py --file <path_to_tf_file>` (for a
    single file) or `python3 scripts/kubernetes/validate_config.py --directory
    <path_to_tf_dir>` (to check a directory for PromQL syntax errors, missing
    Kubernetes resource labels, and duplicate signal targets).

---

## Alert on Latency

Monitors the 95th percentile (P95) of HTTP request duration to detect slow
responses.

### Query Standard Prometheus HTTP Latency Metrics

```promql
histogram_quantile(0.95,
  sum(
    rate(
      http_request_duration_seconds_bucket{
        cluster="${var.cluster_name}",
        namespace="${var.namespace}"
      }[5m]
    )
  ) by (le, service, ingress)
) > 2.0
```

### Query OpenTelemetry HTTP Latency Metrics

If your application is instrumented with OpenTelemetry, it might use
`http_server_request_duration_milliseconds`:

```promql
histogram_quantile(0.95,
  sum(
    rate(
      http_server_request_duration_milliseconds_bucket{
        cluster="${var.cluster_name}",
        namespace="${var.namespace}"
      }[5m]
    )
  ) by (le, service)
) > 2000
```

*   **Threshold**: `2.0` seconds (or `2000` ms). Adjust based on latency target.
*   **Buffer**: Use `duration = "300s"` in the alert policy for instantaneous
    percentiles or `duration = "0s"` when multi-window smoothing is applied.

---

## Alert on Traffic Rate and Outages

Monitors the volume of requests to detect sudden drops (indicating outage) or
overload spikes.

### Query Request Rate

```promql
sum(
  rate(
    http_requests_total{
      cluster="${var.cluster_name}",
      namespace="${var.namespace}"
    }[5m]
  )
) by (service)
```

### Detect Traffic Drops and Outages

> [!WARNING] **The `== 0` Metric Disappearance Gotcha**: When a service
> experiences a total traffic outage, HTTP requests stop entirely and Prometheus
> stops emitting the `http_requests_total` metric series. Evaluating
> `rate(...) == 0` returns an **empty vector** (no data) rather than a `0`
> value, so the alert will **fail to fire**.

To reliably detect a complete traffic loss, use **`default 0`** or
**`absent()`**:

#### Compare Historical Traffic Using Default Zero

Fires if current 5m traffic is zero when historical traffic 1 week ago was
active (> 1 QPS):

```promql
(
  sum(
    rate(
      http_requests_total{
        cluster="${var.cluster_name}",
        namespace="${var.namespace}"
      }[5m]
    )
  ) by (service) default 0
) == 0
and
(
  sum(
    rate(
      http_requests_total{
        cluster="${var.cluster_name}",
        namespace="${var.namespace}"
      }[5m] offset 1w
    )
  ) by (service)
) > 1
```

#### Detect Missing Series Using Absent

Fires if the metric series is completely absent:

```promql
absent(
  http_requests_total{
    cluster="${var.cluster_name}",
    namespace="${var.namespace}"
  }
) == 1
```

---

## Alert on Multi Window Multi Burn Rate SLO Errors

Monitors service reliability against defined Service Level Objectives (SLOs)
using **Multi-Window Multi-Burn-Rate (MWMBR)** alerts.

**Service availability and latency SLOs are owned by the
`google-cloud-slo-alert-configuration` skill.** Delegate to it whenever the user
asks for an SLO, an error budget, or burn-rate alerting on a GKE service. That
skill owns the SLO wizard, the burn-rate templates
(`references/promql_templates.md`), the SLI mapping
(`references/service_metrics.md`), and the App Hub scoping labels
(`references/app_hub_labels.md`).

**Context to hand off** (so the SLO skill does not repeat discovery):

*   **Resource type**: GKE service (`prometheus_target` / App Hub service).
*   **Grouping labels**: `cluster`, `namespace`, `service`.
*   **Availability SLI**: the request metric the workload actually emits — see
    the table below.
*   **SLO target**: the user's target, or `0.999` (99.9%) if they did not give
    one.

**Resolve the SLI source before delegating.** GKE has no single default
availability SLI — which metric exists depends on how the workload is
instrumented:

| SLI source | Metric | When it applies |
| :--- | :--- | :--- |
| App Hub registered service | `service:server_request_count` | Service is registered in an App Hub application |
| OTLP or Prometheus sidecar | `http_requests_total` | Workload exports its own HTTP request counter |
| Istio or Anthos Service Mesh | `istio_requests_total` | Mesh-managed traffic |

> [!IMPORTANT] If you cannot determine which of these the cluster emits, you
> MUST **ask the user which request metric their services expose** and say so
> explicitly in your response. Do not silently assume one.

**Fallback** — only if `google-cloud-slo-alert-configuration` is not installed:
use the burn-rate queries below, which are a complete solution on their own.
Even then, your response MUST name `google-cloud-slo-alert-configuration` as the
owner of SLO configuration, state that what you emitted is a local fallback, and
list the handoff context above. Never silently present SLO policies as if this
skill owned them.

> [!NOTE] **Why SLO Burn Rates over Simple Ratios?** Simple static error ratios
> (such as `rate(5xx)/rate(total) > 5%`) cause severe alert fatigue during
> low-traffic periods (where 1 error out of 2 requests = 50%) and fail to detect
> slow, steady error budget drains. Multi-window burn rates evaluate both a
> short-term window (to ensure the outage is currently active) and a long-term
> window (to ensure significant error budget consumption).

The threshold formula is: \[ \text{Threshold} = (1 - \text{SLO\_TARGET}) \times
\text{BURN\_RATE\_FACTOR} \]

> [!WARNING] **Do not mix up the tiers.** When you emit the standard two-policy
> burn-rate pair, it is **Fast Burn** (factor `14.4`, `1h` and `5m`) plus
> **Slow Burn** (factor `1.0`, `3d` and `6h`). **Medium Burn** (factor `6.0`,
> `6h` and `30m`) is an optional third tier — never substitute it for Slow Burn
> and never label a `6.0` / `6h` and `30m` policy "Slow Burn".

> [!IMPORTANT] **Parameterize the SLO target.** Generated Terraform MUST declare
> a `variable "slo_target"` and substitute `(1 - var.slo_target)` (or `(1 -
> ${var.slo_target})` inside a heredoc) in every burn-rate threshold. Never
> hardcode the error budget in the emitted PromQL.

### Configure a Fast Burn Rate Alert

*   **Burn Rate Factor**: `14.4` (Consumes 2% of a 30-day error budget in 1
    hour)
*   **Windows**: Long window = `1h`, Short window = `5m`
*   **Duration**: `0s` (the dual lookback windows already smooth transient
    spikes)

```promql
(
  (
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}",
          status=~"5.."
        }[5m]
      )
    ) by (service)
    /
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}"
        }[5m]
      )
    ) by (service)
  ) > (1 - ${var.slo_target}) * 14.4
)
and
(
  (
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}",
          status=~"5.."
        }[1h]
      )
    ) by (service)
    /
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}"
        }[1h]
      )
    ) by (service)
  ) > (1 - ${var.slo_target}) * 14.4
)
```

### Configure a Medium Burn Rate Alert

*   **Burn Rate Factor**: `6.0` (Consumes 5% of error budget in 6 hours)
*   **Windows**: Long window = `6h`, Short window = `30m`
*   **Duration**: `0s`

```promql
(
  (
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}",
          status=~"5.."
        }[30m]
      )
    ) by (service)
    /
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}"
        }[30m]
      )
    ) by (service)
  ) > (1 - ${var.slo_target}) * 6.0
)
and
(
  (
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}",
          status=~"5.."
        }[6h]
      )
    ) by (service)
    /
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}"
        }[6h]
      )
    ) by (service)
  ) > (1 - ${var.slo_target}) * 6.0
)
```

### Configure a Slow Burn Rate Alert

*   **Burn Rate Factor**: `1.0` (Consumes 10% of error budget in 3 days)
*   **Windows**: Long window = `3d`, Short window = `6h`
*   **Duration**: Omit the `duration` field entirely (Cloud Monitoring rejects a
    retest buffer when the lookback window exceeds 25 hours).

```promql
(
  (
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}",
          status=~"5.."
        }[6h]
      )
    ) by (service)
    /
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}"
        }[6h]
      )
    ) by (service)
  ) > (1 - ${var.slo_target}) * 1.0
)
and
(
  (
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}",
          status=~"5.."
        }[3d]
      )
    ) by (service)
    /
    sum(
      rate(
        http_requests_total{
          cluster="${var.cluster_name}",
          namespace="${var.namespace}"
        }[3d]
      )
    ) by (service)
  ) > (1 - ${var.slo_target}) * 1.0
)
```

---

## Alert on Memory Saturation

In Kubernetes, CPU is compressible and throttled by CFS quotas rather than
causing container termination. Memory saturation, however, is uncompressible and
directly causes Out-Of-Memory (`OOMKilled`) pod terminations. Therefore,
Kubernetes cluster saturation alerting focuses on **Memory Saturation**. (CPU
saturation alerts and `container_cpu_usage_seconds_total` are not recommended
for cluster alert policies).

### Calculate Memory Utilization Against Limits

Uses `container_memory_working_set_bytes` (active memory plus unevictable
caches) compared to the configured limit `container_spec_memory_limit_bytes`:

```promql
sum(
  container_memory_working_set_bytes{
    cluster="${var.cluster_name}",
    namespace="${var.namespace}",
    container!=""
  }
) by (pod, container)
/
sum(
  container_spec_memory_limit_bytes{
    cluster="${var.cluster_name}",
    namespace="${var.namespace}",
    container!=""
  }
) by (pod, container) > 0.9
```

*   **Cost Tier**: Tier 1 Kubelet/cAdvisor metric that does not require
    kube-state-metrics (Zero KSM cost).
*   **Buffer**: `duration = "300s"` to allow short-lived memory spikes.
*   **Prerequisite**: Workload pod specs MUST configure explicit memory limits
    (`resources.limits.memory`) or this query will return `NaN` and fail to
    resolve.

---

## Monitor Cluster Health and Infrastructure

Critical infrastructure alerts that impact service reliability.

### Alert on Pod CrashLooping and Container Restarts

Alerts if a pod is restarting frequently, indicating crash loops (such as
OOMKilled events, panics, or configuration errors).

```promql
sum(
  increase(
    kube_pod_container_status_restarts_total{
      cluster="${var.cluster_name}",
      namespace="${var.namespace}"
    }[15m]
  )
) by (pod, container) > 3
```

*   **Duration**: Set Terraform `duration = "0s"` (or `"60s"`).
    *   **Crucial Rule**: The `[15m]` lookback window already smooths out
        spikes. Adding a `300s` duration causes a 20-minute delay before
        critical crashloop alerts fire.

### Alert on Unready Kubernetes Nodes

Alerts if a Kubernetes node enters an unhealthy state.

```promql
kube_node_status_condition{
  cluster="${var.cluster_name}",
  condition="Ready",
  status="true"
} == 0
```

*   **Trigger**: When the value is `0`, the node is NotReady.
*   **Buffer**: Use `duration = "300s"` to account for transient network blips
    or node drainage during GKE node pool upgrades.
