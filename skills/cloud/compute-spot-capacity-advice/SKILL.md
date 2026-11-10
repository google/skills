---
name: compute-spot-capacity-advice
metadata:
  version: "1.0.0"
  category: Compute
description: >-
  Evaluates Google Compute Engine (GCE) Spot VM capacity obtainability, placement
  likelihood, and machine family or regional flexibility. Use when planning batch
  workloads, finding available Spot CPU or GPU capacity, assessing stockout risks,
  or optimizing instance distribution across zones. Don't use for TPU availability,
  on-demand reservation capacity (use compute-on-demand-reservations), or future
  GPU/TPU calendar bookings (use compute-future-reservations).
---

<!-- disableFinding(LINE_OVER_80) -->

# Compute Engine Spot Capacity Advice

The `compute-spot-capacity-advice` skill provides telemetry and architectural guidance to assess the obtainability of Google Compute Engine (GCE) Spot VMs before submitting creation requests.

Spot VMs run on spare compute capacity and are subject to preemption. Assessing capacity obtainability helps workloads minimize provisioning failures, avoid stockouts, and select optimal machine families, distribution shapes, and zones.

> [!NOTE]
> Spot Capacity Advice is served on the Compute Engine Beta API (`compute.beta.AdviceService.Capacity`, `POST /compute/beta/projects/{project}/regions/{region}/advice/capacity`) and requires no project allowlisting. Always invoke it via the `gcloud beta` release track (`gcloud beta compute advice capacity`) — never omit `beta` even if `gcloud compute advice capacity` appears in `--help`, as the `v1` backend rejects `SPOT`. Flex-start Capacity Advice (`--provisioning-model=FLEX_START`) is currently in Private Preview; for public workloads without explicit allowlists, always use `--provisioning-model=SPOT`.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST read and follow the instructions in [Usage Attribution](references/attribution.md).

---

## Prerequisites & IAM Requirements

Before querying Spot capacity advice, ensure the environment meets these requirements:

1. **Project & Region Configuration**: Prefer passing `--project={project_id}` and `--region={region}` directly on each command to avoid overwriting global workstation state, or obtain explicit user confirmation before setting defaults (e.g., `us-central1`):
   ```bash
   gcloud config set project {project_id}
   gcloud config set compute/region {region}
   ```
2. **Billing & API Enablement**: Ensure the project has an active billing account attached and the Compute Engine API is enabled:
   ```bash
   gcloud services enable compute.googleapis.com --project={project_id}
   ```
