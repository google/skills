# C++ SDK Reference & Examples

This guide translates a **Draft Bucket Creation Plan** (from Phase 2) into the
official Google Cloud Storage C++ client library
(`google/cloud/storage/client.h`).

*   [Cloud Storage C++ Client Library](https://cloud.google.com/cpp/docs/reference/storage/latest)

## Version Requirements

> [!IMPORTANT]
>
> **Encryption Enforcement Config**
> (`customer_supplied_encryption_enforcement_config`) requires the C++ Cloud
> Storage SDK version **2.46.0** or higher. If using a version below 2.46.0,
> configure this setting via the [REST API](rest.md), [gcloud](gcloud.md), or
> [Terraform](terraform.md).

## Translation Mapping Table

Draft Plan Field / Setting          | C++ SDK Feature / Attribute (`::google::cloud::storage`)
:---------------------------------- | :-------------------------------------------------------
**Client Initialization**           | `namespace gcs = ::google::cloud::storage; auto client = gcs::Client();`
**Bucket Name & Project Creation**  | `client.CreateBucket(bucket_name, std::move(metadata), gcs::OverrideDefaultProject(project_id))`
**Location**                        | `metadata.set_location("us-central1")`
**Placement (Dual-Region / Zonal)** | `metadata.set_custom_placement_config(gcs::BucketCustomPlacementConfig{{"us-east1-b"}})`
**Replication Speed (RPO)**         | `metadata.set_rpo("ASYNC_TURBO")`
**Storage Class**                   | `metadata.set_storage_class(gcs::storage_class::Standard())` (or `Nearline()`, `Coldline()`, `Archive()`, `"RAPID"`)
**UBLA**                            | `gcs::BucketIamConfiguration iam_config; iam_config.uniform_bucket_level_access = gcs::UniformBucketLevelAccess{true, {}}; metadata.set_iam_configuration(iam_config)`
**Public Access Prevention**        | `iam_config.public_access_prevention = gcs::PublicAccessPreventionEnforced()` (or `gcs::PublicAccessPreventionInherited()`; pass via `metadata.set_iam_configuration(iam_config)`)
**Soft Delete**                     | `metadata.set_soft_delete_policy(std::chrono::seconds(7 * 24 * 3600))` (`std::chrono::seconds(0)` to disable)
**Object Versioning**               | `metadata.set_versioning(gcs::BucketVersioning{true})` (or `metadata.enable_versioning()`)
**Encryption (CMEK)**               | `gcs::BucketEncryption encryption; encryption.default_kms_key_name = kms_key; metadata.set_encryption(encryption)`
**Restrict Encryption (CSEK)**      | `encryption.customer_supplied_encryption_enforcement_config.restriction_mode = "FullyRestricted"` (**v2.46.0+**)
**Autoclass**                       | `metadata.set_autoclass(gcs::BucketAutoclass{true})`
**Hierarchical Namespace**          | `metadata.set_hierarchical_namespace(gcs::BucketHierarchicalNamespace{true})`
**Labels**                          | `metadata.upsert_label("key", "value")`
**IP Filtering**                    | *Not exposed in C++ client library* (use [REST API](rest.md), [gcloud](gcloud.md), or [Terraform](terraform.md))
**Allow Cross-Org VPCs**            | *Not exposed in C++ client library* (use [REST API](rest.md), [gcloud](gcloud.md), or [Terraform](terraform.md))
**Lifecycle Policies (OLM)**        | `metadata.set_lifecycle(gcs::BucketLifecycle{{gcs::LifecycleRule(condition, action)}})`
**CORS**                            | `metadata.set_cors({gcs::CorsEntry{3600, {"GET", "HEAD"}, {"*"}, {"Content-Type"}}})`
**Website Configuration**           | `metadata.set_website(gcs::BucketWebsite{"index.html", "404.html"})`
**Public IAM Policy**               | `client.GetNativeBucketIamPolicy(bucket_name, gcs::RequestedPolicyVersion(3))` -> append `allUsers` -> `client.SetNativeBucketIamPolicy(...)`
**Pub/Sub Notifications**           | `client.CreateNotification(bucket_name, topic_name, gcs::payload_format::JsonApiV1(), gcs::NotificationMetadata())`
**Bucket Retention Period**         | `metadata.set_retention_policy(std::chrono::seconds(90 * 24 * 3600))`
**Lock Bucket Retention Policy**    | `client.LockBucketRetentionPolicy(bucket_name, metadata->metageneration())` (**irreversible**)
**Object Retention (Object Lock)**  | `client.CreateBucket(bucket_name, std::move(metadata), gcs::EnableObjectRetention(true), gcs::OverrideDefaultProject(project_id))`
**Set Object Retention**            | `gcs::WithObjectMetadata(gcs::ObjectMetadata{}.set_retention(gcs::ObjectRetention{gcs::ObjectRetentionLocked(), retain_until}))` (or `gcs::ObjectRetentionUnlocked()`; on `client.PatchObject`, pass `gcs::OverrideUnlockedRetention(true)` to shorten/remove/lock `Unlocked`)
**Rapid Cache**                     | `StorageControlClient::CreateAnywhereCache` (`google/cloud/storagecontrol/v2/storage_control_client.h`)

--------------------------------------------------------------------------------

## C++ SDK Examples

### Example 1: Sensitive Data / Compliance (UBLA, PAP, CMEK, CSEK Restricted, Soft Delete, Retention, Autoclass, Labels, OLM)

*(For a baseline secure GMEK bucket without CMEK, keep `STANDARD`, UBLA,
enforced PAP, 7-day Soft Delete, `gcs::OverrideDefaultProject(project_id)`, and
`.set_encryption(encryption)` with
`customer_supplied_encryption_enforcement_config.restriction_mode =
"FullyRestricted"`, while omitting `default_kms_key_name` and unused optional
calls.)*

```cpp
#include "google/cloud/storage/client.h"
#include <chrono>
#include <string>
#include <utility>

namespace gcs = ::google::cloud::storage;
using ::google::cloud::StatusOr;

StatusOr<gcs::BucketMetadata> CreateComplianceBucket(gcs::Client client,
                                                     std::string const& project_id,
                                                     std::string const& bucket_name,
                                                     std::string const& kms_key) {
  gcs::BucketIamConfiguration iam_config;
  iam_config.uniform_bucket_level_access = gcs::UniformBucketLevelAccess{true, {}};
  iam_config.public_access_prevention = gcs::PublicAccessPreventionEnforced();

  gcs::BucketEncryption encryption;
  encryption.default_kms_key_name = kms_key;  // Omit for standard GMEK buckets while keeping CSEK FullyRestricted below
  // Enforcement config fields require google-cloud-cpp >= 2.46.0
  encryption.customer_supplied_encryption_enforcement_config.restriction_mode = "FullyRestricted";
  encryption.customer_managed_encryption_enforcement_config.restriction_mode = "NotRestricted";
  encryption.google_managed_encryption_enforcement_config.restriction_mode = "NotRestricted";

  gcs::BucketLifecycle lifecycle;
  lifecycle.rule = {
      gcs::LifecycleRule(
          gcs::LifecycleRule::MaxAge(7),
          gcs::LifecycleRule::AbortIncompleteMultipartUpload()
      )
  };

  gcs::BucketMetadata metadata = gcs::BucketMetadata()
      .set_storage_class(gcs::storage_class::Standard())
      .set_location("us-central1")
      .set_iam_configuration(iam_config)
      .set_encryption(encryption)
      .set_soft_delete_policy(std::chrono::seconds(7 * 24 * 3600)) // 7 days (use 30 * 24 * 3600 for 30 days)
      .set_retention_policy(std::chrono::seconds(90 * 24 * 3600))  // 90 days
      .set_autoclass(gcs::BucketAutoclass{true})
      .upsert_label("data-class", "pii")
      .upsert_label("owner", "security-team")
      .set_lifecycle(lifecycle);

  // NOTE: IP Filtering is not exposed in the C++ client library; configure via REST, gcloud, or Terraform.
  return client.CreateBucket(bucket_name, std::move(metadata),
                             gcs::OverrideDefaultProject(project_id));
}

// WARNING: Locking the retention policy is permanent and irreversible.
StatusOr<gcs::BucketMetadata> LockRetentionPolicy(gcs::Client client,
                                                  std::string const& bucket_name) {
  StatusOr<gcs::BucketMetadata> metadata = client.GetBucketMetadata(bucket_name);
  if (!metadata) return metadata;
  return client.LockBucketRetentionPolicy(bucket_name, metadata->metageneration());
}
```

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website, CORS, Versioning)

