# Custom Agents — `define_custom_agent` (Experimental)

> See [agents.md](agents.md).

`ai.define_agent` runs a built-in model + tool loop. When you need custom
multi-step orchestration, subagent delegation, custom streaming, or manual
control over messages, custom state, and artifacts, register a custom turn loop
with `ai.define_custom_agent`. Callers still talk to the agent through
`chat.send(...)`, `chat.send_stream(...)`, `chat.detach(...)`, and
`serve_agent(...)`.

- [Anatomy](#anatomy): Lines 18-75
- [Streaming custom agent example](#streaming-custom-agent-example): Lines 77-143
- [Non-streaming handle_turn with tools](#non-streaming-handle_turn-with-tools): Lines 145-204

---

## Anatomy

Register one async `fn(sess: SessionRunner, ctx: AgentContext) -> AgentResult`.
Inside `fn`, define
`handle_turn(inp: AgentInput, turn_ctx: TurnContext) -> TurnResult | None`, pass
it to `await sess.run(handle_turn)`, and return `await sess.result()`:

```python
from genkit.exp.agent import (
    AgentContext,
    AgentFinishReason,
    AgentInput,
    AgentResult,
    SessionRunner,
    TurnContext,
    TurnResult,
)


async def custom_fn(sess: SessionRunner, ctx: AgentContext) -> AgentResult:
    async def handle_turn(inp: AgentInput, turn_ctx: TurnContext) -> TurnResult | None:
        # 1. inp.message is already appended to sess.get_messages() before handle_turn runs
        # 2. Emit live chunks with ctx.send_chunk(AgentStreamChunk(...))
        # 3. Persist assistant/tool messages via sess.add_messages([...]) or sess.set_messages([...])
        return TurnResult(finish_reason=AgentFinishReason.STOP)

    await sess.run(handle_turn)
    return await sess.result()
```

Runtime mechanics:

- **Automatic user message append**: Before calling `handle_turn`, `sess.run`
  appends `inp.message` (`AgentInput` carries `message`, `resume`, and `detach`)
  to session history. `await sess.get_messages()` already returns
  `list[Message]` including the current user prompt — do not wrap items in
  `Message(m)`.
- **`TurnContext` (`turn_ctx`)**: Exposes `snapshot_id` (pre-reserved at turn
  start when a `store` is configured, `None` otherwise), `parent_snapshot_id`,
  and `turn_index`. Pre-reserving `snapshot_id` lets you name external worktrees
  or scratch directories after the snapshot before the turn commits.
  `turn_index` is 0-based within one invocation; each `chat.send` starts a new
  invocation, so it does not count turns across the session.
- **`SessionRunner` (`sess`) helpers**: `get_messages()` / `add_messages([...])`
  / `set_messages([...])`, `get_custom()` / `update_custom(sync_fn)`, and
  `get_artifacts()` / `add_artifacts([...])`. Both `add_messages` and
  `add_artifacts` take a `list`.
- **Turn completion and failures**: `TurnResult` accepts
  `(finish_reason=..., error=...)` — it does **not** take `messages=`. Raising
  an exception inside `handle_turn` ends the turn with
  `finish_reason=AgentFinishReason.FAILED`, populates `res.error` on the
  caller's `AgentResponse`, and stops the turn loop. `chat.send` returns that
  failed turn; it does not raise.
- **Model failures do not raise**: `ai.generate` and `ai.generate_stream` report
  provider errors on `response.error` with `finish_reason='failed'`. Raise a
  `GenkitError` from it so the caller's `res.error` keeps the provider status
  (e.g. `UNAVAILABLE`); otherwise the caller sees a generic `UNKNOWN` "Agent
  turn failed." (or a silent `STOP` if you hardcode the finish reason).

## Streaming custom agent example

```python
from genkit_google_genai import GoogleAI

from genkit import GenkitError
from genkit.exp import Genkit
from genkit.exp.agent import (
    AgentContext,
    AgentFinishReason,
    AgentInput,
    AgentResult,
    AgentStreamChunk,
    InMemorySessionStore,
    SessionRunner,
    TurnContext,
    TurnResult,
)

ai = Genkit(plugins=[GoogleAI()])
store = InMemorySessionStore()


async def custom_coder_fn(sess: SessionRunner, ctx: AgentContext) -> AgentResult:
    async def handle_turn(inp: AgentInput, turn_ctx: TurnContext) -> TurnResult | None:
        # 1. Read history (already includes inp.message as list[Message])
        history = await sess.get_messages()

        # 2. Stream model chunks out through AgentContext
        stream_resp = ai.generate_stream(
            model=GoogleAI.gemini('gemini-flash-latest'),
            system='Concise Python systems assistant.',
            messages=history,
        )
        async for chunk in stream_resp.stream:
            ctx.send_chunk(AgentStreamChunk(model_chunk=chunk))

        # 3. Fail the turn on model errors (generate reports them instead of raising)
        res = await stream_resp.response
        if res.error is not None:
            raise GenkitError(status=res.error.status, message=res.error.message)

        # 4. Persist the assistant reply so subsequent turns see it
        if res.message:
            await sess.add_messages([res.message])

        # 5. Every model FinishReason value exists on AgentFinishReason
        return TurnResult(finish_reason=AgentFinishReason(res.finish_reason.value))

    await sess.run(handle_turn)
    return await sess.result()


agent = ai.define_custom_agent(name='customCoder', fn=custom_coder_fn, store=store)


async def main() -> None:
    chat = agent.chat()
    res = await chat.send('Show a dict comprehension that inverts keys and values.')
    print(res.text)
    # => inverted = {v: k for k, v in original.items()}
    #    (model reply, usually wrapped in a markdown code fence)


if __name__ == '__main__':
    ai.run_main(main())
```

## Non-streaming `handle_turn` with tools

When `ai.generate(..., tools=[...])` runs a multi-step tool loop inside
`handle_turn`, `res.messages` contains the full conversation transcript (prior
history + intermediate tool requests/responses + final model reply, plus a
leading `Role.SYSTEM` message when `system=` was passed). Strip `Role.SYSTEM`
and save the updated transcript with `await sess.set_messages(...)`:

```python
from datetime import datetime, timezone

from genkit_google_genai import GoogleAI

from genkit import GenkitError, Role
from genkit.exp import Genkit
from genkit.exp.agent import (
    AgentContext,
    AgentFinishReason,
    AgentInput,
    AgentResult,
    InMemorySessionStore,
    SessionRunner,
    TurnContext,
    TurnResult,
)

ai = Genkit(plugins=[GoogleAI()])


@ai.tool(name='utcNow', description='Return the current UTC timestamp.')
async def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ops_agent_fn(sess: SessionRunner, ctx: AgentContext) -> AgentResult:
    async def handle_turn(inp: AgentInput, turn_ctx: TurnContext) -> TurnResult | None:
        # 1. Run the model + tool loop over the session history
        history = await sess.get_messages()
        res = await ai.generate(
            model=GoogleAI.gemini('gemini-flash-latest'),
            system='Ops assistant. Use utcNow when asked for the current time.',
            messages=history,
            tools=[utc_now],
        )
        if res.error is not None:
            raise GenkitError(status=res.error.status, message=res.error.message)

        # 2. Persist tool-request, tool-response, and final model messages without duplicating system
        await sess.set_messages([m for m in res.messages if m.role != Role.SYSTEM])
        return TurnResult(finish_reason=AgentFinishReason(res.finish_reason.value))

    await sess.run(handle_turn)
    return await sess.result()


ops_agent = ai.define_custom_agent(name='opsAgent', fn=ops_agent_fn, store=InMemorySessionStore())
```

Related guides: [state](agents-state.md) · [artifacts](agents-artifacts.md) ·
[tools](agents.md#tools-progress-chunks-and-multipart-responses)
