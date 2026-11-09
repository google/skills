# Model Providers

- [Google AI (Gemini)](#google-ai-gemini): Lines 12-38
- [Vertex AI](#vertex-ai): Lines 40-58
- [Anthropic (Claude)](#anthropic-claude): Lines 60-90
- [OpenAI-Compatible (compat_oai)](#openai-compatible-compat_oai): Lines 92-116
- [Ollama (Local Models)](#ollama-local-models): Lines 118-145
- [Multiple Providers](#multiple-providers): Lines 147-170

---

## Google AI (Gemini)

```go
import "github.com/firebase/genkit/go/plugins/googlegenai"

g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.GoogleAI{}))
```

**Env var:** `GEMINI_API_KEY` or `GOOGLE_API_KEY`

Model names follow the format `googleai/<model-id>`. Look up the latest model
IDs at https://ai.google.dev/gemini-api/docs/models.

```go
// By name string
ai.WithModelName("googleai/gemini-flash-latest")

// Model ref with provider-specific config
ai.WithModel(googlegenai.ModelRef("googleai/gemini-flash-latest", &genai.GenerateContentConfig{
	ThinkingConfig: &genai.ThinkingConfig{
		ThinkingBudget: genai.Ptr[int32](0), // disable thinking
	},
}))

// Lookup a model instance
m := googlegenai.GoogleAIModel(g, "gemini-flash-latest")
```

## Vertex AI

```go
import "github.com/firebase/genkit/go/plugins/googlegenai"

g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.VertexAI{}))
```

**Env vars:** `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (or
`GOOGLE_CLOUD_REGION`)

Uses Application Default Credentials (`gcloud auth application-default login`).

Model names follow the format `vertexai/<model-id>`. Same model IDs as Google
AI.

```go
ai.WithModelName("vertexai/gemini-flash-latest")
```

## Anthropic (Claude)

```go
import (
	"github.com/anthropics/anthropic-sdk-go"          // Anthropic SDK types
	ant "github.com/firebase/genkit/go/plugins/anthropic" // Genkit plugin
)

g := genkit.Init(ctx, genkit.WithPlugins(&ant.Anthropic{}))
```

**Env var:** `ANTHROPIC_API_KEY`

Model names follow the format `anthropic/<model-id>`. Look up the latest model
IDs at https://docs.anthropic.com/en/docs/about-claude/models.

```go
// By name
ai.WithModelName("anthropic/claude-sonnet-4-6")

// With provider-specific config (uses Anthropic SDK types via ai.WithConfig)
ai.WithConfig(&anthropic.MessageNewParams{
	Temperature: anthropic.Float(1.0),
	MaxTokens:   *anthropic.IntPtr(2000),
	Thinking: anthropic.ThinkingConfigParamUnion{
		OfEnabled: &anthropic.ThinkingConfigEnabledParam{
			BudgetTokens: *anthropic.IntPtr(1024),
		},
	},
})
```

## OpenAI-Compatible (compat_oai)

Works with any OpenAI-compatible API: OpenAI, DeepSeek, xAI, etc.

```go
import "github.com/firebase/genkit/go/plugins/compat_oai"

openaiPlugin := &compat_oai.OpenAICompatible{
	Provider: "openai",   // unique identifier
	APIKey:   os.Getenv("OPENAI_API_KEY"),
	// BaseURL: "https://custom-endpoint/v1", // for non-OpenAI providers
}
g := genkit.Init(ctx, genkit.WithPlugins(openaiPlugin))
```

Define models explicitly (not auto-discovered):

```go
model := openaiPlugin.DefineModel("openai", "gpt-4o", compat_oai.ModelOptions{})
```

Use with:
```go
ai.WithModel(model)
```

## Ollama (Local Models)

```go
import "github.com/firebase/genkit/go/plugins/ollama"

ollamaPlugin := &ollama.Ollama{
	ServerAddress: "http://localhost:11434",
	Timeout:       60, // seconds
}
g := genkit.Init(ctx, genkit.WithPlugins(ollamaPlugin))
```

Define models explicitly:

```go
model := ollamaPlugin.DefineModel(g,
	ollama.ModelDefinition{
		Name: "llama3.1",
		Type: "chat", // or "generate"
	},
	nil, // optional *ModelOptions
)
```

Use with:
```go
ai.WithModel(model)
```

## Multiple Providers

Register multiple plugins in a single Genkit instance:

```go
g := genkit.Init(ctx,
	genkit.WithPlugins(
		&googlegenai.GoogleAI{},
		&ant.Anthropic{},
	),
	genkit.WithDefaultModel("googleai/gemini-flash-latest"),
)

// Use different models per call
text1, _ := genkit.GenerateText(ctx, g,
	ai.WithModelName("googleai/gemini-flash-latest"),
	ai.WithPrompt("Hello from Gemini"),
)

text2, _ := genkit.GenerateText(ctx, g,
	ai.WithModelName("anthropic/claude-sonnet-4-6"),
	ai.WithPrompt("Hello from Claude"),
)
```
