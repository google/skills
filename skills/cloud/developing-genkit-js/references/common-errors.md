# Common Errors & Pitfalls

- [When Typecheck Fails](#when-typecheck-fails): Lines 13-16
- [Genkit v1.x vs Pre-1.0 Migration](#genkit-v1x-vs-pre-10-migration): Lines 18-124
- [Zod and Schema Errors](#zod-and-schema-errors): Lines 126-135
- [Tool Usage](#tool-usage): Lines 137-142
- [Handling Failures in Tool Loops](#handling-failures-in-tool-loops): Lines 144-175
- [Multimodal and Image Generation](#multimodal-and-image-generation): Lines 177-187
- [Audio and Speech Generation](#audio-and-speech-generation): Lines 189-196

---

## When Typecheck Fails

**Before searching source code or docs**, check the sections below. Many type
errors are caused by deprecated APIs or incorrect imports.

## Genkit v1.x vs Pre-1.0 Migration

Genkit v1.x introduced significant API changes. This section covers critical
syntax updates.

### Package Imports

- **Correct (v1.x)**: Import core functionality (zod, genkit) from the main
  `genkit` package and plugins from their specific packages.
  ```ts
  import { z, genkit } from 'genkit';
  import { googleAI } from '@genkit-ai/google-genai';
  ```

- **Incorrect (Pre-1.0)**: Importing from `@genkit-ai/ai`, `@genkit-ai/core`, or
  `@genkit-ai/flow`. These packages are internal/deprecated for direct use.
  ```ts
  import { genkit } from "@genkit-ai/core"; // INCORRECT
  import { defineFlow } from "@genkit-ai/flow"; // INCORRECT
  ```

### Model References

- **Correct**: Use plugin-specific model factories or string identifiers
  (prefaced by plugin name).
  ```ts
  // Using model factory (v1.x - Preferred)
  await ai.generate({ model: googleAI.model('gemini-flash-latest'), ... });

  // Using string identifier
  await ai.generate({ model: 'googleai/gemini-flash-latest', ...});
  // Or
  await ai.generate({ model: 'vertexai/gemini-flash-latest', ...});
  ```
- **Incorrect**: Using imported model objects directly or string identifiers
  without plugin name.
  ```ts
  await ai.generate({ model: gemini15Pro, ... }); // INCORRECT (Pre-1.0)
  await ai.generate({ model: 'gemini-flash-latest', ... }); // INCORRECT (No plugin prefix)
  ```

### Model Selection (Gemini)

- **Preferred**: Use latest model aliases (e.g. `gemini-flash-latest`) for best
  performance and features.
  ```ts
  model: googleAI.model('gemini-flash-latest') // PREFERRED
  ```
- **DEPRECATED**: Versioned legacy models (like `gemini-1.5-flash` or
  `gemini-2.5-flash`) should be updated to latest aliases.
  ```ts
  model: googleAI.model('gemini-1.5-flash') // DEPRECATED (Use gemini-flash-latest instead)
  ```

### Response Access

- **Correct (v1.x)**: Access properties directly.
  ```ts
  response.text; // CORRECT
  response.output; // CORRECT
  ```
- **Incorrect (Pre-1.0)**: Calling as methods.
  ```ts
  response.text(); // INCORRECT
  response.output(); // INCORRECT
  ```

### Streaming Generation

- **Correct (v1.x)**: Do NOT await `generateStream`. Iterate over `stream`
  directly. Await `response` property for final result.
  ```ts
  const {stream, response} = ai.generateStream(...); // NO await here
  for await (const chunk of stream) { ... }          // Iterate stream
  const finalResponse = await response;              // Await response property
  ```
- **Incorrect (Pre-1.0)**: Calling stream as a function or awaiting the
  generator incorrectly.
  ```ts
  for await (const chunk of stream()) { ... } // INCORRECT
  await response();                           // INCORRECT
  ```

### Initialization

- **Correct (v1.x)**: Instantiate `genkit`.
  ```ts
  const ai = genkit({ plugins: [...] });
  ```
- **Incorrect (Pre-1.0)**: Global configuration.
  ```ts
  configureGenkit({ plugins: [...] }); // INCORRECT
  ```

### Flow Definitions

- **Correct (v1.x)**: Define flows on the `ai` instance.
  ```ts
  ai.defineFlow({...}, (input) => {...});
  ```
- **Incorrect (Pre-1.0)**: Importing `defineFlow` globally.
  ```ts
  import { defineFlow } from "@genkit-ai/flow"; // INCORRECT
  ```

You should never import `@genkit-ai/flow`, `@genkit-ai/ai` or `@genkit-ai/core`
packages directly.

## Zod and Schema Errors

- **Import Source**: ALWAYS use `import { z } from "genkit"`.
  - Using `zod` directly from `zod` package may cause instance mismatches or
    compatibility issues.
- **Supported Types**: Stick to basic types: scalar (`string`, `number`,
  `boolean`), `object`, and `array`.
  - Avoid complex Zod features unless strictly necessary and verified.
- **Descriptions**: Always use `.describe('...')` for fields in output schemas
  to guide the LLM.

## Tool Usage

- **Tool Not Found**: Ensure tools are registered in the `tools` array of
  `generate` or provided via plugins.
- **MCP Tools**: Use the `ServerName:tool_name` format when referencing MCP
  tools.

## Handling Failures in Tool Loops

- **Don't throw away finished tool rounds.** By default `generate()` throws on a
  model/tool/middleware failure or at `maxTurns`. Since `genkit` 1.43.0,
  `throwOnError: false` returns the failure on the response along with
  `messages` up to the last completed tool round, so you can retry without
  re-running tools that already succeeded:
  ```ts
  const opts = { model: googleAI.model('gemini-flash-latest'), tools: [getWeather], throwOnError: false };
  let res = await ai.generate({ ...opts, prompt: 'What should I wear in Tokyo?' });
  if (res.finishReason === 'failed' || res.finishReason === 'aborted') {
    console.warn(res.error?.status, res.error?.message); // e.g. INTERNAL, tool "getWeather" failed
    res = await ai.generate({ ...opts, messages: res.messages }); // safe to resend
  }
  ```
  `aborted` means the caller stopped it (abort signal, timeout, `maxTurns`);
  `failed` means something broke. Errors before the request resolves (unknown
  model/tool, invalid options) still throw.
- **Agents: retry a failed turn with `send({})`.** A failed agent turn throws
  `AgentError` (from `genkit/beta/client`), but the chat has already adopted the
  resume point. `await chat.send({})` re-runs the turn from there:
  ```ts
  try {
    await chat.send('Book the full itinerary.');
  } catch (err) {
    if (err instanceof AgentError) await chat.send({});
    else throw err;
  }
  ```
- **Recoverable domain errors belong in tool output.** Return
  `{ ok: false, reason: '...' }` from the tool when the model can fix the input;
  throw only when the system can't continue.

## Multimodal and Image Generation

- **Missing responseModalities**: When using image generation models (like
  `gemini-nano-banana-2.1`), you **MUST** specify the response modalities in the
  config.
  ```ts
  config: {
    responseModalities: ["TEXT", "IMAGE"]
  }
  ```
  Failure to do so will result in errors or incorrect output format.

## Audio and Speech Generation

- **Raw PCM Data vs MP3**: Some providers (e.g., Google GenAI) return raw PCM
  data, while others (e.g., OpenAI) return MP3.
  - **DO NOT assume MP3 format.**
  - **DO NOT embed raw PCM in HTML audio tags.**
  - **Action**: Run `genkit docs:search "speech audio"` to find
    provider-specific conversion steps (e.g., PCM to WAV).
