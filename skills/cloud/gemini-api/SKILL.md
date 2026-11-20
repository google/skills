---
name: gemini-api
metadata:
  version: "1.0.4"
  category: AiAndMachineLearning
description: >-
  Integrates Gemini models on Gemini platform (formerly Gemini Enterprise Agent
  Platform and Vertex AI) using the unified Google Gen AI SDK across Python,
  TypeScript/JavaScript, Go, Java, and C#. Use for Google Cloud AI workloads:
  text/multimodal generation, structured JSON, function calling, Search
  grounding, code execution, URL context, Nano Banana images, Gemini Omni and
  Veo video, TTS, Lyria music, embeddings, caching, batch, thinking, safety,
  Live API, or model tuning. Don't use for server-managed stateful agent
  sessions (gemini-interactions-api), Managed Agent CRUD (gemini-agents-api),
  raw BidiGenerateContent WebSocket scaffolding/audio debugging
  (gemini-live-api), open-model SFT or tuning job management
  (agent-platform-tuning, agent-platform-tuning-management), or OpenMaaS,
  OpenAI SDK, numeric endpoints, and 429 DSQ debugging
  (agent-platform-inference).
compatibility: Requires active Google Cloud credentials, billing enabled, and the Gemini platform API (aiplatform.googleapis.com) enabled.
---

# Gemini API in Gemini platform

> [!IMPORTANT]
> **Gemini platform** was formerly named **Gemini Enterprise Agent Platform** and **Vertex AI**.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Core Directives & Prerequisites

