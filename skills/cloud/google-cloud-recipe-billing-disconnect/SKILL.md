---
name: google-cloud-recipe-billing-disconnect
description: >-
  Disables billing for a GCP project when budget thresholds are hit by deploying a Cloud Function, and verifies/enables Data Access audit logging for active high-cost runtime APIs.
  Use when requested to set up auto-disabling of billing, configure cloud spend protection, or when budget overruns and untraceable costs are a concern.
  IMPORTANT: This skill performs a mutation (disabling billing and enabling logging). The agent MUST get explicit user authorization before execution.
preconditions:
  required_iam_roles:
    - roles/billing.user           # (Billing Account User - on Billing Account)
    - roles/billing.projectManager # (Billing Project Manager - on Target Project)
    - roles/resourcemanager.projectIamAdmin # (To update Data Access audit log IAM configurations)
  required_apis:
    - billingbudgets.googleapis.com
    - cloudbilling.googleapis.com
    - cloudfunctions.googleapis.com
    - pubsub.googleapis.com
    - run.googleapis.com
    - logging.googleapis.com
---

<!-- disableFinding(LINE_OVER_80) -->
<!-- disableFinding(WHITESPACE_TRAILING) -->
<!-- disableFinding(HEADING_REPEAT_H1) -->

# Spend Protection via Billing Disconnection

This skill provides a procedural, non-interactive guide to configure automated spend protection on a Google Cloud project. It deploys a serverless Cloud Function triggered by Pub/Sub budget alerts to automatically disconnect the Cloud Billing account, shutting down all resources and services when monthly costs meet or exceed a user-specified threshold.

> [!IMPORTANT]
> For autonomous agents executing this skill:
> 1. **Check-Before-Mutate Audits**: Always perform silent pre-execution state audits prior to proposing or executing any billing changes, budgets, or resource deployments.
> 2. **Single-Question Policy**: Solicit exactly **one** operational parameter or user confirmation at a time during interactive execution.
> 3. **Non-Interactive Output**: Append non-interactive overrides (`--quiet`, `--format="json"`) to all mutation commands to guarantee deterministic, machine-parseable outputs and prevent terminal hangs.
> 4. **First Turn Interaction Rules (Trigger Turn)**: When the developer first triggers this skill (e.g. says "I want to set up automated spend protection"):
>    - **Preamble Guidance**: Proactively include a short orienting preamble guiding the developer to create a Google Cloud account (pointing to the console at `https://console.cloud.google.com/`) and run `gcloud auth login` to authorize their workstation, even if they appear already logged in.
>    - **First Turn Single-Question**: Perform pre-flight audits silently, but do not present a complete parameters summary table or ask for final consent in the first turn. Instead, ask the developer exactly **one** initial operational question (e.g., *"What would you like your monthly spend cap budget threshold to be?"*).

---

## Overview

Unmanaged sandbox environments and trial workloads are vulnerable to unexpected cost spikes. Deploying an automated billing spend cap is an efficient safeguard to stop all Google Cloud resource consumption and halt charge accumulation immediately when a project's costs exceed its budget limit. 

To prevent untraceable budget drains and ensure observability, this skill also programmatically audits and enables Data Access audit logging for active high-cost database, compute, and generative AI services.

---

## Prerequisites

- A personal Google Account or Google Workspace / Cloud Identity account.
- Billing Account Administrator and Project Owner permissions on the target workspace.
- The `gcloud` Command-Line Interface (CLI) must be installed and accessible in the path.

---

## Pre-Execution State Audits

Before asking for confirmation or proposing any mutations, programmatically audit the active shell environment status to gather baseline context and enforce safety guardrails:

1. **Verify CLI Tool Installation:**
   Check that `gcloud` is available in the path:
   ```bash
   which gcloud
   ```
2. **Verify Active Authenticated Account:**
   Check the currently logged-in identity account:
   ```bash
   gcloud config get-value account --format="json"
   ```
