---
name: agent-platform-model-registry
metadata:
  version: "1.0.2"
  category: AiAndMachineLearning
description: >-
  Agent Platform Model Registry Management. Use when you need to upload, list,
  describe, update, or delete machine learning models (and their versions)
  in the Agent Platform Model Registry. Don't use for model training, model
  deployment to endpoints, or managing non-Agent Platform models.
---

# Agent Platform Model Registry Management

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` and append the
attribution suffix to `User-Agent` headers:

```text
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-model-registry)"
User-Agent: <existing_user_agent> agent-skills/1.0 (skill:agent-platform-model-registry)
```

## Overview

This skill provides instructions for managing machine learning models in the
Agent Platform Model Registry. It covers listing models, describing model
details, uploading new models or versions, updating metadata, and deleting
models.

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands on behalf of the user, you MUST adhere to the
following safety tiers based on the action requested:

1.  **Tier R: Read-only (`list`, `describe`, `get`)**
    *   No confirmation needed. Execute immediately to gather information.
2.  **Tier M: Mutating & Reversible (`upload`, `update`)**
    *   Requires **interactive confirmation** with 'Yes'/'No' options. The
        confirmation prompt MUST contain the exact, literal command string with
        all required flags (e.g. `--region=us-central1`, `--project=...`,
        `--display-name="..."`) — natural-language paraphrases are NOT
        sufficient.
    *   **Same-turn restriction**: NEVER execute the command in the same turn as
        receiving the request or presenting the confirmation prompt! In Turn 1,
        you MUST ONLY present the interactive confirmation card with the exact,
        literal command string. Stop and wait for the user's reply; only execute
        in the subsequent turn after explicit 'Yes' / approval. Executing
        `upload` or `update` in Turn 1 without prior confirmation is strictly
        prohibited.
    *   **Mid-flow parameter changes / rejection**: If the user rejects the
        prompt or changes any parameters (e.g., display name, description,
        parent model), do NOT execute the old command. Adapt immediately and
        present a NEW confirmation prompt with the updated literal command and
        wait for approval.
3.  **Tier D: Destructive & Irreversible (`delete`)**
    *   Requires **explicit typed confirmation** (e.g. "I confirm" or "Yes,
        delete it"). Ask for confirmation IMMEDIATELY — before any pre-flight
        checks (don't check if the model is deployed to endpoints first).
    *   **Same-turn restriction**: NEVER execute in the same turn as asking for
        typed confirmation. Wait for the user to reply in a new turn.
    *   **Mid-flow target changes**: If the user changes their mind (e.g.,
        "delete the second model instead"), do NOT delete the first model.
        Present a fresh typed confirmation prompt for the newly selected model
        ID and wait for approval.
4.  **Cost Estimation**: Model Registry operations manage catalog metadata and
    stored model artifacts without provisioning serving compute or endpoints. Do
    NOT call the `estimate_cost` tool for Model Registry actions, as
    `estimate_cost` is designed for serving infrastructure (endpoints/batch
    prediction) and will return an error if called for registry operations. If
    including cost in the preview card, state that Model Registry operations
    incur no serving compute charges ($0.00 compute charges; standard Cloud
    Storage pricing applies to model artifacts).

## Phase 0: Environment Setup & Parameter Resolution

**CRITICAL**: Before running any commands, verify that all necessary parameters
are known:

1.  **Missing Region or Project**: Follow the base environment grounding policy:
    if a session location or project is already set from prior turns, reuse it
    without re-asking. If missing from both prompt and session context, at most
    one direct lookup is permitted (e.g. `gcloud config get project` or `gcloud
    config get compute/region`). If the user refers to "my project" or their
    configured environment and `compute/region` is `(unset)`, fall back to
    `us-central1` per base environment grounding; otherwise, if the region is
    still unresolved, pause and explicitly ask the user for the missing
    parameter before executing regional commands.
2.  **Missing Model ID**: If the user asks to update or describe a model without
    providing the model ID, pause and ask the user for the model ID, or offer to
    list models first to help them find it.
3.  **Placeholder Substitution**: If the user's requested display name contains
    a placeholder token (e.g., `<unique-suffix>`, `[suffix]`, or `<timestamp>`),
    generate a short unique alphanumeric string or timestamp and substitute it
    cleanly. Never pass unexpanded literal placeholder tokens to the API.
4.  **Region and Project Flags**: Always pass `--region=$LOCATION_ID` and
    `--project=$PROJECT_ID` explicitly on all `gcloud ai models` commands. Do
    NOT use `global`.

## 1. Listing Models (Tier R)

Use this command to discover existing models in the registry and retrieve their
numeric IDs. No confirmation is required.

Always pass `--limit`. A project can hold thousands of models, and an unbounded
list pages through every one of them, which can take over a minute and return
hundreds of KB of output. Results come back most recently updated first, so
`--limit=50` returns the newest models in a few seconds.

```bash
gcloud ai models list \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID \
    --limit=50