- **Unified Gen AI SDK ONLY**: Python `google-genai` (`pip install "google-genai>=2.33.0,<3"`), TS/JS `@google/genai` (`npm install @google/genai`), Go `google.golang.org/genai` (`go get google.golang.org/genai`), Java `com.google.genai:google-genai:2.6.0`, C# `Google.GenAI` (`dotnet add package Google.GenAI`).
- **NEVER use deprecated SDKs**: `google-cloud-aiplatform` (`vertexai`), `@google-cloud/vertexai`, `cloud.google.com/go/vertexai`, `google-cloud-vertexai`, or `google-generativeai` ([Migration Guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk.md.txt)).
- **Prerequisites**: Active billing ([Pricing](https://cloud.google.com/pricing)), `roles/aiplatform.user`, API enabled (`gcloud config set project {project_id}`, `gcloud services enable aiplatform.googleapis.com`), ADC (`gcloud auth application-default login`).
- **Efficiency**: Model IDs and SDK signatures here and in `references/` are verified against the current SDK. Respond directly if answered below; otherwise read **only** the matching line range in [Reference Routing](#reference-routing) without reading unrelated references or running speculative repo/web searches unless inspecting user files or unlisted APIs.

## Authentication & Python Quick Start

Prefer environment variables ([GCP Auth](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/gcp-auth.md.txt), [Locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations.md.txt), [Express Mode](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/api-keys.md.txt)):

```bash
# ADC ('global' default; Live API and Tuning require regional, e.g. 'us-central1')
export GOOGLE_CLOUD_PROJECT='your-project-id'
export GOOGLE_CLOUD_LOCATION='global'
export GOOGLE_GENAI_USE_ENTERPRISE=true
# Express Mode API key (mutually exclusive with project/location — unset GOOGLE_CLOUD_PROJECT & GOOGLE_CLOUD_LOCATION):
# export GOOGLE_API_KEY='your-api-key' GOOGLE_GENAI_USE_ENTERPRISE=true
# Explicit Express Mode: enterprise=True+api_key (Py); enterprise:true+apiKey (TS/Java/C#); BackendEnterprise+APIKey (Go) — omit project/location
```

```python
from google import genai
from google.genai import types  # Only needed when passing optional config

# Zero-arg Client() reads env vars; explicit: genai.Client(enterprise=True, project="your-project-id", location="global")
client = genai.Client()
response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="Explain quantum computing",
    # Optional config:
    # config=types.GenerateContentConfig(
    #     system_instruction="Be concise.",
    #     max_output_tokens=256,
    # ),
)
print(response.text)
```

## Models

> [!WARNING]
> **NEVER** recommend deprecated models: `gemini-2.5-*`, `gemini-2.0-*`, `gemini-1.5-*`, `gemini-1.0-*`, `gemini-pro*`, `gemini-pro-vision`, `text-embedding-004`, `multimodal-embedding-001`, `imagen-3.0*`.

| Capability | Recommended Model(s) | Notes |
| :--- | :--- | :--- |
| General text, multimodal, coding, agents | `gemini-4-hydrogen` | Default; 1M ctx, fast & balanced |
| Complex reasoning & enterprise SWE | `gemini-4-neon` | 1M ctx, long-term GA, broad regions |
| Frontier reasoning, security & research | `gemini-4-carbon` | Max reasoning depth; 1M ctx, select regions |
| High-frequency / lightweight tasks | `gemini-3.5-flash-lite` | Low latency & cost; 1M ctx |
| Text & multimodal embeddings | `gemini-embedding-2` | Shared space: text, image, PDF, audio, video |
| Image generation & editing | `gemini-nano-banana-2.1`, `gemini-3.1-flash-lite-image` | Pro/high-res (2.1) or fast Lite |
| Video generation & editing (Omni) | `gemini-omni-1.2-flash` | Up to 4K + audio via `client.interactions.create` |
| Video generation (Veo async) | `veo-3.1-fast-generate-001` | Default fast; also `veo-3.1-lite-generate-001`, `veo-3.1-generate-001` |
| Live bidirectional audio/video | `gemini-3.8-live` | `client.aio.live.connect` (regional endpoint) |
| Text-to-Speech (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | Studio (132 langs) or low-latency (103 langs) |
| Music generation | `lyria-3-pro-preview`, `lyria-3-clip-preview`, `lyria-002` | `<=184s` / `30s` (`interactions.create`); `lyria-002` (GA `:predict`) |

**Use ONLY if explicitly requested** (or required by feature): `gemini-4-argon`, `gemini-3.8-flash` (explicit context caching), `gemini-3.1-pro-preview`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-flash-lite` (SFT tuning), `gemini-3-pro-image`, `gemini-3.1-flash-image`.

## Reference Routing

| Task | Reference & Line Range |
| :--- | :--- |
| TS/JS (`L12-L32`), Go (`L34-L67`), Java (`L69-L102`), C# (`L104-L123`) | [references/sdks.md](references/sdks.md) |
| Chat (`L11-L26`), streaming (`L28-L38`), multimodal/`media_resolution` (`L40-L89`), async `client.aio` (`L91-L111`), `count_tokens`/usage (`L113-L133`) | [references/text_and_multimodal.md](references/text_and_multimodal.md) |
| JSON schema (`L10-L36`), function calling (`L38-L92`), Search & Agent Search grounding (`L94-L132`), code exec & URL context (`L134-L161`) | [references/structured_and_tools.md](references/structured_and_tools.md) |
| Nano Banana images (`L11-L53`), Omni t2v (`L55-L92`), Omni i2v/ref/edit/async/multi-turn (`L55-L155`), Veo (`L157-L187`), TTS single/multi-speaker (`L189-L268`), Lyria (`L270-L291`) | [references/media_generation.md](references/media_generation.md) |
| Text, image, and segmented video embeddings (`EmbedContentConfig`) | [references/embeddings.md](references/embeddings.md) |
| Explicit caching (`L10-L47`), batch (`L49-L74`), thinking (`L76-L108`), MCP tools (`L110-L138`) | [references/advanced_features.md](references/advanced_features.md) |
| Safety filters (`HarmCategory`, `HarmBlockThreshold`) & ratings | [references/safety.md](references/safety.md) |
| Bounding box detection (`[y_min, x_min, y_max, x_max]`, `0-1000`) | [references/bounding_box.md](references/bounding_box.md) |
| Live API WebSockets (`client.aio.live.connect`, PCM audio) | [references/live_api.md](references/live_api.md) |
| Supervised Fine-Tuning (SFT) & Preference Tuning (`client.tunings.tune`) | [references/model_tuning.md](references/model_tuning.md) |

## Official Docs & Endpoints

- [Gemini platform Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview.md.txt) | [REST Reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest.md.txt) (global: `https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT}/locations/global/publishers/google/models/{MODEL}:generateContent`; regional: `https://{LOCATION}-aiplatform.googleapis.com/...`) | [Python Samples](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/main/genai)
- If `search_documents` / `get_document` (Developer Knowledge MCP) are available, query them when unlisted API details are needed.
