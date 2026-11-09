# Agent Sessions & Persistence (Experimental)

> **Experimental / preview API.** Session stores come from
> `ai/exp/localstore`. Read [agents.md](agents.md) for the basics first.

When an agent has a `SessionStore` (via `aix.WithSessionStore`), the **server**
owns the session history. Each turn produces an immutable **snapshot**; the
snapshot chain carries conversation state forward. A store also enables
[branching](agents-branching.md) and
[background execution](agents-background.md).
(Interrupts work with or without a store — see
[human-in-the-loop](agents-human-in-the-loop.md).)

- [Pick a store](#pick-a-store): Lines 24-104
- [Turns persist automatically](#turns-persist-automatically): Lines 106-116
- [Resume a conversation](#resume-a-conversation): Lines 118-140
- [Read a snapshot without running a turn](#read-a-snapshot-without-running-a-turn): Lines 142-160
- [Typed session state](#typed-session-state): Lines 162-190
- [Interrupts (human-in-the-loop)](#interrupts-human-in-the-loop): Lines 192-198
- [Implementing a custom SessionStore](#implementing-a-custom-sessionstore): Lines 200-247

---

## Pick a store

`ai/exp/localstore` ships two single-process stores. Both are generic over the
custom-state type `State` (use `any` when you have no typed custom state).

```go
import "github.com/firebase/genkit/go/ai/exp/localstore"

// In-memory: great for tests/dev; lost on restart.
memStore := localstore.NewInMemorySessionStore[any]()

// File-backed: snapshots persisted as <dir>/<prefix>/<snapshotId>.json
// (the prefix defaults to "global"). Returns an error if dir can't be created.
fileStore, err := localstore.NewFileSessionStore[any]("./.snapshots")
if err != nil {
	log.Fatal(err)
}
```

`localstore` is for local development, tests, and single-instance apps. For
multi-instance production, use the Firestore or PostgreSQL store, or implement
`aix.SessionStore` against your own database (see below).

### PostgreSQL store (experimental)

> Requires Genkit Go v1.14.0+.

`plugins/postgresql/exp` adds a session store with cross-process abort of
detached runs (`LISTEN`/`NOTIFY`), metadata-only reads, and per-tenant prefixes.
It shares the pool of the registered PostgreSQL plugin:

```go
import (
	"github.com/firebase/genkit/go/plugins/postgresql"
	pgexp "github.com/firebase/genkit/go/plugins/postgresql/exp"
)

engine, err := postgresql.NewPostgresEngine(ctx,
	postgresql.WithCloudSQLInstance("my-project", "us-central1", "my-instance"),
	postgresql.WithDatabase("my-database"))
if err != nil {
	log.Fatal(err)
}
g := genkit.Init(ctx,
	genkit.WithExperimental(),
	genkit.WithPlugins(&postgresql.Postgres{Engine: engine}))

store, err := pgexp.NewPostgresSessionStore[ChatState](ctx, g,
	pgexp.WithSnapshotPathPrefix(tenantFromContext))
```

Note: since v1.14.0, `PostgresEngine.Close` no longer closes a pool passed with
`postgresql.WithPool`; close it yourself.

`NewFileSessionStore` options:

- `localstore.WithMaxPersistedChainLength(n)`: keep only the newest `n`
  snapshots in a chain (each save prunes older ancestors). `n >= 1`.
- `localstore.WithSnapshotPathPrefix(fn)`: derive a per-call subdirectory from
  context to isolate snapshots per tenant (e.g. `"org-42/user-7"`).
- `localstore.WithPollInterval(d)`: how often the store re-reads subscribed
  snapshot files to observe cross-process status changes (default 2s). This is
  what lets one process abort a detached turn another process is running.

```go
pruning, err := localstore.NewFileSessionStore[any]("./.snapshots",
	localstore.WithMaxPersistedChainLength(3),
)
```

Attach a store to the agent with `aix.WithSessionStore`:

```go
logbookAgent := genkitx.DefineAgent(g, "logbookAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a personal logbook assistant."),
	},
	aix.WithSessionStore(fileStore),
)
```

## Turns persist automatically

Each turn writes a snapshot chained off the previous one. The turn's snapshot ID
is on `out.SnapshotID`; the conversation's stable ID is on `out.SessionID`.

```go
out1, _ := logbookAgent.RunText(ctx, "Log this: I started studying Genkit today.")
out2, _ := logbookAgent.RunText(ctx, "What did I study today?",
	aix.WithSessionID(out1.SessionID)) // remembers turn 1
fmt.Println(out1.SnapshotID, out2.SnapshotID)
```

## Resume a conversation

Two ways to resume a server-managed conversation:

- `aix.WithSessionID(id)` — resume the session's **latest** snapshot. Use it
  when you track the conversation, not individual snapshots.
- `aix.WithSnapshotID(id)` — resume a **specific** snapshot (see
  [branching](agents-branching.md)).

```go
// Continue from the session's latest snapshot:
out, _ := logbookAgent.RunText(ctx, "Add another note.",
	aix.WithSessionID(sessionID))

// Or continue from an exact checkpoint:
out, _ = logbookAgent.RunText(ctx, "Add another note.",
	aix.WithSnapshotID(snapshotID))
```

Resume is rejected if the latest snapshot is a failed, aborted, or pending dead
end (a pending tip means a detached invocation is still running — wait for it or
abort it). `aix.WithState` is for client-managed agents only and is mutually
exclusive with `WithSessionID` / `WithSnapshotID`.

## Read a snapshot without running a turn

`Agent.GetSnapshot` / `Agent.GetLatestSnapshot` fetch a stored snapshot
(applying
any configured `aix.WithStateTransform`). Handy for restoring a UI after a
reload. They return `FAILED_PRECONDITION` on a client-managed agent (no store).

```go
snap, err := logbookAgent.GetSnapshot(ctx, snapshotID)
if err != nil {
	log.Fatal(err)
}
fmt.Println(snap.Status) // aix.SnapshotStatusCompleted, ...
for _, m := range snap.State.Messages {
	fmt.Println(m.Role, m.Text())
}

latest, _ := logbookAgent.GetLatestSnapshot(ctx, sessionID)
```

## Typed session state

Parameterize the store (and agent) with a struct to attach typed **custom
state**. State is validated (via JSON) when a snapshot is loaded. See
[working with state](agents-state.md) for reading and mutating it inside tools.

```go
type Profile struct {
	Name string `json:"name"`
	Tier string `json:"tier"` // "free" | "pro"
}

profileAgent := genkitx.DefineAgent(g, "profileAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("Greet the user by name and tailor answers to their tier."),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[Profile]()),
)

// Seed custom state on the first turn (client-managed here for illustration;
// with a store you would seed via WithState on a fresh session).
out, _ := profileAgent.Run(ctx,
	&aix.AgentInput{Message: ai.NewUserTextMessage("Hello")},
	aix.WithState(&aix.SessionState[Profile]{
		Custom: Profile{Name: "Ada", Tier: "pro"},
	}),
)
```

## Interrupts (human-in-the-loop)

Interrupts pause a turn so a human can approve or provide input, then resume
from
the exact pause point. They work with a store or with client-managed state
(persistence is orthogonal). See
[Human-in-the-loop / interrupts](agents-human-in-the-loop.md).

## Implementing a custom `SessionStore`

For production, implement `aix.SessionStore` (which is `aix.SnapshotReader` +
`aix.SnapshotWriter`) against your database. Add `aix.SnapshotSubscriber` to
support [background/detach](agents-background.md) aborts.

```go
type SnapshotReader[State any] interface {
	GetSnapshot(ctx context.Context, snapshotID string) (*SessionSnapshot[State], error)
	GetLatestSnapshot(ctx context.Context, sessionID string) (*SessionSnapshot[State], error)
}

type SnapshotWriter[State any] interface {
	// Atomically read the row at id (nil if absent), apply fn, and persist the
	// result. fn must be pure (it may be retried). Returning (nil, nil) skips
	// the write. The store owns identity (SnapshotID); the caller owns
	// timestamps and Status. An empty id means "mint a fresh one".
	SaveSnapshot(ctx context.Context, snapshotID string,
		fn func(existing *SessionSnapshot[State]) (*SessionSnapshot[State], error),
	) (*SessionSnapshot[State], error)
}

// Optional: enables detach/abort by observing status changes without polling.
type SnapshotSubscriber interface {
	OnSnapshotStatusChange(ctx context.Context, snapshotID string) <-chan SnapshotStatus
}
```

Contract notes: preserve `SessionID` across rewrites (a row's session never
changes); default an empty `Status` to `SnapshotStatusCompleted`; keep
`CreatedAt`/`UpdatedAt` caller-managed (persist them verbatim, never stamp
them);
`GetLatestSnapshot` returns the greatest-`CreatedAt` row, ties broken by
`SnapshotID`. See the `localstore` implementations for a reference.

**Prove it with the conformance suite** (v1.14.0+). `ai/exp/sessionstoretest`
checks a store against the contract the agent runtime relies on; the bundled
stores all run it:

```go
import "github.com/firebase/genkit/go/ai/exp/sessionstoretest"

func TestMyStore(t *testing.T) {
	sessionstoretest.Run(t, func(t *testing.T) aix.SessionStore[MyState] {
		return newEmptyStore(t)
	}, nil) // or &sessionstoretest.Options[MyState]{Reopen: ..., Scoped: ...}
}
```