3. **Cloud SDK & Authentication**: Ensure the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) is installed (never execute unprompted host installation or component mutation commands such as `apt-get`, piped shell installer scripts, or `gcloud components install beta` without explicit user approval; direct the user to the installation guide instead), then authenticate via `gcloud auth login` (for interactive CLI), `gcloud auth application-default login` (for SDKs), or `GOOGLE_APPLICATION_CREDENTIALS` (for service accounts).
4. **IAM Permissions**: Grant `roles/compute.viewer` (or a custom role containing the `compute.advice.capacity` permission) following the principle of least privilege.
5. **Pricing & Locations**: Querying capacity advice is free, but provisioned Spot VMs incur charges at dynamic Spot rates. Review [Compute Engine Pricing](https://cloud.google.com/compute/pricing), [Available Regions and Zones](https://docs.cloud.google.com/compute/docs/regions-zones.md.txt), and [Google Cloud Locations](https://cloud.google.com/about/locations) (strip `.md.txt` suffixes when presenting documentation URLs to human users).

---

## Command Syntax & Reference

Query capacity advice using `gcloud beta compute advice capacity`:

```bash
gcloud beta compute advice capacity \
  --project={project_id} \
  --region={region} \
  --provisioning-model=SPOT \
  --size={vm_count} \
  --target-distribution-shape={target_shape} \
  (--instance-selection-machine-types={machine_types} | --instance-selection="name={selection_name},machine-type={machine_type_1},machine-type={machine_type_2}") \
  [--zones={zone_1},{zone_2}]
```

### Flag Reference & CLI Constraints

For complete flag definitions, refer to the [`gcloud beta compute advice capacity` reference documentation](https://docs.cloud.google.com/sdk/gcloud/reference/beta/compute/advice/capacity.md.txt). When constructing commands, apply these non-obvious CLI constraints:

* **`--region` vs. `--zones`**: `--region` is automatically inferred when `--zones` is specified.
* **`--size` Bounds**: Accepts `1` to `1000` VMs per query.
* **`--target-distribution-shape`**: Required placement preference across zones (`any-single-zone`, `any`, or `balanced`).
* **Instance Selection & Unsupported Flags**: Specify up to `5` machine types total across the request using a single `--instance-selection-machine-types` flag, a single `--instance-selection` flag (`gcloud` supports only one `--instance-selection` flag per command), or `--instance-flexibility-policy` (up to `10` named selections). Do not pass `--max-run-duration`, `--accelerator-topology`, `rank`, `min-cpu-platform`, `minCpuPlatform`, or `disks` on the CLI.

---

## Output Interpretation: Scores & Recommendations

The command returns one or more recommendations containing placement shards and evaluation scores (or `{}` if zero candidate zones in the region support the requested machine series; regional stockouts still return a recommendation with `obtainability: 0.1` and `estimatedUptime: 60s`), as shown in the following example output:

```yaml
# Example output
recommendations:
- scores:
    obtainability: 0.9
    estimatedUptime: 3600s
  shards:
  - instanceCount: 100
    machineType: n2-standard-32
    provisioningModel: SPOT
    zone: https://compute.googleapis.com/compute/beta/projects/example-project/zones/us-central1-a
```

### Score Evaluation Rubric

Refer to [View the availability of Spot VMs](https://docs.cloud.google.com/compute/docs/instances/view-vm-availability.md.txt) for full definitions of `scores.obtainability` (`0.0` to `1.0`, emitted in discrete buckets such as `0.9`, `0.5`, and `0.1`) and `scores.estimatedUptime` (`3600s`, `600s`, or `60s`). Treat `obtainability >= 0.7` as strongly obtainable, `0.4`–`0.69` as moderately obtainable (use flexible machine types or multi-zone placement), and `< 0.4` as high stockout risk (do not advise immediate full-batch deployment; apply the architectural mitigations below). Interpret `scores.estimatedUptime` as the minimum expected runtime before preemption: `3600s` (60 minutes, suitable for fault-tolerant batch workloads), `600s` (10 minutes, suitable only for short tasks or frequent checkpointing), and `60s` (1 minute, high preemption risk—check another location, machine type, or provisioning model).

---

## Architectural Mitigation & Best Practices

When capacity is constrained (`obtainability` `< 0.4` or empty `{}` returned when the machine series is unavailable in the region):

1. **Broaden Distribution Shape**:
   * Switch from `--target-distribution-shape=any-single-zone` to `--target-distribution-shape=any` (or `balanced`) so Compute Engine can distribute instances across all available zones in the region.
2. **Inject Instance Flexibility**:
   * Add alternative machine shapes within the same generation (e.g., `n2-standard-32`, `n2-standard-48`) or across families (e.g., `c2-standard-30`, `c3-standard-44`) using `--instance-selection` or `--instance-selection-machine-types` (note that Gen 4+ families such as `c4*`, `n4*`, `m4*`, `h4d*`, `a4*`, and `a3-ultragpu-8g` require Hyperdisk boot volumes rather than `pd-*` disks when creating instances or templates; for newly released machine series, verify supported disk types via `gcloud compute machine-types describe` or the official [machine family documentation](https://docs.cloud.google.com/compute/docs/machine-resource.md.txt)).
3. **Regional Fallbacks**:
   * Evaluate adjacent regions with similar network latency or billing characteristics (e.g., fallback from `us-central1` to `us-east4`, `us-west1`, or `us-east1`).
4. **Accelerator, SKU & Zone Limitations**:
   * `gcloud beta compute advice capacity` evaluates GPU capacity via integrated accelerator machine types (such as `g2-standard-*`, `a2-highgpu-*`, `a3-highgpu-*`, `a3-megagpu-*`) and includes AI zones by default (users should confirm that AI zones are enabled for their project). Do not pass `--accelerator-topology`, and restrict `--instance-selection` strictly to `name` and `machine-type` (do not pass `rank`, `min-cpu-platform`, `disks`, or guest accelerator flags on the `gcloud` CLI; `n1-*` VMs with attached guest GPUs and machine types with non-default Local SSDs are supported only on the Beta REST API under `instanceFlexibilityPolicy.instanceSelections.{selection_name}` via `guestAccelerators` and `disks` with one `type: SCRATCH` entry per Local SSD disk).
   * **Unsupported Spot SKUs, Free Tier & Day-0 Immutability**: Spot VMs do not support `a4x-*` or bare metal (`*-metal`) shapes, Spot `e2-micro` VMs do not qualify for the Google Cloud Free Tier allowance, and existing `STANDARD` VMs cannot be converted in place to `SPOT` via `set-scheduling` (requires recreating the VM).
   * **No TPU Availability Support**: The `advice.capacity` API does not support viewing the availability of Cloud TPUs. For TPU capacity planning and calendar bookings, use `compute-future-reservations` (`gcloud compute advice calendar-mode`).
5. **Quota & Headroom Disclaimer**:
   * Obtainability scores reflect physical datacenter capacity, not project quota allocation. Verify regional Spot CPU/GPU quota (via `gcloud compute regions describe {region}`, `gcloud compute project-info describe`, or the Google Cloud Console Quotas page) before provisioning. Attempting to launch instances without sufficient project quota will fail at runtime despite high physical capacity availability.
6. **Read-Only Advisory, Hardened VM Defaults & MCP Guardrail**:
   * Capacity advice is strictly a read-only advisory tool. Never execute mutating commands (such as `gcloud compute instances create` or `gcloud compute instances delete`) without explicit human approval from the user; provide copy-pasteable commands instead.
   * When generating `gcloud compute instances create` commands for Spot VMs, recommend private networking (`--no-address` paired with IAP TCP forwarding), a custom least-privilege service account (`--service-account`), and `--instance-termination-action=DELETE` (so boot disks do not continue billing after Spot preemption). Remind users to delete temporary Spot VMs (`gcloud compute instances delete {vm_name} --zone={zone}`, which prompts interactively unless `--quiet` is passed) when workloads finish.
   * **Compute Engine MCP `create_instance` Guardrail**: Inspect the in-session MCP `create_instance` tool schema before invoking it (in case newer MCP server versions add support); unless verified in the current schema, MCP `create_instance` omits `provisioning_model` (silently provisioning full-price `STANDARD` VMs), hardcodes `global/networks/default`, and cannot set custom service accounts — always use `gcloud compute instances create --provisioning-model=SPOT` instead.
