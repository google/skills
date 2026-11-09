# Working with Artifacts

> The `Artifact` type is stable and comes from `package:genkit/genkit.dart`, but
> the surrounding agent APIs (`defineAgent`, `currentSession`,
> `InMemorySessionStore`) are experimental and come from
> `package:genkit/experimental.dart`. Read [agents.md](agents.md) first.

**Artifacts** are named, content-bearing deliverables an agent produces during a
session — files, reports, code, etc. They live in the session (deduplicated by
name) and are returned in `res.artifacts` / tracked on the client's
`chat.artifacts`.

> **Dart has no `artifacts()` middleware yet.** Define `write_artifact` /
> `read_artifact` tools directly on top of the session artifact API
> (`ai.currentSession().addArtifacts()` / `getArtifacts()`).

> **Session artifacts vs. real files.** Artifacts (this page) live *in the
> session state* — they travel with the conversation and stream to the client.
> If instead you want the agent to work against **real files on disk** (a
> sandboxed workspace), use the `filesystem()` middleware from
> `package:genkit_middleware/filesystem.dart`
> (`filesystem(rootDirectory: ...)`, backed by `FilesystemPlugin()`), which
> gives the model `list_files` / `read_file` / `write_file` /
> `search_and_replace` tools rooted at a directory. See
> [middleware](genkit_middleware.md). The two approaches are complementary:
> session artifacts for conversation-scoped deliverables, `filesystem()` for
> persistent on-disk work.

- [Give the model artifact tools](#give-the-model-artifact-tools): Lines 37-99
- [How artifacts flow](#how-artifacts-flow): Lines 101-113
- [The Artifact shape](#the-artifact-shape): Lines 115-124
- [Programmatic access (inside tools and custom agents)](#programmatic-access-inside-tools-and-custom-agents): Lines 126-142
- [Reading artifacts on the client](#reading-artifacts-on-the-client): Lines 144-171

---

## Give the model artifact tools

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, currentSession
import 'package:schemantic/schemantic.dart';

import 'genkit.dart';

part 'workspace_agent.g.dart';

@Schema()
abstract class $WriteArtifactInput {
  @Field(description: 'The name (e.g. filename) of the artifact.')
  String get name;
  @Field(description: 'The full content of the artifact.')
  String get content;
}

@Schema()
abstract class $ReadArtifactInput {
  @Field(description: 'The name of the artifact to read.')
  String get name;
}

final writeArtifact = ai.defineTool(
  name: 'write_artifact',
  description: 'Create or overwrite a named artifact (e.g. a file). Pass the '
      'filename as "name" and the full content as "content".',
  inputSchema: WriteArtifactInput.$schema,
  outputSchema: SchemanticType.string(),
  fn: (input, _) async {
    final session = ai.currentSession()!;
    session.addArtifacts([
      Artifact(name: input.name, parts: [TextPart(text: input.content)]),
    ]);
    return .response('Wrote artifact "${input.name}".');
  },
);

final readArtifact = ai.defineTool(
  name: 'read_artifact',
  description: 'Read the content of a previously created artifact by name.',
  inputSchema: ReadArtifactInput.$schema,
  outputSchema: SchemanticType.string(),
  fn: (input, _) async {
    final session = ai.currentSession()!;
    final match = session.getArtifacts().where((a) => a.name == input.name);
    if (match.isEmpty) return .response('Artifact "${input.name}" not found.');
    return .response(match.first.parts.map((p) => p.text ?? '').join());
  },
);

final workspaceAgent = ai.defineAgent(
  name: 'workspaceAgent',
  system: 'You are a code generation assistant. Use write_artifact to create '
      'files (pass the filename as "name" and the full content as "content"). '
      'Use read_artifact to review or modify a previously created file.',
  tools: [writeArtifact, readArtifact],
  use: [retry()],
  store: InMemorySessionStore(),
);
```

## How artifacts flow

Adding an artifact to the session emits an event that the agent runtime forwards
to the client as an `artifact` stream chunk. Artifacts are **deduplicated by
name** — writing the same `name` again replaces it.

Run it; artifacts are produced via the tool and returned in the response:

```dart
final chat = workspaceAgent.chat();
final res = await chat.send(text: 'Write poem.txt with a poem about Genkit');
print(res.artifacts); // List<Artifact>
```

## The `Artifact` shape

```dart
// An artifact's content lives in `parts` (text parts). `name` and `metadata`
// are optional on the type but you should always set `name`.
final artifact = Artifact(
  name: 'poem.txt',
  parts: [TextPart(text: 'Roses are red…')],
);
```

## Programmatic access (inside tools and custom agents)

Use the active session. `ai.currentSession()` returns `null` when there's no
active session, so only call it inside an agent turn.

```dart
final session = ai.currentSession()!;

// Read all artifacts:
final all = session.getArtifacts(); // List<Artifact>
final found = all.where((a) => a.name == 'poem.txt').firstOrNull;

// Create / replace artifacts:
session.addArtifacts([
  Artifact(name: 'notes.md', parts: [TextPart(text: '# Notes')]),
]);
```

## Reading artifacts on the client

The `remoteAgent` client tracks artifacts on `chat.artifacts`; each response
exposes `res.artifacts`; and each streamed chunk exposes `chunk.artifact` as it
arrives.

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent

final agent = remoteAgent(url: '/api/workspaceAgent');
final chat = agent.chat();

final turn = chat.sendStream(text: 'Create index.html and styles.css');
await for (final chunk in turn.stream) {
  final artifact = chunk.artifact;
  if (artifact != null) {
    // artifact.name, artifact.parts - render/store it live.
  }
}
final res = await turn.response;
print(res.artifacts); // artifacts produced this turn
print(chat.artifacts); // all artifacts tracked for the session
```

> In [multi-agent orchestration](agents-multi-agent.md), the `agents()`
> delegation middleware can merge sub-agent artifacts into the parent session
> (namespaced by an invocation id) via its `artifactStrategy` option.
