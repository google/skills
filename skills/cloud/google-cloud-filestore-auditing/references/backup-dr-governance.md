# Filestore Disaster Recovery & Backup Governance Reference

This reference covers disaster recovery (DR) standards, backup architecture, SLA
thresholds, and remediation commands for Google Cloud Filestore.

--------------------------------------------------------------------------------

## Table of Contents

| Section | Line hints |
| :--- | :--- |
| [1. Filestore Backup Architecture](#1-filestore-backup-architecture) | Lines 29-43 |
| [2. Disaster Recovery Audit Checks & Thresholds](#2-disaster-recovery-audit-checks--thresholds) | Lines 45-65 |
| • [2.1 Unprotected Instances (Zero Backups)](#21-unprotected-instances-zero-backups) | Lines 47-55 |
| • [2.2 Stale Backups (Exceeded SLA Threshold)](#22-stale-backups-exceeded-sla-threshold) | Lines 57-65 |
| [3. Backup Discovery Across Multi-Runtime Interfaces](#3-backup-discovery-across-multi-runtime-interfaces) | Lines 68-95 |
| • [gcloud CLI](#gcloud-cli-project-wide-discovery) | Lines 70-82 |
| • [MCP Tool Discovery](#mcp-tool-discovery) | Lines 84-88 |
| • [Direct REST API](#direct-rest-api) | Lines 90-95 |
| [4. Matching Backups to Instances](#4-matching-backups-to-instances) | Lines 98-109 |
| [5. Automated Remediation Commands (Backup Creation)](#5-automated-remediation-commands-backup-creation) | Lines 111-169 |
| • [For Zonal Instances](#for-zonal-instances-basic_hdd-basic_ssd-zonal) | Lines 116-141 |
| • [For Regional / Multi-Zone Instances](#for-regional--multi-zone-instances-regional-enterprise) | Lines 143-155 |
| • [MCP create_backup Payload](#mcp-create_backup-payload) | Lines 157-169 |
| [6. Safety & User Confirmation Requirement](#6-safety--user-confirmation-requirement) | Lines 172-180 |

--------------------------------------------------------------------------------

## 1. Filestore Backup Architecture

A Filestore backup is a point-in-time snapshot of an instance file share that is
stored independently from the source Filestore instance cluster:

-   **Independent Failure Domain**: Backups are stored in Google Cloud regional
    storage facilities. If the source Filestore instance or its datacenter
    becomes unavailable, backups remain durable and accessible.
-   **Cross-Region Restoration**: Backups can be restored to a new Filestore
    instance in the same region or in a different region, enabling geographic
    disaster recovery.
-   **Incremental Storage**: Filestore backups share common storage blocks
    across successive backups of the same file share, minimizing storage costs.

--------------------------------------------------------------------------------

## 2. Disaster Recovery Audit Checks & Thresholds

### 2.1 Unprotected Instances (Zero Backups)

-   **Condition**: An instance has 0 backups in the project.
-   **Severity**: **`HIGH`**
-   **Impact**: Accidental volume deletion, ransomware encryption, or physical
    hardware catastrophe will cause unrecoverable data loss.
-   **Remediation**: Create an immediate baseline backup of the primary file
    share.

### 2.2 Stale Backups (Exceeded SLA Threshold)

-   **Condition**: The most recent backup for an instance is older than
    `stale_backup_days` (default: **7 days**).
-   **Severity**: **`MEDIUM`**
-   **Impact**: Violates Recovery Point Objective (RPO) guarantees. Data
    modified since the last backup cannot be restored.
-   **Remediation**: Trigger an ad-hoc backup and configure automated scheduled
    backups using Cloud Scheduler and Cloud Run or Cloud Functions.

--------------------------------------------------------------------------------

## 3. Backup Discovery Across Multi-Runtime Interfaces

### `gcloud` CLI (Project-Wide Discovery)

To discover all backups across all regions in a project, run `gcloud filestore
backups list` without regional restrictions:

```bash
gcloud filestore backups list --project="{project_id}" --format="json"
```

*(Critical: Do NOT pass `--location=-` to `gcloud filestore backups list`; this
flag is unsupported and causes command failure).*

### MCP Tool Discovery

```json
filestore.list_backups({"parent": "projects/{project_id}/locations/-"})
```

### Direct REST API

```
GET https://file.googleapis.com/v1/projects/{project_id}/locations/-/backups
```

--------------------------------------------------------------------------------

## 4. Matching Backups to Instances

Backups must be matched to instances using the full canonical resource URI
rather than short names to avoid cross-zone collisions:

-   **Canonical Instance URI**:
    `projects/{project_id}/locations/{location}/instances/{instance_name}`
-   **Source Instance Property in Backup**: Each backup resource returns
    `sourceInstance`. A backup belongs to an instance if:
    `backup.sourceInstance == instance.name`

--------------------------------------------------------------------------------

## 5. Automated Remediation Commands (Backup Creation)

When generating remediation commands for unprotected instances, determine the
correct location flags based on instance tier:

### For Zonal Instances (`BASIC_HDD`, `BASIC_SSD`, `ZONAL`)

Zonal instances require `--instance-zone`:

```bash
gcloud filestore backups create {instance_name}-backup-$(date +%Y%m%d) \
    --project={project_id} \
    --instance={instance_name} \
    --file-share={file_share_name} \
    --instance-zone={instance_zone} \
    --region={backup_region}
```

*Example*:

```bash
gcloud filestore backups create nfs-prod-backup-20260903 \
    --project=prod-storage \
    --instance=nfs-prod \
    --file-share=vol1 \
    --instance-zone=us-central1-b \
    --region=us-central1
```

### For Regional / Multi-Zone Instances (`REGIONAL`, `ENTERPRISE`)

Regional instances require `--instance-location`:

```bash
gcloud filestore backups create {instance_name}-backup-$(date +%Y%m%d) \
    --project={project_id} \
    --instance={instance_name} \
    --file-share={file_share_name} \
    --instance-location={instance_region} \
    --region={backup_region}
```

### MCP `create_backup` Payload

```json
{
  "parent": "projects/{project_id}/locations/{backup_region}",
  "backupId": "{instance_name}-backup-20260903",
  "backup": {
    "sourceInstance": "projects/{project_id}/locations/{instance_location}/instances/{instance_name}",
    "sourceFileShare": "{file_share_name}",
    "description": "Baseline DR backup generated by google-cloud-filestore-auditing"
  }
}
```

--------------------------------------------------------------------------------

## 6. Safety & User Confirmation Requirement

**MANDATORY GUARDRAIL**: The skill must never execute backup creation commands
without prior user confirmation. Present the dry-run command list and conclude
with an explicit prompt:

> *"Would you like me to proceed with creating baseline backups for the
> unprotected instances? Please confirm to execute."*
