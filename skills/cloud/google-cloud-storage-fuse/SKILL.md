---
name: google-cloud-storage-fuse
description: >-
  Mounts Cloud Storage buckets on Google Cloud as a POSIX file system with
  Cloud Storage FUSE (gcsfuse). Use when interacting with gcsfuse or Cloud
  Storage FUSE mounts: decide whether FUSE, native gs:// reads, or
  Filestore/Managed Lustre fits a workload, deploy tuned mounts on GKE,
  Compute Engine, or Cloud Run, enable and size file, stat, and list caches, tune
  mount flags (--implicit-dirs) or config files, apply workload profiles, keep
  ML checkpointing safe (rename atomicity, hierarchical namespace/HNS, close-time
  finalization, concurrent writers), or diagnose slow training, low throughput,
  or bill spikes with gcsfuse metrics. Covers mount semantics, gcsfuse CLI and
  configs, GKE gcsfuse CSI driver (Workload Identity principal:// bindings,
  profile StorageClasses, sidecar sizing), and Cloud Run volume mounts. Don't use
  for bucket administration without a mount (google-cloud-storage-basics) or
  POSIX shared file systems (Filestore, Managed Lustre; use gke-storage).
license: Apache-2.0
metadata:
  version: "1.0.4"
  publisher: google
  tags: "gcs, gcsfuse, fuse, mount, file-system"
  category: Storage
  support_tier: primary
---

# Cloud Storage FUSE

Cloud Storage FUSE is a POSIX file-system adapter over Cloud Storage on Google
Cloud, operated via the gcsfuse CLI tool. Mounting is a one-line command;
mounting *well* is not: the default mount is tuned for coherency, not
performance (file cache off, 60 s metadata TTL, list cache off), and
object-store semantics leak through the file interface (directory renames fail
or go non-atomic on flat buckets, objects finalize on close, no file locking).
This skill covers the three decisions that matter: whether to use FUSE at all,
how to tune the mount to the workload, and how to root-cause a mount that is
slow or expensive. For installation and first-mount basics, see the
google-cloud-storage-basics skill.

## Attribution

Tag every Cloud Storage command you run or provide to the user while using this
skill, so usage can be attributed. The tag identifies only the skill and its
version; it carries no user data.

-   Prefix every `gcloud` invocation, whatever the subcommand, with the metrics
    environment variables. Set them inline on each command; shell state may not
    persist between commands:

    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-fuse)" \
        gcloud <command> [flags]
    ```

    Do not use `gcloud config set` for this: it would persist beyond the current
    task and mislabel unrelated usage.

-   On direct HTTP calls to the Cloud Storage APIs (for example with `curl`),
    set this exact User-Agent header, verbatim — the collection pipeline parses
    the `gcs-skills/<version>` and `skill:<name>` tokens, so any rewording
    breaks attribution:

    ```
    User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-fuse)
    ```

## Step 1 — Fit Gate (always run this first)

**Never produce mount guidance before the fit gate.** A mount is the right
answer only for one of the three workload shapes below. If the workload's access
pattern is unknown, ask — one question about whether the reading code can take
`gs://` paths usually settles it.

Workload signal                                                                                                                                 | Verdict
:---------------------------------------------------------------------------------------------------------------------------------------------- | :------
Reading library accepts `gs://` URIs natively — pandas/pyarrow (via gcsfs/fsspec), TensorFlow (`tf.io.gfile`), or any fsspec/gcsfs-based loader | **Native reads, no mount.** Point the code at `gs://` paths and stop.
Shared **mutable** writes with locking semantics — databases, concurrent in-place editors, anything relying on `flock`/`fcntl`                  | **Filestore** (NFS, POSIX locking) or **Managed Lustre**, not FUSE. Stop.
Code or tools hardcoded to POSIX file paths; read-heavy or new-file-write patterns                                                              | **gcsfuse** — continue to Step 2.

Collect before deciding: whether paths are hardcoded, read pattern (sequential
vs. random, re-read frequency), write pattern (new files vs. edits vs. directory
renames). These same signals drive tuning later — record the answers.

## Step 2 — Route by intent

User intent (prompt shape)                                                               | Go to
:--------------------------------------------------------------------------------------- | :----
Provision: "mount my bucket for X", "get training data into my pods"                     | [GKE Training Deployment](references/gke-training-deployment.md)
Safety/semantics: "is this write pattern safe?", "can multiple writers share the mount?" | [Checkpoint & Write Safety](references/checkpoint-safety.md)
Regression: "training is slow", "the Cloud Storage bill spiked", "throughput dropped"    | [Performance & Cost Diagnosis](references/performance-diagnosis.md)

**Never diagnose a regression without telemetry.** If gcsfuse metrics are not
enabled on the mount, enabling them is the first remediation step — the
diagnosis reference starts there.

## Reference Directory

-   [GKE Training Deployment](references/gke-training-deployment.md): Fit-gated,
    performance-tuned mounts for training workloads — GKE CSI version gates,
    Workload Identity `principal://` IAM bindings, profile StorageClasses vs.
    static PVs, file cache sizing on Local SSD, sidecar resource annotations,
    complete KSA/PVC/Job manifests, and the Compute Engine and Cloud Run
    variants.

-   [Checkpoint & Write Safety](references/checkpoint-safety.md): Verdicts on
    write patterns — file vs. directory rename atomicity on flat vs.
    hierarchical namespace (HNS) buckets, close-vs-fsync finalization,
    concurrent-writer (`ESTALE`) semantics, streaming-write memory budgets, HNS
    migration, and the `aiml-checkpointing` profile.

-   [Performance & Cost Diagnosis](references/performance-diagnosis.md):
    Telemetry-first runbook for slow mounts and bill spikes — enabling and
    reading gcsfuse metrics, mapping cache-hit and request-mix signatures to
    misconfigurations, the coherency-tuned defaults, tuned config keys with
    their staleness caveats, and billing-line (Class A/B) attribution.
