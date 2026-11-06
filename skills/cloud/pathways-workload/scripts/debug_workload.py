#!/usr/bin/env python3
r"""CLI helper to filter and analyze logs for Pathways on Cloud GKE workloads.

It constructs optimized queries for GCP Cloud Logging and provides commands
to read logs from GKE containers and nodes.

This script is shared with EXTERNAL users.
"""

from collections.abc import Callable, Sequence
import dataclasses
import datetime
import json
import re
import shlex
import subprocess
from typing import Any
import urllib.parse
from absl import app
from absl import flags

_PROJECT = flags.DEFINE_string(
    "project",
    None,
    "GCP project ID. Please verify with the user if this is correct.",
    required=True,
)
_CLUSTER_NAME = flags.DEFINE_string(
    "cluster_name", None, "Target GKE cluster name", required=True
)
_LOCATION = flags.DEFINE_string(
    "location", None, "Cluster location (zone or region)", required=True
)
_JOBSET_NAME = flags.DEFINE_string(
    "jobset_name",
    None,
    "k8s JobSet name. Shorthand for --workload=jobset:<name>.",
)
_LWS_NAME = flags.DEFINE_string(
    "lws_name",
    None,
    "LeaderWorkerSet name (e.g. Pathways inference). Shorthand for"
    " --workload=lws:<name>.",
)
_JOB_NAME = flags.DEFINE_string(
    "job_name",
    None,
    "Plain k8s Job name (not part of a JobSet). Shorthand for"
    " --workload=job:<name>.",
)
_POD_PREFIX = flags.DEFINE_string(
    "pod_prefix",
    None,
    "Pod name prefix, for workloads not created by a JobSet, LeaderWorkerSet or"
    " Job (e.g. bare pods). Shorthand for --workload=pod:<prefix>.",
)
_WORKLOADS = flags.DEFINE_multi_string(
    "workload",
    [],
    "Workload to debug as <kind>:<name>, where <kind> is one of jobset, lws,"
    " job or pod (pod name prefix). Repeat the flag to query several workloads"
    " together, e.g. a JobSet plus a JAX client or proxy that runs in its own"
    " Job: --workload=jobset:my-pw --workload=job:my-client. Combined with"
    " --jobset_name, --lws_name, --job_name and --pod_prefix.",
)
_NAMESPACE = flags.DEFINE_string("namespace", "default", "k8s namespace")
_SIDECAR_CONTAINER = flags.DEFINE_string(
    "sidecar_container",
    "colocated-python-sidecar",
    "Container name of the colocated Python sidecar. Workloads may use a"
    " custom name: it is the container running next to `pathways-worker` in"
    " the TPU worker pods (see the JobSet YAML or the pods' container names).",
)

_START_TIME = flags.DEFINE_string(
    "start_time",
    None,
    "Start timestamp (ISO 8601 / RFC 3339, e.g. 2026-10-22T00:00:00Z)."
    " Timestamps without a timezone are interpreted as UTC.",
)
_END_TIME = flags.DEFINE_string(
    "end_time",
    None,
    "End timestamp (ISO 8601 / RFC 3339, e.g. 2026-10-22T02:00:00Z)."
    " Timestamps without a timezone are interpreted as UTC.",
)
_DURATION = flags.DEFINE_string(
    "duration",
    None,
    "Length of the time window, e.g. 30s, 30m, 2h, 1d, or combinations such"
    " as 1h30m. With --start_time, the window is [start, start + duration];"
    " with --end_time, it is [end - duration, end]; on its own, it is"
    " [now - duration, now]. Cannot be combined with both --start_time and"
    " --end_time.",
)

flags.register_multi_flags_validator(
    ["start_time", "end_time", "duration"],
    lambda f: not (f["start_time"] and f["end_time"] and f["duration"]),
    message=(
        "At most two of --start_time, --end_time and --duration may be"
        " specified."
    ),
)

_ACTION = flags.DEFINE_enum(
    "action",
    "summary",
    [
        "summary",
        "errors",
        "user-workload",
        "proxy",
        "pathways-rm",
        "workers",
        "colocated-python-sidecar",
        "pod-events",
        "node-ooms",
        "interruptions",
        "neighbors",
        "elastic",
        "preflight",
    ],
    "The debugging target or action to perform. Run `preflight` first: it"
    " checks log access and that the workload logged in the time window (it"
    " always runs, with or without --execute).",
)

_EXECUTE = flags.DEFINE_boolean(
    "execute",
    False,
    "If True, will attempt to run the constructed gcloud command locally.",
)

_LIMIT = flags.DEFINE_integer(
    "limit", 100, "Maximum number of log entries to fetch if executing."
)

_ORDER = flags.DEFINE_enum(
    "order",
    "asc",
    ["asc", "desc"],
    "Sort order of returned entries. 'asc' (default) returns the earliest"
    " entries in the time window first, which is what you want when chasing"
    " the first error. Use 'desc' to find the latest progress (e.g. the last"
    " completed step).",
)

_NODE_NAMES = flags.DEFINE_list(
    "node_names",
    [],
    "GKE node names (e.g. gke-tpu-1a2b3c4d-xyz1) the workload ran on, used by"
    " --action=node-ooms and --action=neighbors. If omitted with --execute,"
    " they are discovered from the pods' 'Scheduled' events.",
)

_EXTRA_TERMS = flags.DEFINE_multi_string(
    "extra_terms",
    [],
    "Additional plain-text strings to match, appended to the built-in list of"
    " progress/error strings of the action (OR-ed together). Repeat the flag"
    " for multiple strings, e.g. --extra_terms='train_step'"
    " --extra_terms='loss is nan'. Use it for workload-specific log lines"
    " (e.g. non-MaxText step markers). Only supported by actions with a"
    " built-in list: errors, user-workload, proxy, pathways-rm, workers.",
)

