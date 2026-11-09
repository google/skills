---
name: developing-genkit-dart
description: >-
  Provides guidance on developing AI-powered applications using the Genkit Dart
  SDK. Use when the user asks to build AI agents in Dart, use Genkit flows, or
  integrate LLMs into Dart/Flutter applications. Don't use for Genkit in
  JavaScript/TypeScript, Go, or Python.
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

# Genkit Dart

Genkit Dart is an AI SDK for Dart that provides a unified interface for code
generation, structured outputs, tools, flows, and AI agents.

## Core Features and Usage
If you need help with initializing Genkit (`Genkit()`), Generation
(`ai.generate`), Tooling (`ai.defineTool`), Flows (`ai.defineFlow`), Embeddings
(`ai.embed`), streaming, or calling remote flow endpoints, please load the core
framework reference:
[references/genkit.md](references/genkit.md)

## 1.0 vs pre-1.0 APIs

This skill targets Genkit Dart **1.0** (`genkit: ^1.0.0`). Older code and
training data use pre-1.0 names that no longer compile; the common ones:

- HTTP: `startFlowServer` / per-route `shelfHandler` / `shelf_cors_headers` are
  now `GenkitRouter` + `serve()` or `asShelfHandler()`, with `CorsOptions`;
  context providers take `RequestData`
  ([genkit_shelf.md](references/genkit_shelf.md)).
- `StatusCodes.UNAUTHENTICATED` is `StatusCode.unauthenticated` (lowerCamelCase,
  same for `EvalStatus.pass`, `ToolChoice.required`).
- No `RetryPlugin`; `retry()` is built in and takes `Duration`s
  (`initialDelay`, `maxDelay`, also `cacheTtl` elsewhere).
- Renames: `GenerateResponseHelper` -> `GenerateResult` (`modelResponse`,
  `chunk.modelChunk`), `ExecutablePrompt` -> `Prompt<Input, Output>`,
  `embedMany` -> `embed`, `ToolFnArgs` -> `ToolFnArg`, `toolOutputSchema` ->
  `outputSchema`, `underlyingException` -> `cause`, `modelInfo:` -> `info:`,
  `RemoteAction.dispose()` -> `close()`,
  `prompt(input, PromptGenerateOptions(config: ...))`
  -> `prompt(input, config: ...)` (named options, like `generate`),
  `defineMiddleware` ->
  `ai.defineGenerateMiddleware` (app) / `generateMiddleware` (plugins).
- Provider config types are prefixed: `GeminiThinkingConfig`,
  `GeminiSafetySettings`, `GeminiGoogleSearch`, `GeminiSpeechConfig`,
  `GoogleGenAiEmbedderOptions`, `AnthropicThinkingConfig`.
- Removed: `ToolInterruptException` / `ctx.interrupt()` (return
  `.interrupt(...)`),
  `GoogleAiModels` / `OpenAIModels` constants (use `googleAI.gemini('...')`,
  `openAI.model('...')`). Simulated constrained output is opt-in via
  `simulateConstrainedGeneration()`.
- `.prompt` Picoschema is spec-compliant: `name: type, description`, never
  `name(description): type` ([dotprompt.md](references/dotprompt.md)).

## Prompts (Dotprompt)

`.prompt` files keep prompt content out of Dart code with YAML frontmatter plus
a
Handlebars template. See [references/dotprompt.md](references/dotprompt.md):
`promptDir`, `ai.prompt()` (call/stream/render), variants, partials, named
schemas via `defineSchema`, and the
`tools`/`maxTurns`/`returnToolRequests`/`use`
(middleware) frontmatter fields. A `.prompt` file can also back an agent
directly
via `definePromptAgent`.

## Agents

Genkit Dart has an **agent** API for persistent, multi-turn conversations
(sessions, snapshots, interrupts, branching, background execution, custom state,
artifacts, and multi-agent delegation). The agent/session/snapshot APIs are
**experimental** and live behind opt-in imports: server APIs come from
`package:genkit/experimental.dart` (alongside `package:genkit/genkit.dart`), the
browser/HTTP client from `package:genkit/experimental_client.dart` (alongside
`package:genkit/client.dart`), and `dart:io` extras like `FileSessionStore` from
`package:genkit/experimental_io.dart`. These entry points are `@experimental`,
so
importing them raises an `experimental_member_use` analyzer warning you can
silence in `analysis_options.yaml`. The `remoteAgent` client works from any Dart
app, including **Flutter**, and the backend is fully interchangeable — it can
talk
to a Genkit agent implemented in Dart, JS/TypeScript, or Go over the same HTTP
protocol. A few Dart specifics: interrupts are `ai.defineInterrupt(...)` or
tools that return `.interrupt(...)` (there is no `ctx.interrupt()`), sub-agent
delegation uses
the `agents()` middleware from `package:genkit_middleware`, and there is no
`artifacts()` middleware yet (define artifact tools directly).

