---
name: assured-workloads-basics
description: >-
  Provisions, inspects, updates, and deletes Google Cloud Assured Workloads V1
  compliant folders, CMEK settings, Sovereign Controls by Partners, and service
  usage restrictions. Use when creating, listing, describing, updating, or
  deleting an Assured Workloads workload for any compliance regime or data boundary
  (FedRAMP, DoD IL2/IL4/IL5, ITAR, CJIS, Healthcare, Sovereign Controls by
  Partners, or Regional Data Boundaries). Don't use for brownfield assessments
  or custom frameworks (use assuredworkloads-environment-assessor or
  assuredworkloads-frameworks-*), or non-compliant folders.
metadata:
  version: "1.0.1"
  category: Security
---

# Google Cloud Assured Workloads Basics (V1 GA)

Validate prerequisites, create Assured Workloads V1 compliant folders, allowlist compliant services, and list, inspect, update, or delete existing workloads using `gcloud` and the Google Cloud Python Client Libraries (`google-cloud-assured-workloads` and `google-api-python-client`).

## Usage Attribution

For all `gcloud` CLI, REST API, and MCP attribution requirements when executing commands with this skill, follow the instructions in [Usage Attribution](references/attribution.md).

## Mandatory Guardrails

1. **No Fabrication:** Never invent Organization IDs, Billing Account IDs, Folder IDs, Project IDs, Workload IDs, or Compliance Regime enums. Validate parameters with `scripts/validate_params.py` before running commands.
2. **Regional / Multi-Regional Locations & CLI Surface:** Assured Workloads V1 does **not** support `--location=global`; always use a regional or multi-regional location compatible with the compliance regime (see [references/regimes.md](references/regimes.md)). Never use `gcloud compliance-manager` commands for Assured Workloads V1 workloads.
3. **Human Confirmation Before Mutation:** Read-only operations (`list`, `describe`, and `scripts/manage_workload_updates.py --action=list`) can run immediately after validation, but you **must** obtain explicit user confirmation before executing any mutating or destructive command (`create`, `restrict_allowed_resources.py`, `update`, `manage_workload_updates.py --action=apply`, `delete`, `folders delete`, or `projects delete`).
4. **Telemetry Attribution & Regional Endpoints:**
   * Prefix every `gcloud` command you execute directly with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:assured-workloads-basics)"` (see [Usage Attribution](references/attribution.md)).
   * Configure Python GAPIC and Discovery clients with regional `ClientOptions(api_endpoint="{location}-assuredworkloads.googleapis.com")`.

## Step 0: Prerequisites & Environment Setup

Verify these 5 prerequisites before running Assured Workloads operations:

1. **CLI & Python Libraries:** Install the Google Cloud SDK (`gcloud` — see the [Google Cloud SDK Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)) and Python client libraries:
   ```bash
   pip install "google-cloud-assured-workloads>=1.0,<2" "google-api-python-client>=2.0,<3" "google-auth>=2.0,<3"
   ```
2. **Dual Authentication (CLI + ADC):** Authenticate both `gcloud` and Application Default Credentials (`gcloud auth login && gcloud auth application-default login`, or `gcloud auth activate-service-account --key-file=/path/to/key.json` + `export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"`).
3. **Quota & Admin Project:** `gcloud config set project {admin_project_id}` and `gcloud auth application-default set-quota-project {admin_project_id}`.
4. **API Enablement:** Enable the Assured Workloads API (`assuredworkloads.googleapis.com`):
   ```bash
   gcloud services enable assuredworkloads.googleapis.com --project={admin_project_id}
   ```
5. **Organization-Level IAM Roles (`organizations/{org_id}`):**
   * **Caller:** `roles/assuredworkloads.admin` (or `roles/assuredworkloads.reader` / `roles/assuredworkloads.editor` for read-only `list`/`describe`), `roles/resourcemanager.organizationViewer`, and `roles/billing.user` on `--billing-account=billingAccounts/{billing_id}` when creating workloads (plus `billing.resourceAssociations.create` on `--partner-services-billing-account` for partner workloads).
   * **Assured Workloads Service Agent (`service-{org_number}@gcp-sa-assuredworkloads.iam.gserviceaccount.com`):** `roles/assuredworkloads.serviceAgent`.

