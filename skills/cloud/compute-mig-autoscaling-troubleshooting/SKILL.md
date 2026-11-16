---
name: compute-mig-autoscaling-troubleshooting
description: >-
  Diagnoses and resolves Google Compute Engine Managed Instance Group
  (MIG) autoscaling failures, scale-out blocks, and scale-in stalls. Use ONLY
  when a Compute Engine MIG fails to add or remove VM instances during load
  changes, hits quota or zonal stockout limits, reaches maxNumReplicas
  (CAPPED_AT_MAX_NUM_REPLICAS), conflicts with HTTP(S) load balancer maxRate
  settings, fails to scale in to zero instances, or fails to read Cloud
  Monitoring scaling metrics. DO NOT read or use for Google Kubernetes Engine
  (GKE) Horizontal Pod Autoscaler (HPA), GKE Cluster Autoscaler, standalone
  single-VM creation, or single-VM host maintenance reboots.
metadata:
  version: "1.0.0"
  category: Compute
---

# Compute Engine Managed Instance Group (MIG) Autoscaling Troubleshooting

This skill diagnoses and resolves autoscaling failures in Google Compute Engine
**Managed Instance Groups (MIGs)**. It isolates root causes across
**Project Quotas vs. Physical Zonal Stockouts**, **Autoscaler Policy Limits
(`maxNumReplicas`, `minNumReplicas: 0` scale-to-zero rules, `scaleInControl`,
`mode`, `--cool-down-period`, Load Balancer `UTILIZATION` vs. `RATE`)**, and
**Cloud Monitoring Metric / Service Agent IAM Availability**.

> **MCP Tools:** `get_instance_group_manager_basic_info`,
> `list_instance_group_managers`, `list_managed_instances`,
> `list_instance_templates`, `get_instance_template_basic_info`,
> `get_instance_template_properties`

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

---

## Prerequisites & Environment Setup

Any host, project, IAM, or MIG modifications (installing `gcloud`, configuring
MCP, enabling APIs or Log Analytics, adding IAM bindings, updating autoscalers
or backend services, or deleting resources) must be explicitly approved by the
user before execution.

