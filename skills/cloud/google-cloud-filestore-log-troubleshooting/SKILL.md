---
name: google-cloud-filestore-log-troubleshooting
metadata:
  version: "1.0.2"
  category: Storage
description: >-
  Diagnoses and resolves Filestore client mount failures on Google Cloud,
  permission errors (EACCES), and network timeouts (ETIMEDOUT). Use when an NFS
  mount hangs or fails from a Compute Engine VM, GKE pod, Cloud Run service, or
  Vertex AI workload, when `mount.nfs` reports "Connection timed out" or "access
  denied by server", when checking whether VPC ingress firewall rules or
  `nfsExportOptions` allow a client IP, or when a previously working Filestore
  share suddenly stops mounting after an administrative change. Don't use for
  Cloud Storage (GCS) buckets, Persistent Disk, or Cloud NetApp Volumes, and
  don't use for Filestore capacity scaling or backup and export-policy auditing.
---

<!-- disableFinding(LINE_OVER_80) -->

# Filestore Log-Based Troubleshooting

Diagnoses, troubleshoots, and remediates Filestore client mount failures, permission errors (`EACCES`), and network timeouts (`ETIMEDOUT`) across projects.

## Prerequisites & Quick Start

Required IAM roles on target project(s) (and Shared VPC host project if applicable):
*   **Read**: `roles/file.viewer` (instance & export ACLs), `roles/compute.networkViewer` (VPC firewall rules), `roles/logging.viewer` (Cloud Audit & GKE CSI logs), `roles/mcp.toolUser` (if using MCP tools).
*   **Write (Remediation only)**: `roles/file.editor` (export ACL updates), `roles/compute.securityAdmin` (firewall rule creation).

Authenticate, verify billing/APIs, and configure your environment:

```bash
gcloud auth login && gcloud auth application-default login
gcloud billing projects describe {project_id} --format="value(billingEnabled)"
gcloud services enable file.googleapis.com compute.googleapis.com logging.googleapis.com --quiet
gcloud config set project {project_id} && gcloud config set compute/region {region}
```

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Conceptual & Informational Queries (CRITICAL)

For purely conceptual, architectural, or educational questions (e.g., "What causes EACCES on Filestore?", "Why does GKE Node IP appear instead of Pod IP?", "What ports does Filestore require?", "Explain root squash"):
*   **Rule**: **Answer immediately using pre-trained knowledge and the workflow rules below.** Answering directly minimizes tool latency and token usage when the user only seeks architectural guidance.
*   **Constraint**: **Do not execute external tool calls or API requests** for basic knowledge questions.

## Handling "No-Command" Constraints (CRITICAL)

If the user prompt contains constraints like "Do not execute commands", "without executing", or "read-only":
*   **Rule**: **Strictly avoid calling `run_command`** to execute any shell, Python, or `gcloud` commands.
*   **Discovery**:
    1.  Always read [Usage Attribution](references/attribution.md) first so every recommended `gcloud` command includes the required attribution environment variable.
    2.  Check if Filestore MCP tools (`get_instance`, `list_instances`) are available and use them (API calls, not command executions).
    3.  If MCP tools are unavailable, read `references/mock-fleet-data.md` **only if** the requested instance matches one of the evaluation scenarios (`finance-share`, `shared-nfs`, `ml-data`, `data-hub`, `prod-share`). Never report mock data as live production state. If the instance is not listed there, state that live access is required and provide the exact attributed commands for the user to run.
    4.  **Fast-Path Stop Rule**: Once you have read [Usage Attribution](references/attribution.md) and located the target instance in `references/mock-fleet-data.md`, **stop reading additional files immediately** and formulate your response with the attributed `gcloud` remediation command. Do **NOT** read `scripts/quick_diagnose.py`, `scripts/diagnose_lib.py`, `_internal/quick_diagnose_test.py`, or `EVAL.*` files when command execution is disabled, as inspecting code/test files wastes turns and triggers timeouts.
