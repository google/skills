# Agent Human-in-the-Loop / Interrupts (Experimental)

> See [agents.md](agents.md) · [sessions](agents-sessions.md).

An interrupt pauses an agent mid-turn so a human or policy check can inspect the
pending tool call, then resume execution. Interrupts work both with a store
(across separate HTTP requests) and without a store (in-process or round-tripped
client state).

Turn lifecycle: `chat.send(...)` ->
`res.finish_reason == AgentFinishReason.INTERRUPTED` with `res.interrupts` ->
human decision -> `chat.resume(...)` / `chat.resume_stream(...)`.

- [Gate tools with ToolApproval](#gate-tools-with-toolapproval): Lines 20-69
- [Detect and resume (restart vs respond)](#detect-and-resume-restart-vs-respond): Lines 71-138
- [Custom tool interrupts and Interrupt (BaseException)](#custom-tool-interrupts-and-interrupt-baseexception): Lines 140-187

---

## Gate tools with `ToolApproval`

`ToolApproval(allowed_tools=[...])` lets listed tools execute immediately and
interrupts all other tool calls. An empty list requires approval for every tool.
When pairing `ToolApproval` with `Filesystem` or `Artifacts`, list read-only
tools (`list_files`, `read_file`, `read_artifact`) in `allowed_tools` if only
writes (`write_file`, `edit_file`, `write_artifact`) should pause.

```python
from uuid import uuid4
from genkit_google_genai import GoogleAI
from genkit_middleware import Middleware, ToolApproval
from pydantic import BaseModel, Field

from genkit import Part
from genkit.exp import Genkit
from genkit.exp.agent import AgentFinishReason, InMemorySessionStore


class TransferInput(BaseModel):
    amount: float
    to_account: str = Field(alias='toAccount')

    model_config = {'populate_by_name': True}


class TransferOutput(BaseModel):
    success: bool
    transaction_id: str = Field(alias='transactionId')

    model_config = {'populate_by_name': True}


ai = Genkit(plugins=[GoogleAI(), Middleware()])


@ai.tool(name='transferMoney', description='Transfer money between accounts.')
async def transfer_money(input: TransferInput) -> TransferOutput:
    return TransferOutput(success=True, transactionId=f'txn-{uuid4().hex[:12]}')


agent = ai.define_agent(
    name='bankingAgent',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='Banking assistant. Call transferMoney when the user asks to transfer money.',
    tools=[transfer_money],
    use=[ToolApproval(allowed_tools=[])],
    store=InMemorySessionStore(),
)
```

## Detect and resume (`restart` vs `respond`)

Each entry in `res.interrupts` is an `AgentInterrupt` exposing `.name`, `.ref`,
and `.input` for rendering your approval UI, plus two methods that build `Part`
objects for `chat.resume(...)`:

- **`intr.restart(resumed_metadata={'tool_approved': True})`**: re-runs the
  interrupted tool on the server (`ctx.is_resumed()` becomes `True`).
  `ToolApproval` checks `tool_approved` (or `toolApproved`) in
  `resumed_metadata`. Restart inputs must exactly match the original tool
  request in session history; a forged or modified restart returns a failed turn
  (`AgentFinishReason.FAILED`, `res.error.status == 'INVALID_ARGUMENT'`) instead
  of running the tool.
- **`intr.respond(output)`**: builds a tool response `Part` without executing
  the tool. Use this to deny an action (e.g.
  `intr.respond({'ok': False, 'error': 'declined by user'})`) or answer a
  prompt-style interrupt created with `ai.define_interrupt(...)`.

A resumed turn can call more tools that also need approval, so loop until the
turn stops interrupting:

```python
async def main() -> None:
    chat = agent.chat()

    # 1. Turn pauses before transferMoney executes
    res = await chat.send('Transfer $500 to account 12345 for rent.')

    # 2. Approve pending interrupts until the turn finishes
    while res.finish_reason == AgentFinishReason.INTERRUPTED:
        for intr in res.interrupts:
            print(f'Approving {intr.name}: {intr.input}')
            # => Approving transferMoney: {'amount': 500, 'toAccount': '12345'}
        restart_parts: list[Part] = [
            intr.restart(resumed_metadata={'tool_approved': True})
            for intr in res.interrupts
        ]
        res = await chat.resume(restart=restart_parts)

    # 3. Read the final reply (check res.error if the turn failed)
    print(res.finish_reason, res.text)
    # => stop $500 has been successfully transferred to account 12345.


if __name__ == '__main__':
    ai.run_main(main())
```

Denials and streaming resumes use the same parts (`res` is an interrupted turn):

```python
# Deny without executing the tool:
denied = await chat.resume(
    respond=[intr.respond({'ok': False, 'error': 'transfer declined'}) for intr in res.interrupts],
)

# Or approve and stream the resumed turn:
turn = chat.resume_stream(
    restart=[intr.restart(resumed_metadata={'tool_approved': True}) for intr in res.interrupts],
)
async for chunk in turn.stream:
    if chunk.text:
        print(chunk.text, end='', flush=True)
final = await turn.response
```

Without a store, keep the same `chat` instance or round-trip `messages`,
`state`, and `artifacts` ([without a store](agents.md#without-a-store)).

## Custom tool interrupts and `Interrupt` (`BaseException`)

For domain-specific thresholds (such as only pausing transfers above `$1,000`),
raise `Interrupt` directly inside a tool or register a dedicated prompt tool
with `ai.define_interrupt(...)`:

- **`Interrupt` subclasses `BaseException`**, not `Exception` (like
  `asyncio.CancelledError`). A `try ... except Exception:` block inside a tool
  will **not** swallow an `Interrupt` and accidentally let execution proceed
  without approval. Only catch `Interrupt` explicitly if intended, and always
  re-raise it.
- Read `ctx.is_resumed()` and `ctx.resumed_metadata` on `ToolContext` when the
  caller resumes with `intr.restart(resumed_metadata=...)`. The keys are yours:
  the tool below expects `intr.restart(resumed_metadata={'approved': True})`.

```python
from genkit import Interrupt, ToolContext


@ai.tool(name='wireTransfer', description='Send an external wire transfer.')
async def wire_transfer(input: TransferInput, ctx: ToolContext) -> dict[str, object]:
    if input.amount > 1000 and not ctx.is_resumed():
        # BaseException: an `except Exception:` block can't swallow it
        raise Interrupt({'reason': 'high_value_transfer', 'amount': input.amount})

    if ctx.is_resumed() and not (ctx.resumed_metadata or {}).get('approved'):
        return {'ok': False, 'status': 'rejected'}

    return {'ok': True, 'amount': input.amount, 'to': input.to_account}
```

For pure question/confirmation tools that never run server logic themselves, use
`ai.define_interrupt(...)` and resume with `intr.respond(...)`:

```python
class ConfirmInput(BaseModel):
    action: str
    summary: str


ask_confirmation = ai.define_interrupt(
    name='askConfirmation',
    description='Ask the user to confirm before irreversible actions.',
    input_schema=ConfirmInput,
)
# Add to the agent's tools=[...], then answer with:
# chat.resume(respond=[intr.respond({'confirmed': True}) for intr in res.interrupts])
```
