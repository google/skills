# Java SDK Reference & Examples

This guide translates a **Draft Bucket Creation Plan** (from Phase 2) into the
official Cloud Storage Java client library (`google-cloud-storage`).

*   [Cloud Storage Client for Java Documentation](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview)

## Version Requirements

> [!IMPORTANT]
>
> **Encryption Enforcement Config**
> (`CustomerSuppliedEncryptionEnforcementConfig`) requires the Java SDK version
> **2.55.0** or higher. If using a version below 2.55.0, configure this setting
> via the [REST API](rest.md), [gcloud](gcloud.md), or
> [Terraform](terraform.md).

## Translation Mapping Table

Draft Plan Field / Setting          | Java SDK Feature / Attribute (`com.google.cloud.storage`)
:---------------------------------- | :--------------------------------------------------------
**Client Initialization**           | `Storage storage = StorageOptions.newBuilder().setProjectId(projectId).build().getService();`
**Bucket Name & Creation**          | `BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)...build(); storage.create(bucketInfo);`
**Location**                        | `BucketInfo.Builder.setLocation("us-central1")`
**Placement (Dual-Region / Zonal)** | `BucketInfo.Builder.setCustomPlacementConfig(CustomPlacementConfig.newBuilder().setDataLocations(List).build())`
**Replication Speed (RPO)**         | `BucketInfo.Builder.setRpo(Rpo.ASYNC_TURBO)`
**Storage Class**                   | `BucketInfo.Builder.setStorageClass(StorageClass.STANDARD)` (or `NEARLINE`, `COLDLINE`, `ARCHIVE`, `StorageClass.valueOf("RAPID")`)
**UBLA**                            | `IamConfiguration.newBuilder().setIsUniformBucketLevelAccessEnabled(true)`
**Public Access Prevention**        | `IamConfiguration.newBuilder().setPublicAccessPrevention(BucketInfo.PublicAccessPrevention.ENFORCED)` (or `INHERITED`)
**Soft Delete**                     | `BucketInfo.Builder.setSoftDeletePolicy(SoftDeletePolicy.newBuilder().setRetentionDuration(Duration.ofDays(7)).build())` (`Duration.ZERO` to disable)
**Object Versioning**               | `BucketInfo.Builder.setVersioningEnabled(true)`
**Encryption (CMEK)**               | `BucketInfo.Builder.setDefaultKmsKeyName(kmsKeyId)`
**Restrict Encryption (CSEK)**      | `BucketInfo.Builder.setCustomerSuppliedEncryptionEnforcementConfig(CustomerSuppliedEncryptionEnforcementConfig.of(EncryptionEnforcementRestrictionMode.FULLY_RESTRICTED))` (**v2.55.0+**)
**Autoclass**                       | `BucketInfo.Builder.setAutoclass(BucketInfo.Autoclass.newBuilder().setEnabled(true).build())`
**Hierarchical Namespace**          | `BucketInfo.Builder.setHierarchicalNamespace(BucketInfo.HierarchicalNamespace.newBuilder().setEnabled(true).build())`
**Labels**                          | `BucketInfo.Builder.setLabels(labelsMap)`
**IP Filtering**                    | `BucketInfo.Builder.setIpFilter(BucketInfo.IpFilter.newBuilder()...build())`
**Allow Cross-Org VPCs**            | `BucketInfo.IpFilter.Builder.setAllowCrossOrgVpcs(false)`
**Lifecycle Policies (OLM)**        | `BucketInfo.Builder.setLifecycleRules(Collections.singletonList(new BucketInfo.LifecycleRule(action, condition)))`
**CORS**                            | `BucketInfo.Builder.setCors(Collections.singletonList(cors))`
**Website Configuration**           | `BucketInfo.Builder.setIndexPage("index.html").setNotFoundPage("404.html")`
**Public IAM Policy**               | `Policy policy = storage.getIamPolicy(bucketName)` -> `.toBuilder().addIdentity(StorageRoles.objectViewer(), Identity.allUsers()).build()` -> `storage.setIamPolicy(bucketName, policy)`
**Pub/Sub Notifications**           | `storage.createNotification(bucketName, notificationInfo)`
**Bucket Retention Period**         | `BucketInfo.Builder.setRetentionPeriodDuration(Duration.ofDays(90))`
**Lock Bucket Retention Policy**    | `bucket.lockRetentionPolicy(Storage.BucketTargetOption.metagenerationMatch())` (or `storage.lockRetentionPolicy(bucketInfo, ...)`; **irreversible**)
**Object Retention (Object Lock)**  | `storage.create(bucketInfo, Storage.BucketTargetOption.enableObjectRetention(true))`
**Set Object Retention**            | `BlobInfo.Builder.setRetention(BlobInfo.Retention.newBuilder().setMode(BlobInfo.Retention.Mode.LOCKED).setRetainUntilTime(retainUntil).build())` (or `BlobInfo.Retention.Mode.UNLOCKED`; pass `Storage.BlobTargetOption.overrideUnlockedRetention(true)` on `storage.update` to shorten/remove/lock `UNLOCKED`)
**Rapid Cache**                     | `StorageControlClient.createAnywhereCache` (`com.google.storage.control.v2.StorageControlClient`)

