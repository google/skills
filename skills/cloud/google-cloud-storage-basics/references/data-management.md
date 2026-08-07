# GCS Data Management, Security, & Cloud Audit Logs

This reference guide covers the core data management, security, and cost
optimization capabilities of Google Cloud Storage (GCS). This means providing an
overview of various access control, data protection, and security best practices
while storing data in GCS along with relevant gcloud commands.

> [!TIP] **Automated Security Posture Assessment**
>
> For an automated security analysis of GCS resources in a GCP project, an agent
> should use the `gcs-security-assessment` skill instead of improvising a manual
> assessment:
>
> 1.  **If installed:** Check available skills for `gcs-security-assessment` and
>     invoke it directly by name.
> 2.  **If not installed:** Do not attempt the assessment manually, and do not
>     substitute other security products (e.g. Security Command Center). Give
>     the user this exact command to install the skill, then proceed once it is
>     installed: `npx skills add gemini-cli-extensions/google-cloud-storage
>     --skill gcs-security-assessment`

--------------------------------------------------------------------------------

## 1. Identity and Access Management (IAM)

Cloud Storage uses IAM for access control, allowing you to grant permissions at
the bucket, project, and managed-folder levels.

### Predefined Roles

Assign predefined roles to enforce the principle of least privilege based on the
principal's operational responsibilities:

-   **`roles/storage.admin`:** Grants full control over buckets and their
    objects. This role can be granted at the bucket-level, limiting its scope to
    just that bucket and its objects.
-   **`roles/storage.objectAdmin`:** Grants full control of objects, and allows
    management of folders and Managed Folders, including listing, creating,
    viewing, and deleting them. This role can be granted at the bucket-level,
    limiting its scope to just that bucket's objects and folders/Managed
    Folders. Viewing IAM policies on Managed Folders are excluded.
-   **`roles/storage.objectUser`:** Grants the same permissions as objectAdmin
    except IAM permission for reading/setting object ACLs and permission to set
    or override unlocked retention are excluded.
-   **`roles/storage.objectViewer`:** Grants read-only access to object contents
    and metadata, excluding ACLs. This includes the ability to get/list folders
    and Managed Folders. It can also be scoped to a single bucket's contents.
-   **`roles/storage.objectCreator`:** Allows users to create objects and
    resources like folders/Managed Folders. This does not give permission to
    view, delete, or overwrite objects. It can be scoped to a single bucket.
-   **`roles/storage.bucketViewer`:** Grants permission to list buckets and
    their metadata, excluding IAM policies.
-   **`roles/storage.folderAdmin`:** Grants full control over folders/Managed
    Folders and objects, including listing, creating, viewing, and deleting
    them. This role does grant access to get/set IAM policies on Managed
    Folders.

> [!NOTE]
>
> Roles can be combined to minimize overpermissioning for certain workflows,
> e.g. objectCreator/objectViewer for a read-write workflow but intentionally
> avoiding the delete permission granted by objectUser/objectAdmin.

Reference public documentation for other predefined Storage IAM roles not
mentioned here:
https://docs.cloud.google.com/storage/docs/access-control/iam-roles.

### Custom IAM Roles

If predefined roles provide more permissions than necessary, you can also create
custom IAM roles containing only the specific permissions required by your
workload (e.g. bundling `storage.objects.get` and `storage.objects.list` without
granting delete permission). This enforces strict least privilege and prevents
overpermissioning in sensitive environments.

-   **Create a custom IAM role:**

    ```bash
    gcloud iam roles create myCustomStorageRole \
        --project=my-project \
        --title="Custom Storage Reader" \
        --description="Grants get and list permissions for GCS objects" \
        --permissions=storage.objects.get,storage.objects.list
    ```

-   **List custom roles:**

    ```bash
    # View org-level custom roles
    gcloud iam roles list --organization=1234

    # View project-level custom roles
    gcloud iam roles list --project=4321

    # View predefined roles
    gcloud iam roles list
    ```

