---
name: agent-platform-deploy
metadata:
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
  use `agent-platform-endpoint-management`. Don't use for public Vertex AI
  deployments (use the `vertex-deploy`
  skill) or for running model evaluations (use the `agent-platform-eval-flywheel`
  skill).
---

# Agent Platform Model Garden Deploy Skill

This skill provides instructions for deploying Open Models from Agent Platform
Model Garden to endpoints, and subsequently undeploying them to clean up
resources.

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
        clear confirmation prompt to the user explaining the proposed command.
        You MUST wait for their explicit confirmation before executing. For
        `undeploy-model`, you MUST first verify that the endpoint and deployed
        model exist; if `describe` or `list` returns a 404 or empty result, you
        MUST halt and inform the user rather than attempting undeployment.
3.  **Tier D: Destructive & Irreversible (`delete`)**
    *   **Rule**: This requires **explicit typed confirmation**. You MUST output
        a text message explaining the irreversible nature of endpoint or model
        deletion and asking the user to type "I confirm" or "Yes, delete it"
        before executing the deletion command.

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

## 2.1 Region Availability Check for Publisher Endpoints (Gemini + LoRA base)

> [!NOTE] **Skip this section** if the user is asking to deploy an open-weights
> model from Model Garden (Gemma, Llama, DeepSeek, Qwen, or any user-supplied
> weights) — i.e. anything served via `gcloud ai model-garden models deploy`
> onto a dedicated endpoint. These models have no per-region availability
> restriction; the Model Garden catalog is global. The real failure modes for an
> unusual region are (a) the requested accelerator/machine type isn't offered in
> that region, or (b) the project has no quota — both surface as a clean error
> at deploy time before any resources are provisioned (§3's cost-confirm gate
> catches them). Go straight to §3.
>
> **Apply this section** only if the user is asking to serve a first-party
> managed Gemini model (`google/gemini-*`) or a fine-tuned Gemini LoRA adapter —
> both of which route through a publisher endpoint whose regional availability
> actually varies.

Before responding to any deploy request that names a specific region for a
first-party managed model (`google/gemini-*`) or a fine-tuned Gemini LoRA
adapter, you **MUST** verify the model is actually available in that region by
making a live API call. Do not rely on Google Search, training-corpus knowledge,
or publisher documentation for availability claims — regional availability
changes frequently and grounded text can be stale or wrong.

Probe only the exact model and region the user asked about. Do not probe other
models as a "control" — you cannot infer anything about model A's availability
from model B's status, because a different model may itself be unavailable in
the reference region for unrelated reasons.

For first-party publisher models (`google/*`), probe with a real
`:generateContent` call using a minimal valid payload:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    "https://${LOCATION_ID}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_ID}/publishers/google/${MODEL_ID}:generateContent" \
    -d "{\"contents\":{\"role\":\"user\",\"parts\":{\"text\":\"${PROBE_TEXT:-hi}\"}}}"
```

For fine-tuned Gemini LoRA models (deploying a user-tuned adapter on top of a
base Gemini model), probe the **base model** in the target region using the same
`:generateContent` call above with `${MODEL_ID}` set to the base (e.g.
`gemini-2.5-flash` if the adapter was tuned on `gemini-2.5-flash`). The LoRA
adapter cannot serve in a region where its base model isn't available.

Interpret the probe result and act:

-   **200** — model is available in that region. Proceed with the deploy.
-   **404** — model is not available in that region. STOP. Tell the user plainly
    that the model isn't offered in that region and list the regions where it is
    available (from `gcloud ai model-garden models list
    --filter="name~$MODEL_NAME"` without `--region`). Do not silently switch
    regions. Do not proceed to write deploy code or SDK initialization for the
    unsupported region. Do not run additional "control" probes to double-check
    the 404 — the target-region probe is authoritative.
-   **Any other outcome** (permission denied, quota, transient failure, etc.) —
    do not conclude the model is available or unavailable. Explain the
    underlying cause in plain language (e.g. "your account doesn't have access
    to this project's Vertex AI API — enable it in the console or switch
    projects") and the concrete next action.


## 3. Deploying a Model

> [!WARNING] Deploying models, especially large ones, consumes significant
> compute resources and incurs costs.
>
> 1.  You **MUST** refer to
>     [Agent Platform prediction pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing?hl=en#prediction-and-explanation)
>     to calculate a rough cost estimation based on the requested
>     `--machine-type` and `--accelerator-type` (and count).
> 2.  You **MUST** present this cost estimation to the user and warn them that
>     this is the **list price**, which may differ from their actual bill due to
>     potential discounts or reservations.
> 3.  You **MUST ALWAYS** request explicit confirmation from the user agreeing
>     to the estimated cost before executing any `deploy` command.

To deploy a model, use the `deploy` command. It is highly recommended to use the
`--asynchronous` flag for long-running deployments, and then poll the status if
necessary.

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

PROJECT_ID=$(gcloud config get-value project)
LOCATION_ID="us-central1" # Recommended default region
MODEL_ID="<PUBLISHER>/<FAMILY>@<VERSION-ID>" # PLACEHOLDER — replace with the exact ID from `gcloud ai model-garden models list`

echo "Deploying model $MODEL_ID to project $PROJECT_ID in $LOCATION_ID..."

# Model Garden can automatically select the required hardware based on the list-deployment-config if hardware params are omitted.
# Below is a comprehensive command with all supported parameters:
gcloud ai model-garden models deploy \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --model=$MODEL_ID \
    --machine-type="g2-standard-48" \
    --accelerator-type="NVIDIA_L4" \
    --accelerator-count=4 \
    --endpoint-display-name="my-open-model-deployment" \
    --hugging-face-access-token="YOUR_HF_TOKEN" \
    --reservation-affinity="reservation-affinity-type=specific-reservation,key=compute.googleapis.com/reservation-name,values=my-reservation" \
    --asynchronous

echo "Deployment initiated asynchronously."
```

