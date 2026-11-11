# Go SDK Reference & Examples

This guide translates a **Draft Bucket Creation Plan** (from Phase 2) into the
official Cloud Storage Go client library (`cloud.google.com/go/storage`).

*   [Cloud Storage Go Package Reference](https://pkg.go.dev/cloud.google.com/go/storage)

## Version Requirements

> [!IMPORTANT]
>
> **Encryption Enforcement Config**
> (`CustomerSuppliedEncryptionEnforcementConfig`) requires
> `cloud.google.com/go/storage` version **1.61.0** or higher. If using a version
> below 1.61.0, configure this setting via the [REST API](rest.md),
> [gcloud](gcloud.md), or [Terraform](terraform.md).

## Translation Mapping Table

Draft Plan Field / Setting          | Go SDK Feature / Attribute (`cloud.google.com/go/storage`)
:---------------------------------- | :---------------------------------------------------------
**Client Initialization**           | `client, err := storage.NewClient(ctx)`
**Bucket Name & Creation**          | `bucket := client.Bucket(bucketName); err := bucket.Create(ctx, projectID, attrs)`
**Location**                        | `BucketAttrs.Location: "us-central1"`
**Placement (Dual-Region / Zonal)** | `BucketAttrs.CustomPlacementConfig: &storage.CustomPlacementConfig{DataLocations: []string{"us-east1-b"}}`
**Replication Speed (RPO)**         | `BucketAttrs.RPO: storage.RPOAsyncTurbo`
**Storage Class**                   | `BucketAttrs.StorageClass: "STANDARD"` (or `"NEARLINE"`, `"COLDLINE"`, `"ARCHIVE"`, `"RAPID"`)
**UBLA**                            | `BucketAttrs.UniformBucketLevelAccess: storage.UniformBucketLevelAccess{Enabled: true}`
**Public Access Prevention**        | `BucketAttrs.PublicAccessPrevention: storage.PublicAccessPreventionEnforced` (or `storage.PublicAccessPreventionInherited`)
**Soft Delete**                     | `BucketAttrs.SoftDeletePolicy: &storage.SoftDeletePolicy{RetentionDuration: 7 * 24 * time.Hour}` (`0` to disable)
**Object Versioning**               | `BucketAttrs.VersioningEnabled: true`
**Encryption (CMEK)**               | `BucketAttrs.Encryption: &storage.BucketEncryption{DefaultKMSKeyName: kmsKeyID}`
**Restrict Encryption (CSEK)**      | `BucketAttrs.CustomerSuppliedEncryptionEnforcementConfig: &storage.EncryptionEnforcementConfig{RestrictionMode: storage.FullyRestricted}` (**v1.61.0+**)
**Autoclass**                       | `BucketAttrs.Autoclass: &storage.Autoclass{Enabled: true}`
**Hierarchical Namespace**          | `BucketAttrs.HierarchicalNamespace: &storage.HierarchicalNamespace{Enabled: true}`
**Labels**                          | `BucketAttrs.Labels: map[string]string{"key": "value"}`
**IP Filtering**                    | *Not exposed in Go v1 client library* (use [REST API](rest.md), [gcloud](gcloud.md), or [Terraform](terraform.md))
**Allow Cross-Org VPCs**            | *Not exposed in Go v1 client library* (use [REST API](rest.md), [gcloud](gcloud.md), or [Terraform](terraform.md))
**Lifecycle Policies (OLM)**        | `BucketAttrs.Lifecycle: storage.Lifecycle{Rules: []storage.LifecycleRule{...}}`
**CORS**                            | `BucketAttrs.CORS: []storage.CORS{{MaxAge: 3600 * time.Second, Methods: ..., Origins: ..., ResponseHeaders: ...}}`
**Website Configuration**           | `BucketAttrs.Website: &storage.BucketWebsite{MainPageSuffix: "index.html", NotFoundPage: "404.html"}`
**Public IAM Policy**               | `policy, _ := bucket.IAM().Policy(ctx)` -> `policy.Add(iam.AllUsers, "roles/storage.objectViewer")` -> `bucket.IAM().SetPolicy(ctx, policy)`
**Pub/Sub Notifications**           | `bucket.AddNotification(ctx, &storage.Notification{TopicProjectID: ..., TopicID: ..., PayloadFormat: storage.JSONPayload})`
**Bucket Retention Period**         | `BucketAttrs.RetentionPolicy: &storage.RetentionPolicy{RetentionPeriod: 90 * 24 * time.Hour}`
**Lock Bucket Retention Policy**    | `bucket.If(storage.BucketConditions{MetagenerationMatch: attrs.MetaGeneration}).LockRetentionPolicy(ctx)` (**irreversible**)
**Object Retention (Object Lock)**  | `bucket := client.Bucket(bucketName).SetObjectRetention(true)` (before `bucket.Create`)
**Set Object Retention**            | `wc.ObjectAttrs.Retention = &storage.ObjectRetention{Mode: "Locked", RetainUntil: ...}` (or `"Unlocked"`; or `obj.Update(ctx, storage.ObjectAttrsToUpdate{Retention: ...})`, chaining `obj.OverrideUnlockedRetention(true)` to shorten/remove/lock `Unlocked`)
**Rapid Cache**                     | `StorageControlClient.CreateAnywhereCache` (`cloud.google.com/go/storage/control/apiv2`)

--------------------------------------------------------------------------------

## Go SDK Examples

### Example 1: Sensitive Data / Compliance (UBLA, PAP, CMEK, CSEK Restricted, Soft Delete, Retention, Autoclass, Labels, OLM)

*(For a baseline secure bucket, keep `STANDARD`, UBLA, enforced PAP, 7-day Soft
Delete, `CustomerSuppliedEncryptionEnforcementConfig` (`FullyRestricted`), and
`projectID`, omitting unused optional fields in `storage.BucketAttrs`.)*

```go
import (
    "context"
    "time"

    "cloud.google.com/go/storage"
)

func CreateComplianceBucket(ctx context.Context, client *storage.Client, projectID, bucketName, kmsKeyID string) (*storage.BucketAttrs, error) {
    bucket := client.Bucket(bucketName)
    attrs := &storage.BucketAttrs{
        Location:     "us-central1",
        StorageClass: "STANDARD",
        UniformBucketLevelAccess: storage.UniformBucketLevelAccess{
            Enabled: true,
        },
        PublicAccessPrevention: storage.PublicAccessPreventionEnforced,
        Encryption: &storage.BucketEncryption{
            DefaultKMSKeyName: kmsKeyID,
        },
        // Requires cloud.google.com/go/storage >= v1.61.0
        CustomerSuppliedEncryptionEnforcementConfig: &storage.EncryptionEnforcementConfig{
            RestrictionMode: storage.FullyRestricted,
        },
        // NOTE: IP Filtering is not exposed in the Go v1 client library; configure via REST, gcloud, or Terraform.
        // WARNING: Locking the retention policy is permanent and irreversible:
        // bucket.If(storage.BucketConditions{MetagenerationMatch: attrs.MetaGeneration}).LockRetentionPolicy(ctx)
        RetentionPolicy: &storage.RetentionPolicy{
            RetentionPeriod: 90 * 24 * time.Hour,
        },
        Autoclass: &storage.Autoclass{
            Enabled: true,
        },
        Labels: map[string]string{
            "data-class": "pii",
            "owner":      "security-team",
        },
        Lifecycle: storage.Lifecycle{
            Rules: []storage.LifecycleRule{
                {
                    Action:    storage.LifecycleAction{Type: "AbortIncompleteMultipartUpload"},
                    Condition: storage.LifecycleCondition{AgeInDays: 7},
                },
            },
        },
        SoftDeletePolicy: &storage.SoftDeletePolicy{
            RetentionDuration: 7 * 24 * time.Hour,
        },
    }
    if err := bucket.Create(ctx, projectID, attrs); err != nil {
        return nil, err
    }
    return bucket.Attrs(ctx)
}
```

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website, CORS, Versioning)