```cpp
#include "google/cloud/storage/client.h"
#include <chrono>
#include <string>
#include <utility>

namespace gcs = ::google::cloud::storage;
using ::google::cloud::StatusOr;

StatusOr<gcs::BucketMetadata> CreateStaticWebsiteBucket(gcs::Client client,
                                                       std::string const& project_id,
                                                       std::string const& bucket_name) {
  gcs::CorsEntry cors;
  cors.max_age_seconds = 3600;
  cors.method = {"GET", "HEAD", "OPTIONS"};
  cors.origin = {"*"};
  cors.response_header = {"Content-Type"};

  gcs::BucketMetadata metadata = gcs::BucketMetadata()
      .set_storage_class(gcs::storage_class::Standard())
      .set_location("US")
      .set_iam_configuration(gcs::BucketIamConfiguration{
          gcs::UniformBucketLevelAccess{true, {}},
          gcs::PublicAccessPreventionInherited()
      })
      .set_versioning(gcs::BucketVersioning{true})
      .set_soft_delete_policy(std::chrono::seconds(7 * 24 * 3600))
      .set_website(gcs::BucketWebsite{"index.html", "404.html"})
      .set_cors({cors});

  StatusOr<gcs::BucketMetadata> bucket = client.CreateBucket(
      bucket_name, std::move(metadata), gcs::OverrideDefaultProject(project_id));
  if (!bucket) return bucket;

  auto current_policy = client.GetNativeBucketIamPolicy(
      bucket_name, gcs::RequestedPolicyVersion(3));
  if (!current_policy) return current_policy.status();

  current_policy->set_version(3);
  current_policy->bindings().emplace_back(
      gcs::NativeIamBinding("roles/storage.objectViewer", {"allUsers"}));

  auto updated = client.SetNativeBucketIamPolicy(bucket_name, *current_policy);
  if (!updated) return updated.status();

  return bucket;
}
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

```cpp
#include "google/cloud/storage/client.h"
#include <chrono>
#include <string>
#include <utility>

