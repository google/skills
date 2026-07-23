---
name: gboc-3p-app-log-config
description: >-
  Configures the Google-Built OpenTelemetry Collector (GBOC) to collect and
  parse logs from well-known third-party applications (Nginx, Apache, MySQL,
  MongoDB, Kafka, PostgreSQL, Cassandra, IIS, and more) on a VM, replicating the
  Ops Agent's parsing (regexes, timestamp and severity mapping, httpRequest
  structure) by referencing the upstream ops-agent source. Use when setting up
  GBOC log collection for a specific supported third-party app, when you need the
  exact Ops Agent regex or field mapping for an app, or to make GBOC log output
  match the Ops Agent format. Don't use for generic or custom (non-standard) log
  formats (use generate-gboc-log-config) or for metrics collection.
---

# Configure GBOC for Third-Party App Logs (Ops Agent parity)

## What this skill is for

The Ops Agent ships built-in log parsers for dozens of third-party apps. GBOC
(a stock OpenTelemetry Collector distribution) does **not** ship these parsers,
but you can reproduce their output by reading the Ops Agent source and
translating it into stock GBOC components (`filelog` receiver + `transform`
processor + `googlecloud` exporter).

This skill is **reference-driven**: rather than embedding every app's intricate
regex (they change and are easy to get subtly wrong), it points you to the
authoritative ops-agent source and gives you the rules to translate it faithfully.

**Relationship to other skills:**

-   Use [generate-gboc-log-config](../generate-gboc-log-config/SKILL.md) for the
    generic mechanics (choosing OS, reading the log file, editing
    `config.yaml`, restarting the service, verifying ingestion) and for custom /
    non-standard log formats. This skill focuses only on the app-specific
    parsing that must match the Ops Agent.

## Supported apps

Only apps that the Ops Agent defines a **logging** parser for are supported.
The full list, the receiver types each app exposes, and the exact GitHub
reference links are in
[references/ops-agent-references.md](references/ops-agent-references.md).

Quick check: if the app is not in that table (i.e. it has no logging processor
in the ops-agent `apps/` directory), treat the log as a custom format and use
[generate-gboc-log-config](../generate-gboc-log-config/SKILL.md) instead.

## Workflow

### 1. Identify the app and its receiver type

Ask which app (e.g. `nginx`) and which log stream (e.g. access vs. error). Map it
to the ops-agent app name and receiver type using the table in
[references/ops-agent-references.md](references/ops-agent-references.md)
(e.g. `nginx` → `nginx_access`, `nginx_error`).

### 2. Fetch the authoritative Ops Agent definition

Read two sources for that app:

1.  **`apps/<app>.go`** — defines the receiver types, the regex (often via a
    shared helper like `genericAccessLogParser`), the `TimeFormat`, field type
    casts, and the severity `ModifyFields` mapping.
2.  **The OTel golden** `logging-otel-receiver_<app>` (only some apps have one)
    — shows the exact `transform` statements and final field layout the Ops
    Agent produces for the OTel pipeline.

> [!TIP]
> `read_url_content` truncates long files. Fetch raw sources with `curl` and
> grep them instead:
> ```bash
> curl -sSL https://raw.githubusercontent.com/GoogleCloudPlatform/ops-agent/master/apps/nginx.go
> curl -sSL https://raw.githubusercontent.com/GoogleCloudPlatform/ops-agent/master/apps/common_logging_processors.go
> ```
> Access-log parsers (apache, nginx, jetty, tomcat, couchbase, iis) live in the
> shared `genericAccessLogParser` in `apps/common_logging_processors.go`.

### 3. Translate Ops Agent constructs into stock GBOC

The Ops Agent goldens use custom OTTL functions (`ExtractPatternsRubyRegex`,
`IsMatchRubyRegex`) that are **not** compiled into GBOC. Do not copy goldens
verbatim. Instead translate using the rules in
[references/ops-agent-to-gboc-mapping.md](references/ops-agent-to-gboc-mapping.md),
which covers regex syntax conversion, the `httpRequest` structure, timestamp and
severity mapping, `jsonPayload` vs. labels, and includes a full worked Nginx
example.

### 4. Merge into the VM's config and deploy

Hand off to [generate-gboc-log-config](../generate-gboc-log-config/SKILL.md) for
reading the existing `config.yaml`, backing it up, merging the new receiver /
processor / pipeline, restarting `otelcol-google`, and verifying with
`gcloud logging read`.

### 5. Verify parity

Confirm the emitted `LogEntry` matches the Ops Agent shape: correct `logName`
(e.g. `nginx_access`), populated `httpRequest` where applicable, `severity`
translated, and no leftover `-` placeholder fields in `jsonPayload`.

## Key gotchas (see the mapping reference for detail)

-   **Regex flavor**: Ops Agent regexes use Ruby `(?<name>...)`; RE2 (Go /
    OTTL / stanza `regex_parser`) needs `(?P<name>...)`.
-   **httpRequest**: build the `attributes["gcp.http_request"]` map — the
    `googlecloud` exporter maps it to `LogEntry.httpRequest`. Cast `status` to an
    integer; keep `responseSize` as a string.
-   **jsonPayload vs. labels**: the exporter turns the log record **body** (a
    map) into `jsonPayload`, and **attributes** into labels (except the special
    `gcp.*` keys). Put user-facing fields in the body.
-   **Placeholder values**: apache/nginx-style parsers omit fields equal to `-`.
-   **Component availability**: some operators (`csv`, `windowseventlog`) may not
    be compiled into a given GBOC build; fall back to `regex_parser`. Verify with
    the interactive-run trick in
    [generate-gboc-log-config](../generate-gboc-log-config/SKILL.md).
