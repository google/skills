# Cloud Storage Infrastructure as Code (Terraform)

Terraform is an open-source Infrastructure as Code (IaC) tool created by
HashiCorp that allows you to define, provision, and manage cloud infrastructure
using a declarative configuration language (HashiCorp Configuration Language, or
HCL).

Instead of manual action via the Google Cloud Console or CLI commands, Terraform
lets you specify the desired state of your Google Cloud Storage (GCS) resources
in code, and automatically handles the API calls required to create, update, or
delete them.

## Advantages of Terraform

-   **Declarative Configuration:** You define the target state of your buckets,
    IAM policies, and lifecycle rules. Terraform determines what changes are
    necessary to achieve that state.
-   **Version Control and Collaboration:** Infrastructure configurations live
    alongside application code in version control systems (like Git), enabling
    peer code reviews, auditability, and rollback capabilities.
-   **Repeatability and Consistency:** You can reliably provision identical
    storage architectures across multiple environments (e.g., development,
    staging, production) without human error.
-   **Automated Drift Detection:** Running `terraform plan` compares your active
    cloud resources against your defined code, immediately highlighting
    unauthorized manual changes ("configuration drift").

> [!WARNING] **State Management & Immutability Limits:** Terraform tracks
> deployed infrastructure via state files (`terraform.tfstate`). In team
> environments, you **must** configure a secure remote state backend (e.g.
> through a GCS bucket) to prevent concurrent execution conflicts and protect
> sensitive metadata. Furthermore, certain core GCS bucket properties — such as
> `name` and `location` — are immutable after creation. Attempting to modify
> these fields in Terraform will force a destructive resource replacement
> (`destroy` followed by `create`), which will fail if the bucket contains
> objects or cause permanent data loss if safeguards like `lifecycle {
> prevent_destroy = true }` are omitted.

## Core Concepts in Terraform

In Terraform, Cloud Storage buckets are managed using the
`google_storage_bucket` resource from the official Google Cloud provider. The
configuration maps directly to GCS core concepts like location types, storage
classes, lifecycle policies, and data protection features.

Google recommends enabling **Uniform Bucket-Level Access**
(`uniform_bucket_level_access = true`) and **Public Access Prevention**
(`public_access_prevention = "enforced"`) on all new buckets to enforce secure,
IAM-only access control.

### Scenario 1: Single-Region Bucket with Standard Storage, Lifecycle Rules, and IP Filtering

This scenario provisions a regional bucket designed for active application data.
It uses the `STANDARD` storage class, implements Object Lifecycle Management
(OLM) to automatically transition older data to archive storage or clean up
expired versions, and restricts access to specific IP ranges using bucket IP
filtering.

```
resource "google_storage_bucket" "app_data" {
  name                        = "my-regional-app-data-bucket"
  location                    = "US-CENTRAL1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Enable Object Versioning
  versioning {
    enabled = true
  }

  # Prevent accidental deletion of the bucket
  lifecycle {
    prevent_destroy = true
  }

  # Object Lifecycle Management (OLM)
  # Rule 1: Transition objects older than 365 days to ARCHIVE storage
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }

  # Rule 2: Delete non-current object versions when there are more than 3 newer versions
  lifecycle_rule {
    condition {
      num_newer_versions = 3
    }
    action {
      type = "Delete"
    }
  }

  # IP Filtering Configuration
  # Restricts bucket access strictly to the specified public IP ranges
  ip_filter {
    mode                           = "Enabled"
    allow_all_service_agent_access = true

    public_network_source {
      # Allow all public IPv4 and IPv6 traffic (effectively blocking private
      # traffic from a VPC network).
      allowed_ip_cidr_ranges = ["0.0.0.0/0", "::/0"]
    }
  }
}
```

### Scenario 2: Dual-Region Bucket with Public Access Prevention and Turbo Replication

This scenario demonstrates a highly available dual-region setup designed for
disaster recovery and continuity. It uses a predefined dual-region (`NAM4`),
enforces public access prevention, and enables Turbo Replication (`ASYNC_TURBO`)
for a backed 15-minute recovery point objective (RPO).

