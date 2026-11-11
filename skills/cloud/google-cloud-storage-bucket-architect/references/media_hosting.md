# Media Hosting & Content Delivery Network (CDN)

This reference document outlines the secure-by-default, high-performance
configuration mapping and architecture recommendation for Cloud Storage buckets
serving as the origin for media assets and Content Delivery Networks (CDNs).

## Description

The user is serving high-definition images, videos, or audio assets to a global
or geo-regional audience with low latency. Cloud Storage acts as the origin
store for a CDN (e.g. Cloud CDN or third-party CDNs), and requires high read QPS
scaling, high bandwidth, and immediate data availability.

## Bucket Configuration Plan Mapping

The following table maps the Media Hosting & CDN to specific Cloud Storage
features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status             | Recommendations & Implementation Details
:------------------------------------- | :----------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended | **Autoclass** or **Standard** Storage Class.<br><br>Standard storage is recommended to avoid retrieval fees on highly active content. Autoclass is ideal for automatically transitioning stale media assets or raw originals to colder tiers over time.
**Bucket Type**                        | Highly Recommended | For **live-streaming**: **Regional** or **Dual-Regional** buckets (to co-locate compute and storage). For **Video-on-Demand (VOD)**: **Multi-Regional (MR)** to distribute content closer to a global user base.
**CORS**                               | Highly Recommended | **Configure CORS.** Allow `GET` and `HEAD` requests from expected domains (or `["*"]` for global public assets) using `set_bucket_cors` to enable client-side asset loading.
**Signed URLs**                        | Optional           | Use only if media assets require paid access or must be gated by authentication token.
**Uniform Bucket-Level Access (UBLA)** | **Required**       | **Must be enabled.** Prevents legacy object-level ACLs from overriding bucket-level IAM policies.
**Soft Delete**                        | Highly Recommended | **Enabled (default 7 days).** Vital to protect crucial application media assets from accidental purge commands or deployment script bugs.
**Object Versioning**                  | Good to Have       | Suggest as an alternative to prevent accidental media overwrite or modification if Soft Delete is disabled.
**IP Filtering**                       | Good to Have       | Restrict admin operations and raw manual exports to trusted corporate SOC IP perimeters.
**Object Lifecycle Management (OLM)**  | Good to Have       | If Autoclass is disabled, automatically transition older, unviewed original media assets to colder storage tiers. Recommend standard OLM rule: Transition to `ARCHIVE` after 365 days.
**Hierarchical Namespace**             | Highly Recommended | **Enable Hierarchical Namespace** for high-volume or high-QPS streaming workloads. Hierarchical Namespace buckets offer up to **8x higher initial QPS** limits for object operations compared to standard buckets.<br><br>*Note: Hierarchical Namespace is incompatible with Object Versioning, and Retention Policies (Bucket Lock/Object Lock). Hierarchical Namespace is compatible with Soft Delete.*
**Storage Transfer Service (STS)**     | Good to Have       | Relocate and replicate media assets across regions using STS to move content closer to growing user bases and minimize latency.
**Cloud Logging**                      | Good to Have       | Enable audit logging for troubleshooting access and tracking server-side security events.
**Cloud Monitoring**                   | Good to Have       | Track network egress, operations count, and monitor operational error rates (404, 503).

## Key Pre-Deployment Questions to Ask:

1.  **Is this for live-streaming or Video-On-Demand (VOD)?**
    *   *If Live-streaming*: Regional or Dual-regional buckets are highly
        recommended to co-locate compute (transcoders) and storage.
    *   *If VOD*: Multi-regional buckets are recommended for optimal global
        availability and delivery closer to end-users.

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Autoclass                   | https://cloud.google.com/storage/docs/autoclass
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Locations                   | https://cloud.google.com/storage/docs/locations
CORS                        | https://cloud.google.com/storage/docs/using-cors
Signed URLs                 | https://cloud.google.com/storage/docs/access-control/signed-urls
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
Soft Delete                 | https://cloud.google.com/storage/docs/soft-delete
Object Versioning           | https://cloud.google.com/storage/docs/object-versioning
Bucket IP Filtering         | https://cloud.google.com/storage/docs/ip-filtering-overview
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Hierarchical Namespace      | https://cloud.google.com/storage/docs/hns-overview
Storage Transfer Service    | https://cloud.google.com/storage-transfer/docs/overview
Cloud Audit Logging         | https://cloud.google.com/storage/docs/audit-logging
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
