# Phase 4: Distributed trace instrumentation and Cloud Logging correlation

- [1. Architecture layers, propagation contract, and workflow](#1-architecture-layers-propagation-contract-and-workflow): Lines 26-89
- [2. HTTP and gRPC wrapping](#2-http-and-grpc-wrapping): Lines 90-138
- [3. W3C carrier over Pub/Sub message attributes](#3-w3c-carrier-over-pubsub-message-attributes): Lines 139-238
- [4. Cloud Logging trace-correlated slog handler](#4-cloud-logging-trace-correlated-slog-handler): Lines 239-355
- [5. Generic port decorator for stage spans](#5-generic-port-decorator-for-stage-spans): Lines 356-417
- [6. TracerProvider: OTLP export, sampler, shutdown](#6-tracerprovider-otlp-export-sampler-shutdown): Lines 418-511
- [7. Deterministic unit tests with the in-memory exporter](#7-deterministic-unit-tests-with-the-in-memory-exporter): Lines 512-546

Grounding documentation:

-   Cloud Trace with OpenTelemetry in Go: https://docs.cloud.google.com/trace/docs/setup/go-ot.md.txt
-   Migrate from the Trace exporter to OTLP: https://docs.cloud.google.com/trace/docs/migrate-to-otlp-endpoints.md.txt
-   Cloud Run trace sampling behaviour: https://docs.cloud.google.com/run/docs/trace.md.txt
-   Pub/Sub client-library tracing (`googclient_traceparent`): https://docs.cloud.google.com/pubsub/docs/open-telemetry-tracing.md.txt
-   Cloud Logging structured logging special fields: https://docs.cloud.google.com/logging/docs/structured-logging.md.txt

Instrument services end to end so inbound HTTP/gRPC requests start a server
span, outbound calls and Pub/Sub publishes carry W3C Trace Context forward,
consumers continue the same trace, database stages emit child spans, and every
log line carries `logging.googleapis.com/trace`. Every Go block headed
`// file:` is compiled and unit-tested (`go test -race`, `otel` v1.47.0,
`semconv` v1.37.0).

## 1. Architecture layers, propagation contract, and workflow

Install OpenTelemetry packages (Go example; Python uses
`opentelemetry-instrument` + `opentelemetry-exporter-otlp`, Java the
`-javaagent` OpenTelemetry agent, Node.js
`@opentelemetry/auto-instrumentations-node`):

```bash
go get go.opentelemetry.io/otel@latest \
  go.opentelemetry.io/otel/sdk@latest \
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc@latest \
  go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp@latest \
  go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc@latest
```

Export spans over OTLP to `telemetry.googleapis.com:443` with
`roles/telemetry.tracesWriter` (`telemetry.googleapis.com` API) and
`roles/logging.logWriter` (`logging.googleapis.com` API). The legacy
`opentelemetry-operations-go/exporter/trace` package (`roles/cloudtrace.agent`)
is deprecated (archived after 2027-01-01) and is an escape hatch only for code
that already depends on it.

Where instrumentation lives:

| Layer | Rule | Rationale |
| --- | --- | --- |
| Domain and use cases | **Default:** no OpenTelemetry imports; pass `ctx` through every port. | Keeps business logic testable without SDKs and insulated from SDK upgrades. |
| Primary adapters (Pub/Sub consumer, HTTP, gRPC) | Start the root or consumer span; extract upstream context. | The adapter is the first code that sees the carrier. |
| Secondary adapters (repository, publisher, external clients) | Wrap port calls with a tracing decorator producing child spans per stage. | Per-stage latency (`db.stage`, `db.validate`, `db.commit`) pinpoints bottlenecks. |
| Application layer (escape hatch) | Call `otel.Tracer(...)` directly only where the codebase permits SDK imports in services. | Simpler when no clean-architecture constraint exists. |

Propagation and correlation contract:

| Boundary | Operation | Keys and format | Rationale |
| --- | --- | --- | --- |
| Inbound HTTP / gRPC | Wrap handlers per route (`otelhttp.NewHandler`, `otelgrpc.NewServerHandler` stats handler) so a `SpanKindServer` span starts from incoming `traceparent`. | `traceparent`, `tracestate` headers; `http.route` (per-route wrapping on Go 1.22+ `ServeMux`), `rpc.service` | Works with no Pub/Sub at all. |
| Outbound HTTP / gRPC | Use instrumented clients (`otelhttp.NewTransport`, `otelgrpc.NewClientHandler`) so downstream calls become `SpanKindClient` children. | same headers | Makes the critical path visible hop by hop (input to Phase 1). |
| Pub/Sub hop, **default** | Enable the client library's built-in tracing on **both** sides (`pubsub.ClientConfig{EnableOpenTelemetryTracing: true}`); in the `Receive` callback start child spans from the callback `ctx` and **do not re-extract** from attributes (never pass trace IDs in the message payload). | library writes `googclient_traceparent` / `googclient_tracestate` | Publisher, queue dwell, and consumer spans are emitted in one trace; manual re-extraction would detach them. |
| Pub/Sub hop, **escape hatch** | Inject `traceparent` into message attributes on publish and extract it (falling back to `googclient_*` keys) to start a `SpanKindConsumer` span, **only** when one side is not a Google client library with tracing enabled (push subscriptions, Eventarc, Cloud Run functions, or a foreign producer). | `traceparent`, `messaging.system=gcp_pubsub`, `messaging.destination.subscription.name`, `messaging.operation.name=process` | Preserves continuity where the client library cannot do it automatically. |
| Database and stage operations | Child spans (`SpanKindClient`/`Internal`); `RecordError` + `SetStatus(codes.Error, ...)` on failure; leave status `Unset` on success. | `db.system`, low-cardinality `{operation} {target}` name (never open spans per loop iteration or put IDs/payloads in span names) | Attributes failures to the exact stage without blowing up trace cardinality. |
| Structured logs | Log with context-aware calls (`InfoContext`, `ErrorContext`) through a handler that emits Cloud Logging fields at the top level even inside `WithGroup`. | `logging.googleapis.com/trace` = `projects/{project_id}/traces/{trace_id}`, `logging.googleapis.com/spanId`, `logging.googleapis.com/trace_sampled`, top-level `severity` (`WARN` → `WARNING`) and `message` | Enables one-click log-to-trace navigation; context-free log calls lose correlation. |

Scope rules for Phase 4:

-   **Synchronous HTTP/gRPC-only services (no Pub/Sub)**: use sections 2 and
    4–7 only (`TracerProvider` with the Cloud Run
    `WithRemoteParentNotSampled` sampler rule, `otelhttp`, `otelgrpc` stats
    handlers, DB stage decorator, `slog` correlation); **never** introduce
    Pub/Sub topics or attribute carriers.
-   **Cloud Run missing-traces trap**: Cloud Run injects a `traceparent` header
    on every request with the `sampled` flag cleared (`00`) for all but ~0.1
    req/s/instance. A plain `ParentBased(TraceIDRatioBased(ratio))` sampler
    obeys that cleared remote parent flag and drops almost every trace! Fix
    the sampler first using
    `ParentBased(TraceIDRatioBased(ratio), WithRemoteParentNotSampled(TraceIDRatioBased(ratio)))`
    (never recommend `AlwaysSample` in production without warning about cost,
    and do not blame the exporter or IAM before fixing the sampler).
-   **Querying existing traces**: if the user asks how to find slow traces
    (e.g. *"all traces slower than 2s"*), answer with the Cloud Trace console
    or API (https://docs.cloud.google.com/trace/docs/finding-traces.md.txt) or
    the `cloud-trace-querying` skill — never answer with OpenTelemetry setup
    code, never require re-instrumenting first, and never invent a trace query
    language.

## 2. HTTP and gRPC wrapping

```go
// file: telemetry/httpgrpc.go
package telemetry

import (
	"net/http"

	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"google.golang.org/grpc"
)

// WrapHandler instruments one inbound HTTP route with a SpanKindServer span
// that continues the incoming traceparent. Wrap per route (not the whole mux)
// so http.route is populated from the Go 1.22+ ServeMux pattern.
func WrapHandler(pattern string, h http.Handler) http.Handler {
	return otelhttp.NewHandler(h, pattern)
}

// NewHTTPClient returns an outbound client whose requests become
// SpanKindClient children and carry traceparent downstream.
func NewHTTPClient(base http.RoundTripper) *http.Client {
	if base == nil {
		base = http.DefaultTransport
	}
	return &http.Client{Transport: otelhttp.NewTransport(base)}
}

// GRPCServerOption instruments all inbound gRPC calls (stats handler API;
// the older interceptor API is deprecated).
func GRPCServerOption() grpc.ServerOption {
	return grpc.StatsHandler(otelgrpc.NewServerHandler())
}

// GRPCDialOption instruments all outbound gRPC calls.
func GRPCDialOption() grpc.DialOption {
	return grpc.WithStatsHandler(otelgrpc.NewClientHandler())
}
```
```go
mux := http.NewServeMux()
mux.Handle("GET /orders/{id}", telemetry.WrapHandler("GET /orders/{id}", getOrder))
client := telemetry.NewHTTPClient(nil)
srv := grpc.NewServer(telemetry.GRPCServerOption())
conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()), telemetry.GRPCDialOption())
```

## 3. W3C carrier over Pub/Sub message attributes

Default for the Pub/Sub hop is the client library's built-in tracing (pass
`&pubsub.ClientConfig{EnableOpenTelemetryTracing: true}` to
`pubsub.NewClientWithConfig` on both publisher and subscriber; start child spans
from the `Receive` callback `ctx`). Use the carrier below only as the escape
hatch for push, Eventarc, Cloud Run functions, or foreign producers:

```go
// file: telemetry/carrier.go
package telemetry

import (
	"context"

	"go.opentelemetry.io/otel"
	semconv "go.opentelemetry.io/otel/semconv/v1.37.0"
	"go.opentelemetry.io/otel/trace"
)

// AttributeCarrier adapts Pub/Sub message attributes to the OpenTelemetry
// propagation.TextMapCarrier interface. It reads the W3C "traceparent" and falls back
// to "googclient_traceparent" / "googclient_tracestate", the keys written by
// Pub/Sub client libraries that have built-in OpenTelemetry tracing enabled.
type AttributeCarrier map[string]string

// Client libraries with built-in tracing prefix the W3C keys with "googclient_".
const googClientPrefix = "googclient_"

func (c AttributeCarrier) Get(key string) string {
	if c == nil {
		return ""
	}
	if v, ok := c[key]; ok && v != "" {
		return v
	}
	if key == "traceparent" || key == "tracestate" {
		return c[googClientPrefix+key]
	}
	return ""
}

func (c AttributeCarrier) Set(key, val string) {
	if c != nil {
		c[key] = val
	}
}

func (c AttributeCarrier) Keys() []string {
	keys := make([]string, 0, len(c))
	for k := range c {
		keys = append(keys, k)
	}
	return keys
}

// StartConsumerSpan extracts the upstream context from message attributes and
// starts a SpanKindConsumer span named "process {subscription}" per the
// OpenTelemetry messaging semantic conventions (v1.27+).
//
// Use it only when the client library's built-in tracing is NOT active on this
// side (push subscriptions, Eventarc, Cloud Run functions, or a producer you do
// not control). With pubsub.ClientConfig{EnableOpenTelemetryTracing: true} the
// Receive callback already runs inside a library-created consumer span: start
// child spans from that ctx and do not re-extract from attributes.
func StartConsumerSpan(ctx context.Context, tracer trace.Tracer, subscriptionID, msgID string, attrs map[string]string) (context.Context, trace.Span) {
	parent := otel.GetTextMapPropagator().Extract(ctx, AttributeCarrier(attrs))
	return tracer.Start(parent, "process "+subscriptionID,
		trace.WithSpanKind(trace.SpanKindConsumer),
		trace.WithAttributes(
			semconv.MessagingSystemGCPPubSub,
			semconv.MessagingDestinationSubscriptionName(subscriptionID),
			semconv.MessagingMessageID(msgID),
			semconv.MessagingOperationTypeProcess,
			semconv.MessagingOperationName("process"),
		),
	)
}

// InjectOutboundAttributes writes traceparent/tracestate from ctx into the
// attribute map that will be attached to the outgoing Pub/Sub message.
func InjectOutboundAttributes(ctx context.Context, attrs map[string]string) map[string]string {
	if attrs == nil {
		attrs = make(map[string]string, 2)
	}
	otel.GetTextMapPropagator().Inject(ctx, AttributeCarrier(attrs))
	return attrs
}
```
Producer side (escape hatch), right before publishing with
`cloud.google.com/go/pubsub/v2`:

```go
attrs := telemetry.InjectOutboundAttributes(ctx, map[string]string{
	"event_type":     ev.Type,
	"schema_version": "1",
})
res := publisher.Publish(ctx, &pubsub.Message{Data: ev.Payload, Attributes: attrs})
```

## 4. Cloud Logging trace-correlated slog handler

```go
// file: telemetry/slog_handler.go
package telemetry

import (
	"context"
	"fmt"
	"io"
	"log/slog"

	"go.opentelemetry.io/otel/trace"
)

// cloudLoggingHandler decorates a slog.Handler with the Cloud Logging special
// fields that link a log line to its trace and span. It records WithAttrs /
// WithGroup as operations replayed on top of the base handler at Handle time,
// so the trace fields always land at the TOP level of the JSON object even when
// the logger is inside a group (Cloud Logging ignores nested keys).
type cloudLoggingHandler struct {
	base      slog.Handler
	ops       []func(slog.Handler) slog.Handler
	projectID string
}

// WrapHandlerWithCloudTrace adds trace correlation to any handler (idempotent).
func WrapHandlerWithCloudTrace(inner slog.Handler, projectID string) slog.Handler {
	if _, already := inner.(*cloudLoggingHandler); already {
		return inner
	}
	return &cloudLoggingHandler{base: inner, projectID: projectID}
}

// NewCloudLoggingJSONLogger emits structured JSON that Cloud Logging parses:
// "severity" and "message" top-level keys plus trace correlation fields.
func NewCloudLoggingJSONLogger(w io.Writer, projectID string, level slog.Level) *slog.Logger {
	base := slog.NewJSONHandler(w, &slog.HandlerOptions{
		Level: level,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			if len(groups) > 0 {
				return a // only rewrite the built-in top-level keys, never user attributes
			}
			switch a.Key {
			case slog.LevelKey:
				if lvl, ok := a.Value.Any().(slog.Level); ok {
					return slog.String("severity", severityFor(lvl))
				}
				return a
			case slog.MessageKey:
				if a.Value.Kind() == slog.KindString {
					return slog.String("message", a.Value.String())
				}
				return a
			default:
				return a
			}
		},
	})
	return slog.New(WrapHandlerWithCloudTrace(base, projectID))
}

// severityFor maps slog levels to Cloud Logging LogSeverity names
// (slog says "WARN", Cloud Logging expects "WARNING").
func severityFor(l slog.Level) string {
	switch {
	case l >= slog.LevelError+4:
		return "CRITICAL"
	case l >= slog.LevelError:
		return "ERROR"
	case l >= slog.LevelWarn:
		return "WARNING"
	case l >= slog.LevelInfo:
		return "INFO"
	default:
		return "DEBUG"
	}
}

func (h *cloudLoggingHandler) Enabled(ctx context.Context, l slog.Level) bool {
	return h.base.Enabled(ctx, l)
}

func (h *cloudLoggingHandler) Handle(ctx context.Context, r slog.Record) error {
	target := h.base
	if sc := trace.SpanContextFromContext(ctx); sc.IsValid() && h.projectID != "" {
		target = target.WithAttrs([]slog.Attr{
			slog.String("logging.googleapis.com/trace", fmt.Sprintf("projects/%s/traces/%s", h.projectID, sc.TraceID().String())),
			slog.String("logging.googleapis.com/spanId", sc.SpanID().String()),
			slog.Bool("logging.googleapis.com/trace_sampled", sc.IsSampled()),
		})
	}
	for _, op := range h.ops {
		target = op(target)
	}
	return target.Handle(ctx, r)
}

func (h *cloudLoggingHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return h.withOp(func(inner slog.Handler) slog.Handler { return inner.WithAttrs(attrs) })
}

func (h *cloudLoggingHandler) WithGroup(name string) slog.Handler {
	if name == "" {
		return h
	}
	return h.withOp(func(inner slog.Handler) slog.Handler { return inner.WithGroup(name) })
}

func (h *cloudLoggingHandler) withOp(op func(slog.Handler) slog.Handler) *cloudLoggingHandler {
	ops := make([]func(slog.Handler) slog.Handler, len(h.ops)+1)
	copy(ops, h.ops)
	ops[len(h.ops)] = op
	return &cloudLoggingHandler{base: h.base, ops: ops, projectID: h.projectID}
}
```

## 5. Generic port decorator for stage spans

```go
// file: telemetry/decorator.go
package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// Traced wraps any port call with a child span, keeping the domain package
// free of OpenTelemetry imports. Use one instance per logical stage
// (for example "db.insert", "validate", "db.commit"). Kind defaults to
// SpanKindInternal; set SpanKindClient for calls that leave the process
// (database, HTTP, gRPC).
type Traced[T any, R any] struct {
	SpanName string
	Tracer   trace.Tracer
	Kind     trace.SpanKind
	Attrs    []attribute.KeyValue
	Next     func(ctx context.Context, in T) (R, error)
}

func (d *Traced[T, R]) Execute(ctx context.Context, in T) (R, error) {
	kind := d.Kind
	if kind == trace.SpanKindUnspecified {
		kind = trace.SpanKindInternal
	}
	ctx, span := d.Tracer.Start(ctx, d.SpanName,
		trace.WithSpanKind(kind),
		trace.WithAttributes(d.Attrs...),
	)
	defer span.End()

	res, err := d.Next(ctx, in)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return res, err
	}
	// Leave status Unset on success: the OpenTelemetry spec reserves Ok for an
	// explicit application assertion, and Unset keeps the span overridable.
	return res, nil
}
```
Example wrapping a repository port without importing OpenTelemetry in the
domain package:

```go
commit := &telemetry.Traced[*domain.Order, struct{}]{
	SpanName: "db.insert orders",
	Tracer:   otel.Tracer("orders/adapters/db"),
	Kind:     trace.SpanKindClient,
	Attrs:    []attribute.KeyValue{attribute.String("db.system", "postgresql")},
	Next:     func(ctx context.Context, o *domain.Order) (struct{}, error) { return struct{}{}, repo.Save(ctx, o) },
}
```

## 6. TracerProvider: OTLP export, sampler, shutdown

```go
// file: telemetry/provider.go
package telemetry

import (
	"context"
	"fmt"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.37.0"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/oauth"
)

// ProviderConfig controls exporter and sampling for a service.
type ProviderConfig struct {
	ProjectID      string
	ServiceName    string
	ServiceVersion string
	// SampleRatio applies to root spans AND to spans whose remote parent is not
	// sampled (for example requests entering through Cloud Run, which sets a
	// traceparent with the sampled flag cleared for most requests). 1.0 in test,
	// 0.05-0.2 in high-volume production.
	SampleRatio float64
}

const telemetryEndpoint = "telemetry.googleapis.com:443"

// InitTracerProvider registers a global TracerProvider that exports spans over
// OTLP/gRPC to the Google Cloud Telemetry API (the supported path; the legacy
// Cloud Trace exporter package is deprecated) and a W3C TraceContext + Baggage
// propagator. Call the returned shutdown function after consumers have
// drained, before closing the database.
func InitTracerProvider(ctx context.Context, cfg ProviderConfig) (shutdown func(context.Context) error, err error) {
	creds, err := oauth.NewApplicationDefault(ctx) // ADC: Workload Identity, SA key, or gcloud auth application-default login
	if err != nil {
		return nil, fmt.Errorf("load application default credentials: %w", err)
	}
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(telemetryEndpoint),
		otlptracegrpc.WithTLSCredentials(credentials.NewClientTLSFromCert(nil, "")),
		otlptracegrpc.WithDialOption(grpc.WithPerRPCCredentials(creds)),
		otlptracegrpc.WithHeaders(map[string]string{"x-goog-user-project": cfg.ProjectID}),
	)
	if err != nil {
		return nil, fmt.Errorf("create OTLP trace exporter: %w", err)
	}
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(cfg.ServiceName),
			semconv.ServiceVersion(cfg.ServiceVersion),
			attribute.String("gcp.project_id", cfg.ProjectID), // required by the Telemetry API
		),
	)
	if err != nil {
		return nil, fmt.Errorf("build resource: %w", err)
	}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(NewSampler(cfg.SampleRatio)),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{},
	))
	return tp.Shutdown, nil
}

// NewSampler returns a ParentBased sampler that honours an upstream *sampled*
// decision but applies ratio when the remote parent is NOT sampled. Without the
// second rule, ParentBased drops almost every request behind Cloud Run, whose
// frontend only marks ~0.1 request/s/instance as sampled.
func NewSampler(ratio float64) sdktrace.Sampler {
	if ratio <= 0 || ratio > 1 {
		ratio = 1
	}
	return sdktrace.ParentBased(
		sdktrace.TraceIDRatioBased(ratio),
		sdktrace.WithRemoteParentNotSampled(sdktrace.TraceIDRatioBased(ratio)),
	)
}
```
Call `shutdown(ctx)` in the graceful-shutdown sequence after consumers drain
and before closing the database.

## 7. Deterministic unit tests with the in-memory exporter

Never contact Cloud Trace or require network/credentials in unit tests; assert
propagation and log correlation with `go.opentelemetry.io/otel/sdk/trace/tracetest`:

```go
func setupTestTracer(t *testing.T) (*tracetest.InMemoryExporter, trace.Tracer) {
	t.Helper()
	exp := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exp))
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{}))
	t.Cleanup(func() { _ = tp.Shutdown(context.Background()) })
	return exp, tp.Tracer("test-tracer")
}
```

Required unit-test assertions and Phase 4 checklist:

1.  Inbound `traceparent`
    `00-11111111111111111111111111111111-2222222222222222-01` (or
    `googclient_traceparent`) yields a `SpanKindConsumer` span named
    `process {subscription}` continuing `TraceID`
    `11111111111111111111111111111111` and parent span ID `2222222222222222`.
2.  Child stage spans share the trace ID; failing stages set `codes.Error` and
    record the error; successful stages leave status `Unset`.
3.  Logs emitted with context contain top-level `logging.googleapis.com/trace`
    set to `projects/my-project/traces/11111111111111111111111111111111`,
    `logging.googleapis.com/spanId`, `logging.googleapis.com/trace_sampled`,
    and `severity` (`WARNING`, not `WARN`) even inside `WithGroup`.
4.  Nil or empty attributes do not panic and start a root trace.
5.  `NewSampler` samples remote-parent-not-sampled spans at `ratio` (Cloud Run)
    and honours sampled remote parents.
6.  Domain packages contain zero `go.opentelemetry.io` imports when clean
    architecture applies.
