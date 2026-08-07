---
name: agent-platform-inference
metadata:
  category: AiAndMachineLearning
description: >-
  Connects to and performs inference with Google Cloud Agent Platform GenAI
  models, including First-Party Gemini models and Third-Party OpenMaaS models
  (Llama, DeepSeek, Qwen, etc.). Use when you need to generate code for calling
  Gemini or OpenMaaS models, authenticate with GenAI SDK, OpenAI SDK, or legacy
  Agent Platform SDK, configure base URLs and global/regional endpoints, or troubleshoot
  429 Resource Exhausted (DSQ), 400 User Validation, or 404 Not Found errors.
  Don't use for deploying models to endpoints or for running model evaluations.
---

# Agent Platform GenAI Inference Skill

This skill provides instructions for authenticating and connecting to Google
Cloud Agent Platform to use Generative AI models. It covers:

*   **First-Party publisher models** (Gemini) — section 2.
*   **Third-Party publisher models** (OpenMaaS: Llama, DeepSeek, Qwen, etc.)
    — section 3.
*   **Custom endpoints** (any model on a numeric `projects/.../endpoints/<id>`
    resource — tuned Gemini models, OSS LLMs self-deployed from Model Garden
    via the `agent-platform-deploy` skill, and legacy custom models) —
    section 4.

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands or scripts on behalf of the user, you must adhere
to the following safety tiers based on the action requested. (The skill is
read-only; other safety tiers are omitted):

1.  **Tier R: Read-only / Inference (`client.models.generate_content`,
    `client.chat.completions.create`, `client.completions.create`,
    `client.embeddings.create`)**
    *   Requires **interactive confirmation** with 'Yes'/ 'No' options before
        executing model inference on behalf of the user, to prevent unexpected
        cost or quota consumption. The confirmation prompt must clearly explain
        the proposed inference execution and its key parameters (e.g., target
        model ID, SDK choice, input prompt). Natural-language paraphrases
        without specifying the parameters are NOT sufficient.
    *   **Same-turn restriction**: Do not execute the inference scripts or
        commands in the same turn as presenting the confirmation prompt. Stop
        and wait for the user's reply; only execute after explicit 'Yes' /
        approval.
    *   **Gold Standard Example**: > I will perform model inference with the
        following parameters. Please > confirm this information before I
        proceed: > * **Model ID**: `deepseek-ai/deepseek-v3.2-maas` > * **SDK**:
        OpenAI SDK (via Vertex AI Endpoint) > * **Input Prompt**: "Explain the
        concept of quantum computing..." > Do you confirm? [Yes/No]

## Phase 0: Environment Setup

**CRITICAL**: Before running any of the Python sample scripts in the `scripts/`
directory (e.g., `scripts/openmaas_openai_sdk.py`), you MUST ensure the
environment is correctly initialized by following these steps:

1.  **Google Cloud Authentication**: Authenticate with your Google Cloud
    credentials and configure active Application Default Credentials (ADC) for
    Agent Platform access:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

2.  **Enable API** (if not already enabled):

    ```bash
    gcloud services enable aiplatform.googleapis.com
    ```

3.  **Python Dependencies**: The scripts import `vertexai` (from
    `google-cloud-aiplatform`), `google-genai`, and `openai`. Do **not** create
    a virtual environment — it starts empty and hides packages the environment
    already provides, forcing a redundant install. Probe, and install only what
    is missing:

    ```bash
    python3 -c "import vertexai, google.genai, openai" \
      || pip install -r scripts/requirements.txt
    ```

    The pins in `scripts/requirements.txt` are a fallback for an environment
    that does not already provide these SDKs; do not apply them on top of a
    working environment.

4.  **Verify Setup (Optional)**: Run all sample scripts at once to verify the
    environment is working end-to-end:

    ```bash
    ./scripts/verify_all.sh
    ```

