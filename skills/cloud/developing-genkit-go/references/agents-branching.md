# Agent Branching (Experimental)

> **Experimental / preview API.** Requires a [session store](agents-sessions.md)
> so snapshots are persistent. Read [agents.md](agents.md) first.

A `SnapshotID` is an **immutable checkpoint**, like a git commit. You can fork
as
many independent timelines as you want from the same snapshot — each turn from a
snapshot creates a new, independent snapshot; the original is unchanged.

To branch, run a turn resuming from an earlier snapshot via
`aix.WithSnapshotID(id)`.

- [Branch from a checkpoint](#branch-from-a-checkpoint): Lines 21-49
- ["Pick a variant"](#pick-a-variant): Lines 51-79
- [Resume by session vs. by snapshot](#resume-by-session-vs-by-snapshot): Lines 81-86
- [Restore history from a snapshot](#restore-history-from-a-snapshot): Lines 88-111

---

## Branch from a checkpoint

```go
assistant := genkitx.DefineAgent(g, "assistant",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a helpful assistant."),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)

root, _ := assistant.RunText(ctx, "Hello!")
checkpoint := root.SnapshotID // branch point

// Branch A - forks from `checkpoint`.
a1, _ := assistant.RunText(ctx, "My name is Bob.", aix.WithSnapshotID(checkpoint))
a2, _ := assistant.RunText(ctx, "What is my name?", aix.WithSnapshotID(a1.SnapshotID)) // -> Bob

// Branch B - forks from the SAME `checkpoint`, fully independent.
b1, _ := assistant.RunText(ctx, "My name is John.", aix.WithSnapshotID(checkpoint))
b2, _ := assistant.RunText(ctx, "What is my name?", aix.WithSnapshotID(b1.SnapshotID)) // -> John

_ = a2
_ = b2
```

Each turn returns a fresh `SnapshotID`; the two branches never share one past
the
common `checkpoint`.

## "Pick a variant"

A common pattern: generate two variants from the same checkpoint in parallel,
let the user pick one, and continue from the chosen snapshot.

```go
func twoVariants(ctx context.Context, agent *aix.Agent[any], checkpoint, text string) (a, b *aix.AgentOutput[any], err error) {
	var wg sync.WaitGroup
	var errA, errB error
	wg.Add(2)
	go func() { defer wg.Done(); a, errA = agent.RunText(ctx, text, aix.WithSnapshotID(checkpoint)) }()
	go func() { defer wg.Done(); b, errB = agent.RunText(ctx, text, aix.WithSnapshotID(checkpoint)) }()
	wg.Wait()
	if errA != nil {
		return nil, nil, errA
	}
	if errB != nil {
		return nil, nil, errB
	}
	return a, b, nil // a.SnapshotID != b.SnapshotID; both branch from the same point
}

// When the user picks a variant, its SnapshotID becomes the new branch point:
// checkpoint = chosen.SnapshotID
```

When no branch point exists yet (the very first turn), start a fresh session by
omitting the invocation option, then use the returned `SnapshotID` as the branch
point going forward.

## Resume by session vs. by snapshot

- `aix.WithSnapshotID(id)` — fork from an **exact** checkpoint (branching).
- `aix.WithSessionID(id)` — continue the session's **latest** snapshot. If
  history was forked, the most recently created branch wins; use
  `WithSnapshotID` when you need a specific branch.

## Restore history from a snapshot

Use `Agent.GetSnapshot` to read a snapshot's state without starting a turn —
handy for restoring a UI after a reload (e.g. a `SnapshotID` stored in the URL).

```go
snap, err := assistant.GetSnapshot(ctx, snapshotID)
if err != nil {
	log.Fatal(err)
}
for _, m := range snap.State.Messages {
	if m.Role == ai.RoleUser || m.Role == ai.RoleModel {
		fmt.Printf("%s: %s\n", m.Role, m.Text())
	}
}
```

Over HTTP, expose `Agent.GetSnapshotAction()` so a remote client can fetch
snapshots (see [agents.md](agents.md#serve-an-agent-over-http)).

> Abandoned branches simply remain in the store as immutable snapshots; nothing
> is overwritten when you branch. (A `FileSessionStore` configured with
> `WithMaxPersistedChainLength` prunes only along a single chain's parent links,
> so sibling branches are retained independently.)
