# Observability (Tracing, OpenTelemetry, Reflection API)

> Pluggable instrumentation, `otelgenai`, and the reflection API settings
> require Genkit Go v1.14.0+.

- [How tracing works](#how-tracing-works): Lines 13-27
- [Export OpenTelemetry GenAI semantic conventions (otelgenai)](#export-opentelemetry-genai-semantic-conventions-otelgenai): Lines 29-72
- [Custom instrumentation](#custom-instrumentation): Lines 74-94
- [Reflection API outside dev](#reflection-api-outside-dev): Lines 96-117

---

## How tracing works

- **In dev** (`genkit start`), Genkit posts spans straight to the Developer UI's
  telemetry server; no OpenTelemetry SDK is on that path. The Dev UI shows
  Genkit spans only: spans you write through OTel directly (`otelhttp`,
  `trace.SpanFromContext(ctx)`) go to your OTel backend, not the Dev UI.
- **Elsewhere**, spans go through pluggable instrumentation providers. The
  default, `&tracing.OTelInstrumentation{}`, creates OTel spans with `genkit:*`
  attributes on the `TracerProvider` you register. Genkit installs none itself,
  so nothing leaves the process until you (or a plugin such as Firebase)
  register
  one.
- Write span metadata with `tracing.SetSpanMetadata`. The old
  `tracing.TracerProvider`, `tracing.Tracer`, and `WriteTelemetry*` helpers are
  deprecated.

## Export OpenTelemetry GenAI semantic conventions (`otelgenai`)

Sends Genkit telemetry to any OTLP backend in the vendor-neutral `gen_ai.*`
shape (`chat <model>` spans, token usage and duration metrics).

```bash
go get github.com/firebase/genkit/go/plugins/otelgenai
go get go.opentelemetry.io/contrib/exporters/autoexport
```

```go
import (
	"github.com/firebase/genkit/go/core/tracing"
	"github.com/firebase/genkit/go/plugins/otelgenai"
)

// 1. The app owns the OTel SDK: register TracerProvider / MeterProvider /
//    LoggerProvider (e.g. with autoexport), and defer their Shutdown.
// 2. Set the GenAI instrumentation before genkit.Init:
tracing.SetInstrumentation(otelgenai.New(&otelgenai.Options{
	ContentCapturingMode: otelgenai.SpanOnly, // default NoContent; may contain PII
	EmitToolSpans:        true,
}))
g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.GoogleAI{}))
```

`otelgenai.Options`: `ContentCapturingMode` (`NoContent`, `SpanOnly`,
`EventOnly`, `SpanAndEvent`; falls back to
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`), `CaptureActionIO`,
`EmitToolSpans`, `DisableMetrics`, `ScopeName`, and explicit
`TracerProvider`/`MeterProvider`/`LoggerProvider` (default: the globals). Pass
`nil` for the defaults.

Gotchas:

- **It replaces the default encoding.** To export both, list both:
  `tracing.SetInstrumentation(&tracing.OTelInstrumentation{},
  otelgenai.New(nil))`.
- **Do not use it alone with the Firebase or Google Cloud telemetry plugins.**
  They build metrics/logs from the `genkit:*` attributes; without
  `OTelInstrumentation` in the list their Genkit metrics stop.
- **`EventOnly` content goes to the OTel logs signal**, which trace-only
  backends like Jaeger can't show.
- Runnable sample: `go/samples/otel-genai` (Jaeger + collector, no Docker).

## Custom instrumentation

Implement `tracing.Instrumentation` (`StartSpan` returns a `tracing.Span` with
`TraceInfo`, `SetMetadata`, and `End`). Genkit owns the run, so a provider
observes it but cannot skip or repeat it. Return a nil `Span` to ignore a span.

Scope providers to one context (one request, one agent run) with
`tracing.WithInstrumentation(ctx, providers...)`. `aix.Observer` is a ready-made
scoped provider that reports each model call, typed; the `Budget` middleware is
built on it:

```go
ctx = tracing.WithInstrumentation(ctx, aix.Observer{
	ModelDone: func(ctx context.Context, call *aix.ModelCall) {
		if u := call.Response.Usage; u != nil {
			meter.Add(tenant, call.Model, u)
		}
	},
})
out, err := supportAgent.RunText(ctx, msg)
```

## Reflection API outside dev

The CLI and Dev UI talk to the app through the reflection API. By default it
runs only under `GENKIT_ENV=dev` on `127.0.0.1:3100+`. To run it elsewhere
(e.g. staging), turn it on explicitly and protect it:

```bash
GENKIT_REFLECTION_ENABLED=true \
GENKIT_REFLECTION_HOST=0.0.0.0 \
GENKIT_REFLECTION_PORT=3100 \
GENKIT_REFLECTION_SECRET_TOKEN="$(openssl rand -hex 32)" \
./server
```

- `GENKIT_REFLECTION_ENABLED`: `true` on anywhere, `false` off even under dev.
  Any other value makes `genkit.Init` panic.
- `GENKIT_REFLECTION_SECRET_TOKEN`: every request must send it in the
  `x-genkit-reflection-secret` header (`/api/__health` stays open). Without it,
  anyone who can reach the port can run every flow, model, and tool.
- `genkit.WithReflectionPort(3200)` binds exactly that port (panics if taken);
  `0` lets the OS pick. The env var wins over the option, and neither turns the
  API on.