5.  **Execution**: Run the scripts with a plain `python3 scripts/...`. There is
    no environment to activate first.



> [!IMPORTANT] **CRITICAL: Model IDs & Availability** * **Gemini Models**: See
> [Gemini Models][gemini-models-docs] for valid Model IDs and Regions. *
> **OpenMaaS Models**: See
> [Use Open Models on Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/use-open-models)
> for Llama, DeepSeek, Qwen, etc. * **Incomplete Lists**: The Model IDs listed
> in this skill are **examples only** and may be incomplete or outdated. *
> **Action**: Always verify the Model ID and Region using the links above before
> generating code.
>
> \[gemini-models-docs]:
> https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate
>
>
> ## Workflow Decision Tree

1.  **Model Family Identification**: Has the user specified whether they want to
    call a **Gemini** (First-Party) model or an **OpenMaaS** (Third-Party, e.g.
    Llama, DeepSeek, Qwen) model?

    *   **No** -> Ask the user which model family they want to use. If they
        provide a specific model name, infer the family from the name.
    *   **Yes** -> Proceed to Step 2.

2.  **SDK Choice**: Which SDK does the user want to use?

    *   **Gemini + GenAI SDK** (preferred for Gemini) -> Proceed to [1. Gemini
        Models].
    *   **Gemini + legacy Vertex AI SDK** -> Proceed to [1. Gemini Models].
    *   **OpenMaaS + OpenAI SDK** (preferred for OpenMaaS) -> Proceed to [2.
        OpenMaaS Models].
    *   **OpenMaaS + GenAI SDK** -> Proceed to [2. OpenMaaS Models].
    *   **Unsure** -> Default to the preferred SDK for the chosen family.

3.  **Troubleshooting**: Is the user reporting an error (429 Resource Exhausted,
    400 User Validation, 404 Not Found, etc.)?

    *   **Yes** -> Proceed to [3. Troubleshooting & Common Error Codes].
    *   **No** -> Proceed with the SDK choice from Step 2.

## 0.5 Region Availability Check for Publisher Endpoints (Gemini + LoRA base)

> [!NOTE] **Skip this section** if either of these applies:
>
> - The user is calling a custom endpoint (§4) — a tuned Gemini model served on
>   a numeric `projects/.../endpoints/<id>`, a self-deployed OSS LLM (Llama,
>   DeepSeek, Qwen, Gemma, etc.), or a legacy custom model. Those requests hit
>   a specific endpoint resource whose region is fixed at deploy time; if the
>   caller-side region doesn't match, the endpoint lookup returns a clean 404
>   without incurring inference cost. Go to §4.
> - The user is calling an OpenMaaS publisher model (§2) — Llama, DeepSeek,
>   Qwen, etc. served via the global `openapi` base URL. These don't have
>   per-region availability restrictions in the same way first-party Gemini
>   does. Go to §2.
>
> **Apply this section** only if the user is calling a first-party managed
> Gemini model (`gemini-*`, via §1), including fine-tuned LoRA adapters on
> top of Gemini — these route through a publisher endpoint whose regional
> availability actually varies.

Before responding to any inference request that names a specific region for a
first-party managed Gemini model (`gemini-*`) or a fine-tuned Gemini LoRA
adapter (identified by numeric endpoint ID + user-stated base model), you
**MUST** verify the model is actually available in that region by making a
live API call. Do not rely on Google Search, training-corpus knowledge, or
publisher documentation for availability claims — regional availability
changes frequently and grounded text can be stale or wrong.

Probe only the exact model and region the user asked about. Do not probe other
models as a "control" — you cannot infer anything about model A's availability
from model B's status, because a different model may itself be unavailable in
the reference region for unrelated reasons.

For first-party Gemini models, probe with a real `:generateContent` call using
a minimal valid payload:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    "https://${LOCATION_ID}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_ID}/publishers/google/${MODEL_ID}:generateContent" \
    -d "{\"contents\":{\"role\":\"user\",\"parts\":{\"text\":\"${PROBE_TEXT:-hi}\"}}}"
