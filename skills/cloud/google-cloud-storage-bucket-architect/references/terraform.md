# Terraform Google Provider Cloud Storage Reference

> [!IMPORTANT]
>
> **DO NOT APPLY THESE CONFIGURATIONS AUTOMATICALLY.** Present the generated
> Terraform configuration snippets to the user for review and integration.

## Official Documentation Reference

*   [Terraform Registry: `google_storage_bucket`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket)
*   [Terraform Registry: `google_storage_bucket_object`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket_object)
*   [Terraform Registry: `google_storage_notification`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_notification)
*   [Terraform Registry: `google_storage_anywhere_cache`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_anywhere_cache)

--------------------------------------------------------------------------------

## Translation Mapping Table

Draft Plan Field / Setting         | `google_storage_bucket` Attribute / Resource           | Notes / Action
:--------------------------------- | :----------------------------------------------------- | :-------------
**Bucket Name**                    | `name`                                                 | Required string. Must be globally unique.
**Project**                        | `project`                                              | Optional string (defaults to provider project).
**Location**                       | `location`                                             | Required string: e.g., `"us-central1"`, `"US"`, `"nam4"`. For zonal buckets, set to the region (e.g., `"us-east1"`).
**Placement**                      | `custom_placement_config.data_locations`               | List of strings: `["us-east1", "us-west1"]` (custom dual-region) or `["us-east1-b"]` (zonal bucket).
**Replication Speed (RPO)**        | `rpo`                                                  | String: `"ASYNC_TURBO"` (for dual-region buckets).
**Storage Class**                  | `storage_class`                                        | `"STANDARD"`, `"NEARLINE"`, `"COLDLINE"`, `"ARCHIVE"`, `"RAPID"`. Must be `"STANDARD"` if Autoclass is enabled; `"RAPID"` for zonal buckets.
**UBLA**                           | `uniform_bucket_level_access`                          | Boolean. Always set to `true`.
**Public Access Prevention**       | `public_access_prevention`                             | String: `"enforced"` or `"inherited"`.
**Soft Delete**                    | `soft_delete_policy.retention_duration_seconds`        | Seconds: `604800` (7 days default) to `7776000` (90 days). Set to `0` to disable (must be `0` for zonal buckets).
**Object Versioning**              | `versioning.enabled`                                   | Boolean. Enables/disables versioning.
**Encryption (CMEK)**              | `encryption.default_kms_key_name`                      | Full KMS key ID (`"projects/.../cryptoKeys/..."`). Optional when only setting enforcement blocks. ⚠️ **See Note 1 below.**
**Restrict Encryption (CSEK)**     | `encryption` (`*_encryption_enforcement_config`)       | Nested `customer_supplied_encryption_enforcement_config` block inside `encryption` (`restriction_mode = "FullyRestricted"`). See Example 1.
**Autoclass**                      | `autoclass.enabled`                                    | Boolean (`true` to enable; incompatible with zonal buckets).
**Hierarchical Namespace**         | `hierarchical_namespace.enabled`                       | Boolean (`true` to enable at creation only — **irreversible**; incompatible with versioning, Bucket Lock, and Object Lock).
**Labels**                         | `labels`                                               | Map of strings (`{ key = "value" }`).
**IP Filtering**                   | `ip_filter`                                            | Block defining IP/VPC rules. See Example 1 below.
**Lifecycle Policies (OLM)**       | `lifecycle_rule`                                       | One or more `lifecycle_rule` blocks. See Examples 1 & 3 below.
**CORS**                           | `cors`                                                 | One or more `cors` blocks. See Example 2 below.
**Website Configuration**          | `website`                                              | Block with `main_page_suffix` and `not_found_page`. See Example 2 below.
**Public IAM Policy**              | Resource: `google_storage_bucket_iam_member`           | Separate resource granting `roles/storage.objectViewer` to `allUsers`.
**Pub/Sub Notifications**          | Resource: `google_storage_notification`                | Separate resource linking bucket and Pub/Sub topic. ⚠️ **See Note 1 below.**
**Bucket Retention Period**        | `retention_policy.retention_period`                    | Number in seconds (e.g., `7776000` for 90 days, `220752000` for 7 years).
**Lock Bucket Retention Policy**   | `retention_policy.is_locked`                           | Boolean. Setting `is_locked = true` permanently locks the policy. **Irreversible.**
**Object Retention (Object Lock)** | `enable_object_retention`                              | Boolean (`true` to enable per-object retention).
**Set Object Retention**           | Resource: `google_storage_bucket_object` (`retention`) | `retention` block with `mode` (`"Locked"`/`"Unlocked"`) and `retain_until_time` on `google_storage_bucket_object`.
**Rapid Cache**                    | Resource: `google_storage_anywhere_cache`              | Separate resource linking bucket to Rapid Cache zone.

