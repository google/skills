// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// OpenCode 2 plugin: adds the plugin's skills, its always-on rules, and its
// MCP servers signed in with Application Default Credentials.

import type {Plugin} from "@opencode/plugin";
import {GoogleAuth} from "./google-auth.ts";
import {helperOf, readAlwaysOnRules, readOpenCodeMcpServers, readSkills} from "./plugin-files.ts";

const ID = "google-cloud";
// How long the first prompt waits in all for the first token and the servers'
// tools. OpenCode doesn't finish shutting down while a prompt hook runs and
// gives up after 10 seconds without disposing the plugin, which would leave a
// hung helper running, so this stays under that.
const FIRST_PROMPT_WAIT_MS = 8 * 1000;

/**
 * Whether ctx.tool.list(), as JSON, holds a tool of the server: it lists MCP
 * tools by their own name, with the server's name as namespace.
 */
function hasNamespace(tools: string, server: string): boolean {
  return tools.includes(`"namespace":${JSON.stringify(server)}`);
}

/**
 * The server's status in ctx.mcp.list(), as JSON, such as "connected".
 */
function statusOf(list: string, server: string): string | undefined {
  const name = JSON.stringify(server).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`"name":${name},"status":\\{"status":"([a-z_]+)"`).exec(list)?.[1];
}

const plugin: Plugin.Plugin = {
  id: ID,
  async setup(ctx) {
    const servers = readOpenCodeMcpServers();
    const auth = new GoogleAuth(helperOf(servers), () => ctx.mcp.reload(), (message) =>
      console.warn(`${ID}: Google Cloud MCP calls will fail until Application Default Credentials work: ${message}`),
    );

    // Servers the user's own config replaces: the plugin doesn't set or wait
    // for them.
    const overridden = new Set<string>();
    await ctx.mcp.transform((editor) => {
      for (const server of servers) {
        // A server of the same name in the user's own config wins. Each run
        // starts from the config, so the plugin's earlier entry isn't here.
        if (editor.get(server.name)) {
          overridden.add(server.name);
          continue;
        }
        overridden.delete(server.name);
        // Registered before the first token arrives, and even without ADC, on
        // purpose: a call without a token fails with an authentication error,
        // and the skills tell the user to run gcloud auth
        // application-default login (or set the Developer Knowledge API key).
        // Every reload runs this again, so a new token replaces the old
        // headers. Only a server that names a headersHelper gets them.
        editor.set(server.name, {
          ...server.extra,
          type: "remote",
          url: server.url,
          headers: { ...server.headers, ...(server.headersHelper ? auth.headers : {}) },
          // The plugin signs in itself, with the headersHelper script.
          oauth: false,
          ...(server.timeoutMs ? { timeout: { execution: server.timeoutMs } } : {}),
        } as Parameters<typeof editor.set>[1]);
      }
    });

    // ctx.mcp.reload() reconnects every MCP server, not just the plugin's, so
    // any running tool call holds back new headers.
    await ctx.tool.hook("execute.before", () => auth.callStarted());
    await ctx.tool.hook("execute.after", () => auth.callEnded());

    const skills = readSkills();
    await ctx.skill.transform((editor) => {
      for (const skill of skills) {
        editor.add({
          id: skill.name,
          name: skill.name,
          description: skill.description,
          // OpenCode offers a skill to the model unless this is false; set it
          // so the skills keep working if that default changes.
          autoinvoke: true,
          path: skill.path,
          content: skill.body,
        } as Parameters<typeof editor.add>[0]);
      }
    });

    // The first token is applied by a reload when it arrives.
    const started = auth.start();
    auth.startRenewing();

    // A prompt sent before the first token waits for it, and then for the
    // servers' tools to be listed again (at most 8 seconds in all, see
    // FIRST_PROMPT_WAIT_MS): the token reloads the servers, and a run started
    // before their tools are back has none. ctx.mcp.list() reports the
    // servers connected before that, so wait on ctx.tool.list() instead.
    // Without a token (sign-in failed fast) the servers still list their
    // tools, so the model sees them and the authentication error rather than
    // no tools at all; a server that fails ends the wait. Later prompts don't
    // wait, so a server that never lists tools costs 8 seconds once; they
    // renew a token that expired while the machine slept.
    let waited = false;
    await ctx.session.hook("prompt", async () => {
      if (waited) return Promise.race([auth.renewInUse(), new Promise((resolve) => setTimeout(resolve, FIRST_PROMPT_WAIT_MS))]);
      waited = true;
      const end = Date.now() + FIRST_PROMPT_WAIT_MS;
      const first = await Promise.race([
        started.then(() => true),
        new Promise<false>((resolve) => setTimeout(() => resolve(false), FIRST_PROMPT_WAIT_MS)),
      ]);
      // A run that ends before the helper does (opencode run) would otherwise
      // say nothing: stopping the plugin cuts the fetch short without an error.
      if (!first) {
        console.warn(
          `${ID}: scripts/adc-headers hasn't finished after ${FIRST_PROMPT_WAIT_MS / 1000} seconds, so Google Cloud ` +
            `MCP calls will fail until it does. Check that "gcloud auth application-default print-access-token" works.`,
        );
      }
      const ours = servers.filter((server) => !overridden.has(server.name));
      while (Date.now() < end) {
        const tools = JSON.stringify(await ctx.tool.list());
        const list = JSON.stringify(await ctx.mcp.list());
        // Ready once its tools are listed, or once it has failed: OpenCode
        // reports a server connected shortly before its tools are listed.
        const ready = (server: string) =>
          hasNamespace(tools, server) || !["pending", "connected"].includes(statusOf(list, server) ?? "pending");
        if (ours.every((server) => ready(server.name))) return;
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    });

    const rules = readAlwaysOnRules();
    if (rules.length > 0) {
      await ctx.session.hook("context", (event) => {
        for (const rule of rules) event.system.push({ type: "text", text: rule.text });
      });
    }

    return () => auth.stop();
  },
};

// OpenCode loads a plugin from its module's default export.
// tslint:disable-next-line:no-default-export
export default plugin;
