---
name: google-agents-cli-onboarding
description: >-
  Onboarding entrypoint for agents-cli in Agent Platform. It should be used
  when the user wants to "create a new agent", "develop an agent", "build an agent using ADK",
  "run the agent locally", "debug agent code", "test an agent", "evaluate an agent",
  "deploy an agent", "publish an agent", "monitor an agent", or needs the ADK (Agent Development Kit)
  development lifecycle.
---

> [!TIP] **One-Time Setup**: To install the CLI and enable all 7 specialized
> development skills in your coding agent, run the setup command:
>
> ```bash
> uvx google-agents-cli setup
> ```
>
> Alternatively, to install only the expert skills and let the agent handle
> execution:
>
> ```bash
> npx skills add google/agents-cli
> ```

## Overview

This skill serves as the entrypoint for **agents-cli** — Google's toolkit for
building, evaluating, and deploying AI agents on the Gemini Enterprise Agent
Platform.

Use this skill to perform the initial setup and identify the correct specialized
workflows for your task.

## The ADK Development Lifecycle

After running the setup, the following specialized skills become available and
will activate automatically based on your requests. Use this table to identify
which skill to load for your current phase:

| Phase            | Specialized Skill                 | Purpose / When to     |
:                  :                                   : Load                  :
| :--------------- | :-------------------------------- | :-------------------- |
| **0 —            | `google-agents-cli-workflow`      | **Clarify intent.**   |
: Understand**     :                                   : Define the agent spec :
:                  :                                   : in                    :
:                  :                                   : `.agents-cli-spec.md` :
:                  :                                   : before coding.        :
| **1 — Study**    | `google-agents-cli-workflow`      | **Leverage samples.** |
:                  :                                   : Study existing ADK    :
:                  :                                   : samples (e.g.,        :
:                  :                                   : `ambient-expense`)    :
:                  :                                   : before scaffolding.   :
| **2 — Scaffold** | `google-agents-cli-scaffold`      | **Create/Enhance.**   |
:                  :                                   : Initialize the        :
:                  :                                   : project structure,    :
:                  :                                   : CI/CD, and            :
:                  :                                   : infrastructure        :
:                  :                                   : templates.            :
| **3 — Build**    | `google-agents-cli-adk-code`      | **Implement.** Write  |
:                  :                                   : agent logic, tools,   :
:                  :                                   : callbacks, and manage :
:                  :                                   : state using ADK APIs. :
| **4 — Evaluate** | `google-agents-cli-eval`          | **Validate Quality.** |
:                  :                                   : Run systematic        :
:                  :                                   : evaluations           :
:                  :                                   : (LLM-as-judge).       :
| **5 — Deploy**   | `google-agents-cli-deploy`        | **Go Production.**    |
:                  :                                   : Deploy to Agent       :
:                  :                                   : Runtime (Vertex AI),  :
:                  :                                   : Cloud Run, or GKE.    :
| **6 — Publish**  | `google-agents-cli-publish`       | **Register.** Make    |
:                  :                                   : your agent available  :
:                  :                                   : as a tool in Gemini   :
:                  :                                   : Enterprise.           :
| **7 — Observe**  | `google-agents-cli-observability` | **Monitor.** Set up   |
:                  :                                   : Cloud Trace,          :
:                  :                                   : prompt-response       :
:                  :                                   : logging, and BigQuery :
:                  :                                   : analytics.            :

## Key CLI Commands

Below are the primary commands you will use throughout the development
lifecycle:

| Command                      | Description                                   |
| :--------------------------- | :-------------------------------------------- |
| `agents-cli setup`           | Install the CLI and configure skills in your  |
:                              : coding agent.                                 :
| `agents-cli scaffold <name>` | Create a new agent project from a template.   |
| `agents-cli eval run`        | Run the agent and grade the traces in a single|
:                              : step (generate + grade).                      :
| `agents-cli deploy`          | Deploy your agent to Google Cloud (Agent      |
:                              : Runtime, Cloud Run, GKE).                     :
| `agents-cli publish gemini-enterprise` | Register your deployed agent with Gemini      |
:                                       : Enterprise.                                   :

*For the full list of available commands and global options, run `agents-cli
--help`.*

## Next Steps

Follow this sequence to initiate the development workflow:

1.  **Execute Setup:** Run the `uvx` or `npx` command in the `[!TIP]` box above
    to install the CLI and enable the specialized skills in your environment.
2.  **Verify Installation:** Run `agents-cli info` to confirm the installation
    and view the active project configuration.
3.  **Initiate Phase 0:** Ask the user for their core requirements (agent
    purpose, external tools, deployment target) and document them in
    `.agents-cli-spec.md` before writing any code.

## Reporting Issues

Report bugs or improvements at [Google Agents CLI Issues](https://github.com/google/agents-cli/issues).

## Supporting Links

*   [Google Agents CLI Documentation](https://github.com/google/agents-cli/tree/main/docs/src)
