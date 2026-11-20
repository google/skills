---
name: gcloud
metadata:
  version: "1.0.4"
  category: CloudInfrastructureAndServices
description: >-
  Provides safety-critical validation, guardrails, and data reduction for gcloud
  CLI operations across Google Cloud Platform (GCP) services and infrastructure.
  Use when planning, generating, constructing, proposing, describing, or
  executing any gcloud CLI commands - including when answering questions about
  gcloud syntax, or formatting flags. Don't use when writing Google Cloud
  client library code or raw REST/gRPC API requests.
---

# gcloud CLI Skill for AI Agents

> [!CAUTION]
>
> ### MANDATORY PRE-CONDITION: EXPLICIT LEAF-LEVEL SYNTAX VALIDATION
>
> All pre-existing knowledge of `gcloud` commands, flags, flag values, and
> positional argument syntax is **stale and prone to hallucination**.
>
> NEVER propose command parameters, output flag options, execute commands, OR
> outline step-by-step plans for any `gcloud` task before validating leaf-level
> syntax via `gcloud help <command>` (or including leaf-level help lookup as a
> mandatory step in the plan).
>
> **Mandatory Action Rules**:
>
> 1.  **Direct Execution & Code Generation**: **ALWAYS** invoke `gcloud help
>     <leaf_command>` (e.g. `gcloud help compute instances create` or `gcloud
>     help sql instances create`) before proposing or executing the final
>     command syntax, **UNLESS** the user prompt already provides `gcloud help`
>     output, states to assume command syntax is already validated, or instructs
>     not to execute any commands. When instructed not to execute any commands,
>     **NEVER** invoke `run_command` (not even for `gcloud help` or directory
>     listing commands like `ls`); read bundled reference files
>     (`references/cli-usage.md`, `references/mcp-usage.md`, and
>     `references/attribution.md`) directly with `read_file`.
>
> 2.  **Planning & Strategy Queries**: When asked for a plan, strategy, or next
>     steps to achieve a user goal (e.g., *"What is your plan to accomplish
>     X..."*), the response **MUST explicitly include running `gcloud help
>     <leaf_command>`** as Step 1 of the plan before proposing flags or
>     executing commands.
>
> 3.  **Non-Transitive Validation**: Parent command group help (e.g. `gcloud
>     help compute`) is not sufficient for leaf-level syntax validation.
>     Validation must occur at the specific leaf subcommand level.
>
> 4.  **FORBIDDEN Web Search Fallback**: NEVER use `search_web`, web search, or
>     external documentation search tools for gcloud CLI syntax. `gcloud help
>     <leaf_command>` is the **EXCLUSIVE** authorized authority for command
>     syntax.
>
> 5.  **User Flag & Project Preservation**: When proposing intermediate command
>     steps, **ALWAYS** preserve all user-specified flags (including
>     `--project=<project_id>`) in the proposed response text.
>
> 6.  **Mandatory Plan Template**: When generating a plan, the response **MUST**
>     copy this exact 4-step structure:
>
>     -   **Step 1**: Syntax Validation via `gcloud help <leaf_command>`
>     -   **Step 2**: Parameter Verification (confirming required and optional
>         flags, and explicitly checking if the `--dry-run` or `--validate-only`
>         flag is supported)
>     -   **Step 3**: Dry-Run Command Proposal (If `--dry-run` or
>         `--validate-only` is supported, there MUST be a `--dry-run` or
>         `--validate-only` invocation before the next step.)
>     -   **Step 4**: Command Proposal & Authorization (If the command is on the
>         "Prohibited Operations" denylist, state that autonomous execution is
>         forbidden, and the user MUST be explicitly asked for authorization to
>         proceed. If the command is NOT on the denylist, propose or proceed
>         with execution, while following *ALL* "Execution Constraints" below.)

This document provides essential guidelines and best practices for AI agents
interacting with the Google Cloud SDK (`gcloud` CLI). Following these rules is
critical to avoid hallucinated commands, flags, flag values, and positional
argument syntax, prevent destructive actions, and minimize context window usage.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md). If a more specific product or
domain skill (e.g., `cloud-run-basics`, `bigquery-basics`, `gke-basics`) is
also loaded or active for the current task, **ALWAYS** use that specific
skill's `skill:<name>` attribution tag instead of `skill:gcloud`. For commands
executed directly in the terminal when no product-specific skill applies (never
in generated scripts, Terraform, or user code), prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:gcloud)"`
and append `agent-skills/1.0 (skill:gcloud)` to `User-Agent` headers.

## Execution Modes

AI agents can interact with Google Cloud resources in two primary ways:

-   **Direct CLI Execution**: Executing `gcloud` commands directly in a local or
    automated shell environment. See [CLI Usage](references/cli-usage.md) for
    installation, authentication flows, and configuration management.
-   **Model Context Protocol (MCP)**: Invoking structured tools via the Cloud
    CLI remote MCP server (`run_gcloud_command`). See
    [MCP Usage](references/mcp-usage.md) for tool schemas, parameter rules, and
    server configuration.

## Core Principles

### 1. Explicit Command Validation (Mandatory)

*   **Action**: **ALWAYS** call `gcloud help <command>` for the *exact* command
    that is intended to be run (e.g., `gcloud help compute instances create`).
*   **Verify**: Ensure the command, flags, flag values, and positional argument
    syntax are valid for that specific leaf command before attempting execution
    or presenting plans. Validation is not transitive from parent groups.

### 2. Data Reduction Strategies (Mandatory)

Minimize the volume of data returned by `gcloud` to save context window space
and reduce latency. DO NOT execute any `list` command without including at least
one data reduction flag (`--limit`, `--filter`, or `--format`).

*   **Projection**: Use `--format="json(key1, key2, ...)"` to select only the
    specific fields needed for the task. To understand the advanced projection
    and formatting syntax, refer to `gcloud topic projections` and `gcloud topic
    formats`.

*   **Limiting**: Use `--limit=N` to cap the number of resources returned.

*   **Filtering**: Use `--filter` to narrow down results server-side. Prioritize
    `:` for pattern matching and never quote the right side of the colon. Treat
    the entire filter flag as a singular string without quoting or escaping
    characters. To study the filter expression syntax, refer to `gcloud topic
    filters`.

*   **Schema Discovery**: Unconstrained resource lists can quickly exhaust the
    context window with redundant data. To prevent this, discover a resource's
    schema before executing queries. If unsure of the JSON key path for
    projecting fields (`--format`) or filtering (`--filter`), run the targeted
    resource's list command (if supported) with a single-item limit:

    ```bash
    gcloud <GROUP> <RESOURCE> list --limit=1 --format=json
    ```

    Examine this single instance's JSON structure to safely identify the correct
    schema keys before requesting full or filtered datasets.

### 3. Execution Constraints

*   **Single Commands**: Execute a single `gcloud` command at a time. No command
    chaining or sequencing.
*   **No Shell Operators**: Do not use command substitution (`$(...)`), pipes
    (`|`), or redirection (`>`, `>>`, `<`). This is to increase command safety
    and ensure commands are more easily understandable and reviewable by users.
*   **Non-Interactive Execution (`--quiet` / `-q`)**: Pass the `--quiet` (or
    `-q`) global flag on all execution commands (e.g., `gcloud pubsub topics
    delete temp-topic --quiet --project=test-project`). AI agents run in
    headless, non-interactive environments without a TTY or `stdin` input
    handler. Without `--quiet`, commands that prompt for user confirmation (such
    as deleting resources, approving defaults, or selecting unspecified regions)
    will pause execution indefinitely waiting for input, causing background task
    timeouts. Including `--quiet` forces non-interactive mode, causing `gcloud`
    to automatically accept safe default choices or fail immediately with an
    explicit error if required parameters are missing.
*   **No Blind Lists**: NEVER execute a `list` command without `--limit`,
    `--filter`, or `--format`.

### 4. Project and Location Scoping (Critical)

To ensure commands are deterministic, non-interactive, and target the correct
environment, they must explicitly provide project and location scoping.

*   **Explicit Project Target**: Do not rely on active configuration defaults.
    Always append `--project=<PROJECT_ID>` to all resource-manipulating and
    querying commands (unless running pure local config commands). This avoids
    accidental execution against the wrong project.

*   **Prevent Location Prompts**: Many Google Cloud resources are regional or
    zonal. If the location flag is omitted (e.g., `--region`, `--zone`, or
    `--location`), `gcloud` will trigger an interactive prompt to select a
    zone/region. This violates the **No Interactivity** rule. Always provide
    explicit location flags if the command requires them.

*   **Location Discovery**: If the correct region, zone, or location for a
    service is not known, run discovery commands first (remembering to limit
    results if there are many):

    *   **Compute Engine (VMs, Networks)**:

        *   `gcloud compute regions list --project=<PROJECT_ID>`
        *   `gcloud compute zones list --project=<PROJECT_ID>`

    *   **Other Services (Standard API Style)**: Many GCP services utilize a
        unified `locations list` command:

        *   `gcloud <GROUP> locations list --project=<PROJECT_ID>`
        *   *Examples*: `gcloud artifacts locations list`, `gcloud kms locations
            list`, `gcloud secrets locations list`.

## Safety & Guardrails

> [!CAUTION] **Destructive actions (delete, update, remove) MUST be explicitly
> authorized by the user.** Never invoke them autonomously unless explicitly
> instructed to do so in the context of a safe, pre-approved workflow.

### Prohibited Operations (Denylist)

NEVER execute the following commands autonomously. These require explicit
human-in-the-loop authorization:

*   **Any IAM policy, role, or binding modification** (Security): Risk of
    privilege escalation, administrative lockout, service disruption, or
    unauthorized data exposure.
*   **No Proactive API Enabling**: Assume necessary APIs are enabled. To prevent
    unexpected resource provisioning or billing charges, do not proactively try
    to enable APIs. User approval is required to enable any API.
*   **No Proactive `gcloud` CLI Installation** (Host Modification): Never
    autonomously install the Google Cloud CLI (`gcloud` CLI) or additional
    `gcloud` CLI components (`gcloud components install`, `gcloud components
    update`, or system package manager installs of the `gcloud` CLI). If the
    `gcloud` binary or a required CLI component is missing, you **must** inform
    the user, ask for explicit user confirmation (e.g., *"I am ready to install
    the Google Cloud CLI (`gcloud`). Do you want me to proceed?"*), and
    **strictly stop** to wait for the user's positive affirmation before
    executing any installation commands.
*   **`gcloud * delete`** (Destructive): Irreversible resource destruction
    (e.g., project deletion) or data wiping.
*   **`gcloud billing *`** (Financial): Risk of service disruption or unbounded
    costs.
*   **`gcloud organizations *`** (Governance): Org-level changes affect security
    posture for all users.
*   **`gcloud kms *`** (Encryption): Risk of permanently locking data.
*   **`gcloud infra-manager deployments apply`** (Destructive): Autonomous IaC
    execution can destroy managed resources.

### Execution Guidelines

*   **Dry Run (Mandatory)**: If the `--dry-run` or `--validate-only` flag (or
    equivalent) is listed in the command help output, ALWAYS include the flag in
    the proposed command or initial execution step. ALWAYS preview changes with
    `--dry-run` or `--validate-only` prior to actual execution.

*   **Long Running Operations**: For commands that support it, the `--async`
    flag is highly recommended for long-running operations to avoid blocking the
    agentic flow. Note that not every command has an `--async` flag. For
    commands that return an operation ID (whether via `--async` or by default),
    operation status must be polled for completion, if needed for the next step.

*   **Non-Interactive Flag (`--quiet`)**: Include `--quiet` (or `-q`) on all
    proposed or executed commands to guarantee non-interactive execution without
    waiting for TTY confirmation prompts.

## Structured Workflows

### Discovery Workflow

When asked to perform a task on a service that is unfamiliar:

1.  **Invoke Help**: Call `gcloud help <COMMAND>` on the target leaf command
    prior to execution.
2.  **Traverse Command Tree**: Run help on command groups (e.g., `gcloud help
    compute` or `gcloud help`) to discover available subgroups and commands if
    the exact command is unknown.
3.  **Discover Schema**: Run `gcloud <GROUP> <RESOURCE> list --limit=1
    --format=json` to inspect JSON keys before constructing filters or
    projections. DO NOT execute unconstrained `list` commands without scoping
    flags (e.g., `--limit=1`) to prevent context window exhaustion.
4.  **Enforce Data Reduction**: Include data reduction flags (`--limit`,
    `--filter`, `--format`) on all command executions.

## Quick Reference / Cheat Sheet

Task               | Command Template
------------------ | ----------------------------------------------------------
Discover Schema    | `gcloud <GROUP> <RESOURCE> list --limit=1 --format=json`
Filtered List      | `gcloud <GROUP> <RESOURCE> list --filter="status:RUNNING"`
Specific Columns   | `gcloud <GROUP> <RESOURCE> list --format="json(name, id)"`
Learn Filters      | `gcloud topic filters`
Learn Formats      | `gcloud topic formats`
Learn Projections  | `gcloud topic projections`
Asynchronous Op    | `gcloud <COMMAND> --async`
Check Operation    | `gcloud <GROUP> operations describe <OPERATION_ID>`
Common commands    | `gcloud cheat-sheet`
List Regions (GCE) | `gcloud compute regions list --project=<PROJECT_ID>`
List Zones (GCE)   | `gcloud compute zones list --project=<PROJECT_ID>`
List Locations     | `gcloud <GROUP> locations list --project=<PROJECT_ID>`

Refer to the
[gcloud CLI Scripting Guide](https://docs.cloud.google.com/sdk/docs/scripting-gcloud.md.txt)
for guidance on using the gcloud CLI in automation.

## Reference Directory

-   [CLI Usage](references/cli-usage.md): Platform installation, authentication
    methods (interactive, headless, ADC, service account keys, impersonation),
    and local configuration management.

-   [MCP Usage](references/mcp-usage.md): Using the Cloud CLI remote MCP
    server (`run_gcloud_command`), project parameter scoping, input files, and
    execution guidelines.

-   [Usage Attribution](references/attribution.md): Standardized usage
    attribution tags and multi-skill precedence rules for `gcloud` CLI, REST
    API, and MCP requests.
