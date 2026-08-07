---
name: gke-workload-troubleshooting
metadata:
  category: Containers
description: >-
  Diagnoses GKE workload failures (CrashLoopBackOff, OOMKilled, ImagePullBackOff, Pending, etc.) via logs and events. Use when pods fail to start or crash repeatedly. Don't use for GKE cluster infrastructure provisioning, node pool creation, or non-Kubernetes Google Cloud services.
---

# GKE Workload Troubleshooting Skill

Use this skill to systematically diagnose and resolve failures in application
workloads deployed in GKE clusters. This skill operates non-interactively and
enforces a read-only diagnostics boundary before proposing manifest or config
corrections.

## 🔍 Diagnostic Workflow

### Step 0: Non-Interactive Context Discovery & Time Window Definition

1.  **Parameter Extraction**: Extract required context (`project_id`,
    `cluster_name`, `cluster_location`, `workload_name`, `workload_namespace`)
    non-interactively from the user prompt, active `SETTINGS.md`, or active
    environment defaults:

    -   Default `workload_namespace` to `default` if omitted.
    -   Infer missing cluster parameters from active environment (`kubectl
        config current-context` or `gcloud config get-value project`).
    -   Prioritize non-interactive context discovery from prompts and
        environment defaults to ensure autonomous execution flow.

2.  **Cluster Credentials & Fallback Mode**:

    -   Attempt credential fetch: `gcloud container clusters get-credentials
        {cluster_name} --region/--zone {cluster_location}`
    -   **Fallback / Dry-Run Mode**: If the cluster is unreachable,
        non-existent, or live command execution fails (such as in sandboxed
        evaluations, dry-run mode, or offline analysis):
        -   Limit retry attempts to avoid resource exhaustion and context
            overflow in unreachable cluster scenarios.
        -   Immediately present the exact sequence of `kubectl` diagnostic
            commands for the human operator to run.
        -   Synthesize the root cause analysis and output the proposed GitOps
            manifest fix based on the reported symptoms.

3.  **Time Handling & Fallbacks**:

    -   **Determine Issue Timestamp ({issue_time})**:
        -   **Specific Time Provided**: If the user provides a specific
            timestamp, use it as `{issue_time}`.
        -   **Relative Time Provided (e.g., "5 minutes ago")**: Dynamically
            calculate the corresponding UTC timestamp based on current system
            time, and use it as `{issue_time}`.
        -   **No Time Provided (Default)**: Use current system time as
            `{issue_time}`.
    -   **Window Calculation**: Center a 1-hour query window around
        `{issue_time}` (`start_time` = `{issue_time} - 30m`, `end_time` =
        `{issue_time} + 30m`).

--------------------------------------------------------------------------------

### Step 1: Analyze Pod Status and Conditions

Inspect the workload's active pod states and controller status.

**Diagnostic Commands:**

```bash
# 1. Inspect the deployment's actual selector labels:
kubectl get deployment {workload_name} -n {workload_namespace} -o jsonpath='{.spec.selector.matchLabels}'
# 2. Query the pods using the returned labels, for example:
kubectl get pods -l {selector_labels} -n {workload_namespace}
kubectl get deploy/{workload_name} -n {workload_namespace} -o yaml
```

#### Diagnostic Decision Tree:

-   **Phase: Pending**:
    -   The Pod cannot schedule on any node. Proceed directly to **Step 2 (Query
        Namespace Events)**.
-   **State: CrashLoopBackOff / Error**:

    -   Container is booting but exiting repeatedly. Check the terminated status
        using:

    ```bash
    kubectl get pod {pod_name} -n {workload_namespace} -o jsonpath='{.status.containerStatuses[*].lastState.terminated}'
    ```

    -   **ExitCode: 137 (OOMKilled)**: Memory limit reached. Proceed to **Step 3
        (Inspect Logs)** and inspect container startup command to differentiate
        between an application-level memory leak/loop vs an infrastructure
        capacity limit mismatch, then proceed to **Step 5** to propose fixes.
    -   **ExitCode: 1 or other non-zero codes**: The application code crashed.
        Proceed directly to **Step 3 (Inspect Logs)**.

-   **State: ContainerCreating**:

    -   The container is blocked during volume mount, networking setup, or image
        pulling. Proceed directly to **Step 2 (Query Namespace Events)**.

--------------------------------------------------------------------------------

### Step 2: Query Namespace Events

Look for infrastructure, volume, image, or scheduling alerts in GKE.

**Diagnostic Command:**

```bash
kubectl get events -n {workload_namespace} --sort-by='.metadata.creationTimestamp'
# Or query Cloud Logging for historical GKE events within the time window:
gcloud logging read "resource.type=\"k8s_cluster\" AND logName=\"projects/{project_id}/logs/events\" AND jsonPayload.involvedObject.namespace=\"{workload_namespace}\"" --start-time="{start_time}" --end-time="{end_time}" --project="{project_id}"
```

