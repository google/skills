---
name: gke-ai-troubleshooting-jobset-interruption
metadata:
  category: Containers
description: >-
  Diagnoses GKE JobSet interruptions, restarts, and preemptions for AI/ML training workloads autonomously.
  Use when troubleshooting JobSet restart loops, spot VM preemptions, node readiness failures, host VM issues, or coordinator worker crashes.
  Don't use for general GKE cluster creation, basic workload deployment, or non-JobSet application issues.
---

# GKE JobSet Interruption Troubleshooting

Use this skill to systematically diagnose and resolve JobSet interruptions,
restarts, and preemptions on GKE clusters hosting large-scale AI/ML workloads.

## ⚠️ Prerequisites & Sandbox Rules

-   JobSet metrics package must be enabled in `kube-state-metrics` for your
    cluster.
-   Cloud Logging and Cloud Monitoring enabled for the Google Cloud Project.
-   **Autonomous & Sandbox Execution Rule**: If API queries, tools, or commands
    encounter `403 Permission Denied`, authentication errors, or network
    isolation, **do NOT enter authentication or credential troubleshooting
    loops**. Populate the query templates with the acquired variables
    (`{project_id}`, `{cluster_name}`, `{workload_name}`, `{start_time}`,
    `{end_time}`), inspect any locally staged telemetry or mock data files if
    available, and complete the diagnostic workflow and resolution
    recommendations autonomously.

## 🔍 Diagnostic Workflow

### Step 0: Context Acquisition & Time Window Definition

Independently gather context using tools, workspace files, environment details,
or user prompt context:

-   **Project ID** (`{project_id}`)
-   **Cluster Name** (`{cluster_name}`)
-   **Workload Name (JobSet Name)** (`{workload_name}`)
-   **Workload Namespace** (`{namespace}`)
-   **Issue Time** (`{issue_time}`)

If specific variables are not explicitly provided by the user, inspect cluster
resources or logs to determine them, or use the `{variable}` placeholders
provided.

#### Time Handling Rules

1.  **Autonomous Time Window**: If a relative time (e.g., "X minutes ago") or no
    exact timestamp is provided, calculate the query window based on current
    time or available log timestamps.
2.  **Window Calculation**: If a timestamp `{issue_time}` is available (or
    calculated as `T`), set `{start_time}` = `T - 30m` and `{end_time}` = `T +
    30m`.

--------------------------------------------------------------------------------

### Step 1: Identify JobSet Restarts and Attempts [Low Risk]

Verify if the JobSet is experiencing restart loops and determine the frequency
of restarts.

#### Visual Chart / MQL Query - restarts

-   **MQL Query Specification**:

    ```mql
    fetch prometheus_target
    | metric 'prometheus.googleapis.com/kube_jobset_restarts/gauge'
    | filter resource.cluster_name == '{cluster_name}' && metric.jobset_name == '{workload_name}'
    | align next_older(1m)
    | every 1m
    | group_by [metric.jobset_name], [val: max(value)]
    ```

#### PromQL Metric Query - restarts

-   **PromQL Query Specification**:

    ```promql
    kube_jobset_restarts{jobset_name="{workload_name}", cluster="{cluster_name}"}
    ```

-   **Diagnostic Logic**: A non-zero or increasing value for restarts indicates
    that the JobSet is being actively restarted by the controller due to worker
    failure or interruption.

-   **Automation**: Proceed to Step 2 automatically after reporting findings.

--------------------------------------------------------------------------------

### Step 2: Inspect Nodepool Interruptions [Low Risk]

Determine if the JobSet restarts were triggered by physical nodepool-level
events (such as spot preemptions, maintenance, or host terminations).

#### A. Metrics Query (Nodepool Interruption Counts)

##### Visual Chart / MQL Query - interruptions

-   **MQL Query Specification**:

    ```mql
    fetch k8s_node_pool
    | metric 'kubernetes.io/node_pool/interruption_count'
    | filter cluster_name == '{cluster_name}'
    | align next_older(10m)
    | every 10m
    | group_by [metric.interruption_type, metric.interruption_reason, metadata.system.node_pool_name], [val: sum(value)]
    ```

##### PromQL Query - interruptions

-   **PromQL Query Specification**:

    ```promql
    sum by (interruption_type, interruption_reason, node_pool_name, cluster_name) (
      avg_over_time(kubernetes_io:node_pool_interruption_count{cluster_name="{cluster_name}"}[10m])
    )
    ```

#### B. Log Query (Nodepool Life Events)

-   **LQL Log Filter Specification**:

    ```sql
    resource.type="gke_nodepool"
    AND resource.labels.cluster_name="{cluster_name}"
    AND timestamp >= "{start_time}"
    AND timestamp <= "{end_time}"
    ```

-   **Diagnostic Logic**:

    -   **PreemptionEvent**: Spot VMs were preempted, or node was scale-down.
    -   **MaintenanceEvent**: Node pool updated or Google scheduled maintenance.
    -   **TerminationEvent**: Serious host failures. Check `interruption_reason`
        or logs for host issues.
    -   See [Failure Signatures](references/failure_signatures.md) for examples
        of node termination logs and preemption events.

-   **Automation**: Proceed to Step 3 automatically.

--------------------------------------------------------------------------------

### Step 3: Inspect Nodes and Underlying Host VMs [Low Risk]

Correlate node readiness failures with physical host VMs to see if a single
faulty host repeatedly fails coordinator pods.

#### A. Metrics Query (Node Ready Status Check)

##### Visual Chart / MQL Query - node status

