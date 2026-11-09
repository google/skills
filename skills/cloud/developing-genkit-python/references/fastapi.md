# FastAPI — Genkit Python

- [Install](#install): Lines 14-35
- [Serve a Flow or Agent](#serve-a-flow-or-agent): Lines 39-95
- [HTTP Error Redaction and PublicError](#http-error-redaction-and-publicerror): Lines 99-114
- [Streaming (SSE)](#streaming-sse): Lines 118-171
- [Auth and Context Providers](#auth-and-context-providers): Lines 175-250
- [Advanced Flow Composition](#advanced-flow-composition): Lines 254-328
- [Structured Output Endpoint](#structured-output-endpoint): Lines 332-356
- [Python HTTP Client](#python-http-client): Lines 360-372

---

## Install

```bash
uv add 'genkit-fastapi==0.13.*' fastapi uvicorn
```

Imports are split between stable flow serving and experimental agent serving:

- **Stable flows (`genkit_fastapi`)**:
  - `serve_flow` — mount a flow as a FastAPI `APIRouter` (supports `base_path=`
    and `context_dependency=`)
  - `genkit_fastapi_handler` — decorator stacking `@app.post('/...')` directly
    over `@ai.flow()` (supports `context_provider=`)
  - `handle_genkit_request` — low-level handler for custom `@app.post` routes
    with multiple FastAPI `Depends(...)` parameters
- **Experimental agents (`genkit_fastapi.exp`)**:
  - `serve_agent` — mount an experimental `Agent` (`genkit.exp.Genkit`) as an
    `APIRouter` (see [Agent HTTP](agents-http.md))
- **Framework-agnostic web utilities (`genkit.web`)**:
  - `RequestData`, `ContextProvider`, `StreamHandle`, `to_sse`, `read_body`,
    `wants_stream`, `result_json`, `error_body`, `error_json`, `error_sse`,
    `error_status`

---

## Serve a Flow or Agent

```python
import os
import uvicorn
from fastapi import FastAPI
from genkit import PublicError
from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore
from genkit_fastapi import serve_flow
from genkit_fastapi.exp import serve_agent
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))

concierge = ai.define_agent(
    name='conciergeAgent',
    system='Hotel concierge. Keep answers under 40 words.',
    store=InMemorySessionStore(),
)


@ai.flow()
async def lookup_reservation(code: str) -> dict:
    if not code.startswith('RES-'):
        raise PublicError('NOT_FOUND', f'Reservation {code} not found')  # HTTP 404
    return {'code': code, 'status': 'confirmed'}


app = FastAPI()
# Paths default to the agent name and the flow's Python function name (override via base_path=...):
#   POST /api/conciergeAgent (+ /getSnapshot and /abort, since the agent has a store)
#   POST /api/lookup_reservation
app.include_router(serve_agent(concierge), prefix='/api')
app.include_router(serve_flow(lookup_reservation), prefix='/api')


async def main() -> None:
    config = uvicorn.Config(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8080')))
    await uvicorn.Server(config).serve()


if __name__ == '__main__':
    ai.run_main(main())
```

If your app only serves flows (no agents), import `Genkit` from `genkit` instead
of `genkit.exp`.

With `GENKIT_ENV=dev` (which `genkit start` sets automatically), the Dev UI
reflection server starts on a background thread, so either entrypoint works:

```bash
genkit start -- uv run uvicorn main:app --reload   # reload-friendly ASGI dev server + Dev UI
genkit start -- uv run src/main.py                 # driven via ai.run_main(main()) + Dev UI
uvicorn main:app                                   # production (no Dev UI)
```

---

## HTTP Error Redaction and `PublicError`

Over HTTP (`serve_flow`, `serve_agent`, `genkit_fastapi_handler`,
`handle_genkit_request`), Genkit separates internal errors from caller-visible
errors:

- **`PublicError(status, message, details)`**: returns the corresponding HTTP
  status (`NOT_FOUND` -> 404, `INVALID_ARGUMENT` -> 400, `UNAUTHENTICATED` ->
  401, `PERMISSION_DENIED` -> 403) with `status`, `message`, and `details`. Keep
  secrets and cross-tenant data out of `PublicError`.
- **Invalid flow input**: returns HTTP 400 with field names and Pydantic's
  built-in messages (never echoing submitted values; custom validator text shows
  as `Invalid value` unless the validator raises `PublicError`).
- **Any other `GenkitError`, provider error, or Python exception**: logged
  server-side with full traceback (`5xx`) and returned to the client as
  `500 {"status": "INTERNAL", "message": "Internal Error"}`.

---

## Streaming (SSE)

`serve_flow`, `serve_agent`, `genkit_fastapi_handler`, and
`handle_genkit_request` stream Server-Sent Events when the client sends
`Accept: text/event-stream` (or `?stream=true`), and automatically cancel the
running flow if the client disconnects. Otherwise they return `{"result": ...}`.

**Wire format (SSE):**
```text
data: {"message": "<chunk>"}
data: {"message": "<chunk>"}
data: {"result": "<final output>"}
```
Errors during streaming emit `data: {"error": {...}}` formatted with the same
`PublicError` redaction rules.

**Minimal streaming FastAPI flow (`FlowContext`):**

```python
from pydantic import BaseModel
from fastapi import FastAPI
from genkit import FlowContext, Genkit
from genkit_fastapi import serve_flow
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))


class BriefInput(BaseModel):
    topic: str


@ai.flow()
async def stream_brief(input: BriefInput, ctx: FlowContext[str]) -> str:
    sr = ai.generate_stream(prompt=f'Write a concise brief on {input.topic}.')
    parts: list[str] = []
    async for chunk in sr.stream:
        if chunk.text:
            ctx.send_chunk(chunk.text)  # each call emits one SSE frame
            parts.append(chunk.text)
    return ''.join(parts)


app = FastAPI()
app.include_router(serve_flow(stream_brief), prefix='/api')  # POST /api/stream_brief
```

**Test with `curl`:**
```bash
curl -N -X POST http://localhost:8080/api/stream_brief \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"data": {"topic": "zero-downtime Postgres migrations"}}'
```

---

## Auth and Context Providers

### 1. FastAPI `Depends` via `serve_flow(..., context_dependency=...)`

```python
from fastapi import Header
from genkit import FlowContext, PublicError
from genkit_fastapi import serve_flow


async def require_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization:
        raise PublicError('UNAUTHENTICATED', 'Missing Authorization header')  # 401
    return {'auth': {'token': authorization}}


@ai.flow()
async def account_summary(account_id: str, ctx: FlowContext) -> dict:
    caller = (ctx.context or {}).get('auth')
    return {'account_id': account_id, 'caller': caller}


app.include_router(
    serve_flow(account_summary, context_dependency=require_auth),
    prefix='/api',
)
```

### 2. Decorator Style (`@genkit_fastapi_handler`) with `genkit.web.RequestData`

```python
from genkit import PublicError
from genkit.web import RequestData
from genkit_fastapi import genkit_fastapi_handler


async def auth_provider(req: RequestData) -> dict:
    token = req.headers.get('authorization')
    if not token:
        raise PublicError('UNAUTHENTICATED', 'Missing bearer token')  # 401
    return {'user_token': token}


@app.post('/api/ask')
@genkit_fastapi_handler(ai, context_provider=auth_provider)
@ai.flow()
async def ask(question: str) -> str:
    res = await ai.generate(prompt=question)
    return res.text
```

### 3. Custom Route Escape Hatch (`handle_genkit_request` or `genkit.web`)

When a route needs multiple `Depends(...)` parameters while keeping the Genkit
wire format:

```python
from fastapi import Depends, Request
from genkit_fastapi import handle_genkit_request


@app.post('/api/custom-brief')
async def custom_brief(
    request: Request,
    auth_ctx: dict = Depends(require_auth),
):
    return await handle_genkit_request(
        request,
        action=stream_brief,
        context=auth_ctx,
    )
```

If writing a completely custom non-Genkit JSON wrapper around
`await my_flow.run(data)`, map exceptions with `error_body(e)` and
`error_status(e)` from `genkit.web` so internal errors stay redacted.

---

## Advanced Flow Composition

### Nested Flow Streaming

Forward a child flow's chunks to the parent's SSE stream via
`await child.run(input, on_chunk=ctx.send_chunk)`. All arguments after the input
on `.run(...)` are keyword-only:

```python
class SectionInput(BaseModel):
    topic: str


@ai.flow()
async def draft_body(input: SectionInput, ctx: FlowContext[str]) -> str:
    sr = ai.generate_stream(prompt=f'Explain {input.topic} with concrete examples.')
    chunks: list[str] = []
    async for chunk in sr.stream:
        if chunk.text:
            ctx.send_chunk(chunk.text)
            chunks.append(chunk.text)
    return ''.join(chunks)


@ai.flow()
async def draft_headline(input: SectionInput) -> str:
    res = await ai.generate(prompt=f'One-line title for: {input.topic}')
    return res.text.strip()


@ai.flow()
async def full_report(input: SectionInput, ctx: FlowContext[str]) -> str:
    headline = await draft_headline(input)
    ctx.send_chunk(f'# {headline}\n\n')
    body = (await draft_body.run(input, on_chunk=ctx.send_chunk)).response
    return f'# {headline}\n\n{body}'
```

### Parallel Flows (`asyncio.gather`)

```python
import asyncio


class CodeReviewInput(BaseModel):
    diff: str


class ReviewFindings(BaseModel):
    findings: list[str]


@ai.flow()
async def check_security(input: CodeReviewInput) -> ReviewFindings:
    res = await ai.generate(
        prompt=f'List security issues in this diff: {input.diff[:2000]}',
        output_schema=ReviewFindings,
    )
    return res.output or ReviewFindings(findings=[])


@ai.flow()
async def check_correctness(input: CodeReviewInput) -> ReviewFindings:
    res = await ai.generate(
        prompt=f'List logic bugs in this diff: {input.diff[:2000]}',
        output_schema=ReviewFindings,
    )
    return res.output or ReviewFindings(findings=[])


@ai.flow()
async def review_diff(input: CodeReviewInput) -> ReviewFindings:
    sec, bugs = await asyncio.gather(check_security(input), check_correctness(input))
    return ReviewFindings(findings=sec.findings + bugs.findings)
```

---

## Structured Output Endpoint

Check `response.output is None` before returning so truncated model replies
surface cleanly instead of failing output validation:

```python
from genkit import PublicError


class SentimentResult(BaseModel):
    sentiment: str
    confidence: float
    key_phrases: list[str]


@ai.flow()
async def analyze_sentiment(text: str) -> SentimentResult:
    response = await ai.generate(
        prompt=f'Analyze customer sentiment: {text}',
        output_schema=SentimentResult,
    )
    if response.output is None:
        raise RuntimeError(f'Model returned incomplete JSON: {response.error}')
    return response.output
```

---

## Python HTTP Client

Genkit HTTP endpoints expect `{"data": ...}` on input (`{"data": null}` uses the
flow parameter's default) and return `{"result": ...}`:

```python
import httpx

async with httpx.AsyncClient(base_url='http://127.0.0.1:8080') as client:
    resp = await client.post('/api/analyze_sentiment', json={'data': 'Fast shipping, great packaging.'})
    resp.raise_for_status()
    result = resp.json()['result']
```
