---
name: compute-on-demand-reservations
metadata:
  version: "1.0.0"
  category: Compute
description: >-
  Inspects, verifies, and manages Google Compute Engine (GCE) On-Demand reservations
  and analyzes consumed versus available reserved capacity. Use when checking active
  reservation capacity, determining whether reserved VMs are available or exhausted,
  verifying reservation targeting (automatic versus specific reservation), or sharing
  reservations across projects. Don't use for Spot capacity advice (use
  compute-spot-capacity-advice) or future calendar bookings (use compute-future-reservations).
---

# Compute Engine On-Demand Reservations

The `compute-on-demand-reservations` skill inspects and manages active Google Compute Engine (GCE) On-Demand reservations. It determines whether guaranteed capacity is available, calculates consumption, verifies instance targeting policies, and audits cross-project sharing.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST read and follow the instructions in [Usage Attribution](references/attribution.md).

---

## Prerequisites, IAM & Billing

Before querying or managing On-Demand reservations, ensure the environment meets these requirements:

1. **Project & Region Configuration**: Prefer passing `--project={project_id}` and `--zone={zone}` directly on each command to avoid overwriting global workstation state, or obtain explicit user confirmation before setting defaults (e.g., `us-central1` / `us-central1-a`):
   ```bash
   gcloud config set project {project_id}
   gcloud config set compute/region {region}
   gcloud config set compute/zone {zone}
   ```
2. **Billing & API Enablement**: Ensure the project has an active billing account attached and the Compute Engine API is enabled:
   ```bash
   gcloud services enable compute.googleapis.com --project={project_id}
   ```
3. **Cloud SDK & Authentication**: Ensure the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) is installed (never execute unprompted host installation commands such as `apt-get` or `curl | bash` without explicit user approval; direct the user to the installation guide instead), then authenticate via `gcloud auth login` (for interactive CLI), `gcloud auth application-default login` (for SDKs), or `GOOGLE_APPLICATION_CREDENTIALS` (for service accounts).
4. **IAM Permissions**:
   * **Read-Only Inspection (`list`, `describe`)**: Grant `roles/compute.viewer` (or custom role with `compute.reservations.list` and `compute.reservations.get`).
   * **Reservation Lifecycle (`create`, `update`, `delete`)**: Grant `roles/compute.admin` (or custom role with `compute.reservations.create`, `compute.reservations.resize`, `compute.reservations.update`, and `compute.reservations.delete`).
   * **Consuming Reservations (`instances create`)**: Grant `roles/compute.instanceAdmin.v1` on the project launching VMs (and on **both** the host/owner project and the consumer project when consuming a shared reservation).
