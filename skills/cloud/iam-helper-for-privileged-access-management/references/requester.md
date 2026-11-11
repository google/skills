# Mode 1: Interactive Access Elevation (Requester Workflow)

Follow these steps when the user requests temporary access elevation.

*(Rule: Throughout this playbook, select the resource scope flag corresponding
to where the target entitlement is defined: pass `--project=PROJECT_ID`,
`--folder=FOLDER_ID`, or `--organization=ORGANIZATION_ID`).*

## Table of Contents

*   [Prerequisites & Permissions](#prerequisites)
*   [Step 1: Collect & Validate Core Inputs](#step-1)
*   [Step 2: Search Existing PAM Entitlements Along the Hierarchy](#step-2)
*   [Step 3: Request Grant](#step-3)
*   [Step 4: Handle Status & Termination](#step-4)

### Prerequisites & Permissions {#prerequisites}

*   **Requester Eligibility:** To become a requester, the user simply must be
    added to the `eligibleUsers` list in the entitlement. No explicit IAM roles
    are required.
*   **Discover Eligible Entitlements:** Requesters can discover their eligible
    entitlements using `gcloud pam entitlements search --caller-access-type=grant-requester` without needing the
    `roles/privilegedaccessmanager.viewer` role.
*   **Broad Search & Role Inspection:** Searching all entitlements across scopes
    (`list`/`describe`) requires `roles/privilegedaccessmanager.viewer`, and
    inspecting role definitions (`gcloud iam roles describe`) requires
    `roles/iam.roleViewer`.

### Step 1: Collect & Validate Core Inputs {#step-1}

Validate or ask the user for these four parameters:

*   **Principal Email:** The Identity requesting access (e.g.,
    `user:user@example.com`).
*   **Permission Name:** The required IAM permission (e.g.,
    `compute.instances.start`).
*   **Requested Duration:** Default to `3600s` (60 mins) if unspecified.
*   **Target Resource:** Accept short names (like `my-project`) from the user and
    format them as fully qualified URIs internally (e.g.,
    `//cloudresourcemanager.googleapis.com/projects/my-project`).

### Step 2: Search Existing PAM Entitlements Along the Hierarchy {#step-2}

Check for active entitlements satisfying the request across the target resource and its ancestor hierarchy (Project, ancestor Folders, and Organization).

> [!IMPORTANT]
> A single `gcloud pam entitlements search` command only queries the exact scope specified and does **not** automatically traverse parent folders or organizations. Because entitlements granting access to a project can be defined at ancestor folder or organization levels, use the helper script to search across the entire hierarchy.

Run the hierarchy search script:

```bash
bash scripts/search_eligible_entitlements.sh --project=PROJECT_ID
```
*(Or pass `--folder=FOLDER_ID` or `--organization=ORGANIZATION_ID` based on the target resource scope).*

#### Fallback (Direct Bash Command)

If executing without local script access, search across the project and its ancestor hierarchy using:

```bash
project="PROJECT_ID"
echo "=== Searching Project Scope ==="
gcloud pam entitlements search --caller-access-type=grant-requester \
  --location=global --project="$project" --format=json

echo "=== Searching Ancestor Folders & Organization ==="
while read -r id type; do
  if [[ "$type" == "folder" ]]; then
    gcloud pam entitlements search --caller-access-type=grant-requester \
      --location=global --folder="$id" --format=json
  elif [[ "$type" == "organization" ]]; then
    gcloud pam entitlements search --caller-access-type=grant-requester \
      --location=global --organization="$id" --format=json
  fi
done < <(gcloud projects get-ancestors "$project" --format="value(id,type)" 2>/dev/null || true)
```

Extract the `roleBindings` from the search results to verify if any returned entitlement grants the needed permission or role.

*   **Match Found:** If an entitlement grants the required permission, store its `ENTITLEMENT_ID` and the scope level where it was found (Project, Folder, or Organization). **Rule:** If multiple eligible entitlements are found across the hierarchy, prefer the least scoped entitlement (e.g., prefer Project over Folder, and Folder over Organization). Proceed to Step 3.
*   **No Match:** Abort and inform the user that no eligible entitlement exists for their request.

--------------------------------------------------------------------------------

### Step 3: Request Grant {#step-3}

Request a temporary grant using `gcloud pam grants create`:

Ensure the `--requested-duration` flag matches the exact timeframe specified by
the user (e.g., if the user requests elevation for `2 hours`, pass exactly
`--requested-duration=7200s`). If the user omitted specifying a custom
timeframe, use the `60 mins` (`3600s`) default.

Pass the scope flag matching where the entitlement is defined (`--project`,
`--folder`, or `--organization`):

```bash
# Example using a project-level entitlement:
gcloud pam grants create \
    --entitlement=ENTITLEMENT_ID \
    --location=global \
    --requested-duration=DURATION \
    --justification="Automated temporary access request" \
    --project=PROJECT_ID
```

*(Note: The scope flag `--project`, `--folder`, or `--organization` must match
where the entitlement is defined. To narrow an organization- or folder-level
entitlement to a child resource via `--requested-resources=projects/PROJECT_ID`,
use `gcloud beta pam grants create`, as `--requested-resources` is only
available
in the `beta` track).*

### Step 4: Handle Status & Termination {#step-4}

Verify state in response:

*   **`APPROVAL_AWAITED`:** Notify: "The grant request (`GRANT_ID`) is raised.
    Access will be active after approval." Terminate immediately.
*   **`SCHEDULED` or `ACTIVATING`:** The grant is approved but provisioning is pending. Wait ~30 seconds and retry checking the state 2-3 times.
*   **`ACTIVE`:** Confirm activation and proceed. Do not revoke the grant upon
    completing tasks; allow automatic expiration.
