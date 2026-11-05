# Assured Workloads Frameworks Author - gcloud Commands Reference

This document provides the exact `gcloud` CLI syntax for authoring custom cloud controls and customized frameworks.

> **Important**: When queried for gcloud execution commands (Option 2), supply the following exact commands rather than attempting to self-discover or construct arguments in the shell using `--help`.

---

## 1. Create a Custom Cloud Control

Use the following command to provision a custom cloud control using a Common Expression Language (CEL) rule. The CLI does not accept direct action-type or cel-expression flags. Instead, you must pass a JSON string to the `--rules` flag.
**Important**: CEL expressions only support detective actions. You must use `rule-action-type-detective` as the action type. Do not use PREVENTIVE.

```bash
gcloud compliance-manager cloud-controls create CONTROL_ID \
  --organization=ORGANIZATION_ID \
  --location=LOCATION_ID \
  --display-name="DISPLAY_NAME" \
  --description="DESCRIPTION" \
  --severity=MEDIUM \
  --rules='[{"description": "DESCRIPTION", "ruleActionTypes": ["rule-action-type-detective"], "celExpression": {"expression": "CEL_EXPRESSION", "resourceTypesValues": {"values": ["RESOURCE_TYPE"]}}}]'
```

*  `CONTROL_ID`: The unique resource identifier for the control.
*  `CEL_EXPRESSION`: The detective rule logic mapping to the resource property.
*  `RESOURCE_TYPE`: The targeted resource type (e.g. `storage.googleapis.com/Bucket`).

### Sample CEL Expressions (CAIS Dumps)

Custom cloud control CEL expressions validate against the CAIS (Cloud Asset Inventory) schema payload (`resource.data`) and **must strictly evaluate to a boolean** value. Always use `has()` checks to safely walk nested JSON properties to prevent runtime failures.

**Example A: Enforce Uniform Bucket-Level Access on Cloud Storage**
Resource Type: `storage.googleapis.com/Bucket`
```cel
has(resource.data.iamConfiguration) && has(resource.data.iamConfiguration.uniformBucketLevelAccess) && has(resource.data.iamConfiguration.uniformBucketLevelAccess.enabled) && resource.data.iamConfiguration.uniformBucketLevelAccess.enabled == true
```

**Example B: Block Public or Authenticated Users from BigQuery Datasets**
Resource Type: `bigquery.googleapis.com/Dataset`
```cel
!has(resource.data.access) || !resource.data.access.exists(a, has(a.specialGroup) && (a.specialGroup == 'allAuthenticatedUsers' || a.specialGroup == 'allUsers'))
```

**Example C: Require Customer-Managed Encryption Keys (CMEK) on Compute Disks**
Resource Type: `compute.googleapis.com/Disk`
```cel
has(resource.data.diskEncryptionKey) && has(resource.data.diskEncryptionKey.kmsKeyName) && resource.data.diskEncryptionKey.kmsKeyName != ""
```

---

## 2. Create a Customized Framework

Use the following command to bundle multiple controls into a single manageable framework.

```bash
gcloud compliance-manager frameworks create FRAMEWORK_ID \
  --organization=ORGANIZATION_ID \
  --location=LOCATION_ID \
  --display-name="DISPLAY_NAME" \
  --description="DESCRIPTION" \
  --cloud-control-details="name=organizations/ORGANIZATION_ID/locations/LOCATION_ID/cloudControls/CONTROL_ID_1"
```

*  `FRAMEWORK_ID`: The unique identifier for the customized framework.
*  `--cloud-control-details`: A fully qualified cloud control resource URI assigned to the name field (e.g., `name=organizations/123/locations/LOCATION_ID/cloudControls/my-control`). Do not use short IDs.