```

For inference against a fine-tuned Gemini LoRA adapter, probe the **base
model** in the target region using the same `:generateContent` call above with
`${MODEL_ID}` set to the base (e.g. `gemini-2.5-flash` if the adapter was
tuned on `gemini-2.5-flash`). The LoRA adapter cannot serve in a region where
its base model isn't available.

Interpret the probe result and act:

-   **200** — model is available in that region. Proceed with the SDK setup in
    §1.
-   **404** — model is not available in that region. STOP. Tell the user
    plainly that the model isn't offered in that region and list the regions
    where it is available (from
    [Gemini Models][gemini-models-docs] or `gcloud ai model-garden models list
    --filter="name~$MODEL_NAME"` without `--region`). Do not silently switch
    regions. Do not proceed to write inference code or SDK initialization for
    the unsupported region. Do not run additional "control" probes to
    double-check the 404 — the target-region probe is authoritative.
-   **Any other outcome** (permission denied, quota, transient failure, etc.)
    — do not conclude the model is available or unavailable. Explain the
    underlying cause in plain language (e.g. "your account doesn't have access
    to this project's Vertex AI API — enable it in the console or switch
    projects") and the concrete next action.

## 1. Gemini Models

For Gemini models (e.g., `gemini-2.5-pro`, `gemini-3-flash-preview`), the
**GenAI SDK** (`google-genai`) is the **PREFERRED** method. The legacy
`vertexai` SDK is still supported but GenAI SDK is recommended for new projects.

> [!IMPORTANT]
> **Preview Models (including Gemini 3.1)** are often **ONLY** available in the
> `global` region. Stable models are available in `us-central1` and other
> regions.

### Choosing the Right SDK

*   **Gemini Models**: **GenAI SDK** (`google-genai`) is **PREFERRED**. Use
    OpenAI SDK for compatibility, or Legacy SDK (`vertexai`) if needed.
*   **OpenMaaS Models**: **OpenAI SDK** is **HIGHLY RECOMMENDED**. Use GenAI SDK
    or Legacy SDK if you have specific infrastructure requirements.

### Installation

```bash
pip install google-genai
```

### Python Example (GenAI SDK - Preferred)

See [`scripts/gemini_genai_sdk.py`](scripts/gemini_genai_sdk.py) for the
complete code.

### Alternative: OpenAI SDK (Chat Completions)

Use the standard OpenAI SDK with the Agent Platform endpoint. This is great for
cross-compatibility.

See [`scripts/gemini_openai_sdk.py`](scripts/gemini_openai_sdk.py) for the
complete code.

### Legacy: Agent Platform SDK

The legacy `vertexai` SDK is still widely used but `google-genai` is preferred
for new Gemini projects.

See [`scripts/gemini_vertexai_sdk.py`](scripts/gemini_vertexai_sdk.py) for the
complete code.

**Documentation**:
[Google GenAI SDK](https://github.com/googleapis/python-genai)

**Documentation**:
[Agent Platform Gemini Models](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/google-models)

## 2. OpenMaaS Models (Llama, DeepSeek, Qwen, etc.)

For OpenMaaS (Model-as-a-Service) models, the **HIGHLY RECOMMENDED** approach is
to use the standard **OpenAI SDK** with a specific Vertex AI endpoint.

> [!WARNING] While `GenerativeModel` *can* support some OpenMaaS models, it is
> **discouraged**. Use the OpenAI SDK for best compatibility (especially for
> Chat Completions).

### Installation

```bash
pip install openai google-auth
```

### Authentication for OpenAI SDK

You **MUST** use a Google Cloud OAuth access token as the API key for the OpenAI
SDK.

```python
import google.auth
from google.auth.transport.requests import Request

def get_gcp_access_token():
    creds, _ = google.auth.default()
    creds.refresh(Request())
    return creds.token
