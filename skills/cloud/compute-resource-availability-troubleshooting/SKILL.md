---
name: compute-resource-availability-troubleshooting
description: >-
  Diagnoses, mitigates, and prevents Google Compute Engine resource
  availability and capacity stockout errors (ZONE_RESOURCE_POOL_EXHAUSTED,
  ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS, and machine type or accelerator
  unavailable in zone). Use ONLY when VM creation, Managed Instance Group (MIG)
  scale-out, or stopped instance startup fails due to regional or zonal
  hardware capacity exhaustion for GPUs, TPUs, or specific CPU shapes. DO NOT
  read or use for IAM permission errors, project quota limit increases without
  stockouts, general greenfield VM creation, or unexpected host reboots on
  already-running VMs.
metadata:
  version: "1.0.0"
  category: Compute
---

# Compute Engine Resource Availability and Stockout Troubleshooting

> **MCP Tools:** `list_machine_types`, `list_accelerator_types`,
> `get_zone_operation`, `list_instance_group_managers`,
> `list_managed_instances`, `list_reservations`, `get_reservation_details`

This skill diagnoses and resolves Google Compute Engine resource availability
errors (capacity stockouts). It provides immediate tactical workarounds to get
blocked workloads running and long-term architectural mitigations using
Regional Managed Instance Group (MIG) distribution shapes, Instance
Flexibility, Dynamic Workload Scheduler (DWS) Flex-Start, and On-Demand
Capacity Reservations.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

---

## Prerequisites & Environment Setup

Any host, project, IAM, or Compute Engine resource modifications (installing
`gcloud`, configuring MCP, enabling APIs or Log Analytics, creating instances
or reservations, updating MIGs, or deleting resources) must be explicitly
approved by the user before execution.

