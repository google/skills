# Agents

> **Agents are experimental.** The agent/session/snapshot APIs are NOT covered
> by semantic-versioning stability and live behind opt-in imports:
>
> - Server (agents, sessions, snapshots): `package:genkit/experimental.dart`
>   (alongside the stable `package:genkit/genkit.dart`).
> - Browser/HTTP client (`remoteAgent`, `AgentChat`, ...):
>   `package:genkit/experimental_client.dart` (alongside
>   `package:genkit/client.dart`).
> - `dart:io` extras (`FileSessionStore`):
>   `package:genkit/experimental_io.dart`.
>
> The entry points are marked `@experimental`, so importing them produces an
> `experimental_member_use` analyzer warning on the import line. Opt out once
> you
> accept the churn by adding to `analysis_options.yaml`:
>
> ```yaml
> analyzer:
>   errors:
>     experimental_member_use: ignore
> ```
>
> `CancellationController` / `CancellationToken` are stable and stay on
> `package:genkit/genkit.dart` / `client.dart`, not behind these imports.

An **agent** is a persistent, multi-turn conversation primitive built on top of
prompts + tools. Compared to a bare `ai.generate`/`ai.definePrompt` loop, an
agent adds:

- **Sessions**: multi-turn history tracked as immutable **snapshots**.
- **State**: typed session state (messages + custom data + artifacts).
- **Interrupts**: human-in-the-loop pause/resume.
- **Branching**: fork a conversation from any snapshot.
- **Detaching**: run a turn in the background and poll for the result.

Progressive disclosure — read the file for the level you need:

- This file: defining an agent, serving it, and **client-managed state** (no
  store).
- [Sessions & persistence](agents-sessions.md): `SessionStore`,
  `InMemorySessionStore`, `FileSessionStore`, `FirestoreSessionStore`.
- [Human-in-the-loop / interrupts](agents-human-in-the-loop.md): pausing for
  approval/input and resuming.
- [Branching](agents-branching.md): forking a conversation from a snapshot.
- [Background agents](agents-background.md): detaching long-running turns and
  polling.
- [Working with state](agents-state.md): typed custom session state and client
  auto-sync.
- [Artifacts](agents-artifacts.md): producing/reading named deliverables.
- [Multi-agent orchestration](agents-multi-agent.md): delegating to sub-agents.
- [Advanced custom agents](agents-custom.md): `defineCustomAgent` for full turn
  control.
- [Deploying agents](agents-deployment.md): serving multiple agents over HTTP
  with `GenkitRouter.addAgent`, shelf, CORS.

