<!-- disableFinding(LINE_OVER_80) -->
<!-- disableFinding(LIST_NO_LINE) -->
<!-- disableFinding(LINK_ID) -->

# Cloud Logging & Audit Drift Queries for Google Cloud Filestore

This guide provides tested Cloud Logging query filters and schemas for
diagnosing Filestore mount issues, detecting administrative configuration drift,
and inspecting client-side mount errors.

## Table of Contents

*   [1. Filestore Administrative Audit Drift (Cloud Audit Logs)](#1-filestore-administrative-audit-drift-cloud-audit-logs):
    Lines 23-65
*   [2. GKE Filestore CSI Driver Mount Logs](#2-gke-filestore-csi-driver-mount-logs):
    Lines 68-103
*   [3. GCE VM Syslog & Serial Port Logs](#3-gce-vm-syslog--serial-port-logs):
    Lines 106-130
*   [4. Querying Across Agent Runtimes](#4-querying-across-agent-runtimes):
    Lines 133-153

--------------------------------------------------------------------------------

## 1. Filestore Administrative Audit Drift (Cloud Audit Logs)

When an existing, previously functioning Filestore mount suddenly begins failing
with `EACCES` or timeouts, query Cloud Audit Logs to determine if an
administrative change (configuration drift) modified the instance export options
or network settings within the last 24–48 hours.

### Query Filter:

```
logName="projects/{project_id}/logs/cloudaudit.googleapis.com%2Factivity"
AND protoPayload.serviceName="file.googleapis.com"
AND protoPayload.resourceName=~"instances/{instance_id}"
AND timestamp >= "{RFC3339_TIMESTAMP_24H_AGO}"
```

### CLI Command (`gcloud`):

```bash
gcloud logging read \
  'logName="projects/{project_id}/logs/cloudaudit.googleapis.com%2Factivity" AND protoPayload.serviceName="file.googleapis.com" AND protoPayload.resourceName=~".*{instance_id}.*"' \
  --project="{project_id}" \
  --freshness="1d" \
  --format="table(timestamp,protoPayload.methodName.basename(),protoPayload.authenticationInfo.principalEmail)"
```

> **Always scope to the Admin Activity log.** Dropping the `logName` filter also
> matches `cloudaudit.googleapis.com%2Fdata_access` entries, which record
> read-only `GetInstance` and `ListInstances` calls. Those reads are not
> configuration changes, and including them causes healthy instances to be
> reported as drifted — including reads issued by the diagnosis itself.

### Key Payload Fields to Extract:

*   `timestamp`: When the administrative change occurred.
*   `protoPayload.authenticationInfo.principalEmail`: User or service account
    that initiated the change.
*   `protoPayload.methodName`: e.g.
    `google.cloud.filestore.v1.Filestore.UpdateInstance` or `DeleteInstance`.
*   `protoPayload.request.updateMask`: Indicates which fields were changed (e.g.
    `fileShares` or `nfsExportOptions`).

--------------------------------------------------------------------------------

## 2. GKE Filestore CSI Driver Mount Logs

For GKE workloads utilizing the GCP Filestore CSI driver
(`filestore.csi.storage.gke.io`), mount failures are logged by the
`gcp-filestore-driver` container running in the `kube-system` namespace.

### Query Filter:

```
resource.type="k8s_container"
AND resource.labels.namespace_name="kube-system"
AND resource.labels.container_name="gcp-filestore-driver"
AND severity >= ERROR
AND timestamp >= "{RFC3339_TIMESTAMP_3H_AGO}"
```

### CLI Command (`gcloud`):

```bash
gcloud logging read \
  'resource.type="k8s_container" AND resource.labels.container_name="gcp-filestore-driver" AND severity>=ERROR' \
  --project="{project_id}" \
  --freshness="3h" \
  --limit=10 \
  --format="value(textPayload,jsonPayload.message)"
```

### Common CSI Error Messages:

*   `mount failed: exit status 32 ... mount.nfs: Connection timed out`:
    Indicates network/firewall blockage on port 2049.
*   `mount failed: exit status 32 ... mount.nfs: access denied by server while
    mounting`: Indicates export ACL rejection of the GKE worker node IP.
*   `RPC: Program not registered`: Port 111 (rpcbind) blocked.

--------------------------------------------------------------------------------

## 3. GCE VM Syslog & Serial Port Logs

For Compute Engine VMs failing to mount a Filestore volume:

### Query Filter:

```
resource.type="gce_instance"
AND logName=~"logs/syslog"
AND textPayload=~"mount\.nfs"
AND timestamp >= "{RFC3339_TIMESTAMP_6H_AGO}"
```

### CLI Command (`gcloud`):

```bash
gcloud logging read \
  'resource.type="gce_instance" AND textPayload=~"mount\.nfs"' \
  --project="{project_id}" \
  --freshness="6h" \
  --limit=5 \
  --format="value(timestamp,textPayload)"
```

--------------------------------------------------------------------------------

## 4. Querying Across Agent Runtimes

### Option A: Gemini Enterprise File Agent / Native GCP API Tool (`call_gcp_api`)

```json
{
  "service": "logging",
  "version": "v2",
  "resource_path": "entries:list",
  "request_body": {
    "resourceNames": ["projects/{project_id}"],
    "filter": "logName=\"projects/{project_id}/logs/cloudaudit.googleapis.com%2Factivity\" AND protoPayload.serviceName=\"file.googleapis.com\" AND protoPayload.resourceName=~\".*{instance_id}.*\"",
    "pageSize": 5
  }
}
```

### Option B: Cloud Logging MCP Tool

Call `read_log_entries` with `filter` and `project_id`.
