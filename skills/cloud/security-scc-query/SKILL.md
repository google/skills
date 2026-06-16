---
name: security-scc-query
description: >-
  Queries and retrieves active security findings or toxic combinations from Google Cloud Security Command Center (SCC). Use when retrieving details for a security finding by its name, validating finding scope (e.g., verifying findingClass is TOXIC_COMBINATION), or fetching finding details for triage. Don't use for drafting remediation configurations (use security-remediation-draft), analyzing service account IAM permissions (use security-iam-analyzer), or executing resource changes.
---

<!-- disableFinding(HTML_BROKEN) -->
<!-- disableFinding(LINE_OVER_80) -->

# Security Command Center (SCC) Query Skill

This skill provides guidelines and gcloud CLI command patterns for retrieving
and querying security findings and toxic combinations from Google Cloud Security
Command Center (SCC).

> [!IMPORTANT] **CRITICAL GOTCHA**: There is NO `gcloud scc findings describe`
> command. Any attempt to run it will fail with `Invalid choice: 'describe'`. To
> describe or retrieve details for a specific finding by its name, you MUST use
> `gcloud scc findings list` with a filter on `name`.

## 3-Tier Consent Gate

*   **Tier R (Read-Only)**: Listing active findings, retrieving finding details,
    and fetching attack path simulation metadata.
*   **Tier M (Mutating)**: None. This skill is strictly read-only.
*   **Tier D (Destructive)**: None.

## When to Use

*   To retrieve the detailed JSON representation of a Security Command Center
    finding using its unique finding name.
*   To list active findings or toxic combinations in a project or organization.
*   To retrieve the attack path simulation (APS) details embedded in toxic
    combination findings.

## Execution Rules & Constraints

1.  **Zero-Speculation Gating**:
    *   You **MUST NOT** speculate, guess, or use any placeholder or hardcoded
        IDs for Project, Organization, Folder, Source, or Finding. Every ID used
        MUST come directly from the user's prompt or context.
    *   If the project ID, organization ID, or folder ID is missing or not
        provided in the user's prompt or context, you **MUST** halt execution
        immediately and ask the user to provide the correct project,
        organization, or folder ID.
    *   You **MUST NOT** attempt to execute any commands, checks, or searches to
        discover the missing IDs. This includes, but is not limited to:
        *   Running configuration checks like `gcloud config list` or `gcloud
            auth list`.
        *   Running discovery or list commands like `gcloud projects list` or
            `gcloud organizations list`.
        *   Searching workspace files, environment variables, or logs.
2.  **NEVER search the workspace for finding details**:
    *   All SCC findings and toxic combinations reside strictly in the cloud.
        You **MUST NOT** attempt to search the workspace files (using `grep`,
        `grep_search`, `find`, or any python scripts) under any circumstances.
    *   If the user specifies a unique finding name in their request, and the
        `gcloud scc findings list` command filtered by that name returns an
        empty result, you **MUST** immediately stop and report to the user that
        the specified finding could not be found. You **MUST NOT** attempt to
        list all findings in the organization/project or ask the user to choose
        from other findings.
3.  **Ambiguous or Missing Finding Name**:
    *   If the user asks for details of the active finding in a
        project/organization but does not specify the unique finding name, you
        should list the active findings.
    *   If multiple findings are provided in the user's prompt or context, or if
        multiple findings are returned by the list command, you **MUST NOT**
        unilaterally pick one to describe, nor attempt to retrieve details for
        multiple findings. You **MUST** immediately halt execution and ask the
        user to specify which finding name they want details for.
    *   If the list command returns **zero findings** (empty result), you
        **MUST** immediately stop and report to the user that no active findings
        were found in the specified project/organization. You **MUST NOT**
        search the workspace or try to find it elsewhere.
4.  **Do NOT verify or describe attack path resources**:

    *   This skill is strictly for retrieving and extracting details *from the
        SCC finding payload itself*.
    *   You **MUST NOT** attempt to run any commands to describe, verify, or
        query the actual GCP resources (such as GCS buckets, service accounts,
        VMs, or IAM policies) mentioned in the finding's attack path.
    *   Resource analysis must be delegated to other skills (like
        `security-iam-analyzer`) or skipped entirely if not explicitly requested
        by the user.

5.  **Immediate Halt on Execution Errors**:

    *   If any `gcloud` command fails due to permission, authorization,
        authentication, configuration, or connectivity issues (for example,
        receiving `PERMISSION_DENIED`, `IAM_PERMISSION_DENIED`, credential
        expiration, or API endpoint connection timeouts), you **MUST** halt
        execution immediately.
    *   You **MUST NOT** attempt to troubleshoot, resolve, or search for
        credentials/configs. Specifically, do not:
        *   Search the workspace or look for local configuration/credentials
            files.
        *   Query gcloud configuration or authentication states (e.g., `gcloud
            config ...` or `gcloud auth ...`).
        *   Enter any debugging or diagnostic loops (like running `grep`,
            `find`, or custom scripts).
    *   Report the failure and the verbatim error message from the failed
        command to the user immediately.

## Execution Workflow

### Step 1: Extract and Validate Finding Name

The agent must expect a `finding_name` (e.g.
`organizations/{org_id}/sources/{source_id}/findings/{finding_id}`) to proceed.
If the `finding_name` is missing from the context, list the active findings
first (using the workflow below), and if multiple findings are returned, ask the
user to specify which one they want details for.

### Step 2: Retrieve Finding Details

Retrieve the finding details by listing findings under the organization or
source parent, filtered by the unique finding name.

*   **Command Pattern**:

    ```bash
    gcloud scc findings list {parent} \
      --filter="name=\"{finding_name}\"" \
      --location=global \
      --format="json"
    ```

    *   `{parent}`: The organization ID (e.g. `organizations/{org_id}`) or
        source name (e.g. `organizations/{org_id}/sources/{source_id}`)
        extracted from `{finding_name}`.
    *   `{finding_name}`: The full finding name resource path.

*   **Safety Warning**: NEVER run `gcloud scc findings describe {finding_name}`.

### Step 3: Validate Finding Scope

Inspect the retrieved finding JSON payload:

1.  **Finding Class**: Confirm the `findingClass` is `TOXIC_COMBINATION`. If not
    `TOXIC_COMBINATION` and the finding name does not contain `/issues/`, inform
    the user that automated triage is currently only supported for Toxic
    Combinations.
2.  **Parent**: Confirm the parent resource starts with `organizations/`. If the
    parent starts with `projects/` or `folders/`, inform the user that automated
    triage is only supported for organization-level findings.

### Step 4: Extract Attack Path details

For `TOXIC_COMBINATION` findings, the attack path is described in the
`attackExposure` object inside the finding details.

1.  Verify the `attackExposure` field is present and has a `score > 0`.
2.  Examine the attack path nodes and edges in the finding payload or referenced
    `attackExposureResult` to identify exposed resources and attack
    trajectories.

## Reference Schema

See [finding_schema.md](references/finding_schema.md) for the JSON structure of
a Security Command Center finding.
