---
name: agent-platform-tuning
metadata:
  version: "1.0.2"
  category: AiAndMachineLearning
description: >-
  Agent Platform Model Tuning. Use when you need to fine-tune open models
  or Gemini models using Agent Platform infrastructure. Don't use for model
  training outside Agent Platform, model deployment to endpoints (use
  `agent-platform-deploy`), or managing serving endpoints (use
  `agent-platform-endpoint-management`).
---

# Agent Platform Model Tuning

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` and append the
attribution suffix to `User-Agent` headers:

```text
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-tuning)"
User-Agent: <existing_user_agent> agent-skills/1.0 (skill:agent-platform-tuning)
```

## Overview

This skill provides procedural knowledge for fine-tuning Large Language Models
(both Open Models and Gemini Models) using Agent Platform's tuning service. It
covers the entire lifecycle from environment setup and data preparation to job
configuration, monitoring, and deployment.

## Workflow Decision Tree

1.  **Project & Region Verification Check**: Has the user provided the Google
    Cloud project and region?

    -   **No** → **STOP tool execution immediately**. Do NOT run verification
        commands (`gcloud services list`, `gcloud projects get-iam-policy`), do
        NOT create resources, and do NOT begin dataset preparation. Prompt the
        user to specify or confirm the project and region (e.g. "Could you
        please specify which Google Cloud project and region you would like to
        use?").
        -   If the user's inquiry is solely to check or verify environment
            readiness (APIs, IAM, service agents), ask ONLY for the project and
            region. Do NOT ask for the model category.
        -   If the user is requesting a tuning workflow and also omitted whether
            they want to tune an Open Model or a Gemini Model, you may ask both
            questions together.
    -   **Yes** → Proceed.

2.  **Model Category Identification**: Has the user explicitly stated whether
    they want to tune an **Open Model** or a **Gemini Model**?

    -   **No** →
        -   **EXCEPTION for Environment Verification Inquiries:** If the user is
            only asking to check or verify that the environment, APIs, IAM
            permissions, or service agents are ready for tuning, do NOT ask for
            the model category. Verify the environment once the project and
            region are known and confirm readiness.
        -   Otherwise, **STOP tool execution**. Ask the user if they want to
            tune an Open Model or a Gemini Model. **General Setup and
            Prerequisite Inquiries (e.g., "What environment setup is
            needed?"):** If the user asks what environment setup, prerequisites,
            APIs, or permissions are needed to start fine-tuning, and has not
            yet chosen a model category:
        *   Describe the setup requirements (APIs, IAM permissions/service
            agents, and Python SDKs).
        *   Regarding Cloud Storage: state that an existing Cloud Storage bucket
            is needed for datasets and artifacts (e.g.,
            `gs://<existing-bucket>`). **CRITICAL:** Do NOT instruct the user to
            create a bucket, do NOT output a `gcloud storage buckets create`
            command in setup instructions, and do NOT assume a non-existent
            bucket exists (users may not have bucket creation permissions and
            will provide their own existing bucket).
        *   You MUST explicitly conclude your prose response with the direct
            question: **"Would you like to tune an Open Model or a Gemini
            Model?"** (do NOT bury this choice inside a bulleted "Suggested Next
            Steps" list). Never provide setup instructions without explicitly
            asking this question in prose. (Note: if they ask to actively check
            or verify a project whose ID or region is missing, ask for the
            project and region first without running tool calls).
    -   If the user provides a specific tuning purpose, you should recommend
        three models: one Open Model, one Gemini Model, and a third generally
        recommended choice. Briefly list the pros and cons of each (e.g., Gemini
        models might be more expensive, etc.). **CRITICAL:** You must read
        `references/models.md` during this step and only recommend models
        explicitly listed in that catalog. Never recommend uncataloged or
        unsupported models like `google/gemma-2-9b-it`, `gemma-2`, or `Mistral`
        — only recommend supported models such as Gemma 3
        (`google/gemma3@gemma-3-12b-it`), Qwen 3 (`qwen/qwen3@qwen3-8b`), or
        Llama 3.1 (`meta/llama3_1@llama-3.1-8b`). For Gemini models, ONLY
        recommend `gemini-2.5-flash` (recommended for general/coding/chat) or
        `gemini-2.5-pro`. Never recommend `gemini-1.5-flash-002`,
        `gemini-1.5-pro-002`, or `gemini-1.5-flash`, which are deprecated and
        unsupported by the tuning service. If the user names a model that is not
        in the catalog, follow the fallback rule in that catalog. Do not proceed
        with model configuration until the category is confirmed.
    -   **Distillation requests**: If the user asks to distill a model, names a
        teacher model, or wants a smaller model to learn from a larger one, this
        is an Open Model workflow using distillation. Read "Distillation" in
        `references/models.md` and use only the teacher and student models
        listed there.
    -   **Yes** → Proceed.

