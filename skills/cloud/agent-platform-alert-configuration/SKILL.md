---
name: agent-platform-alert-configuration
metadata:
  category: AiAndMachineLearning
description: >-
  Configures best-practice alerting policies for AI agents using OpenTelemetry
  (OTel) metrics. Use when analyzing, writing, or deploying alerting policies
  to monitor agent latency, error rates, token usage, and quality metrics.
  NOTE: Reliability, Cost, Safety, and Security alerts use generic OTel metrics
  and work across runtimes (e.g., Cloud Run, Vertex AI). Quality alerts rely
  on Vertex AI Online Monitors and are strictly bound to Vertex AI deployments.
allowed-tools: terraform gcloud python
---

# Agent Platform Alert Configuration

## Critical Steps

### 1. Safety & Confirmation Tiers (CRITICAL)

Before executing any commands or writing configurations on behalf of the user,
you MUST adhere to the following safety tiers based on the action requested:

1.  **Tier R: Read-only (`check_telemetry.py` / `gather_agent_info.py`)**
    *   **Rule**: No confirmation needed. You may execute these scripts
        immediately to inspect telemetry status or gather agent configuration
        details.
2.  **Tier B: Billing & Resource Creation (`create_online_monitor.py` /
    provisioning)**
    *   **Rule**: **Explicit User Confirmation Required**. These actions incur
        additional billing charges and create cloud resources. The agent MUST
        ALWAYS warn the user explicitly about the potential extra billing costs
        of BOTH the Online Monitor (specifically mentioning **LLM evaluations**)
        and Telemetry (specifically mentioning **Cloud Trace/Logging export**).
        You MUST STOP and ask for explicit approval before proceeding with
        provisioning or providing setup commands.

### 2. Prerequisites & Dependencies

#### Agent Telemetry

*   **Disclaimer**: For Reliability, Cost, Safety, and Security alerts to
    function, the underlying agent MUST be instrumented to emit OpenTelemetry
    (OTel) metrics. If the agent does not emit these metrics, the alerting
    policies will have no data stream to evaluate.

#### Python Environment

Before executing any python script in this skill you MUST install the required
dependencies in your environment. Run this command first:

```bash
pip install -r scripts/requirements.txt
```

### 3. Input Assumptions

*   **Explicit Project Adherence**: You must ONLY configure alerts, query
    telemetry, or interact with the Google Cloud Project(s) explicitly provided
    by the user in the prompt. Do NOT assume or use other projects from your
    environment or history unless the user explicitly directs you to do so.
*   **Sequential File Transformations**: If the user explicitly asks to copy a
    file and then modify it, you MUST perform these actions sequentially (copy
    first, then modify) rather than writing the final content directly.

### 4. Execution Steps

1.  **Mandatory Prerequisite Execution Protocol (SEQUENTIAL)**: Before
    generating or writing ANY configuration, you MUST execute these steps in
    order:
    1.  **Step 1: Streamlined Discovery (Mandatory)**: Run
        `gather_agent_info.py` to automatically identify agent runtime, check
        telemetry, metric scopes, linked datasets, and more. This script covers
        most of the manual checks listed in subsequent steps.
        *   Command: `python3 scripts/gather_agent_info.py --project-id
            {project_id} --agent-name {agent_name}`
        *   **Note**: If this script **fails**, returns **partial data**, or
            doesn't produce everything you need, you MUST satisfy requirements
            by running the manual fallback steps listed in Step 2 and then
            perform Step 3 below. If Step 1 succeeds and provides all info,
            **SKIP** to Step 3 (Pre-existing Policies Check).
    2.  **Step 2: Metric Scope Check (Fallback)**: Run this ONLY if Step 1
        failed to determine the metric scope.
        *   **Action A (CLI)**: Run `gcloud beta monitoring metrics-scopes list
            projects/{project_id}`. If a scoping project is returned, you MUST
            deploy policies there.
        *   **Action B (Code Scan)**: Search Terraform configurations for
            `google_monitoring_monitored_project` resources to extract the
            scoping project.
        *   **Action C (Fallback)**: If ambiguous, ASK the user: "Are you using
            a multi-project Cloud Monitoring Metric Scope? If so, what is the
            scoping project ID?"
    3.  **Step 3: Pre-existing Policies Check**: Avoid duplicates.
        *   **Action**: Scan the target directory to see if aggregated policies
            already exist targeting the same metrics (grouped by
            `reasoning_engine_id` or `gen_ai_agent_name`). Use
            `scan_duplicates.py` to verify.
