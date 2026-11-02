# Cluster/Node/Pod Health, Maintenance & Managed Prometheus (GMP)

## Table of Contents

-   **1. Control-Plane Health (`kcp_healthchecks`) & Maintenance Windows** (Lines 10–65)
-   **2. Node Health, Registration Failures & Persistent Node Labels** (Lines 67–99)
-   **3. Pod Startup Timeline, Mass Evictions & Autopilot Preemption** (Lines 101–128)
-   **4. Multi-Burn-Rate SLO Alerting & GMP Troubleshooting** (Lines 130–204)

## 1. Control-Plane Health (`kcp_healthchecks`) & Maintenance Windows

To check whether Google considers a GKE cluster's control plane healthy, use the
**`kubernetes.io/cluster/kcp_healthchecks`** system metric (on the `k8s_cluster`
monitored resource, included in the default `SYSTEM` metrics package):

1.  **Metric semantics & rate-ratio query**: `kubernetes.io/cluster/kcp_healthchecks`
    is an incremental (`DELTA` / `CUMULATIVE` counter) metric sampled every 60s
    that counts Google-internal control-plane probes, labeled by boolean
    `success` (`"true"` or `"false"`). Chart or alert on control-plane
    availability by dividing the rate of successful checks (`success="true"`) by
    the overall rate of checks across all `success` values:

    ```promql
    sum by (project_id, location, cluster_name) (rate(kubernetes_io:cluster_kcp_healthchecks{monitored_resource="k8s_cluster", success="true"}[5m]))
    / sum by (project_id, location, cluster_name) (rate(kubernetes_io:cluster_kcp_healthchecks{monitored_resource="k8s_cluster"}[5m]))
    ```

2.  **Ruling out a GKE control-plane outage (`kcp_healthchecks` innocence)**:
    Check `kubernetes.io/cluster/kcp_healthchecks` (rate ratio) alongside
    `apiserver_request_duration_seconds` and `apiserver_request_total`
    (`code="429"` / `5xx`) in Cloud Monitoring. When `kcp_healthchecks` and API
    server latency are healthy with no `429` throttling, slow pod deletions or
    client delays originate from client-side request concurrency, pod
    finalizers/graceful termination, or the customer's own pod-creating service
    rather than a GKE control-plane fault.
3.  **Maintenance windows, zonal resize downtime & cluster access errors**:
    -   **Maintenance window metrics & policy limits**: Query
        `kubernetes.io/cluster/in_maintenance_window` (boolean `GAUGE` on
        `monitored_resource="k8s_cluster"`, included in default `SYSTEM`
        metrics; PromQL:
        `kubernetes_io:cluster_in_maintenance_window{monitored_resource="k8s_cluster"}`)
        in Cloud Monitoring and correlate with `gcloud container operations list`
        (or Cloud Audit Logs for `RESIZE_CLUSTER` or `UPGRADE_MASTER`) to verify
        whether brief API unavailability, blocked updates, or lease-loss alerts
        occurred during scheduled maintenance. Move the maintenance window to a
        lower-traffic period or use `kubernetes.io/cluster/in_maintenance_window`
        to suppress transient alerts. Ensure maintenance windows/exclusions do
        not violate GKE limits (see
        https://docs.cloud.google.com/kubernetes-engine/docs/concepts/maintenance-windows-and-exclusions#limitations-maint-exclusions,
        requiring at least 48 hours of total maintenance availability in any
        32-day (and 92-day) rolling window, in contiguous blocks of at least 4
        hours) so routine control-plane upgrades and repairs are not blocked.
    -   **Zonal resize downtime vs. access errors (`EOF` / `CLOUD_KMS_KEY_ERROR`)**:
        Correlate `kubernetes.io/cluster/kcp_healthchecks` and
        `kubernetes.io/cluster/in_maintenance_window` with `gcloud container
        operations list` (`RESIZE_CLUSTER` or `UPGRADE_MASTER`): **zonal
        clusters** have a single control-plane replica that experiences expected
        15–30 minute API downtime during resizes and upgrades (mitigate by
        migrating to a regional cluster). If `kubectl` fails with `EOF` or
        `CLOUD_KMS_KEY_ERROR`, check `gcloud container clusters describe
        {cluster_name}` (`masterAuthorizedNetworksConfig`, `databaseEncryption`,
        and cluster conditions) and project IAM/APIs to resolve client IP
        allowlist blocks (`EOF`), disabled Cloud KMS keys
        (`CLOUD_KMS_KEY_ERROR`), a disabled `container.googleapis.com` API, or
        missing GKE service agent IAM bindings.

## 2. Node Health, Registration Failures & Persistent Node Labels

