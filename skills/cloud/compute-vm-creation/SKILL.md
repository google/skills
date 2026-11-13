---
name: compute-vm-creation
description: >-
  Guides the planning, configuration, and provisioning of standalone Google
  Compute Engine virtual machines (VMs) and bare metal (-metal) instances using
  gcloud CLI commands or direct MCP tool execution. Use ONLY when the user wants
  to create, configure, or provision a new standalone Compute Engine VM or bare
  metal instance from conversational intents (hardware sizing, region selection,
  OS image, networking, security defaults). DO NOT read or use for Google
  Kubernetes Engine (GKE) Autopilot or Standard clusters, Kubernetes node pools
  or Pods, container orchestration, managing existing VMs, Managed Instance
  Groups (MIGs), or Instance Templates.
metadata:
  version: "1.0.0"
  category: Compute
---

# Compute Engine VM Creation

This skill provides an interactive, intent-based experience for provisioning
standalone Google Compute Engine VM and bare metal (`-metal`) instances. It
supports users ranging from beginners asking to "create a VM" to cloud engineers
requiring customized infrastructure, mapping natural language intents to secure
Compute Engine configurations grounded in the Golden Path.

> **MCP Tools:** `list_instances`, `create_instance`, `get_instance_basic_info`,
> `delete_instance`, `get_zone_operation`, `list_machine_types`,
> `list_accelerator_types`, `list_images`

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md). Never include attribution
environment variables or `User-Agent` tags in generated scripts, Terraform, or
copy-pasteable commands shown to the user.

---

## Prerequisites

Ensure the following setup requirements are met before provisioning instances.
Any host modifications (such as installing or updating the `gcloud` CLI,
installing or configuring the Google Compute Engine MCP server, or modifying
local environment configuration) must be explicitly approved by the user before
execution.

