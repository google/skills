# Agent Branching (Beta)

> **Beta / preview API.** Requires a [session store](agents-sessions.md) so
> snapshots are persistent. Read [agents.md](agents.md) first.

A `snapshotId` is an **immutable checkpoint**, like a git commit. You can fork
as
many independent timelines as you want from the same snapshot — each turn from a
snapshot creates a new, independent snapshot; the original is unchanged.

To branch, open a new `chat` attached to an earlier snapshot via
`chat({ snapshotId })`.

## Server-side branching

```ts
import { z } from 'genkit';
import { InMemorySessionStore } from 'genkit/beta';
import { ai } from './genkit.js';

export const assistant = ai.defineAgent({
  name: 'assistant',
  system: 'You are a helpful assistant.',
  store: new InMemorySessionStore(),
});

const root = assistant.chat();
const res1 = await root.send('Hello!');
const checkpoint = res1.snapshotId; // branch point

// Branch A - forks from `checkpoint`.
const branchA = assistant.chat({ snapshotId: checkpoint });
await branchA.send('My name is Bob.');
const resA = await branchA.send('What is my name?'); // -> Bob

// Branch B - forks from the SAME `checkpoint`, fully independent.
const branchB = assistant.chat({ snapshotId: checkpoint });
await branchB.send('My name is John.');
const resB = await branchB.send('What is my name?'); // -> John
```

## Client-side branching ("pick a variant")

A common pattern: generate two variants from the same checkpoint in parallel,
let the user pick one, and continue from the chosen snapshot.

```ts
import { remoteAgent } from 'genkit/beta/client';

const agent = remoteAgent({ url: '/api/branchingAgent' });
let snapshotId: string | undefined; // current branch point

async function twoVariants(text: string) {
  // Each variant gets its own chat branching from the same snapshot
  // (or a fresh session when there's no branch point yet).
  const makeChat = () =>
    snapshotId ? agent.chat({ snapshotId }) : agent.chat();

  const [a, b] = await Promise.all([
    makeChat().send(text),
    makeChat().send(text),
  ]);
  // a.snapshotId !== b.snapshotId - both branch from the same point.
  return { a, b };
}

// When the user picks a variant, its snapshotId becomes the new branch point:
function pick(chosenSnapshotId: string) {
  snapshotId = chosenSnapshotId;
}
```

## Restoring history from a snapshot

Use `agent.getSnapshot(snapshotId)` to read a snapshot's state without starting
a
turn — handy for restoring a UI after a reload (e.g. snapshotId stored in the
URL). The server must expose the agent's `getSnapshotDataAction` (see
[agents.md](agents.md#serve-an-agent-over-http)).

```ts
import type { Part } from 'genkit/beta';
import { remoteAgent } from 'genkit/beta/client';

const agent = remoteAgent({ url: '/api/branchingAgent' });

const snapshot = await agent.getSnapshot(snapshotId);
const history = (snapshot?.state?.messages ?? [])
  .filter((m) => m.role === 'user' || m.role === 'model')
  .map((m) => ({
    role: m.role,
    text: (m.content ?? [])
      .filter((p: Part) => p.text)
      .map((p: Part) => p.text)
      .join(''),
  }));
```

> Abandoned branches simply remain in the store as immutable snapshots; nothing
> is overwritten when you branch.
