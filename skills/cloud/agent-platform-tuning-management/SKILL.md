---
name: agent-platform-tuning-management
metadata:
  version: "1.0.2"
  category: AiAndMachineLearning
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

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` and append the
attribution suffix to `User-Agent` headers:

```text
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-tuning-management)"
User-Agent: <existing_user_agent> agent-skills/1.0 (skill:agent-platform-tuning-management)
```

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands on behalf of the user, you MUST adhere to the
following safety tiers based on the action requested:

1.  **Tier R: Read-only (`list`, `get`)**
    *   **Rule**: No confirmation needed. You may execute these commands
        immediately to gather information for the user.
2.  **Tier D: Destructive & Interruptive (`cancel`)**
    *   **Rule**: Cancellation is a Tier D action requiring **explicit typed
        confirmation** (e.g. "I confirm" or "Yes, cancel it").
    *   **Required Fields in Dry-Run Confirmation Card**: Before cancelling a
        tuning job, you MUST present a dry-run confirmation preview clearly
        listing:
        *   **Target Resource**: The full tuning job resource name or ID (e.g.
            `projects/<PROJECT_ID>/locations/<REGION>/tuningJobs/<JOB_ID>`).
        *   **Command / Script**: The exact cancellation command or Python code
            to be executed.
        *   **Expected Effect**: Stops the ongoing tuning job; any in-progress
            training will be halted and cannot be resumed.
        *   Ask the user to explicitly confirm (e.g., "Do you confirm? Please
            reply with 'I confirm' or 'Yes, cancel it'.").
    *   **Same-turn restriction**: NEVER execute the cancellation in the same
        turn as presenting the preview card. Stop immediately and wait for the
        user to confirm in a new turn. Even if the user provided pre-emptive
        confirmation (e.g. "Yes, I confirm, cancel tuning job ...") or provides
        a corrected job ID, you MUST present the dry-run preview for that
        specific job ID and wait for confirmation in a separate turn before
        issuing the cancellation.

## Phase 0: Environment Setup

**CRITICAL**: Before running any of the Python snippets below, you MUST ensure
the environment is correctly initialized by following these steps:

1.  **Google Cloud Authentication**: Authenticate with your Google Cloud account
    and configure active Application Default Credentials (ADC) for Agent
    Platform access:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

2.  **Python Dependencies**: This skill needs `google-cloud-aiplatform`. Do
    **not** create a virtual environment — it starts empty and hides packages
    the environment already provides, forcing a redundant install. Probe, and
    install only what is missing:

    ```bash
    python3 -c "import vertexai" || pip install google-cloud-aiplatform
    ```

3.  **Execution**: Run Python snippets with a plain `python3`. There is no
    environment to activate first.

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
> Python snippet fails because of an invalid filter (e.g., `400 Provided filter
> is not valid`), fix or drop the `filter` parameter and re-run. If it fails
> with an error indicating a missing or inaccessible project or job ID (`403
> Permission Denied`, `404 Not Found`, or invalid resource ID), you **MUST**
> inform the user that the project or tuning job does not exist or cannot be
> accessed, prompt the user to provide a valid Project ID or Job ID, and stop
> tool execution immediately to wait for their response (do **NOT** loop or
> assume the resource is valid).

### 1. Listing Tuning Jobs (Tier R)

If the user asks "What tuning jobs do I have running?" or wants to find a
specific job ID, always execute Python code via `run_command` (do NOT use
`curl`). If the user gave a project ID or number, use that **exact** value
(otherwise fall back to the configured project). Pass `page_size=20` and read
the first page (only page through every job if the user explicitly asks for a
total count or the full list). Filter server-side when asked for running jobs
(`state="JOB_STATE_RUNNING" OR state="JOB_STATE_PENDING"`) or a specific model
display name (`display_name:"NAME"`), print `job.tuned_model_display_name`, and
note when `first_page.next_page_token` is set so the 20 most recently updated
jobs are not presented as the entire history:

```python
from google.cloud import aiplatform_v1

project_id = "YOUR_PROJECT_ID"  # If the user gave a project ID/number, use it explicitly
region = "YOUR_REGION"
parent = f"projects/{project_id}/locations/{region}"

client = aiplatform_v1.GenAiTuningServiceClient(
    client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
)

request = {
    "parent": parent,
    "page_size": 20,
    # Optional server-side filter, e.g.:
    # "filter": 'state="JOB_STATE_RUNNING" OR state="JOB_STATE_PENDING"',
}
response = client.list_tuning_jobs(request=request)
first_page = next(iter(response.pages), None)
for job in (first_page.tuning_jobs if first_page else []):
    print(f"Name: {job.name}")
    print(f"Display Name: {job.tuned_model_display_name}")
    print(f"Base Model: {job.base_model}")
    print(f"State: {job.state.name}")
if first_page and first_page.next_page_token:
    print("Note: More jobs exist beyond this first page of 20 most recently updated jobs.")
```

### 2. Getting Details for a Specific Job (Tier R)

If the user provides a Tuning Job ID and asks for its status, always execute
Python code via `run_command` (never use `curl`). If the user gave a project ID
or number, use it explicitly:

```python
from google.cloud import aiplatform_v1

project_id = "YOUR_PROJECT_ID"  # If the user gave a project ID/number, use it explicitly
region = "YOUR_REGION"
job_id = "YOUR_JOB_ID"  # 19-digit ID
name = f"projects/{project_id}/locations/{region}/tuningJobs/{job_id}"

client = aiplatform_v1.GenAiTuningServiceClient(
    client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
)

job = client.get_tuning_job(name=name)
print(f"Name: {job.name}")
print(f"Base Model: {job.base_model}")
print(f"State: {job.state.name}")
print(f"Tuning Model: {job.tuned_model_display_name}")
```

### 3. Canceling a Job (Tier D)

If the user explicitly requests to stop, abort, or cancel a tuning job:

**Safety Check**: Follow the **Tier D (Destructive / Irreversible)**
confirmation rules in the Operation Tiers section above:

-   **Never report an outcome you did not observe**: Never claim a job was
    canceled or report a backend error without actually observing it from an API
    call.
-   Present the confirmation preview with **Expected Effect** conditioned on the
    job's observed state (for active `PENDING`/`RUNNING` jobs: stops in-progress
    training, which cannot be resumed, without deleting the base model or
    dataset; if the job is already in a terminal state `SUCCEEDED`, `FAILED`, or
    `CANCELLED`, state its current terminal state explicitly and note that no
    active training is running).
-   Wait for explicit user confirmation in a new turn before calling
    `client.cancel_tuning_job(name=name)` via Python (`run_command`), and report
    the actual API response verbatim.

```python
from google.cloud import aiplatform_v1

project_id = "YOUR_PROJECT_ID"  # Use the EXACT project ID/number the user gave
region = "YOUR_REGION"
job_id = "YOUR_JOB_ID"  # 19-digit ID
name = f"projects/{project_id}/locations/{region}/tuningJobs/{job_id}"

client = aiplatform_v1.GenAiTuningServiceClient(
    client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
)

client.cancel_tuning_job(name=name)
print(f"Successfully requested cancellation for {name}")
```
