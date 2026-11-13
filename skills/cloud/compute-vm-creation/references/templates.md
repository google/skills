# Compute Engine VM Creation Reference Templates

## Table of Contents

- [1. Golden Path General Purpose (Production)](#1-golden-path-general-purpose-production): Lines 40-90
- [2. Developer Dev/Test VM (Cost-Optimized Spot)](#2-developer-devtest-vm-cost-optimized-spot): Lines 92-135
- [3. High-Performance General Purpose & Compute-Heavy](#3-high-performance-general-purpose-compute-heavy): Lines 137-226
- [4. GPU Workstation (ML Inference)](#4-gpu-workstation-ml-inference): Lines 228-288
- [5. Bare Metal Instance (-metal)](#5-bare-metal-instance--metal): Lines 290-335

---

## Global Template & MCP Schema Conventions

- **Interactive Safety**: Copy-pasteable `gcloud compute instances create` and
  `gcloud compute instances delete` snippets intentionally omit `--quiet` so
  interactive `[Y/n]` confirmation prompts protect manual runs against
  accidental resource creation or permanent disk deletion (see
  [Delete a VM](https://docs.cloud.google.com/compute/docs/instances/deleting-instance.md.txt)).
- **Enterprise VPC Subnets (`--subnet={subnet}`)**: Replace `{subnet}` with the
  target custom VPC subnet name, a Shared VPC subnet URI
  (`projects/{host_project_id}/regions/{region}/subnetworks/{subnet}`), or
  `default` **only** after verifying the `default` VPC exists (many enterprise
  organizations enforce `constraints/compute.skipDefaultNetworkCreation`).
- **MCP `create_instance` Schema Boundary (`McpCreateInstanceRequest`)**: The
  Compute Engine MCP server's `create_instance` tool accepts **only eight flat
  top-level JSON fields**: `project`, `zone`, `name`, `machineType` (bare short
  name such as `"e2-standard-2"`, never `"zones/{zone}/machineTypes/..."`),
  `imageProject`, `imageFamily`, `guestAccelerators`
  (`[{"acceleratorType": "nvidia-l4", "acceleratorCount": 1}]`), and
  `maintenancePolicy` (`"MIGRATE"` or `"TERMINATE"`). Because the MCP server
  hardcodes `global/networks/default` and default disk/service-account settings,
  **always use `gcloud compute instances create` (or REST `instances.insert`)**
  whenever `--no-address`, custom subnets, custom service accounts, Shielded VM
  flags, OS Login, Spot scheduling, custom disk sizes/types, Hyperdisk, or bare
  metal (`-metal`) settings are required.

---

## 1. Golden Path General Purpose (Production)

The secure, resilient, and enterprise-ready baseline. Uses `e2-standard-2` with
a `30` GB `pd-balanced` boot disk (matching the Standard Tier Golden Path; scale
down to `e2-medium` for light websites/apps or up to `e2-standard-4` with a
`50` GB `pd-balanced` disk for higher-concurrency production services),
private-only networking (`--no-address` paired with Cloud NAT and
[IAP TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding.md.txt)),
IAM-governed SSH (`enable-oslogin`), Shielded VM protections, and a custom
service account. Default OS image family is `debian-12` (or `debian-13`).

**Via gcloud CLI (Recommended for Hardened Production):**

```bash
gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type=e2-standard-2 \
    --network-tier=PREMIUM \
    --subnet={subnet} \
    --no-address \
    --maintenance-policy=MIGRATE \
    --metadata=enable-oslogin=TRUE \
    --service-account={custom_service_account} \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-12,mode=rw,size=30,type=projects/{project_id}/zones/{zone}/diskTypes/pd-balanced \
    --shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --reservation-affinity=any
```

**Via MCP (`create_instance` JSON — Default-VPC Prototyping Only):**

```json
{
  "project": "{project_id}",
  "zone": "{zone}",
  "name": "{vm_name}",
  "machineType": "e2-standard-2",
  "imageProject": "debian-cloud",
  "imageFamily": "debian-12",
  "maintenancePolicy": "MIGRATE"
}
```

> **Important:** MCP `create_instance` attaches the VM to
> `global/networks/default` with default disk size/type and default service
> account settings. Do **not** use MCP `create_instance` when `--no-address`,
> custom `--subnet={subnet}`, `{custom_service_account}`, OS Login, or custom
> disk sizing is required—use `gcloud compute instances create` instead.

## 2. Developer Dev/Test VM (Cost-Optimized Spot)

Ideal for sandboxes, scripting, and stateless batch testing. Uses Spot
provisioning (`--provisioning-model=SPOT`) with valid termination flags
(`--instance-termination-action=DELETE` [or `STOP` if preserving the stopped VM
and boot disk on preemption], `--maintenance-policy=TERMINATE`, and
`--no-restart-on-failure`; see
[Create and use Spot VMs](https://docs.cloud.google.com/compute/docs/instances/create-use-spot.md.txt)),
private-by-default networking (`--no-address`), OS Login, a custom service
account, and Shielded VM protections.

**Via gcloud CLI:**

```bash
gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type=e2-medium \
    --subnet={subnet} \
    --no-address \
    --metadata=enable-oslogin=TRUE \
    --service-account={custom_service_account} \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --provisioning-model=SPOT \
    --instance-termination-action=DELETE \
    --maintenance-policy=TERMINATE \
    --no-restart-on-failure \
    --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-12,mode=rw,size=20,type=projects/{project_id}/zones/{zone}/diskTypes/pd-standard \
    --shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring
```

> **MCP `create_instance` Compatibility Note:** `McpCreateInstanceRequest` does
> **not** support `SPOT` provisioning (`provisioningModel`,
> `instanceTerminationAction`, `automaticRestart`), `--no-address`, or custom
> subnets/service accounts. Always use `gcloud compute instances create` (or
> Compute Engine v1 REST `instances.insert`) for Spot VMs.

> **Warning:** Spot instances can be preempted at any time by Google Cloud.
> Recommend these only for stateless, fault-tolerant workloads, and always
> provide cleanup instructions
> (`gcloud compute instances delete {vm_name} --zone={zone} --delete-disks=all`)
> so disposable test instances do not incur orphaned resource charges.

## 3. High-Performance General Purpose & Compute-Heavy

Designed for CPU-intensive workloads like C++ builds, high-throughput data
pipelines, or batch processing.

- **3rd-Gen High-Performance General Purpose**: Use `c3-standard-4` or
  `n2-standard-4` with `pd-ssd` (or `pd-balanced`) as the baseline 4-vCPU
  machine type unless the user requests a different vCPU count.
- **Compute-Optimized Family (`C2`, `C2D`, `H3`, `H4D`)**: When strict
  compute-optimized CPU clocks/ratios are requested, use `c2d-standard-4` (with
  `pd-ssd`) or `h3-standard-88` (supports `pd-balanced` or
  `hyperdisk-balanced`).
- **4th-Gen General Purpose (`C4`, `N4`, Arm `C4A`)**: Legacy `pd-*` disk types
  (`pd-standard`, `pd-balanced`, `pd-ssd`) are **unsupported and rejected** on
  4th-generation series (`C4`, `N4`, `C4A`, `C4D`, `M4`, `X4`, `A4`). Always
  pair 4th-gen VMs with **Google Cloud Hyperdisk** (`hyperdisk-balanced` by
  default; note that `N4` supports `hyperdisk-balanced` and
  `hyperdisk-throughput`, not `hyperdisk-extreme`—see *"Machine series support
  for Hyperdisk"* in
  [About Google Cloud Hyperdisk](https://docs.cloud.google.com/compute/docs/disks/hyperdisks.md.txt)),
  `nic-type=GVNIC`, and `debian-13` (or `debian-12-arm64` / `debian-13-arm64` on
  Arm `C4A`).

**Via gcloud CLI (3rd-Gen `c3-standard-4` with `pd-ssd`):**

```bash
gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type=c3-standard-4 \
    --subnet={subnet} \
    --no-address \
    --metadata=enable-oslogin=TRUE \
    --service-account={custom_service_account} \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-12,mode=rw,size=100,type=projects/{project_id}/zones/{zone}/diskTypes/pd-ssd \
    --maintenance-policy=MIGRATE \
    --shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring
```

**Via gcloud CLI (4th-Gen `c4-standard-4` with `hyperdisk-balanced` &
`GVNIC`):**

```bash
gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type=c4-standard-4 \
    --network-interface=subnet={subnet},no-address,nic-type=GVNIC \
    --metadata=enable-oslogin=TRUE \
    --service-account={custom_service_account} \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-13,mode=rw,size=100,type=projects/{project_id}/zones/{zone}/diskTypes/hyperdisk-balanced \
    --maintenance-policy=MIGRATE \
    --shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring
```

**Via MCP (`create_instance` JSON — Default-VPC 3rd-Gen Prototyping Only):**

```json
{
  "project": "{project_id}",
  "zone": "{zone}",
  "name": "{vm_name}",
  "machineType": "c3-standard-4",
  "imageProject": "debian-cloud",
  "imageFamily": "debian-12",
  "maintenancePolicy": "MIGRATE"
}
```

> **Warning (Cost & Day-0 Mutability):** High-performance (`C3`/`N2`/`C4`/`N4`)
> and compute-optimized (`C2D`/`H3`) instances plus `pd-ssd` / Hyperdisk volumes
> carry premium costs (disks are billed continuously even when the VM is
> stopped). Persistent Disks and Hyperdisks cannot shrink in-place, and changing
> disk type requires creating a new disk from a snapshot and swapping it on a
> stopped VM via `detach-disk` and `attach-disk --boot` (without recreating the
> VM). Stopped standalone IPv4 VMs can migrate VPC/subnet in-place via
> `gcloud compute instances network-interfaces update` (only NIC count `nic1+`
> is fixed at creation) and can be renamed in-place via `gcloud compute
> instances set-name {vm_name} --new-name={new_name} --zone={zone}` (see
> [Rename a VM](https://docs.cloud.google.com/compute/docs/instances/rename-instance.md.txt)
> and [Update instance properties](https://docs.cloud.google.com/compute/docs/instances/update-instance-properties.md.txt)).
> Properties that genuinely require **recreating the VM** are **zone**, **CPU
> architecture** (`x86_64` vs. `ARM64`), and **Encrypted-Memory VM (AMD SEV-SNP
> or Intel TDX)** enablement.

## 4. GPU Workstation (ML Inference)

> **Mandatory Response Warnings (Always State in Reply):** Always warn the user
> about **high GPU hourly compute costs**, required **project/regional GPU quota
> verification**, and that **GPU VMs do not support live migration**
> (`--maintenance-policy=TERMINATE` is mandatory; never set `MIGRATE`—see
> [Handle GPU host maintenance events](https://docs.cloud.google.com/compute/docs/gpus/gpu-host-maintenance.md.txt)).

Tailored for LLM inference, deep learning, or graphics workloads on the `G2`
series with an NVIDIA L4 GPU, using a current Ubuntu Deep Learning VM image
(`projects/deeplearning-platform-release/global/images/family/common-cu129-ubuntu-2404-nvidia-580`,
or `common-cu129-ubuntu-2204-nvidia-580`), private-by-default networking
(`--no-address`), OS Login, a custom service account, and
`--maintenance-policy=TERMINATE`.

**Via gcloud CLI:**

```bash
gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type=g2-standard-4 \
    --accelerator=type=nvidia-l4,count=1 \
    --subnet={subnet} \
    --no-address \
    --metadata=enable-oslogin=TRUE \
    --service-account={custom_service_account} \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --maintenance-policy=TERMINATE \
    --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/deeplearning-platform-release/global/images/family/common-cu129-ubuntu-2404-nvidia-580,mode=rw,size=100,type=projects/{project_id}/zones/{zone}/diskTypes/pd-balanced \
    --shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring
```

**Via MCP (`create_instance` JSON — Default-VPC Prototyping Only):**

```json
{
  "project": "{project_id}",
  "zone": "{zone}",
  "name": "{vm_name}",
  "machineType": "g2-standard-4",
  "imageProject": "deeplearning-platform-release",
  "imageFamily": "common-cu129-ubuntu-2404-nvidia-580",
  "guestAccelerators": [
    {
      "acceleratorType": "nvidia-l4",
      "acceleratorCount": 1
    }
  ],
  "maintenancePolicy": "TERMINATE"
}
```

> **Warning:** GPU instances carry high hourly costs and require verified GPU
> quota in the target GCP project and zone. GPU VMs **do not support live
> migration** (`--maintenance-policy=TERMINATE` is mandatory; never set
> `MIGRATE`). Use `gcloud compute instances create` instead of MCP
> `create_instance` whenever `--no-address`, custom subnets, custom disk size,
> or `{custom_service_account}` is required.

## 5. Bare Metal Instance (`-metal`)

Designed for workloads requiring direct physical CPU/PMU access, third-party
hypervisors, or specialized licensing (`c3-standard-192-metal`,
`c4-standard-288-metal`, `x4-megamem-1440-metal`). See
[Bare metal instances](https://docs.cloud.google.com/compute/docs/instances/bare-metal-instances.md.txt)
and
[Operating system details](https://docs.cloud.google.com/compute/docs/images/os-details.md.txt)
for non-default SKUs:

- **Hyperdisk Only**: Must use `hyperdisk-balanced` (or supported Hyperdisk
  types); legacy `pd-*` disks and Windows images are unsupported.
- **Intel IDPF Networking & Supported OS**: Must configure `nic-type=IDPF`
  inside `--network-interface=subnet={subnet},no-address,nic-type=IDPF` (neither
  `GVNIC` nor `VIRTIO_NET` is supported, and `--network-interface` must **not**
  be combined with top-level `--subnet` or `--no-address` flags). Use
  `debian-13` as the default Debian image (`debian-12` is unsupported on
  `C3-metal`, `C4-metal`, and `X4`).
- **Host Maintenance & OS Login**: Must set `--maintenance-policy=TERMINATE` and
  `--metadata=enable-oslogin=TRUE`.
- **Shielded Flags**: Standard x86 `-metal` SKUs lack a hypervisor vTPM—pass
  `--no-shielded-secure-boot` and omit `--shielded-vtpm` /
  `--shielded-integrity-monitoring` (vTPM on bare metal is supported only on
  `A4X Max` and Arm `C4A` bare metal SKUs).

**Via gcloud CLI (CLI / REST Only — Unsupported by MCP `create_instance`):**

```bash
gcloud compute instances create {vm_name} \
    --project={project_id} \
    --zone={zone} \
    --machine-type=c3-standard-192-metal \
    --network-interface=subnet={subnet},no-address,nic-type=IDPF \
    --maintenance-policy=TERMINATE \
    --metadata=enable-oslogin=TRUE \
    --service-account={custom_service_account} \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-13,mode=rw,size=200,type=projects/{project_id}/zones/{zone}/diskTypes/hyperdisk-balanced \
    --no-shielded-secure-boot
```

> **Warning:** Bare metal (`-metal`) instances provision an entire physical host
> (for example, 192–1440 logical processors), incur substantial dedicated-host
> hourly costs, require dedicated bare-metal regional CPU quota, and cannot use
> MCP `create_instance` because `McpCreateInstanceRequest` cannot set
> `nic-type=IDPF`, `hyperdisk-balanced`, `--no-address`, or OS Login metadata.
