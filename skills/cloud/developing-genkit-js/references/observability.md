# Observability (Tracing, OpenTelemetry, Reflection API)

> Pluggable instrumentation, `@genkit-ai/otel`, and the reflection API settings
> require `genkit >= 1.43.0`.

- [How tracing works](#how-tracing-works): Lines 13-21
- [Export OpenTelemetry GenAI semantic conventions (@genkit-ai/otel)](#export-opentelemetry-genai-semantic-conventions-genkit-aiotel): Lines 23-81
- [Custom instrumentation](#custom-instrumentation): Lines 83-119
- [Reflection API outside dev](#reflection-api-outside-dev): Lines 121-142

---

## How tracing works

- **In dev** (`genkit start`), Genkit posts spans straight to the Developer UI's
  telemetry server. No OpenTelemetry SDK is involved. Logs written with
  `logger` from `genkit/logging` show up next to the span that produced them.
- **Elsewhere**, spans go through pluggable `Instrumentation` providers. The
  default provider creates OpenTelemetry spans with `genkit:*` attributes.
  Nothing is exported until an OTel SDK is started, directly or by a plugin
  such as `enableFirebaseTelemetry()` (Genkit Monitoring).

## Export OpenTelemetry GenAI semantic conventions (`@genkit-ai/otel`)

Use this to send Genkit telemetry to any OTLP backend (Jaeger, Grafana,
Honeycomb, Datadog, ...) in the vendor-neutral `gen_ai.*` shape.

```bash
npm i @genkit-ai/otel @opentelemetry/sdk-node
```

```ts
import { googleAI } from '@genkit-ai/google-genai';
import { GenAiInstrumentation } from '@genkit-ai/otel';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { genkit } from 'genkit';
import { configureInstrumentation } from 'genkit/tracing';

// 1. The app owns the OTel SDK. With no args it reads the standard OTEL_* env
//    vars (default: OTLP http/protobuf on localhost:4318).
const sdk = new NodeSDK();
sdk.start();

// 2. Route Genkit spans through the GenAI provider. Call once, before genkit().
configureInstrumentation(
  new GenAiInstrumentation({
    contentCapturingMode: 'SPAN_ONLY', // prompts/responses on spans; may contain PII
    emitToolSpans: true, // execute_tool spans
  })
);

// 3. Use Genkit as usual.
const ai = genkit({ plugins: [googleAI()] });
```

What you get: `chat <model>` client spans with `gen_ai.request.*`,
`gen_ai.usage.*`, and `gen_ai.response.finish_reasons`; optional
`execute_tool <name>` spans; a generic span per other Genkit action (tagged
`genkit.action.type`); and the `gen_ai.client.token.usage` and
`gen_ai.client.operation.duration` metrics.

Options: `contentCapturingMode` (`'NO_CONTENT'` default, `'SPAN_ONLY'`,
`'EVENT_ONLY'`, `'SPAN_AND_EVENT'`; falls back to the
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` env var), `captureActionIO`
(raw `genkit.input`/`genkit.output`, default `false`), `emitToolSpans` (default
`false`), `emitMetrics` (default `true`), `scopeName`, and explicit
`tracer`/`meter`/`logger`.

Gotchas:

- **Do not combine with `enableFirebaseTelemetry()` or
  `enableGoogleCloudTelemetry()`.** `configureInstrumentation` replaces the
  default provider, and those plugins build their metrics/logs from its
  `genkit:*` attributes. Their Genkit metrics stop with no error. Pick one.
- **`EVENT_ONLY` content goes to the OTel logs signal**, not the span. Jaeger
  can't show it; use `SPAN_ONLY`/`SPAN_AND_EVENT` there.
- **The Dev UI keeps working.** Under `genkit start`, its own provider always
  runs first. To preview what the OTel export looks like in the Dev UI, run
  `genkit start --experimental-use-otel -- <command>`.
- **No SDK, no export.** Without a started OTel SDK the provider is inert and
  logs one warning.

## Custom instrumentation

Implement `Instrumentation` to send spans somewhere else. `runInNewSpan` wraps
the operation like middleware: call `next` exactly once, return its result,
rethrow its errors unchanged.

```ts
import { INVALID_SPAN_CONTEXT, trace } from '@opentelemetry/api';
import {
  configureInstrumentation,
  type Instrumentation,
  type InstrumentationNext,
  type InstrumentationSpanInfo,
} from 'genkit/tracing';

class TimingInstrumentation implements Instrumentation {
  async runInNewSpan<T>(
    info: InstrumentationSpanInfo,
    next: InstrumentationNext<T>
  ): Promise<T> {
    const start = performance.now();
    try {
      // Not OTel-based: pass a non-recording span and empty ids.
      return await next(trace.wrapSpanContext(INVALID_SPAN_CONTEXT), {
        traceId: '',
        spanId: '',
        setMetadata() {},
      });
    } finally {
      // metadata.state is 'success' | 'error' once next settles.
      console.log(info.metadata.path, info.metadata.state, performance.now() - start);
    }
  }
}

configureInstrumentation(new TimingInstrumentation());
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
node lib/index.js
```

- `GENKIT_REFLECTION_ENABLED`: `true` on anywhere, `false` off even under dev.
  Any other value makes `genkit()` throw.
- `GENKIT_REFLECTION_SECRET_TOKEN`: every request must send it in the
  `x-genkit-reflection-secret` header (`/api/__health` stays open). Without it,
  anyone who can reach the port can run every flow, model, and tool.
- `genkit({ reflectionPort: 3200 })` binds exactly that port and fails if taken;
  `0` lets the OS pick; unset searches upward from 3100. The env var wins over
  the option, and neither turns the API on.