```

> [!NOTE] Google Cloud access tokens typically expire after 1 hour. The
> `get_gcp_access_token()` function above retrieves a *fresh* token at the time
> it is called. For long-running
> applications, you implement a refresh mechanism. See
> [Refresh the access token](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/openai/auth-and-credentials?hl=en#refresh_your_credentials)
> for details.

### Configuration (Base URL)



-   **Global Endpoint** (Recommended for most models requiring global
    availability):
    `https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/global/endpoints/openapi`
-   **Regional Endpoint**:
    `https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{REGION}/endpoints/openapi`


### Python Example (OpenMaaS - Chat Completions)

See [`scripts/openmaas_openai_sdk.py`](scripts/openmaas_openai_sdk.py) for the
complete code.

> [!TIP] **Alternative: Environment Variables** You can set environment
> variables in your shell instead of updating the code.
>
> **Alternative: Environment Variables** You can set environment variables in
> your shell instead of updating the code.

```bash
export OPENAI_BASE_URL="https://aiplatform.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/global/endpoints/openapi"
export OPENAI_API_KEY="$(gcloud auth application-default print-access-token)"
```
> Then initialize the client without arguments: `client = OpenAI()`

### Python Example (OpenMaaS - Completions API)

The following models support the legacy Completions API: `zai-org/glm-5-maas`,
`moonshotai/kimi-k2-thinking-maas`, `minimaxai/minimax-m2-maas`,
`deepseek-ai/deepseek-v3.1-maas`, and `deepseek-ai/deepseek-v3.2-maas`.

```python
response = client.completions.create(
    model="deepseek-ai/deepseek-v3.2-maas",
    prompt="Once upon a time",
    max_tokens=100
)
print(response.choices[0].text)
```

### Python Example (OpenMaaS - Embeddings)

```python
# Verify specific Embedding Model ID on Model Garden (e.g., intfloat/multilingual-e5-small)
response = client.embeddings.create(
    model="intfloat/multilingual-e5-large-maas",
    input="The quick brown fox jumps over the lazy dog",
)
print(response.data[0].embedding)
```

### Alternative: GenAI SDK

The `google-genai` SDK can also access OpenMaaS models via the `vertexai`
backend.

See [`scripts/openmaas_genai_sdk.py`](scripts/openmaas_genai_sdk.py) for the
complete code.

> [!IMPORTANT]
> **Model ID Format**: For GenAI SDK with OpenMaaS, you **MUST** use the full
> path: `publishers/PUBLISHER/models/MODEL` (e.g.,
> `publishers/zai-org/models/glm-5-maas`).

### Legacy: Agent Platform SDK (OpenMaaS)

For OpenMaaS, you can also use `GenerativeModel` (if supported).

See [`scripts/openmaas_vertexai_sdk.py`](scripts/openmaas_vertexai_sdk.py) for
the complete code.

> [!IMPORTANT] **Model ID Format**: For Agent Platform SDK with OpenMaaS, you
> **MUST** use the full path: `publishers/PUBLISHER/models/MODEL`.

### Model Reference & Availability

**Documentation**:
[Use Open Models on Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/use-open-models)

> [!TIP]
> **Self-Deployment for Control**: If you need **dedicated hardware**
> (GPUs/TPUs), **guaranteed capacity**, or **specific regional placement** not
> offered by MaaS, you can **Self-Deploy** these models to Agent Platform
> Endpoints. Search for the model in Model Garden and click "Deploy" to select
> your machine type. See the `agent-platform-deploy` skill for the deployment
> workflow, and **section 4 of this skill** for how to invoke the resulting
> self-deployed endpoint (use `/chat/completions` on the dedicated endpoint
> DNS, NOT the OpenMaaS publisher URL above).

> [!IMPORTANT] **Finding Inference Examples**: The list above is a starting
> point. For the **definitive** inference snippets (especially for Chat
> Completions payload structure): 1. Consult the
> [Use Open Models on Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/use-open-models)
> list. 2. Click the link for your specific model (e.g., "DeepSeek-V3") to visit
> its **Model Garden** page. 3. Look for the **"Sample Code"** or **"Use this
> model"** button on the Model Garden page to get the exact `curl` or Python
> code for that specific model version.

> [!NOTE] This list is **INCOMPLETE**. See
> [Use Open Models on Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/use-open-models)
> for the full list of supported models.

Model Family  | Model ID Examples                              | Location      | Notes
:------------ | :--------------------------------------------- | :------------ | :----
**Llama 4**   | `meta/llama-4-maverick-17b-128e-instruct-maas` | `us-east5`    |
**Llama 4**   | `meta/llama-4-scout-17b-16e-instruct-maas`     | `us-east5`    |
**Llama 3.3** | `meta/llama-3.3-70b-instruct-maas`             | `us-central1` |
**DeepSeek**  | `deepseek-ai/deepseek-v3.2-maas`               | `global`      | Global ONLY
**DeepSeek**  | `deepseek-ai/deepseek-v3.1-maas`               | `us-west2`    | US-West2 ONLY
**DeepSeek**  | `deepseek-ai/deepseek-r1-0528-maas`            | `us-central1` |
**Qwen 3**    | `qwen/qwen3-coder-480b-a35b-instruct-maas`     | `global`      |
**Qwen 3**    | `qwen/qwen3-next-80b-a3b-instruct-maas`        | `global`      |
**Kimi**      | `moonshotai/kimi-k2-thinking-maas`             | `global`      |
**MiniMax**   | `minimaxai/minimax-m2-maas`                    | `global`      |
**GLM**       | `zai-org/glm-4.7-maas`, `zai-org/glm-5-maas`   | `global`      |

## 4. Custom Endpoints (tuned Gemini, self-deployed OSS LLM, legacy custom)

This section covers how to invoke a model on an Agent Platform
**Endpoint** that belongs to your project — i.e., something with a
numeric resource name like
`projects/.../endpoints/5875254126916403200`. This is distinct from
calling the publisher MaaS surfaces in sections 2 and 3 (which hit
`publishers/.../models/...` or `endpoints/openapi`, not your endpoint
ID).

> [!IMPORTANT]
>
> **Publisher MaaS vs your endpoint (don't confuse them).** Section 3's
> OpenMaaS examples (e.g. `meta/llama-3.3-70b-instruct-maas`) hit a
> **shared publisher URL** at
> `/v1/projects/.../locations/.../endpoints/openapi`. This section's
> recipes hit **YOUR** endpoint at `/v1/projects/.../endpoints/<id>`.
> If you have a Llama / Gemma / etc. model deployed via Model Garden
> "Deploy" (NOT the MaaS publisher product), follow this section — not
> section 3.

> [!IMPORTANT]
>
> **Two orthogonal axes determine the call shape:**
>
> **Axis 1 — model family** drives the RPC method and payload:
>
> | Endpoint serves | Method | Payload |
> |---|---|---|
> | A **tuned Gemini model** (output of Gemini tuning — the endpoint is already deployed for you) | `:generateContent` | `contents` / `generationConfig` |
> | A **self-deployed OSS LLM** (Llama, DeepSeek, Qwen, Gemma, Mistral, etc., deployed via Model Garden) | `/chat/completions` | OpenAI-compatible `messages` |
> | A **legacy custom model** (classification, regression, custom-trained, embedding) | `:predict` | `instances` / `parameters` |
>
> Run `gcloud ai endpoints describe <ENDPOINT_ID> --region=<REGION>
> --format=json` and inspect `deployedModels[].model` to decide:
> contains `gemini` → tuned Gemini; matches an OSS publisher
> (`meta/`, `google/gemma-`, `deepseek-ai/`, `qwen/`, ...) → OSS LLM;
> otherwise → likely legacy custom.
>
> **Axis 2 — endpoint type (shared vs dedicated)** drives the URL host:
>
> | `dedicatedEndpointEnabled` | Host |
> |---|---|
> | `false` (default — shared endpoint) | `<REGION>-aiplatform.googleapis.com` |
> | `true` (dedicated endpoint, has its own DNS) | the value of `dedicatedEndpointDns` (format: `<ENDPOINT_ID>.<REGION>-<PROJECT_NUM>.prediction.vertexai.goog`) |
>
> A dedicated endpoint **cannot** be reached via the shared
> `<REGION>-aiplatform.googleapis.com` host (per the
> `Endpoint.dedicated_endpoint_enabled` proto: *"Once you enabled
> dedicated endpoint, you won't be able to send request to the shared
> DNS"*). Always check `dedicatedEndpointDns` in the describe output:
> if it's set, use it as the host; otherwise use the shared host.
>
> **Path is always
> `/v1/projects/.../locations/.../endpoints/<id>/...`** on both hosts.
> Both `/v1/` (GA) and `/v1beta1/` (beta) route to the same backend; the
> recipes in this skill use `/v1/`. The public
> [Gemma deployment notebook](https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/community/model_garden/model_garden_gemma_deployment_on_vertex.ipynb)
> still uses `/v1beta1/`, which also works.

### 4a. REST recipe — tuned Gemini model

Output of Gemini tuning is always an endpoint that's already deployed for
you, reachable on the shared host with `:generateContent`.

```bash
PROJECT_ID=my-project
ENDPOINT_ID=5875254126916403200
REGION=us-central1
TOKEN=$(gcloud auth application-default print-access-token)

curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/endpoints/${ENDPOINT_ID}:generateContent" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "Hello! Introduce yourself briefly."}]}
    ],
    "generationConfig": {
      "temperature": 0.2
    }
  }'
```

> [!WARNING]
>
> **If you set `maxOutputTokens`, be generous for thinking models.**
> Gemini 2.5 Pro (and other thinking-enabled models) emit "thoughts"
> tokens that count against `maxOutputTokens` BEFORE any user-visible
> text. With a small cap (e.g. 100), the entire budget is consumed by
> thoughts and the response has empty `text` parts but a non-zero
> `usageMetadata.candidatesTokenCount`.
>
> If you don't need to constrain output length, omit `maxOutputTokens`
> entirely and let the model emit as much as it wants. If you do set
> it: `>= 512` for any chat-like use, `>= 1024` for a paragraph of
> output. If you see `finishReason: "MAX_TOKENS"` and no `text`
> content in the response, your cap is too low.

### 4b. REST recipe — self-deployed OSS LLM (Llama, DeepSeek, Qwen, Gemma, etc.)

Self-deployed OSS LLMs may be on a **shared** or **dedicated** endpoint
depending on how the deploy was configured (`dedicated_endpoint_enabled`
at create time). The recipe below handles both cases by checking
`dedicatedEndpointDns` in the describe output.

```bash
PROJECT_ID=my-project
ENDPOINT_ID=5875254126916403200
REGION=us-central1
TOKEN=$(gcloud auth application-default print-access-token)

