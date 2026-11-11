# AI & Machine Learning (Storage for AI)

This reference document outlines the configuration mapping and architecture
recommendation for Cloud Storage buckets optimized for AI/ML workloads,
including model training, checkpointing, and model inference.

## Description

The user is running demanding AI/ML workloads (such as Large Language Model
training, computer vision pipelines, or high-throughput batch inference)
utilizing TPU or GPU accelerators. These workloads require ultra-high read/write
throughput, sub-millisecond latencies, and co-location with compute resources to
prevent compute starvation.

## Architecture Alternatives: Rapid Cache vs. Zonal Buckets (Rapid Bucket)

Depending on the specific workload phase (Training, Checkpointing, or Inference)
and data access patterns, recommend one of the two Cloud Storage Rapid
solutions. Per the
[Rapid Bucket Terminology](https://cloud.google.com/storage/docs/rapid/rapid-bucket#terminology),
**Rapid Bucket** is the product that enables buckets to be created with a zonal
location and the **Rapid storage class**, while individual buckets are referred
to as **zonal buckets**.

Dimension                  | Rapid Cache                                                                                                                    | Zonal Buckets (Rapid Bucket)
:------------------------- | :----------------------------------------------------------------------------------------------------------------------------- | :---------------------------
**Description**            | SSD-backed zonal read cache attached to an existing Cloud Storage bucket (regional, dual-regional, or multi-regional).         | Zonal bucket in the `RAPID` storage class.
**Primary Use Case**       | **Model Training & Inference** where datasets already exist in a Cloud Storage bucket.                                         | **Model Checkpointing** and high-QPS, write-heavy training tasks.
**Read/Write**             | **Read-Only**. Writes must be written to the underlying bucket.                                                                | **Read and Write**. Serves as a writable source of truth.
**Namespace**              | Same namespace as the underlying Cloud Storage bucket.                                                                         | Independent namespace (must copy/upload data directly).
**Performance**            | High throughput. Initial read cold-start penalty can be avoided using **ingest-on-write**. Same QPS as standard Cloud Storage. | Ultra-low latency, high throughput, and high QPS (no cold start).
**Data Lifecycle**         | Default TTL is 24 hours. Cache automatically evicts stale data.                                                                | Permanent storage (data lives forever until deleted).
**Appendability**          | No append support.                                                                                                             | **Supports Append (BiDi protocol)** to write streaming data up to 5TiB.
**Hierarchical Namespace** | Optional.                                                                                                                      | **Required** (Always enabled, not configurable).

--------------------------------------------------------------------------------

## Rapid Cache Specific Recommendations

When the architecture plan recommends **Rapid Cache**, the agent MUST explicitly
configure and recommend the following:

1.  **Zonal Co-location**: Co-locate the Rapid Cache instance in the exact same
    zone as the compute cluster (e.g. GPU/TPU cluster).
2.  **Ingest-on-Write (Recommended to Avoid Cold Start)**: Enable
    [ingest-on-write](https://cloud.google.com/storage/docs/rapid/rapid-cache#ingest-on-write)
    (at bucket-level or prefix/managed folder level) so that newly written data
    is immediately ingested into the cache upon write. This eliminates initial
    cache misses and avoids cold-start penalties for read-after-write workloads.

--------------------------------------------------------------------------------

## Zonal Buckets (Rapid Bucket) Specific Recommendations

When the architecture plan recommends **Zonal Buckets (Rapid Bucket)**, the
agent MUST explicitly configure and recommend the following:

1.  **Zonal Co-location**: Co-locate the zonal bucket in the exact same zone as
    the compute/training nodes (e.g. `us-east4-a` for GPU cluster in
    `us-east4-a`) to eliminate network bottlenecks.
2.  **Storage Class**: The storage class MUST be set to `RAPID`.
3.  **Disable Soft Delete**: Soft delete is not supported for zonal buckets and
    MUST be disabled (set `--soft-delete-duration=0` during creation).
4.  **Hierarchical Namespace**: Hierarchical Namespace MUST be enabled.
5.  **BiDi Protocol Recommendation**: For streaming, write-heavy, or logging
    workloads, explicitly recommend utilizing the **BiDi protocol**
    (Bidirectional Streaming) on the zonal bucket to enable low-latency,
    high-QPS streaming append operations up to 5TiB.

--------------------------------------------------------------------------------

## Bucket Configuration Plan Mapping

The following table maps Cloud Storage features to AI/ML workloads and details
their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status                     | Recommendations & Implementation Details
:------------------------------------- | :------------------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended         | Use **STANDARD** for standard buckets, or **RAPID** storage class for zonal buckets.
**Bucket Type**                        | Highly Recommended         | **Zonal** (with Rapid Bucket) or **Regional / Dual-region / Multi-region** (for Cloud Storage bucket with Rapid Cache) to co-locate storage and compute.
**CORS & Signed URLs**                 | Optional / Not Recommended | Avoid exposing AI datasets directly to public users.
**Uniform Bucket-Level Access (UBLA)** | **Required**               | **Must be enabled** for baseline access control security.
**Encryption (CMEK)**                  | Highly Recommended         | Configure CMEK. Use KMS Autokey for automation.
**Soft Delete**                        | Good to Have               | Optional for non-zonal buckets (useful but not highly recommended due to potential storage cost overhead from massive AI dataset churn). Unsupported for zonal buckets.
**Object Lifecycle Management (OLM)**  | Highly Recommended         | Define OLM rules to automatically delete stale checkpoints (e.g. keep only the last 3 days of checkpoints) to avoid massive storage bills on zonal disks.
**Labels & Tagging**                   | Highly Recommended         | Apply billing and ownership labels (e.g. `{"workload": "ai-training"}`) to accurately trace expensive high-performance storage spend.
**BiDi (Bidirectional Streaming)**     | Highly Recommended         | Utilize the BiDi protocol on zonal buckets to enable low-latency, high-QPS streaming and append operations.
**Cloud Monitoring**                   | Highly Recommended         | Monitor caching metrics, hit rates, and ingress/egress bandwidth to ensure TPUs/GPUs are not bottlenecked by storage.

## Key Pre-Deployment Questions to Ask:

1.  **What phase of the AI/ML pipeline is this storage for?**
    *   *If Training / Inference (read-heavy)*: Ask if the dataset already
        exists. Recommend **Rapid Cache** to save migration time and egress
        costs.
    *   *If Checkpointing (write-heavy)*: Recommend **zonal buckets** (with
        Rapid Bucket) for low-latency writes.
2.  **What zone is your compute cluster (TPU/GPU) located in?**
    *   *Recommendation*: Co-locate the Rapid Cache or zonal bucket in the exact
        same zone (e.g. `us-central1-a`) to eliminate network bottlenecks.
3.  **If using Rapid Cache, do you want to enable ingest-on-write?**
    *   *Recommendation*: Enable ingest-on-write so that data is ingested into
        the cache upon write, eliminating initial cache misses and cold-start
        penalties.

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Rapid Bucket Terminology    | https://cloud.google.com/storage/docs/rapid/rapid-bucket#terminology
Locations                   | https://cloud.google.com/storage/docs/locations
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
CMEK                        | https://cloud.google.com/storage/docs/encryption/customer-managed-keys
Soft Delete                 | https://cloud.google.com/storage/docs/soft-delete
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Bucket Labels               | https://cloud.google.com/storage/docs/using-bucket-labels
Hierarchical Namespace      | https://cloud.google.com/storage/docs/hns-overview
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
