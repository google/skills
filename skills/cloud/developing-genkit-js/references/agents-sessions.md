# Agent Sessions & Persistence (Beta)

> **Beta / preview API.** Session stores are imported from `genkit/beta`
> (`InMemorySessionStore`, `FileSessionStore`) and
> `@genkit-ai/google-cloud/beta`
> (`FirestoreSessionStore`). See [agents.md](agents.md) for the basics first.

When an agent has a `store`, the **server** owns the session history. Each turn
produces an immutable **snapshot**; the snapshot chain is what carries
conversation state forward. A store also enables
[branching](agents-branching.md)
and [background execution](agents-background.md). (Interrupts work with or
without
a store — see [human-in-the-loop](agents-human-in-the-loop.md).)

- [Pick a store](#pick-a-store): Lines 24-69
- [Typed session state](#typed-session-state): Lines 71-93
- [Interrupts (human-in-the-loop)](#interrupts-human-in-the-loop): Lines 95-100
- [Firestore session store (scalable, Beta)](#firestore-session-store-scalable-beta): Lines 102-136
- [Implementing a custom SessionStore](#implementing-a-custom-sessionstore): Lines 138-159

---

## Pick a store

```ts
import { InMemorySessionStore, FileSessionStore } from 'genkit/beta';

// In-memory: great for tests/dev; lost on restart.
const memStore = new InMemorySessionStore();

// File-backed: snapshots persisted under <dir>/global/<snapshotId>.json
const fileStore = new FileSessionStore('./.snapshots');

// File store with chain pruning - keep only the last N snapshots in a chain.
const pruning = new FileSessionStore('./.snapshots', {
  maxPersistedChainLength: 3,
});
```

Attach it to the agent:

```ts
import { ai } from './genkit.js';

export const logbookAgent = ai.defineAgent({
  name: 'logbookAgent',
  system: 'You are a personal logbook assistant.',
  store: fileStore,
});
```

A single `chat` persists to the store and threads the snapshot forward
automatically:

```ts
const chat = logbookAgent.chat();
const res1 = await chat.send('Log this: I started studying Genkit today.');
const res2 = await chat.send('What did I study today?'); // remembers turn 1
console.log(res1.snapshotId, res2.snapshotId);
```

Resume a prior conversation by snapshot id:

```ts
// Continue an existing session from its latest snapshot.
const resumed = logbookAgent.chat({ snapshotId: res2.snapshotId });
await resumed.send('Add another note.');
```

## Typed session state

Use `stateSchema` to attach typed custom state to the session. `State` is
inferred from the schema and validated when a snapshot is loaded.

```ts
import { z } from 'genkit';

const Profile = z.object({ name: z.string(), tier: z.enum(['free', 'pro']) });

export const profileAgent = ai.defineAgent({
  name: 'profileAgent',
  system: 'Greet the user by name and tailor answers to their tier.',
  store: new InMemorySessionStore<z.infer<typeof Profile>>(),
  stateSchema: Profile,
});

// Seed custom state when opening the chat. Custom state lives under `.custom`
// of the `SessionState` (that's what `stateSchema` validates).
const chat = profileAgent.chat({
  state: { custom: { name: 'Ada', tier: 'pro' } },
});
```

## Interrupts (human-in-the-loop)

Interrupts pause a turn so a human can approve/provide input, then resume from
the exact pause point. They work with a store or with client-managed state
(persistence is orthogonal). See the dedicated reference:
[Human-in-the-loop / interrupts](agents-human-in-the-loop.md).

## Firestore session store (scalable, Beta)

For production, `FirestoreSessionStore` (from `@genkit-ai/google-cloud/beta`)
persists each turn as an incremental JSON Patch diff anchored to periodic
sharded
checkpoints — no single document approaches Firestore's 1 MiB limit, and
reads/writes per turn are bounded by `checkpointInterval` rather than total
session length (scales to long-lived chat/coding agents).

```ts
import { genkit } from 'genkit/beta';
import { FirestoreSessionStore } from '@genkit-ai/google-cloud/beta';

const ai = genkit({ plugins: [/* ... */] });

const myAgent = ai.defineAgent({
  name: 'myAgent',
  system: 'You are a helpful assistant.',
  // Defaults to a new Firestore() using Application Default Credentials.
  store: new FirestoreSessionStore(),
});
```

Options:

- `db`: explicit Firestore instance (defaults to a new `Firestore()`, honoring
  `FIRESTORE_EMULATOR_HOST`).
- `collection`: snapshot collection (default `"genkit-sessions"`). Companion
  collections `"<collection>-pointers"` and `"<collection>-shards"` are derived.
- `checkpointInterval`: turns between full-state checkpoints (default `25`).
  Lower for small, read-heavy state; raise for large per-turn state.
- `shardSize`: max bytes per shard/diff document (default `512 KiB`).

> On Firebase, `@genkit-ai/firebase` re-exports this store with Firebase app
> setup (a `firebaseApp` option). See its README.

## Implementing a custom `SessionStore`

```ts
import type { SessionStore } from 'genkit/beta';

// S is the custom state type.
const store: SessionStore<MyState> = {
  // Load a snapshot by snapshotId OR sessionId (exactly one).
  async getSnapshot(opts) {
    /* ... */ return undefined;
  },
  // Atomically read → mutate → persist. Returns the snapshotId used,
  // or null when the mutator returns null.
  async saveSnapshot(snapshotId, mutator, options) {
    /* ... */ return snapshotId ?? 'new-id';
  },
  // Optional: subscribe to snapshot state changes (used by background agents).
  onSnapshotStateChange(snapshotId, callback, options) {
    return () => {}; // unsubscribe
  },
};
```