_MIN_SEVERITY = flags.DEFINE_enum(
    "min_severity",
    None,
    ["DEFAULT", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL"],
    "Also match every log line at or above this severity (e.g. WARNING or"
    " ERROR), OR-ed with the built-in list and --extra_terms. Use it to catch"
    " problems the built-in list does not know about, e.g. on the workers or"
    " the RM. DEFAULT matches every line, for errors that are logged at INFO."
    " Note: non-first lines of multiline logs may show up as ERROR."
    " Only supported by the same actions as --extra_terms.",
)

_FIRST_PER_POD = flags.DEFINE_integer(
    "first_per_pod",
    0,
    "If > 0 (with --execute), keep only the first N matching entries of each"
    " pod/container (in --order) plus its last matching entry, so a few chatty"
    " pods or a cascade across hundreds of pods do not fill --limit, while a"
    " fatal error at the end of a pod's log is still shown. Fetches up to"
    " --fetch_limit entries and prints at most --limit of the kept ones.",
)

_FETCH_LIMIT = flags.DEFINE_integer(
    "fetch_limit",
    1000,
    "Maximum entries fetched from Cloud Logging when --first_per_pod is set."
    " Larger values cover more pods but are slower; narrow the time window"
    " first.",
)

# Node names per query for node-scoped actions (node-ooms, neighbors); larger
# node sets are queried in batches to stay under Cloud Logging's filter length
# limit.
_NODE_BATCH_SIZE = 200

# How far before the query window to look for the pods' "Scheduled" events
# when discovering the workload's nodes (pods are often scheduled well before
# the failure).
_NODE_DISCOVERY_LOOKBACK = datetime.timedelta(hours=24)

_BASE_CONSOLE_URL = "https://console.cloud.google.com/logs/query"

# Workload kinds accepted by --workload, mapped to the Cloud Logging pod label
# that identifies their pods. Cloud Logging stores pod labels with "." replaced
# by "_". `pod` has no label; it matches pod names by prefix.
_KIND_LABELS = {
    "jobset": "k8s-pod/jobset_sigs_k8s_io/jobset-name",
    "lws": "k8s-pod/leaderworkerset_sigs_k8s_io/name",
    "job": "k8s-pod/batch_kubernetes_io/job-name",
    "pod": None,
}


@dataclasses.dataclass(frozen=True)
class Target:
  """One workload object to debug.

  Attributes:
    kind: One of `_KIND_LABELS` (jobset, lws, job or pod).
    name: The object name, or a pod name prefix for kind `pod`.
  """

  kind: str
  name: str


@dataclasses.dataclass(frozen=True)
class Workload:
  """Identifies the GKE workload being debugged.

  Attributes:
    project: GCP project ID that owns the GKE cluster.
    cluster: Name of the GKE cluster running the workload.
    location: Zone or region of the GKE cluster.
    targets: The JobSets, LeaderWorkerSets, Jobs or pod name prefixes that make
      up the workload. Logs of all of them are queried together.
    namespace: k8s namespace the workload runs in.
    node_names: GKE node (VM instance) names the workload's pods ran on. Used to
      scope node-level logs that carry no cluster label (serial console).
    sidecar_container: Container name of the colocated Python sidecar.
  """

  project: str
  cluster: str
  location: str
  targets: tuple[Target, ...]
  namespace: str
  node_names: tuple[str, ...] = ()
  sidecar_container: str = "colocated-python-sidecar"

  @property
  def names(self) -> tuple[str, ...]:
    """Names of the targets; pods of every kind are named with this prefix."""
    return tuple(t.name for t in self.targets)


def parse_targets(
    workloads: Sequence[str],
    jobset: str | None = None,
    lws: str | None = None,
    job: str | None = None,
    pod_prefix: str | None = None,
) -> tuple[Target, ...]:
  """Builds the workload targets from --workload and the shorthand flags.

  Args:
    workloads: Values of --workload, each `<kind>:<name>`.
    jobset: Value of --jobset_name.
    lws: Value of --lws_name.
    job: Value of --job_name.
    pod_prefix: Value of --pod_prefix.

  Returns:
    The de-duplicated targets, in the order given.

  Raises:
    ValueError: If a --workload value is malformed or no target is given.
  """
  targets = []
  for value in workloads:
    kind, sep, name = value.partition(":")
    kind = kind.strip().lower()
    name = name.strip()
    if not sep or kind not in _KIND_LABELS or not name:
      raise ValueError(
          f"Invalid --workload {value!r}; expected <kind>:<name> with kind one"
          f" of {', '.join(_KIND_LABELS)}."
      )
    targets.append(Target(kind, name))
  for kind, name in (
      ("jobset", jobset),
      ("lws", lws),
      ("job", job),
      ("pod", pod_prefix),
  ):
    if name:
      targets.append(Target(kind, name))
  if not targets:
    raise ValueError(
        "Specify the workload with --jobset_name, --lws_name, --job_name,"
        " --pod_prefix or --workload."
    )
  return tuple(dict.fromkeys(targets))


# ---------------------------------------------------------------------------
# Query building helpers.
# ---------------------------------------------------------------------------


_DURATION_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)([smhdw])")


def parse_duration(value: str) -> datetime.timedelta:
  """Parses a duration such as `30m`, `2h` or `1h30m` into a timedelta.

  Args:
    value: The duration string. A leading `-` or `+` is ignored.

  Returns:
    The parsed (positive) duration.

  Raises:
    ValueError: If `value` is not a valid, non-zero duration.
  """
  text = value.strip().lower().lstrip("+-")
  if not text or _DURATION_RE.sub("", text):
    raise ValueError(
        f"Invalid duration {value!r}; expected e.g. 30s, 30m, 2h, 1d, 1h30m."
    )
  delta = datetime.timedelta()
  for amount, unit in _DURATION_RE.findall(text):
    delta += datetime.timedelta(**{_DURATION_UNITS[unit]: float(amount)})
  if not delta:
    raise ValueError(f"Duration {value!r} must be greater than zero.")
  return delta