--------------------------------------------------------------------------------

## Java SDK Examples

### Example 1: Sensitive Data / Compliance (UBLA, PAP, CMEK, CSEK Restricted, Soft Delete, Retention, Autoclass, Labels, OLM, IP Filter)

*(For a baseline secure bucket, keep `projectId`, `StorageClass.STANDARD`, UBLA,
enforced PAP, 7-day Soft Delete, and
`setCustomerSuppliedEncryptionEnforcementConfig(csekConfig)`
(`FULLY_RESTRICTED`), omitting unused optional builder calls on
`BucketInfo.newBuilder(bucketName)`.)*

```java
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.BucketInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageClass;
import com.google.cloud.storage.StorageOptions;
import java.time.Duration;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class GcsExamples {

  public static Bucket createComplianceBucket(String projectId, String bucketName, String kmsKeyId) {
    Storage storage = StorageOptions.newBuilder()
        .setProjectId(projectId)
        .build()
        .getService();

    BucketInfo.IamConfiguration iamConfig = BucketInfo.IamConfiguration.newBuilder()
        .setIsUniformBucketLevelAccessEnabled(true)
        .setPublicAccessPrevention(BucketInfo.PublicAccessPrevention.ENFORCED)
        .build();

    // Requires google-cloud-storage >= 2.55.0
    BucketInfo.CustomerSuppliedEncryptionEnforcementConfig csekConfig =
        BucketInfo.CustomerSuppliedEncryptionEnforcementConfig.of(
            BucketInfo.EncryptionEnforcementRestrictionMode.FULLY_RESTRICTED);
    BucketInfo.CustomerManagedEncryptionEnforcementConfig cmekConfig =
        BucketInfo.CustomerManagedEncryptionEnforcementConfig.of(
            BucketInfo.EncryptionEnforcementRestrictionMode.NOT_RESTRICTED);
    BucketInfo.GoogleManagedEncryptionEnforcementConfig gmekConfig =
        BucketInfo.GoogleManagedEncryptionEnforcementConfig.of(
            BucketInfo.EncryptionEnforcementRestrictionMode.NOT_RESTRICTED);

    BucketInfo.IpFilter.PublicNetworkSource publicSource =
        BucketInfo.IpFilter.PublicNetworkSource.of(Collections.singletonList("192.0.2.0/24"));
    BucketInfo.IpFilter.VpcNetworkSource vpcSource =
        BucketInfo.IpFilter.VpcNetworkSource.newBuilder()
            .setNetwork("projects/" + projectId + "/global/networks/NETWORK_NAME")
            .setAllowedIpCidrRanges(Collections.singletonList("10.0.0.0/16"))
            .build();
    BucketInfo.IpFilter ipFilter = BucketInfo.IpFilter.newBuilder()
        .setMode("Enabled")
        .setAllowAllServiceAgentAccess(true)
        .setAllowCrossOrgVpcs(false)
        .setPublicNetworkSource(publicSource)
        .setVpcNetworkSources(Collections.singletonList(vpcSource))
        .build();

    Map<String, String> labels = new HashMap<>();
    labels.put("data-class", "pii");
    labels.put("owner", "security-team");

    BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)
        .setLocation("us-central1")
        .setStorageClass(StorageClass.STANDARD)
        .setIamConfiguration(iamConfig)
        .setDefaultKmsKeyName(kmsKeyId)
        .setCustomerSuppliedEncryptionEnforcementConfig(csekConfig)
        .setCustomerManagedEncryptionEnforcementConfig(cmekConfig)
        .setGoogleManagedEncryptionEnforcementConfig(gmekConfig)
        .setIpFilter(ipFilter)
        .setSoftDeletePolicy(BucketInfo.SoftDeletePolicy.newBuilder()
            .setRetentionDuration(Duration.ofDays(7))
            .build())
        .setRetentionPeriodDuration(Duration.ofDays(90))
        .setAutoclass(BucketInfo.Autoclass.newBuilder().setEnabled(true).build())
        .setLabels(labels)
        .setLifecycleRules(Collections.singletonList(
            new BucketInfo.LifecycleRule(
                BucketInfo.LifecycleRule.LifecycleAction.newAbortIncompleteMPUploadAction(),
                BucketInfo.LifecycleRule.LifecycleCondition.newBuilder().setAge(7).build()
            )
        ))
        .build();

    return storage.create(bucketInfo);
  }

  // WARNING: Locking the retention policy is permanent and irreversible.
  public static Bucket lockRetentionPolicy(String projectId, String bucketName) {
    Storage storage = StorageOptions.newBuilder().setProjectId(projectId).build().getService();
    return storage.get(bucketName).lockRetentionPolicy(Storage.BucketTargetOption.metagenerationMatch());
  }
}
```

