# Agents (Experimental)

> Experimental APIs live under `.exp` modules (`genkit.exp`, `genkit.exp.agent`,
> `genkit_fastapi.exp`, `genkit_middleware.exp`, `genkit_google_cloud.exp`) and
> can change between minor releases.

Turn a model and tools into a stateful multi-turn conversation with snapshots,
typed custom state, human approvals, branching, and detached background runs.

Deeper topics: [sessions](agents-sessions.md) ·
[HITL](agents-human-in-the-loop.md) · [branching](agents-branching.md) ·
[background](agents-background.md) · [state](agents-state.md) ·
[artifacts](agents-artifacts.md) · [custom](agents-custom.md) ·
[HTTP](agents-http.md)

- [Define an agent](#define-an-agent): Lines 26-85
- [Tools, progress chunks, and multipart responses](#tools-progress-chunks-and-multipart-responses): Lines 87-117
- [Middleware](#middleware): Lines 119-169
- [Chat and streaming](#chat-and-streaming): Lines 171-206
- [Errors and cancellation](#errors-and-cancellation): Lines 208-247
- [Without a store](#without-a-store): Lines 249-271
- [Verify an agent from the CLI (flow:run)](#verify-an-agent-from-the-cli-flowrun): Lines 273-290

---

## Define an agent

Import `Genkit` from `genkit.exp` to opt into `define_agent`,
`define_prompt_agent`, `define_custom_agent`, and `ai.agent(name)`. Stable
`from genkit import Genkit` does not expose agent methods.

```python
from genkit_google_genai import GoogleAI
from pydantic import BaseModel

from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore


class WeatherInput(BaseModel):
    location: str


class WeatherOutput(BaseModel):
    weather: str
    temperature: str


# 1. Initialize experimental Genkit instance
ai = Genkit(plugins=[GoogleAI()])


# 2. Define a typed tool
@ai.tool(name='getWeather', description='Get weather for a city.')
async def get_weather(input: WeatherInput) -> WeatherOutput:
    return WeatherOutput(weather=f'Sunny in {input.location}', temperature='21°C')


# 3. Register a store-backed agent
agent = ai.define_agent(
    name='weatherAgent',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='Weather assistant. Use getWeather for weather questions.',
    tools=[get_weather],
    store=InMemorySessionStore(),  # omit store= for client-managed history
)
```

Key `define_agent` keyword arguments:

- **`model`**: `GoogleAI.gemini('gemini-flash-latest')` (or a `'plugin/model'`
  string)
- **`config`**: typed config such as `GeminiConfig(thinking_level='HIGH')` or
  `AnthropicConfig(thinking='adaptive', effort='high')`
- **`use`**: middleware instances (`Retry`, `Fallback`, `ToolApproval`,
  `Filesystem`, `Skills`, `Artifacts`, `Surfaces`)
- **`state_schema`**: Pydantic `BaseModel` typing `chat.state`, `res.state`, and
  `chunk.custom` ([state](agents-state.md))
- **`max_turns`**: tool-loop ceiling per user message (default 50)
- **`state_transform` / `chunk_transform`**: egress hooks that redact client
  views without altering stored state

For `.prompt` files or `ai.define_prompt(...)`, wire the registered prompt name
directly with `ai.define_prompt_agent(name='greeterPrompt', store=...)`. For
custom turn loops, use [`ai.define_custom_agent(...)`](agents-custom.md).

## Tools, progress chunks, and multipart responses

A tool takes at most one typed input parameter (a Pydantic `BaseModel` for
structured arguments or a scalar like `str`, or no input parameter) plus an
optional `ToolContext[ChunkT]` parameter.

```python
import asyncio
from pydantic import BaseModel

from genkit import MultipartToolResponse, Part, ToolContext


class PrepProgress(BaseModel):
    stage: str
    percent: int


@ai.tool(name='prepareOrder', description='Prepare a kitchen order and stream stage progress.')
async def prepare_order(dish: str, ctx: ToolContext[PrepProgress]) -> MultipartToolResponse[dict[str, str]]:
    # 1. Stream partial tool progress (arrives on chunk.tool_responses with part.is_partial == True)
    ctx.send_chunk(PrepProgress(stage='searing', percent=40))
    await asyncio.sleep(0.2)
    ctx.send_chunk(PrepProgress(stage='plating', percent=90))

    # 2. Return structured output alongside extra content parts (e.g. media or text)
    return MultipartToolResponse(
        output={'status': 'ready', 'dish': dish},
        content=[Part.from_text(f'Ticket closed for {dish}.')],
    )
```

## Middleware

Import standard middleware from `genkit_middleware`, session-bound `Artifacts`
from `genkit_middleware.exp`, and generative UI `Surfaces` from `genkit_a2ui`.
Register `Middleware()` in `plugins=[...]` when you want standard middleware
listed in the Dev UI or referenced by `.prompt` files; passing instances in
`use=[...]` works either way.

- **`Filesystem`** (`genkit_middleware`): `list_files` and `read_file` scoped to
  `root_dir`; pass `allow_write_access=True` to add `write_file` and
  `edit_file`.
- **`ToolApproval`** (`genkit_middleware`): tools in `allowed_tools` run
  automatically; all other tools pause the turn with an interrupt
  ([HITL](agents-human-in-the-loop.md)). It gates every tool call, including the
  ones `Filesystem` and `Artifacts` add.
- **`Skills`** (`genkit_middleware`): injects `SKILL.md` descriptions and
  exposes `use_skill`.
- **`Retry` / `Fallback`** (`genkit_middleware`): `Retry` retries transient
  failures (`UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `ABORTED`,
  `INTERNAL` by default); `Fallback` switches to alternate models.
- **`Artifacts`** (`genkit_middleware.exp`): adds `read_artifact` and
  `write_artifact` tools plus an active artifact listing in the system prompt
  ([artifacts](agents-artifacts.md)).
- **`Surfaces`** (`genkit_a2ui`): A2UI surface instructions, validation, and
  part parsing.

```python
from genkit_google_genai import GoogleAI
from genkit_middleware import Filesystem, Middleware, Retry, Skills, ToolApproval
from genkit_middleware.exp import Artifacts

from genkit.exp import Genkit
from genkit.exp.agent import FileSessionStore

ai = Genkit(plugins=[GoogleAI(), Middleware()])

coding_agent = ai.define_agent(
    name='codingAgent',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='Coding assistant. Explore with list_files/read_file before editing.',
    use=[
        ToolApproval(allowed_tools=['list_files', 'read_file', 'read_artifact', 'use_skill']),
        Filesystem(root_dir='./workspace', allow_write_access=True),
        Artifacts(),
        Skills(skill_paths=['./skills']),
        Retry(max_retries=3),
    ],
    store=FileSessionStore('./.snapshots'),
    max_turns=30,
)
```

## Chat and streaming

Run one turn at a time per `AgentChat`. Use `ai.run_main(main())` for standalone
scripts.

```python
async def main() -> None:
    chat = agent.chat()

    # 1. One-shot turn
    res = await chat.send('Weather in Tokyo?')
    print(res.text, res.snapshot_id)
    # => It is 21°C and sunny in Tokyo. 8f3c...

    # 2. Streamed turn (.stream yields AgentChunk, .response resolves to AgentResponse)
    turn = chat.send_stream('What about Paris?')
    async for chunk in turn.stream:
        if chunk.text:
            print(chunk.accumulated_text, end='\r', flush=True)
    final = await turn.response

    # 3. Rehydrate history from the store on a new chat instance
    resumed = await agent.load_chat(snapshot_id=final.snapshot_id)
    followup = await resumed.send('Which cities did we check?')
    print(followup.text)


if __name__ == '__main__':
    ai.run_main(main())
```

- **`await agent.load_chat(snapshot_id=...)`**: fetches the stored snapshot
  immediately so `chat.messages`, `chat.state`, and `chat.artifacts` are
  populated locally.
- **`agent.chat(session_id=...)`**: attaches a lazy resume handle that continues
  from the session's last completed turn, skipping any failed or aborted leaf.

## Errors and cancellation

Genkit separates turn failures from call failures:

- **Turn failure (`res.error`)**: When an agent turn starts and fails at
  runtime, `chat.send(...)` does **not** raise. It returns `AgentResponse` with
  `res.finish_reason == AgentFinishReason.FAILED`, `res.text == ''`, and
  `res.error` (`Failure` with `status`, `message`, `details`, and
  `reason: ErrorReason`). The chat drops the unanswered user prompt from
  `chat.messages`, and the next `send()` continues from the last completed
  snapshot.
- **No turn result (`GenkitError`)**: When no turn runs at all (dropped HTTP
  connection, or `AgentInitError` from passing `snapshot_id` to a storeless
  agent), `chat.send(...)` raises `GenkitError` and restores local chat state.
  Mismatched init arguments (a `state` blob to a store-backed agent, or
  `messages`/`state` mixed with a resume id) raise `AgentInitError` from
  `agent.chat(...)` itself.
- **Cancellation**: native `asyncio.CancelledError`; put tool cleanup in `try` /
  `finally`. `await turn.abort()` detaches the client stream only. To cancel a
  running turn server-side, start it with `chat.detach(...)` and call
  `await task.abort()`; `chat.abort()` during a foreground `send()` does not
  stop that turn
  ([background](agents-background.md#client-detach-vs-server-cancellation)).

```python
from genkit import ErrorReason, GenkitError
from genkit.exp.agent import AgentFinishReason

try:
    res = await chat.send('Run portfolio rebalance.')
except GenkitError as err:
    # No turn ran (transport drop or invalid init)
    print(err.status, err.message)
else:
    if res.error:
        # Turn ran and failed; res.finish_reason == AgentFinishReason.FAILED
        assert res.finish_reason == AgentFinishReason.FAILED
        if res.error.reason == ErrorReason.INVALID_OUTPUT:
            print('Truncated structured output:', res.error.message)
```

## Without a store

Omit `store=` when the client owns conversation state. `snapshot_id` stays
`None`; round-trip `messages`, `state`, and `artifacts` into the next
`agent.chat(...)` call:

```python
stateless = ai.define_agent(
    name='echoNoStore',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='Answer briefly and remember context.',
)

chat = stateless.chat()
await chat.send('My name is Ada.')

resumed = stateless.chat(
    messages=chat.messages,
    state=chat.state,
    artifacts=chat.artifacts,
)
await resumed.send('What is my name? One word.')
```

## Verify an agent from the CLI (`flow:run`)

`genkit flow:run` invokes flows, not agents directly. Wrap a turn in a small
flow and propagate `res.error` so failures surface cleanly:

```python
from genkit import GenkitError


@ai.flow()
async def try_weather_agent(message: str) -> str:
    res = await agent.chat().send(message)
    if res.error:
        raise GenkitError(status=res.error.status, message=res.error.message, details=res.error.details)
    return res.text

# genkit flow:run try_weather_agent '"Weather in Tokyo?"' -- uv run src/main.py
```