def parse_timestamp(value: str) -> datetime.datetime:
  """Parses an ISO 8601 timestamp, assuming UTC if no timezone is given.

  Args:
    value: The timestamp string, e.g. `2026-10-22T00:00:00Z`.

  Returns:
    A timezone-aware datetime.

  Raises:
    ValueError: If `value` is not a valid ISO 8601 timestamp.
  """
  text = value.strip()
  # `fromisoformat` only accepts a trailing "Z" from Python 3.11 onwards.
  if text.endswith(("Z", "z")):
    text = text[:-1] + "+00:00"
  try:
    ts = datetime.datetime.fromisoformat(text)
  except ValueError as e:
    raise ValueError(
        f"Invalid timestamp {value!r}; expected ISO 8601, e.g."
        " 2026-10-22T00:00:00Z."
    ) from e
  if ts.tzinfo is None:
    ts = ts.replace(tzinfo=datetime.timezone.utc)
  return ts


def _to_rfc3339(ts: datetime.datetime) -> str:
  """Formats `ts` as an RFC 3339 UTC timestamp accepted by Cloud Logging."""
  return (
      ts.astimezone(datetime.timezone.utc)
      .isoformat(timespec="seconds")
      .replace("+00:00", "Z")
  )


def compute_time_range(
    start_time: str | None,
    end_time: str | None,
    duration: str | None,
    now: datetime.datetime | None = None,
) -> tuple[datetime.datetime | None, datetime.datetime | None]:
  """Resolves the start/end of the query window from the given parameters.

  Args:
    start_time: Optional ISO 8601 start timestamp.
    end_time: Optional ISO 8601 end timestamp.
    duration: Optional window length, e.g. `2h`.
    now: The current time; defaults to `datetime.now(UTC)`.

  Returns:
    A `(start, end)` tuple; either element may be None (unbounded).

  Raises:
    ValueError: If all three parameters are given, a value fails to parse, or
      the resulting start is after the end.
  """
  if start_time and end_time and duration:
    raise ValueError(
        "At most two of start_time, end_time and duration may be specified."
    )
  start = parse_timestamp(start_time) if start_time else None
  end = parse_timestamp(end_time) if end_time else None
  if duration:
    delta = parse_duration(duration)
    if start:
      end = start + delta
    elif end:
      start = end - delta
    else:
      end = now or datetime.datetime.now(datetime.timezone.utc)
      start = end - delta
  if start and end and start > end:
    raise ValueError(
        f"Start time {_to_rfc3339(start)} is after end time {_to_rfc3339(end)}."
    )
  return start, end


def get_time_filter() -> list[str]:
  """Constructs the time filter part of the query.

  The window is derived from --start_time, --end_time and --duration and is
  always emitted as RFC 3339 timestamps, as required by Cloud Logging.

  Returns:
    A list of timestamp filter clauses (may be empty).
  """
  try:
    start, end = compute_time_range(
        _START_TIME.value, _END_TIME.value, _DURATION.value
    )
  except ValueError as e:
    raise app.UsageError(str(e)) from e
  filters = []
  if start:
    filters.append(f'timestamp >= "{_to_rfc3339(start)}"')
  if end:
    filters.append(f'timestamp <= "{_to_rfc3339(end)}"')
  return filters


def _quote(term: str) -> str:
  """Quotes a plain-text term as a Cloud Logging string literal."""
  return '"' + term.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _any_of(*terms: str) -> list[str]:
  """Returns query lines matching any of the given (already quoted) terms."""
  first, *rest = terms
  return ["(", f"  {first}"] + [f"  OR {term}" for term in rest] + [")"]


def _cluster_filters(
    w: Workload, resource_type: str | None = None
) -> list[str]:
  """Returns filters scoping logs to the workload's GKE cluster."""
  filters = [f'resource.type="{resource_type}"'] if resource_type else []
  filters += [
      f'resource.labels.project_id="{w.project}"',
      f'resource.labels.cluster_name="{w.cluster}"',
      f'resource.labels.location="{w.location}"',
  ]
  return filters


def _target_filter(t: Target) -> str:
  """Returns the clause matching the container logs of one target's pods."""
  label = _KIND_LABELS[t.kind]
  if label is None:
    return f"resource.labels.pod_name:{_quote(t.name)}"
  return f'labels."{label}"={_quote(t.name)}'


def _pod_name_filter(w: Workload) -> str:
  """Matches pods of any target by name prefix (for logs without pod labels).

  Kubernetes events and other `k8s_pod` logs carry no pod labels, but the pods
  of a JobSet, LeaderWorkerSet or Job are named after it.

  Args:
    w: The workload.

  Returns:
    A single filter clause.
  """
  clauses = [f"resource.labels.pod_name:{_quote(n)}" for n in w.names]
  return clauses[0] if len(clauses) == 1 else f"({' OR '.join(clauses)})"


def _jobset_container_filters(w: Workload) -> list[str]:
  """Returns filters scoping logs to containers belonging to the workload."""
  clauses = [_target_filter(t) for t in w.targets]
  target = clauses[0] if len(clauses) == 1 else f"({' OR '.join(clauses)})"
  return _cluster_filters(w, "k8s_container") + [
      f'resource.labels.namespace_name="{w.namespace}"',
      target,
  ]


def _flatten(query: str) -> str:
  """Flattens a multi-line query onto a single line for shell usage."""
  return query.replace("\n", " ").strip()


# ---------------------------------------------------------------------------
# Per-action query builders.
# ---------------------------------------------------------------------------


