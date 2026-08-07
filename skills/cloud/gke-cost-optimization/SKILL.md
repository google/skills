---
name: gke-cost-optimization
description: >-
  Optimizes GKE costs, rightsizes workloads, and configures Spot VMs, CUDs, cost
  allocation, and resource quotas. Use when optimizing GKE cluster or workload
  costs, configuring GKE cost allocation or quotas, rightsizing CPU/memory
  requests, or selecting Spot VMs and machine types. Don't use for general
  compute class provisioning or GPU Selection (use gke-compute-classes instead).
metadata:
  category: CloudObservabilityAndMonitoring
---

# GKE Cost Optimization

This reference covers strategies and workflows for reducing Google Kubernetes
Engine (GKE) costs while maintaining a secure and reliable posture.

> **MCP Tools:** `get_k8s_resource`, `describe_k8s_resource`,
> `apply_k8s_manifest`, `patch_k8s_resource`, `get_cluster`

## Golden Path Cost Features

The golden path already includes cost-optimizing settings:

| Setting                  | Value                  | Impact                  |
| ------------------------ | ---------------------- | ----------------------- |
| `autoscalingProfile`     | `OPTIMIZE_UTILIZATION` | Aggressive node         |
:                          :                        : scale-down reduces idle :
:                          :                        : compute                 :
| `verticalPodAutoscaling` | `enabled`              | VPA recommendations     |
:                          :                        : prevent                 :
:                          :                        : over-provisioning       :
| Autopilot pricing        | Pay per pod request    | No charge for unused    |
:                          :                        : node capacity           :
| Node Auto Provisioning   | enabled                | Right-sized node pools  |
:                          :                        : created automatically   :

## Workflows & Optimization Strategies

### 1. Prerequisite: Cost Allocation & Monitoring

To enable GKE cost allocation (`--enable-cost-allocation`) for billing tracking
across namespaces and labels, inspect live cluster utilization (`kubectl top`),
or run historical cost breakdown queries in BigQuery (`bq`), use the
**`gke-cost-analysis`** skill. Once tracking is active and waste is diagnosed,
apply the optimization workflows below.

### 2. Configure Resource Quotas

Resource quotas restrict total resource consumption across tenants in
multi-tenant clusters, preventing runaway costs.

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute-quota
  namespace: {namespace}
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 16Gi
    limits.cpu: "8"
    limits.memory: 32Gi
EOF
```

### 3. Pod Rightsizing (VPA & MPA)

Adjust pod resource requests to match actual utilization. Over-provisioned
requests are one of the largest sources of waste.

-   **Use VPA in Recommendation Mode**:

```bash
# 1. Deploy VPA in recommendation mode
kubectl apply -f - <<EOF
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: {deployment_name}-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {deployment_name}
  updatePolicy:
    updateMode: "Off"
EOF

# 2. Wait 24+ hours for data collection

# 3. Read recommendations
kubectl get vpa {deployment_name}-vpa -o jsonpath='{.status.recommendation}'
```

-   **Optimization Rules:**

Condition                     | Action                             | Savings
----------------------------- | ---------------------------------- | -------
CPU request >5x P95 actual    | Reduce to `P95 * 1.2`              | High
Memory request >3x P95 actual | Reduce to `P95 * 1.2`              | High
CPU request >2x P95 actual    | Reduce to `P95 * 1.2`              | Medium
No resource requests set      | Add requests (enables bin-packing) | Medium

-   **Use MPA**: Reconcile HPA and VPA recommendations when scaling both
    horizontally and vertically to avoid conflicting scale events.
-   **Review Cost Recommendations**: Check Google Cloud Console (`Cost
    Management` > `GKE Cost Optimization`) for built-in rightsizing suggestions.

### 4. Spot VMs via ComputeClasses & NodeSelector

Use Spot VMs for fault-tolerant workloads to achieve 60-90% cost reduction.

#### 4.1 ComputeClass Configuration

```yaml
apiVersion: cloud.google.com/v1
kind: ComputeClass
metadata:
  name: spot-with-fallback
spec:
  activeMigration:
    optimizeRulePriority: true
  priorities:
  - machineFamily: n4
    spot: true
  - machineFamily: n4
    spot: false
```

#### 4.2 Direct Workload Spot Selection (`nodeSelector`)

For stateless or batch workloads in GKE Autopilot, target Spot capacity directly
using `nodeSelector`:

> [!WARNING] **Preemption Warning**: Spot VMs are interruptible and can be
> preempted at any time with a 30-second notice. Workloads must be
> fault-tolerant and run with at least 2 replicas for high availability. Always
> explicitly warn users about this preemption risk when recommending Spot VMs.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stateless-spot-app
spec:
  replicas: 2
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-provisioning: Spot
      terminationGracePeriodSeconds: 25  # Must be < 30s for Spot preemption handling
      containers:
      - name: app
        image: {image_name}
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "sleep 5"]
```

