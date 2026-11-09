# Agents (Experimental)

> **Experimental / preview API.** Agents live in the `genkit/exp` and `ai/exp`
> packages and are gated behind an opt-in. Initialize Genkit with
> `genkit.WithExperimental()` or the constructors panic. Import paths and
> signatures may change in any minor release.

An **agent** is a persistent, multi-turn conversation primitive built on top of
prompts + tools. Compared to a bare `genkit.Generate` loop, an agent adds:

- **Sessions**: multi-turn history tracked as immutable **snapshots**.
- **State**: typed session state (messages + custom data + artifacts).
- **Interrupts**: human-in-the-loop pause/resume.
- **Branching**: fork a conversation from any snapshot.
- **Detaching**: run a turn in the background and poll for the result.

Read the file for the level you need:

- This file: defining an agent, running it, serving it, and **client-managed
  state** (no store).
- [Sessions & persistence](agents-sessions.md): `SessionStore`,
  `localstore.NewInMemorySessionStore`, `localstore.NewFileSessionStore`.
- [Human-in-the-loop / interrupts](agents-human-in-the-loop.md): pausing for
  approval/input and resuming.
- [Branching](agents-branching.md): forking a conversation from a snapshot.
- [Background agents](agents-background.md): detaching long-running turns and
  polling.
- [Working with state](agents-state.md): typed custom session state and streamed
  patches.
- [Artifacts](agents-artifacts.md): producing/reading named deliverables.
- [Multi-agent orchestration](agents-multi-agent.md): delegating to sub-agents.
- [Advanced custom agents](agents-custom.md): `DefineCustomAgent` for full turn
  control.
- [Deploying agents](agents-deployment.md): serving agents over HTTP.

