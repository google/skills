---
name: agent-platform-deploy
metadata:
  version: "1.0.5"
  category: AiAndMachineLearning
description: >-
  Deploy open models or custom weights from Model Garden to Agent Platform
  endpoints, check the status of an in-progress deployment operation, or clean
  up resources by undeploying models and deleting endpoints. Use when asked to
  actively deploy a model, list the Model Garden CATALOG of available models,
  check if a specific model is deployable
  (`gcloud ai model-garden models list-deployment-config`), query deployment
  cost, troubleshoot deployment errors (like quota limits), or undeploy/clean
  up endpoints. Also use when copying and deploying a 1P Tuned Model. Don't
  use for pure listing/discovery questions of the form "is X deployed?",
  "list my endpoints", or "which regions have models running?" — for those
  use `agent-platform-endpoint-management`. Don't use for running model evaluations
  (use `agent-platform-eval-flywheel` skill).
---

# Agent Platform Model Garden Deploy Skill

This skill provides instructions for deploying Open Models from Agent Platform
Model Garden to endpoints, and subsequently undeploying them to clean up
resources.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` and append the
attribution suffix to `User-Agent` headers:

```text
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-deploy)"
User-Agent: <existing_user_agent> agent-skills/1.0 (skill:agent-platform-deploy)
```

## 1P Tuned Model Copy & Deployment

If you need to copy a **1P (First-Party) Tuned Model** from a source project to
a destination region or project and deploy it to a newly created endpoint, refer
to the
[1P Tuned Model Copy & Deployment Guide](references/copy_deploy_guide.md).

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands on behalf of the user, you MUST adhere to the
following safety tiers based on the action requested:

1.  **Tier R: Read-only (`list`, `describe`, `list-deployment-config`)**
    *   **Rule**: No confirmation needed. You may execute these commands
        immediately to gather information for the user.
2.  **Tier M: Mutating & Reversible (`deploy`, `undeploy-model`)**
    *   **Rule**: This requires explicit user confirmation. You MUST present a
        clear dry-run confirmation card containing:

        1.  Exact proposed `gcloud` command code block (`gcloud ai model-garden
            models deploy ... --asynchronous`).
        2.  Model identifier, destination project ID, and target region.
        3.  Machine type and accelerator configuration.
        4.  Estimated hourly cost ($/hr).
        5.  Endpoint display name.
        6.  Explicit confirmation prompt asking the user to approve before
            execution.
        You MUST wait for their explicit confirmation before executing. For
        `undeploy-model`, you MUST first verify that the endpoint and deployed
        model exist; if `describe` or `list` returns a 404 or empty result, you
        MUST halt and inform the user rather than attempting undeployment.
    *   **Same-turn restriction**: Do not run the command in the same turn as
        presenting the confirmation prompt. End your turn after asking and wait
        for the user's reply; only execute after explicit approval. Printing a
        preview and then calling the tool before the user can answer does not
        count as obtaining confirmation.
3.  **Tier D: Destructive & Irreversible (`delete`)**
    *   **Rule**: This requires **explicit typed confirmation**. You MUST output
        a text message explaining the irreversible nature of endpoint or model
        deletion and asking the user to type "I confirm" or "Yes, delete it"
        before executing the deletion command.

> [!IMPORTANT]
>
> **Always Output Complete Text Response (NEVER Emit Empty Text)**: After
> executing any tool call (such as `gcloud ai model-garden models deploy`,
> `gcloud ai endpoints delete`, `gcloud ai endpoints list`, or status checks),
> you MUST formulate and return a complete, informative textual response to the
> user. Explicitly report the operation name, endpoint name/ID, error message,
> or list of resources. **NEVER finish a turn with empty text or silence**.

## 1. Prerequisites

Before deploying, ensure you have the correct project and region set. The
commands below use placeholder variables `PROJECT_ID` and `LOCATION_ID`.

Ensure you are authenticated:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project $PROJECT_ID
```

## 2. Discovering Deployable Models

You can list models available in Model Garden and check if they can be
self-deployed.

```bash
gcloud ai model-garden models list
```

To see what machine types and accelerators are supported for a specific model,
pass a `MODEL_ID` you obtained from the `models list` output above. Substitute
`<PUBLISHER>/<FAMILY>@<VERSION-ID>` below with the exact string from the catalog
output — the placeholder is deliberately not a real model ID:

```bash
gcloud ai model-garden models list-deployment-config \
    --model="<PUBLISHER>/<FAMILY>@<VERSION-ID>"
```

> [!NOTE] Some models, especially Hugging Face models, might require a Hugging
> Face Access Token for deployment.

