# Google Cloud CLI Commands Reference for Compliance Environment Assessment

This reference documents the read-only Google Cloud CLI (`gcloud`) commands and server-side field projection masks utilized by the `assuredworkloads-environment-assessor` skill.

## Table of Contents

* [1. Scope Resolution & Ancestry](#1-scope-resolution-ancestry)
* [2. Resource Telemetry Ingestion (Cloud Asset Inventory)](#2-resource-telemetry-ingestion-cloud-asset-inventory)
* [3. Assured Workloads Framework & Control Discovery](#3-assured-workloads-framework-control-discovery)
* [4. Organization Policy Inspection](#4-organization-policy-inspection)
* [5. Framework Deployment via Google Cloud Console](#5-framework-deployment-via-google-cloud-console)

---

## 1. Scope Resolution & Ancestry

### Resolve Folder Parent & Organization
```bash
# Check direct parent of folder
gcloud resource-manager folders describe FOLDER_ID --format="value(parent)"
```
*If the parent is `folders/...`, recursively inspect until `organizations/{org_id}` is found.*

### Resolve Project Ancestry
```bash
# List all ancestors from project up to root Organization
gcloud projects get-ancestors PROJECT_ID --format="value(id,type)"
```

---

## 2. Resource Telemetry Ingestion (Cloud Asset Inventory)

### Pass 1: Macro Footprint & API Enumeration (100% Coverage Across Scope)
```bash
gcloud asset search-all-resources \
  --scope="folders/123456" \
  --page-size=500 \
  --format="json(name,assetType,location)" > macro_telemetry.json
```

### Pass 2: Conditional Targeted Deep Ingestion for CMEK Readiness (`kmsKeys`)
```bash
gcloud asset search-all-resources \
  --scope="folders/123456" \
  --asset-types="${TARGET_TYPES}" \
  --page-size=500 \
  --format="json(name,assetType,location,kmsKeys)" > deep_telemetry.json
```
*Note: `search-all-resources` is free of charge ($0 billing impact), but Google Cloud requires an administrative project with an active Cloud Billing account attached to allocate API rate limits (`gcloud config set project PROJECT_ID`).*

### Key Field Extraction
* **`name`**: Cloud resource URI (e.g. `//compute.googleapis.com/projects/.../instances/...`).
* **`assetType`**: Google Cloud resource type (e.g. `compute.googleapis.com/Instance`, `storage.googleapis.com/Bucket`).
* **`location`**: Region or zone string (e.g. `us-central1`, `europe-west3`, `us-east4-a`).
* **`kmsKeys`**: Customer-Managed Encryption Key (CMEK) URIs bound to the resource.

---

## 3. Assured Workloads Framework & Control Discovery

### List & Cache Built-in Assured Workloads Frameworks (Including Bound Parameters)
```bash
if [ ! -s frameworks.json ]; then
  gcloud compliance-manager frameworks list \
    --organization=ORGANIZATION_ID \
    --location=global \
    --filter="category:ASSURED_WORKLOADS" \
    --format="json(name,majorRevisionId,displayName,description,category,cloudControlDetails)" > frameworks.json
fi
```

### On-Demand Service Follow-Up: Describe a Specific Cloud Control
```bash
gcloud compliance-manager cloud-controls describe CONTROL_ID \
  --organization=ORGANIZATION_ID \
  --location=global \
  --format="json(name,displayName,description,supportedEnforcementModes,remediationSteps,parameterSpec)"
```

---

## 4. Organization Policy Inspection

### Describe Effective Universal Constraints on Scope (`38/38` Frameworks)
```bash
# Check effective resource locations constraint
gcloud org-policies describe gcp.resourceLocations \
  --folder=FOLDER_ID \
  --effective \
  --format="json(name,spec.rules)"

# Check effective service usage restriction (SUR) constraint
gcloud org-policies describe gcp.restrictServiceUsage \
  --folder=FOLDER_ID \
  --effective \
  --format="json(name,spec.rules)"

# Check effective TLS version restriction constraint
gcloud org-policies describe gcp.restrictTLSVersion \
  --folder=FOLDER_ID \
  --effective \
  --format="json(name,spec.rules)"
```

---

## 5. Framework Deployment via Google Cloud Console

After completing the read-only compliance assessment, guide the customer or
cloud administrator to deploy the recommended framework in the Google Cloud
Console **Assured Workloads -> Frameworks** tab:

```
https://console.cloud.google.com/compliance/configure/frameworks?organizationId=ORGANIZATION_ID
```

### Recommended Deployment Modes

* **Existing Workloads (Folders or Projects)**: Deploy in
  **Monitoring (`Detective`) mode** first to assess posture and remediate
  findings with zero Day 0 Organization Policy mutations, and then transition
  to **Preventive** mode.
* **New Workloads (Folders or Projects)**: Start directly in **Preventive**
  mode or in **Monitoring (`Detective`) mode**.
