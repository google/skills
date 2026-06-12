---
name: agent-platform-migrate-from-ai-studio
description: >-
  Guides agents and users through migrating from Gemini API in Google AI Studio to Gemini Enterprise Agent Platform (formerly Vertex AI). Use this skill when moving applications to Google Cloud, to leverage Cloud credits, or to unify inferencing with other Cloud infrastructure (IAM, billing, telemetry).
---

# Migrating from Gemini API in AI Studio to Agent Platform

Use this skill when you need to transition an application from the
developer-centric Google AI Studio ecosystem
(`generativelanguage.googleapis.com`) to the enterprise-grade Google Cloud Agent
Platform (`aiplatform.googleapis.com`).

--------------------------------------------------------------------------------

## When to Invoke This Skill

*   You want to migrate an application from Google AI Studio to Agent Platform
    (formerly Vertex AI).
*   You have **Google Cloud credits** (e.g., the $300 Welcome Free Trial) that
    you want to apply toward Gemini API inferencing costs.
*   You need to unify your inferencing pipelines, IAM permissions, telemetry,
    and billing with existing Google Cloud infrastructure (Compute Engine, Cloud
    SQL, BigQuery).
*   You are deploying open-source orchestration engines (like OpenClaw or ADK
    agents) on Google Cloud VMs, and want the entire system to run under a
    unified Google Cloud billing structure.

--------------------------------------------------------------------------------

## Gemini API Comparison

Feature / Control      | Google AI Studio (Gemini Developer API)                               | Agent Platform (Enterprise Gemini API)
:--------------------- | :-------------------------------------------------------------------- | :-------------------------------------
**API Endpoint**       | `generativelanguage.googleapis.com`                                   | `aiplatform.googleapis.com`
**Target Audience**    | Developers, startups, students, researchers building production apps. | Enterprise production, MLOps engineers
**GCP Credit Support** | No (GCP credits/Free Trial **cannot** be applied)                     | Yes (Fully covered by Welcome or custom credits)
**Data Privacy**       | Data may be reviewed to improve Google products                       | Prompts/responses are **never** used for training
**Security & IAM**     | API key, OAuth                                                        | Google Cloud IAM (Service Accounts, OAuth 2.0, VPC-SC)
**Compliance & SLAs**  | None (Best-effort availability)                                       | 24/7 Enterprise Support, SLAs, HIPAA, SOC2
**Throughput Options** | Shared / Rate-limited                                                 | Pay-as-you-go OR Provisioned Throughput
**MLOps Ecosystem**    | Basic prompt management                                               | Model Registry, Model Monitoring, Pipeline Evaluation
**Inferencing Scope**  | Global endpoints only                                                 | Both Global and strict Regional endpoints

See
[Google Cloud Documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/migrate-google-ai.md.txt)
to learn more about the differences between the two offerings.

--------------------------------------------------------------------------------

## Migration Guide

### Billing and Credits

