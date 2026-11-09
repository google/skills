# Agent Artifacts (Experimental)

> See [agents.md](agents.md) · [sessions](agents-sessions.md).

Artifacts are named session deliverables — markdown reports, SQL migrations,
generated files — persisted in `SessionState.artifacts` and exposed as
`chat.artifacts`, `res.artifacts`, and streamed `chunk.artifact`. Writing an
artifact whose `name` already exists replaces the previous version in place.

- [Artifacts middleware (genkit_middleware.exp)](#artifacts-middleware-genkit_middlewareexp): Lines 16-66
- [Writing artifacts from tools and custom agents](#writing-artifacts-from-tools-and-custom-agents): Lines 68-107
- [Reading artifact text](#reading-artifact-text): Lines 109-120

---

## `Artifacts` middleware (`genkit_middleware.exp`)

Import `Artifacts` from `genkit_middleware.exp` (`Middleware()` does not
register it). On every model call, `Artifacts()` appends an `<artifacts>`
listing of the session's current artifacts (name, size, source) to the system
prompt, and gives the model `write_artifact` and `read_artifact` tools. Pass
`Artifacts(readonly=True)` to expose only `read_artifact`. Outside an agent
session the tools return an error result instead of raising.

On a store-backed agent, `agent.chat(artifacts=...)` raises `AgentInitError`
(`FAILED_PRECONDITION`); have the model write artifacts on a turn, or write them
from a tool or [custom agent](agents-custom.md). Store-less agents can seed
`artifacts=` ([state](agents-state.md)).

```python
from genkit_google_genai import GoogleAI
from genkit_middleware.exp import Artifacts

from genkit.exp import Genkit
from genkit.exp.agent import InMemorySessionStore

ai = Genkit(plugins=[GoogleAI()])

agent = ai.define_agent(
    name='workspaceAgent',
    model=GoogleAI.gemini('gemini-flash-latest'),
    system='Use write_artifact to save deliverables and read_artifact to inspect them.',
    use=[Artifacts()],
    store=InMemorySessionStore(),
)


async def main() -> None:
    chat = agent.chat()

    # 1. Stream the turn and observe artifacts as they are written
    turn = chat.send_stream('Write schema.sql for a multi-tenant invoices table.')
    async for chunk in turn.stream:
        if chunk.artifact is not None:
            print('wrote artifact:', chunk.artifact.name)
            # => wrote artifact: schema.sql
    await turn.response

    # 2. Inspect persisted session artifacts
    print([a.name for a in chat.artifacts])
    # => ['schema.sql']


if __name__ == '__main__':
    ai.run_main(main())
```

## Writing artifacts from tools and custom agents

Inside an `@ai.tool()`, get the active session with `current_session()` from
`genkit.exp` (`None` outside an agent turn). Inside a custom agent, call the
same method on the `SessionRunner`. `add_artifacts` takes a `list[Artifact]`,
replaces by name, and emits one `chunk.artifact` per artifact to streaming
callers:

```python
from genkit import Part
from genkit.exp import current_session
from genkit.exp.agent import Artifact


@ai.tool(name='exportAuditReport', description='Save an audit report as a session artifact.')
async def export_audit_report(markdown_body: str) -> dict[str, object]:
    sess = current_session()
    if sess is None:
        return {'ok': False, 'error': 'no active agent session'}

    await sess.add_artifacts([
        Artifact(
            name='audit-report.md',
            parts=[Part.from_text(markdown_body)],
            metadata={'source': 'exportAuditReport'},
        )
    ])
    return {'ok': True, 'name': 'audit-report.md'}
```

From a custom agent's `handle_turn`:

```python
from genkit import Part
from genkit.exp.agent import Artifact, SessionRunner


async def save_report(sess: SessionRunner, body: str) -> None:
    await sess.add_artifacts([Artifact(name='report.md', parts=[Part.from_text(body)])])
```

## Reading artifact text

`Part.text` is `str | None`. This matches what `read_artifact` returns to the
model:

```python
from genkit.exp.agent import Artifact


def artifact_text(artifact: Artifact) -> str:
    return '\n'.join(p.text for p in artifact.parts if p.text)
```