namespace gcs = ::google::cloud::storage;
using ::google::cloud::StatusOr;

StatusOr<gcs::BucketMetadata> CreateCheckpointBucket(gcs::Client client,
                                                     std::string const& project_id,
                                                     std::string const& bucket_name) {
  gcs::BucketIamConfiguration iam_config;
  iam_config.uniform_bucket_level_access = gcs::UniformBucketLevelAccess{true, {}};
  iam_config.public_access_prevention = gcs::PublicAccessPreventionEnforced();

  gcs::BucketLifecycle lifecycle;
  lifecycle.rule = {
      gcs::LifecycleRule(gcs::LifecycleRule::MaxAge(14), gcs::LifecycleRule::Delete())
  };

  gcs::BucketMetadata metadata = gcs::BucketMetadata()
      .set_storage_class("RAPID")
      .set_location("us-east1")
      .set_custom_placement_config(gcs::BucketCustomPlacementConfig{{"us-east1-b"}})
      .set_iam_configuration(iam_config)
      .set_hierarchical_namespace(gcs::BucketHierarchicalNamespace{true})
      .set_soft_delete_policy(std::chrono::seconds(0))
      .set_lifecycle(lifecycle);

  return client.CreateBucket(bucket_name, std::move(metadata),
                             gcs::OverrideDefaultProject(project_id));
}
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

> [!CAUTION]
>
> Setting per-object retention mode to `"Locked"` is permanent and irreversible.
> Once set, the mode cannot be changed back, the retention date can only be
> extended (never shortened or removed), and objects cannot be deleted or
> overwritten by anyone until the retention date expires.

```cpp
#include "google/cloud/storage/client.h"
#include <chrono>
#include <string>
#include <utility>

namespace gcs = ::google::cloud::storage;
using ::google::cloud::StatusOr;

StatusOr<gcs::BucketMetadata> CreateRegulatoryWormBucket(gcs::Client client,
                                                         std::string const& project_id,
                                                         std::string const& bucket_name,
                                                         std::string const& kms_key_id) {
  gcs::BucketIamConfiguration iam_config;
  iam_config.uniform_bucket_level_access = gcs::UniformBucketLevelAccess{true, {}};
  iam_config.public_access_prevention = gcs::PublicAccessPreventionEnforced();

  gcs::BucketLifecycle lifecycle;
  lifecycle.rule = {
      gcs::LifecycleRule(gcs::LifecycleRule::MaxAge(2555), gcs::LifecycleRule::Delete())
  };

  gcs::BucketMetadata metadata = gcs::BucketMetadata()
      .set_storage_class(gcs::storage_class::Archive())
      .set_location("us-east1")
      .set_iam_configuration(iam_config)
      .set_encryption(gcs::BucketEncryption{kms_key_id})
      .upsert_label("compliance-type", "regulatory")
      .upsert_label("retention-period", "7y")
      .set_soft_delete_policy(std::chrono::seconds(7 * 24 * 3600))
      .set_lifecycle(lifecycle);

  return client.CreateBucket(bucket_name, std::move(metadata),
                             gcs::EnableObjectRetention(true),
                             gcs::OverrideDefaultProject(project_id));
}

StatusOr<gcs::ObjectMetadata> UploadObjectWithRetention(gcs::Client client,
                                                        std::string const& bucket_name,
                                                        std::string const& object_name,
                                                        std::string const& contents) {
  auto retain_until = std::chrono::system_clock::from_time_t(1924991999); // 2030-12-31T23:59:59Z
  return client.InsertObject(
      bucket_name, object_name, contents,
      gcs::WithObjectMetadata(gcs::ObjectMetadata{}.set_retention(
          gcs::ObjectRetention{gcs::ObjectRetentionLocked(), retain_until})));
}
```