### Example: Deploying Custom Weights

To deploy a model using custom weights, you can use the exact same `deploy`
command. Instead of providing the model garden model ID, provide the Google
Cloud Storage (GCS) URI to your custom weights folder in the `--model` flag.

```bash
#!/bin/bash
# Example script to deploy a model with custom weights from a GCS bucket

PROJECT_ID=$(gcloud config get-value project)
LOCATION_ID="us-central1"
# Replace with the gs:// URI pointing to your custom weights
MODEL_GCS_URI="gs://your-bucket-name/path/to/custom-weights"

echo "Deploying custom model from $MODEL_GCS_URI to project $PROJECT_ID in $LOCATION_ID..."

gcloud ai model-garden models deploy \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --model=$MODEL_GCS_URI \
    --machine-type="g2-standard-12" \
    --accelerator-type="NVIDIA_L4" \
    --endpoint-display-name="my-custom-model" \
    --asynchronous

echo "Deployment initiated asynchronously."
```

## 4. Checking Deployment Status

When you deploy a model asynchronously using the `--asynchronous` flag, the
`deploy` command will return an operation ID. You can use this ID to check the
ongoing status of the deployment.

```bash
gcloud ai operations describe YOUR_OPERATION_ID \
    --region=$LOCATION_ID
```

> [!NOTE] As an agent, you can also offer to check the status of a deployment
> for the user if they provide an operation ID or if they just initiated the
> deployment with you.

Alternatively, you can list your endpoints to see if it shows up and check the
Cloud Console under the "Online prediction" tab.

```bash
gcloud ai endpoints list \
    --region=$LOCATION_ID
```

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
LOCATION_ID="us-central1"
ENDPOINT_ID="YOUR_ENDPOINT_ID"
PROMPT=${1:-"Explain quantum computing in simple terms."}

echo "Fetching dedicated Endpoint DNS..."
ENDPOINT_URL=$(gcloud ai endpoints describe $ENDPOINT_ID --project=$PROJECT_ID --region=$LOCATION_ID --format="value(dedicatedEndpointDns)")

if [ -z "$ENDPOINT_URL" ]; then
    echo "Error: Could not retrieve a dedicated endpoint URL. Verify your ENDPOINT_ID."
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

To stop incurring charges, you must undeploy the model from the endpoint. This
is a multi-step process if you don't already have the exact endpoint and
deployed model IDs.

### Example: Finding and Undeploying a Model

Here is a bash script demonstrating how to find the IDs and undeploy the model.

```bash
#!/bin/bash
# Example script to undeploy a model

PROJECT_ID=$(gcloud config get-value project)
LOCATION_ID="us-central1"
# The model ID used during deployment (without the provider prefix sometimes, or exactly as listed in describe)
# It's usually easier to find the specific ID via `gcloud ai models list`
# For this example, let's assume we know the exact Endpoint ID and Deployed Model ID.

# 1. Find the Endpoint ID
echo "Listing endpoints in $LOCATION_ID:"
gcloud ai endpoints list --project=$PROJECT_ID --region=$LOCATION_ID

# (Assuming you extracted ENDPOINT_ID from the above output)
# ENDPOINT_ID="your_endpoint_id"

# 2. Find the Deployed Model ID
echo "Listing models in $LOCATION_ID to find model description:"
gcloud ai models list --project=$PROJECT_ID --region=$LOCATION_ID

# (Assuming you found the specific MODEL_ID)
# MODEL_ID="your_model_id"
# gcloud ai models describe $MODEL_ID --project=$PROJECT_ID --region=$LOCATION_ID
# (Extract the deployedModelId from the output)
# DEPLOYED_MODEL_ID="your_deployed_model_id"

# 3. Undeploy
echo "Undeploying model $DEPLOYED_MODEL_ID from endpoint $ENDPOINT_ID..."
gcloud ai endpoints undeploy-model $ENDPOINT_ID \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --deployed-model-id=$DEPLOYED_MODEL_ID

echo "Model undeployed."

# 4. Delete Endpoint
echo "Deleting endpoint $ENDPOINT_ID..."
gcloud ai endpoints delete $ENDPOINT_ID \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --quiet
echo "Endpoint deleted."

# 5. Delete Model
echo "Deleting model $MODEL_ID..."
gcloud ai models delete $MODEL_ID \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --quiet
echo "Model deleted."
```

> [!WARNING] Failing to undeploy a model will result in continuous charges for
> the allocated compute resources, even if you are not sending prediction
> requests. Always clean up after testing.

## 6. Troubleshooting

### Deployment Failure: Quota or Resource Exhausted

If your deployment fails (or stays in an error state) due to `QUOTA_EXCEEDED` or
`RESOURCE_EXHAUSTED` errors, the specific hardware requested (e.g., `NVIDIA_L4`
or `g2-standard-24`) is either not available in your chosen region or exceeds
your project's quota limits.

**Solution:** Look closely at the error message returned. It will often
recommend an alternative region or machine type that currently has availability.
**Ask the user for confirmation** to retry the deployment using the suggested
`--region` or `--machine-type` parameters.

> [!WARNING] If the alternative suggestions involve changing the machine type or
> accelerator, you **MUST** recalculate the estimated cost using
> [Agent Platform prediction pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing?hl=en#prediction-and-explanation),
> warn the user about list prices versus actual billing, and get their explicit
> confirmation for the new cost before retrying the deployment.