## Workflow 1: Create an Assured Workloads workload (Two-Phase Provisioning)

### Phase 1: Validate Parameters & Create Workload (`gcloud assured workloads create`)

1. **Select Regime & Location:** Check [references/regimes.md](references/regimes.md) for all 45 V1 `--compliance-regime` enums and valid `--location` values.
   * **Free-Tier Regional Data Boundaries (`REGIONAL_DATA_BOUNDARY`):** Free-tier regional data boundaries (e.g., *US Data Boundary* with standard commercial support and without sovereign personnel support uplift, *EU Data Boundary*, *Australia/India/UK/Canada/Israel Data Boundary*) map to `--compliance-regime=REGIONAL_DATA_BOUNDARY` (legacy alias: `REGIONAL_CONTROLS`) paired with `--location={location}` (except Japan, which uses `JAPAN_DATA_BOUNDARY`). Do **not** set `--compliance-regime` to paid sovereign support regimes (`US_REGIONS_AND_US_SUPPORT`, `US_DATA_BOUNDARY_AND_SUPPORT`, `FEDRAMP_MODERATE`) when the user requests the free-tier boundary, and never invent non-existent enums like `US_DATA_BOUNDARY`.
2. **Billing Account Discovery (If Omitted):** Never guess a billing account ID. If omitted, run `gcloud billing accounts list --filter="open=true" --format="table(name,displayName)"` or ask the user for `billingAccounts/{billing_id}`.
3. **Validate & Create:** Validate with `python3 scripts/validate_params.py --operation=create ...`, surface any warnings, obtain explicit user confirmation, and execute `gcloud assured workloads create`:
   ```bash
   gcloud assured workloads create \
     --organization={org_id} --location={location} \
     --display-name="{display_name}" --compliance-regime={compliance_regime} \
     --billing-account=billingAccounts/{billing_id} \
     [--provisioned-resources-parent=folders/{parent_folder_id}] [--enable-sovereign-controls] \
     [--next-rotation-time={next_rotation_time} --rotation-period={rotation_seconds}s] \
     [--resource-settings=consumer-project-id={consumer_project_id},consumer-project-name={consumer_project_name},encryption-keys-project-id={kms_project_id},encryption-keys-project-name={kms_project_name},keyring-id={keyring_id}] \
     [--partner={partner_enum}] [--partner-permissions=data-logs-viewer=true|false] \
     [--partner-services-billing-account=billingAccounts/{partner_billing_id}] \
     [--labels=key1=val1,key2=val2] [--external-identifier={external_id}] --format=json
   ```
   * **CMEK & Resource Settings Rules:** `--next-rotation-time` (RFC 3339 timestamp) and `--rotation-period` (seconds, e.g. `172800s`) must be specified together. `encryption-keys-project-id`, `encryption-keys-project-name`, and `keyring-id` in `--resource-settings` require both rotation flags.
   * **Sovereign Controls by Partners (`--compliance-regime=ASSURED_WORKLOADS_FOR_PARTNERS`):**
     * Requests for partner-managed sovereign controls (S3NS, T-Systems, SIA Minsait, PSN, CNTXT, Telefónica) map to `--compliance-regime=ASSURED_WORKLOADS_FOR_PARTNERS`.
     * Requires `--partner` and a supported partner region (see [references/regimes.md](references/regimes.md) for valid `--partner` values, supported regions, and partner billing account requirements).
     * Configure partner permissions on the CLI with `--partner-permissions=data-logs-viewer=true` (or `data-logs-viewer=false`).

### Phase 2 (Optional): Allowlist Compliant Services / Enable BigQuery (`google-cloud-assured-workloads`)

