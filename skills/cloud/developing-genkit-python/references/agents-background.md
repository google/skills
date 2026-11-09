# Background Agents & Cancellation (Experimental)

> Requires a [session store](agents-sessions.md). For abort to cancel a running
> turn, the store must also implement `SnapshotSubscriber`
> (`InMemorySessionStore`, `FileSessionStore`, and `FirestoreSessionStore` do).
> See [agents.md](agents.md).

`await chat.detach(...)` hands a turn to the server, reserves a `snapshot_id` in
`SnapshotStatus.PENDING` (with background heartbeat refreshes), and returns a
`DetachedTask` handle immediately without waiting for model or tool completion.

- [Detach, poll, and load results](#detach-poll-and-load-results): Lines 19-66
- [Client detach vs. server cancellation](#client-detach-vs-server-cancellation): Lines 68-110
- [Tool cancellation (asyncio.CancelledError)](#tool-cancellation-asynciocancellederror): Lines 112-134
- [Fan-out parallel research](#fan-out-parallel-research): Lines 136-162

---

## Detach, poll, and load results

Because the originating `chat` never streams a detached turn's chunks, rehydrate
the finished conversation with
`await agent.load_chat(snapshot_id=task.snapshot_id)` once the task settles:

```python
from genkit_google_genai import GoogleAI

from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore, SnapshotStatus

ai = Genkit(plugins=[GoogleAI()])

agent = ai.define_agent(
    name='backgroundAnalyst',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='Research analyst. Write concise markdown memos.',
    store=InMemorySessionStore(),
)


async def main() -> None:
    # 1. Start the turn on the server and get a snapshot handle immediately
    chat = agent.chat()
    task = await chat.detach('Summarize grid battery storage economics.')
    print(task.snapshot_id)

    # 2. Stream snapshot status updates (or await task.wait(interval=1.0) directly)
    snapshot = None
    async for snap in task.poll(interval=1.0):
        print(snap.status)
        snapshot = snap

    # 3. Verify terminal status and load the completed snapshot
    assert snapshot is not None and snapshot.status == SnapshotStatus.COMPLETED
    done = await agent.load_chat(snapshot_id=task.snapshot_id)
    print(done.messages[-1].text)


if __name__ == '__main__':
    ai.run_main(main())
```

Terminal snapshot statuses on `poll()` / `wait()` are `COMPLETED`, `FAILED`,
`ABORTED`, and `EXPIRED` (reported on read when a pending turn's heartbeat goes
stale). Always check `snapshot.status == SnapshotStatus.COMPLETED` before
reading reply messages.

## Client detach vs. server cancellation

Always `await` abort calls. Genkit distinguishes stopping a local listener from
cancelling work on the server:

- **Client detach (`await turn.abort()` or `asyncio.timeout` /
  `asyncio.wait_for`)**: stops streaming locally and resolves `turn.response` as
  cancelled immediately while the server turn keeps running to completion in the
  background. Wrapping `turn.stream` or `await turn.response` in
  `async with asyncio.timeout(...)` detaches the client the same way and
  re-raises `TimeoutError`.
- **Server cancel (`await task.abort()`, `await chat.abort()`, or
  `await agent.abort(snapshot_id)`)**: flips a pending snapshot to
  `SnapshotStatus.ABORTED` in the store and cancels the running server task.
  Returns the snapshot's **previous** `SnapshotStatus` (`SnapshotStatus.PENDING`
  if this call stopped a live turn; a terminal status if the turn had already
  finished).

`chat.abort()` targets the chat's last recorded snapshot, so calling it while a
foreground `send()` is in flight does not stop that turn: it returns the
previous turn's status (`SnapshotStatus.COMPLETED`), or raises `ValueError` on a
first turn with no snapshot yet. Use `detach()` + `task.abort()` to cancel a
running turn.

```python
chat = agent.chat()
task = await chat.detach('Audit every quarterly filing since 2015.')

# Cancel server-side execution; returns the status from *before* the abort write
previous_status = await task.abort()
# => SnapshotStatus.PENDING (the snapshot row is now SnapshotStatus.ABORTED)

# Aborted leaves are not resumable directly; continue from the last completed turn via session_id
recovered = agent.chat(session_id=chat.session_id)
res = await recovered.send('Audit only Q4 2025 instead.')
print(res.text)
# => Q4 2025 audit: ...
```

On the very first turn of a session, a client-side `turn.abort()` detaches
before the client receives `session_id` or `snapshot_id`. Prefer
`await chat.detach(...)` + `await task.abort()` whenever you need a recoverable
server-side cancel handle from turn start.

## Tool cancellation (`asyncio.CancelledError`)

When a server turn is aborted (or an in-process caller cancels), Python delivers
standard `asyncio.CancelledError` into active model requests, retry sleeps, and
running `@ai.tool()` coroutines at the current `await` (there is no abort-signal
attribute on `ToolContext`). Clean up partial external work in `try` / `finally`
(and always re-raise `CancelledError` if caught):

```python
import asyncio


@ai.tool(name='runBackfill', description='Run a multi-batch warehouse backfill.')
async def run_backfill(table: str) -> dict[str, object]:
    job_id = f'job-{table}'
    try:
        await asyncio.sleep(10.0)
        return {'job_id': job_id, 'status': 'completed'}
    finally:
        # Runs whether the tool returns normally, fails, or receives CancelledError
        print(f'releasing lease for {job_id}')
        # => releasing lease for job-orders  (also after await task.abort() mid-run)
```

## Fan-out parallel research

A single `AgentChat` runs one turn at a time. To run background branches
concurrently, fork independent chats from a shared checkpoint `snapshot_id`:

```python
import asyncio

root = agent.chat()
await root.send('Context: B2B SaaS workload, 50k RPS peak, strict multi-region RPO.')
checkpoint = root.snapshot_id
assert checkpoint is not None


async def research(engine: str) -> tuple[str, str]:
    branch = await agent.load_chat(snapshot_id=checkpoint)
    task = await branch.detach(f'Evaluate {engine} against our requirements.')
    snap = await task.wait(interval=1.0)
    if snap.status != SnapshotStatus.COMPLETED:
        return engine, f'unfinished ({snap.status})'
    done = await agent.load_chat(snapshot_id=task.snapshot_id)
    return engine, done.messages[-1].text


results = await asyncio.gather(research('Cloud Spanner'), research('AlloyDB'))
# => [('Cloud Spanner', '...'), ('AlloyDB', '...')]
```
