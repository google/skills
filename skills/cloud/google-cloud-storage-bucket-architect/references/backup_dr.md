# Backup and Disaster Recovery

This reference document outlines the secure-by-default, highly durable
configuration mapping and architecture recommendation for Cloud Storage buckets
serving as the storage backend for database dumps, virtual machine snapshots,
and system backups.

## Description

The user is storing mission-critical backups and disaster recovery data. This
workload requires high durability, protection against ransomware and accidental
deletion (WORM/Soft Delete), and automated cross-region replication to maintain
recovery objectives (RTO/RPO). Backups are typically written once and read
infrequently, but require rapid access when a restore is triggered.

## Bucket Configuration Plan Mapping

The following table maps the Backup and Disaster Recovery to specific Cloud
Storage features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status             | Recommendations & Implementation Details
:------------------------------------- | :----------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended | **Nearline**, **Coldline**, or **Archive** Storage Class.<br><br>Choose based on retention duration and restore probability. Nearline is ideal for daily/weekly backups (30-day minimum), Coldline for monthly archives (90-day minimum), and Archive for annual backups (365-day minimum).
**Bucket Type**                        | Highly Recommended | **Regional** bucket type. Combine with cross-bucket replication using Storage Transfer Service (STS) to replicate to a disaster recovery region.<br><br>*Note: Dual-Region or Multi-Region buckets are not recommended for backups due to higher cost and lack of flexibility. If the user requests dual-region (e.g. nam4), explicitly advise against it and recommend Regional + STS instead.*
**Signed URLs**                        | Not Recommended    | Typically not required for backup workloads.
**CORS**                               | Not Recommended    | Typically not required for backup workloads.
**Uniform Bucket-Level Access (UBLA)** | **Required**       | **Must be enabled.** Standardizes IAM permissions across the bucket, disabling legacy ACLs.
**Public Access Prevention (PAP)**     | **Required**       | **Must be enforced.** Disallows public access.
**Encryption (CMEK)**                  | Highly Recommended | **Customer-Managed Encryption Keys (CMEK)** via Cloud KMS.<br><br>Use KMS Autokey for automated provisioning, or guide the user to assign a key.
**Soft Delete**                        | Highly Recommended | **Enabled (default 7 days).** Essential baseline defense to recover from accidental deletions by scripts or administrative errors.
**Object Versioning**                  | Good to Have       | Suggest as an alternative to Soft Delete for recovery.
**Data Retention (WORM)**              | Good to Have       | Prompt the user to configure a Retention Policy (Bucket Lock or Object Lock) if immutability is required for ransomware protection or compliance.<br><br>**Warning: Lock mode is permanent and irreversible.**
**IP Filtering**                       | Good to Have       | Restrict access exclusively to trusted corporate data center IPs or secure office perimeters.
**Object Lifecycle Management (OLM)**  | Not Recommended    | Start with the correct storage class. OLM is generally not recommended for transitioning backups unless specific lifecycle needs exist.
**Labels & Tagging**                   | Highly Recommended | **Mandatory** bucket-level tagging (e.g., `{"environment": "production"}` and `{"app": "core-db-backup"}`) to map and audit storage spend.
**Storage Intelligence**               | Good to Have       | Use Storage Insights to monitor backup volume growth and security status.
**Storage Transfer Service (STS)**     | Highly Recommended | Use STS for automated, secure cross-bucket replication to a secondary DR region to simplify disaster recovery.
**Cloud Logging**                      | Highly Recommended | Enable Cloud Logging for troubleshooting network timeouts or throughput bottlenecks during massive backup transfers.
**Cloud Monitoring**                   | Highly Recommended | Track API call counts and storage limits. Configure alerts to fire if a backup bucket registers zero write activity within 24 hours.

## Project-Level Security Checks & Recommendations

Before bucket creation, verify the following project-level configurations:

1.  **Restrict Sharing Org Policy**: Ensure
    `constraints/iam.allowedPolicyMemberDomains` is configured to restrict
    sharing outside of authorized organizational domains.
2.  **Access Transparency**: Ensure Access Transparency is enabled on the
    project to audit Google administrator access.
3.  **Location Org Policy**: Check `constraints/gcp.resourceLocations` to ensure
    bucket creation conforms to the organization's regional residency
    guidelines.
4.  **Cloud Audit Logging**: Ensure Cloud Audit Logging is enabled for the
    project to maintain an audit trail.

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Storage Classes             | https://cloud.google.com/storage/docs/storage-classes
Locations                   | https://cloud.google.com/storage/docs/locations
Signed URLs                 | https://cloud.google.com/storage/docs/access-control/signed-urls
CORS                        | https://cloud.google.com/storage/docs/using-cors
Uniform Bucket-Level Access | https://cloud.google.com/storage/docs/uniform-bucket-level-access
Public Access Prevention    | https://cloud.google.com/storage/docs/public-access-prevention
CMEK                        | https://cloud.google.com/storage/docs/encryption/customer-managed-keys
KMS Autokey                 | https://cloud.google.com/kms/docs/autokey-overview
Soft Delete                 | https://cloud.google.com/storage/docs/soft-delete
Object Versioning           | https://cloud.google.com/storage/docs/object-versioning
Bucket Lock                 | https://cloud.google.com/storage/docs/bucket-lock
Object Lock                 | https://cloud.google.com/storage/docs/object-lock
Bucket IP Filtering         | https://cloud.google.com/storage/docs/ip-filtering-overview
Lifecycle Management        | https://cloud.google.com/storage/docs/lifecycle
Bucket Labels               | https://cloud.google.com/storage/docs/using-bucket-labels
Storage Insights            | https://cloud.google.com/storage/docs/insights/inventory-reports
Storage Transfer Service    | https://cloud.google.com/storage-transfer/docs/overview
Cloud Audit Logging         | https://cloud.google.com/storage/docs/audit-logging
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
