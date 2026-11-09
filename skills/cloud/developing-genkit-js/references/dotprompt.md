# Dotprompt (.prompt files) — Genkit JS

- [What it is](#what-it-is): Lines 16-20
- [Where files live](#where-files-live): Lines 22-35
- [File format](#file-format): Lines 37-61
- [Loading and calling a prompt](#loading-and-calling-a-prompt): Lines 63-100
- [Registering named schemas](#registering-named-schemas): Lines 102-118
- [Variants](#variants): Lines 120-127
- [Partials](#partials): Lines 129-153
- [Helpers](#helpers): Lines 155-165
- [Tools, tool-loop control, and middleware](#tools-tool-loop-control-and-middleware): Lines 167-213
- [Relationship to agents](#relationship-to-agents): Lines 215-219

---

## What it is

`.prompt` files combine YAML frontmatter (model, config, schemas, tools,
middleware) with a Handlebars template. They keep prompt logic out of your
TypeScript code and make variants and iteration easy.

## Where files live

By default Genkit loads `.prompt` files from `./prompts`. Configure with the
`promptDir` option (set to `null` to disable auto-loading):

```ts
import { genkit } from 'genkit';
import { googleAI } from '@genkit-ai/google-genai';

const ai = genkit({
  plugins: [googleAI()],
  promptDir: './prompts', // default
});
```

## File format

`prompts/recipe.prompt`:
```
---
model: googleai/gemini-pro-latest
input:
  schema:
    food: string
    ingredients?(array): string   # ? = optional
output:
  schema: Recipe                  # references a schema registered via ai.defineSchema
---
You are a chef famous for creative recipes.

Generate a recipe for {{food}}.

{{#if ingredients}}
Make sure to include the following ingredients:
{{list ingredients}}
{{/if}}
```

Schema fields use Picoschema (the compact form above) or you can reference a
named schema registered with `ai.defineSchema`.

## Loading and calling a prompt

`ai.prompt(name, { variant? })` returns an `ExecutablePrompt`. The returned
object is **callable** and also has `.stream()`, `.render()`, and `.asTool()`.

```ts
// Non-streaming: call it like a function with the input object.
const recipePrompt = ai.prompt('recipe');
const { output } = await recipePrompt({ food: 'banana bread' });

// With a typed output schema
const RecipeSchema = ai.defineSchema('Recipe', z.object({
  title: z.string(),
  steps: z.array(z.string()),
}));
const result = await ai.prompt<any, typeof RecipeSchema>('recipe')({ food: 'banana bread' });
result.output; // typed as Recipe
```

### Streaming

```ts
const storyPrompt = ai.prompt('story');
const { response, stream } = storyPrompt.stream({ subject: 'a robot' });
for await (const chunk of stream) {
  console.log(chunk.text);
}
const final = await response;
```

### Render without generating

Useful for building `ai.generate` calls or LLM-judge evals:

```ts
const rendered = await ai.prompt('recipe').render({ food: 'banana bread' });
// rendered is a GenerateOptions object (messages, model, config, ...)
```

## Registering named schemas

Reference a schema by name in `.prompt` frontmatter (`input.schema` /
`output.schema`) after registering it:

```ts
import { z } from 'genkit';

const RecipeSchema = ai.defineSchema(
  'Recipe',
  z.object({
    title: z.string().describe('recipe title'),
    ingredients: z.array(z.object({ name: z.string(), quantity: z.string() })),
    steps: z.array(z.string()).describe('the steps required'),
  })
);
```

## Variants

Name the file `<name>.<variant>.prompt` — e.g. `recipe.robot.prompt`. Call with
the `variant` option:

```ts
await ai.prompt('recipe', { variant: 'robot' })({ food: 'oil cake' });
```

## Partials

Reusable template fragments. Name a partial file `_<name>.prompt` and include it
with `{{>name param=value}}`.

`prompts/_style.prompt`:
```
{{ role "system" }}
You should speak as if you are a {{#if personality}}{{personality}}{{else}}pirate{{/if}}.
{{role "user"}}
```

`prompts/story.prompt`:
```
---
model: googleai/gemini-pro-latest
input:
  schema:
    subject: string
    personality?: string
---
{{>style personality=personality}}

Tell me a story about {{subject}}.
```

## Helpers

Register a function callable inside templates:

```ts
ai.defineHelper('list', (data: any) =>
  Array.isArray(data) ? data.map((item) => `- ${item}`).join('\n') : ''
);
```

Then use `{{list ingredients}}` in the template.

## Tools, tool-loop control, and middleware

`.prompt` frontmatter can configure tool calling and attach middleware, so an
agent-style prompt is fully described in the file:

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
maxTurns: 20              # max tool-call loop iterations
returnToolRequests: false # return tool requests instead of running them
use:
  - name: retry           # bare string also works: `- retry`
    config:
      maxRetries: 4
---
{{role "system"}}
You are a friendly trip planning assistant. Help users plan trips by suggesting
attractions and looking up flight information. Keep your tone {{tone}}.

{{history}}
```

- `tools`: list of registered tool names.
- `toolChoice`, `maxTurns`, `returnToolRequests`: same semantics as the
  equivalent `ai.generate` options.
- `use`: list of middleware refs. Each entry is a bare string (middleware name)
  or a map with `name` and optional `config`. Names resolve against middleware
  registered on the Genkit instance — register the middleware plugin so the
  name is available:

```ts
import { retry } from '@genkit-ai/middleware';

const ai = genkit({
  plugins: [googleAI(), retry.plugin()],
  promptDir: './prompts',
});
```

See [Using middleware](middleware.md) for the full list of built-in middleware.

## Relationship to agents

Agents (`defineAgent`) share the same dotprompt frontmatter — `system`/`prompt`,
`tools`, `maxTurns`, `returnToolRequests`, and `use`. A `.prompt` file with
`{{history}}` and tools can back an agent directly. See [Agents](agents.md).

