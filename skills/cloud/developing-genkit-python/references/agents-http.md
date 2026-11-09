# Agent HTTP Serving & Remote Client (Experimental)

> See [agents.md](agents.md) · [FastAPI](fastapi.md).

Mount an agent on FastAPI with `serve_agent` from `genkit_fastapi.exp`, and
connect from another Python service or CLI with `remote_agent` from
`genkit.exp.agent`. Stable flows use `serve_flow` from `genkit_fastapi`
([FastAPI](fastapi.md)).

- [Serve an agent with FastAPI](#serve-an-agent-with-fastapi): Lines 17-59
- [Connect with remote_agent](#connect-with-remote_agent): Lines 61-105
- [Auth, context_dependency, and PublicError](#auth-context_dependency-and-publicerror): Lines 107-193
- [Custom HTTP routes](#custom-http-routes): Lines 195-238

---

## Serve an agent with FastAPI

`serve_agent(agent)` mounts `POST /{agent.name}` for turns: one-shot JSON by
default, SSE when the caller sends `Accept: text/event-stream` or
`?stream=true`. When the agent has a `store`, it also mounts
`POST /{agent.name}/getSnapshot` (`404` when the snapshot is missing) and
`POST /{agent.name}/abort`. Callers can pass `?session_id=` or `?thread_id=` to
continue a session when the body `init` carries no session id.

```python
import uvicorn
from fastapi import FastAPI
from genkit_fastapi.exp import serve_agent
from genkit_google_genai import GoogleAI

from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore

# 1. Initialize the experimental Genkit instance
ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))

# 2. Define a store-backed agent
agent = ai.define_agent(
    name='weatherAgent',
    system='Weather assistant. Keep answers under two sentences.',
    store=InMemorySessionStore(),
)

# 3. Mount /api/weatherAgent, /api/weatherAgent/getSnapshot, and /api/weatherAgent/abort
app = FastAPI()
app.include_router(serve_agent(agent), prefix='/api')

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)
```

Override the route path with `serve_agent(agent, base_path='/chat')`. Add
FastAPI's `CORSMiddleware` as usual if browsers call the agent from another
origin. Run alongside the Developer UI with:

```bash
genkit start -- uv run server.py
```

## Connect with `remote_agent`

`remote_agent` returns an `AgentClient` with the same `chat()`, `load_chat()`,
`get_snapshot()`, and `abort()` surface as an in-process `Agent`. `timeout`
(default `60.0`) is the longest wait for the next bytes from the server, not a
cap on the whole turn.

```python
from genkit.exp.agent import remote_agent


async def run_client() -> None:
    client = remote_agent(
        url='http://127.0.0.1:8080/api/weatherAgent',
        state_management='server',  # use 'client' when the server agent has no store
        timeout=60.0,
    )

    # 1. One-shot turn
    chat = client.chat()
    res = await chat.send('Weather in Tokyo?')
    print(res.text)
    # => I don't have real-time weather data for Tokyo. Check a local forecast for live conditions.

    # 2. Streamed follow-up turn
    turn = chat.send_stream('What about humidity?')
    async for chunk in turn.stream:
        if chunk.text:
            print(chunk.text, end='', flush=True)
    final = await turn.response

    # 3. Rehydrate from the server store onto a new chat handle
    assert final.snapshot_id is not None
    resumed = await client.load_chat(snapshot_id=final.snapshot_id)
    answer = await resumed.send('Which city were we discussing?')
    print(answer.text)
    # => We were discussing Tokyo.
```

Pass `state_schema=MyStateModel` to `remote_agent(...)` when you want
`chat.state`, `res.state`, and `chunk.custom` validated into a Pydantic model on
the client. Omit any trailing slash on `url`; the client derives
`{url}/getSnapshot` and `{url}/abort` from it. A timeout surfaces as
`GenkitError` `DEADLINE_EXCEEDED`, a refused or dropped connection as
`UNAVAILABLE`.

## Auth, `context_dependency`, and `PublicError`

Resolve caller identity on the server with `context_dependency`, a FastAPI
dependency applied to the turn, `getSnapshot`, and `abort` routes. Return a
`dict`; other return values (such as Pydantic models) are dropped. Tools read it
from `ctx.context` (or `Genkit.current_context()`), and `SessionStore` methods
receive it as `context=`.

Errors surface at three boundaries:

- **Inside `context_dependency`**: FastAPI resolves it before Genkit runs, so
  Genkit's error mapping does not apply. Raise
  `fastapi.HTTPException(status_code=401, ...)`; a `PublicError` raised here
  becomes FastAPI's plain `500 Internal Server Error`.
- **Inside Genkit, before or outside a turn**: on `getSnapshot` and `abort`, a
  `PublicError` from your `SessionStore` keeps its status, message, and details
  (`PERMISSION_DENIED` -> `403`). `AgentInitError` (an init that does not match
  the agent's state mode) is a `PublicError` and keeps its status too
  (`FAILED_PRECONDITION` -> `400`). Any other exception returns a redacted
  `500`. Full rules:
  [HTTP Error Redaction](fastapi.md#http-error-redaction-and-publicerror).
- **Inside a running turn**: tool and store exceptions do not become HTTP
  errors. The response is `200` with `finishReason: "failed"` and `error`; the
  client sees `res.finish_reason == AgentFinishReason.FAILED` and `res.error`.

```python
from fastapi import FastAPI, Header, HTTPException
from genkit_fastapi.exp import serve_agent

from genkit import PublicError, ToolContext
from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore, SessionSnapshot, remote_agent
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))


# 1. Resolve the caller from a header; the dict becomes the action context
async def resolve_user(x_api_key: str | None = Header(default=None)) -> dict[str, object]:
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing X-Api-Key header.')
    return {'tenant_id': 'acme', 'role': 'admin'}


# 2. Reject snapshot reads that carry no tenant
class TenantScopedStore(InMemorySessionStore):
    async def get_snapshot(
        self,
        *,
        snapshot_id: str | None = None,
        session_id: str | None = None,
        context: dict[str, object] | None = None,
    ) -> SessionSnapshot | None:
        if not (context or {}).get('tenant_id'):
            raise PublicError('PERMISSION_DENIED', 'Tenant context required.')
        return await super().get_snapshot(snapshot_id=snapshot_id, session_id=session_id, context=context)


# 3. Read the same context from a tool
@ai.tool(name='whoami', description='Inspect caller tenant context.')
async def whoami(ctx: ToolContext) -> dict[str, object]:
    auth = ctx.context or {}
    return {'tenant_id': auth.get('tenant_id'), 'role': auth.get('role')}


support_agent = ai.define_agent(
    name='supportAgent',
    system='Support assistant for the caller tenant.',
    tools=[whoami],
    store=TenantScopedStore(),
)

app = FastAPI()
app.include_router(
    serve_agent(support_agent, context_dependency=resolve_user),
    prefix='/api',
)
# POST /api/supportAgent with no X-Api-Key
# => 401 {"detail":"Missing X-Api-Key header."}

# 4. The remote client sends static headers, or a sync/async callable that returns them
authed_client = remote_agent(
    url='http://127.0.0.1:8080/api/supportAgent',
    state_management='server',
    headers={'X-Api-Key': 'sk-live-...'},
)
```

## Custom HTTP routes

Use `handle_genkit_request` (`genkit_fastapi`) when a route needs path
parameters or extra `Depends(...)` but should keep the Genkit JSON / SSE wire
format. Use `to_sse` (`genkit.web`) to frame any stream handle
(`chat.send_stream()`, `flow.stream()`) as `data: {"message": ...}` frames
followed by `data: {"result": ...}`. Generic flow patterns:
[Custom Route Escape Hatch](fastapi.md#3-custom-route-escape-hatch-handle_genkit_request-or-genkitweb).

```python
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from genkit_fastapi import handle_genkit_request
from pydantic import BaseModel

from genkit.web import to_sse

custom_app = FastAPI()


class TurnRequest(BaseModel):
    prompt: str


# Option A: full Genkit wire contract inside a custom route.
# Body: {"data": {"message": {"role": "user", "content": [{"text": "..."}]}}}
@custom_app.post('/tenants/{tenant_id}/chat')
async def tenant_agent_route(tenant_id: str, request: Request) -> Response:
    # Check the caller may act for tenant_id before trusting the path.
    return await handle_genkit_request(
        request,
        action=support_agent,
        context={'tenant_id': tenant_id},
    )


# Option B: stream one chat turn as SSE from a plain JSON body.
# agent.chat() takes no request context, so the store and tools see context=None.
@custom_app.post('/sessions/{session_id}/stream')
async def stream_session_turn(session_id: str, body: TurnRequest) -> StreamingResponse:
    chat = agent.chat(session_id=session_id)
    turn = chat.send_stream(body.prompt)
    return StreamingResponse(to_sse(turn), media_type='text/event-stream')
```
