# Agent Branching & Time Travel (Experimental)

> Requires a [session store](agents-sessions.md). See [agents.md](agents.md).

Every store-backed turn writes a `SessionSnapshot` keyed by `snapshot_id`, with
`parent_id` pointing at the previous turn. Reopening an earlier `snapshot_id`
with `await agent.load_chat(snapshot_id=...)` and sending a new message writes a
sibling snapshot under the same parent. The original timeline is untouched, and
both branches keep the same `session_id`.

Loading a snapshot restores the **entire** `SessionState` at that point:
`messages`, custom `state`, and `artifacts` revert together. `load_chat` only
resumes `completed` snapshots (see [sessions](agents-sessions.md) for
`load_chat` vs `chat(snapshot_id=...)`).

## Fork sibling timelines

```python
from genkit_google_genai import GoogleAI

from genkit import GenkitError
from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore

ai = Genkit(plugins=[GoogleAI()])

# reject_ambiguous_session=True makes session_id lookups fail loudly once a session forks
store = InMemorySessionStore(reject_ambiguous_session=True)

agent = ai.define_agent(
    name='designer',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='You design product landing pages. Reply in two short sentences.',
    store=store,
)


async def main() -> None:
    # 1. Shared root turn; bookmark snapshot_id as the fork point
    root = agent.chat()
    await root.send('Plan a landing page for an AI note-taking app.')
    checkpoint = root.snapshot_id
    session_id = root.session_id
    assert checkpoint and session_id

    # 2. Fork two independent branches from the same checkpoint
    minimal = await agent.load_chat(snapshot_id=checkpoint)
    await minimal.send('Direction: minimal with generous whitespace.')

    bold = await agent.load_chat(snapshot_id=checkpoint)
    await bold.send('Direction: dark mode and high contrast.')
    chosen_leaf = bold.snapshot_id
    assert chosen_leaf

    print(bold.session_id == minimal.session_id == session_id)
    # => True
    print([m.text for m in bold.messages if m.role == 'user'])
    # => ['Plan a landing page for an AI note-taking app.', 'Direction: dark mode and high contrast.']

    # 3. With two leaves, a bare session_id lookup raises FAILED_PRECONDITION
    try:
        await store.get_snapshot(session_id=session_id)
    except GenkitError as err:
        print(err.status)
        # => FAILED_PRECONDITION

    # 4. Continue linearly from the chosen branch leaf
    resumed = await agent.load_chat(snapshot_id=chosen_leaf)
    await resumed.send('Add a pricing section.')


if __name__ == '__main__':
    ai.run_main(main())
```

## Branching rules

- **Resume by `snapshot_id` after forking**: Once a session has multiple leaf
  snapshots, "latest turn for `session_id`" is ambiguous. By default the store
  picks the most recently created leaf. Pass `reject_ambiguous_session=True` on
  `InMemorySessionStore` or `FileSessionStore` to fail instead:
  `store.get_snapshot(session_id=...)` and `agent.get_snapshot(session_id=...)`
  raise `GenkitError` (`FAILED_PRECONDITION`), and a turn sent on
  `agent.chat(session_id=...)` returns a failed turn with that status on
  `res.error`.
- **Edit-and-resubmit / regenerate**: Store each turn's `snapshot_id` alongside
  the message in your UI. When a user edits an earlier prompt or clicks
  regenerate, load the parent turn's `snapshot_id` and send the revised message.
  Previous answers stay intact as sibling branches.
- **Artifact time travel**: When an agent edits files via `Artifacts()`
  (`genkit_middleware.exp`, see [artifacts](agents-artifacts.md)) or a tool,
  rewinding with `load_chat(snapshot_id=checkpoint)` restores `chat.artifacts`
  and `chat.state` to their values at that turn.
