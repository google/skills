# Agent Branching

> Requires a [session store](agents-sessions.md) so snapshots are persistent.
> Read [agents.md](agents.md) first.

A `snapshotId` is an **immutable checkpoint**, like a git commit. You can fork
as
many independent timelines as you want from the same snapshot — each turn from a
snapshot creates a new, independent snapshot; the original is unchanged.

To branch, open a new `chat` attached to an earlier snapshot via
`agent.chat(snapshotId: ...)`.

- [Server-side branching](#server-side-branching): Lines 20-47
- [Client-side branching ("pick a variant")](#client-side-branching-pick-a-variant): Lines 49-80
- [Restoring history from a snapshot](#restoring-history-from-a-snapshot): Lines 82-110

---

## Server-side branching

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore

import 'genkit.dart';

final assistant = ai.defineAgent(
  name: 'assistant',
  system: 'You are a helpful assistant.',
  store: InMemorySessionStore(),
);

final root = assistant.chat();
final res1 = await root.send(text: 'Hello!');
final checkpoint = res1.snapshotId; // branch point

// Branch A - forks from `checkpoint`.
final branchA = assistant.chat(snapshotId: checkpoint);
await branchA.send(text: 'My name is Bob.');
final resA = await branchA.send(text: 'What is my name?'); // -> Bob

// Branch B - forks from the SAME `checkpoint`, fully independent.
final branchB = assistant.chat(snapshotId: checkpoint);
await branchB.send(text: 'My name is John.');
final resB = await branchB.send(text: 'What is my name?'); // -> John
```

## Client-side branching ("pick a variant")

A common pattern: generate two variants from the same checkpoint in parallel,
let the user pick one, and continue from the chosen snapshot.

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, AgentChat

final agent = remoteAgent(url: '/api/branchingAgent');
String? snapshotId; // current branch point

Future<(AgentResponse, AgentResponse)> twoVariants(String text) async {
  // Each variant gets its own chat branching from the same snapshot
  // (or a fresh session when there's no branch point yet).
  AgentChat makeChat() =>
      snapshotId != null ? agent.chat(snapshotId: snapshotId) : agent.chat();

  final results = await Future.wait([
    makeChat().send(text: text),
    makeChat().send(text: text),
  ]);
  // results[0].snapshotId != results[1].snapshotId - both branch from the
  // same point.
  return (results[0], results[1]);
}

// When the user picks a variant, its snapshotId becomes the new branch point:
void pick(String chosenSnapshotId) {
  snapshotId = chosenSnapshotId;
}
```

## Restoring history from a snapshot

Use `agent.getSnapshot(snapshotId: ...)` to read a snapshot's state without
starting a turn — handy for restoring a UI after a reload (e.g. a snapshotId
stored in the URL). The server must expose the agent's `getSnapshotDataAction`
(see [agents.md](agents.md#serve-an-agent-over-http)).

`getSnapshot(...)` returns an `AgentSnapshot<State>` — a typed veneer that
surfaces `.messages`, `.artifacts`, and typed `.custom` state directly (use
`.sessionState` for the raw `SessionState` if you need it).

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, AgentSnapshot

final agent = remoteAgent(url: '/api/branchingAgent');

final snapshot = await agent.getSnapshot(snapshotId: snapshotId);
final history = (snapshot?.messages ?? [])
    .where((m) => m.role == Role.user || m.role == Role.model)
    .map((m) => (
          role: m.role.value,
          text: m.content.map((p) => p.text ?? '').join(),
        ))
    .toList();
```

> Abandoned branches simply remain in the store as immutable snapshots; nothing
> is overwritten when you branch.