-   **Inspect a custom IAM role:**

    ```bash
    gcloud iam roles describe myCustomStorageRole --project=my-project
    ```

### Adding IAM Policy Bindings at Bucket Level

Use the `gcloud storage` CLI to bind roles to principals (users, service
accounts, or groups) at the bucket or Managed Folder level.

> [!NOTE]
>
> While project, bucket, and Managed Folder IAM policies govern the objects
> within them, **it is not possible to set an IAM policy directly at the object
> level**. Individual object-level permissions can only be managed using legacy
> Access Control Lists (ACLs), which are disabled when Uniform Bucket-Level
> Access is enabled. Using legacy object ACLs is not recommended.

-   **Grant bucket-level access:**

    ```bash
    gcloud storage buckets add-iam-policy-binding gs://my-bucket \
        --member="serviceAccount:my-service-agent@my-project.iam.gserviceaccount.com" \
        --role="roles/storage.objectViewer"
    ```

--------------------------------------------------------------------------------

## 2. Authentication & Authorization

GCS supports multiple authentication mechanisms tailored to different
architectural boundaries and client types.

### IAM Authentication

Authentication confirms identity by exchanging principal credentials—such as
user accounts (`gcloud auth login`) or service accounts—for short-lived OAuth
2.0 access tokens. Application Default Credentials (ADC, via `gcloud auth
application-default login`) automatically locates these credentials across
environments. For advanced architectures, Google Cloud supports Workload
Identity Federation (for keyless multi-cloud/on-premises authentication),
Workforce Identity Federation (for external IdPs), and Service Account
Impersonation.

See the diagram on
https://docs.cloud.google.com/docs/authentication#auth-decision-tree to help the
user determine which authentication method is best for them.

### Signed URLs (V4 Signing)

Signed URLs use signatures to give time-limited access to a specific Cloud
Storage resource, granting permissions like read, write, or delete access
without requiring the client to hold Google Cloud credentials or IAM roles.

The most common uses for signed URLs are uploads and downloads, because in such
requests, object data moves between requesters and Cloud Storage.

> [!NOTE]
>
> Signed URLs can only be used to access Cloud Storage resources through XML API
> endpoints. HMAC credentials are also not supported when using Cloud Storage
> tools to generate signed URLs.

-   **Generate a 15-minute signed upload URL:**

    ```bash
    gcloud storage sign-url gs://my-bucket/uploads/user-profile.png \
        --duration=15m \
        --impersonate-service-account=signed-url-account@my-project.iam.gserviceaccount.com \
        --http-verb=PUT \
        --headers=content-type=image/png
    ```

### HMAC Keys

HMAC keys are a type of credential associated with an account (e.g. a service
account) that allows creation of signatures included in Cloud Storage XML API
requests. These are useful for allowing you to move data between other cloud
storage providers and GCS because HMAC keys allow you to reuse your existing
code to access Cloud Storage.

-   **Create an HMAC key for a service account:**

    ```bash
    gcloud storage hmac create my-service-account@my-project.iam.gserviceaccount.com
    ```

--------------------------------------------------------------------------------

## 3. Access Control Policies

Control how permissions are evaluated and prevent accidental exposure using
bucket-level access guardrails.

### Uniform Bucket-Level Access (UBLA)

Uniform Bucket-Level Access disables legacy object-level Access Control Lists
(ACLs) to ensure that access to the bucket and its objects is only governed by
IAM.

> [!NOTE]
>
> UBLA is required for using Managed Folders, Hierarchical Namespace (HNS)
> buckets, and IAM conditions directly on buckets.

> [!WARNING]
>
> UBLA cannot be disabled after it has been active on a bucket for 90
> consecutive days.

-   **Enable UBLA on an existing bucket:**

    ```bash
    gcloud storage buckets update gs://my-bucket --uniform-bucket-level-access
    ```

### Public Access Prevention (PAP)