- [Setup](#setup): Lines 70-92
- [Define an agent](#define-an-agent): Lines 94-164
- [Agents and middleware go hand in hand](#agents-and-middleware-go-hand-in-hand): Lines 166-208
- [Chat with an agent (server-side)](#chat-with-an-agent-server-side): Lines 210-252
- [Verify an agent from the CLI (flow:run)](#verify-an-agent-from-the-cli-flowrun): Lines 254-268
- [Serve an agent over HTTP](#serve-an-agent-over-http): Lines 270-291
- [Consume an agent from a client (remoteAgent)](#consume-an-agent-from-a-client-remoteagent): Lines 293-328
- [Using from Flutter](#using-from-flutter): Lines 330-405
- [Client-managed state (no server store)](#client-managed-state-no-server-store): Lines 407-446

---

## Setup

Register the plugins your agents need on a shared `Genkit` instance. `retry` is
built into the core `package:genkit/genkit.dart` (no plugin); the other agentic
middleware (`agents`, `filesystem`, `skills`, `toolApproval`) come from
`package:genkit_middleware` and need their plugins registered.

```dart
// genkit.dart - shared instance + model refs.
import 'package:genkit/genkit.dart';
import 'package:genkit_google_genai/genkit_google_genai.dart';

/// The default (capable) model used by most agents.
final ModelRef defaultModel = googleAI.gemini('gemini-flash-latest');

/// A fast/cheap model for auxiliary tasks.
final ModelRef liteModel = googleAI.gemini('gemini-flash-lite-latest');

final Genkit ai = Genkit(
  plugins: [googleAI()],
  model: defaultModel,
);
```

## Define an agent

`ai.defineAgent` combines prompt + tool config + (optional) session store into a
single registered action.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore
import 'package:schemantic/schemantic.dart';

import 'genkit.dart';

part 'weather_agent.g.dart';

@Schema()
abstract class $GetWeatherInput {
  String get location;
}

@Schema()
abstract class $GetWeatherOutput {
  String get weather;
  String get temperature;
}

final getWeather = ai.defineTool(
  name: 'getWeather',
  description: 'Get the current weather for a given location.',
  inputSchema: GetWeatherInput.$schema,
  outputSchema: GetWeatherOutput.$schema,
  fn: (input, _) async => .response(GetWeatherOutput(
    weather: 'Sunny in ${input.location}',
    temperature: '71F',
  )),
);

final weatherAgent = ai.defineAgent(
  name: 'weatherAgent',
  system: 'You are a helpful weather assistant. Use the getWeather tool. '
      'Be concise.',
  tools: [getWeather],
  use: [retry()],
  store: InMemorySessionStore(),
);
```

Common `defineAgent` options:

- `name` (required): action name.
- `description`: shown to an orchestrator that delegates to this agent (see
  [multi-agent](agents-multi-agent.md)).
- `system` / `prompt`: the prompt template (same as `definePrompt`).
- `tools`: tools and interrupt-tools available to the agent.
- `model`: override the default model (e.g. `model: liteModel`).
- `use`: middleware layered on the turn (`retry()`, `filesystem(...)`, etc.).
- `store`: a `SessionStore` for server-side persistence. See
  [sessions](agents-sessions.md).
- `stateSchema`: a `SchemanticType<State>` describing custom session state.
- `maxTurns`: cap the tool-calling loop (e.g. `maxTurns: 30`).

> Schemas use the **schemantic** library (`@Schema()`, `.$schema`, `$`-prefixed
> abstract classes with a generated `.g.dart` part). See
> [references/schemantic.md](schemantic.md).

> **An agent needs a model.** Set `model:` on the agent, or a default `model:`
> on
> the shared `Genkit` instance (as the [Setup](#setup) snippet does). Without
> either, the turn fails with
> `AgentError(INVALID_ARGUMENT): Model must be provided`. The examples here rely
> on the instance default, so if you copy an agent block without it, add a
> `model:`.

## Agents and middleware go hand in hand

Agents and [middleware](genkit_middleware.md) are built for each other: the
`use: [...]` array is where you layer in sophisticated behavior without writing
it yourself — sub-agent delegation, filesystem access, skill loading, tool
approval, retries — each is one line.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore
import 'package:genkit_middleware/filesystem.dart';
import 'package:genkit_middleware/skills.dart';
import 'package:genkit_middleware/tool_approval.dart';

import 'genkit.dart';

final codingAgent = ai.defineAgent(
  name: 'codingAgent',
  system: 'You are an expert AI coding assistant working in a sandboxed '
      'workspace.',
  tools: [runShell, askUser], // your own custom tools/interrupts
  use: [
    // Require user approval (interrupt) before risky tools; reads/run auto-approved.
    // Order matters: keep toolApproval before filesystem.
    toolApproval(
      approved: ['list_files', 'read_file', 'use_skill', 'run_shell', 'ask_user'],
    ),
    // list_files / read_file / write_file / search_and_replace, sandboxed.
    filesystem(rootDirectory: workspaceDir),
    // Load coding conventions on demand via a use_skill tool.
    skills(skillPaths: [skillsDir]),
    // Automatic retry on transient model errors.
    retry(),
  ],
  store: InMemorySessionStore(), // needed for tool approval
  maxTurns: 30,
);
```

Register the corresponding plugins (`FilesystemPlugin()`, `SkillsPlugin()`,
`ToolApprovalPlugin()`) on the `Genkit` instance so the `use: [...]` refs
resolve at runtime (`retry()` is built in). See
[using middleware](genkit_middleware.md).

## Chat with an agent (server-side)

`agent.chat()` opens a conversation. A single `chat` carries state forward
automatically across turns.

```dart
final chat = weatherAgent.chat();

// Non-streaming turn:
final res = await chat.send(text: 'Weather in Tokyo?');
print(res.text);
print(res.snapshotId); // immutable checkpoint id for this turn

// Follow-up turn - history is carried automatically:
final res2 = await chat.send(text: 'What about Paris?');

// Streaming turn:
final turn = chat.sendStream(text: 'And London?');
await for (final chunk in turn.stream) {
  stdout.write(chunk.text);
}
final finalRes = await turn.response;
```

### Per-turn ambient context

`send`, `sendStream`, and `detach` all accept an optional `context` map —
ambient per-turn data (auth, request metadata, etc.) that tools can read via
`ctx.context` (and custom agents via `options.context`).

```dart
final res = await chat.send(
  text: 'What can I do?',
  context: {
    'auth': {'name': 'Ada', 'tier': 'pro'},
  },
);
```

> **In-process only.** The in-process transport honors `context`. The
> **`remoteAgent` (HTTP) transport rejects a non-empty `context` with
> `UnsupportedError`** — remote agents derive context server-side from the HTTP
> request (headers/auth), so don't pass it from the client.

## Verify an agent from the CLI (`flow:run`)

`genkit flow:run` only runs **flows**, not agents, so you can't `flow:run` an
agent directly. To exercise an agent from the CLI (e.g. a quick,
self-terminating
check), wrap one turn in a throwaway flow and run that:

```dart
final tryWeatherAgent = ai.defineFlow(
  name: 'tryWeatherAgent',
  fn: (String message, _) async =>
      (await weatherAgent.chat().send(text: message)).text,
);
// genkit flow:run tryWeatherAgent '"Weather in Tokyo?"' -- dart run main.dart
```

## Serve an agent over HTTP

Use `GenkitRouter` (`package:genkit/io.dart`) with `addAgent`
(`package:genkit/experimental_io.dart`). It mounts the turn route plus the
`/getSnapshot` and `/abort` companions the agent supports (based on its store).

```dart
import 'package:genkit/experimental_io.dart';
import 'package:genkit/io.dart';

void main() async {
  final genkit = GenkitRouter()
    ..addAgent(weatherAgent, path: '/api/weatherAgent');
  await genkit.serve(port: 8080); // plain dart:io, no shelf needed
}
```

In a shelf app: `Router()..mount('/api/', genkit.asShelfHandler())` (from
`genkit_shelf`).

For serving multiple agents, CORS/streaming headers for browser clients, and a
full server, see [Deploying agents](agents-deployment.md).

## Consume an agent from a client (`remoteAgent`)

The browser/Dart client lives in `package:genkit/client.dart`. `remoteAgent`
returns a typed HTTP client; `getSnapshotUrl`/`abortUrl` default to
`${url}/getSnapshot` and `${url}/abort`.

`remoteAgent` talks to any Genkit agent endpoint over HTTP, so the **backend is
fully interchangeable** — the agent can be implemented in Dart, JS/TypeScript,
or
Go. The wire protocol is the same; point `url` at whatever server hosts the
agent.

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, AgentError

final weather = remoteAgent(url: 'http://localhost:8080/api/weatherAgent');

final chat = weather.chat();
final turn = chat.sendStream(text: 'Weather in Tokyo?');
await for (final chunk in turn.stream) {
  stdout.write(chunk.text);
}
final res = await turn.response;
print('${res.snapshotId} ${chat.snapshotId} ${chat.state}');

// Multi-turn - the client carries state forward automatically:
await chat.send(text: 'What about Paris?');

// Errors surface as AgentError with an HTTP-ish status:
try {
  await remoteAgent(url: '$base/api/nope').chat().send(text: 'hi');
} catch (err) {
  if (err is AgentError) print(err.status);
}
```

## Using from Flutter

There is nothing Flutter-specific about the client: a Flutter app uses the same
`remoteAgent` from `package:genkit/client.dart` as any other Dart program. Two
things matter in a real app — **auth headers** and **lifecycle**.

Pass `headers` to attach per-request auth (e.g. a Firebase/OAuth bearer token).
It's a `FutureOr<Map<String, String>?> Function()`, so it can be async and is
called on every request:

```dart
final agent = remoteAgent(
  url: 'https://your-backend.example.com/api/weatherAgent',
  headers: () async => {
    'Authorization': 'Bearer ${await getIdToken()}',
  },
);
```

Create the agent once (e.g. in `initState`, or a provider/singleton) and
`close()` it when done to release the underlying HTTP client. To own the client
yourself, pass `httpClient:` — then it stays caller-owned and `close()` leaves
it
open.

A minimal streaming chat widget — pump `turn.stream` into the UI with
`setState`, then await `turn.response`:

```dart
import 'package:flutter/material.dart';
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, AgentApi

class ChatView extends StatefulWidget {
  const ChatView({super.key});
  @override
  State<ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<ChatView> {
  late final AgentApi _agent = remoteAgent(
    url: 'http://localhost:8080/api/weatherAgent',
  );
  late final _chat = _agent.chat();
  var _reply = '';

  @override
  void dispose() {
    _agent.close(); // release the HTTP client
    super.dispose();
  }

  Future<void> _send(String text) async {
    setState(() => _reply = '');
    final turn = _chat.sendStream(text: text);
    await for (final chunk in turn.stream) {
      setState(() => _reply += chunk.text); // append tokens live
    }
    await turn.response; // final AgentResponse (state already tracked on _chat)
  }

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Expanded(child: SingleChildScrollView(child: Text(_reply))),
      TextField(onSubmitted: _send),
    ],
  );
}
```

The `_chat` instance carries conversation state forward automatically across
turns (`_chat.state`, `_chat.messages`, `_chat.snapshotId`), exactly as on the
server. [Interrupts](agents-human-in-the-loop.md),
[custom state](agents-state.md), and [artifacts](agents-artifacts.md) all work
the same way from Flutter.

## Client-managed state (no server store)

If the agent has **no `store`**, the server is fully stateless and the session
state blob (messages + custom + artifacts) is owned by the caller. The
`remoteAgent` client tracks it and round-trips it on every turn automatically —
no `SessionStore`, no snapshot ids to manage.

```dart
// Server: no `store` → stateless. Client owns the state blob.
import 'package:genkit/experimental.dart'; // defineAgent

final weatherAgentStateless = ai.defineAgent(
  name: 'weatherAgentStateless',
  system: 'You are a helpful weather assistant. Use the getWeather tool. '
      'Be concise.',
  tools: [getWeather],
  use: [retry()],
);
```

```dart
// Client: reuse one `chat` and the state threads automatically.
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent

final agent = remoteAgent(url: '$base/api/weatherAgentStateless');
final chat = agent.chat();

await chat.send(text: 'Weather in London?');
await chat.send(text: 'Is it sunny in Tokyo?'); // remembers prior turns

// The tracked state is available after each turn:
print(chat.state);
print(chat.messages.length);
```

Use client-managed state when you don't want to run server-side storage. Use a
[session store](agents-sessions.md) when the server should own history, or when
you need branching or background execution.
([Interrupts](agents-human-in-the-loop.md) work either way.)