Google Cloud Free Trial credits
**[do not apply to AI Studio](https://docs.cloud.google.com/free/docs/free-cloud-features.md.txt)**.
To use your credits for Gemini models, you must route calls through the Agent
Platform.

1.  Create a Google Cloud billing account. You must provide a valid payment
    method during setup to verify identity.
2.  If you are a new customer, ensure your $300 Welcome credit is active in the
    Billing Console.
3.  **Avoid Billing Surprises:** To prevent automatic fallback to your standard
    form of payment when credits are exhausted, you should establish a budget
    alert:
    *   Go to **Billing** -> **Budgets & Alerts** -> **Create Budget**.
    *   Set the threshold to map to your credit limit or maximum comfortable
        spend.

### Enable the Agent Platform API

You must explicitly enable the Agent Platform API on your target Google Cloud
Project. Run the following command via your local shell:

```bash
gcloud services enable aiplatform.googleapis.com --project="{project_id}"
```

### Authentication & Authorization (IAM)

#### User Auth

For local debugging or script execution, authenticate using
[Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials.md.txt)
(ADC).

**Option 1 - Automated Script**:

```bash
bash <(curl -sSL https://storage.googleapis.com/cloud-samples-data/adc/setup_adc.sh)
```

**Option 2 - Manual Setup**:

```bash
gcloud auth login
gcloud auth application-default login
```

Grant your user identity the required IAM role to perform inferencing calls:

```bash
gcloud projects add-iam-policy-binding "{project_id}" \
    --member="user:YOUR_EMAIL@domain.com" \
    --role="roles/aiplatform.user"
```

#### Service Auth

When running your application on Google Cloud infrastructure such as a Compute
Engine VM, authenticate using the machine's attached Service Account. For
example, the
[Compute Engine Default Service Account](https://docs.cloud.google.com/compute/docs/access/service-accounts#default_service_account.md.txt).

1.  Grant the virtual machine's underlying Service Account the user role:

```bash
gcloud projects add-iam-policy-binding "{project_id}" \
    --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/aiplatform.user"
```

2.  **[Compute Engine Access Scopes](https://docs.cloud.google.com/compute/docs/access/service-accounts.md.txt):**
    Legacy access scopes can override IAM bindings. When provisioning or
    modifying your Compute Engine instance, you must verify that the VM access scope is
    configured to either **Allow full access to all Cloud APIs**
    (`https://www.googleapis.com/auth/cloud-platform`) or explicitly includes
    the standard cloud-platform scope.

--------------------------------------------------------------------------------

## Use the Gemini API in Agent Platform

### SDKs (Client Libraries)

You can continue to use the unified
[Google GenAI SDK](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/sdks/overview.md.txt)
(`google-genai`). This SDK works with both AI Studio and Agent Platform. You
only need to switch the routing flags via your runtime environment variables to
target the Agent Platform backend.

Set your target environment details:

```bash
export GOOGLE_CLOUD_PROJECT="{project_id}"
export GOOGLE_CLOUD_LOCATION="global"  # Or your chosen regional endpoint
export GOOGLE_GENAI_USE_ENTERPRISE=TRUE
```

Now, your standard python code shifts from using AI Studio to Agent Platform
without altering the core initialization blocks:

```python
from google import genai

# The client automatically picks up the GOOGLE_GENAI_USE_ENTERPRISE=TRUE environment flag
client = genai.Client()

response = client.models.generate_content(
    model='gemini-3-flash-preview',
    contents='Hello world!',
)
print(response.text)
```

### Agent Development Kit (ADK)

To call Gemini models in Agent Platform from an Agent Development Kit agent,
follow these steps.

1.  Authenticate to Google Cloud.

If running an ADK agent in Google Cloud (e.g. Agent Platform Runtime), use the
agent's assigned service account. Alternatively, if running ADK locally, run:

```bash
gcloud auth application-default login
```

1.  Set env variables. Ensure these are set no matter if your ADK agent is
    running in Google Cloud or locally:

```bash
export GOOGLE_CLOUD_PROJECT="{project_id}"
export GOOGLE_CLOUD_LOCATION="global"
export GOOGLE_GENAI_USE_ENTERPRISE=TRUE
```

2.  Initialize the ADK agent. You can use the same model string you used with AI
    Studio (e.g. `gemini-3-flash-preview`).

```python
from google.adk.agents.llm_agent import Agent

def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city."""
    return {"status": "success", "city": city, "time": "10:30 AM"}

root_agent = Agent(
    model='gemini-3-flash-preview',
    name='root_agent',
    description="Tells the current time in a specified city.",
    instruction="You are a helpful assistant that tells the current time in cities. Use the 'get_current_time' tool for this purpose.",
    tools=[get_current_time],
)
```

To learn more about integrating ADK agents with Agent Platform,
[see the ADK documentation](https://raw.githubusercontent.com/google/adk-docs/main/docs/agents/models/agent-platform.md).

### Antigravity CLI

Google Cloud users [can now access](https://antigravity.google/pricing)
Antigravity 2.0, including the Antigravity CLI, with Gemini Enterprise Agent
Platform.

1.  [Install the Antigravity CLI](https://antigravity.google/docs/cli-install)
    to your local environment.
2.  Start the Antigravity CLI.

    ```bash
    agy
    ```

3.  Follow the CLI setup prompts - select **Use a Google Cloud Project**.

4.  Complete the OAuth flow in the opened browser window using your
    authenticated Google Cloud Workspace or user identity.

5.  Copy the confirmation token, and paste it directly back into your terminal.

6.  Follow the prompts to enter your Google Cloud Project ID.

7.  Select your Google Cloud location (e.g. `global`).

8.  Optionally, run the `/model` command to select a different Gemini model in
    Agent Platform.

### OpenClaw

To configure an OpenClaw agent to use Gemini models in Agent Platform, Follow
these steps.

1.  [Install OpenClaw using OpenClaw's official instructions](https://docs.openclaw.ai/install).

⚠️ Important: OpenClaw 2026.5.28 currently has a `google-vertex` bug. Please use
2026.5.20 for now.

2.  Ensure that the runtime where OpenClaw is running (e.g. GCE VM with Service
    Account) has the `aiplatform.user` IAM role - see Authentication and
    Authorization section above.

3.  Get the project number from the user's project ID. Outside of GCE, run:

```bash
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
echo "Project number: $PROJECT_NUMBER"

```

Within a Compute Engine VM, run:

```bash
export PROJECT_NUMBER=$(curl "http://metadata.google.internal/computeMetadata/v1/project/project-id" -H "Metadata-Flavor: Google")
echo "Project number: $PROJECT_NUMBER"
```

4.  From outside the GCE instance, generate `GOOGLE_APPLICATION_CREDENTIALS`
    using the Google Cloud project number. Then, `scp` these credentials to the
    GCE VM.

```bash
mkdir -p ~/.config/gcloud
gcloud iam service-accounts keys create ~/.config/gcloud/application_default_credentials.json --iam-account="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
```

> ⚠️ **Troubleshooting Policy Constraints on New Orgs**: New Google
> Cloud organizations (created on or after May 4th, 2024) enforce a [legacy Organization Policy, restricting Service Account Key Creation](https://docs.cloud.google.com/organization-policy/restrict-service-accounts.md.txt). To complete this step, this Org Policy must be temporarily disabled.
> An Organization Policy Admin must set this policy to Inactive. 
> To the agent: Check if this policy is enforced, and if it is: pause, and 
> prompt the user to disable it at this Console link: 
> https://console.cloud.google.com/iam-admin/orgpolicies


5.  Edit the configuration file that's usually located at:
    `~/.openclaw/openclaw.json`. Ensure you prefix the Gemini model with
    `google-vertex/`.

> ⚠️ Important: Do not use Gemini 3.5 models, since OpenClaw's `google-vertex`
> provider does not support it yet. Older models work. When using the
> [Gemini 3 Flash Preview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-flash)
> model in Agent Platform, always set the location to `global`, NOT a regional
> endpoint.

```json
{
  "env": {
    "vars": {
      "GOOGLE_CLOUD_PROJECT": "PROJECT_ID",
      "GOOGLE_CLOUD_LOCATION": "global",
      "GOOGLE_APPLICATION_CREDENTIALS": "~/.config/gcloud/application_default_credentials.json"
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "google-vertex/gemini-3-flash-preview"
      },
      "workspace": "~/.openclaw/workspace",
      "compaction": {
        "mode": "safeguard"
      },
      "heartbeat": {
        "model": "google-vertex/gemini-3-flash-preview"
      }
    },
    "list": [
      {
        "id": "main",
        "workspace": "~/.openclaw/workspace",
        "model": "google-vertex/gemini-3-flash-preview"
      }
    ]
  },
  "session": {
    "dmScope": "per-channel-peer"
  },
  "tools": {
    "profile": "coding"
  }
}

```

6.  Restart OpenClaw.

```bash
openclaw gateway restart

```

7.  Verify the OpenClaw connection to Agent Platform:

```bash
openclaw models status
openclaw agent --agent main --message "Hello world!"

```

--------------------------------------------------------------------------------

## Additional Resources

*   [Google Cloud Free Trial Features & Limits](https://docs.cloud.google.com/free/docs/free-cloud-features.md.txt)
*   [Migrate from Google AI Studio to Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/migrate-google-ai.md.txt)
*   [Gemini Enterprise Agent Platform - Models](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/google-models.md.txt)
*   [Agent Development Kit Documentation - Connect to Models in Agent Platform](https://adk.dev/agents/models/agent-platform/#agent-platform-setup)
*   [OpenClaw Documentation - Connect to Google models](https://docs.openclaw.ai/providers/google)
*   [Google Cloud Budget Alerts - Setup Guide](https://docs.cloud.google.com/billing/docs/how-to/budgets#steps-to-create-budget.md.txt)