Public Access Prevention explicitly blocks any public IAM bindings (such as
`allUsers` or `allAuthenticatedUsers`) on a bucket, overriding any existing
public policies. This can also be enforced at the organization level.

-   **Enforce Public Access Prevention:**

    ```bash
    gcloud storage buckets update gs://my-bucket --public-access-prevention
    ```

--------------------------------------------------------------------------------

## 4. Network Security & Perimeters

Protect storage buckets from unauthorized access and data exfiltration at the
network layer.

-   **VPC Service Controls (VPC-SC):** In order to prevent unintended loss or
    disclosure of sensitive data and data exfiltration, VPC-SC allows you to
    define security policies that prevent access to Google-managed services
    outside of a trusted perimeter, block access to data from untrusted
    locations, and mitigate data exfiltration risks.
-   **Bucket IP Filtering:** Bucket-level access can be restricted through
    allowlisted public or private (VPC network) CIDR ranges, denying all
    requests from outside the range regardless of IAM status (for specific
    buckets).
-   **Regional Endpoints:** Binds API operations and control planes to specific
    geographic endpoints (e.g., `storage.eu.rep.googleapis.com`).

--------------------------------------------------------------------------------

## 5. Data Protection & Immutability

GCS provides several features to help prevent compliance violations, accidental
deletions, and other risk management.

### Soft Delete

Soft delete retains deleted or overwritten buckets and objects for a specified
duration (between 7 and 90 days) before being permanently deleted, allowing a
restoration of its pre-deleted state.

> [!CAUTION]
>
> If a bucket primarily contains short-lived, temporary data, enabling soft
> delete can result in significantly increased storage costs. To optimize cost,
> objects can be renamed instead of copying and temporary data can be stored
> separately (e.g. in buckets with soft delete disabled).

See
https://docs.cloud.google.com/storage/docs/soft-delete#soft-delete-considerations
for more considerations about how Soft Delete interacts with other features.

-   **Configure soft delete duration for a bucket:**

    ```bash
    gcloud storage buckets update gs://my-bucket --soft-delete-duration=30d
    ```

-   **Restore soft-deleted object (with generation):**

    ```bash
      gcloud storage restore gs://my-bucket/my-object#1234
    ```

If no generation is specified, the latest version will be restored.

### Object Versioning

Object Versioning preserves deleted objects as versioned, noncurrent objects
that remain accessible in your bucket until explicitly removed. It's recommended
to consider using Object Lifecycle Management in combination with versioning as
it can remove older versions of an object after a specified length of time or as
newer versions become noncurrent.

> [!CAUTION]
>
> Objects can only be recovered from a deleted bucket when soft delete is
> enabled. Object Versioning does not provide protection against bucket
> deletions.

-   **Enable object versioning:**

    ```bash
    gcloud storage buckets update gs://my-bucket --versioning
    ```

### Object Retention Lock

Object Retention Lock lets you define data retention requirements on a
per-object basis. This differs from Bucket Lock, which defines data retention
requirements uniformly for all objects in a bucket. Enforcing retention is an
irreversible action and an object's retention cannot be reduced or removed by
anyone (including Google Support) until the retention period expires. This can
help primarily with regulatory and compliance requirements (e.g FINRA, SEC, and
CFTC) or regulations in other industries like health care.

> [!NOTE]
>
> Object retention can only be enabled on existing buckets through the Google
> Cloud Console UI. New buckets are supported for standard APIs.

-   **Enable object retention on a bucket:**

    ```bash
    gcloud storage buckets create gs://my-bucket --enable-per-object-retention
    ```

-   **Apply an unlocked retention policy to an object:**

    ```bash
    gcloud storage objects update gs://my-bucket/records/data.csv \
        --retention-mode=Unlocked \
        --retain-until=YYYY-MM-DDT00:00:00Z
    ```

> [!CAUTION]
>
> **CRITICAL:** Locking an object retention policy is irreversible. Ensure your
> compliance timeline is absolute before locking an object.

