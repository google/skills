---
name: agent-platform-tuning
description: >-
  Agent Platform Model Tuning. Use when you need to fine-tune open models
  or Gemini models using Agent Platform infrastructure. Don't use for model
  training outside Agent Platform, model deployment to endpoints (use
  `agent-platform-deploy`), or managing serving endpoints (use
  `agent-platform-endpoint-management`).
---

# Agent Platform Model Tuning

## Overview

This skill provides procedural knowledge for fine-tuning Large Language Models
(both Open Models and Gemini Models) using Agent Platform's tuning service. It
covers the entire lifecycle from environment setup and data preparation to job
configuration, monitoring, and deployment.

## Workflow Decision Tree

1.  **Model Category Identification**: Has the user explicitly stated whether
    they want to tune an **Open Model** or a **Gemini Model**?

    -   **No** → **STOP**. Ask the user if they want to tune an Open Model or a
        Gemini Model. **CRITICAL EXCEPTION for Environment Setup Requests:** If
        the user is specifically asking for environment setup instructions (e.g.
        "What environment setup is needed?"), you **MUST** provide the full
        [Phase 0 environment setup](#phase-0) instructions in your initial
        response, *simultaneously* with asking clarifying questions about the
        model category.
    -   If the user provides a specific tuning purpose, you should recommend
        three models: one Open Model, one Gemini Model, and a third generally
        recommended choice. Briefly list the pros and cons of each (e.g., Gemini
        models might be more expensive, etc.). **CRITICAL:** You must read
        `references/models.md` during this step and only recommend models
        explicitly listed in that catalog. Do not recommend unsupported models
        like Mistral. Do not proceed with model configuration until the category
        is confirmed.
    -   **Yes** → Proceed.

2.  **Environment Check**: Has the environment (Auth, APIs, IAM, Venv) been
    initialized?

    -   **No** → Go to [Phase 0: Environment & IAM Setup](#phase-0).
    -   **Yes** → Proceed.

3.  **Dataset Status**: Is the dataset ready in JSONL format, **is its structure
    valid for tuning**, and is it uploaded to Google Cloud Storage?

    -   **No** → Go to [Phase 1: Dataset Preparation & Upload](#phase-1).
    -   **Yes** → Proceed.

4.  **Column Selection Confirmation**: Have you presented the columns to the
    user and confirmed the mapping?

    -   **No** → **STOP**. You must show samples and get user confirmation on
        column mapping as described in Phase 1.0 before proceeding.
    -   **Yes** → Proceed.

5.  **Configuration**: Has the user provided the target model and
    hyperparameters, or explicitly agreed to your recommendations?

    -   **No** → Go to
        [Phase 2: Model Configuration & Recommendation](#phase-2).
    -   **Yes** → Proceed.

6.  **Job Status**: Has the tuning job been submitted?

    -   **No** → Go to
        [Phase 3: Tuning Job Execution](#phase-3-tuning-job-execution).
    -   **Yes** → Proceed.

7.  **Job Completion**: Is the tuning job complete?

    -   **No** → Go to [Phase 4: Monitoring](#phase-4-monitoring).
    -   **Yes** → Proceed.

8.  **Deployment**: Has the tuned model been deployed (if required)?

    -   **No** → Go to [Phase 5: Model Deployment](#phase-5-model-deployment).
    -   **Yes** → Task Complete.

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
-   Ensure `project` and `location` are known. Use `gcloud config get project`
    to retrieve the current project (and `gcloud config get compute/region` for
    region).
-   **CRITICAL: Ask for Confirmation.** You must prompt the user to confirm the
    retrieved project and region before proceeding, in case they want to switch
    to a different one.

### 0.2 Possible Locations

The following locations are available for tuning:

-   us-central1
-   europe-west4
-   us-west1
-   us-east5
-   asia-southeast1

No other values are supported for this section, ensure that the location is
listed above.

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

### 0.5 Virtual Environment

Create and use a virtual environment named `tuning_agent_venv` in the home
directory. Install dependencies from `references/requirements.txt`.

```bash
python3 -m venv ~/tuning_agent_venv
source ~/tuning_agent_venv/bin/activate
pip install -r references/requirements.txt
```

**CRITICAL AGENT INSTRUCTION:** You **MUST** ensure that every Python command or
script execution (e.g., `python3 scripts/...`, `pip install ...`) is prefixed
with the virtual environment activation command: `source
~/tuning_agent_venv/bin/activate &&`. Additionally, advise the user that every
single time they run a Python command, execute a script, or inspect data inline,
they **MUST** also activate this virtual environment first in their bash
execution. For example: `source ~/tuning_agent_venv/bin/activate && python3
...`. Do not run standalone `python3` commands without activating the
environment, as they will encounter `ModuleNotFoundError` issues.

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
        Do **NOT** ask for 80/20 validation split permission, and do **NOT**
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
    task, refer to [Huggingface Datasets Reference](references/hf_datasets.md)
    and recommend a dataset from this if one exists. For each dataset
    recommended, provide some information about the dataset and provide some
    reasonable splits.

    > [!IMPORTANT]
    >
    > **CRITICAL: Ask for Confirmation and Column Selection.** Do not proceed
    > with dataset preparation or upload until you perform the following steps
    > and get user confirmation:
    >
    > 1.  **Dataset and Split Confirmation:** Present the dataset and available
    >     splits to the user and have them confirm which to use.
    > 2.  **Column Selection (Hugging Face or Custom Datasets):** You must:
    >     -   Provide a list of all available columns in the selected dataset
    >         split.
    >     -   **Show a few samples from the dataset** to help the user
    >         understand the content and make the choice of columns.
    >     -   Recommend which columns should be mapped to `prompt` (or user
    >         message) and `completion` (or assistant response), offering a few
    >         reasonable options if applicable.
    >     -   Ask the user to confirm the column mapping or specify which
    >         columns to use.

### 1.1 Formatting & Validation

-   **Conversion**: If data is in CSV, JSON, or Parquet, use
    `scripts/prepare_dataset.py` to convert.
-   **Validation Split Confirmation**: If the user only provides a training
    dataset, **you must prompt the user** to seek permission to split the
    training dataset 80/20 to form a validation dataset (using
    `--validation_split 0.2`). If they agree, proceed with the split. If they
    decline, just use the training dataset without a validation dataset.
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

Upload formatted `.jsonl` files to GCS using a unique directory (e.g., with a
datetime timestamp) to avoid overwriting outputs from different
runs. <!-- disableFinding(LINE_OVER_80) -->

```bash
ARTIFACTS="gs://YOUR_BUCKET/tuning_agent_job_<datetime>/dataset.jsonl" gcloud
storage cp dataset.jsonl $ARTIFACTS
```

<!-- enableFinding(LINE_OVER_80) -->

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

### 2.2 Calculating Cost (Open Models Only)

-   We can calculate a rough estimate of cost of tuning based on the dataset and
    the selected model in the [Models Catalog](references/models.md):

    ```bash
    python3 scripts/calculate_cost.py \
        --input my_data.jsonl \
        --model MODEL_NAME \
        --tuning_mode TUNING_MODE \
        --epochs epochs
    ```

> [!NOTE]
>
> **Handling Missing Dataset Errors:** If `scripts/calculate_cost.py` fails
> because the dataset file (e.g. `my_data.jsonl` or `dummy_data.jsonl`) cannot
> be found, you **MUST** inform the user that the dataset file does not exist or
> cannot be accessed. You **MUST** prompt the user to provide a valid dataset
> path, and stop tool execution immediately to wait for their response. Do
> **NOT** retry or loop, do **NOT** invent a specific cost number, and do
> **NOT** prompt for job submission approval before receiving a valid dataset
> from the user.

-   **Prompt for Confirmation:** Present the recommended hyperparameter
    configuration and estimated cost to the user and ask for their approval
    before proceeding to job submission. Make sure to note that the estimated
    cost is just an estimate and can vary from actual billing costs.

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

Check if `scripts/tune_gemini_model.py` exists.

-   **If `scripts/tune_gemini_model.py` exists:** Submit the Gemini model tuning
    job using this script.

    ```bash
    python3 scripts/tune_gemini_model.py
    ```

-   **If `scripts/tune_gemini_model.py` does not exist:** Instruct the user to
    manually configure and submit the tuning job via the Google Cloud Console UI
    or using the Agent Platform SDK for Python.

### For Open Models

Submit the open model tuning job using `scripts/tune_open_model.py`. Identify
the model id using available models documentation
at <!-- disableFinding(LINE_OVER_80) -->
[documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/open-model-tuning.md.txt).
<!-- enableFinding(LINE_OVER_80) -->

```bash
python3 scripts/tune_open_model.py \
    --project YOUR_PROJECT \
    --location YOUR_LOCATION \
    --base_model BASE_MODEL_ID \
    --train_dataset gs://YOUR_BUCKET/tuning_agent_job_<datetime>/dataset.jsonl \
    --output_uri gs://YOUR_BUCKET/tuning_agent_job_<datetime>/output \
    --epochs EPOCHS \
    --learning_rate LR \
    --tuning_mode MODE
```

> [!IMPORTANT]
>
> **Interactive Confirmation Required (Tier M):** Before proceeding with job
> submission, you **MUST** present the proposed command string showing all
> literal flags in a confirmation prompt to the user with 'Yes' and 'No'
> options.

> **CRITICAL:** When presenting this confirmation prompt to the user, you MUST
> output it as a direct plain text response and stop tool execution immediately.
> Do NOT call any command execution or interactive tools in the same turn, as
> unexpected tool calls may be auto-replied by the simulation harness and cause
> an infinite loop. Yield immediately for the user's reply.

## Phase 4: Monitoring {#phase-4-monitoring}

Monitor the job via the Cloud Console link provided in the script output.
Additionally, ask the user if they want you to monitor the job status for them
in the background. If they agree, execute `scripts/monitor_tuning_job.py` as a
background task to periodically poll the job status and notify the user to show
the status. If the user declines, leave it completely to the user to check on
the status.

## Phase 5: Model Deployment {#phase-5-model-deployment}

Once the tuning job is `SUCCEEDED`, deploy the model.

```bash
ARTIFACTS="gs://YOUR_BUCKET/tuning_agent_job_<datetime>/output/postprocess/node-0/checkpoints/final"
gcloud ai model-garden models deploy \
    --project=YOUR_PROJECT \
    --region=YOUR_LOCATION \
    --model="$ARTIFACTS" \
    --machine-type=MACHINE_TYPE \
    --accelerator-type=ACCELERATOR_TYPE \
    --accelerator-count=COUNT
```

> [!IMPORTANT]
>
> **Interactive Confirmation Required (Tier M):** Before proceeding with
> deployment, you **MUST** present the proposed command string showing all
> literal flags in a confirmation prompt to the user with 'Yes' and 'No'
> options.

> **CRITICAL:** When presenting this confirmation prompt to the user, you MUST
> output it as a direct plain text response and stop tool execution immediately.
> Do NOT call any command execution or interactive tools in the same turn, as
> unexpected tool calls may be auto-replied by the simulation harness and cause
> an infinite loop. Yield immediately for the user's reply.

Refer to [Models Catalog](references/models.md) for hardware recommendations for
specific open models.

## Resources

-   [Data Preparation Guide](references/data_prep.md)
-   [Models Catalog](references/models.md)
-   [Tuning Guide](references/tuning_guide.md)
-   `scripts/prepare_dataset.py`: Data conversion & validation.
-   `scripts/tune_open_model.py`: Open model tuning job submission.
