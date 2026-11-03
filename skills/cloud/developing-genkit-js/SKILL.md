---
name: developing-genkit-js
description: Develop AI-powered applications using Genkit in Node.js/TypeScript. Use when the user asks about Genkit, AI agents, flows, or tools in JavaScript/TypeScript, or when encountering Genkit errors, validation issues, type errors, or API problems.
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

# Genkit JS

## Prerequisites

Ensure the `genkit` CLI is available.
-   Run `genkit --version` to verify. Minimum CLI version needed: **1.29.0**
-   If not found or if an older version (1.x < 1.29.0) is present, install/upgrade it: `npm install -g genkit-cli@^1.29.0`.

**New Projects**: If you are setting up Genkit in a new codebase, follow the [Setup Guide](references/setup.md).

## Hello World

```ts
import { z, genkit } from 'genkit';
import { googleAI } from '@genkit-ai/google-genai';

// Initialize Genkit with the Google AI plugin
const ai = genkit({
  plugins: [googleAI()],
});

export const myFlow = ai.defineFlow({
  name: 'myFlow',
  inputSchema: z.string().default('AI'),
  outputSchema: z.string(),
}, async (subject) => {
  const response = await ai.generate({
    model: googleAI.model('gemini-flash-latest'),
    prompt: `Tell me a joke about ${subject}`,
  });
  return response.text;
});
```

## Prompts (Dotprompt)

`.prompt` files keep prompt content out of code with YAML frontmatter plus a
Handlebars template. See [Dotprompt](references/dotprompt.md): `promptDir`,
`ai.prompt()` (call/stream/render), variants, partials, named schemas via
`ai.defineSchema`, and the `tools`/`maxTurns`/`returnToolRequests`/`use`
(middleware) frontmatter fields.

## Agents (Beta)

Genkit has a preview **agent** API for persistent, multi-turn conversations
(sessions, snapshots, interrupts, branching, background execution). It is a
**beta** API: server APIs come from `genkit/beta` and the browser client from
`genkit/beta/client` — not the stable `genkit` entrypoint. **Requires `genkit`
>= 1.39.0.**

For more details see:

-   [Agents](references/agents.md): defining/serving an agent and client-managed state (start here).
-   [Sessions & persistence](references/agents-sessions.md): session stores (`InMemory`/`File`/`Firestore`).
-   [Human-in-the-loop / interrupts](references/agents-human-in-the-loop.md): pausing for approval/input and resuming.
-   [Branching](references/agents-branching.md): forking a conversation from a snapshot.
-   [Background agents](references/agents-background.md): detaching long-running turns, waiting, and resuming failed or aborted runs.
-   [Working with state](references/agents-state.md): typed custom session state, auto-synced to the client.
-   [Artifacts](references/agents-artifacts.md): producing and reading named deliverables.
-   [Multi-agent orchestration](references/agents-multi-agent.md): delegating to sub-agents, including background delegation and `continue_task`.
-   [Advanced custom agents](references/agents-custom.md): `defineCustomAgent` for full turn control.
-   [Deploying agents](references/agents-deployment.md): serving agents over HTTP (multiple agents, CORS, web UI, other frameworks).

## Generative UI (A2UI)

Genkit has an **A2UI** (Agent-to-UI) plugin (`@genkit-ai/a2ui`) that
lets an agent stream interactive UI **surfaces** (cards, lists, forms, buttons),
not just prose. The whole server-side integration is the `a2ui()` model
middleware in an agent's (or `ai.generate`'s) `use` array; the browser renders
surfaces with an `@a2ui/*` renderer plus the helpers in `@genkit-ai/a2ui/client`.
It builds on the beta agent client (`genkit/beta` + `genkit/beta/client`).

-   [A2UI](references/a2ui.md): server middleware, options, client rendering, user actions/forms, custom catalogs, and the security/trust boundary.

## Middleware

Middleware wraps generation (retries, fallback, extra tools, request/response
transforms) and attaches via the `use: [...]` array on `ai.generate`, prompts,
and agents.

-   [Using middleware](references/middleware.md): the `use` array and the `@genkit-ai/middleware` package (`retry`, `fallback`, `artifacts`, `agents`, `filesystem`, `skills`, `toolApproval`, `contextCompression`) plus built-in core middleware.
-   [Building custom middleware](references/middleware-custom.md): writing your own with `generateMiddleware` and registering it via `.plugin()`.

