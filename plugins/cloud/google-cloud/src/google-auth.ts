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

// Application Default Credentials headers for the MCP servers. OpenCode and
// Pi send fixed headers, with nothing like Claude Code's headersHelper, so the
// plugin runs scripts/adc-headers itself, the same script Claude Code and
// Codex run, and hands the client new headers when the token changes.

import {execFileSync, spawn} from "node:child_process";
import {homedir} from "node:os";
import {delimiter, join} from "node:path";

// gcloud mints a new access token on every call, valid for an hour; the
// script doesn't pass on the real expiry. Applying a token makes the client
// reconnect the servers, which ends a running call, so a token is renewed
// when it is REFRESH_AFTER_MS old but applied only between calls, and in any
// case before it is APPLY_BY_MS old: the poll notices that at most POLL_MS
// late, so the servers never hold a token older than 54 minutes. Credentials
// with a shorter lifetime (an impersonated service account under a lifetime
// policy, for example) expire before that, and calls fail with 401s until
// the next renewal.
const REFRESH_AFTER_MS = 30 * 60 * 1000;
const APPLY_BY_MS = 50 * 60 * 1000;
// How often to check the token's age, and to retry while there are no
// credentials yet (for example before gcloud auth application-default login).
const POLL_MS = 4 * 60 * 1000;
const SCRIPT_TIMEOUT_MS = 30 * 1000;
// How long the client may take to take new headers before it counts as failed.
const APPLY_TIMEOUT_MS = 30 * 1000;
// A call running longer than this missed its end-of-call event (for example a
// cancelled call), and no longer holds back new headers. It is the longest
// call timeout in the plugin's MCP files; the plugin conformance test checks
// that none is longer.
const MAX_CALL_MS = 20 * 60 * 1000;

/** GoogleAuth's timings; tests shorten them. */
export interface Timings {
  refreshAfterMs: number;
  applyByMs: number;
  pollMs: number;
  scriptTimeoutMs: number;
  applyTimeoutMs: number;
  maxCallMs: number;
}

const TIMINGS: Timings = {
  refreshAfterMs: REFRESH_AFTER_MS,
  applyByMs: APPLY_BY_MS,
  pollMs: POLL_MS,
  scriptTimeoutMs: SCRIPT_TIMEOUT_MS,
  applyTimeoutMs: APPLY_TIMEOUT_MS,
  maxCallMs: MAX_CALL_MS,
};

/**
 * Where the Google Cloud CLI is usually installed. A desktop app started from
 * the Dock or Start menu may not inherit the shell's PATH, so these are added
 * after it.
 */
function gcloudDirs(): string[] {
  const home = homedir();
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA ?? join(home, "AppData", "Local");
    return [
      join(local, "Google", "Cloud SDK", "google-cloud-sdk", "bin"),
      join(process.env.ProgramFiles ?? "C:\\Program Files", "Google", "Cloud SDK", "google-cloud-sdk", "bin"),
      join(process.env["ProgramFiles(x86)"] ?? "C:\\Program Files (x86)", "Google", "Cloud SDK", "google-cloud-sdk", "bin"),
    ];
  }
  return [
    join(home, "google-cloud-sdk", "bin"),
    "/opt/homebrew/bin",
    "/opt/homebrew/share/google-cloud-sdk/bin",
    "/usr/local/bin",
    "/usr/local/share/google-cloud-sdk/bin",
    "/snap/bin",
    "/usr/bin",
  ];
}

/** The message of an error, or the value as text. */
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Rejects after ms with message, so an await never hangs on a promise that
 * doesn't settle.
 */
function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/**
 * Runs the helper and returns its headers. onSpawn gets its process ID, so
 * stop() can end a run still going. Settles within SCRIPT_TIMEOUT_MS, even if
 * the helper outlives its kill.
 */
