# Deploying / Serving Agents over HTTP (Beta)

> **Beta / preview API.** Uses `expressHandler` from `@genkit-ai/express` and
> the
> agent's beta companion actions. Read [agents.md](agents.md) first.

An agent is served as an HTTP endpoint with `expressHandler`. Most agents also
expose two companion actions:

- `agent.getSnapshotDataAction` → `POST /api/<name>/getSnapshot` — read a
  snapshot's state. Needed for [snapshot restore](agents-branching.md) and
  [background](agents-background.md) polling.
- `agent.abortAgentAction` → `POST /api/<name>/abort` — cancel a
  [background](agents-background.md) turn.

These paths match the `remoteAgent` client defaults (`${url}/getSnapshot`,
`${url}/abort`), so a client only needs the base `url`.

- [A reusable exposeAgent helper](#a-reusable-exposeagent-helper): Lines 27-76
- [CORS for browser clients](#cors-for-browser-clients): Lines 78-99
- [Serving a static web UI (optional)](#serving-a-static-web-ui-optional): Lines 101-119
- [Registering agents/flows](#registering-agentsflows): Lines 121-138
- [Other host frameworks](#other-host-frameworks): Lines 140-200

---

## A reusable `exposeAgent` helper

When serving several agents, a small helper keeps registration consistent.

```ts
import { expressHandler } from '@genkit-ai/express';
import { Agent } from 'genkit/beta';
import express from 'express';

const app = express();
app.use(express.json());

// Register an agent at `/api/<name>`, optionally wiring up its companion
// `/getSnapshot` and `/abort` sub-actions.
function exposeAgent(
  name: string,
  agent: Agent,
  opts: { snapshot?: boolean; abort?: boolean } = {}
) {
  app.post(`/api/${name}`, expressHandler(agent));
  if (opts.snapshot) {
    app.post(
      `/api/${name}/getSnapshot`,
      expressHandler(agent.getSnapshotDataAction)
    );
  }
  if (opts.abort) {
    app.post(`/api/${name}/abort`, expressHandler(agent.abortAgentAction));
  }
}

// Plain conversational agent - no companions needed:
exposeAgent('weatherAgent', weatherAgent);

// Snapshot restore / branching - needs getSnapshot:
exposeAgent('branchingAgent', branchingAgent, { snapshot: true });

// Background agent - needs both getSnapshot (polling) and abort:
exposeAgent('backgroundAgent', backgroundAgent, { snapshot: true, abort: true });

app.listen(process.env.PORT ? parseInt(process.env.PORT) : 8080);
```

Which companions to enable:

| Agent capability                          | `snapshot` | `abort` |
| ----------------------------------------- | ---------- | ------- |
| Plain chat (client- or server-state)      | –          | –       |
| Snapshot restore / [branching](agents-branching.md) | ✓ | –       |
| [Background](agents-background.md) / detach | ✓        | ✓       |

## CORS for browser clients

A browser `remoteAgent` calling a different origin (e.g. a Vite dev server)
needs CORS. **Streaming requires the `X-Genkit-Stream-Id` header** to be allowed
on the request and exposed on the response.

```ts
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header(
    'Access-Control-Allow-Headers',
    'Content-Type, Accept, X-Genkit-Stream-Id'
  );
  res.header('Access-Control-Expose-Headers', 'X-Genkit-Stream-Id');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  if (req.method === 'OPTIONS') {
    res.sendStatus(204);
    return;
  }
  next();
});
```

## Serving a static web UI (optional)

To ship a single server that hosts both the API and a built SPA, serve the
static bundle and add a non-`/api` fallback so client-side routing works on deep
links / reloads.

```ts
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const webDist = join(__dirname, '..', 'web', 'dist');
if (existsSync(webDist)) {
  app.use(express.static(webDist));
  // SPA fallback - send index.html for any non-API GET request.
  app.get(/^\/(?!api\/).*/, (_req, res) => {
    res.sendFile(join(webDist, 'index.html'));
  });
}
```

## Registering agents/flows

Agents and flows must be imported so they register with Genkit. Side-effect
imports work, but explicitly referencing them makes the available actions clear:

```ts
import { weatherAgent } from './weather-agent.js';
import { backgroundAgent } from './background-agent.js';

// Force-reference so the modules' top-level defineAgent/defineFlow run.
void [weatherAgent, backgroundAgent];
```

You can also expose plain flows the same way (e.g. helper endpoints):

```ts
app.post('/api/workspace/files', expressHandler(listWorkspaceFiles));
```

## Other host frameworks

`expressHandler` is one of several adapters — an agent is just an action, so any
of these works. Expose the companion actions
(`agent.getSnapshotDataAction`, `agent.abortAgentAction`) at the matching
sub-paths the same way when you need snapshot restore / background.

### Next.js (`@genkit-ai/next`)

`appRoute` turns an agent into an App Router route handler. Put companions in
their own route files.

```ts
// app/api/weatherAgent/route.ts
import { appRoute } from '@genkit-ai/next';
import { weatherAgent } from '@/lib/agents';

export const POST = appRoute(weatherAgent);

// app/api/weatherAgent/getSnapshot/route.ts
export const POST = appRoute(weatherAgent.getSnapshotDataAction);
```

### Web Fetch (`@genkit-ai/fetch`)

Works with any Fetch-API runtime (Hono, Bun, Deno, Cloudflare Workers, Vercel/
Netlify Edge, etc.). `fetchHandler(action)` returns
`(request) => Promise<Response>`;
`fetchHandlers(actions, prefix)` path-routes multiple actions by name.

```ts
import { fetchHandler } from '@genkit-ai/fetch';
import { Hono } from 'hono';
import { weatherAgent } from './agents.js';

const app = new Hono();
app.all('/api/weatherAgent', (c) => fetchHandler(weatherAgent)(c.req.raw));
app.all('/api/weatherAgent/getSnapshot', (c) =>
  fetchHandler(weatherAgent.getSnapshotDataAction)(c.req.raw)
);
```

### Fastify (`@genkit-ai/fastify`)

```ts
import Fastify from 'fastify';
import { fastifyHandler } from '@genkit-ai/fastify';
import { weatherAgent } from './agents.js';

const app = Fastify();
app.post('/api/weatherAgent', fastifyHandler(weatherAgent));
app.post(
  '/api/weatherAgent/getSnapshot',
  fastifyHandler(weatherAgent.getSnapshotDataAction)
);
await app.listen({ port: 8080 });
```

> The `@genkit-ai/vercel-ai` plugin additionally offers a `GenkitChatTransport`
> for the Vercel AI SDK's `useChat`, which tracks the `chatId → snapshotId`
> mapping for you (no client `SessionStore` needed).
