# Dotprompt — Genkit Python

- [What It Is](#what-it-is): Lines 15-20
- [File Format](#file-format): Lines 22-65
- [Python Setup](#python-setup): Lines 67-88
- [Calling a Prompt (Prompt)](#calling-a-prompt-prompt): Lines 90-125
- [Streaming from a Prompt](#streaming-from-a-prompt): Lines 127-145
- [Render Without Generating](#render-without-generating): Lines 147-161
- [Helpers](#helpers): Lines 163-187
- [Variants and Partials](#variants-and-partials): Lines 189-196
- [Prompts with Tools and Middleware](#prompts-with-tools-and-middleware): Lines 198-220

---

## What It Is

`.prompt` files pair YAML frontmatter (model, config, input/output schemas,
tools, middleware) with Handlebars templates. Handlebars templates **only**
render inside `.prompt` files and `ai.define_prompt(...)` — strings passed to
`ai.generate(prompt=..., system=...)` are sent to the model verbatim.

## File Format

Place `.prompt` files inside `prompts/` and pass `prompt_dir=...` to
`Genkit(...)`:

```yaml
---
model: googleai/gemini-flash-latest
config:
  temperature: 0.4
input:
  default:
    tone: practical
  schema:
    food: string
    tone?: string                 # optional scalar - `field?: type`
    ingredients?(array): string   # optional array/object uses parenthetical syntax
output:
  schema: Recipe                  # references a schema registered via ai.define_schema()
  format: json
---
{{role "system"}}
You are a chef. Keep recipes {{tone}}.

{{role "user"}}
Generate a recipe for {{food}}.
{{#if ingredients}}
Prefer these ingredients:
{{list ingredients}}
{{/if}}
```

Use `{{role "system"}}` and `{{role "user"}}` to emit distinct message roles; a
template without `{{role ...}}` becomes a single user message.

**Input & output validation:**

- Prompt inputs **are validated** against `input.schema` (or `input_schema=` on
  `define_prompt`) before calling the model, and `input.default` values from
  `.prompt` frontmatter are filled in automatically.
- When `output.schema` names a Pydantic class registered with
  `ai.define_schema('Recipe', Recipe)`, `response.output` is validated and
  returned directly as `Recipe | None` (`None` when the model's JSON is
  truncated or malformed; check `response.finish_reason`).

## Python Setup

```python
from pathlib import Path
from pydantic import BaseModel
from genkit import Genkit, Prompt
from genkit_google_genai import GoogleAI

ai = Genkit(
    plugins=[GoogleAI()],
    model=GoogleAI.gemini('gemini-flash-latest'),
    prompt_dir=Path(__file__).resolve().parent.parent / 'prompts',
)


class Recipe(BaseModel):
    title: str
    steps: list[str]


ai.define_schema('Recipe', Recipe)
```

## Calling a Prompt (`Prompt`)

`ai.prompt(...)` and `ai.define_prompt(...)` return a `Prompt`. There is no
`.execute()` method — call and `await` the `Prompt` directly:

```python
recipe_prompt: Prompt = ai.prompt('recipe')

# Call options use the same keyword names as `ai.generate`.
# `config` merges key-by-key over the prompt's frontmatter config.
# `output_schema` is fixed by the prompt and cannot be overridden per call.
response = await recipe_prompt(
    {'food': 'banana bread', 'ingredients': ['walnuts', 'cinnamon']},
    config={'temperature': 0.2},
)
if response.output is not None:
    recipe: Recipe = response.output

# Variant (`prompts/recipe.quick.prompt`)
quick_res = await ai.prompt('recipe', variant='quick')({'food': 'banana bread'})
```

### Code-Defined Prompts (`ai.define_prompt`)

```python
class GreetingInput(BaseModel):
    name: str


greet = ai.define_prompt(
    name='greet',
    input_schema=GreetingInput,
    prompt='Say hello to {{name}}.',
)
res = await greet(GreetingInput(name='Ana'))
```

## Streaming from a Prompt

`prompt.stream(...)` is synchronous (do not `await` it); iterate `.stream` and
`await` `.response`:

```python
from genkit import FlowContext

@ai.flow()
async def stream_recipe(food: str, ctx: FlowContext[str]) -> str:
    sr = ai.prompt('recipe').stream({'food': food})
    chunks: list[str] = []
    async for chunk in sr.stream:
        if chunk.text:
            ctx.send_chunk(chunk.text)
            chunks.append(chunk.text)
    final = await sr.response
    return final.text or ''.join(chunks)
```

## Render Without Generating

`render(...)` takes the same arguments as a call and returns the
`GenerateActionOptions` (model, config, messages, output schema) without calling
a model. Use it to debug templates and input defaults:

```python
rendered = await ai.prompt('recipe').render({'food': 'focaccia'})
print(rendered.model, rendered.config)
# => googleai/gemini-flash-latest {'temperature': 0.4}
for message in rendered.messages:
    print(message.role, message.text.strip())
# => system You are a chef. Keep recipes practical.
# => user Generate a recipe for focaccia.
```

## Helpers

Register Handlebars helpers with `ai.define_helper(name, fn)`. Dotprompt calls
every helper as `fn(params, options)`: `params` is the list of positional
template arguments, `options` carries hash arguments. A one-argument function
raises `TypeError` at render time.

```python
from typing import Any


def list_helper(params: list[Any], options: Any) -> str:
    items = params[0] if params else None
    if not isinstance(items, list):
        return ''
    return '\n'.join(f'- {item}' for item in items)


ai.define_helper('list', list_helper)
```

Built-in helpers: `role`, `json`, `media`, `history`, `section`, `ifEquals`,
`unlessEquals`.

Use `{{list ingredients}}` in the `.prompt` body.

## Variants and Partials

- **Variants**: save `<name>.<variant>.prompt` (e.g. `recipe.vegan.prompt`) and
  load with `ai.prompt('recipe', variant='vegan')`.
- **Partials**: prefix partial files with `_` (e.g.
  `prompts/_disclaimer.prompt`) or register with
  `ai.define_partial('disclaimer', '...')`, then include via `{{>disclaimer}}`
  or `{{>disclaimer region=region}}`.

## Prompts with Tools and Middleware

- **Tools**: list registered tool names under `tools:` in YAML frontmatter, or
  pass `tools=[lookup_rate]` when calling
  `await prompt(input, tools=[lookup_rate])`. The tool loop stops after
  `maxTurns` (frontmatter) or `max_turns=` (call), default 50.
- **Middleware**: pass instances at call time with `use=[Retry(max_retries=2)]`.
  To name middleware under `use:` in frontmatter, register it first: add
  `Middleware()` from `genkit_middleware` to `Genkit(plugins=[...])` (registers
  `retry`, `fallback`, `tool_approval`, `skills`, `filesystem`) or define your
  own with `@ai.middleware`. An unregistered name fails with `NOT_FOUND`.

```yaml
---
model: googleai/gemini-flash-latest
tools: [lookup_rate]
use:
  - name: retry
    config:
      max_retries: 2
---
Convert {{amount}} USD to EUR.
```
