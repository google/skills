# Storage Intelligence

Storage Intelligence is a subscription for analyzing and acting on Cloud Storage
data at scale.

-   **Analysis features:** Storage Insights datasets, data insights with Gemini
    Cloud Assist, inventory reports.
-   **Action features:** storage batch operations, bucket relocation.

Use it for organization-wide visibility (cost, security, governance) and for
operations too large to script (billions of objects, whole-bucket moves).

> [!NOTE]
>
> Datasets, batch operations, and bucket relocation **require** the
> subscription. Inventory reports work without it (the subscription covers their
> scan fees). Gemini Cloud Assist answers general GCS questions without it, but
> prompts about *your* buckets need a subscription plus a dataset.

## Choosing the Right Feature

| Goal                                 | Use                              |
| ------------------------------------ | -------------------------------- |
| Org/folder/project-wide metadata &   | Storage Insights datasets        |
: activity analysis, trends, security  :                                  :
: posture                              :                                  :
| Natural-language questions about     | Gemini Cloud Assist (backed by a |
: bucket/object metadata               : dataset)                         :
| Scheduled per-bucket object listing, | Inventory reports                |
: transfer validation                  :                                  :
| Bulk delete / metadata / holds /     | Batch operations (often fed by a |
: CMEK rotation on many objects        : dataset-generated manifest)      :
| Move a bucket to another location,   | Bucket relocation                |
: keeping its name                     :                                  :
| One-off small-scale changes          | Plain `gcloud storage` (no       |
:                                      : subscription needed)             :

--------------------------------------------------------------------------------

## 1. Configuration