# Step 1: discover host. dedicatedEndpointDns is empty for shared endpoints.
DEDICATED_DNS=$(gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="value(dedicatedEndpointDns)")

if [ -n "$DEDICATED_DNS" ]; then
  HOST="$DEDICATED_DNS"
else
  HOST="${REGION}-aiplatform.googleapis.com"
fi

# Step 2: call /chat/completions. Path is identical for both hosts.
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://${HOST}/v1/projects/${PROJECT_ID}/locations/${REGION}/endpoints/${ENDPOINT_ID}/chat/completions" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello! Introduce yourself briefly."}
    ]
  }'
```

> [!NOTE]
>
> -   `max_tokens` (NOT `maxOutputTokens`) — this is OpenAI-compatible
>     vocabulary, not Vertex. Omit it entirely to let the model emit as
>     much as it wants; set it explicitly only if you need to cap output.
> -   The `"model"` field in the OpenAI-style payload can be omitted (or
>     set to `""`) for endpoint deployments — the endpoint already
>     determines which model serves the request.
> -   Same endpoint also exposes `/completions` (legacy text completion)
>     and `/embeddings` for embedding models.
> -   **Reasoning models** (DeepSeek-R1, Kimi-K2-Thinking, GLM-5 variants,
>     etc.) emit thinking tokens that count against `max_tokens` BEFORE
>     the final answer — same pathology as Gemini 2.5 Pro in section 4a.
>     If you DO set `max_tokens` and get an empty
>     `choices[0].message.content` or `finish_reason: "length"`, raise it
>     (>= 1024 for chat, >= 2048 for longer thinking chains) or omit it.

Python equivalent (OpenAI SDK) — mirrors the public
[Gemma deployment notebook](https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/community/model_garden/model_garden_gemma_deployment_on_vertex.ipynb):

```python
import google.auth
from google.auth.transport.requests import Request
import openai