For more details see:

-   [Agents](references/agents.md): defining/serving an agent and client-managed
    state (start here).
-   [Sessions & persistence](references/agents-sessions.md): session stores
    (`InMemorySessionStore`/`FileSessionStore`/`FirestoreSessionStore`).
-   [Human-in-the-loop / interrupts](references/agents-human-in-the-loop.md):
    pausing for approval/input via `.interrupt(...)` and resuming.
-   [Branching](references/agents-branching.md): forking a conversation from a
    snapshot.
-   [Background agents](references/agents-background.md): detaching long-running
    turns and polling.
-   [Working with state](references/agents-state.md): typed custom session
    state, auto-synced to the client.
-   [Artifacts](references/agents-artifacts.md): producing and reading named
    deliverables.
-   [Multi-agent orchestration](references/agents-multi-agent.md): delegating to
    sub-agents with the `agents()` middleware.
-   [Advanced custom agents](references/agents-custom.md): `defineCustomAgent`
    for full turn control.
-   [Deploying agents](references/agents-deployment.md): serving agents over
    HTTP with `GenkitRouter.addAgent` (multiple agents, shelf, CORS).

## Generative UI (A2UI)

Genkit Dart has an **A2UI** (Agent-to-UI) plugin (`genkit_a2ui`)
that lets an agent stream interactive UI **surfaces** (cards, lists, forms,
buttons), not just prose. The whole server-side integration is the `a2ui()`
model
middleware in an agent's (or `ai.generate`'s) `use` list; the Flutter client
renders surfaces with the [`genui`](https://pub.dev/packages/genui) package plus
the helpers in `package:genkit_a2ui/client.dart`. Dart specific: you must
register `A2uiPlugin()` in `Genkit(plugins: [...])` (unlike JS, middleware is
resolved by name from the registry).

-   [A2UI](references/a2ui.md): server middleware, options, Flutter/genui client
    rendering, user actions/forms, custom catalogs, and the security/trust
    boundary.

## Genkit CLI (recommended)

`genkit start` unintrusively wraps any Dart program that uses the Genkit
library, running it unchanged while capturing traces from every Genkit action so
you can prove tools were actually called and inspect model I/O from the
terminal, even for headless checks. It forwards stdio, so interactive CLI tools
that rely on stdin/stdout work without issues. Running the app directly
(`dart run`) skips trace capture, so you're debugging blind. Check install with
`genkit --version`.

**Installation:**
```bash
curl -sL cli.genkit.dev | bash # Native CLI
# OR
npm install -g genkit-cli # Via npm
# OR run commands directly with npx without a global install (prefix every genkit command):
# npx genkit-cli start -- dart run main.dart
```

**Primary pattern (default):** prefix `genkit start --` to your normal run
command. This collects telemetry from any Genkit code your program runs, whether
triggered from the dev UI, your own web server/web UI, or a plain script. Starts
the Developer UI (usually http://localhost:4000) for running flows, model and
agent playground, and browsing traces:

```bash
genkit start -- dart run main.dart
genkit start --noui -- dart run main.dart   # same, without the Dev UI (still a persistent server)
```
`genkit start` runs until you stop it with Ctrl+C. That is expected and correct
for the common cases: a server your web/mobile app calls, or an interactive CLI
you exit yourself. `--noui` only drops the Dev UI; it is **not** a one-shot
command and will not exit on its own. Do **not** use `genkit start` as a
blocking step in automated/non-interactive contexts; use `flow:run` (below) for
that.

**Non-interactive use (agents/CI):** add the global `--non-interactive` flag
before `--` so the CLI uses defaults and never blocks on a prompt (e.g. the
first-run analytics notice):
`genkit start --non-interactive -- dart run main.dart` (works with `flow:run`
too).

**Run a flow (`flow:run`):** invoke a specific flow by name from the CLI. Append
your run command after `--` to spin up the runtime just for this run (the
command runs as-is to register your flows):
```bash
genkit flow:run myFlow '{"data": "input"}' -- dart run main.dart
```
This is **self-terminating**: it runs the flow once, prints a `Trace ID`, then
exits, so it's the right choice for a quick, non-interactive check (unlike
`genkit start`). Note: `flow:run` runs **flows** (`ai.defineFlow`), not agents;
you can't `flow:run` an agent (`ai.defineAgent`) directly. To exercise an agent
from the CLI, wrap one turn in a throwaway flow and run that (see
[Agents](references/agents.md)). Traces for this run can be inspected using the
trace commands below.

**Gotcha: top-level `final` declarations are lazy.** Flows and agents defined as
top-level `final` register with Genkit only when the symbol is first evaluated.
An empty `main()` registers nothing, so `flow:run` fails with
`Process exited before runtime was ready`. Reference the flow/agent symbols from
`main()` (or import a module that does) so their `define*` calls actually run.

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
genkit docs:search "streaming" dart
genkit docs:list dart
genkit docs:read dart/flows.md
```

## Plugin Ecosystem
Genkit relies on a large suite of plugins to perform generative AI actions,
interface with external LLMs, or host web servers.

When asked to use any given plugin, always verify usage by referring to its
corresponding reference below. You should load the reference when you need to
know the specific initialization arguments, tools, models, and usage patterns
for the plugin:

| Plugin Name | Reference Link | Description |
| ---- | ---- | ---- |
| `genkit_google_genai` | [references/genkit_google_genai.md](references/genkit_google_genai.md) | Load for Google Gemini plugin interface usage. |
| `genkit_vertexai` | [references/genkit_vertexai.md](references/genkit_vertexai.md) | Load for Gemini via Vertex AI (Google Cloud auth, versioned model IDs, embeddings incl. multimodal). |
| `genkit_anthropic` | [references/genkit_anthropic.md](references/genkit_anthropic.md) | Load for Anthropic plugin interface for Claude models. |
| `genkit_openai` | [references/genkit_openai.md](references/genkit_openai.md) | Load for OpenAI plugin interface for GPT models, Groq, and custom compatible endpoints. |
| `genkit_middleware` | [references/genkit_middleware.md](references/genkit_middleware.md) | Load for Tooling for specific agentic behavior: `filesystem`, `skills`, and `toolApproval` interrupts. |
| `genkit_mcp` | [references/genkit_mcp.md](references/genkit_mcp.md) | Load for Model Context Protocol integration (Server, Host, and Client capabilities). |
| `genkit_chrome` | [references/genkit_chrome.md](references/genkit_chrome.md) | Load for Running Gemini Nano locally inside the Chrome browser using the Prompt API. |
| `genkit_shelf` | [references/genkit_shelf.md](references/genkit_shelf.md) | Load for serving flows/models/agents over HTTP: `GenkitRouter` (core `package:genkit/io.dart`, standalone `dart:io`) and mounting it into Shelf apps. |
| `genkit_firebase_ai` | [references/genkit_firebase_ai.md](references/genkit_firebase_ai.md) | Load for Firebase AI plugin interface (Gemini API via Vertex AI). |
| `genkit_a2ui` | [references/a2ui.md](references/a2ui.md) | Load for A2UI (Agent-to-UI): streaming generative UI surfaces via the `a2ui()` middleware, rendered on the client with `genui`. |

## External Dependencies
Whenever you define schemas mapping inside of Tools, Flows, and Prompts, you
must use the [schemantic](https://pub.dev/packages/schemantic) library.
To learn how to use schemantic, ensure you read
[references/schemantic.md](references/schemantic.md) for how to implement type
safe generated Dart code. This is particularly relevant when you encounter
symbols like `@Schema()`, `SchemanticType`, or classes with the `$` prefix.
Genkit Dart uses schemantic for all of its data models so it's a CRITICAL skill
to understand for using Genkit Dart.

## Best Practices

- **Agent or flow?** If the task is conversational, multi-turn, or described as
  "an agent", "assistant", or "chatbot", build it with `ai.defineAgent` (see
  [Agents](references/agents.md)) rather than hand-rolling a `generate` + tools
  loop inside a flow. Reach for a plain flow only for single-shot, stateless
  generation.
- Always check that code cleanly compiles using `dart analyze` before generating
  the final response.
- Always use the Genkit CLI for local development and debugging.
- Verify with traces, not a blind run. Running the app directly (`dart run`)
  does not capture dev traces. See the [Genkit CLI](#genkit-cli-recommended)
  section for how to run your app and capture traces.
