---
name: gke-cost-optimization
description: >-
  Optimizes GKE costs, rightsizes workloads, and configures Spot VMs, CUDs, cost
  allocation, and resource quotas. Use when optimizing GKE cluster or workload
  costs, configuring GKE cost allocation or quotas, rightsizing CPU/memory
  requests, or selecting Spot VMs and machine types. Don't use for general
  compute class provisioning or GPU Selection (use gke-compute-classes instead).
metadata:
  version: "1.0.2"
  category: CloudObservabilityAndMonitoring
---

# GKE Cost Optimization

This reference covers strategies and workflows for reducing Google Kubernetes
Engine (GKE) costs while maintaining a secure and reliable posture.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:gke-cost-optimization)"`
and append `agent-skills/1.0 (skill:gke-cost-optimization)` to `User-Agent`
headers.

## Workflows & Optimization Strategies

### 1. Prerequisite: Cost Allocation & Monitoring

To enable GKE cost allocation (`--enable-cost-allocation`) for billing tracking
across namespaces and labels, inspect live cluster utilization (`kubectl top`),
or run historical cost breakdown queries in BigQuery (`bq`), use the
**`gke-cost-analysis`** skill. Once tracking is active and waste is diagnosed,
apply the optimization workflows below.

### 2. Configure Resource Quotas

Resource quotas restrict total resource consumption across tenants in
multi-tenant clusters, preventing runaway costs. Template:
[assets/resource-quota-example.yaml](assets/resource-quota-example.yaml)
(set namespace + `hard` limits, then `kubectl apply -f`).

### 3. Pod Rightsizing (VPA & MPA)

Adjust pod resource requests to match actual utilization. Over-provisioned
requests are one of the largest sources of waste.

-   **Use VPA in Recommendation Mode** (`updateMode: "Off"` — recommends
    without evicting):

```bash
# 1. Deploy VPA in recommendation mode (template: assets/vpa-recommendation-mode.yaml)
kubectl apply -f assets/vpa-recommendation-mode.yaml
# 2. Wait 24+ hours for data collection, then read recommendations
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

For a Spot-first ComputeClass with On-Demand fallback (priority ordering,
`activeMigration`, machine family selection), use the **`gke-compute-classes`**
skill — ComputeClass YAML generation and priority configuration are its domain,
not this skill's.

#### 4.2 Direct Workload Spot Selection (`nodeSelector`)

For stateless or batch workloads in GKE Autopilot, target Spot capacity directly
using `nodeSelector`:

> [!WARNING] **Preemption Warning**: Spot VMs are interruptible and can be
> preempted at any time with a 30-second notice. Workloads must be
> fault-tolerant and run with at least 2 replicas for high availability. Always
> explicitly warn users about this preemption risk when recommending Spot VMs.

The exact Pod-level selector is:

```yaml
nodeSelector:
  cloud.google.com/gke-spot: "true"
```

Full worked Deployment (replicas >= 2, `terminationGracePeriodSeconds: 25`,
`preStop` hook): [assets/spot-deployment-example.yaml](assets/spot-deployment-example.yaml).

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

| Family        | Use Case                                          | Relative Cost |
| ------------- | ------------------------------------------------- | ------------- |
| e2            | General purpose, burstable                        | Lowest        |
| t2a / t2d     | Scale-out (Arm/AMD), price-performance optimized  | Low           |
| n4a           | Axion Arm-based, general-purpose price-performance | Low          |
| n4 / n4d      | General purpose (Intel/AMD), flexible shapes      | Low-Medium    |
| c4a           | Axion Arm-based, general-purpose, high efficiency | Medium        |
| c3 / c4       | Compute-optimized (Intel)                         | Medium-High   |
| c3d / c4d     | Compute-optimized (AMD), high throughput          | Medium-High   |
| ek-standard   | Autopilot enhanced                                | Medium        |
| m3 / x4       | Memory-optimized, SAP HANA, large databases       | High          |
| g2 (L4 GPU)   | AI inference                                      | High          |
| a3 (H100 GPU) | AI training                                       | Highest       |
| a4 / a4x      | Ultra-scale AI (Blackwell GPUs)                   | Highest       |

### 6. Committed Use Discounts (CUDs)

For steady-state workloads with predictable baseline usage, purchase 1-year or
3-year CUDs:

-   **Resource-based CUDs** (committed to a machine family/region): roughly
    high-30s% discount for 1-year, ~55% for 3-year (varies by machine family).
-   **Flexible CUDs** (spend-based, portable across families/regions): lower
    discounts (~28% 1-year, ~46% 3-year) in exchange for flexibility.
-   **Autopilot:** Autopilot-specific CUDs were retired in January 2026 — new
    commitments covering Autopilot usage are spend-based Compute Flexible CUDs
    (existing Autopilot CUD commitments run out their term).
-   Applied automatically to matching usage across the region.
-   Purchase via Google Cloud Console > Billing > Committed use discounts.

**Size the commitment to the steady-state baseline only.** A commitment bills
for the full term whether or not you use it, so over-committing to peak usage
converts a discount into waste. Measure the floor of actual usage over a
representative period, commit to that, and cover everything above it with the
elastic options already in this skill:

-   **Baseline** (always running) → resource-based CUDs.
-   **Variable / bursty** → autoscaling on on-demand capacity.
-   **Interruption-tolerant** (batch, CI, stateless workers) → Spot VMs, which
    stack with autoscaling and need no commitment.

When recommending CUDs, state the split explicitly rather than implying the
whole footprint should be committed.

### 7. Cluster Management & Multi-Tenancy

-   **Idle dev clusters**: GKE has no stop/start operation, and the cluster
    management fee accrues as long as the cluster exists. To cut idle costs,
    scale node pools to zero (`gcloud container clusters resize {cluster_name}
    --node-pool {pool_name} --num-nodes 0`) or delete and recreate the cluster
    via IaC (Terraform/Config Connector).
-   **Right-size node pools (Standard)**: Use Cluster Autoscaler with
    appropriate min/max limits.
-   **Cheap warm headroom instead of overprovisioned nodes**: Standby capacity
    buffers (GKE 1.37.1-gke.3020000+) keep pre-initialized nodes
    suspended — you pay only disk + IP instead of full node price, with ~30s
    resume. See the **`gke-cluster-autoscaler`** skill.
-   **Multi-tenant consolidation**: Share a single cluster across multiple
    engineering teams instead of maintaining per-team clusters, using Namespaces
    and ResourceQuotas to isolate workloads.

## Cost & Utilization Monitoring

To inspect live node/pod utilization (`kubectl top nodes/pods`), view cluster
cost budgets (`gcloud billing budgets list`), or query detailed billing reports
in BigQuery (`bq query`), refer to the **`gke-cost-analysis`** skill.