- **Cloud SDK Installation**: Verify `gcloud` is installed (`gcloud --version`,
  Google Cloud SDK >= 480.0.0) only when executing live CLI commands. If
  missing or outdated, ask the user for explicit approval before installing or
  updating via
  [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
- **Compute Engine MCP Server**: For direct MCP tool execution
  (`list_instances`, `create_instance`, `get_instance_basic_info`,
  `delete_instance`, `get_zone_operation`, `list_machine_types`,
  `list_accelerator_types`, `list_images`), check whether the Compute Engine MCP
  tools are loaded in your active tool declarations, or ask the user for
  approval to configure the server following
  [Use the Compute Engine MCP server](https://docs.cloud.google.com/compute/docs/use-compute-engine-mcp.md.txt).
- **Billing Account**: Confirm the target Google Cloud project has an active
  billing account linked (required even when using
  [Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features.md.txt)
  resources).
- **Authentication**: Authenticate your environment for CLI execution
  (`gcloud auth login`), application/MCP SDKs
  (`gcloud auth application-default login`), or service account credentials
  (`GOOGLE_APPLICATION_CREDENTIALS`).
- **Project Selection & API Enablement**: Set the target project and enable the
  Compute Engine API:
  ```bash
  gcloud config set project {project_id}
  gcloud services enable compute.googleapis.com
  ```
- **Required IAM Roles**:
  - **Caller Roles**: `roles/compute.instanceAdmin.v1` (to create and manage
    instances), `roles/iam.serviceAccountUser` (to attach
    `{custom_service_account}`), and `roles/mcp.toolUser` when invoking the
    Compute Engine MCP server.
  - **IAP SSH/RDP Access for Private (`--no-address`) VMs**: Connecting via
    `gcloud compute ssh {vm_name} --zone={zone} --tunnel-through-iap` requires
    `roles/iap.tunnelResourceAccessor` plus a VPC firewall rule allowing TCP
    `22` (or `3389` for RDP) from IAP's forwarding range `35.235.240.0/20` (see
    [Use IAP for TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding.md.txt)).
  - **Custom VM Service Account Setup**: Fresh projects only contain the default
    Compute Engine service account. If `{custom_service_account}` does not yet
    exist, create a dedicated least-privilege service account first (seeking
    user approval before granting IAM bindings):
    ```bash
    gcloud iam service-accounts create {sa_name} \
      --project={project_id} \
      --display-name="{sa_display_name}"
    gcloud projects add-iam-policy-binding {project_id} \
      --member="serviceAccount:{sa_name}@{project_id}.iam.gserviceaccount.com" \
      --role="roles/logging.logWriter"
    gcloud projects add-iam-policy-binding {project_id} \
      --member="serviceAccount:{sa_name}@{project_id}.iam.gserviceaccount.com" \
      --role="roles/monitoring.metricWriter"
    ```

---

## Workflow

1. **Determine Execution Method & MCP Capability Boundary**:
   - **Fast Conversational Intake (No Shell Probing on Missing Inputs)**: When a
     user asks to configure or create a VM without providing mandatory inputs
     (`project_id`, `vm_name`, `region`/`zone`, or public vs. private
     networking), **respond immediately after reading `SKILL.md` without running
     `gcloud config list`, `gcloud --version`, or any shell commands**. Clarify
     that you can either execute provisioning once confirmed (Automated
     Execution) or provide copy-pasteable `gcloud` commands / JSON payloads
     (Manual Execution), recommend a sizing tier, and ask for the missing inputs
     in a single turn.
   - **MCP vs. `gcloud` Routing Rule**: Compute Engine MCP discovery tools
     (`list_instances`, `get_instance_basic_info`, `list_machine_types`,
     `list_accelerator_types`, `list_images`, `get_zone_operation`) are ideal
     for read-only inspection. However, MCP `create_instance`
     (`McpCreateInstanceRequest`) accepts **only eight flat top-level fields**
     (`project`, `zone`, `name`, bare `machineType`, `imageProject`,
     `imageFamily`, `guestAccelerators`, `maintenancePolicy`) and hardcodes
     `global/networks/default` without `--no-address`, custom subnets, custom
     service accounts, Shielded VM flags, OS Login, Spot scheduling, or custom
     disk sizes/types. **Route all hardened (`--no-address`, custom
     `--subnet={subnet}`, `{custom_service_account}`, Shielded VM, OS Login),
     Spot, custom-disk, 4th-gen Hyperdisk, and bare metal (`-metal`) creations
     to `gcloud compute instances create` (or REST `instances.insert`)** rather
     than dropping security guardrails to fit `create_instance`. Use MCP
     `create_instance` only for default-VPC prototyping when default disk and
     service-account settings are explicitly acceptable.
2. **Gather Mandatory Inputs**: **ALWAYS** ask the user for any missing inputs:
   - **Project ID** (Ask directly if not provided in the prompt).
   - **VM Name** (Offer a friendly default suggestion if unsure, e.g.,
     `my-first-web-server`).
   - **Region & Zone** (Explain *why* simply: *"Choosing a location closer to
     you or your users reduces latency and makes things load faster."* Recommend
     `us-central1` / `us-central1-a` if the user has no preference, and consult
     [Regions and zones](https://docs.cloud.google.com/compute/docs/regions-zones.md.txt),
     [GPU regions and zones](https://docs.cloud.google.com/compute/docs/regions-zones/gpu-regions-zones.md.txt),
     or [Google Cloud locations](https://cloud.google.com/about/locations) only
     when verifying non-default regional availability):
     ```bash
     gcloud config set compute/region {region}
     gcloud config set compute/zone {zone}
     ```
3. **Conversational Triage (Sizing, Generation & OS)**: Map the user's workload
   to the **Intent-Based Sizing Tiers** and hardware generation defaults:
   - **Default OS images**: Use `debian-12` (`debian-cloud`) for `E2`, `N2`,
     `C3` virtualized, and `C2D`; use `debian-13` (`debian-cloud`) for 4th-gen
     (`C4`, `N4`, `X4`) and bare metal (`c3-standard-192-metal`,
     `c4-standard-288-metal`, where `debian-12` is unsupported); use
     `debian-12-arm64` / `debian-13-arm64` for Arm `C4A`; and use
     `common-cu129-ubuntu-2404-nvidia-580` (`deeplearning-platform-release`) for
     `G2` GPUs. Consult
     [Operating system details](https://docs.cloud.google.com/compute/docs/images/os-details.md.txt)
     and
     [Bare metal instances](https://docs.cloud.google.com/compute/docs/instances/bare-metal-instances.md.txt)
     only when selecting non-default OS images or bare metal SKUs.
   - **Storage by generation**: Use `hyperdisk-balanced` on 4th-gen (`C4`, `N4`,
     `C4A`, `C4D`, `M4`, `X4`, `A4`) and bare metal (`-metal`) instances where
     `pd-*` disks are rejected (`N4` supports `hyperdisk-balanced` and
     `hyperdisk-throughput`, not `hyperdisk-extreme`; `H3` supports
     `pd-balanced` and `hyperdisk-balanced`). Consult the *"Machine series
     support for Hyperdisk"* section of
     [About Google Cloud Hyperdisk](https://docs.cloud.google.com/compute/docs/disks/hyperdisks.md.txt)
     only for non-default disk types.
4. **Determine Network Accessibility & Subnet**: **ALWAYS** ask in plain,
   non-technical language whether the VM needs to be reachable from the public
   internet or kept private, noting that private networking (`--no-address`) is
   the security best practice—even when hosting a website or web app. Use
   `--subnet={subnet}` (verifying whether a custom/Shared VPC subnet or
   `default` VPC exists, since many enterprise projects enforce
   `constraints/compute.skipDefaultNetworkCreation`).
5. **Configure Security, OS Login & Service Accounts**: Enable IAM-governed SSH
   via `--metadata=enable-oslogin=TRUE`, recommend a custom least-privilege
   service account (`{custom_service_account}`), and enable Shielded VM flags
   (`--shielded-secure-boot`, `--shielded-vtpm`,
   `--shielded-integrity-monitoring`) on virtualized VMs (on standard x86
   `-metal` bare metal instances, pass `--no-shielded-secure-boot` and omit
   vTPM/integrity flags).
6. **Summarize & Confirm (Mode-Aware)**: Present a clear summary of the proposed
   VM configuration, cost profile, and architectural warnings:
   - **Automated Execution Mode**: **Always** ask for explicit user confirmation
     before executing any mutating provisioning command or tool call (e.g.,
     *"Would you like me to proceed with provisioning this configuration, or
     adjust any settings first?"*).
   - **Manual / `"Do not execute"` Mode**: Instruct the user to review and
     substitute any `{snake_case}` placeholders (such as `{subnet}` or
     `{custom_service_account}`) before running the command in their terminal;
     do **not** offer to execute provisioning when tools are disconnected or
     execution was forbidden.
7. **Execute or Deliver Payloads**:
   - **Automated**: Execute `gcloud compute instances create` (prefixed with
     `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` per
     [Usage Attribution](references/attribution.md)) for hardened/Spot/4th-gen/
     bare-metal configurations, or call MCP `create_instance` for default-VPC
     prototyping, tracking progress via `get_zone_operation` and verifying via
     `get_instance_basic_info`.
   - **Manual**: Output formatted, copy-pasteable `gcloud` CLI commands (without
     `--quiet` or attribution prefixes) or JSON payloads with clear
     instructions.
8. **Verify, Deliver Next Steps & Teardown Guidance**: Provide post-provisioning
   access steps (for example, via `--tunnel-through-iap` with `gcloud compute
   ssh`) and **always** include teardown instructions (omitting `--quiet` so
   interactive confirmation prevents accidental data loss; see
   [Delete a VM](https://docs.cloud.google.com/compute/docs/instances/deleting-instance.md.txt)):
   ```bash
   gcloud compute instances delete {vm_name} --zone={zone} --delete-disks=all
   ```
   Remind the user to pass `--delete-disks=all` (or `--keep-disks=all` if
   retaining data) so persistent disks are not orphaned.

---

## Intent-Based Sizing Tiers

If a user says "I want to create a VM" or is unsure of hardware specs, use this
table to recommend a tier. Point users to
[Google Cloud pricing](https://cloud.google.com/pricing) and
[Compute Engine pricing](https://cloud.google.com/compute/all-pricing) for
current regional rates rather than quoting hardcoded dollar figures.

| **Conversational Tier** | **Best For...** | **Underlying Machine** | **Boot Disk (Default)** | **Cost Profile** |
| --- | --- | --- | --- | --- |
| **Starter Tier** *(Dev/Test & Learning)* | "I just want to play around," "I'm learning Linux," "I have a tiny hobby script." | `e2-micro` (Free Tier eligible) or `e2-small` | 10 GB Standard Disk (`pd-standard`; Free Tier covers up to 30 GB `pd-standard`) | **Very Low** ([Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features.md.txt) covers **one non-preemptible `e2-micro` instance/month** in `us-west1`, `us-central1`, or `us-east1` only; `e2-small` or other regions incur standard billing immediately; active billing account required) |
| **Standard Tier** *(Websites & Apps)* **[GOLDEN PATH]** | "I want to host a website," "I'm running a small database," "I don't know, just give me a basic one." | `e2-standard-2` (default baseline; `e2-medium` for light websites/apps, or `e2-standard-4` with 50 GB `pd-balanced` for higher concurrency) | 30 GB Balanced Disk (`pd-balanced`) | **Moderate** (Pay-as-you-go; see [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)) |
| **Powerhouse Tier** *(Heavy Processing)* | "I have heavy data pipelines," "I'm compiling large codebases," "I need maximum speed." | 3rd-gen General-purpose `c3-standard-4` or `n2-standard-4` (4th-gen `c4-standard-4` / `n4-standard-4` / Arm `c4a-standard-4`; Compute-optimized `c2d-standard-4` / `h3-standard-88`) | 100 GB `pd-ssd` (3rd-gen/`C2D`), `pd-balanced` or `hyperdisk-balanced` (`H3`), or `hyperdisk-balanced` (mandatory on 4th-gen `C4`/`N4`/`C4A`) | **Premium** (Pay-as-you-go) |
| **Specialist Tier** *(AI, Graphics & Bare Metal)* | "I want to run an LLM," "I need a GPU workstation," "I need a bare metal `-metal` host." | `g2-standard-4` (1 NVIDIA L4 GPU) or bare metal `c3-standard-192-metal` / `c4-standard-288-metal` | 100 GB `pd-balanced` (`G2`) or 200 GB `hyperdisk-balanced` (`-metal` / 4th-gen `A4`) | **High** (Requires GPU or dedicated bare-metal CPU quota) |

> **Rule:** Default to the Standard Tier (`e2-standard-2` with a 30 GB
> `pd-balanced` boot disk) unless the user has specific requirements that other
> tiers or sizes satisfy. When a workload maps to a tier without an explicit
> vCPU/RAM count, **always use the baseline machine type listed in the table**
> (`e2-micro` or `e2-small` for Starter; `e2-standard-2` [or `e2-medium` /
> `e2-standard-4` when justified] for Standard; `c3-standard-4` or
> `n2-standard-4` for 3rd-gen Powerhouse, `c4-standard-4` / `n4-standard-4` for
> 4th-gen, or `c2d-standard-4` for Compute-optimized; `g2-standard-4` for L4
> GPU) rather than upsizing to `-8` or `-16`.

---

## Conversational Guidelines (How to Talk to Users)

### 1. Early Fork: Establishing Execution Mode

At the start of an interactive session, state whether execution is automated
(provisioning after confirmation via `gcloud` / Compute Engine MCP) or guided
(outputting copy-pasteable `gcloud` commands or JSON payloads for Cloud Shell or
terminal)—**without running `gcloud config list` or shell commands while
mandatory inputs are still missing**.

### 2. Handling Simple Requests (e.g., "Create a VM" or "Host a Small Website")

Do not overwhelm beginners with block-storage IOPS or CPU architecture jargon,
and **do not run terminal commands before the user answers**. Clarify execution
mode, recommend the **Standard Tier (Golden Path)** baseline (`e2-standard-2` or
`e2-medium` with a **30 GB `pd-balanced` boot disk**), and **always** ask for
all four required inputs in your first response:

1. **Google Cloud Project ID**
2. **VM Name** (e.g., `my-first-web-server`)
3. **Region or Zone** (explaining that a location closer to users lowers network
   latency and makes pages load faster; suggest `us-central1` / `us-central1-a`
   if unsure)
4. **Public Internet vs. Private Networking** (in plain language: *"Does this VM
   need to be reachable from the public internet, or should we keep it private?
   Keeping it private is our default security best practice—even for websites,
   please confirm which you prefer."*)

### 3. Clear Cost, Quota & Resource Availability Guidance

- Warn clearly before provisioning **Powerhouse**, **GPU**, or **Bare Metal**
  instances that specialized hardware and large `pd-ssd` / Hyperdisk volumes
  accumulate costs quickly (disks bill continuously while stopped) and require
  sufficient regional CPU/GPU quota.
- If VM provisioning fails with `ZONE_RESOURCE_POOL_EXHAUSTED` (or
  `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`), explain that this is a physical
  zonal hardware supply shortage that **a project quota increase will not fix**.
  Consult
  [Troubleshoot resource availability errors](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability.md.txt)
  and guide the user to try another zone in the region (e.g., `us-central1-b` or
  `us-central1-c`), adjust machine series/size, or use Compute Engine
  reservations.

---

## Best Practices & Hardening Rules

### Security & Networking

1. **Private-by-Default (`--no-address`)**: Default to `--no-address` on custom
   or verified `--subnet={subnet}` subnets, using Cloud NAT for outbound egress
   and Identity-Aware Proxy (IAP) TCP forwarding (`35.235.240.0/20`, TCP `22` /
   `3389`, `roles/iap.tunnelResourceAccessor`; see
   [Use IAP for TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding.md.txt))
   for SSH/RDP.
2. **OS Login (`--metadata=enable-oslogin=TRUE`)**: Enable OS Login so SSH
   access is tied to IAM roles rather than project-wide static SSH keys.
3. **Custom Service Accounts**: Never use the default Compute Engine service
   account; attach `{custom_service_account}` with least-privilege IAM roles.
4. **Shielded VMs**: Enable `--shielded-secure-boot`, `--shielded-vtpm`, and
   `--shielded-integrity-monitoring` on all virtualized VMs (omit vTPM/integrity
   and set `--no-shielded-secure-boot` on standard x86 `-metal` bare metal).

### Cost Optimization & Reliability

1. **Right-Sizing & Free Tier Accuracy**: Use `e2-micro` (`us-west1`,
   `us-central1`, or `us-east1` only, 1 non-preemptible instance/month, up to
   30 GB `pd-standard`, with an active billing account still required on the
   Google Cloud project; see
   [Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features.md.txt))
   for Free Tier eligibility, or `e2-medium` for light dev/test workloads.
2. **Spot VMs**: Offer Spot VMs (`--provisioning-model=SPOT`,
   `--instance-termination-action=DELETE` [or `STOP`],
   `--maintenance-policy=TERMINATE`, `--no-restart-on-failure`; see
   [Create and use Spot VMs](https://docs.cloud.google.com/compute/docs/instances/create-use-spot.md.txt))
   for stateless, fault-tolerant batch workloads to achieve significant
   discounts compared to standard instances (see
   [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)).
3. **Storage & Host Maintenance**: Default 3rd-gen/E2 boot disks to
   `pd-balanced` (`hyperdisk-balanced` on 4th-gen and `-metal`), and set
   `--maintenance-policy=MIGRATE` on standard virtualized VMs (`TERMINATE` on
   Spot, GPU, and `-metal` instances; see
   [Handle GPU host maintenance events](https://docs.cloud.google.com/compute/docs/gpus/gpu-host-maintenance.md.txt)).

---

## Technical Reference Templates

Every row below summarizes the complete `gcloud compute instances create` flags
(with `{vm_name}`, `--project={project_id}`, and `--zone={zone}`) and 8-field
Compute Engine MCP `create_instance` schema for the five standard VM templates.
Consult [Technical Reference Templates](references/templates.md) when full
multi-line examples or additional template context are needed, and always read
[Usage Attribution](references/attribution.md) before executing any live
`gcloud`, REST API, or MCP command:

| **Template** | **Complete `gcloud compute instances create {vm_name} --project={project_id} --zone={zone}` Flags** | **MCP `create_instance` Routing & Schema** | **Required Warnings** |
| --- | --- | --- | --- |
| **1. Golden Path General Purpose (Production)** | `--machine-type=e2-standard-2 --network-tier=PREMIUM --subnet={subnet} --no-address --maintenance-policy=MIGRATE --metadata=enable-oslogin=TRUE --service-account={custom_service_account} --scopes=https://www.googleapis.com/auth/cloud-platform --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-12,mode=rw,size=30,type=projects/{project_id}/zones/{zone}/diskTypes/pd-balanced --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring --reservation-affinity=any` | 7-field JSON (`project`, `zone`, `name`, `"machineType": "e2-standard-2"`, `"imageProject": "debian-cloud"`, `"imageFamily": "debian-12"`, `"maintenancePolicy": "MIGRATE"`) is for default-VPC prototyping only; route hardened (`--no-address`, custom subnet/SA) deploys to `gcloud`. | Recommend Cloud NAT for egress and IAP TCP forwarding (`35.235.240.0/20`, `roles/iap.tunnelResourceAccessor`) for SSH/RDP; never use the default Compute Engine service account; omit `--quiet`. |
| **2. Developer Dev/Test VM (Cost-Optimized Spot)** | `--machine-type=e2-medium --subnet={subnet} --no-address --metadata=enable-oslogin=TRUE --service-account={custom_service_account} --scopes=https://www.googleapis.com/auth/cloud-platform --provisioning-model=SPOT --instance-termination-action=DELETE --maintenance-policy=TERMINATE --no-restart-on-failure --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-12,mode=rw,size=20,type=projects/{project_id}/zones/{zone}/diskTypes/pd-standard --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring` | **CLI/REST only**—Compute Engine MCP `create_instance` does not support Spot scheduling (`--provisioning-model=SPOT`, `--instance-termination-action`), `--no-address`, or custom subnets/service accounts. | Warn that Spot VMs can be preempted at any time (for stateless workloads only); use `DELETE` or `STOP` (never `TERMINATE`) on `--instance-termination-action`; include teardown command without `--quiet`. |
| **3. High-Performance General Purpose & Compute-Heavy** | **3rd-gen (`c3-standard-4` / `n2-standard-4`)**: `--machine-type=c3-standard-4 --subnet={subnet} --no-address --metadata=enable-oslogin=TRUE --service-account={custom_service_account} --scopes=https://www.googleapis.com/auth/cloud-platform --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-12,mode=rw,size=100,type=projects/{project_id}/zones/{zone}/diskTypes/pd-ssd --maintenance-policy=MIGRATE --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring` (for **4th-gen `c4-standard-4` / `n4-standard-4`**, replace `--subnet`/`--no-address` with `--network-interface=subnet={subnet},no-address,nic-type=GVNIC`, use `debian-13`, and use `hyperdisk-balanced`) | Default-VPC 3rd-gen prototyping only (`"machineType": "c3-standard-4"`); route custom-disk, 4th-gen Hyperdisk, and private-subnet deploys to `gcloud`. | Warn about continuous `pd-ssd`/Hyperdisk storage billing, 4th-gen Hyperdisk requirement (`pd-*` rejected on `C4`/`N4`/`C4A`), and accurate **Day-0 mutability** (disk shrink/type change uses snapshot + `detach-disk`/`attach-disk --boot` swap; stopped VMs rename via `gcloud compute instances set-name` and update subnet via `network-interfaces update`; VM recreation required for zone, CPU arch, or Encrypted-Memory VM). |
| **4. GPU Workstation (ML Inference)** | `--machine-type=g2-standard-4 --accelerator=type=nvidia-l4,count=1 --subnet={subnet} --no-address --metadata=enable-oslogin=TRUE --service-account={custom_service_account} --scopes=https://www.googleapis.com/auth/cloud-platform --maintenance-policy=TERMINATE --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/deeplearning-platform-release/global/images/family/common-cu129-ubuntu-2404-nvidia-580,mode=rw,size=100,type=projects/{project_id}/zones/{zone}/diskTypes/pd-balanced --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring` | 8-field JSON (`"project": "{project_id}"`, `"zone": "{zone}"`, `"name": "{vm_name}"`, `"machineType": "g2-standard-4"`, `"imageProject": "deeplearning-platform-release"`, `"imageFamily": "common-cu129-ubuntu-2404-nvidia-580"`, `"guestAccelerators": [{"acceleratorType": "nvidia-l4", "acceleratorCount": 1}]`, `"maintenancePolicy": "TERMINATE"`) is for default-VPC prototyping only; route hardened deploys to `gcloud`. | Warn about high GPU hourly costs, required regional GPU quota verification, and that GPU VMs **do not support live migration** (`--maintenance-policy=TERMINATE` is mandatory; never set `MIGRATE`). |
| **5. Bare Metal Instance (`-metal`)** | `--machine-type=c3-standard-192-metal --network-interface=subnet={subnet},no-address,nic-type=IDPF --maintenance-policy=TERMINATE --metadata=enable-oslogin=TRUE --service-account={custom_service_account} --scopes=https://www.googleapis.com/auth/cloud-platform --create-disk=auto-delete=yes,boot=yes,device-name={vm_name},image=projects/debian-cloud/global/images/family/debian-13,mode=rw,size=200,type=projects/{project_id}/zones/{zone}/diskTypes/hyperdisk-balanced --no-shielded-secure-boot` (never combine `--network-interface` with top-level `--subnet` or `--no-address`; omit `--shielded-vtpm`) | **CLI/REST only**—unsupported by Compute Engine MCP `create_instance`. | Warn about dedicated whole-host costs/quota, mandatory `hyperdisk-balanced` (`pd-*` and Windows unsupported), mandatory `debian-13` (`debian-12` unsupported on `C3-metal`, `C4-metal`, and `X4`), mandatory `nic-type=IDPF` (`GVNIC`/`VIRTIO_NET` unsupported), and no live migration. |

---

## Instructions & Guardrails

- **EARLY EXECUTION FORK & MCP BOUNDARY**: Never pass unsupported REST fields
  (`instance`, `disks`, `networkInterfaces`, `serviceAccounts`,
  `shieldedInstanceConfig`, `scheduling`) or prefixed machine URIs
  (`zones/{zone}/machineTypes/...`) to MCP `create_instance`, and always route
  hardened (`--no-address`, custom subnet, custom SA, Shielded VM, OS Login),
  Spot, custom-disk, 4th-gen, and `-metal` creations to
  `gcloud compute instances create`.
- **FAST CONVERSATIONAL INTAKE (NO SHELL COMMANDS ON MISSING INPUTS)**: When any
  mandatory input (**Project ID**, **VM name**, **region/zone**, or **public vs.
  private networking**) is missing from the user's prompt, ask for all missing
  inputs directly in your first reply (explaining regional latency benefits and
  recommending private networking) **without running `gcloud config list`,
  `gcloud --version`, or any shell discovery commands first**.
- **PUBLIC IP REMEDIATION CHECKLIST**: Whenever a user requests a public IP or
  direct internet SSH exposure:
  1. Warn clearly about public internet scanners and SSH/RDP brute-force risks.
  2. Recommend **both** **Identity-Aware Proxy (IAP) TCP forwarding**
     (`35.235.240.0/20`, `roles/iap.tunnelResourceAccessor`) for SSH/RDP **and**
     **Cloud NAT** for outbound internet access with `--no-address`.
  3. Include `--metadata=enable-oslogin=TRUE` and all three **Shielded VM**
     flags (`--shielded-secure-boot`, `--shielded-vtpm`,
     `--shielded-integrity-monitoring`) on virtualized VMs.
  4. Recommend a **custom, least-privilege service account** instead of the
     default Compute Engine service account.
- **ACCURATE DAY-0 MUTABILITY WARNINGS**: Explain accurately that:
  - **Disks**: Persistent Disks and Hyperdisks cannot shrink in-place, and
    changing disk type requires creating a new disk from a snapshot and swapping
    it on a stopped VM (`detach-disk` / `attach-disk --boot`) without
    recreating the VM instance.
  - **Networking & Renaming**: Stopped (`TERMINATED`) standalone IPv4 VMs can
    migrate VPC/subnet in-place (`gcloud compute instances network-interfaces
    update`; only NIC count `nic1+` is fixed at creation) and can be renamed
    in-place via `gcloud compute instances set-name` with `--new-name` and
    `--zone`
    (see [Rename a VM](https://docs.cloud.google.com/compute/docs/instances/rename-instance.md.txt)
    and [Update instance properties](https://docs.cloud.google.com/compute/docs/instances/update-instance-properties.md.txt)).
  - **True VM Recreation**: Properties requiring full **VM recreation** are
    **zone**, **CPU architecture** (`x86_64` vs. `ARM64`), and
    **Encrypted-Memory VM (AMD SEV-SNP or Intel TDX)** enablement.
- **4TH-GEN & BARE METAL HARDWARE CONSTRAINTS**: Never pair `pd-*` disks with
  4th-generation (`C4`, `N4`, `C4A`, `C4D`, `M4`, `X4`, `A4`, which require
  `hyperdisk-balanced` and `nic-type=GVNIC`; `N4` supports `hyperdisk-balanced`
  and `hyperdisk-throughput`, not `hyperdisk-extreme`) or bare metal (`-metal`)
  instances. Whenever recommending or generating a bare metal (`-metal`)
  configuration (`C3-metal`, `C4-metal`), **always explicitly state in your
  reply** that: (1) `pd-*` disks are unsupported (`hyperdisk-balanced` is
  mandatory), (2) `debian-13` is required because `debian-12` is unsupported on
  `C3-metal`, `C4-metal`, and `X4`, (3)
  `--network-interface=subnet={subnet},no-address,nic-type=IDPF` is required
  without conflicting top-level `--subnet` or `--no-address` flags (because
  `GVNIC` and `VIRTIO_NET` are unsupported on `-metal`), and (4)
  `--maintenance-policy=TERMINATE`, `--metadata=enable-oslogin=TRUE`, and
  `--no-shielded-secure-boot` (omitting `--shielded-vtpm`) are required.
- **MANDATORY GPU & SPECIALIZED HARDWARE WARNINGS**: Whenever recommending or
  generating a GPU (`G2`, `A3`, `A4`), bare metal (`-metal`), or
  high-performance VM configuration (including in `"Do not execute"` or MCP JSON
  comparisons), **always** explicitly include in your reply: (1) a warning about
  **high GPU or dedicated-host hourly compute costs**, (2) a reminder to
  **verify regional GPU/CPU quota** in the target project, and (3) that **GPU
  and bare metal instances do not support live migration**
  (`--maintenance-policy=TERMINATE` is mandatory).
- **HANDLE `ZONE_RESOURCE_POOL_EXHAUSTED`**: Explain that zonal capacity errors
  are physical hardware shortages (not fixable via quota increases) and guide
  users to alternate zones, alternate machine series, or reservations per
  [Troubleshoot resource availability errors](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability.md.txt).
- **FREE TIER ELIGIBILITY & BILLING ACCOUNT REQUIREMENT**: Whenever a user asks
  about Google Cloud Free Tier eligibility for Compute Engine, always explicitly
  state all four requirements in your reply: (1) only one non-preemptible
  `e2-micro` instance per month is covered (`e2-small` and larger are billed),
  (2) only in `us-west1`, `us-central1`, or `us-east1`, (3) up to 30 GB of
  `pd-standard` Standard Persistent Disk (`pd-balanced` and `pd-ssd` are
  billed), and (4) an **active billing account is still required on the Google
  Cloud project** even for Free Tier usage.
- **ALWAYS INCLUDE SAFE TEARDOWN COMMANDS**: Always provide
  `gcloud compute instances delete {vm_name} --zone={zone} --delete-disks=all`
  (omitting `--quiet` on all copy-pasteable manual `create` and `delete`
  commands) so users can prevent orphaned compute and disk charges safely.
- **MODE-AWARE CONFIRMATION**: Require explicit user confirmation before
  executing provisioning in **Automated Execution** mode; in **Manual / `"Do not
  execute"`** mode, prompt the user to review `{snake_case}` placeholders and
  flags before running the command themselves rather than offering to execute
  it.