from google.cloud import aiplatform

PROJECT_ID = "my-project"
ENDPOINT_ID = "5875254126916403200"
REGION = "us-central1"

aiplatform.init(project=PROJECT_ID, location=REGION)
endpoint = aiplatform.Endpoint(
    f"projects/{PROJECT_ID}/locations/{REGION}/endpoints/{ENDPOINT_ID}"
)
endpoint_resource_name = endpoint.resource_name  # full projects/.../endpoints/<id>
dedicated_dns = endpoint.gca_resource.dedicated_endpoint_dns  # empty if shared

host = dedicated_dns if dedicated_dns else f"{REGION}-aiplatform.googleapis.com"
base_url = f"https://{host}/v1/{endpoint_resource_name}"

creds, _ = google.auth.default()
creds.refresh(Request())

client = openai.OpenAI(base_url=base_url, api_key=creds.token)
response = client.chat.completions.create(
    model="",  # endpoint determines the served model
    messages=[{"role": "user", "content": "Hello! Introduce yourself briefly."}],
    # Omit max_tokens to let the model emit as much as it wants. Set it
    # only if you need to cap output length (see notes above).
)
print(response.choices[0].message.content)
```

See also: `agent-platform-deploy` skill section 4 "Verifying Deployment",
which uses the same pattern post-deploy.

### 4c. REST recipe — legacy `:predict` (custom / classification / embedding)

Same host-discovery logic as 4b (shared or dedicated based on
`dedicatedEndpointDns`):

```bash
DEDICATED_DNS=$(gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="value(dedicatedEndpointDns)")
HOST=${DEDICATED_DNS:-${REGION}-aiplatform.googleapis.com}

curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://${HOST}/v1/projects/${PROJECT_ID}/locations/${REGION}/endpoints/${ENDPOINT_ID}:predict" \
  -d '{
    "instances": [{"key": "value"}],
    "parameters": {}
  }'
```

The exact `instances` shape is model-specific; consult the deployed
model's documentation or the Model Garden card it was deployed from.

### 4d. Python (Vertex AI SDK) — tuned Gemini model

```python
from google import genai
import google.auth

_, project_id = google.auth.default()
client = genai.Client(vertexai=True, project=project_id, location="us-central1")

