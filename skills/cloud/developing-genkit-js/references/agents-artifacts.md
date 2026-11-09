# Working with Artifacts (Beta)

> **Beta / preview API.** The `artifacts()` middleware comes from
> `@genkit-ai/middleware`; the `Artifact` type from `genkit/beta`. Read
> [agents.md](agents.md) first.

**Artifacts** are named, content-bearing deliverables an agent produces during a
session — files, reports, code, etc. They live in the session (deduplicated by
name) and are returned in `res.artifacts` / tracked on the client's
`chat.artifacts`.

- [Give the model artifact tools](#give-the-model-artifact-tools): Lines 20-52
- [The Artifact shape](#the-artifact-shape): Lines 54-67
- [Programmatic access (inside tools and custom agents)](#programmatic-access-inside-tools-and-custom-agents): Lines 69-83
- [Reading artifacts on the client](#reading-artifacts-on-the-client): Lines 85-98
- [Sharing artifacts across agents](#sharing-artifacts-across-agents): Lines 100-113

---

## Give the model artifact tools

The `artifacts()` middleware (see [using middleware](middleware.md)) adds
`write_artifact` and `read_artifact` tools and injects an `<artifacts>` listing
into the system prompt each turn (names + sizes, not full content). No custom
tool code needed.

```ts
import { artifacts } from '@genkit-ai/middleware';
import { ai } from './genkit.js';

export const workspaceAgent = ai.defineAgent({
  name: 'workspaceAgent',
  system: `You are a code generation assistant. Use write_artifact to create
files (pass the filename as "name" and the full content as "content"). Use
read_artifact to review or modify a previously created file.`,
  use: [artifacts()],
});
```

Run it; artifacts are produced via the tool and returned in the response:

```ts
const chat = workspaceAgent.chat();
const res = await chat.send('Write poem.txt with a poem about Genkit');
console.log(res.artifacts); // Artifact[]
```

Options:

- `readonly` (default `false`): when `true`, only `read_artifact` is provided —
  the model can read but not create/update artifacts. Useful on an orchestrator
  that should review (but not produce) sub-agent artifacts.

## The `Artifact` shape

```ts
import type { Artifact } from 'genkit/beta';

// An artifact's content lives in `parts` (text parts). `metadata` is optional.
const artifact: Artifact = {
  name: 'poem.txt',
  parts: [{ text: 'Roses are red…' }],
  metadata: { source: 'workspaceAgent' }, // optional
};
```

Writing the same `name` again **replaces** the artifact (dedup by name).

## Programmatic access (inside tools and custom agents)

Use the active session. `ai.currentSession()` throws when there's no active
session, so only call it inside an agent turn.

```ts
const session = ai.currentSession();

// Read all artifacts:
const all = session.getArtifacts(); // Artifact[]
const found = all.find((a) => a.name === 'poem.txt');

// Create / replace artifacts:
session.addArtifacts([{ name: 'notes.md', parts: [{ text: '# Notes' }] }]);
```

## Reading artifacts on the client

The `remoteAgent` client tracks artifacts on `chat.artifacts` (and each response
exposes `res.artifacts`):

```ts
import { remoteAgent } from 'genkit/beta/client';

const agent = remoteAgent({ url: '/api/workspaceAgent' });
const chat = agent.chat();
const res = await chat.send('Create index.html and styles.css');
console.log(res.artifacts); // Artifact[] produced this turn
console.log(chat.artifacts); // all artifacts tracked for the session
```

## Sharing artifacts across agents

In [multi-agent orchestration](agents-multi-agent.md), set the `agents()`
middleware's `artifactStrategy: 'session'` so sub-agent artifacts are merged
into the parent session (namespaced by invocation ID), and add
`artifacts({ readonly: true })` to the orchestrator so it can `read_artifact`
them:

```ts
use: [
  agents({ agents: ['researcher', 'coder'], artifactStrategy: 'session' }),
  artifacts({ readonly: true }),
];
```
