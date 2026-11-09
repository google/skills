# Agent Sessions & Persistence

> Sessions are experimental. `InMemorySessionStore` and `Session`/`SessionStore`
> come from `package:genkit/experimental.dart`; `FileSessionStore` from
> `package:genkit/experimental_io.dart` (needs `dart:io`);
> `FirestoreSessionStore`
> from `package:genkit_google_cloud`. See [agents.md](agents.md) for the basics
> and the experimental-import note first.

When an agent has a `store`, the **server** owns the session history. Each turn
produces an immutable **snapshot**; the snapshot chain is what carries
conversation state forward. A store also enables
[branching](agents-branching.md)
and [background execution](agents-background.md). (Interrupts work with or
without
a store — see [human-in-the-loop](agents-human-in-the-loop.md).)

- [Pick a store](#pick-a-store): Lines 26-74
- [Typed session state](#typed-session-state): Lines 76-115
- [Interrupts (human-in-the-loop)](#interrupts-human-in-the-loop): Lines 117-122
- [Firestore session store (scalable)](#firestore-session-store-scalable): Lines 124-167
- [Implementing a custom SessionStore](#implementing-a-custom-sessionstore): Lines 169-207

---

## Pick a store

```dart
import 'package:genkit/experimental.dart'; // InMemorySessionStore
import 'package:genkit/experimental_io.dart'; // FileSessionStore (dart:io)

// In-memory: great for tests/dev; lost on restart.
final memStore = InMemorySessionStore();

// File-backed: snapshots persisted as JSON under <dir>/global/.
final fileStore = FileSessionStore('./.snapshots');

// File store with chain pruning - keep only the last N snapshots in a chain.
final pruning = FileSessionStore('./.snapshots', maxPersistedChainLength: 3);
```

Attach it to the agent:

```dart
import 'genkit.dart';

final logbookAgent = ai.defineAgent(
  name: 'logbookAgent',
  system: 'You are a personal logbook assistant.',
  store: fileStore,
);
```

A single `chat` persists to the store and threads the snapshot forward
automatically:

```dart
final chat = logbookAgent.chat();
final res1 = await chat.send(text: 'Log this: I started studying Genkit today.');
final res2 = await chat.send(text: 'What did I study today?'); // remembers turn 1
print('${res1.snapshotId} ${res2.snapshotId}');
```

Resume a prior conversation by snapshot id (server-side):

```dart
// Continue an existing session from a snapshot, restoring its history.
final resumed = await logbookAgent.loadChat(snapshotId: res2.snapshotId);
await resumed.send(text: 'Add another note.');
```

`agent.chat(snapshotId: ...)` opens a new chat that **branches** from a snapshot
without pre-loading its history; `agent.loadChat(...)` returns a chat with the
history restored. See [branching](agents-branching.md).

## Typed session state

Use `stateSchema` to attach typed custom state to the session. It is validated
when a snapshot is loaded. Seed initial custom state when opening the chat via
the `state` argument (a `SessionState`, whose `custom` field holds your data).

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore
import 'package:schemantic/schemantic.dart';

import 'genkit.dart';

part 'profile_agent.g.dart';

@Schema()
abstract class $Profile {
  String get name;
  String get tier; // 'free' | 'pro'
}

final profileAgent = ai.defineAgent(
  name: 'profileAgent',
  system: 'Greet the user by name and tailor answers to their tier.',
  stateSchema: Profile.$schema,
  store: InMemorySessionStore(),
);

// Custom state lives under `.custom` of the SessionState.
final chat = profileAgent.chat(
  state: SessionState(
    custom: {'name': 'Ada', 'tier': 'pro'},
    messages: [],
    artifacts: [],
  ),
);
```

See [working with state](agents-state.md) for reading/mutating custom state
inside tools and syncing it to the client.

## Interrupts (human-in-the-loop)

Interrupts pause a turn so a human can approve/provide input, then resume from
the exact pause point. They work with a store or with client-managed state
(persistence is orthogonal). See the dedicated reference:
[Human-in-the-loop / interrupts](agents-human-in-the-loop.md).

## Firestore session store (scalable)

For production, `FirestoreSessionStore` (from `package:genkit_google_cloud`)
persists each turn as an incremental JSON Patch diff anchored to periodic
sharded
checkpoints — no single document approaches Firestore's 1 MiB limit, and
reads/writes per turn are bounded by `checkpointInterval` rather than total
session length (scales to long-lived chat/coding agents).

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent
import 'package:genkit_google_cloud/firestore_session_store.dart';

import 'genkit.dart';

final myAgent = ai.defineAgent(
  name: 'myAgent',
  system: 'You are a helpful assistant.',
  // Defaults to a new Firestore() using Application Default Credentials.
  store: FirestoreSessionStore(),
);
```

> **Project id.** ADC alone may not carry a project id, so the default
> `Firestore()` can fail at write time with `Project ID has not been discovered
> yet. Initialize the SDK with credentials that include a project ID, set
> project
> ID in Settings, or set the GOOGLE_CLOUD_PROJECT environment variable.` Export
> `GOOGLE_CLOUD_PROJECT` (the Firestore client also reads a small set of
> standard
> GCP project-id env vars), or pass an explicit `Firestore` via `db`.

Options:

- `db`: explicit `Firestore` instance (defaults to a new `Firestore()`, honoring
  `FIRESTORE_EMULATOR_HOST`).
- `collection`: snapshot collection (default `'genkit-sessions'`). Companion
  collections `'<collection>-pointers'` and `'<collection>-shards'` are derived.
- `checkpointInterval`: turns between full-state checkpoints (default `25`).
  Lower for small, read-heavy state; raise for large per-turn state.
- `shardSize`: max bytes per shard/diff document (default `512 KiB`).
- `snapshotPathPrefix`: `String Function(Map<String, dynamic>? context)?` — a
  per-tenant prefix derived from the call context (defaults to `'global'`).

## Implementing a custom `SessionStore`

Implement the `SessionStore` interface. `getSnapshot` loads by `snapshotId` OR
`sessionId`; `saveSnapshot` atomically reads → mutates → persists. Optionally
implement `SnapshotChangeNotifier.onSnapshotStateChange` (used by background
agents) to subscribe to snapshot status changes.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // SessionStore, SessionSnapshot, SnapshotMutator

class MySessionStore implements SessionStore {
  @override
  Future<SessionSnapshot?> getSnapshot({
    String? snapshotId,
    String? sessionId,
    Map<String, dynamic>? context,
  }) async {
    // Load and return a snapshot, or null.
    return null;
  }

  @override
  Future<String?> saveSnapshot(
    String? snapshotId,
    SnapshotMutator mutator, {
    Map<String, dynamic>? context,
  }) async {
    // Read → mutate → persist; return the snapshotId used, or null when the
    // mutator returns null.
    return snapshotId;
  }
}
```

> Check the exact `SessionStore` method signatures in your installed version
> with
> `dart doc` or by inspecting `package:genkit` — the shape above matches the
> in-memory and file stores.
