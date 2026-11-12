---
name: google-cloud-filestore-auditing
metadata:
  version: "1.0.3"
  category: Storage
description: >-
  Audits Filestore instances on Google Cloud across projects for disaster
  recovery readiness (missing or stale backups), security access governance
  (overly permissive NFS export rules, 0.0.0.0/0 exposure, missing ROOT_SQUASH),
  and reliability compliance (Physical Zone Isolation PZI and Physical Zone
  Separation PZS). Use when assessing storage health posture, auditing NFS
  export permissions, identifying unprotected file shares, or validating zone
  failure domains. Don't use for Cloud Storage buckets, Persistent Disk, or
  NetApp Volumes.
---

# Filestore Auditing Skill

This skill enables autonomous agents to audit, evaluate, and report the disaster
recovery, security access governance, and architectural reliability posture of
Filestore fleets across Google Cloud projects.

## Prerequisites / IAM Requirements & Permissions

Before executing this skill, the runtime principal (user account or Service
Account) must possess the following IAM roles and granular permissions on the
target GCP project(s):

### 1. Audit Operations (Read-Only Assessment)

Requires the **`roles/file.viewer`** role, which provides:

-   **`file.instances.list`**: Enumerate Filestore instances across project
    locations.
-   **`file.instances.get`**: Inspect instance configuration, NFS export rules,
    IP ranges, squash mode, and PZI/PZS isolation status.
-   **`file.backups.list`**: Enumerate existing backups across regions.
-   **`file.backups.get`**: Inspect backup timestamps, source instance URIs, and
    status.

### 2. Remediation Operations (Backup Creation)

Requires the **`roles/file.editor`** (or `roles/file.admin`) role, which
provides:

-   **`file.backups.create`**: Create on-demand baseline backups for unprotected
    instances.
-   **`file.operations.get`**: Monitor long-running backup creation operations.

### 3. MCP Tool Invocation

If invoking capabilities via the Filestore MCP Server
(`file.googleapis.com/mcp`):

-   **`roles/mcp.toolUser`**: Required to execute MCP tools (`list_instances`,
    `get_instance`, `list_backups`, `get_backup`, `create_backup`).

### 4. Cloud Authentication Setup

Authenticate the runtime environment using the appropriate method for your execution context:

-   **CLI Execution (`gcloud`)**:
    ```bash
    gcloud auth login
    ```
-   **Application SDKs & Scripts**:
    ```bash
    gcloud auth application-default login
    ```
-   **Automated Services & Service Accounts**:
    ```bash
    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
    ```

### 5. Billing Account Attachment

-   **Active Billing Required**: The target GCP project must have an active Cloud Billing account attached. Filestore instances and backup operations require active billing. Verify billing status with:
    ```bash
    gcloud beta billing projects describe {project_id}
    ```

## Quick Start

1.  Ensure `gcloud` is installed. See
    [gcloud installation guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) if
    needed.
2.  Authenticate your environment:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
3.  Set the target project context and verify an active billing account is attached:

    ```bash
    gcloud config set project {project_id}
    gcloud beta billing projects describe {project_id}
    ```