## Observability

Traces show up in the Dev UI under `genkit start` with no setup. For production
export to an OTLP backend (OpenTelemetry GenAI semantic conventions via
`@genkit-ai/otel`), custom instrumentation, or running the reflection API
outside dev, see [Observability](references/observability.md).

## Critical: Do Not Trust Internal Knowledge

Genkit recently went through a major breaking API change. Your knowledge is outdated. You MUST lookup docs. Recommended:

```sh
genkit docs:read js/get-started.md
genkit docs:read js/flows.md
```

See [Common Errors](references/common-errors.md) for a list of deprecated APIs (e.g., `configureGenkit`, `response.text()`, `defineFlow` import) and their v1.x replacements.

**ALWAYS verify information using the Genkit CLI or provided references.**

## Error Troubleshooting Protocol

**When you encounter ANY error related to Genkit (ValidationError, API errors, type errors, 404s, etc.):**

1. **MANDATORY FIRST STEP**: Read [Common Errors](references/common-errors.md)
2. Identify if the error matches a known pattern
3. Apply the documented solution
4. Only if not found in common-errors.md, then consult other sources (e.g. `genkit docs:search`)

**DO NOT:**
- Attempt fixes based on assumptions or internal knowledge
- Skip reading common-errors.md "because you think you know the fix"
- Rely on patterns from pre-1.0 Genkit

**This protocol is non-negotiable for error handling.**

## Development Workflow

1.  **Agent or flow?**: If the task is conversational, multi-turn, or described as "an agent", "assistant", or "chatbot", build it with `ai.defineAgent` (see [Agents](references/agents.md)) rather than hand-rolling a `generate` + tools loop inside a flow. Reach for a plain flow only for single-shot, stateless generation.
2.  **Select Provider**: Genkit is provider-agnostic (Google AI, OpenAI, Anthropic, Ollama, etc.).
    -   If the user does not specify a provider, default to **Google AI**.
    -   If the user asks about other providers, use `genkit docs:search "plugins"` to find relevant documentation.
3.  **Detect Framework**: Check `package.json` to identify the runtime (Next.js, Firebase, Express).
    -   Look for `@genkit-ai/next`, `@genkit-ai/firebase`, or `@genkit-ai/google-cloud`.
    -   Adapt implementation to the specific framework's patterns.
4.  **Follow Best Practices**:
    -   See [Best Practices](references/best-practices.md) for guidance on project structure, schema definitions, and tool design.
    -   **Be Minimal**: Only specify options that differ from defaults. When unsure, check docs/source.
