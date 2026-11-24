# GKE Training Deployment (Fit-Gated, Tuned Mount)

Provision a performance-tuned gcsfuse mount for training workloads whose code is
hardcoded to POSIX paths (run the SKILL.md fit gate first). GKE version gates
are noted inline.

## Decision table: pick the mount mechanism

Environment              | Mechanism
:----------------------- | :--------
GKE ≥ 1.35.1-gke.1616000 | PV/PVC on a pre-installed **profile StorageClass** (`gcsfusecsi-training`) — preferred; auto-tunes cache, media, and prefetch from node telemetry.
GKE < 1.35.1-gke.1616000 | Static PV/PVC with **explicit mount options replicating the profile** (see manifest B). Profiles are unavailable.
Compute Engine VM        | `gcsfuse --profile=aiml-training` with ADC from the attached service account.
Cloud Run                | Native Cloud Storage volume mounts (`--add-volume type=cloud-storage`).

**Never** pass `profile:aiml-*` as a mount option yourself on GKE: Cloud Storage
FUSE CSI volumes do not support the `profile` field or `--profile` option on any
volume type (ephemeral or PV/PVC). The pre-installed StorageClasses are the only
supported way to use profiles on GKE; on older clusters, set the profile's
individual options explicitly instead (manifest B).

**Never** use the legacy Workload Identity flow (Google service account +
`roles/iam.workloadIdentityUser` + `iam.gke.io/gcp-service-account` KSA
annotation). The current flow is a direct `principal://` IAM binding on the
bucket — no GSA, no JSON keys (step 2).

## Step 1 — Verify cluster gates

```bash
CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-fuse)" \
    gcloud container clusters describe CLUSTER --location=LOCATION \
    --format="value(currentMasterVersion, addonsConfig.gcsFuseCsiDriverConfig.enabled, workloadIdentityConfig.workloadPool)"
```

Requirements: `GcsFuseCsiDriver` addon enabled, a Workload Identity pool set,
and the cluster version against these gates:

-   **Volume-scoped gcsfuse metrics (`k8s_gcs_fuse_volume`,
    `gcsfusecsi/volume/*`):** ≥ 1.37.2-gke.1467000
-   **Profile StorageClasses (`gcsfusecsi-*`):** ≥ 1.35.1-gke.1616000
-   **Pod-scoped gcsfuse metrics (`k8s_pod`, `gcsfusecsi/*`):**
    1.33.0-gke.2248000 to < 1.37.2-gke.1467000
-   **`gcsfuseMetadataPrefetchOnMount`:** ≥ 1.32.1-gke.1357001

Check node cache media (drives step 4):

```bash
kubectl describe node NODE_NAME | grep "cloud.google.com/gke-ephemeral-storage-local-ssd"
```

## Step 2 — Authentication: direct principal:// binding

Grant the workload's Kubernetes ServiceAccount access on the bucket directly.
Use `roles/storage.objectViewer` for read-only training data;
`roles/storage.objectUser` if the workload also writes.

```bash
CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-fuse)" \
    gcloud storage buckets add-iam-policy-binding gs://BUCKET \
    --member="principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/NAMESPACE/sa/KSA_NAME" \
    --role="roles/storage.objectViewer"
```

The KSA itself is a plain ServiceAccount with no annotations (manifest A).

