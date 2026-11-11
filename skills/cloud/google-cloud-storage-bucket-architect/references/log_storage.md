# Log Storage

This reference document outlines the configuration mapping and architecture
recommendation for Cloud Storage buckets optimized for log storage and
ingestion.

## Description

The user is storing high-volume application logs, VPC flow logs, or audit trail
dumps that are typically ingested by SIEM (Security Information and Event
Management) tools or parsed during operational troubleshooting. The primary
goals are minimizing write ingestion costs and eliminating inter-regional
network egress charges, while optimizing storage costs for logs that naturally
grow cold.

## Bucket Configuration Plan Mapping

The following table maps the Log Storage use case to specific Cloud Storage
features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status             | Recommendations & Implementation Details
:------------------------------------- | :----------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended | **Autoclass** Storage Class.<br><br>Raw log ingestion generates massive write operations. Autoclass is ideal since standard writes carry no cost penalty, and older log chunks are automatically transitioned to colder classes as they age.
**Bucket Type**                        | Highly Recommended | **Regional (R)** bucket type.<br><br>Ensure the bucket region matches the exact region hosting your compute resources and SIEM tools. This completely eliminates inter-regional network egress fees during ingestion and analytical querying.
**Uniform Bucket-Level Access (UBLA)** | **Required**       | **Must be enabled.** Standardizes IAM permissions across the bucket.
**Public Access Prevention (PAP)**     | **Required**       | **Must be enforced.** Logs contain sensitive operational details and must never be exposed publicly.
**Encryption (CMEK)**                  | Highly Recommended | Configure **CMEK via Cloud KMS** by default. Use KMS Autokey for automation, or prompt the user.
**IP Filtering**                       | Good to Have       | Limit administrative access and raw log export operations to trusted security operations center (SOC) IP ranges.
**Soft Delete**                        | Optional           | Neither highly recommended nor required, but useful to share with the customer as an essential defensive layer to recover logging windows if an administrative script executes a mass purge command.
**Object Lifecycle Management (OLM)**  | Highly Recommended | Recommended if Autoclass is disabled. Establish rules to transition logs to `ARCHIVE` after 365 days.
**Labels & Tagging**                   | Good to Have       | Apply tagging (e.g. `{"environment": "production"}` and `{"cost-center": "security-ops"}`) to parse out high-volume cloud infrastructure spend.
**Storage Intelligence**               | Good to Have       | Monitor data accumulation rates using Storage Insights to identify which microservices are dominating storage metrics.
**Cloud Monitoring**                   | Highly Recommended | **Configure Cloud Monitoring** to build dashboards tracking storage API call limits, ingestion errors, or spikes in daily write volumes.

## Key Pre-Deployment Questions to Ask:

1.  **In which region are your compute workloads and analytical SIEM tools
    hosted?**
    *   *Recommendation*: Co-locate the bucket in the same region to eliminate
        egress fees.
2.  **What is the typical time window before logs are considered cold or no
    longer queryable?**

## Mandatory Recommendations to Include in the Design Plan:

*   **Cloud Monitoring**: You MUST recommend configuring Cloud Monitoring to
    track Cloud Storage API limits, ingestion errors, and daily write volumes.

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Autoclass                   | https://cloud.google.com/storage/docs/autoclass
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Locations                   | https://cloud.google.com/storage/docs/locations
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
Public Access Prevention    | https://cloud.google.com/storage/docs/public-access-prevention
CMEK                        | https://cloud.google.com/storage/docs/encryption/customer-managed-keys
Bucket IP Filtering         | https://cloud.google.com/storage/docs/ip-filtering-overview
Soft Delete                 | https://cloud.google.com/storage/docs/soft-delete
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Bucket Labels               | https://cloud.google.com/storage/docs/using-bucket-labels
Inventory Reports           | https://cloud.google.com/storage/docs/insights/inventory-reports
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