-   **MQL Query Specification**:

    ```mql
    fetch k8s_node
    | metric 'kubernetes.io/node/status_condition'
    | filter cluster_name == '{cluster_name}' && metric.condition == 'Ready' && metric.status == 'False'
    | align next_older(1m)
    | every 1m
    | group_by [node_name, metadata.user.gke_nodepool], [val: max(value)]
    ```

##### PromQL Query - node status

-   **PromQL Query Specification**:

    ```promql
    sum by (status, condition, node_pool_name) (
      kubernetes_io:node_status_condition{cluster_name="{cluster_name}", condition="Ready", status="False"}
    )
    ```

#### B. Metrics Query (Node-to-Host Metadata Topology Correlation)

-   **MQL Query Specification**:

    ```mql
    fetch k8s_node
    | metric 'kubernetes.io/node/cpu/total_cores'
    | filter cluster_name == '{cluster_name}'
    | align next_older(1m)
    | every 1m
    | group_by [node_name, metadata.user.gce_topology_host, metadata.user.gke_nodepool], [val: max(value)]
    ```

#### C. Log Query (Node Fault Logs)

-   **LQL Log Filter Specification**:

    ```sql
    resource.type="k8s_node"
    AND resource.labels.cluster_name="{cluster_name}"
    AND (textPayload:"host error" OR textPayload:"kernel panic" OR textPayload:"hardware failure" OR textPayload:"NodeNotReady")
    AND timestamp >= "{start_time}"
    AND timestamp <= "{end_time}"
    ```

-   **Diagnostic Logic**: Identify if specific nodes are unhealthy
    (`Ready=False` or `Unknown`) and correlate them to their GCE physical host
    ID via `metadata.user.gce_topology_host`. Check if the same host is
    repeatedly failing.

-   **Automation**: Proceed to Step 4 automatically.

--------------------------------------------------------------------------------

### Step 4: Inspect Pod and Worker / Container Failures [Low Risk]

Analyze pod status phases and retrieve coordinator worker logs to identify
application-level crashes or network deadlocks.

> **Required Execution Order**: You MUST analyze pod status phases (Section A)
> and unschedulable pod metrics (Section B) to assess overall workload health
> before inspecting specific worker container logs (Section C).

#### A. Metrics Query (Pod Lifecycle Phases)

##### Visual Chart / MQL Query - pod phase

-   **MQL Query Specification**:

    ```mql
    fetch k8s_pod
    | metric 'kubernetes.io/pod/status/phase'
    | filter cluster_name == '{cluster_name}' && pod_name ==~ '{workload_name}.*'
    | align next_older(10m)
    | every 10m
    | group_by [metric.phase], [val: count()]
    ```

##### PromQL Query - pod phase

-   **PromQL Query Specification**:

    ```promql
    sum by (phase) (
      avg_over_time(kube_pod_status_phase{cluster="{cluster_name}", pod=~"{workload_name}.*"}[10m])
    )
    ```

#### B. Metrics Query (Unschedulable Pod Count)

-   **MQL Query Specification**:

    ```mql
    fetch k8s_pod
    | metric 'kubernetes.io/pod/status/unschedulable'
    | filter cluster_name == '{cluster_name}' && pod_name ==~ '{workload_name}.*'
    | align next_older(10m)
    | every 10m
    | group_by [pod_name], [val: max(value)]
    ```

#### C. Log Query (Worker Container Logs)

-   **LQL Log Filter Specification**:

    ```sql
    resource.type="k8s_container"
    AND resource.labels.cluster_name="{cluster_name}"
    AND labels."k8s-pod/jobset_sigs_k8s_io/jobset-name"="{workload_name}"
    AND timestamp >= "{start_time}"
    AND timestamp <= "{end_time}"
    ```

-   **Diagnostic Logic**:

    1.  Check the pod timeline to spot pending or unschedulable pods.
    2.  Use worker container logs to analyze worker 0 in slice 0 (coordinator)
        for NCCL timeouts, collective communication issues, or MegaScale hangs.

-   **Automation**: Proceed to Resolution.

--------------------------------------------------------------------------------

## 🛠️ Resolution Workflow

### Resolution 1: Preemption & Autoscaling Optimizations [Low Risk]

If Step 2 showed high preemption counts on Spot VMs:

-   **Action**: Suggest switching critical long-running training workloads to
    **GKE Reserved/On-Demand VMs** or utilizing **Compact Placement Policies**
    to minimize defragmentation interruptions.
-   **Justification**: Eliminates spot-market preemptions and reduces training
    restarts.

### Resolution 2: Quarantine Faulty Host VMs [High Risk]

If Step 3 identified a specific host ID (`gce-topology-host`) that consistently
fails or triggers restarts across multiple attempts:

-   **Action**: Recommend cordoning/draining the GKE node, deleting the
    underlying GCE VM instance to trigger instance recreation, and opening a
    support ticket with Google Cloud Support specifying the physical host ID.
-   **Justification**: GKE auto-repair will recreate the VM instance on healthy
    physical hardware, preventing infinite restart loops.

--------------------------------------------------------------------------------

## 📋 Copypaste Checklist

-   [ ] Gather context and compute `{start_time}` (`{issue_time} - 30m`) and
    `{end_time}` (`{issue_time} + 30m`) window.
-   [ ] Query JobSet restart attempts.
-   [ ] Check Nodepool interruptions (spot preemptions vs. hardware
    terminations).
-   [ ] Query node-to-host mapping and check node logs for physical host errors.
-   [ ] Inspect pod timeline status and coordinator worker container logs.
-   [ ] Recommend appropriate scheduling strategy (On-demand vs Spot) or host VM
    quarantining.
