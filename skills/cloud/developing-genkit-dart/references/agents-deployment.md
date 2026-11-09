# Deploying / Serving Agents over HTTP

> Uses `GenkitRouter` (`package:genkit/io.dart`) with `addAgent`
> (`package:genkit/experimental_io.dart`). Read [agents.md](agents.md) first.
> For general HTTP serving (standalone, shelf, auth), see
> [genkit_shelf.md](genkit_shelf.md).

`addAgent(agent)` mounts the agent's routes, defaulting to `/<agent name>`:

- `POST <path>`: runs a turn (streams with `?stream=true`). Always.
- `POST <path>/getSnapshot`: reads a snapshot. Only for server-managed agents
  (defined with a `store`). Needed for [snapshot restore](agents-branching.md)
  and [background](agents-background.md) polling.
- `POST <path>/abort`: cancels a [background](agents-background.md) turn. Only
  when the store can signal the running turn.

So a client-managed (stateless) agent gets only its turn route. These paths
match the `remoteAgent` client defaults (`${url}/getSnapshot`, `${url}/abort`),
so a client only needs the base `url`. `hideGetSnapshot: true` /
`hideAbort: true` remove supported routes; they can't force unsupported ones.

- [Serving several agents (shelf)](#serving-several-agents-shelf): Lines 30-78
- [Auth](#auth): Lines 80-84
- [CORS for browser clients](#cors-for-browser-clients): Lines 86-90
- [Registering agents/flows](#registering-agentsflows): Lines 92-98
- [Notes](#notes): Lines 100-111

---

## Serving several agents (shelf)

```dart
import 'dart:io';

import 'package:genkit/experimental_io.dart'; // addAgent
import 'package:genkit/io.dart'; // GenkitRouter, CorsOptions
import 'package:genkit_shelf/genkit_shelf.dart'; // asShelfHandler
import 'package:shelf/shelf.dart';
import 'package:shelf/shelf_io.dart' as io;
import 'package:shelf_router/shelf_router.dart';

import 'package:agents_sample/background_agent.dart';
import 'package:agents_sample/weather_agent.dart';
import 'package:agents_sample/weather_agent_stateless.dart';

void main() async {
  final api = GenkitRouter()
    ..addAgent(weatherAgent) // turn + /getSnapshot (+ /abort if supported)
    ..addAgent(backgroundAgent)
    ..addAgent(weatherAgentStateless) // turn only
    // Plain flows used by the UI, on custom paths:
    ..addAction(listWorkspaceFiles, path: '/workspace/files');

  final router = Router()
    // `mount` strips the prefix: agents are at /api/<agentName>.
    ..mount(
      '/api/',
      api.asShelfHandler(
        // Browser clients on another origin (Jaspr/Flutter web dev server).
        cors: const CorsOptions(
          allowedHeaders: ['Content-Type', 'Accept', 'X-Genkit-Stream-Id'],
        ),
      ),
    );

  final port = int.tryParse(Platform.environment['PORT'] ?? '') ?? 8080;
  final server = await io.serve(
    const Pipeline().addMiddleware(logRequests()).addHandler(router.call),
    InternetAddress.anyIPv4,
    port,
  );
  print('Agents API server running on http://localhost:${server.port}');
}
```

Without shelf, skip the `Router` and call
`api.serve(cors: const CorsOptions(...))`; pass `path: '/api/weatherAgent'` to
`addAgent` to keep the `/api` prefix.

## Auth

`addAgent(agent, contextProvider: bearerAuth)` applies the provider to every
route of that agent, so reading or aborting a snapshot is authorized like a
turn. See [genkit_shelf.md](genkit_shelf.md#auth-contextprovider).

## CORS for browser clients

Pass `CorsOptions` to `serve()` / `asShelfHandler()` (no `shelf_cors_headers`).
Browser streaming clients send `X-Genkit-Stream-Id`, which is **not** in the
default `allowedHeaders`, so list it explicitly as above.

## Registering agents/flows

Agents register with Genkit when their defining top-level `final` is evaluated.
Importing the module (e.g. in your server's `bin/server.dart`) and referencing
the agent, as `addAgent(...)` does, ensures the `defineAgent` call runs. Agents
referenced only by name (e.g. sub-agents for `agents(...)` middleware) must be
touched explicitly before use.

## Notes

- The wire body matches the Genkit client:
  `{ "data": <input>, "init": <init> }`.
- For persistence across restarts, use `FileSessionStore`
  (`package:genkit/experimental_io.dart`) or `FirestoreSessionStore`
  (`package:genkit_google_cloud`) instead of `InMemorySessionStore`. See
  [sessions](agents-sessions.md).
- Consuming these endpoints from Dart/Flutter/web uses `remoteAgent` from
  `package:genkit/experimental_client.dart` (alongside
  `package:genkit/client.dart`) — see
  [agents.md](agents.md#consume-an-agent-from-a-client-remoteagent).
