---
name: google-cloud-scc-query
description: >-
  Queries and retrieves active security findings, toxic combinations, or vulnerabilities from Google Cloud Security Command Center (SCC). Use when retrieving details for a security finding by its name, validating finding scope (e.g., verifying findingClass is TOXIC_COMBINATION or VULNERABILITY), or fetching finding details for triage. Always keep executions read-only and never guess missing parameters.
---

<!-- disableFinding(HTML_BROKEN) -->
<!-- disableFinding(LINE_OVER_80) -->

# Security Command Center (SCC) Query Skill

This skill provides guidelines and gcloud CLI command patterns for retrieving
and querying security findings, toxic combinations, and vulnerabilities from
Google Cloud Security Command Center (SCC).

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
*   To list active findings, toxic combinations, or vulnerabilities in a project
    or organization.
*   To retrieve the attack path simulation (APS) details embedded in toxic
    combination findings, or the vulnerability details (like CVE context)
    embedded in vulnerability findings.

## Execution Rules & Constraints

1.  **HITL (Human-in-the-Loop) Escalation**: You MUST immediately halt execution
    and ask the user to provide guidance when encountering ambiguous user
    intent, conflicting SCC facts, or missing `gcloud` or API configuration
    permissions.
2.  **Read-Only Operations**: All executions are strictly Read-Only. You MUST
    NOT execute mutating `gcloud` or Terraform commands under any circumstances.
3.  **Zero-Speculation**: Security findings, resource states, and remediation
    actions MUST NEVER be speculated or assumed. If data is missing, ambiguous,
    or outside vetted bounds, you MUST immediately halt and ask the user for
    clarification.
4.  **Handling Missing IDs**:
    *   If the project ID, organization ID, or folder ID is missing or not
        provided in the user's prompt or context, you **MUST** halt execution
        immediately and ask the user to provide the correct ID, unless the
        finding name itself implies it. You **MUST NOT** speculate, guess, or
        attempt to look up missing identifiers via `gcloud config` (e.g.,
        `gcloud config get-value project`).
5.  **Missing Finding Details**:
    *   If the user specifies a unique finding name in their request, and the
        `gcloud scc findings list` command filtered by that name returns an
        empty result, you **MUST** immediately stop, return a final response to
        the user stating that the specified finding could not be found, and halt
        execution. You **MUST NOT** attempt to list all findings in the
        organization/project, ask the user to choose from other findings, or
        fall back to any other skills or tools.
6.  **Ambiguous or Missing Finding Name**:

    *   If the user asks for details of the active finding in a
        project/organization but does not specify the unique finding name, you
        should list the active findings. You **MUST** format the parent ID into
        the fully qualified parent resource path (e.g.,
        `organizations/{org_id}`, `projects/{project_id}`, or
        `folders/{folder_id}`) and use the exact syntax:

        ```bash
        gcloud scc findings list {parent} \
          --location=global \
          --filter="state=\"ACTIVE\"" \
          --field-mask="finding.name,finding.findingClass,finding.category,finding.state,finding.eventTime" \
          --format="json" --order-by="event_time desc" --limit=100
        ```

    *   If the user specifically asks to list active vulnerabilities or active
        toxic combinations, you **MUST** filter by `findingClass`:

        -   For Vulnerabilities:

            ```bash
            gcloud scc findings list {parent} \
              --location=global \
              --filter="state=\"ACTIVE\" AND findingClass=\"VULNERABILITY\"" \
              --field-mask="finding.name,finding.findingClass,finding.category,finding.state,finding.eventTime,finding.severity,finding.resourceName" \
              --format="json" --order-by="event_time desc" --limit=100
            ```

        -   For Toxic Combinations:

            ```bash
            gcloud scc findings list {parent} \
              --location=global \
              --filter="state=\"ACTIVE\" AND findingClass=\"TOXIC_COMBINATION\"" \
              --field-mask="finding.name,finding.findingClass,finding.category,finding.state,finding.eventTime,finding.severity,finding.resourceName" \
              --format="json" --order-by="event_time desc" --limit=100
            ```

    *   If the user asks to filter findings by a specific category, you **MUST**
        use the exact syntax:

        ```bash
        gcloud scc findings list {parent} \
          --location=global \
          --filter="state=\"ACTIVE\" AND category=\"{category}\"" \
          --field-mask="finding.name,finding.findingClass,finding.category,finding.state,finding.eventTime,finding.severity,finding.resourceName" \
          --format="json" --order-by="event_time desc" --limit=100
        ```

    *   If multiple findings are provided in the user's prompt or context, or if
        multiple findings are returned by the list command, you **MUST NOT**
        unilaterally pick one to describe, nor attempt to retrieve details for
        multiple findings. You **MUST** immediately halt execution and ask the
        user to specify which finding name they want details for.

    *   If the list command returns **zero findings** (empty result), you
        **MUST** immediately stop, return a final response to the user stating
        that no active findings were found in the specified
        project/organization, and halt execution. You **MUST NOT** search the
        workspace, try to find it elsewhere, or invoke other skills.

7.  **Do NOT verify or describe attack path resources**:

    *   This skill is strictly for retrieving and extracting details *from the
        SCC finding payload itself*.
    *   You **MUST NOT** attempt to run any commands to describe, verify, or
        query the actual GCP resources (such as GCS buckets, service accounts,
        VMs, or IAM policies) mentioned in the finding's attack path.
    *   Resource analysis must be delegated to other skills (like
        `security-iam-analyzer`) or skipped entirely if not explicitly requested
        by the user.