> [!NOTE]
>
> *   **Note 1 (Service Agent IAM Prerequisites)**: For **CMEK**, the Cloud
>     Storage service agent
>     (`service-PROJECT_NUM@gs-project-accounts.iam.gserviceaccount.com`, or via
>     `data "google_storage_project_service_account"`) must hold
>     `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the KMS key. For **Pub/Sub
>     Notifications**, grant that service agent (via
>     `google_storage_project_service_account` data source)
>     `roles/pubsub.publisher` on the topic (e.g., via
>     `google_pubsub_topic_iam_binding` or `google_pubsub_topic_iam_member`) and
>     set `depends_on` on `google_storage_notification` targeting the IAM
>     resource.

--------------------------------------------------------------------------------

## Terraform Examples (Including Helper Block Templates)

### Example 1: Sensitive Data / Compliance (CMEK, CSEK Restricted, Retention Policy, Autoclass, Labels, OLM, IP Filter, Soft Delete)

*(For a baseline secure bucket, keep `uniform_bucket_level_access = true`,
`public_access_prevention = "enforced"`, `soft_delete_policy`, and
`customer_supplied_encryption_enforcement_config` inside `encryption`.)*

```tf
resource "google_storage_bucket" "compliance_bucket" {
  name                        = "my-compliance-pii-bucket"
  project                     = "my-compliance-project"
  location                    = "us-central1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  encryption {
    # Omit default_kms_key_name when using Google-managed encryption
    default_kms_key_name = "projects/my-kms-project/locations/us-central1/keyRings/my-keyring/cryptoKeys/my-key"

    customer_supplied_encryption_enforcement_config {
      restriction_mode = "FullyRestricted"
    }
    customer_managed_encryption_enforcement_config {
      restriction_mode = "NotRestricted"
    }
    google_managed_encryption_enforcement_config {
      restriction_mode = "NotRestricted"
    }
  }

  # WARNING: Setting is_locked = true is permanent and irreversible!
  retention_policy {
    retention_period = 7776000 # 90 days in seconds (use 220752000 for 7 years)
    is_locked        = false
  }

  autoclass {
    enabled = true
  }

  labels = {
    data-class = "pii"
    owner      = "security-team"
  }

  lifecycle_rule {
    action {
      type = "AbortIncompleteMultipartUpload"
    }
    condition {
      age = 7
    }
  }

  ip_filter {
    mode                           = "Enabled"
    allow_all_service_agent_access = true
    allow_cross_org_vpcs           = false

    public_network_source {
      allowed_ip_cidr_ranges = ["192.0.2.0/24"]
    }

    vpc_network_sources {
      network                = "projects/PROJECT_ID/global/networks/NETWORK_NAME"
      allowed_ip_cidr_ranges = ["10.0.0.0/16"]
    }
  }

  soft_delete_policy {
    retention_duration_seconds = 604800 # 7 days
  }
}
```

*(Note: Setting `is_locked = true` inside `retention_policy` is permanent and
irreversible—always include a critical warning in prose whenever locking is
requested.)*

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website, CORS, Versioning)

```tf
resource "google_storage_bucket" "static_website" {
  name                        = "www.my-company-site.com"
  location                    = "US"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"

  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 604800 # 7 days
  }
}

resource "google_storage_bucket_iam_member" "public_viewer" {
  bucket = google_storage_bucket.static_website.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

```tf
resource "google_storage_bucket" "checkpoint_bucket" {
  name                        = "my-training-checkpoints-us-east1-b"
  location                    = "us-east1"
  storage_class               = "RAPID"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  custom_placement_config {
    data_locations = ["us-east1-b"]
  }

  hierarchical_namespace {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 14
    }
  }
}
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

> [!CAUTION]
>
> Setting `mode = "Locked"` on an object is permanent and irreversible. Once
> locked, the policy cannot be removed and the retention period can only be
> extended.

```tf
resource "google_storage_bucket" "legal_archive" {
  name                        = "my-legal-archive-bucket"
  location                    = "us-east1"
  storage_class               = "ARCHIVE"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  enable_object_retention     = true

  encryption {
    default_kms_key_name = "projects/my-kms-project/locations/us-east1/keyRings/my-keyring/cryptoKeys/my-key"
  }

  labels = {
    compliance-type  = "regulatory"
    retention-period = "7y"
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 2555
    }
  }

  soft_delete_policy {
    retention_duration_seconds = 604800 # 7 days
  }
}

resource "google_storage_bucket_object" "case_file" {
  name   = "case_file_abc.pdf"
  bucket = google_storage_bucket.legal_archive.name
  source = "path/to/local/file.pdf"

  retention {
    mode              = "Locked"
    retain_until_time = "2030-12-31T23:59:59Z"
  }
}
```