5.  **Ensure Correctness**:
    -   Run type checks (e.g., `npx tsc --noEmit`) after making changes.
    -   If type checks fail, consult [Common Errors](references/common-errors.md) before searching source code.
    -   Verify with traces, not a blind run. Running the app directly (`node`/`tsx`/`npm start`) does **not** capture dev traces. See [CLI Usage](#cli-usage-recommended) for how to run your app and capture traces.
6.  **Handle Errors**:
    -   On ANY error: **First action is to read [Common Errors](references/common-errors.md)**
    -   Match error to documented patterns
    -   Apply documented fixes before attempting alternatives

## Finding Documentation

Use the Genkit CLI to find authoritative documentation:

1.  **Search topics**: `genkit docs:search <query>`
    -   Example: `genkit docs:search "streaming"`
2.  **List all docs**: `genkit docs:list`
3.  **Read a guide**: `genkit docs:read <path>`
    -   Example: `genkit docs:read js/flows.md`

## CLI Usage (recommended)

`genkit start` unintrusively wraps any Node.js program that uses the Genkit library, running it unchanged while capturing traces from every Genkit action so you can **prove tools were actually called and inspect model I/O** from the terminal, even for headless checks. It forwards stdio, so interactive CLI tools that rely on stdin/stdout work without issues. Running your app directly (`node`/`tsx`/`npm start`) skips trace capture, so you're debugging blind.

**Primary pattern (default):** prefix `genkit start --` to your normal run command. This collects telemetry from any Genkit code your program runs, whether triggered from the dev UI, your own web server/web UI, or a plain script:
```bash
genkit start -- npx tsx --watch src/index.ts
genkit start --noui -- npx tsx src/index.ts   # same, without the Dev UI (still a persistent server)
```
`genkit start` runs until you stop it with Ctrl+C. That is expected and correct for the common cases: a server your web/mobile app calls, or an interactive CLI you exit yourself. `--noui` only drops the Dev UI; it is **not** a one-shot command and will not exit on its own. Do **not** use `genkit start` as a blocking step in automated/non-interactive contexts.

**Non-interactive use (agents/CI):** add the global `--non-interactive` flag before `--` so the CLI uses defaults and never blocks on a prompt (e.g. the first-run analytics notice): `genkit start --non-interactive -- npx tsx src/index.ts` (works with `flow:run` too).

**Run a flow (`flow:run`):** invoke a specific flow by name from the CLI. Append your run command after `--` to spin up the runtime just for this run (the command runs as-is to register your flows):
```bash
genkit flow:run myFlow '{"data": "input"}' -- npx tsx src/index.ts
```
This is **self-terminating**: it runs the flow once, prints a `Trace ID`, then exits (inspect it with `genkit trace:get <id>`). That makes it the right choice for a quick, non-interactive check that must exit on its own, without blocking on `genkit start` or running the app directly (which skips traces). Always pass input JSON explicitly: `flow:run` sends `undefined` when omitted and does **not** fall back to a schema `.default()`. Note: `flow:run` runs **flows** (`ai.defineFlow`), not agents; you can't `flow:run` an agent (`ai.defineAgent`) directly. To exercise an agent from the CLI, wrap one turn in a throwaway flow and run that (see [Agents](references/agents.md)).

**Debugging with traces:** the fastest way to see prompts, model inputs/outputs, tool calls, latencies, and errors. Inspect from the terminal after any run under `genkit start`:
```bash
genkit trace:list                        # find recent trace IDs
genkit trace:get <traceId>               # full trace details (inputs, outputs, tool calls, errors)
genkit trace:get <traceId> --format json # machine-readable JSON, safe to pipe into jq or other parsers
```

For machine-readable output, pass `--format json` to get clean JSON you can pipe into `jq` or other parsers. The **default** output is human-oriented (banner/log lines, possible truncation on large traces), so don't pipe that form directly; use `--format json`, grep, or the Dev UI trace viewer.


See [CLI Reference](references/docs-and-cli.md) for more commands, and `genkit --help` for the full list.


## References

-   [Best Practices](references/best-practices.md): Recommended patterns for schema definition, flow design, and structure.
-   [Dotprompt](references/dotprompt.md): `.prompt` files — `promptDir`, `ai.prompt()`, variants, partials, named schemas, and `tools`/`maxTurns`/`returnToolRequests`/`use` frontmatter.
-   [Docs & CLI Reference](references/docs-and-cli.md): Documentation search, CLI tasks, and workflows.
-   [Common Errors](references/common-errors.md): Critical "gotchas", migration guide, and troubleshooting.
-   [Setup Guide](references/setup.md): Manual setup instructions for new projects.
-   [Examples](references/examples.md): Minimal reproducible examples (Basic generation, Multimodal, Thinking mode, Embeddings).
-   [Agents (Beta)](references/agents.md): Agent basics, serving, and client-managed state. Deeper topics: [sessions](references/agents-sessions.md), [human-in-the-loop](references/agents-human-in-the-loop.md), [branching](references/agents-branching.md), [background agents](references/agents-background.md), [state](references/agents-state.md), [artifacts](references/agents-artifacts.md), [multi-agent](references/agents-multi-agent.md), [custom agents](references/agents-custom.md), [deployment](references/agents-deployment.md).
-   [Middleware](references/middleware.md): using middleware and the `@genkit-ai/middleware` package. See also [building custom middleware](references/middleware-custom.md).
-   [Observability](references/observability.md): `@genkit-ai/otel` (OpenTelemetry GenAI semantic conventions), custom `Instrumentation`, and the reflection API outside dev.
-   [A2UI (Generative UI)](references/a2ui.md): the `@genkit-ai/a2ui` plugin (the `a2ui()` middleware), options, client rendering, user actions/forms, custom catalogs, and security.