3. **Programmatic Enterprise Routing Guardrail:**
   Verify if the active profile belongs to a corporate Google Workspace or Cloud Identity Organization node:
   ```bash
   gcloud organizations list --format="json"
   ```
   - If the output is **not empty `[]`** (containing a corporate organization node), immediately **halt execution** of this singleton recipe and route the developer to the official [Google Cloud Enterprise Setup Guide](https://docs.cloud.google.com/docs/enterprise/cloud-setup).
4. **Verify Active Project Context:**
   Verify the active configuration's project ID matches the target `{PROJECT_ID}`:
   ```bash
   gcloud config get-value project --format="json"
   ```
5. **Discover Accessible Billing Accounts:**
   Discover billing account handles linked to the authenticated identity:
   ```bash
   gcloud beta billing accounts list --format="json"
   ```
6. **Idempotency Audits (Discover Existing Spend Protection Resources):**
   Verify if Pub/Sub topics, functions, or budgets already exist for the workspace:
   ```bash
   # Check Pub/Sub topic existence
   gcloud pubsub topics list --filter="name:projects/{PROJECT_ID}/topics/{TOPIC_ID}" --format="json"

   # Check Cloud Function deployment status
   gcloud functions list --filter="name:stop-billing-function" --format="json"

   # Check existing budgets
   gcloud billing budgets list --billing-account={BILLING_ACCOUNT_ID} --format="json"
   ```
7. **Discover Enabled High-Cost Services & Verify Auditing Status:**
   Identify if any high-cost runtime services are enabled, and check if their Data Access audit logs are disabled:
   ```bash
   # Check for enabled target APIs
   gcloud services list --enabled --filter="name:(spanner.googleapis.com OR compute.googleapis.com OR bigquery.googleapis.com OR aiplatform.googleapis.com)" --project={PROJECT_ID} --format="json"

   # For each detected target service, verify if audit logs are currently capturing traffic
   gcloud logging read "resource.type=audited_resource AND protoPayload.serviceName=TARGET_SERVICE_NAME" --limit=1 --format="json"
   ```

---

## Steps

### 1. Pre-flight Verification & Setup Preamble

1. Direct new or unauthenticated developers to create a Google Cloud Account and authorize their terminal CLI session by running:
   ```bash
   gcloud auth login
   ```
2. **Trigger Turn Single-Question Policy**:
   Perform the silent audits described above. Ask the developer for exactly **one** missing operational parameter (e.g., asking for their desired monthly `{BUDGET_AMOUNT}` threshold) to avoid conversational stalling or multiple prompts.

---

### 2. Structured Confirmation & Consent Gate (Mandatory)

Before executing any deployment scripts or mutation commands, the agent **must** present a structured parameters table summarizing the intended setup:

| Operational Parameter | Value |
| :--- | :--- |
| **Target GCP Project** | `{PROJECT_ID}` |
| **Active Billing Account** | `{BILLING_ACCOUNT_ID}` |
| **Hard Monthly Spend Cap** | `${BUDGET_AMOUNT}` |
| **Topic ID** | `{TOPIC_ID}` (Defaults to `billing-alerts-topic`) |
| **Action on Limit Hit** | 🛑 Disables billing (stops all project services) |

Ask the user the exact consent query:
`"I am ready to deploy your billing disconnect spend cap. Do you want me to proceed?"`

**CRITICAL**: The agent **MUST NOT** execute any `billing_caps.sh` scripts or budget mutations during this turn. Display the table, ask the consent query, and **strictly stop** to wait for positive user affirmation.

---

### 3. Deploy Spend Cap Controls

Once explicit user consent is received, proceed with deployment based on the audited baseline state:

- **New Setup deployment:**
  If no budget exists for the project, run the bundled automated script to deploy the Pub/Sub topic and serverless Cloud Function:
  ```bash
  ./projects/billing-disconnect/scripts/billing_caps.sh {PROJECT_ID} {BILLING_ACCOUNT_ID} {BUDGET_AMOUNT} [REGION] [TOPIC_ID]
  ```
- **Budget Threshold Update:**
  If the Pub/Sub topic and Cloud Function are already deployed, and only the spend threshold is being updated, do not rerun the setup script. Update the existing budget resource directly:
  ```bash
  gcloud billing budgets update {BUDGET_NAME_ID} --budget-amount={BUDGET_AMOUNT} --format="json"
  ```

---

### 4. Proactive Logging Enablement

If the audits in Step 1 identified unlogged active high-cost runtime APIs (such as BigQuery, Spanner, Compute, or Gemini/Vertex Agent platform) and Data Access audit logs are disabled:
1. Proactively present a prompt requesting user permission to activate logging: *"I detected that Data Access audit logs are disabled for active services in this project. Can I enable auditing to ensure cost traceability?"*
2. Once approved, enable audit logs programmatically using standard IAM policy overrides with `--quiet --format="json"`.

---

### 5. Verify Pipeline (Safe Mock Gate)

To verify that the Pub/Sub trigger, serverless Cloud Function, and billing disconnect permission scopes are functioning correctly without triggering an actual project shutdown:

1. **Enforce Safe Cost Thresholds (Mandatory Sanitizer)**:
   Programmatically validate that the simulated cost is strictly less than or equal to the budget:
   $$\text{Mock Cost} \le \text{Spend Cap}$$
   > [!CAUTION]
   > If the mock payload is constructed where Cost > Budget, the function will trigger a **real** billing disconnection, shutting down the project.
2. Publish the safe mock event:
   ```bash
   # Message must be Base64 encoded JSON (e.g., Cost: 50, Budget: 100)
   MOCK_DATA=$(echo -n '{"costAmount": 50, "budgetAmount": 100}' | base64) && \
   gcloud pubsub topics publish {TOPIC_ID} --message="$MOCK_DATA" --project={PROJECT_ID}
   ```
3. Verify execution logs to confirm the diagnostic `"No action necessary"` signature is recorded:
   ```bash
   gcloud functions logs read stop-billing-function --region={REGION} --limit=5 --project={PROJECT_ID}
   ```

---

## Downstream Skill Chaining

Automated spend cap protection is now complete. The developer's workspace is safely capped. You can now chain directly to specialized downstream product skills to safely deploy workloads:

1. **Deploy Containerized Workloads (Recommended):**
   Trigger the `cloud-run-basics` skill to deploy serverless containerized applications securely.
2. **Configure Serverless Data Warehouse:**
   Trigger the `bigquery-basics` skill to initialize and query analytical tables.
