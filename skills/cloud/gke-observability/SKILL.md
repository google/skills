---
name: gke-observability
description: >-
  Configures GKE observability, including Cloud Logging, Cloud Monitoring, and
  managed Prometheus. Use when configuring GKE monitoring, setting up GKE
  logging, or configuring Prometheus metrics collection, to diagnose GKE control
  plane, API server, admission webhook, etcd storage, node registration or
  label, and pod eviction, preemption, or scheduling issues using GKE metrics,
  Kubernetes events, and Cloud Logging, and to troubleshoot Managed Service for
  Prometheus (GMP) issues such as missing metrics, unhealthy scrape targets,
  PodMonitoring misconfiguration, rule/alert evaluation failures, and monitoring
  permission errors. Don't use to configure local application logging frameworks
  or external APMs outside GKE.
metadata:
  version: "1.2.1"
  category: CloudObservabilityAndMonitoring
---

# GKE Observability

This reference covers monitoring, logging, and metrics configuration and
troubleshooting for Google Kubernetes Engine (GKE). The golden path enables
comprehensive observability including control-plane metrics and Managed Service
for Prometheus (GMP).

> **MCP Tools:** `get_cluster`, `list_k8s_events`, `get_k8s_logs`,
> `get_k8s_cluster_info`, `describe_k8s_resource`. **CLI-only:** `gcloud
> container clusters update --monitoring=...`, `gcloud logging read`

## Usage Attribution

Do not run live `kubectl`, `gcloud`, or `curl` commands unless the user names a
target cluster/project or asks to inspect a live cluster (output commands and
queries with placeholders, and skip [Usage Attribution](references/attribution.md)).
Before running any live command, read [Usage Attribution](references/attribution.md),
prefix `gcloud` with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:gke-observability)"`,
and append `agent-skills/1.0 (skill:gke-observability)` to `User-Agent` headers
(never in generated scripts, Terraform, or user-facing code).

## Sub-Skill Reference Routing (Progressive Disclosure)

> **Complete Reference Index** (no `scripts/` directory or unlisted reference
> files exist — do not run `ls` on the skill folder; read only the matching
> reference below when answering deep diagnostic, metric, log, or GMP questions):

1.  **[Control-Plane Metrics, Storage, Webhooks & Capacity](references/control-plane-metrics-and-storage.md)**:
    Read for GKE control-plane (KCP) VM CPU or RAM/memory usage questions (not
    publicly exposed) and customer-visible alternatives; cluster etcd /
    etcd-compatible storage left, quota & per-resource scalability limits;
    admission webhook latency, system namespace/Lease/upgrade exclusions,
    `APIService` discovery bloat, client discovery caching bursts
    (`/apis/custom.metrics.k8s.io`, `/apis/metrics.k8s.io`) & proactive GKE
    Recommender insights; watch storms; controller-manager workqueue & scheduler
    lag; or control-plane headroom, VM autoscaling & node-count pre-scaling,
    network egress, connections (`65k`, no per-replica metric) & Protobuf.
2.  **[Cloud Logging, Audit Attribution, APF & API Server Traces](references/logging-audit-and-apiserver-traces.md)**:
    Read for `kube-apiserver` slow-request `Trace[` logs (`trace.go` & KEP-647);
    `httplog.go` client load (`user_agent`, `verb`, `apf_iseats`); Cloud Audit
    Log noisy-neighbor, heavy `LIST` & unindexed CRD `fieldSelector` scan
    tail-latency attribution; API Priority and Fairness (APF) `429`/`504`/`404`
    throttling; `409 Conflict` hot objects (`ConfigMap` -> `Lease` heartbeats) &
    `RenewDeadline / 2` leader-election timeouts; `pods/exec` saturation,
    Konnectivity (`No agent available`), disabled Cloud KMS keys, or in-cluster
    GCP IAM OAuth token webhook authorizer saturation.
3.  **[Cluster/Node/Pod Health, Maintenance & Managed Prometheus (GMP)](references/cluster-node-pod-health-and-gmp.md)**:
    Read for control-plane availability (`kubernetes.io/cluster/kcp_healthchecks`
    rate ratio & ruling out KCP outages); maintenance windows
    (`in_maintenance_window`), zonal resize downtime & cluster access errors
    (`EOF` / `masterAuthorizedNetworksConfig`); node readiness, registration
    (`AUTO_REPAIR_NODES`, Private Google Access) & persistent node-pool labels;
    pod startup timelines, crashing pod logs, `tolerationSeconds: 0` mass
    eviction & Autopilot preemption; or multi-burn-rate SLO alerting
    (`GlobalRules`) & GMP / Grafana / `PodMonitoring` manifests & troubleshooting.