2.  **Alert Policy Type Resource Files**: You MUST list and read files under
    `references/` with names ending in `_alert_policies.md` to learn how to
    configure alert policies based on type. By default you should configure all
    of the following alert types UNLESS the user requests to generate explicit
    alert policies and/or types. Follow their tables of content to help you find
    the reference sections you need to read:

    Alert Type      | Reference File
    :-------------- | :-------------
    **Reliability** | [reliability_alert_policies.md](references/reliability_alert_policies.md)
    **Quality**     | [quality_alert_policies.md](references/quality_alert_policies.md)
    **Cost**        | [cost_alert_policies.md](references/cost_alert_policies.md)
    **Safety**      | [safety_alert_policies.md](references/safety_alert_policies.md)
    **Security**    | [security_alert_policies.md](references/security_alert_policies.md)

### 5. Outputs & Formats

*   **Always configure the supported alerting policies** for the target agent:
    *   **For Reliability Monitoring**: You MUST configure exactly five alerting
        policies:
        1.  **Latency** (anomaly monitoring)
        2.  **Error Rate - Fast Burn SLO** (1-Hour Window)
        3.  **Error Rate - Slow Burn SLO** (3-Day Window)
        4.  **Model Call Error Rate** (SQL-based Log Analytics Alerting)
        5.  **Tool Call Error Rate** (SQL-based Log Analytics Alerting)
    *   **For Quality Monitoring**: You MUST configure exactly three alerting
        policies (Requires Vertex AI Online Monitors):
        1.  **Final Response Quality**
        2.  **Tool Use Quality**
        3.  **Hallucination**
    *   **For Cost Monitoring**: You MUST configure exactly one cost alerting
        policy:
        1.  **Rapid Token Burn Rate** (anomaly monitoring)
    *   **For Safety Monitoring**: You MUST configure exactly one safety
        alerting policy:
        1.  **High Model Armor Safety Policy Trigger Rate** (SQL-based Log
            Analytics Alerting)
    *   **For Security Monitoring**: You MUST configure exactly one security
        alerting policy:
        1.  **High IAM Permission Denied Trigger Rate** (SQL-based Log Analytics
            Alerting)
*   **Terraform Only**: Write the generated observability configuration ONLY as
    Terraform (`.tf`) files (e.g., `alerts.tf`, `variables.tf`).
    -   You **ONLY** need to install Terraform if you're asked to deploy the
        alerts AND there is no valid Terraform install. SQL-based alerting using
        `condition_sql` requires the provider version **>= 6.0.0** (or late 5.x
        versions supporting the feature).
    -   If you are **NOT** asked to deploy the alerts you do not need to install
        terraform.
*   **Dynamic Multi-Resource Alerting (No Single-Resource Pinning)**: You MUST
    NOT hardcode specific agent IDs or resource name filters (e.g.,
    `{gen_ai_agent_name="{agent_name}"}` or
    `metric.labels.agent_resource_name="{agent_name}"`) in alerting conditions
    unless explicitly requested (e.g., "ONLY for this agent"). Merely mentioning
    a specific agent name or ID in the request does NOT constitute an explicit
    request to pin/filter; you MUST still default to dynamic grouping to cover
    all agents. To cover all active agents in the project dynamically:
    *   **For Reliability Metrics using PromQL**: ALWAYS use grouping
        aggregations. Group by `gen_ai_agent_name` (e.g., `by
        (gen_ai_agent_name)`). Avoid filtering to a single ID/Name unless
        requested.
    *   **For Quality Metrics using Standard Threshold Filters**: Omit the
        `agent_resource_name` filter entirely. Configure the condition filter to
        only target the monitored resource type
        (`aiplatform.googleapis.com/OnlineEvaluator`) and metric type
        (`aiplatform.googleapis.com/online_evaluator/scores`) globally for the
        project.
    *   **For Downstream Calls using SQL**: Omit the `ENDS_WITH` filter
        targeting a specific agent name. Instead, extract the agent identifier
        (e.g., `JSON_VALUE(resource.attributes, '$."cloud.resource_id"')`) and
        add it to the `GROUP BY` clause alongside the model or tool name.
*   **Directory Inference**: Prefer the path explicitly provided by the user (if
    any). Otherwise, deploy configuration files to target Terraform or SRE
    folders (e.g. `monitoring/`, `ops/`, `sre/`). Use tools to locate where
    alert policies or state pointers exist in the project, rather than blindly
    writing to the root.
*   **Notification Channels**: By default, never configure any notification
    channels without user input. If the user explicitly provides a notification
    channel in their prompt, configure the alerts to use it. If no notification
    channel is provided, you MUST explicitly ask the user in your final response
    if they would like to configure notification channels. **This is a mandatory
    question and you MUST NOT omit it from your response.** **IMPORTANT** Do NOT
    make assumptions about notification channels. If you search the codebase for
    a notification channel you must ALWAYS confirm with the user before using
    it.
