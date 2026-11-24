# Performance & Cost Diagnosis

Telemetry-driven root-causing for "training through the mount is slow" and "the
Cloud Storage bill spiked after we mounted the bucket". The core insight: **the
default mount is coherency-tuned, not performance-tuned** — most regressions on
untuned mounts are the defaults doing exactly what they promise.

**Never hypothesize before reading telemetry.** If client metrics are not
enabled, enabling them is the first remediation step; while waiting for a
remount window, the server-side `storage.googleapis.com/api/request_count`
metric is always available and needs no mount change.

## The coherency-tuned defaults (the usual suspects)

Knob                                      | Default                  | Effect on a re-read workload
:---------------------------------------- | :----------------------- | :---------------------------
File cache (`cache-dir`)                  | Off                      | Every epoch re-downloads every byte.
`metadata-cache: ttl-secs`                | 60                       | All metadata re-fetched every minute.
`metadata-cache: stat-cache-max-size-mb`  | 34 (~20k files)          | Silently evicts on large file counts → constant re-stats.
`metadata-cache: negative-ttl-secs`       | 5                        | "Not found" results re-checked every 5 s.
List cache (`kernel-list-cache-ttl-secs`) | 0 (off)                  | Every `ls`/directory walk hits the API.
`implicit-dirs`                           | false (true in profiles) | When on (flat buckets), lookups issue extra List calls.

A ~5M-small-file dataset re-read each epoch against these defaults produces
exactly the classic symptom pair: throughput far below local disk, and an
operations-dominated bill.

## Step 1 — Establish telemetry

-   **GKE ≥ 1.37.2-gke.1467000:** `gcsfusecsi/volume/*` metrics (monitored
    resource `k8s_gcs_fuse_volume`) are in Cloud Monitoring by default — no
    action.
-   **GKE 1.33.0-gke.2248000 to < 1.37.2-gke.1467000:** `gcsfusecsi/*` metrics
    (monitored resource `k8s_pod`) are in Cloud Monitoring by default — no
    action.
-   **Self-managed mount → Cloud Monitoring:** Remount with
    `--cloud-metrics-export-interval-secs=60` (needs
    `roles/monitoring.metricWriter` on the mount's service account; native
    metrics are Preview).
-   **Self-managed mount → local scrape:** Remount with
    `--prometheus-port=9920`, then `curl -s localhost:9920/metrics`.
-   **No remount possible yet:** Server-side:
    `storage.googleapis.com/api/request_count` grouped by the `method` label.

```bash
# Self-managed: remount with metrics, reproduce the workload, then inspect
gcsfuse --prometheus-port=9920 BUCKET /mnt/data
curl -s localhost:9920/metrics | grep -E "file_cache_read_count|gcs_request_count|fs_ops_count"
```

Client metrics only accumulate from mount time — reproduce at least one epoch
(or a representative slice) after enabling before reading the numbers.

Also capture the effective mount configuration (the misconfig surface): the
running `gcsfuse` command line and `--config-file` contents on self-managed
hosts; on GKE, `kubectl get pv PV_NAME -o yaml` (check `spec.mountOptions` and
`spec.csi.volumeAttributes`) plus the pod's `gke-gcsfuse/*` annotations.

## Step 2 — Read the signals

Metric (Cloud Monitoring / Prometheus form)                                                | What it tells you
:----------------------------------------------------------------------------------------- | :----------------
`file_cache/read_count`, by `cache_hit` label (`file_cache_read_count{cache_hit="false"}`) | Cache hit rate — the headline signal.
`gcs/request_count` (`gcs_request_count`)                                                  | Requests actually sent to Cloud Storage.
`gcs/request_latencies`, `gcs/retry_count`                                                 | Per-request latency and retry pressure.
`fs/ops_count` by `fs_op` (`fs_ops_count{fs_op="LookUpInode"}`)                            | Operation mix the app drives (stat-heavy? list-heavy?).
`fs/ops_error_count` by `fs_error_category`                                                | Errors surfacing to the app.
Server-side `api/request_count` by `method` (e.g. `ReadObject`)                            | Request mix without any mount change; also the bridge to billing.

