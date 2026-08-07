---
name: agent-platform-endpoint-management
metadata:
  category: AiAndMachineLearning
description: >-
  Manages Agent Platform serving endpoints. Use when you need to create, list,
  describe, update, or delete serving endpoints for model deployment on Agent
  Platform. Also use when troubleshooting endpoint permission, quota, or resource
  busy errors. Don't use for deploying models to endpoints or for running
  model evaluations.
---

# Agent Platform Endpoint Management

## Overview

This skill provides procedural knowledge for managing Agent Platform Endpoints.
Endpoints are logical serving hosts that provide a stable URL for online
predictions. You must create an endpoint before you can deploy a model to it.

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands on behalf of the user, you MUST adhere to the
following safety tiers based on the action requested:

1.  **Tier R: Read-only (`list`, `describe`, `get`)**
    *   No confirmation needed. Execute immediately to gather information.
2.  **Tier M: Mutating & Reversible (`create`, `update`)**
    *   Requires **interactive confirmation** with 'Yes'/'No' options. The
        confirmation prompt MUST contain the exact, literal command string with
        all required flags (e.g. `--region=us-central1`, `--display-name="..."`)
        — natural-language paraphrases are NOT sufficient.
    *   **Same-turn restriction**: NEVER execute the command in the same turn as
        presenting the confirmation prompt. Stop and wait for the user's reply;
        only execute after explicit 'Yes' / approval.
3.  **Tier D: Destructive & Irreversible (`delete`)**
    *   Requires **explicit typed confirmation** (e.g. "I confirm" or "Yes,
        delete it"). Ask for confirmation IMMEDIATELY — before any pre-flight
        checks (don't `describe` first, don't check if the endpoint is empty
        first).
    *   **Same-turn restriction**: NEVER execute in the same turn as asking for
        typed confirmation. Wait for the user to reply in a new turn.

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

3.  **Region**: Always specify `--region=$LOCATION_ID` on each command below. Do
    NOT use `global`. Ask the user to specify the region if not provided.

## 1. Listing Endpoints (Tier R)

Use this command to discover existing endpoints in a specific region and
retrieve their IDs. No confirmation is required.

```bash
gcloud ai endpoints list \
    --region=$LOCATION_ID
```

*(Optional)* For pagination, you MUST use `--limit=$LIMIT` to restrict the total
number of returned endpoints. You can also append `--page-size=$PAGE_SIZE` to
control API chunking, or `--page-token=$PAGE_TOKEN` for next pages.

> [!IMPORTANT]
>
> Always specify the `--region`. Do NOT use 'global'. Ask the user to specify if
> not provided.

## 2. Describing an Endpoint (Tier R)

Retrieve the full metadata for a specific endpoint. No confirmation is required.

```bash
gcloud ai endpoints describe $ENDPOINT_ID \
    --region=$LOCATION_ID
```

## 3. Creating an Endpoint (Tier M)

Create a new endpoint resource. The parent resource is the location. **Action
requires an inline confirmation card before proceeding.**

```bash
gcloud ai endpoints create \
    --region=$LOCATION_ID \
    --display-name="my-endpoint"
```

> [!IMPORTANT]
>
> **You MUST seek interactive confirmation first.** Your confirmation prompt
> **MUST** show the literal command string. For example:
>
> ```bash
> gcloud ai endpoints create --region=$LOCATION_ID --display-name="my-endpoint"
> ```
>
> Or the exact flags. Do not execute this command in the same turn as proposing
> the confirmation.

## 4. Updating an Endpoint (Tier M)

Update endpoint metadata such as display name or labels. **Action requires an
inline confirmation card before proceeding.**

```bash
gcloud ai endpoints update $ENDPOINT_ID \
    --region=$LOCATION_ID \
    --display-name="new-display-name"
```

Check if the endpoint exists first by either listing or describing the endpoint.

> [!IMPORTANT]
>
> **You MUST seek interactive confirmation first.** Your confirmation prompt
> **MUST** show the literal command string. For example:
>
> ```bash
> gcloud ai endpoints update $ENDPOINT_ID --region=$LOCATION_ID --display-name="new-display-name"
> ```
>
> Or the exact flags. **CRITICAL:** You are strictly prohibited from executing
> this command in the same turn as asking for confirmation. When you ask for
> confirmation, you MUST stop immediately and wait for the user to reply.

## 5. Deleting an Endpoint (Tier D)

Permanently delete an endpoint resource. **Action requires explicit typed
confirmation before proceeding.**

```bash
gcloud ai endpoints delete $ENDPOINT_ID \
    --region=$LOCATION_ID
```

> [!WARNING]
>
> All models must be **undeployed** from the endpoint before it can be deleted.
> Do not run `describe` until AFTER you have received typed confirmation to
> delete.

## 6. Traffic Splitting (Tier M)

You can manage traffic split between different models deployed on the same
endpoint during an update. **Action requires an inline confirmation card before
proceeding.**

```bash
# Example: Deploying a model with a specific traffic split is usually done
# via 'gcloud ai endpoints deploy-model'.
```

Refer to the `agent-platform-deploy` skill for instructions on deploying and
undeploying models.

## Troubleshooting

-   **403 Permission Denied**: Ensure `aiplatform.admin` or `owner` role is
    assigned.
-   **Quota Exceeded**: Verify the region's endpoint quota in the Cloud Console.
-   **Resource Busy**: If a deletion fails, check if models are still being
    undeployed.
