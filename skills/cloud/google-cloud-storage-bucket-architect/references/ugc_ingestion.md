# Direct User-Generated Content (UGC) Ingestion

This reference document outlines the secure-by-default configuration mapping and
architecture recommendation for Cloud Storage buckets receiving direct
client-side uploads from user applications (mobile apps, web browsers, etc.)
bypassing backend servers.

## Description

The user is building a mobile or web application where end-users upload heavy
files (such as profile pictures, documents, or video clips) directly to a Cloud
Storage bucket. This is achieved using Signed URLs to authorize uploads and CORS
configuration to allow browser-based calls, avoiding network bottlenecking on
the application's backend web servers.

## Bucket Configuration Plan Mapping

The following table maps the Direct UGC Ingestion use case to specific Cloud
Storage features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status             | Recommendations & Implementation Details
:------------------------------------- | :----------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended | **Autoclass** or **Standard** Storage Class.<br><br>Standard storage is recommended if users frequently view uploaded content immediately. Autoclass is ideal if files naturally go cold over time, avoiding retrieval fee traps.
**Bucket Type**                        | Highly Recommended | **Regional** bucket type. Align storage region with application compute to minimize latency. Create multiple regional buckets if the user base is globally dispersed.
**Signed URLs**                        | **Required**       | **Use Signed URLs** to delegate time-limited read/write access to clients, keeping the bucket secure while offloading traffic from backend servers.
**CORS**                               | **Required**       | **Configure CORS** to allow web applications hosted on custom domains to perform client-side uploads and load resources directly.
**Uniform Bucket-Level Access (UBLA)** | **Required**       | **Must be enabled.** Standardizes IAM permissions across the bucket, disabling granular legacy ACLs.
**Encryption (CMEK)**                  | Good to Have       | Recommend Customer-Managed Encryption Keys (CMEK) primarily for B2B multi-tenant environments with strict compliance mandates.
**Soft Delete**                        | Highly Recommended | **Enabled (default 7 days).** Provides a safety fallback to recover user data from accidental deletions or compromise, without regulatory locking.
**Object Versioning**                  | Good to Have       | Recommend only if users frequently overwrite files of identical names and collaborative history is needed, but govern with strict OLM to control cost.
**IP Filtering**                       | Good to Have       | Restrict admin API endpoints and internal export operations to trusted NAT IPs.
**Object Lifecycle Management (OLM)**  | Highly Recommended | **Enable abortIncompleteMultipartUpload** to clean up abandoned, incomplete client uploads. If Autoclass is disabled, automatically transition older, unaccessed user data to standard cold classes (e.g., transition to `ARCHIVE` after 365 days).
**Labels & Tagging**                   | Good to Have       | Apply organizational metadata tags (e.g. `{"data-class": "ugc"}`) to classify files.
**Storage Intelligence**               | Good to Have       | Use Storage Insights Inventory Reports to track upload scales, distribution statistics, and file counts across massive environments.
**Storage Transfer Service (STS)**     | Good to Have       | Replicate data to backup regions or move ingested data to processing clusters.
**Cloud Logging**                      | Good to Have       | Enable audit logging for tracing client-side errors, upload failures, and CORS anomalies.
**Cloud Monitoring**                   | Highly Recommended | Setup alerts on application error rates (4xx/5xx codes), client quota usage, and volume changes.
**Pub/Sub Notifications**              | Good to Have       | Trigger downstream processing (e.g., malware scanning, image resizing, indexing) automatically when a new object is finalized.

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Autoclass                   | https://cloud.google.com/storage/docs/autoclass
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Locations                   | https://cloud.google.com/storage/docs/locations
Signed URLs                 | https://cloud.google.com/storage/docs/access-control/signed-urls
CORS                        | https://cloud.google.com/storage/docs/using-cors
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
CMEK                        | https://cloud.google.com/storage/docs/encryption/customer-managed-keys
Soft Delete                 | https://cloud.google.com/storage/docs/soft-delete
Object Versioning           | https://cloud.google.com/storage/docs/object-versioning
Bucket IP Filtering         | https://cloud.google.com/storage/docs/ip-filtering-overview
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Bucket Labels               | https://cloud.google.com/storage/docs/using-bucket-labels
Inventory Reports           | https://cloud.google.com/storage/docs/insights/inventory-reports
Storage Transfer Service    | https://cloud.google.com/storage-transfer/docs/overview
Cloud Audit Logging         | https://cloud.google.com/storage/docs/audit-logging
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
Pub/Sub Notifications       | https://cloud.google.com/storage/docs/pubsub-notifications
