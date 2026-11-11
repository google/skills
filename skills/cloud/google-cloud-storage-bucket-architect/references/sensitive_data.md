# Sensitive Data & Compliance (PII, HIPAA, Finance)

This reference document outlines the secure-by-default configuration mapping and
architecture recommendation for Cloud Storage buckets designed to host highly
regulated, sensitive data (such as Personally Identifiable Information (PII),
healthcare records subject to HIPAA, or financial transaction logs).

## Description

The user is storing highly regulated, sensitive data and needs to protect it
against unauthorized public exposure and data exfiltration while maintaining
auditability. This workload typically involves microservice applications or data
pipelines processing data within a secure corporate boundary.

## Bucket Configuration Plan Mapping

The following table maps the Sensitive Data use case to specific Cloud Storage
features and details their recommendation status. See
[Official Documentation References](#official-documentation-references) below
for feature links if further reference is needed (do not fetch routinely).

Cloud Storage Feature / Setting        | Status                     | Recommendations & Implementation Details
:------------------------------------- | :------------------------- | :---------------------------------------
**Storage Class**                      | Highly Recommended         | **Autoclass** or **Standard** Storage Class.<br><br>Autoclass automatically moves cold data to lower-cost tiers without retrieval fees. Standard storage is recommended if data requires frequent, immediate, low-latency access.
**Bucket Type**                        | Highly Recommended         | **Regional** bucket type. Choosing a single region allows co-locating storage with compute resources to avoid latency and egress costs.
**Signed URLs**                        | Optional / Not Recommended | Avoid direct access. Restrict access through backend microservices or require signed URLs only if clients must write directly.
**CORS**                               | Optional / Not Recommended | Disable or restrict to specific trusted internal domains to prevent cross-origin web exfiltration.
**Uniform Bucket-Level Access (UBLA)** | **Required**               | **Must be enabled.** Prevents legacy object-level ACLs from overriding bucket-level IAM policies.
**Public Access Prevention (PAP)**     | **Required**               | **Must be enforced.** Disallows public access via `allUsers` or `allAuthenticatedUsers`.
**Encryption (CMEK)**                  | Highly Recommended         | **Customer-Managed Encryption Keys (CMEK)** via Cloud KMS.<br><br>Use KMS Autokey to dynamically provision keys on bucket creation, or prompt the user for a KMS key path. Do not use Customer-Supplied Encryption Keys (CSEK).
**Soft Delete**                        | Highly Recommended         | **Enabled (default 7 days).** Ensures data can be recovered within the retention window if accidentally deleted by automated scripts or administrative bugs.
**Object Versioning**                  | Good to Have               | Suggest as an alternative to prevent data modification/accidental deletes only if Soft Delete is disabled.
**Data Retention (WORM)**              | Good to Have               | Prompt the user to configure a Retention Policy (Bucket Lock or Object Lock) if regulatory compliance mandates immutability.<br><br>**Warning:** Lock mode is permanent and irreversible.
**IP Filtering**                       | Good to Have               | Limit access to the bucket to specific CIDR ranges or VPC networks (e.g. corporate SOC perimeters).
**Object Lifecycle Management (OLM)**  | Highly Recommended         | Configure rules to automatically abort incomplete multipart uploads (`abortIncompleteMultipartUpload`) to avoid hidden storage costs. If Autoclass is disabled, transition objects to `ARCHIVE` after 365 days.
**Labels & Tagging**                   | Highly Recommended         | **Mandatory** bucket-level tagging (e.g., `{"data-class": "pii"}` and `{"owner": "security-team"}`) to ensure proper data classification and cost-center tracking.
**Storage Transfer Service (STS)**     | Good to Have               | Consider cross-bucket replication via STS to maintain an independent, secure copy of data.
**Cloud Logging**                      | Good to Have               | Enable Cloud Audit Logging (Data Access & Admin Activity logs) for audit trials.
**Cloud Monitoring**                   | Good to Have               | Monitor operational health and watch for spikes in error rates (e.g., 404, 503).

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

## Official Documentation References

Feature / Topic             | Documentation Link
:-------------------------- | :-----------------
Autoclass                   | https://cloud.google.com/storage/docs/autoclass
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
Storage Transfer Service    | https://cloud.google.com/storage-transfer/docs/overview
Cloud Audit Logging         | https://cloud.google.com/storage/docs/audit-logging
Cloud Monitoring            | https://cloud.google.com/storage/docs/monitoring
