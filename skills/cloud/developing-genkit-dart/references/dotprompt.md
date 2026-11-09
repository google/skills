# Dotprompt (.prompt files) — Genkit Dart

- [What it is](#what-it-is): Lines 15-19
- [Where files live](#where-files-live): Lines 21-34
- [File format](#file-format): Lines 36-81
- [Loading and calling a prompt](#loading-and-calling-a-prompt): Lines 83-157
- [Registering named schemas](#registering-named-schemas): Lines 159-191
- [Variants](#variants): Lines 193-201
- [Partials](#partials): Lines 203-213
- [Tools, tool-loop control, and middleware](#tools-tool-loop-control-and-middleware): Lines 215-266
- [Backing an agent with a .prompt file](#backing-an-agent-with-a-prompt-file): Lines 268-282

---

## What it is

`.prompt` files combine YAML frontmatter (model, config, schemas, tools,
middleware) with a Handlebars template. They keep prompt logic out of Dart code
and make variants and iteration easy.

## Where files live

By default Genkit loads `.prompt` files from `./prompts`. Configure with the
`promptDir` parameter on `Genkit(...)` (set to `null` to disable auto-loading):

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_google_genai/genkit_google_genai.dart';

final ai = Genkit(
  plugins: [googleAI()],
  promptDir: './prompts', // default
);
```

## File format

`prompts/greeting.prompt`:
```
---
model: googleai/gemini-flash-latest
input:
  schema:
    name: string
    style: string
---
{{role "system"}}
You are a {{style}} greeter.

{{role "user"}}
Greet {{name}}.
```

Schema fields use Picoschema (the compact form above) or you can reference a
named schema registered with `defineSchema`. A top-level `type` or
`properties` key makes it plain JSON Schema instead.

Picoschema follows the [spec](https://genkit.dev/docs/dotprompt/#picoschema),
same as JS/Go/Python:

```yaml
schema:
  name: string, the person to greet     # description goes after a comma
  nickname?: string                      # optional (and nullable)
  tags(array, relevant tags): string     # array of strings
  steps(array):                          # array of objects
    instruction: string
  address?(object):                      # nested object
    city: string
  status(enum, approval status): [PENDING, APPROVED]
  extra?: any
  (*): string                            # wildcard: additionalProperties
```

The parenthetical is only for a type keyword (`array`, `object`, `enum`) plus an
optional description. `email(the user email): string` is **invalid**; write
`email: string, the user email`. A prompt with an invalid schema logs a warning
when the folder loads and throws `GenkitException` (`invalidArgument`) when it
is rendered; other prompts keep working. A schema name that is still not
registered with `defineSchema` at render time throws too (`failedPrecondition`);
names may be registered after the folder loads.

## Loading and calling a prompt

`ai.prompt(name, {variant})` returns a `Future<Prompt<Input, Output>>`. The
resolved `Prompt` is a **callable object**: invoke it like a function. The
input is a **positional** argument (there is no `input:` named parameter).

```dart
// Non-streaming
final greetingPrompt = await ai.prompt('greeting');
final response = await greetingPrompt({
  'name': 'World',
  'style': 'cheerful',
});
print(response.text);
```

Per-call generation options are **named parameters** after the input, with the
same names as `ai.generate`: `config`, `model`, `messages`, `tools`,
`toolNames`, `toolChoice`, `returnToolRequests`, `maxTurns`, `output`,
`context`, `use`, `cancel` (`render` takes all but `context`/`cancel`). There is
no options object to wrap them in.

```dart
final followUp = await greetingPrompt(
  {'name': 'World', 'style': 'cheerful'},
  config: {'temperature': 0.2}, // merged per key with the prompt's config
  messages: history, // prior turns
  tools: [lookupTool], // appended to the prompt's tools (same for toolNames/use)
  use: [retry()],
);
```

### Typed output

`response.output` is typed by the prompt's `Output`. A `.prompt` file's
`output.schema` has no Dart type, so pass `outputParserSchema` to parse into
one (it is never sent to the model; the file's schema is):

```dart
// Inferred as Prompt<dynamic, Recipe>
final recipePrompt = await ai.prompt(
  'recipe',
  outputParserSchema: Recipe.$schema,
);
final Recipe? recipe = (await recipePrompt({'food': 'pasta'})).output;

// Code-defined with outputSchema: already typed, just name the types.
final joke = await ai.prompt<JokeInput, Joke>('joke');
```

`ai.definePrompt(..., outputSchema: Joke.$schema)` returns a
`Prompt<JokeInput, Joke>` directly. A prompt's `.ref` is a `PromptRef`
(`name`, `metadata`).

### Streaming

```dart
final storyPrompt = await ai.prompt('story');
final stream = storyPrompt.stream({'subject': 'a robot'});
await for (final chunk in stream) {
  print(chunk.text);
}
```

### Render without generating

Returns `GenerateActionOptions` (messages, model, config) without calling the
model — useful for building `ai.generate` calls or evals:

```dart
final greetingPrompt = await ai.prompt('greeting');
final rendered = await greetingPrompt.render({'name': 'World', 'style': 'casual'});
rendered.model;    // resolved model
rendered.messages; // rendered messages
```

## Registering named schemas

Reference a schema by name in `.prompt` frontmatter (`input.schema` /
`output.schema`) after registering it with `defineSchema` (a JSON Schema map):

```dart
ai.defineSchema('Recipe', {
  'type': 'object',
  'properties': {
    'title': {'type': 'string'},
    'steps': {'type': 'array', 'items': {'type': 'string'}},
  },
  'required': ['title', 'steps'],
});
```

Then in `recipe.prompt`:
```
---
model: googleai/gemini-flash-latest
input:
  schema:
    food: string
output:
  schema: Recipe
  format: json
---
Generate a recipe for {{food}}.
```

For code-defined prompts (`ai.definePrompt`) you typically pass a
[schemantic](schemantic.md)-generated schema (e.g. `JokeInput.schema`) as
`inputSchema`.

## Variants

Name the file `<name>.<variant>.prompt` — e.g. `greeting.formal.prompt`. Load
with the `variant` argument:

```dart
final formalPrompt = await ai.prompt('greeting', variant: 'formal');
final response = await formalPrompt({'name': 'Dr. Smith', 'title': 'Professor'});
```

## Partials

Reusable template fragments. Name a partial file `_<name>.prompt` and include it
with `{{> name param=value}}`.

`prompts/_signature.prompt` referenced from another template:
```
Write a short email to {{recipient}} about {{subject}}.

{{> signature}}
```

## Tools, tool-loop control, and middleware

`.prompt` frontmatter can configure tool calling and attach middleware, so an
agent-style prompt is fully described in the file. This is based on
`prompts/tripPlanner.prompt` from the agents testapp (with
`returnToolRequests` shown for completeness):

```
---
model: googleai/gemini-flash-latest
input:
  schema:
    tone: string
tools:
  - getAttractions
  - getFlightInfo
maxTurns: 20              # max tool-call loop iterations
returnToolRequests: false # return tool requests instead of running them
use:
  - name: retry           # bare string also works: `- retry`
    config:
      maxRetries: 4
---
{{role "system"}}
You are a friendly trip planning assistant. Help users plan trips by suggesting
attractions and looking up flight information. Use the available tools to provide
accurate, up-to-date information. Keep your tone {{tone}}.

{{history}}
```

- `tools`: list of registered tool names.
- `toolChoice`, `maxTurns`, `returnToolRequests`: same semantics as the
  equivalent `ai.generate` options.
- `use`: list of middleware refs. Each entry is a bare string (middleware name)
  or a map with `name` and optional `config`. Names resolve against middleware
  registered on the Genkit instance. `retry` (above) is built in; for
  `genkit_middleware` names, register the plugin so the name is available:

```dart
import 'package:genkit_middleware/skills.dart';

final ai = Genkit(
  plugins: [
    googleAI(),
    SkillsPlugin(), // makes `use: [skills]` resolve
  ],
  promptDir: './prompts',
);
```

See [genkit_middleware](genkit_middleware.md) for the middleware package.

## Backing an agent with a .prompt file

`definePromptAgent` wires an agent directly to a `.prompt` file by name. The
frontmatter (`tools`, `maxTurns`, `use`, ...) applies to the agent, and
`promptInput` supplies template variables:

```dart
final tripPlannerAgent = ai.definePromptAgent(
  promptName: 'tripPlanner',            // -> prompts/tripPlanner.prompt
  promptInput: {'tone': 'enthusiastic'}, // fills {{tone}}
  store: InMemorySessionStore(),
);
```

See [Agents](agents.md) for defining and serving agents.