**Spot-Suitable Workloads:**

Workload                          | Spot-Suitable?
--------------------------------- | ---------------
Batch / data processing           | Yes
Dev / test environments           | Yes
Stateless web/API (replicas >= 2) | Yes (with PDBs)
Jobs with checkpointing           | Yes
Stateful workloads (databases)    | No
Single-replica critical services  | No

### 5. Machine Type Selection

When choosing node shapes or configuring ComputeClasses:

| Family        | Use Case                                     | Relative Cost |
| ------------- | -------------------------------------------- | ------------- |
| e2            | General purpose, burstable                   | Lowest        |
| t2a / t2d     | Scale-out (Arm/AMD), price-performance       | Low           |
:               : optimized                                    :               :
| n4a           | Axion Arm-based, general-purpose             | Low           |
:               : price-performance                            :               :
| n4 / n4d      | General purpose (Intel/AMD), flexible shapes | Low-Medium    |
| c4a           | Compute-optimized (Arm), high efficiency     | Medium-High   |
| c3 / c4       | Compute-optimized (Intel)                    | Medium-High   |
| c3d / c4d     | Compute-optimized (AMD), high throughput     | Medium-High   |
| ek-standard   | Autopilot enhanced (golden path)             | Medium        |
| m3 / x4       | Memory-optimized, SAP HANA, large databases  | High          |
| g2 (L4 GPU)   | AI inference                                 | High          |
| a3 (H100 GPU) | AI training                                  | Highest       |
| a4 / a4x      | Ultra-scale AI (Blackwell GPUs)              | Highest       |

### 6. Committed Use Discounts (CUDs)

For steady-state workloads with predictable baseline usage, purchase 1-year or
3-year CUDs:

-   1-year: ~20-30% discount
-   3-year: ~50-55% discount
-   Applied automatically to matching usage across the region.
-   Purchase via Google Cloud Console > Billing > Committed use discounts.

### 7. Cluster Management & Multi-Tenancy

-   **Stop/start dev clusters**: Idle dev clusters cost money even with no
    workloads due to control plane fees.
-   **Right-size node pools (Standard)**: Use Cluster Autoscaler with
    appropriate min/max limits.
-   **Multi-tenant consolidation**: Share a single cluster across multiple
    engineering teams instead of maintaining per-team clusters, using Namespaces
    and ResourceQuotas to isolate workloads.

## Cost & Utilization Monitoring

To inspect live node/pod utilization (`kubectl top nodes/pods`), view cluster
cost budgets (`gcloud billing budgets list`), or query detailed billing reports
in BigQuery (`bq query`), refer to the **`gke-cost-analysis`** skill.

## Dev/Test Cost Savings

For non-production environments, the following golden path deviations provide
cost efficiency without impacting production safety:

| Setting                 | Production (Golden | Dev/Test                      |
:                         : Path)              :                               :
| ----------------------- | ------------------ | ----------------------------- |
| Cluster mode            | Autopilot          | Autopilot (cheaper with fewer |
:                         :                    : pods)                         :
| Release channel         | Regular            | Rapid (get fixes faster)      |
| Private nodes           | Required           | Optional (simpler access)     |
| Monitoring components   | Full suite         | `SYSTEM_COMPONENTS` only      |
| Secret Manager rotation | 120s               | Disabled                      |
| Maintenance windows     | Configured         | Not needed                    |

## Best Practices Summary

1.  **Enable Cost Allocation**: Always enable GKE cost allocation
    (`--enable-cost-allocation`) to gain billing transparency across namespaces
    and labels.
2.  **Enforce Resource Quotas**: Restrict namespace CPU/memory limits in
    multi-tenant environments to prevent runaway costs or noisy neighbors.
3.  **Rightsize Continuously**: Run VPA in recommendation mode (`updateMode:
    Off`) and adjust requests to match `P95 * 1.2`.
4.  **Leverage Spot VMs**: Use Spot VMs with `nodeSelector` or `ComputeClass`
    for stateless, fault-tolerant workloads to save 60-90%.
5.  **Optimize Autoscaling Profile**: Use `OPTIMIZE_UTILIZATION` for aggressive
    node scale-down on idle compute.
6.  **Consolidate & Clean Up**: Stop idle development clusters and consolidate
    multi-team workloads into shared multi-tenant clusters.
