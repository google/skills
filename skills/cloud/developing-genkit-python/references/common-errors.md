# Common Errors — Genkit Python 0.13

Find the symptom, apply the fix. Every message below comes from a real 0.13 run.
Upgrading a 0.12 codebase? Read
[Migrating from 0.12 to 0.13](migrating-from-0.12.md).

- [ai.generate Returns Empty Text and Does Not Raise](#aigenerate-returns-empty-text-and-does-not-raise): Lines 25-57
- [Thinking level MINIMAL is not supported for this model](#thinking-level-minimal-is-not-supported-for-this-model): Lines 61-80
- [ImportError on ActionRunContext, ToolRunContext, MediaPart, TextPart, or genkit.agent](#importerror-on-actionruncontext-toolruncontext-mediapart-textpart-or-genkitagent): Lines 84-119
- [GenkitError INVALID_ARGUMENT on Config Keys](#genkiterror-invalid_argument-on-config-keys): Lines 123-151
- [GenkitError INVALID_ARGUMENT: API Key in config](#genkiterror-invalid_argument-api-key-in-config): Lines 155-167
- [GenkitError NOT_FOUND: Unprefixed Model String](#genkiterror-not_found-unprefixed-model-string): Lines 171-183
- [Vertex AI Fails on gemini-flash-latest](#vertex-ai-fails-on-gemini-flash-latest): Lines 187-197
- [TypeError When Defining or Calling Flows and Tools](#typeerror-when-defining-or-calling-flows-and-tools): Lines 201-232
- [Served Flow Returns 404, 500, or the Wrong Auth Status](#served-flow-returns-404-500-or-the-wrong-auth-status): Lines 236-271
- [response.output Is None on Structured Output](#responseoutput-is-none-on-structured-output): Lines 275-290
- [response.json Is Not the Model Output](#responsejson-is-not-the-model-output): Lines 294-305
- [Prompt Variable Sent Literally](#prompt-variable-sent-literally): Lines 309-319
- [Streaming TypeError or a Flow That Keeps Running After break](#streaming-typeerror-or-a-flow-that-keeps-running-after-break): Lines 323-344
- [Cloud Telemetry Enabled but Spans Do Not Reach Cloud Trace](#cloud-telemetry-enabled-but-spans-do-not-reach-cloud-trace): Lines 348-359
- [Interrupts and Agent Session Pitfalls](#interrupts-and-agent-session-pitfalls): Lines 363-392

---

## `ai.generate` Returns Empty Text and Does Not Raise

`ai.generate` boxes model-side failures into the response: provider rejections,
`UNAVAILABLE`, rate limits, and model IDs the provider does not serve. You get
`response.text == ''`, `response.finish_reason == 'failed'`, and a `Failure` on
`response.error`. Code that only reads `response.text` silently continues with
an empty string.

```python
from genkit import Genkit
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()])

# 1. Prefixed but unserved model ID: no exception
res = await ai.generate(model='googleai/gemini-9-ultra', prompt='Suggest a dish.')
print(repr(res.text), res.finish_reason)
# => '' FinishReason.FAILED

# 2. Check response.error after every call
if res.error:
    print(res.error.status, res.error.message)
    # => NOT_FOUND models/gemini-9-ultra is not found for API version v1beta, or is not supported for generateContent. ...
```

Problems caught before the request is sent raise instead:

- **`ValueError`** from `GoogleAI()` when `GEMINI_API_KEY` is unset
  (`[Genkit] GEMINI_API_KEY environment variable not set.`).
- **`GenkitError` `UNAUTHENTICATED`** on the first `ai.generate` when the key is
  invalid (`API key not valid. Please pass a valid API key.`).
- **`GenkitError`** for an unprefixed model string, unknown config keys, and
  `api_key` in config (sections below).

---

## `Thinking level MINIMAL is not supported for this model`

`gemini-flash-latest` rejects `thinking_level='MINIMAL'`. The call returns a
failed response (see above), not an exception:

```python
from genkit_google_genai import GeminiConfig

res = await ai.generate(prompt='Name one dessert.', config=GeminiConfig(thinking_level='MINIMAL'))
print(res.error.status, res.error.message)
# => INVALID_ARGUMENT Thinking level MINIMAL is not supported for this model. Please retry with other thinking level.
```

Use `'LOW'`, `'MEDIUM'`, or `'HIGH'`:

```python
res = await ai.generate(prompt='Name one dessert.', config=GeminiConfig(thinking_level='LOW'))
print(res.text)
# => Tiramisu.
```

---

## `ImportError` on `ActionRunContext`, `ToolRunContext`, `MediaPart`, `TextPart`, or `genkit.agent`

```text
ImportError: cannot import name 'ActionRunContext' from 'genkit'
ImportError: cannot import name 'MediaPart' from 'genkit'
ModuleNotFoundError: No module named 'genkit.agent'
AttributeError: 'Genkit' object has no attribute 'define_agent'
ValidationError: 1 validation error for Part
  Value error, Part(root=...) is gone; use Part.from_text or Part(text=...)
```

Each symbol has one public home:

```python
# Contexts
from genkit import FlowContext, ToolContext
from genkit.model import ModelContext

# Parts
from genkit import Media, Message, Part, Role
text_part = Part.from_text('Hello')
img_part = Part.from_media('https://example.com/photo.jpg', content_type='image/jpeg')

# Experimental agents and integrations (define_agent exists only on genkit.exp.Genkit)
from genkit.exp import Genkit, current_session
from genkit.exp.agent import Agent, InMemorySessionStore, Session
from genkit_fastapi.exp import serve_agent
from genkit_middleware.exp import Artifacts
```

Two different `Middleware` imports:

- `from genkit_middleware import Middleware, Retry, ToolApproval` imports the
  **`Middleware()` plugin** and built-in middleware.
- `from genkit.middleware import Middleware, MiddlewareContext` imports the
  **base class** for custom middleware.

---

## `GenkitError` `INVALID_ARGUMENT` on Config Keys

Genkit validates config before calling the model. Typos, nested dicts, and
fields that moved off config all raise:

```text
INVALID_ARGUMENT: googleai/gemini-flash-latest: unknown config key 'temprature'; put provider-only settings in config['extra']
INVALID_ARGUMENT: thinking_config was flattened; use include_thoughts / thinking_budget / thinking_level
INVALID_ARGUMENT: googleai/gemini-flash-latest: unknown config key 'tool_choice'; put provider-only settings in config['extra']
```

Use flat typed config, put provider-native keys in `extra`, and pass
`tool_choice` on the call:

```python
from genkit_google_genai import GeminiConfig

cfg = GeminiConfig(
    temperature=0.2,
    thinking_level='HIGH',
    include_thoughts=True,
    extra={'seed': 7},
)
res = await ai.generate(prompt='Pick a wine for salmon.', config=cfg, tool_choice='required', tools=[...])
```

`GeminiConfig.extra` is wire-shaped and deep-merged into the request body, so
nested provider fields go under their wire key (for example
`extra={'generationConfig': {...}}`).

---

## `GenkitError` `INVALID_ARGUMENT`: API Key in `config`

```text
INVALID_ARGUMENT: API key belongs in context.secrets, not config. Pass the key as context={'secrets': {'api_key': ...}}.
```

Set the key on the plugin, or pass a per-request key in `context`:

```python
# Whole app: GoogleAI(api_key=...), OpenAI(api_key=...)
# Per request:
await ai.generate(prompt='Hello', context={'secrets': {'api_key': user_key}})
```

---

## `GenkitError` `NOT_FOUND`: Unprefixed Model String

```text
NOT_FOUND: Failed to resolve model 'gemini-flash-latest'. Ensure the model name includes the plugin namespace (e.g., 'plugin/model').
```

Plain strings need the `<plugin>/` prefix (`'googleai/gemini-flash-latest'`,
`'openai/gpt-4o'`). Model ref helpers (`GoogleAI.gemini('gemini-flash-latest')`,
`Anthropic.claude('claude-sonnet-4-6')`, `OpenAI.gpt('gpt-5.2')`) add it for
you.

A prefixed ID the provider does not serve resolves and fails at call time on
`response.error` instead (see the first section).

---

## Vertex AI Fails on `gemini-flash-latest`

Vertex AI does not serve the Gemini API's rotating `-latest` aliases
(`gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-pro-latest`). The
Vertex plugin's known-model list omits them. Use a versioned ID:

```python
from genkit_google_genai import VertexAI

ai = Genkit(plugins=[VertexAI(location='us-central1')], model=VertexAI.gemini('gemini-3.5-flash'))
```

---

## `TypeError` When Defining or Calling Flows and Tools

```text
TypeError: Tool function must be async. Got sync function: lookup_reservation
TypeError: Flow must be async: sync_menu
TypeError: tool 'check_allergens' takes one input, but 'allergen' is a second parameter. Put the fields on one input model, or annotate 'allergen' as ToolContext.
TypeError: Genkit() takes no positional arguments, got 1. Pass keyword arguments instead, e.g. Genkit(plugins=[...], model="...").
TypeError: Action.run() takes from 1 to 2 positional arguments but 3 were given
```

- `@ai.tool()` and `@ai.flow()` functions must be `async def`.
- Each takes at most one input parameter. A context parameter must be annotated
  (`ctx: FlowContext` or `ctx: ToolContext`); an unannotated `ctx` counts as a
  second input. Wrap multi-field input in one Pydantic `BaseModel`.
- Constructors (`Genkit`, plugins, `GenkitError`) and every option after the
  input on `.run(...)` are keyword-only:

```python
from pydantic import BaseModel
from genkit import ToolContext

class AllergenCheck(BaseModel):
    dish: str
    allergen: str

@ai.tool()
async def check_allergens(check: AllergenCheck, ctx: ToolContext) -> bool:
    """Return True if the dish contains the allergen."""
    return check.allergen in MENU[check.dish].allergens

res = await plan_menu.run(payload, on_chunk=handle_chunk, context={'uid': 'u1'})
```

---

## Served Flow Returns 404, 500, or the Wrong Auth Status

Over HTTP (`serve_flow`, `serve_agent`, `genkit_fastapi_handler`,
`handle_genkit_request`):

- **`404 {"detail":"Not Found"}`**: the route is the Python function name.
  `menu_suggestion_flow` mounts at `POST /menu_suggestion_flow`, not
  `/menuSuggestionFlow`. Override with `serve_flow(flow, base_path=...)`.
- **`500 {"message":"Internal Error","status":"INTERNAL"}`**: the flow raised
  `GenkitError` or any non-`PublicError` exception. Genkit logs the traceback
  server-side and redacts the body. Raise `PublicError` for errors the client
  should see.
- **`400 ... "status":"INVALID_ARGUMENT"`**: the request `data` failed input
  validation.
- **`500 Internal Server Error` (plain text) from a `context_dependency`**:
  `serve_flow(..., context_dependency=...)` runs a FastAPI dependency before
  Genkit's handler, so a `PublicError` raised there is not mapped. Raise
  `fastapi.HTTPException(status_code=401)` in dependencies;
  `PublicError('UNAUTHENTICATED', ...)` maps to 401 only inside a
  `genkit_fastapi_handler` `context_provider` or the flow itself.

```python
from genkit import PublicError

@ai.flow()
async def get_invoice(invoice_id: str) -> dict:
    inv = await find_invoice(invoice_id)
    if inv is None:
        raise PublicError('NOT_FOUND', f'Invoice {invoice_id} not found')
    return inv

# POST /get_invoice {"data": "INV-9"}
# => 404 {"message":"Invoice INV-9 not found","status":"NOT_FOUND"}
```

Full status mapping: [FastAPI](fastapi.md#http-error-redaction-and-publicerror).

---

## `response.output` Is `None` on Structured Output

When a JSON response is truncated (often by `max_output_tokens`) or does not
parse against the schema, `response.output` is `None` and
`response.error.reason` is `ErrorReason.INVALID_OUTPUT`:

```python
from genkit import ErrorReason

res = await ai.generate(prompt='Summarize this invoice.', output_schema=InvoiceSummary)
if res.output is None and res.error and res.error.reason == ErrorReason.INVALID_OUTPUT:
    print(res.error.message)
    # => Model output was not valid JSON for the requested schema: {"vendor": "Acme", "total": 12
```

Raise `max_output_tokens` or simplify the schema, then retry.

---

## `response.json` Is Not the Model Output

`response.json` is Pydantic's deprecated `BaseModel.json` method. Calling it
serializes the whole `ModelResponse` and emits `PydanticDeprecatedSince20`.
Read:

- `response.text` for plain text.
- `response.output` for structured output.
- `response.message` for the full message.

`GenkitError` exposes `e.message`, `e.status`, `e.details`, `e.reason`, and
`e.__cause__`. `e.original_message` raises `AttributeError`.

---

## Prompt Variable Sent Literally

`ai.generate(prompt=..., system=...)` sends strings verbatim. The model receives
`Say hello to {{name}}.` as written. Render templates through `ai.define_prompt`
or a `.prompt` file:

```python
greet = ai.define_prompt(name='greet', prompt='Say hello to {{name}}.')
res = await greet({'name': 'Sam'})
# Model receives: Say hello to Sam.
```

---

## Streaming `TypeError` or a Flow That Keeps Running After `break`

```text
TypeError: object ModelStreamResponse can't be used in 'await' expression
```

1. Do not `await` `ai.generate_stream(...)`, `flow.stream(...)`, or
   `chat.send_stream(...)`. Iterate the stream, then `await` the final response:
   ```python
   sr = ai.generate_stream(prompt='Describe the tasting menu.')
   async for chunk in sr.stream:
       print(chunk.text, end='')
   final = await sr.response
   ```
2. To stop a flow stream early, use `async with`. Leaving the block cancels the
   flow:
   ```python
   async with course_flow.stream(payload) as stream:
       async for chunk in stream:
           if chunk == 'dessert':
               break  # course_flow receives CancelledError
   ```

---

## Cloud Telemetry Enabled but Spans Do Not Reach Cloud Trace

By default in local development (`GENKIT_ENV=dev`),
`enable_google_cloud_telemetry()` runs in local-only mode to prevent polluting
Cloud Trace with local run data. To export traces to GCP from local development,
pass `force_dev_export=True`:

```python
from genkit_google_cloud import enable_google_cloud_telemetry

enable_google_cloud_telemetry(project='bistro-prod', force_dev_export=True)
```

---

## Interrupts and Agent Session Pitfalls

- **`except Exception:` does not catch `Interrupt`**: `Interrupt` subclasses
  `BaseException`, so a tool's catch-all cannot swallow approval interrupts. Put
  side-effect cleanup in `finally`.
- **Approval resume**: build restart parts with
  `part.restart(resumed_metadata={'tool_approved': True})` on items from
  `res.interrupts` (see
  [agents-human-in-the-loop.md](agents-human-in-the-loop.md)).
- **`ImportError: cannot import name 'AgentError'`**: failed turns do not raise.
  `chat.send()` returns a turn with `finish_reason == AgentFinishReason.FAILED`
  and `res.error`. `AgentInitError` raises from `agent.chat(...)` on bad init;
  `send` raises `GenkitError` only when no turn result arrives.
- **`res.snapshot_id` is `None`**: the agent has no store. Pass
  `store=InMemorySessionStore()` to `define_agent` (see [agents.md](agents.md)).
- **`AgentInitError: FAILED_PRECONDITION: Cannot send 'state' to a
  server-managed agent (one with a store). Send 'snapshot_id' or 'session_id'
  instead.`**: store-backed chats resume by ID. Mutate state inside the turn
  (see [agents-state.md](agents-state.md)).
- **Resume picks the wrong branch after a fork**: `session_id` resumes the most
  recently created leaf. Pass the branch's `snapshot_id` (see
  [agents-branching.md](agents-branching.md)).
- **Resume after a failed turn**: only `completed` snapshots resume by
  `snapshot_id`. Use `agent.chat(session_id=...)` to continue from the last good
  turn.
- **`chat.abort()` does nothing**: during a foreground `send` it is a no-op. Run
  the turn with `detach()` and call `await task.abort()` (see
  [agents-background.md](agents-background.md)).
- **Remote client mismatches**: align `state_management` with the server and
  omit trailing slashes on the base URL (see [agents-http.md](agents-http.md)).
