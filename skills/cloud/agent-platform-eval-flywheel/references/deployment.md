# Deploying and Evaluating Models on Agent Platform Endpoints

Reference for the deployment-and-endpoint-evaluation subset of the Quality
Flywheel. Use this guide when the user needs to evaluate a model that is **not
yet served** (must be deployed first) or is served on an Agent Platform
**endpoint** rather than called through the `agentplatform` Python client
directly.

The two scripts referenced here — `scripts/endpoint_evaluation.py` and
`scripts/maas_evaluation.py` — wrap Stage 2 (inference) and Stage 3 (grading) of
the Flywheel against deployed endpoints. They produce the same
`EvaluationResult` shape consumed by `scripts/inspect_results.py` and
`scripts/compare_results.py`, so the rest of the Flywheel (Stages 4 and 5)
applies unchanged.

For the public-docs version of this workflow, see the
[Agent Platform model evaluation docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/eval-python-sdk/run-evaluation).

## When to use this guide

-   The user wants to evaluate a **custom-weights / Bring-Your-Own-Model
    (BYOM)** model deployed to an Agent Platform endpoint.
-   The user wants to evaluate a **Model-as-a-Service (MaaS)** model (e.g.
    `meta/llama3-8b`, `gemini-1.5-pro`) by model ID.
-   The user is at the deploy-then-eval stage: weights exist in GCS or in Model
    Garden but no endpoint has been provisioned yet.

For agent (multi-turn) evaluation, dataset preparation, metric selection,
failure clustering, or iteration, stay in the main SKILL.md flow. This guide
only covers the deployment + endpoint-inference subset.

## Setup

Install the deployment-eval dependencies (in addition to the base SDK install in
the main SKILL.md):

```bash
python3 -m venv .model-eval
source .model-eval/bin/activate
pip install -r references/requirements.txt
```

The scripts also shell out to `gcloud` and `gsutil`, so the user must have the
Google Cloud SDK installed and `gcloud auth application-default login`
completed.

Confirm project / region / quota project:

```bash
gcloud config get project
gcloud config get compute/region
gcloud config get billing/quota_project
```

## 1. Deploy a Model

> [!TIP]
>
> If the `agent-platform-deploy` skill is available, prefer it — it carries the
> full deployment surface. This section is the minimum needed to get an endpoint
> to evaluate against.

```bash
gcloud ai model-garden models deploy \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --model=$MODEL \
    --machine-type=$MACHINE_TYPE \
    --accelerator=$ACCELERATOR_TYPE,count=$ACCELERATOR_COUNT \
    --endpoint-display-name=$ENDPOINT_NAME \
    --asynchronous
```

`MODEL` is either a Model Garden model ID (`meta/llama3-8b`) or a GCS URL to
custom weights. If any of `MACHINE_TYPE`, `ACCELERATOR_TYPE`,
`ACCELERATOR_COUNT` are missing, **stop and ask the user** — do not pick
defaults silently. Confirm the full command with the user before running it.

### Determining hardware requirements

For custom weights stored in GCS, check for a tuning marker first:

```bash
gcloud storage cat $GCS_URL/managed_oss_fine_tuning_marker.json
gcloud storage cat $GCS_URL/config.json
```

If neither is present, ask the user for the base model ID, then query
recommended configs:

```bash
gcloud ai model-garden models list-deployment-config --model=$BASE_MODEL_ID
```

Summarize the recommended machine + accelerator combinations and confirm with
the user before deploying.

## 2. Check Deploy Status

Deploys are asynchronous. Poll the operation:

```bash
gcloud ai operations describe $OPERATION_ID --region=$LOCATION_ID
```

Report the status to the user — including the "not found" case — without asking
for confirmation first.

## 3. Run Inference and Evaluation

> [!WARNING]
>
> Both scripts use LLM-as-a-judge metrics. Tell the user up-front: **this can
> take ~30 minutes per 50 samples**.

Dataset format: JSONL in GCS with a `prompt` field on each line. See
[dataset_schema.md](dataset_schema.md) for the per-metric column requirements.
If the user's dataset doesn't have a `prompt` column, reformat it before
running.

Recommended starter metrics (confirm with the user first):

-   `coherence` — does the response hold together logically?
-   `fluency` — grammatical correctness and natural flow.
-   `text_quality` — overall text quality.

For the full metric catalog, see [metric_registry.md](metric_registry.md).

Suggest an experiment name based on `${MODEL_ID}_${DATASET_NAME}` if the user
doesn't provide one.

### 3.1. Bring-Your-Own-Model (BYOM) Endpoint

Inspect the endpoint first to confirm it exists and to discover the
`dedicatedEndpointDns` (if dedicated):

```bash
gcloud ai endpoints describe $ENDPOINT_ID
```

If the endpoint ID or the dataset bucket doesn't exist, **stop and ask the
user** for a valid value — don't propose a confirmation prompt with broken
inputs.

```bash
python3 scripts/endpoint_evaluation.py \
    --project_id=$PROJECT_ID \
    --location=$LOCATION_ID \
    --endpoint_id=$ENDPOINT_ID \
    --dataset=gs://your-bucket/eval.jsonl \
    --metrics "GENERAL_QUALITY"
```

With a dedicated DNS:

```bash
python3 scripts/endpoint_evaluation.py \
    --project_id=$PROJECT_ID \
    --location=$LOCATION_ID \
    --endpoint_id=$ENDPOINT_ID \
    --dataset=gs://your-bucket/eval.jsonl \
    --dedicated_endpoint_dns=$DEDICATED_ENDPOINT_DNS \
    --metrics "GENERAL_QUALITY"
```

### 3.2. Model-as-a-Service (MaaS)

For MaaS models, no endpoint deploy is needed — call the model by ID:

```bash
python3 scripts/maas_evaluation.py \
    --project_id=$PROJECT_ID \
    --location=$LOCATION_ID \
    --model_id=$MAAS_MODEL_ID \
    --dataset=gs://your-bucket/eval.jsonl \
    --metrics "GENERAL_QUALITY"
```

Same input-validation rule as 3.1: if the bucket doesn't resolve, stop and ask
the user.

## 4. Feed Results Back Into the Flywheel

Both scripts print `summary_metrics` and the first 5 rows of `metrics_table`. To
persist the full result for Stage 4/5 analysis, capture the returned
`eval_result` and serialize it the same way as the main SKILL.md "Always persist
the result" block. Then:

-   `scripts/inspect_results.py --failing-only` for per-case triage.
-   `scripts/compare_results.py --baseline <prev> --candidate <new>` after a fix
    to confirm the target metric improved and nothing regressed.

The deployment workflow is only Stages 1–3 of the Flywheel. Stages 4 (Analyze
Failures) and 5 (Optimize & Iterate) work identically whether the result came
from a deployed endpoint, a MaaS model, or a direct `client.evals.evaluate(...)`
call.
