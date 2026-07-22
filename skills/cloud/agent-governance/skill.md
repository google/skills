---
name: agent-platform-governance
metadata:
  category: AiAndMachineLearning
  description: Manages, applies, and audits Governance, Security, and Cost policies for the Agent Platform. Use when you need to configure Agent Gateways, Model Armor templates, IAM/IAP conditions, or cost-tracking labels.
---

# Agent Platform Governance & Cost Tracking

This skill provides instructions for managing, applying, and auditing security guards, granular access controls, and FinOps labeling for agents deployed on the Agent Platform.

## Usage Guide

To use this skill effectively:
1. **Generate Governance Artifacts:** Provide the `gcloud` commands and YAML/JSON configurations below to help users configure access controls, content safety, and FinOps labels.
2. **Support Automation:** Generate executable setup scripts or IaC blocks that help apply these policies.

---

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands or scripts on behalf of the user, you MUST adhere to the following safety tiers to prevent accidental lockouts, policy overrides, or service disruption:

* **Tier R: Read-only** (list, describe, get, query)
  * No confirmation needed. Execute immediately to gather policy information.
* **Tier M: Mutating & Reversible** (apply, update, import, set)
  * Requires interactive confirmation with 'Yes'/'No' options before applying configurations. The confirmation prompt must contain the exact, literal command string with all required flags (e.g., `--update-labels`, `set-iam-policy`).
  * **Same-turn restriction:** Do not execute the creation code in the same turn as presenting the confirmation prompt. Stop and wait for the user's approval.
* **Tier D: Destructive & Irreversible** (delete, disable)
  * Requires explicit typed confirmation (e.g., "I confirm"). Ask for confirmation IMMEDIATELY before any checks.

---

## Phase 0: Environment Setup

CRITICAL: Before running any `gcloud` commands, advise the user to initialize their environment:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project $PROJECT_ID
```

> 💡 **Tip:** Always dynamically substitute placeholders (such as `$PROJECT_ID`, `$LOCATION_ID`, and `$AGENT_ID`) with verified variables discovered during your workspace analysis.

---

## 1. Access Authorization & Gateway Egress (Tier M)

Control what tools and endpoints an Agent Identity (SPIFFE) is authorized to call through the Agent Gateway.

### Configure IAM Policy with CEL Conditions
Define granular conditions to block or allow access to specific MCP Tools based on attributes like read-only tags. See `references/iam_conditions.md` for advanced CEL expressions.

* **Step 1:** Get existing policy:
  ```bash
  gcloud iap web get-iam-policy \
      --resource-type=AgentRegistryResource \
      --project=$PROJECT_ID --format=json > iap-policy.json
  ```
* **Step 2:** Merge/Apply updated policy with condition:
  ```bash
  gcloud iap web set-iam-policy iap-policy.json \
      --resource-type=AgentRegistryResource \
      --project=$PROJECT_ID
  ```

> ⚠️ **IMPORTANT:** This is a Tier M operation — ensure the user validates the condition logic before applying.

---

## 2. Content Security with Model Armor (Tier M)

Screen prompts/responses for prompt injection, PII, and harmful content.

### Create and Bind Model Armor Template
* **Step 1:** Define the template (e.g., `ma-template.yaml` using the formats in `references/model_armor_config.md`).
* **Step 2:** Import Policy:
  ```bash
  gcloud model-armor policies import my-policy \
      --source=ma-template.yaml \
      --location=$LOCATION_ID
  ```
* **Step 3:** Bind to Gateway via Extension:
  ```bash
  gcloud service-extensions authz-extensions import ma-extension \
      --source=extension-config.yaml \
      --location=$LOCATION_ID
  ```

---

## 3. Cost Tracking & FinOps Labeling (Tier M)

Ensure strict financial accountability by tagging agents consistently.

### Apply Governance Labels
Apply the standardized Labeling Scheme (defined in `references/cost_tracking.md`) to the agent runtime.
```bash
gcloud run services update $SERVICE_NAME \
    --update-labels=agent-id=$AGENT_ID,business-unit=$BU,environment=$ENV \
    --region=$LOCATION_ID
```

### Querying Billing via BigQuery (Tier R)
To identify the top 5 most expensive agents this week, run the analytical query documented in `references/cost_tracking.md`.

---

## 4. Best Practices

* **Dry-Run Mode:** Always advise the user to test IAM and Model Armor configurations in Audit-only or Dry-Run Mode first before switching to ENFORCE.
* **Fail Open/Closed:** Ensure `failOpen: false` configuration is explicitly decided in Gateway Service Extensions.
