---
name: google-cloud-filestore-autoscale
metadata:
  version: "1.0.3"
  category: Storage
description: >-
  Inspects Filestore capacity and utilization on Google Cloud, evaluates storage
  scaling rules, and performs capacity autoscaling (scale UP for low free space
  or scale DOWN for cost optimization). Use when monitoring Filestore instance
  headroom, resizing instance shares, configuring automated growth/shrink
  thresholds (custom thresholds apply globally across projects in session memory),
  or preventing out-of-space outages. Don't use for Cloud Storage (GCS) buckets,
  Persistent Disk block storage, or NetApp Volumes.
---

# Filestore Autoscale

This skill enables agents to inspect, evaluate, and modify Filestore
instance capacities across Google Cloud projects based on configured
thresholds.

## Prerequisites / IAM Requirements

Before an agent or user can execute this skill, their runtime Service Account
must possess the following IAM roles on the target project(s):

-   **`roles/file.editor`** (Required for listing instances and triggering scale
    up/down updates)
-   **`roles/monitoring.viewer`** (Required for reading Cloud Monitoring
    capacity metrics `used_bytes`)
-   **`roles/mcp.toolUser`** (Required if utilizing backend Filestore MCP tools)

## Quick Start

1.  Ensure `gcloud` is installed. See
    [gcloud installation guide](https://cloud.google.com/sdk/docs/install) if
    needed.
2.  Enable essential APIs:

    ```bash
    gcloud services enable file.googleapis.com monitoring.googleapis.com --quiet
    ```
3.  Inspect fleet capacity and free space (see "Discovery & Read Operations"
    below).
4.  Evaluate against configured up/down capacity thresholds.
5.  Scale target instances and apply attribution tags.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Conceptual & Informational Queries (CRITICAL)

For purely conceptual, educational, or informational questions (e.g., "What are Filestore scaling limits?",
"Can Basic instances scale down?", "Explain Filestore Tiers"):

*   **Rule**: **Answer immediately using your pre-trained knowledge and the matrix below.**
*   **Constraint**: **Do not execute external tool calls or API requests** for basic knowledge questions.

## Handling "No-Command" Constraints (CRITICAL)

If the user prompt contains constraints like "Do not execute commands", "without executing", or "read-only":

*   **Rule**: **Strictly avoid calling the `run_command` tool** to execute any
    shell, `gcloud`, or code search (`cs`) commands (including read-only
    list/describe commands).
*   **Discovery**:
    1.  Whenever outputting or recommending a `gcloud` command (including when
        evaluating instance values provided directly in the user prompt), read
        [Usage Attribution](references/attribution.md) first so the command
        includes the required attribution prefix; do not search for additional
        unrelated files when instance tier, capacity, and utilization are
        already in the prompt.
    2.  Otherwise, check if Filestore MCP tools (`list_instances`,
        `get_instance`) are available and use them (these are API calls, not
        command executions).
    3.  If MCP tools are not available, check
        `references/instance-tiers-specs.md` for any mock instance definitions
        or project details matching the request. (Do NOT run repository-wide
        searches or attempt to read evaluation config files such as `EVAL.yaml`
        or `EVAL.txtpb` during evaluation runs as access is restricted).
    4.  If no data can be found, explain the required steps and formulas, and
        output the attributed `gcloud` terminal commands for the user to confirm
        and run, without executing them yourself.
*   **Mandatory User Confirmation Requirement**: Even when the user prompt asks not to execute commands or asks only for command syntax/recommendations, your response MUST STILL end with a clear question prompting the user for confirmation before executing any capacity resizing commands (e.g., *"Would you like me to proceed with scaling `[instance]` from [A] TiB to [B] TiB? Please confirm to execute."*).

## Tier & Capacity Limits Matrix

Filestore tiers enforce specific boundaries and behaviors. The skill must accept both modern UI names (`Basic`, `Zonal`, `Regional`) and legacy API enums interchangeably.

See `references/instance-tiers-specs.md` for the full Tier & Capacity Limits Matrix (Min/Max capacities, step increments).

**Critical Thresholds:**

- **Basic HDD / Basic SSD**: Can scale up, but **cannot scale down**.
- **Zonal / Regional**: Can scale down, but cannot shrink below their minimum
  floor (100 GiB for Regional Small Band, 1 TiB for Zonal Small Band, or 10 TiB
  for Large Band) AND cannot shrink below current `used_bytes`.

## Core Operational Workflow

### 1. Discovery & Read Operations

-   **Step 1 (Fleet Discovery)**: Call the MCP tool
    `list_instances(parent='projects/{project_id}/locations/-')` or CLI `gcloud
    filestore instances list --project={project_id}` to discover all Filestore
    instances in the target project. Read the `capacityGb` and `tier` directly
    from the instances returned.
-   **Step 2 (Single Bulk Utilization Metric Query)**: Immediately after
    discovering instances, query the Cloud Monitoring API for the
    `file.googleapis.com/nfs/server/used_bytes` metric across the entire project
    in a single request (see `references/monitoring-metrics.md` for
    runtime-specific options including GCP REST API, `gcloud`, `curl`, and MCP
    tools).

    **CRITICAL**: Make exactly ONE bulk metric request for the entire project.
    **NEVER emit multiple per-instance queries or loops.** Do NOT filter by zone
    or region.

-   **Step 3 (Metric Extraction & Calculation)**:

    -   Match each instance's short name (or `resource.labels.instance_name` /
        `metric.labels.instance_name`) in the returned `timeSeries` data to
        extract its latest `int64Value` bytes.
    -   If an instance is not listed in `timeSeries` or has no points, default
        its `used_bytes` to 0.
    -   Calculate `used_bytes_gb = used_bytes / (1024^3)`.
    -   Calculate `Free Space % = ((capacityGb - used_bytes_gb) / capacityGb) *
        100`.
    -   NEVER leave `Used Bytes` or `Free Space %` as "N/A". Populate actual
        numbers into the output summary table.

