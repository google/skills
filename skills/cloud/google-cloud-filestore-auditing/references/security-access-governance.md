# Filestore Security & Access Governance Reference

This reference provides governance rules, security risk criteria, and
remediation guidance for Google Cloud Filestore access configurations.

--------------------------------------------------------------------------------

## Table of Contents

| Section | Line hints |
| :--- | :--- |
| [1. NFSv3 Access Control Overview](#1-nfsv3-access-control-overview) | Lines 24-42 |
| [2. Security Findings & Risk Classifications](#2-security-findings--risk-classifications) | Lines 45-87 |
| • [2.1 Overly Permissive Network Exposure (0.0.0.0/0)](#21-overly-permissive-network-exposure-00000) | Lines 47-60 |
| • [2.2 Missing Root Squashing (NO_ROOT_SQUASH)](#22-missing-root-squashing-no_root_squash) | Lines 62-75 |
| • [2.3 Default Open VPC Exports (No Explicit Rules)](#23-default-open-vpc-exports-no-explicit-rules) | Lines 77-87 |
| [3. Recommended Remediation Configurations](#3-recommended-remediation-configurations) | Lines 90-126 |
| • [Recommended JSON Configuration](#recommended-json-configuration) | Lines 92-109 |
| • [Remediation via gcloud CLI](#remediation-via-gcloud-cli) | Lines 111-126 |
| [4. IAM Governance & Least Privilege](#4-iam-governance--least-privilege) | Lines 129-141 |

--------------------------------------------------------------------------------

## 1. NFSv3 Access Control Overview

Google Cloud Filestore instances export file shares using Network File System
version 3 (NFSv3). Because NFSv3 relies on client-reported POSIX user IDs (UIDs)
and group IDs (GIDs) without cryptographic Kerberos authentication by default,
network-level export options are the primary line of defense.

Access permissions are configured on the file share via `nfsExportOptions`. Each
rule within `nfsExportOptions` defines:

-   **`ipRanges`**: A list of IPv4 or IPv6 CIDR blocks permitted to connect.
-   **`accessMode`**: Allowed access level (`READ_WRITE` or `READ_ONLY`).
-   **`squashMode`**: User ID mapping behavior (`NO_ROOT_SQUASH` or
    `ROOT_SQUASH`).
-   **`anonUid`**: The target POSIX UID when squashing root (default: `65534` /
    `nobody`).
-   **`anonGid`**: The target POSIX GID when squashing root (default: `65534` /
    `nogroup`).

--------------------------------------------------------------------------------

## 2. Security Findings & Risk Classifications

### 2.1 Overly Permissive Network Exposure (`0.0.0.0/0`)

-   **Condition**: An export rule contains `0.0.0.0/0`, `0.0.0.0`, or `::/0` in
    its `ipRanges`.
-   **Severity**:
    -   **`CRITICAL`** if `accessMode` is `READ_WRITE`.
    -   **`HIGH`** if `accessMode` is `READ_ONLY`.
-   **Risk**: Any host that can reach the Filestore IP (e.g., peered VPCs,
    shared transit networks, compromised VMs, or interconnects) can mount the
    file share.
-   **Remediation**: Replace `0.0.0.0/0` with explicit, minimal CIDRs
    corresponding to authorized VPC subnets, GKE node pools, or private consumer
    IP ranges.

### 2.2 Missing Root Squashing (`NO_ROOT_SQUASH`)

-   **Condition**: An export rule defines `squashMode: NO_ROOT_SQUASH`.
-   **Severity**:
    -   **`CRITICAL`** if paired with open network exposure (`0.0.0.0/0`) or
        public access.
    -   **`HIGH`** when restricted to internal VPC subnets.
-   **Risk**: Clients connecting with local `root` (UID 0) retain full superuser
    privileges on the Filestore share. Any compromised container or VM running
    as root can overwrite system binaries, read sensitive data, or alter
    security file modes across the entire share.
-   **Remediation**: Configure `squashMode: ROOT_SQUASH`. Clients connecting as
    root are automatically remapped to `anonUid: 65534` (`nobody`), enforcing
    least-privilege POSIX semantics.

### 2.3 Default Open VPC Exports (No Explicit Rules)

-   **Condition**: `nfsExportOptions` is empty or missing from the instance
    specification.
-   **Severity**: **`MEDIUM`**
-   **Risk**: By default in Google Cloud Console and the GCP API, instances
    without explicit export rules allow all compute instances in the connected
    VPC network to mount the share with **`NO_ROOT_SQUASH`** and
    **`READ_WRITE`** permissions.
-   **Remediation**: Add explicit `nfsExportOptions` to the instance
    specification under advanced access controls.

--------------------------------------------------------------------------------

## 3. Recommended Remediation Configurations

### Recommended JSON Configuration

```json
{
  "nfsExportOptions": [
    {
      "ipRanges": [
        "10.128.0.0/20"
      ],
      "accessMode": "READ_WRITE",
      "squashMode": "ROOT_SQUASH",
      "anonUid": 65534,
      "anonGid": 65534
    }
  ]
}
```

### Remediation via `gcloud` CLI

To update export options on an existing instance, provide the export
configuration via `--flags-file` or the direct flags:

```bash
gcloud filestore instances update [INSTANCE_ID] \
    --project=[PROJECT_ID] \
    --zone=[ZONE] \
    --file-share=name=[SHARE_NAME],nfs-export-options='[{"ip-ranges":["10.128.0.0/20"],"access-mode":"READ_WRITE","squash-mode":"ROOT_SQUASH"}]'
```

*(Note: Always prompt for user confirmation before executing modifications on
active file shares to avoid disrupting ongoing client mounts).*

--------------------------------------------------------------------------------

## 4. IAM Governance & Least Privilege

Filestore access control at the GCP project level is governed by Cloud IAM. The
principle of least privilege must be applied:

-   **`roles/file.admin`**: Full administrative control (create, modify, delete
    instances, backups, and snapshots). Restrict strictly to storage and
    platform administrators. Never grant to `allUsers` or
    `allAuthenticatedUsers`.
-   **`roles/file.editor`**: Can modify instances, trigger resizes, and
    create/restore backups.
-   **`roles/file.viewer`**: Read-only access to instance metadata, export
    rules, and backup statuses. Recommended role for audit runners.
