---
name: agent-platform-prompt-management
description: >-
  Manages and orchestrates prompts in Agent Platform. Use when you need to create,
  list, retrieve, version, or delete managed prompts in Agent Platform. Don't use
  for model training, model deployment to endpoints, or managing non-Agent Platform
  prompts.
---

## Usage Guide

To use this skill effectively:
1. **Generate Code**: Provide the Python snippets below to the user to help them
manage prompts in Agent Platform.
2. **No File System Search**: Do not try to find Python files or scripts on the
file system for these operations.

## Phase 0: Environment Setup

**CRITICAL**: Before the user runs any of the Python snippets below, you MUST
advise them to ensure the environment is correctly initialized by following
these steps:

1. **Google Cloud Authentication**: Authenticate with your Google Cloud account
   and configure active Application Default Credentials (ADC) for Agent
   Platform access:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
2. **Virtual Environment**: Create and activate a dedicated virtual environment:
   ```bash
   python3 -m venv ~/prompt_agent_venv
   source ~/prompt_agent_venv/bin/activate
   ```
3. **Install Dependencies**: Install the required Agent Platform SDKs:
   ```bash
   pip install google-cloud-aiplatform google-genai
   ```
4. **Execution**: Advise the user that every time they execute a Python snippet, they must ensure this virtual environment is activated first.

> [!TIP] **Placeholder Parameter Replacement:** The Python scripts below use
> uppercase string placeholders (like `"PROJECT_ID"`, `"LOCATION_ID"`, and
> `"PROMPT_ID"`). You **MUST** dynamically replace these placeholders with the
> actual Project ID, Region, and Prompt ID values provided in the user's prompt
> (or discovered context) before generating or providing the scripts.

## 1. Managing Prompts via Agent Platform SDK

The SDK provides a high-level `Prompt` class in the preview module.

### Create a Prompt (Tier M)

Use when you need to create a new managed prompt in Agent Platform.

*   **Reference**: See [create.md](references/create.md) for detailed instructions and Python snippets.

### List Prompts (Tier R)

```python
from vertexai.preview import prompts

all_prompts = prompts.list()
for p in all_prompts:
    print(f"Name: {p.display_name}, ID: {p.name}")
```

### Retrieve and Use a Prompt (Tier R)

```python
from vertexai.preview import prompts

retrieved_prompt = prompts.get(prompt_id="projects/PROJECT_ID/locations/LOCATION_ID/prompts/PROMPT_ID")
# Versions are supported: prompts.get(prompt_id=..., version_id="2")

# Assemble with variables
assembled = retrieved_prompt.assemble(text="The quick brown fox...")
print(assembled)
```

### Delete a Prompt (Tier D)

**CRITICAL**: You must use the full resource name (e.g.,
`projects/PROJECT_ID/locations/LOCATION_ID/prompts/PROMPT_ID`) when deleting a
prompt. Do not pass just the numeric ID.

**Confirmation Required**: As a Tier D (Destructive) operation, the agent MUST
pause and request explicit, high-friction typed re-confirmation of the prompt
resource name from the user before generating or providing the deletion code.
The action is irreversible.

> [!IMPORTANT]
> **NEVER pre-emptively provide or execute any deletion code before receiving
> the user's response in a new turn.** You must never speculate or assume that
> confirmation will be given. Asking for confirmation and providing the code in
> a single parallel turn is a severe safety violation.

```python
from vertexai.preview import prompts

# Always use full resource name
resource_name = "projects/PROJECT_ID/locations/LOCATION_ID/prompts/PROMPT_ID"
prompts.delete(prompt_id=resource_name)
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
