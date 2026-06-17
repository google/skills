---
name: security-iam-analyzer
description: >-
  Analyzes IAM policies, service accounts, and policy bindings to detect and mitigate excessive or troublesome permissions on Google Cloud. Use when identifying which roles and permissions present security risks, listing IAM policy bindings for a service account, or querying IAM policy recommender. Do not use when querying general SCC findings (use security-scc-query), drafting non-IAM remediations (use security-remediation-draft), or editing local build configurations.
---

<!-- disableFinding(HTML_BROKEN) -->
<!-- disableFinding(LINE_OVER_80) -->

# Security IAM Analyzer Skill

This skill guides the agent in identifying service accounts with excessive
permissions, analyzing assigned roles, querying IAM policy recommenders, and
executing remediation plans (Remove Role, Replace Role, or Custom Role
Creation).

## 3-Tier Consent Gate

*   **Tier R (Read-Only)**: Searching IAM policies, describing service accounts,
    listing recommendations or insights.
*   **Tier M (Mutating)**: Creating custom roles, adding or removing
    project-level or organization-level IAM bindings.
*   **Tier D (Destructive)**: None.

## Execution Rules & Constraints

1.  **Zero-Speculation Gating**:
    *   The project ID and service account email MUST be explicitly provided in
        the user's initial request. You MUST NOT speculate or guess them.
    *   You MUST NOT attempt to run any gcloud commands (such as gcloud config
        get-value project, gcloud projects list, or gcloud iam service-accounts
        list) to discover or guess them if they are missing from the request.
    *   If the project ID or service account email is missing from the user
        request, you MUST immediately halt execution and ask the user to provide
        them.
2.  **NEVER search the workspace or codebase for configuration or resource
    details**:
    *   All project IDs, service account emails, IAM policies, role definitions,
        recommendations, and finding details MUST come strictly from the user's
        prompt or from successfully executed read-only Google Cloud diagnostic
        commands.
    *   You **MUST NOT** use any workspace search or codebase query tools
        (including `code_search`, `grep`, `grep_search`, `find`, or custom
        Python/bash scripts) to locate project IDs, service account emails, role
        names, finding details, or configs.
    *   You **MUST NOT** access, read, or search any files in the workspace
        ending in `.yaml`, `.yml`, or containing `EVAL` (such as `EVAL.yaml`),
        as they contain test case definitions.
3.  **No Recommendations Handling**:
    *   If no recommendations (REMOVE_ROLE or REPLACE_ROLE) and no recommender
        insights are available for the service account, you **MUST** stop and
        report to the user that no active IAM recommendations or insights could
        be found for this service account, and halt execution. Do NOT attempt to
        guess permissions or create custom roles without active
        recommendations/insights.
4.  **Terminal Command Failure**:
    *   If any read-only Google Cloud diagnostic command or tool execution fails
        (returns non-zero exit code, permission denied, authentication error,
        command not found, timeout, or any tool failure), you **MUST**
        immediately treat it as a terminal failure, halt all execution, and
        notify the user.
    *   You **MUST NOT** attempt to troubleshoot, retry, recover, switch active
        accounts, list credentials, search the workspace, or execute fallback
        search/discovery loops.
    *   You **MUST NOT** execute any shell scripts, bash scripts, or bash loops
        (such as trying to run commands under bash or other shells) to
        troubleshoot, retry, or recover from the failure.
5.  **Mutating Actions Consent (Tier M)**:
    *   All remediations that modify IAM policies (e.g. adding roles, removing
        roles, creating custom roles) are Tier M.
    *   You **MUST** format the proposed remediation plan showing the exact
        roles to be added or removed, and the exact commands to be executed, and
        request the user's explicit approval.
    *   You **MUST NOT** execute any mutating command (including role creation,
        binding removal, or binding addition) in the same turn that you propose
        the remediation plan. You **MUST** halt execution immediately after
        proposing the plan and asking for approval.
    *   When execution is resumed, you **MUST** inspect the preceding message
        for explicit, positive user consent (e.g., "yes", "approve", "proceed").
    *   An empty message, a system message, or a continuation prompt without
        explicit positive approval does NOT constitute consent. You **MUST NOT**
        execute any mutating commands on such continuations; instead, you must
        repeat your request for explicit approval and halt execution again.