On GKE (≥ 1.33.0-gke.2248000), the same client metrics appear prefixed and
underscored in Cloud Monitoring according to your cluster version:

-   **GKE ≥ 1.37.2-gke.1467000:**
    -   **Monitored resource:** `k8s_gcs_fuse_volume`
    -   **Resource labels:** `project_id`, `location`, `cluster_name`,
        `namespace_name`, `pod_name`, `volume_name`, `bucket_name` (promotes
        `volume_name` and `bucket_name` to resource labels while retaining
        `pod_name`)
    -   **Metric prefix:** `kubernetes.io/gcsfusecsi/volume/`
    -   **File system latency metric:** `gcsfusecsi/volume/fs_ops_latencies`
    -   **Workload aggregation labels:** `k8s_controller_type` and
        `k8s_controller_name` metric labels — populated only for supported
        workload controllers (`deployment`, `replicaset`, `statefulset`,
        `daemonset`, `jobset`, `leaderworkerset`), and emitted as empty strings
        (`""`) for standalone Pods and unsupported controllers (such as
        standalone `Job`s)
    -   **Metric-specific labels:** `cache_hit` (`file_cache_read_count`,
        `file_cache_read_latencies`), `read_type` (`file_cache_read_count`,
        `file_cache_read_bytes_count`, `gcs_download_bytes_count`,
        `gcs_read_count`), `fs_op` (`fs_ops_count`, `fs_ops_error_count`,
        `fs_ops_latencies`), `fs_error_category` (`fs_ops_error_count`),
        `gcs_method` (`gcs_request_count`, `gcs_request_latencies`), and
        `io_method` (`gcs_reader_count`)
    -   **`pod_uid` label:** Removed from schema
    -   **Sample period and latency units:** `60 s` `sample_period` (up from
        `10 s` on `k8s_pod`), and `gcs_request_latencies` unit metadata changes
        from `ms` to `us` (`fs_ops_latencies` and `file_cache_read_latencies`
        remain in `us`)
-   **GKE 1.33.0-gke.2248000 to < 1.37.2-gke.1467000:**
    -   **Monitored resource:** `k8s_pod`
    -   **Resource labels:** `project_id`, `location`, `cluster_name`,
        `namespace_name`, `pod_name`
    -   **Metric prefix:** `kubernetes.io/gcsfusecsi/`
    -   **File system latency metric:** `gcsfusecsi/fs_ops_latencies`
    -   **`volume_name` and `bucket_name`:** Metric labels on `k8s_pod`
    -   **Metric-specific labels:** Same per-metric labels as
        `k8s_gcs_fuse_volume` (`cache_hit`, `read_type`, `fs_op`,
        `fs_error_category`, `gcs_method`, `io_method`)
    -   **Workload aggregation labels:** Not available
    -   **`pod_uid` label:** Metric label on `k8s_pod` (empty string `""` in ≥
        1.35.2-gke.1442000; per-Pod UID in earlier 1.33–1.35 builds)
    -   **Sample period and latency units:** `10 s` `sample_period`, with
        `gcs_request_latencies` unit metadata in `ms` (`fs_ops_latencies` and
        `file_cache_read_latencies` in `us`)

## Step 3 — Map the signature to the misconfiguration

