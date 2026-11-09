# Background Agents / Detaching

> Detaching **requires a [session store](agents-sessions.md)** — the server
> needs somewhere to write the result when background work finishes. Read
> [agents.md](agents.md) first.

Detaching runs a turn in the background: the server saves a `pending` snapshot
and returns a `snapshotId` **immediately**, keeps processing, then updates the
snapshot to a terminal status (`completed` / `failed` / `aborted` / `expired`).
The client polls for completion and can abort.

- [Define the agent (store required)](#define-the-agent-store-required): Lines 19-46
- [Client-side: detach, poll, and abort](#client-side-detach-poll-and-abort): Lines 48-87
- [Server-side: detach and wait](#server-side-detach-and-wait): Lines 89-101
- [Status values](#status-values): Lines 103-115

---

## Define the agent (store required)

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore

import 'genkit.dart';

final backgroundAgent = ai.defineAgent(
  name: 'backgroundAgent',
  system: 'You are a senior research analyst. Produce a comprehensive '
      'markdown report.',
  use: [retry()],
  store: InMemorySessionStore(), // REQUIRED for detach
);
```

Expose its companion actions so the client can poll/abort (see
[agents.md](agents.md#serve-an-agent-over-http)):

```dart
import 'package:genkit/experimental_io.dart';
import 'package:genkit/io.dart';

// The store makes addAgent mount /getSnapshot and /abort next to the turn route.
final genkit = GenkitRouter()
  ..addAgent(backgroundAgent, path: '/api/backgroundAgent');
```

## Client-side: detach, poll, and abort

On the client (`package:genkit/client.dart`), `chat.detach(text: ...)` (or
`chat.detach(...)`) resolves immediately with a `DetachedTask` carrying the
`snapshotId`. `task.poll(...)` yields `AgentSnapshot`s until a terminal status;
`task.abort()` cancels the background work. Each `AgentSnapshot` surfaces
`.status`, `.messages`, `.artifacts`, and typed `.custom` state directly.

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, DetachedTask

final agent = remoteAgent(url: '/api/backgroundAgent');

// Submit - resolves immediately with a handle.
final task = await agent.chat().detach(text: 'Quantum computing impact');
print(task.snapshotId);

// Poll until a terminal status.
await for (final snap in task.poll(interval: Duration(milliseconds: 1500))) {
  final status = snap.status?.value ?? 'pending';
  if (status == 'completed') {
    final messages = snap.messages;
    final lastModel =
        messages.where((m) => m.role == Role.model).lastOrNull;
    final text =
        (lastModel?.content ?? []).map((p) => p.text ?? '').join();
    print(text);
    break;
  } else if (status == 'failed') {
    throw Exception('Background task failed on the server.');
  } else if (status == 'aborted' || status == 'expired') {
    break;
  }
  // 'pending' → keep polling
}

// Abort an in-flight task at any time:
await task.abort();
```

## Server-side: detach and wait

You can also detach from a server-side chat and wait for the result. `task.wait`
polls the store until a terminal state and resolves with the final snapshot.

```dart
final chat = backgroundAgent.chat();
final task = await chat.detach(text: 'Write a report on renewable energy trends');
print(task.snapshotId); // available immediately

final snapshot = await task.wait(interval: Duration(seconds: 2));
print(snapshot?.status?.value); // 'completed' | 'failed' | 'aborted' | 'expired'
```

## Status values

- `pending` — still processing.
- `completed` — completed successfully (read the result from
  `snapshot.messages`).
- `failed` — error during processing.
- `aborted` — cancelled by the client via `abort()`.
- `expired` — the background worker stopped responding (e.g. server restart);
  terminal, the task can never complete.

> Equivalent low-level wire protocol: the client sends `{ detach: true }` with
> the message; `poll`/`wait` hit the agent's `getSnapshot` action, and `abort`
> hits the `abort` action. `remoteAgent` wraps all of this for you.
