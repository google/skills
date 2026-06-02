---
name: agent-platform-model-registry
description: >-
  Agent Platform Model Registry Management. Use when you need to upload, list,
  describe, update, or delete machine learning models (and their versions)
  in the Agent Platform Model Registry. Don't use for model training, model
  deployment to endpoints, or managing non-Agent Platform models.
---

# Agent Platform Model Registry Management

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
        confirmation prompt MUST contain the exact, literal command string
        with all required flags (e.g. `--region=us-central1`,
        `--display-name="..."`) — natural-language paraphrases are NOT
        sufficient.
    *   **Same-turn restriction**: NEVER execute the command in the same turn
        as presenting the confirmation prompt. Stop and wait for the user's
        reply; only execute after explicit 'Yes' / approval.
3.  **Tier D: Destructive & Irreversible (`delete`)**
    *   Requires **explicit typed confirmation** (e.g. "I confirm" or "Yes,
        delete it"). Ask for confirmation IMMEDIATELY — before any pre-flight
        checks (don't check if the model is deployed to endpoints first).
    *   **Same-turn restriction**: NEVER execute in the same turn as asking
        for typed confirmation. Wait for the user to reply in a new turn.

## Phase 0: Environment Setup

**CRITICAL**: Before running any commands, you MUST ensure the environment is
correctly initialized by following these steps:

1.  **Google Cloud Authentication**: Authenticate with your Google Cloud
    credentials and configure active Application Default Credentials (ADC) for
    Agent Platform access:
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
2.  **Set Project**: Configure the active project for subsequent commands:
    ```bash
    gcloud config set project $PROJECT_ID
    ```
3.  **Region**: Always specify `--region=$LOCATION_ID` on each command below.
    Do NOT use `global`.

## 1. Listing Models (Tier R)

Use this command to discover existing models in the registry and retrieve their
numeric IDs. No confirmation is required.

```bash
gcloud ai models list \
    --region=$LOCATION_ID
```

## 2. Describing a Model (Tier R)

Retrieve the full metadata for a specific model or version. No confirmation is
required.

```bash
gcloud ai models describe $MODEL_ID \
    --region=$LOCATION_ID
```

To target a specific version:

```bash
gcloud ai models describe ${MODEL_ID}@${VERSION_ID} \
    --region=$LOCATION_ID
```

## 3. Uploading a Model (Tier M)

Register a new model or a new version of an existing model. This is a
long-running operation.
**Action requires an inline confirmation card before proceeding.**

### Example: Uploading a Custom Model

```bash
gcloud ai models upload \
    --region=$LOCATION_ID \
    --display-name="my-custom-model" \
    --container-image-uri="gcr.io/my-project/my-model:latest" \
    --artifact-uri="gs://my-bucket/path/to/artifacts"
```

> [!IMPORTANT] This is a Tier M operation — see [Safety & Confirmation Tiers]
> above.

To upload a new version of an existing model, use the `--parent-model` flag or
specify the parent model ID.

## 4. Updating a Model (Tier M)

Update metadata fields like display name, description, or labels.
**Action requires an inline confirmation card before proceeding.**

```bash
gcloud ai models update $MODEL_ID \
    --region=$LOCATION_ID \
    --display-name="new-display-name" \
    --description="Updated description"
```

> [!IMPORTANT] This is a Tier M operation — see [Safety & Confirmation Tiers]
> above.

## 5. Deleting a Model (Tier D)

Permanently delete a Model and all its versions.
**Action requires explicit typed confirmation before proceeding.**

```bash
gcloud ai models delete $MODEL_ID \
    --region=$LOCATION_ID
```

> [!WARNING] This operation is irreversible. All model versions must be
> undeployed from all Endpoints before deletion.