> [!TIP] **Model Recommendation Instructions:** Whenever you are about to name a
> specific model version in a response, do NOT recommend from memory. This
> applies in all of the following situations — not just direct deploy requests:
>
> *   The user asks to deploy a model without naming one.
> *   You are volunteering a next-step suggestion after a `list`, `describe`, or
>     `undeploy` operation (e.g. "Would you like me to deploy `<model>` to this
>     endpoint?").
> *   The user asks a general "what should I use?" / "what's a good model for
>     X?" question.
> *   You are filling in a `MODEL_ID` value in an example command you are
>     showing the user (as opposed to a placeholder like
>     `<PUBLISHER>/<FAMILY>@<VERSION-ID>`).
>
> New model versions ship frequently and older ones may be deprecated, so
> training-corpus knowledge of which models exist is unreliable. Follow this
> procedure:
>
> 1.  **Clarify the use case** if it isn't already clear from context (task
>     type, quality vs. latency vs. cost priorities, hardware/quota constraints,
>     license constraints). Skip if the user has already given enough signal.
> 2.  **Query the live catalog** with `gcloud ai model-garden models list`.
>     Narrow with `--filter` when appropriate (e.g. `--filter="name~gemma"`,
>     `--filter="name~llama"`, `--filter="name~qwen"`,
>     `--filter="name~deepseek"`). Never name a specific model version to the
>     user until you have seen it in the catalog output for this project.
> 3.  **Pick the latest generally-available version** in the family that fits
>     the use case. When multiple size variants exist, pick the one that matches
>     the user's hardware/cost tolerance. Prefer a newer major version over an
>     older one unless it is marked preview/experimental and the user explicitly
>     asked for a stable option.
> 4.  **Verify the exact model ID is deployable** with `gcloud ai model-garden
>     models list-deployment-config --model="<publisher>/<family>@<version>"`
>     before naming it in your response.
> 5.  **Cite the model ID verbatim** in your recommendation, exactly as it
>     appears in the catalog. Do not paraphrase to a family label ("Gemma",
>     "Llama").
>
> The `MODEL_ID` values in the §3 examples below are intentionally
> non-substantive placeholders (`<PUBLISHER>/<FAMILY>@<VERSION-ID>`). Do NOT
> replace them with a remembered model name for a user-facing recommendation —
> always re-run steps 2-4 first, then cite the exact string from the catalog.

## 2.1 Region Availability Check (Gemini + LoRA only)

> For first-party Gemini or LoRA deploys, you must verify region availability
> before proceeding. Load the full instructions with
> `load_skill_resource(skill_name='agent-platform-deploy',
> file_path='references/region_availability.md')`.
>
> **Skip this** for open-weights models (Gemma, Llama, DeepSeek, Qwen) and for
> Gemini-tuned models — they have no per-region publisher endpoint restriction.
> Go straight to §3.

## 3. Deploying a Model

