---
name: security-remediation-draft
description: >-
  Formulates, summarizes, and drafts remediation options for Toxic Combination security issues. Covers business impact synthesis, extraction of exposed resources, and routing to specialized remediation paths (Public Bucket, User Managed Key, IAM Troublesome Permissions, or Public Instance). Use when triaging Toxic Combinations, summarizing attack paths, and presenting remediation choices. Don't use for querying SCC findings (use security-scc-query), analyzing service account IAM permissions (use security-iam-analyzer), or executing changes directly.
---

<!-- disableFinding(HTML_BROKEN) -->
<!-- disableFinding(LINE_OVER_80) -->

# Security Remediation Draft Skill

This skill guides the agent in identifying risks, synthesizing business impact,
formatting findings, and preparing structured remediation choices for Toxic
Combination security issues on Google Cloud.

## 3-Tier Consent Gate

*   **Tier R (Read-Only)**: Analyzing and summarizing finding data, attack
    paths, and resource configurations.
*   **Tier M (Mutating)**: Drafting terraform config or gcloud commands for
    remediation. No commands should be executed without explicit user
    confirmation.
*   **Tier D (Destructive)**: None.

## Execution Rules & Constraints

1.  **Zero-Speculation Gating**:
    *   You **MUST NOT** speculate, guess, or use any placeholder or hardcoded
        IDs, resource names, bucket names, key IDs, or service account emails.
        All values used MUST come directly from the user's input context or the
        output of a successfully executed read-only diagnostic command.
    *   You **MUST NOT** run any Google Cloud diagnostic commands if the
        parameters needed to draft the remediation (such as project ID, bucket
        ID, service account email, firewall rules, or troublesome permissions)
        are already present in the user prompt or input context.
    *   You **MUST NOT** call any MCP search or knowledge tools (such as
        `google-developer-knowledge/search_documents` or other lazy-loaded MCP
        tools) under any circumstances, as they are disabled in this
        environment.
    *   If any critical context parameter (e.g. project ID, bucket ID) is
        missing, halt execution and ask the user to provide it.
    *   If the finding payload or context is missing the `nextSteps` field or if
        it is empty/null, you **MUST NOT** run any Google Cloud diagnostic
        commands, query SCC, or search the workspace to find it or to retrieve
        other missing parameters (such as service account emails or firewall
        rules).
    *   You **MUST** immediately halt and ask the user to provide the missing
        next steps or parameters, or propose a generic fallback remediation
        option based on the category without executing or drafting specific
        commands.
    *   If any read-only Google Cloud diagnostic command, delegated subagent
        analysis, tool execution, or command fails, errors, or times out
        (including **permission prompt timeouts** and **MCP tool
        connection/Forbidden errors**), you **MUST** immediately treat it as a
        terminal failure, halt all execution, and notify the user. You **MUST
        NOT** attempt to troubleshoot, retry, recover, or call `schedule` or
        other tools to wait.
    *   Under no circumstances should you run queries in a loop, search
        workspace files, or run global search/list commands (such as `gcloud scc
        findings list`, `gcloud scc findings group`, `gcloud asset
        search-all-resources`, or `gcloud asset search-all-iam-policies`) to
        guess or find missing payload fields or resource parameters.
2.  **NEVER search the workspace or codebase for finding or resource details**:
    *   All SCC findings, toxic combinations, and active resource metadata
        reside strictly in the cloud or in the provided user prompt.
    *   You **MUST NOT** use any workspace search or codebase query tools
        (including `code_search`, `grep`, `grep_search`, `find`, or custom
        Python/bash scripts) to locate finding details, resource definitions,
        category behaviors, logs, service accounts, project IDs, or test
        specifications. Running `code_search` or reading workspace files to find
        mock service accounts, project IDs, or finding details is strictly
        forbidden and constitutes cheating.
    *   You **MUST NOT** access, read, or search any files in the workspace
        ending in `.yaml`, `.yml`, or containing `EVAL` (such as `EVAL.yaml`),
        as they contain test case definitions. Accessing these files constitutes
        an integrity violation.
3.  **Remediation Action Gating**:

    *   You **MUST** present the identified remediation paths to the user as
        clear, distinct choices.
    *   You **MUST NOT** unilaterally select a single remediation path if
        multiple distinct options are available, OR draft multiple configuration
        remediations, without the user's explicit confirmation or selection,
        **UNLESS**:
        1.  The user prompt explicitly requests multiple options, e.g., using
            plural words like "options", "remediations", or "all options".
        2.  The `nextSteps` field in the finding payload or context lists
            multiple alternative remediation paths or commands (e.g., separated
            by "or" or listed as bullet points). In either of these cases, you
            **MUST** draft remediations for **all** identified options/paths at
            once without halting to ask the user to select.