*Note: Retrieve the sorted events list and manually inspect the event timestamps
(CreationTimestamp/LastSeen) to identify failures occurring within the
`{start_time}` and `{end_time}` window.*

#### Signature Identifiers:

-   **`FailedScheduling`**: Node resource exhaustion. Look for messages like
    `0/3 nodes are available: 3 Insufficient memory.` or missing node affinity
    tolerations (e.g. Spot VM taints).
-   **`FailedMount`**:
    -   Missing PersistentVolumeClaim (`PVC`).
    -   Missing Secret (`Secret "{secret_name}" not found`).
    -   Missing ConfigMap (`ConfigMap "{configmap_name}" not found`).
-   **`Failed` / `BackOff` (Image Pull)**:
    -   Wrong image tag, missing image registry authentication (e.g.,
        ImagePullBackOff).
    -   **Resolution Steps for Wrong Image Tag**:
    *   Identify the failing container image name and the invalid tag.
    *   Check the Git repository history for the last known working image tag
        for this workload. Run `git log -p -S "{image_name}" --
        {manifest_file_path}` (or use `git log` on the folder containing
        manifests) to identify the previous working tag in Git.
    *   If the invalid tag is a recent change in git history, compare it to the
        tag from the last successful commit.
    *   Propose reverting the image tag to the last working version, or
        correcting the tag version in the manifest patch.

--------------------------------------------------------------------------------

### Step 3: Inspect Application Logs

Extract exceptions and stack traces from the application runtime.

**Diagnostic Commands:**

```bash
# Check current active log stream (handles multi-container pods)
kubectl logs {pod_name} -n {workload_namespace} --all-containers --tail=100

# Check logs from previously terminated container instances (handles multi-container pods)
kubectl logs {pod_name} -n {workload_namespace} --all-containers -p --tail=100
```

#### Signature Identifiers:

-   **Out-of-Memory (OOM) Analysis**: Inspect container logs and startup
    commands (`spec.containers[*].command`). Differentiate between an
    **Application Code Leak/Loop** (unbounded array appending, memory leak
    signatures) vs an **Infrastructure Capacity Ceiling Mismatch** (legitimate
    workload demand exceeding limits).
-   **Stack Trace / Unhandled Exception**: Look for language-specific stack
    traces (e.g., `panic:`, `NullPointerException`, `Traceback (most recent
    call)`). This indicates an application bug.
-   **Egress Network Timeout**: Look for connection timeouts (e.g., `Connection
    timed out`, `dial tcp: i/o timeout`). Proceed to **Step 4 (Verify
    Connectivity)**.
-   **Permission Errors (ReadOnlyRootFilesystem)**: Look for write errors (e.g.,
    `Read-only file system`, `Permission denied` when writing to `/tmp` or
    `/var/log`). Propose adding an `emptyDir` volume mount to that directory in
    the manifest.

--------------------------------------------------------------------------------

### Step 4: Verify Service Connectivity and Network Policies

Troubleshoot connection drops to other services.

**Diagnostic Commands:**

```bash
# Verify target endpoint is active
kubectl get endpoints {target_service_name} -n {target_namespace}

# Query network policies inside namespace
kubectl get networkpolicies -n {workload_namespace} -o yaml
```

#### Logic & Dry-Run Fallback:

1.  **Live Cluster Mode**:

    -   If `kubectl get endpoints` returns an empty list, the target
        microservice itself is failing to schedule or boot (troubleshoot target
        service).
    -   If endpoints exist but logs show timeouts, analyze `NetworkPolicy`
        egress blocks to verify if egress traffic to the target service's
        IP/port is allowed.

2.  **Sandboxed / Dry-Run Mode**:

    -   If live `kubectl` queries fail or cluster connection is unavailable, do
        NOT retry live cluster access or enter repetitive connection attempts.
    -   Immediately inspect the application source code (e.g. `worker.py`,
        `app.go`, DB connection strings) or Deployment manifests to identify the
        target service hostname (e.g. `account-db`) and destination port (e.g.
        `5432`).
    -   Present the exact `kubectl get endpoints` and `kubectl get
        networkpolicies` commands for the user, and synthesize the required
        `NetworkPolicy` egress patch allowing traffic to the target service and
        port.

--------------------------------------------------------------------------------

### Step 5: Propose GitOps Correction

Following the GitOps boundary, **do not apply patches directly to the cluster**.

1.  Synthesize the root cause analysis for the human operator (e.g.
    *"payment-api is failing with exit code 137 because its memory limit is set
    to 256Mi while actual usage spiked to 270Mi"*).
2.  Generate the corrected YAML manifest patch (e.g. increase memory limits, add
    missing Secret mounts, or add tolerations for Spot nodes).
3.  Check if a branch or Pull Request (PR) already exists for this
    workload/failure. If so, update the existing branch/PR or notify the user
    instead of creating a duplicate. Otherwise, create a branch, commit the
    change, open a Pull Request (PR) on GitHub, and conclude the workflow (do
    not wait for human merge).
