# Long-Term Archive & Regulatory Compliance

This reference document outlines the secure-by-default, cost-effective
configuration mapping and architecture recommendation for Cloud Storage buckets
optimized for long-term archiving and regulatory compliance mandates.

## Description

The user is retaining data (such as financial statements, medical records, tax
documents, or corporate legal logs) for legal or regulatory requirements
(typically 7-10+ years). The data is accessed very infrequently, but its
integrity must be guaranteed, and it must be protected against accidental or
premature deletion (immutability).

## Bucket Configuration Plan Mapping

The following table maps the Long-Term Archive & Compliance use case to specific
Cloud Storage features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status             | Recommendations & Implementation Details
:------------------------------------- | :----------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended | **Coldline** or **Archive** Storage Class.<br><br>Archive storage offers the lowest cost per gigabyte, ideal for data kept as a legal requirement that may never be read. Beware of high retrieval and early deletion fees (e.g. minimum 365 days retention for Archive).
**Bucket Type**                        | Highly Recommended | **Regional** or **Dual-Regional** bucket configuration. Multi-regional configurations should be avoided if national laws mandate physical data residency boundaries.
**Signed URLs**                        | Good to Have       | Gated write access only; restrict public URLs entirely.
**Uniform Bucket-Level Access (UBLA)** | **Required**       | **Must be enabled.** Standardizes administrative access control across the bucket.
**Public Access Prevention (PAP)**     | **Required**       | **Must be enforced.** Disallows public read permissions.
**Encryption (CMEK)**                  | Highly Recommended | **CMEK via KMS** is standard for compliance workloads. Use KMS Autokey for automated keys, or prompt the user for key paths.
**IP Filtering**                       | Good to Have       | Limit bucket administration endpoints exclusively to verified corporate office IPs or secure VPN ranges.
**Retention Policy (WORM)**            | Good to Have       | Configure Cloud Storage **Bucket Lock** or **Object Lock** to enforce immutability (Write Once, Read Many).<br><br>**Warning: Locking the retention policy is irreversible. Objects cannot be deleted by anyone, including owners or Google Cloud Support, until the retention period expires.**
**Object Lifecycle Management (OLM)**  | Highly Recommended | Configure lifecycle rules to automatically purge expired archive records (e.g. delete after 7 years / 2555 days) to mitigate liability and storage costs.
**Labels & Tagging**                   | Highly Recommended | Apply governance metadata tags (e.g. `{"compliance-type": "hipaa"}` or `{"retention-period": "7-years"}`) for cost-center and policy tracking.
**Storage Intelligence**               | Good to Have       | Use Storage Insights Inventory Reports to track record age, verify compliance counts, and manage data wipes.
**Regional Endpoints**                 | Highly Recommended | Enforce localized control planes to satisfy sovereignty requirements where data operations must stay within regional borders.
**Storage Transfer Service (STS)**     | Good to Have       | Use STS for inter-regional migrations, backup, or ITAR compliance transfers.
**SFTP**                               | Good to Have       | Implement secure SFTP transfers if legacy compliance networks or mainframes upload transaction logs directly.
**Cloud Logging**                      | Highly Recommended | Enable Cloud Storage Audit Logs (Data Access & Admin Activity) to maintain a complete, audit-safe record of data reads, writes, and config updates.
**Cloud Monitoring**                   | Good to Have       | Monitor capacity trends and set alert systems to fire if unexpected large drops in object count or volume occur.

## Key Pre-Deployment Questions to Ask:

1.  **What specific compliance standard governs this data (e.g., HIPAA, SEC Rule
    17a-4, GDPR)?**
2.  **Do you require an irreversible compliance lock (Bucket/Object Lock)?**
    *   *If Yes*: Explain that once locked, even the Project Administrator
        cannot shorten the policy or delete the data. Confirm if they wish to
        proceed with "Locked" or "Unlocked" status.
3.  **What is the exact data retention duration (e.g., 7 years)?**

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Locations                   | https://cloud.google.com/storage/docs/locations
Signed URLs                 | https://cloud.google.com/storage/docs/access-control/signed-urls
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
Public Access Prevention    | https://cloud.google.com/storage/docs/public-access-prevention
CMEK                        | https://cloud.google.com/storage/docs/encryption/customer-managed-keys
Bucket IP Filtering         | https://cloud.google.com/storage/docs/ip-filtering-overview
Bucket Lock                 | https://cloud.google.com/storage/docs/bucket-lock
Object Lock                 | https://cloud.google.com/storage/docs/object-lock
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Bucket Labels               | https://cloud.google.com/storage/docs/using-bucket-labels
Inventory Reports           | https://cloud.google.com/storage/docs/insights/inventory-reports
Storage Transfer Service    | https://cloud.google.com/storage-transfer/docs/overview
SFTP Gateway (SFTP)         | https://cloud.google.com/integration-connectors/docs/connectors/sftp/configure
Cloud Audit Logging         | https://cloud.google.com/storage/docs/audit-logging
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