```go
import (
    "context"
    "time"

    "cloud.google.com/go/iam"
    "cloud.google.com/go/storage"
)

func CreateStaticWebsiteBucket(ctx context.Context, client *storage.Client, projectID, bucketName string) (*storage.BucketAttrs, error) {
    bucket := client.Bucket(bucketName)
    attrs := &storage.BucketAttrs{
        Location:     "US",
        StorageClass: "STANDARD",
        UniformBucketLevelAccess: storage.UniformBucketLevelAccess{
            Enabled: true,
        },
        PublicAccessPrevention: storage.PublicAccessPreventionInherited,
        VersioningEnabled:      true,
        SoftDeletePolicy: &storage.SoftDeletePolicy{
            RetentionDuration: 7 * 24 * time.Hour,
        },
        Website: &storage.BucketWebsite{
            MainPageSuffix: "index.html",
            NotFoundPage:   "404.html",
        },
        CORS: []storage.CORS{{
            MaxAge:          3600 * time.Second,
            Methods:         []string{"GET", "HEAD", "OPTIONS"},
            Origins:         []string{"*"},
            ResponseHeaders: []string{"Content-Type"},
        }},
    }
    if err := bucket.Create(ctx, projectID, attrs); err != nil {
        return nil, err
    }

    iamHandle := bucket.IAM()
    policy, err := iamHandle.Policy(ctx)
    if err != nil {
        return nil, err
    }
    policy.Add(iam.AllUsers, "roles/storage.objectViewer")
    if err := iamHandle.SetPolicy(ctx, policy); err != nil {
        return nil, err
    }
    return bucket.Attrs(ctx)
}
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

```go
import (
    "context"

    "cloud.google.com/go/storage"
)