def summary_query(w: Workload) -> list[str]:
  """Gathers general events and lifecycle details of the workload.

  Matches Kubernetes events whose object name contains a target name, and the
  JobSet / LeaderWorkerSet controller logs that mention it.

  Args:
    w: The workload.

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  objects = " OR ".join(_quote(n) for n in w.names)
  return _cluster_filters(w) + [
      "(",
      (
          '  (resource.type="k8s_cluster" AND'
          f" jsonPayload.involvedObject.name:({objects}))"
      ),
      "  OR",
      (
          '  (resource.type="k8s_container" AND'
          ' resource.labels.namespace_name=("jobset-system" OR "lws-system")'
          f" AND textPayload:({objects}))"
      ),
      ")",
  ]


_CRASH_TERMS = (
    '"SIGSEGV"',
    '"SIGABRT"',
    '"SIGBUS"',
    '"SIGILL"',
    '"SIGFPE"',
    '"Check failed"',
    '"RET_CHECK failure"',
    '"Raising signal"',
    '"Fatal Python error"',
    '"Traceback (most recent call last)"',
    '"terminate called"',
    '"OOMKilled"',
    '"Killed process"',
    '"Memory cgroup out of memory"',
    # Fatal errors that are not crashes and may be logged at INFO or WARNING.
    '"Check failure stack trace"',
    '"Unknown command line flag"',
    '"Address already in use"',
    '"incarnation ID mismatch"',
    '"PermissionDenied"',
    '"403 Forbidden"',
)


def errors_query(w: Workload) -> list[str]:
  """Crash-signature sweep across every container of the workload.

  Container-specific actions only match known progress/error strings, so they
  can miss crashes (e.g. a segfault in pathways-rm). Run this first, ordered
  ascending, and chase the earliest hit. Matches `_CRASH_TERMS`.

  Args:
    w: The workload.

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  return _jobset_container_filters(w)


def user_workload_query(w: Workload) -> list[str]:
  """Filters user workload container logs; matches `_USER_WORKLOAD_TERMS`."""
  # Omit pathways infrastructure containers to find custom named main user
  # containers
  return _jobset_container_filters(w) + [
      'resource.labels.container_name!="pathways-rm"',
      'resource.labels.container_name!="pathways-proxy"',
      'resource.labels.container_name!="pathways-worker"',
      f'resource.labels.container_name!="{w.sidecar_container}"',
  ]


# Progress and error strings of the user workload (JAX) container. Some are
# framework specific (e.g. "completed step" is logged by MaxText); pass
# --extra_terms for other frameworks.
_USER_WORKLOAD_TERMS = (
    '"completed step"',
    '"XPK Start"',
    '"XPK End"',
    '"started goodput"',
    '"Final goodput"',
    '"Restoring checkpoint"',
    '"[process=0] [sync] Finished load"',
    '"Shutting down cumulative goodput process"',
    '"commit_success"',
    '"Fatal Python error:"',
    '"Dict key mismatch"',
    '"Error opening \\"zarr\\" driver"',
    "\"CRITICAL - Timeout from watchdog 'step-timebomb'\"",
    '"RemoteIterator"',
    '"jax.errors.JaxRuntimeError"',
    '"Unable to initialize backend"',
    '"Connecting to IFRT proxy server"',
    '"RESOURCE_EXHAUSTED"',
    *_CRASH_TERMS,
)


def proxy_query(w: Workload) -> list[str]:
  """Queries proxy server logs; matches `_PROXY_TERMS`."""
  return _jobset_container_filters(w) + [
      'resource.labels.container_name="pathways-proxy"'
  ]


# Startup, RM connectivity and error strings of the proxy server.
_PROXY_TERMS = (
    '"IFRT proxy server started"',
    '"IFRT proxy server was terminated"',
    '"Starting new IFRT session"',
    # Repeated "Connection refused" to the RM port (29001) or "not yet
    # heard from" means the resource manager is down or crash-looping.
    '"Connection refused"',
    '"not yet heard from"',
    '"Build label"',
    # Host-to-device transfers from the proxy to the workers are stalled.
    '"Still waiting to acquire semaphore"',
    '"GOAWAY"',
    *_CRASH_TERMS,
)


def pathways_rm_query(w: Workload) -> list[str]:
  """Queries Pathways RM logs; matches `_PATHWAYS_RM_TERMS`."""
  return _jobset_container_filters(w) + [
      'resource.labels.container_name="pathways-rm"'
  ]


# Slice placement, availability, and allocation transitions in Pathways RM.
_PATHWAYS_RM_TERMS = (
    # "Build label" is logged once per process start, so repeated hits
    # mean the RM container is restarting (crash loop).
    '"Build label"',
    '"Pathways Server serving on"',
    '"now ready"',
    '"slice ready"',
    '"New slice available"',
    '"Sufficient slices active"',
    '"Setting new slice event"',
    '"remaining assignable"',
    '"reason: \\"Job cancelled due to"',
    '"expected topology"',
    '"Newly added slice topology"',
    *_CRASH_TERMS,
)


def workers_query(w: Workload) -> list[str]:
  """Queries leader worker logs (`completion-index=0`) to isolate early failures.

  Matches `_WORKERS_TERMS`. The leader filter only applies when every target is
  a JobSet or Job; LeaderWorkerSet and bare-pod workloads get all workers.

  Args:
    w: The workload.

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  filters = _jobset_container_filters(w) + [
      'resource.labels.container_name="pathways-worker"',
  ]
  if all(t.kind in ("jobset", "job") for t in w.targets):
    # Target the leader pods to reduce logging noise significantly.
    # Cloud Logging stores pod labels with "." replaced by "_".
    filters.append(
        'labels."k8s-pod/batch_kubernetes_io/job-completion-index"="0"'
    )
  return filters


# Hang and error strings of the Pathways workers.
_WORKERS_TERMS = (
    '"The host that have no TPU program running:"',
    '"Megascale hang detected"',
    '"Megascale detects a hang"',
    '"HANG_DETECTED"',
    '"FAILED_PRECONDITION"',
    '"jax.errors.JaxRuntimeError"',
    # Transfers from the proxy did not arrive (see the proxy's
    # "Still waiting to acquire semaphore").
    '"Recv completion error"',
    *_CRASH_TERMS,
)


def colocated_python_sidecar_query(w: Workload) -> list[str]:
  """Queries colocated Python sidecar logs (container `w.sidecar_container`)."""
  return _jobset_container_filters(w) + [
      f'resource.labels.container_name="{w.sidecar_container}"',
  ]


def pod_events_query(w: Workload) -> list[str]:
  """Kubernetes events for the workload's pods (scheduling, kills, OOMs, ...).

  Kubernetes only keeps events for about an hour, so `kubectl get events` is
  empty for past incidents; Cloud Logging keeps them.

  Args:
    w: The workload.

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  return _cluster_filters(w, "k8s_pod") + [
      'log_id("events")',
      f'resource.labels.namespace_name="{w.namespace}"',
      _pod_name_filter(w),
      # Drop routine lifecycle noise; keep Killing, BackOff, OOMKilling,
      # Evicted, FailedScheduling, Preempted, Unhealthy, FailedMount, ...
      (
          'NOT jsonPayload.reason=("Pulling" OR "Pulled" OR "Created" OR'
          ' "Started" OR "Scheduled")'
      ),
  ]


