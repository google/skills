# Agent Human-in-the-Loop / Interrupts (Beta)

> **Beta / preview API.** Read [agents.md](agents.md) first.

An **interrupt** pauses an agent mid-turn and hands control back to your code
(or
a human) — e.g. to approve a sensitive action, collect missing input, or confirm
a plan. Internally it's a **tool call used as control flow**: the interrupt tool
never executes on the server; it exists only to pause the turn. You then
**resume** from the exact point it paused.

Interrupts are **orthogonal to persistence** — they work the same whether the
agent uses a [session store](agents-sessions.md) or
[client-managed state](agents.md#client-managed-state-no-server-store). The
paused turn just needs to be carried back into the resume call: with a store the
snapshot does it; without one the client round-trips the state blob (the
`remoteAgent` client handles this for you).

Flow: `chat.send(...)` → response has `res.interrupts` → collect human input →
`chat.resume({ respond: [...] })`.

- [Define an interrupt](#define-an-interrupt): Lines 29-73
- [Detect and resume (server-side)](#detect-and-resume-server-side): Lines 75-126
- [Client-side (browser) interrupts](#client-side-browser-interrupts): Lines 128-168
- [Notes and gotchas](#notes-and-gotchas): Lines 170-188

---

## Define an interrupt

Define it like a tool (with `inputSchema`/`outputSchema`) and add it to the
agent's `tools`. No store is required; this example uses one so the multi-turn
conversation also persists server-side.

```ts
import { z } from 'genkit';
import { InMemorySessionStore } from 'genkit/beta';
import { ai } from './genkit.js';

export const userApproval = ai.defineInterrupt({
  name: 'userApproval',
  description: 'Ask the user for approval before a sensitive action.',
  // What the model passes in when it pauses (shown to the human):
  inputSchema: z.object({ action: z.string(), details: z.string() }),
  // What the human/your code returns to resume:
  outputSchema: z.object({
    approved: z.boolean(),
    feedback: z.string().optional(),
  }),
});

export const transferMoney = ai.defineTool(
  {
    name: 'transferMoney',
    description: 'Transfer money to a specified account.',
    inputSchema: z.object({ amount: z.number(), toAccount: z.string() }),
    outputSchema: z.object({ success: z.boolean(), transactionId: z.string() }),
  },
  async ({ amount, toAccount }) => ({
    success: true,
    transactionId: `txn-${Date.now()}`,
  })
);

export const bankingAgent = ai.defineAgent({
  name: 'bankingAgent',
  system:
    'You are a banking assistant. ALWAYS use the userApproval interrupt to ' +
    'confirm before executing transferMoney.',
  tools: [userApproval, transferMoney],
  store: new InMemorySessionStore(),
});
```

## Detect and resume (server-side)

`res.interrupts` is non-empty when the agent paused. Each entry exposes:

- `.name` — the interrupt's name.
- `.input` — the data the model passed in (typed by the interrupt's
  `inputSchema`).
- `.respond(output)` — **builder** returning a `toolResponse` part to resume
  with
  (provides the tool's output without executing it). Does **not** send.
- `.restart()` — **builder** re-issuing the original tool request (use to retry
  /
  let the tool actually run). Does **not** send.

Resume the **same** chat with `chat.resume(...)` (or `chat.resumeStream(...)`),
which is sugar for `send({ resume })`:

```ts
const chat = bankingAgent.chat();
let res = await chat.send('Transfer $500 to my savings account.');

const approval = res.interrupts.find((i) => i.name === 'userApproval');
if (approval) {
  console.log(approval.input); // { action, details } - show this to the human

  // Collect the human decision, then resume with the interrupt's output:
  res = await chat.resume({
    respond: [approval.respond({ approved: true, feedback: 'Looks good' })],
  });
}
console.log(res.text); // final confirmation
```

Streaming variant:

```ts
const turn = chat.resumeStream({
  respond: [approval.respond({ approved: true })],
});
for await (const chunk of turn.stream) process.stdout.write(chunk.text ?? '');
const res = await turn.response;
```

You can resume multiple interrupts at once by passing several builders, and mix
`respond` (supply output) with `restart` (re-run the tool):

```ts
await chat.resume({
  respond: [a.respond({ approved: true })],
  restart: [b.restart()],
});
```

## Client-side (browser) interrupts

The same pattern works over HTTP with `remoteAgent`. Types come from
`genkit/beta/client`. The client tracks the snapshot, so resuming the same
`chat`
continues exactly where it paused.

```ts
import {
  remoteAgent,
  type AgentChat,
  type AgentInterrupt,
  type AgentResponse,
} from 'genkit/beta/client';

const agent = remoteAgent({ url: '/api/bankingAgent' });
const chat: AgentChat = agent.chat();

// 1. Send and detect the pause.
const res: AgentResponse = await chat.send('Transfer $500 to savings.');
const pending: AgentInterrupt | undefined = res.interrupts.find(
  (i) => i.name === 'userApproval'
);

if (pending) {
  // pending.input → { action, details }; render an approval dialog.

  // 2. After the human approves/denies, resume the SAME chat.
  const respond = pending.respond({ approved: true, feedback: 'ok' });
  const turn = chat.resumeStream({ respond: [respond] });
  for await (const chunk of turn.stream) {
    /* render chunk.text */
  }
  const final = await turn.response;
  // If final.interrupts is non-empty, the agent paused again - repeat.
}
```

> UX tip: don't render a model message bubble for an interrupted turn
> (`res.interrupts.length > 0`); show the approval UI from `interrupt.input`
> instead, then render the model's reply after resuming.

## Notes and gotchas

- **No store required.** Interrupts work with either a
  [session store](agents-sessions.md)
  or [client-managed state](agents.md#client-managed-state-no-server-store) —
  persistence is orthogonal. Just resume on the same `chat` (or, for raw calls,
  carry the returned state/snapshot back into the resume).
- **`respond`/`restart` are builders.** They return parts for the `resume`
  payload; they do not send. You still call `chat.resume(...)`.
- **Resume validation.** The server validates every `respond`/`restart` entry
  against the conversation history (name/ref must match; `restart` input must be
  unchanged). A mismatch is rejected — always build entries from the interrupt
  objects in the response, not hand-rolled parts.
- **Resumable snapshots.** `completed` snapshots are resumable, and since
  `genkit` 1.43.0 so are `failed` and `aborted` ones (they hold the conversation
  up to the last completed tool round; `chat.send({})` retries). `pending` and
  `aborting` snapshots are rejected until they settle.
- **Re-pausing.** After resuming, the new response may interrupt again; loop
  until `res.interrupts` is empty.
