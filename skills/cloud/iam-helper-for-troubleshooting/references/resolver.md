# Administrator & Security Resolver Flow

This guide details how privileged administrators and security agents intake
access requests, resolve blocking deny policies, and provision least-privileged
access.

### Prerequisites & Required Roles

To successfully troubleshoot and remediate access, the caller must possess the
following roles:

*   **Troubleshooting:** `roles/policyintelligence.policyTroubleshooterViewer`
    (or `roles/iam.securityReviewer`), `roles/iam.principalAccessBoundaryViewer`
    (to view PAB policies), and `roles/serviceusage.serviceUsageConsumer` (to
    run gcloud commands).
*   **Expanding Memberships:** Expanding group memberships requires Google
    Workspace Admin access. Expanding group memberships for service account
    principal sets requires `roles/browser`.
*   **Remediation:** `roles/resourcemanager.projectIamAdmin` (for local
    bindings) or `roles/iam.denyAdmin` (for deny policies).
*   *Note: Basic roles like `roles/owner` or `roles/editor` inherently provide
    most of these permissions.*

--------------------------------------------------------------------------------

## Step 1: Intake & Authoritative Diagnosis

1.  Retrieve the `ERROR_ID` (for example, an alphanumeric base64-encoded string
    like `ZGVuaWVkX2J5X2RlbmlhbF9wb2xpY3k...`) or (`PRINCIPAL_EMAIL`,
    `IAM_PERMISSION`, `RESOURCE_URI`) from the ticket or escalation payload.
2.  Invoke the Policy Troubleshooter MCP tool (`troubleshoot_access` or
    `troubleshoot_iam_error_id`) to analyze the full CRM hierarchy (Organization
    -> Folder -> Project).

    *   **Fallback:** If MCP tools are unavailable, use the fallback scripts or
        `gcloud` CLI:

        *   For Error IDs: `ERROR_ID="YOUR_ERROR_ID" python3
            scripts/troubleshooting_error_id.py`
        *   For manual checks: Always use `gcloud policy-troubleshoot iam` with
            `--format=json` and pass `--billing-project` (extracting
            `PROJECT_ID` from `RESOURCE_URI` if present):

        ```bash
        gcloud policy-troubleshoot iam //RESOURCE_URI \
            --principal-email="PRINCIPAL_EMAIL" \
            --permission="IAM_PERMISSION" \
            --billing-project="PROJECT_ID" \
            --format=json
        ```
3.  Evaluate the results:

    *   **CASE A (`accessState: GRANTED` or Inherited Org/Folder Allow
        Policy):** Access is correctly configured and already granted (including
        via inherited organization or folder allow policies, or
        domain-wide/group bindings). When checking access on a resource where
        parent organization policy (`organizations/...` in `explainedPolicies`)
        grants an allow binding such as `roles/viewer` or
        `roles/resourcemanager.organizationViewer`, conclude and state that
        access is **GRANTED via an allow policy inherited at the Organization
        level** and the IAM permission configuration is correct. **Terminate the
        flow immediately.** Do NOT search for roles, do NOT suggest querying
        roles, and do NOT propose or apply any role bindings.
    *   **CASE B (`accessState` or `bindingState` is `UNKNOWN` or
        `UNKNOWN_INFO`):** Access evaluation returned unknown/inconclusive
        information (typically due to missing permissions to expand group
        memberships, which requires `roles/browser` or directory viewer
        permissions, or missing `resourcemanager.projects.getIamPolicy` on
        ancestors). Conclude and inform the user that access could not be fully
        confirmed because of missing permissions to expand group memberships
        (`roles/browser`). **Terminate the troubleshooting flow immediately.**
        Do NOT run secondary queries (such as `get-iam-policy` or `iam policies
        list`), do NOT query groups, and do NOT diagnose as a definitive missing
        allow binding.
    *   **CASE C (`accessState: NOT_GRANTED`):** Access is absent or blocked:
        *   If `denyPolicyExplanation` shows access is blocked by an explicit
            IAM deny policy, explain that an explicit IAM deny policy blocks
            access, advise contacting the Security/Organization Administrator,
            and proceed to Step 2.
        *   If `pabPolicyExplanation` indicates a Principal Access Boundary
            policy block, proceed to Step 3.
        *   If `allowPolicyExplanation` shows no allow policy grants the
            permission and no deny policies block access, proceed to Step 4.
    *   **Caller Permission Denied / Anti-Loop Rule:** If invoking the Policy
        Troubleshooter tool/API or `gcloud policy-troubleshoot` returns
        `PERMISSION_DENIED` (HTTP 403 / insufficient caller permissions to
        troubleshoot the resource), the caller lacks the necessary diagnostic
        permissions (`roles/policyintelligence.policyTroubleshooterViewer` or
        `roles/iam.securityReviewer`). Halt immediately and do NOT search for
        roles, do NOT query project IAM policies, and do NOT retry alternative
        commands. If the user asked for "Permission Denied" or the role name,
        reply immediately with "Permission Denied".

