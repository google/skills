# Agent Human-in-the-Loop / Interrupts (Experimental)

> **Experimental / preview API.** Read [agents.md](agents.md) first. The
> resumable tool API below requires Genkit Go v1.14.0+.

An **interrupt** pauses an agent mid-turn and hands control back to your code
(or
a human), e.g. to approve a sensitive action, collect missing input, or confirm
a plan. Internally it's a **tool call used as control flow**: the interrupting
tool does not produce a normal result; it pauses the turn. You then **resume**
from the exact point it paused.

Interrupts are **orthogonal to persistence**: they work the same whether the
agent uses a [session store](agents-sessions.md) or
[client-managed state](agents.md#client-managed-vs-server-managed-state). The
paused turn just needs to be carried back into the resume: with a store the
session/snapshot ID does it; without one you round-trip the state blob.

The tool side is identical to plain `Generate` (see [tools.md](tools.md)):
`genkit.DefineResumableTool`, `tool.Interrupt`, and the claim through the tool's
`Interrupted` method. Only the delivery differs: an agent takes the resume parts
in an `aix.ToolResume` via `conn.SendResume` or `AgentInput.Resume`.

- [Define a resumable tool](#define-a-resumable-tool): Lines 31-102
- [Detect, claim, and resume (streaming connection)](#detect-claim-and-resume-streaming-connection): Lines 104-167
- [Single-turn resume with Run](#single-turn-resume-with-run): Lines 169-192
- [Notes and gotchas](#notes-and-gotchas): Lines 194-213

---

## Define a resumable tool

`genkit.DefineResumableTool[In, Out, Res]` defines a tool that can pause by
returning `tool.Interrupt(ctx, data)`. `Res` is what the caller sends back; it
arrives as the `*Res` parameter, `nil` on the first call.

```go
import (
	"context"
	"fmt"

	"github.com/firebase/genkit/go/ai"
	aix "github.com/firebase/genkit/go/ai/exp"
	"github.com/firebase/genkit/go/ai/exp/localstore"
	"github.com/firebase/genkit/go/ai/tool"
	"github.com/firebase/genkit/go/genkit"
	genkitx "github.com/firebase/genkit/go/genkit/exp"
)

type TransferInput struct {
	Amount    float64 `json:"amount"`
	ToAccount string  `json:"toAccount"`
}
type TransferOutput struct {
	Success       bool   `json:"success"`
	TransactionID string `json:"transactionId,omitempty"`
}

// ApprovalAsk is the data the tool pauses with.
type ApprovalAsk struct {
	Details string `json:"details"`
}

// ApprovalReply is the resume type the caller answers with.
type ApprovalReply struct {
	Approved bool   `json:"approved"`
	Feedback string `json:"feedback,omitempty"`
}

transferMoney := genkit.DefineResumableTool(g, "transferMoney",
	"Transfer money to a specified account, pausing for user approval.",
	func(ctx context.Context, in TransferInput, reply *ApprovalReply) (TransferOutput, error) {
		if reply == nil {
			// First call: pause and surface the request to the caller.
			return TransferOutput{}, tool.Interrupt(ctx, ApprovalAsk{
				Details: fmt.Sprintf("Transfer $%.2f to %s", in.Amount, in.ToAccount),
			})
		}
		if !reply.Approved {
			return TransferOutput{Success: false}, nil
		}
		return TransferOutput{Success: true, TransactionID: "txn-123"}, nil
	},
)

bankingAgent := genkitx.DefineAgent(g, "bankingAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a banking assistant. Use transferMoney to move funds; it will pause for user approval."),
		ai.WithTools(transferMoney),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

`tool.Interrupt` data must serialize to a JSON object (a struct or map) or be
`nil`. The resume type must be a struct or map too.

Returning an ordinary Go `error` from the tool is different: it **fails the
turn** rather than pausing it (wrapped as `ai.ErrToolFailed`). Return
`tool.Fail(ctx, err)` instead when the model should see the error and retry; see
[tools.md](tools.md#errors-the-model-can-fix).

## Detect, claim, and resume (streaming connection)

Collect interrupt parts from the stream with `chunk.ModelChunk.Interrupts()`,
claim each with the tool's `Interrupted` method (it decodes the input to `In`),
read the pause data with `ai.InterruptAs[T]`, and resume with `aix.ToolResume`.

```go
conn, err := bankingAgent.Connect(ctx)
if err != nil {
	return err
}
_ = conn.SendText("Transfer $500 to my savings account.")

var interrupts []*ai.Part
for chunk, err := range conn.Receive() {
	if err != nil {
		return err
	}
	if chunk.ModelChunk != nil {
		interrupts = append(interrupts, chunk.ModelChunk.Interrupts()...)
	}
	if chunk.TurnEnd != nil {
		break
	}
}

var restart []*ai.Part
for _, part := range interrupts {
	call, ok := transferMoney.Interrupted(part)
	if !ok {
		return fmt.Errorf("no handler for interrupt from tool %q", part.ToolRequest.Name)
	}
	ask, _ := ai.InterruptAs[ApprovalAsk](part)
	fmt.Println(ask.Details, call.Input.Amount) // show this to the human
	restart = append(restart, call.Restart(ApprovalReply{Approved: true}))
}

// Resume the same connection, then receive the continuation.
_ = conn.SendResume(&aix.ToolResume{Restart: restart})
for chunk, err := range conn.Receive() {
	if err != nil {
		return err
	}
	if chunk.ModelChunk != nil {
		fmt.Print(chunk.ModelChunk.Text())
	}
	if chunk.TurnEnd != nil {
		break
	}
}
out, _ := conn.Output()
```

### Respond vs. Restart

| Verb | Goes in | Effect |
| --- | --- | --- |
| `call.Restart(res)` | `aix.ToolResume{Restart: ...}` | Re-runs the tool with the typed resume value. |
| `call.RestartWithInput(in, res)` | `aix.ToolResume{Restart: ...}` | Re-runs it with revised input. |
| `call.Respond(out)` | `aix.ToolResume{Respond: ...}` | Supplies the tool's output; the tool does not run again. |

Both lists may appear in one payload. The claim already type-checked the part,
so
the verbs return no error.

## Single-turn resume with `Run`

You don't need a persistent connection. Detect the interrupt on one `Run`, then
resume with another `Run` carrying the `Resume` payload plus the session source.

```go
out, _ := bankingAgent.RunText(ctx, "Transfer $500 to savings.")
if out.FinishReason == aix.AgentFinishReasonInterrupted {
	var restart []*ai.Part
	for _, part := range out.Message.Content {
		if call, ok := transferMoney.Interrupted(part); ok {
			restart = append(restart, call.Restart(ApprovalReply{Approved: true}))
		}
	}
	out, _ = bankingAgent.Run(ctx,
		&aix.AgentInput{Resume: &aix.ToolResume{Restart: restart}},
		aix.WithSessionID[any](out.SessionID), // server-managed: carry the paused turn back
	)
}
fmt.Println(out.Message.Text())
```

For a client-managed agent, pass `aix.WithState(out.State)` instead of
`WithSessionID`. Over HTTP the same object rides in `data.resume`.

## Notes and gotchas

- **No store required.** Interrupts work with a
  [session store](agents-sessions.md)
  or [client-managed state](agents.md#client-managed-vs-server-managed-state).
- **Build resume parts from the claim.** The framework validates every entry
  against the most recent model response (name/ref must match). Hand-rolled
  parts, or parts from an earlier turn, are rejected.
- **Answer every interrupt** in the turn, or the resume fails.
- **Resumable snapshots.** `completed`, `failed`, and `aborted` snapshots resume
  (failed/aborted ones hold the conversation up to the last completed tool
  round).
  `pending` and `aborting` ones are rejected until they settle.
- **Re-pausing.** After resuming, the turn may interrupt again; loop until the
  finish reason is no longer `aix.AgentFinishReasonInterrupted`.
- **`ToolApproval` middleware.** To gate arbitrary tools (rather than writing a
  resumable tool by hand), `plugins/middleware`'s `ToolApproval` holds any tool
  call outside an allowlist. Claim holds with
  `middleware.ToolApprovalInterrupted`.
  See [middleware](middleware.md).
