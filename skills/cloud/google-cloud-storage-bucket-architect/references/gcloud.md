# gcloud Command Generation Guide

> [!IMPORTANT]
>
> **DO NOT EXECUTE THESE COMMANDS AUTOMATICALLY.** Present generated commands to
> the user for confirmation and execute them in Phase 3 only if explicit
> confirmation is granted by the user.

This guide translates a **Draft Bucket Creation Plan** (Phase 2) into
`gcloud storage` commands.

## Official Documentation References

*   [gcloud storage buckets create](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/create)
*   [gcloud storage buckets update](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/update)
*   [gcloud storage buckets add-iam-policy-binding](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/add-iam-policy-binding)
*   [gcloud storage objects update](https://cloud.google.com/sdk/gcloud/reference/storage/objects/update)
*   [gcloud storage cp](https://cloud.google.com/sdk/gcloud/reference/storage/cp)
*   [gcloud storage buckets notifications create](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/create)
*   [gcloud storage buckets anywhere-caches create](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/anywhere-caches/create)
*   [Create zonal buckets](https://cloud.google.com/storage/docs/rapid/create-zonal-buckets)
*   [Domain-named bucket verification](https://cloud.google.com/storage/docs/domain-name-verification)
*   [Host a static website](https://cloud.google.com/storage/docs/hosting-static-website)

--------------------------------------------------------------------------------

> [!CAUTION]
>
> **DO NOT HALLUCINATE GCLOUD FLAGS.** Ground all `gcloud storage` commands and
> flags strictly in the **Translation Mapping Table** and **Helper Configuration
> Templates** below—do **not** run `gcloud ... --help` or documentation searches
> for any feature already covered in this guide. Never guess or invent flag
> names (e.g., use `--versioning`, not `--enable-versioning`). Only if the user
> explicitly requests a specialized Cloud Storage CLI setting absent from the
> table below (and has not forbidden running commands), verify the exact flag
> via `--help` or the official documentation linked above before presenting it.

## Translation Mapping Table

Prefer combining supported creation flags into a single
`gcloud storage buckets create` command, and combining `update`-only settings
(labels, versioning, CORS, website config, usage logging, or retention lock)
into a single `gcloud storage buckets update` command.

Draft Plan Field / Setting         | gcloud CLI Flag / Subcommand           | Notes / Full Command Syntax
:--------------------------------- | :------------------------------------- | :--------------------------
**Attribution**                    | `CLOUDSDK_METRICS_ENVIRONMENT`         | **Required inline on EVERY `gcloud` command** (including auxiliary `gcloud` commands). ⚠️ **CRITICAL: See Note 1 below.**
**Bucket Name**                    | `gs://[bucket-name]`                   | Positional argument on `create` / `update`. Must be globally unique.
**Project**                        | `--project=[project-id]`               | Global flag specifying target project ID.
**Location**                       | `--location=[location]`                | Region (`us-central1`), multi-region/custom dual-region geo (`US`), or predefined dual-region (`nam4`). ⚠️ **See Note 2 below.**
**Placement**                      | `--placement=[placement]`              | ONLY for custom dual-region (`us-east1,us-west1` with `--location=US`) or zonal (`us-east1-b` with `--location=us-east1`). **NEVER** use with `nam4`/`eur4`/`asia1`. ⚠️ **See Note 2.**
**Replication Speed (RPO)**        | `--rpo=ASYNC_TURBO`                    | Optional. Enables 15-minute Turbo Replication on dual-region buckets.
**Storage Class**                  | `--default-storage-class=[class]`      | `STANDARD` (default; must not be set to another class with Autoclass), `NEARLINE`, `COLDLINE`, `ARCHIVE`, `RAPID` (required for zonal buckets).
**UBLA**                           | `--uniform-bucket-level-access`        | Always enable (`--uniform-bucket-level-access`).
**Public Access Prevention**       | `--[no-]public-access-prevention`      | Enforce (`--public-access-prevention`) by default; use `--no-public-access-prevention` only with clear use-case intent and explicit user consent.
**Soft Delete**                    | `--soft-delete-duration=[duration]`    | E.g., `7d` (default), `14d`. Set to `0` to disable (MUST be `0` for zonal `RAPID` buckets).
**Object Versioning**              | `update ... --versioning`              | **Cannot be set on `create`.** Apply via `gcloud storage buckets update gs://[b] --versioning` (or `--no-versioning`). Recommended fallback if Soft Delete is disabled.
**Encryption (CMEK)**              | `--default-encryption-key=[key-id]`    | Full KMS key path (`projects/[project]/locations/[loc]/keyRings/[ring]/cryptoKeys/[key]`). Omit for GMEK.
**Restrict Encryption (CSEK)**     | `--encryption-enforcement-file=[file]` | JSON file restricting CSEK on `create` or `update`. See **Helper Configuration Templates** below.
**Autoclass**                      | `--enable-autoclass`                   | Requires `STANDARD` storage class; incompatible with zonal buckets and OLM `SetStorageClass` rules (optional: `--autoclass-terminal-storage-class=ARCHIVE`).
**Hierarchical Namespace**         | `--enable-hierarchical-namespace`      | Boolean flag on `create`. Requires UBLA. Required for zonal `RAPID` buckets.
**Labels**                         | `update ... --update-labels=[k=v,...]` | **Cannot be set on `create`.** Apply via `gcloud storage buckets update gs://[b] --update-labels=k1=v1,k2=v2`. ⚠️ **See Note 3.**
**IP Filtering**                   | `--ip-filter-file=[file]`              | JSON file defining IP/VPC rules. See **Helper Configuration Templates** below.
**Cloud Logging (Usage Logs)**     | `update ... --log-bucket=gs://[b]`     | **Cannot be set on `create`.** Apply via `gcloud storage buckets update gs://[b] --log-bucket=gs://[log-bucket] [--log-object-prefix=[prefix]]` (grant `roles/storage.objectCreator` to `cloud-storage-analytics@google.com` on log bucket).
**Lifecycle Policies (OLM)**       | `--lifecycle-file=[file]`              | JSON file defining OLM rules (prefer on `create`; also supported on `update`). See template below.
**CORS**                           | `update ... --cors-file=[file]`        | **Cannot be set on `create`.** Apply via `gcloud storage buckets update gs://[b] --cors-file=cors.json`.
**Website Configuration**          | `update ... --web-main-page-suffix`    | **Cannot be set on `create`.** Apply via `gcloud storage buckets update gs://[b] --web-main-page-suffix=index.html --web-error-page=404.html`.
**Public IAM Policy**              | `buckets add-iam-policy-binding`       | **Cannot be set on `create`.** For public websites/VOD: `gcloud storage buckets add-iam-policy-binding gs://[b] --member=allUsers --role=roles/storage.objectViewer`.
**Pub/Sub Notifications**          | `buckets notifications create`         | **Cannot be set on `create`.** Run `gcloud storage buckets notifications create gs://[b] --topic=[topic-name]`.
**Bucket Retention (Bucket Lock)** | `--retention-period=[duration]`        | E.g., `30d`, `90d`, `2555d`, `157680000s`, or ISO 8601 (`P1Y1M1DT5S`). Sets bucket-wide retention on `create` or `update`.
**Lock Bucket Retention Policy**   | `update ... --lock-retention-period`   | **Cannot be set on `create`.** Run `gcloud storage buckets update gs://[b] --lock-retention-period`. **Permanent and irreversible.**
**Object Retention (Object Lock)** | `--enable-per-object-retention`        | Enables per-object retention. **Can only be set on `create` via `gcloud`.**
**Set Object Retention**           | `objects update` / `storage cp`        | If object commands requested: `gcloud storage objects update gs://[b]/[obj] --retain-until=[RFC3339-ts] --retention-mode=[Locked/Unlocked] [--override-unlocked-retention]` (or set on upload via `gcloud storage cp`; `--override-unlocked-retention` is required to lock, shorten `--retain-until`, or `--clear-retention` on `Unlocked` objects).
**Rapid Cache (Anywhere Cache)**   | `buckets anywhere-caches create`       | **Cannot be set on `create`.** Run `gcloud storage buckets anywhere-caches create gs://[b] [zone] [--ttl=24h] [--enable-ingest-on-write]` (use `--enable-ingest-on-write`, never `--ingest-on-write`).
**Storage Insights Inventory**     | `insights inventory-reports create`    | Optional (only if CLI command is requested): `gcloud storage insights inventory-reports create gs://[src] --destination=gs://[dst]/inventory_reports/`.

> [!IMPORTANT]
>
> *   **Note 1 (Mandatory Inline Attribution Prefix)**: Prefix EVERY `gcloud`
>     command (including auxiliary `gcloud` commands in recommendations, except
>     `gcloud auth print-access-token` inside REST `curl` headers) inline with:
>
>     ```bash
>     CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)"
>     ```
>
> *   **Note 2 (Predefined Dual-Regions vs. Custom Dual-Regions & Zonal)**:
>
>     *   When `nam4` (`us-east1` + `us-central1`), `eur4` (`europe-north1` +
>         `europe-west4`), or `asia1` (`asia-northeast1` + `asia-northeast2`) is
>         specified—even if constituent regions are mentioned—set
>         `--location=nam4` (or `eur4`/`asia1`) directly and **NEVER** pass
>         `--placement` (fails with `HTTPError 400`).
>     *   For **custom dual-regions**, set `--location` to the continent geo
>         area (e.g., `US`) and `--placement=us-east1,us-west1`.
>     *   For **zonal (`RAPID`) buckets**, set `--location=<region>` (e.g.,
>         `us-east1`) and `--placement=<zone>` (e.g., `us-east1-b`).
>
> *   **Note 3 (Explain `create` vs. `update` for Labels)**: Whenever labels are
>     requested with `gcloud`, explicitly state in prose that labels cannot be
>     set during bucket creation via `gcloud` and must be applied using
>     `gcloud storage buckets update --update-labels=...`.

--------------------------------------------------------------------------------

## Helper Configuration Templates

Include the JSON file content alongside your `gcloud` commands whenever
`--encryption-enforcement-file`, `--cors-file`, `--lifecycle-file`, or
`--ip-filter-file` is used (and write it before executing in Phase 3).

### 1. Encryption Enforcement (`encryption_enforcement.json`)

```json
{
  "gmekEnforcement": {"restrictionMode": "NotRestricted"},
  "cmekEnforcement": {"restrictionMode": "NotRestricted"},
  "csekEnforcement": {"restrictionMode": "FullyRestricted"}
}
```

At least one encryption type must remain `NotRestricted`; omitted encryption
types default to allowed on `create`.

### 2. CORS Template (`cors.json`)

```json
[
  {
    "origin": ["https://my-website.appspot.com"],
    "method": ["GET", "HEAD", "PUT"],
    "responseHeader": ["Content-Type", "x-goog-resumable"],
    "maxAgeSeconds": 3600
  }
]
```

*(`responseHeader` and `maxAgeSeconds` are optional; match `origin` and `method`
to the user's request.)*

### 3. Lifecycle OLM Template (`lifecycle.json`)

```json
{
  "rule": [
    {"action": {"type": "AbortIncompleteMultipartUpload"}, "condition": {"age": 7}},
    {"action": {"type": "Delete"}, "condition": {"age": 365}}
  ]
}
```

*   Storage class transition (ONLY when Autoclass is disabled): `{"action":
    {"type": "SetStorageClass", "storageClass": "ARCHIVE"}, "condition": {"age":
    365}}`.
*   Prune non-current versions: `{"action": {"type": "Delete"}, "condition":
    {"daysSinceNoncurrentTime": 30, "isLive": false}}`.

> [!WARNING]
>
> **Autoclass Restrictions**: If Autoclass is enabled on the bucket, the Object
> Lifecycle Management (OLM) configuration **MUST NOT** contain rules using the
> `SetStorageClass` action or `matchesStorageClass` condition (doing so causes
> bucket creation or update to fail).

### 4. IP Filtering Template (`ip_filter.json`)

```json
{
  "mode": "Enabled",
  "allowAllServiceAgentAccess": true,
  "allowCrossOrgVpcs": false,
  "publicNetworkSource": {"allowedIpCidrRanges": ["192.0.2.0/24", "198.51.100.0/32"]},
  "vpcNetworkSources": [
    {"network": "projects/PROJECT_ID/global/networks/NETWORK_NAME", "allowedIpCidrRanges": ["10.0.0.0/16"]}
  ]
}
```

--------------------------------------------------------------------------------

## Conversion Examples

### Example 1: Sensitive Data / Compliance (CMEK, Autoclass, CSEK Restricted, Retention, Labels, OLM, IP Filter)

```bash
# 1. Create the bucket (omit optional flags like CMEK/retention/IP filter if not needed)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets create gs://my-compliance-pii-bucket \
    --project=my-compliance-project --location=us-central1 \
    --uniform-bucket-level-access --public-access-prevention \
    --soft-delete-duration=7d --retention-period=90d --enable-autoclass \
    --default-encryption-key=projects/my-kms-project/locations/us-central1/keyRings/my-keyring/cryptoKeys/my-key \
    --encryption-enforcement-file=encryption_enforcement.json \
    --lifecycle-file=lifecycle_abort.json --ip-filter-file=ip_filter.json

# 2. Add labels (labels cannot be set during bucket creation via gcloud; must use update)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets update gs://my-compliance-pii-bucket \
    --project=my-compliance-project --update-labels=data-class=pii,owner=security-team

# 3. Optional: Lock retention policy (WARNING: irreversible; neither admins nor Cloud Support can shorten/remove it)
# CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
# gcloud storage buckets update gs://my-compliance-pii-bucket --lock-retention-period
```

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website Config, CORS, Versioning)

```bash
# 1. Create the bucket with PAP disabled (--no-public-access-prevention)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets create gs://www.my-company-site.com \
    --project=my-frontend-project --location=US --default-storage-class=STANDARD \
    --uniform-bucket-level-access --no-public-access-prevention --soft-delete-duration=7d

# 2. Configure Website settings, CORS, and Versioning in a single update (cannot be set on create)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets update gs://www.my-company-site.com \
    --web-main-page-suffix=index.html --web-error-page=404.html --cors-file=cors_web.json --versioning

# 3. Grant public read access to website files
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets add-iam-policy-binding gs://www.my-company-site.com \
    --member=allUsers --role=roles/storage.objectViewer
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

```bash
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets create gs://my-training-checkpoints-us-east1-b \
    --project=my-ai-project --location=us-east1 --placement=us-east1-b \
    --default-storage-class=RAPID --uniform-bucket-level-access \
    --enable-hierarchical-namespace --public-access-prevention \
    --soft-delete-duration=0 --lifecycle-file=lifecycle_checkpoint.json
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

```bash
# 1. Create the bucket with per-object retention enabled (can only be set at creation time)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets create gs://my-legal-archive-bucket \
    --project=my-legal-project --location=us-east1 --default-storage-class=ARCHIVE \
    --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=7d \
    --enable-per-object-retention --lifecycle-file=lifecycle_archive.json \
    --default-encryption-key=projects/my-kms-project/locations/us-east1/keyRings/my-keyring/cryptoKeys/my-key

# 2. Apply labels via update (cannot be set during create)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets update gs://my-legal-archive-bucket \
    --project=my-legal-project --update-labels=compliance-type=regulatory,retention-period=7y

# 3. Upload an object with per-object retention (WARNING: Locked mode is permanent and irreversible; no one can delete/shorten until expiry)
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage cp case_file_abc.pdf gs://my-legal-archive-bucket/case_file_abc.pdf \
    --retain-until=2030-12-31T23:59:59Z --retention-mode=Locked

# 4. Or update retention on an existing object (--override-unlocked-retention required to lock, shorten --retain-until, or --clear-retention on Unlocked):
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage objects update gs://my-legal-archive-bucket/case_file_abc.pdf \
    --retain-until=2030-12-31T23:59:59Z --retention-mode=Locked --override-unlocked-retention
```