--------------------------------------------------------------------------------

## Step 2: Remediate Blocking Deny Policies

If one or more IAM v2 deny policies block access, then do the following:

1.  For each blocking policy (`POLICY_ID`), present the admin with the following
    options to avoid dangerous permission escalations (Require a HITL prompt
    before execution):

    *   **Option A: Add the principal to `exceptionPrincipals` (exempt
        principal).**

        *   Update the deny rule definition file to add
            `principal://goog/subject/PRINCIPAL_EMAIL` under
            `denyRule.exceptionPrincipals`, then run the following command:

        ```bash
        gcloud iam policies update POLICY_ID \
            --attachment-point=ATTACHMENT_POINT \
            --kind=denypolicies \
            --policy-file=policy.json
        ```
    *   **Option B: Remove the permission from the deny rule.**

        *   Update the deny rule definition file to remove `IAM_PERMISSION` from
            `denyRule.deniedPermissions` (or add it under
            `denyRule.exceptionPermissions`), then run the following command:

        ```bash
        gcloud iam policies update POLICY_ID \
            --attachment-point=ATTACHMENT_POINT \
            --kind=denypolicies \
            --policy-file=policy.json
        ```
    *   **Option C: Exclude the resource from the deny policy scope.**

        *   Update the deny rule condition in the policy file (for example,
            adding `!resource.matchTag(...)` or narrowing the rule scope so the
            target `RESOURCE_URI` is excluded), then run the following command:

        ```bash
        gcloud iam policies update POLICY_ID \
            --attachment-point=ATTACHMENT_POINT \
            --kind=denypolicies \
            --policy-file=policy.json
        ```
2.  If human approval is granted for the chosen option, apply the policy update.
3.  Wait 60 seconds for policy changes to propagate.
4.  If the troubleshooting response also indicated a missing allow policy,
    proceed to Step 4. Otherwise, proceed to Step 6.

--------------------------------------------------------------------------------

## Step 3: Remediate Blocking Principal Access Boundary (PAB) Policies

If `pabPolicyExplanation` indicates access is blocked by a Principal Access
Boundary policy, then do the following:

