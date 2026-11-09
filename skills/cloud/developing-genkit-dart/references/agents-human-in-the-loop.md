# Agent Human-in-the-Loop / Interrupts

> Read [agents.md](agents.md) first.

An **interrupt** pauses an agent mid-turn and hands control back to your code
(or
a human) — e.g. to approve a sensitive action, collect missing input, or confirm
a plan. Internally it's a **tool call used as control flow**: the interrupt tool
never runs to completion on the server; it pauses the turn. You then **resume**
from the exact point it paused.

> Two ways to define an interrupt:
>
> - `ai.defineInterrupt(...)`: an interrupt-only tool that always pauses and
>   never runs logic. `outputSchema` describes what the caller supplies on
>   resume.
> - A normal `ai.defineTool` whose body returns `.interrupt(data)`: pauses
>   conditionally (e.g. only for large transfers) or after some work.
>
> There is no `ctx.interrupt(...)`; return `.interrupt(...)` from the tool.

```dart
final askUser = ai.defineInterrupt(
  name: 'askUser',
  description: 'Ask the user a clarifying question.',
  inputSchema: .string(), // the question
  outputSchema: .string(), // the answer, supplied on resume
);
```

Interrupts are **orthogonal to persistence** — they work the same whether the
agent uses a [session store](agents-sessions.md) or
[client-managed state](agents.md#client-managed-state-no-server-store). Just
resume on the same `chat` (or, for raw calls, carry the returned state/snapshot
back into the resume).

Flow: `chat.send(text: ...)` → response has `res.interrupts` → collect human
input
→ `chat.resume(respond: [...])`.

- [Define an interrupt (a tool that interrupts)](#define-an-interrupt-a-tool-that-interrupts): Lines 49-113
- [Detect and resume (server-side)](#detect-and-resume-server-side): Lines 115-172
- [Client-side (browser) interrupts](#client-side-browser-interrupts): Lines 174-205
- [Interrupts with tool-approval middleware](#interrupts-with-tool-approval-middleware): Lines 207-232
- [Notes and gotchas](#notes-and-gotchas): Lines 234-248

---

## Define an interrupt (a tool that interrupts)

The example below uses tools that return `.interrupt(...)`, which pauses the
turn; its argument is the data shown to the human. Add interrupts (either kind)
to the agent's `tools`.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore
import 'package:schemantic/schemantic.dart';

import 'genkit.dart';

part 'banking_agent.g.dart';

@Schema()
abstract class $UserApprovalInput {
  @Field(description: 'The action to be approved')
  String get action;
  @Field(description: 'Details about the action')
  String get details;
}

@Schema()
abstract class $TransferMoneyInput {
  double get amount;
  String get toAccount;
}

@Schema()
abstract class $TransferMoneyOutput {
  bool get success;
  String get transactionId;
}

/// Interrupt: always pauses. The caller provides `{ approved, feedback }` on
/// resume. No `outputSchema` - the output comes from the resume call.
final userApproval = ai.defineTool(
  name: 'userApproval',
  description: 'Ask the user for approval before a sensitive action.',
  inputSchema: UserApprovalInput.$schema,
  fn: (input, ctx) async => .interrupt(),
);

/// Executes the transfer. Only reached after the user approves.
final transferMoney = ai.defineTool(
  name: 'transferMoney',
  description: 'Transfer money to a specified account.',
  inputSchema: TransferMoneyInput.$schema,
  outputSchema: TransferMoneyOutput.$schema,
  fn: (input, _) async => .response(TransferMoneyOutput(
    success: true,
    transactionId: 'txn-${DateTime.now().millisecondsSinceEpoch}',
  )),
);

final bankingAgent = ai.defineAgent(
  name: 'bankingAgent',
  system: 'You are a banking assistant. ALWAYS use the userApproval interrupt '
      'to confirm before executing transferMoney.',
  tools: [userApproval, transferMoney],
  use: [retry()],
  store: InMemorySessionStore(),
);
```

## Detect and resume (server-side)

`res.interrupts` is non-empty when the agent paused. Each `AgentInterrupt`
exposes:

- `.name` — the interrupt's name.
- `.input` — the data the model passed in.
- `.respond(output)` — **builder** returning a resume entry that supplies the
  tool's output (without executing it). Does **not** send.
- `.restart([payload])` — **builder** re-issuing the original tool request
  (retry
  / let the tool actually run). Pass an optional `Map` payload; it is nested
  under `metadata.resumed` and read back tool-side via `ctx.resumed`. Does
  **not** send.

Resume the **same** chat with `chat.resume(...)` / `chat.resumeStream(...)`,
passing `respond` / `restart` entries directly:

```dart
final chat = bankingAgent.chat();
var res = await chat.send(text: 'Transfer \$500 to my savings account.');

final approval =
    res.interrupts.where((i) => i.name == 'userApproval').firstOrNull;
if (approval != null) {
  print(approval.input); // { action, details } - show this to the human

  // Collect the human decision, then resume with the interrupt's output:
  res = await chat.resume(
    respond: [
      approval.respond({'approved': true, 'feedback': 'Looks good'}),
    ],
  );
}
print(res.text); // final confirmation
```

Streaming variant:

```dart
final turn = chat.resumeStream(
  respond: [approval.respond({'approved': true})],
);
await for (final chunk in turn.stream) {
  stdout.write(chunk.text);
}
final res = await turn.response;
```

You can resume multiple interrupts at once by passing several builders, and mix
`respond` (supply output) with `restart` (re-run the tool):

```dart
await chat.resume(
  respond: [a.respond({'approved': true})],
  restart: [b.restart()],
);
```

## Client-side (browser) interrupts

The same pattern works over HTTP with `remoteAgent` from
`package:genkit/client.dart`. The client tracks the snapshot, so resuming the
same `chat` continues exactly where it paused.

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, AgentInterrupt

final agent = remoteAgent(url: '/api/bankingAgent');
final chat = agent.chat();

// 1. Send and detect the pause.
final res = await chat.send(text: 'Transfer \$500 to savings.');
final pending =
    res.interrupts.where((i) => i.name == 'userApproval').firstOrNull;

if (pending != null) {
  // pending.input → { action, details }; render an approval dialog.

  // 2. After the human approves/denies, resume the SAME chat.
  final turn = chat.resumeStream(
    respond: [pending.respond({'approved': true, 'feedback': 'ok'})],
  );
  await for (final chunk in turn.stream) {
    /* render chunk.text */
  }
  final finalRes = await turn.response;
  // If finalRes.interrupts is non-empty, the agent paused again - repeat.
}
```

## Interrupts with tool-approval middleware

The [`toolApproval`](genkit_middleware.md) middleware turns selected tools into
approval interrupts without any custom interrupt code. The middleware gates each
tool call itself: a tool is allowed to run only if it is in the `approved` list
or its `resumed` payload carries `{ 'tool-approved': true }`. To let an approved
tool through on resume, **restart** the paused interrupt with that payload — the
`.restart(...)` builder nests it under `metadata.resumed`, exactly what the
middleware reads:

```dart
// `interrupt` is the paused AgentInterrupt from `res.interrupts`.
// Pass this restart entry back when resuming the chat:
await chat.resume(
  restart: [interrupt.restart({'tool-approved': true})],
);
```

If instead you write your own `.interrupt(...)` gate inside a tool (as in the
`coding_agent` sample), you inspect the resume payload yourself via the
`ctx.resumed` getter:

```dart
final resumed = ctx.resumed; // the payload passed to `.restart(...)`
final isApproved = resumed is Map && resumed['tool-approved'] == true;
```

## Notes and gotchas

- **No store required.** Interrupts work with either a
  [session store](agents-sessions.md) or
  [client-managed state](agents.md#client-managed-state-no-server-store).
- **`respond`/`restart` are builders.** They return resume entries; they do not
  send. You still call `chat.resume(...)`.
- **Resume validation.** The server validates each `respond`/`restart` entry
  against the conversation history — always build entries from the interrupt
  objects in the response, not hand-rolled parts.
- **Re-pausing.** After resuming, the new response may interrupt again; loop
  until `res.interrupts` is empty.
- **UX tip:** don't render a model message bubble for an interrupted turn; show
  the approval UI from `interrupt.input` instead, then render the model's reply
  after resuming.
