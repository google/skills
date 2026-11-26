# Log sources for `logs_archive` mode

`trace_logs.py --mode logs_archive` reads exported log **files** or directories
(`--data-path <file-or-dir>`). How those exports are produced is up to the
operator or the agent; the scripts never call a cloud SDK, provider CLI, or
subshell themselves.

## Table of Contents

- [Passing exported logs to the script](#passing-exported-logs-to-the-script):
  Lines 19-41
- [Accepted file shapes (auto-detected, mixable in one
  directory)](#accepted-file-shapes-auto-detected-mixable-in-one-directory):
  Lines 43-73
- [Exporting GKE logs from Cloud
  Logging](#exporting-gke-logs-from-cloud-logging): Lines 75-111
- [What the agent should not do](#what-the-agent-should-not-do): Lines 113-121

## Passing exported logs to the script

To hand logs over without printing raw records into agent context, export them
to a local file first and point `--data-path` at the file or directory:

```bash
# Write each export to its own file in the per-run directory (never append
# multiple JSON arrays into one file), then pass the directory to --data-path.
# Shell state may not persist between commands: run this block as one command
# and use the printed literal absolute path (not "$WORK_DIR") in later ones.
WORK_DIR=$(mktemp -d /tmp/kueue-triage.XXXXXX)
echo "$WORK_DIR"
<read-only export command> > "$WORK_DIR/controller.json"
python3 scripts/trace_logs.py \
  --mode logs_archive \
  --data-path "$WORK_DIR" \
  --ledger-path "$WORK_DIR/ledger.json"
```

Export commands run by the caller must be strictly read-only and scoped to the
target cluster, the incident time window, `kueue-system`, Kubernetes Event logs,
and Admin Activity audit logs as described below and in
["Accessing your logs"](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs.md.txt).

## Accepted file shapes (auto-detected, mixable in one directory)

- **Kueue controller JSON lines (zap)**: produced by `k8s_container` logs
  (`projects/PROJECT_ID/logs/stdout` and `projects/PROJECT_ID/logs/stderr`) or
  container runtime files. `Initializing` and `Configuration loaded` lines
  carry the release and `apiVersion`.
- **Cloud Logging envelope** (`{timestamp, severity,
  jsonPayload|protoPayload|textPayload}`): produced by Cloud Logging JSON or
  JSONL exports (see
  ["Accessing your logs"](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs.md.txt)).
  `protoPayload` Admin Activity audit entries
  (`projects/PROJECT_ID/logs/cloudaudit.googleapis.com%2Factivity`) are
  normalised like `audit.k8s.io/v1`.
- **Kubernetes `Event` objects** (`v1` / `events.k8s.io/v1`): produced by
  `projects/PROJECT_ID/logs/events` (`k8s_pod`, `k8s_node`, `k8s_cluster`) or
  exported Event lists (`List` JSON or one object per line).
- **`audit.k8s.io/v1` `Event` objects (JSONL)**: produced by Kubernetes API
  server audit logs; normalised to
  `(verb, resource, subresource, namespace, name)`.
- **Collector envelope** (`{log|line|message, time|@timestamp,
  kubernetes|labels}`): produced by log collectors; the inner record is
  unwrapped recursively.
- **klog text** (`I0924 12:09:02.123 1 <file>:<line>] ...`): produced by older
  controllers or webhook sidecars (timestamp has no year).

Files are discovered by extension (`.log`, `.txt`, `.json`, `.jsonl`,
`.ndjson`), by whole-word `log`/`logs` in the file name, or under a `log/` or
`logs/` directory (excluding `.yaml`, `.yml`, dotfiles, and archives).
Directory walks read regular files only and skip symlinks. A pretty-printed
manifest that is not a log record yields nothing, so a support bundle directory
can be passed as-is.

## Exporting GKE logs from Cloud Logging

For how GKE routes container logs (`k8s_container`), Kubernetes Events
(`projects/PROJECT_ID/logs/events` on `k8s_pod`, `k8s_node`, and
`k8s_cluster`), control plane logs (`k8s_control_plane_component`), and Admin
Activity audit logs
(`projects/PROJECT_ID/logs/cloudaudit.googleapis.com%2Factivity`), follow
"Accessing your logs", "Understanding your logs", "Resource types", "System
logs", "Kubernetes Event logs", "Application logs", and "Control plane component
logs" in
[View GKE logs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs.md.txt).

Verbose per-transition lines from `kueue-controller-manager` may not be present
at default log verbosity; the scripts report the absence of such lines as
`"not determinable"`, not as evidence.

To export a scoped GKE incident window (`<start>` to `<end>` in RFC3339 UTC for
`<cluster>` in `<project>`) into a local JSON file for `trace_logs.py`, query
Cloud Logging with a filter scoped to:

- `resource.labels.cluster_name="<cluster>"` and RFC3339 UTC bounds
  `timestamp>="<start>"` and `timestamp<="<end>"`
- `resource.labels.namespace_name="kueue-system"` (Kueue controller container
  logs), `logName:"/logs/events"` (Kubernetes Event logs), or
  `logName:"cloudaudit.googleapis.com%2Factivity"` (Admin Activity audit logs)

Save each filter export to its own file in the per-run directory (for example
`"$WORK_DIR/controller.json"`, `"$WORK_DIR/events.json"`,
`"$WORK_DIR/audit.json"` — never append multiple JSON array exports into one
file) and pass the directory via `--data-path "$WORK_DIR"`; `trace_logs.py`
reorders JSON array exports chronologically by `timestamp`. If `trace_logs.py`
reports `skipped_inputs` (symlinks or non-regular files) or
`unreadable_inputs` (unparseable or concatenated JSON exports), do not report
those logs as absent from the cluster: tell the user which files were not read,
re-export each filter to its own regular file (or verify symlink targets) and
rerun, or record the gap under `#### Open Questions` if the files cannot be
recovered.

## What the agent should not do

- Do not print or paste a raw export into the conversation; pass the file to
  the script.
- Do not widen the export to the whole project or cluster — scope to
  `resource.labels.cluster_name`, the incident time window, `kueue-system`,
  Kubernetes Event logs, and the Admin Activity audit log.
- Do not install SDKs to fetch logs; pass the exported files to
  `trace_logs.py`.
