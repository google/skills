# Tools

- [DefineTool](#definetool): Lines 10-31
- [Using Tools in Generation](#using-tools-in-generation): Lines 33-61
- [Tool runtime helpers (ai/tool)](#tool-runtime-helpers-aitool): Lines 63-116
- [Tool interrupts (DefineResumableTool)](#tool-interrupts-defineresumabletool): Lines 118-262

---

## DefineTool

Define a tool the model can call during generation.

```go
type WeatherInput struct {
	Location string `json:"location" jsonschema:"description=City name"`
}

type WeatherOutput struct {
	Temperature float64 `json:"temperature"`
	Conditions  string  `json:"conditions"`
}

weatherTool := genkit.DefineTool(g, "getWeather",
	"Gets the current weather for a location.",
	func(ctx *ai.ToolContext, input WeatherInput) (WeatherOutput, error) {
		// Call your weather API
		return WeatherOutput{Temperature: 72, Conditions: "sunny"}, nil
	},
)
```

## Using Tools in Generation

Pass tools to `Generate`, `GenerateText`, or prompts:

```go
resp, err := genkit.Generate(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("What's the weather in San Francisco?"),
	ai.WithTools(weatherTool),
)
// The model calls the tool automatically and incorporates the result
fmt.Println(resp.Text())
```

### Tool Choice

```go
ai.WithToolChoice(ai.ToolChoiceAuto)     // model decides (default)
ai.WithToolChoice(ai.ToolChoiceRequired) // model must use a tool
ai.WithToolChoice(ai.ToolChoiceNone)     // model cannot use tools
```

### Max Turns

Limit how many tool-call round trips the model can make:

```go
ai.WithMaxTurns(3) // default is 5
```

## Tool runtime helpers (`ai/tool`)

> Requires Genkit Go v1.14.0+.

Package `github.com/firebase/genkit/go/ai/tool` holds the verbs a tool (or a
`WrapTool` hook) calls. They take a `context.Context`, so they work from
`DefineTool` too (`*ai.ToolContext` embeds the context).

| Function | Use |
| --- | --- |
| `tool.Interrupt(ctx, data)` | Pause the call for the caller (see below). |
| `tool.Fail(ctx, err)` | Hand this error to the model as the tool's output so it can fix its input, instead of stopping the loop. |
| `tool.AttachParts(ctx, parts...)` | Attach media (images, etc.) to the result while keeping the tool's own output type. Replaces multipart tools. |
| `tool.SendChunk(ctx, chunk)` | Stream progress from a tool (set `Role: ai.RoleTool`). |
| `tool.OriginalInput[In](ctx)` | On a restart with revised input, the input the tool was first called with. |
| `tool.ResumeData[T](ctx)` | Read a resume payload untyped (for `WrapTool` hooks). |

```go
import "github.com/firebase/genkit/go/ai/tool"

screenshot := genkit.DefineTool(g, "screenshot", "Takes a screenshot of a page.",
	func(ctx *ai.ToolContext, in PageInput) (*PageInfo, error) {
		info, png, err := capture(ctx, in.URL)
		if err != nil {
			return nil, err
		}
		tool.AttachParts(ctx, ai.NewMediaPart("image/png", png)) // a data: URL
		return info, nil // still *PageInfo, so the model sees the real output schema
	})
```

`genkit.DefineMultipartTool` / `ai.MultipartToolResponse` are deprecated; use
`tool.AttachParts`.

### Errors the model can fix

By default a tool error stops the loop with `ai.ErrToolFailed`. Return
`tool.Fail` for errors the model can correct:

```go
query := genkit.DefineTool(g, "query", "Runs a read-only SQL query.",
	func(ctx *ai.ToolContext, in QueryInput) ([]string, error) {
		rows, err := runQuery(ctx, in.SQL)
		if errors.Is(err, errSyntax) {
			return nil, tool.Fail(ctx, err) // the model reads the error and fixes the query
		}
		return rows, err // a lost connection still stops the loop
	})
```

For tools you don't own (e.g. MCP tools), `&middleware.SoftToolErrors{}`
(optionally `Tools: []string{"search"}`) returns every tool error to the model.
See [middleware](middleware.md). A tool that panics fails with the message
`tool panicked` instead of crashing the process.

## Tool interrupts (`DefineResumableTool`)

Pause a tool call to get human input, then resume. Use
`genkit.DefineResumableTool`, whose third type parameter is the **resume type**:
what the caller answers with. The tool receives it as a pointer that is `nil` on
the first call.

> **Do not use** the deprecated `ai.InterruptWith`, `ToolContext.Interrupt`,
> `RestartWith`/`RespondWith`, `WithToolRestarts`/`WithToolResponses`,
> `ai.ResumedValue`, `IsResumed`, or `ai.OriginalInputAs`. The experimental
> `genkitx.DefineInterruptibleTool` and `ai/exp/tool` package were removed in
> v1.14.0.

### Define a resumable tool

```go
import (
	"context"

	"github.com/firebase/genkit/go/ai/tool"
	"github.com/firebase/genkit/go/genkit"
)

type TransferInput struct {
	ToAccount string  `json:"toAccount"`
	Amount    float64 `json:"amount"`
}

type TransferOutput struct {
	Status string `json:"status"`
}

// TransferInterrupt is extra data the tool reports when it pauses.
type TransferInterrupt struct {
	Reason string `json:"reason"`
}

// Confirmation is the resume type. Must be a struct or map (a JSON object).
type Confirmation struct {
	Approved bool `json:"approved"`
}

transferMoney := genkit.DefineResumableTool(g, "transferMoney",
	"Transfers money to another account.",
	func(ctx context.Context, in TransferInput, confirm *Confirmation) (*TransferOutput, error) {
		if confirm == nil && in.Amount > approvalLimit {
			// First call: pause. Data must serialize to a JSON object (or be nil).
			return nil, tool.Interrupt(ctx, TransferInterrupt{Reason: "over_limit"})
		}
		if confirm != nil && !confirm.Approved {
			return &TransferOutput{Status: "declined"}, nil
		}
		// ... perform the transfer
		return &TransferOutput{Status: "completed"}, nil
	},
)
```

`DefineResumableTool` returns `*ai.ResumableToolAction[In, Out, Res]`.

### Handle interrupts

A paused generation returns `(resp, nil)` with `resp.FinishReason ==
ai.FinishReasonInterrupted`. Claim each part in `resp.Interrupts()` with the
tool's `Interrupted` method. The claim matches the part to the tool and decodes
its input, so the verbs after it cannot fail:

| Verb | Effect |
| --- | --- |
| `call.Restart(resume)` | Run the tool again with the typed resume value. |
| `call.RestartWithInput(input, resume)` | Run it again with revised input (history records the revised request). |
| `call.Respond(output)` | Answer with the tool's output; the tool does not run again. |

```go
const maxRounds = 5

resp, err := genkit.Generate(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt(userRequest),
	ai.WithTools(transferMoney),
)
if err != nil {
	return err
}

for round := 0; round < maxRounds && resp.FinishReason == ai.FinishReasonInterrupted; round++ {
	var parts []*ai.Part
	for _, part := range resp.Interrupts() {
		call, ok := transferMoney.Interrupted(part)
		if !ok {
			return fmt.Errorf("no handler for interrupt from tool %q", part.ToolRequest.Name)
		}
		meta, _ := ai.InterruptAs[TransferInterrupt](part) // the data the tool paused with
		log.Println("paused:", meta.Reason)
		approved := askUser(call.Input.Amount, call.Input.ToAccount) // call.Input is TransferInput
		parts = append(parts, call.Restart(Confirmation{Approved: approved}))
	}

	// The full history, the same tools, and every interrupt answered.
	resp, err = genkit.Generate(ctx, g,
		ai.WithMessages(resp.History()...),
		ai.WithTools(transferMoney),
		ai.WithResume(parts...),
	)
	if err != nil {
		return err
	}
}
fmt.Println(resp.Text())
```

Rules:

- **Answer every interrupt** in the turn with exactly one part. Missing one
  fails
  with `ai.ErrUnresolvedToolRequest`; passing `resp.Interrupts()` back as is
  (still paused) fails with `INVALID_ARGUMENT`. The whole resume is checked
  before any tool runs.
- **Several resumable tools?** Try each tool's `Interrupted` on the part; it
  reports false for other tools' interrupts.
- **A resume can pause again.** It returns `(resp, nil)` with `FinishReason`
  interrupted, so loop as above.
- **Middleware holds** (e.g. `ToolApproval`) are not the tool's interrupt: claim
  them with `middleware.ToolApprovalInterrupted(part)`. See
  [middleware](middleware.md).
- **Generic handlers** that only hold the part can build the same parts with
  `part.ToToolRestart(resume)`, `part.ToToolRestartWithInput(input, resume)`,
  and `part.ToToolResponse(output)`. These return an error, since nothing was
  type-checked by a claim.

### Read the original input after a revised restart

```go
if orig, ok := tool.OriginalInput[TransferInput](ctx); ok {
	log.Printf("adjusted from $%.2f to $%.2f", orig.Amount, in.Amount)
}
```

`tool.OriginalInput` reports false on a first call and on a restart that kept
the
input.

Agents use the same tool and claim; only the delivery differs
(`aix.ToolResume`).
See [agents-human-in-the-loop.md](agents-human-in-the-loop.md).