```

*   Keep `--limit=50` when the user asks to list "all" models, and say the reply
    shows the 50 most recently updated models. Do NOT page through the whole
    registry (with gcloud or `Model.list()`) unless the user asks for a count or
    the complete inventory; offer to look up a specific model by display name
    instead.
*   If the user pushes back and asks for the complete inventory, drop `--limit`
    and print one compact line per model with
    `--format="value(name.basename(),displayName)"`. Warn that this can take a
    minute or more in a large project.
*   If the user asks how many models there are, count the IDs without printing
    the list. There is no count API, so this still pages through every model
    (about a minute per 1,500 models); tell the user it may take a while. Do not
    run a `--limit` list first.

    ```bash
    gcloud ai models list \
        --region=$LOCATION_ID \
        --project=$PROJECT_ID \
        --format="value(name)" | wc -l
    ```
*   Do NOT use `--filter` or `--sort-by` to narrow the list. gcloud applies both
    client-side after fetching every page, so they are as slow as an unbounded
    list.
*   To find a model by display name (e.g. to confirm an upload or deletion),
    filter on the server with the Python SDK:

```bash
python3 - <<'PY'
from google.cloud import aiplatform

aiplatform.init(project='<PROJECT_ID>', location='<LOCATION_ID>')
for m in aiplatform.Model.list(filter='display_name="<DISPLAY_NAME>"'):
    print(m.name, m.display_name, m.create_time)
PY
```

## 2. Describing a Model (Tier R)

Retrieve the full metadata for a specific model or version. No confirmation is
required.

```bash
gcloud ai models describe $MODEL_ID \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID
```

To target a specific version:

```bash
gcloud ai models describe ${MODEL_ID}@${VERSION_ID} \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID
```

## 3. Uploading a Model (Tier M)

Register a new model or a new version of an existing model. This is a
long-running operation. **Action requires an inline confirmation card before
proceeding.**

### Example: Uploading a Custom Model

```bash
gcloud ai models upload \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID \
    --display-name="<DISPLAY_NAME>" \
    --container-image-uri="<CONTAINER_IMAGE_URI>" \
    [--artifact-uri="<ARTIFACT_URI>"]
```

> [!IMPORTANT]
>
> This is a Tier M operation — see [Safety & Confirmation Tiers] above.
>
> -   If the user specifies "with no artifact URI", omit `--artifact-uri`.
> -   If registering a new version of an existing model, include
>     `--parent-model=$PARENT_MODEL_ID`.
> -   Substitute `<DISPLAY_NAME>` with the exact name requested by the user.

## 4. Updating a Model (Tier M)

Update metadata fields like display name or description. Note that `gcloud ai
models` does NOT have an `update` subcommand. Instead, model metadata updates
MUST be executed using the Vertex AI Python SDK
(`google.cloud.aiplatform.Model`).

**Action requires an inline confirmation card containing the exact script before
proceeding.**

```bash
python3 -c "
from google.cloud import aiplatform

aiplatform.init(project='$PROJECT_ID', location='$LOCATION_ID')
model = aiplatform.Model('$MODEL_ID')
model.update(display_name='<NEW_DISPLAY_NAME>', description='<NEW_DESCRIPTION>')
print(f'Successfully updated model: {model.resource_name}')
"
```

> [!IMPORTANT]
>
> This is a Tier M operation — see [Safety & Confirmation Tiers] above.
>
> -   If only updating the display name, pass
>     `model.update(display_name='<NEW_DISPLAY_NAME>')`.
> -   If only updating the description, pass
>     `model.update(description='<NEW_DESCRIPTION>')`.
> -   The confirmation card MUST display the exact python command snippet above.
>     NEVER execute in Turn 1; wait for explicit user approval.

## 5. Deleting a Model (Tier D)

Permanently delete a Model and all its versions. **Action requires explicit
typed confirmation before proceeding.**

```bash
gcloud ai models delete $MODEL_ID \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID
```

> [!WARNING]
>
> This operation is irreversible. All model versions must be undeployed from all
> Endpoints before deletion.

## 6. Searching Publisher Models (Tier R)

Before generating interactive model details, you MUST verify the `model_id` by
searching Model Garden Publisher Models. No confirmation is required.

Use the `gcloud ai` CLI to search for matching publisher models.

```bash
gcloud ai model-garden models list --model-filter="<model_name_or_query>" --full-resource-name --format=json
```

This will return a list of matching models. Extract the exact `name` field from
the result (e.g., `publishers/google/models/gemma2` or
`publishers/qwen/models/qwen3-coder`) to use as the verified `model_id`.
