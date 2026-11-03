# Control-Plane Metrics, Storage, Webhooks & Capacity

## Table of Contents

-   **1. Control-Plane Metrics Prerequisites & KCP VM Boundaries** (Lines 13–34)
-   **2. Etcd-Compatible Storage Backend & Remaining-Capacity Queries** (Lines 36–52)
-   **3. Real-Time Storage Quota Alerts, Per-Resource Footprint & Cleanup** (Lines 54–92)
-   **4. Admission Webhooks, Exclusions, Discovery & Recommendations** (Lines 94–159)
-   **5. Watch Activity & Watch Storms** (Lines 161–167)
-   **6. Pod Churn, Controller-Manager Workqueues & Scheduler Lag** (Lines 169–187)
-   **7. Control-Plane Headroom, Network Egress, Connections & Protobuf** (Lines 189–224)

## 1. Control-Plane Metrics Prerequisites & KCP VM Boundaries

> **Control-plane (KCP) VM CPU and RAM/memory usage are not publicly exposed:**
> GKE manages control-plane VMs internally and exposes **no** KCP VM CPU or
> RAM/memory usage metrics in Cloud Monitoring (`kubernetes.io/cluster/*`,
> `kubernetes.io/master/*`, or worker-node-only `kubernetes.io/node/*` /
> `container_*`) or Managed Service for Prometheus. Instead of KCP VM CPU,
> monitor `kubernetes.io/cluster/kcp_healthchecks`,
> `apiserver_request_duration_seconds`, and APF concurrency saturation
> (`apiserver_flowcontrol_priority_level_seat_utilization` and
> `apiserver_current_inflight_requests`). Instead of KCP VM RAM/memory, monitor
> `apiserver_resource_size_estimate_bytes`, `apiserver_storage_size_bytes`
> (`kubernetes.io/cluster/storage/used_bytes` and
> `kubernetes.io/cluster/storage/limit_bytes`), and
> `kubernetes.io/cluster/kcp_healthchecks`.

Whenever recommending any `apiserver_*`, `scheduler_*`, `workqueue_*`, or
`job_controller_*` metric below, state that it is a Managed Service for
Prometheus (GMP) control-plane metric that is **not enabled by default**
(requires `--monitoring=SYSTEM,API_SERVER,SCHEDULER,CONTROLLER_MANAGER,...` and
`--enable-managed-prometheus`; see `SKILL.md` for CLI vs. API enum spellings)
and link to https://docs.cloud.google.com/kubernetes-engine/docs/how-to/control-plane-metrics.

## 2. Etcd-Compatible Storage Backend & Remaining-Capacity Queries

In self-managed Kubernetes, operators check remaining `etcd` space via `etcdctl
endpoint status` or raw `etcd` metrics (`etcd_mvcc_db_total_size_in_bytes`,
`etcd_server_quota_backend_bytes`). **GKE uses a managed etcd-compatible
storage** backend for cluster state and does not expose `etcdctl` or raw
`etcd_*` server metrics—always state explicitly that **GKE uses an
etcd-compatible storage** backend when answering cluster `etcd` storage
questions. Instead, query the default Cloud Monitoring `SYSTEM` metrics
**`kubernetes.io/cluster/storage/used_bytes`** and
**`kubernetes.io/cluster/storage/limit_bytes`** on `monitored_resource="k8s_cluster"`
(enabled out-of-the-box without `API_SERVER` or GMP opt-in):

```promql
# Remaining control-plane storage bytes (divide used_bytes / limit_bytes for utilization ratio)
kubernetes_io:cluster_storage_limit_bytes{monitored_resource="k8s_cluster"} - kubernetes_io:cluster_storage_used_bytes{monitored_resource="k8s_cluster"}
```

## 3. Real-Time Storage Quota Alerts, Per-Resource Footprint & Cleanup

-   **Real-time storage utilization vs. 6h quota delay**: In Cloud Monitoring,
    `kubernetes.io/cluster/storage/used_bytes` and
    `kubernetes.io/cluster/storage/limit_bytes` sample every 60s (avoiding the
    6-hour delay of GCP quota metrics; opt-in GMP also exposes
    `apiserver_storage_size_bytes`). Configure an alert when `used_bytes /
    limit_bytes` approaches capacity on GKE's etcd-compatible control-plane
    datastore so leaked Pods, Jobs, or Secrets are pruned before `etcdserver:
    mvcc: database space exceeded` write locks occur.
-   **Per-resource byte footprint & GKE scalability limits**: Query
    `apiserver_resource_size_estimate_bytes` (or
    `kubernetes.io/master/apiserver/resource_size_estimate_bytes`) and
    `apiserver_storage_objects` grouped by `group` and `resource` to find which
    resource types or CRDs consume the most storage bytes. Compare against GKE
    scalability limits
    (https://cloud.google.com/kubernetes-engine/docs/concepts/planning-large-clusters:
    keep total Pod or ReplicaSet state below ~800 MiB per resource type, keep
    individual ConfigMaps/Secrets below 1 MiB vs. the 1.5 MiB etcd hard limit,
    and stay below ~30,000 Secrets/ConfigMaps).
