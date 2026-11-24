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

// Reads what the OpenCode plugin and the Pi extension need: each client's MCP
// servers from its own folder (com.google.opencode-config/mcp.json and
// com.google.pi-config/mcp.json), and the always-on rules from rules/ and the
// skills from skills/, which every client shares. None of this throws: an
// extension that throws while loading stops Pi from starting, so a file that
// can't be read is skipped with a warning.

import {existsSync, readdirSync, readFileSync} from "node:fs";
import {dirname, join, normalize} from "node:path";
import {fileURLToPath} from "node:url";

/** The plugin's root folder, the parent of src/. */
export const PLUGIN_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

/**
 * An MCP server from a client's mcp.json. The files use .mcp.json's fields
 * (type, url, headers, timeout in milliseconds, headersHelper); any other
 * field is that client's own server setting and is passed to it as written.
 */
export interface McpServer {
  name: string;
  url: string;
  headers: Record<string, string>;
  timeoutMs?: number;
  // The script that prints the sign-in headers, as an absolute path. Only a
  // server that names one gets them.
  headersHelper?: string;
  // The client's own server settings, such as OpenCode's codemode or Pi's
  // exposure.
  extra: Record<string, unknown>;
}

/** A bundled skill: its SKILL.md fields, path and body. */
export interface SkillFile {
  name: string;
  description: string;
  path: string;
  body: string;
}

/**
 * The warnings these readers gave, for a client that shows them later: Pi's
 * full-screen interface draws over anything printed while it loads.
 */
export const warnings: string[] = [];

/** Records a warning and prints it. */
function warn(message: string, error?: unknown): void {
  const text = `${message}${error ? `: ${error instanceof Error ? error.message : String(error)}` : ""}`;
  warnings.push(text);
  console.warn(`google-cloud: ${text}`);
}

/** Reads a JSON object from the plugin, or returns {} with a warning. */
function readJson(relativePath: string): Record<string, unknown> {
  const path = join(PLUGIN_ROOT, relativePath);
  if (!existsSync(path)) {
    warn(`${relativePath} is missing, so the plugin adds no MCP servers`);
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(readFileSync(path, "utf8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
    warn(`${relativePath} isn't a JSON object, so the plugin adds no MCP servers`);
  } catch (error) {
    warn(`couldn't read ${relativePath}, so the plugin adds no MCP servers`, error);
  }
  return {};
}

/** Reads the mcpServers of a client's MCP file, skipping unusable ones. */
function readServers(relativePath: string): McpServer[] {
  const servers = readJson(relativePath)["mcpServers"];
  if (!servers || typeof servers !== "object") return [];
  const result: McpServer[] = [];
  for (const [name, entry] of Object.entries(servers as Record<string, unknown>)) {
    if (!entry || typeof entry !== "object") continue;
    const { type: _type, url, headers, timeout, headersHelper, ...extra } = entry as Record<string, unknown>;
    if (typeof url !== "string" || !url) {
      warn(`${relativePath}: ${name} has no url, so the plugin skips it`);
      continue;
    }
    result.push({
      name,
      url,
      headers: headers && typeof headers === "object" ? (headers as Record<string, string>) : {},
      timeoutMs: typeof timeout === "number" ? timeout : undefined,
      // A function replacement: a string one would read "$&" in the path.
      headersHelper:
        typeof headersHelper === "string"
          ? normalize(headersHelper.replace("${PLUGIN_ROOT}", () => PLUGIN_ROOT))
          : undefined,
      extra,
    });
  }
  return result;
}

/**
 * Returns the headersHelper script the servers name. They share one sign-in,
 * so they name the same script (the conformance test checks this).
 */
export function helperOf(servers: McpServer[]): string {
  return servers.find((server) => server.headersHelper)?.headersHelper ?? join(PLUGIN_ROOT, "scripts", "adc-headers");
}

/** Returns OpenCode's MCP servers from com.google.opencode-config/mcp.json. */
export function readOpenCodeMcpServers(): McpServer[] {
  return readServers("com.google.opencode-config/mcp.json");
}

/** Returns Pi's MCP servers from com.google.pi-config/mcp.json. */
export function readPiMcpServers(): McpServer[] {
  return readServers("com.google.pi-config/mcp.json");
}

/**
 * Splits a Markdown file into its YAML frontmatter fields and its body.
 * Handles the frontmatter these files use: plain or quoted scalars and the
 * folded (>, >-) and literal (|, |-) block styles. Nested maps such as
 * metadata are skipped.
 */
function parseFrontmatter(text: string): { fields: Record<string, string>; body: string } {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text);
  if (!match) return { fields: {}, body: text };
  const fields: Record<string, string> = {};
  const lines = match[1].split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const field = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(lines[i]);
    if (!field) continue;
    const [, key, rest] = field;
    if (/^[>|][+-]?$/.test(rest)) {
      const block: string[] = [];
      while (i + 1 < lines.length && (/^\s/.test(lines[i + 1]) || lines[i + 1] === "")) block.push(lines[++i]);
      if (rest.startsWith(">")) {
        fields[key] = block.map((line) => line.trim()).join(" ").trim();
      } else {
        // A literal block keeps its lines' indentation past the block's own.
        const indent = Math.min(...block.filter((line) => line.trim()).map((line) => /^\s*/.exec(line)![0].length));
        fields[key] = block.map((line) => line.slice(indent).trimEnd()).join("\n").trim();
      }
    } else if (rest) {
      fields[key] = rest.replace(/^(["'])(.*)\1$/, "$2");
    }
  }
  return { fields, body: match[2] };
}

/** Returns the skills in skills/, sorted by name. */
export function readSkills(): SkillFile[] {
  const root = join(PLUGIN_ROOT, "skills");
  const skills: SkillFile[] = [];
  try {
    for (const entry of readdirSync(root, { withFileTypes: true })) {
      const path = join(root, entry.name, "SKILL.md");
      // A skill can be a symlink to its folder.
      if (!(entry.isDirectory() || entry.isSymbolicLink()) || !existsSync(path)) continue;
      try {
        const { fields, body } = parseFrontmatter(readFileSync(path, "utf8"));
        if (!fields.name || !fields.description) continue;
        skills.push({ name: fields.name, description: fields.description, path, body: body.trimStart() });
      } catch (error) {
        warn(`skipping the skill in ${entry.name}`, error);
      }
    }
  } catch (error) {
    warn(`couldn't read ${root}, so the plugin's skills aren't available`, error);
  }
  if (skills.length === 0) warn(`found no skills in ${root}`);
  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Returns the rules marked trigger: always_on, which Antigravity loads into
 * every conversation, as Markdown without their frontmatter.
 */
export function readAlwaysOnRules(): Array<{ name: string; text: string }> {
  const root = join(PLUGIN_ROOT, "rules");
  const rules: Array<{ name: string; text: string }> = [];
  let files: string[] = [];
  try {
    files = readdirSync(root).filter((file) => file.endsWith(".md")).sort();
  } catch (error) {
    warn(`couldn't read ${root}, so the routing rules aren't added`, error);
  }
  for (const file of files) {
    try {
      const { fields, body } = parseFrontmatter(readFileSync(join(root, file), "utf8"));
      if (fields.trigger === "always_on") rules.push({ name: file.replace(/\.md$/, ""), text: body.trim() });
    } catch (error) {
      warn(`skipping the rule ${file}`, error);
    }
  }
  return rules;
}
