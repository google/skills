# Google Cloud Storage Core Concepts

Google Cloud Storage stores immutable objects in buckets within a flat
namespace. All reads and writes are strongly consistent: after an upload,
overwrite, or delete completes, the change is immediately visible globally,
including in object listings.

## Resource Hierarchy

1.  **Project:** The standard Google Cloud container that owns buckets.
2.  **Bucket:** The container for objects. Bucket names share a single global
    namespace, must be 3-63 characters of lowercase letters, numbers, and
    hyphens, and cannot be changed after creation. Location and location type
    are also fixed at creation.
3.  **Object:** An immutable piece of data (up to 5 TiB) plus its metadata.
    Objects cannot be edited in place; an "edit" is an overwrite that creates a
    new object (or a new generation if versioning is enabled).

## Folders and Prefixes

GCS has a flat namespace; `/` characters in object names only simulate a
directory structure.

-   **Prefixes (simulated folders):** Tools like the Cloud Console and `gcloud
    storage` render `gs://bucket/logs/2026/file.txt` as nested folders, but
    `logs/2026/` is just a name prefix. Listing with a prefix and delimiter is
    how "folder" browsing works.

-   **Managed folders:** A Cloud Storage resource that lets you apply IAM
    policies to the group of objects sharing a prefix, rather than to the whole
    bucket. For example, a managed folder at `gs://bucket/teams/alpha/` lets you
    grant a role over only the objects whose names start with `teams/alpha/`;
    those objects are governed by the managed folder's policy in addition to the
    bucket's. Requires uniform bucket-level access.

-   **Hierarchical namespace (HNS):** An opt-in bucket mode (set at creation,
    cannot be changed later) where folders are true resources, enabling atomic
    folder renames and faster folder operations. Well suited to analytics and
    AI/ML workloads, but check the
    [limitations](https://docs.cloud.google.com/storage/docs/hns-overview#hns-limitations)
    first: HNS buckets require uniform bucket-level access and do not support
    Object Versioning, Bucket Lock, Object Retention Lock, object holds,
    cross-bucket replication, or bucket relocation. See
    [High-Performance Storage](high-performance-storage.md).

## Bucket Location Types

| Type             | Description      | When to use                            |
| :--------------- | :--------------- | :------------------------------------- |
| **Region**       | Data stored in a | Lowest storage price; co-locate with   |
:                  : single region.   : compute for best performance.          :
| **Dual-region**  | Data replicated  | High availability with specific region |
:                  : across a chosen  : control; supports turbo replication    :
:                  : pair of regions. : for a 15-minute replication RPO.       :
| **Multi-region** | Data replicated  | Highest availability for broadly       |
:                  : across a         : accessed content; no control over      :
:                  : continent (e.g., : specific regions.                      :
:                  : `US`, `EU`).     :                                        :
| **Zonal**        | Data stored in a | Millisecond-latency access for AI/ML   |
:                  : single zone      : training and other                     :
:                  : (rapid storage   : performance-critical workloads. See    :
:                  : buckets).        : [High-Performance                      :
:                  :                  : Storage](high-performance-storage.md). :

## Storage Classes

The storage class sets the at-rest price, retrieval fee, and minimum storage
duration for an object. Every bucket has a default class applied to new objects;
individual objects can override it.

| Class        | Minimum duration | Retrieval fee | When to use                |
| :----------- | :--------------- | :------------ | :------------------------- |
| **Standard** | None             | None          | Frequently accessed        |
:              :                  :               : ("hot") data and           :
:              :                  :               : short-lived data.          :
| **Nearline** | 30 days          | Yes           | Data accessed about once a |
:              :                  :               : month or less (e.g.,       :
:              :                  :               : backups).                  :
| **Coldline** | 90 days          | Yes           | Data accessed about once a |
:              :                  :               : quarter or less.           :
| **Archive**  | 365 days         | Yes           | Long-term retention        |
:              :                  :               : accessed less than once a  :
:              :                  :               : year.                      :

-   **Autoclass:** A bucket setting that automatically transitions each object
    between classes based on its access pattern, removing retrieval fees and
    class-choice guesswork. Use when access patterns are unknown or mixed.

-   **Rapid storage:** A separate class used by zonal buckets for
    millisecond-latency AI/ML workloads. See
    [High-Performance Storage](high-performance-storage.md).

Objects in colder classes are served with the same millisecond latency as
Standard, with no restore, rehydration, or thaw step — reading from Coldline or
Archive is an immediate `read`, unlike cold tiers on some other clouds. Only the
cost structure differs (retrieval fee plus minimum storage duration). To
transition objects automatically over time, use Object Lifecycle Management or
Autoclass (see [Data Management](data-management.md)).

## Pricing

Cloud Storage pricing has four main components:

-   **Data storage:** A per-GiB monthly rate determined by storage class and
    bucket location. Colder classes store data more cheaply but add retrieval
    fees and minimum storage durations.

-   **Operations:** Per-request charges. Class A operations (writes, listings)
    cost more than Class B operations (reads), and operation prices increase for
    colder storage classes.

-   **Retrieval and early deletion:** Nearline, Coldline, and Archive charge a
    per-GiB retrieval fee, and deleting or rewriting an object before its
    minimum storage duration bills the remainder. Autoclass eliminates both in
    exchange for a small management fee.

-   **Data transfer:** Egress to the internet or across locations is billed;
    ingress and access from co-located compute are free. Dual- and multi-region
    buckets include replication costs.

By default all charges bill to the project that owns the bucket. With
[Requester Pays](https://docs.cloud.google.com/storage/docs/requester-pays)
enabled, access charges (operations, retrieval, data transfer) bill to the
requester's project instead; storage charges always bill to the bucket's
project.

For the latest pricing details, visit:
[Cloud Storage Pricing](https://cloud.google.com/storage/pricing).

## Documentation

-   [Product overview](https://cloud.google.com/storage/docs/introduction)
-   [Buckets](https://cloud.google.com/storage/docs/buckets)
-   [Objects](https://cloud.google.com/storage/docs/objects)
-   [Folders and managed folders](https://cloud.google.com/storage/docs/folders)
-   [Hierarchical namespace](https://cloud.google.com/storage/docs/hns-overview)
-   [Bucket locations](https://cloud.google.com/storage/docs/locations)
-   [Storage classes](https://cloud.google.com/storage/docs/storage-classes)
-   [Consistency](https://cloud.google.com/storage/docs/consistency)
