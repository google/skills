---
name: compute-host-events-troubleshooting
description: >-
  Investigates, diagnoses, and mitigates Google Compute Engine virtual
  machine (VM) host events, including planned infrastructure maintenance
  (migrateOnHostMaintenance, terminateOnHostMaintenance), physical host hardware
  errors (hostError), guest OS terminations (guestTerminate), and Spot or
  Preemptible VM preemptions (compute.instances.preempted) using shutdown-script
  metadata. Use ONLY when an existing Compute Engine VM unexpectedly reboots,
  stops, crashes, is preempted, or becomes unresponsive due to physical host
  maintenance, hardware errors, or Local SSD recovery. DO NOT read or use for
  creating new standalone VMs, Managed Instance Group (MIG) autoscaler scale-out
  or scale-in failures, Google Kubernetes Engine (GKE) clusters, application OOM
  debugging, or VPC firewall issues.
metadata:
  version: "1.0.0"
  category: Compute
---

# Compute Engine VM Host Events & Infrastructure Crash Troubleshooting

This skill diagnoses unexpected Google Compute Engine VM restarts,
terminations, and unresponsiveness caused by infrastructure host events
(`compute.instances.hostError`, `compute.instances.migrateOnHostMaintenance`,
`compute.instances.terminateOnHostMaintenance`, `compute.instances.preempted`,
`compute.instances.automaticRestart`) or guest-OS-initiated shutdowns
(`compute.instances.guestTerminate`). It provides authoritative Cloud Audit Log
queries, Log Analytics `_Required._AllLogs` SQL aggregations, upcoming
maintenance window checks, and host scheduling remediations.

> **MCP Tools:** `get_instance_basic_info`, `list_instances`,
> `list_instance_attached_disks`, `start_instance`, `stop_instance`,
> `reset_instance`, `delete_instance`, `get_zone_operation`

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

---

## Prerequisites & Environment Setup

Any host or project modifications (installing or updating `gcloud`, configuring
the Compute Engine MCP server, enabling APIs or Log Analytics, mutating VM
scheduling/metadata, creating log-based metrics, or deleting resources) must be
explicitly approved by the user before execution.

