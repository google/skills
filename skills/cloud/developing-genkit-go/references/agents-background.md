# Background Agents / Detaching (Experimental)

> **Experimental / preview API.** Detaching **requires a
> [session store](agents-sessions.md)** that also implements
> `aix.SnapshotSubscriber` (both `localstore` stores do) — the server needs
> somewhere to write the result and a way to observe an abort. Read
> [agents.md](agents.md) first.

Detaching runs a turn in the background: the server writes a `pending` snapshot
and returns its `SnapshotID` **immediately**, keeps processing, then rewrites
the
snapshot to a terminal status (`completed` / `failed` / `aborted`). A reader
waits on the snapshot (or polls it) and can `Abort` in the meantime.

- [Define the agent (store required)](#define-the-agent-store-required): Lines 24-34
- [Detach a turn](#detach-a-turn): Lines 36-55
- [Wait (or poll)](#wait-or-poll): Lines 57-82
- [Abort and resume](#abort-and-resume): Lines 84-110
- [Serve detach over HTTP](#serve-detach-over-http): Lines 112-131
- [Status values (aix.SnapshotStatus)](#status-values-aixsnapshotstatus): Lines 133-146

---

## Define the agent (store required)

```go
backgroundAgent := genkitx.DefineAgent(g, "backgroundAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem("You are a senior research analyst. Produce a comprehensive markdown report."),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()), // REQUIRED for detach
)
```

## Detach a turn

`RunDetached` sends one input, returns once the server has accepted the work,
and hands back a `*aix.DetachedTask[State]`. Store its snapshot ID;
`agent.Task(snapshotID)` rebuilds the same handle in any process later.

```go
task, err := backgroundAgent.RunDetached(ctx, &aix.AgentInput{
	Message: ai.NewUserTextMessage("Write a report on renewable energy trends"),
})
if err != nil {
	log.Fatal(err) // the work never started
}
snapshotID := task.SnapshotID() // pending; save this
```

On a live connection, send an input with `Detach: true` (or call `conn.Detach()`
mid-turn); the output has `FinishReason == aix.AgentFinishReasonDetached` and
the
pending `SnapshotID`.

## Wait (or poll)

```go
waitCtx, cancel := context.WithTimeout(ctx, 5*time.Minute)
defer cancel()

snap, err := task.Wait(waitCtx) // blocks until settled; no polling loop needed
if err != nil {
	log.Fatal(err) // the wait itself failed (unknown snapshot, ctx done)
}
switch snap.Status {
case aix.SnapshotStatusCompleted:
	msgs := snap.State.Messages
	fmt.Println(msgs[len(msgs)-1].Text())
case aix.SnapshotStatusFailed, aix.SnapshotStatusAborted:
	// Resume points: State holds the turns that finished (see below).
case aix.SnapshotStatusExpired:
	// The worker died (heartbeat stale). Resume from snap.ParentID and resend.
}
```

`task.Poll(ctx)` does one read instead. `agent.WaitForSnapshot(ctx, id)` waits
on
a bare snapshot ID. Pass `aix.WithMetadataOnly()` to `Poll` / `GetSnapshot` to
read status without loading `State`. `Wait` returns the snapshot for every
outcome; a non-nil error means the wait could not proceed.

## Abort and resume

```go
status, err := task.Abort(ctx) // or backgroundAgent.Abort(ctx, snapshotID)
```

An abort flips `pending` to `aborting` (so `Abort` answers `aborting` for a run
still going), the worker winds down, then the row settles. Check what `Wait`
returns rather than assuming `aborted`: a turn that finished anyway settles
`completed`, and one that broke first settles `failed`.

`failed` and `aborted` snapshots are **resume points**: they hold the
conversation up to the last completed turn. Send an input with no payload to
re-run the turn, or a new message to change course:

```go
snap, _ := task.Wait(ctx)
if snap.Status == aix.SnapshotStatusAborted || snap.Status == aix.SnapshotStatusFailed {
	out, err := backgroundAgent.Run(ctx, &aix.AgentInput{},
		aix.WithSnapshotID[any](snap.SnapshotID))
	// ...
}
```

Detached work runs in the process that started it; it is not durable
execution. On `SIGTERM`, abort pending snapshots and wait for them to settle so
callers find resumable `aborted` rows instead of `expired` ones.

## Serve detach over HTTP

A remote client drives the same story over HTTP: send `{"detach": true, ...}` as
the turn input, then wait on the `waitForSnapshot` companion (or poll
`getSnapshot`) and hit `abort`. Expose the companions next to the agent:

```go
mux.HandleFunc("POST /api/backgroundAgent", genkit.Handler(backgroundAgent))
mux.HandleFunc("POST /api/backgroundAgent/getSnapshot", genkit.Handler(backgroundAgent.GetSnapshotAction()))
mux.HandleFunc("POST /api/backgroundAgent/waitForSnapshot", genkit.Handler(backgroundAgent.WaitForSnapshotAction()))
mux.HandleFunc("POST /api/backgroundAgent/abort", genkit.Handler(backgroundAgent.AbortAction()))
```

One `waitForSnapshot` request holds for at most `aix.WithMaxSnapshotWait`
(default
25s), then answers with the row as it stands (`pending`/`aborting`); a direct
HTTP client must loop until settled. `aix.AgentHandle` (local or
`genkitx.DefineRemoteAgent`) does that for you. `AbortAction()` is non-nil only
when the store implements `aix.SnapshotSubscriber`. See
[deployment](agents-deployment.md).

## Status values (`aix.SnapshotStatus`)

- `SnapshotStatusPending`: still processing.
- `SnapshotStatusAborting`: abort requested; the worker is winding down. Not
  terminal: `Wait` keeps waiting.
- `SnapshotStatusCompleted`: finished successfully; read the result from
  `snap.State.Messages`.
- `SnapshotStatusFailed`: a turn broke; details on `snap.Error`, completed
  turns in `snap.State`. Resumable.
- `SnapshotStatusAborted`: stopped by the caller; `snap.State` holds the turns
  that finished. Resumable.
- `SnapshotStatusExpired`: the background worker stopped responding (its
  heartbeat went stale, e.g. a server restart). Computed on read, never
  persisted; terminal — the task can never complete.