def node_ooms_query(w: Workload) -> list[str]:
  """Out-of-memory kills on the cluster's nodes (head pod and TPU hosts).

  Head-pod OOMs (JAX client, proxy, RM) often never reach container logs. They
  show up as node-problem-detector events (OOMKilling/SystemOOM), kernel
  "Memory cgroup out of memory" lines, and serial-console output.

  Serial-console logs live on `gce_instance`, which has no cluster label, and
  TPU node VMs are named gke-tpu-<hash>, so they are scoped to the workload's
  nodes (`w.node_names`, see `discover_workload_nodes`). Without node names they
  fall back to the cluster's zone, which can include unrelated VMs.

  Args:
    w: The workload.

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  if w.node_names:
    names = " OR ".join(f'"{n}"' for n in w.node_names)
    serial_scope = (
        f'    labels."compute.googleapis.com/resource_name"=({names})'
    )
  else:
    serial_scope = f'    resource.labels.zone:"{w.location}"'
  return [
      "(",
      "  (",
      *(f"    {f}" for f in _cluster_filters(w, "k8s_node")),
      "    (",
      (
          '      (log_id("events") AND'
          ' jsonPayload.reason:("OOMKilling" OR "SystemOOM"))'
      ),
      '      OR "Memory cgroup out of memory"',
      '      OR "Out of memory"',
      '      OR "oom_reaper"',
      '      OR "oom-kill"',
      "    )",
      "  )",
      "  OR",
      "  (",
      '    resource.type="gce_instance"',
      f'    resource.labels.project_id="{w.project}"',
      serial_scope,
      '    log_id("serialconsole.googleapis.com/serial_port_1_output")',
      '    "Memory cgroup out of memory"',
      "  )",
      ")",
  ]


def interruptions_query(w: Workload) -> list[str]:
  """Node pool / node / VM interruptions: preemption, maintenance, host errors."""
  return [
      "(",
      "  (",
      *(f"    {f}" for f in _cluster_filters(w, "gke_nodepool")),
      "  )",
      "  OR",
      "  (",
      *(f"    {f}" for f in _cluster_filters(w, "k8s_node")),
      '    log_id("events")',
      (
          '    jsonPayload.reason:("NodeNotReady" OR "Rebooted" OR'
          ' "NodeShutdown" OR "TerminationEvent" OR "PreemptionEvent" OR'
          ' "MaintenanceEvent")'
      ),
      "  )",
      "  OR",
      "  (",
      '    resource.type="gce_instance"',
      f'    resource.labels.project_id="{w.project}"',
      f'    resource.labels.zone:"{w.location}"',
      '    log_id("cloudaudit.googleapis.com/system_event")',
      (
          '    protoPayload.methodName:("compute.instances.preempted"'
          ' OR "compute.instances.hostError"'
          ' OR "compute.instances.automaticRestart"'
          ' OR "compute.instances.terminateOnHostMaintenance")'
      ),
      "  )",
      ")",
  ]


def neighbors_query(w: Workload) -> list[str]:
  """Container logs from every pod on the workload's nodes, in any namespace.

  Shows other workloads that shared the nodes (e.g. another job's resource
  manager on the same host and port) and the actual container names of the
  workload's own pods (e.g. a custom-named colocated Python sidecar). GKE
  container logs carry the node name in `compute.googleapis.com/resource_name`.

  Args:
    w: The workload. `w.node_names` must be set (see `discover_workload_nodes`).

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  names = " OR ".join(_quote(n) for n in w.node_names)
  return _cluster_filters(w, "k8s_container") + [
      f'labels."compute.googleapis.com/resource_name"=({names})',
  ]


def elastic_query(w: Workload) -> list[str]:
  """Elastic recovery timeline from the user workload and the RM.

  Matches `_ELASTIC_TERMS` in every container except the workers and the
  colocated Python sidecar (i.e. the JAX client, pathways-rm and the proxy).

  Args:
    w: The workload.

  Returns:
    The Cloud Logging filter clauses, one per line.
  """
  return _jobset_container_filters(w) + [
      'resource.labels.container_name!="pathways-worker"',
      f'resource.labels.container_name!="{w.sidecar_container}"',
  ]


# Slice loss/return, recovery attempts, and snapshot/checkpoint restore steps
# logged by pathways-rm and the elastic training loop (pathwaysutils, MaxText).
_ELASTIC_TERMS = (
    '"Slices Now Ready"',
    '"placed -> unplaced"',
    '"Unassigning"',
    '"Elastic attempt"',
    '"New slices found"',
    '"in-memory snapshot"',
    '"Falling back to persistent checkpoint"',
    '"Restoring"',
    '"Resuming"',
    '"commit_success"',
    '"completed step"',
    # Include the exception that ended a recovery attempt.
    *_CRASH_TERMS,
)


@dataclasses.dataclass(frozen=True)
class LogAction:
  """A Cloud Logging based debugging action.

  Attributes:
    title: Human-readable description printed as the action header.
    build_query: Returns the Cloud Logging filter clauses (one per line) for the
      given workload, excluding time filters and match terms.
    terms: Built-in (already quoted) strings, at least one of which a log line
      must contain. Empty if the action does not filter on message content; such
      actions do not accept --extra_terms.
    needs_nodes: Whether the query is scoped to the workload's nodes, which are
      discovered from the pods' "Scheduled" events if not given.
  """

  title: str
  build_query: Callable[[Workload], list[str]]
  terms: tuple[str, ...] = ()
  needs_nodes: bool = False