> [!WARNING] Deploying models, especially large ones, consumes significant
> compute resources and incurs costs.
>
> 1.  You **MUST** compute an hourly $ estimate for the requested
>     `--machine-type` before proposing a deploy. Try each source below in
>     order, falling through to the next on any failure:
>
>     -   Run `scripts/calculate_cost.py`. The accelerator type and count are
>         fixed per machine type in Model Garden and derived automatically.
>         Example:
>
>         ```bash
>         python3 scripts/calculate_cost.py \
>             --machine-type=g2-standard-48
>         ```
>
>         If the script exits non-zero (unknown `--machine-type` — a routine
>         state for machines in the Model Garden catalog but not yet in the
>         price snapshot, e.g. A4/B200 today), fall through to the next source.
>         Do NOT invent a number.
>
>     -   Fall back to
>         [Agent Platform prediction pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing?hl=en#prediction-and-explanation)
> if no source above produced a
>         number. Read the accelerator + hourly rate directly off that page and
>         cite the URL in the estimate you present to the user.
>
> 2.  You **MUST** present this cost estimation to the user and warn them that
>     this is the **list price**, which may differ from their actual bill due to
>     potential discounts, reservations, or non-`us-central1` regions.
> 3.  You **MUST ALWAYS** request explicit confirmation from the user agreeing
>     to the estimated cost before executing any `deploy` command.

To deploy a model, use the `deploy` command. It is highly recommended to use the
`--asynchronous` flag for long-running deployments, and then poll the status if
necessary.

> [!IMPORTANT]
>
> -   **Cost Pushback & Hardware Renegotiation**: If the user pushes back on
>     cost (e.g., "That is too expensive, can you try a smaller
>     configuration?"), or requests an invalid or unsupported hardware
>     combination (e.g. `g2-standard-48g` with 4x H100 GPUs), explain the
>     constraint or invalidity clearly, check `list-deployment-config` to
>     identify the supported alternative (e.g., `g2-standard-24` with 2x L4 or
>     `g2-standard-12` with 1x L4), compute its cost estimate with a single
>     query, and **immediately render a complete Tier M dry-run confirmation
>     card** for that recommended configuration in the same response.
> -   **Region Failover & Quota Exhaustion**: When a deployment fails due to
>     quota or capacity in the requested region (e.g. `QUOTA_EXCEEDED` or
>     `RESOURCE_EXHAUSTED`), identify an alternative supported region (e.g.
>     `us-east4` or `us-east1`), compute its cost estimate with a single query,
>     and **immediately render a complete Tier M dry-run confirmation card with
>     the new `--region` and exact command in the same response**. State the
>     alternative region directly without making unverified capacity claims.
> -   **Efficient Tool Execution (No Redundant Calls)**: Do NOT execute
>     redundant `models list`, `list-deployment-config`, or `--help` commands if
>     the model ID, region, or hardware configuration are already known or
>     resolved. Run each discovery command strictly once.
> -   **Single Status Check & Response Formatting (CRITICAL)**:
>     -   When initiating an asynchronous deployment (`gcloud ai model-garden
>         models deploy ... --asynchronous`), the command output immediately
>         returns the operation name. **Formulate and return your textual
>         confirmation response with the operation name and endpoint display
>         name immediately**. Do NOT call `operations describe` in the same turn
>         as deployment initiation.
>     -   When the user explicitly asks to check deployment status (e.g.,
>         "Please check to see the status of the deployment" or "Can you check
>         if the deployment has finished?"):
>         -   **NEVER run `sleep` commands, `while` loops, or repeated polling
>             calls**.
>         -   Execute `gcloud ai operations describe <OPERATION_NAME>`, the full
>             operation name the deploy command printed, **strictly ONCE**.
>         -   **ALWAYS output a full textual response** reporting the operation
>             status (e.g. "The deployment operation
>             `projects/.../operations/...` is currently in progress / running
>             (created at `...`). Asynchronous model deployment typically takes
>             10–15 minutes to complete").
>         -   Only proceed with sending a test prediction if the status check
>             confirms the endpoint is already serving and ready.
> -   **Alphanumeric Project ID**: Always specify the alphanumeric Project ID
>     (e.g. `my-gcp-project`) for `--project`, NOT the numeric project number
>     (e.g. `123456789012`). If given a numeric project number and its Project
>     ID is not available, pass the number inside a fully-qualified resource
>     name, e.g. `gcloud ai endpoints list
>     --region=projects/123456789012/locations/us-central1`, or as a positional
>     resource, `gcloud ai endpoints describe
>     projects/123456789012/locations/us-central1/endpoints/<ENDPOINT_ID>
>     --region=us-central1`. If `gcloud ai` still refuses because `core/project`
>     is set to a project number, ask the user for the Project ID rather than
>     retrying.
> -   **Valid User-Specified Hardware Priority**: When the user specifies an
>     explicit, valid hardware configuration (e.g. `g2-standard-96` with 8
>     `NVIDIA_L4` GPUs, or `g2-standard-12` with 1 `NVIDIA_L4` GPU), honor that
>     requested configuration for the dry-run preview and cost estimation rather
>     than overriding it with default recommendations. However, if the requested
>     configuration is **invalid or unsupported** (e.g. mismatched GPU count
>     such as `g2-standard-12` with 2 L4 GPUs, or non-existent machine shapes),
>     follow the **Cost Pushback & Hardware Renegotiation** rule above: explain
>     the invalidity clearly, identify the supported alternative (e.g.
>     `g2-standard-24` with 2 L4 GPUs), calculate its cost, and immediately
>     present the confirmation card for the valid alternative.
> -   **Endpoint Display Name**: If the user specifies or requests an endpoint
>     name or display name (e.g. `'usersim-gemma-eval-...'`), you MUST always
>     include `--endpoint-display-name="<NAME>"` in the `deploy` command.

### Example: Deploying an open-weights model from Model Garden

Here is a typical bash script to deploy a model. You can run this block
directly.

```bash
#!/bin/bash
# Example script to deploy an open-weights model from Model Garden.
#
# NOTE: MODEL_ID below is a PLACEHOLDER, not a real model ID. Substitute it
# with a value from a live `gcloud ai model-garden models list` (see §2)
# before running this script, and do NOT quote the placeholder back to the
# user as a recommended model.
#
# IMPORTANT FOR deploy_config["command"]: when building the curl command for
# the deploy confirmation card, inline ALL values as literals — do NOT leave
# ${PROJECT_ID}, ${LOCATION_ID}, or ${PUBLISHER_MODEL} as shell variables.
# The server rejects commands with unresolved variables at render time.
# The only allowed substitution is $(gcloud auth print-access-token).

PROJECT_ID=$(gcloud config get-value project)
# `gcloud ai` needs the alphanumeric Project ID, not the project number.
: "${PROJECT_ID:?no project ID is set; ask the user for the Project ID}"
LOCATION_ID="us-central1" # Recommended default region
# Replace placeholder with exact ID from `gcloud ai model-garden models list`:
MODEL_ID="<PUBLISHER>/<FAMILY>@<VERSION-ID>"

echo "Deploying model $MODEL_ID to project $PROJECT_ID in $LOCATION_ID..."

# Hardware params can be omitted to select recommended default config.
# Comprehensive command with supported parameters:
gcloud ai model-garden models deploy \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --model=$MODEL_ID \
    --machine-type="g2-standard-12" \
    --accelerator-type="NVIDIA_L4" \
    --accelerator-count=1 \
    --endpoint-display-name="my-open-model-deployment" \
    --asynchronous

echo "Deployment initiated asynchronously."
```

With `--asynchronous` the command prints the full operation name,
`projects/<PROJECT>/locations/<REGION>/operations/<OP_ID>`. Pass that to §4: a
bare `<OP_ID>` works only when gcloud has a project.

-   Include `--hugging-face-access-token="<HF_TOKEN>"` when deploying gated
    Hugging Face models that require authentication.
-   Include `--reservation-affinity` (e.g. `none` or
    `reservation-affinity-type=specific-reservation,...`) if using reserved
    compute.

### 1P Tuned Model Cross-Region Copy and Deployment

> For the detailed tuned model copy and deployment workflow, load
> `load_skill_resource(skill_name='agent-platform-deploy',
> file_path='references/copy_deploy_guide.md')`. That guide covers the execution
> sequence, tier assignments for copy/deploy/delete commands, hardware
> renegotiation, test prediction verification, and the in-progress operation
> lock.

## 4. Checking Deployment Status

When you deploy a model asynchronously using the `--asynchronous` flag, the
`deploy` command returns an operation name. Pass the full name to check the
ongoing status of the deployment.

```bash
gcloud ai operations describe YOUR_OPERATION_NAME
```

> [!IMPORTANT]
>
> **Single Status Check Only (No Sleep / Polling Loops)**: Model deployment
> operations take 10–30 minutes. NEVER run `sleep` commands (e.g. `sleep 45 &&
> ...`) or loop `operations describe` repeatedly in a turn. Run `gcloud ai
> operations describe` **strictly ONCE**. If `done` is not true, immediately
> return the operation name and in-progress status to the user and explain that
> deployment takes 10–15 minutes.

Note: Large models (roughly 20B+ parameters) may take 15-20 minutes to fully
deploy and start serving.

### Verifying Deployment

If the model is successfully deployed, verify by making a prediction call to
test. Because Model Garden models are often deployed to Dedicated Endpoints, you
shouldn't use `gcloud ai endpoints predict`. Instead, you must fetch the
endpoint's dedicated DNS name and send a `curl` request.

> [!TIP] Ask the user to try using their own prompt to see the results.
> Otherwise use the default.

Use the following script:

```bash
#!/bin/bash
PROJECT_ID=$(gcloud config get-value project)
: "${PROJECT_ID:?no gcloud project is set; ask the user for the Project ID}"
LOCATION_ID="us-central1"
ENDPOINT_ID="YOUR_ENDPOINT_ID"
PROMPT=${1:-"Explain quantum computing in simple terms."}

echo "Fetching dedicated Endpoint DNS..."
ENDPOINT_URL=$(gcloud ai endpoints describe $ENDPOINT_ID \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --format="value(dedicatedEndpointDns)")

if [ -z "$ENDPOINT_URL" ]; then
    echo "Error: Could not retrieve dedicated endpoint URL for $ENDPOINT_ID."
    exit 1
fi

echo "Sending prediction request to $ENDPOINT_URL..."

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://${ENDPOINT_URL}/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION_ID}/endpoints/${ENDPOINT_ID}/chat/completions" \
  -d '{
    "model": "'"$ENDPOINT_ID"'",
    "messages": [
      {
        "role": "user",
        "content": "'"$PROMPT"'"
      }
    ]
  }'

```

## 5. Undeploying and Cleaning Up

> For the full undeploy and cleanup procedure (find endpoint, undeploy model,
> delete endpoint, delete model), load
> `load_skill_resource(skill_name='agent-platform-deploy',
> file_path='references/undeploy_guide.md')`.

> [!WARNING] Failing to undeploy a model will result in continuous charges for
> the allocated compute resources, even if you are not sending prediction
> requests. Always clean up after testing.

## 6. Troubleshooting

> For troubleshooting quota/resource exhausted errors and hardware fallback,
> load `load_skill_resource(skill_name='agent-platform-deploy',
> file_path='references/troubleshooting.md')`.