### Example 2: Static Website Hosting (Multi-Region `US`, Public Access, Website, CORS, Versioning)

```java
import com.google.cloud.Identity;
import com.google.cloud.Policy;
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.BucketInfo;
import com.google.cloud.storage.Cors;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageClass;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.storage.StorageRoles;
import java.time.Duration;
import java.util.Arrays;
import java.util.Collections;

public class GcsExamples {

  public static Bucket createStaticWebsiteBucket(String projectId, String bucketName) {
    Storage storage = StorageOptions.newBuilder().setProjectId(projectId).build().getService();

    Cors cors = Cors.newBuilder()
        .setMaxAgeSeconds(3600)
        .setMethods(Arrays.asList(HttpMethod.GET, HttpMethod.HEAD, HttpMethod.OPTIONS))
        .setOrigins(Collections.singletonList(Cors.Origin.of("*")))
        .setResponseHeaders(Collections.singletonList("Content-Type"))
        .build();

    BucketInfo.IamConfiguration iamConfig = BucketInfo.IamConfiguration.newBuilder()
        .setIsUniformBucketLevelAccessEnabled(true)
        .setPublicAccessPrevention(BucketInfo.PublicAccessPrevention.INHERITED)
        .build();

    BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)
        .setStorageClass(StorageClass.STANDARD)
        .setLocation("US")
        .setIamConfiguration(iamConfig)
        .setVersioningEnabled(true)
        .setSoftDeletePolicy(BucketInfo.SoftDeletePolicy.newBuilder()
            .setRetentionDuration(Duration.ofDays(7))
            .build())
        .setIndexPage("index.html")
        .setNotFoundPage("404.html")
        .setCors(Collections.singletonList(cors))
        .build();

    Bucket bucket = storage.create(bucketInfo);

    Policy policy = storage.getIamPolicy(bucketName).toBuilder()
        .addIdentity(StorageRoles.objectViewer(), Identity.allUsers())
        .build();
    storage.setIamPolicy(bucketName, policy);
    return bucket;
  }
}
```

### Example 3: AI/ML Checkpointing (Zonal `RAPID` Bucket in `us-east1-b`, HNS, Soft Delete Disabled)

