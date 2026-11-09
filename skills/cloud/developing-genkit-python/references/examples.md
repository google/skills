# Genkit Python Examples

Minimal patterns for generation, structured output, streaming, media, flows,
tools, interrupts, cancellation, and embeddings.

- [Public Imports and Initialization](#public-imports-and-initialization): Lines 17-66
- [Structured Output](#structured-output): Lines 70-106
- [Streaming (Text and Structured Output)](#streaming-text-and-structured-output): Lines 110-138
- [Media Input and Output (Part)](#media-input-and-output-part): Lines 142-206
- [Flows and Streaming Flows](#flows-and-streaming-flows): Lines 210-244
- [Tools, Multipart Tool Responses, and Interrupts](#tools-multipart-tool-responses-and-interrupts): Lines 248-311
- [Cancellation](#cancellation): Lines 315-343
- [Embeddings](#embeddings): Lines 347-374

---

## Public Imports and Initialization

Import only from public modules (`genkit`, `genkit_google_genai`,
`genkit_fastapi`, `genkit_middleware`, `genkit.model`, `genkit.embedder`,
`genkit.middleware`, `genkit.web`, `genkit.exp`, `genkit.exp.agent`). Never
import private `_` submodules.

```python
from genkit import Genkit
from genkit_google_genai import GoogleAI

ai = Genkit(
    plugins=[GoogleAI()],
    model=GoogleAI.gemini('gemini-flash-latest'),
)
```

For multi-turn stateful agents, import `Genkit` from `genkit.exp` and session
types from `genkit.exp.agent` (see [Agents](agents.md)).

### Provider Model Refs & Typed Config

Other providers follow the same `Plugin.helper('model-id')` + `<Plugin>Config`
shape (import list in `SKILL.md`).

```python
from genkit_google_genai import GeminiConfig, GoogleAI

# Typed config with flat fields + `extra` escape hatch for unmodeled provider fields
res = await ai.generate(
    model=GoogleAI.gemini('gemini-flash-latest'),
    prompt='Check recent FDA allergen labeling updates.',
    config=GeminiConfig(
        thinking_level='HIGH',
        include_thoughts=True,
        google_search=True,
        extra={'seed': 42},
    ),
)

# Per-request API key (never pass `api_key` inside `config` - that raises GenkitError)
tenant_res = await ai.generate(
    prompt='Summarize invoice #4821.',
    context={'secrets': {'api_key': tenant_api_key}},
)
```

Config defaults merge key-by-key (`ModelRef` < `Prompt` < call); pass `None` on
a field to clear an inherited key. Unknown config keys raise `GenkitError`
(`INVALID_ARGUMENT`) before calling the provider.

---

## Structured Output

`response.output` is typed `OutputT | None`. If the model reply is cut off
(`max_output_tokens`) or malformed, `response.output` is `None` and
`response.error` (`Failure`) has `reason == ErrorReason.INVALID_OUTPUT`.

```python
from pydantic import BaseModel, TypeAdapter
from genkit import ErrorReason

class CityInfo(BaseModel):
    name: str
    population: int
    country: str

response = await ai.generate(
    prompt='Give facts about Tokyo.',
    output_schema=CityInfo,
)
if response.output is None:
    if response.error and response.error.reason == ErrorReason.INVALID_OUTPUT:
        raise RuntimeError(f'Incomplete structured output: {response.error.message}')
    raise RuntimeError('No structured output returned')

city: CityInfo = response.output

# Arrays
schema = TypeAdapter(list[CityInfo]).json_schema()
list_res = await ai.generate(
    prompt='List 3 cities in Japan.',
    output_format='array',
    output_schema=schema,
)
```

Built-in `output_format` values: `'text'`, `'json'`, `'array'`, `'enum'`,
`'jsonl'`.

---

## Streaming (Text and Structured Output)

```python
sr = ai.generate_stream(prompt='Explain sourdough fermentation.')
async for chunk in sr.stream:
    if chunk.text:
        print(chunk.text, end='', flush=True)
final = await sr.response
```

Streaming structured output yields partial typed objects on `chunk.output`
without raising on incomplete JSON:

```python
class RecipeCard(BaseModel):
    title: str
    prep_minutes: int
    steps: list[str]

sr = ai.generate_stream(
    prompt='Create a weeknight shakshuka recipe.',
    output_schema=RecipeCard,
)
async for chunk in sr.stream:
    if chunk.output:
        print(chunk.output)
final = await sr.response
recipe = final.output  # RecipeCard | None
```

---

## Media Input and Output (`Part`)

Construct parts with `Part.from_text(...)` and `Part.from_media(...)`. Inspect
parts via `part.text` and `part.media`.

### Sending Image / Media Input

```python
import base64
from pathlib import Path
from genkit import Message, Part, Role

# Direct HTTPS URL (< 20 MB) or base64 data URI
b64 = base64.b64encode(Path('receipt.png').read_bytes()).decode()
data_uri = f'data:image/png;base64,{b64}'

msg = Message(
    role=Role.USER,
    content=[
        Part.from_text('Extract the total amount from this receipt.'),
        Part.from_media(data_uri, content_type='image/png'),
    ],
)
response = await ai.generate(messages=[msg])
print(response.text)
```

Media URLs larger than **20 MB** fail instead of downloading into memory, and
`Ollama` does not read local filesystem paths for media.

### Generating Image / Audio / Video Output

```python
from genkit_google_genai import GeminiImageConfig, GeminiTtsConfig, GoogleAI, VertexAI

# Image generation (Imagen catalog is retired; use gemini_image)
img_res = await ai.generate(
    model=GoogleAI.gemini_image('gemini-2.5-flash-image'),
    prompt='Minimalist watercolor illustration of an espresso machine.',
    config=GeminiImageConfig(aspect_ratio='1:1'),
)
for media in img_res.media:
    print(media.content_type, (media.url or '')[:60])

# Inspecting parts directly on a message
if img_res.message:
    for part in img_res.message.content:
        if part.media:
            print(part.media.content_type)

# Text-to-speech
tts_res = await ai.generate(
    model=GoogleAI.gemini_tts('gemini-2.5-flash-preview-tts'),
    prompt='Order 42 is ready at the counter.',
    config=GeminiTtsConfig(voice='Kore'),
)

# Background video generation (Veo via Vertex AI)
op = await ai.generate_operation(
    model=VertexAI.veo('veo-3.1-generate-preview'),
    prompt='Aerial shot of coastal cliffs at sunrise.',
)
while not op.done:
    op = await ai.check_operation(op)
```

---

## Flows and Streaming Flows

Flows validate both input and return values against their type annotations.
Calling `await summarize(inp)` or `await summarize.run(inp)` raises body
exceptions unwrapped in-process; over HTTP, raise `PublicError` for
client-visible 4xx errors (see [FastAPI](fastapi.md)).

```python
from genkit import FlowContext, PublicError

class SummarizeInput(BaseModel):
    text: str

@ai.flow()
async def summarize(input: SummarizeInput) -> str:
    if not input.text.strip():
        raise PublicError('INVALID_ARGUMENT', 'text must not be empty')
    response = await ai.generate(prompt=f'Summarize in two sentences: {input.text}')
    return response.text

# Streaming flow: declare the chunk type on FlowContext[ChunkT]
@ai.flow()
async def stream_story(subject: str, ctx: FlowContext[str]) -> str:
    sr = ai.generate_stream(prompt=f'Write a short story about {subject}.')
    chunks: list[str] = []
    async for chunk in sr.stream:
        if chunk.text:
            ctx.send_chunk(chunk.text)
            chunks.append(chunk.text)
    return ''.join(chunks)
```

Options after the flow's single input on `.run(...)` are keyword-only:
`await stream_story.run('lighthouses', on_chunk=print, context={'role':
'reader'})`.

---

## Tools, Multipart Tool Responses, and Interrupts

Use `@ai.tool()` (there is no `define_tool`). A tool takes **at most one input
parameter** (scalar or Pydantic `BaseModel`) plus an optional
`ctx: ToolContext[ChunkT]`. Use a `BaseModel` whenever a tool needs multiple
arguments or field descriptions.

```python
from pydantic import BaseModel, Field
from genkit import MultipartToolResponse, Part, ToolContext

class OrderLookup(BaseModel):
    order_id: str = Field(description='Order identifier, e.g. ORD-104')
    include_receipt_image: bool = False

class ToolProgress(BaseModel):
    stage: str

@ai.tool()
async def lookup_order(input: OrderLookup, ctx: ToolContext[ToolProgress]) -> str | MultipartToolResponse:
    ctx.send_chunk(ToolProgress(stage='fetching_record'))
    if not input.include_receipt_image:
        return f'Order {input.order_id}: delivered'
    receipt_png = Part.from_media('data:image/png;base64,iVBORw0KGgo=', content_type='image/png')
    return MultipartToolResponse(
        output={'order_id': input.order_id, 'status': 'delivered'},
        content=[receipt_png],
    )

res = await ai.generate(
    prompt='Check status of ORD-104.',
    tools=[lookup_order],
    tool_choice='required',  # 'auto' | 'required' | 'none'
)
```

### Tool Interrupts (Human-in-the-Loop)

Raise `Interrupt(...)` inside a tool (or register a tool via
`ai.define_interrupt(...)`) to pause the generate loop. `Interrupt` subclasses
`BaseException`, so `except Exception:` inside a tool will not swallow it.
Resume using `intr.restart(...)` or `intr.respond(...)`:

```python
from genkit import Interrupt

class RefundInput(BaseModel):
    order_id: str
    amount_cents: int

@ai.tool()
async def issue_refund(input: RefundInput, ctx: ToolContext) -> dict:
    if not ctx.is_resumed():
        raise Interrupt({'order_id': input.order_id, 'amount_cents': input.amount_cents})
    return {'refunded': True, 'approved_by': (ctx.resumed_metadata or {}).get('manager')}

turn1 = await ai.generate(prompt='Refund $25 (2500 cents) on ORD-104.', tools=[issue_refund])
if turn1.interrupts:
    turn2 = await ai.generate(
        messages=turn1.messages,
        tools=[issue_refund],
        resume_restart=[i.restart(resumed_metadata={'manager': 'alex'}) for i in turn1.interrupts],
    )
```

---

## Cancellation

Cancellation uses standard `asyncio.CancelledError`; it reaches model calls,
retry backoff, and running tools at any `await`:

```python
import asyncio

# 1. Cancel an in-flight generate or flow task
task = asyncio.create_task(ai.generate(prompt='Write a detailed migration plan.'))
task.cancel()

# 2. Stop a flow stream early - use `async with` (or `await stream.aclose()`)
# so breaking out of the loop cancels the background flow immediately.
async with stream_story.stream('glaciers') as stream:
    async for chunk in stream:
        if len(chunk) > 0:
            break

# 3. Clean up partial side effects inside `finally` in tools
@ai.tool()
async def hold_inventory(sku: str) -> dict:
    reservation = await reserve_sku(sku)
    try:
        return await commit_reservation(reservation)
    finally:
        if not reservation.committed:
            await release_reservation(reservation)
```

---

## Embeddings

Build embedder refs with `.embedder(...)` and pass provider options in
`config=`:

```python
from genkit import Document
from genkit_google_genai import GoogleAI

embedder = GoogleAI.embedder('gemini-embedding-001')
embeddings = await ai.embed(
    embedder=embedder,
    content='Sourdough starter hydration ratio.',
    config={'task_type': 'RETRIEVAL_DOCUMENT'},
)
vector: list[float] = embeddings[0].embedding

batch = await ai.embed_many(
    embedder=embedder,
    content=['First paragraph.', 'Second paragraph.'],
)

# Multimodal embedding input via Document
image_embeddings = await ai.embed(
    embedder=GoogleAI.embedder('gemini-embedding-2'),
    content=Document.from_media('data:image/png;base64,iVBORw0KGgo=', 'image/png'),
)
```