### Bucket Lock (Retention Policy)

Enforces an immutable retention policy across all objects in a bucket. Once
locked, the policy cannot be deleted or shortened by anyone (including Google
support) until the retention period expires, though it can be increased.

Bucket Lock can also help with regulatory and compliance requirements (FINRA,
SEC, and CFTC) or regulations in other industries like health care.

-   **Configure and lock a 100-day retention policy:**

    ```bash
    # 1. Set the retention policy
    gcloud storage buckets update gs://my-bucket --retention-period=100d

    # 2. Permanently lock the bucket (Requires explicit verification)
    gcloud storage buckets update gs://my-bucket --lock-retention-period
    ```

> [!CAUTION] **CRITICAL:** Locking a bucket retention policy is irreversible.
> Ensure your compliance timeline is absolute before locking the bucket.

### Object Holds

Object holds are metadata flags on individual objects. While the hold exists,
the object cannot be deleted or replaced, though its metadata can be updated.
There are two types of holds:

-   **Temporary Holds:** Objects cannot be deleted or replaced until the hold is
    explicitly released.
-   **Event-Based Holds:** Objects also cannot be deleted or replaced until the
    hold is explicitly released, but this is also used in conjunction with
    retention policies. A hold on an object subject to a retention policy will
    trigger an event which resets the retention timer as soon as the hold is
    released, meaning it is subject to its full retention period.

-   **Enforce holds on an object:**

    ```bash
    # Place a temporary hold for legal investigation
    gcloud storage objects update gs://my-bucket/legal/case-file.pdf --temporary-hold

    # Place an event-based hold for event-driven retention
    gcloud storage objects update gs://my-bucket/contracts/loan.pdf --event-based-hold
    ```

### Encryption Options

-   **Google-Managed Encryption Keys (GMEK):** Ideal for most users who need
    their data encrypted at rest without wanting to manage encryption keys,
    satisfying many compliance requirements automatically.
-   **Customer-Managed Encryption Keys (CMEK):** Allows users to control the
    lifecycle of encryption keys to meet specific compliance standards (e.g.
    PCI-DSS or HIPAA).
-   **Customer-Supplied Encryption Keys (CSEK):** Allows users to use an
    existing key management system outside of Google Cloud. The key is not
    stored within Google.
-   **Client-Side Encryption:** Ensures Google has no possible access to
    unencrypted data but places the full burden of key management, encryption,
    and decryption to the user.

--------------------------------------------------------------------------------

## 6. Cost Optimization & Object Lifecycle Management

GCS provides automated features and lifecycle policies to help manage storage
costs efficiently without manual intervention.

### Object Lifecycle Management (OLM)

Allows users to configure a set of rules which apply to current/future objects
in the bucket. When that criteria is met, Cloud Storage automatically performs a
specified action on the object, for example:

-   Downgrade storage class to Coldline for objects older than a year.
-   Delete objects created before January 1st, 2019.
-   Keep only the 3 most recent versions of each object in a bucket with
    versioning enabled.

Example Lifecycle policy:

```json
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "daysSinceNoncurrentTime": 7
        }
      }
    ]
  }
}
```

-   **Apply an OLM policy using gcloud:**

    ```bash
    gcloud storage buckets update gs://my-bucket --lifecycle-file=lifecycle.json
    ```

### Autoclass

Autoclass simplifies and automates cost saving for Cloud Storage data by moving
data that isn't accessed to colder storage classes (reducing storage cost) and
moving data that is accessed to Standard storage to optimize future accesses.

-   **Enable Autoclass on a bucket:**

    ```bash
    gcloud storage buckets update gs://my-bucket --enable-autoclass
    ```

--------------------------------------------------------------------------------

## 7. Cloud Audit Logs

Google Cloud Audit Logs provide oversight into operational and data access
activities within Cloud Storage. They are broken down into two primary
categories:

