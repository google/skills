---
name: google-cloud-filestore-nfs-browser
metadata:
  version: "1.0.2"
  category: Storage
description: >-
  Inspects, searches, and reads files and POSIX metadata on Filestore (NFS)
  instances on Google Cloud without local NFS client packages or root
  privileges. Use when browsing Filestore shares, searching files, reading
  remote logs, or inspecting file attributes; don't use for Cloud Storage
  buckets, Cloud NetApp Volumes, Persistent Disks, or modifying/deleting files.
---

# Filestore NFS File Browser

Enables autonomous agents and cloud engineers to inspect, search, and read files
located on Filestore (NFS) instances without needing local NFS
client packages (`nfs-common`), root privileges, or manual VPC network mounting.

## Quick Start

1.  Ensure `gcloud` is installed and authenticated. See
    [gcloud installation guide](https://cloud.google.com/sdk/docs/install) if
    needed.
2.  Enable essential APIs:

    ```bash
    gcloud services enable file.googleapis.com compute.googleapis.com run.googleapis.com --quiet
    ```
3.  Discover instances and choose an execution engine (see
    [Execution Engine Selection](#execution-engine-selection) below).
4.  Run inspection actions using the self-contained runner
    `scripts/nfs_browser.py` included within this skill package.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Conceptual & Informational Queries (CRITICAL)

For purely conceptual, educational, or architectural questions (e.g., "How do I
inspect files on Filestore?", "How to deploy the Serverless Cloud Run NFS
Bridge?", "Explain Cloud Run NFS volume mounts"):

*   **Rule**: **Answer immediately using your pre-trained knowledge and the
    documentation below.** Answering directly minimizes tool invocation latency
    and token consumption when the user only seeks architecture or workflow
    guidance.
*   **Constraint**: **Do not execute external tool calls or API requests** for
    basic knowledge questions.
*   **Bridge Deployment Explanations**: Always highlight that Cloud Run scales
    to zero with **$0 idle compute cost**, detail the `gcloud run deploy`
    command with `--add-volume` and `--vpc-egress=all-traffic`, and specify the
    required IAM permissions (`roles/run.invoker` for callers and
    `roles/run.admin` for deployers).

## Handling "No-Command" Constraints (CRITICAL)

If the user prompt contains constraints like "Do not execute commands", "don't
run any commands", "without executing", or "read-only":

*   **Rule**: **Strictly NEVER invoke the `run_command` tool** for any reason
    (do NOT run `gcloud`, `python3`, `ls`, or any local/remote shell command,
    including read-only directory listings or discovery checks).
*   **Discovery**:
    1.  Check if mock definitions or instance parameters are provided directly
        in the user's prompt, conversation history, or local documentation
        files.
    2.  Read [Usage Attribution](references/attribution.md), explain the
        required steps, output the exact terminal commands with proper
        attribution, and explain what the commands do.
    3.  Do not attempt to read or search `EVAL.*` configuration files during
        evaluations as access to eval suites is restricted.

## Execution Engine Selection

Filestore instances are accessible via private VPC IPs. Select the engine
matching your environment:

*   **Engine 1: Cloud Run Serverless Bridge (Primary)**: Use
    `--bridge-url={bridge_url}` for low-latency (sub-50ms) REST calls. Scales to
    zero ($0 idle cost). Requires `roles/run.invoker`. See
    [references/nfs-bridge-setup.md](references/nfs-bridge-setup.md).
*   **Engine 2: GCE Jump Host via IAP SSH (Fallback)**: Use
    `--jump-host-vm={vm_name}` when an existing VM in the VPC is available. Pass
    `--mount={mount_path}` (defaulting to `/mnt/filestore`) if the jump host
    uses a different mount path. Zero new deployment needed. Requires
    `roles/iap.tunnelResourceAccessor`. See
    [references/iap-jump-host.md](references/iap-jump-host.md).

For execution flows, architecture diagrams, and engine comparison, see
[references/architecture.md](references/architecture.md).

## Core Operational Workflow

### 1. Discovery & Instance Targeting

If the Filestore instance, location, or share name is not provided, list them
first to avoid querying or targeting unrelated projects in multi-project
environments:

```bash
gcloud filestore instances list --project={project_id}
```

*   **Always Include Instance, Project & Path**: Every `scripts/nfs_browser.py`
    command and written response MUST explicitly include
    `--project={project_id}`, `--instance={instance_id}`, and `--path={path}`,
    naming the target Filestore instance ID (`{instance_id}`), project
    (`{project_id}`), and path (`{path}`) explicitly in the explanation.
*   **Fast Fallback When Live Access or Engine Flag Is Unavailable**: If a
    `gcloud` check returns `PERMISSION_DENIED` or `NOT_FOUND`, or if neither
    `--bridge-url` nor `--jump-host-vm` is configured, stop retrying immediately
    (do NOT read `scripts/*.py` source files to debug flags) and provide the
    exact `scripts/nfs_browser.py` command with `--project={project_id}`,
    `--instance={instance_id}`, `--path={path}`, and `--bridge-url` /
    `--jump-host-vm` placeholders.

### 2. Directory Tree Exploration (`tree`)

Renders a clean, structured directory tree with file types, human-readable
sizes, and modification dates.

```bash
# List top-level folders with depth 1
python3 scripts/nfs_browser.py tree \
  --project={project_id} \
  --instance={instance_id} \
  --path=/ \
  --depth=1

# List subfolder recursively with depth 2 and pagination cap
python3 scripts/nfs_browser.py tree \
  --project={project_id} \
  --instance={instance_id} \
  --path=/backup/logs/ \
  --depth=2 \
  --max-entries=100
```

### 3. File Pattern & Content Grep (`search`)

Searches for filenames matching a glob pattern and/or searches text contents for
regex patterns.

```bash
# Search for all tar.gz backup archives
python3 scripts/nfs_browser.py search \
  --project={project_id} \
  --instance={instance_id} \
  --path=/backups/ \
  --pattern="*.tar.gz"

# Grep for error patterns inside log files
python3 scripts/nfs_browser.py search \
  --project={project_id} \
  --instance={instance_id} \
  --path=/app/logs/ \
  --pattern="*.log" \
  --grep="FATAL|Exception|OutOfMemory" \
  --max-results=25
```

### 4. Chunked File Reading (`read`)

Safely reads text file chunks to protect the LLM context window against token
blowup. Always default to a safe chunk size (e.g., `--head 50` or `--tail 50`)
when the user does not specify an explicit range. Unbounded reads are
automatically capped to a safe limit of 100 lines. Always explicitly explain
that chunked reading protects the LLM context window from overflow and token
exhaustion.

```bash
# Read the last 50 lines (tail) of a log file
python3 scripts/nfs_browser.py read \
  --project={project_id} \
  --instance={instance_id} \
  --path=/backup/logs/app.log \
  --tail=50

# Read lines 100 to 200 of a config file
python3 scripts/nfs_browser.py read \
  --project={project_id} \
  --instance={instance_id} \
  --path=/config/settings.yaml \
  --lines=100:200

# Read the first 30 lines (head)
python3 scripts/nfs_browser.py read \
  --project={project_id} \
  --instance={instance_id} \
  --path=/var/log/syslog \
  --head=30
```

### 5. File Metadata & Attribute Inspection (`stat`)

Inspects POSIX permissions (`0644`), UID/GID, byte sizes, and timestamps.

```bash
python3 scripts/nfs_browser.py stat \
  --project={project_id} \
  --instance={instance_id} \
  --path=/backup/database_dump.tar.gz
```

## Context Window & LLM Safety Rules

1.  **Strictly Read-Only Guarantee**: This skill is strictly read-only. It
    provides no write, edit, delete, or truncate capabilities.
2.  **Never Dump Entire Large Files**: Always request a slice (`--lines`), head
    (`--head 50`), or tail (`--tail 50`) and explicitly explain that chunked
    reading protects the LLM context window against token overflow and client
    timeouts.
3.  **Handle Pagination**: Tree listings are capped at 100 entries per response.
    When truncated, the tool outputs a clear `[TRUNCATED]` notice so the agent
    can target specific subpaths.
4.  **Binary Protection**: Non-text files (e.g. `.tar.gz`, `.iso`, `.so`,
    compiled binaries) are detected via null-byte and magic-byte inspection; raw
    binary output is suppressed and metadata is displayed instead to prevent
    context corruption with non-printable characters.
5.  See
    [references/token-safety-guardrails.md](references/token-safety-guardrails.md)
    for full token guardrail details.

## Expected Errors & Recovery Strategies

| Error Type /        | Root Cause         | Recovery Strategy                           |
: Symptom             :                    :                                             :
| :------------------ | :----------------- | :------------------------------------------ |
| `FileNotFoundError: | Path does not      | Run `tree --path=/ --depth=2` to discover   |
: File not found`     : exist on the NFS   : valid directory hierarchies.                :
:                     : export.            :                                             :
| `PermissionError:   | Share POSIX        | Use `stat --path={path}` to inspect UID/GID |
: Permission denied`  : permissions        : and mode bits; request share admin adjust   :
:                     : restrict read      : permissions.                                :
:                     : access.            :                                             :
| `HTTPException: 403 | Path parameter     | Use clean paths (e.g. `/logs/app.log`)      |
: Access denied\:     : contains `../` or  : anchored to the NFS mount root.             :
: path traversal`     : a symlink          :                                             :
:                     : attempting escape  :                                             :
:                     : outside mount      :                                             :
:                     : point.             :                                             :
| `Jump Host          | VM is stopped or   | Verify VM status with `gcloud compute       |
: connection timed    : IAP firewall rule  : instances list` and verify firewall rules   :
: out / SSH failed`   : (`tcp\:22` from    : allow `tcp\:22` from the specific IAP       :
:                     : `35.235.240.0/20`) : netblock `35.235.240.0/20` (e.g., `gcloud   :
:                     : is missing.        : compute firewall-rules list                 :
:                     :                    : --filter="sourceRanges\:35.235.240.0/20"`). :
| `Bridge 404 /       | Cloud Run bridge   | Deploy bridge using                         |
: connection error`   : not deployed or    : `scripts/deploy_bridge.sh` or fall back to  :
:                     : URL invalid.       : GCE IAP Jump Host via `--jump-host`.        :

## Reference Directory

For progressive disclosure of deeper topics, consult the `references/`
directory:

-   [Usage Attribution](references/attribution.md)
-   [Multi-Engine Architecture & Execution Flow](references/architecture.md)
-   [Serverless NFS Bridge Setup Guide](references/nfs-bridge-setup.md)
-   [GCE Jump Host IAP SSH Guide](references/iap-jump-host.md)
-   [Token Safety & Context Guardrails](references/token-safety-guardrails.md)
-   [Troubleshooting & Common Errors](references/troubleshooting.md)

## Bundled Scripts & Components

The skill package bundles the following scripts and service components:

-   `scripts/nfs_browser.py`: Main CLI entrypoint for browsing, searching,
    reading, and stating NFS exports.
-   `scripts/formatters.py`: Output formatters for human-readable terminal
    rendering and token-safe summaries.
-   `scripts/jump_host_engine.py`: Remote SSH jump host execution engine via
    Google Cloud IAP tunnel.
-   `scripts/nfs_browser_test.py`: Comprehensive unit test suite covering
    formatters, HTTP bridge, and SSH jump host engines.
-   `scripts/deploy_bridge.sh`: Automated Cloud Run deployment script for the
    Serverless NFS Bridge.
-   `scripts/bridge_server/main.py`: FastAPI Cloud Run server implementation for
    direct NFS mounts.
-   `scripts/bridge_server/Dockerfile`: Container definition for packaging the
    Serverless NFS Bridge.
-   `scripts/bridge_server/requirements.txt`: Python dependencies for the Cloud
    Run bridge service.
