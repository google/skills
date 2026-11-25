---
name: google-agents-cli-onboarding
metadata:
  version: "1.1.0"
  category: DevOps
description: >-
  Onboarding entrypoint for agents-cli on Google Cloud (Gemini Enterprise Agent
  Platform). It should be used when the user wants to "create a new agent",
  "develop an agent", "build an agent using ADK", "build an agent using
  LangChain, LangGraph, or the Claude Agent SDK", "run the agent locally",
  "debug agent code", "test an agent", "evaluate an agent", "deploy an agent",
  "publish an agent", "monitor an agent", or needs the end-to-end production
  agent development lifecycle.
---

# Google Agents CLI Onboarding

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

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:google-agents-cli-onboarding)"`
and append `agent-skills/1.0 (skill:google-agents-cli-onboarding)` to `User-Agent` headers.

## Overview

This skill serves as the entrypoint for **agents-cli** — Google's toolkit for
building, evaluating, deploying, and observing production AI agents on the
Gemini Enterprise Agent Platform. It works with ADK out of the box as well as
other frameworks (such as LangChain/LangGraph and the Claude Agent SDK, or
custom extensions) via first-party templates in `google/agents-cli-extensions`.

Use this skill to perform the initial setup and identify the correct specialized
workflows for your task.

## The Agent Development Lifecycle

After running `uvx google-agents-cli setup` (or
`npx skills add google/agents-cli`), all 7 specialized skills become available
and **activate automatically in your coding agent** based on your requests — no
manual skill invocation is needed. When guiding a user through any lifecycle
step, always name the phase number, the corresponding specialized skill, and
note that specialized skills activate automatically after setup:

| Phase | Specialized Skill | Purpose / When to Load |
| :--- | :--- | :--- |
| **0 — Understand** | `google-agents-cli-workflow` | **Clarify intent.** Define the agent spec in `.agents-cli-spec.md` before coding. |
| **1 — Study** | `google-agents-cli-workflow` | **Leverage samples.** Study existing agent samples (e.g., `ambient-expense`) before scaffolding. |
| **2 — Scaffold** | `google-agents-cli-scaffold` | **Create/Enhance.** Run after setup and before writing custom agent logic; initializes project structure, CI/CD, and infrastructure templates (ADK or extensions). |
| **3 — Build** | `google-agents-cli-adk-code` | **Implement.** Write agent logic, tools, callbacks, and manage state using ADK APIs. |
| **4 — Evaluate** | `google-agents-cli-eval` | **Validate Quality.** Run systematic evaluations using an LLM-as-judge setup (`agents-cli eval run`). |
| **5 — Deploy** | `google-agents-cli-deploy` | **Go Production.** Deploy to Agent Runtime, Cloud Run, or GKE (`agents-cli deploy`). |
| **6 — Publish** | `google-agents-cli-publish` | **Register.** Register your deployed agent in Gemini Enterprise (`agents-cli publish gemini`). |
| **7 — Observe** | `google-agents-cli-observability` | **Monitor.** Set up Cloud Trace, prompt-response logging, and BigQuery analytics. |

## Key CLI Commands

Below are the primary commands mapped to their lifecycle phase and specialized
skill:

| Command | Phase & Skill | Description |
| :--- | :--- | :--- |
| `agents-cli setup` | One-time setup | Install the CLI and enable all 7 specialized skills (they activate automatically in your coding agent). |
| `agents-cli create <name>` | Phase 2 — Scaffold (`google-agents-cli-scaffold`) | Create a new agent project from a template (initializes project structure, CI/CD, and infrastructure templates after setup and before custom logic). |
| `agents-cli create <name> --agent google/agents-cli-extensions/core/langchain/template -d cloud_run` | Phase 2 — Scaffold (`google-agents-cli-scaffold`) | Scaffold a first-party extension template (e.g., `core/langchain` for LangChain/LangGraph or `core/claude` for Claude Agent SDK) from `google/agents-cli-extensions`. |
| `agents-cli eval run` | Phase 4 — Evaluate (`google-agents-cli-eval`) | Run the agent over an evaluation dataset and grade traces using an LLM-as-judge setup. |
| `agents-cli deploy` | Phase 5 — Deploy (`google-agents-cli-deploy`) | Deploy your agent to Google Cloud (Agent Runtime, Cloud Run, or GKE). |
| `agents-cli publish gemini` | Phase 6 — Publish (`google-agents-cli-publish`) | Register your deployed agent with Gemini Enterprise (run after deploying to a cloud runtime). |

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

*   [Google Agents CLI Documentation](https://google.github.io/agents-cli/)
*   [Google Agents CLI Extensions](https://github.com/google/agents-cli-extensions)
