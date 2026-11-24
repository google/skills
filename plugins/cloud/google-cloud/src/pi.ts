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

// Pi extension: adds the plugin's always-on rules and its MCP servers signed
// in with Application Default Credentials. Pi loads the skills itself, from
// "pi.skills" in package.json.

import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";
import {GoogleAuth} from "./google-auth.ts";
import {helperOf, type McpServer, readAlwaysOnRules, readPiMcpServers, warnings} from "./plugin-files.ts";

const ID = "google-cloud";
// How long the first prompt waits for the servers' tools after the first token.
const TOOLS_WAIT_MS = 10 * 1000;

/**
 * Pi names an MCP tool mcp__<server>__<tool>, with characters other than
 * letters, digits and "_" replaced by "_".
 */
function toolPrefix(server: string): string {
  return `mcp__${server.replace(/[^A-Za-z0-9_]/g, "_")}__`;
}

/**
 * Registers the plugin's always-on rules and MCP servers with Pi, which loads
 * an extension from its module's default export.
 */
// tslint:disable-next-line:no-default-export
export default async function googleCloud(pi: ExtensionAPI): Promise<void> {
  const rules = readAlwaysOnRules();
  // The current session's ctx; Pi's ctx and action methods are stale once the
  // session ends, and using them then throws, which ends Pi.
  let session: { ui: { notify(message: string, level: "warning"): void } } | undefined;
  const warn = (message: string) => {
    try {
      session?.ui.notify(`${ID}: ${message}`, "warning");
    } catch {
      // The session ended in the meantime.
    }
  };
  // The first token's fetch, and whether the first prompt has waited for it.
  let firstToken: Promise<void> = Promise.resolve();
  let waited = false;
  let renewIfDue: () => Promise<void> = () => Promise.resolve();
  let waitForTools: () => Promise<void> = () => Promise.resolve();
  let turnStarted: () => void = () => {};
  pi.on("before_agent_start", async (event) => {
    // The first prompt waits for the first token (at most the helper's
    // 30-second limit), so the model's first calls carry it, and then for the
    // servers' tools: applying the token re-registers the servers, and Pi
    // hides their tools until they reconnect, so a request sent then would
    // declare none. A later prompt renews a token that expired while the
    // machine slept, and waits for the tools the same way.
    if (!waited) {
      waited = true;
      await firstToken;
    } else {
      await renewIfDue();
    }
    await waitForTools();
    for (const rule of rules) event.systemPromptOptions.sections[rule.name] = rule.text;
    turnStarted();
  });

  // This load's warnings, taken from the shared list so that a later load (a
  // new session in the same process) doesn't repeat them.
  const loadWarnings = warnings.splice(0);

  // Pi releases before built-in MCP still get the skills and the rules. An
  // extension that throws while loading stops Pi from starting.
  if (typeof pi.registerMcpServer !== "function") {
    pi.on("session_start", (_event, ctx) => {
      for (const message of loadWarnings.splice(0)) ctx.ui.notify(`${ID}: ${message}`, "warning");
      ctx.ui.notify(`${ID}: the Google Cloud MCP servers need a newer Pi; run pi update.`, "warning");
    });
    return;
  }

  const servers = readPiMcpServers();
  loadWarnings.push(...warnings.splice(0));

  // Servers another extension registered first, such as a second install of
  // this plugin. Pi throws for those names, and a throw while loading stops
  // Pi, so they are skipped and reported instead.
  const conflicts = new Map<string, string>();
  const reportConflict = (message: string) =>
    warn(`${message}. Is the plugin installed twice? pi list shows what's installed, and pi remove <source> removes one.`);
  const register = () => {
    for (const server of servers) {
      // Registered before the first token arrives, and even without ADC, on
      // purpose: a call without a token fails with an authentication error,
      // and the skills tell the user to run gcloud auth
      // application-default login (or set the Developer Knowledge API key).
      try {
        pi.registerMcpServer(server.name, serverConfig(server, auth.headers));
        conflicts.delete(server.name);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        // One that appears after session_start is reported now.
        if (session && conflicts.get(server.name) !== message) reportConflict(message);
        conflicts.set(server.name, message);
      }
    }
  };
  // Registering a name again replaces the earlier registration, so this also
  // applies new headers. A server of the same name in the user's mcp.json wins.
  const auth = new GoogleAuth(helperOf(servers), register, (message) =>
    warn(`Google Cloud MCP calls will fail until Application Default Credentials work: ${message}`),
  );
  register();
  renewIfDue = () => auth.renewInUse();
  // Waits (at most 10 seconds) until every server's tools are active. It runs
  // from before_agent_start: Pi's action methods, getActiveTools included,
  // throw while extensions load and once the session has ended.
  waitForTools = async () => {
    if (!auth.headers["Authorization"]) return;
    const ready = () => {
      try {
        const tools = pi.getActiveTools();
        return servers.every(
          (server) => conflicts.has(server.name) || tools.some((tool) => tool.startsWith(toolPrefix(server.name))),
        );
      } catch {
        return true;
      }
    };
    const end = Date.now() + TOOLS_WAIT_MS;
    while (session && !ready() && Date.now() < end) await new Promise((resolve) => setTimeout(resolve, 100));
  };

  // New headers are held back for a whole agent turn, not just a call to the
  // plugin's tools: re-registering hides the servers' tools until they
  // reconnect, and Pi builds the turn's next request right after each call.
  // GoogleAuth still applies them once the token in use is 50 minutes old, or
  // once a turn has run 20 minutes.
  let inTurn = false;
  turnStarted = () => {
    if (inTurn) return;
    inTurn = true;
    auth.callStarted();
  };
  const turnEnded = () => {
    if (!inTurn) return;
    inTurn = false;
    auth.callEnded();
  };
  pi.on("agent_end", turnEnded);
  // A long turn that keeps calling tools isn't one that missed its end.
  pi.on("tool_execution_start", () => {
    if (inTurn) auth.callActive();
  });
  // Pi loads extensions afresh for each session (a new session, /resume or
  // /fork runs this function again after session_shutdown), and some commands
  // load them without starting a session, so gcloud runs and renewal runs
  // only while a session does, as Pi's extension docs ask for timers.
  pi.on("session_start", (_event, ctx) => {
    session = ctx;
    // Printed while Pi loaded, where its interface hides them.
    // Shown once per load: Pi can fire session_start twice for a new session.
    for (const message of loadWarnings.splice(0)) warn(message);
    for (const message of conflicts.values()) reportConflict(message);
    // The servers are registered again with the first token when it arrives.
    firstToken = auth.start();
    auth.startRenewing();
  });
  pi.on("session_shutdown", () => {
    session = undefined;
    turnEnded();
    auth.stop();
  });
}

/**
 * Pi's server entry. Only a server that names a headersHelper gets the
 * Application Default Credentials headers.
 */
function serverConfig(server: McpServer, adcHeaders: Record<string, string>) {
  return {
    ...server.extra,
    type: "http" as const,
    url: server.url,
    headers: { ...server.headers, ...(server.headersHelper ? adcHeaders : {}) },
    // Pi's timeout is in seconds.
    ...(server.timeoutMs ? { timeout: Math.ceil(server.timeoutMs / 1000) } : {}),
  } as Parameters<ExtensionAPI["registerMcpServer"]>[1];
}
