# Working with Artifacts (Experimental)

> **Experimental / preview API.** The `Artifacts` middleware comes from
> `plugins/middleware/exp`; the `Artifact` type from `ai/exp`. Read
> [agents.md](agents.md) first.

**Artifacts** are named, content-bearing deliverables an agent produces during a
session — files, reports, code, etc. They live in the session (deduplicated by
name) and are returned on `out.Artifacts`.

```go
import (
	aix "github.com/firebase/genkit/go/ai/exp"
	middlewarex "github.com/firebase/genkit/go/plugins/middleware/exp"
)
```

- [Give the model artifact tools](#give-the-model-artifact-tools): Lines 25-69
- [The Artifact shape](#the-artifact-shape): Lines 71-82
- [Programmatic access (inside tools and custom agents)](#programmatic-access-inside-tools-and-custom-agents): Lines 84-112
- [Sharing artifacts across agents](#sharing-artifacts-across-agents): Lines 114-131

---

## Give the model artifact tools

The `middlewarex.Artifacts` middleware (see [using middleware](middleware.md))
adds `read_artifact` and `write_artifact` tools and injects an `<artifacts>`
listing (names + sizes, not full content) into the system prompt each turn. No
custom tool code needed. Attach it via the `ai.WithUse` prompt option.

```go
workspaceAgent := genkitx.DefineAgent[any](g, "workspaceAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem(`You are a code generation assistant. Use write_artifact to create
files (pass the filename as "name" and the full content as "content"). Use
read_artifact to review or modify a previously created file.`),
		ai.WithUse(&middlewarex.Artifacts{}),
	},
)
```

No session store is needed to produce artifacts — they are returned on
`out.Artifacts` either way (this agent is
[client-managed](agents.md#client-managed-vs-server-managed-state),
hence the explicit `[any]` type parameter). Add a store (e.g.
`localstore.NewFileSessionStore`) only when artifacts should persist across
turns
or sessions. See [sessions](agents-sessions.md).

Run it; artifacts are produced via the tool and returned in the output:

```go
out, _ := workspaceAgent.RunText(ctx, "Write poem.txt with a poem about Genkit")
for _, a := range out.Artifacts {
	fmt.Println(a.Name)
}
```

`middlewarex.Artifacts` option:

- `Readonly` (default `false`): when `true`, only `read_artifact` is provided —
  the model can read but not create/update artifacts. Useful on an orchestrator
  that should review (but not produce) sub-agent artifacts.

```go
ai.WithUse(&middlewarex.Artifacts{Readonly: true})
```

## The `Artifact` shape

```go
// An artifact's content lives in Parts (text/media parts). Metadata is optional.
artifact := &aix.Artifact{
	Name:     "poem.txt",
	Parts:    []*ai.Part{ai.NewTextPart("Roses are red…")},
	Metadata: map[string]any{"source": "workspaceAgent"}, // optional
}
```

Writing the same `Name` again **replaces** the artifact (dedup by name).

## Programmatic access (inside tools and custom agents)

Use the session's artifact store. `aix.ArtifactStoreFromContext(ctx)` returns a
`State`-agnostic view (so tools don't need to know the agent's `State` type), or
`nil` when there is no active session.

```go
store := aix.ArtifactStoreFromContext(ctx)
if store == nil {
	// not inside an agent session
}

// Read all artifacts:
for _, a := range store.Artifacts() {
	if a.Name == "poem.txt" {
		// ...
	}
}

// Create / replace artifacts:
store.AddArtifacts(&aix.Artifact{
	Name:  "notes.md",
	Parts: []*ai.Part{ai.NewTextPart("# Notes")},
})
```

From a [custom agent](agents-custom.md) you can also stream an artifact to the
client with `resp.SendArtifact(a)`, which forwards it and adds it to the session
in one call.

## Sharing artifacts across agents

In [multi-agent orchestration](agents-multi-agent.md), set the `Agents`
middleware's `ArtifactStrategy: middlewarex.ArtifactStrategySession` so
sub-agent
artifacts are merged into the parent session (namespaced by invocation ID), and
add `&middlewarex.Artifacts{Readonly: true}` to the orchestrator so it can
`read_artifact` them:

```go
ai.WithUse(
	&middlewarex.Agents{
		Agents:           []aix.AgentRef{{Name: "researcher"}, {Name: "coder"}},
		ArtifactStrategy: middlewarex.ArtifactStrategySession,
	},
	&middlewarex.Artifacts{Readonly: true},
)
```
