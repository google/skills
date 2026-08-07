---
name: gke-workload-scaling
description: >-
  Manages scaling for GKE workloads using HPA and VPA. Use when configuring
  Horizontal Pod Autoscaler (HPA), configuring Vertical Pod Autoscaler (VPA),
  or applying best practices for GKE workload autoscaling. Do not use for
  cluster-level autoscaling (Cluster Autoscaler), static cluster sizing,
  or configuring node-level machine styles directly.
metadata:
  category: Containers
---

# GKE Workload Scaling

This skill provides workflows and best practices for scaling applications on
Google Kubernetes Engine (GKE). It covers manual scaling, Horizontal Pod
Autoscaling (HPA), and Vertical Pod Autoscaling (VPA).

## Workflows

### 1. Manual Scaling

Scale a deployment to a fixed number of replicas. Useful for immediate manual
intervention or testing.

**Command:**

```bash
kubectl scale deployment {deployment_name} --replicas={number} -n {namespace}

# Verify the scale event
kubectl get deployment {deployment_name} -n {namespace}
```

### 2. Horizontal Pod Autoscaling (HPA)

Automatically scale the number of pods based on observed CPU utilization, memory
utilization, or custom metrics.

**Prerequisites:**

-   Metrics Server must be running (enabled by default on GKE).
-   Containers clearly define resource requests/limits.

**Quick Command:**

```bash
kubectl autoscale deployment {deployment_name} --cpu-percent=50 --min=1 --max=10
```

**Manifest Approach (Recommended):** Use a YAML manifest for version-controlled
configuration. See [assets/hpa-example.yaml](assets/hpa-example.yaml) for a
template.

```bash
kubectl apply -f assets/hpa-example.yaml

# Verify HPA is created and fetching metrics
kubectl get hpa
```

**Custom Metrics & External Metrics:** For GKE, the modern and recommended
approach for scaling based on Cloud Monitoring metrics (e.g., Pub/Sub queue
length) is to use the **External** metric type, which is natively supported by
the GKE control plane without requiring the Custom Metrics Adapter. For
application-specific metrics exposed via Prometheus, you can use **Google Cloud
Managed Service for Prometheus** or the Prometheus Adapter.

### 3. Vertical Pod Autoscaling (VPA)

Automatically adjust the CPU and memory reservations for your pods to match
actual usage. This is critical for right-sizing workloads.

**Prerequisites:**

-   VPA must be enabled on the cluster.
    -   **Autopilot:** Enabled by default.
    -   **Standard:** Must be enabled manually.

**Enable VPA on Standard Cluster:**

```bash
gcloud container clusters update {cluster_name} --enable-vertical-pod-autoscaling --zone {zone}
```

**Update Modes:**

-   `Off`: Calculates recommendations but does not apply them. Good for "dry
    run" analysis.
-   `Initial`: Assigns resources only at pod creation time.
-   `Auto`: Updates running pods by restarting them if recommendations differ
    significantly from requests.
-   `InPlaceOrRecreate`: Attempts to update Pod resources without recreating the
    Pod. If in-place update is not possible, it reverts to `Auto` mode (requires
    GKE 1.34+).

**Example:** See [assets/vpa-example.yaml](assets/vpa-example.yaml) for a
configuration template.

## Best Practices

1.  **Define Resource Requests:** HPA and VPA rely on accurate resource
    requests. Always define them in your container specs.
2.  **Avoid Metric Conflicts:** Do not configure HPA and VPA to use the same
    metric (e.g., both CPU). This causes thrashing.
    -   *Typical Pattern:* HPA on CPU, VPA on Memory.
3.  **Pod Disruption Budgets (PDBs):** Define PDBs to ensure application
    availability during scaling events or node upgrades.
4.  **HPA Lag:** HPA has a stabilization window (default 5 mins) to prevent
    rapid fluctuation.
5.  **VPA "Auto" Mode Risks:** In "Auto" mode, VPA restarts pods to change
    resources. Ensure your application handles restarts gracefully (e.g.,
    handles SIGTERM).
    -   *Note:* By default, VPA requires at least 2 replicas to perform
        evictions (to prevent a situation where the only running replica is
        evicted, causing downtime). In GKE 1.22+, you can override this by
        setting `minReplicas` in `PodUpdatePolicy`.

## Rightsizing Workflow

1.  Deploy VPA in `Off` mode for 24+ hours
2.  Read recommendations: `kubectl describe vpa {deployment_name}-vpa -n
    {namespace}`
3.  Compare `target` values against current `requests`
4.  Apply with 20% buffer: `new_request = target * 1.2`
5.  Use patch format or update deployment manifest to apply new resource
    requests

Condition                     | Recommendation                       | Risk
----------------------------- | ------------------------------------ | ------
CPU request >5x P95 actual    | Reduce to `P95 * 1.2`                | Medium
Memory request >3x P95 actual | Reduce to `P95 * 1.2`                | Medium
CPU request >2x P95 actual    | Rightsizing with 20% buffer          | Low
No resource limits set        | Add limits to prevent noisy-neighbor | Low
