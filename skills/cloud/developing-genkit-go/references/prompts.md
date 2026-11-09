# Prompts

- [DefinePrompt](#defineprompt): Lines 10-53
- [DefineDataPrompt (Typed Input/Output)](#definedataprompt-typed-inputoutput): Lines 55-94
- [.prompt Files (Dotprompt)](#prompt-files-dotprompt): Lines 96-278
- [Schemas](#schemas): Lines 280-323

---

## DefinePrompt

Define a reusable prompt in code with a default model and template.

```go
jokePrompt := genkit.DefinePrompt(g, "joke",
	ai.WithModel(googlegenai.ModelRef("googleai/gemini-flash-latest", nil)),
	ai.WithInputType(JokeRequest{Topic: "example"}),
	ai.WithPrompt("Tell me a joke about {{topic}}."),
)
```

### Execute

```go
resp, err := jokePrompt.Execute(ctx,
	ai.WithInput(map[string]any{"topic": "cats"}),
)
fmt.Println(resp.Text())
```

### ExecuteStream

```go
stream := jokePrompt.ExecuteStream(ctx,
	ai.WithInput(map[string]any{"topic": "cats"}),
)
for result, err := range stream {
	if err != nil { return err }
	if result.Done { break }
	fmt.Print(result.Chunk.Text())
}
```

### Override Options at Execution

```go
resp, err := jokePrompt.Execute(ctx,
	ai.WithInput(map[string]any{"topic": "cats"}),
	ai.WithModelName("googleai/gemini-pro-latest"),  // override model
	ai.WithConfig(map[string]any{"temperature": 0.9}),
	ai.WithTools(myTool),
)
```

## DefineDataPrompt (Typed Input/Output)

Strongly-typed prompts with Go generics.

```go
type JokeRequest struct {
	Topic string `json:"topic"`
}

type Joke struct {
	Setup     string `json:"setup" jsonschema:"description=The setup"`
	Punchline string `json:"punchline" jsonschema:"description=The punchline"`
}

jokePrompt := genkit.DefineDataPrompt[JokeRequest, *Joke](g, "structured-joke",
	ai.WithModel(googlegenai.ModelRef("googleai/gemini-flash-latest", nil)),
	ai.WithPrompt("Tell me a joke about {{topic}}."),
)
```

### Execute (typed)

```go
joke, resp, err := jokePrompt.Execute(ctx, JokeRequest{Topic: "cats"})
// joke is *Joke, resp is *ModelResponse
```

### ExecuteStream (typed)

```go
stream := jokePrompt.ExecuteStream(ctx, JokeRequest{Topic: "cats"})
for result, err := range stream {
	if err != nil { return err }
	if result.Done {
		finalJoke := result.Output // *Joke
		break
	}
	fmt.Print(result.Chunk) // partial *Joke
}
```

## .prompt Files (Dotprompt)

Define prompts in separate files with YAML frontmatter and Handlebars templates.

### Basic .prompt File

`prompts/joke.prompt`:
```
---
model: googleai/gemini-flash-latest
input:
  schema:
    topic: string
---
Tell me a joke about {{topic}}.
```

### Load and Use

```go
// LookupPrompt returns Prompt (untyped: map[string]any input, string output)
jokePrompt := genkit.LookupPrompt(g, "joke")
resp, err := jokePrompt.Execute(ctx,
	ai.WithInput(map[string]any{"topic": "cats"}),
)
```

### Typed .prompt File

`prompts/structured-joke.prompt`:
```
---
model: googleai/gemini-flash-latest
config:
  thinkingConfig:
    thinkingBudget: 0
input:
  schema: JokeRequest
output:
  format: json
  schema: Joke
---
Tell me a joke about {{topic}}.
```

Register Go types so the .prompt file can reference them by name:
```go
genkit.DefineSchemaFor[JokeRequest](g)
genkit.DefineSchemaFor[Joke](g)

jokePrompt := genkit.LookupDataPrompt[JokeRequest, *Joke](g, "structured-joke")
joke, resp, err := jokePrompt.Execute(ctx, JokeRequest{Topic: "cats"})
```

### LoadPrompt (Explicit Path)

```go
prompt := genkit.LoadPrompt(g, "./prompts/countries.prompt", "countries")
resp, err := prompt.Execute(ctx)
```

### .prompt File Features

**Multi-message prompts with roles:**
```
---
model: googleai/gemini-flash-latest
input:
  schema:
    question: string
---
{{ role "system" }}
You are a helpful assistant.

{{ role "user" }}
{{question}}
```

**Media in prompts:**
```
---
model: googleai/gemini-flash-latest
input:
  schema:
    videoUrl: string
    contentType: string
---
{{ role "user" }}
Summarize this video:
{{media url=videoUrl contentType=contentType}}
```

**Conditionals and loops:**
```
---
input:
  schema:
    topic: string
    dietaryRestrictions?(array): string
---
Write a recipe about {{topic}}.
{{#if dietaryRestrictions}}
Dietary restrictions: {{#each dietaryRestrictions}}{{this}}{{#unless @last}}, {{/unless}}{{/each}}.
{{/if}}
```

**Inline schema in .prompt file:**
```
---
model: googleai/gemini-flash-latest
input:
  schema:
    topic: string
    style?: string
output:
  format: json
  schema:
    title: string
    body: string
    tags(array): string
---
Write an article about {{topic}}.
{{#if style}}Write in a {{style}} style.{{/if}}
```

**Tools, tool-loop control, and middleware:**

`.prompt` frontmatter can also configure tool calling and attach middleware, so
an agent-style prompt can be fully described in the file:

```
---
model: googleai/gemini-flash-latest
input:
  schema:
    tone: string
tools:
  - getAttractions
  - getFlightInfo
toolChoice: auto          # auto | required | none
maxTurns: 20              # max tool-call loop iterations (WithMaxTurns)
returnToolRequests: false # return tool requests instead of running them (WithReturnToolRequests)
use:
  - name: genkit-middleware/retry
    config:
      maxRetries: 2
  - genkit-middleware/fallback   # bare string = middleware name, no config
---
{{role "system"}}
You are a friendly trip planning assistant. Keep your tone {{tone}}.

{{history}}
```

Field mapping:

| Frontmatter | Option | Notes |
| --- | --- | --- |
| `tools` | `WithTools` | list of registered tool names (strings) |
| `toolChoice` | `WithToolChoice` | `auto`, `required`, or `none` |
| `maxTurns` | `WithMaxTurns` | integer |
| `returnToolRequests` | `WithReturnToolRequests` | boolean |
| `use` | `WithUse` | list of middleware refs |

`use` entries are resolved by name against middleware registered on the
`*Genkit`
instance. Each entry is either a bare string (the middleware name) or a map with
`name` and optional `config`. Register the built-in middleware plugin so names
like `genkit-middleware/retry` resolve:

```go
import "github.com/firebase/genkit/go/plugins/middleware"

g := genkit.Init(ctx, genkit.WithPlugins(
	&googlegenai.GoogleAI{},
	&middleware.Middleware{}, // registers genkit-middleware/{retry,fallback,filesystem,skills,toolApproval}
))
```

Available named middleware: `genkit-middleware/retry`,
`genkit-middleware/fallback`,
`genkit-middleware/filesystem`, `genkit-middleware/skills`,
`genkit-middleware/toolApproval`. See [references/middleware.md](middleware.md).

## Schemas

### DefineSchemaFor (from Go type)

Registers a Go struct as a named schema for use in `.prompt` files.

```go
genkit.DefineSchemaFor[JokeRequest](g)
genkit.DefineSchemaFor[Joke](g)
```

The schema name matches the Go type name. Use `jsonschema` struct tags for
metadata:

```go
type Recipe struct {
	Title       string       `json:"title" jsonschema:"description=The recipe title"`
	Difficulty  string       `json:"difficulty" jsonschema:"enum=easy,enum=medium,enum=hard"`
	Ingredients []Ingredient `json:"ingredients"`
	Steps       []string     `json:"steps"`
}

type Ingredient struct {
	Name   string  `json:"name"`
	Amount float64 `json:"amount"`
	Unit   string  `json:"unit"`
}
```

### DefineSchema (manual JSON Schema)

```go
genkit.DefineSchema(g, "Recipe", map[string]any{
	"type": "object",
	"properties": map[string]any{
		"title": map[string]any{"type": "string"},
		"ingredients": map[string]any{
			"type":  "array",
			"items": map[string]any{"type": "object"},
		},
	},
	"required": []string{"title", "ingredients"},
})
```