1.  Present the admin with remediation options (Require HITL approval before
    execution):

    *   **Option A: Update the PAB Policy Resources.** Add the target resource
        or its parent folder/project to the list of allowed resources defined in
        the PAB policy:

        ```bash
        gcloud iam principal-access-boundary-policies update PAB_POLICY_ID \
            --location=global \
            --organization=ORGANIZATION_ID \
            --add-details-rules=description="Allow target resource",effect=ALLOW,resources=//cloudresourcemanager.googleapis.com/projects/PROJECT_ID
        ```
    *   **Option B: Modify Principal Sets.** Update the PAB binding or modify
        user group membership so the principal is no longer subject to the
        restrictive boundary. For example, to remove a restrictive PAB binding,
        run the following command:

        ```bash
        gcloud iam policy-bindings delete BINDING_ID \
            --location=global \
            --organization=ORGANIZATION_ID
        ```

        For more specific steps on modifying bindings, refer to the
        [Principal Access Boundary documentation](https://cloud.google.com/iam/docs/principal-access-boundary-policies-create).
2.  Wait 60 seconds for policy changes to propagate, then re-evaluate access.

--------------------------------------------------------------------------------

## Step 4: Discover Least-Privileged Role

If access is missing due to an absent allow policy, then do the following:

1.  First, explain the diagnostic findings: confirm that no allow policy grants
    `IAM_PERMISSION` and there are no blocking deny policies.
2.  **Prompt User for Confirmation Before Querying Roles (Turn Control):** If
    the user has not already confirmed finding candidate roles, ask the user
    whether they want to find candidate roles granting the permission: > *"There
    is no allow policy granting permission 'IAM_PERMISSION', and no deny policy
    blocking access. Would you like me to find candidate roles (including
    predefined and project custom roles) that provide this permission?
    (Yes/No)"*
3.  **Execute Role Query (After Receiving User Confirmation):** Run the automated
    least-privileged role finder script (preferred, as it evaluates both predefined
    and project custom roles and returns a single optimal role, avoiding long lists):

    ```bash
    IAM_PERMISSION="YOUR_IAM_PERMISSION" \
    TARGET_PROJECT_ID="YOUR_PROJECT_ID" \
    python3 scripts/least_privileged_role.py
    ```

    *Fallback (Manual CLI queries):* If the script cannot be executed, search for matching predefined and project custom roles using `gcloud iam roles list`:

    ```bash
    # Predefined roles matching permission:
    gcloud iam roles list --filter="includedPermissions:IAM_PERMISSION" --format="table(name,title)"

    # Project custom roles matching permission:
    gcloud iam roles list --project=TARGET_PROJECT_ID --filter="includedPermissions:IAM_PERMISSION" --format="table(name,title)"
    ```

    Select the role returned with the least privilege (`ROLE_NAME`). Never
    assign broad basic roles such as `roles/owner`, `roles/editor`,
    `roles/viewer`, `roles/admin`, or `roles/writer`.
4.  Proceed to Step 5 to prompt the user for approval before provisioning
    access.

--------------------------------------------------------------------------------

## Step 5: Provision Access (Subject to Guardrails)

When prompting the human for HITL approval, explicitly state the target resource
(e.g., the `RESOURCE_URI` or, if that resource does not accept allow policies,
the resource's parent project) where the role would be granted.

If creating a new role grant, evaluate `ROLE_NAME` against the approval tiers
defined in the organization's customized guardrails:

*   **Standard Roles (HITL Protocol):** If `ROLE_NAME` is a standard role
    granting read/view or write/mutating permissions (for example,
    `roles/*.viewer`, `roles/*.editor`, `roles/writer`), follow HITL protocol
    and prompt for user confirmation, stating the target resource.
*   **Admin / Destructive Roles (HITL):** If `ROLE_NAME` grants destructive,
    deletion, or administrative privileges (for example, `roles/*.admin`,
    `roles/owner`, `roles/resourcemanager.*Admin`, `roles/iam.*`), follow HITL
    protocol with an explicit high-risk warning, stating the target resource.

Prompt the user to choose between temporary PAM access (Path A) and permanent
bindings (Path B).

### Provisioning Paths:

#### Path A: Privileged Access Manager (PAM Entitlement - Preferred)

Ask the user if PAM is enabled, or check for existing PAM entitlements using
`gcloud pam entitlements list`. If the organization uses PAM for time-bound,
audited access, delegate the provisioning to
`@skill:iam-helper-for-privileged-access-management`:

1.  **If an entitlement already exists** for `ROLE_NAME` covering
    `PRINCIPAL_EMAIL`: Delegate to
    `@skill:iam-helper-for-privileged-access-management` to request a grant
    against the existing entitlement.
2.  **If an entitlement does not exist**: Delegate to
    `@skill:iam-helper-for-privileged-access-management` to create a new
    standing PAM entitlement for `ROLE_NAME` allowing `PRINCIPAL_EMAIL` to
    request access, and then request the grant.

#### Path B: Permanent IAM Role Binding (Direct Grant)

If permanent standing access is approved, then run one of the following commands, based on the resource that they need access on:

*   **For Projects:**

    ```bash
    gcloud projects add-iam-policy-binding PROJECT_ID \
        --member="user:PRINCIPAL_EMAIL" \
        --role="ROLE_NAME"
    ```
*   **For Folders:**

    ```bash
    gcloud resource-manager folders add-iam-policy-binding FOLDER_ID \
        --member="user:PRINCIPAL_EMAIL" \
        --role="ROLE_NAME"
    ```
*   **For Organizations:**

    ```bash
    gcloud organizations add-iam-policy-binding ORGANIZATION_ID \
        --member="user:PRINCIPAL_EMAIL" \
        --role="ROLE_NAME"
    ```

--------------------------------------------------------------------------------

## Step 6: Verification & Handoff

1.  Verify that the binding or PAM grant is active by re-running the policy
    troubleshooter check.
2.  Provide a structured resolution summary:
    *   **Root Cause:** Deny policy / PAB policy / Missing allow policy.
    *   **Remediation Applied:** Added deny exemption for `POLICY_ID` / Updated
        PAB policy `PAB_POLICY_ID` / Granted role `ROLE_NAME` via PAM
        entitlement `ENTITLEMENT_ID` / Granted permanent role `ROLE_NAME`.
    *   **Target Principal:** `PRINCIPAL_EMAIL`
3.  **Notify Developer / Transfer Back:**
    *   Inform the requester that the permission barrier is resolved.
    *   Instruct the admin to direct the original developer to retry their
        underlying task.
