---
name: gke-storage
description: >-
  Manages GKE storage, including PVCs, PersistentVolumes, and Filestore. Use
  when configuring GKE storage or creating PVCs. For GCS FUSE mounts, use
  google-cloud-storage-fuse. For diagnosing storage failures (volume attach/mount
  errors, disk performance/node storage pressure, or Cloud Storage FUSE OOM), use
  gke-storage-troubleshooting. Don't use for database
  administration or replication strategies outside volume provisioning context.
metadata:
  version: "1.0.4"
  category: Storage
---

# GKE Storage

> **Routing Note:** For Cloud Storage FUSE (`gcsfuse`) mounts or the GKE
> `gcsfuse.csi.storage.gke.io` CSI driver, use the `google-cloud-storage-fuse`
> skill.

This reference covers storage configuration for GKE clusters including
persistent disks, file storage, and cloud storage integration.

> **MCP Tools:** `apply_k8s_manifest`, `get_k8s_resource`,
> `describe_k8s_resource`, `get_cluster`

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:gke-storage)"`
and append `agent-skills/1.0 (skill:gke-storage)` to `User-Agent` headers.

## Golden Path Storage Defaults

The golden path Autopilot config enables these CSI drivers:

| Driver          | Golden Path       | Access Mode     | Use Case             |
| --------------- | ----------------- | --------------- | -------------------- |
| Compute Engine  | Enabled (default) | ReadWriteOnce   | Block storage for    |
: Persistent Disk :                   :                 : databases,           :
: CSI             :                   :                 : single-pod workloads :
| Google Cloud    | Enabled           | ReadWriteMany   | Shared NFS for       |
: Filestore CSI   :                   :                 : multi-pod access     :
| Cloud Storage   | Enabled           | ReadWriteMany / | Mount GCS buckets as |
: FUSE CSI        :                   : ReadOnlyMany    : volumes              :
| Managed Lustre  | Disabled (opt-in) | ReadWriteMany   | High-performance     |
: CSI             :                   :                 : parallel file system :
| Boot disk type  | `pd-balanced`     | N/A             | Node boot disks      |

## StorageClasses

### Default StorageClasses

GKE provides built-in StorageClasses:

StorageClass   | Disk Type             | Use Case
-------------- | --------------------- | ------------------------------
`standard-rwo` | `pd-balanced`         | Balanced persistent disk (default)
`premium-rwo`  | `pd-ssd`              | High IOPS, databases
`standard-rwx` | Filestore (Basic HDD) | Shared NFS
`premium-rwx`  | Filestore (Basic SSD) | Shared NFS, higher performance

### Custom StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-regional
provisioner: pd.csi.storage.gke.io
parameters:
  type: pd-ssd
  replication-type: regional-pd    # Replicate across 2 zones
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true         # Always enable for production
```

## PersistentVolumeClaims

### Block Storage (ReadWriteOnce)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: database-pvc
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: premium-rwo
  resources:
    requests:
      storage: 100Gi
```

### Shared File Storage (ReadWriteMany via Filestore)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-data
spec:
  accessModes:
  - ReadWriteMany
  storageClassName: standard-rwx
  resources:
    requests:
      storage: 1Ti    # Filestore minimum is 1 TiB for Basic tier
```

### GCS Bucket Mount (Cloud Storage FUSE)

Mount a GCS bucket as a volume without a PVC:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gcs-reader
  annotations:
    gke-gcsfuse/volumes: "true"
spec:
  containers:
  - name: reader
    image: busybox
    command: ["ls", "/data"]
    volumeMounts:
    - name: gcs-bucket
      mountPath: /data
  volumes:
  - name: gcs-bucket
    csi:
      driver: gcsfuse.csi.storage.gke.io
      readOnly: true
      volumeAttributes:
        bucketName: <BUCKET_NAME>
```

> Requires Workload Identity for the pod's service account to have
> `roles/storage.objectViewer` on the bucket.

## Volume Expansion

If `allowVolumeExpansion: true` is set on the StorageClass, resize by updating
the PVC:

```bash
# kubectl
kubectl patch pvc <PVC_NAME> -p '{"spec":{"resources":{"requests":{"storage":"200Gi"}}}}'
```

```
# MCP (preferred)
patch_k8s_resource(parent="...", resourceType="persistentvolumeclaim", name="<PVC_NAME>",
  patch='{"spec":{"resources":{"requests":{"storage":"200Gi"}}}}')
```

Kubernetes automatically resizes the filesystem.

## Stateful Storage & Capacity Constraints

When configuring storage for stateful workloads, keep the following capacity and scheduling constraints in mind:

*   **Existing zonal PVs pin the workload to a zone:** A Pod that uses an existing zonal PersistentVolume (for example, in `europe-north1-b`) can only run in that zone. The cluster autoscaler can't work around a capacity shortage by adding nodes in another zone; any fallback must be in the same zone.
*   **Use automated disk type selection and topology-aware scheduling for new workloads:** Use `volumeBindingMode: WaitForFirstConsumer` so the volume is created in the zone where the Pod lands. When a ComputeClass mixes machine generations (for example, C4/N4 priority with N2 fallback), configure the StorageClass for **automated disk type selection** (`parameters.type: dynamic` with `pd-type: pd-balanced`, `hyperdisk-type: hyperdisk-balanced`, `disk-type-preference: hyperdisk-type`, and `use-allowed-disk-topology: "true"`, GKE 1.35.3-gke.1290000+; or `use-allowed-disk-topology: "true"` on GKE 1.34.1-gke.2541000+) so the autoscaler only picks nodes that support the disk type and new volumes get a compatible disk type per node.
*   **Same-zone PD-type swaps rarely help:** Switching a same-zone fallback from `pd-ssd` to `pd-balanced` is unlikely to resolve a zonal capacity shortage, because both can be affected by the same zonal constraints. Prefer a fallback to a Hyperdisk-capable machine series (for example, C3 or N4) with `hyperdisk-balanced`.
*   **Check Hyperdisk quotas first:** Hyperdisk quotas (for example, `HDB-TOTAL-GB`, throughput, and IOPS) are separate from Persistent Disk quotas. Verify the regional limits before recommending a Hyperdisk Balanced fallback.

## Best Practices

1.  **Always enable volume expansion**: Set `allowVolumeExpansion: true` on all
    StorageClasses
2.  **Use regional PDs for production**: `replication-type: regional-pd`
    replicates across 2 zones for HA
3.  **Use `WaitForFirstConsumer`**: Ensures the PV is provisioned in the same
    zone as the pod
4.  **Choose the right disk type**: `pd-ssd` for databases, `pd-balanced`
    (golden path default) for general use, `pd-standard` for cold storage
5.  **Use Filestore for shared access**: When multiple pods need to read/write
    the same files
6.  **Use GCS FUSE for data pipelines**: Mount buckets directly for ML training
    data, logs, etc.
7.  **Back up PVCs**: Use Backup for GKE (see the `gke-backup-dr` skill) to
    protect persistent data
