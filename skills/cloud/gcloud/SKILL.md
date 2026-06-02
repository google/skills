---
name: gcloud
description: >-
  Interacts with Google Cloud services using the gcloud CLI safely and
  efficiently. Covers command validation, data reduction, safety guardrails with
  a denylist, and workflows for discovery and investigation. You MUST read this
  skill before invoking any gcloud command. Use when managing cloud resources,
  querying configurations, or troubleshooting issues via gcloud. Don't use when
  writing or debugging Google Cloud client library code or raw REST/gRPC API
  interactions.
---

# gcloud CLI Skill for AI Agents

This document provides essential guidelines and best practices for AI agents
interacting with the Google Cloud SDK (`gcloud` CLI). Following these rules is
critical to avoid hallucinated commands, flags, flag values, and positional
argument syntax, prevent destructive actions, and minimize context window usage.

## Getting Started

### 1. Installation

If the `gcloud` executable is missing, refer to the official
[Google Cloud CLI Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk)
to install it on your platform (Linux, macOS, Windows, etc.).

### 2. Authorization

Authenticate the CLI with Google Cloud. Choose the flow that matches your
running environment:

*   **User Account (Interactive)**: Run `gcloud auth login`. Follow the browser
    prompts to sign in.
*   **User Account (Headless Flow)**: If operating on a terminal without a web
    browser (e.g. containers, remote SSH), append the `--no-browser` flag:
    `gcloud auth login --no-browser`. Copy the URL, sign in on another machine,
    and return the authentication code.
*   **Application Default Credentials (ADC)**: To authenticate code calls from
    local applications or SDK libraries, set up ADC via `gcloud auth
    application-default login` (append `--no-browser` for headless
    environments).
*   **Service Account (Best for Detached/Headless Automation)**: Authenticate
    directly using a JSON key file. Ideal for fully automated, background tasks
    and pipelines: `gcloud auth activate-service-account
    --key-file=path/to/key.json`. Note that some organizations may restrict
    access to JSON key files for security reasons.
*   **Service Account Impersonation (Preferred for Local Pair-Programming
    Agents)**: Leverage the human developer's existing user credentials to
    assume a service account identity. Best for local development assistants to
    avoid insecure private keys on human workstations: `gcloud config set
    auth/impersonate_service_account SERVICE_ACCT_EMAIL`

*Separation of Privilege (Critical)*: Both service account approaches ensure the
agent's permissions remain strictly distinct from the human user's wide access
limits (enforcing least privilege), and ensure actions are properly audited
under the agent's focused identity. *(Impersonation requires
`roles/iam.serviceAccountTokenCreator`)*.

For more detailed strategies and authentication types (such as Workload Identity
Federation), see
[Authorizing the gcloud CLI](https://docs.cloud.google.com/sdk/docs/authorizing).

## Core Principles

### 1. Explicit Command Validation (Mandatory)

Your internal knowledge of `gcloud` may be stale or prone to hallucination
(e.g., hallucinating commands, flags, flag values, or positional argument
syntax). You are **FORBIDDEN** from executing commands until you have validated
the exact syntax at the leaf level.

*   **Action**: Always call `gcloud help <command>` for the *exact* command you
    intend to run (e.g., `gcloud help compute instances create`).
*   **Verify**: Ensure the command, flags, flag values, and positional argument
    syntax are valid for that specific leaf command before attempting execution.
    Validation is not transitive from parent groups.

### 2. Data Reduction Strategies

To save context window space and reduce latency, always minimize the volume of
data returned by `gcloud`.

*   **Projection**: Use `--format=json(key1, key2, ...)` to select only the
    specific fields needed for your task. To understand the advanced projection
    and formatting syntax, refer to `gcloud topic projections` and `gcloud topic
    formats`.

*   **Limiting**: Use `--limit=N` to cap the number of resources returned.

*   **Filtering**: Use `--filter` to narrow down results server-side. Prioritize
    `:` for pattern matching and never quote the right side of the colon. Treat
    the entire filter flag as a singular string without quoting or escaping
    characters. To study the filter expression syntax, refer to `gcloud topic
    filters`.

*   **Schema Discovery**: Unconstrained resource lists can quickly exhaust your
    context window with redundant data. To prevent this, discover a resource's
    schema before executing queries. If you are unsure of the JSON key path for
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
*   **No Interactivity**: Do not run interactive commands or commands requiring
    a TTY (e.g., `gcloud interactive`). You must enforce non-interactive mode by
    appending `--quiet` (or `-q`) to your commands. This ensures that defaults
    are used or errors are raised if input is required.

### 4. Project and Location Scoping (Critical)

To ensure commands are deterministic, non-interactive, and target the correct
environment, you must explicitly manage project and location scoping.

*   **Explicit Project Target**: Do not rely on active configuration defaults.
    Always append `--project=<PROJECT_ID>` to all resource-manipulating and
    querying commands (unless running pure local config commands). This avoids
    accidental execution against the wrong project.

*   **Prevent Location Prompts**: Many Google Cloud resources are regional or
    zonal. If you omit the location flag (e.g., `--region`, `--zone`, or
    `--location`), `gcloud` will trigger an interactive prompt to select a
    zone/region. This violates the **No Interactivity** rule. Always provide
    explicit location flags if the command requires them.

*   **Location Discovery**: If you do not know the correct region, zone, or
    location for a service, run discovery commands first (remembering to limit
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

You are **strictly prohibited** from executing the following commands
autonomously. These require explicit human-in-the-loop authorization:

*   **Any IAM policy, role, or binding modification** (Security): Risk of
    privilege escalation, administrative lockout, service disruption, or
    unauthorized data exposure.
*   **No Proactive API Enabling**: Assume necessary APIs are enabled. To prevent
    unexpected resource provisioning or billing charges, do not proactively try
    to enable APIs. User approval is required to enable any API.
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

*   **Dry Run (Mandatory)**: You MUST invoke a command with `--dry-run` (or
    equivalent) first if it exists, before executing the actual command, to
    preview changes.

*   **Long Running Operations**: For commands that support it, the `--async`
    flag is highly recommended for long-running operations to avoid blocking the
    agentic flow. Note that not every command has an `--async` flag. For
    commands that return an operation ID (whether via `--async` or by default),
    you are responsible for polling for completion if the operation status is
    needed for the next step.

## Structured Workflows

### Discovery Workflow

When asked to perform a task on a service you are not familiar with:

1.  You MUST invoke help on a command (e.g., `gcloud help <COMMAND>`) before
    invoking it.
2.  If you do not know the exact command, traverse the command tree by invoking
    help on a command group (e.g., `gcloud help compute`) to discover available
    subcommands and groups.
3.  **Schema Discovery**: If you need to filter or project fields from a list
    command, but do not know the exact JSON keys, first run `gcloud <GROUP>
    <RESOURCE> list --limit=1 --format=json` to safely discover the schema.
    **Never** run a raw `list` command without scoping constraints (like
    `--limit=1`), as unconstrained results will pollute and exhaust your context
    window.
4.  Execute with data reduction flags.

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
Check Operation    | `gcloud operations describe <OPERATION_ID>`
Common commands    | `gcloud cheat-sheet`
List Regions (GCE) | `gcloud compute regions list --project=<PROJECT_ID>`
List Zones (GCE)   | `gcloud compute zones list --project=<PROJECT_ID>`
List Locations     | `gcloud <GROUP> locations list --project=<PROJECT_ID>`

Refer to the
[gcloud CLI Scripting Guide](https://docs.cloud.google.com/sdk/docs/scripting-gcloud)
for guidance on using the gcloud CLI in automation.