_LOG_ACTIONS: dict[str, LogAction] = {
    "summary": LogAction(
        "summary (Workload events & controller manager logs)", summary_query
    ),
    "errors": LogAction(
        "errors (Crash and fatal-error sweep across all workload containers)",
        errors_query,
        _CRASH_TERMS,
    ),
    "user-workload": LogAction(
        "user-workload (User container steps & error filtering)",
        user_workload_query,
        _USER_WORKLOAD_TERMS,
    ),
    "proxy": LogAction("proxy (Proxy server logs)", proxy_query, _PROXY_TERMS),
    "pathways-rm": LogAction(
        "pathways-rm (Resource Manager slice state transitions)",
        pathways_rm_query,
        _PATHWAYS_RM_TERMS,
    ),
    "workers": LogAction(
        "workers (Leader worker logs filtering)", workers_query, _WORKERS_TERMS
    ),
    "colocated-python-sidecar": LogAction(
        "colocated-python-sidecar (Colocated Python sidecar logs)",
        colocated_python_sidecar_query,
    ),
    "pod-events": LogAction(
        "pod-events (Kubernetes events for the workload's pods)",
        pod_events_query,
    ),
    "node-ooms": LogAction(
        "node-ooms (Node-level OOM validation)",
        node_ooms_query,
        needs_nodes=True,
    ),
    "interruptions": LogAction(
        "interruptions (Node pool / node / VM preemption, maintenance, host"
        " errors)",
        interruptions_query,
    ),
    "neighbors": LogAction(
        "neighbors (Pods and containers that logged on the workload's nodes)",
        neighbors_query,
        needs_nodes=True,
    ),
    "elastic": LogAction(
        "elastic (Slice loss, recovery and restore timeline)",
        elastic_query,
        _ELASTIC_TERMS,
    ),
}


# ---------------------------------------------------------------------------
# Output and execution.
# ---------------------------------------------------------------------------


def _run_command(cmd: list[str], tool_name: str) -> str | None:
  """Runs `cmd`, returning its stdout, or None (after reporting) on failure."""
  try:
    return subprocess.run(
        cmd, capture_output=True, text=True, check=True
    ).stdout
  except subprocess.CalledProcessError as e:
    print(f"Error executing {tool_name}: {e.stderr}")
    return None


def print_console_url(query: str, project: str) -> None:
  """Prints a clickable Cloud Console URL."""
  encoded_query = urllib.parse.quote(query.strip(), safe="")
  url = f"{_BASE_CONSOLE_URL};query={encoded_query};project={project}"
  print("--- Clickable Cloud Logging Link ---")
  print(url)
  print("------------------------------------\n")


_VALUE_FORMAT = (
    "value(timestamp,resource.labels.pod_name,resource.labels.container_name,"
    "severity,jsonPayload.reason,protoPayload.methodName,textPayload,"
    "jsonPayload.message)"
)


def print_gcloud_cmd(query: str, project: str) -> None:
  """Prints the equivalent gcloud logging read command."""
  cmd = (
      f"gcloud logging read {shlex.quote(_flatten(query))} "
      f"--project={shlex.quote(project)} "
      f"--limit={_LIMIT.value} "
      f"--order={_ORDER.value} "
      f"--format={shlex.quote(_VALUE_FORMAT)}"
  )
  print("\n--- Equivalent gcloud command ---")
  print(cmd)
  print("----------------------------------\n")


def _format_entry(log: dict[str, object]) -> str:
  """Formats one log entry compactly: time, pod/container, severity, message."""
  resource = log.get("resource") or {}
  labels = resource.get("labels", {}) if isinstance(resource, dict) else {}
  where = "/".join(
      str(labels[k]) for k in ("pod_name", "container_name") if labels.get(k)
  ) or str(labels.get("node_name") or resource.get("type", ""))
  json_payload = log.get("jsonPayload") or {}
  proto_payload = log.get("protoPayload") or {}
  if log.get("textPayload"):
    message = log["textPayload"]
  elif isinstance(json_payload, dict) and (
      json_payload.get("message") or json_payload.get("reason")
  ):
    reason = json_payload.get("reason")
    message = (f"[{reason}] " if reason else "") + str(
        json_payload.get("message", "")
    )
  elif isinstance(proto_payload, dict) and proto_payload.get("methodName"):
    message = (
        f"{proto_payload['methodName']} {proto_payload.get('resourceName', '')}"
    )
  else:
    message = json.dumps(json_payload or proto_payload, indent=2)
  timestamp = log.get("timestamp", "UNKNOWN_TIME")
  severity = log.get("severity", "DEFAULT")
  return f"[{timestamp}] [{severity}] [{where}] {message}"


def fetch_logs(
    query: str, project: str, limit: int
) -> list[dict[str, Any]] | None:
  """Runs `gcloud logging read` and returns the entries (None on error)."""
  cmd = [
      "gcloud",
      "logging",
      "read",
      _flatten(query),
      f"--project={project}",
      f"--limit={limit}",
      f"--order={_ORDER.value}",
      "--format=json",
  ]
  print(f"Running: {' '.join(cmd)} ...\n")
  stdout = _run_command(cmd, "gcloud command")
  if stdout is None:
    return None
  try:
    return json.loads(stdout)
  except json.JSONDecodeError:
    print("Error parsing JSON output from gcloud command.")
    return None


def first_per_pod(
    logs: Sequence[dict[str, Any]], n: int
) -> list[tuple[dict[str, Any], int]]:
  """Keeps the first `n` entries and the last entry of each pod/container.

  The last entry is always kept because a pod's fatal error is often its final
  matching line, logged after routine or cascade lines.

  Args:
    logs: Log entries, already ordered (by --order).
    n: Leading entries to keep per pod/container.

  Returns:
    (entry, dropped) pairs in input order, where `dropped` is set on the last
    kept entry before a gap to the number of that pod/container's entries that
    were skipped there.
  """
  indices: dict[tuple[str, str], list[int]] = {}
  for i, log in enumerate(logs):
    labels = (log.get("resource") or {}).get("labels", {})
    key = (labels.get("pod_name", ""), labels.get("container_name", ""))
    indices.setdefault(key, []).append(i)
  dropped_after: dict[int, int] = {}
  keep: set[int] = set()
  for idx in indices.values():
    head = idx[:n]
    keep.update(head)
    if len(idx) > n:
      keep.add(idx[-1])
      skipped = len(idx) - n - 1
      if skipped:
        dropped_after[head[-1] if head else idx[-1]] = skipped
  return [(logs[i], dropped_after.get(i, 0)) for i in sorted(keep)]


