---
name: developing-genkit-python
description: >-
  Provides guidance on developing AI-powered applications using Genkit Python
  (0.13) and migrating Genkit Python 0.12 projects to 0.13. Use when building AI
  agents, flows, tools, structured outputs, or FastAPI routes in Python,
  upgrading from Genkit 0.12, or debugging Genkit imports, config errors, or
  traces. Don't use for Genkit in JavaScript/TypeScript, Go, or Dart.
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

# Genkit Python

Build AI features in Python — generation, structured output, streaming, tools,
flows, and multi-turn agents — with Genkit Python 0.13.

- **New project?** See [Setup](references/setup.md) and
  [Examples](references/examples.md).
- **Upgrading from 0.12 or fixing broken 0.12 imports/signatures?** Read
  [Migrating from 0.12 to 0.13](references/migrating-from-0.12.md) first.

## Prerequisites

- Python **3.10+** and **`uv`**
  ([install](https://docs.astral.sh/uv/getting-started/installation/))
- Genkit CLI: `npm install -g genkit-cli` if `genkit --version` is missing

## Hello World

```python
from genkit import Genkit
from genkit_google_genai import GoogleAI

ai = Genkit(
    plugins=[GoogleAI()],
    model=GoogleAI.gemini('gemini-flash-latest'),
)


async def main() -> None:
    response = await ai.generate(prompt='Suggest one seasonal pasta dish.')
    if response.error:
        raise RuntimeError(response.error.message)
    print(response.text)
    # => Lemony tagliatelle with asparagus, sweet peas, and herb ricotta


if __name__ == '__main__':
    ai.run_main(main())
```

`ai.generate` does not raise when the provider rejects or fails a call
(`INVALID_ARGUMENT`, `UNAVAILABLE`, rate limits). It returns `response.error`
(`Failure` with `.status` and `.message`), `finish_reason == 'failed'`, and
empty text. Problems caught before the call raise: `GoogleAI()` raises
`ValueError` without `GEMINI_API_KEY`; an unknown model, invalid key, or unknown
config field raises `GenkitError`. See
[Common Errors](references/common-errors.md).

## Agents (Experimental)

Multi-turn chats with history, typed state, human approval, branching, and
background work live under `genkit.exp` and `genkit.exp.agent`. Start here:
[Agents](references/agents.md).

```python
from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()], model=GoogleAI.gemini('gemini-flash-latest'))
agent = ai.define_agent(
    name='concierge',
    system='You are a concise hotel concierge.',
    store=InMemorySessionStore(),
)

chat = agent.chat()
res = await chat.send('Recommend a quiet dinner spot.')  # AgentResponse
print(res.text)
# => Try Osteria Lume on 5th; it has booths and low music.

turn = chat.send_stream('Is it open past 10pm?')  # AgentTurn
async for chunk in turn.stream:
    if chunk.text:
        print(chunk.text, end='')
final = await turn.response  # AgentResponse
```

More: [sessions](references/agents-sessions.md) ·
[HITL](references/agents-human-in-the-loop.md) ·
[branching](references/agents-branching.md) ·
[background](references/agents-background.md) ·
[state](references/agents-state.md) ·
[artifacts](references/agents-artifacts.md) ·
[custom](references/agents-custom.md) ·
[HTTP](references/agents-http.md)

## Imports

Every symbol lives in one public module (never import private `_` submodules;
see [Migrating from 0.12 to 0.13](references/migrating-from-0.12.md) if a 0.12
symbol moved):

- **Core app**: `from genkit import Genkit, FlowContext, ToolContext, Message, Part, Role, Media, Document, MultipartToolResponse, PublicError, GenkitError, Failure, ErrorReason`
- **Google GenAI & Vertex AI**: `from genkit_google_genai import GoogleAI, VertexAI, GeminiConfig, GeminiImageConfig, GeminiTtsConfig`
- **Other providers**: `from genkit_vertexai import ModelGarden` ·
  `from genkit_anthropic import Anthropic, AnthropicConfig` ·
  `from genkit_openai import OpenAI, OpenAIConfig` ·
  `from genkit_ollama import Ollama, OllamaConfig` ·
  `from genkit_amazon_bedrock import Bedrock, BedrockConfig`
- **Built-in middleware**: `from genkit_middleware import Middleware, Retry, Fallback, ToolApproval, Skills, Filesystem` (plus `from genkit_middleware.exp import Artifacts` for agent sessions)
- **Writing custom middleware**:
  `from genkit.middleware import Middleware, MiddlewareContext`
- **FastAPI & HTTP**:
  `from genkit_fastapi import serve_flow, genkit_fastapi_handler,
  handle_genkit_request` · `from genkit_fastapi.exp import serve_agent` ·
  `from genkit.web import RequestData, to_sse, error_body, error_status`
- **Agents (experimental)**: `from genkit.exp import Genkit, current_session` · `from genkit.exp.agent import Agent, Session, InMemorySessionStore, FileSessionStore, remote_agent`
- **Telemetry**: `from genkit_google_cloud import enable_google_cloud_telemetry`
  · `from genkit.telemetry import configure_instrumentation` ·
  `from genkit_otel import GenAiInstrumentation`
- **MCP (Client & Host)**: `from genkit_mcp import define_mcp_client, define_mcp_host, McpClient, McpHost`
- **Testing & Mocks**: `from genkit.testing import define_echo_model, define_scripted_model, EchoModel, ScriptedModel`
- **Evaluators (0.13 only; cut from 1.0, additive later)**:
  `from genkit_evaluators import register_genkit_evaluators` ·
  `from genkit.evaluator import BaseDataPoint, EvaluatorResponse, Score,
  ScoreDetails, ScoreStatus`

## Workflow

1. **Agent or flow?** Use `ai.define_agent` (on `genkit.exp.Genkit`, see
   [Agents](references/agents.md)) for multi-turn chats, state, or
   human-in-the-loop approval instead of hand-rolling a message loop inside a
   flow. Use `@ai.flow()` on `genkit.Genkit` for stateless request/response or
   streaming pipelines.
2. **Configure credentials & model refs.** Set **`GEMINI_API_KEY`**. Prefer
   typed refs (`GoogleAI.gemini('gemini-flash-latest')`) and typed flat configs
   (`GeminiConfig(...)`) so your type checker validates fields before runtime.
   Prefixed strings (`'googleai/gemini-flash-latest'`) also work.
3. **Enter via `ai.run_main(main())`** for standalone scripts and CLI apps so
   the process stays up for the Dev UI under `genkit start`. FastAPI apps skip
   `run_main`; uvicorn keeps the process alive:
   `genkit start -- uv run uvicorn main:app --reload`.
4. **Run with [Dev Workflow](references/dev-workflow.md)** (`genkit start` + Dev
   UI) and type-check with `pyright`, `mypy`, or `ty`.
5. **Verify with traces**, not a blind `uv run`. See
   [Genkit CLI](#genkit-cli-recommended).
6. **Stuck?** Check [Gotchas](#gotchas),
   [Common Errors](references/common-errors.md), or
   [Migrating from 0.12 to 0.13](references/migrating-from-0.12.md).

## Gotchas

- **Agents need `genkit.exp`**: `from genkit.exp import Genkit`. Stable
  `genkit.Genkit` has no `define_agent`.
- **Tools are async**: `@ai.tool()` raises `TypeError` on a plain `def`; use
  `async def`.
- **Check `response.error`**: provider failures come back on the response, not
  as exceptions (see [Hello World](#hello-world)).
- **Gemini thinking levels**: `GeminiConfig(thinking_level='MINIMAL')` fails on
  `gemini-flash-latest`; use `'LOW'`, `'MEDIUM'`, or `'HIGH'`.
- **Vertex AI model IDs**: Vertex does not serve `-latest` aliases. Pass a
  pinned model ID to `VertexAI.gemini(...)`.
- **Logging**: `genkit.get_logger` is structlog-based.
  `enable_google_cloud_telemetry()` injects trace context for GCP log-trace
  correlation.
- **Cloud telemetry auth**: call `enable_google_cloud_telemetry()` with
  Application Default Credentials or explicit `credentials=` (service account
  dict or `Credentials` instance).

## Genkit CLI (recommended)

`genkit start` wraps any Python program that uses Genkit, capturing traces from
every action while forwarding stdio cleanly. Running `uv run` directly skips
trace capture.

**Primary pattern (persistent server + Dev UI):**
```bash
genkit start -- uv run src/main.py
genkit start --noui -- uv run src/main.py   # persistent runtime without opening the Dev UI
```
`genkit start` runs until stopped with Ctrl+C (even with `--noui`). Do **not**
run `genkit start` as a blocking step in automated/non-interactive scripts; use
`flow:run` instead.

**Non-interactive use (agents/CI):** pass `--non-interactive` before `--` so the
CLI never blocks on prompts:
```bash
genkit start --non-interactive -- uv run src/main.py
```

**One-shot flow execution (`flow:run`):** spins up the runtime, invokes one
`@ai.flow()` by name, prints a `Trace ID`, and exits:
```bash
genkit flow:run myFlow '{"data": "input"}' -- uv run src/main.py
```
Note: `flow:run` invokes flows (`@ai.flow()`), not agents (`ai.define_agent`).
Wrap a single agent turn in a helper flow to exercise it via `flow:run` (see
[Agents](references/agents.md)).

**Inspecting traces:**
```bash
genkit trace:list                        # list recent trace IDs
genkit trace:get <traceId>               # human-readable trace inspection
genkit trace:get <traceId> --format json # machine-readable JSON for jq / scripts
```
Always pass `--format json` when piping into `jq` or other parsers.

See [Dev Workflow](references/dev-workflow.md) for the full pre-run checklist
and Dev UI walkthrough.

## References

- [Migrating from 0.12 to 0.13](references/migrating-from-0.12.md):
  Deterministic 0.12 -> 0.13 renames, config flattening, `PublicError`, and
  `exp` moves.
- [Examples](references/examples.md): Structured output, streaming, media parts,
  flows, tools, interrupts, cancellation, embeddings.
- [Setup](references/setup.md): Project bootstrap with `uv`, version alignment,
  and provider plugins.
- [Common Errors](references/common-errors.md): Fast fixes for 0.13 validation
  errors, HTTP 500 redaction, streaming, and sessions.
- [FastAPI](references/fastapi.md): `serve_flow`, `serve_agent`, `PublicError`,
  SSE streaming, and parallel flows.
- [Dotprompt](references/dotprompt.md): `.prompt` files, schema validation,
  variants, partials, and helpers.
- [Evals](references/evals.md): 0.13 evaluator syntax (deprecated; removed in
  1.0).
- [Dev Workflow](references/dev-workflow.md): `genkit start`, Dev UI, and trace
  verification checklist.
- [Agents (Experimental)](references/agents.md): Multi-turn stateful agents
  (`genkit.exp`).
