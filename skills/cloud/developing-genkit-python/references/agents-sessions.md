# Sessions & Persistence (Experimental)

> See [agents.md](agents.md).

With a `SessionStore`, the server owns conversation history. Every turn writes a
`SessionSnapshot` keyed by `snapshot_id`, enabling resume across restarts,
[branching](agents-branching.md), and
[detached background turns](agents-background.md).
[Interrupts](agents-human-in-the-loop.md) work with or without a store.

- [Choose a store](#choose-a-store): Lines 18-47
- [Persist and rehydrate a chat](#persist-and-rehydrate-a-chat): Lines 49-81
- [Resume and lookup methods](#resume-and-lookup-methods): Lines 83-98
- [Typed state and multi-user isolation](#typed-state-and-multi-user-isolation): Lines 100-108

---

## Choose a store

Import local stores from `genkit.exp.agent` and the production Firestore store
from `genkit_google_cloud.exp`:

```python
from genkit.exp.agent import FileSessionStore, InMemorySessionStore
from genkit_google_cloud.exp import FirestoreSessionStore

# 1. Local dev & tests (lost when the process exits)
mem_store = InMemorySessionStore()

# 2. Local disk persistence (one <snapshot_id>.json file per turn)
file_store = FileSessionStore(
    './.snapshots',
    max_persisted_chain_length=20,  # optional: prune oldest ancestors on save
    reject_ambiguous_session=True,  # optional: raise on session_id lookup after a fork
)

# 3. Production durable store (JSON Patch diffs + sharded checkpoints, ADC auth)
firestore_store = FirestoreSessionStore(
    collection='genkit-sessions',
    snapshot_path_prefix=lambda ctx: (ctx or {}).get('tenant_id', 'global'),
)
```

`FirestoreSessionStore` stores each turn as a JSON Patch diff from its parent
with periodic sharded checkpoints so large sessions stay below Firestore's 1 MiB
document limit without secondary indexes. Pass `snapshot_path_prefix` to isolate
multi-tenant paths from action `context`.

## Persist and rehydrate a chat

```python
from genkit_google_genai import GoogleAI

from genkit.exp import Genkit
from genkit.exp.agent import FileSessionStore

ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))

agent = ai.define_agent(
    name='logbookAgent',
    system='You are a concise engineering logbook assistant.',
    store=FileSessionStore('./.snapshots'),
)


async def main() -> None:
    # 1. Run turn 1; save res.snapshot_id in your app database
    chat = agent.chat()
    res = await chat.send('Log: migrated auth service to token exchange.')
    checkpoint = res.snapshot_id
    assert checkpoint is not None

    # 2. Rehydrate full state (messages, state, artifacts) onto a fresh chat
    resumed = await agent.load_chat(snapshot_id=checkpoint)
    res2 = await resumed.send('Add note: latency p99 stayed at 14ms.')
    print(res2.text)


if __name__ == '__main__':
    ai.run_main(main())
```

## Resume and lookup methods

- **`await agent.load_chat(snapshot_id=...)` / `load_chat(session_id=...)`**:
  reads the stored snapshot immediately and populates `chat.messages`,
  `chat.state`, and `chat.artifacts`. Pointing `load_chat` at a failed, aborted,
  or pending leaf loads that row as-is; calling `send()` on a non-completed
  snapshot returns `res.error` (`SNAPSHOT_NOT_RESUMABLE`).
- **`agent.chat(session_id=...)`**: attaches a lazy session handle without an
  upfront read. On the next `send()`, the server automatically walks back past
  any failed, aborted, or expired leaf to continue from the last completed turn
  (or starts a fresh session under `session_id` if no turn has completed yet).
- **`agent.chat(snapshot_id=...)`**: attaches a lazy resume handle to a specific
  completed snapshot.
- **`await agent.get_snapshot(snapshot_id=...)` /
  `get_snapshot(session_id=...)`**: inspects the raw `SessionSnapshot` without
  creating a chat.

## Typed state and multi-user isolation

- **Typed state**: Pass `state_schema=MyModel` on the agent. On a store-backed
  agent, `agent.chat(state=...)` raises `AgentInitError` immediately; mutate
  state from tools with `current_session()` from `genkit.exp` (see
  [state](agents-state.md)).
- **Multi-user sessions**: One `Agent` instance safely serves many users on a
  shared store. Each `agent.chat()` mints a distinct `session_id`; store
  `session_id` or `snapshot_id` per user in your application database.