```java
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.BucketInfo;
import com.google.cloud.storage.BucketInfo.CustomPlacementConfig;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageClass;
import com.google.cloud.storage.StorageOptions;
import java.time.Duration;
import java.util.Collections;

public class GcsExamples {

  public static Bucket createCheckpointBucket(String projectId, String bucketName) {
    Storage storage = StorageOptions.newBuilder().setProjectId(projectId).build().getService();

    BucketInfo.IamConfiguration iamConfig = BucketInfo.IamConfiguration.newBuilder()
        .setIsUniformBucketLevelAccessEnabled(true)
        .setPublicAccessPrevention(BucketInfo.PublicAccessPrevention.ENFORCED)
        .build();

    BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)
        .setStorageClass(StorageClass.valueOf("RAPID"))
        .setLocation("us-east1")
        .setCustomPlacementConfig(CustomPlacementConfig.newBuilder()
            .setDataLocations(Collections.singletonList("us-east1-b"))
            .build())
        .setIamConfiguration(iamConfig)
        .setHierarchicalNamespace(BucketInfo.HierarchicalNamespace.newBuilder().setEnabled(true).build())
        .setSoftDeletePolicy(BucketInfo.SoftDeletePolicy.newBuilder()
            .setRetentionDuration(Duration.ZERO)
            .build())
        .setLifecycleRules(Collections.singletonList(
            new BucketInfo.LifecycleRule(
                BucketInfo.LifecycleRule.LifecycleAction.newDeleteAction(),
                BucketInfo.LifecycleRule.LifecycleCondition.newBuilder().setAge(14).build()
            )
        ))
        .build();

    return storage.create(bucketInfo);
  }
}
```

### Example 4: WORM Archive with Object Lock (Per-Object Retention)

> [!CAUTION]
>
> Setting per-object retention mode to `BlobInfo.Retention.Mode.LOCKED` is
> permanent and irreversible. Once set, the mode cannot be changed back, the
> retention date can only be extended (never shortened or removed), and objects
> cannot be deleted or overwritten by anyone until the retention date expires.

```java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.BucketInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageClass;
import com.google.cloud.storage.StorageOptions;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class GcsExamples {

  public static Bucket createRegulatoryWormBucket(String projectId, String bucketName, String kmsKeyId) {
    Storage storage = StorageOptions.newBuilder().setProjectId(projectId).build().getService();

    BucketInfo.IamConfiguration iamConfig = BucketInfo.IamConfiguration.newBuilder()
        .setIsUniformBucketLevelAccessEnabled(true)
        .setPublicAccessPrevention(BucketInfo.PublicAccessPrevention.ENFORCED)
        .build();

    Map<String, String> labels = new HashMap<>();
    labels.put("compliance-type", "regulatory");
    labels.put("retention-period", "7y");

    BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)
        .setStorageClass(StorageClass.ARCHIVE)
        .setLocation("us-east1")
        .setIamConfiguration(iamConfig)
        .setDefaultKmsKeyName(kmsKeyId)
        .setLabels(labels)
        .setSoftDeletePolicy(BucketInfo.SoftDeletePolicy.newBuilder()
            .setRetentionDuration(Duration.ofDays(7))
            .build())
        .setLifecycleRules(Collections.singletonList(
            new BucketInfo.LifecycleRule(
                BucketInfo.LifecycleRule.LifecycleAction.newDeleteAction(),
                BucketInfo.LifecycleRule.LifecycleCondition.newBuilder().setAge(2555).build()
            )
        ))
        .build();

    return storage.create(bucketInfo, Storage.BucketTargetOption.enableObjectRetention(true));
  }

  public static Blob uploadObjectWithRetention(String projectId, String bucketName, String objectName, byte[] content) {
    Storage storage = StorageOptions.newBuilder().setProjectId(projectId).build().getService();
    OffsetDateTime retainUntil = OffsetDateTime.of(2030, 12, 31, 23, 59, 59, 0, ZoneOffset.UTC);

    BlobInfo blobInfo = BlobInfo.newBuilder(bucketName, objectName)
        .setRetention(BlobInfo.Retention.newBuilder()
            .setMode(BlobInfo.Retention.Mode.LOCKED)
            .setRetainUntilTime(retainUntil)
            .build())
        .build();

    return storage.create(blobInfo, content);
  }
}
```