ENDPOINT_ID = "5875254126916403200"
response = client.models.generate_content(
    model=f"projects/{project_id}/locations/us-central1/endpoints/{ENDPOINT_ID}",
    contents="Hello! Introduce yourself briefly.",
    config={"temperature": 0.2},  # add max_output_tokens only if you need a cap
)
print(response.text)
```

## 5. Troubleshooting & Common Error Codes

### 429: Resource Exhausted

*   **Cause**: OpenMaaS and Gemini models use **Dynamic Shared Quota (DSQ)**.
    Resources are pooled and allocated dynamically based on availability. A 429
    error indicates the shared pool is temporarily exhausted, not necessarily
    that *your* specific project quota is hit (though it can be).
*   **Solution**: Implement strict **exponential backoff and retry** strategies.
*   **High Throughput**: For production workloads requiring high throughput or
    guaranteed capacity, consider **Provisioned Throughput (PT)**.
*   **Important**: Quota increases through normal cloud processes (Cloud
    Console) are **NOT** applicable for DSQ constraints.
*   **Documentation**:
    [Quotas and limits (DSQ)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/quotas)

### 400: User Validation Error

*   **Cause**: Invalid request format, unsupported parameter, or incorrect Model
    ID.
*   **Action**: Double-check your request payload and parameters. Verify the
    Model ID and Region are correct.
*   **Custom endpoints**: pick the right method + host per section 4's
    decision tables:
    *   Tuned Gemini + you called `:predict` → switch to `:generateContent`
        (section 4a). Error mentions "Required instances format mismatch".
    *   OSS LLM (Llama/DeepSeek/Qwen/Gemma/etc.) + you called
        `:generateContent` or `:predict` → switch to `/chat/completions`
        (section 4b). Error may be 404, 405, or "method not allowed".
    *   Legacy / custom-trained + you called `:generateContent` or
        `/chat/completions` → switch to `:predict` (section 4c).
*   **Dedicated endpoint reached on the shared host (or vice versa)**:
    *   Symptom: DNS resolution failure (`Could not resolve host`) or 404.
    *   Cause: dedicated endpoints don't accept traffic on
        `<REGION>-aiplatform.googleapis.com`, and the dedicated DNS
        (`*.prediction.vertexai.goog`) only exists when
        `dedicatedEndpointEnabled` is true.
    *   Action: re-check `gcloud ai endpoints describe ... --format=json`
        for the `dedicatedEndpointDns` field; use it iff non-empty (per
        the host-discovery snippets in section 4b/4c).

### Empty response text on Gemini deployed endpoints

*   **Cause**: `maxOutputTokens` is set too low. Gemini 2.5 Pro and other
    thinking models emit "thoughts" tokens that count against the budget
    BEFORE any user-visible text. With a small cap (e.g. 100), the entire
    budget is consumed by thoughts and the response has empty `text` parts
    but a non-zero `usageMetadata.candidatesTokenCount` and
    `finishReason: "MAX_TOKENS"`.
*   **Action**: Omit `maxOutputTokens` entirely (let the model emit as much
    as it wants), or raise it to >= 512 for chat-like use, >= 1024 for
    longer output. See section 4 "Custom Endpoints" for details.

### 404: Not Found / Model Not Available

*   **Cause**: The model is not enabled, or not available in the specified
    project or region.
*   **Action**:
    1.  **Check Location Availability**:
        *   **OpenMaaS**: Verify the model is available in your region. See
            [Model Availability by Location](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations#genai-open-models).
        *   **Gemini**:
            *   **Source of Truth**: Always check
                [Gemini Model Locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations#google-models)
                for the authoritative list.
            *   **Preview Models**: All Preview models (e.g., Gemini 3.1,
                experimental versions) are often **ONLY** available in the
                `us-central1` or `global` regions.
            *   **Stable Models**: (e.g., Gemini 2.5 Pro) Available in
                `us-central1`, `europe-west4`, and many other regions.
            *   **Important**: If you get a 404/400 error, try switching your
                client location to `us-central1` or `global`.
    2.  **Enable Llama Models**: For **Llama 3.3** and **Llama 4**, you **MUST**
        enable the model in Model Garden before use. Go to the
        [Model Garden](https://console.cloud.google.com/agent-platform/model-garden),
        search for the model card (e.g., "Llama 3.3 API Service"), and click
        **Enable**. Only then can you make inference requests.