### 2. Autoscale Needed Matrix

The skill must categorize each evaluated instance into one of 5 definitive verdicts. On the initial analysis/fleet inspection run, the skill suggests the required scaling action with target capacity and update commands, and **prompts for user confirmation before executing any autoscale modifications**. State the value of the "Autoscale Needed" column clearly as one of the following:

-   **Yes (Scale Up)**: Triggered when free space percentage is below the
    scale-up safety threshold (< 15% free space remaining). The evaluation
    response MUST explicitly state that the current free space percentage is
    below the 15% scale-up safety threshold. Capacity must be increased by 10%
    (default) or step-size minimum, rounded to the tier's step increment (1 GiB
    for Regional Small Band [100 GiB-10,239 GiB] or Basic, 256 GiB for Zonal
    Small Band [1-9.75 TiB] or Enterprise [1-10 TiB],
    2.5 TiB for Large Band [10-100 TiB],
    as specified in `references/instance-tiers-specs.md`), not exceeding the
    maximum capacity. Always explicitly state the calculated target capacity in
    **both TiB and GiB** (for example, for a 1 TiB [1024 GiB] Basic instance
    increased by +10%, explicitly state `1.1 TiB` alongside its 1 GiB
    step-aligned equivalent `1126 GiB` / `1127 GiB`). Suggest target capacity,
    provide the attributed `gcloud`
    update command, and MUST conclude the response with a clear question
    prompting the user for confirmation to execute (e.g., *"Would you like me to
    proceed with scaling `[instance]` from [A] TiB to [B] TiB? Please confirm to
    execute."*).
-   **Yes (Scale Down)**: Triggered when free space exceeds the scale-down
    threshold (> 30% free space remaining) and the instance is eligible for
    downscaling (Zonal or Regional / Enterprise tiers). Apply the default step
    reduction of -10% of current capacity, aligned to the tier's step increment
    (1 GiB for Regional Small Band [100 GiB-10,239 GiB], 256 GiB for Zonal
    Small Band [1-9.75 TiB] or Enterprise [1-10 TiB],
    2.5 TiB for Large Band [10-100 TiB],
    as specified in `references/instance-tiers-specs.md`). For example, for a
    2 TiB (2048 GiB) Enterprise / Zonal Small Band instance, rounding to the
    256 GiB step yields a proposed target capacity of 1.75 TiB (1792 GiB, or
    1.8 TiB). The response MUST explicitly verify that the proposed target
    capacity (e.g. 1.75 TiB / 1792 GiB or 1.8 TiB) remains strictly above both
    the tier's minimum capacity floor (100 GiB for Regional Small Band, 1 TiB
    for Zonal Small Band / Enterprise, or 10 TiB for Large Band) and currently
    used space (e.g. 0.9 TiB). Do NOT reduce directly to the floor in a single
    step. Suggest target capacity, estimated cost savings, provide the
    attributed `gcloud` update command, and prompt the user for confirmation to
    execute.