1. **Google Cloud SDK**: Verify `gcloud` is installed (`gcloud --version`). If
   missing or outdated, ask the user for approval before installing via
   [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
2. **Compute Engine MCP Server & Capability Boundary**:
   - The Compute Engine MCP server
     ([Use the Compute Engine MCP server](https://docs.cloud.google.com/compute/docs/use-compute-engine-mcp.md.txt))
     exposes zonal VM discovery and lifecycle tools (`get_instance_basic_info`,
     `list_instances`, `list_instance_attached_disks`, `start_instance`,
     `stop_instance`, `reset_instance`, `delete_instance`,
     `get_zone_operation`, requiring `roles/mcp.toolUser`).
   - **Critical Routing Rule**: `get_instance_basic_info` returns a reduced
     `InstanceBasicInfo` projection (`name`, `id`, `status`, `machine_type`,
     `create_time`, `guest_accelerators`) that **omits `scheduling` and
     `resourceStatus.upcomingMaintenance`**, and Compute Engine MCP does **not**
     expose tools for Cloud Logging queries, serial console output,
     `set-scheduling`, `perform-maintenance`, or instance metadata updates.
     Always route full scheduling inspection, upcoming maintenance checks,
     serial port output, audit log queries, and scheduling/metadata mutations to
     `gcloud` (or Compute Engine / Cloud Logging REST APIs).
3. **Authentication**:
   - Local CLI: `gcloud auth login`
   - Application Default Credentials: `gcloud auth application-default login`
   - Service Accounts: Set `GOOGLE_APPLICATION_CREDENTIALS` to your service
     account credentials path.
4. **Project, Region & Billing**:
   ```sh
   gcloud config set project {project_id}
   gcloud config set compute/region {region}
   gcloud config set compute/zone {zone}
   ```
   *Note: An active billing account attachment is required (even when evaluating
   Free Tier eligible resources). If no region is specified, default to
   `us-central1` (`us-central1-a`), and check
   [Google Cloud locations](https://cloud.google.com/about/locations) for
   regional hardware availability.*
5. **API Enablement**:
   ```sh
   gcloud services enable compute.googleapis.com logging.googleapis.com monitoring.googleapis.com
   ```
6. **Required IAM Roles**:
   - **Read-Only Diagnostics**: `roles/compute.viewer` (instance scheduling and
     serial console output), `roles/logging.viewer` (or
     `roles/logging.privateLogViewer` to read `system_event` and `activity`
     audit logs), and `roles/logging.viewAccessor` for Log Analytics queries in
     Cloud Logging (plus `roles/bigquery.jobUser` and
     `roles/bigquery.dataViewer` when querying a linked Log Analytics dataset
     from BigQuery Studio or `bq`).
   - **Remediation & MCP**: `roles/compute.instanceAdmin.v1` (to run
     `set-scheduling`, `perform-maintenance`, `add-metadata`, or
     `remove-metadata`), `roles/logging.configWriter` (to create log-based
     metrics), and `roles/mcp.toolUser` (for Compute Engine MCP calls).

---

## Diagnostic Workflow: Classify the Termination Event

When a user reports an unexpected VM reboot, stop, or crash, run targeted Cloud
Logging queries against `cloudaudit.googleapis.com/system_event` (Compute Engine
infrastructure events) and `cloudaudit.googleapis.com/activity`
(caller-initiated API stops/resets). Always pass `--freshness=7d` (or a window
covering the incident timestamp) because `gcloud logging read` defaults
`--freshness` to `1d` and silently returns zero rows for incidents older than 24
hours. See
[Troubleshooting VM shutdowns and reboots](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-reboots.md.txt).

### Key Distinction: `hostError` vs. Planned Maintenance vs. `preempted`

- **`compute.instances.hostError` (Unplanned Hardware/Hypervisor Crash)**:
  Indicates an unexpected hardware or hypervisor failure on the physical server
  hosting the VM. If `scheduling.automaticRestart` is `true`
  (`--restart-on-failure`), Compute Engine automatically restarts the VM on a
  healthy physical host (typically within **3 to 5.5 minutes** from detection on
  standard VMs, logging `compute.instances.automaticRestart`). On VMs with
  attached Local SSDs, Compute Engine logs `compute.instances.hostError` with
  `operation.first="true"` when Local SSD recovery begins and
  `operation.last="true"` when recovery completes or reaches
  `scheduling.localSsdRecoveryTimeout`.
- **`compute.instances.migrateOnHostMaintenance` /
  `compute.instances.terminateOnHostMaintenance` (Planned Infrastructure
  Maintenance)**: Compute Engine logs these exact `system_event` method names
  (along with `compute.instances.upcomingMaintenance` notifications) during
  scheduled hardware or hypervisor updates. Depending on `onHostMaintenance`,
  the VM either transparently live-migrates (`MIGRATE` ->
  `compute.instances.migrateOnHostMaintenance`) or terminates (`TERMINATE` ->
  `compute.instances.terminateOnHostMaintenance`, followed by
  `compute.instances.automaticRestart` if `automaticRestart: true`).
- **`compute.instances.preempted` (Spot / Preemptible VM Reclaimed)**: Indicates
  Compute Engine reclaimed capacity from a Spot VM or Preemptible VM.

### 1. Query Infrastructure Host Events & Caller Stops in Cloud Logging

Run this `gcloud logging read` command to determine whether `{vm_name}`
experienced a physical host error, planned maintenance, Spot preemption, MIG
recreation, or an external caller-initiated API stop/reset:

```sh
gcloud logging read 'resource.type="gce_instance" AND (log_id("cloudaudit.googleapis.com/system_event") OR log_id("cloudaudit.googleapis.com/activity")) AND protoPayload.methodName=~"(compute\.instances\.(hostError|migrateOnHostMaintenance|terminateOnHostMaintenance|preempted|automaticRestart|upcomingMaintenance|guestTerminate|repair.*)|v1\.compute\.instances\.(stop|reset|delete|performMaintenance|simulateMaintenanceEvent))" AND protoPayload.resourceName:"{vm_name}"' \
    --project={project_id} \
    --freshness=7d \
    --limit=25 \
    --format="table(timestamp, logName.basename(), protoPayload.methodName, protoPayload.authenticationInfo.principalEmail, operation.first, operation.last, protoPayload.status.message)"
```

### 2. Check Specifically for Guest OS Initiated Terminations (`guestTerminate`)

If the VM stopped without a `hostError`, maintenance termination, preemption, or
user-initiated `v1.compute.instances.stop` Admin Activity log, check whether the
shutdown was initiated **from inside the Guest OS** (`sudo shutdown -h now`,
`poweroff`, `systemctl poweroff`, or an internal watchdog script):

```sh
gcloud logging read 'resource.type="gce_instance" AND log_id("cloudaudit.googleapis.com/system_event") AND protoPayload.methodName="compute.instances.guestTerminate" AND protoPayload.resourceName:"{vm_name}"' \
    --project={project_id} \
    --freshness=7d \
    --limit=20 \
    --format="yaml(timestamp, protoPayload.methodName, protoPayload.authenticationInfo.principalEmail, protoPayload.status)"
```

- **Critical `guestTerminate` Attribution Nuance**: Because
  `compute.instances.guestTerminate` is a `system_event` generated when the
  guest ACPI power-off reaches the hypervisor, Compute Engine **always records
  its generic built-in system principal in
  `protoPayload.authenticationInfo.principalEmail`** — it **never** identifies
  which Linux/Windows user, cron job, or script inside the VM ran
  `shutdown`/`poweroff` (whereas external caller-initiated
  `v1.compute.instances.stop`, `reset`, or `delete` entries in
  `cloudaudit.googleapis.com/activity` record the external IAM user or service
  account in `principalEmail`).
- **How to Find the In-Guest Culprit**: Inspect the VM's serial console output
  and guest OS logs from the previous boot (`journalctl -b -1`,
  `/var/log/syslog` or `/var/log/messages`, `/var/log/auth.log`, and `last -x
  shutdown reboot`):
  ```sh
  gcloud compute instances get-serial-port-output {vm_name} --project={project_id} --zone={zone} --port=1
  ```

### 3. Log Analytics SQL Query: Aggregate Host Events Across the Project

Compute Engine host events (`hostError`, `migrateOnHostMaintenance`,
`terminateOnHostMaintenance`, `preempted`, `automaticRestart`,
`guestTerminate`) are `cloudaudit.googleapis.com/system_event` logs. By default,
Cloud Logging's `_Default` sink **excludes** `system_event` logs and routes them
exclusively to the **`_Required`** log bucket.

> **Prerequisites for `_Required._AllLogs` SQL**:
> 1. Upgrade the **`_Required`** bucket to **Log Analytics** (seek user approval
>    first):
>    ```sh
>    gcloud logging buckets update _Required --project={project_id} --location=global --enable-analytics
>    ```
> 2. In Log Analytics `_AllLogs` schemas, `resource.labels` has BigQuery type
>    **`JSON`** (not `STRUCT`). Always extract fields with
>    `JSON_VALUE(resource.labels.zone)` and
>    `JSON_VALUE(resource.labels.instance_id)` — grouping directly on raw `JSON`
>    expressions fails with `Grouping by expressions of type JSON is not
>    allowed`.

```sql
SELECT
  JSON_VALUE(resource.labels.zone) AS zone,
  JSON_VALUE(resource.labels.instance_id) AS instance_id,
  REGEXP_EXTRACT(proto_payload.audit_log.resource_name, r'[^/]+$') AS vm_name,
  proto_payload.audit_log.method_name AS event_type,
  COUNT(*) AS event_count
FROM `{project_id}.global._Required._AllLogs`
WHERE
  resource.type = 'gce_instance'
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND proto_payload.audit_log.method_name IN (
    'compute.instances.hostError',
    'compute.instances.migrateOnHostMaintenance',
    'compute.instances.terminateOnHostMaintenance',
    'compute.instances.preempted',
    'compute.instances.automaticRestart',
    'compute.instances.guestTerminate'
  )
GROUP BY zone, instance_id, vm_name, event_type
ORDER BY event_count DESC;
```

### 4. Inspect Upcoming Scheduled Host Maintenance & Trigger Early Maintenance

For instances that emit advance maintenance notifications (such as `A4X Max`,
`A4X`, `A4`, `A3`, `A2`, `G4`, `G2` GPU instances, bare metal `-metal`
instances, `H4D` / Cloud RDMA instances, `X4` instances, storage-optimized `Z3`
/ `Z4D` / `Z4M` Local SSD instances, or Cloud TPU nodes), inspect upcoming
maintenance via `gcloud` or the in-guest metadata server. See
[Monitor and plan for a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/monitor-plan-host-maintenance-event.md.txt)
and
[Get live migration notices from the metadata server](https://docs.cloud.google.com/compute/docs/metadata/getting-live-migration-notice.md.txt):

```sh
# 1. Check a single instance for scheduling policy and upcoming maintenance (Compute Engine API):
gcloud compute instances describe {vm_name} --project={project_id} --zone={zone} \
    --format="yaml(name, scheduling, resourceStatus.upcomingMaintenance)"

# 2. List upcoming maintenance windows across all instances in the project:
gcloud compute instances list --project={project_id} \
    --format="table(name, zone.basename(), resourceStatus.upcomingMaintenance.type, resourceStatus.upcomingMaintenance.windowStartTime, resourceStatus.upcomingMaintenance.windowEndTime, resourceStatus.upcomingMaintenance.canReschedule, resourceStatus.upcomingMaintenance.maintenanceStatus)"

# 3. Query from inside the Guest OS via the Metadata Server:
curl -s "http://metadata.google.internal/computeMetadata/v1/instance/upcoming-maintenance?alt=json" \
    -H "Metadata-Flavor: Google"
```

- **API vs. Metadata Server JSON Field Name Difference**:
  - In `gcloud` / Compute Engine REST (`resourceStatus.upcomingMaintenance`) and
    Cloud Logging, the maintenance classification field is named **`type`**
    (`SCHEDULED` or `UNSCHEDULED`), alongside `maintenanceStatus` (`PENDING` or
    `ONGOING`), `canReschedule` (`true` or `false`), `windowStartTime`,
    `windowEndTime`, and `latestWindowStartTime`.
  - When querying `/computeMetadata/v1/instance/upcoming-maintenance?alt=json`
    inside the guest OS, returns `"NONE"` when no maintenance is scheduled, or a
    JSON object where the classification property is named **`maintenanceType`**
    (e.g., `"maintenanceType": "SCHEDULED"`).
- **Manually Trigger Host Maintenance Early (`perform-maintenance`)**:
  - **Preconditions**: Check `canReschedule` and `maintenanceStatus` first. You
    can run `perform-maintenance` when `canReschedule` is `true` (and
    `maintenanceStatus` is `PENDING` when an active notice exists, or on
    supported machine series before a notice is posted to reset the maintenance
    cycle). If an active notice reports `canReschedule: false` or
    `maintenanceStatus: ONGOING`, manual triggering is rejected by the API.
  - **Immediate Impact**: Confirm with the user before running —
    `perform-maintenance` starts host maintenance **immediately** (terminating
    and optionally restarting `TERMINATE`-policy instances right away). See
    [Simulate or trigger a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/trigger-host-maintenance-event.md.txt):

```sh
gcloud compute instances perform-maintenance {vm_name} --project={project_id} --zone={zone}
```

---

## Actionable Remediation & Hardening Rules

*Required IAM Role*: Modifying instance scheduling or metadata requires
`roles/compute.instanceAdmin.v1`. Always obtain user confirmation before
executing mutating commands.

### Case A: Preventing Downtime During Planned Maintenance (`MIGRATE` Policy)

If a live-migration-capable VM (such as an `N2`, `N2D`, `C3`, `C3D`, `C4`, or
`N4` instance; note that standard `E2` VMs **only** support `MIGRATE` during
host maintenance events and disallow `TERMINATE`) logged
`compute.instances.terminateOnHostMaintenance` during routine host maintenance,
its `scheduling.onHostMaintenance` policy was set to `TERMINATE` instead of
`MIGRATE`.

- **Fix**: Enable Live Migration (`--maintenance-policy=MIGRATE`) and Automatic
  Restart (`--restart-on-failure`, which sets REST
  `scheduling.automaticRestart: true`; use `--no-restart-on-failure` to
  disable). Per
  [Set VM host maintenance policy](https://docs.cloud.google.com/compute/docs/instances/setting-vm-host-options.md.txt),
  `gcloud compute instances set-scheduling` updates `onHostMaintenance`,
  `automaticRestart` (except on running CSEK-encrypted VMs),
  `hostErrorTimeoutSeconds`, and `localSsdRecoveryTimeout` **in-place on a
  running VM** without stopping or rebooting it *(note: although the
  `gcloud compute instances set-scheduling --help` / REST
  `instances.setScheduling` reference docstring contains a legacy note stating
  the method requires a stopped `TERMINATED` instance, stopping the VM first is
  only required when changing `--provisioning-model` / `--preemptible` or
  updating `automaticRestart` on CSEK-encrypted VMs)*:

```sh
gcloud compute instances set-scheduling {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --maintenance-policy=MIGRATE \
    --restart-on-failure
```

- **VM Families & Configurations That Do Not Support Live Migration (Always
  Clarify)**:
  Whenever recommending `--maintenance-policy=MIGRATE`, explicitly note which VM
  configurations **cannot** live-migrate and instead require
  `--maintenance-policy=TERMINATE` paired with `--restart-on-failure` (except
  Spot/Preemptible VMs, which require `TERMINATE` with
  `--no-restart-on-failure`), and note that standard **`E2`** VMs only support
  `MIGRATE`:
  - **Spot VMs (`provisioningModel: SPOT`) and legacy Preemptible VMs**
  - **GPU-attached VMs** (`A4X Max`, `A4X`, `A4`, `A3`, `A2`, `G4`, `G2`, and
    `N1` with attached GPUs; note that `N2` does not support attached GPUs)
  - **Cloud TPU VMs** and **Bare Metal Instances** (`*-metal`)
  - **Instances with a Cloud RDMA network interface** (such as `H4D` and `Z4M`
    with Cloud RDMA)
  - **`X4` and `X5` memory-optimized instances**
  - **Large Local SSD Configurations** (`Z3` instances with > 18,000 GiB of
    Local SSD, and `Z4D` / `Z4M` instances with > 42,000 GiB of Local SSD)

### Case B: Faster Recovery from Unresponsive Hosts (`--host-error-timeout-seconds`)

If an application experiences prolonged unresponsiveness before Compute Engine's
default host watchdog declares a `hostError`, shorten the detection timeout via
`--host-error-timeout-seconds`:

- **Constraints**: Must be specified in **30-second increments**. Valid range is
  **`90` to `300` seconds in `gcloud`** (`90` to `330` seconds via Compute
  Engine REST `instances.setScheduling`). Unsupported on **Sole-Tenant** VMs and
  **Spot / Preemptible** VMs. Updates dynamically on a running VM (see
  [Set VM host maintenance policy](https://docs.cloud.google.com/compute/docs/instances/setting-vm-host-options.md.txt)):

```sh
gcloud compute instances set-scheduling {vm_name} --project={project_id} --zone={zone} --host-error-timeout-seconds=90
```

### Case C: Customizing Local SSD Recovery Timeout (`--local-ssd-recovery-timeout`)

When a `hostError` strikes a VM with attached **Local SSDs**, Compute Engine
attempts to recover data from the failed host's NVMe drives while the VM stays
offline, logging `compute.instances.hostError` with `operation.first="true"`
when recovery begins and `operation.last="true"` when recovery completes or
reaches `scheduling.localSsdRecoveryTimeout`.

- **Valid Range, Defaults & Trade-off**: Valid values are **`0` to `168` hours
  (up to 7 days)** in **1-hour increments** (see
  [About host maintenance](https://docs.cloud.google.com/compute/docs/instances/host-maintenance-overview.md.txt)):
  - **Defaults by Machine Series**:
    - **`168` hours (7 days)**: `Z4M` bare metal and `Z3` bare metal
      (`z3-highmem-192-highlssd-metal`) instances
    - **`6` hours**: `Z4D`, `Z4M`, and `Z3` VMs
    - **`1` hour**: All other instance types
  - **Stateless Scratch / Cache Local SSDs**: Set
    `--local-ssd-recovery-timeout=0` to **skip NVMe data recovery and restart
    the VM immediately** with blank Local SSDs.
  - **Stateful Local SSD Data**: Increase `--local-ssd-recovery-timeout` (up to
    `168` hours, e.g., `--local-ssd-recovery-timeout=24`) to give Compute Engine
    more time to recover attached Local SSD data before restarting.

```sh
# Fast restart (0 hours wait) for stateless cache/scratch Local SSD workloads:
gcloud compute instances set-scheduling {vm_name} --project={project_id} --zone={zone} --local-ssd-recovery-timeout=0
```

### Case D: Handling Spot / Preemptible VM Preemptions (`compute.instances.preempted`)

When `compute.instances.preempted` appears in Cloud Logging, Compute Engine
reclaimed a **Spot VM** or **Preemptible VM** by sending an **ACPI G2 Soft Off**
signal.

1. **Best-Effort Preemption Window**: The ACPI shutdown window provides **up to
   30 seconds on a best-effort basis** (not guaranteed under severe physical
   capacity emergencies), so keep checkpointing scripts fast and idempotent and
   persist critical state continuously. See
   [Spot VMs](https://docs.cloud.google.com/compute/docs/instances/create-use-spot.md.txt).
2. **Attach a `shutdown-script` & Check the Metadata Server**: Query
   `http://metadata.google.internal/computeMetadata/v1/instance/preempted` with
   header `Metadata-Flavor: Google` (`TRUE` during preemption vs. `FALSE` on
   normal shutdown):

```sh
gcloud compute instances add-metadata {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --metadata=shutdown-script='#!/bin/bash
PREEMPTED=$(curl -s "http://metadata.google.internal/computeMetadata/v1/instance/preempted" -H "Metadata-Flavor: Google")
if [ "$PREEMPTED" = "TRUE" ]; then
  echo "Spot VM preemption detected; flushing checkpoints..."
  # Insert fast (<20s), idempotent checkpoint or drain command here
fi'
```

3. **Safe Rollback of Test Shutdown Metadata (Always Include)**:
   ```sh
   gcloud compute instances remove-metadata {vm_name} --project={project_id} --zone={zone} --keys=shutdown-script
   ```

### Case E: VM Lifecycle Events Dashboard & High-Availability SAP Workloads

1. **`GCE VM Lifecycle Events Monitoring` Dashboard (`vm-lifecycle-events`
   Log-Based Metric)**:
   To populate the pre-generated **`GCE VM Lifecycle Events Monitoring`**
   dashboard in Cloud Monitoring (**Monitoring > Dashboards > Dashboard List**),
   create the `vm-lifecycle-events` counter metric using `--config-from-file` so
   the required `method` `STRING` label extractor on `protoPayload.methodName`
   is included (`gcloud logging metrics create --log-filter` alone omits label
   extractors):
   ```yaml
   # Save as vm-lifecycle-events-metric.yaml:
   name: vm-lifecycle-events
   description: "Count of Compute Engine VM lifecycle and host events by method"
   filter: >-
     resource.type="gce_instance" AND
     (log_id("cloudaudit.googleapis.com/activity") OR log_id("cloudaudit.googleapis.com/system_event")) AND
     operation.first="true"
   metricDescriptor:
     metricKind: DELTA
     valueType: INT64
     unit: "1"
     labels:
       - key: method
         valueType: STRING
         description: "Compute Engine lifecycle or host event method"
   labelExtractors:
     method: >-
       REGEXP_EXTRACT(protoPayload.methodName, "(recreateInstance|hostError|automaticRestart|guestTerminate|terminateOnHostMaintenance|preempted|insert|stop|delete|reset|start)")
   ```
   ```sh
   gcloud logging metrics create vm-lifecycle-events --project={project_id} --config-from-file=vm-lifecycle-events-metric.yaml
   ```
2. **SAP Workloads (HANA / NetWeaver)**:
   If the impacted VM runs **SAP HANA** or **SAP NetWeaver**, verify automatic
   Pacemaker cluster failover to the secondary node in Cloud Monitoring using
   the **SAP HANA Availability**
   (`google_agent_for_sap.agent-for-sap-hana-availability-monitoring`) or **SAP
   NetWeaver Availability**
   (`google_agent_for_sap.agent-for-sap-netweaver-availability-monitoring`)
   dashboards.

---

## Verification, Rollback & Cleanup

1. **Verify Updated Scheduling Policy**:
   ```sh
   gcloud compute instances describe {vm_name} --project={project_id} --zone={zone} \
       --format="yaml(scheduling, resourceStatus.upcomingMaintenance)"
   ```
2. **Remove Test Shutdown Metadata**:
   ```sh
   gcloud compute instances remove-metadata {vm_name} --project={project_id} --zone={zone} --keys=shutdown-script
   ```
3. **Teardown Temporary Test VMs**: Delete any temporary test VMs when finished
   (omitting `--quiet` on manual commands so interactive confirmation prevents
   accidental disk loss):
   ```sh
   gcloud compute instances delete {vm_name} --project={project_id} --zone={zone} --delete-disks=all
   ```
4. **Pricing Reference**: Read-only troubleshooting queries create no billable
   VM resources (user-defined log-based metrics and Log Analytics queries on
   linked BigQuery datasets follow standard Cloud Monitoring and BigQuery
   pricing). Consult [Google Cloud pricing](https://cloud.google.com/pricing)
   and [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)
   for current Standard vs. Spot regional rates rather than hardcoded dollar
   figures.
