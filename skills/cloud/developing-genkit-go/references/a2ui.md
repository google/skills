# A2UI (Agent-to-UI) generative UI

The A2UI plugin (`github.com/firebase/genkit/go/plugins/a2ui/exp`, imported as
`a2uix`) brings [A2UI](https://a2ui.org/), a transport-agnostic, JSON-based
streaming UI protocol, to Genkit Go agents. The plugin is in preview: it lives
under the `.../a2ui/exp` import path (package `exp`, aliased `a2uix` following
`aix` and `genkitx`) and its APIs may change in any minor version release.

A2UI builds on the experimental agent API
(`genkit.Init(ctx, genkit.WithExperimental())`). Read [Agents](agents.md)
first if you have not.

An A2UI-enabled agent streams more than prose. It streams interactive UI
**surfaces** (cards, lists, forms, buttons) that a client renders incrementally
as the model responds. The entire Go integration is a single model middleware:
add `&a2uix.Surfaces{}` to a generate/agent's `ai.WithUse` and nothing else
changes.

- [Go is server-only: bring your own client](#go-is-server-only-bring-your-own-client): Lines 28-53
- [Server: add the a2ui middleware](#server-add-the-a2ui-middleware): Lines 55-120
- [Serve the agent over HTTP](#serve-the-agent-over-http): Lines 122-173
- [Custom catalogs](#custom-catalogs): Lines 175-234
- [Security and the trust boundary](#security-and-the-trust-boundary): Lines 236-257
- [How it works](#how-it-works): Lines 259-278

---

## Go is server-only: bring your own client

**Go has no A2UI client/renderer.** The Go plugin is the server half: it injects
catalog capabilities into the prompt and rewrites the model's a2ui blocks into
a2ui data parts on the stream. To actually render surfaces in a browser or app,
use a JS or Dart/Flutter client that talks to your Go agent over HTTP. The Go
server and the JS/Dart client are wire-compatible (same `application/a2ui+json`
data parts, same catalog ids), so mix and match freely.

For the client half, refer to the A2UI reference in the Genkit **JS** or
**Dart**
skill (the `a2ui.md` reference in `developing-genkit-js` /
`developing-genkit-dart`).
Read their client sections and ignore their server/`a2ui()` middleware sections
(that is the JS/Dart server, replaced by the Go server below):

- **JS**: browser rendering with an `@a2ui/*` renderer (Lit/React/Angular) plus
  the `@genkit-ai/a2ui/client` helpers (`remoteAgent`, `a2uiEnvelopesFromParts`,
  `actionToMessage`).
- **Dart/Flutter**: rendering with the
  [`genui`](https://pub.dev/packages/genui) package plus the
  `package:genkit_a2ui/client.dart` helpers.

The client points `remoteAgent` at the Go endpoint (for example
`remoteAgent({ url: '/api/uiAgent' })`), and the client's renderer registers a
catalog under the **same catalog id** the Go server advertises.

## Server: add the `a2ui` middleware

Add `&a2uix.Surfaces{}` to the generate call (or agent inline prompt) via
`ai.WithUse`. That is the whole server-side setup. Registering `&a2uix.A2UI{}`
in `genkit.Init` is **optional**: it only surfaces the middleware and catalogs
in
the Dev UI. The middleware works via `ai.WithUse` regardless.

```go
import (
	"context"

	"github.com/firebase/genkit/go/ai"
	aix "github.com/firebase/genkit/go/ai/exp"
	"github.com/firebase/genkit/go/ai/exp/localstore"
	"github.com/firebase/genkit/go/genkit"
	genkitx "github.com/firebase/genkit/go/genkit/exp"
	a2uix "github.com/firebase/genkit/go/plugins/a2ui/exp"
	"github.com/firebase/genkit/go/plugins/googlegenai"
)

ctx := context.Background()
// &a2uix.A2UI{} is optional (Dev UI only); the middleware works without it.
g := genkit.Init(ctx,
	genkit.WithPlugins(&googlegenai.GoogleAI{}, &a2uix.A2UI{}),
	genkit.WithExperimental(),
)

uiAgent := genkitx.DefineAgent(g, "uiAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithSystem(
			"You help users. Render an A2UI surface whenever a result is " +
				"clearer shown than told (weather, comparisons, lists, forms). " +
				"Keep prose brief; put the substance in the UI."),
		ai.WithUse(&a2uix.Surfaces{}), // defaults to the bundled basic catalog
	},
	// Server-managed state: the client just passes a session id (remoteAgent
	// handles that), history lives in the store.
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

It works identically on a one-shot `genkit.Generate`:

```go
resp, err := genkit.Generate(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Show me the weather in Tokyo"),
	ai.WithUse(&a2uix.Surfaces{}),
)
```

### Middleware ordering

A2UI keeps per-turn streaming state (a stream parser and its minted surface ids)
for the model call it wraps. Place any retrying/fallback middleware (which
re-invokes the model) **outside** A2UI so each attempt gets a fresh A2UI turn.
`ai.WithUse(A, B)` means A wraps B:

```go
ai.WithUse(
	&middleware.Retry{MaxRetries: 5}, // outer: fresh A2UI turn per attempt
	&a2uix.Surfaces{},                   // inner
)
```

## Serve the agent over HTTP

Serve the agent with `genkit.Handler` (see
[Deploying agents](agents-deployment.md)).
A server-managed agent exposes three endpoints the `remoteAgent` client expects:
the turn endpoint plus its `/getSnapshot` and `/abort` companions.

```go
mux := http.NewServeMux()
mux.HandleFunc("POST /api/uiAgent", genkit.Handler(uiAgent))
mux.HandleFunc("POST /api/uiAgent/getSnapshot", genkit.Handler(uiAgent.GetSnapshotAction()))
mux.HandleFunc("POST /api/uiAgent/waitForSnapshot", genkit.Handler(uiAgent.WaitForSnapshotAction()))
mux.HandleFunc("POST /api/uiAgent/abort", genkit.Handler(uiAgent.AbortAction()))

log.Fatal(server.Start(ctx, "127.0.0.1:8080", mux))
```

If the browser is served from a different origin than the agent (for example a
Vite dev server on `:5173`), wrap the entire router/mux with permissive CORS
middleware (as shown in
[Deploying agents](agents-deployment.md#cors-for-browser-clients))
so that preflight OPTIONS requests are handled automatically without needing to
register duplicate bare paths. Behind a same-origin proxy (for example Vite
preview),
CORS is a no-op.

You can also drive the agent directly with curl:

```bash
curl -N -X POST 'http://localhost:8080/api/uiAgent?stream=true' \
  -H "Content-Type: application/json" \
  -d '{"data": {"message": {"role": "user", "content": [{"text": "What is the weather in Tokyo?"}]}}}'
```

### Config options

`&a2uix.Surfaces{}` fields (all optional):

| Field          | Default                             | Description                                                                                                  |
| -------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `Catalog`      | nil                                 | Inline `*a2uix.Catalog`. Wins over `CatalogID`, but is not serialized, so prefer `CatalogID` + `LoadCatalog`. |
| `CatalogID`    | `a2uix.DefaultCatalogID` (`"basic"`) | Id of a catalog registered with `a2uix.LoadCatalog`. Resolved from the registry at call time.                 |
| `Instructions` | `a2uix.InstructionsSystem`           | Where catalog capabilities are injected. `a2uix.InstructionsNone` injects nothing (supply your own).          |
| `Validate`     | `a2uix.ValidateWarn`                 | `ValidateWarn` logs and drops bad blocks; `ValidateStrict` returns an error; `ValidateOff` skips checking.   |
| `SurfaceID`    | fresh UUID                          | Surface-id policy. Set a fixed string to reuse one id per surface; empty mints a fresh UUID per surface.     |
| `Version`      | `a2uix.DefaultVersion` (`"v0.9"`)    | Protocol version stamped on envelopes. Validated against `a2uix.SupportedVersions`.                           |

Use `Validate: a2uix.ValidateStrict` during development to fail fast on
malformed
JSON or components outside the catalog. See
[Security](#security-and-the-trust-boundary)
for what strict does and does not check.

## Custom catalogs

The `CatalogID` is a **catalog id** resolved from the Genkit registry. The
bundled basic catalog (`a2uix.BasicCatalog()`, id `a2uix.BasicCatalogID`,
mirroring
`@a2ui/web_core`'s basic catalog) is the default and needs no registration. A
catalog describes the components the model may emit:

- `ID`: globally-unique URI (also used as `catalogId` on `createSurface`).
- `Components`: each an `a2uix.CatalogComponent` with `Name` (matches the
  renderer
  type), `Description` (one-line summary), and `Props` (a compact, model-facing
  text description of the component's props, kept as plain text to minimize
  prompt tokens).

Register a catalog with `a2uix.LoadCatalog`, then reference it by id. Start from
the basic catalog and add your own component:

```go
import a2uix "github.com/firebase/genkit/go/plugins/a2ui/exp"

weatherCatalog := a2uix.BasicCatalog()
weatherCatalog.ID = "https://my-app.org/catalogs/weather.json"
weatherCatalog.Components = append(weatherCatalog.Components, a2uix.CatalogComponent{
	Name:        "Gauge",
	Description: "A circular gauge visualizing a single numeric value.",
	Props:       "value: number or { path } binding (required); min?: number; max?: number; label?: string; unit?: string.",
})

if err := a2uix.LoadCatalog(g, weatherCatalog); err != nil {
	log.Fatalf("loading catalog: %v", err)
}

uiAgent := genkitx.DefineAgent(g, "uiAgent",
	aix.InlinePrompt{
		ai.WithModelName("googleai/gemini-flash-latest"),
		ai.WithUse(&a2uix.Surfaces{
			CatalogID: weatherCatalog.ID,
			Validate:  a2uix.ValidateStrict,
		}),
	},
	aix.WithSessionStore(localstore.NewInMemorySessionStore[any]()),
)
```

You can also load a catalog from a JSON file with
`a2uix.LoadCatalogFile(g, "./my-catalog.json")` (an object with an `id` string
and
a `components` array). To surface the bundled basic catalog in the Dev UI
alongside custom ones, call `a2uix.RegisterBasicCatalog(g)` (optional; the
middleware falls back to it either way). `LoadCatalog` is idempotent per id.

The **client must register a matching renderer under the same catalog id**, and
each component `Name` must match on both sides. Otherwise the model emits a
component the client cannot render. See the A2UI reference in the JS or Dart
skill for how to register a custom component (a genui `CatalogItem` in Dart, an
`@a2ui/*` renderer in JS). Catalogs live in the registry under value type
`a2uix.CatalogValueType`
(`"a2ui-catalog"`); the Dev UI lists them at
`GET /api/values?type=a2ui-catalog`.

## Security and the trust boundary

Generative UI moves model output into the client UI, so treat every surface an
agent emits as **untrusted input**. `Validate` (including `ValidateStrict`)
checks
envelope structure and component *type names* against the catalog only. It does
**not** validate component props or data-model values: model-controlled values
such as an `Image`'s url or a `Text`'s inline Markdown pass through untouched.
`ValidateStrict` is a well-formedness check, not a security boundary.

- **The client renderer/catalog owns prop sanitization.** Whatever renders a
  surface is responsible for escaping and sanitizing prop values before they
  reach the UI.
- **Restrict remote sources at the host.** On the web, serve the client with a
  Content Security Policy that limits `img-src` and other fetch directives to
  origins you trust.
- **Do not put secrets in the data model.** Anything bound into a surface's data
  model can be echoed back through an action's `context`.

For server-side control over props (for example, allow-listing image hosts), add
your own model middleware after `&a2uix.Surfaces{}` to inspect and rewrite the
emitted a2ui parts.

## How it works

A2UI rides on its own part channel: a Genkit `data` part with mime type
`application/a2ui+json` (`a2uix.A2UIMimeType`) whose data is
`{ "envelopes": [...] }`. On each model call, `&a2uix.Surfaces{}`:

1. Sanitizes inbound a2ui parts (a surface action sent back as the next turn, or
   replayed history) into model-readable text, so a model that does not
   understand the a2ui mime type can still reason about prior surfaces and user
   actions.
2. Injects the catalog's capabilities into the system prompt (unless
   `Instructions: a2uix.InstructionsNone`).
3. Intercepts the model output (streamed chunks and the final message).
4. Extracts `a2ui` fenced code blocks from the model's text.
5. Validates them against the catalog (per `Validate`).
6. Rewrites them into canonical a2ui data parts.

For a complete, runnable example (a Go backend plus a Vite + Lit web frontend),
see `go/samples/basic-middleware/a2ui` in the Genkit repo (it serves the same
agent the JS `a2ui` testapp's web UI talks to).