*   **Plain English Response**: You MUST include a plain English explanation for
    what the alerts do in your response. This must explain in plain English what
    the alert measures, how the algorithm works, and what a trigger indicates.

### 6. Output Verification

*   **Background Task Cleanup**: You MUST check the status of all background
    tasks that you spawn. Before completing your execution and returning your
    final response, you MUST terminate or kill any active or hanging background
    tasks (using the `manage_task` tool with action `kill`).
*   **Validate Configuration**: Run the **Config Linting** tool to make sure all
    the output files are written with the correct grammar and structure. See
    details about the tool in the `Tooling Scripts` section below.

## Tooling Scripts

Use the following scripts to discover agents, gather configuration details,
resolve duplicates, and validate configs:

1.  **Agent Information Gathering**: Streamlines discovery, environment auditing
    (Metric Scopes, BQ Datasets, Notification Channels), table derivations (Log
    & Trace), and Online Evaluator checks.
    *   Command: `python3 scripts/gather_agent_info.py --project-id {project_id}
        --agent-name {agent_name}`
2.  **Duplicate Check & Merge**: Checks for pre-existing alerts in the target
    folder to ensure changes are merged in-place rather than appended:
    *   Command: `python3 scripts/scan_duplicates.py {target_tf_dir}
        --engine-var '${var.gen_ai_agent_name}'`
3.  **Config Linting**: Validates PromQL grammar, matching engine labels, and
    HCL structure:
    *   Command: `python3 scripts/lint_syntax.py {path_to_tf_file}`
    *   **Self-Correction Loop**: If validation fails (exits non-zero or outputs
        errors), you MUST read the command output, locate the line/file
        containing the lint error, analyze the PromQL syntax or Terraform HCL
        issue, apply adjustments in-place, and re-run the `lint_syntax.py`
        validation. Repeat this loop until the validation script passes
        successfully.

## Gotchas & Behavioral Corrections

*   **Raw Error Boundaries**: Explain that raw error counts or absolute failed
    request count boundaries do not scale under changing traffic throughput.
    Recommend ratio-based error rate alerts instead.
*   **Safe Threshold Modulation E2E Validation**: When verifying a dynamic
    metric threshold policy end-to-end, do NOT attempt to force real platform
    errors. Instead, deploy the alert policy with standard safe bounds (Z-score
    multiplier > 15), then temporarily update standard deviation Z-score limits
    to a negative value (e.g. > -3) to trigger/verify the "Firing" state before
    reverting. Always get confirmation before taking this action proactively.
*   **Expected Script Failures**:
    *   `scan_duplicates.py` exiting with code 1: Parse the JSON
        output for duplicate resource targets. Perform in-place upgrade edits,
        then re-check until it passes with 0.
    *   **Avoid Redundant Discovery Calls**: If `gather_agent_info.py`
        successfully returns the Trace or Log table names (or writes them to
        variables file), do NOT redundantly call
        `list_trace_scope_table_names.py` or `list_log_scope_table_names.py`.
        These scripts are run internally by `gather_agent_info.py` and are
        provided as external Fallbacks only.
    *   **Script Execution Failures & Self-Correction**: If the execution of
        utility scripts (such as `gather_agent_info.py`, `check_telemetry.py`,
        `create_online_monitor.py`, `analyze_traffic.py`,
        `list_log_scope_table_names.py`, or `list_trace_scope_table_names.py`)
        fails unexpectedly, you MUST read and inspect the stdout/stderr logs or
        error output. Analyze the error message and attempt to dynamically
        correct parameters and retry execution before escalating or
        falling back to manual plans. Consult the relevant domain-specific
        reference file for detailed troubleshooting steps for specific scripts.
*   **Distribution Metric Aligner Constraint**: Standard `ALIGN_MEAN` cannot be
    applied to `DELTA` distribution metrics like `online_evaluator/scores`. You
    MUST use percentile-based aligners (like `ALIGN_PERCENTILE_50`) to reduce
    the score distribution into a comparable numeric stream.
*   **HCL Heredoc Interpolation**: When referencing Terraform variables inside
    PromQL or SQL queries (which are defined as strings), you MUST use the
    ${var.variable_name} syntax. Bare references like var.variable_name will
    fail at deployment time.
*   **Avoid Recursive Directory Operations**: You MUST NOT run recursive listing
    or search commands (such as `ls -R`, `find .`, or raw recursive `grep`) from
    the repository root if it contains a very large number of files, as this
    will freeze your session. Always target specific subdirectories.

## Supporting Links

*   [Continuous evaluation with online monitors](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-online)
*   [Agent Platform Quality Metrics](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/rubric-metric-details)
*   [Google Cloud Alerting Policies Guide](https://cloud.google.com/monitoring/alerts)
*   [Google Cloud Monitoring PromQL Documentation](https://cloud.google.com/monitoring/promql)
