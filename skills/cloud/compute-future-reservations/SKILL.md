---
name: compute-future-reservations
metadata:
  version: "1.0.0"
  category: Compute
description: >-
  Evaluates future GPU and TPU reservation feasibility and calendar-mode booking
  options in Google Compute Engine (GCE). Use when planning future AI/ML training
  runs, checking reservation availability windows, verifying accelerator cluster
  topologies, or assessing future capacity lead times. Don't use for active
  on-demand reservations (use compute-on-demand-reservations), immediate Spot
  capacity queries (use compute-spot-capacity-advice), or Standard Future
  Reservations (--reservation-mode=DEFAULT).
---

# Compute Engine Future Reservations & Calendar-Mode Feasibility

The `compute-future-reservations` skill assesses future capacity availability and feasibility for high-demand AI/ML hardware (NVIDIA GPUs, H4D VMs, and Google Cloud TPUs). It enables infrastructure engineers to evaluate future reservation windows, match cluster topologies, and manage calendar-mode bookings.

> [!NOTE]
> **Scope Boundary (Calendar Mode vs. Standard Future Reservations)**: This skill covers **Calendar-Mode Future Reservations** (`--reservation-mode=CALENDAR`, backed by Dynamic Workload Scheduler for up to 90 days on supported families such as `a3*`, `a4*`, `h4d*`, and Cloud TPUs; for newly released machine series, verify Calendar Mode support dynamically via `gcloud compute advice calendar-mode` or the official [Calendar Mode documentation](https://docs.cloud.google.com/compute/docs/instances/provisioning-models.md.txt#instance-availability)). Do not apply Calendar-Mode flags (`--reservation-mode=CALENDAR`, `--deployment-type=DENSE`) to **Standard Future Reservations** (`--reservation-mode=DEFAULT` for general-purpose CPU families, `a2*`/`g2*` GPUs, `DRAFT` planning workflows, or multi-month/CUD commitments).

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST read and follow the instructions in [Usage Attribution](references/attribution.md).

---

## Prerequisites, IAM & Billing

Before querying calendar-mode advice or submitting future reservation requests, ensure the environment meets these requirements:

1. **Project & Region Configuration**: Prefer passing `--project={project_id}` and `--region={region}` (or `--zone={zone}`) directly on each command to avoid overwriting global workstation state, or obtain explicit user confirmation before setting defaults (e.g., `us-central1`):
   ```bash
   gcloud config set project {project_id}
   gcloud config set compute/region {region}
   ```
2. **Billing & API Enablement**: Ensure the project has an active billing account attached and the Compute Engine API is enabled:
   ```bash
   gcloud services enable compute.googleapis.com --project={project_id}
   ```
3. **Cloud SDK & Authentication**: Ensure the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) is installed (never execute unprompted host installation commands such as `apt-get` or `curl | bash` without explicit user approval; direct the user to the installation guide instead), then authenticate via `gcloud auth login` (for interactive CLI), `gcloud auth application-default login` (for SDKs), or `GOOGLE_APPLICATION_CREDENTIALS` (for service accounts).
4. **IAM Permissions**:
   * **Feasibility, Creation & Inspection (`advice calendar-mode`, `create`, `list`, `describe`, `delete`)**: Grant `roles/compute.futureReservationUser` (includes `compute.advice.calendarMode`, `compute.futureReservations.create`, `compute.futureReservations.delete`, `compute.futureReservations.get`, `compute.futureReservations.list`, and `compute.reservations.create`, **excluding `compute.futureReservations.cancel`**).
   * **Cancelling Requests (`cancel`)**: Grant `roles/compute.futureReservationAdmin` (or `roles/compute.admin`), which is required for `compute.futureReservations.cancel`.
5. **Quota & Organization Policy**: Submitting a Calendar-Mode request requires **0 reservation quota** for GPUs and TPUs, but **H4D VMs require sufficient regional CPU quota** at submission, and **all** workloads require sufficient VM/TPU, boot disk, and IP quota at `start-time` to consume the auto-created reservation. Sharing across projects requires allowlisting the host project in organization policy `constraints/compute.sharedReservationsOwnerProjects`.
6. **Billing & Pricing Warning**: Approved Calendar-Mode Future Reservations automatically provision capacity at `start-time` and bill for the entire committed window whether or not VMs or TPUs are actively running. Review [Compute Engine Pricing](https://cloud.google.com/compute/pricing), [Available Regions and Zones](https://docs.cloud.google.com/compute/docs/regions-zones.md.txt), and [Google Cloud Locations](https://cloud.google.com/about/locations) (strip `.md.txt` suffixes when presenting documentation URLs to human users) before submitting requests.

---

## Command Syntax & Reference

### 1. Evaluate Calendar-Mode Feasibility Advice

Query the optimal time window and zone for a planned block of GPU or TPU capacity:

```bash
# For GPU / H4D VMs:
gcloud compute advice calendar-mode \
  --project={project_id} \
  --region={region} \
  --machine-type={machine_type} \
  --vm-count={total_instances} \
  --start-time-range=from={start_date},to={end_date} \
  --duration-range=min={min_duration},max={max_duration} \
  [--location-policy={zone}={policy}]

# For Cloud TPUs (supported --tpu-version values: V6E, V5P, V5E; --workload-type is required for V5E):
gcloud compute advice calendar-mode \
  --project={project_id} \
  --region={region} \
  --tpu-version={V6E|V5P|V5E} \
  --chip-count={chip_count} \
  --start-time-range=from={start_date},to={end_date} \
  --duration-range=min={min_duration},max={max_duration} \
  [--workload-type={BATCH|SERVING}] \
  [--location-policy={zone}={policy}]
```

### 2. Inspect Existing Future Reservations

```bash
# List planned future reservations
gcloud compute future-reservations list \
  --project={project_id} \
  [--zones={zone}]

# Inspect a specific future reservation plan
gcloud compute future-reservations describe {future_reservation_name} \
  --zone={zone} \
  --project={project_id}
```

### 3. Create a Calendar-Mode Future Reservation Request

> [!IMPORTANT]
> Submitting a future reservation request (`--planning-status=SUBMITTED`) commits to capacity billing once approved. Always obtain explicit human approval before executing `gcloud compute future-reservations create`.

Once a feasible reservation window and zone are confirmed via `calendar-mode`, create and submit the request:

```bash
# For GPU / H4D VMs (requires --deployment-type=DENSE):
gcloud compute future-reservations create {future_reservation_name} \
  --project={project_id} \
  --zone={zone} \
  --total-count={total_instances} \
  --machine-type={machine_type} \
  --deployment-type=DENSE \
  --reservation-mode=CALENDAR \
  --planning-status=SUBMITTED \
  --require-specific-reservation \
  --reservation-name={reservation_name} \
  --start-time={start_rfc3339} \
  --end-time={end_rfc3339} \
  --auto-delete-auto-created-reservations \
  [--share-setting=projects --share-with={consumer_project_ids}]

# For Cloud TPUs:
gcloud compute future-reservations create {future_reservation_name} \
  --project={project_id} \
  --zone={zone} \
  --tpu-version={tpu_version} \
  --chip-count={chip_count} \
  --reservation-mode=CALENDAR \
  --planning-status=SUBMITTED \
  --require-specific-reservation \
  --reservation-name={reservation_name} \
  --start-time={start_rfc3339} \
  --end-time={end_rfc3339} \
  --auto-delete-auto-created-reservations \
  [--workload-type={BATCH|SERVING}] \
  [--share-setting=projects --share-with={consumer_project_ids}]
```

### 4. Cancel or Delete a Future Reservation (Resource Teardown)

To cancel a pending/submitted request or clean up a cancelled/completed future reservation (requires explicit human approval; `cancel` requires `roles/compute.futureReservationAdmin`):

* **Cancellation Cutoff (`cancel`)**: An `APPROVED` Calendar-Mode request can only be self-service cancelled when **`start-time` is at least 30 days (`720` hours) away**, or **within 24 hours of submission provided `start-time` is at least 4 days (`96` hours) away**.
* **Deletion Preconditions (`delete`)**: `delete` only succeeds once the request is `CANCELLED` or past `end-time`, and prompts interactively unless `--quiet` is passed.

```bash
# Cancel a pending or approved future reservation request (within the allowed window)
gcloud compute future-reservations cancel {future_reservation_name} \
  --zone={zone} \
  --project={project_id}

# Delete a cancelled or completed future reservation record
gcloud compute future-reservations delete {future_reservation_name} \
  --zone={zone} \
  --project={project_id}
```

### 5. Consume the Auto-Created Reservation at `start-time`

When `start-time` arrives, Compute Engine automatically provisions the targeted reservation `{reservation_name}`:

* **For GPU / H4D VMs**: Launch instances with `--provisioning-model=RESERVATION_BOUND`, `--maintenance-policy=TERMINATE`, `--instance-termination-action={STOP|DELETE}`, private networking (`--no-address` with IAP TCP forwarding), and a custom least-privilege `--service-account`:
  ```bash
  gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type={machine_type} \
    --reservation-affinity=specific \
    --reservation={reservation_name} \
    --provisioning-model=RESERVATION_BOUND \
    --maintenance-policy=TERMINATE \
    --instance-termination-action=DELETE \
    [--no-address] \
    [--service-account={service_account_email}]
  ```
* **For Cloud TPUs**: Consume the auto-created reservation via the Compute Engine API using `gcloud compute instances create` or a Compute Engine Managed Instance Group (`gcloud compute instance-templates create` + `gcloud compute instance-groups managed create`) with the TPU machine type (e.g., `ct6e-standard-8t`), `--reservation-affinity=specific`, `--reservation=projects/{project_id}/reservations/{reservation_name}`, `--provisioning-model=RESERVATION_BOUND`, and `--maintenance-policy=TERMINATE` (see [Consume a TPU reservation](https://docs.cloud.google.com/tpu/docs/consume-reservation-compute.md.txt)).

---

## Key Parameters & Planning Dimensions

* **Calendar-Mode Query Flags**:
  * `--start-time-range=from={start_date},to={end_date}`: Required acceptable start window in date or RFC 3339 format (e.g., `from=2026-11-01T00:00:00Z,to=2026-11-30T00:00:00Z`).
  * `--duration-range=min={min_duration},max={max_duration}`: Required minimum and maximum operational duration needed (e.g., `min=7d,max=14d` or `min=14d,max=14d`). Both `min` and `max` must be provided.
  * `--location-policy={zone}={policy}`: Optional per-zone inclusion/exclusion policy (`ALLOW` or `DENY`, e.g., `us-central1-a=ALLOW,us-central1-b=DENY`).
  * `--tpu-version={V6E|V5P|V5E}`: Supported TPU versions in `advice calendar-mode` (`TPU7X` is supported only in `future-reservations create`, not in `advice calendar-mode`).
  * `--workload-type={BATCH|SERVING}`: **Required** when `--tpu-version=V5E` and optional for `V6E` and `V5P`. `BATCH` optimizes for high-throughput batch ML training; `SERVING` optimizes for low-latency concurrent ML inference requests. Do not specify for GPU or H4D VMs.
* **Calendar-Mode Reservation Creation Flags**:
  * `--reservation-mode=CALENDAR`: Required to create a Calendar-Mode future reservation.
  * `--planning-status=SUBMITTED`: Required to submit the Calendar-Mode request for GCP review immediately (self-service Calendar-Mode requests reject `DRAFT` status).
  * `--require-specific-reservation` & `--reservation-name={reservation_name}`: Required to name and target the reservation that Compute Engine automatically creates at `start-time` (`{reservation_name}` must be at most **38 characters**, e.g., `{future_reservation_name}-res`).
  * `--deployment-type=DENSE`: Required when reserving GPU or H4D VMs to ensure tightly coupled placement.
  * `--share-setting={share_type}`: Optional for single-project (`local`) reservations; required only when sharing across consumer projects (`projects`, specified via `--share-with`).
  * `--auto-delete-auto-created-reservations`: Required flag in Calendar Mode so auto-created reservations are automatically deleted at `end-time` (`--no-auto-delete-auto-created-reservations` is rejected with `CALENDAR_MODE_MISSING_AUTO_DELETE`).
* **Lead Times & Hardware Limits** (baseline self-service limits; verify current limits dynamically via `gcloud compute advice calendar-mode` or the official [VM Calendar Mode](https://docs.cloud.google.com/compute/docs/instances/future-reservations-calendar-mode-overview.md.txt#limitations) and [TPU Calendar Mode](https://docs.cloud.google.com/tpu/docs/calendar-mode-reservation.md.txt) documentation as new hardware or limits roll out):
  * **GPU (`a4-highgpu-8g`, `a3-ultragpu-8g`, `a3-megagpu-8g`, `a3-highgpu-8g`, `a3-edgegpu-8g`) and H4D VMs (`h4d-standard-192`, `h4d-highmem-192`, `h4d-highmem-192-lssd`)**:
    * **Instance Count (`--vm-count` / `--total-count`)**: `1` to `80` VMs for GPUs (`1` to `256` VMs for H4D). Note: `a2-*`, `g2-*`, and `a4x-*` families are not supported in Calendar Mode.
    * **Minimum Lead Time**: Earliest start time must be at least **87 hours** (3 days, 15 hours) in advance of current time.
    * **Booking Horizon**: Can reserve up to **60 days** in advance.
    * **Duration**: Minimum **24 hours**, maximum **90 days**.
  * **Cloud TPUs**:
    * **Valid Chip Counts (`--chip-count`) by TPU Version** (check the official [TPU Calendar Mode documentation](https://docs.cloud.google.com/tpu/docs/calendar-mode-reservation.md.txt) or CLI validation feedback if newly released TPU versions or slice sizes are requested):
      * **`V6E`**: `1, 4, 8, 16, 32, 64, 128, 256` chips.
      * **`V5P`**: `4, 8, 16, 32, 64, 128, 256, 512, 1024` chips (`1` chip is invalid; self-service requests in Calendar Mode allow up to `1024` chips per request).
      * **`V5E`** (`--workload-type` required): `SERVING` supports `1, 4, 8` chips; `BATCH` supports `16, 32, 64, 128, 256` chips.
      * **`TPU7X`** (allowlist-only; `future-reservations create` only; not supported in `advice calendar-mode`): `4, 8, 16, 32, 64, 128, 256, 512, 1024` chips (`1` chip is invalid).
    * **Minimum Lead Time**: Earliest start time must be at least **6 hours** in advance of current time.
    * **Booking Horizon**: Can reserve up to **120 days** in advance.
    * **Duration**: Minimum **24 hours**, maximum **90 days**.

---

## Output Interpretation & Decision Matrix

`gcloud compute advice calendar-mode` returns a `recommendations` list containing `recommendationsPerSpec.spec`:

```yaml
recommendations:
- recommendationsPerSpec:
    spec:
      endTime: '2026-11-29T00:00:00Z'
      location: zones/us-central1-a
      otherLocations:
        zones/us-central1-b:
          details: this machine family is not supported in this zone
          status: NOT_SUPPORTED
      recommendationId: 87cc2159-5205-4804-b764-a0ca8d10397c
      recommendationType: FUTURE_RESERVATION
      startTime: '2026-11-15T00:00:00Z'
```

### Feasibility States

1. **FEASIBLE (Direct Match Available)**:
   * `spec` includes `startTime`, `endTime`, and `location` (e.g., `zones/us-central1-a`; strip the `zones/` prefix when passing the bare zone name such as `us-central1-a` to `--zone` in `gcloud compute future-reservations create`).
   * `otherLocations` keys are always intra-region zones (`zones/<zone>`) within the single queried `--region`, and may report runner-up zones within that same region with `status: RECOMMENDED` (or `NO_CAPACITY`, `CONDITIONS_NOT_MET`, `NOT_SUPPORTED`).
   * **Action**: Present the recommended window and copy-pasteable `gcloud compute future-reservations create` command, and ask for explicit human approval before creating the reservation.
2. **INFEASIBLE / CONSTRAINED (No `startTime` / `location` Returned)**:
   * Hardware or window constraints prevent fulfillment in the requested region or timeframe, and all intra-region `otherLocations` entries (`zones/<zone>`) report `status: NO_CAPACITY`, `CONDITIONS_NOT_MET`, or `NOT_SUPPORTED` (`RECOMMENDED` is never returned when `startTime`/`location` is absent, and `otherLocations` never lists other regions).
   * **Mitigations**:
     * **Query Alternative Regions**: Re-run `gcloud compute advice calendar-mode --region={other_region}` against other regions that host the target accelerator (e.g., `us-east4` or `us-west1`).
     * **Flex Time Window**: Widen `--start-time-range=from=...,to=...` to grant the scheduler a broader search window.
     * **Shorten Duration**: Reduce `--duration-range` by breaking massive training runs into smaller checkpointed phases.
     * **Alternative Hardware Generations**: Evaluate equivalent compute alternatives (e.g., comparing `a3-highgpu-8g` with `a3-megagpu-8g` or newer generation TPU slices).

---

## Operational Guardrails

* **Human-Approval Guardrail & Request Immutability**: Never execute mutating commands (`gcloud compute future-reservations create`, `cancel`, `delete`, or `gcloud compute reservations update`) without explicit human approval from the user. Submitted Calendar-Mode future reservation requests cannot be modified via `gcloud compute future-reservations update`; only the auto-created reservation can be updated after `start-time` via `gcloud compute reservations update` (for example, to modify shared consumer projects or Vertex AI access).
* **Compute Engine MCP Server Guardrail**: The Compute Engine MCP server exposes zero tools for `AdviceService` (`advice calendar-mode`) or `FutureReservationsService`, and MCP `create_instance` cannot set `provisioning_model: RESERVATION_BOUND` when consuming auto-created Calendar-Mode reservations. Always use the `gcloud` CLI.
* **Past Date Validation**: If the user's requested reservation window or start date is in the past relative to the current date, do not generate speculative future reservation queries or commands. Ask clarifying questions requesting valid future start and end dates.
* **Negative Guardrail (No Spot Capacity Telemetry)**: Do not use real-time Spot capacity advice (`gcloud beta compute advice capacity --provisioning-model=SPOT`) or emit obtainability scores when planning future GPU/TPU reservations. Future capacity planning requires calendar-mode feasibility analysis, not real-time Spot preemption metrics.