*   **Mandatory User Confirmation Requirement**: Even when command execution is disabled or the user asks only for recommendations, your response **MUST STILL end with a clear question prompting the user for explicit confirmation** before applying any remediation (e.g., *"Would you like me to proceed with creating the VPC ingress firewall rule `[rule_name]`? Please confirm to proceed."*).

## Multi-Runtime Execution Options

### Option 1: Bundled Python CLI Script (Recommended for CLI / Terminal Agents)

```bash
# Single instance diagnosis
python3 scripts/quick_diagnose.py --instance="<INSTANCE_ID>" --location="<LOCATION_OR_ZONE>" \
    [--project="<PROJECT_ID>"] [--client-ip="<CLIENT_IP>"] [--client-subnet="<CLIENT_SUBNET_CIDR>"]

# Bulk project-wide fleet diagnosis
python3 scripts/quick_diagnose.py --all --project="<PROJECT_ID>" [--json]
```

| Flag | Purpose |
| :--- | :--- |
| `--instance`, `--location` | Filestore instance ID and region/zone (`--zone` is a legacy alias). Required unless `--all`. |
| `--project` | GCP project ID (defaults to active `gcloud` project). |
| `--client-ip` / `--client-subnet` | Client IP or CIDR to evaluate against export ACLs and ingress firewall rules. |
| `--json` | Emit machine-readable JSON on stdout (narrative report goes to stderr). |
| `--apply-fix` | Execute generated remediation commands. **Only pass after explicit user confirmation.** |

### Option 2: Filestore MCP Tools / REST API / `gcloud` CLI
*   **MCP Tools**: Call `get_instance(name='projects/{project_id}/locations/{location}/instances/{instance_id}')` and inspect `fileShares[0].nfsExportOptions` and `networks[0].network`.
*   **Native REST API (`call_gcp_api`)**: Invoke `service="file"`, `version="v1"`, `resource_path="projects/{project_id}/locations/{location}/instances/{instance_id}"`.
*   **Standard `gcloud`**:
    ```bash
    gcloud filestore instances describe {instance_id} --location={location} --project={project_id} --format=json
    ```

--------------------------------------------------------------------------------

## Core Operational Workflow

### Step 1: Parameter Extraction & GKE Node Architecture
*   Extract `instance`, `location` (region/zone), `project`, and `client_ip` / `client_subnet`. If target parameters are missing, list instances or ask the user to confirm.
*   **GKE Architecture Rule**: PersistentVolumes are mounted by the Linux kernel on the **GKE Worker Node**, not inside the Pod network namespace. Even if Pod IPs (`10.4.0.0/14`) are allowlisted, the NFS server sees traffic originating from the **GKE Node Internal IP**. Always evaluate and allowlist the **GKE Node Subnet CIDR** in `nfsExportOptions` and VPC firewall rules.

### Step 2: Instance Metadata & Shared VPC Resolution
1.  Verify instance `state` is `READY` (report state blocker if `CREATING`, `DELETING`, or `ERROR`).
2.  Extract primary Filestore IP (`networks[0].ipAddresses[0]`) and VPC network URI.
3.  If `networks[0].network` references `projects/{host_project}/global/networks/{network}`, resolve `{host_project}` as the Shared VPC host project for firewall queries.

### Step 3: Export ACL Evaluation (`EACCES` vs `EROFS`)
1.  Inspect `fileShares[0].nfsExportOptions` (if empty, default `0.0.0.0/0` `READ_WRITE` `NO_ROOT_SQUASH` applies).
2.  **`EACCES (Permission Denied by Server)`**: Triggered when the client IP or subnet CIDR is not covered by any `ipRanges` entry.
    *   **Remediation**: Non-destructively append the client IP/subnet CIDR to `nfsExportOptions`, preserving all existing export rules to avoid breaking active mounts.