* **When Required:** For `FEDRAMP_MODERATE` and `DATA_BOUNDARY_FOR_FEDRAMP_MODERATE`, BigQuery is automatically enabled at creation (skip Phase 2). For all other regimes (such as `FEDRAMP_HIGH`), BigQuery is initially blocked by the folder's `constraints/gcp.restrictServiceUsage` organization policy while a background configuration process completes (typically 5–10 minutes after creation).
* **Never Bypass Org Policies Manually:** Do **not** manually override or delete `constraints/gcp.restrictServiceUsage` on the folder to bypass Assured Workloads compliance controls.
* **Programmatic Allowlisting (`AssuredWorkloadsServiceClient.restrict_allowed_resources`):** Once background setup completes and compliant services (like BigQuery) appear in `compliantButDisallowedServices`, run `python3 scripts/restrict_allowed_resources.py --organization={org_id} --location={location} --workload-id={workload_id} --restriction-type=ALLOW_COMPLIANT_RESOURCES` (after user confirmation), or call the official `google-cloud-assured-workloads` Python client library directly:
  ```python
  from google.api_core.client_options import ClientOptions
  from google.cloud import assuredworkloads_v1

  client = assuredworkloads_v1.AssuredWorkloadsServiceClient(
      client_options=ClientOptions(
          api_endpoint=f"{location}-assuredworkloads.googleapis.com"
      ),
      transport="rest",
  )
  request = assuredworkloads_v1.RestrictAllowedResourcesRequest(
      name=f"organizations/{org_id}/locations/{location}/workloads/{workload_id}",
      restriction_type=assuredworkloads_v1.RestrictAllowedResourcesRequest.RestrictionType.ALLOW_COMPLIANT_RESOURCES,
  )
  client.restrict_allowed_resources(request=request)
  ```
  *(Supported `RestrictionType` values: `ALLOW_COMPLIANT_RESOURCES`, `APPEND_COMPLIANT_RESOURCES`, or `ALLOW_ALL_GCP_RESOURCES`).*

## Workflow 2: List & Describe Assured Workloads workloads (`gcloud`)

Read-only `list` and `describe` operations do not require user confirmation after validating with `scripts/validate_params.py`.

1. **List Workloads (`ListWorkloads`):**
   ```bash
   gcloud assured workloads list --organization={org_id} --location={location} \
     [--filter="{filter_expression}"] [--limit={limit}] [--page-size={page_size}] --format=json
   ```
2. **Describe a Specific Workload (`GetWorkload`):**
   ```bash
   gcloud assured workloads describe {workload_id} --organization={org_id} --location={location} --format=json
   ```
   *(Or pass the full resource name `organizations/{org_id}/locations/{location}/workloads/{workload_id}`).*
   * **Key `describe` Output Fields:** `name`, `displayName`, `complianceRegime`, `partner`, `resources` (provisioned `CONSUMER_FOLDER` folder ID, `CONSUMER_PROJECT`, `ENCRYPTION_KEYS_PROJECT`, and `KEYRING`), `etag` (optimistic concurrency token required for `update`/`delete`), `compliantButDisallowedServices`, `kajEnrollmentState`, `saaEnrollmentResponse`, `violationNotificationsEnabled`, and `labels`.

## Workflow 3: Delete an Assured Workloads workload (`DeleteWorkload`)

An Assured Workloads workload **cannot** be deleted while its provisioned Cloud Resource Manager folder (`folders/{folder_id}`) or child projects still exist (`FAILED_PRECONDITION: Workload is not empty` / `ERROR_CODE_WORKLOAD_NOT_EMPTY`). Never run `gcloud assured workloads delete` before deleting the provisioned folder and its child projects.

