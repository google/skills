# Dev Workflow — Genkit Python

- [Agent Responsibility](#agent-responsibility): Lines 14-30
- [Step 1: Get a Gemini API Key](#step-1-get-a-gemini-api-key): Lines 34-37
- [Step 2: Export the API Key](#step-2-export-the-api-key): Lines 41-51
- [Step 3: Install Dependencies](#step-3-install-dependencies): Lines 55-65
- [Step 4: Start the Dev UI](#step-4-start-the-dev-ui): Lines 69-114
- [Step 5: Test in the Dev UI](#step-5-test-in-the-dev-ui): Lines 118-130
- [CLI Commands](#cli-commands): Lines 134-182
- [Troubleshooting](#troubleshooting): Lines 186-194

---

## Agent Responsibility

After generating or migrating code:

1. Run the project's type checker (`pyright`, `mypy`, or `ty`) in `.venv` so
   typed configs (`GeminiConfig`), generic contexts (`FlowContext[T]`,
   `ToolContext[T]`), keyword-only signatures, and `OutputT | None` checks pass
   before handing off.
2. Give the developer:
   - Copy-paste setup commands with absolute paths
   - The `genkit start` command to run in their foreground terminal (expected to
     block)
   - Exact Dev UI steps to exercise the flow or agent and inspect traces

Do not run `genkit start` as an interactive blocking command on the developer's
behalf unless explicitly asked; use `genkit flow:run` for automated one-shot
verification.

---

## Step 1: Get a Gemini API Key

If the developer needs a key, create one at
`https://aistudio.google.com/apikey`.

---

## Step 2: Export the API Key

```bash
export GEMINI_API_KEY=your-api-key-here
```

Persist across shell sessions if desired:

```bash
echo 'export GEMINI_API_KEY=your-api-key-here' >> ~/.zshrc && source ~/.zshrc
```

---

## Step 3: Install Dependencies

Replace `/path/to/your-project` with the project's absolute path:

```bash
cd /path/to/your-project
uv add 'genkit==0.13.*' 'genkit-google-genai==0.13.*'
```

(Run `uv init` first if `pyproject.toml` does not exist yet — see
[Setup](setup.md).)

---

## Step 4: Start the Dev UI

The examples below use this `src/main.py`:

```python
from pydantic import BaseModel

from genkit import Genkit

ai = Genkit()


class OrderInput(BaseModel):
    text: str


@ai.flow()
async def order_flow(inp: OrderInput) -> str:
    return f'order: {inp.text}'


async def main() -> None:
    print(await order_flow(OrderInput(text='smoked salmon tartine')))


if __name__ == '__main__':
    ai.run_main(main())
    # => order: smoked salmon tartine
    #    Under `genkit start`, the process stays up for the Dev UI until Ctrl+C.
```

Run in a foreground terminal (blocks until stopped with `Ctrl+C`):

```bash
cd /path/to/your-project
GEMINI_API_KEY=your-api-key-here genkit start -- uv run src/main.py
```

For FastAPI apps, run uvicorn under `genkit start` instead; the reflection
server starts on a background thread (see [FastAPI](fastapi.md)):

```bash
GEMINI_API_KEY=your-api-key-here genkit start -- uv run uvicorn main:app --reload
```

Wait for the CLI to print `Genkit Developer UI: http://localhost:4000`.

---

## Step 5: Test in the Dev UI

1. Open **`http://localhost:4000`** in a browser.
2. Pick the registered flow, prompt, or model from the left sidebar. Flows
   appear under their Python function name (e.g. `order_flow`).
3. Paste JSON matching the flow's single input parameter, e.g. for
   `order_flow(inp: OrderInput)`:
   ```json
   {"text": "smoked salmon tartine"}
   ```
4. Click **Run** and inspect the validated output on the right.
5. Open **Traces** in the left sidebar to inspect every span, rendered prompt,
   tool call, token count, latency, and unwrapped error stack trace.

---

## CLI Commands

`genkit start` sets `GENKIT_ENV=dev`, runs your command, and stores local traces
from every Genkit action under `.genkit/` in the project root. The app's stdout
and stderr pass through. Running `uv run` directly skips the reflection server
and local trace capture.

**Persistent dev runtime:**
```bash
genkit start -- uv run src/main.py
genkit start --noui -- uv run src/main.py                 # no Dev UI; runtime still blocks until Ctrl+C
genkit start --non-interactive -- uv run src/main.py      # CLI prompts take the default choice (CI/agents)
genkit start --port 4001 -- uv run src/main.py            # Dev UI on another port
```

**One-shot flow execution (`flow:run`):** with `-- <cmd>`, it starts the app,
runs one `@ai.flow()` by its Python function name, prints `Result:` and
`Trace ID:`, and exits:
```bash
genkit flow:run order_flow '{"text": "smoked salmon tartine"}' -- uv run src/main.py
# => Result:
#    order: smoked salmon tartine
#    Trace ID: 395f73c3d0d662c28711239a4354bf53
```
Without `-- <cmd>`, `flow:run` targets a runtime already started by
`genkit start` in the same directory, and fails with `No runtimes found` if none
is running. A `str` input is a JSON string: `'"risotto"'`.

`flow:run` runs `@ai.flow()` actions, not agents. Wrap one agent turn in a small
flow to test it (see [Agents](agents.md#verify-an-agent-from-the-cli-flowrun)).

**Inspecting traces from the terminal:**
```bash
genkit trace:list --limit 5     # recent trace IDs with status, input, output
genkit trace:get <traceId>      # full trace as JSON: every span, attributes, input, output
```
`trace:get` prints a `Telemetry API running on ...` line before the JSON on
stdout, so strip it before piping into `jq`:
```bash
genkit trace:get <traceId> | sed 1d | jq -r '.spans[].displayName'
# => order_flow
```

**Built-in CLI documentation lookup:**
```bash
genkit docs:search "streaming" python
genkit docs:list python
genkit docs:read python/flows.md
```

---

## Troubleshooting

- `genkit: command not found` — `npm install -g genkit-cli`
- `GEMINI_API_KEY` missing — `export GEMINI_API_KEY=your-key`
- Port 4000 busy — `genkit start --port 4001 -- uv run src/main.py`
- `uv: command not found` — `pipx install uv` or `pip install uv`
- Action missing in Dev UI — ensure standalone scripts enter via
  `ai.run_main(main())` and check terminal output for startup import or
  validation errors (see [Common Errors](common-errors.md)).