3.  **Environment Check**: Has the environment (Auth, APIs, IAM, Venv) been
    initialized?

    -   **No** → Go to [Phase 0: Environment & IAM Setup](#phase-0).
    -   **Yes** → Proceed.

4.  **Dataset Status**: Is the dataset ready in JSONL format, **is its structure
    valid for tuning**, and is it uploaded to Google Cloud Storage?

    ```
    -   **No** → Go to [Phase 1: Dataset Preparation & Upload](#phase-1).
    -   **Yes** → Proceed.
    ```

5.  **Column Selection Confirmation**: Have you presented the columns to the
    user and confirmed the mapping?

    -   **No** → **STOP**. You must show samples and get user confirmation on
        column mapping as described in Phase 1.0 before proceeding.
    -   **Yes** → Proceed.

6.  **Configuration**: Has the user provided the target model and
    hyperparameters, or explicitly agreed to your recommendations?

    -   **No** → Go to
        [Phase 2: Model Configuration & Recommendation](#phase-2).
    -   **Yes** → Proceed.

7.  **Job Status**: Has the tuning job been submitted?

    ```
    -   **No** → Go to
        [Phase 3: Tuning Job Execution](#phase-3-tuning-job-execution).
    -   **Yes** → Proceed.
    ```

8.  **Job Completion**: Is the tuning job complete?

    ```
    -   **No** → Go to [Phase 4: Monitoring](#phase-4-monitoring).
    -   **Yes** → Proceed.
    ```

9.  **Deployment**: Has the tuned model been deployed (if required)?

    ```
    -   **No** → Go to [Phase 5: Model Deployment](#phase-5-model-deployment).
    -   **Yes** → Task Complete.
    ```

## Phase 0: Environment & IAM Setup {#phase-0}

Ensure the foundational environment is ready before proceeding.

### 0.1 Authentication & Project Context

-   Check if `gcloud` CLI is installed. If it is not installed, prompt the user
    for permission to install it before proceeding. If it is installed, update
    it:

```bash
gcloud components update --quiet > /dev/null 2>&1
```

-   Verify `gcloud auth list`. If not authenticated, run `gcloud auth login`.
-   **Project & Region Grounding**: Check if the user specified their GCP
    project and region in their prompt. If the user's prompt omits either the
    project or the region (e.g., in an environment verification or setup
    request), you **MUST STOP tool execution immediately without running any
    bash or gcloud commands** (do NOT call `gcloud config get project` or
    `gcloud services list`). Ask the user to provide their project ID/number and
    region.
-   Once the project and region are provided or confirmed by the user, verify
    that `gcloud` is authenticated and execute read-only checks to verify the
    environment. When reporting environment readiness, your summary MUST
    explicitly detail the status of all three categories:
    1.  **Required APIs**: explicitly report that both
        `aiplatform.googleapis.com` (Agent Platform) and
        `storage.googleapis.com` (Cloud Storage) are enabled.
    2.  **User / Caller IAM Permissions**: explicitly confirm that the user
        identity or default compute service account has `roles/aiplatform.user`
        and `roles/storage.admin` (or `roles/storage.objectAdmin`).
    3.  **Service Agents & Roles**: explicitly report that the Agent Platform
        Service Agent
        (`service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`) has
        `roles/aiplatform.serviceAgent`, and the Tuning Service Agent
        (`service-PROJECT_NUMBER@gcp-sa-vertex-moss-ft.iam.gserviceaccount.com`
        or `gcp-sa-vertex-tune`) has `roles/aiplatform.tuningServiceAgent`.
        Always explicitly state the verified project and region (e.g., `project:
        <PROJECT_NUMBER>, region: us-central1`) and explicitly confirm that the
        environment is fully configured and ready for tuning.

### 0.2 Location

Location handling **depends on the model category** you established in the
workflow decision tree. The two categories have different supported locations —
never apply one category's locations to the other.

-   **Open models** share one fixed location set, and `global` is the
    recommended choice.
-   **Gemini models** differ per model and must be looked up. `global` is not
    accepted for them today.

If the user names a location that is not valid for their model and category,
STOP. Respond with an error naming the requested location as unsupported, list
the locations that are valid, and do NOT ask for a dataset, do NOT proceed with
any other setup step, and do NOT silently retry elsewhere.

#### Open Models (RECOMMEND: `global`)

**Recommend `global` and confirm it with the user.** Propose it as a single
recommended choice rather than making the user pick a region first, and do not
steer them toward a specific region instead.

These are the only locations available for open model tuning:

-   `global` (the recommended choice)
-   `us-central1`
-   `europe-west4`
-   `us-west1`
-   `us-east5`
-   `asia-southeast1`

The `global` endpoint automatically selects a supported region that has
available capacity, so it is the most likely to be scheduled successfully.
Pinning a region up front restricts the job to that one region's capacity, which
is why `global` is the recommended location for open model tuning.

-   **The user named a location** → use it verbatim, provided it is `global` or
    one of the regions listed above. Do not talk them out of it.
-   **The user asked which locations are supported** → answer the question.
    Share the list above and say that `global` is recommended and why. Never
    withhold it.
-   **The user did not name a location** → propose `global` and ask them to
    confirm it before you proceed. Say that `global` lets the service pick a
    region with available capacity. Do NOT silently assume `global`.

The point of proposing a single choice is to avoid making region selection a
decision the user must resolve before anything else can happen — that ordering
is what previously blocked people. It is not a reason to hide the list: quote it
whenever the user asks, and quote it when rejecting an unsupported location.

Fall back to an explicit region **only** in the cases below, and tell the user
why you are doing so:

-   **CMEK.** Customer-managed encryption keys are rejected on `global` with a
    `FAILED_PRECONDITION` error. A CMEK-protected job must name the region that
    holds the key.

-   **Data residency.** If the user requires the job to stay in a specific
    jurisdiction, honor their region. `global` currently runs the job in either
    `us-central1` or `europe-west4`.

If a `global` job is accepted but then fails with a `FAILED_PRECONDITION` error
saying the model does not support global endpoint tuning, that model is not
onboarded to the global endpoint yet. The model itself is still tunable:
resubmit once in an explicit region from the list above (`us-central1` is the
safest choice) and tell the user why you switched.

##### Working with a `global` job

-   The API host stays `aiplatform.googleapis.com`. There is no
    `global-aiplatform.googleapis.com` host.
-   The service resolves `global` to a real region at run time. Sub-resources
    (the tuned model, checkpoints, TensorBoard) come back with that **real**
    region in their resource names, not `global`. Read the location out of the
    returned resource name before using it for monitoring or deployment; never
    assume it is still `global`.
-   Quota is shared across regions, so pinning a region does not grant extra
    quota.

#### Gemini Models (per-model, look it up)

`global` is **not accepted for Gemini tuning today** — the service rejects it at
job creation with a `FAILED_PRECONDITION` error, so do not propose it here.

**There is no single region allowlist for Gemini.** Supported tuning regions
vary by model and by model version: some Gemini models are restricted to two
regions while others support many more. Do NOT reuse the open model list above,
and do NOT assume a region carries over from another Gemini model.

Before submitting, look up the chosen model in the supervised fine-tuning
documentation and read its **"Supported endpoint for model tuning"**
row:
[supervised tuning](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/supervised-tuning)


-   **The user asked which regions are supported** → look up that specific model
    and tell them what the docs say. Do not answer from memory or from the open
    model list, and do not answer for a different Gemini model.
-   **The model's row names specific regions** → the user's region must be one
    of them. If it is not, STOP and report the supported regions for that model.
-   **The model's row is absent or the docs are unclear** → ask the user for the
    region rather than guessing one.

Confirm the region with the user before proceeding. Note that some Gemini models
also restrict CMEK and serve tuned models only on the `us` and `eu` multi-region
endpoints, so check the same table for those limits before promising them.

### 0.3 Enable APIs

Ensure `aiplatform.googleapis.com` and `storage.googleapis.com` are enabled.

```bash
gcloud services enable aiplatform.googleapis.com storage.googleapis.com \
    --project=YOUR_PROJECT
```

### 0.4 IAM Permissions

Verify the following identities have the required roles.

-   **Agent Platform Service Agent**:
    `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`
-   **Managed OSS Fine Tuning Service Agent**:
    `service-PROJECT_NUMBER@gcp-sa-vertex-moss-ft.iam.gserviceaccount.com`
-   **User Identity**: The account running the commands.

### 0.5 Python Dependencies

The scripts in this skill import `vertexai` (from `google-cloud-aiplatform`),
`google-genai`, `google-cloud-storage`, and `datasets`.

**CRITICAL AGENT INSTRUCTION:** Do **not** create a virtual environment, and do
not install anything before checking. A venv starts empty and hides packages the
environment already provides, forcing a redundant several-minute install.

Probe first and install only if the probe fails:

```bash
python3 -c "import vertexai, google.genai, google.cloud.storage, datasets" \
  || pip install -r references/requirements.txt
```

Then run every script with a plain `python3 scripts/...` — no activation prefix.

The `references/requirements.txt` pins are a fallback for an environment that
does not already provide these SDKs. Do not apply them on top of a working
environment: they would downgrade packages other tools may share.

## Phase 1: Dataset Preparation & Upload {#phase-1}

### 1.0 Dataset Discovery & Confirmation

-   **User-Provided Dataset Verification:** If the user specifies a dataset
    filename or path in their prompt, verify its existence in the workspace
    (e.g. via script execution or checking for typos).
    *   **If the file cannot be found anywhere**, you **MUST** inform the user
        that the dataset file does not exist or cannot be accessed. You **MUST**
        prompt the user to provide a valid dataset path. Alternatively, if
        candidate dataset files are found in the workspace during your search,
        you **MUST** present the candidates to the user and ask them to select
        one. You **MUST** stop tool execution immediately after reporting the
        missing file or presenting candidates, and wait for the user's response.
        Do **NOT** ask for 90/10 validation split permission, and do **NOT**
        attempt to upload the dataset before receiving a valid dataset file
        selection from the user.
    *   **If the file is found and verified**, proceed to Step 1.1 Formatting &
        Validation below.
-   **Auto-Discovery: From User Bucket:** If the user does not have a dataset
    and no suitable alternative is found in the Hugging Face reference, offer to
    search the user's GCS buckets for potential training data. Prioritize
    searching for files with extensions like `.jsonl`, `.json`, `.csv`, and
    `.parquet`. If such files are found, read the first few lines/records of
    each to determine if they contain text-based data suitable for tuning (e.g.,
    prompt/completion pairs) that can be modified to follow
    [Data Preparation Guide](references/data_prep.md) and is related to the
    tuning task requested. **DO NOT** search without prompting first.
-   **Auto-Discovery: From Task to Huggingface:** If the user has a specific
    task (e.g. math reasoning, coding, instruction following) or wants to use a
    Hugging Face dataset without naming a specific one, refer to
    [Huggingface Datasets Reference](references/hf_datasets.md) and recommend
    matching datasets (e.g., `open-r1/OpenR1-Math-220k` or
    `AI-MO/NuminaMath-TIR` for mathematical reasoning; `openai/gsm8k` is also
    widely used). For each dataset recommended, provide some information about
    the dataset and provide some reasonable splits, and ask the user to select
    one. Do NOT output generic instructions telling the user to prepare and
    upload their own data — proactively guide the interactive dataset discovery,
    preview, and preparation flow.

    > [!IMPORTANT] **CRITICAL: Ask for Confirmation and Column Selection.** Once
    > the dataset is selected, execute Python via `run_command` to inspect the
    > dataset using `load_dataset(..., streaming=True)`. Do not proceed with
    > dataset preparation or upload until you perform the following steps and
    > get user confirmation: 1. **Dataset and Split Confirmation:** Present the
    > dataset and available splits to the user and have them confirm which to
    > use. 2. **Column Selection (Hugging Face or Custom Datasets):** You
    > must: - Provide a list of all available columns in the selected dataset
    > split. - **Show a few samples from the dataset** to help the user
    > understand the content and make the choice of columns. - Recommend which
    > columns should be mapped to `prompt` (or user message) and `completion`
    > (or assistant response), offering a few reasonable options if
    > applicable. - Ask the user to confirm the column mapping or specify which
    > columns to use.

    For distillation, map only the prompt column. The teacher model writes the
    responses, so no completion column is needed.

### 1.1 Formatting & Validation

-   **Conversion**: If data is in CSV, JSON, or Parquet, use
    `scripts/prepare_dataset.py` to convert.
-   **Validation Split Confirmation**: Except for prompt-only distillation data
    (next bullet), whenever generating or preparing a single dataset without an
    explicit validation set (including when generating sample chat/instruction
    datasets or preparing training datasets), you MUST generate or process the
    data using Python via `run_command` and **you MUST prompt the user** to seek
    permission to split the training dataset 90/10 to form a validation dataset
    (using `--validation_split 0.1` or Python script). If they agree, proceed
    with the split. If they decline, just use the training dataset without a
    validation dataset. Do **NOT** offer an 80/20 split; the tuning service
    rejects it, for the reason given in
    the
    [Data Preparation Guide](references/data_prep.md#sizing-the-validation-split).
 Do NOT proceed to upload the dataset or
    submit the tuning job before asking the user about the 90/10 validation
    split!
-   **Distillation training data**: Convert with `--prompt_only` and no
    `--completion_col`; see the
    [Data Preparation Guide](references/data_prep.md#distillation-datasets). Do
    **NOT** offer the 90/10 split for a prompt-only file: the split would have
    no responses, and a validation dataset must include them. Validation is
    optional for distillation; use one only if the user has separate data with
    responses, and convert it the normal way.
-   **Validation**: If data is already in JSONL, validate it before uploading.
    Simply having a `.jsonl` extension is not enough. You must verify that the
    content schema is valid for tuning (e.g. correct system/user/model roles).

```bash
python3 scripts/prepare_dataset.py \
    --input my_data.jsonl \
    --format <messages|messages_gemini> \
    --validate_only
```

*(Use `--format messages` for open models and `--format messages_gemini` for
Gemini models.)* - Refer to [Data Preparation Guide](references/data_prep.md)
for required schemas.

### 1.2 Upload

Upload formatted `.jsonl` files (both training and validation splits, if
applicable) to GCS using a unique directory (e.g., with a datetime timestamp) to
avoid overwriting outputs from different runs. If the user named a bucket (e.g.,
`gs://mybucket`), use that bucket name EXACTLY as provided (verbatim) and NEVER
prepend the project ID or modify the bucket name. Upload local `.jsonl` splits
to an existing bucket via `google.cloud.storage.Client` in Python (do NOT create
a missing bucket unprompted here; see Phase 3 if a bucket needs to be proposed
and confirmed):

```python
from google.cloud import storage

storage_client = storage.Client(project=PROJECT)
bucket = storage_client.bucket(BUCKET_NAME)
bucket.blob(f"tuning_agent_job_{TIMESTAMP}/train.jsonl").upload_from_filename(
    "/tmp/train.jsonl"
)
if VAL_DATASET_PATH:
    bucket.blob(f"tuning_agent_job_{TIMESTAMP}/val.jsonl").upload_from_filename(
        VAL_DATASET_PATH
    )
```

## Phase 2: Model Configuration & Recommendation {#phase-2}

Help the user choose the best model and parameters. **Always seek user
confirmation before submitting the job.**

-   If the user does not specify a specific model in their prompt, calculate
    recommendations based on the **Models Catalog**.
-   **Prompt for Confirmation:** Present the recommended model to the user and
    ask for their confirmation before configuring hyperparameters.

### 2.1 Configuration

#### For Open Models

-   Recommend `tuning_mode`, `epochs`, `learning_rate`, and `adapter_size` based
    on the [Tuning Guide](references/tuning_guide.md) and model-specific
    baselines in the [Models Catalog](references/models.md).

#### Verify the Live Model ID

Before submitting the job, run `scripts/list_models.py` and pick `--base_model`
only from its `models` output. Do not invent IDs or version numbers.

```bash
python3 scripts/list_models.py --project YOUR_PROJECT --filter gemini
```

Output: `{"models": [...], "total_count": N, "truncated": bool}`.

-   For Gemini, strip `google/` and `@default` (e.g.
    `google/gemini-2.5-flash@default` → `gemini-2.5-flash`); for open models,
    pass `publisher/family@version` as-is.
-   Skip Gemini variants ending in `-embedding`, `-tts`, `-image`,
    `-computer-use`, or `-native-audio`; they are not tunable.
-   If `truncated` is `true`, re-run with a tighter `--filter` (e.g.
    `gemini-2.5`) before deciding the target version is unavailable.
-   If `models` is empty, stop and ask the user.

### 2.2 Calculating Cost (Open Models Only)

> [!WARNING] **CRITICAL: Always Use `run_command` with
> `scripts/calculate_cost.py`** Do **NOT** call the `estimate_cost` ADK tool for
> model tuning. The `estimate_cost` tool only supports specific endpoint serving
> pricing and will fail with `Unsupported request type` on tuning requests. You
> **MUST** call the `run_command` tool to execute Python code or
> `scripts/calculate_cost.py` (or
> `/workspace/skills/agent-platform-tuning/scripts/calculate_cost.py`) to
> calculate the cost. Whenever a model is chosen or the user switches models
> (e.g. from Llama to Gemma), you **MUST** call `run_command` to calculate or
> recalculate the cost before presenting the dry-run confirmation prompt. Always
> report the calculated dollar figure (e.g., `Estimated tuning cost: $X.XX`) in
> the dry-run confirmation prompt.

-   We calculate the estimated cost of tuning based on the dataset and the
    selected model in the [Models Catalog](references/models.md):

    ```bash
    python3 scripts/calculate_cost.py \
        --input my_data.jsonl \
        --model MODEL_NAME \
        --tuning_mode TUNING_MODE \
        --epochs epochs
    ```

    `--model` takes either the display name (`Qwen 3 8B`) or the same resource
    name you pass to `--base_model` (`qwen/qwen3@qwen3-8b`), so the value chosen
    in Step 2.1 can be reused as-is.

> [!NOTE] **Distillation cost:** `scripts/calculate_cost.py` counts only the
> text in the dataset. For a prompt-only distillation dataset it leaves out the
> teacher's responses, which the student also trains on, and it does not include
> the teacher model calls, which are billed separately at the teacher's
> managed-model price. Present the figure as a lower bound.

> [!NOTE] **Handling Missing Dataset Errors:** If `scripts/calculate_cost.py`
> fails because the dataset file (e.g. `my_data.jsonl` or `dummy_data.jsonl`)
> cannot be found, you **MUST** inform the user that the dataset file does not
> exist or cannot be accessed. You **MUST** prompt the user to provide a valid
> dataset path, and stop tool execution immediately to wait for their response.
> Do **NOT** retry or loop, do **NOT** invent a specific cost number, and do
> **NOT** prompt for job submission approval before receiving a valid dataset
> from the user.

-   **Prompt for Confirmation:** Present the recommended hyperparameter
    configuration and estimated cost (with the concrete dollar figure calculated
    above) to the user and ask for their approval before proceeding to job
    submission. Make sure to note that the estimated cost is just an estimate
    and can vary from actual billing costs.

## Phase 3: Tuning Job Execution {#phase-3-tuning-job-execution}

**CRITICAL Pre-Flight Check (GCS Verification):** Before you propose a
confirmation prompt or submit any tuning job, you **MUST** verify that the
specified training dataset GCS URI (e.g. `gs://dummy_bucket/dataset.jsonl` or
`gs://YOUR_BUCKET/...`) actually exists and is accessible. Run `gcloud storage
ls $DATASET_URI` (or `gsutil ls`).

*   **If the verification fails** (e.g. `BucketNotFound`, `404`, `AccessDenied`,
    or indicating a dummy/missing bucket), you **MUST** inform the user that the
    GCS bucket or dataset does not exist or cannot be accessed. You **MUST**
    prompt the user to provide a valid GCS URI for the dataset, and stop tool
    execution immediately to wait for their response. Do **NOT** propose a
    confirmation prompt and do **NOT** execute any tuning scripts before
    receiving a valid dataset URI from the user.
*   **If the verification succeeds**, proceed to propose the confirmation prompt
    below.

### For Gemini Models

Submit the Gemini supervised fine-tuning job using the Python SDK
(`google.genai` or `vertexai.tuning.sft`):

```python
from google import genai
from google.genai import types

client = genai.Client(enterprise=True, project=PROJECT, location=LOCATION)
tuning_job = client.tunings.tune(
    base_model=BASE_MODEL,  # e.g. "gemini-2.5-flash"
    training_dataset=types.TuningDataset(gcs_uri=TRAIN_DATASET_URI),
    config=types.CreateTuningJobConfig(
        epoch_count=EPOCHS,  # e.g. 3
        learning_rate_multiplier=LEARNING_RATE_MULTIPLIER,  # e.g. 1.0
        validation_dataset=(
            types.TuningValidationDataset(gcs_uri=VAL_DATASET_URI)
            if VAL_DATASET_URI
            else None
        ),
    ),
)
print("Tuning Job Resource Name:", tuning_job.name)
```

Alternatively using `vertexai.tuning.sft`:

```python
import vertexai
from vertexai.tuning import sft

vertexai.init(project=PROJECT, location=LOCATION)
job = sft.train(
    source_model=BASE_MODEL,
    train_dataset=TRAIN_DATASET_URI,
    validation_dataset=VAL_DATASET_URI,
    epochs=EPOCHS,
    learning_rate_multiplier=LEARNING_RATE_MULTIPLIER,
)
print("Tuning Job Resource Name:", job.resource_name)
```

Execute the Python script via `python3` (inline or written to
`/tmp/submit_gemini_tuning.py`). Report the returned operation name or trackable
resource identifier, and do NOT wait for the terminal state.

### For Open Models

Submit the open model tuning job using `scripts/tune_open_model.py` or the
Python SDK. Identify the model id using available models documentation
at
[documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/open-model-tuning#supported-models).


`--base_model` takes a publisher model **resource name**
(`{publisher}/{model_id}@{version_id}`), not the display name shown in the
catalog. See "Model Resource Name Format" in `references/models.md` for the
format, verified examples, and how to look up a name you do not have.

Using `scripts/tune_open_model.py`:

```bash
python3 scripts/tune_open_model.py \
    --project YOUR_PROJECT \
    --location global \
    --base_model BASE_MODEL_ID \
    --train_dataset gs://YOUR_BUCKET/tuning_agent_job_<datetime>/train.jsonl \
    --output_uri gs://YOUR_BUCKET/tuning_agent_job_<datetime>/output \
    --epochs EPOCHS \
    --learning_rate LR \
    --tuning_mode MODE
```

*(Run `scripts/tune_open_model.py`, which maps `--tuning_mode` (`FULL` /
`PEFT_ADAPTER`) to `types.TuningMode`, sets adapter sizes and labels, and passes
`output_uri` into `CreateTuningJobConfig(output_uri=...)`.)*

This script is open model only, and `--location` falls back to `global` if
omitted. Always pass the location the user confirmed in section 0.2 explicitly,
so it is visible in the command string you present for approval. If job
submission fails (e.g., due to a missing or invalid parameter), report the error
verbatim and present a fresh confirmation prompt showing the updated command
before resubmitting.

#### Distillation

Add `--method DISTILLATION` and `--teacher_model`. `--base_model` is the
student. Use only the teacher and student models listed under "Distillation" in
`references/models.md`.

```bash
python3 scripts/tune_open_model.py \
    --project YOUR_PROJECT \
    --location global \
    --method DISTILLATION \
    --teacher_model TEACHER_MODEL_ID \
    --base_model STUDENT_MODEL_ID \
    --train_dataset gs://YOUR_BUCKET/tuning_agent_job_<datetime>/prompts.jsonl \
    --output_uri gs://YOUR_BUCKET/tuning_agent_job_<datetime>/output \
    --epochs EPOCHS \
    --learning_rate LR \
    --tuning_mode MODE
```

-   The training dataset can contain prompts only; the teacher writes the
    responses. A validation dataset must include responses.
-   Teacher calls draw on the project's quota for the teacher model.
-   The job writes the teacher-labeled data to
    `distillation_labelled_dataset.jsonl` in the output directory.

> [!WARNING] **`--output_uri` / `output_uri` is required for open models.** The
> Python SDK declares it as `output_uri: Optional[str] = None`, but the tuning
> backend rejects open model jobs that omit it with `INVALID_ARGUMENT: The
> output_uri field is required for this model.` Treat the SDK's "optional"
> signature as wrong here and always pass a GCS destination (`output_uri`) both
> in CLI flags and in `CreateTuningJobConfig(output_uri=...)`.

Because the flag is mandatory, you must establish where the tuned model is
written before you can submit. **Never invent a bucket name, derive one from the
project number, or run `gcloud storage buckets create` unprompted.** Creating a
bucket is a mutating action and is subject to the Tier M confirmation policy
below.

-   **The user named a bucket or URI** → use it EXACTLY as specified by the user
    (verbatim), appending a unique per-job directory as in section 1.2.
    **CRITICAL:** NEVER alter, prefix, or prepend the project number or anything
    else to a user-specified bucket name! Even if `gcloud storage buckets list`
    shows an existing bucket with a project-prefixed name (e.g.
    `gs://PROJECT-mybucket` when the user asked for `gs://mybucket`), you MUST
    use the user's exact bucket name `gs://mybucket` verbatim. Never silently
    substitute an existing bucket.
-   **A bucket was already used for the dataset upload in section 1.2** →
    propose reusing it for the output and ask the user to confirm.
-   **Neither or user states they have no bucket** → Check existing buckets in
    the project (`gcloud storage buckets list --project=PROJECT`) or offer to
    create a dedicated bucket. When proposing a bucket to create, ensure the
    bucket name is unique by including a unique suffix or timestamp (e.g.
    `gs://PROJECT-tuning-$(date +%s)` or
    `gs://PROJECT-tuning-artifacts-<timestamp>` in LOCATION) to prevent HTTP 409
    collisions with previously created buckets. Propose the destination bucket
    in your configuration dry-run preview and ask the user for confirmation
    before proceeding.

> [!IMPORTANT] **Interactive Confirmation Required (Tier M):** Before proceeding
> with job submission, you **MUST** present the proposed command string showing
> all literal flags (including `--output_uri` for open models and estimated
> cost) in a confirmation prompt to the user with 'Yes' and 'No' options. Do NOT
> execute the tuning job submission via `run_command` in the same turn as
> presenting the confirmation prompt; yield immediately for the user's reply.

## Phase 4: Monitoring {#phase-4-monitoring}

Monitor the job via the Cloud Console link provided in the script output.
`--location` is required and must be the same location you submitted with: an
open model job submitted on `global` is polled with `--location global`, even
though the work runs in a real region behind the scenes.

Additionally, ask the user if they want you to monitor the job status for them
in the background. If they agree, execute `scripts/monitor_tuning_job.py` as a
background task to periodically poll the job status and notify the user to show
the status. If the user declines, leave it completely to the user to check on
the status.

## Phase 5: Model Deployment {#phase-5-model-deployment}

Once the tuning job is `SUCCEEDED`, deploy the tuned checkpoint by registering
it in Model Registry with the base model's serving container, then deploying
that registered model to a new endpoint. **CRITICAL:** If the tuning job is
still pending/running (`tuned_model_name` is `None` or not yet generated),
**NEVER deploy the untuned base model (e.g., `google/gemma3@...`) as a
substitute!** Instead, explicitly inform the user that deployment of the tuned
model cannot proceed until the tuning job finishes (`JOB_STATE_SUCCEEDED`) and
generates the tuned model artifact.

Deployment requires a real region — `global` is not valid here. If the job ran
on `global`, read the region out of the tuned model's resource name
(`projects/.../locations/<REGION>/models/...`) and deploy there; do not guess.

If a deploy step is rejected for quota, report the API's error verbatim.

```bash
#!/bin/bash
# Deploy a tuned checkpoint by registering it in Model Registry with the base
# model's serving container, then deploying to a new endpoint. All four gcloud
# calls hit aiplatform.googleapis.com.
set -euo pipefail
PROJECT_ID="YOUR_PROJECT"
LOCATION_ID="YOUR_LOCATION"          # e.g. us-central1; NOT global.
BASE_MODEL="<PUBLISHER>/<FAMILY>@<VERSION-ID>"   # the base model you tuned; e.g. google/gemma3@gemma-3-4b-it
ARTIFACTS="gs://YOUR_BUCKET/tuning_agent_job_<datetime>/output/postprocess/node-0/checkpoints/final"
DISPLAY_NAME="my-tuned-model"
# Explicit IDs, so no step can pick up an older model or endpoint that shares
# the display name.
RUN_ID="tuned-$(date +%Y%m%d-%H%M%S)"

# 1. List the base model's verified deployment configs and pick the row that
#    fits the user-approved cost/perf. CONFIG_INDEX is its 0-based table row.
gcloud ai model-garden models list-deployment-config \
    --model="$BASE_MODEL" \
    --project="$PROJECT_ID"
CONFIG_INDEX="<pick from step 1>"

# Turn that row into gcloud flags files. The table shows only the image, but
# the container also needs the row's args, env, ports and routes; its
# --model/--model-path arg points at the base weights and is repointed at
# $ARTIFACTS.
gcloud ai model-garden models list-deployment-config \
    --model="$BASE_MODEL" \
    --project="$PROJECT_ID" \
    --format=json | python3 -c '
import json, sys
idx, artifacts = int(sys.argv[1]), sys.argv[2]
cfg = json.load(sys.stdin)[idx]
spec = dict(cfg["containerSpec"])
args, repointed = [], 0
for a in spec.pop("args", []):
    flag = a.split("=", 1)[0]
    if flag in ("--model", "--model-path"):
        a, repointed = flag + "=" + artifacts, repointed + 1
    args.append(a)
if repointed != 1:
    sys.exit("expected exactly one --model/--model-path arg, found %d" % repointed)
upload = {"--container-image-uri": spec.pop("imageUri"), "--container-args": args}
if "command" in spec:
    upload["--container-command"] = spec.pop("command")
if "env" in spec:
    upload["--container-env-vars"] = {e["name"]: e["value"] for e in spec.pop("env")}
if "ports" in spec:
    upload["--container-ports"] = [str(p["containerPort"]) for p in spec.pop("ports")]
for key, flag in (("predictRoute", "--container-predict-route"),
                  ("healthRoute", "--container-health-route"),
                  ("sharedMemorySizeMb", "--container-shared-memory-size-mb")):
    if key in spec:
        upload[flag] = str(spec.pop(key))
if "deploymentTimeout" in spec:  # e.g. "7200s"
    upload["--container-deployment-timeout-seconds"] = str(
        int(float(spec.pop("deploymentTimeout").rstrip("s"))))
if spec:
    sys.exit("unhandled containerSpec fields: %s" % sorted(spec))
m = cfg["dedicatedResources"]["machineSpec"]
deploy = {"--machine-type": m["machineType"]}
if "acceleratorType" in m:
    deploy["--accelerator"] = {
        "type": m["acceleratorType"].lower().replace("_", "-"),
        "count": str(m.get("acceleratorCount", 1))}
json.dump(upload, open("/tmp/upload_flags.yaml", "w"), indent=1)
json.dump(deploy, open("/tmp/deploy_flags.yaml", "w"), indent=1)
' "$CONFIG_INDEX" "$ARTIFACTS"
cat /tmp/upload_flags.yaml /tmp/deploy_flags.yaml

# 2. Register the tuned checkpoint in Model Registry with the base model's
#    serving container. Blocks until the upload finishes.
gcloud ai models upload \
    --project="$PROJECT_ID" \
    --region="$LOCATION_ID" \
    --model-id="$RUN_ID" \
    --display-name="$DISPLAY_NAME" \
    --artifact-uri="$ARTIFACTS" \
    --flags-file=/tmp/upload_flags.yaml

# 3. Create a dedicated endpoint.
gcloud ai endpoints create \
    --project="$PROJECT_ID" \
    --region="$LOCATION_ID" \
    --endpoint-id="$RUN_ID" \
    --display-name="$DISPLAY_NAME"

# 4. Deploy the registered model to the endpoint.
gcloud ai endpoints deploy-model "$RUN_ID" \
    --project="$PROJECT_ID" \
    --region="$LOCATION_ID" \
    --model="$RUN_ID" \
    --display-name="$DISPLAY_NAME" \
    --flags-file=/tmp/deploy_flags.yaml
```

`set -e` stops the sequence at the first failed step. Step 4 blocks until the
model is serving, which can take 20 minutes or more; its progress output prints
the operation name, `projects/<PROJECT>/locations/<REGION>/operations/<OP_ID>`.
Pass that whole name to `gcloud ai operations describe <OPERATION_NAME>` for
status checks from another shell: a bare `<OP_ID>` works only when gcloud has a
project.

> [!IMPORTANT] **Interactive Confirmation Required (Tier M):** Before proceeding
> with deployment, you **MUST** present the three write commands (steps 2-4)
> with all literal values filled in, plus the generated flags files (container
> image, args, machine type, accelerator config), in a confirmation prompt to
> the user with 'Yes' and 'No' options. Do NOT execute the deployment commands
> via `run_command` in the same turn as presenting the confirmation prompt;
> yield immediately for the user's reply.

Refer to [Models Catalog](references/models.md) for hardware recommendations for
specific open models.

## Resources

-   [Data Preparation Guide](references/data_prep.md)
-   [Models Catalog](references/models.md)
-   [Tuning Guide](references/tuning_guide.md)
-   `scripts/prepare_dataset.py`: Data conversion & validation.
-   `scripts/tune_open_model.py`: Open model tuning job submission.