function runAdcHeaders(
  helper: string,
  timeoutMs: number,
  onSpawn: (pid: number | undefined) => void = () => {},
): Promise<Record<string, string>> {
  // Windows names it Path, and a copy of process.env keeps that name, so drop
  // every spelling before setting PATH: with two, a child can read either.
  const env: Record<string, string | undefined> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (key.toUpperCase() !== "PATH") env[key] = value;
  }
  env.PATH = [process.env.PATH, ...gcloudDirs()].filter(Boolean).join(delimiter);
  const windows = process.platform === "win32";
  // cmd.exe /s strips the outer pair of quotes from what follows /c, so the
  // path gets two pairs and is passed verbatim, as Node's own shell option
  // does; otherwise a path with a space, such as C:\Users\First Last\...,
  // splits at the space.
  const [file, args] = windows
    ? ["cmd.exe", ["/d", "/s", "/c", `""${helper}.cmd""`]]
    : ["bash", [helper]];
  // On POSIX the helper leads its own process group, so a timeout can stop
  // gcloud too: killing only the shell leaves gcloud running until it gives
  // up. That also keeps it from the terminal's Ctrl+C, so an exit hook stops
  // it if the client exits first.
  const options = { env, windowsHide: true, windowsVerbatimArguments: windows, detached: !windows };
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, options);
    onSpawn(child.pid);
    // Kept until the helper has exited, not just until this settles: one that
    // outlives its timeout is still stopped when the client exits. SIGTERM
    // lets the script release its lock; a SIGKILL would leave the lock behind.
    const killOnExit = () => killTree(child.pid, true);
    process.once("exit", killOnExit);
    const exited = () => {
      process.removeListener("exit", killOnExit);
      if (child.pid !== undefined) signaled.delete(child.pid);
    };
    let settled = false;
    const finish = (settle: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      settle();
    };
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8").on("data", (chunk: string) => (stdout += chunk));
    child.stderr.setEncoding("utf8").on("data", (chunk: string) => (stderr += chunk));
    const timer = setTimeout(() => {
      killTree(child.pid);
      // Settle on the timeout itself: close fires only once the process has
      // exited and its pipes are closed, which a wedged gcloud may never do.
      finish(() =>
        reject(new Error(
          `scripts/adc-headers didn't finish in ${timeoutMs / 1000} seconds. Check that ` +
          `"gcloud auth application-default print-access-token" works; if you haven't signed in, ` +
          `run: gcloud auth application-default login`,
        )),
      );
    }, timeoutMs);
    child.on("error", (error) => {
      exited();
      finish(() => reject(error));
    });
    child.on("close", (code, signal) => {
      exited();
      finish(() => {
        if (code !== 0) {
          reject(new Error(stderr.trim() || `scripts/adc-headers stopped (${signal ?? `exit code ${code}`}).`));
          return;
        }
        // stdout carries an access token, so describe it without quoting it:
        // these messages are logged and shown to the user.
        let parsed: unknown;
        try {
          parsed = JSON.parse(stdout);
        } catch {
          const first = JSON.stringify(stdout.trimStart()[0] ?? "");
          reject(new Error(`scripts/adc-headers printed ${stdout.length} bytes that aren't JSON (starting with ${first}).`));
          return;
        }
        const headers = parsed as Record<string, unknown>;
        if (
          !parsed || typeof parsed !== "object" || Array.isArray(parsed) ||
          Object.values(headers).some((value) => typeof value !== "string")
        ) {
          reject(new Error("scripts/adc-headers printed JSON that isn't an object of string headers."));
          return;
        }
        resolve(headers as Record<string, string>);
      });
    });
  });
}

/** The helpers killTree has sent SIGTERM to, until they exit. */
const signaled = new Set<number>();

/**
 * Stops the helper and everything it started: cmd.exe, PowerShell and gcloud
 * on Windows, the shell and gcloud elsewhere. On POSIX it sends SIGTERM, which
 * the script traps to release its lock, and forces it 2 seconds later unless
 * the client is exiting (exiting), when there is no later.
 */
function killTree(pid: number | undefined, exiting = false): void {
  if (pid === undefined) return;
  // A second SIGTERM interrupts the script while it releases its lock, so the
  // exit hook leaves alone a helper that stop() or the timeout already asked
  // to stop.
  if (exiting && signaled.has(pid)) return;
  if (!exiting) signaled.add(pid);
  try {
    if (process.platform === "win32") {
      // Waited for: a client that exits right after stop() would otherwise
      // end taskkill before it reaches gcloud.
      execFileSync("taskkill", ["/pid", String(pid), "/t", "/f"], { windowsHide: true, stdio: "ignore", timeout: 10000 });
      return;
    }
    process.kill(-pid, "SIGTERM");
    if (exiting) return;
  } catch {
    return; // It has already exited.
  }
  const force = setTimeout(() => {
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      // It exited on SIGTERM.
    }
  }, 2000);
  (force as { unref?: () => void }).unref?.();
}

/**
 * Keeps Application Default Credentials headers for the MCP servers, from
 * scripts/adc-headers, and calls onChange to have the client take new ones.
 */
export class GoogleAuth {
  /** The headers the client was last given; read them in onChange. */
  headers: Record<string, string> = {};
  /** Why the last fetch failed, until one succeeds. */
  error: string | undefined;
  // When the headers in use were fetched.
  private appliedAt = 0;
  // Headers fetched but not given to the client yet, and when.
  private fetched: { headers: Record<string, string>; at: number } | undefined;
  // When each running call started, oldest first.
  private readonly calls: number[] = [];
  // Calls dropped from calls for running past maxCallMs, whose end hasn't come.
  private dropped = 0;
  // The renewal under way, so the poll, callEnded and prompts share one.
  private running: Promise<void> | undefined;
  private stopped = false;
  private timer: ReturnType<typeof setInterval> | undefined;
  // The helper's process ID while it runs.
  private helper: number | undefined;
  private reported: string | undefined;
  private readonly script: string;
  private readonly onChange: () => void | Promise<void>;
  private readonly onError: (message: string) => void;
  private readonly timings: Timings;

