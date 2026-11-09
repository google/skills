# A2UI (Agent-to-UI) generative UI

The `@genkit-ai/a2ui` plugin brings
> [A2UI](https://a2ui.org/), a transport-agnostic, JSON-based streaming UI
> protocol, to Genkit agents.
>
> A2UI builds on the agent client, so it uses the agent APIs: `genkit/beta` on
> the server and `genkit/beta/client` in the browser. Read [Agents](agents.md)
> first if you have not.

An A2UI-enabled agent streams more than prose. It streams interactive UI
**surfaces** (cards, lists, forms, buttons) that a client renders incrementally
as the model responds. The entire server-side integration is a single model
middleware: add `a2ui()` to an agent's `use` array and nothing else changes.

- [Install](#install): Lines 26-41
- [Server: add the a2ui() middleware](#server-add-the-a2ui-middleware): Lines 43-106
- [Client: render surfaces](#client-render-surfaces): Lines 108-162
- [Handling user actions](#handling-user-actions): Lines 164-224
- [Custom catalogs](#custom-catalogs): Lines 226-276
- [Security and the trust boundary](#security-and-the-trust-boundary): Lines 278-298
- [How it works](#how-it-works): Lines 300-321

---

## Install

```bash
npm i @genkit-ai/a2ui
```

To render surfaces in the browser you also need a renderer. A2UI ships renderers
for [`@a2ui/lit`](https://www.npmjs.com/package/@a2ui/lit),
[`@a2ui/react`](https://www.npmjs.com/package/@a2ui/react), and
[`@a2ui/angular`](https://www.npmjs.com/package/@a2ui/angular). The examples
here
use Lit:

```bash
npm i @a2ui/lit @a2ui/web_core @a2ui/markdown-it lit @lit/context
```

## Server: add the `a2ui()` middleware

Add `a2ui()` to your agent's `use` array. That is the whole server-side setup.
`use` auto-registers the middleware, so no plugin entry is required in
`genkit({ plugins: [...] })`.

```ts
import { googleAI } from '@genkit-ai/google-genai';
import { a2ui } from '@genkit-ai/a2ui';
import { genkit } from 'genkit/beta';

const ai = genkit({ plugins: [googleAI()] });

export const uiAgent = ai.defineAgent({
  name: 'uiAgent',
  model: googleAI.model('gemini-flash-latest'),
  system:
    'You help users. Render an A2UI surface whenever a result is clearer ' +
    'shown than told (weather, comparisons, lists, forms). Keep prose brief; ' +
    'put the substance in the UI.',
  use: [a2ui()], // defaults to the bundled 'basic' catalog
});
```

It works identically on a one-shot `ai.generate`:

```ts
const res = await ai.generate({
  model: googleAI.model('gemini-flash-latest'),
  prompt: 'Show me the weather in Tokyo',
  use: [a2ui()],
});
```

Serve the agent over HTTP with `expressHandler` (see
[Deploying agents](agents-deployment.md)); the browser talks to it with
`remoteAgent`. `expressHandler` reads the request body, so mount
`express.json()` before the route or the first turn fails with
`request.body is undefined`:

```ts
import { expressHandler } from '@genkit-ai/express';
import express from 'express';

const app = express();
app.use(express.json()); // required: expressHandler reads req.body
app.post('/api/uiAgent', expressHandler(uiAgent));
```

### Options

Pass options to `a2ui({ ... })`:

| Option         | Default    | Description                                                                                             |
| -------------- | ---------- | ------------------------------------------------------------------------------------------------------- |
| `catalog`      | `'basic'`  | Id of the catalog describing what the agent may render.                                                 |
| `instructions` | `'system'` | Where to inject catalog capabilities. `'none'` injects nothing (supply your own instructions instead).  |
| `validate`     | `'warn'`   | Validate emitted envelopes. `'warn'` logs and drops bad blocks; `'strict'` throws; `'off'` skips it.    |
| `surfaceId`    | fresh UUID | Surface id policy. Defaults to a new UUID per surface; pass a fixed string to reuse one id per surface. |
| `version`      | `'v0.9'`   | Protocol version stamped on envelopes.                                                                  |

Use `validate: 'strict'` during development to fail fast on malformed JSON or
components outside the catalog. See [Security](#security-and-the-trust-boundary)
for what `'strict'` does and does not check.

## Client: render surfaces

`@genkit-ai/a2ui/client` is browser-safe (no Node dependencies). Consume the
agent with `remoteAgent`, pull A2UI envelopes off each chunk with
`a2uiEnvelopesFromParts`, and feed whole envelopes to a renderer. A2UI travels
as
`data` parts on the raw model chunk, so read them from
`chunk.raw.modelChunk?.content`.

```ts
import { A2uiSurface, basicCatalog } from '@a2ui/lit/v0_9';
import '@a2ui/lit/v0_9'; // registers <a2ui-surface> + basic components
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import { a2uiEnvelopesFromParts } from '@genkit-ai/a2ui/client';
import { remoteAgent } from 'genkit/beta/client';

const chat = remoteAgent({ url: '/api/uiAgent' }).chat();

const processor = new MessageProcessor([basicCatalog]);
processor.onSurfaceCreated((surface) => {
  // `a2ui-surface` is not in the DOM's tag map, so narrow to the renderer's
  // element class for a typed `.surface` property.
  const el = document.createElement('a2ui-surface') as A2uiSurface;
  el.surface = surface;
  document.getElementById('log')!.appendChild(el);
});

const turn = chat.sendStream('What is the weather in Tokyo?');
for await (const chunk of turn.stream) {
  if (chunk.text) appendProse(chunk.text);
  const envelopes = a2uiEnvelopesFromParts(chunk.raw.modelChunk?.content);
  if (envelopes.length) processor.processMessages(envelopes);
}
await turn.response; // surfaces any server error / finalizes the turn
```

`remoteAgent` manages the session id for you, so a single `chat` keeps the whole
conversation server-side (the agent's session store holds history).

### Lightweight helper (no full agent client)

If you do not want to drive `remoteAgent` yourself, the client entrypoint also
ships `streamA2uiAgent`, an async generator that yields `{ type: 'text' }` and
`{ type: 'envelopes' }` events:

```ts
import { streamA2uiAgent } from '@genkit-ai/a2ui/client';

for await (const ev of streamA2uiAgent({ url: '/api/uiAgent', message: 'weather in Tokyo' })) {
  if (ev.type === 'text') appendProse(ev.text);
  else processor.processMessages(ev.envelopes);
}
```

`StreamA2uiAgentOptions` also accepts `sessionId`, `headers`, and `abortSignal`.

## Handling user actions

When a user interacts with a surface (for example, presses a `Button`), the
renderer's action callback hands you a typed `A2uiClientAction`. Turn it into an
agent input with `actionToMessage` and send it as the next turn:

```ts
import { actionToMessage } from '@genkit-ai/a2ui/client';

const processor = new MessageProcessor([basicCatalog], (action) => {
  const turn = chat.sendStream({ message: actionToMessage(action) });
  // ...consume turn.stream like above...
});
```

The action's `name` is sent as the user message; the full action (including its
`context`) is attached as an a2ui data part so the agent can react to it.

### Forms

Input components (`TextField`, `CheckBox`, `Slider`) do **not** send their
values
automatically. To capture what the user entered, the model must:

1. Bind each input's `value` to a data-model path (`{ "path": "/email" }`).
2. Echo those same paths in the submit `Button`'s `action.event.context`.

The catalog capabilities injected into the system prompt already instruct the
model to do this. Without both steps, the action arrives with an empty
`context`.

### Renderer requirements (Lit basic catalog)

The `@a2ui/lit` basic catalog needs two host-side pieces to render fully:

- A **MarkdownRenderer** provided via Lit context (for example, backed by
  `@a2ui/markdown-it`). `Text` heading `variant`s render as Markdown; without a
  renderer, headings show as literal `##`.
- The **Material Symbols Outlined** font. The `Icon` component renders names as
  font ligatures; without the font, icon names show as literal text. Load it in
  your HTML:
  ```html
  <link rel="stylesheet"
    href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0..1,0" />
  ```

Wire up the Markdown renderer and inject the basic catalog styles once at
startup:

```ts
import { Context } from '@a2ui/lit/v0_9';
import { renderMarkdown } from '@a2ui/markdown-it';
import { injectBasicCatalogStyles } from '@a2ui/web_core/v0_9/basic_catalog';
import { ContextProvider } from '@lit/context';

injectBasicCatalogStyles();
new ContextProvider(document.body as any, {
  context: Context.markdown,
  initialValue: renderMarkdown,
});
```

## Custom catalogs

The `catalog` option is a **catalog id** resolved from the Genkit registry. The
bundled `'basic'` catalog (mirroring `@a2ui/web_core`'s basic catalog) is the
default and needs no registration. A catalog describes the components the model
may emit:

- `id`: globally-unique URI (also used as `catalogId` on `createSurface`).
- `components[]`: each with `name` (matches the renderer type), `description`
  (one-line summary), and `props` (a compact, model-facing text description of
  the component's props, kept as plain text to minimize prompt tokens).

Register a catalog with `loadCatalog`, then reference it by id. Load from a JSON
file:

```ts
import { loadCatalog } from '@genkit-ai/a2ui';

await loadCatalog(ai, { id: 'my-catalog', file: './my-catalog.json' });
```

Or define one in memory (start from `basicCatalog` and add your own component):

```ts
import { a2ui, basicCatalog, loadCatalog, type A2uiCatalog } from '@genkit-ai/a2ui';

const myCatalog: A2uiCatalog = {
  id: 'https://my-app.org/catalogs/weather.json',
  components: [
    ...basicCatalog.components,
    {
      name: 'Gauge',
      description: 'A circular gauge visualizing a single numeric value.',
      props: 'value: number or { path } binding (required); min?: number; max?: number; label?: string; unit?: string.',
    },
  ],
};

await loadCatalog(ai, { id: 'my-catalog', catalog: myCatalog });

export const uiAgent = ai.defineAgent({
  name: 'uiAgent',
  model: googleAI.model('gemini-flash-latest'),
  use: [a2ui({ catalog: 'my-catalog', validate: 'strict' })],
});
```

The **client must register a matching renderer** under the same catalog id, and
the component `name` must match on both sides. Otherwise the model emits a
component the client cannot render. Catalogs live in the registry under value
type `a2ui-catalog`.

## Security and the trust boundary

Generative UI moves model output into the DOM, so treat every surface an agent
emits as **untrusted input**. The `validate` option (including `'strict'`)
checks
envelope structure and component *type names* against the catalog only. It does
**not** validate component props or data-model values: model-controlled values
such as `Image.url` and `Text` (inline Markdown that a renderer may turn into
HTML) pass through untouched. `'strict'` is a well-formedness check, not a
security boundary.

- **The renderer/catalog owns prop sanitization.** Whatever renders a surface is
  responsible for escaping and sanitizing prop values before they reach the DOM.
- **Restrict remote sources at the host.** Serve the app with a Content Security
  Policy that limits `img-src` and other fetch directives to origins you trust.
- **Do not put secrets in the data model.** Anything bound into a surface's data
  model can be echoed back through an action's `context`.

For server-side control over props (for example, allow-listing image hosts), add
your own model middleware after `a2ui()` to inspect and rewrite the emitted a2ui
parts.

## How it works

A2UI rides on its own part channel: a Genkit `data` part with mime type
`application/a2ui+json` whose `data` is `{ envelopes: [...] }`. On each model
call
inside the agent's tool loop, `a2ui()`:

1. Injects the catalog's capabilities into the system prompt (unless
   `instructions: 'none'`).
2. Intercepts the model output (streamed chunks and the final message).
3. Extracts `a2ui` fenced code blocks from the model's text.
4. Validates them against the catalog (per `validate`).
5. Rewrites them into canonical a2ui data parts.

Inbound a2ui parts (a surface action sent back as the next turn, or replayed
history) are summarized into plain text before the underlying model sees them,
so
a model that does not understand the a2ui mime type can still reason about prior
surfaces and user actions.

For a complete, runnable example (Express backend plus a Vite + Lit frontend),
see the `a2ui` testapp in the Genkit JS repo.

