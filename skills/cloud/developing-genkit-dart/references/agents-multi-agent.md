# Multi-Agent Orchestration / Sub-Agents

> Sub-agent delegation uses the `agents()` middleware from
> `package:genkit_middleware/agents.dart`. Read [agents.md](agents.md) first.

A common pattern is an **orchestrator** agent that delegates tasks to
specialized **sub-agents** (e.g. a `researcher` and a `coder`). The `agents()`
middleware injects one delegation tool per sub-agent (`delegate_to_<name>`),
appends a `<sub-agents>` block to the orchestrator's system prompt, and — when
the model calls a delegation tool — runs the sub-agent and returns its response
as the tool result.

To make the middleware available, register `AgentsPlugin()` on the `Genkit`
instance:

```dart
import 'package:genkit_middleware/agents.dart';

final ai = Genkit(plugins: [googleAI(), AgentsPlugin()]); // retry() is built in
```

- [1. Define the sub-agents](#1-define-the-sub-agents): Lines 31-58
- [2. Wire up the orchestrator](#2-wire-up-the-orchestrator): Lines 60-102
- [agents() options](#agents-options): Lines 104-114
- [Background (async) delegation](#background-async-delegation): Lines 116-144
- [Sharing artifacts between agents](#sharing-artifacts-between-agents): Lines 146-156
- [Other middleware](#other-middleware): Lines 158-168

---

## 1. Define the sub-agents

Give each sub-agent a `description` — it's auto-discovered from registry
metadata
and shown to the orchestrator so the model knows when to delegate.

```dart
import 'package:genkit/experimental.dart'; // defineAgent

import 'genkit.dart';

final researcher = ai.defineAgent(
  name: 'researcher',
  description:
      'A thorough research assistant that provides well-sourced answers.',
  system: 'You are a thorough research assistant. When asked a question, '
      'provide a clear, well-structured, and well-sourced answer.',
  maxTurns: 10,
);

final coder = ai.defineAgent(
  name: 'coder',
  description: 'Writes, debugs, and explains code. Use for any programming tasks.',
  system: 'You are an expert programmer. Provide clean, well-commented code '
      'with explanations. Use Dart by default unless asked otherwise.',
  maxTurns: 10,
);
```

## 2. Wire up the orchestrator

Add `agents()` to the orchestrator's `use: [...]`. Pass the sub-agent **names**;
their descriptions are auto-discovered from the registry.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore
import 'package:genkit_middleware/agents.dart';

import 'genkit.dart';

final orchestratorAgent = ai.defineAgent(
  name: 'orchestratorAgent',
  system: '''
You are a helpful project assistant.

Analyze the user's request and delegate to the appropriate sub-agent.
If the request requires both research AND code, call them sequentially.
After receiving sub-agent responses, synthesize a final answer for the user.''',
  use: [
    agents(
      agents: ['researcher', 'coder'],
      maxDelegations: 5, // guard rail against runaway delegation loops
      historyLength: 4, // forward the last N user/model messages as context
    ),
  ],
  store: InMemorySessionStore(),
);
```

Run it like any other agent:

```dart
final chat = orchestratorAgent.chat();
final turn = chat.sendStream(
  text: 'Research the best sorting algorithms, then write a Dart quicksort.',
);
await for (final chunk in turn.stream) {
  stdout.write(chunk.text);
}
final res = await turn.response;
```

## `agents()` options

- `agents` (required): `List<String>` of sub-agent names. Each description is
  auto-discovered from the registry.
- `toolPrefix`: prefix for generated tool names. Defaults to `delegate_to` →
  `delegate_to_<agent>`.
- `maxDelegations`: max delegations per `generate` call. Prevents runaway loops.
- `historyLength`: number of recent user/model messages forwarded to sub-agents
  as context. `0`/omitted sends only the task description.
- `artifactStrategy`: `'inline'` (default) or `'session'` — see below.
- `async`: enable background delegation — see below.

## Background (async) delegation

Set `async: true` to let the orchestrator run sub-agents in the background. Each
delegation tool then accepts a `background` flag that starts the sub-agent and
returns a `taskId` immediately, and the middleware adds
`check_background_tasks`, `wait_for_background_tasks`, and
`abort_background_tasks` tools so the model can launch several tasks in parallel
and collect them later. A `continue_task` tool lets the model retry a
failed/aborted task or follow up on a completed one.

```dart
final orchestratorAgent = ai.defineAgent(
  name: 'orchestratorAgent',
  system: 'Delegate independent tasks in the background, then collect the '
      'results before answering.',
  use: [
    agents(
      agents: ['researcher', 'coder'],
      async: true, // adds background delegation + the background-task tools
    ),
  ],
  store: InMemorySessionStore(),
);
```

> Background delegation requires **server-managed sub-agents** — each sub-agent
> needs a session `store` that supports detach (see
> [background agents](agents-background.md)). A sub-agent without a store cannot
> be run in the background.

## Sharing artifacts between agents

Sub-agents can produce [artifacts](agents-artifacts.md). `artifactStrategy`
controls how they reach the orchestrator:

- `'inline'` (default): artifact content is included in the delegation tool
  result (so the model sees it directly) **and** merged into the parent session.
- `'session'`: artifacts are merged into the parent session only; the tool
  result
  lists artifact names, not content. Merged artifacts are namespaced by an
  invocation id (`<invocationId>/<name>`).

## Other middleware

`package:genkit_middleware` also exports `filesystem`, `skills`, and
`toolApproval`; `retry` ships in core `package:genkit`. They attach the same way
via `use: [...]` on an agent (or on `ai.generate`) — see
[using middleware](genkit_middleware.md). `retry()` is commonly paired with
delegation.

> Note: if a sub-agent triggers an [interrupt](agents-human-in-the-loop.md), it
> is reported back to the orchestrator as a normal tool response (not propagated
> as a resumable interrupt). Delegate self-contained tasks.
