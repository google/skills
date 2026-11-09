# Agents (Beta)

> **Beta / preview API.** Agents are not yet stable. Server APIs come from
> `genkit/beta`; the browser client comes from `genkit/beta/client`. Import
> paths
> and signatures may change. Always use `genkit/beta`, not `genkit`, for agents.
>
> **Requires `genkit` >= 1.39.0.**

An **agent** is a persistent, multi-turn conversation primitive built on top of
prompts + tools. Compared to a bare `ai.generate`/`ai.definePrompt` loop, an
agent adds:

- **Sessions**: multi-turn history tracked as immutable **snapshots**.
- **State**: typed session state (messages + custom data + artifacts).
- **Interrupts**: human-in-the-loop pause/resume.
- **Branching**: fork a conversation from any snapshot.
- **Detaching**: run a turn in the background and poll for the result.

Progressive disclosure — read the file for the level you need:

- This file: defining an agent, serving it, and **client-managed state** (no
  store).
- [Sessions & persistence](agents-sessions.md): `SessionStore`,
  `InMemorySessionStore`, `FileSessionStore`, `FirestoreSessionStore`.
- [Human-in-the-loop / interrupts](agents-human-in-the-loop.md): pausing for
  approval/input and resuming.
- [Branching](agents-branching.md): forking a conversation from a snapshot.
- [Background agents](agents-background.md): detaching long-running turns and
  polling.
- [Working with state](agents-state.md): typed custom session state and client
  auto-sync.
- [Artifacts](agents-artifacts.md): producing/reading named deliverables.
- [Multi-agent orchestration](agents-multi-agent.md): delegating to sub-agents.
- [Advanced custom agents](agents-custom.md): `defineCustomAgent` for full turn
  control.
- [Deploying agents](agents-deployment.md): serving multiple agents over HTTP,
  CORS, web UI, other frameworks.

