# Working with Agent State (Experimental)

> **Experimental / preview API.** Read [agents.md](agents.md) first.

Beyond message history, an agent session can hold typed **custom state** — your
own structured data (a task list, a workflow status, counters, etc.). Tools read
and mutate it during a turn, and every mutation is streamed to a connected
client
as a JSON Patch so the client's view stays live.

- [Declare the state shape](#declare-the-state-shape): Lines 20-46
- [Read and mutate state inside tools](#read-and-mutate-state-inside-tools): Lines 48-91
- [Seed and read state](#seed-and-read-state): Lines 93-110
- [Live state on a connection](#live-state-on-a-connection): Lines 112-141
- [Prompt templating with state](#prompt-templating-with-state): Lines 143-151
- [Custom status streaming from a custom agent](#custom-status-streaming-from-a-custom-agent): Lines 153-158

---

## Declare the state shape

The custom-state type is the `State` type parameter of the agent (and its
store).
It lives under `Custom` of `aix.SessionState[State]`.

```go
type TaskItem struct {
	ID    int    `json:"id"`
	Title string `json:"title"`
	Done  bool   `json:"done"`
}

type TaskState struct {
	Tasks  []TaskItem `json:"tasks"`
	NextID int        `json:"nextId"`
}

taskAgent := genkitx.DefineAgent(g, "taskAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You manage the user's task list. Use the tools to modify it."),
		ai.WithTools(addTask), // defined below
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[TaskState]()),
)
```

## Read and mutate state inside tools

Inside a tool, get the live session from context with
`aix.SessionFromContext[State](ctx)`, then read with `session.Custom()` and
mutate with `session.UpdateCustom(fn)`. `UpdateCustom` takes
`func(State) State` and writes the result back atomically. When the session is
driven by an agent invocation, the mutation is automatically streamed to the
client as an `AgentStreamChunk.CustomPatch`.

```go
type AddTaskInput struct {
	Title string `json:"title"`
}

addTask := genkit.DefineTool(g, "addTask",
	"Add a new task. Returns the created task.",
	func(ctx *ai.ToolContext, in AddTaskInput) (TaskItem, error) {
		session := aix.SessionFromContext[TaskState](ctx.Context)
		if session == nil {
			return TaskItem{}, fmt.Errorf("addTask must run inside an agent session")
		}
		var created TaskItem
		session.UpdateCustom(func(s TaskState) TaskState {
			if s.NextID == 0 {
				s.NextID = 1
			}
			created = TaskItem{ID: s.NextID, Title: in.Title, Done: false}
			s.Tasks = append(s.Tasks, created)
			s.NextID++
			return s
		})
		return created, nil
	},
)
```

`aix.SessionFromContext[State]` returns `nil` outside an active session (or when
the `State` type does not match), so guard against it. Note the tool's context
is
`ctx.Context` (the `*ai.ToolContext` embeds the standard `context.Context`).

> Do not call other `Session` methods (or send on a `Responder`) from inside the
> `UpdateCustom` callback: it runs while the session lock is held and would
> deadlock.

## Seed and read state

Seed initial custom state with `aix.WithState` on the first turn. For a
server-managed agent, later turns resume with `aix.WithSessionID` and the state
is loaded from the snapshot.

```go
out, _ := taskAgent.Run(ctx,
	&aix.AgentInput{Message: ai.NewUserTextMessage("Add a task: buy groceries")},
	aix.WithState(&aix.SessionState[TaskState]{
		Custom: TaskState{Tasks: nil, NextID: 1},
	}),
)
// For a client-managed agent, the final state is on out.State:
if out.State != nil {
	fmt.Printf("%+v\n", out.State.Custom)
}
```

## Live state on a connection

A connection tracks custom state as it streams: each `Receive()`d chunk carries
a
`CustomPatch` (an RFC 6902 JSON Patch delta), which the connection applies to an
internal copy. Read it any time with `conn.Custom()`.

```go
conn, _ := taskAgent.Connect(ctx,
	aix.WithState(&aix.SessionState[TaskState]{Custom: TaskState{NextID: 1}}),
)
_ = conn.SendText("Add buy groceries, then mark it done")
for chunk, err := range conn.Receive() {
	if err != nil {
		log.Fatal(err)
	}
	if len(chunk.CustomPatch) > 0 {
		cur, _ := conn.Custom() // TaskState reflecting deltas so far
		fmt.Printf("live: %+v\n", cur)
	}
	if chunk.TurnEnd != nil {
		break
	}
}
```

The first `CustomPatch` of each turn is a whole-document replace (re-basing the
client); later patches are incremental diffs. The authoritative final state is
on
`out.State` (client-managed) or the turn-end snapshot (server-managed).

## Prompt templating with state

Inside a prompt template, the session's custom state is available as
`{{@state}}`,
evaluated fresh at render time so the template always sees the latest values.

```go
ai.WithSystem("The user's current task list: {{json @state.tasks}}. Help them manage it."),
```

## Custom status streaming from a custom agent

For live mid-turn progress (a `status` field that updates as a long turn runs),
mutate custom state from a [custom agent](agents-custom.md): every
`UpdateCustom` emits a `CustomPatch` chunk automatically, so the connection's
`Custom()` stays live without extra wiring.
