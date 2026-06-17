---
name: agent-platform-deploy
description: >-
  Deploy open models or custom weights from Model Garden to Agent Platform
  endpoints, check deployment status, verify serving endpoints, or clean up
  resources by undeploying models and deleting endpoints. Use when asked to
  deploy models on Agent Platform, list available Model Garden models, check if
  a model is deployable, query deployment cost, troubleshoot deployment errors
  (like quota limits), or undeploy/clean up endpoints. Also use when copying
  and deploying a 1P Tuned Model. Don't use for public Vertex AI deployments
  (use the `vertex-deploy` skill) or for running model evaluations (use the
  `agent-platform-eval` skill).
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

To see what machine types and accelerators are supported for a specific model
(e.g., `google/gemma3@gemma-3-27b-it`):

```bash
gcloud ai model-garden models list-deployment-config \
    --model="google/gemma3@gemma-3-27b-it"
```

> [!NOTE]
>
> Some models, especially Hugging Face models, might require a Hugging Face
> Access Token for deployment.

> [!TIP]
>
> **Model Recommendation Instructions:** If a user asks to deploy a model but
> **does not specify which one**, you should recommend a model based on their
> use case (e.g., Llama 3.3 70B for general purpose or Gemma 3 for lightweight
> tasks). * You **MUST** ensure you are recommending the **latest version** or
> **popular version** of the suggested model family. * You **MUST** verify the
> model is currently deployable using `gcloud ai model-garden models list`
> before suggesting it to the user.

## 3. Deploying a Model

> [!WARNING]
>
> Deploying models, especially large ones, consumes significant compute
> resources and incurs costs.
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

### Example: Deploying Gemma 3

Here is a typical bash script to deploy a model. You can run this block
directly.

```bash
#!/bin/bash
# Example script to deploy a model from Model Garden

PROJECT_ID=$(gcloud config get-value project)
LOCATION_ID="us-central1" # Recommended default region
MODEL_ID="google/gemma3@gemma-3-27b-it" # Replace with your chosen model ID

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
    --endpoint-display-name="my-gemma-deployment" \
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

> [!NOTE]
>
> As an agent, you can also offer to check the status of a deployment for the
> user if they provide an operation ID or if they just initiated the deployment
> with you.

Alternatively, you can list your endpoints to see if it shows up and check the
Cloud Console under the "Online prediction" tab.

```bash
gcloud ai endpoints list \
    --region=$LOCATION_ID
```

Note: Large models (like Llama 3.1 8B or Gemma 27B) may take 15-20 minutes to
fully deploy and start serving.

### Verifying Deployment

If the model is successfully deployed, verify by making a prediction call to
test. Because Model Garden models are often deployed to Dedicated Endpoints, you
shouldn't use `gcloud ai endpoints predict`. Instead, you must fetch the
endpoint's dedicated DNS name and send a `curl` request.

> [!TIP]
>
> Ask the user to try using their own prompt to see the results. Otherwise use
> the default.

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

> [!WARNING]
>
> Failing to undeploy a model will result in continuous charges for the
> allocated compute resources, even if you are not sending prediction requests.
> Always clean up after testing.

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

> [!WARNING]
>
> If the alternative suggestions involve changing the machine type or
> accelerator, you **MUST** recalculate the estimated cost using
> [Agent Platform prediction pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing?hl=en#prediction-and-explanation),
> warn the user about list prices versus actual billing, and get their explicit
> confirmation for the new cost before retrying the deployment.
