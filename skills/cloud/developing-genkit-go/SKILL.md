---
name: developing-genkit-go
description: >-
  Provides guidance on developing AI-powered applications using Genkit in Go.
  Use when the user asks to build AI features, agents, flows, or tools in Go
  using Genkit, or when working with Genkit Go code involving generation,
  prompts, streaming, tool calling, or model providers. Don't use for Genkit in
  JavaScript/TypeScript, Python, or Dart.
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

# Genkit Go

Genkit Go is an AI SDK for Go that provides generation, structured output,
streaming, tool calling, prompts, and flows with a unified interface across
model providers.

## Hello World

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"

	"github.com/firebase/genkit/go/ai"
	"github.com/firebase/genkit/go/genkit"
	"github.com/firebase/genkit/go/plugins/googlegenai"
	"github.com/firebase/genkit/go/plugins/server"
)

func main() {
	ctx := context.Background()
	g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.GoogleAI{}))

	genkit.DefineFlow(g, "jokeFlow", func(ctx context.Context, topic string) (string, error) {
		return genkit.GenerateText(ctx, g,
			ai.WithModelName("googleai/gemini-flash-latest"),
			ai.WithPrompt("Tell me a joke about %s", topic),
		)
	})

	mux := http.NewServeMux()
	for _, f := range genkit.ListFlows(g) {
		mux.HandleFunc("POST /"+f.Name(), genkit.Handler(f))
	}
	log.Fatal(server.Start(ctx, "127.0.0.1:8080", mux))
}
```

## Core Features

Load the appropriate reference based on what you need:

| Feature | Reference | When to load |
| --- | --- | --- |
| Initialization | [references/getting-started.md](references/getting-started.md) | Setting up `genkit.Init`, plugins, the `*Genkit` instance pattern |
| Generation | [references/generation.md](references/generation.md) | `Generate`, `GenerateText`, `GenerateData`, streaming, output formats, `Embed` |
| Prompts | [references/prompts.md](references/prompts.md) | `DefinePrompt`, `DefineDataPrompt`, `.prompt` files, schemas |
| Tools | [references/tools.md](references/tools.md) | `DefineTool`, `DefineResumableTool` interrupts (`Interrupted` claim, `Restart`/`Respond`, `WithResume`), `ai/tool` helpers (`tool.Interrupt`, `tool.Fail`, `tool.AttachParts`) |
| Middleware | [references/middleware.md](references/middleware.md) | `ai.Middleware`, `ai.WithUse`, `Hooks` (Generate/Model/Tool), built-ins (`Retry`, `Fallback`, `ToolApproval`, `Filesystem`, `Skills`, `SoftToolErrors`, `ContextCompression`, `Budget`) |
| Observability | [references/observability.md](references/observability.md) | OpenTelemetry export (`otelgenai`), `tracing.SetInstrumentation`, `aix.Observer`, reflection API outside dev |
| Flows & HTTP | [references/flows-and-http.md](references/flows-and-http.md) | `DefineFlow`, `DefineStreamingFlow`, `genkit.Handler`, HTTP serving |
| Model Providers | [references/providers.md](references/providers.md) | Google AI, Vertex AI, Anthropic, OpenAI-compatible, Ollama setup |

## Agents (Experimental)

Genkit Go has an **experimental** agent API for persistent, multi-turn
conversations (sessions, snapshots, interrupts, branching, background
execution).
It is gated: initialize with `genkit.Init(ctx, genkit.WithExperimental())` or
the
constructors panic. Server constructors come from `genkit/exp` (aliased
`genkitx`); types and options from `ai/exp` (aliased `aix`); session stores from
`ai/exp/localstore`.

- **Agent or flow?** If the task is conversational, multi-turn, or described as
  "an agent", "assistant", or "chatbot", build it with `genkitx.DefineAgent`
  rather than hand-rolling a `Generate` + tools loop in a flow. Reach for a
  plain flow only for single-shot, stateless generation.

For details see:

-   [Agents](references/agents.md): defining/serving an agent, running turns,
    and client- vs server-managed state (start here).
-   [Sessions & persistence](references/agents-sessions.md): session stores
    (`localstore.NewInMemorySessionStore`/`NewFileSessionStore`, PostgreSQL),
    snapshots, and the `sessionstoretest` conformance suite.
-   [Human-in-the-loop / interrupts](references/agents-human-in-the-loop.md):
    pausing for approval/input and resuming.
-   [Branching](references/agents-branching.md): forking a conversation from a
    snapshot.
-   [Background agents](references/agents-background.md): detaching long-running
    turns and polling.
-   [Working with state](references/agents-state.md): typed custom session
    state, streamed as JSON patches.
-   [Artifacts](references/agents-artifacts.md): producing and reading named
    deliverables.
-   [Multi-agent orchestration](references/agents-multi-agent.md): delegating to
    sub-agents, background delegation, `continue_task`, and remote agents
    (`DefineRemoteAgent`).
-   [Advanced custom agents](references/agents-custom.md): `DefineCustomAgent`
    for full turn control.
-   [Deploying agents](references/agents-deployment.md): serving agents over
    HTTP with `genkit.Handler`.

## Generative UI (A2UI)

Genkit Go has an **A2UI** (Agent-to-UI) plugin
(`github.com/firebase/genkit/go/plugins/a2ui/exp`, imported as `a2uix`) that
lets an agent stream interactive UI **surfaces** (cards, lists, forms, buttons),
not just prose. The whole integration is the `&a2uix.Surfaces{}` model
middleware added via `ai.WithUse`
on a generate call or agent inline prompt. **Go is server-only: it has no A2UI
client/renderer.** Render surfaces with a JS or Dart/Flutter client that talks
to
your Go agent over HTTP (the server and clients are wire-compatible).

-   [A2UI](references/a2ui.md): server middleware, options, custom catalogs, and
    security. For the client (rendering surfaces), refer to the A2UI reference
    in the Genkit JS or Dart skill.

## Genkit CLI (recommended)

`genkit start` unintrusively wraps any Go program that uses the Genkit library,
running it unchanged while capturing traces from every Genkit action so you can
prove tools were actually called and inspect model I/O from the terminal, even
for headless checks. It forwards stdio, so interactive CLI tools that rely on
stdin/stdout work without issues. Running the app directly (`go run .`) skips
trace capture, so you're debugging blind. Check install with `genkit --version`.

**Installation:**
```bash
curl -sL cli.genkit.dev | bash
```

**Primary pattern (default):** prefix `genkit start --` to your normal run
command. This collects telemetry from any Genkit code your program runs, whether
triggered from the dev UI, your own web server/web UI, or a plain script. Starts
the Developer UI (usually http://localhost:4000) for running flows, model and
agent playground, and browsing traces:
```bash
genkit start -- go run .
genkit start --noui -- go run .   # same, without the Dev UI (still a persistent server)
genkit start -o -- go run .       # also opens the browser
```
`genkit start` runs until you stop it with Ctrl+C. That is expected and correct
for the common cases: a server your web/mobile app calls, or an interactive CLI
you exit yourself. `--noui` only drops the Dev UI; it is **not** a one-shot
command and will not exit on its own. Do **not** use `genkit start` as a
blocking step in automated/non-interactive contexts; use `flow:run` (below) for
that.

**Non-interactive use (agents/CI):** add the global `--non-interactive` flag
before `--` so the CLI uses defaults and never blocks on a prompt (e.g. the
first-run analytics notice): `genkit start --non-interactive -- go run .` (works
with `flow:run` too).

**Run a flow (`flow:run`):** invoke a specific flow by name from the CLI. Append
your run command after `--` to spin up the runtime just for this run (the
command runs as-is to register your flows):
```bash
genkit flow:run myFlow '{"data": "input"}' -- go run .
genkit flow:run myFlow '{"data": "input"}' --stream -- go run .   # with streaming
genkit flow:run myFlow '{"data": "input"}' --wait -- go run .     # wait for completion
```
This is **self-terminating**: it runs the flow once, prints a `Trace ID`, then
exits, so it's the right choice for a quick, non-interactive check (unlike
`genkit start`). Traces for this run can be inspected using the trace commands
below.

**Debugging with traces:** the fastest way to see prompts, model inputs/outputs,
tool calls, latencies, and errors. Inspect from the terminal after any run under
`genkit start`:
```bash
genkit trace:list                        # find recent trace IDs
genkit trace:get <traceId>               # full trace details (inputs, outputs, tool calls, errors)
genkit trace:get <traceId> --format json # machine-readable JSON, safe to pipe into jq or other parsers
```

For machine-readable output, pass `--format json` to get clean JSON you can pipe
into `jq` or other parsers. The **default** output is human-oriented (banner/log
lines, possible truncation on large traces), so don't pipe that form directly;
use `--format json`, grep, or the Dev UI trace viewer.

**Documentation:**
```bash
genkit docs:search "streaming" go
genkit docs:list go
genkit docs:read go/flows.md
```

See [references/getting-started.md](references/getting-started.md) for full CLI
and Developer UI details.

## Key Guidance

- **Pass `g` explicitly.** The `*Genkit` instance returned by `genkit.Init` is
  the central registry. Pass it to all Genkit functions rather than storing it
  as a global. This is a core pattern throughout the SDK.
- **Wrap AI logic in flows.** Flows give you tracing, observability, HTTP
  deployment via `genkit.Handler`, and the ability to test from the Developer UI
  and CLI. Any generation call worth keeping should live in a flow.
- **Verify with traces, not a blind run.** Running the app directly (`go run .`)
  does not capture dev traces. See the [Genkit CLI](#genkit-cli-recommended)
  section for how to run your app and capture traces.
- **Use `jsonschema:"description=..."` struct tags on output types.** The model
  uses these descriptions to understand what each field should contain. Without
  them, structured output quality drops significantly.
- **Write good tool descriptions.** The model decides which tools to call based
  on their description string. Vague descriptions lead to missed or incorrect
  tool calls.
- **Use `.prompt` files for complex prompts.** They separate prompt content from
  Go code, support Handlebars templating, and can be iterated on without
  recompilation. Code-defined prompts are better for simple, single-line cases.
- **Use `DefineResumableTool` for interrupts.** Claim paused calls with the
  tool's `Interrupted` method and resume with `ai.WithResume`.
  `ai.InterruptWith`, `RestartWith`/`RespondWith`, and `WithToolRestarts` are
  deprecated; `genkitx.DefineInterruptibleTool` and `ai/exp/tool` were removed
  in v1.14.0. See [references/tools.md](references/tools.md).
- **Reach for built-in middleware before writing one.** `Retry`, `Fallback`,
  `ToolApproval`, `Filesystem`, `Skills`, and `SoftToolErrors` cover the common
  cross-cutting needs and compose with each other via `ai.WithUse`. See
  [references/middleware.md](references/middleware.md). When you do write custom
  middleware, allocate per-call state in closures captured by `New`, and guard
  anything that `WrapTool` mutates because tools may run concurrently.
- **Look up the latest model IDs.** Model names change frequently. Check
  provider documentation for current model IDs rather than relying on hardcoded
  names. See [references/providers.md](references/providers.md).
