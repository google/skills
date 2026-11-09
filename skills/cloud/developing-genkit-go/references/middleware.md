# Middleware

Middleware wraps `Generate` calls to add cross-cutting behavior (retries,
logging, fallback, gating, sandboxed tools) without touching the flow that uses
it. Middleware composes, so a single `Generate` call can stack several
behaviors. Built-ins ship in the `plugins/middleware` package; custom middleware
is just a Go struct with two methods.

- [The mental model](#the-mental-model): Lines 24-52
- [When each hook fires](#when-each-hook-fires): Lines 54-70
- [Composition order](#composition-order): Lines 72-87
- [Per-call state](#per-call-state): Lines 89-141
- [Plugin-level state](#plugin-level-state): Lines 143-184
- [Composition with WithUse](#composition-with-withuse): Lines 186-202
- [Inline middleware](#inline-middleware): Lines 204-222
- [Application-owned middleware](#application-owned-middleware): Lines 224-240
- [Built-in middleware](#built-in-middleware): Lines 242-456
- [Practical patterns](#practical-patterns): Lines 458-551
- [Migration note](#migration-note): Lines 553-558
- [See also](#see-also): Lines 560-566

---

## The mental model

A middleware is a config struct that implements two methods:

```go
type Middleware interface {
    Name() string                            // stable, registered identifier
    New(ctx context.Context) (*Hooks, error) // produces a per-call hook bundle
}
```

The same struct value the user passes to `ai.WithUse` is the value the runtime
calls `New` on. There is no separate factory parameter and no embedded base
type. Per-call state goes in closures captured by `New`. Plugin-level state goes
on unexported fields of the struct.

`New` is invoked once per `Generate` call. The returned `*Hooks` is reused
across every iteration of the tool loop within that call.

```go
type Hooks struct {
    Tools        []Tool                                        // injected for this call
    WrapGenerate func(ctx, *GenerateParams, GenerateNext) ...  // tool-loop iteration
    WrapModel    func(ctx, *ModelParams, ModelNext) ...        // model API call
    WrapTool     func(ctx, *ToolParams, ToolNext) ...          // tool execution
}
```

A nil hook is a pass-through. Implement only what the middleware needs.

## When each hook fires

A `Generate` call executes a tool loop: model produces output, any tool calls
execute, results feed back into a new model call, repeat until the model stops.
The hooks fire at three different layers of this loop:

| Hook | Fires | Sees |
| --- | --- | --- |
| `WrapGenerate` | Once per tool-loop iteration. `N` tool turns means `N+1` invocations. | The accumulated `ModelRequest`, the iteration index, the streaming callback, and `MessageIndex` (the next streamed-message slot). |
| `WrapModel` | Once per actual model API call, inside the iteration. | The `ModelRequest` about to go to the model and the streaming callback. |
| `WrapTool` | Once per tool execution. May run **concurrently** for parallel tool calls in the same iteration. | The `ToolRequest` and the resolved `Tool`. |

`WrapGenerate` is the right place for logic that needs to see the whole
conversation (rewrites, system-prompt injection, message accumulation).
`WrapModel` is the right place for logic about the model call itself (retry,
fallback, caching). `WrapTool` is the right place for logic about a single tool
execution (approval, sandboxing, logging).

## Composition order

`ai.WithUse(A, B, C)` expands to `A { B { C { actual } } }` at call time. Each
layer's `next` continuation runs the next inner layer:

```go
ai.WithUse(
    &middleware.Retry{MaxRetries: 3},     // outer: retries the whole inner stack
    &middleware.Fallback{Models: ...},    // inner: tries fallback models on failure
)
// effective chain: Retry { Fallback { model } }
```

Order matters. `Retry` outside `Fallback` retries the entire fallback cascade as
a unit. Swapped, you'd retry the primary first and only fall back after
exhausting retries.

## Per-call state

State that should be shared across the hooks of a single `Generate` call lives
in closures captured by `New`. Each `Generate` call gets a fresh `Hooks` bundle,
so nothing leaks between calls.

```go
type Counter struct{}

func (Counter) Name() string { return "mine/counter" }

func (Counter) New(ctx context.Context) (*ai.Hooks, error) {
    var modelCalls int
    return &ai.Hooks{
        WrapModel: func(ctx context.Context, p *ai.ModelParams, next ai.ModelNext) (*ai.ModelResponse, error) {
            modelCalls++
            return next(ctx, p)
        },
        WrapGenerate: func(ctx context.Context, p *ai.GenerateParams, next ai.GenerateNext) (*ai.ModelResponse, error) {
            // The same modelCalls variable is visible here because both closures
            // capture it from the enclosing New scope.
            resp, err := next(ctx, p)
            if err == nil {
                log.Printf("iteration %d: %d model calls so far", p.Iteration, modelCalls)
            }
            return resp, err
        },
    }, nil
}
```

`WrapTool` may be invoked concurrently for parallel tool calls in the same
iteration. Any state it mutates must be guarded:

```go
func (Counter) New(ctx context.Context) (*ai.Hooks, error) {
    var (
        mu        sync.Mutex
        toolCalls int
    )
    return &ai.Hooks{
        WrapTool: func(ctx context.Context, p *ai.ToolParams, next ai.ToolNext) (*ai.MultipartToolResponse, error) {
            mu.Lock()
            toolCalls++
            mu.Unlock()
            return next(ctx, p)
        },
    }, nil
}
```

`WrapGenerate` and `WrapModel` are not called concurrently within a single
`Generate` call.

## Plugin-level state

When a middleware needs resources its config can't carry as JSON (an HTTP
client, a database handle, a logger), put them on **unexported** fields of the
config struct. The plugin sets them on a prototype, and `ai.NewMiddleware`
captures that prototype in a closure that value-copies it across JSON-dispatched
invocations:

```go
type Logger struct {
    Prefix string `json:"prefix,omitempty"`
    out    io.Writer // unexported; preserved across JSON dispatch via value-copy
}

func (Logger) Name() string { return "mine/logger" }

func (l Logger) New(ctx context.Context) (*ai.Hooks, error) {
    return &ai.Hooks{
        WrapModel: func(ctx context.Context, p *ai.ModelParams, next ai.ModelNext) (*ai.ModelResponse, error) {
            start := time.Now()
            resp, err := next(ctx, p)
            fmt.Fprintf(l.out, "%s model call took %s\n", l.Prefix, time.Since(start))
            return resp, err
        },
    }, nil
}

type LoggerPlugin struct{ Out io.Writer }

func (p *LoggerPlugin) Name() string                          { return "logger" }
func (p *LoggerPlugin) Init(ctx context.Context) []api.Action { return nil }

func (p *LoggerPlugin) Middlewares(ctx context.Context) ([]*ai.MiddlewareDesc, error) {
    return []*ai.MiddlewareDesc{
        ai.NewMiddleware("logs model call latency", Logger{out: p.Out}),
    }, nil
}
```

The Dev UI and other-runtime callers send JSON config; the prototype's value
copy preserves `out` (unexported, not in JSON) while `Prefix` is overridden by
the unmarshaled config.

## Composition with WithUse

```go
response, _ := genkit.Generate(ctx, g,
    ai.WithModelName("googleai/gemini-flash-latest"),
    ai.WithPrompt("Explain quantum computing."),
    ai.WithUse(
        Logger{Prefix: "[trace]"},
        &middleware.Retry{MaxRetries: 3},
    ),
)
```

No registration is required for pure-Go use. `WithUse` calls each value's `New`
directly on a fast path; the registry is only consulted for JSON-dispatched
calls (Dev UI or cross-runtime). Registration is what makes a middleware visible
to the Dev UI and addressable by name.

## Inline middleware

For ad-hoc middleware that does not need Dev UI visibility or a named type, use
`ai.MiddlewareFunc`:

```go
ai.WithUse(ai.MiddlewareFunc(func(ctx context.Context) (*ai.Hooks, error) {
    return &ai.Hooks{
        WrapModel: func(ctx context.Context, p *ai.ModelParams, next ai.ModelNext) (*ai.ModelResponse, error) {
            log.Printf("model call: %s", p.Request.Messages[len(p.Request.Messages)-1].Text())
            return next(ctx, p)
        },
    }, nil
}))
```

The adapter satisfies `Middleware` with a placeholder `Name()` of `"inline"`.
Inline middleware is resolved on the fast path and never touches the registry,
so the placeholder name is fine.

## Application-owned middleware

Use `genkit.DefineMiddleware` to register a middleware your application owns
directly. Registration surfaces it in the Dev UI and lets cross-runtime callers
reference it by name:

```go
genkit.DefineMiddleware(g, "logs model call latency", Logger{out: os.Stderr})

// Lookup by name (mostly for inspection / cross-runtime dispatch).
desc := genkit.LookupMiddleware(g, "mine/logger")
```

For application code, `DefineMiddleware` is the typical entry point. For plugin
authors, `ai.NewMiddleware` (no registration) plus
`MiddlewarePlugin.Middlewares()` is the typical entry point. `genkit.Init`
registers the returned descriptors automatically.

## Built-in middleware

The `plugins/middleware` package bundles six production-ready implementations
(`Retry`, `Fallback`, `ToolApproval`, `Filesystem`, `Skills`, `SoftToolErrors`);
the experimental `plugins/middleware/exp` package (imported as `middlewarex`)
adds `ContextCompression`, `Budget`, `Agents`, and `Artifacts`. Register the
plugin once during `Init` to make them visible to the Dev UI:

```go
import "github.com/firebase/genkit/go/plugins/middleware"

g := genkit.Init(ctx, genkit.WithPlugins(
    &googlegenai.GoogleAI{},
    &middleware.Middleware{},
))
```

### `Retry`

Retries failed model API calls with exponential backoff and jitter. Hooks
`WrapModel`.

```go
ai.WithUse(&middleware.Retry{
    MaxRetries:     3,     // default 3
    InitialDelayMs: 1000,  // default 1000
    MaxDelayMs:     60000, // default 60000
    BackoffFactor:  2,     // default 2
    NoJitter:       false, // default false
    // Statuses (default: UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED, ABORTED, INTERNAL)
    // Statuses: []core.StatusName{core.UNAVAILABLE, core.RESOURCE_EXHAUSTED},
})
```

Non-`GenkitError` errors (network, parse, etc.) are always retried.
`GenkitError` errors are retried only if their status is in `Statuses`. The
backoff respects `ctx.Done()`: a canceled context aborts the retry loop with the
last error.

### `Fallback`

Tries alternative models when the primary fails with a fallback-eligible status.
Hooks `WrapModel`.

```go
ai.WithUse(&middleware.Fallback{
    Models: []ai.ModelRef{
        googlegenai.ModelRef("googleai/gemini-flash-latest", nil),
        googlegenai.ModelRef("vertexai/gemini-flash-latest", nil),
    },
    // default Statuses: UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED,
    // ABORTED, INTERNAL, NOT_FOUND, UNIMPLEMENTED
})
```

Each fallback model uses its own `ModelRef.Config()` verbatim; the original
request's config is **not** inherited. Compose with `Retry` outside to retry the
whole cascade, or inside to retry just the primary before falling back.

### `ToolApproval`

Holds any tool call not in the allow list, exposing approval as a
human-in-the-loop step. Hooks `WrapTool`.

```go
approval := ai.WithUse(&middleware.ToolApproval{
    AllowedTools: []string{"lookup", "search"}, // anything else is held
})
```

Claim holds with `middleware.ToolApprovalInterrupted` (not the tool's own
`Interrupted`) and answer with a typed `middleware.ToolCallDecision`. Keep the
same middleware on the resume call:

```go
var parts []*ai.Part
for _, part := range resp.Interrupts() {
    if call, ok := middleware.ToolApprovalInterrupted(part); ok {
        decision := middleware.ToolCallDecision{Approved: confirm(part.ToolRequest.Name, call.Input)}
        if !decision.Approved {
            decision.Reason = "the user declined" // the model sees this as the tool's error
        }
        parts = append(parts, call.Restart(decision))
    }
}
resp, err = genkit.Generate(ctx, g,
    ai.WithMessages(resp.History()...),
    ai.WithTools(writeFile),
    approval,
    ai.WithResume(parts...),
)
```

Silence never approves: any restart without `Approved: true` refuses the call,
and the model receives the refusal as a tool error and continues. Answer a hold
with `Restart`, not `Respond`.

**Judge model.** Let a model decide calls the allowlist does not cover
(auto-approval). It answers allow, deny (the model sees the denial), or ask
(held for you), and fails closed:

```go
ai.WithUse(&middleware.ToolApproval{
    AllowedTools: []string{"list_files"},
    Judge:        googlegenai.ModelRef("googleai/gemini-flash-lite-latest", nil),
    JudgePolicy:  "Never allow deleting anything outside build/.",
})
```

### `SoftToolErrors`

Returns tool errors to the model as the tool's output (`{"error": "..."}`)
instead of stopping the loop, so the model can fix its input. Useful for tools
you don't own, like MCP tools. Interrupts and cancellation still stop the loop.

```go
ai.WithUse(&middleware.SoftToolErrors{})                         // every tool
ai.WithUse(&middleware.SoftToolErrors{Tools: []string{"search"}}) // only these
```

For a tool you own, return `tool.Fail(ctx, err)` for just the errors the model
can fix. See [tools.md](tools.md#errors-the-model-can-fix).

### `ContextCompression` (experimental, `middlewarex`)

Keeps long chats and tool loops inside a context budget. The model receives a
compressed view; `resp.History()` keeps every original message, with compression
state in metadata.

```go
import middlewarex "github.com/firebase/genkit/go/plugins/middleware/exp"

ai.WithUse(
    &middlewarex.ContextCompression{
        MaxInputTokens:        80_000,
        DedupeToolResponses:   &middlewarex.CompressionDedupe{},
        TruncateToolResponses: &middlewarex.CompressionToolTruncation{MaxChars: 2000},
        Summarize: &middlewarex.CompressionSummarizer{
            Model: googlegenai.ModelRef("googleai/gemini-flash-lite-latest", nil),
        },
        // also: MaxMessages, PreserveRecent (4), MaxToolResponseChars (400000),
        // SkipSummarizationThreshold, ReplaceHistory
    },
    &middleware.Retry{}, // inside compression, so a retry resends the compressed view
)
```

List it after context-adding middleware (`Skills`, `Filesystem`, `Agents`,
`Artifacts`) and before `Retry`/`Fallback`.
`middlewarex.ResolveCompressedHistory(msgs)` returns what the model received.
Set `MaxInputTokens` well above a typical first turn.

### `Budget` (experimental, `middlewarex`)

Caps what a run (or an agent session) may spend. Each non-zero field of `Limit`
(an `ai.GenerationUsage`) is a cap; `Custom` is capped key by key.

```go
resp, err := genkit.Generate(ctx, g,
    ai.WithPrompt("Research the topic and summarize it."),
    ai.WithTools(search),
    ai.WithUse(&middlewarex.Budget{Limit: ai.GenerationUsage{
        TotalTokens: 200_000,
        Custom:      map[string]float64{"cost": 0.50},
    }}),
)
if errors.Is(err, ai.ErrBudgetExceeded) {
    log.Println(resp.FinishReason) // aborted; resp.History() keeps the rounds that ran
}
```

Checked before each model call, so a run can go over by one turn. Subagents
count toward the run. `Scope: middlewarex.BudgetScopeSession` caps the whole
agent session (needs a session store). `Interrupt: true` pauses instead of
stopping; claim with `middlewarex.BudgetInterrupted(part)` and restart with
`middlewarex.BudgetDecision{Approved: true}`.

Every run reports usage: `resp.Usage` is the last model call, `resp.TotalUsage`
sums every call in the run (nested ones included). Agents report
`TurnEnd.Usage`, `out.Usage`, and `out.State.Usage` (session total).

### `Filesystem`

Grants the model scoped file access under a single root directory via
`list_files`, `read_file`, plus `write_file` and `search_and_replace` when
writes are enabled. Hooks `WrapGenerate` and `WrapTool` and contributes `Tools`.

```go
ai.WithUse(&middleware.Filesystem{
    RootDir:          "./workspace",
    AllowWriteAccess: true,
    ToolNamePrefix:   "",  // set distinct prefixes if attaching multiple Filesystem middlewares
})
```

Path safety is enforced by `os.Root` (Go 1.25+), which rejects any path
resolving outside the root, including via `..`, absolute paths, or symlinks.
`read_file` returns its content as a queued user message on the next turn (not
as the tool's direct output) so binary types like images can be inlined as media
parts.

### `Skills`

Exposes a local library of `SKILL.md` files as loadable system instructions.
Hooks `WrapGenerate` and contributes a `use_skill` tool.

```go
ai.WithUse(&middleware.Skills{SkillPaths: []string{"skills"}}) // default: ["skills"]
```

A skill is a directory containing `SKILL.md`, optionally with YAML frontmatter
(`name`, `description`). The middleware injects a system prompt listing
available skills, and the model calls `use_skill("name")` to pull the skill body
into the conversation on demand. Heavier persona instructions stay off the hot
path until actually loaded.

## Practical patterns

### Streaming-aware middleware

If your `WrapGenerate` or `WrapModel` hook emits its own messages (injected user
content, system updates), use the streaming callback and the `MessageIndex`
cursor in `GenerateParams`:

```go
WrapGenerate: func(ctx context.Context, p *ai.GenerateParams, next ai.GenerateNext) (*ai.ModelResponse, error) {
    if p.Callback != nil {
        _ = p.Callback(ctx, &ai.ModelResponseChunk{
            Role:    ai.RoleUser,
            Index:   p.MessageIndex,
            Content: []*ai.Part{ai.NewTextPart("[injected context]")},
        })
        p.MessageIndex++ // advance so downstream middleware and the model see the shifted index
    }
    p.Request.Messages = append(p.Request.Messages, ai.NewUserMessage(ai.NewTextPart("[injected context]")))
    return next(ctx, p)
},
```

`Filesystem` does this to deliver `read_file` content to the model while
preserving streamed-chunk ordering.

### Adding tools from middleware

`Hooks.Tools` registers extra tools for the duration of the call without the
user wiring them through `ai.WithTools`. Useful when the middleware's hooks and
tools work as a pair (e.g., `Filesystem`'s read/write tools, `Skills`'s
`use_skill` tool):

```go
return &ai.Hooks{
    Tools:    []ai.Tool{myTool},
    WrapTool: myInterceptor, // intercepts both myTool and any user-supplied tools
}, nil
```

Duplicate tool names across user-supplied tools and middleware-contributed tools
error out at call setup; the call won't run.

### Interrupting from `WrapTool`

A `WrapTool` hook pauses a call with `tool.Interrupt(ctx, data)` (from
`github.com/firebase/genkit/go/ai/tool`), reads its answer on the restart with
`tool.ResumeData[T](ctx)`, and skips calls it already let through with
`tool.Released(ctx)`. (`ai.NewToolInterruptError` was removed in v1.14.0.)

```go
WrapTool: func(ctx context.Context, p *ai.ToolParams, next ai.ToolNext) (*ai.MultipartToolResponse, error) {
    if shouldGate(p.Tool.Name()) && !tool.Released(ctx) {
        if d, ok := tool.ResumeData[MyDecision](ctx); ok {
            if !d.Approved {
                return nil, errors.New("declined")
            }
            return next(ctx, p)
        }
        return nil, tool.Interrupt(ctx, map[string]any{"message": "needs approval"})
    }
    return next(ctx, p)
},
```

Export a typed claim for your hold by wrapping
`ai.MiddlewareInterrupted[Res](name, part)`, as `ToolApprovalInterrupted` does.
`ToolApproval` uses this pattern.

### Modifying the request safely

`p.Request` is the live request for the iteration. Mutating it in place affects
later layers. If the change should be visible only to the inner layer, copy
first:

```go
WrapModel: func(ctx context.Context, p *ai.ModelParams, next ai.ModelNext) (*ai.ModelResponse, error) {
    req := *p.Request
    req.Messages = append([]*ai.Message(nil), p.Request.Messages...)
    req.Messages = append(req.Messages, extraSystemMessage)
    p.Request = &req
    return next(ctx, p)
},
```

`Skills.injectSkillsPrompt` shows the same pattern for `ModelRequest` cloning.

### Idempotent re-injection across iterations

`WrapGenerate` runs once per tool-loop iteration. If you inject content into the
request, you'll inject it on every iteration unless you mark and detect what
you've already added. `Skills` tags its system prompt part with metadata
(`skills-instructions: true`) and refreshes that one part in place rather than
appending a new one each turn.

## Migration note

The legacy `ai.ModelMiddleware` / `ai.WithMiddleware` API is preserved and
marked deprecated. Prefer `ai.Middleware` / `ai.WithUse`, which adds
`WrapGenerate` and `WrapTool` hooks plus `Hooks.Tools` for dynamically injected
tools.

## See also

- [`tools.md`](tools.md) for tool definition, interrupt/restart machinery used
  by `ToolApproval`.
- Sample sources under `go/samples/basic-middleware/`: `retry-fallback`,
  `filesystem`, `skills`.
- The `plugins/middleware` package source for reference implementations.