## Golden Path Observability Defaults

Setting                                             | Golden Path Value                                                                                                                                   | Notes
--------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -----
`loggingConfig` components                          | SYSTEM_COMPONENTS, WORKLOADS                                                                                                                        | Full workload logging
`monitoringConfig` components                       | SYSTEM_COMPONENTS, STORAGE, POD, DEPLOYMENT, STATEFULSET, DAEMONSET, HPA, JOBSET, CADVISOR, KUBELET, DCGM, APISERVER, SCHEDULER, CONTROLLER_MANAGER | Full suite including control-plane
`managedPrometheusConfig.enabled`                   | `true`                                                                                                                                              | Google-managed Prometheus
`advancedDatapathObservabilityConfig.enableMetrics` | `true`                                                                                                                                              | Dataplane V2 flow metrics
`loggingService`                                    | `logging.googleapis.com/kubernetes`                                                                                                                 | Cloud Logging
`monitoringService`                                 | `monitoring.googleapis.com/kubernetes`                                                                                                              | Cloud Monitoring

## Enabling Full Monitoring & Logging

Include all four caveats whenever providing a `--monitoring` or `--logging`
command so users avoid accidental metric loss, surprise billing, or silent IAM
failures:

1.  **Control-plane metrics and logs are NOT enabled by default.** State this
    outright: `API_SERVER`, `SCHEDULER`, and `CONTROLLER_MANAGER` are off on
    every new cluster (as are `DCGM`, `CADVISOR`, `KUBELET`, and kube-state
    `POD`, `DEPLOYMENT`, `STATEFULSET`, `DAEMONSET`, `HPA`, `STORAGE`,
    `JOBSET`). Only `SYSTEM` is enabled by default. Link to
    https://docs.cloud.google.com/kubernetes-engine/docs/how-to/control-plane-metrics
    and
    https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs#control_plane_logs.
2.  **The flag replaces, it does not append.** Passing `--monitoring` or
    `--logging` overrides the existing component list; pass the full desired
    list including `SYSTEM`.
3.  **Control-plane and kube-state metrics bill per sample ingested** via
    Managed Service for Prometheus (GMP). Mention the cost impact on large
    clusters; use `--monitoring=SYSTEM` in non-production to reduce cost.
4.  **Verify APIs and IAM permissions (`PermissionDenied`).** Check `gcloud
    container clusters describe {cluster_name} --region {region}
    --format="yaml(loggingConfig,monitoringConfig)"`, ensure
    `logging.googleapis.com` and `monitoring.googleapis.com` are enabled, and
    verify the node service account / GKE service agent has
    `roles/monitoring.metricWriter` and
    `roles/container.defaultNodeServiceAgent`.

> **CLI flag vs. API enum spelling (mixing them fails the command):**
>
> Component      | `gcloud --monitoring=` | `monitoringConfig` API enum
> -------------- | ---------------------- | ---------------------------
> System         | `SYSTEM`               | `SYSTEM_COMPONENTS`
> API server     | `API_SERVER`           | `APISERVER`
> Controller mgr | `CONTROLLER_MANAGER`   | `CONTROLLER_MANAGER`

```bash
# Enable golden path monitoring and control-plane logging suite
gcloud container clusters update {cluster_name} --region {region} \
  --monitoring=SYSTEM,API_SERVER,SCHEDULER,CONTROLLER_MANAGER,STORAGE,POD,DEPLOYMENT,STATEFULSET,DAEMONSET,HPA,JOBSET,CADVISOR,KUBELET,DCGM \
  --logging=SYSTEM,WORKLOAD,API_SERVER,SCHEDULER,CONTROLLER_MANAGER \
  --quiet

# Enable Managed Prometheus and Dataplane V2 flow/policy observability
gcloud container clusters update {cluster_name} --region {region} \
  --enable-managed-prometheus \
  --enable-dataplane-v2-flow-observability \
  --quiet
```

## Core GKE Metrics & Alerting Baseline

Explicitly name **Google Cloud Monitoring** when proposing dashboards and
alerts, and cover cluster/node CPU and memory capacity, pod restarts
(`CrashLoopBackOff`), volume space exhaustion, and API server latency
(`apiserver_request_duration_seconds`). Direct control-plane VM CPU/RAM metrics
are not publicly exposed — read
[Control-Plane Metrics, Storage, Webhooks & Capacity](references/control-plane-metrics-and-storage.md)
whenever asked about control-plane VM CPU/memory or deep control-plane metrics.

