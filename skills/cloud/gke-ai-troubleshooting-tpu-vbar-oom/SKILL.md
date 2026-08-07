---
name: gke-ai-troubleshooting-tpu-vbar-oom
description: >-
  Diagnoses and prevents vbar_control_agent segfaults, out-of-memory (OOM) errors,
  and TPU device initialization failures on TPU v6e nodes in GKE caused by race
  conditions during TPU device resets or high-frequency metrics polling. Use when
  troubleshooting vbar_control_agent crashes, memory cgroup OOMs in serial console
  logs, tpu-device-plugin metrics checksum corruption errors, or custom TPU metrics
  collection conflicts on GKE TPU v6e nodes. Don't use for general non-TPU container
  OOM troubleshooting or standard GKE node lifecycle operations.
metadata:
  category: CloudObservabilityAndMonitoring
---

# TPU Connection Failure and VBAR OOM Troubleshooting

Use this skill to systematically diagnose and prevent `vbar_control_agent`
segfaults and Out-Of-Memory (OOM) errors on TPU v6e nodes.

## ⚠️ Prerequisites

-   Cloud Logging must be enabled for the project.
-   Access to the project and cluster via `gcloud` or equivalent tool.

## 🔍 Diagnostic Workflow

### Step 0: Context Acquisition & Time Window Definition

Independently gather required context using available GCP/GKE tools or use the
provided `{variable}` placeholders:

-   `{project_id}`: The GCP Project ID (e.g., `customer-ai-project-123`).
-   `{cluster_name}`: The GKE Cluster Name (e.g., `tpu-cluster-prod`).
-   `{node_name}`: The Node Name or Instance ID (e.g., `tpu-node-1`).
-   `{workload_name}`: The Workload Name / JobSet Name (e.g.,
    `my-training-job-456`).
-   `{namespace}`: The Workload Namespace.
-   `{issue_time}`: The timestamp of the issue (e.g., `2026-04-14T20:00:00Z`).

#### Time Handling & Execution Rules

1.  **Window Calculation**: If an issue timestamp `{issue_time}` is provided,
    calculate the query time window as `[{issue_time} - 30m]` to
    `[{issue_time} + 30m]`.
    -   Let `{start_time}` = `{issue_time} - 30m`
    -   Let `{end_time}` = `{issue_time} + 30m`
2.  **Informational vs. Live Execution**: If the user request is informational
    or query-formulation (e.g. "How can I check...", "How do I determine..."),
    or if live GCP project resources are not actively targetable, directly
    output the calculated time window, log names, and Cloud Logging filter
    templates without attempting live log execution commands.

### Step 1: Check for `vbar_control_agent` OOMs

Look for specific `out of memory` messages from `vbar_control_agent` in serial
console logs (`serialconsole.googleapis.com%2fserial_port_1_output`).

-   **Tool to use**: `query_logs` (for live diagnostics)
-   **Filter Templates**:

**Serial Console Logs (OOMs):**

```sql
logName="projects/{project_id}/logs/serialconsole.googleapis.com%2fserial_port_1_output"
AND labels."compute.googleapis.com/resource_name"="{node_name}"
AND SEARCH(text_payload, "Memory cgroup out of memory: Killed process .* (vbar_control_ag)")
AND timestamp >= "{start_time}"
AND timestamp <= "{end_time}"
```

-   **Logic**: Presence of `Memory cgroup out of memory` messages related to
    `vbar_control_agent`. Stack traces pointing to
    `libtpu::tpunetd::VBARControlHelper::MetricsReadFromVBAR` are a strong
    indicator.
-   **Automation**: Proceed to next step automatically after reporting findings.
-   **Reference**: See `references/failure_signatures.md` for example log
    patterns.

### Step 2: Investigate `tpu-device-plugin` Metrics Fetch Failures [Low Risk]

Check if `tpu-device-plugin` is reporting metric fetch failures.

-   **Tool to use**: `query_logs`
-   **Filter Template**:

```sql
resource.type="k8s_container"
AND resource.labels.project_id="{project_id}"
AND resource.labels.cluster_name="{cluster_name}"
AND resource.labels.container_name="tpu-device-plugin"
AND severity=ERROR
AND textPayload:"metrics fetch failed for .* deviceID and .* device path with error: checksum didn't match with the metrics data. Corrupt data found"
AND timestamp >= "{start_time}"
AND timestamp <= "{end_time}"
```

-   **Logic**: Errors indicating "metrics fetch failed" with "checksum didn't
    match" suggest vBAR memory corruption.
-   **Automation**: Proceed to next step automatically after reporting findings.

### Step 3: Check for Custom Metrics Collection Usage [Low Risk]

Inspect cluster configurations, workloads, or container specs to determine if
custom TPU metrics collection mechanisms are deployed.

-   **Action**: Check if custom scripts or agents (e.g., using
    `libtpu.sdk.tpumonitoring`) are deployed that frequently query
    `GetHostMetrics` from `vBAR Control Agent`.
-   **Verification Commands**:

    -   **Kubectl Search (Inspect workload env/specs)**:

    ```bash
    kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}'
    ```

    -   **Log Search Filter (`query_logs`)**:

    ```sql
    resource.type="k8s_container"
    AND resource.labels.project_id="{project_id}"
    AND resource.labels.cluster_name="{cluster_name}"
    AND textPayload:"libtpu.sdk.tpumonitoring"
    AND timestamp >= "{start_time}"
    AND timestamp <= "{end_time}"
    ```

-   **Logic**: Confirmation of custom metrics collection helps confirm the race
    condition hypothesis.

## 🛠️ Resolution Workflow

### Resolution 1: Temporarily Disable Custom Metrics Collection [High Risk]

If a custom metrics collection agent is identified, recommend disabling it.

-   **Action**: Recommend disabling the custom metrics collector.
-   **Justification**: Prevents reads from vBAR during device resets, stopping
    crashes and OOMs.

### Resolution 2: Await `vbar_control_agent` Resiliency Update [Low Risk]

Advise that a permanent fix will be available in a future GKE version.

-   **Action**: Recommend upgrading GKE when the fix is available.
-   **Justification**: The updated agent will be resilient to memory corruption
    and gracefully handle reads from unbound vBARs.

## 📋 copypaste checklist

-   [ ] Acquire context and compute `[{start_time}, {end_time}]` window.
-   [ ] Check for `vbar_control_agent` segfaults and OOMs using `query_logs`.
-   [ ] Investigate `tpu-device-plugin` failures using `query_logs`.
-   [ ] Inspect for custom metrics collection usage.
-   [ ] Advise disabling custom metrics collection if applicable.
-   [ ] Advise awaiting resiliency update.
