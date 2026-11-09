# Agent State (Experimental)

> See [agents.md](agents.md) · [sessions](agents-sessions.md).

An agent session tracks three layers: `messages`, custom `state` (typed by
`state_schema`), and `artifacts`. When `state_schema` (a Pydantic `BaseModel`)
is set, `chat.state`, `res.state`, and streamed `chunk.custom` validate into
instances of that model instead of bare dicts.

- [Two state-management modes](#two-state-management-modes): Lines 18-32
- [Client-managed typed state](#client-managed-typed-state): Lines 34-76
- [Mutating state from tools (current_session)](#mutating-state-from-tools-current_session): Lines 78-131
- [Live state patches](#live-state-patches): Lines 133-151
- [Egress redaction (state_transform and chunk_transform)](#egress-redaction-state_transform-and-chunk_transform): Lines 153-188

---

## Two state-management modes

- **Server-managed (`store=...`)**: Genkit owns persistence. Resume with
  `snapshot_id` or `session_id`. Passing `state=`, `messages=`, or `artifacts=`
  to `agent.chat(...)` on a store-backed agent raises `AgentInitError`
  (`FAILED_PRECONDITION`).
- **Client-managed (`store=None`)**: Your caller owns persistence. Seed
  `agent.chat(state=...)` and pass `messages`, `state`, and `artifacts` back on
  subsequent chats.

Custom state holds application data (UI state, workflow counters, active ticket
IDs). Genkit does not inject `state` into the model prompt unless your system
prompt, messages, or tools expose it. Declaring `state_schema` alone leaves
`chat.state` as `None` until client seeding or `session.update_custom(...)`
writes a value.

## Client-managed typed state

```python
from genkit_google_genai import GoogleAI
from pydantic import BaseModel

from genkit.exp import Genkit


class DinerProfile(BaseModel):
    name: str
    allergies: list[str] = []


ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))

agent = ai.define_agent(
    name='conciergeAgent',
    system='Restaurant concierge. Keep replies brief.',
    state_schema=DinerProfile,
)


async def main() -> None:
    # 1. Seed typed state on a storeless agent
    chat = agent.chat(state=DinerProfile(name='Ada', allergies=['peanuts']))
    await chat.send('Recommend an appetizer.')
    assert chat.state is not None
    print(chat.state.name, chat.state.allergies)
    # => Ada ['peanuts']

    # 2. Round-trip messages, state, and artifacts to continue later
    resumed = agent.chat(
        messages=chat.messages,
        state=chat.state,
        artifacts=chat.artifacts,
    )
    await resumed.send('What about dessert?')


if __name__ == '__main__':
    ai.run_main(main())
```

## Mutating state from tools (`current_session`)

Inside an `@ai.tool()`, get the active session with `current_session()` from
`genkit.exp` (`None` outside an agent turn) and update custom state there.

`await sess.update_custom(fn)` is async; `fn` is sync. `fn` receives `None` on
the first write, then whatever the session currently holds: the model instance
you last returned, or a plain dict once state has round-tripped through JSON (a
persistent store, an HTTP client). Normalize it before building the new state:

```python
from typing import Any

from genkit_google_genai import GoogleAI
from pydantic import BaseModel, Field

from genkit.exp import Genkit, current_session
from genkit.exp.agent import InMemorySessionStore


class CaseState(BaseModel):
    case_id: str = ''
    status: str = 'open'


class OpenCaseInput(BaseModel):
    case_id: str = Field(description='Support case identifier')


ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))


@ai.tool(name='openCase', description='Open or switch the active support case.')
async def open_case(input: OpenCaseInput) -> dict[str, Any]:
    sess = current_session()
    if sess is None:
        return {'ok': False, 'error': 'no active agent session'}

    def mutate(c: CaseState | dict[str, Any] | None) -> CaseState:
        base = c if isinstance(c, CaseState) else CaseState.model_validate(c or {})
        return CaseState(case_id=input.case_id, status=base.status)

    await sess.update_custom(mutate)
    return {'ok': True, 'case_id': input.case_id}


agent = ai.define_agent(
    name='supportOps',
    system='Support ops assistant. Call openCase when given a case ID.',
    tools=[open_case],
    state_schema=CaseState,
    store=InMemorySessionStore(),
)
```

## Live state patches

Every `await sess.update_custom(...)` call (from a tool or a
[custom agent](agents-custom.md)) emits an RFC 6902 JSON Patch chunk
(`chunk.raw.custom_patch`). `AgentTurn.stream` applies the patch and puts the
resolved state on `chunk.custom`, typed by `state_schema`. With the `supportOps`
agent above:

```python
chat = agent.chat()
turn = chat.send_stream('Open case SUP-402.')
async for chunk in turn.stream:
    if chunk.custom is not None:
        print(chunk.custom.case_id, chunk.custom.status)
        # => SUP-402 open
res = await turn.response
print(res.state)
# => case_id='SUP-402' status='open'
```

## Egress redaction (`state_transform` and `chunk_transform`)

`state_transform` and `chunk_transform` filter what leaves the server without
altering persisted snapshots:

- **`state_transform(state: SessionState) -> SessionState`**: shapes snapshot
  reads, client-managed `AgentOutput.state`, and streamed custom-patch
  baselines. Must return a `SessionState` (use `state.model_copy(update=...)` so
  `session_id` is preserved).
- **`chunk_transform(chunk: AgentStreamChunk) -> AgentStreamChunk | None`**:
  reshapes or drops individual stream chunks; return `None` to suppress a chunk.

```python
from genkit.exp.agent import AgentStreamChunk, InMemorySessionStore, SessionState


def redact_state(state: SessionState) -> SessionState:
    custom = dict(state.custom or {})
    custom.pop('internal_token', None)
    return state.model_copy(update={'custom': custom})


def drop_debug_artifacts(chunk: AgentStreamChunk) -> AgentStreamChunk | None:
    if chunk.artifact and chunk.artifact.name == 'debug.log':
        return None
    return chunk


guarded_agent = ai.define_agent(
    name='guardedAgent',
    system='Concise support agent.',
    state_transform=redact_state,
    chunk_transform=drop_debug_artifacts,
    store=InMemorySessionStore(),
)
```
