# Configure Compute Engine and AI Hypercomputer Alerts

Configure observability and alerting policies for Google Cloud Compute Engine VMs, Managed Instance Groups (MIGs), and AI Hypercomputer GPU and TPU reservations using Terraform and PromQL.

## Table of Contents

* [Discover Resource Parameters and Schemas](#discover-resource-parameters-and-schemas): Lines 28-49
* [Monitor Core Compute Engine VM Golden Signals](#monitor-core-compute-engine-vm-golden-signals): Lines 50-128
  * [Monitor Hypervisor CPU Utilization](#monitor-hypervisor-cpu-utilization): Lines 52-63
  * [Monitor Guest OS Memory Saturation](#monitor-guest-os-memory-saturation): Lines 64-78
  * [Monitor Mounted Filesystem Disk Space](#monitor-mounted-filesystem-disk-space): Lines 79-100
  * [Monitor Persistent Disk and Hyperdisk I/O Throttling](#monitor-persistent-disk-and-hyperdisk-io-throttling): Lines 101-113
  * [Monitor Network Egress, Packet Drops, and MIG Saturation](#monitor-network-egress-packet-drops-and-mig-saturation): Lines 114-128
* [Configure Host and Reservation Maintenance Alerts](#configure-host-and-reservation-maintenance-alerts): Lines 129-213
  * [Differentiate Planned, Emergent, and Combined Maintenance](#differentiate-planned-emergent-and-combined-maintenance): Lines 154-192
  * [Filter Maintenance Lifecycle Events](#filter-maintenance-lifecycle-events): Lines 193-213
* [Monitor VM Availability and Interruption Reports](#monitor-vm-availability-and-interruption-reports): Lines 214-263
  * [Detect Stopped VMs with Absent Uptime Conditions](#detect-stopped-vms-with-absent-uptime-conditions): Lines 216-221
  * [Alert on VM Interruption Count Metrics](#alert-on-vm-interruption-count-metrics): Lines 222-239
  * [Diagnose Interruptions with Interruption Report Logs](#diagnose-interruptions-with-interruption-report-logs): Lines 240-263
* [Configure GPU XID Health Insights Alerts](#configure-gpu-xid-health-insights-alerts): Lines 264-285
* [Monitor Machine, Sub-Block, and Fabric Health](#monitor-machine-sub-block-and-fabric-health): Lines 286-326
  * [Query Machine and Fabric Health Metrics](#query-machine-and-fabric-health-metrics): Lines 299-324
  * [Compare Current Metrics with Evolving Domain Signals](#compare-current-metrics-with-evolving-domain-signals): Lines 325-326

---

## Discover Resource Parameters and Schemas

Before finalizing alert thresholds, label matchers, or Terraform variables, ground all Compute Engine resource identifiers, hardware families, and capacity ceilings in actual resource configuration rather than guesswork:

* **Determine When to Execute or Parameterize**:
  * If a required parameter (such as `machine_type`, numeric `instance_id` versus `instance_name`, disk `device_name`, `storage_type`, `provisionedIops`, or `provisionedThroughput`, network egress bandwidth tier `totalEgressBandwidthTier`, MIG `max_replicas` or `location`, reservation `enableEmergentMaintenance`, `block_id`, or `subblock_id`, or Cloud Logging `_Default` bucket `retentionDays`) is **already supplied in the user prompt**, use the provided value directly.
  * If any parameter is **not specified** and live Google Cloud credentials are available, look it up using the CLI and API commands below. Always include the relevant lookup commands in your operational explanation so operators can verify or populate their Terraform variables.
  * **Guardrail**: Do **not** search the local workspace for unrelated `.tf` files or external modules. Always validate generated PromQL queries with `python3 scripts/lint_promql.py '<PROMQL_QUERY>'`.

| Alert Domain | Parameters to Look Up | CLI and Script Lookup Commands | REST API Field or Endpoint |
| :--- | :--- | :--- | :--- |
| **Metric Schema and PromQL Validation** | Exact PromQL metric name, `unit`, `metricKind`, `valueType`, resource and metric labels | `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type gce_instance` (or `gce_instance_group`, `compute.googleapis.com/Machine`) and `python3 scripts/lint_promql.py '<PROMQL_QUERY>'` | `GET monitoring.googleapis.com/v3/projects/{project}/metricDescriptors` |
| **VM Identity and Machine Family** | Numeric `instance_id` (`id`), string `instance_name` (`name`), `zone`, `machineType` (`e2-*` versus `n2`, `c2`, `c3`, `m2`, `a3`, or `a4`) | `gcloud compute instances list --project=<PROJECT_ID> --format="table(id,name,zone.basename(),machineType.basename(),status)"` | `instances.get` $\rightarrow$ `id`, `name`, `zone`, `machineType` |
| **Guest OS and Cloud Ops Agent** | Guest OS license (`cos-cloud` versus Linux or Windows), Ops Agent metadata (`enable-osconfig`), active `agent.googleapis.com/*` time series | `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(machineType,disks[].licenses,metadata.items)"` and `gcloud monitoring time-series list --project=<PROJECT_ID> --filter='metric.type=starts_with("agent.googleapis.com/")' --limit=5` | `instances.get` $\rightarrow$ `disks[].licenses[]`, `metadata.items[]`; `projects.timeSeries.list` |
| **Persistent Disk and Hyperdisk Caps** | Attached `device_name` (`deviceName`), `storage_type` (`type`), `sizeGb`, `provisionedIops`, `provisionedThroughput` | `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="table(disks[].deviceName,disks[].source.basename(),disks[].type,disks[].interface)"` and `gcloud compute disks list --project=<PROJECT_ID> --format="table(name,zone.basename(),type.basename(),sizeGb,provisionedIops,provisionedThroughput)"` | `instances.get` $\rightarrow$ `disks[].deviceName`; `disks.get` $\rightarrow$ `type`, `sizeGb`, `provisionedIops`, `provisionedThroughput` |
| **Network Egress Bandwidth Cap** | Machine family vCPU count (`guestCpus`), `nicType` (`GVNIC`), `totalEgressBandwidthTier` (`TIER_1` versus `DEFAULT`) | `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(machineType,networkPerformanceConfig.totalEgressBandwidthTier,networkInterfaces[].nicType)"` and `gcloud compute machine-types describe <MACHINE_TYPE> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(name,guestCpus)"` | `instances.get` $\rightarrow$ `networkPerformanceConfig.totalEgressBandwidthTier`; `machineTypes.get` $\rightarrow$ `guestCpus` |
| **MIG Autoscaler Ceiling** | `instance_group_name`, `location` (zone or region), `max_replicas` (`maxNumReplicas`), `minNumReplicas`, `targetSize` | `gcloud compute instance-groups managed list --project=<PROJECT_ID> --format="table(name,location(),targetSize,autoscaler.autoscalingPolicy.maxNumReplicas,autoscaler.autoscalingPolicy.mode)"` and `gcloud compute autoscalers list --project=<PROJECT_ID> --format="table(name,target.basename(),autoscalingPolicy.maxNumReplicas)"` | `instanceGroupManagers.get` / `regionInstanceGroupManagers.get` $\rightarrow$ `status.autoscaler`; `autoscalers.get` $\rightarrow$ `autoscalingPolicy.maxNumReplicas` |
| **Reservations, Blocks, Sub-Blocks, and Maintenance Types** | `reservation_id`, `enableEmergentMaintenance`, maintenance `type` (`scheduled`, `unscheduled`, or `multiple`), `block_id`, `subblock_id`, `cluster_id`, `subblockHealthInfo` | `gcloud compute reservations describe <RESERVATION_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(id,name,enableEmergentMaintenance,specificReservation,resourceStatus)"`; `gcloud compute reservations blocks list <RESERVATION_NAME> --zone=<ZONE> --project=<PROJECT_ID>`; `gcloud compute reservations sub-blocks list <RESERVATION_NAME> --block-name=<BLOCK_NAME> --zone=<ZONE> --project=<PROJECT_ID>` | `reservations.get`, `reservationBlocks.list`/`get`, `reservationSubBlocks.list`/`get` (`--full-view=SUB_BLOCK_VIEW_FULL`) |
| **Cloud Logging Bucket Retention and Reports** | `_Default` log bucket `retentionDays` ($\ge 3$ days required for 72h diagnosis), active interruption and XID logs | `gcloud logging buckets describe _Default --location=global --project=<PROJECT_ID> --format="value(retentionDays)"` and `gcloud logging read 'resource.type="gce_instance" AND (log_id("compute.googleapis.com/interruption_report") OR log_id("compute.googleapis.com/gpu_health_insights_report"))' --project=<PROJECT_ID> --limit=5` | `logging.googleapis.com/v2/projects/{project}/locations/global/buckets/_Default` $\rightarrow$ `retentionDays` |

---

## Monitor Core Compute Engine VM Golden Signals

### Monitor Hypervisor CPU Utilization
* **PromQL Metric**: `compute_googleapis_com:instance_cpu_utilization` (`monitored_resource="gce_instance"`)
* **Scale**: Fractional `0.0` to `1.0` (`unit = "10^2.%"`). Set threshold to `> 0.85` for 85%.
* **Parameter and Resource Lookups**:
  * Look up numeric `instance_id` (`id`), human-readable `instance_name` (`name`), `zone`, and `machineType` (including shared-core `e2-micro`, `e2-small`, and `e2-medium` bursting behavior versus dedicated vCPUs) by running:
    `gcloud compute instances list --project=<PROJECT_ID> --format="table(id,name,zone.basename(),machineType.basename(),status)"`
  * Verify metric descriptor unit and labels by running:
    `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type gce_instance --metric-prefix compute.googleapis.com/instance/cpu/`
* **Grouping and Filtering Rules**:
  * Always aggregate with `avg by (instance_id, instance_name, zone)` or `avg_over_time(...[5m])` — **never** flat-sum CPU percentages across instances (`sum(...)`).
  * Filter human-readable VM names using `instance_name` or `metadata_system_name` (never assign a string hostname to numeric `instance_id`).

### Monitor Guest OS Memory Saturation
* **Prerequisite and Cost Guardrail (MUST Explain)**: You **must** explain that native hypervisor memory metrics (`compute.googleapis.com/instance/memory/balloon/ram_used`) are **only available for E2 family VMs**. For N2, C2, C3, M2, A3, and A4 VMs, the **Cloud Ops Agent** must be installed on the VM to emit `agent.googleapis.com/memory/percent_used`, and you **must explicitly state that the Cloud Ops Agent incurs Cloud Monitoring metric ingestion charges** (see [Cloud Monitoring pricing](https://docs.cloud.google.com/stackdriver/pricing.md.txt)).
* **Parameter and Resource Lookups**:
  * **Machine Type Lookup**: Verify whether target VMs belong to the `e2-*` series or non-E2 series (`n2-*`, `c2-*`, `c3-*`, `m2-*`, `a3-*`, `a4-*`) by running:
    `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="value(machineType.basename())"`
  * **Ops Agent Telemetry Verification**: Verify whether the Cloud Ops Agent is installed and actively reporting `agent.googleapis.com/memory/percent_used` in the project by running:
    `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type gce_instance --metric-prefix agent.googleapis.com/memory/` or `gcloud monitoring time-series list --project=<PROJECT_ID> --filter='metric.type="agent.googleapis.com/memory/percent_used"' --limit=5`
* **PromQL Query**:
  ```promql
  avg by (instance_id, zone) (
    agent_googleapis_com:memory_percent_used{monitored_resource="gce_instance", state="used"}
  ) >= 90
  ```
  *Alternatively, sum non-free states: `sum by (instance_id, zone) (agent_googleapis_com:memory_percent_used{monitored_resource="gce_instance", state!="free"}) >= 90`. Never sum across all states, which always equals 100%.*

### Monitor Mounted Filesystem Disk Space
* **Prerequisite and Cost Guardrail (MUST Explain)**: You **must** explain that standard hypervisor `compute.googleapis.com/instance/disk/*` metrics only measure block-level I/O (bytes and IOPS), not mounted filesystem fullness (`ENOSPC`). Monitoring mounted disk space requires the **Cloud Ops Agent** (`agent.googleapis.com/disk/*`, which **incurs Cloud Monitoring metric ingestion charges**; see [Cloud Monitoring pricing](https://docs.cloud.google.com/stackdriver/pricing.md.txt)) or Container-Optimized OS guest metrics (`compute.googleapis.com/guest/disk/bytes_used`).
* **Parameter and Resource Lookups**:
  * **Guest OS Image and Device Lookup**: Inspect the boot and data disk OS license (to distinguish `cos-cloud` Container-Optimized OS from standard Linux or Windows) and attached block `deviceName` values by running:
    `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(disks[].deviceName,disks[].licenses,metadata.items)"`
  * **Active Filesystem Metric and `device` Label Discovery**: Verify active `agent.googleapis.com/disk/percent_used` or `compute.googleapis.com/guest/disk/bytes_used` series and mounted `device` labels by running:
    `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type gce_instance --metric-prefix agent.googleapis.com/disk/`
* **PromQL Queries**:
  * **Static Threshold (>85%)**:
    ```promql
    max by (instance_id, device, zone) (
      agent_googleapis_com:disk_percent_used{monitored_resource="gce_instance", state="used", device!~"loop.*|tmpfs|squashfs"}
    ) > 85
    ```
  * **4-Day Linear Exhaustion Forecast**:
    ```promql
    predict_linear(
      agent_googleapis_com:disk_bytes_used{monitored_resource="gce_instance", state="free"}[6h:5m],
      4 * 24 * 3600
    ) < 0
    ```

### Monitor Persistent Disk and Hyperdisk I/O Throttling
* **Metrics (`monitored_resource="gce_instance"`)**:
  * Throttled IOPS: `compute_googleapis_com:instance_disk_throttled_read_ops_count`, `compute_googleapis_com:instance_disk_throttled_write_ops_count`
  * Throttled Throughput: `compute_googleapis_com:instance_disk_throttled_read_bytes_count`, `compute_googleapis_com:instance_disk_throttled_write_bytes_count`
  * Total IOPS, Throughput, and Latency: `compute_googleapis_com:instance_disk_read_ops_count`, `compute_googleapis_com:instance_disk_write_ops_count`, `compute_googleapis_com:instance_disk_read_bytes_count`, `compute_googleapis_com:instance_disk_write_bytes_count`, `compute_googleapis_com:instance_disk_average_io_latency`
* **Parameter and Resource Lookups**:
  * **Disk Type and Provisioned IOPS or Throughput Lookup**: Look up each disk's `type` (`pd-balanced`, `pd-ssd`, `pd-extreme`, `hyperdisk-balanced`, `hyperdisk-extreme`, `hyperdisk-throughput`, `hyperdisk-ml`), `sizeGb`, `provisionedIops`, and `provisionedThroughput` by running:
    `gcloud compute disks list --project=<PROJECT_ID> --format="table(name,zone.basename(),type.basename(),sizeGb,provisionedIops,provisionedThroughput)"`
    `gcloud compute disks describe <DISK_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(name,type,sizeGb,provisionedIops,provisionedThroughput)"`
  * **VM `device_name` Mapping**: Resolve how each disk maps to the `device_name` and `storage_type` metric labels on the VM by running:
    `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="table(disks[].deviceName,disks[].source.basename(),disks[].type,disks[].interface)"`
* **Rule**: Wrap `DELTA` counters in `rate(...[5m])`, group by `(instance_id, instance_name, device_name, storage_type, zone)`, and use `duration = "300s"` to filter out sub-second micro-burst throttling.

### Monitor Network Egress, Packet Drops, and MIG Saturation
* **Parameter and Resource Lookups**:
  * **Per-VM Network Egress Bandwidth Ceiling Lookup**: Because Compute Engine egress bandwidth limits depend on machine family, vCPU count (`2 Gbps` per vCPU up to the machine-series standard cap), and whether `TIER_1` high-bandwidth networking on `GVNIC` is enabled, look up the VM's networking tier and vCPU count before setting static bytes-per-second thresholds:
    `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(machineType,networkPerformanceConfig.totalEgressBandwidthTier,networkInterfaces[].nicType)"`
    `gcloud compute machine-types describe <MACHINE_TYPE> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(name,guestCpus)"`
    *Convert the resolved Gbps limit to bytes per second using $\text{Gbps} \times 125{,}000{,}000$ and set the alert threshold at 80–85% of the ceiling; use `125000000` (1 Gbps) as a baseline when unspecified.*
  * **MIG `max_replicas` and Location Lookup**: Look up the Managed Instance Group's `name` (`instance_group_name`), `location` (zone for zonal MIGs or region for regional MIGs), `targetSize`, and autoscaler ceiling (`autoscaler.autoscalingPolicy.maxNumReplicas`) by running:
    `gcloud compute instance-groups managed list --project=<PROJECT_ID> --format="table(name,location(),targetSize,autoscaler.autoscalingPolicy.maxNumReplicas,autoscaler.autoscalingPolicy.minNumReplicas,autoscaler.autoscalingPolicy.mode)"`
    `gcloud compute instance-groups managed describe <MIG_NAME> [--zone=<ZONE> | --region=<REGION>] --project=<PROJECT_ID> --format="yaml(name,targetSize,status.autoscaler,autoscaler.autoscalingPolicy)"`
* **Network Egress Bandwidth**: `sum by (instance_id, instance_name, zone) (rate(compute_googleapis_com:instance_network_sent_bytes_count{monitored_resource="gce_instance"}[5m])) > 125000000` (1 Gbps = 125 MB/s; scale to 80–85% of the looked-up machine-type or `TIER_1` bandwidth cap).
* **Packet Drops**: `compute_googleapis_com:firewall_dropped_packets_count` (VPC firewall drops) and `agent_googleapis_com:interface_errors` (Ops Agent guest NIC RX/TX errors).
* **MIG Capacity Saturation**: Compare `compute_googleapis_com:instance_group_size{monitored_resource="gce_instance_group"}` (or `autoscaler_googleapis_com:capacity`) by `(instance_group_name, location)` against `max_replicas` (`autoscalingPolicy.maxNumReplicas`) at Warning (`> 0.80`) and Critical (`>= 0.95`).

---

## Configure Host and Reservation Maintenance Alerts

For Compute Engine VMs and AI Hypercomputer GPU and TPU reservations (`A3`, `A3 Ultra`, `A4`, `A4X`, `A4X Max`), configure log-based alerting policies (`google_monitoring_alert_policy` with `condition_matched_log` or `google_logging_metric`) to track scheduled, started, and completed maintenance and repair events—including differentiating **Planned maintenance (`type=scheduled`)**, **Emergent maintenance (`type=unscheduled`)**, and **Combined planned and emergent maintenance (`type=multiple`)**.

* **Parameter and Topology Lookups**:
  * **Reservation, Maintenance `type`, and `enableEmergentMaintenance` Lookup**: Inspect reservation names, machine types, `enableEmergentMaintenance` status, and `resourceStatus.reservationMaintenance` (`upcomingGroupMaintenance.type`, `upcomingGroupMaintenance.maintenanceReasons`, `windowStartTime`, `windowEndTime`) by running:
    `gcloud compute reservations list --project=<PROJECT_ID> --format="table(name,zone.basename(),specificReservation.instanceProperties.machineType,specificReservation.count,enableEmergentMaintenance)"`
    `gcloud compute reservations describe <RESERVATION_NAME> --zone=<ZONE> --project=<PROJECT_ID> --flatten=resourceStatus.reservationMaintenance`
    *REST API: `GET https://compute.googleapis.com/compute/v1/projects/{project}/aggregated/reservations?fields=items.name,items.specificReservation.instanceProperties.machineType,items.enableEmergentMaintenance,items.resourceStatus.reservationMaintenance`*
  * **Reservation Block and Sub-Block Topology Lookup**: Discover block and sub-block names, IDs, `upcomingGroupMaintenance.type`, and pending or ongoing maintenance counts by running:
    `gcloud compute reservations blocks list <RESERVATION_NAME> --zone=<ZONE> --project=<PROJECT_ID>`
    `gcloud compute reservations blocks describe <RESERVATION_NAME> --block-name=<BLOCK_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(id,name,reservationBlockMaintenance)"`
    `gcloud compute reservations sub-blocks list <RESERVATION_NAME> --block-name=<BLOCK_NAME> --zone=<ZONE> --project=<PROJECT_ID>`
    `gcloud compute reservations sub-blocks describe <RESERVATION_NAME> --block-name=<BLOCK_NAME> --sub-block-name=<SUB_BLOCK_NAME> --zone=<ZONE> --full-view=SUB_BLOCK_VIEW_FULL --project=<PROJECT_ID>`
  * **VM Instance Maintenance `type` Lookup**: Inspect individual VM upcoming maintenance metadata (`resourceStatus.upcomingMaintenance.type`) by running:
    `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(resourceStatus.upcomingMaintenance)"`
    *Or query from inside the Guest OS using `curl "http://metadata.google.internal/computeMetadata/v1/instance/upcoming-maintenance?alt=json" -H "Metadata-Flavor: Google"`.*

> [!TIP]
> * **7-Day Advance Notice (`enableEmergentMaintenance`)**: Recommend enabling hardware emergency maintenance notifications (`gcloud compute reservations update RESERVATION_NAME --enable-emergent-maintenance --zone=ZONE` or `enableEmergentMaintenance: true` in REST) to increase advance notice from a few hours to **at least 7 days** for unplanned host repairs. Wait for explicit user confirmation before executing `gcloud compute reservations update`.
> * **Maintenance Reasons (`upcomingGroupMaintenance.maintenanceReasons` / `protoPayload.metadata.maintenanceReasons`)**:
>   * **Planned**: `PLANNED_UPDATE`, `PLANNED_NETWORK_UPDATE`, `FAILURE_GPU_CUSTOMER_REPORTED` (after faulty host report).
>   * **Unplanned or Emergency**: `FAILURE_GPU`, `FAILURE_GPU_XID`, `FAILURE_GPU_TEMPERATURE`, `FAILURE_NVLINK`, `FAILURE_DISK`, `FAILURE_MEMORY`, `FAILURE_INTERFACE`, `FAILURE_NETWORK`, `FAILURE_INFRA`.
> * **Proactive Manual Maintenance**: Operators can proactively trigger maintenance before the scheduled window using `gcloud compute reservations perform-maintenance`, `gcloud compute reservations blocks perform-maintenance`, or `gcloud compute reservations sub-blocks perform-maintenance` with `--scope=all|running|unused`. Never execute `perform-maintenance` commands without explicit user confirmation.

### Differentiate Planned, Emergent, and Combined Maintenance

Maintenance notification metadata includes a **`type`** field that distinguishes routine planned maintenance from urgent hardware or emergent maintenance:
* **Cloud Audit Logs (`cloudaudit.googleapis.com/system_event`)**: Populated at **`protoPayload.metadata.type`** (flat top-level key inside `protoPayload.metadata` on `compute.instances.upcomingMaintenance`, `compute.reservations.upcomingGroupMaintenance`, `compute.reservations.block.upcomingGroupMaintenance`, and `compute.reservations.subBlock.upcomingGroupMaintenance`).
* **Compute Engine API and Guest Metadata**: Populated at `resourceStatus.upcomingMaintenance.type` (VM instances) and `upcomingGroupMaintenance.type` (reservations, blocks, and sub-blocks).

| Metadata `type` Value | Maintenance Category | Description and Alert Routing Strategy |
| :--- | :--- | :--- |
| **`scheduled`** (`"SCHEDULED"`) | **Planned Maintenance** | Routine infrastructure or network updates (`PLANNED_UPDATE`, `PLANNED_NETWORK_UPDATE`, or `FAILURE_GPU_CUSTOMER_REPORTED`) scheduled with standard advance notice (7+ days). Route to **Warning or ticket** channels so operators can plan a maintenance window or run `perform-maintenance` proactively. |
| **`unscheduled`** (`"UNSCHEDULED"`) | **Emergent Maintenance** | Urgent, unplanned host hardware or critical security repairs (`FAILURE_GPU`, `FAILURE_GPU_XID`, `FAILURE_GPU_TEMPERATURE`, `FAILURE_NVLINK`, `FAILURE_DISK`, `FAILURE_MEMORY`, `FAILURE_INTERFACE`, `FAILURE_NETWORK`, `FAILURE_INFRA`). Route to **Critical or paging** channels so operators can checkpoint jobs and drain or repair affected capacity. |
| **`multiple`** (`"MULTIPLE"`) | **Combination of Planned and Emergent Maintenance** | Indicates that **both planned (`scheduled`) and emergent (`unscheduled`) maintenance events** are pending concurrently within the same group window (emitted on **Reservations, Reservation Blocks, and Sub-Blocks**). **Always include `type=multiple` (`"MULTIPLE"`) alongside `type=unscheduled` (`"UNSCHEDULED"`) in Emergent Maintenance alerts** so an existing planned maintenance window never masks a newly scheduled urgent hardware repair. |

> [!IMPORTANT]
> **Avoid Filtering Emergent or Multiple Alerts by `protoPayload.status.message =~ "scheduled"`**: For `UNSCHEDULED` and `MULTIPLE` group maintenance events on reservation blocks and sub-blocks, `protoPayload.status.message` reads `"Urgent maintenance is required..."` or `"Multiple maintenance events are required..."` (which does **not** contain the word `"scheduled"`). When differentiating Planned versus Emergent maintenance, filter directly on **`protoPayload.metadata.type`** (using case-insensitive regex `protoPayload.metadata.type =~ "(?i)^scheduled$"` or exact uppercase enum `protoPayload.metadata.type="SCHEDULED"`, `"UNSCHEDULED"`, `"MULTIPLE"`), optionally paired with `protoPayload.metadata.maintenanceStatus="PENDING"` to alert only when a window is pending rather than ongoing.

#### Filter Log-Based Alerts by Maintenance Type

1. **Planned Maintenance Alert (`type=scheduled` / `"SCHEDULED"`)**:
   ```text
   protoPayload.methodName=~"^compute\.(instances\.upcomingMaintenance|reservations\.(block\.|subBlock\.)?upcomingGroupMaintenance)$" AND severity>=DEFAULT AND protoPayload.metadata.type=~"(?i)^scheduled$"
   ```
   *Or exact match: `protoPayload.metadata.type="SCHEDULED"`.*
2. **Emergent Maintenance Alert (`type=unscheduled` / `"UNSCHEDULED"` and `type=multiple` / `"MULTIPLE"`)**:
   * **Emergent Only (`type=unscheduled`)**:
     ```text
     protoPayload.methodName=~"^compute\.(instances\.upcomingMaintenance|reservations\.(block\.|subBlock\.)?upcomingGroupMaintenance)$" AND severity>=DEFAULT AND protoPayload.metadata.type=~"(?i)^unscheduled$"
     ```
     *Or exact match: `protoPayload.metadata.type="UNSCHEDULED"`.*
   * **Emergent and Combined Planned/Emergent (`type=unscheduled` OR `type=multiple` — Recommended for Paging on Any Urgent Repair)**:
     ```text
     protoPayload.methodName=~"^compute\.(instances\.upcomingMaintenance|reservations\.(block\.|subBlock\.)?upcomingGroupMaintenance)$" AND severity>=DEFAULT AND protoPayload.metadata.type=~"(?i)^(unscheduled|multiple)$"
     ```
     *Or exact match: `(protoPayload.metadata.type="UNSCHEDULED" OR protoPayload.metadata.type="MULTIPLE")`.*
3. **Combination of Planned and Emergent Maintenance Alert (`type=multiple` / `"MULTIPLE"`, Group/Reservation/Block/Sub-Block)**:
   ```text
   protoPayload.methodName=~"^compute\.reservations\.(block\.|subBlock\.)?upcomingGroupMaintenance$" AND severity>=DEFAULT AND protoPayload.metadata.type=~"(?i)^multiple$"
   ```
   *Or exact match: `protoPayload.metadata.type="MULTIPLE"`.*

### Filter Maintenance Lifecycle Events

1. **Reservation-Level Group Maintenance**:
   * **Scheduled**: `protoPayload.methodName="compute.reservations.upcomingGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "scheduled"`
   * **Completed**: `protoPayload.methodName="compute.reservations.completedGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "completed"`
2. **Reservation Block-Level Group Maintenance**:
   * **Scheduled**: `protoPayload.methodName="compute.reservations.block.upcomingGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "scheduled"`
   * **Started**: `protoPayload.methodName="compute.reservations.block.startGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "started"`
   * **Completed**: `protoPayload.methodName="compute.reservations.block.completedGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "completed"`
3. **Reservation Sub-Block Maintenance and Unused Machine Repairs (A4X and A4X Max)**:
   * **Scheduled**: `protoPayload.methodName="compute.reservations.subBlock.upcomingGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "scheduled"`
   * **Started**: `protoPayload.methodName="compute.reservations.subBlock.startGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "started"`
   * **Completed**: `protoPayload.methodName="compute.reservations.subBlock.completedGroupMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "completed"`
   * **Unused Machine Repair Started**: `protoPayload.methodName="compute.reservations.subblock.unusedmachinerepair" AND severity>=DEFAULT AND protoPayload.status.message =~ "maintenance"`
   * **Unused Machine Repair Completed**: `protoPayload.methodName="compute.reservations.subblock.unusedmachinerepaircomplete" AND severity>=DEFAULT AND protoPayload.status.message =~ "repaired"`
4. **Individual Compute Instance Host Maintenance**:
   * **Scheduled, Window Opened, or Completed**: `protoPayload.methodName="compute.instances.upcomingMaintenance" AND severity>=DEFAULT AND protoPayload.status.message =~ "(scheduled|ongoing|completed)"`
   * **Started (Termination on Maintenance)**: `protoPayload.methodName="compute.instance.terminateOnHostMaintenance" AND severity>=DEFAULT`

---

## Monitor VM Availability and Interruption Reports

### Detect Stopped VMs with Absent Uptime Conditions
When a Compute Engine (GCE) VM stops, crashes, or is terminated, it **stops emitting `compute.googleapis.com/instance/uptime` time-series samples altogether**. Consequently, a simple threshold alert (`compute.googleapis.com/instance/uptime < 1`) will **fail to trigger**. Always use `absent_over_time(compute_googleapis_com:instance_uptime{monitored_resource="gce_instance"}[5m])` (or `condition_absent`) to detect down VMs, and `compute_googleapis_com:instance_uptime_total < 300` to detect recent reboots.
* **Parameter and Resource Lookups**:
  * Verify VM host maintenance policy (`scheduling.onHostMaintenance`: `MIGRATE` versus `TERMINATE` and `scheduling.automaticRestart`) by running:
    `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(id,name,status,scheduling)"`

### Alert on VM Interruption Count Metrics
* **PromQL Metric**: `compute_googleapis_com:instance_interruption_count` (`monitored_resource="gce_instance"`, `GAUGE`, `INT64`, emitted every 1m with ~2m latency; the stream is undefined when the count is 0).
* **Parameter and Schema Lookup**:
  * Verify `interruption_count` label keys and documented enums by running:
    `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type gce_instance --metric-prefix compute.googleapis.com/instance/interruption_count`
* **Labels and Mapping**:
  * `interruption_type="TerminationEvent"` $\rightarrow$ `interruption_reason` $\in$ `["HostError", "UrgentRepairs", "UserReportedFault", "UserInitiatedTermination"]`
  * `interruption_type="MaintenanceEvent"` $\rightarrow$ `interruption_reason` $\in$ `["PlannedMaintenance", "EmergentMaintenance"]`
* **PromQL Query (Paging on Unplanned Disruptions)**:
  ```promql
  sum by (instance_id, instance_name, zone, interruption_type, interruption_reason) (
    compute_googleapis_com:instance_interruption_count{
      monitored_resource="gce_instance",
      interruption_reason=~"HostError|UrgentRepairs|EmergentMaintenance|UserReportedFault"
    }
  ) > 0
  ```

### Diagnose Interruptions with Interruption Report Logs
* **Log Stream**: `log_id("compute.googleapis.com/interruption_report")` (or `logName=~"logs/compute.googleapis.com%2Finterruption_report"`) on `resource.type="gce_instance"`.
* **Parameter and Log Retention Lookups**:
  * **Cloud Logging Bucket Retention Lookup**: Verify that the target Cloud Logging bucket (`_Default` or custom routed bucket) has `retentionDays >= 3` (72+ hours) by running:
    `gcloud logging buckets describe _Default --location=global --project=<PROJECT_ID> --format="value(retentionDays)"`
    *If `retentionDays` is less than 3, update it with `gcloud logging buckets update _Default --location=global --retention-days=30 --project=<PROJECT_ID>` after obtaining explicit user confirmation.*
  * **Recent Interruption Report Payload Inspection**: Inspect recent `instanceInterruptionReport` and `resourceTopology` (`reservationId`, `blockId`, `subblockId`, `machineId`) entries by running:
    `gcloud logging read 'resource.type="gce_instance" AND log_id("compute.googleapis.com/interruption_report")' --project=<PROJECT_ID> --limit=5 --format=json`
* **Payload Fields (`jsonPayload.instanceInterruptionReport` and `jsonPayload.resourceTopology`)**:
  * `impactCategory`: `"INSTANCE_INTERRUPTION"`
  * `resourceTopology`: `reservationId`, `blockId`, `subblockId`, `machineId`
  * `type`: `"CRITICAL_FAILURE"` (maps to `HostError`), `"URGENT_REPAIR"` (maps to `UrgentRepairs`), `"EMERGENT_MAINTENANCE"`, `"PLANNED_MAINTENANCE"`, `"USER_REPORTED_FAULT"`, `"USER_INITIATED_TERMINATION"`
  * `reason`:
    * `CRITICAL_FAILURE`: `FAILURE_HOST_SOFTWARE_KPANIC`, `FAILURE_HOST_SOFTWARE_SERR`, `FAILURE_HOST_SOFTWARE_OOM`, `FAILURE_GUEST_KPANIC`, `FAILURE_HOST_POWER`, `FAILURE_HOST_HARDWARE_GPU`
    * `EMERGENT_MAINTENANCE`: `FAILURE_DOMAIN_NVLINK`, `FAILURE_DOMAIN_NVSWITCH`, `FAILURE_DOMAIN_POWER`, `FAILURE_TOR_SWITCH`, `FAILURE_HOST`, `FAILURE_HOST_HARDWARE`, `FAILURE_HOST_HARDWARE_DISK`, `FAILURE_HOST_HARDWARE_MEMORY`, `FAILURE_HOST_HARDWARE_GPU`, `FAILURE_HOST_HARDWARE_GPU_XID`, `FAILURE_HOST_HARDWARE_TEMPERATURE`, `FAILURE_HOST_NETWORK`, `FAILURE_HOST_NETWORK_NIC`, `FAILURE_HOST_NETWORK_LINK`, `FAILURE_HOST_NETWORK_SOFTWARE`
    * `USER_REPORTED_FAULT`: `BEHAVIOR_UNSPECIFIED`, `PERFORMANCE`, `SILENT_DATA_CORRUPTION`, `UNRECOVERABLE_GPU_ERROR`
  * `status` (**72-Hour Diagnostic Lifecycle**):
    1. `"INITIAL_DIAGNOSIS"` (~30 minutes after VM termination)
    2. `"PENDING_DIAGNOSIS"` (~6 hours after VM termination)
    3. `"COMPLETE"` (final root cause diagnosis up to **72 hours** after termination)
* **Log Retention Requirement**: Always configure a Cloud Logging retention policy of **at least 3 days (72+ hours)** to ensure all diagnostic stages (`INITIAL_DIAGNOSIS` $\rightarrow$ `PENDING_DIAGNOSIS` $\rightarrow$ `COMPLETE`) are retained and matched.

---

## Configure GPU XID Health Insights Alerts

Operators running GPU workloads on `A3` (H100), `A3 Ultra` (H200), `A4` (B200), `A4X` (GB200), and `A4X Max` (GB300) instances often call the `Report host as faulty` API for every NVIDIA XID error, even when a **GPU reset** or **NVIDIA driver update** resolves the issue. **Compute Engine (GCE) GPU XID Insights** (published within 5–10 minutes of XID occurrence in syslog) categorizes XID errors and logs actionable recommendations:

* **Parameter and Resource Lookups**:
  * **Accelerator and Machine Family Lookup**: Confirm the VM's GPU machine family (`a3-highgpu-8g`, `a3-megagpu-8g`, `a3-ultragpu-8g`, `a4-highgpu-8g`, `a4x-*`) and attached `guestAccelerators` by running:
    `gcloud compute instances list --project=<PROJECT_ID> --filter="machineType ~ '(a3|a4)'" --format="table(id,name,zone.basename(),machineType.basename(),guestAccelerators[].acceleratorType.basename())"`
  * **GPU XID Insights and In-Band Event Log Lookup**: Inspect recent `gpu_health_insights_report` recommendations and raw in-band XID telemetry (`compute.googleapis.com/gpu_xid_events`, including `driverVersion`, `gpuUuid`, and `code`) by running:
    `gcloud logging read 'resource.type="gce_instance" AND (log_id("compute.googleapis.com/gpu_health_insights_report") OR log_id("compute.googleapis.com/gpu_xid_events"))' --project=<PROJECT_ID> --limit=5 --format=json`
* **Log Stream**: `log_id("compute.googleapis.com/gpu_health_insights_report")` (or `logName=~"logs/compute.googleapis.com%2Fgpu_health_insights_report"`)
* **Resource Type and Severity**: `resource.type="gce_instance"` AND `severity>=ERROR`
* **Payload Structure**:
  * `jsonPayload.impactCategory="GPU_INTERRUPTION"`
  * `jsonPayload.gpuInterruptionReport.xidInterruptionSources[]` (`xidCode`, `gpuUid`)
  * `jsonPayload.gpuInterruptionReport.summary` (contains explicit recommended action)
* **Actionable Remediation Matrix**:
  1. **GPU Driver Update Recommended**: **XIDs `109`, `119`, `120`** (`A3`, `A3-ultra`, `A4`, `A4x`, `A4x-max`) — upgrade to the recommended NVIDIA driver rather than calling `Report host as faulty`.
  2. **GPU Reset Recommended**: **XID `154`** (`A3`, `A3-ultra`, `A4`, `A4x`, `A4x-max`) and **XIDs `144`, `145`, `146`, `149`, `150`** (`A4`, `A4x`, `A4x-max`) — reset the affected GPU(s).
  3. **Host or NVLink Switch Repair**: **XID `79`** (GPU fallen off the bus) — requires physical technician repair through **Emergent Maintenance** (7-day notice when enabled; immediate VM disruption if disabled).

---

## Monitor Machine, Sub-Block, and Fabric Health

When monitoring AI Hypercomputer reservation SLA and SLO targets and physical host, sub-block, or NVLink and ICI fabric health transitions (`HEALTHY` $\rightarrow$ `UNHEALTHY`):

* **Parameter and Topology Lookups**:
  * **Physical Topology ID Lookup (`reservation_id`, `block_id`, `subblock_id`, `cluster_id`, `host`)**: Look up the topology hashes and IDs for instances, blocks, and sub-blocks by running:
    * **From VM Instance**: `gcloud compute instances describe <INSTANCE_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(id,name,resourceStatus.physicalTopology)"` (returns `physicalTopology.cluster`, `physicalTopology.block`, `physicalTopology.subblock`, `physicalTopology.host`).
    * **From Reservation Block (`PhysicalHostTopology`)**: `gcloud compute reservations blocks describe <RESERVATION_NAME> --block-name=<BLOCK_NAME> --zone=<ZONE> --project=<PROJECT_ID> --format="yaml(id,name,physicalTopology,instances)"`
    * **From Reservation Sub-Block (`subblockHealthInfo`)**: `gcloud compute reservations sub-blocks describe <RESERVATION_NAME> --block-name=<BLOCK_NAME> --sub-block-name=<SUB_BLOCK_NAME> --zone=<ZONE> --full-view=SUB_BLOCK_VIEW_FULL --project=<PROJECT_ID> --format="yaml(id,name,healthInfo,physicalTopology)"` (returns `healthyHostCount`, `degradedHostCount`, `healthyInfraCount`, `degradedInfraCount`).
  * **Metric Schema Discovery (`compute.googleapis.com/Machine` and `gce_instance`)**:
    `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type compute.googleapis.com/Machine --metric-prefix compute.googleapis.com/machine/`
    `python3 scripts/discover_metric_schema.py --project <PROJECT_ID> --resource-type gce_instance --metric-prefix compute.googleapis.com/instance/gpu/`

### Query Machine and Fabric Health Metrics
1. **Physical Machine Status (`compute.googleapis.com/machine/machine_status`)**:
   * **PromQL Metric**: `compute_googleapis_com:machine_machine_status`
   * **Monitored Resource**: `monitored_resource="compute.googleapis.com/Machine"`
   * **Labels**:
     * `machine_health`: `"HEALTHY"`, `"UNHEALTHY"`
     * `unhealthy_category`: `"REPAIRING"`, `"UNAVAILABLE"`, `"PENDING_USER_REPORT"`, `"UNKNOWN"` (populated when `machine_health="UNHEALTHY"`)
     * `machine_utilization`: values such as `"OCCUPIED"`
     * Topology labels: `reservation_id`, `block_id`, `subblock_id`, `cluster_id`
   * **PromQL Query (Unhealthy Machine or Sub-Block Degradation)**:
     ```promql
     sum by (reservation_id, block_id, subblock_id, cluster_id, unhealthy_category) (
       compute_googleapis_com:machine_machine_status{
         monitored_resource="compute.googleapis.com/Machine",
         machine_health="UNHEALTHY"
       }
     ) > 0
     ```
2. **VM and Slice Infrastructure Health (`compute.googleapis.com/instance/gpu/infra_health` and `compute.googleapis.com/instance/tpu/infra_health`)**:
   * **PromQL Metrics**: `compute_googleapis_com:instance_gpu_infra_health` and `compute_googleapis_com:instance_tpu_infra_health` (`monitored_resource="gce_instance"`)
   * **Labels**: `Value` (`"Healthy"`, `"Unhealthy"`, `"Unknown"`) / `health_status` (`"HEALTHY"`, `"UNHEALTHY"`), `unhealthy_category`, `reservation_id`, `block_id`, `subblock_id`, `machine_id`, `cluster_id`.
3. **NVLink, NVSwitch, GPU DRAM, and TPU ICI Fabric Health Metrics (`monitored_resource="gce_instance"`)**:
   * **GPU NVLink and NVSwitch**: `compute_googleapis_com:instance_gpu_gpu_nvlink_link_downed_counter`, `compute_googleapis_com:instance_gpu_nvswitch_link_downed_counter`, `compute_googleapis_com:instance_gpu_nvlink_runtime_error`
   * **GPU Memory (ECC and Row Remapping)**: `compute_googleapis_com:instance_gpu_dram_uncorrectable_ecc_error_count`, `compute_googleapis_com:instance_gpu_dram_row_remapping_failed`
   * **TPU Inter-Chip Interconnect (ICI)**: `compute_googleapis_com:instance_tpu_accelerator_network_ici_link_health`, `compute_googleapis_com:instance_tpu_accelerator_network_ici_link_flaps`

### Compare Current Metrics with Evolving Domain Signals
* Dedicated domain-level signals—including `domain_status` (with `healthy_host_count`, `degraded_host_count`, `degraded_switch_count`, `maintenance_slo_exceeded`, and `DOWNTIME_PERIOD_INCLUSION`), **Slot API health status enums**, **Subblock Describe API (`subblockHealthInfo`: `healthyHostCount`, `degradedHostCount`, `inSloHostCount`, `outSloHostCount`)**, and **Machine/Domain Repair Lifecycle logs (`PRE_REPAIR_DIAG`, `ACTIVE_REPAIR`, `POST_REPAIR_VALIDATION`, `COMPLETED`)**—are evolving across rollout phases. Always aggregate `compute_googleapis_com:machine_machine_status{machine_health="UNHEALTHY"}`, `compute_googleapis_com:instance_gpu_infra_health` / `instance_tpu_infra_health`, and NVLink or ICI fabric metrics by `(reservation_id, block_id, subblock_id, unhealthy_category)` to alert on machine and domain or sub-block health state changes in Cloud Monitoring today.
