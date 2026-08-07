---
name: gke-tpu-metrics-monitoring
description: >-
  Monitors and troubleshoots GKE TPU workloads, nodes, and node pools using GKE
  system metrics and PromQL. Use when monitoring TensorCore duty cycle, TPU memory,
  node readiness, multi-host TPU node pool availability, host maintenance or
  preemption interruptions, and calculating MTTR or MTBI metrics for GKE TPUs.
  Don't use for general non-TPU GKE workload monitoring or non-metric TPU debugging.
metadata:
  category: CloudObservabilityAndMonitoring
---

# GKE TPU Metrics Monitoring Guide

This skill enables the agent to monitor GKE TPU workloads, nodes, and node pools using GKE system metrics. It helps diagnose if workload interruptions or performance issues are caused by underlying infrastructure.

## Step 0: Mandatory Context

Independently gather required context (such as cluster details or node pool names) using available GKE and Cloud tools, or use the provided `{variable}` placeholders:

- `{project_id}`: The GCP Project ID.
- `{cluster_name}`: The GKE Cluster Name.
- `{location}`: The GKE Cluster Location (region or zone).
- `{node_name}`: (Optional) The name of the specific GKE node.
- `{node_pool_name}`: (Optional) The name of the GKE node pool.

---

## Diagnostic Steps

### Step 1: Verify TPU Runtime Metrics Configuration [Low Risk] [Auto]

Before analyzing runtime metrics, verify that the workload is configured to export them.

- **Action**: Verify that the Pod specification for the TPU workload includes:
  - `containerPort: 8431`
  - JAX version `0.4.14` or later (if using JAX).
  - GKE version is `1.27.4-gke.900` or later.
  - GKE System Metrics are enabled on the cluster.

### Step 2: Monitor TPU Runtime Metrics [Low Risk] [Auto]

If configured correctly, the following metrics are available in Cloud Monitoring (monitored resources `k8s_node` and `k8s_container`):

- **Container Metrics**:
  - `kubernetes.io/container/accelerator/duty_cycle`: Percentage of time over the past sampling period (60 seconds) during which the TensorCores were actively processing on a TPU chip.
  - `kubernetes.io/container/accelerator/memory_used`: Amount of accelerator memory allocated in bytes.
  - `kubernetes.io/container/accelerator/memory_total`: Total accelerator memory in bytes.
- **Node Metrics**:
  - `kubernetes.io/node/accelerator/duty_cycle`
  - `kubernetes.io/node/accelerator/memory_used`
  - `kubernetes.io/node/accelerator/memory_total`

### Step 3: Check Node Status Condition [Low Risk] [Auto]

Query the status condition of GKE nodes (GKE version `1.32.1-gke.1357001` or later).

- **PromQL Query (Check if a specific node is Ready)**:
  ```promql
  kubernetes_io:node_status_condition{monitored_resource="k8s_node", cluster_name="{cluster_name}", node_name="{node_name}", condition="Ready", status="True"}
  ```
- **PromQL Query (List nodes with non-Ready conditions that are True)**:
  ```promql
  kubernetes_io:node_status_condition{monitored_resource="k8s_node", cluster_name="{cluster_name}", condition!="Ready", status="True"}
  ```
- **PromQL Query (List nodes that are NOT Ready)**:
  ```promql
  kubernetes_io:node_status_condition{monitored_resource="k8s_node", cluster_name="{cluster_name}", condition="Ready", status="False"}
  ```
- **PromQL Query (Fleet-wide node status)**:
  ```promql
  avg by (condition,status)(avg_over_time(kubernetes_io:node_status_condition{monitored_resource="k8s_node"}[5m]))
  ```

### Step 4: Check Node Pool Status [Low Risk] [Auto]

Query the status of multi-host TPU node pools.

- **PromQL Query (Verify if a specific node pool is Running)**:
  ```promql
  kubernetes_io:node_pool_status{monitored_resource="k8s_node_pool", cluster_name="{cluster_name}", node_pool_name="{node_pool_name}", status="Running"}
  ```