- [Packages and import aliases](#packages-and-import-aliases): Lines 48-65
- [Setup](#setup): Lines 67-78
- [Define an agent](#define-an-agent): Lines 80-177
- [Agents and middleware go hand in hand](#agents-and-middleware-go-hand-in-hand): Lines 179-204
- [Run an agent (single turn)](#run-an-agent-single-turn): Lines 206-234
- [Chat with an agent (multi-turn)](#chat-with-an-agent-multi-turn): Lines 236-279
- [Verify an agent from the CLI (flow:run)](#verify-an-agent-from-the-cli-flowrun): Lines 281-296
- [Serve an agent over HTTP](#serve-an-agent-over-http): Lines 298-339
- [Client-managed vs server-managed state](#client-managed-vs-server-managed-state): Lines 341-381

---

## Packages and import aliases

Agents span a few packages. These aliases are used throughout the agent docs:

```go
import (
	"github.com/firebase/genkit/go/ai"
	aix "github.com/firebase/genkit/go/ai/exp"           // types: Agent, Session, options, AgentInput/Output
	"github.com/firebase/genkit/go/ai/exp/localstore"    // session stores
	"github.com/firebase/genkit/go/genkit"
	genkitx "github.com/firebase/genkit/go/genkit/exp"   // constructors: DefineAgent, DefineCustomAgent, ...
)
```

`genkitx` (genkit/exp) holds the registry-aware constructors you call.
`aix` (ai/exp) holds the types, options, and the returned `*aix.Agent[State]`.
Both packages are named `exp`, which is why the docs alias them `genkitx` and
`aix`.

## Setup

```go
ctx := context.Background()
g := genkit.Init(ctx,
	genkit.WithExperimental(), // REQUIRED: opts into the genkit/exp surface
	genkit.WithPlugins(&googlegenai.GoogleAI{}),
)
```

Without `genkit.WithExperimental()`, `genkitx.DefineAgent` (and every other
`genkit/exp` constructor) panics with a message pointing you at the fix.

## Define an agent

`genkitx.DefineAgent` combines an inline prompt + tools + (optional) session
store into a single registered action. The prompt is an `aix.InlinePrompt` — a
slice of `ai.PromptOption` values, the same options you would pass to
`genkit.DefinePrompt`.

```go
type WeatherInput struct {
	City string `json:"city"`
}
type WeatherOutput struct {
	TempC   float64 `json:"tempC"`
	Summary string  `json:"summary"`
}

getWeather := genkit.DefineTool(g, "getWeather",
	"Look up the current weather for a city.",
	func(ctx *ai.ToolContext, in WeatherInput) (WeatherOutput, error) {
		return WeatherOutput{TempC: 21, Summary: "Sunny"}, nil
	},
)

weatherAgent := genkitx.DefineAgent(g, "weatherAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a helpful weather assistant. Use the getWeather tool. Be concise."),
		ai.WithTools(getWeather),
	},
	// A session store is optional. Omit it for client-managed state (see below).
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

The `State` type parameter is inferred from the typed options (here
`aix.WithSessionStore(...[any]())` makes `State = any`). For a
**client-managed**
agent with no typed option, pass `State` explicitly:
`genkitx.DefineAgent[any](g, "name", prompt)`.

Constructor choices:

- `genkitx.DefineAgent` — inline prompt (the common case, above).
- `genkitx.DefinePromptAgent` — back the agent with a prompt already in the
  registry (e.g. a `.prompt` file). By default it uses the prompt registered
  under the agent's own name; use `aix.WithNamedPrompt` to point at another.
- `genkitx.DefineCustomAgent` — full control over the turn loop. See
  [advanced custom agents](agents-custom.md).

### Backing an agent with a `.prompt` file

`genkitx.DefinePromptAgent` pairs an agent with a prompt from the registry — for
example a `.prompt` file loaded at startup — so prompt authors can tune the
model, config, template, and default input without touching the Go wiring. With
no source option it defaults to the prompt registered under the agent's own
name.

```prompt
---
# prompts/chef.prompt
model: googleai/gemini-flash-latest
input:
  schema: ChatPromptInput
  default:
    personality: a Michelin-starred chef who loves explaining technique
---
You are {{personality}}. Keep every answer very brief, a few sentences at most.
```

If the `.prompt` frontmatter references a schema by name, register that Go type
with `genkit.DefineSchemasFor` **before** defining the agent (the prompt is
rendered at definition time):

```go
type ChatPromptInput struct {
	Personality string `json:"personality"`
}

genkit.DefineSchemasFor(g, ChatPromptInput{}) // resolve "ChatPromptInput" in the .prompt

chef := genkitx.DefinePromptAgent(g, "chef", // loads prompts/chef.prompt by name
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
	aix.WithDescription[any]("Michelin-starred chef"),
)
```

To supply an input from code, or to back several agents with one shared prompt,
add `aix.WithNamedPrompt(name, input)`.

Common agent options (all from `aix`):

- `aix.WithSessionStore(store)`: server-side snapshot persistence. See
  [sessions](agents-sessions.md).
- `aix.WithDescription[State](desc)`: human-readable description (shown in the
  Dev UI; used by [sub-agent delegation](agents-multi-agent.md)).
- `aix.WithStateTransform[State](fn)`: rewrite state on its way out to a client
  (e.g. PII redaction).
- `aix.WithStreamTransform[State](fn)`: rewrite stream chunks on their way out.

## Agents and middleware go hand in hand

Agents and [middleware](middleware.md) are built for each other: the
`ai.WithUse(...)` prompt option layers in behavior without writing it yourself.
Most agent capabilities — sub-agent delegation, artifacts, retries, fallback,
tool approval — are just middleware you drop in.

```go
weatherAgent := genkitx.DefineAgent(g, "weatherAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a helpful weather assistant."),
		ai.WithTools(getWeather),
		ai.WithUse(
			&middleware.Retry{},        // plugins/middleware: retry transient model errors
			&middlewarex.Artifacts{},   // plugins/middleware/exp: read_artifact / write_artifact
		),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

`plugins/middleware` provides `Retry`, `Fallback`, `ToolApproval`, `Filesystem`,
and `Skills`. `plugins/middleware/exp` (aliased `middlewarex`) adds the
agent-specific `Agents` (sub-agent delegation) and `Artifacts` middleware. See
[using middleware](middleware.md) and [multi-agent](agents-multi-agent.md).

## Run an agent (single turn)

`Agent.RunText` and `Agent.Run` run one turn and return the final
`*aix.AgentOutput[State]`.

```go
out, err := weatherAgent.RunText(ctx, "Weather in Tokyo?")
if err != nil {
	log.Fatal(err)
}
fmt.Println(out.Message.Text())
fmt.Println(out.SnapshotID)   // immutable checkpoint id for this turn (server-managed only)
fmt.Println(out.FinishReason) // e.g. aix.AgentFinishReasonStop
```

`Run` takes an `*aix.AgentInput` when you need more than user text (a full
message, a resume payload, or a detach signal):

```go
out, err := weatherAgent.Run(ctx, &aix.AgentInput{
	Message: ai.NewUserTextMessage("Weather in Tokyo?"),
})
```

In-band failures (a failed turn) resolve as a failed `AgentOutput`
(`out.FinishReason == aix.AgentFinishReasonFailed`, `out.Error` populated), not
a
Go `error`. A returned `error` means the invocation never started (e.g. a
rejected session source).

## Chat with an agent (multi-turn)

`Agent.Connect` opens a bidirectional streaming session. A single connection
carries state forward automatically across turns. Send input, iterate
`Receive()` until a `TurnEnd`, then send the next input.

```go
conn, err := weatherAgent.Connect(ctx)
if err != nil {
	log.Fatal(err)
}

// Turn 1 (streaming):
_ = conn.SendText("Weather in Tokyo?")
for chunk, err := range conn.Receive() {
	if err != nil {
		log.Fatal(err)
	}
	if chunk.ModelChunk != nil {
		fmt.Print(chunk.ModelChunk.Text())
	}
	if chunk.TurnEnd != nil {
		break // turn done; safe to send the next input
	}
}

// Turn 2 - history is carried automatically on the same connection:
_ = conn.SendText("What about Paris?")
for chunk, err := range conn.Receive() {
	if err != nil {
		log.Fatal(err)
	}
	if chunk.TurnEnd != nil {
		break
	}
}

out, err := conn.Output() // finalize; closes input and drains remaining chunks
```

Connection helpers: `SendText`, `SendMessage`, `Send` (raw `*aix.AgentInput`),
`SendResume` (see [interrupts](agents-human-in-the-loop.md)), `Detach` (see
[background](agents-background.md)), `Receive` (chunk iterator), `Custom`
(live custom state, see [state](agents-state.md)), `Output`, and `Close`.

## Verify an agent from the CLI (`flow:run`)

`genkit flow:run` runs **flows**, not agents, so you can't `flow:run` an agent
directly. To exercise an agent from the CLI (a quick, self-terminating check),
wrap one turn in a throwaway flow and run that:

```go
genkit.DefineFlow(g, "tryWeatherAgent", func(ctx context.Context, message string) (string, error) {
	out, err := weatherAgent.RunText(ctx, message)
	if err != nil {
		return "", err
	}
	return out.Message.Text(), nil
})
// genkit flow:run tryWeatherAgent '"Weather in Tokyo?"' -- go run .
```

## Serve an agent over HTTP

An agent is an `api.BidiAction`, so `genkit.Handler` serves it one turn per
request. Optionally serve its companion actions for snapshot lookup
(`GetSnapshotAction`) and background aborts (`AbortAction`); both are `nil` for
a
client-managed agent (no store).

```go
mux := http.NewServeMux()
mux.HandleFunc("POST /api/weatherAgent", genkit.Handler(weatherAgent))

// Optional companions (needed for snapshot restore / branching / background):
if snap := weatherAgent.GetSnapshotAction(); snap != nil {
	mux.HandleFunc("POST /api/weatherAgent/getSnapshot", genkit.Handler(snap))
}
if abort := weatherAgent.AbortAction(); abort != nil {
	mux.HandleFunc("POST /api/weatherAgent/abort", genkit.Handler(abort))
}

log.Fatal(server.Start(ctx, "127.0.0.1:8080", mux))
```

The request body is `{"data": <AgentInput>, "init": <AgentInit>}`. `data`
carries
the turn's input; `init` carries the session source (see below). Set
`Accept: text/event-stream` (or add `?stream=true`) to stream chunks.

Rather than wiring companions by hand, `genkit/exp` ships a default HTTP layout:
`genkitx.AllAgentRoutes(g)` returns a route per registered agent (mounted under
`/agents/<name>`, with `getSnapshot` / `abort` added for capable agents), which
you range over onto a mux:

```go
for _, route := range genkitx.AllAgentRoutes(g) {
	mux.HandleFunc(route.Pattern(), route.Handler())
}
```

For serving multiple agents, the route helpers, CORS headers for browser
clients,
and companion routing, see [Deploying agents](agents-deployment.md).

## Client-managed vs server-managed state

**Server-managed** (a `SessionStore` is configured): the server owns history as
snapshots. Resume with `aix.WithSessionID` (latest snapshot of a session) or
`aix.WithSnapshotID` (a specific snapshot). Over HTTP, `init` carries
`{"sessionId": ...}` or `{"snapshotId": ...}`.

```go
out1, _ := weatherAgent.RunText(ctx, "Weather in London?")
out2, _ := weatherAgent.RunText(ctx, "Is it sunny in Tokyo?",
	aix.WithSessionID(out1.SessionID)) // resumes the conversation
```

**Client-managed** (no store): the server is stateless and the caller owns the
session state blob (messages + custom + artifacts). Round-trip it via
`aix.WithState` / `out.State`. Over HTTP, `init` carries `{"state": ...}`.

```go
statelessAgent := genkitx.DefineAgent[any](g, "weatherAgentStateless",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a helpful weather assistant. Be concise."),
		ai.WithTools(getWeather),
	},
)

// First turn: start fresh; the framework mints a SessionID inside the state.
out1, _ := statelessAgent.RunText(ctx, "Weather in London?")

// Next turn: pass the returned state back to resume.
out2, _ := statelessAgent.Run(ctx,
	&aix.AgentInput{Message: ai.NewUserTextMessage("And Tokyo?")},
	aix.WithState(out1.State),
)
fmt.Println(out2.State) // updated blob to carry forward again
```

Use client-managed state when you don't want server-side storage. Use a
[session store](agents-sessions.md) when the server should own history, or when
you need branching or background execution.
([Interrupts](agents-human-in-the-loop.md) work either way.)
