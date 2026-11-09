# Serving over HTTP (`GenkitRouter`, `genkit_shelf`)

HTTP serving lives in core `package:genkit/io.dart` (`GenkitRouter`, plain
`dart:io`, no web framework). `genkit_shelf` is only an adapter that mounts a
`GenkitRouter` into a [shelf](https://pub.dev/packages/shelf) app.

> There is no `startFlowServer` and no `FlowWithContextProvider`. Do not add
> `shelf_cors_headers`; CORS is `CorsOptions`.

- [Standalone server (no shelf)](#standalone-server-no-shelf): Lines 20-55
- [Existing shelf app](#existing-shelf-app): Lines 57-88
- [Own dart:io server](#own-dartio-server): Lines 90-104
- [Auth: contextProvider](#auth-contextprovider): Lines 106-121
- [Agents](#agents): Lines 123-127
- [CORS](#cors): Lines 129-134
- [Older clients](#older-clients): Lines 136-144

---

## Standalone server (no shelf)

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/io.dart';
import 'package:genkit_google_genai/genkit_google_genai.dart';

void main() async {
  final ai = Genkit(plugins: [googleAI()]);

  final flow = ai.defineFlow(
    name: 'myFlow',
    inputSchema: .string(),
    outputSchema: .string(),
    fn: (String input, _) async => 'Hello $input',
  );

  // Any action can be served, including models (here for remote clients
  // using defineRemoteModel).
  final geminiFlash = googleAI().model('gemini-flash-latest');

  final genkit = GenkitRouter()
    ..addAction(flow) // POST /myFlow (stream with ?stream=true)
    ..addAction(geminiFlash, path: '/v1/gemini');

  await genkit.serve(
    port: 8080, // default: $PORT, then 3400. Host defaults to 0.0.0.0.
    cors: const CorsOptions(allowedOrigins: ['https://myapp.dev']), // default: no CORS
  );
}
```

`addAction` returns `void`; use cascades (`..`), not method chaining.
`serve` logs its address via `package:logging`
(`Logger.root.onRecord.listen(print)`
to see it).

## Existing shelf app

```dart
import 'dart:io';

import 'package:genkit/io.dart';
import 'package:genkit_shelf/genkit_shelf.dart';
import 'package:shelf/shelf.dart';
import 'package:shelf/shelf_io.dart' as io;
import 'package:shelf_router/shelf_router.dart';

void main() async {
  // `flow`, `geminiFlash`: as above. `bearerAuth`: see Auth below.
  final genkit = GenkitRouter()
    ..addAction(flow) // served at /api/myFlow below
    ..addAction(geminiFlash, contextProvider: bearerAuth);

  final app = Router()
    ..get('/health', (Request request) => Response.ok('OK'))
    ..mount('/api/', genkit.asShelfHandler(cors: const CorsOptions()));

  await io.serve(
    const Pipeline().addMiddleware(logRequests()).addHandler(app.call),
    InternetAddress.anyIPv4,
    8080,
  );
}
```

Unknown paths get a `404`, so it also works in a shelf `Cascade`. To serve one
action on a route of your choosing:
`router.post('/myFlow', shelfHandler(flow, contextProvider: bearerAuth))`.

## Own `dart:io` server

```dart
final server = await HttpServer.bind(InternetAddress.anyIPv4, 8080);
await for (final request in server) {
  if (await genkit.handleHttpRequest(request, basePath: '/api')) continue;
  // ... your own routes; or ioHandler(action) for a single action
  request.response
    ..statusCode = HttpStatus.notFound
    ..close();
}
```

Other frameworks: adapt the framework-neutral `GenkitRouter.handle` /
`actionHandler` (`GenkitHttpRequest` -> `GenkitHttpResponse`), plus `withCors`.

## Auth: `contextProvider`

A `ContextProvider` gets a framework-neutral `RequestData` (lowercased
`headers`, `method`, parsed `input`) and returns the action context
(`ctx.context` in the flow). A thrown `GenkitException` is answered with its
status; anything else with `403`.

```dart
Future<Map<String, dynamic>> bearerAuth(RequestData request) async {
  final user = await checkUserToken(request.headers['authorization']);
  if (user == null) {
    throw GenkitException('Unauthorized', status: StatusCode.unauthenticated); // 401
  }
  return {'userId': user.id};
}
```

## Agents

`addAgent` (from `package:genkit/experimental_io.dart`) mounts the turn route
plus the `/getSnapshot` and `/abort` companions the agent supports. See
[agents-deployment.md](agents-deployment.md).

## CORS

`CorsOptions()` defaults: any origin, `Content-Type` + `Authorization`
request headers, exposes `x-genkit-trace-id` / `x-genkit-span-id`. Browser
streaming clients (JS `remoteAgent`/`streamFlow`) also send
`X-Genkit-Stream-Id`, so add it to `allowedHeaders` for those.

## Older clients

Streamed failures end with a `data: {"error": ...}` frame. Dart/Flutter clients
on `package:genkit` 0.17 or earlier only understand the older frame; while such
clients are in the field, use `GenkitRouter(sendLegacyErrorFrame: true)` (also
on `shelfHandler`/`ioHandler`).

Consume served endpoints with `defineRemoteAction` / `defineRemoteModel`
(`package:genkit/client.dart`), `remoteAgent`, or the JS client.