-   **No (Healthy)**: Triggered when the instance's free space is within the
    optimal operating range (15% – 30%). No action required.
-   **No (At min capacity limit)**: Triggered when free space is > 30%, but the
    instance is already at the minimum allowed tier capacity floor (100 GiB for
    Regional Small Band, 1 TiB for Zonal Small Band / Enterprise, or 10 TiB for
    Large Band) or currently used space limit. No action can be taken.
-   **No (Tier cannot scale down)**: Triggered when free space is > 30%, but the
    instance is on a Basic tier (Basic HDD / Basic SSD) which does not support
    downscaling. The agent must explicitly inform the user that scale-down is
    not supported and suggest data migration instead. No action can be taken.

### Output Format

**Every status report, evaluation, or recommendation response MUST include a markdown table summarizing the evaluated instances.** Even if evaluating a single instance, format it as a table.
The table MUST contain the following columns:

*   `Instance`
*   `Service Tier`
*   `Provisioned Capacity`
*   `Used Bytes`
*   `Free Space %`
*   `Autoscale Needed` (MUST contain one of: `Yes (Scale Up)`, `Yes (Scale Down)`, `No (Healthy)`, `No (At min capacity limit)`, or `No (Tier cannot scale down)`)

Example standard output table:

```markdown
| Instance | Service Tier | Provisioned Capacity | Used Bytes | Free Space % | Autoscale Needed | Proposed Action |
|---|---|---|---|---|---|---|
| `[instance-name]` | REGIONAL | 2048 GiB | 900 GiB | 56.05% | Yes (Scale Down) | Scale down to 1792 GiB. `gcloud filestore instances update ...` |
```

### 3. Execution & Confirmation Workflow

1. **Analysis & Recommendation (First Run / Inspection)**:
   - Calculate step-aligned target capacity adhering to tier ceilings, floors, and basic scale-up only rules.
   - Present the summary table and proposed actions.
   - **MANDATORY USER CONFIRMATION PROMPT**: Whenever recommending target capacity or providing a `gcloud filestore instances update` command, your response MUST explicitly include a clear question asking the user to confirm execution before any modifications are made (e.g. *"Would you like me to proceed with scaling `[instance]` from [A] TiB to [B] TiB? Please confirm to execute."*) to prevent accidental billing spikes or capacity exhaustion.
   - **Do not execute autoscale commands without user confirmation.**
2. **Execution upon Confirmation**:
   - Once the user confirms (e.g., "Yes, proceed with scaling", "Scale instance X"), execute the attributed `gcloud filestore instances update` command on the confirmed instance(s).
3. **Fallback**:
   - If execution fails due to Prod mutation restrictions, output the failure reason and provide the user with the exact attributed `gcloud` command to run manually, reminding them to confirm before manual execution.

### Custom Thresholds

When the user configures or passes custom threshold values in prompts (e.g.
"Scale up if free space drops below 10% with a 20% step", or custom
max_threshold / up_increment):

1.  **Global Session Memory Confirmation**: The response MUST accept and
    acknowledge the custom thresholds and MUST explicitly confirm that custom
    thresholds apply globally across projects in session memory, explicitly
    mentioning the target project IDs evaluated or active in session memory to
    prevent accidental cross-project misconfiguration.
2.  **Configuration Summary**: The response MUST display the updated active
    configuration summary showing all active thresholds and step increments.
3.  **Preserve Overrides**: The response MUST NOT revert to default thresholds
    (15% / 10%) when custom overrides are provided.

## Reference Directory

For progressive disclosure of deeper topics, consult the `references/` directory:

- [Usage Attribution](references/attribution.md)
- [Instance Tiers & Specs](references/instance-tiers-specs.md)
- [Monitoring Metrics Formulas](references/monitoring-metrics.md)
- [Troubleshooting & Errors](references/troubleshooting-errors.md)