-   **Quota exhaustion (`mvcc: database space exceeded`) & CRD bloat cleanup**:
    When creations, updates, or Lease renewals fail with `etcdserver: mvcc:
    database space exceeded`, delete bloated objects in small paced batches:
    -   **Version behavior on failing deletes**: State explicitly that while
        some earlier GKE versions blocked all edits (including deletes) on
        hitting storage quota, this is no longer the case in newer GKE versions
        (`kubectl delete` remains permitted).
    -   Finished `batch/v1` Jobs and CronJob pods (`concurrencyPolicy: Allow`):
        set `.spec.ttlSecondsAfterFinished` on Jobs and
        `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` on CronJobs;
        retained ReplicaSets (lower `.spec.revisionHistoryLimit`), Kyverno
        `admissionreports`, oversized Secrets/ConfigMaps, or stuck finalizers.
-   **Excessive `VolumeSnapshot` objects hanging `LIST` (<50,000 limit)**: When
    new `VolumeSnapshot` objects take 30+ minutes to become ready or deleted
    snapshots stay stuck in `Terminating`, check `apiserver_storage_objects` and
    `apiserver_resource_size_estimate_bytes` (plus `kube-apiserver` slow `LIST`
    `Trace[` logs) for `volumesnapshots` and `volumesnapshotcontents` causing
    `snapshot-controller` `LIST` timeouts; prune old snapshots and enforce a
    retention policy keeping the total count well below 50,000.

## 4. Admission Webhooks, Exclusions, Discovery & Recommendations

-   **Measuring webhook latency & errors**: When API calls or pod creations time
    out (`context deadline exceeded`), query
    `apiserver_admission_webhook_admission_duration_seconds` (grouped by `name`,
    `type`, `operation`, and `rejected`) and
    `apiserver_admission_webhook_rejection_count` alongside `kube-apiserver`
    slow-request `Trace[` logs, GKE Webhook Insights (`Verify webhook with
    unavailable endpoints`), and `kubernetes.io/cluster/kcp_healthchecks` (to
    verify the GKE control plane itself is healthy before requesting an upsize).
    Scale/fix backing webhook pods, tighten `timeoutSeconds` (e.g., 2–5s), scope
    `namespaceSelector`, or set `failurePolicy: Ignore` where appropriate.
-   **System namespace & Lease exclusions (preventing controller leadership loss
    & CNI `NotReady` nodes)**: Inspect `ValidatingWebhookConfiguration` and
    `MutatingWebhookConfiguration` rules. Exclude `kube-system` and
    `kube-node-lease` via `namespaceSelector` on third-party webhooks (Kyverno,
    Datadog, Vault, OpenTelemetry, or OPA Gatekeeper's
    `admission.gatekeeper.sh/ignore` label) and remove `coordination.k8s.io`
    `leases` (`coordination.k8s.io/leases`) from webhook rules so slow/crashed
    webhooks never block controller Lease renewals or `kube-system` CNI pods
    (`netd`, `anetd`, leaving new nodes stuck `NotReady` with `CNI plugin not
    initialized`).
-   **Control-plane upgrade failures & addon deadlocks**: When upgrades fail and
    roll back or Cluster Autoscaler stops initializing after an upgrade with
    `failurePolicy: Fail` webhooks, check Cloud Audit Logs or webhook
    metrics/logs during the upgrade window for denied/timed-out requests from
    `system:apiserver` (on `rbac.authorization.k8s.io/clusterrolebindings`) or
    `system:addon-manager` (on system `customresourcedefinitions` such as
    `capacitybuffers.autoscaling.x-k8s.io`). Exempt `rbac.authorization.k8s.io`
    bootstrap bindings and GKE system CRDs (`*.gke.io`, `autoscaling.x-k8s.io`)
    from webhook rules or set `failurePolicy: Ignore`.
-   **Unavailable webhook endpoints, OOMKilled pods, `APIService` & discovery**:
    -   Inspect `MutatingWebhookConfiguration` / `ValidatingWebhookConfiguration`
        service references, verify `EndpointSlice` addresses match running pod
        IPs, inspect CRD conversion webhooks (`spec.conversion.webhook`), and
        check backing pod health and OOM kills (`jsonPayload.reason="OOMKilling"`,
        `kubectl describe pod {pod_name}`, `kubectl logs {pod_name} --previous`).
        Increase memory limits on OOMKilled webhook pods (e.g., Gatekeeper or
        Kubeflow `cache-server`), fix the deployment, or scope
        rules/`failurePolicy`.
    -   When every `kubectl` command takes 15–30s, run `kubectl get apiservices`
        and `kubectl --v=6` alongside `apiserver_response_sizes` and
        `apiserver_request_duration_seconds` to spot unavailable `APIService`
        backends or multi-megabyte discovery documents from aggregated APIs
        (`custom.metrics.k8s.io`, `external.metrics.k8s.io`). Disable or filter
        unbounded custom metrics exporters (e.g., Airflow or Prometheus adapters
        exporting thousands of series into API discovery).
    -   When custom scripts, cron jobs, or CLI invocations flood
        `/apis/custom.metrics.k8s.io` and `/apis/metrics.k8s.io` with thousands
        of requests per minute (visible in Cloud Audit Logs / `httplog.go`
        `userAgent` and `apiserver_request_total`), clients are polling API
        discovery without a persistent local cache; enable client-side discovery
        caching (`client-go` `disk.NewCachedDiscoveryClientForConfig` /
        `memory.NewMemCacheClient` or a persistent shared `kubectl --cache-dir`
        rather than ephemeral per-run directories).
