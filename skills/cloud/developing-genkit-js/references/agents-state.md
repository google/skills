# Working with Agent State (Beta)

> **Beta / preview API.** Read [agents.md](agents.md) first.

Beyond message history, an agent session can hold typed **custom state** — your
own structured data (a task list, a workflow status, counters, etc.). Tools read
and mutate it during a turn, and it is automatically synced to the
[`remoteAgent`](agents.md#consume-an-agent-from-a-client-remoteagent) client.

- [Declare the state shape](#declare-the-state-shape): Lines 17-45
- [Read and mutate state inside tools](#read-and-mutate-state-inside-tools): Lines 47-83
- [Seed and read state (server-side)](#seed-and-read-state-server-side): Lines 85-102
- [Auto-sync to the remoteAgent client](#auto-sync-to-the-remoteagent-client): Lines 104-140

---

## Declare the state shape

Pass a `stateSchema` (Zod) to `defineAgent`. `State` is inferred from it and
validated when a snapshot is loaded.

```ts
import { z } from 'genkit';
import { ai } from './genkit.js';

const TaskItem = z.object({
  id: z.number(),
  title: z.string(),
  done: z.boolean(),
});

const TaskState = z.object({
  tasks: z.array(TaskItem),
  nextId: z.number(),
});

export const taskAgent = ai.defineAgent({
  name: 'taskAgent',
  stateSchema: TaskState,
  system: 'You manage the user\'s task list. Use the tools to modify it.',
  tools: [
    /* addTask, toggleTask, removeTask - below */
  ],
});
```

## Read and mutate state inside tools

Tools call `ai.currentSession<S>()` to access the live session, then
`session.getCustom()` / `session.updateCustom(mutator)`. `updateCustom` takes
`(custom?: S) => S` and returns the new state.

```ts
type TaskState = z.infer<typeof TaskState>;

const addTask = ai.defineTool(
  {
    name: 'addTask',
    description: 'Add a new task. Returns the created task.',
    inputSchema: z.object({ title: z.string() }),
    outputSchema: z.object({
      id: z.number(),
      title: z.string(),
      done: z.boolean(),
    }),
  },
  async (input) => {
    const session = ai.currentSession<TaskState>();
    let created!: { id: number; title: string; done: boolean };
    session.updateCustom((state) => {
      const s = state ?? { tasks: [], nextId: 1 };
      created = { id: s.nextId, title: input.title, done: false };
      s.tasks.push(created);
      s.nextId++;
      return s;
    });
    return created;
  }
);
```

`ai.currentSession()` throws if called outside an active session (e.g. a tool
invoked without a running agent turn), so only use it inside agent tools.

## Seed and read state (server-side)

Seed initial custom state when opening a chat. The `state` argument is a
`SessionState<S>`: custom data goes under `.custom` (alongside `messages` and
`artifacts`).

```ts
const chat = taskAgent.chat({
  state: {
    custom: { tasks: [], nextId: 1 },
    messages: [],
    artifacts: [],
  },
});

const res = await chat.send('Add a task: buy groceries');
console.log(res.state); // res.state returns the custom state directly
```

## Auto-sync to the `remoteAgent` client

When you talk to the agent over HTTP, the `remoteAgent` client tracks custom
state for you. Parameterize the client with your state type, seed it the same
way (`state.custom`), and after a turn read it off `chat.state`.

**Important:** on the client, custom fields are **flattened directly onto
`chat.state`** (e.g. `chat.state.tasks`) — not under `chat.state.custom`.

```ts
import { remoteAgent, type AgentChat } from 'genkit/beta/client';

interface TaskState {
  tasks: { id: number; title: string; done: boolean }[];
  nextId: number;
}

const agent = remoteAgent<TaskState>({ url: '/api/taskAgent' });
const chat: AgentChat<TaskState> = agent.chat({
  state: { custom: { tasks: [], nextId: 1 }, messages: [], artifacts: [] },
});

const turn = chat.sendStream('Add buy groceries, then mark it done');
for await (const chunk of turn.stream) {
  /* render chunk.text */
}
await turn.response;

// Custom state is flattened onto chat.state:
console.log(chat.state?.tasks);
```

There is **no `onStateChange` subscription** — state updates ride on the
streamed chunks. Read the authoritative state from `chat.state` after
`await turn.response`. (For live mid-stream status updates from a custom agent,
see [advanced custom agents](agents-custom.md), which emit `customPatch` chunks
as state changes.)
