# Static Website Hosting

This reference document outlines the configuration mapping and architecture
recommendation for Cloud Storage buckets configured to host static websites.

## Description

The user is deploying a static website (HTML, CSS, JavaScript, media assets)
directly to Cloud Storage. The site needs to be publicly accessible, support
custom domain mapping, scale automatically for viral traffic spikes, and serve
assets with low latency without backend servers.

## Bucket Configuration Plan Mapping

The following table maps the Static Website Hosting use case to specific Cloud
Storage features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status                   | Recommendations & Implementation Details
:------------------------------------- | :----------------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended       | **Standard** Storage Class.<br><br>Required for web serving to ensure immediate, low-latency, and high-throughput asset delivery. Colder tiers must be avoided due to retrieval fees.
**Bucket Type**                        | Highly Recommended       | **Multi-Regional (MR)**. Distributes website content globally to ensure high availability and low latency for diverse user locations.
**CORS**                               | Highly Recommended       | Configure CORS if the site loads assets from other origins, or if assets from this bucket are queried by external frontends.
**Website Settings**                   | **Required**             | **Configure Website Configuration.** Set the `mainPageSuffix` (e.g. `index.html`) and `notFoundPage` (e.g. `404.html`) to handle root requests and errors.
**Uniform Bucket-Level Access (UBLA)** | **Required**             | **Must be enabled.** Standardizes IAM permissions across the bucket.
**Public Access Prevention (PAP)**     | **Disabled** (Exception) | **Must be set to "inherited" / Disabled.** Public access must be allowed to serve web traffic. Grant `roles/storage.objectViewer` to `allUsers` to make assets publicly accessible.
**Soft Delete**                        | Good to Have             | Enabled as a critical rollback mechanism. Helps restore website files quickly if deleted by broken build/deploy scripts.
**Object Versioning**                  | Good to Have             | Alternative to Soft Delete. Allows rolling back bad deployments to a prior known good state, but requires OLM to prune history.
**IP Filtering**                       | Optional                 | Use only if you must limit access to specific IP ranges (including countries or corporate networks, e.g. staging site).
**Object Lifecycle Management (OLM)**  | Highly Recommended       | If Versioning is enabled, set lifecycle rules to prune non-current versions (e.g., after 30 days) to prevent old builds from increasing storage bills. Recommend standard OLM rule:<br>Transition to `ARCHIVE` after 365 days.
**Labels & Tagging**                   | Good to Have             | Apply environment tags (e.g., `{"environment": "production"}`).
**Storage Transfer Service (STS)**     | Good to Have             | Replicate site assets closer to compute regions using STS.
**Cloud Logging**                      | Highly Recommended       | Enable logs to analyze web usage stats, referral paths, and user-agent data.
**Cloud Monitoring**                   | Highly Recommended       | Setup alerts on public egress, total operations, and error rates (e.g., 404/503).
**Pub/Sub Notifications**              | Good to Have             | Trigger downstream workflows (such as clearing a CDN cache) whenever `index.html` or other assets are updated.

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Locations                   | https://cloud.google.com/storage/docs/locations
CORS                        | https://cloud.google.com/storage/docs/using-cors
Hosting Static Website      | https://cloud.google.com/storage/docs/hosting-static-website
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
Public Access Prevention    | https://cloud.google.com/storage/docs/public-access-prevention
Make Bucket Public          | https://cloud.google.com/storage/docs/access-control/making-data-public
Soft Delete                 | https://cloud.google.com/storage/docs/soft-delete
Object Versioning           | https://cloud.google.com/storage/docs/object-versioning
Bucket IP Filtering         | https://cloud.google.com/storage/docs/ip-filtering-overview
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Bucket Labels               | https://cloud.google.com/storage/docs/using-bucket-labels
Storage Transfer Service    | https://cloud.google.com/storage-transfer/docs/overview
Cloud Audit Logging         | https://cloud.google.com/storage/docs/audit-logging
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
Pub/Sub Notifications       | https://cloud.google.com/storage/docs/pubsub-notifications
