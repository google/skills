# Multi-Agent Orchestration / Sub-Agents (Beta)

> **Beta / preview API.** Sub-agent delegation uses the `agents()` middleware
> from `@genkit-ai/middleware`. Read [agents.md](agents.md) first.

A common pattern is an **orchestrator** agent that delegates tasks to
specialized **sub-agents** (e.g. a `researcher` and a `coder`). The `agents()`
middleware injects one delegation tool per sub-agent (`delegate_to_<name>`),
appends a `<sub-agents>` block to the orchestrator's system prompt, and — when
the model calls a delegation tool — runs the sub-agent and returns its response
as the tool result.

- [1. Define the sub-agents](#1-define-the-sub-agents): Lines 23-51
- [2. Wire up the orchestrator](#2-wire-up-the-orchestrator): Lines 53-95
- [agents() options](#agents-options): Lines 97-112
- [Background delegation (async: true)](#background-delegation-async-true): Lines 114-154
- [Continuing a task (continue_task)](#continuing-a-task-continue_task): Lines 156-174
- [Sharing artifacts between agents](#sharing-artifacts-between-agents): Lines 176-187
- [Other middleware](#other-middleware): Lines 189-214

---

## 1. Define the sub-agents

Give each sub-agent a `description` — it's auto-discovered and shown to the
orchestrator so the model knows when to delegate.

```ts
import { artifacts, retry } from '@genkit-ai/middleware';
import { ai, defaultModel } from './genkit.js';

export const researcher = ai.defineAgent({
  name: 'researcher',
  description:
    'A thorough research assistant that searches the web and provides ' +
    'well-sourced answers.',
  model: defaultModel,
  system:
    'You are a thorough research assistant. Save findings with write_artifact.',
  maxTurns: 10,
  use: [retry(), artifacts()],
});

export const coder = ai.defineAgent({
  name: 'coder',
  description: 'An expert programmer that writes clean, well-commented code.',
  system: 'You are an expert programmer. Save code with write_artifact.',
  maxTurns: 10,
  use: [artifacts(), retry()],
});
```

## 2. Wire up the orchestrator

Add `agents()` to the orchestrator's `use: [...]`. Each entry is a name string
(description auto-discovered) or `{ name, description }` to override.

```ts
import { agents, artifacts, retry } from '@genkit-ai/middleware';
import { ai } from './genkit.js';

export const orchestratorAgent = ai.defineAgent({
  name: 'orchestratorAgent',
  system: `You are a helpful project assistant. Analyze the request and
delegate to the appropriate sub-agent. If it needs research AND code, call them
sequentially, then synthesize a final answer.`,
  use: [
    agents({
      agents: [
        'researcher', // auto-discovered description
        {
          name: 'coder',
          description: 'Writes, debugs, and explains code. Use for programming.',
        },
      ],
      maxDelegations: 5, // guard rail against runaway delegation loops
      historyLength: 4, // forward the last N user/model messages as context
      artifactStrategy: 'session', // see "Sharing artifacts" below
    }),
    artifacts({ readonly: true }), // read sub-agent artifacts via read_artifact
    retry(),
  ],
});
```

Run it like any other agent:

```ts
const chat = orchestratorAgent.chat();
const turn = chat.sendStream(
  'Research the best sorting algorithms, then write a TypeScript quicksort.'
);
for await (const chunk of turn.stream) process.stdout.write(chunk.text ?? '');
const res = await turn.response;
```

## `agents()` options

- `agents` (required): array of sub-agent refs. A `string` (name, description
  auto-discovered from the registry) or `{ name, description? }` (explicit
  override).
- `toolPrefix`: prefix for generated tool names. Default `"delegate_to"` →
  `delegate_to_<agent>`. Empty string uses bare agent names.
- `maxDelegations`: max delegations per `generate` call. Prevents runaway loops.
- `historyLength`: number of recent user/model messages forwarded to sub-agents
  as context. `0`/omitted sends only the task description. (Only client-managed
  sub-agents — no `store` — accept ad-hoc seeded history; server-managed
  sub-agents skip it and just receive the task.)
- `artifactStrategy`: `'inline'` (default) or `'session'` — see below.
- `async`: enables background delegation (see below).
- `maxWaitSeconds`: caps one `wait_for_background_tasks` call, whatever timeout
  the model asks for.

## Background delegation (`async: true`)

> Requires `genkit >= 1.43.0`.

By default a delegation blocks the orchestrator's turn. With `async: true`,
each delegation tool accepts `background: true` and returns a task ID
(`<agent>:<snapshotId>`) immediately; the orchestrator keeps working and
collects results later. Three tools are added:

- `check_background_tasks({ taskIds })`: current status, no waiting.
- `wait_for_background_tasks({ taskIds, timeoutSeconds?, waitFor? })`: blocks
  until they settle (`waitFor: "first"` returns on the first one).
- `abort_background_tasks({ taskIds })`: stops tasks no longer needed.

**The sub-agent needs a `store`.** Background work is tracked by a pending
snapshot; a store-less sub-agent can only be delegated to synchronously.

```ts
import { InMemorySessionStore } from 'genkit/beta';

const logAnalyst = ai.defineAgent({
  name: 'logAnalyst',
  description: 'Reads service logs and reports what they show.',
  store: new InMemorySessionStore(), // required for background delegation
  tools: [readLogs],
});

const commander = ai.defineAgent({
  name: 'commander',
  system:
    'Start investigations IN THE BACKGROUND ("background": true), post a status ' +
    'update while they run, then collect them with wait_for_background_tasks.',
  tools: [postStatus],
  maxTurns: 20, // background work adds tool rounds; raise the ceiling
  use: [agents({ agents: ['logAnalyst', 'deployHistorian'], async: true })],
});
```

Tell the orchestrator in its system prompt to set `"background": true`; the
model decides per call. History is never forwarded to a store-backed sub-agent,
so task descriptions must stand alone.

## Continuing a task (`continue_task`)

> Requires `genkit >= 1.43.0`.

A delegation to a store-backed sub-agent returns `{ response, taskId, status }`
even when synchronous. The
`continue_task({ taskId, instructions?, background? })`
tool picks it up:

- `failed` / `aborted`: retries from the last saved progress (finished tool
  calls are not repeated); `instructions` steer the retry.
- `completed`: follow-up `instructions` in the sub-agent's own session.
- `expired`: fences the dead worker, then continues.
- `pending` / `aborting`: refused; use the wait/check tool.

Task IDs are scoped to the conversation: the tools only accept IDs this
conversation's delegations returned. Two `agents()` instances in one call need
distinct `toolPrefix` values, or both register `continue_task` and the call is
rejected.

## Sharing artifacts between agents

Sub-agents can produce [artifacts](agents-artifacts.md). `artifactStrategy`
controls how they reach the orchestrator:

- `'inline'` (default): artifact content is included in the delegation tool
  result (so the model sees it directly) **and** merged into the parent session.
- `'session'`: artifacts are merged into the parent session only; the tool
  result lists artifact names, not content. Pair with the `artifacts()`
  middleware so the orchestrator can `read_artifact` on demand (the pattern
  shown above). Merged artifacts are namespaced by an invocation ID
  (`<agentName>_<rand>/<name>`).

## Other middleware

`@genkit-ai/middleware` also exports `retry`, `fallback`, `filesystem`,
`skills`, `toolApproval`, and `contextCompression`. They attach the same way via
`use: [...]` on an
agent (or on `ai.generate`) — see [using middleware](middleware.md). `retry()`
is commonly paired with delegation:

```ts
import { retry } from '@genkit-ai/middleware';

retry({
  maxRetries: 3, // default 3
  initialDelayMs: 1000, // default 1000
  maxDelayMs: 60000, // default 60000
  backoffFactor: 2, // default 2 (exponential backoff)
  // statuses defaults to UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED,
  // ABORTED, INTERNAL
});
```

> Note: if a sub-agent triggers an [interrupt](agents-human-in-the-loop.md) or
> fails, it is reported back to the orchestrator as a normal tool response (not
> propagated as a resumable interrupt or thrown). Tell the orchestrator how to
> handle failures, e.g. with `continue_task`. Interactive, stateful sub-agent
> interrupts are a future feature, so delegate self-contained tasks.