When proposing node health charts, combine both metrics below and **state both
metrics' limitations explicitly** (neither metric is complete alone):

1.  **`kubernetes.io/node/status_condition`** (on `monitored_resource="k8s_node"`,
    filtered by `condition="Ready"` / `status_condition="Ready"`, grouped by
    `status` = `True` / `False` / `Unknown`; PromQL: `count by (status)
    (kubernetes_io:node_status_condition{monitored_resource="k8s_node",
    condition="Ready"})`): Tracks healthy vs. unhealthy registered nodes, **but
    only reports values for nodes that have successfully bootstrapped** (missing
    VMs stuck failing registration).
2.  **`compute.googleapis.com/instance_group/size`** (on `gce_instance_group`,
    filtered by `instance_group_name="gke-<cluster_name>-.*"`): Tracks the total
    number of GCE nodes in the cluster, **but does not differentiate between
    healthy and unhealthy nodes** (so comparing `instance_group/size` against
    `status_condition="Ready"` is required to spot unbootstrapped VMs).
3.  **Node registration failures (`AUTO_REPAIR_NODES`)**: When new node pools
    fail registration before reporting `kubernetes.io/node/status_condition`,
    query the consumer project's Cloud Audit Logs
    (`cloudaudit.googleapis.com/activity`) for GCE instance creation denials
    (`403` / `constraints/gcp.resourceLocations`), verify Private Google Access
    (`privateIpGoogleAccess`) is enabled on the cluster subnet, and check VPC
    routes/firewall rules so traffic to `*.googleapis.com`, `*.gcr.io`, and
    `*.pkg.dev` is not blackholed into a custom VPN or firewall.
4.  **Node labels overwritten on upgrade (`kubectl label node` vs. Node Pool
    API)**: `gcp-controller-manager` reconciles node labels declared in the GKE
    Node Pool API specification during control-plane upgrades and node repairs
    (visible as `system:gcp-controller-manager` node patches in Cloud Audit
    Logs), reverting manual `kubectl label node {node_name} {key}={val}
    --overwrite` edits on GKE-managed label keys. Update node pool labels
    persistently via `gcloud container node-pools update {pool_name}
    --node-labels=...` (or Terraform `node_config.labels`).

## 3. Pod Startup Timeline, Mass Evictions & Autopilot Preemption

-   **End-to-end pod startup lifecycle & crashing pods**: To pinpoint whether a
    slow-starting pod was delayed during controller creation, scheduling,
    `kubelet` pickup, or container startup, correlate Kubernetes Events
    (`resource.type="k8s_pod"` or `k8s_event`) with Cloud Audit Logs
    (`cloudaudit.googleapis.com/activity`), optional control-plane component
    logs (`kube-scheduler`, `kube-controller-manager`, `kube-apiserver` under
    `resource.type="k8s_control_plane_component"`), and node `kubelet` logs
    (`resource.type="k8s_node"`). For crashing pods, run `kubectl logs
    {pod_name} --previous` (or `-p`), `kubectl describe pod {pod_name}`, and
    query Cloud Logging (`resource.type="k8s_container"`).
