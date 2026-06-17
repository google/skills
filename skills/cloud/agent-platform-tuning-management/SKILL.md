---
name: agent-platform-tuning-management
description: >-
  Manages GenAI tuning jobs in Agent Platform. Use this to list, get, or cancel
  ongoing model tuning jobs. Don't use for fine-tuning models (use
  `agent-platform-tuning`), deploying models to endpoints (use
  `agent-platform-deploy`), or managing serving endpoints (use
  `agent-platform-endpoint-management`).
---

# Agent Platform Tuning Management

This skill provides instructions on how to manage GenAI Tuning Jobs using the
Agent Platform Python SDK. Use this skill when a user wants to check the status
of their tuning runs, find an active tuning job, or cancel a job that is running
too long.

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands on behalf of the user, you MUST adhere to the
following safety tiers based on the action requested:

1.  **Tier R: Read-only (`list`, `get`)**
    *   **Rule**: No confirmation needed. You may execute these commands
        immediately to gather information for the user.
2.  **Tier D: Destructive & Interruptive (`cancel`)**
    *   **Rule**: This requires **explicit typed confirmation**. You MUST output
        a text message to the user explaining that this will stop the tuning
        process and any progress will be lost, and asking them to type "I
        confirm" or "Yes, cancel it". You MUST ask for this confirmation
        IMMEDIATELY, before executing the cancel command.

## Phase 0: Environment Setup

**CRITICAL**: Before running any of the Python snippets below, you MUST ensure
the environment is correctly initialized by following these steps:

1.  **Virtual Environment**: Create and activate a virtual environment:

    ```bash
    python3 -m venv ~/tuning_mgr_venv
    source ~/tuning_mgr_venv/bin/activate
    ```

2.  **Google Cloud Authentication**: Authenticate with your Google Cloud account
    and configure active Application Default Credentials (ADC) for Agent
    Platform access:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

3.  **Install Dependencies**: Install the required Agent Platform SDK:

    ```bash
    pip install google-cloud-aiplatform
    ```

4.  **Execution**: Advise the user that every time they execute a Python
    snippet, they must ensure this virtual environment is activated first.

## Workflow Decision Tree

1.  **Information Gathering**: Do you have a Project ID and Region?

    *   **No** -> You **MUST** ask the user for the missing Project ID and
        Region in plain text, or advise them to check their gcloud
        configuration. If neither location has this information, then ask the
        user to provide it. Do not attempt to search random regions on your own.
    *   **Yes** -> Proceed to Step 2.

2.  **Task Type**: What does the user want to do?

    *   **Find or List Jobs** -> Use the Python SDK to list tuning jobs. (Tier
        R)
    *   **Check Status / Inspect a Specific Job** -> Use the Python SDK to get
        tuning job details. (Tier R)
    *   **Cancel a Job** -> Ask for confirmation, then use the Python SDK to
        cancel the tuning job. (Tier D)

## Using the Python SDK

> [!NOTE]
>
> **Resource Verification & Missing Projects/Jobs:** If the execution of the
> Python snippet fails with an error (such as `403 Permission Denied`, `404 Not
> Found`, `INVALID_ARGUMENT`, or indicating a dummy/missing project or job ID),
> you **MUST** inform the user that the project or tuning job does not exist or
> cannot be accessed. You **MUST** prompt the user to provide a valid Project ID
> or Job ID, and stop tool execution immediately to wait for their response. Do
> **NOT** retry or loop, do **NOT** assume the resource is valid, and do **NOT**
> execute further scripts before receiving valid details from the user.

### 1. Listing Tuning Jobs (Tier R)

If the user asks "What tuning jobs do I have running?" or wants to find a
specific job ID:

```python
from google.cloud import aiplatform_v1

project_id = "YOUR_PROJECT_ID"
region = "YOUR_REGION"
parent = f"projects/{project_id}/locations/{region}"

client = aiplatform_v1.GenAiTuningServiceClient(
    client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
)

jobs = client.list_tuning_jobs(parent=parent)
for job in jobs:
    print(f"Name: {job.name}")
    print(f"Base Model: {job.base_model}")
    print(f"State: {job.state}")
```

### 2. Getting Details for a Specific Job (Tier R)

If the user provides a Tuning Job ID and asks for its status:

```python
from google.cloud import aiplatform_v1

project_id = "YOUR_PROJECT_ID"
region = "YOUR_REGION"
job_id = "YOUR_JOB_ID"  # 19-digit ID
name = f"projects/{project_id}/locations/{region}/tuningJobs/{job_id}"

client = aiplatform_v1.GenAiTuningServiceClient(
    client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
)

job = client.get_tuning_job(name=name)
print(f"Name: {job.name}")
print(f"Base Model: {job.base_model}")
print(f"State: {job.state}")
print(f"Tuning Model: {job.tuned_model_display_name}")
```

### 3. Canceling a Job (Tier D)

If the user explicitly requests to stop, abort, or cancel a running tuning job:

**Safety Check**: **Action requires explicit typed confirmation before
proceeding.** You MUST ask the user for confirmation before generating or
providing this script, even if they provided the job ID, unless they explicitly
use confirming language like "Yes, I confirm, cancel tuning job 123456".

> [!IMPORTANT]
>
> **NEVER pre-emptively provide or execute any cancellation code before
> receiving the user's response in a new turn.** You must never speculate or
> assume that confirmation will be given. Asking for confirmation and providing
> the code in a single parallel turn is a severe safety violation.

```python
from google.cloud import aiplatform_v1

project_id = "YOUR_PROJECT_ID"
region = "YOUR_REGION"
job_id = "YOUR_JOB_ID"  # 19-digit ID
name = f"projects/{project_id}/locations/{region}/tuningJobs/{job_id}"

client = aiplatform_v1.GenAiTuningServiceClient(
    client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
)

client.cancel_tuning_job(name=name)
print(f"Successfully requested cancellation for {name}")
```
