# Python SDK Reference & Examples

This guide translates a **Draft Bucket Creation Plan** (from Phase 2) into the
official Cloud Storage Python client library (`google-cloud-storage`).

*   [Cloud Storage Python Client Library](https://cloud.google.com/python/docs/reference/storage/latest)

## Version Requirements

> [!IMPORTANT]
>
> **Encryption Enforcement Config** (`EncryptionEnforcementConfig`) requires
> `google-cloud-storage` version **3.10.0** or higher. Always include a note in
> your response stating that `EncryptionEnforcementConfig` requires version
> **3.10.0 or higher**, and that if the user's SDK version is below 3.10.0, they
> must supplement using the [REST API](rest.md) or create the bucket using
> [gcloud](gcloud.md) or [Terraform](terraform.md). When generating code
> snippets for the user, do **not** execute `python3` or `pip` in the terminal
> to inspect the host machine's installed SDK version unless the user explicitly
> asks to inspect or execute in their local environment.

## Translation Mapping Table

Draft Plan Field / Setting          | Python SDK Feature / Attribute
:---------------------------------- | :-----------------------------
**Client Initialization**           | `client = storage.Client(project=project_id)`
**Bucket Name**                     | `bucket = client.bucket(bucket_name)` (passed to `client.create_bucket(bucket_or_name, ...)`, which accepts `Bucket` or `str`)
**Location**                        | `location="us-central1"` (arg in `client.create_bucket(bucket, location=...)`)
**Placement (Dual-Region / Zonal)** | `data_locations=["us-east1-b"]` (arg in `client.create_bucket(...)`; for zonal buckets, `location` is the region and `data_locations` has the zone)
**Replication Speed (RPO)**         | `bucket.rpo = "ASYNC_TURBO"`
**Storage Class**                   | `bucket.storage_class = "STANDARD"` (or `"NEARLINE"`, `"COLDLINE"`, `"ARCHIVE"`, `"RAPID"`)
**UBLA**                            | `bucket.iam_configuration.uniform_bucket_level_access_enabled = True`
**Public Access Prevention**        | `bucket.iam_configuration.public_access_prevention = "enforced"` (or `"inherited"`)
**Soft Delete**                     | `bucket.soft_delete_policy.retention_duration_seconds = 604800` (`0` to disable for zonal buckets)
**Object Versioning**               | `bucket.versioning_enabled = True` (omit or `False` when disabled)
**Encryption (CMEK)**               | `bucket.default_kms_key_name = kms_key_link`
**Restrict Encryption (CSEK)**      | `bucket.encryption.customer_supplied_encryption_enforcement_config = EncryptionEnforcementConfig(restriction_mode="FullyRestricted")` (**v3.10.0+**)
**Autoclass**                       | `bucket.autoclass_enabled = True`
**Hierarchical Namespace**          | `bucket.hierarchical_namespace_enabled = True`
**Labels**                          | `bucket.labels = {"key": "value"}`
**IP Filtering**                    | `from google.cloud.storage.ip_filter import IPFilter, PublicNetworkSource, VpcNetworkSource; bucket.ip_filter = ip_filter`
**Allow Cross-Org VPCs**            | `ip_filter.allow_cross_org_vpcs = False`
**Lifecycle Policies (OLM)**        | `bucket.lifecycle_rules = [{"action": {"type": "..."}, "condition": {"age": 7}}]`
**CORS**                            | `bucket.cors = [{"origin": [...], "method": [...], "responseHeader": [...], "maxAgeSeconds": 3600}]`
**Website Configuration**           | `bucket.configure_website(main_page_suffix="index.html", not_found_page="404.html")`
**Public IAM Policy**               | `policy = bucket.get_iam_policy(requested_policy_version=3)` -> append `allUsers` to `roles/storage.objectViewer` -> `bucket.set_iam_policy(policy)`
**Pub/Sub Notifications**           | `notification = bucket.notification(topic_name=...); notification.create()`
**Bucket Retention Period**         | `bucket.retention_period = 7776000` (in seconds)
**Lock Bucket Retention Policy**    | `bucket.lock_retention_policy()` (**permanent and irreversible**)
**Object Retention (Object Lock)**  | `client.create_bucket(bucket_or_name=bucket_name, location=..., enable_object_retention=True)`
**Set Object Retention**            | `blob.retention.mode = "Locked"` (or `"Unlocked"`), `blob.retention.retain_until_time = dt`, then upload or `blob.patch()` (pass `override_unlocked_retention=True` to shorten/remove/lock an existing `"Unlocked"` retention)
**Rapid Cache**                     | `StorageControlClient.create_anywhere_cache` (`google-cloud-storage-control`)

--------------------------------------------------------------------------------

## Python SDK Examples

### Example 1: Sensitive Data / Compliance (UBLA, PAP, CMEK, CSEK Restricted, Soft Delete, Retention, Autoclass, Labels, OLM, IP Filter)

*(For a baseline secure bucket, keep `project=project_id`, `"STANDARD"`, UBLA,
`"enforced"` PAP, 7-day Soft Delete, and
`customer_supplied_encryption_enforcement_config` (`"FullyRestricted"`),
omitting unused optional attributes such as `default_kms_key_name`,
`autoclass_enabled`, `retention_period`, `ip_filter`, or `lifecycle_rules`.)*

```python
from google.cloud import storage
from google.cloud.storage.bucket import EncryptionEnforcementConfig
from google.cloud.storage.ip_filter import IPFilter, PublicNetworkSource, VpcNetworkSource

def create_compliance_bucket(project_id: str, bucket_name: str, kms_key_link: str):
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    bucket.storage_class = "STANDARD"
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    bucket.iam_configuration.public_access_prevention = "enforced"
    bucket.default_kms_key_name = kms_key_link
    bucket.soft_delete_policy.retention_duration_seconds = 604800  # 7 days

    # Requires google-cloud-storage >= 3.10.0 (use REST, gcloud, or Terraform on older versions)
    bucket.encryption.customer_supplied_encryption_enforcement_config = (
        EncryptionEnforcementConfig(restriction_mode="FullyRestricted")
    )

    bucket.retention_period = 7776000  # 90 days (call bucket.lock_retention_policy() to lock; permanent and irreversible)
    bucket.autoclass_enabled = True
    bucket.labels = {"data-class": "pii", "owner": "security-team"}
    bucket.lifecycle_rules = [
        {
            "action": {"type": "AbortIncompleteMultipartUpload"},
            "condition": {"age": 7},
        }
    ]

    ip_filter = IPFilter()
    ip_filter.mode = "Enabled"
    ip_filter.allow_all_service_agent_access = True
    ip_filter.allow_cross_org_vpcs = False
    ip_filter.public_network_source = PublicNetworkSource(
        allowed_ip_cidr_ranges=["192.0.2.0/24"]
    )
    ip_filter.vpc_network_sources = [
        VpcNetworkSource(
            network="projects/PROJECT_ID/global/networks/NETWORK_NAME",
            allowed_ip_cidr_ranges=["10.0.0.0/16"],
        )
    ]
    bucket.ip_filter = ip_filter

    return client.create_bucket(bucket, location="us-central1")
```

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website Config, CORS, Versioning)