-   **Proactive GKE Control-Plane & Webhook Insights / Recommendations**: Check
    GKE Insights and Recommendations in the Cloud Console or via `gcloud
    recommender insights list` and `gcloud recommender recommendations list`
    (`--insight-type=google.container.DiagnosisInsight` /
    `--recommender=google.container.DiagnosisRecommender`). Warn users against
    ignoring GKE control-plane recommendations—especially admission webhook
    findings (unavailable endpoints, high latency, missing `kube-system`
    exclusions) or CRDs with an invalid `caBundle`—because they can overload or
    destabilize the control plane. Link to
    https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-webhooks
    and https://docs.cloud.google.com/kubernetes-engine/docs/how-to/crd-with-invalid-caBundle.

## 5. Watch Activity & Watch Storms

When a misconfigured agent or DaemonSet is suspected of causing a watch storm or
repeatedly re-establishing broken watches, query GMP `apiserver_longrunning_requests`
(`verb="WATCH"`, grouped by `group`, `resource`, `scope`) for active watchers,
`apiserver_watch_events_total` (grouped by `group`, `kind`, `version`) for watch
event volume/rate, and `apiserver_watch_events_sizes` for watch payload sizes.

## 6. Pod Churn, Controller-Manager Workqueues & Scheduler Lag

When batch job bursts (tens of thousands of concurrent Jobs) delay pod
creation/scheduling by 10–20 minutes—saturating `kube-controller-manager` and
`kube-scheduler` QPS/workqueues, often exacerbated by crashing DaemonSets—or
when custom controllers fall behind:

-   Enable `SCHEDULER` and `CONTROLLER_MANAGER` control-plane metrics.
-   Query `workqueue_depth`, `workqueue_queue_duration_seconds`,
    `workqueue_adds_total`, `workqueue_retries_total`, and `job_controller_*`
    metrics (such as `job_controller_job_sync_duration_seconds`) on
    `kube-controller-manager`.
-   Query `scheduler_pending_pods`, `scheduler_schedule_attempts_total`, and
    `scheduler_scheduling_attempt_duration_seconds` on `kube-scheduler`, plus
    mutating `apiserver_request_total` (`CREATE`, `DELETE`, `PATCH`, `UPDATE`)
    to measure object churn.
-   Correlate workqueue growth (e.g., `pod-garbage-collector` or `replicaset`
    lag) with API server latency and high churn; prune orphaned objects, tune
    controller concurrency, and pace or batch job submissions.

## 7. Control-Plane Headroom, Network Egress, Connections & Protobuf

-   **Saturation, headroom & control-plane VM autoscaling**: Monitor
    `apiserver_flowcontrol_priority_level_seat_utilization`,
    `apiserver_current_inflight_requests`, and
    `apiserver_request_duration_seconds` (plus
    `apiserver_flowcontrol_request_wait_duration_seconds` and
    `apiserver_flowcontrol_rejected_requests_total`). Always cover three
    operational guidance points when discussing control-plane headroom or
    preventing overload:
    1.  **Correlate spikes with workload changes** (new DaemonSets, unpaginated
        `LIST` calls, bursty controllers) to roll back or tune workloads before
        saturating `kube-apiserver`.
    2.  **Automatic control-plane VM scaling**: Highlight that GKE
        control-plane VMs are autoscaled to match observed load, so
        control-plane capacity adjusts dynamically as cluster activity grows.
    3.  **Proactive resize via node count**: Explain that the GKE control plane
        uses cluster node count as one of its autoscaling signals, so adding
        more nodes upfront (for example, ahead of a planned batch or traffic
        surge) is a relatively simple way to force a proactive control-plane
        resize—while noting that the exact scaling rules change frequently, so
        there is no reliable fixed threshold that GKE can share.
-   **Control-plane network egress, connections (`65k`), & Protobuf**: State
    explicitly out loud that **GKE does not offer a per-replica control-plane
    connection count metric** (so active watch/long-running stream metrics
    serve only as an indirect proxy). Check for heavy response/watch payload
    egress, connection limits (`65k`), or high JSON serialization overhead via
    `apiserver_response_sizes`, `apiserver_watch_events_sizes`,
    `apiserver_longrunning_requests`, and `apiserver_request_total` by
    `contentType` (`application/json` vs.
    `application/vnd.kubernetes.protobuf`). Always advise both mitigations:
    (1) configure custom controllers and high-volume clients to use Protobuf
    serialization (`application/vnd.kubernetes.protobuf`) instead of JSON, and
    (2) scope `WATCH`/`LIST` selectors (`labelSelector`, `fieldSelector`, and
    namespace-scoped informers) to reduce control-plane network egress and
    keep active connections within safe scalability limits.