4.  **Handling Missing nextSteps**:

    *   If the input finding payload does not contain a `nextSteps` field, or if
        the `nextSteps` field is null or empty, you **MUST** detect this missing
        information.
    *   You **MUST** immediately halt and ask the user to provide the next steps
        or the specific resource parameters.
    *   You **MUST NOT** run any Google Cloud diagnostic commands, query SCC, or
        search the workspace/codebase to try to find the missing details or
        parameters.
    *   You may propose a generic, non-executable fallback remediation option
        based on the category (e.g., advising to restrict firewall rules for
        public VMs), but you must still halt and ask the user for the specific
        parameters needed to draft the commands.

5.  **Strict Prohibition on Mutating Commands**:

    *   You **MUST NOT** run or execute any mutating Google Cloud commands under
        any circumstances (such as `gcloud ... update ...`, `gcloud iam ...`,
        `gcloud storage ... update`, or any command that writes, modifies, or
        updates Google Cloud resource configurations or states).
    *   Your role is strictly to **draft** the remediation. You must never
        attempt to apply or execute the modifications directly on the live
        infrastructure or resources.

## Execution Workflow

### Step 0: Gating Check for nextSteps and Parameters

Before taking any other actions or running any commands:

1.  Check if the input finding payload contains a non-empty `nextSteps` field.
2.  If `nextSteps` is missing, null, or empty, and you do not have the required
    resource parameters (e.g. project ID, bucket ID) present in the prompt:
    -   Do NOT run any gcloud or diagnostic commands.
    -   Do NOT run any search or directory list commands.
    -   Immediately halt and formulate the finding summary using the template
        (with generic fallback options based on the category) and ask the user
        to provide the missing details using the `ask_question` tool.
    -   Stop execution here.

### Step 1: Risk Factor Analysis

Analyze the attack path vector data to identify which of the following risk
factors are present:

1.  **Publicly Exposed Bucket**: GCS bucket allowing public read or write access
    (`allUsers` or `allAuthenticatedUsers`).
2.  **User Managed Key**: Service account using user-managed keys that could be
    leaked or compromised.
3.  **IAM Troublesome Permissions**: Service account with highly permissive or
    risky roles/permissions (e.g. `iam.serviceAccounts.actAs`).
4.  **Publicly Exposed Instance**: VM instances with external IP addresses and
    permissive firewall rules.

### Step 2: Context and Parameter Extraction

Extract the specific context required to formulate the remediation plan:

*   **nextSteps**: Extract the `nextSteps` field if available. If missing,
    follow the "Handling Missing nextSteps" rule.
*   **For Public Buckets**: Extract the `bucket_id` of the exposed GCS bucket.
*   **For User Managed Keys**: Extract the `key_name` of the service account
    key.
*   **For IAM Troublesome Permissions**:
    *   Find the service account's email (`service_account_email`) and its
        `project_id`.
    *   Compile the specific risky permissions (e.g.,
        `iam.serviceAccounts.actAs`, `storage.objects.list`) into
        `troublesome_permissions`.
*   **For Public Instances**: Extract the firewall rules (`firewall_rules`) that
    expose the instance.

### Step 3: Business Impact Synthesizing

Formulate the `finding_summary` by explaining the business impact of this Toxic
Combination (e.g., "A publicly exposed compute instance has software
vulnerabilities and can assume a highly privileged service account, potentially
allowing an attacker to read sensitive GCS buckets.").

### Step 4: Presentation Formatting

Format the summary exactly as shown in
[presentation_template.md](references/presentation_template.md).

### Step 5: Remediation Action Routing

Depending on whether a path has been pre-selected or multiple options need to be
drafted:

*   **If multiple options are requested/provided** (e.g., in the user prompt or
    `nextSteps`): Draft the remediation configurations for all requested options
    in parallel (e.g., draft the command to remove public members AND draft the
    command to enable public access prevention).
*   **If a specific path is selected by the user** (or specified in the prompt):
    Route directly to that remediation path.
*   **Otherwise**: Present the identified risk factors as choices to the user,
    and wait for their selection before routing.

Route the remediation drafting as follows:

*   **Public Bucket Remediation**: Pass `bucket_id` and `finding_summary` to
    draft a bucket policy update (e.g., removing public members).
*   **User Managed Key Remediation**: Pass `key_name` and `finding_summary` to
    draft a key rotation or deletion plan.
*   **IAM Troublesome Permissions**: You **MUST** use the `invoke_subagent` tool
    with `TypeName="security-iam-analyzer"` to analyze and remediate this
    finding. Before calling `invoke_subagent`, you **MUST** read the relative
    path of the skill file at
    `third_party/skills/skills/cloud/security-iam-analyzer/SKILL.md` using
    `view_file` first to understand the subagent's expected execution loop. You
    **MUST NOT** formulate the remediation commands yourself, and you **MUST
    NOT** delegate this task to generic research subagents (such as
    `research-google`).
*   **Public Instance Remediation**: Pass `firewall_rules` and `finding_summary`
    to draft firewall rule modifications to isolate the instance.