1. **Google Cloud SDK**: Verify `gcloud` is installed (`gcloud --version`). If
   missing or outdated, ask the user for approval before installing via
   [Install the Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
2. **Compute Engine MCP Server & Capability Boundary**: When the Compute Engine
   MCP server is configured (see
   [Use the Compute Engine MCP server](https://docs.cloud.google.com/compute/docs/use-compute-engine-mcp.md.txt);
   requires `roles/mcp.toolUser`), prefer its read-only discovery tools before
   falling back to `gcloud`:
   - `list_machine_types` and `list_accelerator_types` to check whether a
     machine shape or GPU accelerator is offered in a target zone.
   - `get_zone_operation` to inspect a failed zonal operation's `error.errors`
     array (`ZONE_RESOURCE_POOL_EXHAUSTED`,
     `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`, or `QUOTA_EXCEEDED`).
   - `list_instance_group_managers` and `list_managed_instances` to inspect
     **zonal** MIGs and per-instance `currentAction` / `lastAttempt.errors`
     (note: all Compute Engine MCP MIG tools—`list_instance_group_managers`,
     `list_managed_instances`, and `get_instance_group_manager_basic_info`—only
     accept a `zone` parameter and cannot inspect **regional** MIGs; use
     `gcloud` with `--region={region}` or REST for regional MIGs).
   - `list_reservations` and `get_reservation_details` to inspect existing
     zonal reservation capacity (`specificReservation.count` vs.
     `specificReservation.inUseCount`).
   - **MCP Limitations (Use `gcloud` or REST Instead)**: MCP `create_instance`
     does **not** expose `provisioning_model` (`FLEX_START` / `SPOT`),
     `max_run_duration`, `instance_termination_action`, or
     `reservation_affinity`. MCP also lacks tools for Cloud Logging queries
     (`gcloud logging read`), Spot Capacity Advisor
     (`gcloud beta compute advice capacity`), Bulk Insert
     (`gcloud compute instances bulk create`), MIG distribution updates
     (`gcloud compute instance-groups managed update`), and reservation
     creation or deletion (`gcloud compute reservations create` / `delete`).
     Always use `gcloud` or the Compute Engine REST API for those operations.
3. **Authentication**: Local CLI (`gcloud auth login`), Application Default
   Credentials (`gcloud auth application-default login`), or headless/CI-CD via
   `GOOGLE_APPLICATION_CREDENTIALS` or Workload Identity Federation.
4. **Project, Region, Billing & API Enablement**:
   ```sh
   gcloud config set project {project_id}
   gcloud config set compute/region {region}
   gcloud config set compute/zone {zone}
   gcloud services enable compute.googleapis.com logging.googleapis.com
   ```
   *Note: An active billing account attachment is required (even for Free Tier
   eligible resources such as `e2-micro`). Never hardcode regions or zones;
   confirm `{project_id}`, `{region}`, and `{zone}` (defaulting to a
   well-supported region such as `us-central1` / `us-central1-a` if
   unspecified), and consult
   [Google Cloud Locations](https://cloud.google.com/about/locations) to verify
   regional and zonal availability (preview features and specialized GPUs/TPUs
   are restricted to specific locations).*
5. **Required IAM Roles**:
   - **Read-Only Diagnostics & Capacity Advice**: `roles/compute.viewer` and
     `roles/logging.viewer`.
   - **Log Analytics SQL (`_Default._AllLogs`)**: `roles/logging.viewAccessor`
     (plus `roles/bigquery.jobUser` and `roles/bigquery.dataViewer` when
     querying via a linked BigQuery dataset).
   - **Instance & MIG Remediation**: `roles/compute.instanceAdmin.v1` (plus
     `roles/iam.serviceAccountUser` when attaching a service account to VMs).
   - **Reservation Creation & Teardown**: `roles/compute.admin` (or a custom
     role granting `compute.reservations.create`, `compute.reservations.update`,
     and `compute.reservations.delete`, which are **not** included in
     `roles/compute.instanceAdmin.v1`).
   - **MCP Tool Invocation**: `roles/mcp.toolUser`.

---

## Step 1: Verify Stockout Scope & Distinguish from Quota Errors

### A. Core Domain Rules (Explain to User)

Before taking action, clarify these three foundational Compute Engine behaviors
(see
[Troubleshooting resource availability errors](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability.md.txt)):

1. **Stockout != Quota**: `ZONE_RESOURCE_POOL_EXHAUSTED` (and
   `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`) means physical hardware
   capacity for that specific resource pool in that specific zone is
   temporarily full. Increasing project quota (**IAM & Admin > Quotas & System
   Limits**) will **not** resolve a physical stockout. Conversely,
   `QUOTA_EXCEEDED` means the project's administrative quota ceiling has been
   reached regardless of physical hardware availability. When returned,
   `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS` also includes `errorInfo.reason`
   (such as `configuration_availability` for unsupported hardware combinations
   that will not succeed on retry) and `errorInfo.metadata.zonesAvailable`
   listing sibling zones with capacity.
2. **Scoped to Specific Shape & Zone**: A stockout applies only to the exact
   machine shape or accelerator (for example, `g2-standard-4` or
   `c4-standard-32`) in that zone (for example, `us-central1-a`). Sibling zones
   (`us-central1-b`, `us-central1-c`, `us-central1-f`) or smaller shapes
   (`c4-standard-16`) frequently have ample capacity.
3. **Existing Running VMs Are Safe**: Resource availability errors affect only
   **new capacity allocations** (creating new VMs, starting stopped
   `TERMINATED` VMs, changing machine types, or MIG scale-out). Currently
   running `RUNNING` VMs in the zone are unaffected.

### B. Query Cloud Audit Logs for Resource Availability vs. Quota Failures

Run `gcloud logging read` with an explicit `--freshness` window (`gcloud
logging read` defaults to `1d`, so multi-day investigations require
`--freshness=7d` or `--freshness=14d`). Inspect
`protoPayload.response.error.errors[0].code` (not `.reason`) to distinguish
`ZONE_RESOURCE_POOL_EXHAUSTED` / `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`
from `QUOTA_EXCEEDED`:

```sh
gcloud logging read \
    'resource.type="gce_instance" AND log_id("cloudaudit.googleapis.com/activity") AND (protoPayload.status.message:("ZONE_RESOURCE_POOL_EXHAUSTED" OR "does not have enough resources available" OR "resource pool exhausted" OR "does not exist in zone" OR "QUOTA_EXCEEDED" OR "Quota") OR protoPayload.response.error.errors.code:("ZONE_RESOURCE_POOL_EXHAUSTED" OR "ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS" OR "QUOTA_EXCEEDED"))' \
    --project={project_id} --freshness=7d --limit=20 \
    --format="table(timestamp, resource.labels.zone, protoPayload.resourceName, protoPayload.response.error.errors[0].code, protoPayload.status.message)"
```

- **If `code` is `QUOTA_EXCEEDED` (Always Include Regional Quota Inspection)**:
  Do **not** treat this as a physical stockout. Always provide `gcloud compute
  regions describe` to inspect regional quota limits and usage, and direct the
  user to **IAM & Admin > Quotas & System Limits** (or switch to a machine
  family with quota headroom):
  ```sh
  gcloud compute regions describe {region} --project={project_id} \
      --format="table(quotas:format='table(metric,limit,usage)')"
  ```
- **If a MIG is failing to scale out**: Also inspect MIG provisioning errors
  directly (via Compute Engine MCP `list_managed_instances` for zonal MIGs, or
  `gcloud`):
  ```sh
  # Zonal MIG (--zone={zone}) vs. Regional MIG (--region={region}):
  gcloud compute instance-groups managed list-errors {mig_name} \
      --project={project_id} --zone={zone}
  gcloud compute instance-groups managed list-errors {mig_name} \
      --project={project_id} --region={region}
  ```

### C. Analyze Historical Stockout Frequency with Log Analytics SQL

Because failed `cloudaudit.googleapis.com/activity` entries have severity
`ERROR` (`severity_number >= 500`), Cloud Logging routes them to the
**`_Default` log bucket** (`{project_id}.global._Default._AllLogs`), whereas
`_Required._AllLogs` only stores Admin Activity logs below `ERROR` and System
Event logs.

- **Prerequisite**: Upgrade `_Default` to Log Analytics (see
  [Query and view logs in Log Analytics](https://docs.cloud.google.com/logging/docs/analyze/query-and-view.md.txt)):
  ```sh
  gcloud logging buckets update _Default \
      --project={project_id} --location=global --enable-analytics
  ```
- **JSON Column Extraction Rule**: In `_AllLogs`, `resource.labels` and
  `proto_payload.audit_log.request` have BigQuery type `JSON`. Never reference
  `resource.labels.zone` directly in `GROUP BY`—always extract scalar `STRING`
  values with `JSON_VALUE(...)`:
  ```sql
  SELECT
    JSON_VALUE(resource.labels.zone) AS zone,
    REGEXP_EXTRACT(JSON_VALUE(proto_payload.audit_log.request.machineType), r'([^/]+)$') AS machine_type,
    proto_payload.audit_log.status.message AS status_message,
    COUNT(*) AS stockout_count,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
  FROM `{project_id}.global._Default._AllLogs`
  WHERE
    timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
    AND log_id = 'cloudaudit.googleapis.com/activity'
    AND resource.type = 'gce_instance'
    AND (
      proto_payload.audit_log.status.message LIKE '%ZONE_RESOURCE_POOL_EXHAUSTED%'
      OR proto_payload.audit_log.status.message LIKE '%does not have enough resources available%'
      OR TO_JSON_STRING(proto_payload.audit_log.response.error.errors) LIKE '%ZONE_RESOURCE_POOL_EXHAUSTED%'
    )
  GROUP BY zone, machine_type, status_message
  ORDER BY stockout_count DESC;
  ```

---

## Step 2: Immediate Tactical Mitigations (Unblock Workload Now)

Execute these five steps in priority order to provision the blocked workload
immediately:

### 1. Discover Sibling Zones Supporting the Machine Shape or GPU

If a zone returns `ZONE_RESOURCE_POOL_EXHAUSTED` or `Machine type with name
'...' does not exist in zone '...'`, check which sibling zones in `{region}`
offer the target machine shape and (if applicable) GPU accelerator using
Compute Engine MCP `list_machine_types` / `list_accelerator_types` or `gcloud`:

```sh
# List all zones in {region} that offer {machine_type}:
gcloud compute machine-types list --project={project_id} \
    --filter="name={machine_type} AND zone ~ ^{region}-" \
    --format="table(name, zone, guestCpus, memoryMb)"
# For GPU workloads (especially N1 with attached GPUs), verify accelerator zones:
gcloud compute accelerator-types list --project={project_id} \
    --filter="name={accelerator_type} AND zone ~ ^{region}-" \
    --format="table(name, zone, maximumCardsPerInstance)"
```

### 2. Use Bulk Insert (`bulk create`) to Pick an Available Zone

Instead of guessing and retrying individual zones manually, use `gcloud compute
instances bulk create` with `--region={region}` and
`--target-distribution-shape=ANY_SINGLE_ZONE` (for colocated VMs or `--count=1`)
or `--target-distribution-shape=BALANCED` (to spread across available zones).
Compute Engine automatically selects zone(s) in `{region}` with capacity (see
[Create VMs in bulk](https://docs.cloud.google.com/compute/docs/instances/multiple/create-in-bulk.md.txt)):

```sh
# On instances bulk create, --target-distribution-shape is UPPERCASE (ANY, ANY_SINGLE_ZONE, BALANCED):
gcloud compute instances bulk create \
    --project={project_id} --region={region} \
    --name-pattern="{vm_name}-#" --count={vm_count} \
    --target-distribution-shape=ANY_SINGLE_ZONE \
    --machine-type={machine_type}
```

### 3. Check Spot VM Obtainability via Spot Capacity Advisor (`advice capacity`)

When provisioning **Spot VMs**, use `gcloud beta compute advice capacity` (the
Spot Capacity Advisor API) to compare real-time Spot obtainability scores and
estimated uptime (`estimatedUptime`) across zones and machine types in
`{region}` before creating instances (use
`gcloud beta compute advice capacity-history` for 30-day historical preemption
rates; see
[View the availability of Spot VMs](https://docs.cloud.google.com/compute/docs/instances/view-vm-availability.md.txt)):

- **Critical Scope & Flag Rules**:
  1. `gcloud beta compute advice capacity` supports **only Spot VMs**
     (`--provisioning-model=SPOT`, the only supported value; it cannot query
     `STANDARD` on-demand capacity).
  2. There is **no `--machine-type` flag** on `advice capacity`—specify machine
     types with
     `--instance-selection-machine-types={machine_type_1},{machine_type_2}` or
     `--instance-selection="name={selection_name},machine-type={machine_type}"`.
  3. On `advice capacity`, `--target-distribution-shape` choices are
     **UPPERCASE** (`ANY`, `ANY_SINGLE_ZONE`, or `BALANCED`). Always include
     `--provisioning-model=SPOT`, `--instance-selection-machine-types`, and
     uppercase `--target-distribution-shape=ANY` (or `ANY_SINGLE_ZONE` /
     `BALANCED`):

```sh
gcloud beta compute advice capacity \
    --project={project_id} --region={region} \
    --provisioning-model=SPOT --size={vm_count} \
    --instance-selection-machine-types={machine_type_1},{machine_type_2} \
    --target-distribution-shape=ANY
```

### 4. Right-Size Large Shapes (> 32 vCPUs)

Physical host fragmentation makes large machine shapes (such as `*-standard-64`,
`*-standard-96`, or `*-standard-128`) significantly scarcer than smaller shapes.
If the workload can scale horizontally, split a single 64-vCPU request into two
32-vCPU VMs or four 16-vCPU VMs.

### 5. Use Dynamic Workload Scheduler (DWS) Flex-Start for Scarce GPUs

When scarce GPU shapes (`a4-highgpu-8g`, `a3-highgpu-8g`, `a2-highgpu-1g`, or
`g2-standard-4`) fail immediate creation with `ZONE_RESOURCE_POOL_EXHAUSTED`,
use **Dynamic Workload Scheduler (DWS) Flex-Start** to queue and automatically
provision capacity when hardware frees up (see
[About Dynamic Workload Scheduler](https://docs.cloud.google.com/compute/docs/instances/provisioning-models.md.txt)
and
[Create a standalone Flex-start VM](https://docs.cloud.google.com/compute/docs/instances/create-flex-start-vm.md.txt)):

- **Mandatory CLI Rules for DWS Flex-Start Standalone VMs**:
  1. **Machine Family Accelerator & Maintenance Rule**: For `G2` (`nvidia-l4`),
     `G4`, `A2` (`nvidia-tesla-a100`), `A3`, and `A4` machine series, GPUs are
     **automatically attached** by the machine type (omit `--accelerator` unless
     attaching GPUs to `N1` or using vWS). Standalone Flex-Start GPU creation
     requires `--reservation-affinity=none`, `--max-run-duration` (`10m` to
     `7d`), `--instance-termination-action=DELETE` (or `STOP`),
     `--maintenance-policy=TERMINATE`, and `--request-valid-for-duration`
     (`90s` to `2h` to queue in a zone, or `0s` for immediate-only allocation).
  2. For multi-instance GPU jobs or longer/multi-zone queueing, use a **MIG
     with a Flex-Start instance template and resize requests** (see
     [Create resize requests in a MIG](https://docs.cloud.google.com/compute/docs/instance-groups/create-resize-requests-mig.md.txt)).
     The MIG requires autoscaling disabled,
     `--default-action-on-vm-failure=do-nothing`, and (on a Regional MIG)
     `--target-distribution-shape=any-single-zone` with
     `--instance-redistribution-type=none`.

```sh
# Option A: Standalone VM with DWS Flex-Start (queues up to 2h via --request-valid-for-duration):
gcloud compute instances create {vm_name} \
    --project={project_id} --zone={zone} \
    --machine-type=g2-standard-4 \
    --provisioning-model=FLEX_START \
    --reservation-affinity=none \
    --request-valid-for-duration=2h \
    --max-run-duration=7d \
    --instance-termination-action=DELETE \
    --maintenance-policy=TERMINATE
# Option B: Instance Template + Zonal or Regional MIG Resize Request (longer queueing):
gcloud compute instance-templates create {template_name} \
    --project={project_id} --machine-type=g2-standard-4 \
    --provisioning-model=FLEX_START \
    --reservation-affinity=none \
    --max-run-duration=7d \
    --instance-termination-action=DELETE \
    --maintenance-policy=TERMINATE
# Queue capacity on a MIG configured per bullet 2 (--zone={zone} or --region={region}):
gcloud compute instance-groups managed resize-requests create {mig_name} \
    --project={project_id} --region={region} \
    --resize-request={request_name} --resize-by={vm_count}
```

---

## Step 3: Long-Term Architectural Prevention

To permanently eliminate single-zone stockouts for production services,
implement one or more of the following patterns:

### A. Configure Regional MIGs with `balanced` or `any` Distribution Shape

A Regional MIG spreads instances across zones in a region. Configure its Target
Distribution Shape (see
[Regional MIG distribution shape documentation](https://docs.cloud.google.com/compute/docs/instance-groups/regional-mig-distribution-shape.md.txt)):

- **`balanced` (`BALANCED`)**: Prioritizes even zonal distribution, but
  automatically spills over to healthy sibling zones during a stockout.
- **`any` (`ANY`)**: Provisions capacity in whichever zone has available
  hardware fastest, maximizing obtainability under regional pressure.
- **`any-single-zone` (`ANY_SINGLE_ZONE`)**: Colocates all VMs in one healthy
  zone with sufficient capacity (ideal for low-latency inter-node workloads).

**Critical Operational Rule (`--instance-redistribution-type`)**:
- Regional MIGs default to `even` (`EVEN`) + `proactive` (`PROACTIVE`), which
  periodically **deletes running VMs in over-represented zones and recreates
  them** in under-represented or recovering zones to enforce strict zonal
  balance—disrupting stateful workloads and failing during stockouts.
- `balanced` (`BALANCED`), `any` (`ANY`), and `any-single-zone`
  (`ANY_SINGLE_ZONE`) **all require** `--instance-redistribution-type=none`.
  Compute Engine supports `proactive` redistribution **only** with `even` and
  rejects `proactive` with `balanced`, `any`, or `any-single-zone` (see
  [Set a target distribution shape](https://docs.cloud.google.com/compute/docs/instance-groups/regional-mig-set-target-distribution-shape.md.txt)).
- **Calliope Flag Case Rule**: Unlike `instances bulk create` (uppercase),
  `gcloud compute instance-groups managed update` requires **lowercase** values
  for `--target-distribution-shape` (`any`, `any-single-zone`, `balanced`,
  `even`) and `--instance-redistribution-type` (`none`, `proactive`):

```sh
# Allow spillover to healthy zones without proactively deleting running VMs:
gcloud compute instance-groups managed update {mig_name} \
    --project={project_id} --region={region} \
    --instance-redistribution-type=none --target-distribution-shape=balanced
# Or maximize obtainability in any zone (requires --instance-redistribution-type=none):
gcloud compute instance-groups managed update {mig_name} \
    --project={project_id} --region={region} \
    --instance-redistribution-type=none --target-distribution-shape=any
```

### B. Enable MIG Instance Flexibility (Multi-Family Machine Type Fallback)

Configure the MIG with **Instance Flexibility** (`instanceFlexibilityPolicy`)
so it can fall back across equivalent machine families (for example, rank 1
`c3-standard-8`, rank 2 `n2-standard-8` or `n2d-standard-8`) when the primary
family is exhausted (see
[About instance flexibility](https://docs.cloud.google.com/compute/docs/instance-groups/about-instance-flexibility.md.txt)
and
[Add instance flexibility](https://docs.cloud.google.com/compute/docs/instance-groups/configure-instance-flexibility.md.txt)):

- **Constraints & Disk/Repair Rules**:
  - Supported **only on Regional MIGs** (not Zonal MIGs) with
    `--target-distribution-shape` set to `balanced`, `any`, or
    `any-single-zone` (default `even` is rejected) and
    `--instance-redistribution-type=none`. Configure with
    `gcloud beta compute instance-groups managed update`
    (`--instance-selection` / `--remove-instance-selections`) or REST
    `instanceFlexibilityPolicy.instanceSelections`.
  - Falling back across series with incompatible boot disk support (such as
    Hyperdisk-only `n4-standard-8` to Persistent-Disk-only `n2-standard-8`)
    requires per-selection disk overrides via `--instance-flexibility-policy`
    (or `--flags-file`) rather than `--instance-selection` alone.
  - Enable `--force-update-on-repair` so MIG VM repairs can fall back to
    alternative machine types (and whenever using disk or CPU overrides).

```sh
gcloud beta compute instance-groups managed update {mig_name} \
    --project={project_id} --region={region} \
    --target-distribution-shape=balanced \
    --instance-redistribution-type=none \
    --instance-selection="name=primary-tier,machine-type=c3-standard-8,rank=1" \
    --instance-selection="name=fallback-tier,machine-type=n2-standard-8,rank=2"
```

### C. Purchase On-Demand Capacity Reservations

For mission-critical production workloads requiring 100% guaranteed zonal
capacity assurance, create an On-Demand Zonal Reservation (see
[About reservations of zonal resources](https://docs.cloud.google.com/compute/docs/instances/reservations-overview.md.txt)
and
[Create a reservation for a single project](https://docs.cloud.google.com/compute/docs/instances/reservations-single-project.md.txt)):

- **Operational & IAM Rules**:
  1. Requires `roles/compute.admin` (or custom `compute.reservations.*`) and
     **succeeds only when physical capacity is currently available in
     `{zone}`**—if `{zone}` is actively stocked out, create the reservation in
     an available sibling zone or wait until capacity replenishes.
  2. For **N1 with GPUs** or **Local SSDs**, `--accelerator` and `--local-ssd`
     flags must **exactly match** the consuming VM's properties.

```sh
gcloud compute reservations create {reservation_name} \
    --project={project_id} --zone={zone} \
    --vm-count={vm_count} --machine-type={machine_type}
```

---

## Safe Rollback, Teardown & Cost Governance

1. **Restore Regional MIG Distribution Settings**: To roll back from `any` to
   opportunistic zonal balance (`balanced` requires
   `--instance-redistribution-type=none` and converges on resizes), or to
   return a stateless MIG to strict `even` + `proactive` distribution (after
   [manually rebalancing](https://docs.cloud.google.com/compute/docs/instance-groups/regional-mig-rebalance-manually.md.txt)
   if zone counts differ by more than 1 VM):
   ```sh
   # Option A: Converge opportunistically on resizes without deleting VMs:
   gcloud compute instance-groups managed update {mig_name} \
       --project={project_id} --region={region} \
       --target-distribution-shape=balanced --instance-redistribution-type=none
   # Option B: Stateless strict even + proactive (rebalance manually first if >1 VM diff):
   gcloud compute instance-groups managed update {mig_name} \
       --project={project_id} --region={region} \
       --target-distribution-shape=even --instance-redistribution-type=none
   gcloud compute instance-groups managed update {mig_name} \
       --project={project_id} --region={region} \
       --instance-redistribution-type=proactive
   ```
2. **Remove MIG Instance Selections**: To roll back fallback selections:
   ```sh
   gcloud beta compute instance-groups managed update {mig_name} \
       --project={project_id} --region={region} \
       --remove-instance-selections=fallback-tier
   ```
3. **Delete Unused Capacity Reservations & Temporary VMs**:
   - **Cost Warning**: On-Demand Capacity Reservations are billed at standard
     Compute Engine rates from creation **whether or not VMs run inside them**
     (and count toward regional quota). Consult
     [Google Cloud pricing](https://cloud.google.com/pricing) and
     [Compute Engine pricing](https://cloud.google.com/compute/all-pricing) for
     current rates rather than quoting hardcoded prices.
   - Omit `--quiet` on manual destructive commands so interactive confirmation
     prevents accidental deletion in production:
     ```sh
     gcloud compute reservations delete {reservation_name} \
         --project={project_id} --zone={zone}
     gcloud compute instances delete {vm_name} \
         --project={project_id} --zone={zone}
     ```
