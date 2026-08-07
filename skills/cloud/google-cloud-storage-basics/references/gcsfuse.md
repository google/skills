# Cloud Storage FUSE (GCSFuse)

Cloud Storage FUSE (gcsfuse) is an open-source FUSE adapter that mounts Google
Cloud Storage (GCS) buckets as local file systems on Linux; Windows (including
Windows Subsystem for Linux) and macOS are not supported. It allows applications
to read and write objects using standard POSIX file system semantics (`open`,
`read`, `write`, `close`) without modifying application code or adopting Google
Cloud client libraries. It is heavily used in AI/ML training and serving (e.g.,
PyTorch, TensorFlow data loaders), data science notebooks, analytics pipelines,
and legacy applications.

Several behaviors below are version-dependent; check the installed version with
`gcsfuse --version`. This reference is current as of GCSFuse v3.10 (June 2026).

> [!IMPORTANT] **Not a General-Purpose POSIX File System:** Cloud Storage FUSE
> translates file operations into Cloud Storage REST API calls. It is optimized
> for high-throughput sequential reads and writes (such as loading model
> checkpoints or training datasets), but it does not support full POSIX
> compliance. Do not use it as a drop-in replacement for NFS or local block
> storage where random writes or file locking are required. For fully
> POSIX-compliant file system products in Google Cloud, see
> [Filestore](https://cloud.google.com/filestore/docs) or
> [Google Cloud Managed Lustre](https://cloud.google.com/managed-lustre/docs).

## Quick Start and Installation

> [!NOTE] You cannot use Google Cloud Shell to mount Cloud Storage buckets with
> Cloud Storage FUSE. Run commands on a local Linux machine, Compute Engine VM,
> or supported container environment.

### Managed Environments (Recommended)

In Google Cloud managed compute platforms, Cloud Storage FUSE is pre-integrated
and managed automatically:

*   **Google Kubernetes Engine (GKE):** Use the official
    [Cloud Storage FUSE CSI driver](https://cloud.google.com/kubernetes-engine/docs/concepts/cloud-storage-fuse-csi-driver)
    to mount buckets into Pods either via static `PersistentVolume` (PV) and
    `PersistentVolumeClaim` (PVC) specifications or directly as CSI ephemeral
    volumes.

    *   **GKE Volume Pod Annotation:** Even when using PV/PVC, the Pod
        annotation `gke-gcsfuse/volumes: "true"` is required.
    *   Example pod configuration annotations (Note that on GKE Standard
        clusters, setting a resource limit annotation automatically sets both
        the request and limit of the sidecar container to that same value):

        ```yaml
        metadata:
          annotations:
            gke-gcsfuse/volumes: "true"
            gke-gcsfuse/cpu-limit: "500m"                 # Optional (sets request & limit)
            gke-gcsfuse/memory-limit: "256Mi"             # Optional (sets request & limit)
            gke-gcsfuse/ephemeral-storage-limit: "10Gi"   # Optional (sets request & limit)
        ```

*   **Vertex AI & Cloud Run:** Direct volume mounting of Cloud Storage buckets
    is natively supported in container configurations.

### Manual Linux Installation (Debian / Ubuntu)

For custom Linux environments, install via the official Google Cloud APT
repository using modern keyring verification:

```bash
# 1. Install prerequisites
sudo apt-get update
sudo apt-get install -y curl lsb-release

# 2. Add the Cloud Storage FUSE distribution URI as a source
export GCSFUSE_REPO=gcsfuse-$(lsb_release -c -s)
echo "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt $GCSFUSE_REPO main" | sudo tee /etc/apt/sources.list.d/gcsfuse.list

# 3. Import the Google Cloud public key
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo tee /usr/share/keyrings/cloud.google.asc

# 4. Update package list and install gcsfuse
sudo apt-get update
sudo apt-get install -y gcsfuse
```

## Authentication

Cloud Storage FUSE uses Application Default Credentials (ADC). Authenticate
before mounting:

```bash
# For interactive development or user sessions:
gcloud auth application-default login
```

On Compute Engine VMs or GKE, ensure the attached IAM service account has the
necessary permissions.

*   `roles/storage.objectUser` (covers create, read, update, delete, and list
    for standard workloads).
*   `roles/storage.objectViewer` is the minimum role required to mount a bucket;
    it allows mounting, listing, and reading file contents, but **NOT**
    creating, updating, or deleting objects.

## Mounting and Unmounting

### Mounting Buckets

Create an empty local directory as a mount point and invoke `gcsfuse`:

```bash
# Create local mount directory
mkdir -p /mnt/gcs/my-bucket

# Mount bucket with implicit directory inference
gcsfuse --implicit-dirs my-bucket /mnt/gcs/my-bucket

# Mount a specific subdirectory prefix only (useful for multi-tenant buckets)
gcsfuse --only-dir=data/training --implicit-dirs my-bucket /mnt/gcs/my-bucket

# Mount read-only for shared static datasets; prevents accidental writes and
# pairs well with aggressive caching (see Caching Configuration)
gcsfuse -o ro --implicit-dirs my-bucket /mnt/gcs/my-bucket
```

### Static Mounting via `/etc/fstab`

To persist mounts across system reboots, add an entry to `/etc/fstab`. Before
using the `allow_other` mount option for non-root users, you must edit
`/etc/fuse.conf` and uncomment or add the `user_allow_other` directive.

```
# <file system>  <mount point>        <type>    <options>                                    <dump>  <pass>
my-bucket        /mnt/gcs/my-bucket   gcsfuse   rw,user,noauto,implicit_dirs,allow_other,uid=1001,gid=1001     0       0
```

> [!NOTE] The `noauto` option prevents boot hangs if network connectivity or ADC
> authentication is not ready during early system startup. If automated
> boot-time mounting is required, replace `noauto` with `_netdev` so the OS
> waits for network initialization before mounting.

> [!IMPORTANT] **Persistent Owner Mapping:** Static mounts executed at boot via
> `/etc/fstab` are run by the system as `root`. To ensure non-root applications
> can access files (even with `allow_other`), you must map ownership by
> including `uid` and `gid` in your fstab options (e.g. `uid=1001,gid=1001`).

### Unmounting

Unmount using standard Linux FUSE unmount utilities:

```bash
# Unmount safely (Linux)
fusermount -u /mnt/gcs/my-bucket

# Alternative root unmount command
sudo umount /mnt/gcs/my-bucket
```

> [!CAUTION] Never run `rm -rf` on an active mount point directory to clean it
> up or unmount it. Doing so will recursively delete all objects in the
> underlying Google Cloud Storage bucket! Always unmount first with `fusermount
> -u`.

## CRUD Operations (Bash & Python Equivalent)

Always use context managers in Python so file handles close deterministically
and uploads finalize on close:

Operation           | Bash Command Example                         | Python Equivalent                                                        | GCS API Mapping
:------------------ | :------------------------------------------- | :----------------------------------------------------------------------- | :--------------
**Create / Upload** | `echo "data" > /mnt/gcs/my-bucket/file.txt`  | `with open('/mnt/gcs/my-bucket/file.txt', 'w') as f: f.write('data\n')`  | Streams bytes directly to Cloud Storage by default in v3.0+; finalizes upload on close.
**Read / Download** | `cat /mnt/gcs/my-bucket/file.txt`            | `with open('/mnt/gcs/my-bucket/file.txt', 'r') as f: data = f.read()`    | Initiates GET object request; streams bytes or fetches from cache.
**Update / Append** | `echo "more" >> /mnt/gcs/my-bucket/file.txt` | `with open('/mnt/gcs/my-bucket/file.txt', 'a') as f: f.write('more\n')`  | Downloads existing object, appends locally (or uses server-side compose without downloading if file >= 2 MB), re-uploads upon close. Rapid Buckets instead append directly with no re-upload.
**Delete**          | `rm /mnt/gcs/my-bucket/file.txt`             | `import os; os.remove('/mnt/gcs/my-bucket/file.txt')`                    | Initiates DELETE object request.
**Create Folder**   | `mkdir -p /mnt/gcs/my-bucket/new-folder`     | `import os; os.makedirs('/mnt/gcs/my-bucket/new-folder', exist_ok=True)` | Creates a 0-byte marker object named `new-folder/` (flat namespace buckets) or calls native folder creation API (HNS buckets).

## POSIX Semantics & Limitations

AI agents and automated workflows must account for these architectural
differences before recommending or interacting with Cloud Storage FUSE:

*   **No POSIX File Locking:** Cloud Storage FUSE does not support advisory or
    mandatory file locking (`flock`, `fcntl`, `lockf`). Applications expecting
    POSIX locks across distributed workers will encounter race conditions.
*   **Streaming Writes & Finalization (`close` vs `fsync`):** By default in
    GCSFuse v3.0+ (`--enable-streaming-writes=true`), sequential writes to new
    files stream directly to GCS. Under streaming writes, calling `fsync()` does
    **not** finalize the object on GCS; data is finalized and made visible only
    when the file handle is closed (`close()`). For out-of-order appends or when
    streaming writes are disabled, GCSFuse reverts to legacy staging (buffering
    locally in `--temp-dir` and uploading/finalizing the full object on
    `fsync()` or `close()`). For high-frequency log streams, use Cloud Storage
    client libraries, Cloud Logging directly, or a
    [Rapid Bucket](high-performance-storage.md), where appended data is visible
    in real time.
*   **No Random Writes or Small Appends:** Because GCS objects are immutable,
    writing to the middle of an existing file or appending to files smaller than
    2 MB causes Cloud Storage FUSE to stage and re-upload the entire modified
    file upon file close (`close()` or `flush()`).
    *   **Exception (Append Optimization):** Appending content to the end of a
        file that is 2 MB or larger is optimized so that only the newly appended
        content is uploaded via object composition. This optimization does
        **not** apply to Rapid Buckets (which do not support compose); staged
        re-uploads there always rewrite the full object.
    *   **Exception (Rapid Buckets):** Objects in
        [Rapid Buckets](high-performance-storage.md) are natively appendable.
        Appends through a file handle opened in append mode (`O_APPEND`) to an
        unfinalized object stream directly to GCS with no staging or re-upload
        (`enable-rapid-appends`, default `true`). Random (out-of-order) writes
        still fall back to staged full re-uploads.
*   **Rename Atomicity & Hierarchical Namespace (HNS):** Renaming an individual
    file is an atomic `objects.move` operation by default (in both flat and HNS
    buckets; controlled by `enable-atomic-rename-object`, on by default).
    Renaming a *directory* in a standard flat-namespace bucket, however,
    requires moving every individual object under that prefix (an $O(N)$
    operation), which is non-atomic and slow for large folders. If your workload
    relies on directory renaming or atomic checkpoint rotation, use a bucket
    with **Hierarchical Namespace (HNS)** enabled. Note that while HNS directory
    renames are atomic metadata-only operations, they are executed as
    asynchronous long-running operations (LROs): the folders being renamed can
    still be read and listed during the rename, but write operations on them are
    blocked until the operation completes.
*   **First-Writer-Wins Concurrency (`ESTALE`):** Cloud Storage objects are
    immutable and replaced atomically. If two independent FUSE mounts open and
    modify the same file simultaneously, **first-writer-wins** semantics apply.
    The first mount to close/sync updates the object generation in GCS; when the
    second mount attempts to close/sync its edits, `gcsfuse` returns a
    `syscall.ESTALE` (Stale File Handle) error due to generation precondition
    mismatch (`if-generation-match`).
*   **Implicit Directories Syntax & HNS Redundancy:** GCS does not have native
    directories. Folders are simulated using object keys with trailing slashes
    (e.g., `logs/`). When accessing buckets populated by external tools (such as
    S3 CLI or older scripts) that did not create explicit 0-byte directory
    marker objects, you must mount with `--implicit-dirs` so GCSFuse can infer
    directories from object prefix paths. Note that `--implicit-dirs` adds
    `List` API overhead and is unnecessary if the target bucket has Hierarchical
    Namespace (HNS) enabled.
*   **Extended Attributes:** Not supported.
*   **chmod/chown:** Run without error but are **silently ignored**. Permissions
    must be set at mount time via `--file-mode`, `--dir-mode`, `--uid`, `--gid`.

### POSIX Operation to GCS Mapping

| POSIX Operation        | GCS Translation          | Performance & Cost       |
:                        :                          : Implications (Flat vs    :
:                        :                          : HNS)                     :
| :--------------------- | :----------------------- | :----------------------- |
| **Read (Sequential)**  | `GetObject` (range read) | Efficient, especially    |
:                        :                          : with caching enabled.    :
| **Write (New File)**   | `WriteObject`            | Default in v3.0+.        |
:                        : (Streaming)              : Uploads directly to GCS  :
:                        :                          : in chunks (uses ~96MB    :
:                        :                          : RAM). Falls back to      :
:                        :                          : local staging if limits  :
:                        :                          : exceeded.                :
| **Modify               | Rewrite / Append         | GCS objects are          |
: (Append/Edit)**        :                          : immutable. Standard      :
:                        :                          : edits trigger a full     :
:                        :                          : rewrite. Appends to      :
:                        :                          : files >= 2MB upload only :
:                        :                          : the appended content.    :
| **Rename File (Flat)** | Atomic Move              | Atomic move by default.  |
:                        : (`objects.move`), with   : Non-atomic copy+delete   :
:                        : copy+delete fallback     : is used only if atomic   :
:                        :                          : rename is disabled.      :
| **Rename File (HNS)**  | Atomic Move              | Atomic metadata-only     |
:                        : (`objects.move`)         : operation. Fast, does    :
:                        :                          : not copy data.           :
| **Rename Directory     | Disabled by default.     | Non-atomic. Renames each |
: (Flat)**               : Enabled via              : descendant individually; :
:                        : `--rename-dir-limit`.    : fails with `EMFILE` if   :
:                        : Batch per-object moves   : the directory has more   :
:                        :                          : descendants than the     :
:                        :                          : limit.                   :
| **Rename Directory     | Atomic Rename            | Atomic metadata-only     |
: (HNS)**                : (`folders.rename`)       : operation. Fast.         :
| **Hard Links**         | Not Supported            | Unsupported operation.   |

## Rapid Bucket Integration

Cloud Storage FUSE supports mounting
[Rapid Buckets](high-performance-storage.md) (zonal, high-performance object
storage designed for AI/ML and analytics workloads). Use version 3.7.2 or later.
Google Kubernetes Engine (GKE) environments require version `1.35.0-gke.3047001`
or later. When mounting a Rapid Bucket, GCSFuse utilizes several performance
optimizations:

*   **Optimized Read Path:** GCSFuse automatically utilizes an optimized read
    path that leverages the Linux kernel's read-ahead algorithm by default,
    enabling faster sequential data access and higher aggregate throughput.
    *   *Note on Caching:* The optimized read path is incompatible with GCSFuse
        file caching and buffered reads. By default, these features are disabled
        for Rapid Buckets. To use them, you must disable the kernel reader by
        setting `enable-kernel-reader: false` (a `file-system` config option not
        listed in the public config-file reference).
    *   *Note on non-GKE hosts:* Outside GKE, the optimized read path also
        requires manual kernel tuning with root access (e.g., increasing
        `read_ahead_kb` and the FUSE `max_background` and `congestion_threshold`
        limits) to reach full throughput.
*   **Native Appends & Real-Time Visibility:** Rapid Bucket objects are
    appendable, and GCSFuse uploads data to them in real time for **new files
    regardless of the mode they were opened in**, and for **existing
    (unfinalized) files when opened in append mode (`O_APPEND`)**. Flushed data
    is readable by other clients in real time — unlike standard buckets, where
    data becomes visible only when the file is closed. By default, closing a
    file does **not** finalize the object (`finalize-file-for-rapid: false`), so
    it remains appendable. Appendable objects accept only one writer at a time;
    a new writer preempts the existing stream.
*   **Streaming Persistence:** Object streams are kept open by default for zonal
    buckets, allowing efficient operations (such as reading a Parquet file's
    metadata and subsequent row data in a single stream) and reducing metadata
    round-trip latency.
    *   *Tip:* To maximize the benefits of streaming persistence, ensure your
        application maintains open file handles and reuses them for subsequent
        operations on the same object.

## Caching Configuration

Caching is essential to reduce latency and API cost (especially metadata
operations). Configure caching using a YAML configuration file or the equivalent
command-line flags — every config-file option has a corresponding flag (e.g.,
`file-cache: max-size-mb` ↔ `--file-cache-max-size-mb`).

### Caching Mechanisms

| Mechanism          | Purpose                         | Recommended For      |
| :----------------- | :------------------------------ | :------------------- |
| **File Cache**     | Caches object content locally   | AI/ML dataset        |
: (`file-cache`)     : on disk (`cache-dir`) to serve  : loading, multi-pass  :
:                    : repeated reads at local         : training epochs, and :
:                    : SSD/NVMe speeds.                : repeated query       :
:                    :                                 : workloads.           :
| **Metadata Cache** | Caches file stat attributes in  | Directory-heavy      |
: (`metadata-cache`) : memory to eliminate             : workloads with       :
:                    : high-latency RPCs during `ls`   : thousands of files.  :
:                    : and `stat` calls (enabled by    :                      :
:                    : default).                       :                      :
| **List Cache**     | Caches directory listing scans  | Workloads performing |
: (`file-system`)    : in kernel memory                : frequent directory   :
:                    : (`kernel-list-cache-ttl-secs`). : traversals.          :

Run GCSFuse with the config file:

```bash
gcsfuse --config-file=/path/to/config.yaml my-bucket /path/to/mount
```

### High-Performance Cache Config (Example)

Use this profile for read-heavy workloads (e.g., ML training) where data is
static during the mount.

```yaml
# Root-level configuration
cache-dir: /mnt/local-ssd/gcsfuse-cache # Point to high-performance media (e.g., Local SSD)
file-cache:
  # Enable local file caching
  max-size-mb: -1 # -1 for unlimited (constrained only by local disk)
  enable-parallel-downloads: true # Enabled by default; accelerates large file reads
  cache-file-for-range-read: true # Caches even if file is read in chunks
metadata-cache:
  # TTL for stat (metadata) cache
  # -1 means infinite TTL (perfect for static/read-only datasets)
  ttl-secs: -1
  stat-cache-max-size-mb: 34 # Default. Type cache merged into stat cache in v3.8.0; type-cache flags are no-ops
file-system:
  # Caches directory listings in the kernel
  kernel-list-cache-ttl-secs: -1
```

> [!WARNING] **Stale Data Risk:** Setting `ttl-secs` or
> `kernel-list-cache-ttl-secs` to `-1` or long durations means GCSFuse will not
> detect changes (metadata or file listings) made to the bucket outside of this
> mount. If the bucket is updated by other clients, users will see stale data or
> missing files.

## Documentation

*   [Cloud Storage FUSE overview](https://cloud.google.com/storage/docs/cloud-storage-fuse/overview)
*   [Install Cloud Storage FUSE](https://cloud.google.com/storage/docs/cloud-storage-fuse/install)
*   [Mount a bucket](https://cloud.google.com/storage/docs/cloud-storage-fuse/mount-bucket)
*   [Configuration file reference](https://cloud.google.com/storage/docs/cloud-storage-fuse/config-file)
*   [Caching](https://cloud.google.com/storage/docs/cloud-storage-fuse/caching)
*   [CSI driver for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/persistent-volumes/cloud-storage-fuse-csi-driver)
*   [Semantics and limitations](https://github.com/GoogleCloudPlatform/gcsfuse/blob/master/docs/semantics.md)
*   [GitHub Repository](https://github.com/GoogleCloudPlatform/gcsfuse)