- [Setup](#setup): Lines 51-62
- [Define an agent](#define-an-agent): Lines 64-102
- [Agents and middleware go hand in hand](#agents-and-middleware-go-hand-in-hand): Lines 104-144
- [Chat with an agent (server-side)](#chat-with-an-agent-server-side): Lines 146-168
- [Verify an agent from the CLI (flow:run)](#verify-an-agent-from-the-cli-flowrun): Lines 170-187
- [Serve an agent over HTTP](#serve-an-agent-over-http): Lines 189-222
- [Consume an agent from a client (remoteAgent)](#consume-an-agent-from-a-client-remoteagent): Lines 224-252
- [Client-managed state (no server store)](#client-managed-state-no-server-store): Lines 254-301

---

## Setup

```ts
// genkit.ts - note the `genkit/beta` import (required for agents)
import { genkit } from 'genkit/beta';
import { googleAI } from '@genkit-ai/google-genai';

export const ai = genkit({
  plugins: [googleAI()],
  model: googleAI.model('gemini-flash-latest'),
});
```

## Define an agent

`ai.defineAgent` combines prompt + tool config + (optional) session store into a
single registered action.

```ts
import { z } from 'genkit';
import { ai } from './genkit.js';

const getWeather = ai.defineTool(
  {
    name: 'getWeather',
    description: 'Look up the current weather for a city.',
    inputSchema: z.object({ city: z.string() }),
    outputSchema: z.object({ tempC: z.number(), summary: z.string() }),
  },
  async ({ city }) => ({ tempC: 21, summary: 'Sunny' })
);

export const weatherAgent = ai.defineAgent({
  name: 'weatherAgent',
  system:
    'You are a helpful weather assistant. Use the getWeather tool. Be concise.',
  tools: [getWeather],
  // `store` is optional. Omit it for client-managed state (see below).
});
```

Common `defineAgent` options:

- `name` (required): action name.
- `system` / `prompt` / dotprompt fields: same as `definePrompt`.
- `tools`: tools and interrupts available to the agent.
- `model`: override the default model.
- `store`: a `SessionStore` for server-side persistence. See
  [sessions](agents-sessions.md).
- `stateSchema`: a `z.ZodType<State>` describing custom session state. When set,
  `State` is inferred and validated at load time.
- `input` / `inputSchema`: input variables for the prompt template.

## Agents and middleware go hand in hand

Agents and [middleware](middleware.md) are built for each other: the
`use: [...]`
array is where you layer in sophisticated behavior without writing it yourself.
Most agent capabilities — sub-agent delegation, artifacts, filesystem access,
skill loading, tool approval, retries — are just middleware you drop in.

For example, a full coding assistant is mostly configuration:

```ts
import { filesystem, retry, skills, toolApproval } from '@genkit-ai/middleware';
import { FileSessionStore } from 'genkit/beta';
import { ai } from './genkit.js';

export const codingAgent = ai.defineAgent({
  name: 'codingAgent',
  system: 'You are an expert AI coding assistant working in a sandboxed workspace.',
  tools: [runShell, askUser], // your own custom tools/interrupts
  use: [
    // Require user approval (interrupt) before risky tools; reads auto-approved.
    // Order matters: keep toolApproval before filesystem.
    toolApproval({
      approved: ['list_files', 'read_file', 'use_skill', 'run_shell', 'ask_user'],
    }),
    // list_files / read_file / write_file / search_and_replace, sandboxed.
    filesystem({ rootDirectory: WORKSPACE_DIR, allowWriteAccess: true }),
    // Load coding conventions on demand via a use_skill tool.
    skills({ skillPaths: [SKILLS_DIR] }),
    // Automatic retry on transient model errors.
    retry(),
  ],
  store: new FileSessionStore('./.snapshots-coding'), // needed for tool approval
  maxTurns: 30,
});
```

That single `use` array gives the agent filesystem tools, an on-demand skills
library, human-in-the-loop approval for writes, and retries — each is one line.
See [using middleware](middleware.md) for the full catalog and
[building custom middleware](middleware-custom.md) to write your own.

## Chat with an agent (server-side)

`agent.chat()` opens a conversation. A single `chat` carries state forward
automatically across turns.

```ts
const chat = weatherAgent.chat();

// Non-streaming turn:
const res = await chat.send('Weather in Tokyo?');
console.log(res.text);
console.log(res.snapshotId); // immutable checkpoint id for this turn

// Follow-up turn - history is carried automatically:
const res2 = await chat.send('What about Paris?');

// Streaming turn:
const turn = chat.sendStream('And London?');
for await (const chunk of turn.stream) {
  process.stdout.write(chunk.text ?? '');
}
const final = await turn.response;
```

## Verify an agent from the CLI (`flow:run`)

`genkit flow:run` only runs **flows**, not agents, so you can't `flow:run` an
agent directly. To exercise an agent from the CLI (e.g. a quick,
self-terminating
check), wrap one turn in a throwaway flow and run that:

```ts
import { z } from 'genkit';
import { weatherAgent } from './weather-agent.js';
import { ai } from './genkit.js';

export const tryWeatherAgent = ai.defineFlow(
  { name: 'tryWeatherAgent', inputSchema: z.string(), outputSchema: z.string() },
  async (message) => (await weatherAgent.chat().send(message)).text
);
// genkit flow:run tryWeatherAgent '"Weather in Tokyo?"' -- npx tsx src/index.ts
```

## Serve an agent over HTTP

Use `expressHandler` from `@genkit-ai/express`. Optionally expose the agent's
companion `getSnapshotDataAction` (for state lookup/restore) and
`abortAgentAction` (for background aborts).

```ts
import { expressHandler } from '@genkit-ai/express';
import express from 'express';
import { weatherAgent } from './weather-agent.js';

const app = express();
app.use(express.json());

// Main turn endpoint:
app.post('/api/weatherAgent', expressHandler(weatherAgent));

// Optional companions (needed for snapshot restore / branching / background):
app.post(
  '/api/weatherAgent/getSnapshot',
  expressHandler(weatherAgent.getSnapshotDataAction)
);
app.post(
  '/api/weatherAgent/abort',
  expressHandler(weatherAgent.abortAgentAction)
);

app.listen(8080);
```

For serving multiple agents, CORS/streaming headers for browser clients, a
static
web UI, and other host frameworks (Next.js, Firebase), see
[Deploying agents](agents-deployment.md).

## Consume an agent from a client (`remoteAgent`)

The browser/Node client lives in `genkit/beta/client`. `remoteAgent` returns a
typed HTTP client; `getSnapshotUrl`/`abortUrl` default to `${url}/getSnapshot`
and `${url}/abort`.

```ts
import { remoteAgent, AgentError } from 'genkit/beta/client';

const weather = remoteAgent({ url: 'http://localhost:8080/api/weatherAgent' });

const chat = weather.chat();
const turn = chat.sendStream('Weather in Tokyo?');
for await (const chunk of turn.stream) {
  process.stdout.write(chunk.text ?? '');
}
const res = await turn.response;
console.log(res.snapshotId, chat.snapshotId, chat.state);

// Multi-turn - the client carries state forward automatically:
await chat.send('What about Paris?');

// Errors surface as AgentError with an HTTP-ish status:
try {
  await remoteAgent({ url: '/api/nope' }).chat().send('hi');
} catch (err) {
  if (err instanceof AgentError) console.log(err.status);
}
```

## Client-managed state (no server store)

If the agent has **no `store`**, the server is fully stateless and the session
state blob (messages + custom + artifacts) is owned by the caller. The
`remoteAgent` client tracks it and round-trips it on every turn automatically —
no `SessionStore`, no snapshot ids to manage.

```ts
// Server: no `store` → stateless. Client owns the state blob.
export const weatherAgentStateless = ai.defineAgent({
  name: 'weatherAgentStateless',
  system: 'You are a helpful weather assistant. Use getWeather. Be concise.',
  tools: [getWeather],
});
```

```ts
// Client: reuse one `chat` and the state threads automatically.
import { remoteAgent, type AgentChat } from 'genkit/beta/client';

const agent = remoteAgent({ url: '/api/weatherAgentStateless' });
const chat: AgentChat = agent.chat();

await chat.send('Weather in London?');
await chat.send('Is it sunny in Tokyo?'); // remembers prior turns

// The full state blob is available after each turn:
const res = await chat.send('And Paris?');
console.log(JSON.stringify(res.raw.state, null, 2));
```

If you call the stateless agent directly (e.g. from a flow) instead of via
`remoteAgent`, you must round-trip the state yourself:

```ts
async function turn(state: unknown | undefined, text: string) {
  // Resume from prior state, or start fresh on the first turn.
  const chat = weatherAgentStateless.chat(state ? { state } : undefined);
  const res = await chat.send(text);
  // Return the updated state so the caller can pass it back next turn.
  return { state: res.raw.state, text: res.text };
}
```

Use client-managed state when you don't want to run server-side storage (e.g.
the client persists history itself). Use a [session store](agents-sessions.md)
when the server should own history, or when you need branching or background
execution. ([Interrupts](agents-human-in-the-loop.md) work either way.)