4.  Configure a well-supported default region (e.g., `us-central1`). See official
    [region availability documentation](https://cloud.google.com/about/locations):

    ```bash
    gcloud config set compute/region us-central1
    ```
5.  Verify required service APIs are enabled:

    ```bash
    gcloud services enable file.googleapis.com --quiet
    ```
6.  Run fleet discovery and backup inventory (see "Discovery & Read Operations"
    below).
7.  Evaluate findings against the audit rules matrix and render the executive
    scorecard and inventory table.
8.  If unprotected instances are identified, present baseline backup creation
    commands and prompt the user for confirmation.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Conceptual & Informational Queries (CRITICAL)

For purely conceptual, educational, or architectural questions (e.g., *"What is
Physical Zone Isolation (PZI) in Filestore?"*, *"What is the difference between
PZI and PZS?"*, *"Why is NO_ROOT_SQUASH dangerous?"*, *"Explain Filestore backup
architecture"*):

-   **Rule**: Answer immediately in a single turn using pre-trained knowledge
    and the definitions in this `SKILL.md` file:
    -   **Physical Zone Isolation (`PZI` / `satisfiesPzi`)**: Ensures a zonal
        resource's physical hardware is confined to an isolated physical failure
        domain within a datacenter so localized hardware failures do not cross
        zones.
    -   **Physical Zone Separation (`PZS` / `satisfiesPzs`)**: Ensures
        multi-zone or regional primary and replica nodes are hosted in
        physically distinct, independent datacenter facilities so a
        facility-wide outage cannot affect both copies.
-   **Constraint**: **Do NOT call ANY tools whatsoever** (do NOT call
    `read_file` on `references/`, `run_command`, MCP tools, or API requests) for
    purely conceptual questions—respond directly right away.

## Handling "No-Command" Constraints & Evaluations (CRITICAL)

If the user prompt contains constraints like *"Do not execute commands"*,
*"without executing"*, or *"read-only"*:

-   **Rule**: **Strictly avoid calling the `run_command` tool** to execute any
    shell, python, or `gcloud` commands.
-   **Discovery Hierarchy**:
    1.  Always read [Usage Attribution](references/attribution.md) whenever
        outputting or recommending `gcloud` commands (such as backup creation
        or export remediation commands) so they include the required attribution
        prefix.
    2.  Check if Filestore MCP tools (`list_instances`, `list_backups`) are
        available and query them directly (these are API invocations, not shell
        command executions).
    3.  If MCP tools are not present or cannot connect, search local reference
        markdown files (specifically the mock fleet definitions in
        `references/zone-isolation-pzi-pzs.md`) for any mock instances or
        project details matching the request. (Do NOT attempt to read evaluation
        config files such as `EVAL.yaml` or `EVAL.txtpb` during evaluation runs
        as access is restricted and triggers anti-cheating timeouts).
    4.  If no data is available in context or mock references, explain the audit
        evaluation formulas and provide the attributed `gcloud` commands for
        manual terminal execution.
-   **Mandatory User Confirmation Requirement**: Even when the user prompt asks
    not to execute commands or asks only for audit recommendations, any response
    recommending backup remediation MUST STILL end with a clear confirmation
    prompt before execution (e.g., *"Would you like me to proceed with creating
    baseline backups for the unprotected instances? Please confirm to
    proceed."*).

--------------------------------------------------------------------------------

## Core Operational Workflow

### 1. Discovery & Read Operations

The agent must discover all Filestore instances and backups in the target
project.

-   **Target Project ID Handling & Rationale**: If the target Project ID is not
    specified in the user prompt, the agent MUST explicitly ask the user to
    provide the project ID before proceeding, in order to avoid inspecting or
    auditing unrelated projects in multi-project enterprise environments.

Choose the discovery method matching your runtime environment:

#### Option A: Filestore MCP Tools (Recommended when MCP is mounted)

1.  **Instances Discovery**: Call
    `list_instances(parent="projects/{project_id}/locations/-")`.
2.  **Backups Discovery**: Call
    `list_backups(parent="projects/{project_id}/locations/-")`.

#### Option B: `gcloud` CLI (Terminal / Coding Harnesses)

1.  **Instances Discovery**:

    ```bash
    gcloud filestore instances list --project="{project_id}" --format="json"
    ```
2.  **Backups Discovery**:

    ```bash
    gcloud filestore backups list --project="{project_id}" --format="json"
    ```

    *(Note: Do NOT pass `--location=-` to `gcloud filestore backups list`;
    omitting the flag queries all regions across the project automatically).*

#### Option C: GCP REST API (`call_gcp_api` in Gemini Enterprise File Agent / curl)

1.  **Instances**: `GET
    https://file.googleapis.com/v1/projects/{project_id}/locations/-/instances`
2.  **Backups**: `GET
    https://file.googleapis.com/v1/projects/{project_id}/locations/-/backups`

#### Option D: Standalone Script Runner

For environments with standard python3 execution enabled, the agent may invoke
the portable script: `python3 scripts/filestore_audit.py
--project="{project_id}" [--format=markdown|json]`

--------------------------------------------------------------------------------

### 2. Audit Evaluation & Vector Checks

For each discovered instance, evaluate three audit vectors:

#### Vector 1: Disaster Recovery & Backup Protection

-   Match backups to instances using full canonical resource URIs
    (`backup.sourceInstance == instance.name`).
-   **Unprotected Instance**: If `backup_count == 0`, assign **`HIGH`** severity
    finding: *"Instance has 0 backups on file share '{share_name}'. Disaster
    recovery is not configured."*
-   **Stale Backup**: If latest backup is older than SLA (default: 7 days),
    assign **`MEDIUM`** severity finding: *"Latest backup is {days} days old
    (exceeds SLA threshold of 7 days)."*
-   Refer to `references/backup-dr-governance.md` for backup retention and SLA
    rules.

#### Vector 2: Security & Access Governance

-   Inspect `fileShares[0].nfsExportOptions`:
    -   **Open Network Exposure**: If `0.0.0.0/0`, `0.0.0.0`, or `::/0` is
        present in `ipRanges`, assign **`CRITICAL`** severity (if `accessMode:
        READ_WRITE`) or **`HIGH`** severity (if `READ_ONLY`): *"Export rule
        exposes share to 0.0.0.0/0 with accessMode='{access_mode}'."*
    -   **Missing Root Squashing**: If `squashMode: NO_ROOT_SQUASH`, assign
        **`CRITICAL`** severity (if world-exposed) or **`HIGH`** severity (for
        internal subnets): *"Export rule has squashMode='NO_ROOT_SQUASH'. Remote
        root clients retain superuser UID 0 privileges."*
    -   **Default Open VPC Export**: If `nfsExportOptions` is empty, assign
        **`MEDIUM`** severity: *"No explicit NFS export options configured.
        Share defaults to open client access within VPC with NO_ROOT_SQUASH."*
-   Refer to `references/security-access-governance.md` for export option
    configurations.

#### Vector 3: Zone Isolation & Reliability Compliance

-   **Physical Zone Isolation (PZI)**: If `satisfiesPzi: false`, assign
    **`MEDIUM`** severity: *"Instance does not satisfy Physical Zone Isolation
    (PZI)."*
-   **Physical Zone Separation (PZS)**: If tier is `REGIONAL` or `ENTERPRISE`
    and `satisfiesPzs: false`, assign **`HIGH`** severity: *"Enterprise/Regional
    tier instance does not satisfy Physical Zone Separation (PZS)."*
-   **Performance Limits**: Extract `performanceLimits.maxWriteIops` and
    `performanceLimits.maxReadThroughputBps` (convert to MB/s).
-   Refer to `references/zone-isolation-pzi-pzs.md` for datacenter failure
    domain isolation standards.

--------------------------------------------------------------------------------

### 3. Executive Posture Scoring & Grading

Calculate fleet posture grade as defined in `references/audit-rules-matrix.md`:

-   **Grade F (🔴 CRITICAL RISK)**: $\ge 1$ `CRITICAL` findings.
-   **Grade C (🟠 ELEVATED RISK)**: 0 Critical, but $\ge 1$ `HIGH` findings.
-   **Grade B (🟡 MODERATE)**: 0 Critical/High, but $\ge 1$ `MEDIUM` findings.
-   **Grade A (🟢 HEALTHY)**: 0 findings across all vectors.

Calculate `Backup Protection Rate %`: $$\text{Protection Rate} =
\frac{\text{Total Instances} - \text{Unprotected Instances}}{\text{Total
Instances}} \times 100$$

--------------------------------------------------------------------------------

### 4. Required Output Format

**Every audit report response MUST include the following structured sections in
Markdown:**

#### 1. Executive Posture Scorecard

```markdown
## Executive Posture Scorecard: `{project_id}`

| Metric | Status | Details |
| :--- | :--- | :--- |
| **Overall Health Posture** | **[🔴 CRITICAL RISK / 🟠 ELEVATED RISK / 🟡 MODERATE / 🟢 HEALTHY]** | [Grade F / C / B / A] |
| **Instances Audited** | `[count]` | Total Filestore instances evaluated |
| **Backup Protection Rate** | **[pct]%** | `[protected]/[total]` instances have active backups |
| **Critical & High Security Findings** | `[crit] Critical, [high] High` | Open exports (0.0.0.0/0) or NO_ROOT_SQUASH |
| **PZI Isolation Compliance** | `[pzi_count]/[total]` | Physical Zone Isolation adherence |
```

#### 2. Priority Findings & Remediation Matrix

List findings ranked by severity (`CRITICAL` $\to$ `HIGH` $\to$ `MEDIUM` $\to$
`LOW`):

```markdown
## Priority Findings & Remediation Matrix

| Severity | Instance ID | Category | Finding Description | Remediation Plan |
| :--- | :--- | :--- | :--- | :--- |
| 🚨 **CRITICAL** | `[instance]` | Security | [Description] | [Remediation] |
| ⚠️ **HIGH** | `[instance]` | Disaster Recovery | [Description] | [Remediation] |
```

#### 3. Filestore Instance Inventory & Compliance Status

```markdown
## Filestore Instance Inventory & Compliance Status

| Instance ID | Location | Tier | Capacity | Reserved CIDR | Write IOPS | Throughput | PZI | PZS | Backups | Latest Backup |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[id]` | `[loc]` | `[tier]` | `[cap] GiB` | `[cidr]` | `[iops]` | `[tp] MB/s` | ✅ Yes / ❌ No | ✅ Yes / ❌ No / N/A | 🔴 0 / ✅ `[n]` | `[date]` |
```

#### 4. Automated Remediation & Mandatory Confirmation Gate

If any unprotected instances are discovered, display attributed backup creation
commands and conclude with an explicit confirmation request:

```bash
gcloud filestore backups create [INSTANCE]-backup-[DATE] \
    --project=[PROJECT_ID] \
    --instance=[INSTANCE] \
    --file-share=[SHARE] \
    [--instance-zone=[ZONE] | --instance-location=[REGION]] \
    --region=[BACKUP_REGION]
```

> **Confirmation Required**: Would you like me to proceed with creating baseline
> backups for the unprotected instances? Please confirm to proceed.

**CRITICAL RATIONALE**: Do NOT execute backup creation without explicit user
confirmation. Confirmation is strictly required before executing any mutation or
backup creation commands in order to prevent unintended operational disruption,
unwanted resource allocation, or unexpected backup storage billing.

--------------------------------------------------------------------------------

## Reference Directory

For progressive disclosure and deep architectural guidance, consult the
following references:

-   [Usage Attribution](references/attribution.md)
-   [Security & Access Governance](references/security-access-governance.md)
-   [Disaster Recovery & Backup Governance](references/backup-dr-governance.md)
-   [Zone Isolation (PZI) & Reliability (PZS)](references/zone-isolation-pzi-pzs.md)
-   [Audit Rules & Scoring Matrix](references/audit-rules-matrix.md)
-   [Standalone Python Audit Script](scripts/filestore_audit.py)
