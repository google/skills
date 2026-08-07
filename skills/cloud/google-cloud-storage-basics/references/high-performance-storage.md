# High-Performance Cloud Storage (AI/ML, Analytics, and More)

Data-intensive and latency-sensitive workloads such as AI/ML training and
serving, analytics, high-performance computing (HPC), media processing, and
high-rate logging or messaging are often bottlenecked by how fast data reaches
the compute. Cloud Storage offers three features to remove that bottleneck. They
are most associated with AI/ML but help any read-heavy or latency-critical
workload:

-   **Rapid Bucket** and **Rapid Cache** are the two products in the **Cloud
    Storage Rapid** family. Rapid Bucket stores data in a new zonal,
    high-performance bucket, while Rapid Cache accelerates reads from your
    *existing* buckets.
-   **Hierarchical namespace (HNS)** is a bucket mode that adds filesystem-like
    folders and higher request rates. It is required by Rapid Bucket and is also
    useful on its own.

Decision guide: to accelerate reads from data you already store, use **Rapid
Cache** (no migration). For a new, latency-critical workload you can colocate
with accelerators, use a **Rapid Bucket**. To get fast folder operations and
higher QPS on a standard bucket, enable **HNS**.

Rapid Bucket and Rapid Cache are premium, performance-tier features available
only in selected regions and zones. For most workloads, a standard regional or
multi-region bucket is the right default.

## Feature Comparison

| Feature          | What it is        | When to use       | Key benefits      |
| :--------------- | :---------------- | :---------------- | :---------------- |
| **Rapid Bucket** | A zonal bucket    | New,              | Sub-millisecond   |
:                  : using the Rapid   : latency-critical  : latency, up to 15 :
:                  : storage class.    : workloads that    : TB/s aggregate    :
:                  : Data lives in a   : can colocate data : throughput, and   :
:                  : single zone,      : with compute in   : 20 million QPS;   :
:                  : colocated with    : one zone, such as : supports          :
:                  : your compute and  : AI/ML training,   : streaming object  :
:                  : accelerators.     : checkpointing,    : appends.          :
:                  :                   : evaluation, and   :                   :
:                  :                   : serving, plus     :                   :
:                  :                   : HPC, high-rate    :                   :
:                  :                   : logging, and      :                   :
:                  :                   : messaging queues. :                   :
| **Rapid Cache**  | A fully managed,  | Read-heavy        | Up to 2.5 TB/s    |
:                  : SSD-backed zonal  : workloads on      : throughput and    :
:                  : read cache        : existing buckets  : lower read        :
:                  : (formerly         : where data is     : latency;          :
:                  : Anywhere Cache)   : read often but    : autoscales;       :
:                  : that fronts       : changed rarely,   : reduces           :
:                  : existing          : such as AI/ML     : data-transfer,    :
:                  : regional,         : training and data : retrieval, and    :
:                  : dual-region, or   : loading,          : read-operation    :
:                  : multi-region      : checkpoint        : fees versus       :
:                  : buckets with no   : restores,         : reading directly  :
:                  : data migration or : analytics, and    : from the bucket.  :
:                  : code changes.     : repeated content  :                   :
:                  :                   : serving.          :                   :
| **Hierarchical   | A bucket mode,    | Workloads needing | Up to 8x higher   |
: namespace        : set at creation,  : fast folder       : initial QPS;      :
: (HNS)**          : where folders are : operations,       : atomic and fast   :
:                  : real resources    : filesystem        : folder renames;   :
:                  : with              : semantics, or     : efficient         :
:                  : filesystem-like   : higher request    : listing;          :
:                  : semantics.        : rates, such as    : preserves object  :
:                  :                   : analytics, AI/ML  : metadata (and     :
:                  :                   : frameworks like   : lifecycle age)    :
:                  :                   : TensorFlow,       : across renames.   :
:                  :                   : Pandas, and       :                   :
:                  :                   : PyTorch, and any  :                   :
:                  :                   : large dataset     :                   :
:                  :                   : organized into    :                   :
:                  :                   : many folders.     :                   :
:                  :                   : Required to       :                   :
:                  :                   : create a Rapid    :                   :
:                  :                   : Bucket.           :                   :

## Important Constraints

Verify these before recommending a feature. The high-performance options trade
flexibility and redundancy for speed.

-   **Rapid Bucket:**

    -   Requires hierarchical namespace and uniform bucket-level access, and
        gcloud CLI version **553.0.0 or later** (earlier versions are not
        compatible with zonal buckets).
    -   Mounting zonal buckets with Cloud Storage FUSE requires **gcsfuse
        version 3.7.2 or later** — earlier releases (including 3.x versions
        before 3.7.2) cannot mount them. Through the GKE CSI driver, the GKE
        cluster must be `1.35.0-gke.3047001` or later.
    -   Data is stored in a **single zone** with no cross-zone redundancy, so it
        does not have the durability and availability of a regional bucket. For
        data you cannot lose, copy it to a regional bucket (for example,
        replicate checkpoints).
    -   Not compatible with Object Versioning, soft delete, cross-bucket
        replication, resumable uploads, object rewrite or compose,
        customer-supplied encryption keys (CSEK), HMAC keys, BigQuery,
        Autoclass, Bucket Lock, Object Retention Lock, object holds, or
        Requester Pays. In particular, a Rapid Bucket **cannot be fronted by
        Rapid Cache** — the two Cloud Storage Rapid products are alternatives,
        not a stack.