5. **Quota & Organization Policy**: Creating an On-Demand reservation immediately consumes regional CPU, GPU, or Local SSD quota. For **shared reservations**, Compute Engine deducts regional quota in **both** the host project (at reservation creation) and the consumer project (when VMs launch), and requires the host project to be allowlisted in organization policy `constraints/compute.sharedReservationsOwnerProjects`.
6. **Billing & Pricing Warning**: On-Demand reservations are billed immediately upon creation at the full On-Demand VM rate whether or not VMs are running and consuming the reservation. Review [Compute Engine Pricing](https://cloud.google.com/compute/pricing), [Available Regions and Zones](https://docs.cloud.google.com/compute/docs/regions-zones.md.txt), and [Google Cloud Locations](https://cloud.google.com/about/locations) (strip `.md.txt` suffixes when presenting documentation URLs to human users) before provisioning.

---

## Command Syntax & Reference

### 1. List Reservations in a Project / Zone

```bash
gcloud compute reservations list \
  --project={project_id} \
  [--zones={zone}] \
  [--format="table(name,zone.basename(),specificReservation.instanceProperties.machineType.basename(),specificReservation.assuredCount,specificReservation.inUseCount,specificReservation.count,specificReservationRequired,shareSettings.shareType,status)"]
```

### 2. Inspect Reservation Details & Capacity Metrics

```bash
gcloud compute reservations describe {reservation_name} \
  --zone={zone} \
  --project={project_id}
```

*(Note: Dense accelerator reservations backed by `aggregateReservation` leave `specificReservation.*` columns blank in `list` and expose `aggregateReservation.totalResources` and `aggregateReservation.inUseResources` via `describe`.)*

### 3. Create a New On-Demand Reservation

> [!IMPORTANT]
> Creating a reservation immediately incurs billing charges. Always obtain explicit human approval before executing `gcloud compute reservations create`.

```bash
gcloud compute reservations create {reservation_name} \
  --project={project_id} \
  --zone={zone} \
  --vm-count={vm_count} \
  (--machine-type={machine_type} | --source-instance-template={template_name}) \
  [--min-cpu-platform={min_cpu_platform}] \
  [--accelerator=count={gpu_count},type={gpu_type}] \
  [--local-ssd=interface={nvme|scsi}] \
  [--require-specific-reservation] \
  [--share-setting=projects --share-with={consumer_project_ids}]  # up to 100 consumer projects in the same org (excluding the host project)
```

### 4. Update or Resize an Existing Reservation

Resizing capacity (`--vm-count`) and modifying shared consumer projects are mutable in place after obtaining explicit human approval (`--share-with` and `--add-share-with` accept up to 100 consumer project IDs or project numbers in the same organization excluding the host project itself, while `--remove-share-with` strictly requires numeric **project numbers**). Hardware attributes (`machineType`, `minCpuPlatform`, `accelerator`, `localSsd`, `zone`, and `specificReservationRequired`) are immutable after creation and require recreating the reservation.

```bash
gcloud compute reservations update {reservation_name} \
  --project={project_id} \
  --zone={zone} \
  [--vm-count={new_vm_count}] \
  [--add-share-with={project_ids_or_numbers} | --remove-share-with={project_numbers}]
```

### 5. Delete an Unused On-Demand Reservation (Resource Teardown)

To stop ongoing billing for an unused On-Demand reservation, delete it after obtaining explicit human approval (note: deletion fails if the reservation is attached to a resource-based Committed Use Discount where `commitment` is set—which must be swapped via `gcloud beta compute commitments update-reservations`—or if a targeted reservation with `specificReservationRequired: true` still has `inUseCount > 0`; the command also prompts interactively unless `--quiet` is passed):

```bash
gcloud compute reservations delete {reservation_name} \
  --zone={zone} \
  --project={project_id}
```

---

## Capacity Utilization Analysis

When inspecting reservation output, verify that the reservation `status` is `READY` or `UPDATING` (exclude reservations in `CREATING` or `DELETING` states) and calculate available capacity using the following fields:

* **`status`**: Must be `READY` or `UPDATING` before instances can consume reserved capacity. While a reservation is `UPDATING` (for example, during a capacity resize or share-setting modification), its already provisioned capacity remains consumable up to `specificReservation.assuredCount`. Only `CREATING` and `DELETING` states block consumption.
* **`specificReservation.assuredCount`**: The number of reserved VM instances currently provisioned and physically backed by Compute Engine hardware. Note that `assuredCount` can be less than `specificReservation.count` while a reservation is actively upsizing or if a physical host failure degrades the reservation (`healthInfo.healthStatus: DEGRADED`).
* **`specificReservation.count`**: The total requested target number of VM instances in this reservation block.
* **`specificReservation.inUseCount`**: The number of reserved instances currently consumed by running VMs.
* **Available Reserved Capacity**:
  ```text
  Available Capacity = specificReservation.assuredCount - specificReservation.inUseCount
  ```

### Health & Consumption Thresholds

* **Available (`> 0`)**: Provisioned reserved capacity is immediately available. Workloads can launch with 100% provisioning assurance.
* **Exhausted (`inUseCount >= assuredCount`)**: Provisioned reserved capacity is fully consumed. New instances matching this specification fall back to unreserved on-demand capacity (if allowed) or fail to launch.

---

## Reservation Targeting Policies

Reservations operate under two distinct consumption modes defined by `specificReservationRequired`:

| Setting | Consumption Mode | Matching Behavior |
| :--- | :--- | :--- |
| `specificReservationRequired: false` | **Automatic (`ANY_RESERVATION`)** | Any newly created `STANDARD` VM whose properties **identically match all reserved `instanceProperties`** automatically consumes this reservation. |
| `specificReservationRequired: true` | **Targeted (`SPECIFIC_RESERVATION`)** | VMs do not consume this capacity unless they match all reserved `instanceProperties` and explicitly specify `--reservation-affinity=specific --reservation={reservation_name}`. |

### Exact Hardware & Property Matching Requirement

For a VM to consume a reservation (under either `ANY_RESERVATION` or `SPECIFIC_RESERVATION`), **every** property below must match the reservation's `specificReservation.instanceProperties` 100% identically:

* **Project and `zone`**: Same project for `LOCAL` reservations, or an authorized consumer project listed in `shareSettings.projectMap`, in the exact same `zone`.
* **`machineType`**: Exact machine type shape.
* **`minCpuPlatform`**: Must match verbatim. If the reservation was created without an explicit CPU platform (`"Automatic"`), passing `--min-cpu-platform` on the VM does **not** match (and vice versa).
* **`guestAccelerators`**: Exact GPU `acceleratorType` and `acceleratorCount` (if any).
* **`localSsds`**: Exact Local SSD partition count **and** exact storage interface (`NVME` versus `SCSI`, if any).
* **Placement policies**: Exact compact placement `resourcePolicies` and `locationHint` (if present on the reservation).
* **`provisioningModel`**: Must be `STANDARD` (`SPOT` VMs never consume On-Demand reservations).

> [!WARNING]
> **Silent Double-Billing Trap**: Under `ANY_RESERVATION` (`--reservation-affinity=any`, the default), if a newly created VM matches `zone` and `machineType` but differs on even a single property (such as `NVME` vs. `SCSI` Local SSD interface or `minCpuPlatform`), Compute Engine silently skips the reservation, launches an unreserved On-Demand VM, and bills for both the idle reservation and the new VM. Creating both the reservation and VMs from the same `--source-instance-template` prevents property drift.

### VM Provisioning Best Practices

When provisioning VMs, recommend private networking (`--no-address` paired with IAP TCP forwarding) and a custom least-privilege service account (`--service-account`):

* To consume a targeted reservation (`specificReservationRequired: true`) during instance creation (note: passing `--reservation-affinity=specific` against a reservation with `specificReservationRequired: false` is rejected by Compute Engine):
  ```bash
  gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type={machine_type} \
    --reservation-affinity=specific \
    --reservation={reservation_name} \
    [--no-address] \
    [--service-account={service_account_email}]
  ```
* To prevent an instance from consuming any reservation:
  ```bash
  gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type={machine_type} \
    --reservation-affinity=none \
    [--no-address] \
    [--service-account={service_account_email}]
  ```

---

## Cross-Project Shared Reservations

Shared reservations allow multiple projects within the same Google Cloud organization to draw from a shared pool of reserved capacity.

* Inspect `shareSettings`:
  * `shareType: LOCAL`: Reservation is private to the host project.
  * `shareType: SPECIFIC_PROJECTS`: Shared with specific consumer projects keyed under `projectMap` (mapping each project ID or number to `{"projectId": "..."}`).
* **Visibility & CUD Caveats**:
  * Running `gcloud compute reservations list --project={consumer_project_id}` in a consumer project **never** displays shared reservations owned by a host project; always query `--project={host_project_id}` (or Cloud Asset Inventory) to inspect `assuredCount` and `inUseCount`.
  * Committed Use Discount (CUD) pricing only covers shared reservation consumers when the host and consumer projects belong to the **same Cloud Billing account**.
* Consumer projects consume shared capacity by specifying `--project={consumer_project_id}` and referencing the host project in `--reservation`:
  ```bash
  gcloud compute instances create {vm_name} \
    --project={consumer_project_id} \
    --zone={zone} \
    --machine-type={machine_type} \
    --reservation-affinity=specific \
    --reservation=projects/{host_project_id}/reservations/{reservation_name} \
    [--no-address] \
    [--service-account={service_account_email}]
  ```

---

## Operational Guardrails & Recommendations

* **Human-Approval Guardrail**: Never execute mutating commands (`gcloud compute reservations create`, `gcloud compute reservations update`, `gcloud compute reservations delete`, or `gcloud compute instances create`) without explicit human approval from the user. Provide copy-pasteable commands and highlight billing implications first.
* **Compute Engine MCP Server Guardrail**: When the Compute Engine MCP server is enabled, inspect the in-session MCP tool schemas before invoking them (in case newer MCP server versions add support); unless verified in the current schema:
  * MCP `list_reservations` is single-zone only and **strips `specific_reservation` counts/shape and `share_settings`** (call `get_reservation_details` per reservation or use `gcloud compute reservations list`).
  * No MCP tools exist to create, update, or delete reservations.
  * MCP `create_instance` omits `reservation_affinity`, `min_cpu_platform`, and `local_ssd` (cannot target `SPECIFIC_RESERVATION` or shared reservations and risks silent unreserved double-billing); fall back to `gcloud` CLI when these parameters are absent from the tool schema.
* **Missing Reservation Advisory**: When no matching or available reservation exists in the target zone:
  * Inform the user that instances launch against unreserved on-demand capacity (subject to stock availability).
  * If guaranteed capacity is required, advise creating a new reservation using `gcloud compute reservations create`.
  * If the workload is interruptible or fault-tolerant, suggest evaluating Spot VMs using `compute-spot-capacity-advice`.
* **Negative Guardrail (No Spot Telemetry for On-Demand)**: Do not use Spot capacity advice (`gcloud beta compute advice capacity --provisioning-model=SPOT`) or emit obtainability scores when inspecting or verifying standard On-Demand reservations. On-Demand reservation checks must inspect concrete reservation status and counts via `gcloud compute reservations list` and `describe`.
