# Flows & HTTP

- [DefineFlow](#defineflow): Lines 10-29
- [DefineStreamingFlow](#definestreamingflow): Lines 31-101
- [Named Sub-Steps](#named-sub-steps): Lines 103-125
- [HTTP Handlers](#http-handlers): Lines 127-192

---

## DefineFlow

Wrap AI logic in a flow for observability, tracing, and HTTP deployment.

```go
jokeFlow := genkit.DefineFlow(g, "jokeFlow",
	func(ctx context.Context, topic string) (string, error) {
		return genkit.GenerateText(ctx, g,
			ai.WithModelName("googleai/gemini-flash-latest"),
			ai.WithPrompt("Tell me a joke about %s", topic),
		)
	},
)
```

### Running a Flow Directly

```go
result, err := jokeFlow.Run(ctx, "cats")
```

## DefineStreamingFlow

Flows that stream chunks back to the caller. Two common patterns:

### Pattern 1: Passthrough Streaming

Pass the stream callback directly through to `WithStreaming`. The callback type
is `ai.ModelStreamCallback` =
`func(context.Context, *ai.ModelResponseChunk) error`:

```go
genkit.DefineStreamingFlow(g, "streamingJokeFlow",
	func(ctx context.Context, topic string, sendChunk ai.ModelStreamCallback) (string, error) {
		resp, err := genkit.Generate(ctx, g,
			ai.WithModelName("googleai/gemini-flash-latest"),
			ai.WithPrompt("Tell me a long joke about %s", topic),
			ai.WithStreaming(sendChunk), // passthrough
		)
		if err != nil {
			return "", err
		}
		return resp.Text(), nil
	},
)
```

### Pattern 2: Manual String Streaming

Use `core.StreamCallback[string]` to stream extracted text:

```go
genkit.DefineStreamingFlow(g, "streamingJokeFlow",
	func(ctx context.Context, topic string, sendChunk core.StreamCallback[string]) (string, error) {
		stream := genkit.GenerateStream(ctx, g,
			ai.WithModelName("googleai/gemini-flash-latest"),
			ai.WithPrompt("Tell me a long joke about %s", topic),
		)
		for result, err := range stream {
			if err != nil {
				return "", err
			}
			if result.Done {
				return result.Response.Text(), nil
			}
			sendChunk(ctx, result.Chunk.Text())
		}
		return "", nil
	},
)
```

### Typed Streaming Flows

Use `core.StreamCallback[T]` with `GenerateDataStream` for typed chunks:

```go
genkit.DefineStreamingFlow(g, "structuredStream",
	func(ctx context.Context, input JokeRequest, sendChunk core.StreamCallback[*Joke]) (*Joke, error) {
		stream := genkit.GenerateDataStream[*Joke](ctx, g,
			ai.WithModelName("googleai/gemini-flash-latest"),
			ai.WithPrompt("Tell me a joke about %s", input.Topic),
		)
		for result, err := range stream {
			if err != nil { return nil, err }
			if result.Done { return result.Output, nil }
			sendChunk(ctx, result.Chunk)
		}
		return nil, nil
	},
)
```

## Named Sub-Steps

Use `core.Run` inside a flow for traced sub-steps:

```go
genkit.DefineFlow(g, "pipeline",
	func(ctx context.Context, input string) (string, error) {
		subject, err := core.Run(ctx, "extract-subject", func() (string, error) {
			return genkit.GenerateText(ctx, g,
				ai.WithPrompt("Extract the subject from: %s", input),
			)
		})
		if err != nil { return "", err }

		joke, err := core.Run(ctx, "generate-joke", func() (string, error) {
			return genkit.GenerateText(ctx, g,
				ai.WithPrompt("Tell me a joke about %s", subject),
			)
		})
		return joke, err
	},
)
```

## HTTP Handlers

### genkit.Handler

Convert any flow into an `http.HandlerFunc`:

```go
mux := http.NewServeMux()
for _, f := range genkit.ListFlows(g) {
	mux.HandleFunc("POST /"+f.Name(), genkit.Handler(f))
}
log.Fatal(server.Start(ctx, "127.0.0.1:8080", mux))
```

### Request/Response Format

**Non-streaming request:**
```bash
curl -X POST http://localhost:8080/jokeFlow \
  -H "Content-Type: application/json" \
  -d '{"data": "bananas"}'
```

Response: `{"result": "Why did the banana go to the doctor?..."}`

**Streaming request:**
```bash
curl -N -X POST http://localhost:8080/streamingJokeFlow \
  -H "Content-Type: application/json" \
  -d '{"data": "bananas"}'
```

Streaming responses use Server-Sent Events (SSE) format.

### genkit.HandlerFunc

For frameworks that expect error-returning handlers:

```go
handler := genkit.HandlerFunc(myFlow)
// handler is func(http.ResponseWriter, *http.Request) error
```

### Context Providers

Inject request context (e.g., auth headers) into flow execution:

```go
mux.HandleFunc("POST /myFlow", genkit.Handler(myFlow,
	genkit.WithContextProviders(func(ctx context.Context, rd core.RequestData) (api.ActionContext, error) {
		// rd.Headers contains HTTP headers
		return api.ActionContext{"userId": rd.Headers.Get("X-User-Id")}, nil
	}),
))
```

### ListFlows

Get all registered flows for dynamic route setup:

```go
flows := genkit.ListFlows(g) // []api.Action
for _, f := range flows {
	fmt.Println(f.Name())
}
```
