# Building Custom Middleware

Write reusable, named middleware with `generateMiddleware`. It returns a factory
you call in the `use: [...]` array (see [using middleware](middleware.md)) —
exactly how the `@genkit-ai/middleware` package's middleware are built. The
factory can take optional Zod-validated config and gets access to the `ai`
instance.

```ts
// timing.ts
import { generateMiddleware, z } from 'genkit';

const OptionsSchema = z.object({ label: z.string().optional() });

export const timing = generateMiddleware(
  {
    name: 'timing',
    description: 'Logs how long the model call takes.',
    configSchema: OptionsSchema,
  },
  ({ config, ai }) => {
    // Runs once per generate() call. Return any of the hooks below.
    return {
      model: async (req, ctx, next) => {
        const start = Date.now();
        const res = await next(req, ctx);
        console.log(`[${config?.label ?? 'timing'}] ${Date.now() - start}ms`);
        return res;
      },
    };
  }
);
```

## Register it as a plugin

Register custom middleware with Genkit via its `.plugin()` method. This is the
recommended setup — without it the middleware still works in `use: [...]`, but
it
is **not visible to the Genkit Dev UI**.

```ts
import { genkit } from 'genkit';
import { googleAI } from '@genkit-ai/google-genai';
import { timing } from './timing.js';

export const ai = genkit({
  plugins: [googleAI(), timing.plugin()],
});

// Then use the factory in `use: [...]`:
await ai.generate({
  model: googleAI.model('gemini-flash-latest'),
  prompt: 'Hi',
  use: [timing({ label: 'gen' })],
});
```

## Available hooks

The instantiate callback returns a `GenerateMiddlewareDef` with any subset of:

- `generate(envelope, ctx, next)` — wrap the **whole generate action**. The
  `envelope` carries `{ request, currentTurn, messageIndex }`. Use it to inject
  request params, post-process the response, or catch errors across the tool
  loop.
- `model(req, ctx, next)` — wrap the **underlying model call** (caching, retry,
  request/response rewriting). `req` is a `GenerateRequest`.
- `tool(req, ctx, next)` — wrap **individual tool calls** (validate inputs,
  cache or override tool output). `req` is a `ToolRequestPart`; return a
  `ToolResponsePart | undefined`.
- `tools: ToolAction[]` — **statically inject tools** whenever the middleware is
  active (how `artifacts()` / `filesystem()` add their tools).

```ts
generateMiddleware({ name: 'example' }, ({ ai }) => ({
  generate: async (envelope, ctx, next) => next(envelope, ctx),
  model: async (req, ctx, next) => next(req, ctx),
  tool: async (req, ctx, next) => next(req, ctx),
  tools: [
    /* ToolAction[] */
  ],
}));
```

Call `next(...)` to continue the chain (optionally with a modified
request/envelope) and transform the result before returning it.

## Choosing a hook

- Transform prompt/messages or the final result across the whole turn →
  `generate`.
- Cache/retry/rewrite a single model round-trip → `model`.
- Gate or memoize tool execution → `tool`.
- Make extra capabilities available to the model → `tools`.

> Reminder: register custom middleware via `.plugin()` (see above). It works in
> `use: [...]` without registering, but unregistered middleware is not visible
> to
> the Genkit Dev UI.
