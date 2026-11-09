# Multi-Agent Orchestration / Sub-Agents (Experimental)

> **Experimental / preview API.** Sub-agent delegation uses the `Agents`
> middleware from `plugins/middleware/exp`. Read [agents.md](agents.md) first.

A common pattern is an **orchestrator** agent that delegates tasks to
specialized
**sub-agents** (e.g. a `researcher` and a `coder`). The `middlewarex.Agents`
middleware injects one delegation tool per sub-agent (`delegate_to_<name>`),
appends a `<sub-agents>` block to the orchestrator's system prompt, and — when
the
model calls a delegation tool — runs the sub-agent with the task and returns its
response as the tool result.

```go
import (
	aix "github.com/firebase/genkit/go/ai/exp"
	middlewarex "github.com/firebase/genkit/go/plugins/middleware/exp"
	"github.com/firebase/genkit/go/plugins/middleware" // Retry, etc.
)
```

- [1. Define the sub-agents](#1-define-the-sub-agents): Lines 34-58
- [2. Wire up the orchestrator](#2-wire-up-the-orchestrator): Lines 60-98
- [middlewarex.Agents fields](#middlewarexagents-fields): Lines 100-119
- [Background delegation (Async: true)](#background-delegation-async-true): Lines 121-160
- [Continuing a task (continue_task)](#continuing-a-task-continue_task): Lines 162-179
- [Delegating to a remote agent](#delegating-to-a-remote-agent): Lines 181-204
- [Sharing artifacts between agents](#sharing-artifacts-between-agents): Lines 206-220
- [Combining with retries](#combining-with-retries): Lines 222-245

---

## 1. Define the sub-agents

Give each sub-agent a description via `aix.WithDescription` — it's
auto-discovered and shown to the orchestrator so the model knows when to
delegate.

```go
researcher := genkitx.DefineAgent(g, "researcher",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a thorough research assistant. Save findings with write_artifact."),
		ai.WithUse(&middleware.Retry{}, &middlewarex.Artifacts{}),
	},
	aix.WithDescription[any]("A thorough research assistant that provides well-sourced answers."),
)

coder := genkitx.DefineAgent(g, "coder",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are an expert programmer. Save code with write_artifact."),
		ai.WithUse(&middlewarex.Artifacts{}, &middleware.Retry{}),
	},
	aix.WithDescription[any]("An expert programmer that writes clean, well-commented code."),
)
```

## 2. Wire up the orchestrator

Add `&middlewarex.Agents{...}` to the orchestrator's `ai.WithUse`. Reference
each
sub-agent by `aix.AgentRef` — a bare `{Name: ...}` (description auto-discovered
from the registry) or `agent.Ref()` (captures the agent's name and description).

```go
orchestrator := genkitx.DefineAgent(g, "orchestrator",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem(`You are a helpful project assistant. Analyze the request and
delegate to the appropriate sub-agent. If it needs research AND code, call them
sequentially, then synthesize a final answer.`),
		ai.WithUse(
			&middlewarex.Agents{
				Agents: []aix.AgentRef{
					{Name: "researcher"}, // by name (description auto-discovered)
					coder.Ref(),          // by instance (carries its description)
				},
				MaxDelegations:   5,                                   // guard rail against runaway loops
				HistoryLength:    4,                                   // forward the last N user/model messages as context
				ArtifactStrategy: middlewarex.ArtifactStrategySession, // see "Sharing artifacts" below
			},
			&middlewarex.Artifacts{Readonly: true}, // read sub-agent artifacts via read_artifact
			&middleware.Retry{},
		),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

Run it like any other agent:

```go
out, _ := orchestrator.RunText(ctx,
	"Research the best sorting algorithms, then write a Go quicksort.")
fmt.Println(out.Message.Text())
```

## `middlewarex.Agents` fields

- `Agents` (required): sub-agent references (`[]aix.AgentRef`). Each is a bare
  `{Name: ...}` (description auto-discovered) or `agent.Ref()` (explicit).
- `ToolPrefix` (`*string`): prefix for generated delegation tool names. `nil`
  defaults to `"delegate_to"` (tools become `delegate_to_<agent>`); a pointer to
  the empty string uses bare agent names.
- `MaxDelegations` (`int`): cap on delegations per generate call. `0` means
  unlimited. Prevents runaway loops.
- `HistoryLength` (`int`): number of recent user/model messages forwarded to a
  sub-agent as context. `0` sends only the task description. History is
  forwarded
  only to **client-managed** sub-agents (no session store); server-managed
  sub-agents receive only the task.
- `ArtifactStrategy` (`middlewarex.ArtifactStrategy`): `ArtifactStrategyInline`
  (default) or `ArtifactStrategySession` — see below. The type and its constants
  live in `plugins/middleware/exp` alongside the `Agents` middleware.
- `Async` (`bool`): enables background delegation (see below).
- `MaxWaitSeconds` (`int`): caps one `wait_for_background_tasks` call, whatever
  timeout the model asks for. `0` lets the model decide.

## Background delegation (`Async: true`)

> Requires Genkit Go v1.14.0+.

By default a delegation blocks the orchestrator's turn. With `Async: true`, each
delegation tool accepts `background: true` and returns a task ID immediately,
and three tools are added:

- `check_background_tasks({taskIds})`: current status, no waiting.
- `wait_for_background_tasks({taskIds, timeoutSeconds, waitFor})`: blocks until
  they settle (`waitFor: "first"` returns on the first one).
- `abort_background_tasks({taskIds})`: stops tasks no longer needed.

**The sub-agent needs a session store** (with detach support). Background work
is tracked by a pending snapshot.

```go
researcher := genkitx.DefineAgent(g, "researcher",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("Research one question and answer in a few sentences."),
	},
	aix.WithDescription[any]("Researches one question."),
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()), // required for background
)

orchestrator := genkitx.DefineAgent(g, "orchestrator",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem(`Give each part of a question to the researcher IN THE BACKGROUND
("background": true), then collect the answers with wait_for_background_tasks.`),
		ai.WithUse(&middlewarex.Agents{
			Agents: []aix.AgentRef{researcher.Ref()},
			Async:  true,
		}),
		ai.WithMaxTurns(10), // background work adds tool rounds
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

## Continuing a task (`continue_task`)

> Requires Genkit Go v1.14.0+.

A delegation to a store-backed sub-agent returns a `taskId` and a settled
`status` even when synchronous. The
`continue_task({taskId, instructions, background})`
tool picks it up:

- **failed / aborted**: continues from the last saved progress (finished tool
  calls are not repeated); `instructions` steer the retry.
- **completed**: follow-up `instructions` in the sub-agent's own session.
- **expired**: fences the dead worker, then continues from the parent snapshot.
- **interrupted**: refused (no way to answer the interrupt from here).

Task IDs are scoped to the conversation: the tools accept only IDs this call or
its history minted. Two `Agents` instances in one call need distinct
`ToolPrefix` values.

## Delegating to a remote agent

> Requires Genkit Go v1.14.0+.

Any agent another Genkit app serves over HTTP (Go, JS, or Dart) can be a
sub-agent. Register it with `genkitx.DefineRemoteAgent`; the orchestrator code
is the same as for a local agent, background delegation included:

```go
researcher := genkitx.DefineRemoteAgent(g, "researcher", "https://research.internal/agents/researcher",
	aix.WithDescription[any]("Researches one question and answers in a few sentences."),
	aix.WithAgentMetadata(&aix.AgentMetadata{
		StateManagement: aix.AgentStateManagementServer, // remote keeps its own session
		Abortable:       true,                            // its store can stop background work
	}),
	// aix.WithHTTPClient(idTokenClient), aix.WithHeaders(fn), aix.WithRouteURLs(...)
)
```

`researcher.Ref()` then goes in `Agents` as usual. The handle
(`*aix.AgentHandle`)
also runs the remote agent directly (`Run`, `RunText`, `RunDetached`, `Task`,
`WaitForSnapshot`, `Abort`). The remote server needs a session store for
background tasks and `continue_task`.

## Sharing artifacts between agents

Sub-agents can produce [artifacts](agents-artifacts.md). `ArtifactStrategy`
controls how they reach the orchestrator:

- `middlewarex.ArtifactStrategyInline` (default): artifact content is included
  in
  the delegation tool result (so the model sees it directly) **and** merged into
  the parent session.
- `middlewarex.ArtifactStrategySession`: artifacts are merged into the parent
  session only; the tool result lists artifact names, not content. Pair it with
  `&middlewarex.Artifacts{}` on the orchestrator so it can `read_artifact` on
  demand (the pattern above). Merged artifacts are namespaced by an invocation
  ID
  (`<agentName>_<n>/<name>`) and tagged with their source agent.

## Combining with retries

`plugins/middleware`'s `Retry` (and `Fallback`) attach the same way via
`ai.WithUse` on an agent, and pair well with delegation:

```go
ai.WithUse(&middleware.Retry{
	MaxRetries:     3,     // default 3
	InitialDelayMs: 1000,  // default 1000
	MaxDelayMs:     60000, // default 60000
	BackoffFactor:  2,     // default 2
})
```

See [using middleware](middleware.md) for the full catalog (`Retry`, `Fallback`,
`ToolApproval`, `Filesystem`, `Skills`, `SoftToolErrors`, `ContextCompression`,
`Budget`). A `Budget` on the orchestrator also counts in-process sub-agents, so
delegation cannot spend around the cap.

> Note: a sub-agent failure is reported back to the orchestrator as the
> delegation tool's output, with a task ID to `continue_task` it. A sub-agent
> [interrupt](agents-human-in-the-loop.md) is reported the same way but cannot
> be
> continued, so delegate self-contained tasks.