-   **Rapid Cache:**

    -   A read cache, not durable storage. Cached data can be evicted, and it
        does not accelerate writes.
    -   Delete a bucket's caches before deleting the bucket.

-   **Hierarchical namespace:** Set at creation and cannot be changed later, and
    requires uniform bucket-level access. Not compatible with Object Versioning,
    Bucket Lock, Object Retention Lock, object holds, cross-bucket replication,
    or bucket relocation. See [Core Concepts](core-concepts.md). Lifecycle rules
    act on objects only — empty folders persist until deleted explicitly — but
    as of **August 26, 2026**, the lifecycle Delete action also deletes an empty
    folder once it meets all of the rule's conditions, so folder-sweeper
    automation can be retired after that date.

## Enabling Each Feature

Hierarchical namespace and Rapid Bucket are configured at bucket creation and
cannot be turned on later. Both require uniform bucket-level access.

```bash
# Hierarchical namespace bucket (regional, dual-region, or multi-region):
gcloud storage buckets create gs://BUCKET_NAME \
    --location=LOCATION \
    --uniform-bucket-level-access --enable-hierarchical-namespace

# Rapid Bucket (zonal, Rapid storage class; HNS and UBLA are required):
gcloud storage buckets create gs://BUCKET_NAME \
    --location=REGION --placement=ZONE \
    --default-storage-class=RAPID \
    --enable-hierarchical-namespace --uniform-bucket-level-access
```

`ZONE` must be a zone within `REGION` (for example, `--location=us-east1
--placement=us-east1-b`), and the zone must be one where Rapid Bucket is
available, so check the linked docs first.

Rapid Cache is added to an *existing* bucket. Create it through the recommender
workflow below so you only cache where it saves cost.

## Workflow: Recommend and Create Cost-Optimal Rapid Caches

Rather than guess where caching pays off, use the **Rapid Cache recommender**.
It analyzes your bucket's read activity over the past seven days, simulates how
a cache would have performed, and only recommends a cache when it would be
cost-effective: the simulated cache exceeds 100 GiB and meets at least one of a
hit rate above 80%, net savings above $700 per week on multi-region
data-transfer-out fees (based on negotiated price), or peak throughput above 800
Gbps. Following its recommendations is therefore cost-optimal by design.

1.  **Enable the Recommender API:**

    ```bash
    gcloud services enable recommender.googleapis.com --quiet
    ```

    Viewing recommendations also requires the Rapid Cache recommender
    permissions (`recommender.storageBucketAnywhereCacheRecommendations.get` and
    `.list`). See
    [Rapid Cache recommender](https://docs.cloud.google.com/storage/docs/rapid/rapid-cache-recommender)
    for the exact roles and permissions.

2.  **List recommendations** (`BUCKET_REGION` is the bucket's region, a single
    region such as `us-central1`):

    ```bash
    gcloud recommender recommendations list \
        --project=PROJECT_ID --location=BUCKET_REGION \
        --recommender=google.storage.bucket.AnywhereCacheRecommender \
        --format=json
    ```

    Each recommendation includes the target bucket, the zone to cache in, a
    suggested TTL, and the projected cost/performance impact. The recommender ID
    and the `recommender.storageBucketAnywhereCache*` permissions retain the
    legacy AnywhereCache name, so use them verbatim.

3.  **Create the recommended cache** in the suggested zone. The product is Rapid
    Cache, but the CLI command path still uses `anywhere-caches`:

    ```bash
    gcloud storage buckets anywhere-caches create gs://BUCKET_NAME CACHE_ZONE \
        --ttl=7d
    ```

    `--ttl` accepts a duration from 1 to 7 days (default 1 day). Add the
    optional `--enable-ingest-on-write` flag to also cache objects when they are
    written, not just on first read.

4.  **Verify the cache** is active:

    ```bash
    gcloud storage buckets anywhere-caches list gs://BUCKET_NAME
    ```

To monitor savings across many buckets continuously, export recommendations to
BigQuery with the BigQuery Data Transfer Service and review them on a schedule.

## Documentation

-   [Cloud Storage Rapid overview](https://docs.cloud.google.com/storage/docs/rapid/high-performance-storage)
-   [Rapid Bucket](https://docs.cloud.google.com/storage/docs/rapid/rapid-bucket)
-   [Rapid Cache](https://docs.cloud.google.com/storage/docs/rapid/rapid-cache)
-   [Rapid Cache recommender](https://docs.cloud.google.com/storage/docs/rapid/rapid-cache-recommender)
-   [Create and use a Rapid Cache](https://docs.cloud.google.com/storage/docs/rapid/use-rapid-cache)
-   [Hierarchical namespace](https://docs.cloud.google.com/storage/docs/hns-overview)
-   [Design storage for AI and ML workloads](https://docs.cloud.google.com/ai-hypercomputer/docs/storage)
