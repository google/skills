# Background Agents / Detaching (Beta)

> **Beta / preview API.** Detaching **requires a
> [session store](agents-sessions.md)** —
> the server needs somewhere to write the result when background work finishes.
> Read [agents.md](agents.md) first.

Detaching runs a turn in the background: the server saves a `pending` snapshot
and returns a `snapshotId` **immediately**, keeps processing, then updates the
snapshot to a terminal status (`completed` / `failed` / `aborted` / `expired`).
The client polls for completion and can abort.

- [Define the agent (store required)](#define-the-agent-store-required): Lines 21-54
- [Server-side: detach and wait](#server-side-detach-and-wait): Lines 56-74
- [Resume a failed or aborted task](#resume-a-failed-or-aborted-task): Lines 76-91
- [Client-side: detach, poll, and abort](#client-side-detach-poll-and-abort): Lines 93-133
- [Status values](#status-values): Lines 135-155

---

## Define the agent (store required)

```ts
import { InMemorySessionStore } from 'genkit/beta';
import { ai } from './genkit.js';

export const backgroundAgent = ai.defineAgent({
  name: 'backgroundAgent',
  system:
    'You are a senior research analyst. Produce a comprehensive markdown report.',
  store: new InMemorySessionStore(), // REQUIRED for detach
});
```

Expose its companion actions so the client can poll/abort (see
[agents.md](agents.md#serve-an-agent-over-http)):

```ts
app.post('/api/backgroundAgent', expressHandler(backgroundAgent));
app.post(
  '/api/backgroundAgent/getSnapshot',
  expressHandler(backgroundAgent.getSnapshotDataAction)
);
app.post(
  // Optional (genkit >= 1.43.0): lets remoteAgent's task.wait() block on the
  // server in one request instead of polling getSnapshot.
  '/api/backgroundAgent/waitForSnapshot',
  expressHandler(backgroundAgent.waitForSnapshotAction)
);
app.post(
  '/api/backgroundAgent/abort',
  expressHandler(backgroundAgent.abortAgentAction)
);
```

## Server-side: detach and wait

`chat.detach(message)` returns a `DetachedTask` carrying the `snapshotId`.
`task.wait()` blocks until a terminal state and resolves with the final
snapshot. The wait happens next to the store, so there is no polling loop on
your side.

```ts
const chat = backgroundAgent.chat();
const task = await chat.detach('Write a report on renewable energy trends');
console.log(task.snapshotId); // available immediately

// Bound the wait with an abort signal; the task keeps running if it fires.
const snapshot = await task.wait({ abortSignal: AbortSignal.timeout(60_000) });
console.log(snapshot.status); // 'completed' | 'failed' | 'aborted' | 'expired'
```

Without a `DetachedTask` handle, `backgroundAgent.waitForSnapshot(snapshotId)`
does the same from a stored ID.

## Resume a failed or aborted task

> Requires `genkit >= 1.43.0`. Earlier versions only resumed `completed`
> snapshots.

`failed` and `aborted` snapshots hold the conversation up to the last completed
tool round, so they are resume points. `send({})` (no message, no resume)
re-runs the turn without repeating finished tool calls:

```ts
const snap = await task.wait();
if (snap.status === 'failed' || snap.status === 'aborted') {
  const retry = await backgroundAgent.loadChat({ snapshotId: snap.snapshotId });
  await retry.send({}); // or retry.send('Try again, but skip X.')
}
```

## Client-side: detach, poll, and abort

On the client (`genkit/beta/client`), `task.poll()` yields snapshots until a
terminal status; `task.abort()` cancels the background work.

```ts
import { remoteAgent, type DetachedTask } from 'genkit/beta/client';
import type { MessageData, Part } from 'genkit/beta';

const agent = remoteAgent({ url: '/api/backgroundAgent' });

// Submit - resolves immediately with a handle.
const task: DetachedTask = await agent.chat().detach('Quantum computing impact');
console.log(task.snapshotId);

// Poll until a terminal status.
for await (const snap of task.poll({ intervalMs: 2000 })) {
  if (snap.status === 'completed') {
    const messages: MessageData[] = snap.state?.messages ?? [];
    const lastModel = messages.filter((m) => m.role === 'model').at(-1);
    const text = (lastModel?.content ?? [])
      .filter((p: Part) => p.text)
      .map((p: Part) => p.text)
      .join('');
    console.log(text);
    break;
  } else if (snap.status === 'failed') {
    throw new Error('Background task failed on the server.');
  } else if (snap.status === 'aborted') {
    break;
  } else if (snap.status === 'expired') {
    // Worker stopped sending heartbeats (e.g. the server restarted) so the
    // task can never complete - treat as terminal.
    break;
  }
  // 'pending' → keep polling
}

// Abort an in-flight task at any time:
await task.abort();
```

## Status values

- `pending`: still processing.
- `aborting`: `abort()` was called; the worker is winding down. Not terminal:
  `wait()` keeps waiting until it settles as `aborted`.
- `completed`: completed successfully (read the result from
  `snapshot.state.messages`).
- `failed`: error during processing. Resumable (see above).
- `aborted`: stopped by the caller. Carries the state the run had committed;
  resumable.
- `expired`: the background worker stopped responding (e.g. server restart);
  terminal, the task can never complete.

Pass `metadataOnly: true` in the `getSnapshot` request body to read status
without loading the conversation state.

> Equivalent low-level wire protocol: the client sends `{ detach: true }` with
> the message; `poll` hits the agent's `getSnapshot` action, `wait` hits
> `waitForSnapshot` (falling back to polling `getSnapshot` when it is not
> mounted), and `abort` hits the `abort` action. `remoteAgent` wraps all of
> this for you.