For **cross-project mounts** (GKE cluster in Project A, bucket in Project B):
GKE's storage profile controller attempts an upfront bucket scan using the GKE
control-plane service agent
(`service-PROJECT_A_NUM@container-engine-robot.iam.gserviceaccount.com`). To
prevent Pods getting stuck in `SchedulingGated`
(`gke-gcsfuse/bucket-scan-pending`) with `403 Forbidden`, either set
`skipCSIBucketAccessCheck: "true"` on the PV (Manifests A & B) to skip the
control-plane pre-scan, or grant `roles/storage.bucketViewer` and
`roles/storage.objectViewer` to the cluster's GKE service agent on Project B's
bucket. The Step 2 `principal://` binding likewise goes on the bucket in Project
B, not in the cluster project: the member string still references Project A's
Workload Identity pool (`PROJECT_NUMBER` and `PROJECT_ID` are the cluster
project's), but the IAM policy must be granted in the bucket-owning project.

## Step 3 — What the training profile does (and does not do)

The `gcsfusecsi-training` StorageClass layers two things:

-   **Client profile `aiml-training`** sets: `implicit-dirs`, `metadata-cache:
    negative-ttl-secs: 0`, `metadata-cache: ttl-secs: -1`, `metadata-cache:
    stat-cache-max-size-mb: -1`. It does **not** enable the file cache — no
    client profile does.
-   **GKE CSI automation** (StorageClass parameters) adds:
    `gcsfuseMetadataPrefetchOnMount: "true"`, `skipCSIBucketAccessCheck:
    "true"`, and dynamic file-cache sizing — the driver picks cache capacity and
    medium from node resources, bucket size, and sidecar limits
    (`fuseFileCacheMediumPriority:
    "gpu:ram|lssd,tpu:ram,general_purpose:ram|lssd"`, memory budget 0.7 of
    allocatable, ephemeral-storage budget 0.85). So on the profile path the file
    cache **is** auto-enabled and auto-sized — verify it actually engaged (step
    6), because the driver silently disables it when no medium has enough space.

List the pre-installed classes: `kubectl get sc -l gke-gcsfuse/profile=true`
(`gcsfusecsi-training`, `gcsfusecsi-checkpointing`, `gcsfusecsi-serving`).

To tune or customize mount options on the PV:

-   **Scope massive namespaces (10M+ files):** Add `mountOptions:
    ["only-dir=<subfolder>"]` (or config `only-dir: <subfolder>`) to restrict
    FUSE tracking to the active dataset partition (e.g. `train/`). This avoids
    populating stat cache entries for the full namespace (~1.5 GiB RAM per 1M
    files) and accelerates directory traversal.
-   **Override profile defaults:** Set `spec.mountOptions` or
    `spec.csi.volumeAttributes` on the PV. If you set `file-cache: max-size-mb`
    manually, dynamic sizing is overridden for that component and you must also
    configure a custom read cache volume (`gke-gcsfuse-cache`).

## Step 4 — File cache on the manual path (older clusters)

For multi-epoch training that re-reads the dataset, the file cache is the single
highest-impact knob; without the profile automation you must enable and size it
explicitly:

-   Size `file-cache: max-size-mb` (or the `fileCacheCapacity` volume attribute)
    to hold the working dataset.
-   Media, in order of preference: Local SSD (A3/GPU nodes with the
    `cloud.google.com/gke-ephemeral-storage-local-ssd: "true"` label; A3+ is set
    up automatically), RAM disk for TPU v6+ nodes, `pd-ssd`/ `pd-balanced`
    otherwise. Avoid the boot disk.
-   The cache lands on the sidecar's emptyDir by default, so the pod annotation
    `gke-gcsfuse/ephemeral-storage-limit` must exceed the cache capacity.

## Step 5 — Manifests

Every pod consuming a gcsfuse volume requires the sidecar-injection annotation
`gke-gcsfuse/volumes: "true"` — PV/PVC and ephemeral volumes alike.

**Sidecar sizing and resource limits:**

-   `gke-gcsfuse/ephemeral-storage-limit`: Must exceed the file cache capacity
    when using emptyDir.
-   `gke-gcsfuse/cpu-limit` and `gke-gcsfuse/memory-limit`: Leave unset (or
    `"0"`, the default on GKE ≥ 1.29.1-gke.1670000). Setting conservative CPU
    limits causes aggressive CFS throttling during multi-threaded prefetching;
    setting tight memory limits causes the sidecar to be OOMKilled (`ExitCode
    137`) when stat cache or streaming buffers fill. If limits are mandated,
    size memory well above the combined stat cache (~1.5 GiB / 1M files) and
    streaming block budget.

**Manifest A — KSA + profile-path PV/PVC (GKE ≥ 1.35.1-gke.1616000):**

```yaml
# ksa.yaml - no GSA annotation; access comes from the principal:// binding
apiVersion: v1
kind: ServiceAccount
metadata:
  name: KSA_NAME
  namespace: NAMESPACE
---
# pv.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: training-data-pv
spec:
  storageClassName: gcsfusecsi-training
  capacity:
    storage: 1Ti          # placeholder; not enforced for gcsfuse
  accessModes:
    - ReadOnlyMany
  mountOptions:
    - ro                  # training data is read-only for the pods
  csi:
    driver: gcsfuse.csi.storage.gke.io
    volumeHandle: BUCKET  # the bucket name
    volumeAttributes:
      skipCSIBucketAccessCheck: "true"  # prevents SchedulingGated 403 on cross-project mounts
---
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: training-data-pvc
  namespace: NAMESPACE
spec:
  storageClassName: gcsfusecsi-training
  volumeName: training-data-pv
  accessModes:
    - ReadOnlyMany
  resources:
    requests:
      storage: 1Ti
```

**Manifest B — older clusters: replicate the profile as explicit options.** Same
PV/PVC as above, but `storageClassName: ""` and:

```yaml
  mountOptions:
    - ro
    - implicit-dirs
    - metadata-cache:negative-ttl-secs:0
    - metadata-cache:ttl-secs:-1
    - metadata-cache:stat-cache-max-size-mb:-1
    - file-cache:max-size-mb:512000        # size to the dataset
    - file-cache:cache-file-for-range-read:true
    # - only-dir=data/train                # optional: scope namespace to save stat-cache RAM
  csi:
    driver: gcsfuse.csi.storage.gke.io
    volumeHandle: BUCKET
    volumeAttributes:
      gcsfuseMetadataPrefetchOnMount: "true"   # GKE ≥ 1.32.1-gke.1357001
      skipCSIBucketAccessCheck: "true"         # prevents SchedulingGated 403 on cross-project mounts
```

The infinite metadata TTL and unlimited stat cache assume the dataset is
immutable during training; budget ~1.5 GiB RAM per million files for the stat
cache.

**Manifest C — training Job:**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-job
  namespace: NAMESPACE
spec:
  template:
    metadata:
      annotations:
        gke-gcsfuse/volumes: "true"              # required for sidecar injection
        gke-gcsfuse/ephemeral-storage-limit: 600Gi   # > file cache capacity
        # gke-gcsfuse/cpu-limit: "0"             # default unlimited; do not set tight limits
        # gke-gcsfuse/memory-limit: "0"          # default unlimited; avoid OOMKill (Exit 137)
    spec:
      serviceAccountName: KSA_NAME
      nodeSelector:
        cloud.google.com/gke-ephemeral-storage-local-ssd: "true"
      containers:
        - name: trainer
          image: TRAINING_IMAGE
          volumeMounts:
            - name: training-data
              mountPath: /data
              readOnly: true
      volumes:
        - name: training-data
          persistentVolumeClaim:
            claimName: training-data-pvc
      restartPolicy: Never
```

## Step 6 — Apply and verify

```bash
kubectl apply -f ksa.yaml -f pv.yaml -f pvc.yaml -f training-job.yaml
kubectl exec POD -c trainer -- ls /data | head    # mount works, data visible
```

Then confirm the cache engaged and troubleshoot common blockers:

-   **`SchedulingGated` (`gke-gcsfuse/bucket-scan-pending`):** Upfront bucket
    access check failed (common on cross-project mounts). Fix by setting
    `skipCSIBucketAccessCheck: "true"` in `spec.csi.volumeAttributes` or
    granting `bucketViewer`/`objectViewer` to the cluster's GKE service agent.
-   **Sidecar OOMKilled (`ExitCode 137`) / CPU throttling:** Sidecar limits
    throttled prefetching or ran out of memory under stat/file cache load.
    Remove `gke-gcsfuse/cpu-limit` and `gke-gcsfuse/memory-limit` (or set
    `"0"`).
-   **Profile cache verification:** Check the `GCSFuseCSIRecommendation` log
    entry for the `decision` block (`fileCacheBytes`, `fileCacheMedium`); the
    warning "No suitable file cache medium found" means the cache was silently
    disabled — fix node media or sidecar limits.
-   **Cache hit rate (Cloud Monitoring):** Exported by default on GKE ≥
    1.33.0-gke.2248000 (disable via the `disableMetrics: "true"` volume
    attribute). After the first epoch, `cache_hit="true"` reads should approach
    100% from epoch 2 onward (see
    [Performance & Cost Diagnosis](performance-diagnosis.md) for the full metric
    map):
    -   **GKE ≥ 1.37.2-gke.1467000:** `gcsfusecsi/volume/file_cache_read_count`
        on monitored resource `k8s_gcs_fuse_volume`
    -   **GKE < 1.37.2-gke.1467000:** `gcsfusecsi/file_cache_read_count` on
        monitored resource `k8s_pod`

## Non-GKE variants

Environment    | Command
:------------- | :------
Compute Engine | `gcsfuse --profile=aiml-training --config-file=cache.yaml BUCKET /mnt/data` — profile works directly (≥ v3.4.0); still enable the file cache in the config file. ADC comes from the attached service account.
Cloud Run      | `gcloud run services update SERVICE --add-volume=name=data,type=cloud-storage,bucket=BUCKET --add-volume-mount=volume=data,mount-path=/data`

## Documentation

-   [GKE profiles for Cloud Storage FUSE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/persistent-volumes/gcsfuse-profiles.md.txt)
-   [CSI driver setup and Workload Identity](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-setup.md.txt)
-   [Static PV/PVC provisioning](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-pv.md.txt)
-   [Sidecar configuration](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-sidecar.md.txt)
-   [CSI performance tuning](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-perf.md.txt)
-   [Volume attributes reference](https://docs.cloud.google.com/kubernetes-engine/docs/reference/cloud-storage-fuse-csi-driver/volume-attr.md.txt)
-   [Profile-based configurations](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/profile-based-configurations.md.txt)
