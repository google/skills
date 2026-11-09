# Advanced Custom Agents — `defineCustomAgent` (Beta)

> **Beta / preview API.** `ai.defineCustomAgent` comes from `genkit/beta`. Read
> [agents.md](agents.md) and [agent state](agents-state.md) first.

`defineAgent` runs a single prompt + tool loop. When you need **full control of
the turn** — multiple sequential model calls, custom logic between them, manual
message/state management, or custom progress streaming — use
`ai.defineCustomAgent`. You provide the handler that runs the turn.

- [When to use it](#when-to-use-it): Lines 18-28
- [Signature](#signature): Lines 30-54
- [Example: multi-step research agent](#example-multi-step-research-agent): Lines 56-127
- [Custom status streaming](#custom-status-streaming): Lines 129-149

---

## When to use it

Reach for `defineCustomAgent` when a turn needs to:

- make **multiple model calls** with your own orchestration between them;
- run **multi-step workflows** (decompose → research → synthesize);
- **manually manage** messages and custom state;
- **stream custom status** updates to the client mid-turn.

Otherwise prefer `defineAgent` (simpler; custom state still works — see
[agent state](agents-state.md)).

## Signature

```ts
ai.defineCustomAgent(
  config: {
    name: string;
    description?: string;
    stateSchema?: z.ZodType<State>;
    store?: SessionStore<State>;
  },
  fn: async (sess, { sendChunk }) => { message: MessageData }
);
```

The handler receives a session runner `sess` and a turn context (`sendChunk` to
stream chunks to the client). It must return `{ message }` — the final model
message for the turn.

Key `sess` methods:

- `sess.run(async (input) => {...})` — runs the turn; adds `input.message` (the
  incoming user message) to the session before calling your callback, so
  `sess.getMessages()` includes it. `input.message?.content` holds the parts.
- `sess.getMessages()` — the full message history.
- `sess.addMessages([...])` — append messages (e.g. your final model response).

## Example: multi-step research agent

```ts
import { z } from 'genkit';
import { ai, liteModel } from './genkit.js';

interface ResearchState {
  status?: string; // live progress shown to the client
  subQuestions: string[];
  subAnswers: { question: string; answer: string }[];
}

export const researchAgent = ai.defineCustomAgent(
  { name: 'researchAgent' },
  async (sess, { sendChunk }) => {
    let lastMessage: any;
    const session = ai.currentSession<ResearchState>();

    await sess.run(async (input) => {
      const userText = input.message?.content[0]?.text ?? '';

      // Step 1: decompose (a fast model). Mutating custom state auto-emits a
      // `customPatch` chunk so the client's tracked state stays live.
      session.updateCustom((s) => ({
        ...s!,
        status: 'Decomposing question…',
      }));
      const decompose = await ai.generate({
        model: liteModel,
        prompt: `Break this into 2-3 sub-questions (JSON array): "${userText}"`,
        output: { format: 'json', schema: z.array(z.string()).min(2).max(3) },
      });
      const subQuestions = decompose.output ?? [userText];
      session.updateCustom((s) => ({ ...s!, subQuestions, subAnswers: [] }));

      // Step 2: research each sub-question (main model).
      const subAnswers: { question: string; answer: string }[] = [];
      for (let i = 0; i < subQuestions.length; i++) {
        session.updateCustom((s) => ({
          ...s!,
          status: `Researching (${i + 1}/${subQuestions.length})`,
        }));
        const research = await ai.generate({ prompt: subQuestions[i] });
        subAnswers.push({ question: subQuestions[i], answer: research.text });
      }
      session.updateCustom((s) => ({ ...s!, subAnswers }));

      // Step 3: synthesize and STREAM the final answer to the client.
      session.updateCustom((s) => ({ ...s!, status: 'Synthesizing…' }));
      const synthesis = ai.generateStream({
        prompt: `Synthesize a unified answer from:\n${JSON.stringify(subAnswers)}`,
      });
      for await (const chunk of synthesis.stream) {
        sendChunk({ modelChunk: chunk }); // stream model output to the client
      }
      const final = await synthesis.response;
      lastMessage = final.message;

      // Record the final response in the session history.
      if (lastMessage) sess.addMessages([lastMessage]);
      session.updateCustom((s) => ({ ...s!, status: 'Done' }));
    });

    return {
      message: lastMessage ?? {
        role: 'model' as const,
        content: [{ text: 'Research complete.' }],
      },
    };
  }
);
```

## Custom status streaming

Calling `session.updateCustom(...)` during the turn automatically emits a
`customPatch` chunk, so the `remoteAgent` client's tracked
[custom state](agents-state.md) (e.g. the `status` field) stays live
**mid-stream**
without any extra wiring. Stream model output separately with
`sendChunk({ modelChunk })`.

Seed and run a custom agent exactly like a regular one:

```ts
const chat = researchAgent.chat({
  state: { custom: { subQuestions: [], subAnswers: [] }, messages: [], artifacts: [] },
});
const turn = chat.sendStream('Impacts of electric vehicles?');
for await (const chunk of turn.stream) {
  /* chunk.text for model output; chat.state.status for live progress */
}
await turn.response;
```