6.  **No Manual Waiting via Timers**:
    *   The system automatically notifies you and resumes execution when
        background tasks (such as gcloud commands) complete.
    *   You **MUST NOT** call the schedule tool or create timers to check on
        command status, as this causes unnecessary timeouts.
7.  **MCP Tool Call Prohibition**:
    *   You **MUST NOT** call or use any MCP search or knowledge tools,
        including but not limited to
        `google-developer-knowledge/search_documents`, `get_documents`,
        `answer_query`, or other lazy-loaded or eager MCP tools.
    *   All external documentation, Web, or MCP search queries are strictly
        prohibited during the execution of this skill.

## Execution Workflow

### Step 1: Resolve Project ID

The user request might provide the project display name (e.g., "test-project")
instead of the project ID. You MUST first resolve it to the correct GCP project
ID:

```bash
gcloud projects list \
  --filter="name={project_id}" \
  --format="value(projectId)"
```

If this returns a resolved project ID, use it as the `{project_id}` for all
subsequent commands. Otherwise, use the original `{project_id}` provided in the
request.

### Step 2: Query Policy Bindings

To identify where the service account holds permissions across the project, run:

```bash
gcloud asset search-all-iam-policies \
  --scope="projects/{project_id}" \
  --query="policy:\"serviceAccount:{sa_email}\"" \
  --format="json"
```

*   **Edge Case**: If this returns empty, the service account might have been
    deleted. Verify its existence:

    ```bash
    gcloud iam service-accounts describe {sa_email}
    ```

    If this command fails with a `NOT_FOUND` error, inform the user that the
    service account is already deleted and the finding is resolved.

### Step 3: Identify Problematic Roles

Examine the policies returned in Step 2. Match the service account's assigned
roles against `{troublesome_permissions}` to determine which roles grant those
permissions.

### Step 4: Query IAM Recommender

Query active recommendations to find the safest fix.

1.  **Search for REMOVE_ROLE recommendations**:

    ```bash
    gcloud recommender recommendations list \
      --recommender=google.iam.policy.Recommender \
      --location=global \
      --project="{project_id}" \
      --filter="stateInfo.state=\"ACTIVE\" AND content.overview.member=\"serviceAccount:{sa_email}\" AND recommenderSubtype=\"REMOVE_ROLE\"" \
      --format="json"
    ```

2.  **Search for REPLACE_ROLE recommendations** (fallback if no REMOVE_ROLE
    recommendation exists):

    ```bash
    gcloud recommender recommendations list \
      --recommender=google.iam.policy.Recommender \
      --location=global \
      --project="{project_id}" \
      --filter="stateInfo.state=\"ACTIVE\" AND content.overview.member=\"serviceAccount:{sa_email}\" AND recommenderSubtype=\"REPLACE_ROLE\"" \
      --format="json"
    ```

### Step 5: Formulate and Execute Remediation Plan

Present the feasible plans to the user. Do not perform any mutating action
without explicit approval. You MUST propose the plan and request approval, and
you MUST NOT execute any mutating commands in the same turn or on an empty
resume/system continuation.

#### Plan A: Remove Role

If a `REMOVE_ROLE` recommendation is active and targets a role containing
troublesome permissions:

1.  Add new roles with lesser privileges (if recommended).
2.  Remove the excessive role.

#### Plan B: Replace Role

If a `REPLACE_ROLE` recommendation is active:

1.  Add the new roles suggested by the recommendation.
2.  Remove the old excessive roles.
3.  *Safety Note*: Add new roles BEFORE removing old ones to prevent service
    disruption.

#### Plan C: Create Custom Role

If recommender insights exist but no recommendations are available, and the
exercised/inferred permissions do not include the troublesome permission:

1.  Create a custom role with all required permissions:

    ```bash
    gcloud iam roles create {role_id} \
      --project="{project_id}" \
      --title="{role_title}" \
      --permissions="{permissions_comma_separated}" \
      --stage="GA"
    ```

2.  Bind the custom role to the service account.

3.  Remove the old excessive roles.