- **PromQL Query (Monitor node pools grouped by status)**:
  ```promql
  count by (status)(count_over_time(kubernetes_io:node_pool_status{monitored_resource="k8s_node_pool"}[5m]))
  ```
  _Possible statuses_: `Provisioning`, `Running`, `Error`, `Reconciling`, `Stopping`.

### Step 5: Check Node Pool Availability [Low Risk] [Auto]

Query if all nodes in a multi-host TPU node pool are available.

- **PromQL Query (Check availability over time)**:
  ```promql
  avg by (node_pool_name)(avg_over_time(kubernetes_io:node_pool_multi_host_available{monitored_resource="k8s_node_pool", cluster_name="{cluster_name}"}[5m]))
  ```
  _Value_: `1` (True, all nodes available) or `0` (False, some nodes unavailable).

### Step 6: Analyze Node Interruptions [Low Risk] [Auto]

Query the count of interruptions for GKE nodes.

- **PromQL Query (Breakdown of interruptions and causes)**:
  ```promql
  sum by (interruption_type,interruption_reason)(sum_over_time(kubernetes_io:node_interruption_count{monitored_resource="k8s_node"}[5m]))
  ```
  _Interruption Types_: `TerminationEvent`, `MaintenanceEvent`, `PreemptionEvent`.
  _Interruption Reasons_: `HostError`, `Eviction`, `AutoRepair`.
- **PromQL Query (Filter for Host Maintenance events)**:
  ```promql
  sum by (interruption_type,interruption_reason)(sum_over_time(kubernetes_io:node_interruption_count{monitored_resource="k8s_node", interruption_reason="HW/SW Maintenance"}[5m]))
  ```
- **PromQL Query (Interruption count aggregated by node pool)**:
  ```promql
  sum by (node_pool_name,interruption_type,interruption_reason)(sum_over_time(kubernetes_io:node_pool_interruption_count{monitored_resource="k8s_node_pool", interruption_reason="HW/SW Maintenance", node_pool_name="{node_pool_name}"}[5m]))
  ```

### Step 7: Calculate Recovery and Interruption Metrics [Low Risk] [Auto]

Calculate Mean Time to Recovery (MTTR) and Mean Time Between Interruptions (MTBI) over the last 7 days.

- **PromQL Query (MTTR - Mean Time to Recovery)**:
  ```promql
  sum(sum_over_time(kubernetes_io:node_pool_accelerator_times_to_recover_sum{monitored_resource="k8s_node_pool", cluster_name="{cluster_name}"}[7d])) / sum(sum_over_time(kubernetes_io:node_pool_accelerator_times_to_recover_count{monitored_resource="k8s_node_pool",cluster_name="{cluster_name}"}[7d]))
  ```
- **PromQL Query (MTBI - Mean Time Between Interruptions)**:
  ```promql
  sum(count_over_time(kubernetes_io:node_memory_total_bytes{monitored_resource="k8s_node", node_name=~"gke-tpu.*|gk3-tpu.*", cluster_name="{cluster_name}"}[7d])) / sum(sum_over_time(kubernetes_io:node_interruption_count{monitored_resource="k8s_node", node_name=~"gke-tpu.*|gk3-tpu.*", cluster_name="{cluster_name}"}[7d]))
  ```

### Step 8: Monitor TPU Host Metrics [Low Risk] [Auto]

For GKE version `1.28.1-gke.1066000` or later, monitor TPU host performance.

- **Container Metrics**:
  - `kubernetes.io/container/accelerator/tensorcore_utilization`: Current percentage of the TensorCore that is utilized.
  - `kubernetes.io/container/accelerator/memory_bandwidth_utilization`: Current percentage of the accelerator memory bandwidth that is being used.
- **Node Metrics**:
  - `kubernetes.io/node/accelerator/tensorcore_utilization`
  - `kubernetes.io/node/accelerator/memory_bandwidth_utilization`

