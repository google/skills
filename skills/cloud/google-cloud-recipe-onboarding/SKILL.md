---
name: google-cloud-recipe-onboarding
description: >-
  Guides a developer's first steps on Google Cloud, covering account creation,
  billing setup, project management, and deploying a first resource.
  Use when a new developer wants to initialize their first Google Cloud project,
  configure billing, and verify deployment.
  Don't use for enterprise organization setup (use Google Cloud Setup guided flow for that instead).
  Don't use for complex multi-project architectures.
---

# Onboarding to Google Cloud

This skill provides a streamlined, non-interactive "happy path" for a singleton developer to get started with [Google Cloud](https://cloud.google.com/). It covers everything from environment verification and authentication to project selection, billing account linkage, and downstream safety chaining.

> [!IMPORTANT]
> For autonomous agents executing this skill:
> 1. **Check-Before-Mutate Audits**: Always perform silent pre-execution state audits prior to proposing or executing any project or billing changes.
> 2. **Single-Question Policy**: Ask the user for exactly **one** operational parameter or confirmation at a time during interactive execution.
> 3. **Non-Interactive Output**: Append non-interactive overrides (`--quiet`, `--format="json"`) to all mutation commands to guarantee deterministic, machine-parseable outputs and prevent terminal hangs.
> 4. **First Turn Interaction Rules (Trigger Turn)**: When the developer first triggers this skill with a general onboarding request (e.g. says "I want to get started with Google Cloud"):
>    - **Preamble Guidance**: Proactively include a short orienting preamble guiding the developer to create a Google Cloud account (pointing to the console at `https://console.cloud.google.com/`) and run `gcloud auth login` to authorize their workstation, even if they appear to be already logged in.
>    - **First Turn Single-Question**: Perform pre-flight audits silently, but do not present a complete parameters summary table or ask for final consent in the first turn. Instead, ask the developer exactly **one** initial operational question (e.g., *"Would you like to reuse an existing active project, or create a brand new one?"*).
>    *Note: If the developer's initial prompt explicitly states "I approve the onboarding configuration", "Let's proceed with onboarding", or requests a dry-run plan (e.g., "Show me the exact plan or dry-run commands"), bypass the general preamble and initial question, and proceed directly to the requested step.*

---

## Overview

For an individual developer, onboarding to Google Cloud involves verifying local terminal tools, establishing an authenticated session, selecting or instantiating a workspace ([Project](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy.md.txt)), and linking it to an active billing account. Google Cloud offers a Free Tier and a Free Trial with $300 in credits for first-time users. [Learn more here](https://docs.cloud.google.com/free/docs/free-cloud-features).

---

## Prerequisites

- A personal Google Account (e.g., `@gmail.com`) or Google Workspace / Cloud Identity account.
- A valid payment method (credit card or bank account) required for identity verification and to activate the $300 Free Trial credit introduced in the Overview.

---

## Steps

### Section 1: Verify Host Tooling Setup

Before soliciting input or proposing mutations, silently audit the host system's active tooling and environment status.

1. Check if the `gcloud` CLI binary is installed and accessible:
   ```bash
   which gcloud
   ```
2. Check if there is an active authenticated identity session:
   ```bash
   gcloud auth list --format="json"
   ```
3. If the pre-execution audit for `which gcloud` returns a valid path, proceed directly to Section 2: Authenticate and Route Session.
4. If the binary is missing, halt execution and direct the agent/developer to the [gcloud skill](https://github.com/google/skills/tree/main/skills/cloud/gcloud) or official [Google Cloud CLI Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) for setup and authentication instructions before retrying.

---

### Section 2: Authenticate and Route Session

Authorize the gcloud CLI to access Google Cloud using the developer's Google Account, and verify that the account is appropriate for standalone developer onboarding.

1. **Execute Credentials Authentication:**
   ```bash
   gcloud auth login
   ```
   > [!IMPORTANT]
   > **New User / Unauthenticated Guidance**:
   > If the pre-execution state audits or command failures confirm that the developer is unauthenticated (e.g., `gcloud auth list` is empty or active credentials are missing):
   > 1. Guide them to create a Google Cloud account by navigating to the [Google Cloud Console](https://console.cloud.google.com/).
   > 2. Instruct them to execute the `gcloud auth login` command to authorize their local workstation terminal session.
   > 3. Do not attempt project creation or resource configuration until authentication is completed successfully.

2. **Verify Active Identity:**
   ```bash
   gcloud config get-value account --format="json"
   ```

3. **Programmatic Enterprise Routing Guardrail:**
   Before proceeding, verify if the account is bound to a corporate organization, as enterprise setups must follow a different architecture:
   ```bash
   gcloud organizations list --format="json"
   ```
   - Note that new Free Trial accounts automatically receive a Self-Owned Organization (SOO). To distinguish between a personal Free Trial account and an enterprise organization, inspect the JSON output:
     - **Enterprise Organization (Halt Execution)**: If the output list contains an organization node where `owner.directoryCustomerId` is present (confirming a domain-verified Google Workspace or Cloud Identity organization), or if the user's prompt explicitly mentions corporate landing zones or multi-tenant project structures:
       - **Halt execution** of this skill immediately.
       - Route the developer to the official [Google Cloud Setup guided flow](https://docs.cloud.google.com/docs/enterprise/cloud-setup.md.txt).
     - **Personal Account / Free Trial SOO (Proceed)**: If the output list is empty `[]`, or if it contains a Self-Owned Organization (where `owner.directoryCustomerId` is absent and `displayName` is not a verified domain name), proceed to Section 3: Select or Instantiate Your Google Cloud Project.

---

### Section 3: Select or Instantiate Your Google Cloud Project

Google Cloud resources are organized into **Projects**. When developers sign up for a Free Trial via the console, Google Cloud automatically creates a default project (e.g., "My First Project"). Always audit the active environment first to reuse existing projects and prevent token-burning collision errors.

1. **Silent Project Discovery:**
   List active, accessible projects (limited to prevent context window overflow):
   ```bash
   gcloud projects list --filter="lifecycleState=ACTIVE" --limit=20 --format="json"
   ```
2. **Reuse Existing Project (Recommended):**
   If the list returns an active project, present it to the developer and propose setting it as the default working project:
   ```bash
   gcloud config set project {PROJECT_ID} --quiet
   ```
3. **Create Custom Project:**
   If no projects exist, or if the developer explicitly requests a brand new workspace:
   - Solicit a custom `PROJECT_ID` and `PROJECT_NAME` from the developer (Single-Question Policy).
   - **Structured Confirmation & Consent Gate (Mandatory)**:
     Before running any project creation or billing linkage commands, the agent **must** present a structured markdown table summarizing the target parameters:
     | Parameter | Value |
     | :--- | :--- |
     | Target Project ID | `{PROJECT_ID}` |
     | Target Project Name | `{PROJECT_NAME}` |
     | Active Identity Account | `{ACCOUNT}` |
     | Target Billing Account ID | `{BILLING_ACCOUNT_ID}` |

     Ask the user the exact consent query:
     `"I am ready to initialize your Google Cloud project and link billing. Do you want me to proceed?"`

     **CRITICAL**: The agent **MUST NOT** execute any `gcloud projects create` or billing link commands during this turn. You must display this table, ask the exact consent query, and **strictly stop** to wait for the user's positive affirmation.
    - **Project ID Collision Suffix Recovery**: If the project creation
      command fails because the `PROJECT_ID` is already taken globally
      (returning a `PROJECT_ID_COLLISION` or `ALREADY_EXISTS` error):
      - Automatically append a random 4-digit suffix (e.g., changing `my-project` to `my-project-8472`).
      - Propose this new available project ID to the developer and re-solicit consent before retrying.
   - **Execute Project Creation**: Once explicit user consent is confirmed:
     ```bash
     gcloud projects create {PROJECT_ID} --name="{PROJECT_NAME}" --quiet --format="json"
     ```
   - Set the active working project:
     ```bash
     gcloud config set project {PROJECT_ID} --quiet
     ```

---

### Section 4: Verify and Link Billing

To deploy resources on Google Cloud, your project must be linked to an active Cloud Billing account.

1. **Audit Billing Status:**
   Check if the active project is already linked to a billing account:
   ```bash
   gcloud billing projects describe {PROJECT_ID} --format="json"
   ```
2. If the output contains `"billingEnabled": true`, skip linkage and proceed immediately to Section 5: Skill Chaining (Spend Controls & Workloads).
3. **Discover Available Billing Accounts:**
   If the project is unlinked, query the available billing account handles linked to the authenticated user identity:
   ```bash
   gcloud billing accounts list --format="json"
   ```
4. **Link Billing Account:**
   Propose linking the project to the discovered Billing Account ID, and execute:
   ```bash
   gcloud billing projects link {PROJECT_ID} --billing-account={BILLING_ACCOUNT_ID} --format="json"
   ```

---

### Section 5: Skill Chaining (Spend Controls & Workloads)

Onboarding setup is now complete. To safeguard your environment and deploy workloads, you can chain to downstream specialized skills:

1. **Billing Spend Controls:**
   To avoid accidental cost overruns, consider setting up a programmatic control to automatically disable billing. When billing is disabled, all Google Cloud services and usage in the project are terminated to stop further costs:
- Direct the developer to the official [Disable Billing Usage with Notifications Guide](https://docs.cloud.google.com/billing/docs/how-to/disable-billing-with-notifications.md.txt), which provides detailed instructions on how to automatically shut down billing when costs exceed the project budget.
2.  **Deploy Workloads**: To deploy your first resource, trigger the downstream
    specialized skill matching your target application (e.g.,
    [cloud-run-basics](https://github.com/google/skills/blob/main/skills/cloud/cloud-run-basics)
    or `bigquery-basics`). If the specialized skill is not locally available,
    direct the developer to the corresponding official quickstart, such as the
    [Cloud Run Container Deployment Quickstart](https://docs.cloud.google.com/run/docs/quickstarts/deploy-container.md.txt).
    *Note: Those downstream specialized skills are individually responsible for
    dynamically enabling their own required service APIs (e.g.,
    run.googleapis.com) inline during execution.*

---

## Validation Logic

After completing the onboarding steps, programmatically verify the completed environment state using these diagnostic commands:

1. **Verify CLI Installation:**
   ```bash
   which gcloud
   ```
2. **Verify Authenticated Identity:**
   ```bash
   gcloud config get-value account
   ```
3. **Verify Project Workspace Existence:**
   ```bash
   gcloud projects describe {PROJECT_ID} --format="json"
   ```
4. **Verify Billing Linkage** (Ensure the JSON output contains `"billingEnabled": true`):
   ```bash
   gcloud billing projects describe {PROJECT_ID} --format="json"
   ```

---

## Additional Resources

- [Google Cloud Getting Started landing page](https://docs.cloud.google.com/docs/get-started.md.txt)
- [Google Cloud overview](https://docs.cloud.google.com/docs/overview.md.txt)
- [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [Google Cloud Cloud Setup guided flow](https://docs.cloud.google.com/docs/enterprise/cloud-setup.md.txt)

