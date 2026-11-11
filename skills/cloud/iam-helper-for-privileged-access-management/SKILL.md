---
name: iam-helper-for-privileged-access-management
metadata:
  version: "1.0.2"
  category: Security
description: >-
  Manages the end-to-end lifecycle of on-demand, temporary access using
  Privileged Access Manager (PAM). Use when a user asks to create, read,
  update, or delete PAM entitlements, request temporary access, or
  approve/deny pending PAM grants. Do NOT use for permanent IAM policy
  bindings, troubleshooting IAM permission errors, or general Google Cloud
  resource provisioning.
---

# Privileged Access Manager (PAM)

This skill provides step-by-step guidance for planning, validating, and
executing Privileged Access Manager (PAM) entitlement CRUD operations, approval
workflow configurations, access elevations, and grant approval/denial workflows.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Table of Contents

*   [Core Concepts](#core-concepts)
*   [Approval Workflows & Max Request Duration](#approval-workflows)
*   [Safety & Confirmation Strategy](#safety-confirmation)
*   [Plan-Validate-Execute Pattern](#plan-validate-execute)
*   [Mode 1: Interactive Access Elevation](#mode-1)
*   [Mode 2: Standalone Entitlement CRUD](#mode-2)
*   [Mode 3: Approver Workflow](#mode-3)
*   [Supporting Links & Resources](#supporting-links)

## Core Concepts {#core-concepts}

Privileged Access Manager (PAM) replaces permanent or ambient IAM role
assignments with on-demand, time-bound, and audited access elevations. Rather than
appending permanent IAM policy bindings, PAM uses:

*   **Entitlements:** Configurations defining access scopes, eligible
    requesters, and approvers.
*   **Grants:** Short-lived requests created against entitlements to activate
    the entitlement's IAM roles.

### Privileged Access (`privilegedAccess`)

The `privilegedAccess` block in an entitlement defines the precise access scope that will be granted. An access scope comprises three essential components:
*   **Resource:** The target Google Cloud resource (Project, Folder, or Organization) where access is granted.
*   **Role Setup:** The IAM role (`roleBindings.role`) to be assigned.
*   **Condition:** (Optional) An IAM condition expression (`roleBindings.conditionExpression`) restricting when or where the role applies.

### Core Workflow

1.  Administrators create Entitlements.
2.  Requesters can then request Grants against these entitlements.
3.  If the entitlement is configured with approvals, then an approver must
    approve the requested grant.
4.  Once all necessary approval steps are completed, the grant is activated for
    the requested time.
5.  The grant automatically ends after the requested duration has elapsed, and
    the elevated access is removed.

## Approval Workflows & Max Request Duration {#approval-workflows}

### Approval Workflows (`approvalWorkflow`)

When sensitive environments require human approval before temporary access is
activated, configure the `approvalWorkflow` block in the entitlement YAML
manifest (`entitlement.yaml`).

```yaml
approvalWorkflow:
  manualApprovals:
    # Optional: requires approver to supply a justification string
    requireApproverJustification: true
    steps:
    - approvalsNeeded: 1
      approverEmailRecipients:
      - approver@example.com
      approvers:
      - principals:
        - user:db-lead@my-company.com  # or group:sre-leads@my-company.com
```

*   **When to include:** Include `approvalWorkflow` whenever the user prompt
    specifies that manual approval or an approver (user or group) is required.
*   **Outcome:** When a user requests a grant against an entitlement
    with `approvalWorkflow`, the grant transitions to `APPROVAL_AWAITED`.
    Requesters must await an Approver's decision (`Mode 3`).

### Max Request Duration (`maxRequestDuration`)

`maxRequestDuration` defines the maximum single access elevation timeframe a requester
may ask for when placing a grant request.

*   **Flexible Configuration:** Configure `maxRequestDuration` according to the
    user's specific request (e.g. `8 hours` / `28800s`, `1 hour` / `3600s`, `24
    hours` / `86400s`).
*   **Default Value:** If the user does NOT specify a maximum request duration,
    default to `4 hours` (`14400s`).
*   **YAML Syntax:** Always format `maxRequestDuration` as a string in seconds
    in the entitlement YAML (e.g., `"14400s"`, `"28800s"`).

## Safety & Confirmation Strategy {#safety-confirmation}

Adhere strictly to these workflow guards:

*   **Modifying / Destructive Executions (Create, Update, Delete, Approve, Deny, Revoke):** Always
    present a plain-text summary of the planned adjustments and prompt the user
    for explicit confirmation (Yes/No).
*   **Read-Only Inspections (List, Describe, Search):** Run autonomously without
    requesting confirmation.
*   **Batching Bash Commands (Reduce User Confirmations):** The host environment
    requires user approval for every individual shell tool call. To minimize
    confirmation popups, combine sequential read-only and lookup commands into a
    single compound bash script within one tool call (e.g., combining project,
    folder, and organization hierarchy audits into a single multiline
    execution).
*   **Anti-Loop Strategy:** If a command fails with a clear, actionable error,
    you may attempt to self-debug and retry. If the error is ambiguous, halt
    immediately, present the stderr output, and await user direction.

## Plan-Validate-Execute Pattern {#plan-validate-execute}

For all modifying actions (Mode 1 Step 3, Mode 2 Create, Update, Delete, Mode 3 Approve, Deny):

1.  **Plan:** Construct the proposed parameters or read the sample entitlement
    structure. (For entitlement creation, load and use the template:
    [assets/entitlement_template.yaml](assets/entitlement_template.yaml)).
2.  **Validate:** Inspect the target configuration parameters (resource names,
    role bindings, duration limits) for compliance with corporate rules.
3.  **Execute:** Present the validated plan, obtain explicit user confirmation,
    and run the `gcloud` command.

--------------------------------------------------------------------------------

## Mode 1: Interactive Access Elevation {#mode-1}

When the user requests temporary access elevation as a Requester, load and
follow the detailed instructions in
[`references/requester.md`](references/requester.md).

--------------------------------------------------------------------------------

## Mode 2: Standalone Entitlement CRUD {#mode-2}

Follow these steps for entitlement configurations.

### Required Permissions for Entitlement Admins

*   `roles/privilegedaccessmanager.admin`: Required to create, update, and
    delete entitlement configurations (`Mode 2 CRUD`).
*   **Scope IAM Admin Rights:** Required on the target hierarchy scope because
    creating an entitlement authorizes future role evaluations and bindings on
    that scope:
    *   **Organizations:** `roles/iam.securityAdmin`
    *   **Folders:** `roles/resourcemanager.folderAdmin`
    *   **Projects:** `roles/resourcemanager.projectIamAdmin`
*   `roles/privilegedaccessmanager.viewer`: Required to list and describe
    entitlements across scopes.

*(Rule: For all Standalone Entitlement CRUD commands below, use the flag
matching where the entitlement is defined: pass `--project=PROJECT_ID`,
`--folder=FOLDER_ID`, or `--organization=ORGANIZATION_ID`).*

### 1. Create Entitlement

1.  Check if `ENTITLEMENT_ID` exists:

```bash
gcloud pam entitlements describe ENTITLEMENT_ID \
    --location=global \
    --project=PROJECT_ID
```

*   **If Exists:** Halt. Ask: *"The requested PAM Entitlement `ENTITLEMENT_ID`
    already exists. Would you like to view its details or update it instead?
    (View / Update / Exit)"*
*   **If NOT_FOUND:** Load the template
    [assets/entitlement_template.yaml](assets/entitlement_template.yaml).
    Generate IDs in lowercase using hyphen separators derived from the role name
    (e.g., `compute-admin` for `roles/compute.admin`). **Note:**
    *   You may specify multiple IAM roles under `roleBindings`.
    *   You may also include an optional IAM `conditionExpression` for each role binding.
    *   Legacy basic roles (e.g., `roles/viewer`, `roles/editor`, `roles/owner`)
        are NOT supported. Instead, use the basic roles (`roles/reader`,
        `roles/writer`, `roles/admin`). Ensure you select a valid predefined,
        custom, or basic role.
*   Set `maxRequestDuration` based on user specification (e.g. `"28800s"` for 8
    hours, `"3600s"` for 1 hour). If unspecified by the user, default to
    `"14400s"` (4 hours). If manual approval is specified by policy or requested
    by the user, configure the `approvalWorkflow` block in `entitlement.yaml`.
    Preserve `requesterJustificationConfig: {unstructured: {}}`.
*   Prompt: *"You are about to create the PAM Entitlement `ENTITLEMENT_ID`. Do
    you approve this creation? (Yes/No)"*
*   Deploy:

```bash
gcloud pam entitlements create ENTITLEMENT_ID \
    --location=global \
    --entitlement-file=entitlement.yaml \
    --project=PROJECT_ID
```

### 2. Read Entitlements

Run these read operations autonomously:

List all entitlements at a single scope:

```bash
gcloud pam entitlements list \
    --location=global \
    --project=PROJECT_ID
```

To list all entitlements defined across the entire resource hierarchy (project, ancestor folders, and organization), use the hierarchy listing script:

```bash
bash scripts/list_entitlements_hierarchy.sh --project=PROJECT_ID
```
*(Or pass `--folder=FOLDER_ID` or `--organization=ORGANIZATION_ID`).*

Describe target entitlement:

```bash
gcloud pam entitlements describe ENTITLEMENT_ID \
    --location=global \
    --project=PROJECT_ID
```

### 3. Update Entitlement

1.  Run the `export` command to generate the current config (which includes the `etag`):

    ```bash
    gcloud pam entitlements export ENTITLEMENT_ID \
        --location=global \
        --project=PROJECT_ID > {scratch}/updated_entitlement.yaml
    ```

    If missing, offer to run `list` or exit.

2.  Edit the exported `{scratch}/updated_entitlement.yaml` file to apply the requested changes (e.g., updating
    `maxRequestDuration`, `approvalWorkflow`, or `eligibleUsers`). Do not alter the `etag`.

3.  Prompt: *"You are about to update the PAM Entitlement `ENTITLEMENT_ID`. Do
    you approve this update? (Yes/No)"*

4.  Execute:

```bash
gcloud pam entitlements update ENTITLEMENT_ID \
    --location=global \
    --entitlement-file={scratch}/updated_entitlement.yaml \
    --project=PROJECT_ID
```

### 4. Delete Entitlement

1.  Verify existence using `describe`. If missing, offer list/exit.
2.  **Safety Check:** An entitlement cannot be deleted if there are open grants.
    Before deleting, search for any `ACTIVE` or `SCHEDULED` grants:

    ```bash
    gcloud pam grants list \
        --entitlement=ENTITLEMENT_ID \
        --location=global \
        --project=PROJECT_ID \
        --filter="state:(ACTIVE, SCHEDULED)"
    ```

    If any open grants are found, prompt the user for permission to revoke them: *"There are active or scheduled grants on this entitlement. Do you authorize me to revoke them so the entitlement can be deleted? (Yes/No)"*

    If Yes, revoke them:

    ```bash
    gcloud pam grants revoke GRANT_ID \
        --entitlement=ENTITLEMENT_ID \
        --location=global \
        --project=PROJECT_ID \
        --reason="Revoking to delete entitlement"
    ```

3.  Prompt: *"You are about to permanently delete the PAM Entitlement
    `ENTITLEMENT_ID`. Do you approve this deletion? (Yes/No)"*

4.  Execute:

```bash
gcloud pam entitlements delete ENTITLEMENT_ID \
    --location=global \
    --project=PROJECT_ID
```

--------------------------------------------------------------------------------

## Mode 3: Approver Workflow {#mode-3}

When an Approver needs to review, approve, or reject pending grant requests,
load and follow the detailed instructions in
[`references/approver.md`](references/approver.md).

--------------------------------------------------------------------------------

## Supporting Links & Resources {#supporting-links}

For further information on working with Privileged Access Manager, refer to:

*   [Google Cloud Privileged Access Manager Overview][pam-overview]
*   [Setting up PAM Entitlements][pam-create]
*   [Requesting and auditing PAM Grants][pam-grants]
*   [gcloud SDK pam Reference Guide][pam-gcloud]

[pam-overview]: https://cloud.google.com/iam/docs/pam-overview
[pam-create]: https://cloud.google.com/iam/docs/pam-create-entitlements
[pam-grants]: https://cloud.google.com/iam/docs/pam-request-temporary-elevated-access
[pam-gcloud]: https://cloud.google.com/sdk/gcloud/reference/pam