Configure on a **project, folder, or organization**. Children inherit the
configuration, and you can override it at lower levels. Each resource has one
edition configuration: `INHERIT` (default when unset), `STANDARD` (all features,
set by `enable`), `DISABLED`, or `TRIAL`. Bucket filters scope by location or
name regex. Requires `roles/storage.admin`
(`storage.intelligenceConfigs.update`). See
[Configure and manage Storage Intelligence](https://cloud.google.com/storage/docs/storage-intelligence/configure-and-manage-storage-intelligence).

```bash
# Exactly one of --project, --sub-folder, --organization:
gcloud storage intelligence-configs enable --project=my-project

# Org-wide with filters:
gcloud storage intelligence-configs enable --organization=123456789 \
    --exclude-bucket-id-regexes="colddata.*" --include-locations=us-east1

gcloud storage intelligence-configs describe --project=my-project
gcloud storage intelligence-configs disable  --project=my-project

# update takes exactly one settings flag:
gcloud storage intelligence-configs update --project=my-project \
    --include-locations=us-east1
```

**30-day trial:** enables all `STANDARD` features and waives the object
management fee (other charges, e.g. BigQuery, still apply). Eligible **once**
per org/folder/project. **Auto-converts to paid `STANDARD` after 30 days**, so
disable within the window to avoid charges. Datasets created during the trial
persist (and keep billing BigQuery storage) until deleted.

--------------------------------------------------------------------------------

## 2. Storage Insights Datasets

A queryable index of **metadata and activity** for buckets/objects in scope,
delivered as a **BigQuery linked dataset**: metadata snapshots (projects,
buckets, objects), activity views (mutations, errors, bucket/project/regional
activity), and processing events/errors. See
[Configure datasets](https://cloud.google.com/storage/docs/insights/configure-datasets).

Key properties and limits:

-   **Scope:** one org, or up to 10,000 projects/folders, with bucket name-regex
    and location filters. `--auto-add-new-buckets` covers future buckets.
-   **Retention:** a rolling window of up to **90 days** for metadata. Activity
    data can be set separately, up to **365 days** (`0` excludes it).
-   **Locations:** BigQuery locations `EU`, `US`, `asia-south1`, `asia-south2`,
    `asia-southeast1`, `europe-west1`, `us-central1`, `us-east1`, `us-east4`
    only.
-   **Freshness:** the initial load takes 24–48h, activity data lands in ~4h,
    and metadata snapshots refresh every 24h.

```bash
gcloud storage insights dataset-configs create my_dataset \
    --location=us-central1 --organization=123456789 \
    --retention-period-days=30 --source-projects=987654321,123123123

# Must link to BigQuery before querying:
gcloud storage insights dataset-configs create-link my_dataset --location=us-central1
```

After creation, grant the Storage Insights service agent
(`service-PROJECT_NUMBER@gcp-sa-storageinsights.iam.gserviceaccount.com`) the
required permissions. Without them, no data flows. Service agents can be
per-config (default) or per-project (`--identity=IDENTITY_TYPE_PER_PROJECT`).

Use cases:

-   **Estate analysis:** find duplicates, temp data, and data in unexpected
    regions, or extract prefix lists to feed batch operations.
-   **Activity:** identify inactive buckets and map the hottest
    projects/prefixes. The regional activity view (request/response bytes per
    region) informs bucket relocation decisions.
-   **Security:** object `securityInsights` computes **public access status**
    (evaluates PAP, UBLA, ACLs, IAM, org policies, and shows where the grant
    originates). Audit encryption (`encryptionType`) and retention
    (`retentionExpirationTime`, `softDeletePolicy`).
-   **Troubleshooting:** `object_events_view` records errored operations with
    reasons (e.g., find buckets with high 429 rates).
-   **Content analysis:** join metadata to object data via BigQuery `ObjectRef`
    functions (`ref` column).

**Dashboards:** connect the linked dataset to Looker Studio, or start from the
[dashboard template](https://lookerstudio.google.com/reporting/670eee3f-ad6d-45ea-a169-853ab023dc84).
Dashboard queries consume BigQuery compute, so evaluate on a small dataset
first.

Limitations: public access status skips objects in managed folders and ignores
VPC-SC and IP filtering. CRC32C/MD5 checksums are missing for CMEK objects, and
renaming an HNS folder makes its objects reappear as new entries.

--------------------------------------------------------------------------------

## 3. Data Insights with Gemini Cloud Assist (Preview)

With a linked dataset, the Cloud Assist panel on the console's Storage Insights
page answers natural-language prompts about your metadata and returns the
underlying SQL. Examples: "5 largest buckets without Autoclass enabled",
"objects with a retention expiration date within the next 30 days", "buckets
with a high volume of small files". Including "Cloud Storage" in the prompt
improves quality.

Setup: enable Gemini Cloud Assist and Storage Intelligence, create and link a
dataset, grant the service agent `roles/bigquery.dataViewer`, and give users
`roles/bigquery.jobUser`, `roles/bigquery.dataViewer`,
`roles/storageinsights.viewer`.

Quotas and limits:

-   Prompts needing **≥ 800 GB** of processing return SQL only, for you to run
    yourself. Processing is capped at **50 TiB/month/org**.
-   Returns at most the **top 5** matching resources per prompt.
-   Reads only the **latest snapshot**, so no time-series ("how much did my
    bucket grow"). Cost data, activity data ("last access time"), and some
    configs (e.g., soft delete) aren't in the dataset at all.
-   Still in Preview, so validate responses before acting.

--------------------------------------------------------------------------------

## 4. Inventory Reports

Scheduled per-bucket object listings (CSV or Apache Parquet) written to a
destination bucket, as a faster alternative to paginated `Objects: list`. The
report config lives on the source bucket (max 100 per bucket) and defines the
frequency (daily/weekly), the metadata fields (always `project`, `bucket`, and
`name`, plus optional fields like `size`, `timeCreated`, `updated`,
`storageClass`, `etag`, checksums, `generation`, `contentType`, and
`retentionExpirationTime`), and the destination bucket (same project and
location as the source, or the source bucket itself). Reports over 1M objects
are sharded, with a `*_manifest.json` written when all shards are complete.

**Use for:** quick single-bucket analysis, transfer validation, per-bucket
audits. **Use datasets instead for:** multi-bucket/org-wide analysis, trends,
activity data.

> [!NOTE]
>
> Delivery is best-effort, so reports may skip days or miss objects. For
> complete daily coverage, use datasets instead. Not compatible with bucket IP
> filtering, and unavailable in a few locations (e.g., `me-central1`,
> `me-central2`, dual-regions `eur5`/`eur7`/`eur8`).

--------------------------------------------------------------------------------

## 5. Storage Batch Operations

Serverless jobs that run **one transformation** across objects in **one
bucket**, scaling to ~1B objects in ~3 hours with concurrent jobs. Jobs are LROs
with progress tracking and automatic retries.

Job types:

-   **delete**
-   **metadata update**: custom metadata, or fixed fields like `Content-Type`,
    `Cache-Control`, `Custom-Time`, and retention config
-   **object hold** set/release
-   **object rewrite**: CMEK key or storage class
-   **object context updates**

Objects are selected either by a **manifest** (a CSV in GCS with the header
`bucket,name,generation`, where generation is optional and rows for other
buckets are ignored) or by up to 1,000 **object prefixes** (an empty list means
the whole bucket). A common pattern is to query a dataset to generate the
manifest.

```bash
# Bulk metadata update from a manifest:
gcloud storage batch-operations jobs create my-job \
    --bucket=my-bucket \
    --manifest-location=gs://my-bucket/manifest.csv \
    --put-metadata=Content-Language=en

# Always dry-run large deletes first (counts affected objects, no changes):
gcloud storage batch-operations jobs create my-dry-run \
    --bucket=my-bucket --included-object-prefixes=tmp/,staging/ \
    --delete-object --dry-run

gcloud storage batch-operations jobs describe my-job   # also: cancel, delete
```

> [!CAUTION]
>
> Batch deletes are recoverable only via soft delete (7-day default). If soft
> delete is disabled on the bucket, deleted objects are unrecoverable.

Limits: jobs auto-cancel after **14 days**, at most 1,000 prefixes per job, at
most ~20 concurrent jobs per bucket recommended, and **Requester Pays buckets
are unsupported**. Pricing adds no fee beyond the subscription, but normal
per-operation charges apply: transformations are Class A (skipped if the object
is already in the desired state), deletes are free, and listing during jobs and
dry runs is Class A.

--------------------------------------------------------------------------------

## 6. Bucket Relocation

Moves a bucket to a different location **without renaming it or manual data
copying**, preserving object metadata and storage classes, including Autoclass
(legacy classes convert to Standard). Reads stay available throughout. Typical
drivers: cut inter-region transfer costs, colocate with compute, or move from a
region to a dual/multi-region for resilience (use the dataset regional activity
view to find candidates).

Two types, determined by source/destination locations:

-   **With write downtime** (most moves: region↔region, region↔dual-region,
    across multi-region codes): writes are blocked only during the final
    synchronization step, which **you** initiate.
-   **Without write downtime** (locations sharing a multi-region code, e.g.
    configurable dual-region ↔ multi-region): no finalize step, but takes a
    **minimum of 7 days** regardless of size, and latency may increase.

```bash
# 1. Dry run first to catch incompatibilities early:
gcloud storage buckets relocate gs://my-bucket --location=us-central1 --dry-run

# 2. Initiate. Bucket metadata is write-locked, object reads/writes continue:
gcloud storage buckets relocate gs://my-bucket --location=us-central1

# 3. Finalize (write-downtime moves only). Object writes fail with HTTP 412
#    until complete, then the lock lifts automatically:
gcloud storage buckets relocate --finalize \
    --operation=projects/_/buckets/my-bucket/operations/OPERATION_ID
```

Copy duration scales with object count, churn, and size (objects over 10 GB move
slowly, at roughly a day per TB-sized object). Check the compatibility list
before starting: Firebase and appspot buckets can't be relocated at all,
multipart uploads and retention policies have restrictions, and with-downtime
moves support fewer features. `ME-CENTRAL1` and `ME-WEST1` aren't supported.

--------------------------------------------------------------------------------

## 7. Pricing

-   **Subscription:** $2.50 per million objects/month, amortized daily, billed
    to the bucket's project, only for objects older than 24h. Early termination
    fee if a bucket leaves `STANDARD` tier within 30 days (deletions exempt).
-   **Datasets:** no extra SI fee (multiple configs over the same buckets pay
    once), but BigQuery storage and query charges apply (~300 MB metadata per TB
    of data daily). Disabling SI stops snapshots but does **not** delete
    BigQuery data, so delete dataset configs to stop charges.
-   **Batch operations:** standard Class A/B operation charges per object
    (deletes free).
-   **Bucket relocation:** **$0.04/GB** moved, plus inter-region transfer, one
    Class A op per object, and storage billed in **both** locations during the
    move. There are no retrieval or early-deletion fees, and transfer is waived
    if source and destination overlap in a region.
-   **Trial:** waives the object management fee and the early termination fee.

Details: https://cloud.google.com/storage/pricing#storage-intelligence

--------------------------------------------------------------------------------

## Documentation

-   [Storage Intelligence Overview](https://cloud.google.com/storage/docs/storage-intelligence/overview)
-   [Configure and Manage Storage Intelligence](https://cloud.google.com/storage/docs/storage-intelligence/configure-and-manage-storage-intelligence)
-   [30-Day Introductory Trial](https://cloud.google.com/storage/docs/storage-intelligence/30-day-introductory-trial/overview)
-   [Storage Insights Datasets](https://cloud.google.com/storage/docs/insights/datasets)
    /
    [Configure Datasets](https://cloud.google.com/storage/docs/insights/configure-datasets)
    /
    [Tables and Schemas](https://cloud.google.com/storage/docs/insights/dataset-tables-and-schemas)
-   [Analyze Data with Gemini Cloud Assist](https://cloud.google.com/storage/docs/analyze-data-gemini-cloud-assist)
-   [Inventory Reports](https://cloud.google.com/storage/docs/insights/inventory-reports)
-   [Batch Operations](https://cloud.google.com/storage/docs/batch-operations/overview)
    /
    [Create and Manage Jobs](https://cloud.google.com/storage/docs/batch-operations/create-manage-batch-operation-jobs)
-   [Bucket Relocation](https://cloud.google.com/storage/docs/bucket-relocation/overview)
    /
    [Plan a Relocation](https://cloud.google.com/storage/docs/bucket-relocation/plan-bucket-relocation)
