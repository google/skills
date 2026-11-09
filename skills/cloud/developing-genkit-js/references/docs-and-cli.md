# Genkit Documentation & CLI

This reference lists common tasks and workflows using the `genkit` CLI. For
authoritative command details, always run `genkit --help` or
`genkit <command> --help`.

- [Prerequisites:](#prerequisites): Lines 16-21
- [Documentation](#documentation): Lines 23-30
- [Development Workflow (recommended)](#development-workflow-recommended): Lines 32-68
- [Flow Execution (secondary)](#flow-execution-secondary): Lines 70-93
- [Evaluation](#evaluation): Lines 95-115
- [Tracing](#tracing): Lines 117-132

---

## Prerequisites:

Ensure that the CLI is on `genkit-cli` version >= 1.29.0. If not, or if an older
version (1.x < 1.29.0) is present, update the Genkit CLI version. Alternatively,
to run commands with a specific version or without global installation, prefix
them with `npx -y genkit-cli@^1.29.0`.

## Documentation

-   **Search docs**: `genkit docs:search <query>`
    -   Example: `genkit docs:search "streaming"`
    -   Example: `genkit docs:search "rag retrieval"`
-   **Read doc**: `genkit docs:read <path>`
    -   Example: `genkit docs:read js/overview.md`
-   **List docs**: `genkit docs:list`

## Development Workflow (recommended)

`genkit start` unintrusively wraps any Node.js program that uses the Genkit
library, running it unchanged while capturing traces from every Genkit action so
you can prove tools were actually called and inspect model I/O from the
terminal, even for headless checks. It forwards stdio, so interactive CLI tools
that rely on stdin/stdout work without issues. Running your app directly
(`node`/`tsx`/`npm start`) skips trace capture, so you're debugging blind.

**Primary pattern (default):** prefix `genkit start --` to your normal run
command. This collects telemetry from any Genkit code your program runs, whether
triggered from the dev UI, your own web server/web UI, or a plain script:

-   **Node.js (TypeScript)**:
    ```bash
    genkit start -- npx tsx --watch src/index.ts
    ```
-   **Next.js**:
    ```bash
    genkit start -- npx next dev
    ```
-   **Without the Dev UI** (still a persistent server):
    ```bash
    genkit start --noui -- npx tsx src/index.ts
    ```

`genkit start` runs until you stop it with Ctrl+C. That is expected and correct
for the common cases: a server your web/mobile app calls, or an interactive CLI
you exit yourself. `--noui` only drops the Dev UI; it is **not** a one-shot
command and will not exit on its own. Do **not** use `genkit start` as a
blocking step in automated/non-interactive contexts; use `flow:run` (below) for
that.

For non-interactive/agent/CI use, add the global `--non-interactive` flag before
`--` so the CLI uses defaults and never blocks on a prompt (e.g. the first-run
analytics notice), e.g.
`genkit flow:run myFlow '<input>' --non-interactive -- npx tsx src/index.ts`.

## Flow Execution (secondary)

-   **Run a flow**: `genkit flow:run <flowName> '<inputJSON>' -- <run cmd>`
    -   Invokes a specific flow by name from the CLI. Append your run command
        after `--` to spin up the runtime for this run (the command runs as-is
        to register your flows): it runs once, prints a `Trace ID`, then exits,
        so it's the right choice for a quick, non-interactive check that must
        self-terminate (unlike `genkit start`). Note: `flow:run` runs **flows**
        (`ai.defineFlow`), not agents; you can't `flow:run` an agent
        (`ai.defineAgent`) directly. To verify an agent, wrap one turn in a
        throwaway flow and run that. Traces for the run can be inspected with
        the tracing commands below.
    -   **Always pass input JSON explicitly.** `flow:run` sends `undefined` when
        the input is omitted and does **not** fall back to a schema
        `.default()`, so a flow with a defaulted input will fail validation
        unless you pass the value.
    -   **Simple Input**:
        ```bash
        genkit flow:run tellJoke '"chicken"' -- npx tsx src/index.ts
        ```
    -   **Object Input**:
        ```bash
        genkit flow:run generateStory '{"subject": "robot", "genre": "sci-fi"}' -- npx tsx src/index.ts
        ```

## Evaluation

-   **Evaluate a flow**: `genkit eval:flow <flowName> [data] -- <run cmd>`
    -   Runs a flow and evaluates the output against configured evaluators. As
        with `flow:run`, append your run command after `--` to spin up the
        runtime for the run.
    -   **Example (Single Input)**:
        ```bash
        genkit eval:flow answerQuestion '[{"testCaseId": "1", "input": {"question": "What is Genkit?"}}]' -- npx tsx src/index.ts
        ```
    -   **Example (Batch Input)**:
        ```bash
        genkit eval:flow answerQuestion --input inputs.json -- npx tsx src/index.ts
        ```

-   **Run Evaluation**: `genkit eval:run <dataset>`
    -   Evaluates a dataset against configured evaluators.
    -   **Example**:
        ```bash
        genkit eval:run dataset.json --output results.json
        ```

## Tracing

-   **Get a trace**: `genkit trace:get <traceId>`
    -   Retrieves detailed information for a specific trace by its ID. This is
        particularly useful for debugging failed model calls, inspecting tool
        execution, or analyzing the exact inputs and outputs of a specific step
        in your flow.
    -   **Machine-readable output**: add `--format json` (e.g.
        `genkit trace:get <traceId> --format json`) to get clean JSON you can
        pipe into `jq` or other parsers.
-   **List traces**: `genkit trace:list [options]`
    -   Lists recent traces. Use this to find trace IDs from recent executions.
-   **Piping to parsers**: the **default** trace output is human-oriented (extra
    banner/log lines, possible truncation on large traces), so don't pipe that
    form directly into `jq`. Use `--format json` for clean JSON, or the Dev UI
    trace viewer (`genkit start`) for complex traces.