  // helper is the servers' headersHelper script; on Windows the .cmd file
  // beside it runs, as for Claude Code. onChange is called with new headers,
  // but not while a call is running unless the token in use is APPLY_BY_MS
  // old: the client may reconnect the servers to apply them, which ends the
  // call. onError is called when a fetch fails for a new reason.
  constructor(
    helper: string,
    onChange: () => void | Promise<void>,
    onError: (message: string) => void = () => {},
    timings: Partial<Timings> = {},
  ) {
    this.script = helper;
    this.onChange = onChange;
    this.onError = onError;
    this.timings = { ...TIMINGS, ...timings };
  }

  // Fetches the first headers and applies them through onChange, as a renewal
  // does, so the plugin can register its servers first and not hold up the
  // client while gcloud runs (gcloud can take 30 seconds to fail). Never
  // throws: on failure, headers stays empty and error says why.
  async start(): Promise<void> {
    await this.renewIfDue();
  }

  // Starts renewing the headers. Calling it again while it runs does nothing.
  startRenewing(): void {
    this.stopped = false;
    if (this.timer) return;
    this.timer = setInterval(() => void this.renewIfDue(), this.timings.pollMs);
    (this.timer as { unref?: () => void }).unref?.();
  }

  // Renews now if it is due, for the clients' prompt hooks: a machine that
  // was asleep would otherwise send a prompt with an expired token until the
  // next poll.
  async renewIfDue(): Promise<void> {
    if (this.isDue()) await this.renew();
  }

  // For the clients' later prompts: renews a token that is in use and stale,
  // or applies one held back. Without a token it does nothing, and the poll
  // retries: signed out, a prompt would otherwise wait for a helper run (up to
  // 30 seconds) every time.
  async renewInUse(): Promise<void> {
    if (!this.headers["Authorization"] && !this.fetched) return;
    await this.renewIfDue();
  }

  // Stops renewing; a fetch still running then applies nothing.
  stop(): void {
    this.stopped = true;
    // A helper still running would hold gcloud's lock after the client exits.
    killTree(this.helper);
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
  }

  callStarted(): void {
    this.calls.push(Date.now());
  }

  // Marks the newest running call as still active, for a call that is a
  // whole agent turn: only a turn quiet for maxCallMs counts as having missed
  // its end.
  callActive(): void {
    if (this.calls.length > 0) this.calls[this.calls.length - 1] = Date.now();
  }

  callEnded(): void {
    // Ends don't say which call ended. One for a dropped call (the oldest) must
    // not remove a younger call's entry; if the dropped one never ends, a
    // younger call is held back until it too is dropped, which is the safe way
    // round.
    if (this.dropped > 0) this.dropped--;
    else this.calls.shift();
    if (this.fetched) void this.renew();
  }

  private isDue(): boolean {
    return (
      this.fetched !== undefined ||
      !this.headers["Authorization"] ||
      Date.now() - this.appliedAt >= this.timings.refreshAfterMs
    );
  }

  // Whether running calls keep new headers back now.
  private callsHoldBack(): boolean {
    const cutoff = Date.now() - this.timings.maxCallMs;
    while (this.calls.length > 0 && this.calls[0] <= cutoff) {
      this.calls.shift();
      this.dropped++;
    }
    return (
      this.calls.length > 0 &&
      Boolean(this.headers["Authorization"]) &&
      Date.now() - this.appliedAt < this.timings.applyByMs
    );
  }

  private renew(): Promise<void> {
    // After stop(), a call that ends must not start the helper again.
    if (this.stopped) return Promise.resolve();
    this.running ??= this.renewOnce().finally(() => (this.running = undefined));
    return this.running;
  }

  private async renewOnce(): Promise<void> {
    if (!this.fetched || Date.now() - this.fetched.at >= this.timings.refreshAfterMs) {
      if (!(await this.fetch())) return;
    }
    if (this.stopped || this.callsHoldBack()) return;
    const fetched = this.fetched!;
    this.headers = fetched.headers;
    try {
      await withTimeout(Promise.resolve(this.onChange()), this.timings.applyTimeoutMs, "the client didn't take them in time");
    } catch (error) {
      // Kept as fetched, so the next poll applies them again.
      console.warn(`google-cloud: couldn't apply new credentials: ${errorMessage(error)}`);
      return;
    }
    this.appliedAt = fetched.at;
    if (this.fetched === fetched) this.fetched = undefined;
  }

  private async fetch(): Promise<boolean> {
    try {
      const headers = await runAdcHeaders(this.script, this.timings.scriptTimeoutMs, (pid) => (this.helper = pid));
      this.fetched = { headers, at: Date.now() };
      this.error = this.reported = undefined;
      return true;
    } catch (error) {
      // A fetch stop() cut short says nothing about the credentials.
      if (this.stopped) return false;
      this.error = errorMessage(error);
      if (this.error !== this.reported) {
        this.reported = this.error;
        this.onError(this.error);
      }
      return false;
    } finally {
      this.helper = undefined;
    }
  }
}