def run_gcloud(queries: Sequence[str], project: str) -> None:
  """Runs the queries (one per node batch), merges and prints the entries."""
  per_pod = _FIRST_PER_POD.value
  limit = max(_FETCH_LIMIT.value, _LIMIT.value) if per_pod > 0 else _LIMIT.value
  logs = []
  hit_limit = False
  for query in queries:
    batch = fetch_logs(query, project, limit)
    if batch is None:
      return
    hit_limit |= len(batch) >= limit
    logs.extend(batch)
  if not logs:
    print("No logs found matching the query.")
    return
  if len(queries) > 1:
    logs.sort(
        key=lambda e: e.get("timestamp", ""), reverse=_ORDER.value == "desc"
    )
  if per_pod > 0:
    entries = first_per_pod(logs, per_pod)
  else:
    entries = [(log, 0) for log in logs]
  for log, dropped in entries[: _LIMIT.value]:
    more = (
        f"  (... {dropped} more from this pod/container; its last line follows)"
        if dropped
        else ""
    )
    print(_format_entry(log) + more)
  if per_pod > 0 and len(entries) > _LIMIT.value:
    print(
        f"\n[note] {len(entries) - _LIMIT.value} more pod/container entries"
        " not shown; raise --limit."
    )
  if hit_limit:
    print(
        f"\n[note] Hit the fetch limit ({limit}). Narrow the time window or"
        " raise --limit/--fetch_limit; with --order=asc you are seeing the"
        " earliest entries."
    )


def discover_workload_nodes(w: Workload) -> tuple[str, ...]:
  """Finds the nodes the workload's pods were scheduled on.

  Reads the pods' "Scheduled" events ("Successfully assigned <ns>/<pod> to
  <node>") from Cloud Logging, starting `_NODE_DISCOVERY_LOOKBACK` before the
  query window.

  Args:
    w: The workload.

  Returns:
    Sorted, de-duplicated node names (empty if none were found).
  """
  try:
    start, end = compute_time_range(
        _START_TIME.value, _END_TIME.value, _DURATION.value
    )
  except ValueError as e:
    raise app.UsageError(str(e)) from e
  time_filters = []
  if start:
    time_filters.append(
        f'timestamp >= "{_to_rfc3339(start - _NODE_DISCOVERY_LOOKBACK)}"'
    )
  if end:
    time_filters.append(f'timestamp <= "{_to_rfc3339(end)}"')
  query = "\n".join(
      _cluster_filters(w, "k8s_pod")
      + [
          'log_id("events")',
          f'resource.labels.namespace_name="{w.namespace}"',
          _pod_name_filter(w),
          'jsonPayload.reason="Scheduled"',
      ]
      + time_filters
  )
  cmd = [
      "gcloud",
      "logging",
      "read",
      _flatten(query),
      f"--project={w.project}",
      "--limit=2000",
      "--format=value(jsonPayload.message)",
  ]
  # Large lookback windows occasionally hit transient backend deadlines; retry
  # once before falling back to zone scoping.
  stdout = _run_command(cmd, "node discovery") or _run_command(
      cmd, "node discovery (retry)"
  )
  nodes = set()
  for line in (stdout or "").splitlines():
    m = re.search(r"\bto (\S+)\s*$", line)
    if m:
      nodes.add(m.group(1))
  return tuple(sorted(nodes))


def build_action_query(
    action: LogAction,
    w: Workload,
    extra_terms: Sequence[str] = (),
    min_severity: str | None = None,
) -> list[str]:
  """Returns the action's filter clauses, OR-ing its terms with extra matches.

  Args:
    action: The log action.
    w: The workload.
    extra_terms: Additional plain-text (unquoted) strings to match.
    min_severity: If set, also match every entry at or above this severity.

  Raises:
    app.UsageError: If `extra_terms` or `min_severity` is given for an action
      without terms.
  """
  if (extra_terms or min_severity) and not action.terms:
    raise app.UsageError(
        "--extra_terms and --min_severity are only supported by actions with"
        " a built-in list of terms: "
        + ", ".join(name for name, a in _LOG_ACTIONS.items() if a.terms)
    )
  filters = action.build_query(w)
  terms = action.terms + tuple(_quote(t) for t in extra_terms)
  if min_severity:
    terms += (f"severity>={min_severity}",)
  return filters + _any_of(*terms) if terms else filters


def run_neighbors(queries: Sequence[str], w: Workload) -> None:
  """Lists the distinct namespace/pod/container that logged on the nodes.

  Pods that do not belong to the workload are marked, so co-located workloads
  stand out.

  Args:
    queries: The `neighbors` queries (one per node batch), with time filters.
    w: The workload.
  """
  counts: dict[tuple[str, ...], int] = {}
  for query in queries:
    cmd = [
        "gcloud",
        "logging",
        "read",
        _flatten(query),
        f"--project={w.project}",
        f"--limit={max(_LIMIT.value, 10000)}",
        "--format=value("
        + ",".join([
            "resource.labels.namespace_name",
            "resource.labels.pod_name",
            "resource.labels.container_name",
        ])
        + ")",
    ]
    print(f"Running: {' '.join(cmd)} ...\n")
    stdout = _run_command(cmd, "gcloud command")
    if stdout is None:
      return
    for line in stdout.splitlines():
      key = tuple(line.split("\t"))
      if len(key) == 3:
        counts[key] = counts.get(key, 0) + 1
  if not counts:
    print("No container logs found on these nodes.")
    return
  print("lines  namespace/pod/container  (* = not part of this workload)")
  for (ns, pod, container), n in sorted(counts.items()):
    own = ns == w.namespace and any(pod.startswith(x) for x in w.names)
    print(f"{n:6d} {'' if own else '* '}{ns}/{pod}/{container}")


