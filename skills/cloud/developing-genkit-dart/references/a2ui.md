# A2UI (Agent-to-UI) generative UI

The `genkit_a2ui` package brings
> [A2UI](https://a2ui.org/), a transport-agnostic, JSON-based streaming UI
> protocol, to Genkit Dart agents.
>
> A2UI builds on the agent client. Server APIs come from
> `package:genkit/genkit.dart`; the browser/Flutter client comes from
> `package:genkit/client.dart`. Read [Agents](agents.md) first if you have not.

An A2UI-enabled agent streams more than prose. It streams interactive UI
**surfaces** (cards, lists, forms, buttons) that a client renders incrementally
as the model responds. The entire server-side integration is a single model
middleware: add `a2ui()` to an agent's `use` list and nothing else changes.

- [Install](#install): Lines 26-49
- [Server: add the a2ui() middleware](#server-add-the-a2ui-middleware): Lines 51-124
- [Client: render surfaces (Flutter and genui)](#client-render-surfaces-flutter-and-genui): Lines 126-184
- [Handling user actions](#handling-user-actions): Lines 186-248
- [Custom catalogs](#custom-catalogs): Lines 250-330
- [Security and the trust boundary](#security-and-the-trust-boundary): Lines 332-355
- [How it works](#how-it-works): Lines 357-378

---

## Install

On the **server** (the shelf app that hosts the agent), add `genkit_a2ui`
alongside the packages the agent already needs. List `genkit` explicitly even
though `genkit_a2ui` pulls it in transitively, otherwise `dart analyze` warns
with `depend_on_referenced_packages` (the server code imports
`package:genkit/genkit.dart` directly):

```bash
dart pub add genkit genkit_a2ui genkit_google_genai
```

To render surfaces you also need a renderer. The Flutter renderer for A2UI is
[`genui`](https://pub.dev/packages/genui). On the **client** Flutter app, add it
plus `a2ui_core`, and `genkit` + `genkit_a2ui` for the client helpers
(`remoteAgent`, `a2uiEnvelopesFromParts`, `actionToMessage`):

```bash
flutter pub add genkit genkit_a2ui 'genui:^0.10.4' 'a2ui_core:^0.1.1'
```

Pin these versions: the client code below targets the `genui` 0.10 API with
`a2ui_core` 0.1. An unpinned add can resolve an older `genui` and a newer,
incompatible `a2ui_core`, and the snippets then fail to compile.

## Server: add the `a2ui()` middleware

Add `a2ui()` to your agent's `use` list. That is the whole server-side setup.

**Dart specific:** Dart middleware is resolved by name from
the registry, so you MUST register `A2uiPlugin()` in `Genkit(plugins: [...])`
before referencing it via `a2ui()`.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, InMemorySessionStore
import 'package:genkit_a2ui/a2ui.dart';
import 'package:genkit_google_genai/genkit_google_genai.dart';

// A2uiPlugin() registers the a2ui() middleware so `use: [a2ui()]` resolves.
final ai = Genkit(plugins: [googleAI(), A2uiPlugin()]);

final uiAgent = ai.defineAgent(
  name: 'uiAgent',
  model: googleAI.gemini('gemini-flash-latest'),
  system:
      'You help users. Render an A2UI surface whenever a result is clearer '
      'shown than told (weather, comparisons, lists, forms). Keep prose brief; '
      'put the substance in the UI.',
  use: [a2ui()], // defaults to the bundled 'basic' catalog
  store: InMemorySessionStore(),
);
```

It works identically on a one-shot `ai.generate`:

```dart
final res = await ai.generate(
  model: googleAI.gemini('gemini-flash-latest'),
  prompt: 'Show me the weather in Tokyo',
  use: [a2ui()],
);
```

Serve the agent over HTTP with `GenkitRouter` (see
[Deploying agents](agents-deployment.md)). `addAgent` mounts the turn route plus
`/getSnapshot` and `/abort` for a server-managed agent:

```dart
import 'package:genkit/experimental_io.dart';
import 'package:genkit/io.dart';

void main() async {
  final genkit = GenkitRouter()..addAgent(uiAgent, path: '/api/uiAgent');
  await genkit.serve(
    port: 8080,
    // Flutter web runs on another origin.
    cors: const CorsOptions(
      allowedHeaders: ['Content-Type', 'Accept', 'X-Genkit-Stream-Id'],
    ),
  );
}
```

### Options

Pass options to `a2ui(...)`:

| Option         | Default    | Description                                                                                             |
| -------------- | ---------- | ------------------------------------------------------------------------------------------------------- |
| `catalog`      | `'basic'`  | Id of the catalog describing what the agent may render.                                                 |
| `instructions` | `'system'` | Where to inject catalog capabilities. `'none'` injects nothing (supply your own instructions instead).  |
| `validate`     | `'warn'`   | Validate emitted envelopes. `'warn'` logs and drops bad blocks; `'strict'` throws; `'off'` skips it.    |
| `surfaceId`    | fresh UUID | Surface id policy. Defaults to a new UUID per surface; pass a fixed string to reuse one id per surface. |
| `version`      | `'v0.9'`   | Protocol version stamped on envelopes.                                                                  |

Use `validate: 'strict'` during development to fail fast on malformed JSON or
components outside the catalog. See [Security](#security-and-the-trust-boundary)
for what `'strict'` does and does not check.

## Client: render surfaces (Flutter and genui)

`package:genkit_a2ui/client.dart` is browser/Flutter-safe (no `dart:io`).
Consume
the agent with `remoteAgent`, pull A2UI envelopes off each chunk's content with
`a2uiEnvelopesFromParts`, convert each envelope to a genui `A2uiMessage`, and
feed
it to a `SurfaceController`. A2UI travels as `data` parts on the raw model
chunk,
so read them from `chunk.raw.modelChunk?.content`.

```dart
import 'package:a2ui_core/a2ui_core.dart' as core;
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent, AgentApi
import 'package:genkit_a2ui/client.dart';
import 'package:genui/genui.dart' hide basicCatalogId, DataPart;

// remoteAgent returns an AgentApi<State> (not a `RemoteAgent`).
final agent = remoteAgent(
  url: 'http://localhost:8080/api/uiAgent',
  getSnapshotUrl: 'http://localhost:8080/api/uiAgent/getSnapshot',
  abortUrl: 'http://localhost:8080/api/uiAgent/abort',
);
final chat = agent.chat();

// genui registers an empty stub for an unknown catalog id, so re-tag its basic
// catalog with the id the plugin's bundled basic catalog advertises.
final catalog = BasicCatalogItems.asCatalog().copyWith(catalogId: basicCatalogId);
final surfaceController = SurfaceController(catalogs: [catalog]);

final turn = chat.sendStream(text: 'What is the weather in Tokyo?');
await for (final chunk in turn.stream) {
  if (chunk.text.isNotEmpty) appendProse(chunk.text);
  for (final envelope in a2uiEnvelopesFromParts(chunk.raw.modelChunk?.content)) {
    surfaceController.handleMessage(core.A2uiMessage.fromJson(envelope));
  }
}
await turn.response;
```

**Dart specific:** importing both `package:genkit/client.dart` and
`package:genui/genui.dart` collides on two symbols, so hide genui's:

- `basicCatalogId`: both packages export one with *different* values. You want
  the plugin's; if the ids do not match, genui registers an empty stub and
  surfaces render blank.
- `DataPart`: genkit's client and genui (via `genai_primitives`) both export a
  `DataPart` class, so referencing `DataPart` unqualified is ambiguous.

Hence `import 'package:genui/genui.dart' hide basicCatalogId, DataPart;`.

`remoteAgent` manages the session id for you, so a single `chat` keeps the whole
conversation server-side (the agent's session store holds history).

In a Flutter app, listen to `surfaceController.surfaceUpdates` to add a
`Surface(surfaceContext: surfaceController.contextFor(id))` widget to your chat
log when a `SurfaceAdded` update arrives, and listen to
`surfaceController.onSubmit` to route actions back to the agent (see below).

## Handling user actions

When a user interacts with a surface (for example, presses a `Button`),
`surfaceController.onSubmit` emits a genui `ChatMessage`. That message is *not*
an
`A2uiClientAction` you can hand straight to `actionToMessage`: genui reports the
interaction as a `UiInteractionPart` whose payload is a JSON string
`{ "version": ..., "action": { name, surfaceId, widgetId, context } }`. Decode
that part into an `A2uiClientAction`, then `actionToMessage(...)` it and send it
as the next turn:

```dart
import 'dart:convert';
import 'package:genkit_a2ui/client.dart';
import 'package:genui/genui.dart' hide basicCatalogId, DataPart;

surfaceController.onSubmit.listen((ChatMessage message) {
  final action = _actionFromSubmit(message);
  // Guard against re-entrancy: ignore a new action while a turn is still
  // streaming, otherwise two concurrent turns interleave.
  if (action == null || busy) return;
  final turn = chat.sendStream(message: actionToMessage(action));
  // ...consume turn.stream like above (prose + a2uiEnvelopesFromParts)...
});

/// Extracts an [A2uiClientAction] from a genui onSubmit [ChatMessage].
A2uiClientAction? _actionFromSubmit(ChatMessage message) {
  for (final part in message.parts) {
    final interaction = part.asUiInteractionPart?.interaction;
    if (interaction == null) continue;
    final decoded = jsonDecode(interaction);
    final action = decoded is Map ? decoded['action'] : null;
    if (action is Map) {
      final m = action.cast<String, dynamic>();
      return A2uiClientAction(
        name: (m['name'] as String?) ?? 'action',
        surfaceId: (m['surfaceId'] as String?) ?? '',
        // genui names it `widgetId`; A2uiClientAction calls it sourceComponentId.
        sourceComponentId: (m['widgetId'] as String?) ?? '',
        timestamp: DateTime.now().toUtc().toIso8601String(),
        context: (m['context'] as Map?)?.cast<String, dynamic>() ?? const {},
      );
    }
  }
  return null;
}
```

The action's `name` is sent as the user message; the full action (including its
`context`) is attached as an a2ui data part so the agent can react to it.

### Forms

Input components (`TextField`, `CheckBox`, `Slider`) do **not** send their
values
automatically. To capture what the user entered, the model must:

1. Bind each input's `value` to a data-model path (`{ "path": "/email" }`).
2. Echo those same paths in the submit `Button`'s `action.event.context`.

The catalog capabilities injected into the system prompt already instruct the
model to do this. Without both steps, the action arrives with an empty
`context`.

## Custom catalogs

The `catalog` option is a **catalog id** resolved from the Genkit registry. The
bundled `'basic'` catalog is the default and needs no registration. A catalog
describes the components the model may emit:

- `id`: globally-unique URI (also used as `catalogId` on `createSurface`).
- `components`: each with `name` (matches the renderer type), `description`
  (one-line summary), and `props` (a compact, model-facing text description of
  the component's props, kept as plain text to minimize prompt tokens).

A custom catalog has two halves that MUST agree on a catalog id: the **server**
catalog (what the model is told it may render, and validated against) and the
**client** renderer (the widgets that actually paint the components). Define the
id once and share it.

### Server: register the catalog

Start from `basicCatalog` and add your own component, then register it with
`loadCatalog` before serving any turns and reference it by id:

```dart
import 'package:genkit_a2ui/a2ui.dart';

const weatherCatalogId = 'com.example.a2ui.weather';

final weatherCatalog = A2uiCatalog(
  id: weatherCatalogId,
  components: [
    ...basicCatalog.components,
    const A2uiCatalogComponent(
      name: 'Gauge',
      description: 'A circular gauge visualizing a single numeric value.',
      props: 'value: number or { path } binding (required); min?: number; '
          'max?: number; label?: string; unit?: string.',
    ),
  ],
);

// Call once at startup, before the agent handles a turn.
Future<void> registerCatalogs() =>
    loadCatalog(ai, id: weatherCatalogId, catalog: weatherCatalog);

final uiAgent = ai.defineAgent(
  name: 'uiAgent',
  model: googleAI.gemini('gemini-flash-latest'),
  use: [a2ui(catalog: weatherCatalogId, validate: 'strict')],
  store: InMemorySessionStore(),
);
```

You can also load a catalog from a JSON file:
`loadCatalog(ai, id: 'my-catalog', file: './my-catalog.json')`.

### Client: register a matching widget

On the Flutter client, implement the matching component as a genui `CatalogItem`
(a `name`, a prop `dataSchema`, and a `widgetBuilder`) and re-tag the catalog
with
the SAME id:

```dart
final gaugeCatalogItem = CatalogItem(
  name: 'Gauge', // MUST match the server component name
  dataSchema: _gaugeSchema, // built with json_schema_builder's `S`
  widgetBuilder: (itemContext) {
    // Resolve { path } bindings via genui's Bound* widgets, then paint.
    return _GaugeWidget(...);
  },
);

final catalog = BasicCatalogItems.asCatalog().copyWith(
  newItems: [gaugeCatalogItem],
  catalogId: weatherCatalogId, // MUST match the server catalog id
);
```

If the `name` or catalog id disagree, the model emits a component the client
cannot render, or the client registers widgets under an id no surface
references.
Catalogs live in the registry under value type `a2ui-catalog`.

## Security and the trust boundary

Generative UI moves model output into the UI, so treat every surface an agent
emits as **untrusted input**. The `validate` option (including `'strict'`)
checks
envelope structure and component *type names* against the catalog only. It does
**not** validate component props or data-model values: model-controlled values
such as `Image.url` and `Text` (inline Markdown that a renderer may turn into
rich content) pass through untouched. `'strict'` is a well-formedness check, not
a
security boundary.

- **The renderer/catalog owns prop sanitization.** Whatever renders a surface
  (for example `genui` plus your Markdown renderer) is responsible for escaping
  and sanitizing prop values before they reach the UI.
- **Restrict remote sources at the host.** On the web, serve the app with a
  Content Security Policy that limits `img-src` and other fetch directives to
  origins you trust.
- **Do not put secrets in the data model.** Anything bound into a surface's data
  model can be echoed back through an action's `context`.

For server-side control over props (for example, allow-listing image hosts), add
your own model middleware after `a2ui()` to inspect and rewrite the emitted a2ui
parts.

## How it works

A2UI rides on its own part channel: a Genkit `data` part with mime type
`application/a2ui+json` whose `data` is `{ "envelopes": [...] }`. On each model
call inside the agent's tool loop, `a2ui()`:

1. Injects the catalog's capabilities into the system prompt (unless
   `instructions: 'none'`).
2. Intercepts the model output (streamed chunks and the final message).
3. Extracts `a2ui` fenced code blocks from the model's text.
4. Validates them against the catalog (per `validate`).
5. Rewrites them into canonical a2ui data parts.

Inbound a2ui parts (a surface action sent back as the next turn, or replayed
history) are summarized into plain text before the underlying model sees them,
so
a model that does not understand the a2ui mime type can still reason about prior
surfaces and user actions.

For a complete, runnable example (a shelf server plus a Flutter genui client
with
a custom `Gauge` catalog), see the `a2ui` testapp in the Genkit Dart repo.