```
resource "google_storage_bucket" "mission_critical_dr" {
  name                        = "my-dual-region-dr-bucket"
  location                    = "NAM4"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Enable Turbo Replication for 15-minute RPO
  rpo = "ASYNC_TURBO"

  # Enable Object Versioning for point-in-time recovery
  versioning {
    enabled = true
  }

  # Retain soft-deleted objects for 14 days (1,209,600 seconds)
  soft_delete_policy {
    retention_duration_seconds = 1209600
  }
}
```

*Note: For predefined dual-regions like `NAM4` or `EUR4`, GCS automatically
manages the underlying region pairing. To create a **custom dual-region** (e.g.,
pairing `US-EAST1` and `US-WEST1`), set `location` to the parent continent
multi-region (e.g., `"US"`) and define the specific region pair inside a
`custom_placement_config` block:*

```
resource "google_storage_bucket" "custom_dual_region" {
  name                        = "my-custom-dual-region-bucket"
  location                    = "US" # Parent continent multi-region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  custom_placement_config {
    data_locations = ["US-EAST1", "US-WEST1"]
  }
}
```

### Scenario 3: Nearline Storage with Object Retention (WORM) and CMEK Encryption

This scenario provisions a compliance archive bucket designed for long-term,
tamper-proof record keeping (e.g., financial or healthcare audit logs). It uses
the `NEARLINE` storage class, enforces Customer-Managed Encryption Keys (CMEK),
and enables Object Retention to support Write-Once-Read-Many (WORM) compliance.

```
resource "google_storage_bucket" "compliance_vault" {
  name                        = "my-compliance-vault-bucket"
  location                    = "US-EAST1"
  storage_class               = "NEARLINE"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Enable Object Retention Lock capability on the bucket
  enable_object_retention = true

  # Customer-Managed Encryption Key (CMEK) configuration
  # Note: The Cloud Storage service agent must be granted the CryptoKey Encrypter/Decrypter role on this key.
  encryption {
    default_kms_key_name = "projects/my-project/locations/us-east1/keyRings/my-keyring/cryptoKeys/my-key"
  }

  # Ensure audit trails are preserved by preventing accidental destruction
  lifecycle {
    prevent_destroy = true
  }
}
```

*Note: To apply specific retention periods to individual objects within a
retention-enabled bucket, use the `google_storage_bucket_object` resource or
SDKs to set object-level retention rules.*

### Scenario 4: Bucket IAM Policy and Service Account Access

This scenario provisions a bucket and grants an application service account read
and write access to stored objects. In Terraform, bucket IAM permissions can be
managed using `google_storage_bucket_iam_member` (non-authoritative, additive),
`google_storage_bucket_iam_binding` (authoritative for a specific role), or
`google_storage_bucket_iam_policy` (authoritative for all roles on the bucket).

Here, we use `google_storage_bucket_iam_member` to grant the
`roles/storage.objectViewer` role to a service account without overwriting other
existing permissions on the bucket:

```
resource "google_storage_bucket" "secure_assets" {
  name                        = "my-secure-assets-bucket"
  location                    = "US-CENTRAL1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

# Grant Storage Object Viewer permissions to an application service account
resource "google_storage_bucket_iam_member" "sa_object_viewer" {
  bucket = google_storage_bucket.secure_assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:my-app-sa@my-project.iam.gserviceaccount.com"
}
```

## Documentation and References

-   [Cloud Storage Overview](https://docs.cloud.google.com/storage/docs/introduction)
-   [Terraform Google Provider Documentation: google_storage_bucket](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket)
-   [Terraform Google Provider Documentation: google_storage_bucket_object](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket_object)
-   [Terraform Google Provider Documentation: google_storage_bucket_iam](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket_iam)
-   [Google Cloud Terraform Best Practices](https://docs.cloud.google.com/docs/terraform/best-practices/general-style-structure)
-   [Sample for Creating a Bucket to Store Terraform State](https://docs.cloud.google.com/storage/docs/samples/storage-bucket-tf-with-versioning?hl=en)