-   **Admin Activity Audit Logs:** Records operations that modify the
    configuration or metadata of a bucket or object (e.g., creating a bucket,
    updating IAM policies). These are enabled by default and cannot be disabled.
-   **Data Access Audit Logs:** Records API calls that read or write metadata or
    object data (e.g., uploading or downloading objects). These are disabled by
    default to manage log volume and ingestion costs.

### Enabling Data Access Logs for Cloud Storage

To turn on Data Access audit logs for Cloud Storage (`storage.googleapis.com`),
you configure the IAM policy at the project (or folder/organization) level.

> [!WARNING] High-volume Data Access logging (`DATA_READ` / `DATA_WRITE`) can
> generate massive log volumes, resulting in high ingestion and storage costs.
> Refer to
> [Managing Data Access Audit Log Costs](#managing-data-access-audit-log-costs)
> below to see how to configure cost-saving exemptions.

-   **Enable Data Access logs using gcloud:**

    ```bash
    # 1. Export the current project IAM policy
    gcloud projects get-iam-policy my-project > policy.yaml

    # 2. Append or update the auditConfigs section in policy.yaml:
    # auditConfigs:
    # - auditLogConfigs:
    #   - logType: DATA_READ
    #   - logType: DATA_WRITE
    #   service: storage.googleapis.com

    # 3. Apply the updated IAM policy
    gcloud projects set-iam-policy my-project policy.yaml
    ```

### Managing Data Access Audit Log Costs

To control costs, restrict service account logging:

*   **Exempt service accounts (Recommended):** Add `exemptedMembers` under
    `auditConfigs` in your IAM policy to prevent log generation:

    ```yaml
    auditConfigs:
    - service: storage.googleapis.com
      auditLogConfigs:
      - logType: DATA_READ
        exemptedMembers: [ "serviceAccount:my-sa@my-project.iam.gserviceaccount.com" ]
      - logType: DATA_WRITE
        exemptedMembers: [ "serviceAccount:my-sa@my-project.iam.gserviceaccount.com" ]
    ```

*   **Exclude logs:** Log Router exclusion filters discard logs *after*
    generation, which still incurs service processing load. Audit configuration
    is preferred.

*   **Rates:** Ingestion is $0.50/GiB (first 50 GiB/month free); storage is
    $0.01/GiB/month (first 30 days free).

*   **Formula:** `Monthly GiB = QPS * 2,628,000 * 1KB / 1e6 * 0.93`.

    *   `2,628,000`: Average seconds per month.
    *   `1KB`: Estimated size per audit log entry.
    *   `1e6`: Conversion factor from KB to GB (1,000,000 KB).
    *   `0.93`: Factor to convert decimal GB to binary GiB.

--------------------------------------------------------------------------------

## Documentation

-   [Cloud Storage IAM Overview](https://cloud.google.com/storage/docs/access-control/iam)
-   [Uniform Bucket-Level Access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)
-   [Legacy Object ACLs](https://docs.cloud.google.com/storage/docs/access-control/lists)
-   [Authentication](https://docs.cloud.google.com/docs/authentication)
-   [HMAC Keys](https://docs.cloud.google.com/storage/docs/authentication/hmackeys)
-   [Public Access Prevention](https://cloud.google.com/storage/docs/public-access-prevention)
-   [Soft Delete Overview](https://cloud.google.com/storage/docs/soft-delete)
-   [Object Lifecycle Management](https://cloud.google.com/storage/docs/lifecycle)
-   [Autoclass Overview](https://cloud.google.com/storage/docs/autoclass)
-   [Object Lock and Retention](https://cloud.google.com/storage/docs/object-lock)
-   [Bucket Lock](https://cloud.google.com/storage/docs/bucket-lock)
-   [Cloud Audit Logs for Cloud Storage](https://cloud.google.com/storage/docs/audit-logging)
-   [Cloud Logging Pricing](https://cloud.google.com/logging/pricing)
