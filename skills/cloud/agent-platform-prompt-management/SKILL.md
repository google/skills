---
name: agent-platform-prompt-management
metadata:
  category: AiAndMachineLearning
description: >-
  Manages and orchestrates prompts in Agent Platform. Use when you need to create,
  list, retrieve, version, or delete managed prompts in Agent Platform. Don't use
  for model training, model deployment to endpoints, or managing non-Agent Platform
  prompts.
---

## Usage Guide

To use this skill effectively:

1.  **Generate Code**: Provide the Python snippets below to the user to help
    them manage prompts in Agent Platform.

2.  **No File System Search**: Do not try to find Python files or scripts on the
    file system for these operations.

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands or scripts on behalf of the user, you must adhere
to the following safety tiers based on the action requested, to prevent
accidental mutation or permanent deletion of prompt resources:

1.  **Tier R: Read-only (`list`, `get`)**
    *   No confirmation needed. Execute immediately to gather information.
2.  **Tier M: Mutating & Reversible (`create`)**

    *   Requires **interactive confirmation** with 'Yes'/'No' options before
        executing prompt creation, to prevent unintended resource proliferation
        or misconfiguration. The confirmation prompt must clearly explain the
        proposed prompt creation and its key parameters (e.g., display name,
        template text, target model). Natural-language paraphrases without
        specifying the parameters are not sufficient.
    *   **Same-turn restriction**: Do not execute the creation code in the same
        turn as presenting the confirmation prompt. Stop and wait for the user's
        reply; only execute after explicit 'Yes' / approval.
    *   **Gold Standard Example**:

        > I will create a prompt in Agent Platform with the following
        > parameters. Please confirm this information before I proceed:
        >
        > *   **Display Name**: `Customer Support Greeting`
        > *   **Target Model**: `gemini-2.5-pro`
        > *   **Template Text**: "Hello {{user_name}}, how can I help..."
        >
        > Do you confirm? [Yes/No]

3.  **Tier D: Destructive & Irreversible (`delete`)**

    *   Requires **explicit typed confirmation** (e.g. "I confirm" or "Yes,
        delete it") before executing prompt deletion, to prevent accidental
        permanent loss of production prompt assets. Ask for confirmation before
        any pre-flight checks.
    *   **Same-turn restriction**: NEVER execute in the same turn as asking for
        typed confirmation. Wait for the user to reply in a new turn.
    *   **Gold Standard Example**:

        > I will permanently delete the following prompt from Agent Platform.
        > This action is irreversible. Please explicitly type your confirmation
        > (e.g., "I confirm") before I proceed:
        >
        > *   **Prompt ID**: `prompt_12345abc`
        > *   **Display Name**: `Legacy Outdated Prompt`
        >
        > Please type your confirmation to proceed.

## Phase 0: Environment Setup

**CRITICAL**: Before the user runs any of the Python snippets below, you MUST
advise them to ensure the environment is correctly initialized by following
these steps:

1.  **Google Cloud Authentication**: Authenticate with your Google Cloud account
    and configure active Application Default Credentials (ADC) for Agent
    Platform access:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

2.  **Python Dependencies**: This skill needs `google-cloud-aiplatform` and
    `google-genai`. Do **not** create a virtual environment — it starts empty
    and hides packages the environment already provides, forcing a redundant
    install. Probe, and install only what is missing:

    ```bash
    python3 -c "import vertexai, google.genai" \
      || pip install google-cloud-aiplatform google-genai
    ```

3.  **Execution**: Run Python snippets with a plain `python3`. There is no
    environment to activate first.

> [!TIP]
>
> **Placeholder Parameter Replacement:** The Python scripts below use uppercase
> string placeholders (like `"PROJECT_ID"`, `"LOCATION_ID"`, and `"PROMPT_ID"`).
> You **MUST** dynamically replace these placeholders with the actual Project
> ID, Region, and Prompt ID values provided in the user's prompt (or discovered
> context) before generating or providing the scripts.

## 1. Managing Prompts via Agent Platform SDK

The SDK provides a high-level `Prompt` class in the preview module.

### Create a Prompt (Tier M)

Use when you need to create a new managed prompt in Agent Platform.

*   **Reference**: See [create.md](references/create.md) for detailed
    instructions and Python snippets.

### List Prompts (Tier R)

```python
import vertexai
from vertexai.preview import prompts

vertexai.init(project="PROJECT_ID", location="LOCATION_ID")

all_prompts = prompts.list()
for p in all_prompts:
    print(f"Name: {p.display_name}, ID: {p.prompt_id}")
```

### Retrieve and Use a Prompt (Tier R)

```python
import vertexai
from vertexai.preview import prompts

vertexai.init(project="PROJECT_ID", location="LOCATION_ID")

retrieved_prompt = prompts.get(prompt_id="PROMPT_ID")
# Versions are supported: prompts.get(prompt_id="PROMPT_ID", version_id="2")

# Assemble with variables (kwargs must match template variable names)
assembled = retrieved_prompt.assemble_contents(text="The quick brown fox...")
print(assembled)
```

### Delete a Prompt (Tier D)

**CRITICAL**: You must pass the numeric prompt ID (e.g.,
`"1234567890123456789"`) to `prompts.delete()`. The SDK constructs the full
resource path internally using the project and location from `vertexai.init()`.

**Confirmation Required**: As a Tier D (Destructive) operation, the agent MUST
pause and request explicit, high-friction typed re-confirmation of the prompt ID
from the user before generating or providing the deletion code. The action is
irreversible.

> [!IMPORTANT]
>
> **NEVER pre-emptively provide or execute any deletion code before receiving
> the user's response in a new turn.** You must never speculate or assume that
> confirmation will be given. Asking for confirmation and providing the code in
> a single parallel turn is a severe safety violation.

```python
import vertexai
from vertexai.preview import prompts

vertexai.init(project="PROJECT_ID", location="LOCATION_ID")

prompts.delete(prompt_id="PROMPT_ID")
```

## 2. Best Practices

-   **Idempotency**:
    *   **Tier R** (List, Get): Inherently idempotent.
    *   **Tier D** (Delete): Re-running a delete on a non-existent or already
        deleted resource returns NOT_FOUND. Treat this as success.
-   **Placeholders**: Use the standard placeholder syntax (variable name
    enclosed in double curly braces) in your prompt templates.
-   **Versioning**: Always tag or record version IDs when making updates to
    production prompts.
-   **Model Reference**: Specify the target model ID (e.g., `gemini-2.5-pro`)
    when creating the prompt to ensure consistency.
-   **Underlying Schema**: When using the Dataset API, always use the correct
    `metadata_schema_uri` and nested `metadata` structure to ensure the prompt
    is recognized by Agent Platform Studio and the Prompts SDK.