Metric                                           | Source             | Use / Alert Threshold
------------------------------------------------ | ------------------ | ---------------------
`apiserver_request_duration_seconds`             | API Server (GMP)   | Control-plane latency (Alert: P99 > 5s)
`scheduler_scheduling_attempt_duration_seconds`  | Scheduler (GMP)    | Current GKE scheduling latency (`scheduler_schedule_attempts_total{result="error"} > 0`)
`container_cpu_usage_seconds_total`              | cAdvisor (Node)    | Worker-node container CPU usage
`container_memory_working_set_bytes`             | cAdvisor (Node)    | Worker-node container memory usage
`kubernetes.io/node/cpu/core_usage_time`         | Cloud Monitoring   | Node CPU usage (`kubernetes.io/node/memory/used_bytes` for memory)
`kube_pod_status_phase`                          | kube-state-metrics | Pod lifecycle phase (requires deploying GMP or self-managed kube-state-metrics)
`kube_pod_container_status_restarts_total`       | kube-state-metrics | Pod crash loops (Alert: > 5 in 10m; requires kube-state-metrics)
`kube_node_status_condition`                     | kube-state-metrics | Node readiness (`condition="Ready", status!="True"`; or `kubernetes.io/node/status_condition`)
`kubelet_volume_stats_used_bytes / capacity`     | Kubelet            | PVC capacity utilization (Alert: > 85%)
`DCGM_FI_DEV_GPU_UTIL`                           | DCGM (GMP)         | GPU utilization (Alert: > 95% sustained)

## Live Resource Usage & Cloud Logging Queries

Use `kubectl top` for live usage (no MCP or `gcloud` equivalent):

```bash
kubectl top pods --all-namespaces --sort-by=cpu
kubectl top nodes
kubectl top pods --containers -n {namespace}
```

Use `gcloud logging read` (or Cloud Logging Log Explorer) with LQL filters:

```bash
# Control-plane component logs (requires API_SERVER / SCHEDULER / CONTROLLER_MANAGER enabled)
gcloud logging read 'resource.type="k8s_control_plane_component" AND resource.labels.cluster_name="{cluster_name}"' --project {project_id} --limit 50 --quiet

# Container errors: resource.type="k8s_container" AND resource.labels.container_name="{container_name}" AND severity>=ERROR
# OOMKilled events: resource.type="k8s_event" AND jsonPayload.reason="OOMKilling"
# FailedScheduling: resource.type="k8s_event" AND jsonPayload.reason="FailedScheduling"
# Cloud Audit Logs: resource.type="k8s_cluster" AND logName:"cloudaudit.googleapis.com"
# Dataplane V2 network policy / packet drop logs: logName:"policy_action" AND jsonPayload.disposition="DENY"
```

## Distributed Tracing, Profiling & Recent Additions

-   **Cloud Trace & OpenTelemetry**: Deploy the OpenTelemetry Collector
    (`googlecloud` exporter with Workload Identity) or enable **Managed
    OpenTelemetry for GKE (Preview)** on GKE 1.34.1-gke.2178000+ (`gcloud beta
    container clusters update {cluster_name} --region {region}
    --managed-otel-scope=COLLECTION_AND_INSTRUMENTATION_COMPONENTS`).
-   **Cloud Profiler**: Continuous low-overhead production CPU/memory profiling.
-   **PSI (Pressure Stall Information) metrics**: cAdvisor
    `container_pressure_{cpu,memory,io}_{waiting,stalled}_seconds_total` via GMP
    `ClusterNodeMonitoring` (GKE 1.35+).

## Supporting Links

-   [GKE System Metrics](https://docs.cloud.google.com/monitoring/api/metrics_kubernetes)
-   [GKE Control-Plane Metrics](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/control-plane-metrics)
-   [GKE Control-Plane Logs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs#control_plane_logs)
-   [Google Cloud Managed Service for Prometheus](https://cloud.google.com/stackdriver/docs/managed-prometheus)
-   [Troubleshoot Managed Service for Prometheus](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus/troubleshooting.md.txt)
-   [Rule Evaluation (Rules / ClusterRules / GlobalRules)](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus/rules-managed.md.txt)
-   [Cloud Logging Query Language (LQL)](https://cloud.google.com/logging/docs/view/logging-query-language)
-   [Google Cloud Monitoring Alerts](https://cloud.google.com/monitoring/alerts)
