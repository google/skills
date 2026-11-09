# Advanced Custom Agents — `DefineCustomAgent` (Experimental)

> **Experimental / preview API.** `genkitx.DefineCustomAgent` comes from
> `genkit/exp`. Read [agents.md](agents.md) and [agent state](agents-state.md)
> first.

`DefineAgent` runs a single prompt + tool loop. When you need **full control of
the turn** — multiple sequential model calls, custom logic between them, manual
message/state management, or custom progress streaming — use
`genkitx.DefineCustomAgent`. You provide the function that runs the turn loop.

- [When to use it](#when-to-use-it): Lines 20-30
- [Signature](#signature): Lines 32-71
- [Example: multi-step research agent](#example-multi-step-research-agent): Lines 73-162
- [Custom status streaming](#custom-status-streaming): Lines 164-194
- [Notes](#notes): Lines 196-209

---

## When to use it

Reach for `DefineCustomAgent` when a turn needs to:

- make **multiple model calls** with your own orchestration between them;
- run **multi-step workflows** (decompose → research → synthesize);
- **manually manage** messages and custom state;
- **stream custom status** updates to the client mid-turn.

Otherwise prefer `DefineAgent` (simpler; custom state still works — see
[agent state](agents-state.md)).

## Signature

```go
func DefineCustomAgent[State any](
	g *genkit.Genkit,
	name string,
	fn aix.AgentFunc[State],
	opts ...aix.AgentOption[State],
) *aix.Agent[State]

// where:
type AgentFunc[State any] = func(ctx context.Context, resp aix.Responder, sess *aix.SessionRunner[State]) (*aix.AgentResult, error)
```

Your `fn` receives:

- `resp aix.Responder` — the output channel to the client.
  `resp.SendModelChunk(chunk)`
  streams generation tokens; `resp.SendArtifact(a)` streams (and records) an
  artifact. Sends are fire-and-forget.
- `sess *aix.SessionRunner[State]` — the session plus turn-loop control. Call
  `sess.Run(ctx, perTurn)` to enter the loop; it blocks per turn until the
  client
  sends the next input.

Key `sess` methods:

- `sess.Run(ctx, func(ctx, input *aix.AgentInput) (*aix.TurnResult, error))` —
  runs the turn loop. The incoming `input.Message` is added to the session
  before
  your callback runs, so `sess.Messages()` includes it. Return a
  `*aix.TurnResult`
  to report the finish reason (or `nil` to report none).
- `sess.Messages()` / `sess.AddMessages(...)` / `sess.SetMessages(...)` — read
  and
  write conversation history.
- `sess.UpdateCustom(fn)` — mutate typed custom state; auto-streams a
  `CustomPatch` chunk (see [state](agents-state.md)).
- `sess.Result()` — build an `*aix.AgentResult` from the current session (last
  message + artifacts), a convenience for the return value.

## Example: multi-step research agent

```go
type ResearchState struct {
	Status       string   `json:"status,omitempty"` // live progress shown to the client
	SubQuestions []string `json:"subQuestions"`
	SubAnswers   []QA     `json:"subAnswers"`
}
type QA struct {
	Question string `json:"question"`
	Answer   string `json:"answer"`
}

researchAgent := genkitx.DefineCustomAgent(g, "researchAgent",
	func(ctx context.Context, resp aix.Responder, sess *aix.SessionRunner[ResearchState]) (*aix.AgentResult, error) {
		var lastMessage *ai.Message
		err := sess.Run(ctx, func(ctx context.Context, input *aix.AgentInput) (*aix.TurnResult, error) {
			userText := input.Message.Text()

			// Step 1: decompose. Mutating custom state auto-emits a CustomPatch
			// chunk so the client's tracked state stays live.
			sess.UpdateCustom(func(s ResearchState) ResearchState {
				s.Status = "Decomposing question…"
				return s
			})
			subQs, _, err := genkit.GenerateData[[]string](ctx, g,
				ai.WithModelName("googleai/gemini-flash-latest"),
				ai.WithPrompt("Break this into 2-3 sub-questions (JSON array): %q", userText),
			)
			if err != nil {
				return nil, err
			}

			sess.UpdateCustom(func(s ResearchState) ResearchState {
				s.SubQuestions, s.SubAnswers = *subQs, nil
				return s
			})

			// Step 2: research each sub-question.
			var answers []QA
			for i, q := range *subQs {
				sess.UpdateCustom(func(s ResearchState) ResearchState {
					s.Status = fmt.Sprintf("Researching (%d/%d)", i+1, len(*subQs))
					return s
				})
				a, err := genkit.GenerateText(ctx, g,
					ai.WithModelName("googleai/gemini-flash-latest"),
					ai.WithPrompt(q),
				)
				if err != nil {
					return nil, err
				}
				answers = append(answers, QA{Question: q, Answer: a})
			}
			sess.UpdateCustom(func(s ResearchState) ResearchState {
				s.SubAnswers, s.Status = answers, "Synthesizing…"
				return s
			})

			// Step 3: synthesize and STREAM the final answer to the client.
			var reason aix.AgentFinishReason
			for result, err := range genkit.GenerateStream(ctx, g,
				ai.WithModelName("googleai/gemini-flash-latest"),
				ai.WithPrompt("Synthesize a unified answer from: %v", answers),
			) {
				if err != nil {
					return nil, err
				}
				if result.Done {
					lastMessage = result.Response.Message
					reason = aix.AgentFinishReason(result.Response.FinishReason)
					sess.AddMessages(lastMessage) // record the final response in history
				} else {
					resp.SendModelChunk(result.Chunk) // stream model output to the client
				}
			}
			sess.UpdateCustom(func(s ResearchState) ResearchState { s.Status = "Done"; return s })

			// Report how the turn ended; the framework forwards it on TurnEnd and
			// persists it on the snapshot.
			return &aix.TurnResult{FinishReason: reason}, nil
		})
		if err != nil {
			return nil, err
		}
		return sess.Result(), nil
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[ResearchState]()),
)
```

## Custom status streaming

Calling `sess.UpdateCustom(...)` during the turn automatically emits a
`CustomPatch` chunk, so a connection's tracked [custom state](agents-state.md)
(e.g. the `Status` field) stays live **mid-stream** without extra wiring. Stream
model output separately with `resp.SendModelChunk(chunk)`.

Run a custom agent exactly like a regular one:

```go
conn, _ := researchAgent.Connect(ctx,
	aix.WithState(&aix.SessionState[ResearchState]{}),
)
_ = conn.SendText("Impacts of electric vehicles?")
for chunk, err := range conn.Receive() {
	if err != nil {
		log.Fatal(err)
	}
	if chunk.ModelChunk != nil {
		fmt.Print(chunk.ModelChunk.Text()) // model output
	}
	if len(chunk.CustomPatch) > 0 {
		cur, _ := conn.Custom()
		fmt.Println("status:", cur.Status) // live progress
	}
	if chunk.TurnEnd != nil {
		break
	}
}
out, _ := conn.Output()
```

## Notes

- **Per-turn metadata.** Inside the `sess.Run` callback,
  `aix.TurnContextFromContext(ctx)` returns the turn's `SnapshotID`,
  `ParentSnapshotID`, and `TurnIndex` — reserved before the turn runs, so you
  can
  name external resources (e.g. a git worktree) after the snapshot up front.
- **Validate untrusted resume.** If you accept `input.Resume` from untrusted
  callers, call
  `aix.ValidateResumeAgainstHistory(input.Resume, sess.Messages())`
  before forwarding it to the model (the prompt-backed loop does this for you).
- **Recovering from a failed turn.** If your callback returns an error, `Run`
  records the failure and stops; you may call `Run` again to keep processing, or
  return the error to resolve the invocation as a failed `AgentOutput`.