1. **Inspect & Validate:** Run `gcloud assured workloads describe` to identify the provisioned folder (`folders/{folder_id}`) and child projects (`{project_id}`), and validate with `python3 scripts/validate_params.py --operation=delete --workload-id={workload_id} --organization={org_id} --location={location}`.
2. **Confirm & Execute Ordered Deletion Sequence:** Obtain explicit user confirmation, then run in strict bottom-up order:
   ```bash
   # Step 1: Delete child projects inside the workload folder first
   gcloud projects delete {project_id} --quiet

   # Step 2: Delete the provisioned Assured Workloads folder
   gcloud resource-manager folders delete {folder_id}

   # Step 3: Delete the Assured Workloads workload after folder deletion propagates
   gcloud assured workloads delete {workload_id} --organization={org_id} --location={location} --quiet
   ```
   * **Propagation Delay & `--etag` Note:** Folder deletion state (`DELETE_REQUESTED`) can take a brief propagation delay (15–60s) before Assured Workloads recognizes the folder as deleted. If `ERROR_CODE_WORKLOAD_NOT_EMPTY` transiently persists after deleting the folder, wait 15–20 seconds and retry `gcloud assured workloads delete` **without** a stale `--etag` (as deleting underlying resources changes the workload's concurrency token).

## Workflow 4: Update an Assured Workloads workload (`UpdateWorkload` & Compliance Updates)

### 4A. Update Workload Metadata & Notifications (`gcloud assured workloads update`)

* **Updatable Fields (at least one required):**
  * `--display-name="{new_display_name}"`: 4–30 characters (`[a-zA-Z0-9 -]`, no trailing spaces).
  * `--labels=key1=val1,key2=val2`: Replaces the workload's label map (include existing labels to preserve them).
  * `--violation-notifications-enabled=true|false`: Enables or disables email notifications for organization policy compliance violations to Essential Contacts (Legal category).
  * `--etag={etag}`: Current concurrency token from `describe`/`list`.
* **Immutable Fields (Cannot Be Modified After Creation):** `complianceRegime`, `location`, `billingAccount`, and `partner` are immutable. `gcloud assured workloads update` **cannot** change a workload's `complianceRegime` or `location` in-place; changing regimes requires creating a new Assured Workloads workload.
* **Validate, Confirm, & Execute:** Validate with `python3 scripts/validate_params.py --operation=update ...`, obtain explicit user confirmation, and run:
  ```bash
  gcloud assured workloads update {workload_id} --organization={org_id} --location={location} \
    [--display-name="{new_display_name}"] [--labels=key1=val1,key2=val2] \
    [--violation-notifications-enabled=true|false] [--etag={etag}] --format=json
  ```

### 4B. List & Apply Compliance Posture Updates (`updates.list` & `updates.apply`)

`gcloud assured workloads` does **not** have a built-in CLI subcommand to list or apply compliance posture updates from the `updates` sub-resource (`gcloud assured workloads update` only updates workload metadata). Use `scripts/manage_workload_updates.py` (`--action=list` or `--action=apply` after user confirmation) or `googleapiclient.discovery.build` against the regional Assured Workloads v1 API (`https://{location}-assuredworkloads.googleapis.com`):

* **`AVAILABLE` vs. `WITHDRAWN` Update States:**
  * **`AVAILABLE` (One Update Per Constraint):** Each `AVAILABLE` update record corresponds to an individual organization policy constraint update (`details.orgPolicyUpdate.suggestedPolicy.constraint`). If multiple updates are `AVAILABLE`, each corresponds to a different constraint and must be applied individually (or sequentially via `--update-id=ALL`)—applying the newest update does **not** apply older `AVAILABLE` updates for other constraints.
  * **`WITHDRAWN` (Superseded):** When a newer policy update supersedes an older unapplied update for the same constraint, Assured Workloads marks the older update `WITHDRAWN`. Filter for state `AVAILABLE` and never apply `WITHDRAWN` updates.
* **Python Discovery API Pattern (`updates.list`, `updates.apply`, & LRO Polling):**
  ```python
  import time
  from google.api_core.client_options import ClientOptions
  from googleapiclient import discovery

  service = discovery.build(
      "assuredworkloads",
      "v1",
      client_options=ClientOptions(
          api_endpoint=f"https://{location}-assuredworkloads.googleapis.com"
      ),
  )
  parent = f"organizations/{org_id}/locations/{location}/workloads/{workload_id}"

  # 1. List updates and filter for AVAILABLE state
  resp = (
      service.organizations()
      .locations()
      .workloads()
      .updates()
      .list(parent=parent)
      .execute()
  )
  available = [u for u in resp.get("updates", []) if u.get("state") == "AVAILABLE"]

  # 2. Apply each AVAILABLE update and poll the returned Long-Running Operation (LRO)
  for update in available:
    op = (
        service.organizations()
        .locations()
        .workloads()
        .updates()
        .apply(name=update["name"], body={})
        .execute()
    )
    while not op.get("done", False):
      time.sleep(3)
      op = (
          service.organizations()
          .locations()
          .operations()
          .get(name=op["name"])
          .execute()
      )
  ```

## Common Error Handling & Troubleshooting (`scripts/diagnose_error.py`)

Never blindly retry deterministic `400 INVALID_ARGUMENT`, `403 PERMISSION_DENIED`, `404 NOT_FOUND`, or `FAILED_PRECONDITION` errors. Run `python3 scripts/diagnose_error.py --error-message="{error_output_text}"` to match any error against the full Assured Workloads `ErrorInfo.reason` catalog.

### Troubleshooting `Folder creation was unsuccessful. Please try again.` (LRO Inspection)

When `gcloud assured workloads create` fails with the generic message `Folder creation was unsuccessful. Please try again.`, do **not** blindly retry. Inspect the failed Long-Running Operation (LRO) in the same organization and location to retrieve the specific `ErrorInfo.reason`:
```bash
gcloud assured operations list --organization={org_id} --location={location} --format=json
gcloud assured operations describe {operation_id} --organization={org_id} --location={location} --format=json
```
*(Or run `python3 scripts/diagnose_error.py --fetch-latest-lro --organization={org_id} --location={location}`).*

**Common Folder Creation Preconditions to Check in the LRO Error:**
* **Duplicate sibling folder display name (`ERROR_CODE_FOLDER_NAME_UNIQUENESS`):** A sibling folder with the same `--display-name` already exists under the target parent (`organizations/{org_id}` or `folders/{parent_folder_id}`). Choose a unique `--display-name` or a different `--provisioned-resources-parent`.
* **Nesting inside an existing Assured Workloads folder (`ERROR_CODE_INVALID_PROVISIONED_RESOURCES_PARENT`):** Assured Workloads folders cannot be nested inside another Assured Workloads folder. Specify a standard non-workload parent folder or omit `--provisioned-resources-parent`.
* **Folder quota or nesting depth limit (`ERROR_CODE_FOLDER_CREATION_PRECONDITION_FAILED`):** The target parent reached the Cloud Resource Manager 300 direct child-folder quota or the 10-level folder nesting depth limit.

## Reference Documentation

* **[references/regimes.md](references/regimes.md):** Complete table of all 45 Assured Workloads V1 compliance regimes, modern `DATA_BOUNDARY_FOR_*` enums, legacy aliases, partner enums, and supported regional/multi-regional locations.
* **Official Google Cloud Documentation:** [Assured Workloads Overview](https://docs.cloud.google.com/assured-workloads/docs/overview.md.txt), [Supported Locations & Data Boundaries](https://docs.cloud.google.com/assured-workloads/docs/locations.md.txt), [Assured Workloads Pricing](https://cloud.google.com/assured-workloads/pricing), [Apply Workload Updates](https://docs.cloud.google.com/assured-workloads/docs/apply-updates.md.txt), [Sovereign Controls by Partners Overview](https://cloud.google.com/sovereign-controls-by-partners/docs/overview), [Sovereign Controls by Partners Locations](https://cloud.google.com/sovereign-controls-by-partners/docs/locations).