func CreateCheckpointBucket(ctx context.Context, client *storage.Client, projectID, bucketName string) (*storage.BucketAttrs, error) {
    bucket := client.Bucket(bucketName)
    attrs := &storage.BucketAttrs{
        Location:     "us-east1",
        StorageClass: "RAPID",
        UniformBucketLevelAccess: storage.UniformBucketLevelAccess{
            Enabled: true,
        },
        PublicAccessPrevention: storage.PublicAccessPreventionEnforced,
        CustomPlacementConfig: &storage.CustomPlacementConfig{
            DataLocations: []string{"us-east1-b"},
        },
        HierarchicalNamespace: &storage.HierarchicalNamespace{
            Enabled: true,
        },
        Lifecycle: storage.Lifecycle{
            Rules: []storage.LifecycleRule{
                {
                    Action:    storage.LifecycleAction{Type: "Delete"},
                    Condition: storage.LifecycleCondition{AgeInDays: 14},
                },
            },
        },
        SoftDeletePolicy: &storage.SoftDeletePolicy{
            RetentionDuration: 0,
        },
    }
    if err := bucket.Create(ctx, projectID, attrs); err != nil {
        return nil, err
    }
    return bucket.Attrs(ctx)
}
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

> [!CAUTION]
>
> Setting per-object retention mode to `"Locked"` is permanent and irreversible.
> Once set, the mode cannot be changed back, the retention date can only be
> extended (never shortened or removed), and objects cannot be deleted or
> overwritten by anyone until the retention date expires.

```go
import (
    "context"
    "time"

    "cloud.google.com/go/storage"
)

func CreateRegulatoryWormBucket(ctx context.Context, client *storage.Client, projectID, bucketName, kmsKeyID string) (*storage.BucketAttrs, error) {
    bucket := client.Bucket(bucketName).SetObjectRetention(true)
    attrs := &storage.BucketAttrs{
        Location:     "us-east1",
        StorageClass: "ARCHIVE",
        UniformBucketLevelAccess: storage.UniformBucketLevelAccess{
            Enabled: true,
        },
        PublicAccessPrevention: storage.PublicAccessPreventionEnforced,
        Encryption: &storage.BucketEncryption{
            DefaultKMSKeyName: kmsKeyID,
        },
        Labels: map[string]string{
            "compliance-type":  "regulatory",
            "retention-period": "7y",
        },
        SoftDeletePolicy: &storage.SoftDeletePolicy{
            RetentionDuration: 7 * 24 * time.Hour,
        },
        Lifecycle: storage.Lifecycle{
            Rules: []storage.LifecycleRule{
                {
                    Action:    storage.LifecycleAction{Type: "Delete"},
                    Condition: storage.LifecycleCondition{AgeInDays: 2555},
                },
            },
        },
    }
    if err := bucket.Create(ctx, projectID, attrs); err != nil {
        return nil, err
    }
    return bucket.Attrs(ctx)
}

func UploadObjectWithRetention(ctx context.Context, client *storage.Client, bucketName, objectName string) error {
    wc := client.Bucket(bucketName).Object(objectName).NewWriter(ctx)
    wc.ObjectAttrs.Retention = &storage.ObjectRetention{
        Mode:        "Locked",
        RetainUntil: time.Date(2030, 12, 31, 23, 59, 59, 0, time.UTC),
    }
    if _, err := wc.Write([]byte("compliance data")); err != nil {
        wc.Close()
        return err
    }
    return wc.Close()
}
```