1. **Google Cloud SDK**: Verify `gcloud` is installed (`gcloud --version`). If
   missing or outdated, seek user approval before installing via
   [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
2. **Compute Engine MCP Server & Capability Boundary**:
   - The Compute Engine MCP server
     ([Use the Compute Engine MCP server](https://docs.cloud.google.com/compute/docs/use-compute-engine-mcp.md.txt))
     exposes read-only **zonal** MIG and template discovery tools
     (`get_instance_group_manager_basic_info`, `list_instance_group_managers`,
     `list_managed_instances`, `list_instance_templates`,
     `get_instance_template_basic_info`, `get_instance_template_properties`) and
     requires `roles/mcp.toolUser`.
   - **Critical Routing Rule**: `get_instance_group_manager_basic_info` requires
     a single `zone` (no regional MIG RPCs exist in Compute Engine MCP) and
     returns `InstanceGroupManagerBasicInfo` (`name`, `id`, `instance_template`,
     `target_size`, `status`), which **omits `autoscaler.status`,
     `autoscaler.statusDetails`, `autoscaler.recommendedSize`, and
     `autoscaler.autoscalingPolicy`**. Compute Engine MCP also lacks
     `list-errors`, Cloud Logging/Monitoring queries, and `update-autoscaling` /
     `set-autoscaling` mutations. Always route regional MIG inspection,
     `autoscaler.*` diagnostics, `list-errors`, Cloud Logging/Monitoring
     queries, and autoscaling mutations to `gcloud` (or Compute Engine /
     Monitoring / Logging REST APIs).
3. **Authentication**: Local CLI (`gcloud auth login`), Application Default
   Credentials (`gcloud auth application-default login`), or Service Accounts
   (`GOOGLE_APPLICATION_CREDENTIALS`).
4. **Project, Region, Billing & API Enablement**:
   ```sh
   gcloud config set project {project_id}
   gcloud config set compute/region {region}
   gcloud config set compute/zone {zone}
   gcloud services enable compute.googleapis.com logging.googleapis.com monitoring.googleapis.com
   ```
   *Note: An active billing account attachment is required (even when using Free
   Tier eligible resources). Default to a well-supported region such as
   `us-central1` if unspecified, and consult
   [Google Cloud locations](https://cloud.google.com/about/locations) to verify
   regional and zonal machine family availability.*
5. **Required IAM Roles**:
   - **Human Caller / Agent Roles**: `roles/compute.viewer`,
     `roles/logging.viewer` (plus `roles/logging.viewAccessor` for Log
     Analytics, and `roles/bigquery.jobUser` + `roles/bigquery.dataViewer` for
     linked BigQuery datasets), and `roles/monitoring.viewer` for read-only
     diagnostics; `roles/compute.instanceAdmin.v1` (plus
     `roles/iam.serviceAccountUser` when updating templates with a VM service
     account, `roles/compute.loadBalancerAdmin` for Backend Service updates, and
     `roles/resourcemanager.projectIamAdmin` to repair project IAM bindings) for
     remediation; and `roles/mcp.toolUser` for Compute Engine MCP calls.
   - **Google-Managed Service Agents (Project-Level)**:
     - **Compute Engine Service Agent**
       (`service-{project_number}@compute-system.iam.gserviceaccount.com`):
       requires `roles/compute.serviceAgent` (includes Cloud Monitoring metric
       read permissions).
     - **Google APIs Service Agent**
       (`{project_number}@cloudservices.gserviceaccount.com`): requires
       `roles/compute.instanceGroupManagerServiceAgent` (creates and deletes MIG
       member VMs).

---

## Step 1: Identify Problem Scope & Inspect Autoscaler Status

### A. Inspect Live MIG Stability, Autoscaler Status & Per-VM Actuation Errors

Inspect `status.isStable`, `autoscaler.status`, `autoscaler.statusDetails`,
`autoscaler.recommendedSize`, `autoscaler.autoscalingPolicy`, and `targetSize`
via `gcloud compute instance-groups managed describe` (pass `--region={region}`
for Regional MIGs or `--zone={zone}` for Zonal MIGs), and run `gcloud compute
instance-groups managed list-errors` to surface asynchronous VM creation errors:

```sh
# 1. Inspect Autoscaler status, statusDetails, recommendedSize, and policy (Regional MIG):
gcloud compute instance-groups managed describe {mig_name} --project={project_id} --region={region} \
    --format="yaml(name, targetSize, status.isStable, autoscaler.status, autoscaler.statusDetails, autoscaler.recommendedSize, autoscaler.autoscalingPolicy)"

# (For a Zonal MIG, replace --region={region} with --zone={zone}:)
gcloud compute instance-groups managed describe {mig_name} --project={project_id} --zone={zone} \
    --format="yaml(name, targetSize, status.isStable, autoscaler.status, autoscaler.statusDetails, autoscaler.recommendedSize, autoscaler.autoscalingPolicy)"

# 2. Inspect per-instance actuation errors logged by the MIG controller:
gcloud compute instance-groups managed list-errors {mig_name} --project={project_id} --region={region} --limit=25
```

**Authoritative `autoscaler.statusDetails[]` (`type` & `message`) Values &
Root Causes** (see
[Understanding autoscaler decisions](https://docs.cloud.google.com/compute/docs/autoscaler/understanding-autoscaler-decisions.md.txt)):
Each item in `autoscaler.statusDetails[]` on the REST `Autoscaler` resource
contains a structured `type` enum and a human-readable `message` string:
- **`CAPPED_AT_MAX_NUM_REPLICAS`** (`"The number of instances has reached the`
  `maxNumReplicas. The autoscaler cannot add more instances."`):
  Current target size has hit the configured `autoscalingPolicy.maxNumReplicas`
  ceiling while demand warrants more VMs.
- **`NOT_ENOUGH_QUOTA_AVAILABLE` / `QUOTA_EXCEEDED`** (`"Quota for some`
  `resources is exceeded. Increase the quota or delete resources to free up`
  `more quota."`, paired with **`QUOTA_EXCEEDED`** in `list-errors` and Cloud
  Audit Logs): Project or regional quota (`CPUS`, `IN_USE_ADDRESSES`,
  `SSD_TOTAL_GB`, or GPUs) is exhausted.
- **`ZONE_RESOURCE_STOCKOUT` / `REGION_RESOURCE_STOCKOUT`** (paired with
  **`ZONE_RESOURCE_POOL_EXHAUSTED`** or
  **`ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`** in `list-errors` and Cloud
  Audit Logs): Temporary physical hardware shortage in the target zone or
  region.
- **`MISSING_CUSTOM_METRIC_DATA_POINTS` / `CUSTOM_METRIC_INVALID` /
  `CUSTOM_METRIC_DATA_POINTS_TOO_SPARSE`** (`"The monitoring metric that was`
  `specified does not exist or does not have the required labels. Check the`
  `metric."`):
  The autoscaler cannot read valid 60-second data points from the configured
  Cloud Monitoring metric, or
  `service-{project_number}@compute-system.iam.gserviceaccount.com` lacks
  `roles/compute.serviceAgent`.
- **`UNSUPPORTED_MAX_RATE_LOAD_BALANCING_CONFIGURATION`** (`"Autoscaling does`
  `not work with an HTTP/S load balancer configured for maxRate."`),
  **`BACKEND_SERVICE_DOES_NOT_EXIST`**, **`MORE_THAN_ONE_BACKEND_SERVICE`**, or
  **`MISSING_LOAD_BALANCING_DATA_POINTS`**: Load-balancing autoscaling conflicts
  with a Backend Service configured in `RATE` (`maxRate`) balancing mode instead
  of `UTILIZATION`, references a deleted/multiple backend services, or receives
  no traffic.
- **`ALL_INSTANCES_UNHEALTHY`** (`"All instances in the instance group are`
  `unhealthy (not in RUNNING state). If this is an error, check the`
  `instances."`):
  All MIG instances are not in `RUNNING` state, halting load-based scaling
  decisions until instances recover.
- **`MODE_ONLY_SCALE_OUT` / `MODE_ONLY_UP` / `MODE_OFF` / `MIN_EQUALS_MAX` /
  `SCALING_SCHEDULE_AFFECTING_MIN_REPLICAS` / `WARNING_NO_INSTANCES`**:
  Policy mode or schedule constraints actively restricting scale-in or
  scale-out.

### B. Query Cloud Audit Logs for Autoscaler Decisions & Instance Creation Failures

Query Cloud Audit Logs across `autoscaler`, `gce_autoscaler`,
`gce_instance_group_manager`, `gce_instance_group`, and `gce_instance` (passing
`--freshness=7d` because `gcloud logging read` defaults to `1d`). See
[Viewing autoscaler logs](https://docs.cloud.google.com/compute/docs/autoscaler/viewing-autoscaler-logs.md.txt):

- **Autoscaler `system_event` Audit Log Schemas (`protoPayload.metadata`)**:
  - **Resize decisions (`compute.autoscalers.resize`, `@type:`
    `"type.googleapis.com/autoscaler.AutoscalerSizeChangeExplanation"`)**:
    Records `protoPayload.metadata.oldSize`, `protoPayload.metadata.newSize`,
    `protoPayload.metadata.autoscalingMode`,
    `protoPayload.metadata.autoscalingReason.summary`,
    `protoPayload.metadata.autoscalingReason.scalingSignal` (`name`,
    `calculatedSize`, `calculationDetails.servingSize`,
    `calculationDetails.signalTarget`, `calculationDetails.signalValue`), and
    `protoPayload.metadata.autoscalingReason.scalingLimit` (`name`, `limitSize`,
    `limitPolicy`, e.g., `MAX_REPLICAS_LIMIT` or `SCALE_IN_LIMIT`).
  - **Status transitions (`compute.autoscalers.changeStatus`,
    `@type: "type.googleapis.com/autoscaler.AutoscalerStatusChange"`)**:
    Records human-readable status message transitions in
    `protoPayload.metadata.oldStatus.details` and
    `protoPayload.metadata.newStatus.details` (for example, transitioning from
    `"OK"` to `"Quota for some resources is exceeded. Increase the quota or`
    `delete resources to free up more quota."`;
    `statusDetails[].type` enum codes live on the REST `Autoscaler` resource
    rather than inside `changeStatus` log entries).

```sh
# 1. Query failed MIG resize, autoscaler, and VM insertion Admin Activity logs (projecting errors[0].code):
gcloud logging read '(resource.type="autoscaler" OR resource.type="gce_autoscaler" OR resource.type="gce_instance_group_manager" OR resource.type="gce_instance_group" OR resource.type="gce_instance") AND severity>=ERROR AND protoPayload.methodName=~"compute\.(regionInstanceGroupManagers|instanceGroupManagers|instances|instanceGroups|autoscalers|regionAutoscalers)\.(resize|insert|addInstances|removeInstances|changeStatus|update|patch)" AND protoPayload.resourceName:"{mig_name}"' \
    --project={project_id} --freshness=7d --limit=25 \
    --format="table(timestamp, resource.type, protoPayload.methodName, protoPayload.status.message, protoPayload.response.error.errors[0].code, protoPayload.response.error.errors[0].message)"

# 2. Query autoscaler system_event resize decisions and status change explanations:
gcloud logging read '(resource.type="autoscaler" OR resource.type="gce_autoscaler") AND log_id("cloudaudit.googleapis.com/system_event") AND protoPayload.methodName=~"compute\.autoscalers\.(resize|changeStatus)"' \
    --project={project_id} --freshness=7d --limit=25 \
    --format="yaml(timestamp, protoPayload.methodName, protoPayload.metadata.oldSize, protoPayload.metadata.newSize, protoPayload.metadata.autoscalingReason, protoPayload.metadata.oldStatus.details, protoPayload.metadata.newStatus.details)"
```

**Distinguishing `QUOTA_EXCEEDED` vs. `ZONE_RESOURCE_POOL_EXHAUSTED`**:
- **`QUOTA_EXCEEDED`**: A **project or regional quota limit** was reached (e.g.,
  `Quota 'CPUS' exceeded. Limit: 24.0 in region us-central1`). Resolve by
  requesting a quota increase, deleting idle resources, or switching to a
  machine family with separate regional quota headroom.
- **`ZONE_RESOURCE_POOL_EXHAUSTED` (or
  `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`)**: A physical **zonal hardware
  stockout** (requesting a project quota increase will **not** fix this).
  Resolve by migrating to a Regional MIG spanning multiple zones with `ANY`
  target distribution shape, or switching zones/machine series.

### C. Compare Autoscaler Recommended Size vs. Actual MIG Size in Cloud Monitoring

*Required IAM Roles*: `roles/monitoring.viewer` and `roles/compute.viewer`.

Query these two GA Cloud Monitoring metrics to compare autoscaler intent against
actual group size:
1. **`compute.googleapis.com/instance_group/size`**
   (`resource.type="instance_group"`, filtered by
   `resource.labels.instance_group_name="{mig_name}"`): Actual number of VM
   instances currently in the group.
2. **`autoscaler.googleapis.com/recommended_size`**
   (`resource.type="autoscaler"`, filtered by
   `resource.labels.instance_group_manager_name="{mig_name}"`): Instance count
   calculated and recommended by the autoscaler from active scaling signals.

**How to Interpret Metric Divergence**:
- **If `autoscaler.googleapis.com/recommended_size >`
  `compute.googleapis.com/instance_group/size` (Scale-Out Blocked)**:
  The autoscaler wants more VMs, but actuation is blocked by:
  1. `maxNumReplicas` ceiling (`CAPPED_AT_MAX_NUM_REPLICAS`),
  2. Project/regional `QUOTA_EXCEEDED` (`NOT_ENOUGH_QUOTA_AVAILABLE`), or
  3. Physical stockout (`ZONE_RESOURCE_POOL_EXHAUSTED` /
     `ZONE_RESOURCE_STOCKOUT`).
- **If `autoscaler.googleapis.com/recommended_size <`
  `compute.googleapis.com/instance_group/size` (Scale-In Delayed or Blocked)**:
  Load dropped and the autoscaler recommends fewer VMs, but scale-in is held by:
  1. The built-in **10-minute stabilization period** (`stabilizationPeriodSec`,
     default `600` seconds of sustained lower demand to prevent flapping),
  2. **Scale-in controls (`scaleInControl`)**, where `maxScaledInReplicas`
     (`maxScaledInReplicas.fixed`, `maxScaledInReplicas.percent`, and
     `maxScaledInReplicas.calculated`) caps VM deletions per trailing
     `timeWindowSec`, or
  3. Autoscaler `mode` set to **`ONLY_SCALE_OUT`** (`--mode=only-scale-out`).

### D. Log Analytics SQL Query: Rank MIGs & VM Insertions by Failure Volume

Failed `activity` audit logs (`severity_number >= 500`, `ERROR` and above) route
to `_Default._AllLogs` (whereas `system_event` autoscaler status events route to
`_Required._AllLogs`). Upgrade `_Default` if needed (with user approval):

```sh
gcloud logging buckets update _Default --project={project_id} --location=global --enable-analytics
```

In `_AllLogs`, `resource.labels` has BigQuery type **`JSON`** (always extract
labels via `JSON_VALUE(...)`), and include `'gce_instance'` and `'autoscaler'`
in `resource.type IN (...)` so failed `instances.insert` and `autoscalers.*`
operations are captured alongside `instanceGroupManagers.resize`:

```sql
SELECT
  TIMESTAMP_TRUNC(timestamp, HOUR) AS hour_bucket,
  resource.type AS resource_type,
  COALESCE(JSON_VALUE(resource.labels.location), JSON_VALUE(resource.labels.zone)) AS location,
  REGEXP_EXTRACT(proto_payload.audit_log.resource_name, r'[^/]+$') AS target_resource,
  proto_payload.audit_log.method_name AS method_name,
  proto_payload.audit_log.status.message AS status_message,
  COUNT(*) AS error_count
FROM `{project_id}.global._Default._AllLogs`
WHERE
  timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND resource.type IN ('autoscaler', 'gce_autoscaler', 'gce_instance_group_manager', 'gce_instance_group', 'gce_instance')
  AND severity_number >= 500
  AND REGEXP_CONTAINS(
    proto_payload.audit_log.method_name,
    r'compute\.(regionInstanceGroupManagers|instanceGroupManagers|instanceGroups|autoscalers|regionAutoscalers|instances)\.(resize|addInstances|removeInstances|insert|update|patch|changeStatus)$'
  )
GROUP BY hour_bucket, resource_type, location, target_resource, method_name, status_message
ORDER BY hour_bucket DESC, error_count DESC;
```

---

## Step 2: Diagnose & Remediate via 4-Branch Decision Tree

### Branch 1: Resource Quota Constraints (`QUOTA_EXCEEDED` / `NOT_ENOUGH_QUOTA_AVAILABLE`)

When `QUOTA_EXCEEDED` blocks scaling (e.g., `CPUS`, `IN_USE_ADDRESSES`,
`SSD_TOTAL_GB`, or GPUs), **always include all 4 steps below**:

1. **Verify Project & `compute.googleapis.com` API Configuration (Always
   Include)**:
   ```sh
   gcloud config set project {project_id}
   gcloud services enable compute.googleapis.com
   ```
2. **Inspect Regional Quota Usage and Limits**:
   ```sh
   gcloud compute regions describe {region} --project={project_id} \
       --format="table(quotas:format='table(metric,limit,usage)')"
   ```
3. **Request a Quota Increase**: Submit a quota increase request in the Google
   Cloud Console under **IAM & Admin > Quotas & System Limits** (`IAM & Admin >
   Quotas`).
4. **Immediate Workarounds to Unblock Scaling**:
   - **Switch Machine Family**: Update the MIG's Instance Template to a machine
     family governed by a separate regional CPU quota pool with headroom (e.g.,
     switching between `e2`, `n2`, `n2d`, or `c3`).
   - **Spread Load Across Another Region**: Add a sibling MIG in another region
     behind a global Backend Service.
   - **Delete Unused Resources**: Remove idle VMs, unattached static IPs, or
     orphaned disks in the region.

### Branch 2: Scale-Out Configuration & Thrashing (`CAPPED_AT_MAX_NUM_REPLICAS`, Load Balancer `maxRate`, `--cool-down-period`)

1. **Ceiling Reached (`CAPPED_AT_MAX_NUM_REPLICAS`)**: Raise
   `--max-num-replicas` via `update-autoscaling` (use `--region={region}` for
   regional MIGs):
   ```sh
   gcloud compute instance-groups managed update-autoscaling {mig_name} \
       --project={project_id} --zone={zone} --max-num-replicas={new_max_replicas}
   ```
2. **HTTP(S) Load Balancer `RATE` vs. `UTILIZATION` Conflict
   (`UNSUPPORTED_MAX_RATE_LOAD_BALANCING_CONFIGURATION`)**: Switch the Backend
   Service backend from `RATE` to `UTILIZATION` (or switch the MIG autoscaler
   signal to CPU or a Cloud Monitoring metric). Pass
   `--instance-group-zone={zone}` for a Zonal MIG or
   `--instance-group-region={region}` for a Regional MIG (and replace `--global`
   with `--region={backend_service_region}` if the Backend Service is regional):
   ```sh
   # Zonal MIG attached to a global Backend Service:
   gcloud compute backend-services update-backend {backend_service} --project={project_id} --global \
       --instance-group={mig_name} --instance-group-zone={zone} --balancing-mode=UTILIZATION --max-utilization=0.8

   # Regional MIG attached to a global Backend Service:
   gcloud compute backend-services update-backend {backend_service} --project={project_id} --global \
       --instance-group={mig_name} --instance-group-region={region} --balancing-mode=UTILIZATION --max-utilization=0.8
   ```
3. **Boot Disk / Missing Image Errors**: Inspect `gcloud compute instance-groups
   managed list-errors {mig_name} --project={project_id} --zone={zone}` and
   verify the template's boot image exists via `gcloud compute
   instance-templates describe {template_name} --project={project_id}`.
4. **Initialization Period (`--cool-down-period`) vs. Stabilization Period
   (`--stabilization-period`)**:
   - **Critical CLI Rule**: `--cool-down-period` (VM startup initialization
     window, default `60`s) does **not** exist on `update-autoscaling`—it is
     accepted **only** on `set-autoscaling`. Because `set-autoscaling`
     **replaces** the entire `autoscalingPolicy`, always inspect existing policy
     signals via `describe` first and pass `--max-num-replicas` plus active
     scaling targets (such as `--target-cpu-utilization`) together:
     ```sh
     gcloud compute instance-groups managed set-autoscaling {mig_name} --project={project_id} --zone={zone} \
         --min-num-replicas={min_replicas} --max-num-replicas={max_replicas} \
         --target-cpu-utilization={target_cpu} --cool-down-period=120
     ```
   - To tune the **scale-in stabilization window** (default `600`s) without
     replacing the policy, `--stabilization-period` **is** supported directly on
     `update-autoscaling`:
     ```sh
     gcloud compute instance-groups managed update-autoscaling {mig_name} \
         --project={project_id} --zone={zone} --stabilization-period=600
     ```

### Branch 3: Scale-Down Blocked or Delayed (`scaleInControl`, `ONLY_SCALE_OUT`, or `minNumReplicas: 0`)

If traffic dropped hours ago and `autoscaler.googleapis.com/recommended_size` is
far below `compute.googleapis.com/instance_group/size` (or the MIG refuses to
scale in to `0` instances):

1. **Inspect `autoscaler.autoscalingPolicy.mode`, `scaleInControl`, and
   `minNumReplicas`**:
   ```sh
   gcloud compute instance-groups managed describe {mig_name} --project={project_id} --zone={zone} \
       --format="yaml(autoscaler.autoscalingPolicy.mode, autoscaler.autoscalingPolicy.minNumReplicas, autoscaler.autoscalingPolicy.scaleInControl, autoscaler.autoscalingPolicy.coolDownPeriodSec)"
   ```
   - `scaleInControl` contains `timeWindowSec` and the nested object
     `maxScaledInReplicas` (`maxScaledInReplicas.fixed`,
     `maxScaledInReplicas.percent`, and `maxScaledInReplicas.calculated`).
   - *(Note: REST/`describe` outputs uppercase `ON` / `ONLY_SCALE_OUT` / `OFF`,
     whereas `gcloud` CLI `--mode` requires **lowercase** `--mode=on`,
     `--mode=only-scale-out`, or `--mode=off`.)*
2. **Scaling In to Zero / Scaling Out from Zero (`minNumReplicas: 0`)**:
   - Per [Understanding autoscaler decisions](https://docs.cloud.google.com/compute/docs/autoscaler/understanding-autoscaler-decisions.md.txt),
     a MIG with `minNumReplicas: 0` **cannot scale in to `0` instances** if its
     autoscaling policy includes **any per-instance signal** (CPU utilization,
     HTTP load balancing serving capacity, or a per-instance Cloud Monitoring
     metric), and cannot scale out from `0` if its only signal is a per-instance
     metric (because `0` running VMs emit no per-instance metrics).
   - To scale in to `0` and back out from `0`, configure only **scaling
     schedules** (`scalingSchedules`) or a **group-level Cloud Monitoring
     metric** using `--stackdriver-metric-single-instance-assignment`
     (`singleInstanceAssignment`, such as a Pub/Sub subscription backlog).
3. **Remediate `mode` or `scaleInControl`**:
   ```sh
   # Enable full scaling (--mode=on) and relax scale-in throttling:
   gcloud compute instance-groups managed update-autoscaling {mig_name} --project={project_id} --zone={zone} \
       --mode=on --scale-in-control=max-scaled-in-replicas-percent=50,time-window=600

   # Or clear scale-in controls completely for immediate scale-down after stabilization:
   gcloud compute instance-groups managed update-autoscaling {mig_name} --project={project_id} --zone={zone} \
       --mode=on --clear-scale-in-control
   ```
4. **Safe Rollback to Conservative Scale-In Limits (Always Include)**:
   Whenever modifying `scaleInControl`, **always** provide rollback commands to
   restore conservative scale-in limits after recovery so sudden traffic
   rebounds do not hit an under-provisioned MIG:
   ```sh
   gcloud compute instance-groups managed update-autoscaling {mig_name} --project={project_id} --zone={zone} \
       --mode=on --scale-in-control=max-scaled-in-replicas-percent=10,time-window=600
   ```

### Branch 4: Scaling Metric Availability & Service Agent IAM Issues

1. **Repair Google-Managed Service Agent IAM Roles**: Look up `{project_number}`
   first, then obtain explicit user approval before restoring bindings:
   ```sh
   # Step 1: Retrieve {project_number} for {project_id}:
   gcloud projects describe {project_id} --format="value(projectNumber)"

   # Step 2a: Restore Compute Engine Service Agent (reads Cloud Monitoring scaling metrics):
   gcloud projects add-iam-policy-binding {project_id} \
       --member="serviceAccount:service-{project_number}@compute-system.iam.gserviceaccount.com" \
       --role="roles/compute.serviceAgent"

   # Step 2b: Restore Google APIs Service Agent (creates and deletes MIG member VMs):
   gcloud projects add-iam-policy-binding {project_id} \
       --member="serviceAccount:{project_number}@cloudservices.gserviceaccount.com" \
       --role="roles/compute.instanceGroupManagerServiceAgent"
   ```
2. **Verify Custom Cloud Monitoring Metric Resource & Label Contract**:
   - **Per-Instance Metrics**: Must be written to monitored resource
     `gce_instance` with the **numeric VM `instance_id`** and **`zone`** labels
     (**`instance_name` is NOT a valid `gce_instance` monitored resource
     label**).
   - **Data Type, Kind & Frequency**: Export `INT64` or `DOUBLE` values with
     `GAUGE` or `DELTA` metric kind (**`CUMULATIVE` metrics are unsupported**)
     at least every **60 seconds**. See
     [Scaling based on Cloud Monitoring metrics](https://docs.cloud.google.com/compute/docs/autoscaler/scaling-cloud-monitoring-metrics.md.txt).

---

## Proactive Hardening, Safe Rollback & Cleanup

1. **Predictive Autoscaling (CPU Workloads)**: For workloads with recurring
   daily or weekly cycles, enable Predictive Autoscaling (note that
   `update-autoscaling` accepts `--cpu-utilization-predictive-method` only when
   CPU utilization scaling is already configured; otherwise configure both via
   `set-autoscaling`). See
   [Predictive autoscaling](https://docs.cloud.google.com/compute/docs/autoscaler/predictive-autoscaling.md.txt):
   ```sh
   # On a MIG that already scales on CPU utilization:
   gcloud compute instance-groups managed update-autoscaling {mig_name} --project={project_id} --zone={zone} \
       --cpu-utilization-predictive-method=optimize-availability

   # Or configure CPU target + Predictive Autoscaling together (replaces policy):
   gcloud compute instance-groups managed set-autoscaling {mig_name} --project={project_id} --zone={zone} \
       --min-num-replicas={min_replicas} --max-num-replicas={max_replicas} \
       --target-cpu-utilization=0.6 --cpu-utilization-predictive-method=optimize-availability
   ```
2. **Safe Rollback of Scale-In Controls**:
   ```sh
   gcloud compute instance-groups managed update-autoscaling {mig_name} --project={project_id} --zone={zone} \
       --mode=on --scale-in-control=max-scaled-in-replicas-percent=10,time-window=600
   ```
3. **Teardown Temporary Test MIGs & Templates**: Delete temporary test resources
   when finished (omitting `--quiet` on manual commands so interactive
   confirmation prevents accidental deletion):
   ```sh
   gcloud compute instance-groups managed delete {mig_name} --project={project_id} --zone={zone}
   gcloud compute instance-templates delete {template_name} --project={project_id}
   ```
4. **Pricing Reference**: Autoscaling policies incur no extra fee beyond member
   VM instances, disks, and Cloud Monitoring custom metric ingestion. Consult
   [Google Cloud pricing](https://cloud.google.com/pricing) and
   [Compute Engine pricing](https://cloud.google.com/compute/all-pricing) for
   current regional rates rather than quoting hardcoded dollar figures.