def _node_batches(w: Workload) -> list[Workload]:
  """Splits a workload with many nodes into batches of `_NODE_BATCH_SIZE`."""
  nodes = w.node_names
  if len(nodes) <= _NODE_BATCH_SIZE:
    return [w]
  return [
      dataclasses.replace(w, node_names=nodes[i : i + _NODE_BATCH_SIZE])
      for i in range(0, len(nodes), _NODE_BATCH_SIZE)
  ]


def do_log_action(action: LogAction, w: Workload) -> None:
  """Builds, prints, and optionally executes the query for a log action.

  Node-scoped actions with many nodes run one query per node batch; only the
  first batch's query is printed.

  Args:
    action: The log action.
    w: The workload.
  """
  batches = _node_batches(w) if action.needs_nodes else [w]
  queries = [
      "\n".join(
          build_action_query(
              action, b, _EXTRA_TERMS.value, _MIN_SEVERITY.value
          )
          + get_time_filter()
      )
      for b in batches
  ]
  print(f"=== Action: {action.title} ===")
  if len(queries) > 1:
    print(
        f"[note] {len(w.node_names)} nodes are queried in {len(queries)}"
        f" batches of up to {_NODE_BATCH_SIZE}; showing the first batch's"
        " query.\n"
    )
  print_console_url(queries[0], w.project)
  print_gcloud_cmd(queries[0], w.project)
  if not _EXECUTE.value:
    return
  if action.build_query is neighbors_query:
    run_neighbors(queries, w)
  else:
    run_gcloud(queries, w.project)


def _probe(query: str, project: str) -> tuple[bool | None, str]:
  """Returns (found any entry, error text); found is None on error."""
  cmd = [
      "gcloud",
      "logging",
      "read",
      _flatten(query),
      f"--project={project}",
      "--limit=1",
      "--format=value(timestamp)",
  ]
  try:
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
  except subprocess.CalledProcessError as e:
    return None, e.stderr
  return bool(out.stdout.strip()), ""


def run_preflight(w: Workload) -> None:
  """Checks log access and that the workload logged in the time window.

  An empty result from another action only means "no error" once these checks
  pass.

  Args:
    w: The workload.
  """
  time_filters = get_time_filter()
  print("=== Preflight ===")
  start, _ = compute_time_range(
      _START_TIME.value, _END_TIME.value, _DURATION.value
  )
  if start and start < datetime.datetime.now(
      datetime.timezone.utc
  ) - datetime.timedelta(days=30):
    print(
        "[warn] The window starts more than 30 days ago; logs may be past the"
        " project's retention period (30 days in the _Default bucket).\n"
    )

  found, err = _probe(
      "\n".join(_cluster_filters(w, "k8s_container") + time_filters),
      w.project,
  )
  if found is None:
    reason = (
        "no permission to read logs (needs roles/logging.viewer)"
        if "PERMISSION_DENIED" in err
        else err.strip().splitlines()[0] if err.strip() else "unknown error"
    )
    print(f"[FAIL] Cannot read logs in project {w.project}: {reason}")
    print("Results from other actions are not meaningful until this passes.")
    return
  if not found:
    print(
        f"[FAIL] No container logs at all for cluster {w.cluster} in"
        f" {w.location} in the time window. Check the project, cluster,"
        " location, time window and log retention."
    )
    return
  print(f"[ok] Cluster {w.cluster} has container logs in the window.")

  for t in w.targets:
    single = dataclasses.replace(w, targets=(t,))
    has_logs, _ = _probe(
        "\n".join(_jobset_container_filters(single) + time_filters), w.project
    )
    has_events, _ = _probe(
        "\n".join(
            pod_events_query(single)[:-1] + time_filters
        ),
        w.project,
    )
    label = f"{t.kind}:{t.name} (namespace {w.namespace})"
    if has_logs:
      print(f"[ok] {label}: container logs found.")
    elif has_events:
      print(
          f"[warn] {label}: pod events but no container logs; the containers"
          " may never have started. Run --action=pod-events and"
          " --action=summary."
      )
    else:
      print(
          f"[FAIL] {label}: no container logs or pod events in the window."
          " Check the name, kind (--jobset_name/--lws_name/--job_name/"
          "--pod_prefix), namespace and time window."
      )


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError("Too many command-line arguments.")

  try:
    targets = parse_targets(
        _WORKLOADS.value,
        jobset=_JOBSET_NAME.value,
        lws=_LWS_NAME.value,
        job=_JOB_NAME.value,
        pod_prefix=_POD_PREFIX.value,
    )
  except ValueError as e:
    raise app.UsageError(str(e)) from e
  workload = Workload(
      project=_PROJECT.value,
      cluster=_CLUSTER_NAME.value,
      location=_LOCATION.value,
      targets=targets,
      namespace=_NAMESPACE.value,
      node_names=tuple(_NODE_NAMES.value),
      sidecar_container=_SIDECAR_CONTAINER.value,
  )
  if _ACTION.value == "preflight":
    run_preflight(workload)
    return
  action = _LOG_ACTIONS[_ACTION.value]
  if action.needs_nodes and not workload.node_names:
    nodes = discover_workload_nodes(workload) if _EXECUTE.value else ()
    if nodes:
      print(
          f"Scoping to the workload's {len(nodes)} node(s):"
          f" {', '.join(nodes)}\n"
      )
      workload = dataclasses.replace(workload, node_names=nodes)
    elif _ACTION.value == "node-ooms":
      print(
          "[note] Node names unknown (pass --node_names, or --execute to"
          " discover them); serial-console logs are scoped to zone"
          f" '{workload.location}' and may include unrelated VMs.\n"
      )
    else:
      raise app.UsageError(
          f"--action={_ACTION.value} needs the workload's nodes: pass"
          " --node_names, or --execute to discover them from the pods'"
          " 'Scheduled' events."
      )
  do_log_action(action, workload)


if __name__ == "__main__":
  app.run(main)
