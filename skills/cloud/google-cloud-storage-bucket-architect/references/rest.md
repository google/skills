# Cloud Storage JSON API Reference

> [!IMPORTANT]
>
> **DO NOT EXECUTE THESE COMMANDS AUTOMATICALLY.** Present the generated
> payloads and `curl` commands to the user and only execute them in Phase 3 if
> explicit confirmation is granted.

## Official Documentation Reference

*   [Cloud Storage JSON API Overview](https://cloud.google.com/storage/docs/json_api)
*   [Buckets Resource Reference](https://cloud.google.com/storage/docs/json_api/v1/buckets)
*   [Objects Resource Reference](https://cloud.google.com/storage/docs/json_api/v1/objects)

--------------------------------------------------------------------------------

## Translation Mapping Table

Draft Plan Field / Setting         | REST API Resource Field / Path                      | Notes / Action
:--------------------------------- | :-------------------------------------------------- | :-------------
**Bucket Name**                    | `name`                                              | String in request body. Must be globally unique.
**Project**                        | Query Parameter: `?project=[project-id]`            | Passed in the query string of the request URL.
**Location**                       | `location`                                          | E.g., `"us-central1"`, `"US"`, `"nam4"`. For zonal buckets, set to the region (e.g., `"us-east1"`).
**Placement**                      | `customPlacementConfig.dataLocations`               | Array of strings: `["us-east1", "us-west1"]` (custom dual-region) or `["us-east1-a"]` (zonal bucket). Omit for predefined dual-regions (`nam4`, `eur4`, `asia1`).
**Replication Speed (RPO)**        | `rpo`                                               | String: `"ASYNC_TURBO"` (for dual-region buckets).
**Storage Class**                  | `storageClass`                                      | `"STANDARD"`, `"NEARLINE"`, `"COLDLINE"`, `"ARCHIVE"`, `"RAPID"`.
**UBLA**                           | `iamConfiguration.uniformBucketLevelAccess.enabled` | Boolean. Always set to `true`.
**Public Access Prevention**       | `iamConfiguration.publicAccessPrevention`           | String: `"enforced"` or `"inherited"`.
**Soft Delete**                    | `softDeletePolicy.retentionDurationSeconds`         | Integer seconds: e.g., `604800` (7 days), `864000` (10 days). Set to `0` to disable.
**Object Versioning**              | `versioning.enabled`                                | Boolean. Enables/disables versioning.
**Encryption (CMEK)**              | `encryption.defaultKmsKeyName`                      | Full KMS key ID: `"projects/.../cryptoKeys/..."`.
**Restrict Encryption (CSEK)**     | `encryption.*EncryptionEnforcementConfig`           | Restricts encryption methods under `encryption`. See template below.
**Autoclass**                      | `autoclass.enabled`                                 | Boolean (`true` to enable; `storageClass` must be `"STANDARD"` or omitted).
**Hierarchical Namespace**         | `hierarchicalNamespace.enabled`                     | Boolean (`true` to enable).
**Labels**                         | `labels`                                            | JSON object of string key-value pairs (`{"k": "v"}`). Can be set directly on `POST` creation in REST.
**IP Filtering**                   | `ipFilter`                                          | Object defining IP/VPC rules. See template below.
**Lifecycle Policies (OLM)**       | `lifecycle.rule`                                    | Array of rule objects. See template below.
**CORS**                           | `cors`                                              | Array of CORS rule objects.
**Website Configuration**          | `website.mainPageSuffix` / `website.notFoundPage`   | Strings for index (`"index.html"`) and error (`"404.html"`) pages.
**Public IAM Policy**              | `storage.buckets.setIamPolicy`                      | Read-modify-write (`GET /iam` then `PUT /iam`) adding `allUsers` to `roles/storage.objectViewer`.
**Pub/Sub Notifications**          | `storage.notifications.insert`                      | `POST https://storage.googleapis.com/storage/v1/b/BUCKET_NAME/notificationConfigs`.
**Bucket Retention Period**        | `retentionPolicy.retentionPeriod`                   | Integer seconds (e.g., `7776000` for 90 days).
**Lock Bucket Retention Policy**   | `storage.buckets.lockRetentionPolicy`               | `POST .../b/BUCKET_NAME/lockRetentionPolicy?ifMetagenerationMatch=METAGENERATION`. **Irreversible.**
**Object Retention (Object Lock)** | Query Parameter: `enableObjectRetention=true`       | Creation-only (`buckets.insert`) query param (`?project=...&enableObjectRetention=true`); **permanently** enables object retention.
**Set Object Retention**           | Object `retention` property                         | `{"mode": "Locked", "retainUntilTime": "2030-12-31T23:59:59Z"}` (`"Locked"` or `"Unlocked"`) on object upload or `PATCH`.
**Rapid Cache**                    | `storage.anywhereCaches.insert`                     | `POST https://storage.googleapis.com/storage/v1/b/BUCKET_NAME/anywhereCaches`.

--------------------------------------------------------------------------------

## Helper Configuration Templates

### Encryption Enforcement, IP Filtering, Lifecycle, and CORS Snippets

Include only active top-level keys in your `POST`/`PATCH` body. Unlike
`gcloud`'s short root keys (`csekEnforcement`), the JSON API nests full
`*EncryptionEnforcementConfig` objects under `encryption`:

```json
{
  "encryption": {
    "googleManagedEncryptionEnforcementConfig": {"restrictionMode": "NotRestricted"},
    "customerManagedEncryptionEnforcementConfig": {"restrictionMode": "NotRestricted"},
    "customerSuppliedEncryptionEnforcementConfig": {"restrictionMode": "FullyRestricted"}
  },
  "ipFilter": {
    "mode": "Enabled",
    "allowAllServiceAgentAccess": true,
    "allowCrossOrgVpcs": false,
    "publicNetworkSource": {"allowedIpCidrRanges": ["192.0.2.0/24"]},
    "vpcNetworkSources": [
      {"network": "projects/PROJECT_ID/global/networks/NETWORK_NAME", "allowedIpCidrRanges": ["10.0.0.0/16"]}
    ]
  },
  "lifecycle": {
    "rule": [
      {"action": {"type": "AbortIncompleteMultipartUpload"}, "condition": {"age": 7}},
      {"action": {"type": "Delete"}, "condition": {"age": 365}}
    ]
  },
  "cors": [
    {
      "origin": ["https://example.appspot.com"],
      "method": ["GET", "PUT", "POST", "DELETE"],
      "responseHeader": ["Content-Type", "Authorization"],
      "maxAgeSeconds": 3600
    }
  ]
}
```

--------------------------------------------------------------------------------

## Executing REST Requests via cURL (Mandatory Attribution Header)

Every `curl` command MUST include
`Authorization: Bearer $(gcloud auth print-access-token)` (note:
`gcloud auth print-access-token` inside `curl` does NOT take the
`CLOUDSDK_METRICS_ENVIRONMENT` prefix) and the exact `User-Agent` header:

```bash
curl -X POST \
  "https://storage.googleapis.com/storage/v1/b?project=PROJECT_ID" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
  -H "Content-Type: application/json" \
  -d @body.json
```

--------------------------------------------------------------------------------

## REST API Request Examples

All requests below use the `curl` headers above (`Authorization`,
`User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)`,
`Content-Type: application/json`). Bucket creation uses
`POST https://storage.googleapis.com/storage/v1/b?project=PROJECT_ID`; bucket
updates use `PATCH https://storage.googleapis.com/storage/v1/b/BUCKET_NAME`.

### Example 1: Sensitive Data / Compliance (CMEK, CSEK Restricted, Autoclass, Soft Delete, Retention, Labels, OLM, IP Filter)

*(For a baseline secure bucket without CMEK/Autoclass/IP filter, include only
`name`, `location`, `storageClass`, `iamConfiguration`, `softDeletePolicy`, and
`encryption.customerSuppliedEncryptionEnforcementConfig`.)*

**Method/URL:**
`POST https://storage.googleapis.com/storage/v1/b?project=my-compliance-project`

```json
{
  "name": "my-compliance-pii-bucket",
  "location": "us-central1",
  "storageClass": "STANDARD",
  "iamConfiguration": {
    "uniformBucketLevelAccess": {"enabled": true},
    "publicAccessPrevention": "enforced"
  },
  "encryption": {
    "defaultKmsKeyName": "projects/my-kms-project/locations/us-central1/keyRings/my-keyring/cryptoKeys/my-key",
    "customerSuppliedEncryptionEnforcementConfig": {"restrictionMode": "FullyRestricted"},
    "customerManagedEncryptionEnforcementConfig": {"restrictionMode": "NotRestricted"},
    "googleManagedEncryptionEnforcementConfig": {"restrictionMode": "NotRestricted"}
  },
  "softDeletePolicy": {"retentionDurationSeconds": 604800},
  "retentionPolicy": {"retentionPeriod": 7776000},
  "autoclass": {"enabled": true},
  "labels": {"data-class": "pii", "owner": "security-team"},
  "lifecycle": {
    "rule": [{"action": {"type": "AbortIncompleteMultipartUpload"}, "condition": {"age": 7}}]
  },
  "ipFilter": {
    "mode": "Enabled",
    "allowAllServiceAgentAccess": true,
    "allowCrossOrgVpcs": false,
    "publicNetworkSource": {"allowedIpCidrRanges": ["192.0.2.0/24"]},
    "vpcNetworkSources": [
      {"network": "projects/my-project/global/networks/my-vpc-network", "allowedIpCidrRanges": ["10.0.0.0/16"]}
    ]
  }
}
```

*(Note: To permanently lock the retention policy, send an empty POST request to
`POST
https://storage.googleapis.com/storage/v1/b/my-compliance-pii-bucket/lockRetentionPolicy?ifMetagenerationMatch=METAGENERATION`.
Locking is irreversible.)*

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website Config, CORS, Versioning)

**1. Create Bucket
(`POST https://storage.googleapis.com/storage/v1/b?project=my-frontend-project`):**

```json
{
  "name": "www.my-company-site.com",
  "location": "US",
  "storageClass": "STANDARD",
  "iamConfiguration": {
    "uniformBucketLevelAccess": {"enabled": true},
    "publicAccessPrevention": "inherited"
  },
  "softDeletePolicy": {"retentionDurationSeconds": 604800},
  "website": {"mainPageSuffix": "index.html", "notFoundPage": "404.html"},
  "cors": [
    {"origin": ["*"], "method": ["GET", "HEAD", "OPTIONS"], "responseHeader": ["Content-Type"], "maxAgeSeconds": 3600}
  ],
  "versioning": {"enabled": true}
}
```

**2. Set Public Read Access (Read-Modify-Write `GET /iam` then `PUT /iam`):**

> [!WARNING]
>
> `PUT /iam` replaces the entire IAM policy. Always
> `GET https://storage.googleapis.com/storage/v1/b/www.my-company-site.com/iam`
> first, append the new binding to the existing root-level `bindings` array
> while preserving `etag` (do NOT wrap in `{"policy": ...}`), and `PUT` back to
> `https://storage.googleapis.com/storage/v1/b/www.my-company-site.com/iam`:

```json
{
  "kind": "storage#policy",
  "etag": "CAE=",
  "bindings": ["<...existing projectOwner/Viewer bindings from GET...>", {"role": "roles/storage.objectViewer", "members": ["allUsers"]}]
}
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

**Method/URL:**
`POST https://storage.googleapis.com/storage/v1/b?project=my-ai-project`

```json
{
  "name": "my-training-checkpoints-us-east1-b",
  "location": "us-east1",
  "storageClass": "RAPID",
  "customPlacementConfig": {"dataLocations": ["us-east1-b"]},
  "iamConfiguration": {
    "uniformBucketLevelAccess": {"enabled": true},
    "publicAccessPrevention": "enforced"
  },
  "hierarchicalNamespace": {"enabled": true},
  "softDeletePolicy": {"retentionDurationSeconds": 0},
  "lifecycle": {
    "rule": [{"action": {"type": "Delete"}, "condition": {"age": 14}}]
  }
}
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

**1. Create Bucket (`POST
https://storage.googleapis.com/storage/v1/b?project=my-legal-project&enableObjectRetention=true`):**

```json
{
  "name": "my-legal-archive-bucket",
  "location": "us-east1",
  "storageClass": "ARCHIVE",
  "iamConfiguration": {
    "uniformBucketLevelAccess": {"enabled": true},
    "publicAccessPrevention": "enforced"
  },
  "encryption": {
    "defaultKmsKeyName": "projects/my-kms-project/locations/us-east1/keyRings/my-keyring/cryptoKeys/my-key"
  },
  "softDeletePolicy": {"retentionDurationSeconds": 604800},
  "labels": {"compliance-type": "regulatory", "retention-period": "7y"},
  "lifecycle": {
    "rule": [{"action": {"type": "Delete"}, "condition": {"age": 2555}}]
  }
}
```

**2. Set Object Retention on Upload or Existing Object:**

> [!CAUTION]
>
> Setting object retention `mode` to `"Locked"` is permanent and irreversible.
> Once locked, retention cannot be removed or shortened (only extended).

*   **On Upload (`POST
    https://storage.googleapis.com/upload/storage/v1/b/my-legal-archive-bucket/o?uploadType=multipart`)**:
    Metadata JSON part (`"Unlocked"` or `"Locked"`): `{"name":
    "compliance_report_2026.pdf", "retention": {"mode": "Unlocked",
    "retainUntilTime": "2030-12-31T23:59:59Z"}}`.
*   **On Existing Object (`PATCH
    https://storage.googleapis.com/storage/v1/b/my-legal-archive-bucket/o/OBJECT_NAME?overrideUnlockedRetention=true`)**:
    Body `{"retention": {"mode": "Locked", "retainUntilTime":
    "2030-12-31T23:59:59Z"}}`. You MUST append `?overrideUnlockedRetention=true`
    when changing `Unlocked` to `Locked`, shortening `retainUntilTime`, or
    removing retention, or the request will fail.