Signature                                                                                              | Root cause                                                                                | Fix (exact keys)
:----------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------- | :---------------
`cache_hit="false"` on ~all reads; download volume ≈ dataset × epochs                                  | File cache off (no `cache-dir`) or undersized                                             | `cache-dir` + `file-cache: max-size-mb` sized to the dataset (`-1` = fill the cache dir). Parallel downloads auto-enable with the cache.
Stat/metadata-dominated request mix; `fs_ops_count` LookUpInode-heavy; slowness scales with file count | 60 s TTL expiring + 34 MiB stat cache (~20k entries) thrashing against a large file count | `metadata-cache: ttl-secs: -1` and `stat-cache-max-size-mb: -1` — **immutable data only**; budget ~1.5 GiB RAM per million files (~1,720 bytes/file). Scope with `only-dir` if only a subset of the bucket is needed.
List-dominated mix (`objects.list` / ListObjects methods); directory walks slow                        | List cache off; or `implicit-dirs` on a flat bucket adding List calls per lookup          | `file-system: kernel-list-cache-ttl-secs: -1` — **read-only mounts only**; prefer buckets with hierarchical namespace (HNS) enabled over `implicit-dirs`.
Sidecar OOMKilled (Exit 137) or severe CPU throttling during reads                                     | Sidecar memory or CPU limits set too low on GKE                                           | Leave limits unset (default "0" on GKE ≥ 1.29.1); or set memory limit > stat/file cache budget.

Attribution logic for the bill: no file cache → every epoch re-reads all objects
(`objects.get`, Class B, billed per operation); expiring metadata + evicting
stat cache → re-stats (`objects.get` metadata, Class B); list cache off /
implicit-dirs → repeated `objects.list` (Class A, ~12.5× the per-op price of
Class B on standard buckets). Deletes are free.

## Step 4 — Apply the fix

```yaml
# tuned.yaml - read-heavy, immutable dataset re-read across epochs
cache-dir: /mnt/local-ssd/gcsfuse-cache
file-cache:
  max-size-mb: -1              # or size to the dataset
metadata-cache:
  ttl-secs: -1                 # immutable data only
  stat-cache-max-size-mb: -1   # ~1.5 GiB RAM per 1M files
file-system:
  kernel-list-cache-ttl-secs: -1   # read-only mounts only
# only-dir: dataset/train      # optional: scope namespace on 10M+ object buckets
```

```bash
gcsfuse --config-file=tuned.yaml BUCKET /mnt/data
```

> [!WARNING]
>
> **Staleness trade-off:** `-1` TTLs mean this mount never sees changes made to
> the bucket by other clients. Apply only to data that is immutable for the life
> of the mount, and prefer mounting read-only (`-o ro`). If the bucket is
> mutable, size TTLs to the acceptable staleness window instead.

Config hygiene while editing: `metadata-cache: type-cache-max-size-mb` is a
no-op since v3.8.0 (type cache merged into stat cache) — delete it from any
config that still sets it. On GKE, apply the same keys as PV `mountOptions`
entries (`file-cache:max-size-mb:...` colon syntax) — see
[GKE Training Deployment](gke-training-deployment.md). On Rapid (zonal) buckets
the file cache and buffered reads are no-ops by default (the kernel read path
replaces them) — this runbook's cache fixes apply to standard buckets.

## Step 5 — Verify and state the expected billing delta

Re-run one epoch, then check:

-   `file_cache_read_count{cache_hit="true"}` ≈ 100% of reads from epoch 2
    onward (first epoch populates the cache).
-   `gcs/request_count` drops to roughly one GET per object per mount lifetime
    (plus the initial listing) instead of per epoch.
-   On the bill: the **Class B line** (`objects.get` — data reads and metadata
    stats) drops roughly in proportion to the former epoch count; the **Class A
    line** (`objects.list`) drops if list caching or HNS addressed a list-heavy
    signature. Confirm server-side with `api/request_count` by `method`
    before/after.

## Documentation

-   [Cloud Storage FUSE metrics](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/metrics.md.txt)
-   [Config file reference](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/config-file.md.txt)
-   [File caching](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/file-caching.md.txt)
-   [Performance tuning](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/performance.md.txt)
-   [Cloud Storage pricing (operation classes)](https://cloud.google.com/storage/pricing)
-   [Google Cloud metrics list (api/request_count)](https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z.md.txt)