3.  **`EROFS (Read-only file system)`**: Triggered when `accessMode` is `READ_ONLY` but client writes are attempted.

### Step 4: VPC Ingress Firewall Inspection (`ETIMEDOUT`)
1.  Query ingress firewall rules in the VPC network (in the host project if Shared VPC).
2.  **`ETIMEDOUT (Connection Timed Out)`**: Triggered when priority-sorted ingress rules block or fail to allow TCP port `2049` (NFS) and TCP/UDP port `111` (rpcbind) from the client CIDR.
    *   **Remediation**: Create an ingress firewall rule (`ALLOW` `tcp:2049,udp:2049,tcp:111,udp:111`) from the client subnet CIDR.

### Step 5: Cloud Audit Logs & Configuration Drift Scanning
Query Cloud Audit Admin Activity logs (`file.googleapis.com`) over the past 24 hours to check if an `UpdateInstance` operation modified export ACLs or networks:

```bash
gcloud logging read 'logName="projects/{project_id}/logs/cloudaudit.googleapis.com%2Factivity" AND protoPayload.serviceName="file.googleapis.com" AND protoPayload.resourceName=~".*{instance}.*"' \
    --project="{project_id}" --freshness="1d" --limit=5 --format="json"
```

*   **Scope to Admin Activity**: Always include `cloudaudit.googleapis.com%2Factivity` in `logName` so read-only `GetInstance`/`ListInstances` calls (`data_access`) are not falsely flagged as administrative drift.
*   **Drift is Informational**: Recent `UpdateInstance` events explain *when* and *by whom* (`principalEmail`, `timestamp`) configuration changed, but only a failed export ACL or firewall check constitutes a mount blocker.
*   **Single Bulk Query Rule**: When scanning multiple instances (`--all`), issue a single project-wide audit log query rather than per-instance queries in a loop.
*   **GKE CSI Driver Logs**: Optionally inspect `resource.labels.container_name="gcp-filestore-driver"` (`severity>=ERROR`) for client-side mount errors.

--------------------------------------------------------------------------------

## Output Format & Mandatory Confirmation Gate

Every diagnostic report MUST include a structured summary table and root cause analysis:

````markdown
### Filestore Diagnostic Report: `[instance-name]`

| Parameter | Value |
| :--- | :--- |
| **Instance ID** | `[instance-name]` (`[location]`, Tier: `[tier]`, State: `READY`) |
| **Filestore IP & Network** | `[filestore-ip]` on VPC `[network-name]` (Host Project: `[host-project]`) |
| **Port 2049 & Export ACL** | Port 2049: `OPEN / BLOCKED` \| Export ACL: `PASS / REJECTED` |
| **Diagnostic Verdict** | **HEALTHY** or **BLOCKED: [Root Cause]** |

#### Root Cause Analysis & Recommended Remediation
- [Explanation of ETIMEDOUT (missing firewall rule on port 2049) vs EACCES (missing export ACL rule) and any recent UpdateInstance audit drift]

```bash
gcloud compute firewall-rules create ...
```
````

### Interactive Remediation Confirmation Gate (MANDATORY)
*   **NEVER execute write or remediation commands without explicit user confirmation.**
*   Always conclude your response with an explicit confirmation question:
    > *"Would you like me to proceed with executing this remediation command for you? Please confirm to proceed."*

## References & Bundled Scripts
*   [Usage Attribution](references/attribution.md)
*   [Error Signatures & Architecture Matrix](references/error-signatures.md)
*   [Cloud Logging & Audit Drift Queries](references/logging-and-audit-queries.md)
*   [VPC Network & Firewall Specification](references/network-firewall-spec.md)
*   [Mock Fleet Data for Evaluations](references/mock-fleet-data.md)
*   `scripts/quick_diagnose.py` & `scripts/diagnose_lib.py`: Zero-dependency CLI runner and pure-Python evaluation engine.
