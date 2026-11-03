# Generation

## GenerateText

Simplest form. Returns a string.

```go
text, err := genkit.GenerateText(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Tell me a joke about %s", topic),
)
```

## Generate

Returns a full `*ModelResponse` with metadata, usage stats, and history.

```go
resp, err := genkit.Generate(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithSystem("You are a helpful assistant."),
	ai.WithPrompt("Explain %s", topic),
)
fmt.Println(resp.Text())         // concatenated text
fmt.Println(resp.FinishReason)   // ai.FinishReasonStop, etc.
fmt.Println(resp.Usage)          // token counts
```

## GenerateData (Structured Output)

Returns a typed Go value parsed from the model's JSON output.

```go
type Joke struct {
	Setup     string `json:"setup" jsonschema:"description=The setup of the joke"`
	Punchline string `json:"punchline" jsonschema:"description=The punchline"`
}

joke, resp, err := genkit.GenerateData[Joke](ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Tell me a joke about %s", topic),
)
// joke is *Joke, resp is *ModelResponse
```

## Streaming

### GenerateStream

Returns an iterator. Each value has `.Done`, `.Chunk`, and `.Response`.

```go
stream := genkit.GenerateStream(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Tell me a long story about %s", topic),
)
for result, err := range stream {
	if err != nil {
		return err
	}
	if result.Done {
		finalText := result.Response.Text()
		break
	}
	fmt.Print(result.Chunk.Text()) // incremental text
}
```

### GenerateDataStream (Structured Streaming)

Streams typed partial objects as they arrive.

```go
stream := genkit.GenerateDataStream[Joke](ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Tell me a joke about %s", topic),
)
for result, err := range stream {
	if err != nil {
		return err
	}
	if result.Done {
		finalJoke := result.Output // *Joke
		break
	}
	partialJoke := result.Chunk // *Joke (partial)
}
```

### Callback-Based Streaming

Use `ai.WithStreaming` with `Generate` for callback-style streaming. The callback receives `*ai.ModelResponseChunk`:

```go
resp, err := genkit.Generate(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Tell me a story"),
	ai.WithStreaming(func(ctx context.Context, chunk *ai.ModelResponseChunk) error {
		fmt.Print(chunk.Text()) // extract text from chunk
		return nil
	}),
)
// resp contains the final complete response
```

## Common Options

```go
// Model selection
ai.WithModel(googlegenai.ModelRef("googleai/gemini-flash-latest", nil))  // model reference
ai.WithModelName("googleai/gemini-flash-latest")                         // by name string

// Content
ai.WithPrompt("Tell me about %s", topic)    // user message (supports fmt verbs)
ai.WithSystem("You are a pirate.")          // system instructions
ai.WithMessages(msg1, msg2)                 // conversation history
ai.WithDocs(doc1, doc2)                     // context documents
ai.WithTextDocs("context 1", "context 2")   // context as strings

// Model config (provider-specific)
ai.WithConfig(map[string]any{"temperature": 0.7})
```

## Output Formats

Control how the model structures its output.

### By Go Type

```go
// Automatically uses JSON format and instructs model to match the type
ai.WithOutputType(MyStruct{})
```

### By Format String

```go
ai.WithOutputFormat(ai.OutputFormatJSON)   // single JSON object
ai.WithOutputFormat(ai.OutputFormatJSONL)  // JSON Lines (one object per line)
ai.WithOutputFormat(ai.OutputFormatArray)  // JSON array
ai.WithOutputFormat(ai.OutputFormatEnum)   // constrained enum value
ai.WithOutputFormat(ai.OutputFormatText)   // plain text (default)
```

### Enum Output

```go
type Color string
const (
	Red   Color = "red"
	Green Color = "green"
	Blue  Color = "blue"
)

text, err := genkit.GenerateText(ctx, g,
	ai.WithPrompt("What color is the sky?"),
	ai.WithOutputEnums(Red, Green, Blue),
)
```

### Custom Output Instructions

```go
ai.WithOutputInstructions("Return a JSON object with fields: name (string), age (number)")
```

### Combining Format + Schema

```go
// JSONL with a typed schema (useful for streaming lists)
genkit.DefinePrompt(g, "characters",
	ai.WithPrompt("Generate 5 story characters"),
	ai.WithOutputType([]StoryCharacter{}),
	ai.WithOutputFormat(ai.OutputFormatJSONL),
)
```

## Embeddings

```go
res, err := genkit.Embed(ctx, g,
	ai.WithEmbedderName("googleai/gemini-embedding-001"),
	ai.WithTextDocs("The sky is blue.", "Grass is green."), // one embedding per doc
)
if err != nil {
	return err
}
vector := res.Embeddings[0].Embedding // []float32

// Optional tuning (default is 3072 dimensions)
res, err = genkit.Embed(ctx, g,
	ai.WithEmbedderName("googleai/gemini-embedding-001"),
	ai.WithTextDocs("The sky is blue."),
	ai.WithConfig(&genai.EmbedContentConfig{
		OutputDimensionality: genai.Ptr[int32](768),
		TaskType:             "RETRIEVAL_DOCUMENT",
	}),
)
```

Common embedders: `googleai/gemini-embedding-001` (text),
`googleai/gemini-embedding-2` (multimodal: text, image, video).

Multimodal input goes in a document's media parts:

```go
res, err := genkit.Embed(ctx, g,
	ai.WithEmbedderName("googleai/gemini-embedding-2"),
	ai.WithDocs(&ai.Document{Content: []*ai.Part{
		ai.NewMediaPart("image/png", "data:image/png;base64,..."),
	}}),
)
```