8.  **Immediate Halt on Execution Errors**:

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

9.  **Strict Turn Budget (Single-Attempt)**:

    -   You are allowed a maximum of **1 tool-execution turn** (a single
        attempt/turn) to retrieve the finding payload. Under no circumstances
        are you allowed a second turn or any additional tool calls. If after
        this **single tool-execution turn** you have not successfully retrieved
        the finding details (e.g., the command fails or returns empty), you
        **MUST** immediately stop all tool calls, explain the situation, and
        halt execution. Do NOT attempt any other commands or variations.

10. **No Retries or Variations on Empty/Failure Results**:

    -   If the `gcloud scc findings list` command returns an empty array `[]` or
        fails with an error, you **MUST NOT** attempt to run it again with
        different filters, different parent parameters, or different arguments.
        You **MUST NOT** run other listing or diagnostic commands. Treat the
        empty result or error as final, halt execution immediately, and report
        the verbatim outcome to the user.

## Intent-Based Query Strategies

When querying SCC, you must first determine the user's intent. Do not default to
retrieving the full finding payload unless specifically asked for a single
finding.

### 1. Discovery Strategy (High-Level Aggregation)

**Intent**: The user wants to understand the landscape, count findings, or see
the most common issues (e.g., "What are the most common findings?", "Show me a
summary by category"). **Action**: Use `gcloud scc findings group` to aggregate.
Allowed fields for `--group-by` are strictly: `resource_name`, `category`,
`state`, `parent`. Do not group by other fields. **Command Pattern**:

```bash
gcloud scc findings group {parent} \
  --location=global \
  --group-by="{group_by_field}" \
  --filter="state=\"ACTIVE\"" \
  --format="json"
```

### 2. Listing Strategy (Filtered Projection)

**Intent**: The user wants to see a list of findings matching criteria, but does
not explicitly ask for a deep dive into a single finding (e.g., "List my active
vulnerabilities", "Show me recent toxic combinations"). **Action**: Use `gcloud
scc findings list` with `--field-mask` projection to avoid massive payloads.
**Command Pattern**:

```bash
gcloud scc findings list {parent} \
  --location=global \
  --filter="state=\"ACTIVE\"" \
  --field-mask="finding.name,finding.findingClass,finding.category,finding.state,finding.eventTime,finding.severity,finding.resourceName" \
  --format="json" --order-by="event_time desc" --limit=100
```

*(Append `AND findingClass=\"{class}\"` to the filter if a specific class is
requested).*

### 3. Deep Dive Strategy (Specific Finding Details)

**Intent**: The user provides a specific finding name or explicitly asks to
retrieve all details for one finding. **Action**: First, verify the **Parent
Scope**. Confirm the parent starts with `organizations/`. If it is `projects/`
or `folders/`, you MUST immediately halt and inform the user that automated
triage is only supported for organization-level findings. Do not attempt to run
any commands. If it is `organizations/`, use `gcloud scc findings list` with a
strict filter on the name, and NO `--field-mask` to get the full payload.
**Command Pattern**:

```bash
gcloud scc findings list {parent} \
  --filter="name=\"{finding_name}\"" \
  --location=global \
  --format="json" --order-by="event_time desc" --limit=100
```

*   **Safety Warning**: NEVER run `gcloud scc findings describe {finding_name}`.

### Validation and Routing (After Retrieval)

Once a full payload is retrieved (Deep Dive), analyze the payload based on the
finding class:

1.  **TOXIC_COMBINATION**: Analyze the payload and generate a non-mutating
    remediation draft based on the finding context and attack path.
2.  **VULNERABILITY**: Extract CVE/EPSS/CVSS and use this context to prioritize
    the risk and propose non-mutating remediation steps.
3.  **MISCONFIGURATION**: Analyze the misconfiguration and generate a
    non-mutating remediation draft.

### Extract Attack Path or Vulnerability Details

**For `TOXIC_COMBINATION` findings:** The attack path is described in the
`attackExposure` object inside the finding details.

1.  Verify the `attackExposure` field is present and has a `score > 0`.
2.  Examine the attack path nodes and edges in the finding payload or referenced
    `attackExposureResult` to identify exposed resources and attack
    trajectories.

**For `VULNERABILITY` findings:**

1.  Extract CVSS, EPSS, CISA KEV, and affected package details from the
    `vulnerability.cve` object.
2.  Use this extracted context to evaluate and prioritize the vulnerability
    risk.

### Declarative Handoff (Toxic Combinations / Misconfigurations)

If the finding relates to a "Publicly Accessible VM" or "Open Firewall Port",
you **MUST** rely entirely on the Attack Path or misconfiguration context within
the payload to confirm the exposure. Then, end your response by explicitly
asking the user to choose the next step:

*   **Mute:** Ask if they want to mute the finding. If they choose this, draft
    the `gcloud scc findings set-mute <finding_id> --organization=<org_id>
    --source=<source_id> --location=global --mute=MUTED` command.
*   **Mitigate:** Ask if they want to draft right-sized firewall rules (via
    `gcloud` or Terraform) to restrict the exposed ports. Always output
    non-mutating drafts and never execute them without explicit permission.

## Reference Schema

See [finding_schema.md](references/finding_schema.md) for the JSON structure of
a Security Command Center finding.
