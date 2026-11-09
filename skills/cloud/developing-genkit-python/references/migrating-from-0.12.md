# Migrating from Genkit Python 0.12 to 0.13

Genkit Python 0.13 aligns every symbol, signature, and error contract ahead of
1.0 without deprecation aliases. Use this reference when upgrading a 0.12
codebase or replacing 0.12 patterns (`ActionRunContext`, `ToolRunContext`,
`*_model()`, `GeminiConfigSchema`, `options=`, `abort_signal`, `restart_tool`,
`RuntimeErrorReason`, `add_gcp_telemetry`, `MediaPart`, `TextPart`, or
`from genkit.exp import Agent`).

- [Agent Guardrails Before Editing](#agent-guardrails-before-editing): Lines 25-51
- [1. Upgrade Packages Together](#1-upgrade-packages-together): Lines 55-70
- [2. Single-Home Namespace Layout](#2-single-home-namespace-layout): Lines 74-164
- [3. Removed Symbols and Enums Replaced by Strings](#3-removed-symbols-and-enums-replaced-by-strings): Lines 168-206
- [4. Model and Embedder Helpers, Constructors, and Plugins](#4-model-and-embedder-helpers-constructors-and-plugins): Lines 210-267
- [5. Config Classes, extra, tool_choice, and API Keys](#5-config-classes-extra-tool_choice-and-api-keys): Lines 271-327
- [6. Typed Contexts, Multipart Tools, Interrupts, and Cancellation](#6-typed-contexts-multipart-tools-interrupts-and-cancellation): Lines 331-421
- [7. Errors, HTTP Redaction (PublicError), and genkit.web](#7-errors-http-redaction-publicerror-and-genkitweb): Lines 425-488
- [8. Prompts, Structured Output, Validation, and Telemetry](#8-prompts-structured-output-validation-and-telemetry): Lines 492-525
- [9. Plugin and Custom Middleware Authors](#9-plugin-and-custom-middleware-authors): Lines 529-567
- [10. Evaluators (0.13 Only, Removed in 1.0)](#10-evaluators-013-only-removed-in-10): Lines 571-601
- [11. Verification Checklist](#11-verification-checklist): Lines 605-616

---

## Agent Guardrails Before Editing

1. **Stop before porting evaluators.** Evaluators (`define_evaluator`,
   `ai.evaluate`, `genkit.evaluator`, `genkit-evaluators`) still run in 0.13,
   but this is their last release: **Genkit 1.0 cuts them from the 1.0 release**
   (evaluation will return as an additive feature in a later release;
   `genkit-evaluators` 0.13 requires `genkit<1`). If the project contains
   evaluator code, stop and ask the developer before porting it. Recommend
   deleting evaluator code now; apply the 0.13 renames below only if the
   developer chooses to stay pinned to `0.13.*`.
2. **Audit HTTP-served error paths.** Over HTTP (`serve_flow`, `serve_agent`,
   `genkit_fastapi_handler`, `handle_genkit_request`, `genkit_flask_handler`,
   `genkit_django_handler`, `genkit.web`), `GenkitError` and unhandled
   exceptions now return
   `500 {"status": "INTERNAL", "message": "Internal Error"}`. Convert errors
   meant for callers (404, 401/403, domain validation) to
   `PublicError(status, message, details)`. Ask the developer before exposing
   any error message whose contents might include internal data or tenant state.
3. **Audit silent behavior changes.** Type checkers catch symbol renames and
   signatures, not runtime behavior changes:
   - Search for `{{` inside `ai.generate(prompt=..., system=...)` — strings
     there are now sent literally instead of rendered as Handlebars templates.
   - Search for reads of `response.output` — truncated or malformed JSON now
     returns `None` and sets `response.error` (`Failure` with
     `ErrorReason.INVALID_OUTPUT`).
   - Check `try` / `except GenkitError` blocks around `await my_flow(x)` or
     `await my_flow.run(x)` — actions now raise body exceptions unwrapped.

---

## 1. Upgrade Packages Together

Keep `genkit` and every `genkit-*` package on the same `0.13.*` minor line:

```bash
uv add 'genkit==0.13.*' 'genkit-google-genai==0.13.*'  # include every genkit-* package in use
```

- **Vertex AI Model Garden extras**: install extras for third-party SDKs:
  ```bash
  uv add 'genkit-vertexai[anthropic]'  # Claude on Model Garden
  uv add 'genkit-vertexai[openai]'     # Llama, Mistral, and OpenAI-compatible models
  ```
- **Flask**: `genkit-flask` no longer pulls in `genkit-google-genai`
  transitively. Run `uv add 'genkit-google-genai==0.13.*'` if the app uses
  Gemini.

---

## 2. Single-Home Namespace Layout

Every public symbol lives in one module listed in its `__all__`. Plugin
submodules (such as `genkit_openai.models` or `genkit_vertexai.model_garden`)
are private; import from each plugin's top-level package (`genkit_google_genai`,
`genkit_vertexai`, `genkit_openai`, etc.).

- **`genkit`**: application code (`Genkit`, `Message`, `Role`, `Part`, `Media`,
  `Document`, `ToolChoice`, `ModelResponse`, `ModelResponseChunk`,
  `ModelStreamResponse`, `StreamResponse`, `FinishReason`, `Failure`,
  `ErrorReason`, `GenkitError`, `PublicError`, `Flow`, `FlowContext`, `Tool`,
  `ToolContext`, `Interrupt`, `MultipartToolResponse`, `Prompt`, `Embedding`,
  `Operation`, `GenkitLogger`, `get_logger`).
- **`genkit.model`**: custom models and model inspection (`Model`, `ModelRef`,
  `BackgroundModel`, `ModelContext`, `ModelRequest`, `ModelInfo`,
  `ModelSupports`, `ModelStage`, `GenerationUsage`, `ConstrainedSupport`,
  `ModelConfig`).
- **`genkit.embedder`**: custom embedders (`Embedder`, `EmbedderRef`,
  `EmbedRequest`, `EmbedResponse`, `EmbedderInfo`, `EmbedderSupports`).
- **`genkit.evaluator`**: evaluator types (`Evaluator`, `BatchEvaluator`,
  `BaseDataPoint`, `EvaluatorResponse`, `Score`, `ScoreDetails`, `ScoreStatus`).
- **`genkit.middleware`**: writing custom middleware (`Middleware`,
  `MiddlewareContext`, `GenerateHookParams`, `ModelHookParams`,
  `ToolHookParams`). Note: the `Middleware()` plugin that registers `Retry`,
  `Fallback`, `ToolApproval`, `Skills`, and `Filesystem` lives in
  `genkit_middleware`.
- **`genkit.formats`**: custom output formatters (`Formatter`,
  `FormatterConfig`, `FormatHandler`).
- **`genkit.plugin_api`**: writing plugins (`Plugin`, `Action`, `ActionKind`,
  `GenkitConfig`, `provider_error`, `loop_local_client`, `GENKIT_USER_AGENT`).
- **`genkit.web`**: HTTP serving helpers (`RequestData`, `ContextProvider`,
  `to_sse`, `read_body`, `wants_stream`, `result_json`, `error_body`,
  `error_json`, `error_sse`, `error_status`).
- **`genkit.telemetry`**: custom tracing (`Instrumentation`, `SpanContext`,
  `configure_instrumentation`).
- **`genkit.testing`**: test doubles (`EchoModel`, `ScriptedModel`,
  `StaticResponseModel`, `define_echo_model`, `define_scripted_model`,
  `define_static_response_model`).
- **`genkit.exp` & `genkit.exp.agent`**: experimental agent APIs
  (`from genkit.exp import Genkit, current_session`;
  `from genkit.exp.agent import Agent, Session, InMemorySessionStore,
  FileSessionStore, remote_agent`).

Look up any moved symbol directly from the installed environment:

```bash
python - <<'EOF'
import importlib
target = 'ModelSupports'
for mod in [
    'genkit', 'genkit.model', 'genkit.embedder', 'genkit.evaluator',
    'genkit.middleware', 'genkit.formats', 'genkit.plugin_api', 'genkit.web',
    'genkit.telemetry', 'genkit.testing', 'genkit.exp', 'genkit.exp.agent',
]:
    if target in importlib.import_module(mod).__all__:
        print(mod)
EOF
```

### Renamed While Moving

```python
# Old (0.12)
from genkit import Constrained, ExecutablePrompt, ModelUsage, RuntimeErrorReason, Stage, Supports

# New (0.13)
from genkit import ErrorReason, Prompt
from genkit.model import ConstrainedSupport, GenerationUsage, ModelStage, ModelSupports
```

### Experimental (`exp`) Moves

```python
# Old (0.12)
from genkit.exp import Agent, AgentError, InMemorySessionStore, Session
from genkit_fastapi import serve_agent
from genkit_middleware import Artifacts

# New (0.13)
from genkit.exp import Genkit, current_session
from genkit.exp.agent import Agent, InMemorySessionStore, Session
from genkit_fastapi.exp import serve_agent
from genkit_middleware.exp import Artifacts
from genkit_google_cloud.exp import FirestoreSessionStore
```

`define_agent`, `define_custom_agent`, `define_prompt_agent`, and `@ai.agent()`
exist on `genkit.exp.Genkit`, not `genkit.Genkit`. `AgentError` is removed: a
failed turn sets `res.error` (`Failure`), and a call that produces no turn
raises `GenkitError`. Tools in a detached turn are cancelled with
`await task.abort()` instead of polling `abort_signal`.

---

## 3. Removed Symbols and Enums Replaced by Strings

0.12 model and config enums (`GoogleAIGeminiVersion`, `KnownGemini*`,
`KnownGpt`, `KnownClaude`, `*Version`, `GeminiEmbeddingModels`,
`VertexEmbeddingModels`, `EmbeddingTaskType`, `VertexAIEvaluationMetricType`)
are removed. Pass plain string values; helper signatures use `Literal` unions
for static checking while still accepting new model IDs as strings.

```python
# Old (0.12)
from genkit_google_genai import GoogleAI, GoogleAIGeminiVersion

model = GoogleAI.gemini_model(GoogleAIGeminiVersion.GEMINI_3_FLASH_PREVIEW)

# New (0.13)
from genkit_google_genai import GeminiConfig, GoogleAI

model = GoogleAI.gemini('gemini-3-flash-preview')
cfg = GeminiConfig(thinking_level='HIGH')  # checked against 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH'
```

Other removed items and their 0.13 replacements:

- **`MediaPart` and `TextPart` (`Part(root=...)`)**: removed (`Part(root=...)`
  raises `ValueError`). Construct parts with `Part.from_text('...')` (or
  `Part(text='...')`) and `Part.from_media(url, content_type='image/jpeg')` (or
  `Part(media=Media(url=..., content_type=...))`). Read via `part.text` and
  `part.media`.
- **Name helpers** (`bedrock_name`, `anthropic_name`, `ollama_name`,
  `openai_model`, `genkit_eval_name`, `package_name`): pass `'plugin/model'`
  strings (e.g. `'openai/gpt-4o'`) or typed model refs (`OpenAI.gpt('gpt-4o')`).
- **`GoogleAI.imagen_model(...)`**: Imagen catalog is retired; use
  `GoogleAI.gemini_image('gemini-2.5-flash-image')`.
- **`Candidate`**: read `response.message` directly.
- **`Document.data`, `Document.data_type`, `Document.from_data()`**: construct
  with `Document(content=[...], metadata=...)`, `Document.from_text(...)`, or
  `Document.from_media(...)`.
- **`ai.registry`**: use lookup helpers directly on `Genkit` (e.g.
  `ai.prompt(...)`).

---

## 4. Model and Embedder Helpers, Constructors, and Plugins

Model helpers drop `_model`, and `.embedding()` becomes `.embedder()`:

```python
# Old (0.12)
GoogleAI.gemini_model('gemini-flash-latest')
GoogleAI.gemini_image_model('gemini-2.5-flash-image')
GoogleAI.gemini_tts_model('gemini-2.5-flash-preview-tts')
GoogleAI.embedding('gemini-embedding-001')
VertexAI.veo_model('veo-3.1-generate-001')
Anthropic.claude_model('claude-sonnet-4-6')

# New (0.13)
GoogleAI.gemini('gemini-flash-latest')
GoogleAI.gemini_image('gemini-2.5-flash-image')
GoogleAI.gemini_tts('gemini-2.5-flash-preview-tts')
GoogleAI.embedder('gemini-embedding-001')
VertexAI.veo('veo-3.1-generate-001')
Anthropic.claude('claude-sonnet-4-6')
OpenAI.gpt('gpt-5.2')
```

### Keyword-Only Signatures

`Genkit(...)`, plugin constructors, `GenkitError(...)`, and options after an
action's single input on `.run(...)` are keyword-only:

```python
# Old (0.12)
ai = Genkit([GoogleAI()], GoogleAI.gemini_model('gemini-flash-latest'))
out = await my_flow.run(data, on_chunk, ctx)

# New (0.13)
ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))
out = await my_flow.run(data, on_chunk=on_chunk, context=ctx)
```

### Provider Plugin Updates

```python
# VertexAI (in genkit_google_genai): project_id= -> project=
from genkit_google_genai import VertexAI
VertexAI(project='my-project', location='us-central1')

# Vertex AI Model Garden (in genkit_vertexai): ModelGardenPlugin -> ModelGarden
from genkit_vertexai import ModelGarden
ModelGarden(project='my-project', location='us-central1')

# Ollama: server_address= -> base_url=; pulled models resolve automatically (no ModelDefinition/EmbeddingDefinition)
import os
from genkit_ollama import Ollama
Ollama(base_url=os.getenv('OLLAMA_HOST'))  # local file paths for media are no longer read

# Amazon Bedrock: ModelDefinition removed; BedrockImageConfig -> StabilityImageConfig
from genkit_amazon_bedrock import Bedrock, StabilityImageConfig
Bedrock(region='us-east-1', models=['us.amazon.nova-lite-v1:0'])
```

---

## 5. Config Classes, `extra`, `tool_choice`, and API Keys

### Flat Config Classes

`*ConfigSchema` classes drop the `Schema` suffix and flatten nested provider
dicts. Unknown or nested keys (such as `thinking_config` or a typo like
`'temprature'`) raise `GenkitError` (`INVALID_ARGUMENT`) before calling the
model.

```python
# Old (0.12)
from genkit_google_genai import GeminiConfigSchema, GeminiImageConfigSchema, GeminiTtsConfigSchema, GemmaConfigSchema
config = {'thinking_config': {'thinking_level': 'HIGH', 'include_thoughts': True}}
config = {'google_search_retrieval': True}
config = {'speech_config': {'voice_config': {'prebuilt_voice_config': {'voice_name': 'Kore'}}}}

# New (0.13)
from genkit_google_genai import GeminiConfig, GeminiImageConfig, GeminiTtsConfig, GemmaConfig
cfg1 = GeminiConfig(thinking_level='HIGH', include_thoughts=True, google_search=True)
cfg2 = GeminiTtsConfig(voice='Kore')
```

```python
# Anthropic flat config (ThinkingConfig, OutputConfig, TaskBudget, RequestMetadata, *ToolChoice removed)
from genkit_anthropic import AnthropicConfig
cfg = AnthropicConfig(thinking='enabled', thinking_budget=1024)
cfg_adaptive = AnthropicConfig(thinking='adaptive', effort='high', task_budget=20000, user_id='diner-42')
```

- **Unmodeled provider fields (`extra`)**: pass provider-specific keys not
  declared on the config class in `extra={...}` (supported across Gemini, Veo,
  Interactions, OpenAI, Anthropic, Ollama, and Bedrock). `OpenAIConfig.user` is
  removed; use `extra={'user': '...'}` if needed.
  ```python
  from genkit_amazon_bedrock import BedrockConfig
  cfg = BedrockConfig(extra={'some_provider_option': 1})
  ```
- **Config layering**: defaults merge key-by-key (`ModelRef` < `Prompt` < call).
  Pass `None` for a field to clear an inherited key.
- **`tool_choice` on `generate`**: moved out of `config` onto
  `ai.generate(...)`:
  ```python
  # Old (0.12): config={'tool_choice': {'type': 'any'}}
  await ai.generate(prompt='Check weather in Tokyo.', tools=[get_weather], tool_choice='required')  # 'auto' | 'required' | 'none'
  ```
- **`options=` -> `config=` on `embed` and `evaluate`**:
  ```python
  await ai.embed(embedder=GoogleAI.embedder('gemini-embedding-001'), content='doc', config={'task_type': 'RETRIEVAL_DOCUMENT'})
  ```
- **API keys rejected in `config`**: passing `api_key` in `config` now raises
  `GenkitError` (`INVALID_ARGUMENT`) in every plugin. Set the key on the plugin
  or pass per-request keys in `context`:
  ```python
  await ai.generate(prompt='Hello', context={'secrets': {'api_key': user_key}})
  ```
  Note: `ModelGarden` uses ADC only and rejects per-request keys; `ai.embed()`
  has no `context` parameter and always uses the plugin's key.

---

## 6. Typed Contexts, Multipart Tools, Interrupts, and Cancellation

### Typed Contexts (`FlowContext`, `ToolContext`, `ModelContext`)

`ActionRunContext` and `ToolRunContext` are removed from `genkit`. Chunk types
move from `@ai.flow(chunk_type=...)` into the generic parameter on `FlowContext`
/ `ToolContext`. Every action accepts at most one input parameter plus an
optional typed context; Genkit finds the context by its type annotation. The new
contexts subclass `ActionRunContext`, so an old annotation still type-checks
once the import is fixed.

```python
from pydantic import BaseModel
from genkit import FlowContext, ModelResponse, MultipartToolResponse, Part, ToolContext
from genkit.model import ModelContext, ModelRequest

class Status(BaseModel):
    step: str

# Flow streaming typed chunks
@ai.flow()
async def plan_trip(city: str, ctx: FlowContext[Status]) -> str:
    ctx.send_chunk(Status(step='searching flights'))
    return f'Planned {city}'

# Tool streaming typed chunks + returning multipart content
@ai.tool()
async def capture_chart(metric: str, ctx: ToolContext[Status]) -> MultipartToolResponse:
    ctx.send_chunk(Status(step='rendering'))
    png = Part.from_media('data:image/png;base64,iVBORw0KGgo=', content_type='image/png')
    return MultipartToolResponse(output={'ok': True, 'metric': metric}, content=[png])

# Custom model implementation
async def my_model_fn(request: ModelRequest, ctx: ModelContext) -> ModelResponse:
    ...
```

### Multipart Tool Responses

`from genkit import response` is removed. Replace
`response({'ok': True}, parts=[png])` with
`MultipartToolResponse(output={'ok': True}, content=[png])` (see `capture_chart`
above).

### Interrupts

- `restart_tool` and `respond_to_interrupt` are replaced by methods on the
  interrupt `Part`:
  ```python
  # Old (0.12): restart_tool(interrupt=intr, resumed_metadata={'approved': True})
  # Old (0.12): respond_to_interrupt({'status': 'declined'}, interrupt=intr)

  # New (0.13)
  restart = intr.restart(resumed_metadata={'approved': True})
  reply = intr.respond({'status': 'declined'})
  ```
- `Interrupt` now subclasses `BaseException` (like `asyncio.CancelledError`) so
  a tool's `except Exception:` cannot swallow an approval interrupt. Catch
  `Interrupt` explicitly only if inspecting and re-raising it.

### Native `asyncio` Cancellation

`ctx.abort_signal` is removed. Delete `if ctx.abort_signal.is_set(): raise ...`
checks; cancellation uses standard `asyncio.CancelledError`, propagating into
model requests, retry sleeps, and running tools at any `await`. If a tool
catches `asyncio.CancelledError`, it must re-raise it.

```python
import asyncio

# Cancel an in-flight call
task = asyncio.create_task(ai.generate(prompt='Draft a long report.'))
task.cancel()

# Stop a flow stream early - MUST use `async with` (or `await stream.aclose()`),
# otherwise a bare `break` leaves the background flow running.
async with plan_trip.stream('Kyoto') as stream:
    async for chunk in stream:
        if chunk.step == 'searching flights':
            break  # cancels plan_trip; stream.response raises CANCELLED

# Put partial-work cleanup in `finally` inside tools
@ai.tool()
async def reserve_table(party_size: int) -> dict:
    hold_id = await acquire_hold(party_size)
    try:
        return await confirm_hold(hold_id)
    finally:
        if not await is_confirmed(hold_id):
            await release_hold(hold_id)
```

---

## 7. Errors, HTTP Redaction (`PublicError`), and `genkit.web`

### Returned vs Raised Errors

- **Returned errors (`Failure`)**: `res.error`, `operation.error`, and
  `agent_res.error` are typed `Failure`
  (`from genkit import ErrorReason, Failure`) with `.status`, `.message`,
  `.details`, and `.reason`. `RuntimeErrorReason` is renamed to `ErrorReason`.
- **Raised errors (`GenkitError`)**: `e.original_message`, `e.http_code`,
  `e.trace_id`, and `e.cause` are removed. Read `e.message`, `e.status`,
  `e.details`, `e.reason`, and `e.__cause__`.
- **Plugin exception classes removed**: classes like `OllamaConnectionError` are
  gone; inspect `e.status` (e.g. `if e.status == 'UNAVAILABLE':`).
- **Action exceptions are unwrapped**: `await my_flow.run(x)` raises the
  exception the body raised. Replace `except GenkitError` wrappers that were
  catching your own exception types with those types directly. `Retry` and
  `Fallback` only retry failures a plugin classified (such as `UNAVAILABLE`).

### HTTP Serving & `PublicError`

In-process calls (`await my_flow(x)`, `await my_flow.run(x)`) see full unwrapped
exceptions. Over HTTP, Genkit redacts internal failures:

- **`PublicError(status, message, details)`**: returns the matching HTTP status
  (e.g. `NOT_FOUND` -> 404, `UNAUTHENTICATED` -> 401, `PERMISSION_DENIED` ->
  403) with `status`, `message`, and `details`.
- **Invalid top-level flow input**: returns 400 with field names and Pydantic's
  built-in messages (custom validator strings are replaced with `Invalid value`
  unless the validator raises `PublicError`).
- **All other `GenkitError`s, provider errors, and Python exceptions**: logged
  server-side with traceback and returned to the client as
  `500 {"status": "INTERNAL", "message": "Internal Error"}`.
- **Streaming**: the same body arrives inside a `data: {"error": {...}}` SSE
  frame.

Everything in a `PublicError`'s `message` and `details` reaches the client
verbatim; keep secrets and other tenants' IDs out of it.

**Context providers**: `RequestData` moves from `genkit.plugin_api` to
`genkit.web` and exposes `.method`, `.headers`, and `.input` on Flask, FastAPI,
and Django. Replace framework-specific reads like
`req.request.META.get('HTTP_AUTHORIZATION')` with
`req.headers.get('authorization')`.

```python
from genkit import PublicError
from genkit.web import RequestData, error_body, error_status

async def auth_context(req: RequestData) -> dict:
    token = req.headers.get('authorization')
    if not token:
        raise PublicError('UNAUTHENTICATED', 'Missing bearer token')  # 401
    return {'user': await verify_token(token)}

@ai.flow()
async def get_order(order_id: str) -> dict:
    order = await db_find(order_id)
    if order is None:
        raise PublicError('NOT_FOUND', f'Order {order_id} not found')  # 404
    return order
```

For hand-written HTTP routes that call `my_flow.run(...)` directly, serialize
errors with `error_body(e)` and `error_status(e)` from `genkit.web`.

---

## 8. Prompts, Structured Output, Validation, and Telemetry

- **No Handlebars rendering in `ai.generate`**:
  `ai.generate(prompt='Hi {{name}}')` sends `'Hi {{name}}'` verbatim. Move
  templates to `ai.define_prompt(name='greet', prompt='Hi {{name}}')` or
  `.prompt` files.
- **Prompt calls & validation**:
  `await prompt({'dish': 'pie'}, config={'temperature': 0.2})` validates input
  against `input.schema`, fills in `.prompt` defaults, merges `config`
  key-by-key over the prompt's config, and locks `output_schema` at definition
  time.
- **Truncated structured output**: if a reply hits `max_output_tokens` or
  produces invalid JSON, `res.output` is `None` and
  `res.error.reason == ErrorReason.INVALID_OUTPUT`:
  ```python
  res = await ai.generate(prompt='...', output_schema=City)
  if res.output is None:
      raise RuntimeError(f'Structured output failed: {res.error}')
  ```
- **Flow I/O validation**: flow inputs and return values are validated against
  their type annotations, so a flow that returns the wrong shape raises;
  `{"data": null}` over HTTP uses the parameter default.
- **Media URL limit**: media URLs over 20 MB fail instead of downloading into
  memory.
- **Telemetry**:
  ```python
  # Old (0.12): add_gcp_telemetry(project_id='my-project', force_dev_export=True)
  # New (0.13): FIREBASE_PROJECT_ID fallback removed; pass project= or set GOOGLE_CLOUD_PROJECT
  from genkit_google_cloud import enable_google_cloud_telemetry
  enable_google_cloud_telemetry(project='my-project')

  # Custom trace instrumentation (replaces tracer / add_custom_exporter / AdjustingTraceExporter)
  from genkit.telemetry import Instrumentation, configure_instrumentation
  ```

---

## 9. Plugin and Custom Middleware Authors

```python
# Custom middleware: BaseMiddleware -> Middleware, GenerateMiddlewareContext -> MiddlewareContext
from pydantic import BaseModel
from genkit.middleware import Middleware, MiddlewareContext

class PiiRedactConfig(BaseModel):
    mask: str = '[REDACTED]'

@ai.middleware
class PiiRedact(Middleware[PiiRedactConfig]):
    name = 'pii_redact'

    async def model(self, params, ctx: MiddlewareContext, next_fn):
        return await next_fn(params, ctx)
```

- `GenerateMiddleware`, `MiddlewareRef`, `MiddlewarePlugin`, and
  `new_middleware` are removed; `Middleware.tools()` returns `Tool` handles.
- Removed `genkit.plugin_api` helpers and their replacements:
  ```python
  # Old (0.12)
  from genkit.plugin_api import model, model_ref, background_model, embedder, embedder_ref, ModelConfig
  from genkit.plugin_api import wrap_http_error, from_http_code, parse_retry_after_ms
  from genkit.plugin_api import get_cached_client, GENKIT_CLIENT_HEADER, GENKIT_VERSION, tracer, add_custom_exporter

  # New (0.13)
  from genkit import get_logger
  from genkit.embedder import Embedder, EmbedderRef
  from genkit.model import BackgroundModel, Model, ModelConfig, ModelRef
  from genkit.plugin_api import GENKIT_USER_AGENT, GenkitConfig, loop_local_client, provider_error
  from genkit.telemetry import Instrumentation, configure_instrumentation
  ```
- Custom formatters import `Formatter`, `FormatterConfig`, and `FormatHandler`
  from `genkit.formats`.
- `Plugin.resolve(kind, name)` now receives `name` **without** the `'myplugin/'`
  prefix. `Plugin.model()`, `Plugin.embedder()`, and `Supports.context` are
  removed. `generate_operation` receives only what a background start uses.

---

## 10. Evaluators (0.13 Only, Removed in 1.0)

Apply only if the developer explicitly confirms keeping evaluators pinned to
`genkit==0.13.*`. Renames: `EvalFnResponse` -> `EvaluatorResponse`,
`EvalStatusEnum` -> `ScoreStatus`, `Details` -> `ScoreDetails`; `evaluation` is
now a `list[Score]`; `ai.define_evaluator(name=..., fn=...)` becomes positional
`(name, fn)`; `display_name=` and `definition=` stay required keywords.
`EvaluatorResponse` requires `test_case_id`.

```python
from genkit.evaluator import BaseDataPoint, EvaluatorResponse, Score, ScoreDetails, ScoreStatus

async def exact_match(dp: BaseDataPoint, _options: object = None) -> EvaluatorResponse:
    passed = str(dp.output or '').strip() == str(dp.reference or '').strip()
    return EvaluatorResponse(
        test_case_id=dp.test_case_id or '',
        evaluation=[
            Score(
                score=1.0 if passed else 0.0,
                status=ScoreStatus.PASS if passed else ScoreStatus.FAIL,
                details=ScoreDetails(reasoning='Exact string match'),
            )
        ],
    )

# Positional (name, fn); display_name and definition are required keywords
ai.define_evaluator('byo/exact_match', exact_match, display_name='Exact Match', definition='Exact string match.')

# options= -> config=; returns list[EvaluatorResponse] directly (no .root)
results = await ai.evaluate(evaluator='byo/exact_match', dataset=rows, config={})
```

---

## 11. Verification Checklist

1. Run the project's type checker (`pyright`, `mypy`, or `ty`) — catches moved
   imports, enum-to-`Literal` arguments, keyword-only calls,
   `FlowContext`/`ToolContext` generics, and `OutputT | None` checks on
   `response.output`.
2. Grep for `{{` inside `ai.generate(` calls and move templates to
   `ai.define_prompt` or `.prompt` files. Grep for reads of `response.output`
   that assume it is never `None`.
3. Grep for `GenkitError` inside HTTP-served flows and context providers;
   convert caller-facing errors to `PublicError`.
4. Run the test suite.