```python
from google.cloud import storage

def create_static_website_bucket(project_id: str, bucket_name: str):
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    bucket.storage_class = "STANDARD"
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    bucket.iam_configuration.public_access_prevention = "inherited"  # allow public access
    bucket.versioning_enabled = True
    bucket.soft_delete_policy.retention_duration_seconds = 604800  # 7 days

    bucket.configure_website(
        main_page_suffix="index.html",
        not_found_page="404.html",
    )
    bucket.cors = [{
        "origin": ["*"],
        "method": ["GET", "HEAD", "OPTIONS"],
        "responseHeader": ["Content-Type"],
        "maxAgeSeconds": 3600,
    }]

    new_bucket = client.create_bucket(bucket, location="US")

    policy = new_bucket.get_iam_policy(requested_policy_version=3)
    policy.bindings.append({
        "role": "roles/storage.objectViewer",
        "members": {"allUsers"},
    })
    new_bucket.set_iam_policy(policy)
    return new_bucket
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

```python
from google.cloud import storage

def create_checkpoint_bucket(project_id: str, bucket_name: str):
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    bucket.storage_class = "RAPID"
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    bucket.iam_configuration.public_access_prevention = "enforced"
    bucket.hierarchical_namespace_enabled = True
    bucket.soft_delete_policy.retention_duration_seconds = 0
    bucket.lifecycle_rules = [
        {"action": {"type": "Delete"}, "condition": {"age": 14}}
    ]

    # location is the region; data_locations contains the zone
    return client.create_bucket(
        bucket, location="us-east1", data_locations=["us-east1-b"]
    )
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

> [!CAUTION]
>
> Setting per-object retention mode to `"Locked"` is permanent and irreversible.
> Once set, the mode cannot be changed back, the retention date can only be
> extended (never shortened or removed), and objects cannot be deleted or
> overwritten by anyone until the retention date expires.

```python
import datetime
from google.cloud import storage

def create_regulatory_worm_bucket(project_id: str, bucket_name: str, kms_key_id: str):
    client = storage.Client(project=project_id)

    bucket = client.create_bucket(
        bucket_or_name=bucket_name,
        location="us-east1",
        enable_object_retention=True,
    )
    bucket.storage_class = "ARCHIVE"
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    bucket.iam_configuration.public_access_prevention = "enforced"
    bucket.default_kms_key_name = kms_key_id
    bucket.labels = {"compliance-type": "regulatory", "retention-period": "7y"}
    bucket.soft_delete_policy.retention_duration_seconds = 604800
    bucket.lifecycle_rules = [
        {"action": {"type": "Delete"}, "condition": {"age": 2555}}
    ]
    bucket.patch()
    return bucket

def upload_object_with_retention(bucket_name: str, source_file: str, destination_blob: str):
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(destination_blob)
    blob.retention.mode = "Locked"
    blob.retention.retain_until_time = datetime.datetime(
        2030, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc
    )
    blob.upload_from_filename(source_file)
    return blob
```