-   **`tolerationSeconds: 0` mass pod eviction**: If pods are simultaneously
    evicted during a brief control-plane hiccup when nodes briefly enter
    `NodeStatusUnknown`, inspect workload Pod/Deployment specs (`kubectl get
    deploy -o yaml`) for custom `tolerations` on
    `node.kubernetes.io/unreachable` (`NoExecute`) and
    `node.kubernetes.io/not-ready` (`NoExecute`) with `tolerationSeconds: 0`
    (which overrides Kubernetes's default 300s eviction grace period), and
    remove the `tolerationSeconds: 0` override.
-   **Autopilot single-node bin-packing & system-addon preemption**: If all
    replicas of a Deployment pack onto a single node at its `maxPods` limit
    (`32/32` on Autopilot), surging `system-cluster-critical` addons (priority
    `2000000000`) during a control-plane upgrade trigger scheduler preemption,
    which bypasses `PodDisruptionBudget` when no other capacity is immediately
    available. Configure `topologySpreadConstraints` or `podAntiAffinity` across
    nodes/zones so replicas never co-locate on a single node, and assign an
    appropriate `PriorityClass`.

## 4. Multi-Burn-Rate SLO Alerting & GMP Troubleshooting

### Prometheus / Grafana / PagerDuty Control-Plane SLO Alerting

When generating Grafana dashboards and multi-burn-rate Prometheus alert rules
for GKE control-plane health (routed to PagerDuty or Slack via Alertmanager or
Cloud Monitoring notification channels; output YAML/JSON directly inline without
scratch generator scripts), use `GlobalRules` (`monitoring.googleapis.com/v1`,
required when evaluating against Cloud Monitoring / GMP system metrics) covering
`apiserver_request_duration_seconds` (e.g., fast `5m`/`1h` 14.4x + slow
`30m`/`6h` 6x burn rates), `apiserver_admission_webhook_admission_duration_seconds`,
`apiserver_flowcontrol_rejected_requests_total`, and storage utilization
(`kubernetes_io:cluster_storage_used_bytes / kubernetes_io:cluster_storage_limit_bytes`
or `apiserver_storage_size_bytes`), queried in Grafana via the GMP data source
(`GET` HTTP method and two-argument `label_values(<metric>, <label>)`).
**Always state explicitly that GKE control-plane `apiserver_*` metrics are NOT
enabled by default**, and instruct how to enable them (`gcloud container
clusters update {cluster_name} --region {region}
--monitoring=SYSTEM,API_SERVER,SCHEDULER,CONTROLLER_MANAGER,...
--enable-managed-prometheus`, noting `--monitoring` replaces the existing list).

### Troubleshooting Managed Service for Prometheus (GMP)

Stay read-only (`kubectl get` / `describe` / `logs`) and propose config changes:

1.  **First: split ingestion-side vs. query-side**: Query `up` in the **Metrics
    Explorer PromQL tab** in Cloud Monitoring. If `up` returns data, ingestion
    works and the issue is query-side (Grafana / PromQL / permissions). If `up`
    is empty, the issue is ingestion-side (collectors, scrape config, or write
    IAM).
2.  **Ingestion-side checks**:
    -   **GMP system pods**: Verify GMP is active via `gcloud container clusters
        describe {cluster_name}` and inspect pods in `gmp-system` (Standard) or
        `gke-gmp-system` (Autopilot) (`gmp-operator`, `collector` DaemonSet, and
        `rule-evaluator`):
        ```bash
        kubectl get pods -n gmp-system            # gke-gmp-system on Autopilot
        kubectl logs -n gmp-system -l app.kubernetes.io/name=collector -c prometheus
        ```
        A `collector` in `CrashLoopBackOff` with `OOMKilled` indicates high
        cardinality—drop unneeded series/labels via `metricRelabeling` or apply
        a VPA.
    -   **`PodMonitoring` vs. `ClusterPodMonitoring`**: Always write `PodMonitoring`
        manifests with `apiVersion: monitoring.gke.io/v1` (`kind: PodMonitoring`
        is namespace-scoped; `ClusterPodMonitoring` is cluster-wide), setting
        `spec.selector.matchLabels` to match pod labels and `spec.endpoints`
        with `port` (container port name or number), `path` (e.g., `/metrics`),
        and `interval` (e.g., `30s`).
    -   **Target status debugging**: Temporarily patch `OperatorConfig` in
        `gmp-public` with `features.targetStatus.enabled: true`, run `kubectl
        describe podmonitoring {name}` (`Active Targets`, `Unhealthy Targets`,
        `Last Error`), then disable to prevent operator OOMs on large clusters.
3.  **Permissions (`403` / `PermissionDenied`)**: GMP inherits the **node
    service account**. Ingestion requires `roles/monitoring.metricWriter`
    (`Permission monitoring.timeSeries.create denied` in collector logs);
    `rule-evaluator` and query paths (including Grafana via Workload Identity)
    require `roles/monitoring.viewer`.
4.  **Rule & alert evaluation (`Rules` / `ClusterRules` / `GlobalRules`)**: Use
    `GlobalRules` to evaluate rules against Cloud Monitoring system/control-plane
    metrics (`Rules` and `ClusterRules` silently return no data for them). Check
    `rule-evaluator` logs (`-c evaluator`).
5.  **Query-side (Grafana / PromQL)**:
    -   Point the Grafana data source at the GMP frontend query proxy (not
        `localhost:9090`) and set **HTTP Method to `GET`** (`POST` fails with
        `no match[] parameter provided`).
    -   Use the two-argument `label_values(<metric>, <label>)` in Grafana
        template variables (single-argument `label_values(<label>)` is
        unsupported by GMP).
    -   Include a `monitored_resource` label matcher when querying Cloud
        Monitoring metrics that exist across multiple resource types.
6.  **Cost, cardinality & quota (`429` / `RESOURCE_EXHAUSTED`)**: Inspect Cloud
    Monitoring **Metrics Management** to find top billable/high-cardinality
    metrics. Prune with `metricRelabeling` (`action: drop` or `action:
    labeldrop` for unbounded labels like `user_id`/`request_id`) or raise the
    scrape `interval` before requesting quota increases.
