"""Derived log facts for the `gke-kueue-troubleshooting` skill.

Turns normalised log lines (Kueue controller JSON, `audit.k8s.io/v1` events,
Kubernetes Events) into the `derived_log_diagnostics` block that
`trace_logs.py` prints: an entity inventory, key errors/events, audit actions
and neutral `derived_log_facts`.

The extraction runs in two layers over a single `LogScanState`:

  * record scanners `scan_<topic>(rec, state)` — applied to every parsed record
    in `RECORD_SCANNERS` order, each filling the accumulators of one topic;
  * fact emitters `emit_<fact>(state)` — applied once after the scan in
    `LOG_FACT_EMITTERS` order, each returning `(key, text)` fact tuples.

Plain-text signals that do not need a parsed record (TAS domain errors,
strict-decoding errors, webhook timeouts, API-pressure markers) are collected
by `scan_text_signals` on every line, structured or not.

Every fact string is observational: it states what the log said and, at most,
one sentence of version-independent Kueue semantics with a source citation.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
from typing import Any, Callable

import k8s_objects
import kueue_schema
import log_envelopes
import log_signatures
import report_output

# Exact controller log messages this module matches. Every entry must exist in
# the Kueue source at kueue_schema.KUEUE_SOURCE_REF (tests/test_scripts.py
# checks this when a Kueue checkout is available).
KUEUE_LOG_LITERALS = (
    ("cmd/kueue/main.go", "Configuration loaded"),
    (
        "pkg/scheduler/scheduler.go",
        "Workload successfully admitted and assigned flavors",
    ),
    (
        "pkg/controller/jobframework/reconciler.go",
        "Updating the PodsReady condition",
    ),
    (
        "pkg/controller/core/workload_controller.go",
        "exceeding the PodsReady timeout",
    ),
    (
        "pkg/controller/core/workload_controller.go",
        (
            "Workload is inadmissible because the LocalQueue is terminating or"
            " missing"
        ),
    ),
    (
        "pkg/scheduler/preemption/preemption.go",
        "Fair Sharing within the cohort",
    ),
    ("pkg/cache/scheduler/tas_flavor_snapshot.go", "no topology domains"),
    (
        "pkg/scheduler/flavorassigner/flavorassigner.go",
        "couldn't assign flavors",
    ),
    (
        "pkg/scheduler/flavorassigner/flavorassigner.go",
        "unavailable in ClusterQueue",
    ),
    (
        "pkg/scheduler/flavorassigner/flavorassigner.go",
        "insufficient unused quota",
    ),
    ("pkg/cache/queue/manager.go", "localQueue doesn't exist"),
    # Signature table (log_signatures.py)
    (
        "pkg/scheduler/flavorassigner/flavorassigner.go",
        "couldn't assign flavors to pod set",
    ),
    (
        "pkg/scheduler/flavorassigner/flavorassigner.go",
        "insufficient quota for",
    ),
    (
        "pkg/scheduler/flavorassigner/flavorassigner.go",
        "insufficient unused quota for",
    ),
    (
        "pkg/cache/scheduler/tas_flavor_snapshot.go",
        "doesn't allow to fit any of",
    ),
    ("pkg/cache/scheduler/tas_flavor_snapshot.go", "allows to fit only"),
    (
        "pkg/scheduler/scheduler.go",
        (
            "Workload requires preemption, but there are no candidate workloads"
            " allowed for preemption"
        ),
    ),
    (
        "pkg/scheduler/preemption/preemption.go",
        "Preempted to accommodate a workload",
    ),
    (
        "pkg/controller/core/workload_controller.go",
        "Exceeded the PodsReady timeout",
    ),
    (
        "pkg/controller/core/workload_controller.go",
        "exceeding the maximum number of re-queuing retries",
    ),
    (
        "pkg/controller/core/workload_controller.go",
        "the retention period has elapsed",
    ),
    (
        "pkg/controller/core/workload_controller.go",
        "Deleted finished workload due to elapsed retention",
    ),
    (
        "pkg/scheduler/flavorassigner/tas_flavorassigner.go",
        "does not contain the requested level",
    ),
    (
        "pkg/scheduler/flavorassigner/tas_flavorassigner.go",
        "supports only TopologyAwareScheduling",
    ),
    ("pkg/scheduler/scheduler.go", "Flavors considered"),
)

# Event emitters that belong to Kueue or to the Kubernetes core controllers.
# Anything else (cluster autoscalers, node provisioners, device operators,
# provider controllers) is an external emitter: its Events are surfaced
# verbatim with the emitter name, whatever their type or reason, so that the
# agent can attribute them without the script knowing any provider's reason
# vocabulary.
_CORE_EMITTER_PREFIXES = (
    "kueue",
    "job-controller",
    "jobset",
    "cronjob-controller",
    "kubelet",
    "default-scheduler",
    "replicaset-controller",
    "deployment-controller",
    "statefulset-controller",
    "daemonset-controller",
    "endpoint",
    "node-controller",
    "taint",
    "service-controller",
    "persistentvolume",
    "attachdetach",
    "horizontal-pod-autoscaler",
    "garbage-collector",
    "namespace-controller",
    "leaderworkerset",
    "ray",
    "kubeflow",
)


# Kueue registers its Event recorders as `<gvk>-kueue-controller`,
# `multikueue-*`, `tas-*`, `concurrent-admission-controller`,
# `failure-recovery-*` and `ElasticJobUngater`
# (pkg/controller/jobframework/setup.go, pkg/controller/tas/constants.go,
# pkg/controller/concurrentadmission, pkg/controller/failurerecovery,
# cmd/kueue/main.go).
_KUEUE_EMITTER_MARKERS = (
    "kueue",
    "tas-",
    "concurrent-admission",
    "failure-recovery",
    "elasticjob",
)


def _is_event_record(d: dict[str, Any]) -> bool:
  return (
      d.get("kind") == "Event"
      or d.get("logger") == "events"
      or isinstance(d.get("involvedObject"), dict)
      or isinstance(d.get("regarding"), dict)
      or isinstance(d.get("source"), dict)
      or any(
          d.get(k)
          for k in (
              "reportingController",
              "reportingComponent",
              "reportingInstance",
          )
      )
  )


def event_emitter(d: dict[str, Any]) -> str:
  """Returns the Event emitter name ('' when unknown) from raw or normalised rows."""
  if not _is_event_record(d):
    return ""
  return log_envelopes.extract_event_emitter(d)


def is_external_emitter(d: dict[str, Any]) -> bool:
  """True when an Event comes from a component outside Kueue and the Kubernetes core."""
  emitter = event_emitter(d).lower()
  if not emitter or emitter.startswith("kind source:"):
    return False
  if any(marker in emitter for marker in _KUEUE_EMITTER_MARKERS):
    return False
  return not any(emitter.startswith(p) for p in _CORE_EMITTER_PREFIXES)


_FRAMEWORKS_YAML_RE = re.compile(
    r"integrations:[ \t]*\n(?:[ \t]+(?!frameworks:)\S.*\n)*?[ \t]+frameworks:["
    r" \t]*\n((?:[ \t]+-[ \t]*\S+[ \t]*\n?)+)"
)
_FRAMEWORKS_JSON_RE = re.compile(r'"frameworks"\s*:\s*\[([^\]\[]{0,2000})\]')


def frameworks_from_config(config_text: str) -> list[str] | None:
  """integrations.frameworks from the 'Configuration loaded' payload (YAML or JSON); None if absent."""
  m = _FRAMEWORKS_YAML_RE.search(config_text)
  if m:
    return [
        ln.strip().lstrip("-").strip().strip("'\"")
        for ln in m.group(1).splitlines()
        if ln.strip()
    ]
  m = _FRAMEWORKS_JSON_RE.search(config_text)
  if m:
    return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
  return None


# Audit verbs on these resources are summarised under `audit_resource_actions`.
_AUDITED_RESOURCES = frozenset({
    "workloads",
    "localqueues",
    "clusterqueues",
    "cohorts",
    "resourceflavors",
    "admissionchecks",
    "provisioningrequestconfigs",
    "topologies",
    "workloadpriorityclasses",
    "multikueueconfigs",
    "multikueueclusters",
    "jobs",
    "jobsets",
    "namespaces",
    "nodes",
    "configmaps",
})

# Audited mutations of these resources (any verb) and deletions of any audited
# resource receive a fact id: they change the admission graph or its
# configuration. Job/Workload creations and status patches do not.
_GRAPH_CONFIG_RESOURCES = frozenset({
    "localqueues",
    "clusterqueues",
    "cohorts",
    "resourceflavors",
    "admissionchecks",
    "provisioningrequestconfigs",
    "topologies",
    "workloadpriorityclasses",
    "multikueueconfigs",
    "multikueueclusters",
    "namespaces",
    "configmaps",
})

# Error lines matching these substrings are ordinary controller retry noise
# (optimistic-concurrency conflicts); they stay in key_errors_and_events but
# do not receive a fact id.
_ROUTINE_ERROR_MARKERS = (
    "the object has been modified; please apply your changes",
    "already exists",
)

# API-pressure signals, classified by the side that produced them.
#   kueue-client : emitted by Kueue's own client-go rate limiter
#                  (clientConnection.qps/burst in KueueConfiguration).
#   apiserver    : emitted by the Kubernetes API server (HTTP 429/503,
#                  API Priority and Fairness shedding).
#   kueue-leader : controller-runtime leader election outcome.
# The table is observational: it records what the log said and which component
# said it; it does not assert why. A status number counts only next to
# `code` / `status` / `HTTP`: a bare 429 or 503 is as often part of an object
# name or a resourceVersion.
_HTTP_STATUS_CONTEXT = r"(?:code|status|HTTP)[\s:=\"'\\]{0,4}"
_API_PRESSURE_SIGNALS: tuple[tuple[str, str, str], ...] = (
    (
        "kueue-client",
        "client-side rate limiter / throttling",
        (
            r"client-side throttling|rate:\s*Wait\([^)]*\)\s*would exceed"
            r" context deadline"
        ),
    ),
    (
        "apiserver",
        "HTTP 503 / the server is currently unable to handle the request",
        (
            r"unable to handle the request|503 Service Unavailable|"
            + _HTTP_STATUS_CONTEXT
            + r"503\b"
        ),
    ),
    (
        "apiserver",
        "HTTP 429 / too many requests",
        r"too many requests|" + _HTTP_STATUS_CONTEXT + r"429\b",
    ),
    (
        "kueue-leader",
        "leader election lost / failed to renew lease",
        r"leader election lost|failed to renew lease(?!.*context canceled)",
    ),
)
_API_PRESSURE_SIDE_NOTE = {
    "kueue-client": (
        "emitted by Kueue's own client-go rate limiter; its budget is"
        " KueueConfiguration.clientConnection.qps/burst"
        " (https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/,"
        " https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/)"
    ),
    "apiserver": (
        "emitted by the Kubernetes API server, not by Kueue; HTTP 429/503 are"
        " produced by API Priority and Fairness (per priority level / flow"
        " schema) or an overloaded/unavailable server; whether other clients of"
        " that API server are affected is not visible in this log alone"
    ),
    "kueue-leader": (
        "KueueConfiguration.leaderElection configures manager.Manager leader"
        " election"
        " (https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/,"
        " https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/)"
    ),
}

_AUDIT_LOGGERS = ("audit", "cloud-audit")
_ADMISSION_MSG = "Workload successfully admitted and assigned flavors"
_LQ_MISSING_MSG = (
    "Workload is inadmissible because the LocalQueue is terminating or missing"
)

# Controller lifecycle chatter that never describes a workload decision.
_BENIGN_SIGNALS = (
    "RoleTracker: leader election enabled",
    "Stopping and waiting for",
    "Shutdown signal received",
    "All workers finished",
    "Wait completed, proceeding to shutdown",
    "client rate limiter Wait returned an error: context canceled",
)
_KEY_EVENT_REASONS = frozenset({
    "Pending",
    "FailedScheduling",
    "EvictedDueToPodsReadyTimeout",
    "EvictedDueToAdmissionCheck",
    "AdmissionCheckUpdated",
    "UpdatedAdmissionCheck",
    "Evicted",
    "Preempted",
    "NotTriggerScaleUp",
    "BookingExpired",
    "FailedCreate",
    "Inadmissible",
})
# Matched case-sensitively against the combined signal text.
_KEY_EVENT_MARKERS = (
    "couldn't assign flavors",
    "localQueue doesn't exist",
    "strict decoding error",
)
# Matched against the lower-cased combined signal text.
_KEY_EVENT_MARKERS_LOWER = (
    "inadmissible",
    "retrying after failure",
    "evicted due to",
    "context deadline exceeded",
    "would exceed context deadline",
    "client-side throttling",
    "leader election lost",
    "failed to renew lease",
    "unable to handle the request",
)
_MAX_KEY_EVENTS = 30
_MAX_AUDIT_ACTIONS = 35
_MAX_AUDIT_DELETIONS = 35
_MAX_AUDIT_ACTIONS_WITH_STATUS = 40


# ---------------------------------------------------------------------------
# Typed access to a parsed record
# ---------------------------------------------------------------------------


def _ref_name(value: Any) -> str:
  """Name from a logged object ref: `{name: ...}` (klog ObjectRef) or a plain string."""
  if isinstance(value, dict):
    return str(value["name"]) if value.get("name") else ""
  if isinstance(value, str):
    return value
  return ""


def _ref_namespace(value: Any, default: str = "") -> str:
  """Namespace of a klog ObjectRef dict; `default` for strings and other shapes."""
  if isinstance(value, dict) and isinstance(value.get("namespace"), str):
    return value["namespace"]
  return default


def _qualified(namespace: Any, name: str) -> str:
  return f"{namespace}/{name}" if namespace else name


def _first_str(d: dict[str, Any], *keys: str) -> str:
  """`str()` of the first truthy value among `keys` ('' when none)."""
  for key in keys:
    if d.get(key):
      return str(d[key])
  return ""


@dataclasses.dataclass(frozen=True)
class LogRecord:
  """A parsed log record with its commonly read fields normalised to strings."""

  raw: dict[str, Any]
  msg: str
  note: str
  err: str
  reason: str
  logger: str
  ts: str
  level: str
  ev_type: str
  workload: Any
  wl_full: str
  obj: dict[str, Any] | None
  job_ref: str = ""

  @classmethod
  def from_dict(cls, d: Any) -> "LogRecord":
    """Builds a record from any JSON value; non-dict input yields an empty record."""
    if not isinstance(d, dict):
      d = {}
    wl = d.get("workload")
    wl_full = ""
    if isinstance(wl, dict) and wl.get("name"):
      wl_full = _qualified(_ref_namespace(wl), str(wl["name"]))
    elif isinstance(wl, str) and wl:
      wl_full = wl
    # The job reconciler logs with `job=<ns>/<name>` (ReconcileGenericJob),
    # not `workload`.
    job = d.get("job")
    job_ref = ""
    if isinstance(job, str):
      job_ref = job
    elif isinstance(job, dict) and job.get("name"):
      job_ref = _qualified(_ref_namespace(job), str(job.get("name")))
    obj = d.get("object") or d.get("involvedObject")
    return cls(
        raw=d,
        msg=_first_str(d, "msg", "message"),
        note=_first_str(d, "note"),
        err=_first_str(d, "error", "err"),
        reason=_first_str(d, "reason"),
        logger=_first_str(d, "logger"),
        ts=_first_str(d, "ts", "time", "timestamp"),
        level=_first_str(d, "level", "severity").lower(),
        ev_type=_first_str(d, "type"),
        workload=wl,
        wl_full=wl_full,
        obj=obj if isinstance(obj, dict) else None,
        job_ref=job_ref,
    )

  @property
  def ts_field(self) -> str:
    """The literal `ts` field (audit entries are stamped from it alone)."""
    return _first_str(self.raw, "ts")

  @property
  def is_audit(self) -> bool:
    """Audit entries are summarised under `audit_resource_actions`, never as key events."""
    return self.logger in _AUDIT_LOGGERS or self.msg.startswith("[Audit ")

  @property
  def is_audit_source(self) -> bool:
    """Wider test used for source counting (also cloud audit envelopes)."""
    return (
        self.is_audit
        or bool(self.raw.get("auditID"))
        or bool(self.raw.get("protoPayload"))
    )

  @property
  def is_kubernetes_event(self) -> bool:
    """An exported Event object (normalised or raw), not a controller log line about one."""
    return (
        self.raw.get("source_kind") == log_envelopes.K8S_EVENT_SOURCE_KIND
        or self.raw.get("kind") == "Event"
        or bool(self.raw.get("involvedObject") and self.reason)
    )

  @property
  def combined_signal(self) -> str:
    return f"{self.msg} | {self.reason} | {self.note} | {self.err}"

  @property
  def msg_and_note(self) -> str:
    return self.msg + " " + self.note

  @property
  def named_obj(self) -> dict[str, Any] | None:
    """`object` / `involvedObject` when it carries a name."""
    return self.obj if self.obj is not None and self.obj.get("name") else None


# ---------------------------------------------------------------------------
# Scan state
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class LogScanState:
  """Every accumulator filled by the scanners and read by the emitters."""

  source_counts: dict[str, int] = dataclasses.field(
      default_factory=lambda: {
          "total": 0,
          "kueue-controller": 0,
          "audit": 0,
          "kubernetes-event": 0,
          "unstructured": 0,
      }
  )
  window_start: str = ""
  window_end: str = ""
  config_excerpt: str = ""
  config_frameworks: list[str] | None = None
  # Entity inventory.
  workloads: set[str] = dataclasses.field(default_factory=set)
  cluster_queues: set[str] = dataclasses.field(default_factory=set)
  local_queues: set[str] = dataclasses.field(default_factory=set)
  resource_flavors: set[str] = dataclasses.field(default_factory=set)
  namespaces: set[str] = dataclasses.field(default_factory=set)
  nodes: set[str] = dataclasses.field(default_factory=set)
  discovered_kinds: set[str] = dataclasses.field(
      default_factory=lambda: {
          "ClusterQueue",
          "LocalQueue",
          "Workload",
          "ResourceFlavor",
          "KueueConfiguration",
      }
  )
  # Admission volume: (clusterQueue, flavor, resource) -> summed resourceUsage;
  # admitted count per CQ.
  admitted_usage: dict[tuple[str, str, str], float] = dataclasses.field(
      default_factory=dict
  )
  admitted_count_by_cq: dict[str, int] = dataclasses.field(default_factory=dict)
  # PodsReady transitions.
  waiting_pods_ready_workloads: set[str] = dataclasses.field(
      default_factory=set
  )
  pods_ready_true_workloads: set[str] = dataclasses.field(default_factory=set)
  # Reference -> `reason` of its latest status=False line ('' when not logged).
  pods_ready_false_reason: dict[str, str] = dataclasses.field(
      default_factory=dict
  )
  empty_lq_workloads: set[str] = dataclasses.field(default_factory=set)
  in_cohort_preemptions: list[str] = dataclasses.field(default_factory=list)
  has_insufficient_quota_pending: bool = False
  # Audit trail.
  audit_actions: list[tuple[str | None, str]] = dataclasses.field(
      default_factory=list
  )
  seen_audit: set[str] = dataclasses.field(default_factory=set)
  audit_non_delete_count: int = 0
  audit_delete_count: int = 0
  omitted_audit: int = 0
  omitted_audit_deletions: int = 0
  workload_status_by_name: dict[str, str] = dataclasses.field(
      default_factory=dict
  )
  # Namespace -> (timestamp, response code as logged or '').
  audit_namespace_deletions: dict[str, tuple[str, str]] = dataclasses.field(
      default_factory=dict
  )
  audit_cq_quota_patches: list[str] = dataclasses.field(default_factory=list)
  # (timestamp, ClusterQueue, value, principal, verb, confirmed_change).
  audit_cq_quota_patch_detail: list[tuple[str, str, str, str, str, bool]] = (
      dataclasses.field(default_factory=list)
  )
  # Raw CQ quota events buffered during scan, resolved in chronological order
  # at the end of `scan_lines`: (ts, seq, cq, kind, value, principal, verb).
  audit_cq_quota_events: list[tuple[str, int, str, str, str, str, str]] = (
      dataclasses.field(default_factory=list)
  )
  audit_cq_quota_seq: int = 0
  # ClusterQueue -> nominalQuota values of the latest request body seen for it.
  audit_cq_quota_bodies: dict[str, str] = dataclasses.field(
      default_factory=dict
  )
  audit_indexed_jobs_no_max_failed: list[str] = dataclasses.field(
      default_factory=list
  )
  # Key errors / events.
  key_events: list[tuple[str, str]] = dataclasses.field(default_factory=list)
  seen_events: set[str] = dataclasses.field(default_factory=set)
  omitted_events: int = 0
  # Plain-text signals.
  topology_levels_without_domains: set[str] = dataclasses.field(
      default_factory=set
  )
  strict_unknown_fields: set[str] = dataclasses.field(default_factory=set)
  unavailable_resources: set[str] = dataclasses.field(default_factory=set)
  webhook_timeout_targets: set[str] = dataclasses.field(default_factory=set)
  # Webhook name -> connection-level causes logged for it (no timeout among
  # them is implied; see `scan_text_signals`).
  webhook_connection_errors: dict[str, set[str]] = dataclasses.field(
      default_factory=dict
  )
  # Webhook name -> other logged causes (neither timeout nor connection-level).
  webhook_other_errors: dict[str, set[str]] = dataclasses.field(
      default_factory=dict
  )
  api_pressure_signals: set[tuple[str, str]] = dataclasses.field(
      default_factory=set
  )
  client_throttling_count: int = 0
  # Controller-message signatures (log_signatures.SIGNATURES), keyed by
  # signature key.
  signature_hits: dict[str, log_signatures.SignatureHits] = dataclasses.field(
      default_factory=dict
  )


# ---------------------------------------------------------------------------
# Plain-text scanning (every line, structured or not)
# ---------------------------------------------------------------------------

_TAS_LEVEL_RE = re.compile(
    r"no topology domains at level:\s*([A-Za-z0-9./_-]+)"
)
_UNAVAILABLE_RESOURCE_RE = re.compile(
    r"resource\s+([a-z0-9._/-]+)\s+unavailable in ClusterQueue"
)
_UNKNOWN_FIELD_RE = re.compile(r'unknown field\s*\\?"([^"\\]+)\\?"')
_WEBHOOK_FAILURE_RE = re.compile(
    r'failed calling webhook\s+\\?"([^"\\]+)\\?"', re.IGNORECASE
)
# The webhook URL always carries `?timeout=<n>s`; it is not a cause.
_WEBHOOK_URL_TIMEOUT_RE = re.compile(r"\?timeout=\d+s")
# Go error texts, matched case-sensitively after the webhook name.
_WEBHOOK_TIMEOUT_CAUSE_RE = re.compile(
    r"context deadline exceeded|Client\.Timeout|i/o timeout"
)
_WEBHOOK_CONNECTION_CAUSE_RE = re.compile(r"connection refused|\bEOF\b")
_WEBHOOK_CALL_PREFIX_RE = re.compile(
    r"^(?:failed to call webhook:\s*)?"
    r'(?:(?:Post|Get|Put|Patch|Delete)\s+\\?"[^"\\]+\\?":\s*)?'
)
_UNESCAPED_JSON_END_RE = re.compile(r'(?<!\\)["}]')


def _extract_webhook_other_cause(cause_text: str, *, is_json_line: bool) -> str:
  """Extracts and redacts the trailing error cause after a webhook name."""
  text = cause_text.lstrip(" :")
  if is_json_line:
    end_m = _UNESCAPED_JSON_END_RE.search(text)
    if end_m:
      text = text[: end_m.start()]
  text = _WEBHOOK_CALL_PREFIX_RE.sub("", text).replace('\\"', '"').strip()
  text = " ".join(log_envelopes.redact_env_text(text).split())
  return text[:160]


def _scan_webhook_failure(text: str, state: LogScanState) -> None:
  """Classifies a 'failed calling webhook' line by its stated cause.

  Timeout and connection-level causes are recorded in dedicated sets; any other
  logged cause (such as missing endpoints or certificate errors) is recorded
  verbatim under `webhook_other_errors` without calling it a timeout.

  Args:
    text: Log line text.
    state: Scan state updated in place.
  """
  wh_m = _WEBHOOK_FAILURE_RE.search(text)
  if not wh_m:
    return
  cause_text = _WEBHOOK_URL_TIMEOUT_RE.sub("", text[wh_m.end() :])
  if _WEBHOOK_TIMEOUT_CAUSE_RE.search(cause_text):
    state.webhook_timeout_targets.add(wh_m.group(1))
    return
  conn_m = _WEBHOOK_CONNECTION_CAUSE_RE.search(cause_text)
  if conn_m:
    state.webhook_connection_errors.setdefault(wh_m.group(1), set()).add(
        conn_m.group(0)
    )
    return
  other = _extract_webhook_other_cause(
      cause_text, is_json_line=text.lstrip().startswith("{")
  )
  if other:
    state.webhook_other_errors.setdefault(wh_m.group(1), set()).add(other)


def scan_text_signals(text: str, state: LogScanState) -> None:
  """Collects signals that are recognisable from the raw line text alone."""
  low = text.lower()
  lvl_m = _TAS_LEVEL_RE.search(text)
  if lvl_m:
    state.topology_levels_without_domains.add(lvl_m.group(1))
    state.discovered_kinds.add("Topology")
  unavail_m = _UNAVAILABLE_RESOURCE_RE.search(text)
  if unavail_m:
    state.unavailable_resources.add(unavail_m.group(1))
  if "ProvisioningRequest" in text or "provisioningrequest" in low:
    state.discovered_kinds.update(
        {"AdmissionCheck", "ProvisioningRequestConfig"}
    )
  if "strict decoding error" in text:
    state.strict_unknown_fields.update(_UNKNOWN_FIELD_RE.findall(text))
  _scan_webhook_failure(text, state)
  # API-pressure signals are classified by the side that produced them so the
  # reader can tell a Kueue-side client limiter apart from API-server-side
  # rejection; the two have different owners and different remediations.
  for sig_side, sig_name, pat in _API_PRESSURE_SIGNALS:
    if re.search(pat, text, re.IGNORECASE):
      state.api_pressure_signals.add((sig_side, sig_name))
  if "client-side throttling, not priority and fairness" in low:
    state.client_throttling_count += 1


# ---------------------------------------------------------------------------
# Record scanners
# ---------------------------------------------------------------------------


def scan_source_and_window(rec: LogRecord, state: LogScanState) -> None:
  """Counts the record under its source and widens the observed time window."""
  if rec.is_audit_source:
    state.source_counts["audit"] += 1
  elif rec.is_kubernetes_event:
    state.source_counts["kubernetes-event"] += 1
  else:
    state.source_counts["kueue-controller"] += 1
  if rec.ts and not rec.ts.replace(".", "", 1).isdigit():
    state.window_start = min(state.window_start or rec.ts, rec.ts)
    state.window_end = max(state.window_end, rec.ts)


_CONFIG_LOADED_MSGS = (
    "Configuration loaded",
    "Successfully loaded configuration",
)


def scan_config(rec: LogRecord, state: LogScanState) -> None:
  """Keeps the latest 'Configuration loaded' / 'Successfully loaded configuration' payload and its integrations.frameworks."""
  if rec.msg in _CONFIG_LOADED_MSGS and rec.raw.get("config"):
    config_text = str(rec.raw.get("config"))
    state.config_excerpt = config_text[:1500]
    state.config_frameworks = frameworks_from_config(config_text)


def scan_workload_ref(rec: LogRecord, state: LogScanState) -> None:
  """Records the `workload` reference and its namespace."""
  if not rec.wl_full:
    return
  state.workloads.add(rec.wl_full)
  ns = _ref_namespace(rec.workload)
  if ns:
    state.namespaces.add(ns)


def scan_admission(rec: LogRecord, state: LogScanState) -> None:
  """Sums resourceUsage from 'Workload successfully admitted and assigned flavors'."""
  d = rec.raw
  if rec.msg != _ADMISSION_MSG or not isinstance(d.get("assignments"), list):
    return
  adm_cq_name = _ref_name(d.get("clusterQueue"))
  if not adm_cq_name:
    return
  state.admitted_count_by_cq[adm_cq_name] = (
      state.admitted_count_by_cq.get(adm_cq_name, 0) + 1
  )
  for ps in d.get("assignments") or []:
    if not isinstance(ps, dict):
      continue
    flavors_map = (
        ps.get("flavors") if isinstance(ps.get("flavors"), dict) else {}
    )
    usage_map = (
        ps.get("resourceUsage")
        if isinstance(ps.get("resourceUsage"), dict)
        else {}
    )
    for res_n, qty in usage_map.items():
      fl_n = str(flavors_map.get(res_n) or "")
      qv = report_output.parse_quantity(qty)
      if qv is None:
        continue
      k3 = (adm_cq_name, fl_n, str(res_n))
      state.admitted_usage[k3] = state.admitted_usage.get(k3, 0.0) + qv


def scan_pods_ready(rec: LogRecord, state: LogScanState) -> None:
  """Tracks PodsReady condition transitions keyed by the Job/Workload reference."""
  if rec.msg != "Updating the PodsReady condition":
    return
  # JobReconciler.ReconcileGenericJob logs this at V(3) on every PodsReady
  # transition with the condition's reason and status; its logger carries
  # `job=<ns>/<name>`, not `workload`.
  ref = rec.job_ref or rec.wl_full
  if not ref:
    return
  status = str(rec.raw.get("status", "")).lower()
  if status == "false":
    state.waiting_pods_ready_workloads.add(ref)
    state.pods_ready_false_reason[ref] = rec.reason
    state.pods_ready_true_workloads.discard(ref)
  elif status == "true":
    state.pods_ready_true_workloads.add(ref)
    state.waiting_pods_ready_workloads.discard(ref)


def scan_local_queue_missing(rec: LogRecord, state: LogScanState) -> None:
  """Workloads reconciled with an empty LocalQueue name."""
  if _LQ_MISSING_MSG in rec.msg:
    lq_obj = rec.raw.get("localQueue")
    lq_name = lq_obj.get("name") if isinstance(lq_obj, dict) else None
    if isinstance(lq_name, str) and not lq_name and rec.wl_full:
      state.empty_lq_workloads.add(rec.wl_full)


_PREEMPTION_PATH_RE = re.compile(
    r"preemptor path:\s*(\S+);\s*preemptee path:\s*(\S+)"
)


def scan_fair_sharing(rec: LogRecord, state: LogScanState) -> None:
  """In-cohort fair-sharing preemptions and 'insufficient unused quota' markers."""
  if (
      rec.reason == "InCohortFairSharing"
      or "due to Fair Sharing within the cohort" in rec.msg_and_note
  ):
    p_cq = _first_str(rec.raw, "preemptingClusterQueue")
    t_cq = _first_str(rec.raw, "targetClusterQueue")
    if p_cq or t_cq:
      state.in_cohort_preemptions.append(f"{p_cq}->{t_cq}")
    else:
      pm = _PREEMPTION_PATH_RE.search(rec.msg_and_note)
      if pm:
        state.in_cohort_preemptions.append(f"{pm.group(1)}->{pm.group(2)}")
      else:
        state.in_cohort_preemptions.append("InCohortFairSharing")
  if "insufficient unused quota" in rec.msg_and_note.lower():
    state.has_insufficient_quota_pending = True


def scan_queues(rec: LogRecord, state: LogScanState) -> None:
  """Discovers ClusterQueues and LocalQueues named by the record."""
  d = rec.raw
  cq_name = _ref_name(d.get("clusterQueue") or d.get("clusterqueue"))
  if cq_name:
    state.cluster_queues.add(cq_name)
  lq = d.get("localQueue") or d.get("queue")
  if isinstance(lq, dict) and lq.get("name"):
    state.local_queues.add(
        _qualified(
            _ref_namespace(lq, _first_str(d, "namespace")), str(lq["name"])
        )
    )
  elif isinstance(lq, str) and lq:
    state.local_queues.add(lq)


def scan_entities(rec: LogRecord, state: LogScanState) -> None:
  """Discovers ResourceFlavors, Nodes and Workload object refs (with PodsReady evictions)."""
  d = rec.raw
  rf = d.get("resourceFlavor")
  if isinstance(rf, dict) and rf.get("name"):
    state.resource_flavors.add(str(rf["name"]))
  elif "flavor" in rec.logger and d.get("name"):
    state.resource_flavors.add(str(d["name"]))
  if "node-reconciler" in rec.logger and d.get("name"):
    state.nodes.add(str(d["name"]))
  obj = rec.named_obj
  if (
      obj is not None
      and obj.get("kind", "") == "Workload"
      and isinstance(obj["name"], str)
  ):
    state.workloads.add(_qualified(_ref_namespace(obj), obj["name"]))


@dataclasses.dataclass(frozen=True)
class _AuditRef:
  verb: str
  resource: str
  subresource: str
  res_name: str
  namespace: str = ""
  name: str = ""

  @property
  def short_name(self) -> str:
    """Object name; the last path segment of `resourceName` when no name field is known."""
    return self.name or self.res_name.rsplit("/", 1)[-1]


_AUDIT_MSG_RE = re.compile(
    r"\[Audit\s+([a-zA-Z]+)\s+([a-zA-Z0-9._/-]+)\]\s*(\S+)?"
)


def _audit_ref(rec: LogRecord) -> _AuditRef:
  """Verb / resource / subresource / target of an audit entry from its fields, methodName or `[Audit ...]` prefix."""
  d = rec.raw
  verb = _first_str(d, "verb")
  resource = _first_str(d, "resource")
  subresource = _first_str(d, "subresource")
  res_name = _first_str(d, "resourceName")
  namespace = _first_str(d, "namespace")
  name = _first_str(d, "name")
  if (not verb or not resource) and d.get("methodName"):
    parsed = log_envelopes.gcp_audit_ref(
        str(d["methodName"]), _first_str(d, "providerResourceName") or res_name
    )
    verb = verb or parsed.verb
    resource = resource or parsed.resource
    subresource = subresource or parsed.subresource
    namespace = namespace or parsed.namespace
    name = name or parsed.name
  if (not verb or not resource) and rec.msg.startswith("[Audit "):
    am = _AUDIT_MSG_RE.match(rec.msg)
    if am:
      msg_resource, _, msg_subresource = am.group(2).partition("/")
      verb = verb or am.group(1)
      resource = resource or msg_resource
      subresource = subresource or msg_subresource
      res_name = res_name or (am.group(3) or "")
  return _AuditRef(verb, resource, subresource, res_name, namespace, name)


def _audit_principal(d: dict[str, Any]) -> str:
  user_field = d.get("user")
  return str(
      d.get("principalEmail")
      or (
          user_field.get("username", "")
          if isinstance(user_field, dict)
          else user_field or ""
      )
  )


def _audit_response_code(d: dict[str, Any]) -> int | None:
  code = d.get("responseCode")
  if isinstance(code, str) and code.isdigit():
    return int(code)
  if isinstance(code, int) and not isinstance(code, bool):
    return code
  return None


def _audit_rejection(d: dict[str, Any]) -> str:
  """Formats the rejection code suffix for an audit row, or returns ''.

  `audit.k8s.io` rows carry the HTTP status, which reports a rejection from
  400 up. Cloud audit rows carry a `google.rpc.Code` instead, where every
  non-zero value (1-16) is an error; those are printed as `rpc_code=<N>`.

  Args:
    d: Normalised audit row.

  Returns:
    `' code=<N>'`, `' rpc_code=<N>'`, or `''`.
  """
  code = _audit_response_code(d)
  if code is None:
    return ""
  if code >= 400:
    return f" code={code}"
  if 0 < code < 100:
    return f" rpc_code={code}"
  return ""


def _nominal_quota_values(spec: Any) -> list[str]:
  """`<flavor>/<resource>=<nominalQuota>` for every quota a ClusterQueue `spec` body sets."""
  rows: list[str] = []
  groups = k8s_objects.as_dict(spec).get("resourceGroups")
  for group in k8s_objects.dict_items(groups):
    for flavor in k8s_objects.dict_items(group.get("flavors")):
      for res in k8s_objects.dict_items(flavor.get("resources")):
        if res.get("nominalQuota") is not None:
          rows.append(
              f"{flavor.get('name', '')}/{res.get('name', '')}"
              f"={res['nominalQuota']}"
          )
  return rows


_RFC3339_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d+))?"
    r"(Z|[+-]\d{2}:?\d{2})?$",
    re.IGNORECASE,
)
_NON_QUOTA_PATCH_LEAVES = (
    "/borrowingLimit",
    "/lendingLimit",
    "/coveredResources",
)


def _ts_sort_key(ts: str) -> tuple[int, int, int, str]:
  """Chronological sort key handling variable fractional-second RFC3339 strings."""
  m = _RFC3339_TS_RE.match(ts.strip())
  if not m:
    return (1, 0, 0, ts)
  base, frac, tz = m.groups()
  tz_iso = "+00:00" if not tz or tz.upper() == "Z" else tz
  if len(tz_iso) == 5:
    tz_iso = f"{tz_iso[:3]}:{tz_iso[3:]}"
  try:
    dt = datetime.datetime.fromisoformat(f"{base}{tz_iso}")
  except ValueError:
    return (1, 0, 0, ts)
  nanos = int((frac or "0")[:9].ljust(9, "0"))
  return (0, int(dt.timestamp()), nanos, ts)


def _extract_patch_nominal_quotas(val: Any, depth: int = 0) -> list[str]:
  """Extracts `nominalQuota` summaries from a JSON-patch `value` payload."""
  if depth > 4:
    return []
  if isinstance(val, dict):
    if "resourceGroups" in val:
      return _nominal_quota_values(val)
    if "flavors" in val:
      return _nominal_quota_values({"resourceGroups": [val]})
    if "resources" in val:
      return _nominal_quota_values({"resourceGroups": [{"flavors": [val]}]})
    if "nominalQuota" in val:
      rname = str(val.get("name") or "<resource>")
      return [f"{rname}={val['nominalQuota']}"]
  elif isinstance(val, list):
    out: list[str] = []
    for item in val:
      out.extend(_extract_patch_nominal_quotas(item, depth + 1))
    return out
  return []


def _append_quota_event(
    state: LogScanState,
    rec: LogRecord,
    ref: _AuditRef,
    kind: str,
    val: str,
    principal: str,
) -> None:
  """Appends one sequenced ClusterQueue quota event for chronological sorting."""
  state.audit_cq_quota_seq += 1
  state.audit_cq_quota_events.append((
      rec.ts_field,
      state.audit_cq_quota_seq,
      ref.short_name,
      kind,
      val,
      principal,
      ref.verb,
  ))


def _record_json_patch_op(
    op: dict[str, Any],
    rec: LogRecord,
    state: LogScanState,
    ref: _AuditRef,
    principal: str,
) -> None:
  """Buffers one RFC 6902 JSON-patch operation affecting ClusterQueue quota."""
  op_name = str(op.get("op") or "").lower()
  if op_name == "test":
    return
  path = str(op.get("path") or "")
  if "nominalQuota" in path:
    if op_name == "remove" and "value" not in op:
      val = "<removed>"
    elif op_name in ("move", "copy") and "value" not in op:
      val = f"<{op_name} from {op.get('from', '')}>"
    else:
      val = str(op.get("value"))
    _append_quota_event(state, rec, ref, "json_patch", val, principal)
    return
  if path != "/spec" and not path.startswith("/spec/resourceGroups"):
    return
  op_val = op.get("value")
  if path == "/spec" and isinstance(op_val, dict):
    body = ", ".join(_nominal_quota_values(op_val))
    if body:
      _append_quota_event(state, rec, ref, "body", body, principal)
    return
  if path == "/spec/resourceGroups" and isinstance(op_val, list):
    body = ", ".join(_nominal_quota_values({"resourceGroups": op_val}))
    if body:
      _append_quota_event(state, rec, ref, "body", body, principal)
    return
  if path.endswith(_NON_QUOTA_PATCH_LEAVES):
    return
  extracted = ", ".join(_extract_patch_nominal_quotas(op_val))
  if (
      extracted
      or op_name in ("remove", "move", "copy")
      or isinstance(op_val, (dict, list))
  ):
    kind = "partial_patch" if extracted else "clear_body"
    _append_quota_event(state, rec, ref, kind, extracted, principal)


def _record_quota_patches(
    rec: LogRecord, state: LogScanState, ref: _AuditRef
) -> None:
  """Buffers `clusterqueues` nominalQuota events for chronological resolution.

  Reads JSON-patch operations (`request` list) and create / merge-patch /
  update bodies (`spec`). Actual earlier-body diffing happens in
  `_resolve_quota_events` after sorting by parsed timestamp so newest-first log
  exports do not reverse the diff or misattribute principals.

  Args:
    rec: Audit record.
    state: Scan state to extend.
    ref: Parsed audit reference of `rec`.
  """
  d = rec.raw
  principal = _audit_principal(d)
  for op in k8s_objects.dict_items(d.get("request")):
    _record_json_patch_op(op, rec, state, ref, principal)
  body = ", ".join(_nominal_quota_values(d.get("spec")))
  if body:
    _append_quota_event(state, rec, ref, "body", body, principal)


def _resolve_quota_events(state: LogScanState) -> None:
  """Resolves buffered CQ quota events in chronological `(timestamp, seq)` order."""
  for ts, _, cq, kind, val, principal, verb in sorted(
      state.audit_cq_quota_events, key=lambda e: (_ts_sort_key(e[0]), e[1])
  ):
    if kind == "clear_body":
      state.audit_cq_quota_bodies.pop(cq, None)
      continue
    if kind == "partial_patch":
      state.audit_cq_quota_bodies.pop(cq, None)
      summary = f"{{{val}}}"
      state.audit_cq_quota_patches.append(f"{cq}={summary}")
      state.audit_cq_quota_patch_detail.append(
          (ts, cq, summary, principal, verb, False)
      )
      continue
    if kind == "json_patch":
      state.audit_cq_quota_bodies.pop(cq, None)
      state.audit_cq_quota_patches.append(f"{cq}={val}")
      state.audit_cq_quota_patch_detail.append(
          (ts, cq, val, principal, verb, True)
      )
      continue
    earlier = state.audit_cq_quota_bodies.get(cq)
    state.audit_cq_quota_bodies[cq] = val
    if verb == "create" or val == earlier:
      continue
    if earlier is None:
      summary, confirmed = f"{{{val}}}", False
    else:
      summary, confirmed = f"{{{val}}} (earlier body: {{{earlier}}})", True
    state.audit_cq_quota_patches.append(f"{cq}={summary}")
    state.audit_cq_quota_patch_detail.append(
        (ts, cq, summary, principal, verb, confirmed)
    )


def _record_indexed_job(
    rec: LogRecord, state: LogScanState, res_name: str
) -> None:
  """Job / JobSet creations with backoffLimitPerIndex set and maxFailedIndexes unset."""
  spec_d = rec.raw["spec"]
  target = str(res_name or rec.raw.get("name") or "")
  candidates: list[tuple[str, dict[str, Any]]] = [(target, spec_d)]
  for rj in k8s_objects.dict_items(spec_d.get("replicatedJobs")):
    rj_spec = k8s_objects.as_dict(rj.get("template")).get("spec")
    if isinstance(rj_spec, dict):
      candidates.append(
          (f"{target}:replicatedJob[{rj.get('name', '')}]", rj_spec)
      )
  for ref_label, sub_spec in candidates:
    if (
        sub_spec.get("backoffLimitPerIndex") is not None
        and sub_spec.get("maxFailedIndexes") is None
    ):
      state.audit_indexed_jobs_no_max_failed.append(
          f"{ref_label} (completionMode={sub_spec.get('completionMode')},"
          f" backoffLimitPerIndex={sub_spec.get('backoffLimitPerIndex')},"
          " maxFailedIndexes=unset)"
      )


def _scan_audit_config_changes(
    rec: LogRecord, state: LogScanState, ref: _AuditRef
) -> None:
  """Namespace deletions, nominalQuota writes and Indexed Job creations seen in the audit trail (rejected calls are skipped)."""
  d = rec.raw
  if _audit_rejection(d):
    return
  if ref.verb == "delete" and ref.resource == "namespaces" and ref.short_name:
    code = _audit_response_code(d)
    state.audit_namespace_deletions.setdefault(
        ref.short_name, (rec.ts_field, "" if code is None else str(code))
    )
  if (
      ref.verb in ("create", "patch", "update")
      and ref.resource == "clusterqueues"
      and not ref.subresource
  ):
    _record_quota_patches(rec, state, ref)
  if (
      ref.verb == "create"
      and ref.resource in ("jobs", "jobsets")
      and isinstance(d.get("spec"), dict)
  ):
    _record_indexed_job(rec, state, ref.res_name)


_MAX_AUDIT_LINE = 1400


def _replace_audit_spec_segment(msg: str, spec_json: str) -> str:
  """Replaces the first ` spec=...` segment up to the next audit field or end."""
  start = msg.find(" spec=")
  if start < 0:
    return f"{msg} spec={spec_json}"
  tail_start = start + len(" spec=")
  end = len(msg)
  for marker in (" annotations=", " labels=", " status="):
    pos = msg.find(marker, tail_start)
    if 0 <= pos < end:
      end = pos
  return f"{msg[:start]} spec={spec_json}{msg[end:]}"


def _audit_action_suffix(d: dict[str, Any], msg: str) -> str:
  """Response code of a rejected call, principal and request body, where `msg` does not already carry them."""
  suffix = _audit_rejection(d)
  principal = _audit_principal(d)
  if principal and "principal=" not in msg:
    suffix += f" principal={principal}"
  if isinstance(d.get("request"), (dict, list)) and "request=" not in msg:
    body = json.dumps(log_envelopes.redact_env_values(d["request"]))
    suffix += f" request={body[:400]}"
  return suffix


def _audit_action_line(rec: LogRecord) -> str:
  """Builds the audit summary text with spec, status code, principal, and request body.

  Container `env` values are redacted. The message is cut, never the
  trailing fields.

  Args:
    rec: Audit record.

  Returns:
    Redacted, length-bounded audit action summary line.
  """
  d = rec.raw
  msg = rec.msg
  if isinstance(d.get("spec"), dict):
    spec_json = json.dumps(
        log_envelopes.redact_env_values(d["spec"]), sort_keys=True
    )[:1200]
    msg = _replace_audit_spec_segment(msg, spec_json)
  msg = log_envelopes.redact_env_text(msg)
  suffix = _audit_action_suffix(d, msg)
  return msg[: max(0, _MAX_AUDIT_LINE - len(suffix))] + suffix


def _is_listed_audit_action(ref: _AuditRef) -> bool:
  """Mutations of audited resources, minus subresources and add-on / CA-bundle ConfigMaps."""
  if (
      ref.verb not in ("create", "delete", "patch", "update")
      or ref.subresource
      or ref.resource not in _AUDITED_RESOURCES
  ):
    return False
  return ref.resource != "configmaps" or not (
      report_output.is_managed_addon_namespace(ref.namespace)
      or ref.short_name == "kube-root-ca.crt"
  )


def _scan_audit_actions(
    rec: LogRecord, state: LogScanState, ref: _AuditRef
) -> None:
  """Workload status patches and deduplicated, capped audit mutations.

  A rejected call is listed with its response code and gets no fact id. A
  change of the admission graph (a deletion, or any mutation of a
  `_GRAPH_CONFIG_RESOURCES` object) is listed once per call, so two updates
  of one object at different times are both kept; other audited mutations
  (Node, Job, Workload writes) collapse when the same body repeats.

  Args:
    rec: Audit record.
    state: Scan state to extend.
    ref: Parsed audit reference of `rec`.
  """
  d = rec.raw
  rejection = _audit_rejection(d)
  if (
      ref.resource == "workloads"
      and ref.subresource == "status"
      and (d.get("status") or " status=" in rec.msg)
  ):
    if not rejection:
      state.workload_status_by_name[ref.res_name] = str(rec.msg)[:850]
    return
  if not _is_listed_audit_action(ref):
    return
  graph_change = ref.verb == "delete" or ref.resource in _GRAPH_CONFIG_RESOURCES
  line = _audit_action_line(rec)
  ts = rec.ts_field
  dedup_audit_key = f"{ts if graph_change else ''}{rejection} {line[:260]}"
  if dedup_audit_key in state.seen_audit:
    return
  state.seen_audit.add(dedup_audit_key)
  if ref.verb == "delete":
    if state.audit_delete_count >= _MAX_AUDIT_DELETIONS:
      state.omitted_audit_deletions += 1
      return
    state.audit_delete_count += 1
  else:
    if state.audit_non_delete_count >= _MAX_AUDIT_ACTIONS:
      state.omitted_audit += 1
      return
    state.audit_non_delete_count += 1
  audit_key = (
      f"audit:{ref.verb}:{ref.resource}"
      if graph_change and not rejection
      else None
  )
  state.audit_actions.append((audit_key, (f"{ts} " if ts else "") + line))


def scan_audit(rec: LogRecord, state: LogScanState) -> None:
  """Audit entries: configuration changes and the capped `audit_resource_actions` list."""
  if not rec.is_audit:
    return
  ref = _audit_ref(rec)
  _scan_audit_config_changes(rec, state, ref)
  _scan_audit_actions(rec, state, ref)


def _is_housekeeping_event(rec: LogRecord) -> bool:
  """Records about Kueue's optional components, add-on namespaces or controller lifecycle chatter."""
  obj_text = json.dumps(rec.obj) if rec.obj is not None else ""
  noise_probe = f"{rec.combined_signal} | {rec.logger} | {obj_text}".lower()
  if "kueueviz" in noise_probe or "certwatcher" in noise_probe:
    return True
  if rec.obj is not None and report_output.is_managed_addon_namespace(
      _ref_namespace(rec.obj)
  ):
    return True
  return any(benign in rec.combined_signal for benign in _BENIGN_SIGNALS)


def _is_key_event(rec: LogRecord) -> bool:
  """Errors, Warnings, external-emitter Events and known decision messages."""
  signal = rec.combined_signal
  low = signal.lower()
  return (
      rec.reason in _KEY_EVENT_REASONS
      or rec.ev_type == "Warning"
      or is_external_emitter(rec.raw)
      or rec.level in ("error", "fatal", "panic")
      or bool(rec.err)
      or any(marker in signal for marker in _KEY_EVENT_MARKERS)
      or any(marker in low for marker in _KEY_EVENT_MARKERS_LOWER)
  )


def _key_event_summary(rec: LogRecord) -> tuple[str, str]:
  """Returns `(summary_line, detail)` for a key event."""
  d = rec.raw
  obj_ref = ""
  obj = rec.named_obj
  if obj is not None:
    obj_ref = f"[{obj.get('kind', 'Object')}/{obj.get('name')}] "
  elif isinstance(rec.workload, dict) and rec.workload.get("name"):
    obj_ref = f"[Workload/{rec.workload.get('name')}] "
  lq_detail = ""
  if isinstance(d.get("localQueue"), dict) and "localQueue" in rec.msg:
    lq_detail = f"localQueue={json.dumps(d.get('localQueue'))}"
  detail = (
      rec.note
      or rec.err
      or lq_detail
      or (
          json.dumps(log_envelopes.redact_env_values(d["spec"]))[:500]
          if d.get("spec")
          else ""
      )
  )
  emitter_tag = (
      f" (emitter: {event_emitter(d)})" if is_external_emitter(d) else ""
  )
  summary_line = (
      f"{obj_ref}{rec.reason or rec.logger}: {rec.msg}"
      + (f" — {detail}" if detail and detail not in rec.msg else "")
      + emitter_tag
  )
  return summary_line, detail


def scan_key_events(rec: LogRecord, state: LogScanState) -> None:
  """Selects the deduplicated, capped `key_errors_and_events` entries."""
  if rec.is_audit or _is_housekeeping_event(rec) or not _is_key_event(rec):
    return
  summary_line, detail = _key_event_summary(rec)
  dedup_key = summary_line[:220]
  if dedup_key in state.seen_events:
    return
  state.seen_events.add(dedup_key)
  if len(state.key_events) >= _MAX_KEY_EVENTS:
    state.omitted_events += 1
    return
  # Routine optimistic-concurrency noise is listed but not tracked as a fact.
  routine = any(
      marker in rec.combined_signal for marker in _ROUTINE_ERROR_MARKERS
  )
  group_msg = (
      detail if (detail and rec.msg in ("", "Event occurred")) else rec.msg
  )
  if routine:
    fact_key = ""
  else:
    fact_key = report_output.fact_group_key(
        "logerr", "", rec.reason or rec.logger, group_msg
    )
  state.key_events.append((fact_key, summary_line[:450]))


def scan_signatures(rec: LogRecord, state: LogScanState) -> None:
  """Matches the controller-message signature table against the record's message, note and error."""
  if rec.is_audit:
    return
  log_signatures.scan_signature_text(
      rec.combined_signal, state.signature_hits, rec.ts
  )


RecordScanner = Callable[[LogRecord, LogScanState], None]

# Applied to every parsed record, in this order.
RECORD_SCANNERS: tuple[RecordScanner, ...] = (
    scan_source_and_window,
    scan_config,
    scan_workload_ref,
    scan_admission,
    scan_pods_ready,
    scan_local_queue_missing,
    scan_fair_sharing,
    scan_queues,
    scan_entities,
    scan_audit,
    scan_key_events,
    scan_signatures,
)


# ---------------------------------------------------------------------------
# Fact emitters
# ---------------------------------------------------------------------------

Fact = tuple[str | None, str]


def emit_log_coverage(state: LogScanState) -> list[Fact]:
  """Evidence coverage of the log window, emitted first so the reader knows which questions this source can answer."""
  source_questions = (
      (
          "kueue-controller",
          (
              "Kueue's own admission, preemption, requeue and config-loading"
              " decisions"
          ),
      ),
      ("audit", "who created/patched/deleted which object and when"),
      (
          "kubernetes-event",
          "scheduler/kubelet outcome per pod and Kueue Events per Workload",
      ),
  )
  counts = state.source_counts
  absent_sources = [
      f"{s} (answers: {q})" for s, q in source_questions if not counts.get(s)
  ]
  return [(
      "",
      (
          f"LOG_COVERAGE: lines={counts['total']}"
          f" (kueue-controller={counts['kueue-controller']},"
          f" audit={counts['audit']},"
          f" kubernetes-event={counts['kubernetes-event']},"
          f" unstructured={counts['unstructured']});"
          f" window={state.window_start or '?'} .. {state.window_end or '?'};"
          f" absent sources={absent_sources or 'none'}. Logs show decisions and"
          " their stated reasons, not declared configuration: nominalQuota,"
          " borrowingLimit, nodeLabels and other spec fields are only"
          " observable from the objects themselves (snapshot) or from audit"
          " patch bodies. A question that needs an absent source cannot be"
          " settled from this log; name the source when reporting it as not"
          " determinable."
      ),
  )]


def emit_tas_level(state: LogScanState) -> list[Fact]:
  return [
      (
          f"logfact:tas-level:{level}",
          (
              "TAS_LOG_FACT: controller logged 'no topology domains at level:"
              f" {level}'"
              " (https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/)."
              " It is emitted when the TAS snapshot for the ResourceFlavor has"
              " zero domains at that level: no node both matches the flavor's"
              " nodeLabels and carries every label key listed in"
              " Topology.spec.levels (and, where the scheduler gate applies,"
              " is Ready and schedulable)."
          ),
      )
      for level in sorted(state.topology_levels_without_domains)
  ]


def emit_namespace_delete(state: LogScanState) -> list[Fact]:
  """`delete namespaces` requests that the audit log does not show as rejected."""
  facts: list[Fact] = []
  for ns_name, (ts, code) in sorted(state.audit_namespace_deletions.items()):
    ts_part = f" at {ts}" if ts else ""
    if code:
      outcome_part = f" (response code {code})"
    else:
      outcome_part = (
          " (whether the request succeeded is not determinable from this entry)"
      )
    facts.append((
        f"logfact:namespace-delete:{ns_name}",
        (
            "AUDIT_LOG_FACT: the audit log records a `delete namespaces`"
            f" request for namespace `{ns_name}`{ts_part}{outcome_part}. A"
            " completed namespace deletion removes every namespaced object in"
            " it (Jobs, Workloads, LocalQueues, Pods)."
        ),
    ))
  return facts


def emit_unknown_field(state: LogScanState) -> list[Fact]:
  return [
      (
          f"logfact:unknown-field:{field}",
          (
              "CONTROLLER_LOG_FACT: controller logged 'strict decoding error:"
              f' unknown field "{field}"\' while loading '
              "KueueConfiguration"
              " (https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/, "
              "https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/)."
          ),
      )
      for field in sorted(state.strict_unknown_fields)
  ]


def emit_unavailable_resource(state: LogScanState) -> list[Fact]:
  return [
      (
          f"logfact:unavailable-resource:{res_name}",
          (
              f"CONTROLLER_LOG_FACT: controller reported 'resource {res_name}"
              " unavailable in ClusterQueue' (the resource is requested by a"
              " podset but is not covered by any resourceGroup of the"
              " ClusterQueue)."
          ),
      )
      for res_name in sorted(state.unavailable_resources)
  ]


def emit_webhook_timeout(state: LogScanState) -> list[Fact]:
  """Webhook call failures with a logged timeout, connection-level cause, or other logged error."""
  facts: list[Fact] = [
      (
          f"logfact:webhook-timeout:{wh_target}",
          (
              "CONTROLLER_LOG_FACT: logs record 'failed calling webhook"
              f' "{wh_target}"\' with timeout / context deadline exceeded —'
              " API server calls to the admission webhook endpoint did not"
              " complete before the webhook timeout."
          ),
      )
      for wh_target in sorted(state.webhook_timeout_targets)
  ]
  for wh_target, causes in sorted(state.webhook_connection_errors.items()):
    if wh_target in state.webhook_timeout_targets:
      continue
    facts.append((
        f"logfact:webhook-timeout:{wh_target}",
        (
            "CONTROLLER_LOG_FACT: logs record 'failed calling webhook"
            f' "{wh_target}"\' with {" / ".join(sorted(causes))} — API server'
            " calls to the admission webhook endpoint ended with a"
            " connection-level error; no timeout is logged for them."
        ),
    ))
  for wh_target, causes in sorted(state.webhook_other_errors.items()):
    if (
        wh_target in state.webhook_timeout_targets
        or wh_target in state.webhook_connection_errors
    ):
      continue
    facts.append((
        f"logfact:webhook-error:{wh_target}",
        (
            "CONTROLLER_LOG_FACT: logs record 'failed calling webhook"
            f' "{wh_target}"\' with logged error:'
            f" {'; '.join(sorted(causes)[:3])}."
        ),
    ))
  return facts


def emit_api_pressure(state: LogScanState) -> list[Fact]:
  return [
      (
          f"logfact:api-pressure:{sig_side}:{sig_name}",
          (
              f"CONTROLLER_LOG_FACT: logs record '{sig_name}' (source side:"
              f" {sig_side} — {_API_PRESSURE_SIDE_NOTE[sig_side]})."
          ),
      )
      for sig_side, sig_name in sorted(state.api_pressure_signals)
  ]


def emit_in_cohort_preemption(state: LogScanState) -> list[Fact]:
  if not state.in_cohort_preemptions:
    return []
  uniq_paths = sorted(set(state.in_cohort_preemptions))[:4]
  return [(
      "logfact:in-cohort-preemption-volume",
      (
          f"CONTROLLER_LOG_FACT: logs record {len(state.in_cohort_preemptions)}"
          " InCohortFairSharing preemption entries (preemptor->preemptee"
          f" paths={uniq_paths}). Each preemption updates the Workload status"
          " and emits an Event"
          " (https://kueue.sigs.k8s.io/docs/concepts/preemption/); Fair"
          " Sharing preemption works with withinClusterQueue and"
          " reclaimWithinCohort"
          " (https://kueue.sigs.k8s.io/docs/concepts/preemption/)."
      ),
  )]


def emit_client_throttling(state: LogScanState) -> list[Fact]:
  if not state.client_throttling_count:
    return []
  return [(
      "logfact:client-throttling-volume",
      (
          f"CONTROLLER_LOG_FACT: logs record {state.client_throttling_count}"
          " 'Waited for ... due to client-side throttling, not priority and"
          " fairness' delays. This message is emitted by client-go when a"
          " request waits on Kueue's own rate limiter"
          " (KueueConfiguration.clientConnection.qps/burst,"
          " https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/,"
          " https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/)."
      ),
  )]


def emit_jobset_integration(state: LogScanState) -> list[Fact]:
  frameworks = state.config_frameworks
  if (
      frameworks is None
      or "jobset.x-k8s.io/jobset" in frameworks
      or not state.empty_lq_workloads
  ):
    return []
  return [(
      "logfact:jobset-integration-disabled",
      (
          "CONTROLLER_LOG_FACT: the 'Configuration loaded' payload lists"
          f" integrations.frameworks={sorted(frameworks)} without"
          " 'jobset.x-k8s.io/jobset', while child Jobs"
          f" {sorted(state.empty_lq_workloads)} are reconciled by the batch/job"
          " integration with an empty queue-name label (localQueue={'name':"
          " ''}) and marked Inadmissible. The enabled set is"
          " KueueConfiguration.integrations.frameworks"
          " (https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/,"
          " https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/)."
      ),
  )]


_PODS_READY_REASON_NOTES = {
    "WaitForStart": (
        " For eviction metrics,"
        " https://kueue.sigs.k8s.io/docs/reference/metrics/ defines"
        ' underlying_cause "WaitForStart" as: "the pods have not been ready'
        ' since admission, or the workload is not admitted".'
    ),
    "WaitForScheduling": (
        ' Per "Unscheduled timeout" in'
        " https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/,"
        ' "Workloads waiting for scheduling report PodsReady=False with reason'
        ' WaitForScheduling."'
    ),
}


def emit_waiting_pods_ready(state: LogScanState) -> list[Fact]:
  """References whose latest logged PodsReady status is False, with the logged reason."""
  stuck_waiting = sorted(
      state.waiting_pods_ready_workloads - state.pods_ready_true_workloads
  )
  facts: list[Fact] = []
  for wl_wait in stuck_waiting:
    reason = state.pods_ready_false_reason.get(wl_wait, "")
    reason_note = _PODS_READY_REASON_NOTES.get(reason, "")
    facts.append((
        f"logfact:waiting-pods-ready:{wl_wait}",
        (
            "CONTROLLER_LOG_FACT: the job reconciler logged 'Updating the"
            " PodsReady condition' with status=False"
            + (f" (reason={reason})" if reason else "")
            + f" for '{wl_wait}' and no later status=True for the same"
            " reference"
            " (https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/)."
            + reason_note
        ),
    ))
  return facts


def _partition_quota_provenance(
    details: list[tuple[str, str, str, str, str, bool]],
) -> tuple[
    dict[str, tuple[str, str, str]],
    dict[str, set[str]],
    dict[str, tuple[str, str, str]],
]:
  """Splits audit quota entries into confirmed changes and unconfirmed bodies."""
  confirmed_by_cq: dict[str, tuple[str, str, str]] = {}
  principals_by_cq: dict[str, set[str]] = {}
  unconfirmed_by_cq: dict[str, tuple[str, str, str]] = {}
  for ts_p, cq_p, val_p, who_p, verb_p, confirmed in sorted(
      details, key=lambda t: _ts_sort_key(t[0])
  ):
    if confirmed:
      confirmed_by_cq[cq_p] = (ts_p, val_p, verb_p)
      principals_by_cq[cq_p] = {who_p or "<unknown principal>"}
      unconfirmed_by_cq.pop(cq_p, None)
    else:
      unconfirmed_by_cq[cq_p] = (ts_p, val_p, verb_p)
  return confirmed_by_cq, principals_by_cq, unconfirmed_by_cq


def _format_quota_provenance_lead(
    confirmed_by_cq: dict[str, tuple[str, str, str]],
    principals_by_cq: dict[str, set[str]],
    unconfirmed_by_cq: dict[str, tuple[str, str, str]],
) -> str:
  """Formats the lead sentence separating confirmed updates from first-seen bodies."""
  unconf_rows = [
      f"{cq_p}: {verb} body carried nominalQuota={val}"
      + (f" at {ts_p}" if ts_p else "")
      for cq_p, (ts_p, val, verb) in sorted(unconfirmed_by_cq.items())
  ]
  if not confirmed_by_cq:
    verbs = "/".join(
        sorted({verb for _, _, verb in unconfirmed_by_cq.values()})
    )
    return (
        f"AUDIT_LOG_FACT: audit log records clusterqueues.{verbs} request"
        " bodies carrying nominalQuota while workloads emit Pending"
        " ('insufficient unused quota'); no earlier body is in this log, so"
        " whether nominalQuota changed is not determinable. Per ClusterQueue:"
        f" {'; '.join(unconf_rows[:8])}. "
    )
  verbs = "/".join(sorted({verb for _, _, verb in confirmed_by_cq.values()}))
  prov_rows = [
      f"{cq_p}: latest"
      + (" confirmed" if cq_p in unconfirmed_by_cq else "")
      + f" nominalQuota {verb}={val}"
      + (f" at {ts_p}" if ts_p else "")
      + f" by {sorted(principals_by_cq[cq_p])}"
      for cq_p, (ts_p, val, verb) in sorted(confirmed_by_cq.items())
  ]
  lead = (
      f"AUDIT_LOG_FACT: audit log records clusterqueues.{verbs} updates to"
      " nominalQuota while workloads emit Pending ('insufficient unused"
      f" quota'). Per ClusterQueue: {'; '.join(prov_rows[:8])}. "
  )
  if unconf_rows:
    lead += (
        "Other clusterqueues writes whose request body carried nominalQuota"
        " without a comparable earlier body in this log (whether nominalQuota"
        f" changed is not determinable): {'; '.join(unconf_rows[:8])}. "
    )
  return lead


def emit_quota_patch_provenance(state: LogScanState) -> list[Fact]:
  """Per-ClusterQueue provenance for confirmed nominalQuota changes and first-seen bodies."""
  if not (
      state.audit_cq_quota_patches and state.has_insufficient_quota_pending
  ):
    return []
  confirmed_by_cq, principals_by_cq, unconfirmed_by_cq = (
      _partition_quota_provenance(state.audit_cq_quota_patch_detail)
  )
  lead = _format_quota_provenance_lead(
      confirmed_by_cq, principals_by_cq, unconfirmed_by_cq
  )
  seen_cqs = set(confirmed_by_cq) | set(unconfirmed_by_cq)
  admitted_without_audit = sorted(set(state.admitted_count_by_cq) - seen_cqs)
  unpatched_note = ""
  if admitted_without_audit:
    unpatched_note = (
        "ClusterQueues that admitted workloads in this log but have no"
        f" nominalQuota write in the audit trail: {admitted_without_audit}. "
    )
  return [(
      "logfact:audit-cq-quota-patch",
      lead
      + unpatched_note
      + "Per https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/,"
      " nominalQuota is the quantity of this resource that is available for a"
      " ClusterQueue at a specific time; compare these values with"
      " COHORT_RESOURCE_ARITHMETIC when a snapshot is available.",
  )]


def emit_admission_volume(state: LogScanState) -> list[Fact]:
  """Summarises admitted resourceUsage volume per ClusterQueue and flavor."""
  if not state.admitted_usage:
    return []
  by_cq: dict[str, list[str]] = {}
  for (cq_a, fl_a, res_a), total_a in sorted(state.admitted_usage.items()):
    by_cq.setdefault(cq_a, []).append(
        f"{res_a}@{fl_a or '<no flavor>'}={report_output.fmt_quantity(total_a, res_a)}"
    )
  rows = [
      f"{cq_a}(admissions={state.admitted_count_by_cq.get(cq_a, 0)}):"
      f" {', '.join(parts)}"
      for cq_a, parts in sorted(by_cq.items())
  ]
  return [(
      "logfact:admission-volume",
      (
          "ADMISSION_VOLUME_BY_CLUSTERQUEUE: summed resourceUsage from"
          " 'Workload successfully admitted and assigned flavors'"
          " (https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/) over this"
          f" log window, per ClusterQueue and flavor: {'; '.join(rows[:10])}."
          " This is admitted volume over time, not current reservation; it"
          " shows which ClusterQueues consumed each flavor's quota."
      ),
  )]


def emit_signatures(state: LogScanState) -> list[Fact]:
  """One fact per matched controller-message signature (mechanism_hint + next_check + citation)."""
  return log_signatures.emit_signature_facts(state.signature_hits)


def emit_indexed_jobs(state: LogScanState) -> list[Fact]:
  if not state.audit_indexed_jobs_no_max_failed:
    return []
  return [(
      "logfact:audit-indexed-job-backoff",
      (
          "AUDIT_LOG_FACT: audit log records creation of Indexed Job(s)"
          f" {state.audit_indexed_jobs_no_max_failed[:2]} with"
          " backoffLimitPerIndex set and no maxFailedIndexes "
          "(Kubernetes defaults spec.backoffLimit=2147483647 when"
          " backoffLimitPerIndex is set). Under batch/v1 semantics a failed"
          " index that has exhausted "
          "backoffLimitPerIndex is not retried while remaining indexes keep"
          " running, so the Job stays active "
          "(https://kubernetes.io/docs/concepts/workloads/controllers/job/,"
          " https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/)."
      ),
  )]


FactEmitter = Callable[[LogScanState], list[Fact]]

# Produces `derived_log_facts`, in this order (LOG_COVERAGE always first).
LOG_FACT_EMITTERS: tuple[FactEmitter, ...] = (
    emit_log_coverage,
    emit_tas_level,
    emit_namespace_delete,
    emit_unknown_field,
    emit_unavailable_resource,
    emit_webhook_timeout,
    emit_api_pressure,
    emit_in_cohort_preemption,
    emit_client_throttling,
    emit_jobset_integration,
    emit_waiting_pods_ready,
    emit_quota_patch_provenance,
    emit_admission_volume,
    emit_indexed_jobs,
    emit_signatures,
)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def scan_lines(lines: list[str]) -> LogScanState:
  """Runs the text scanner on every line and the record scanners on every parsed JSON object."""
  state = LogScanState()
  for raw in lines:
    raw_str = raw.strip()
    if raw_str:
      state.source_counts["total"] += 1
      if not raw_str.startswith("{"):
        state.source_counts["unstructured"] += 1
    scan_text_signals(raw_str, state)
    if not raw_str.startswith("{"):
      if raw_str:
        log_signatures.scan_signature_text(raw_str, state.signature_hits)
      continue
    try:
      d = json.loads(raw_str)
    except (json.JSONDecodeError, RecursionError):
      state.source_counts["unstructured"] += 1
      continue
    if not isinstance(d, dict):
      continue
    rec = LogRecord.from_dict(d)
    for scanner in RECORD_SCANNERS:
      scanner(rec, state)
  _resolve_quota_events(state)
  return state


def _finalize_sections(state: LogScanState) -> None:
  """Appends workload status patches and truncation trailers to capped sections."""
  status_cap = _MAX_AUDIT_ACTIONS_WITH_STATUS + state.audit_delete_count
  for wl_stat in state.workload_status_by_name.values():
    if (
        wl_stat[:220] not in state.seen_audit
        and len(state.audit_actions) < status_cap
    ):
      state.audit_actions.append((None, wl_stat[:850]))
  # Untagged trailer lines so the reader knows the lists are capped (they
  # survive `tag_log_facts`, which rebuilds the sections from these tuples).
  if state.omitted_events:
    state.key_events.append((
        "",
        (
            f"... {state.omitted_events} more distinct error/Warning entries"
            f" omitted (first {_MAX_KEY_EVENTS} kept); the complete timeline is"
            " in full_report_file"
        ),
    ))
  if state.omitted_audit:
    state.audit_actions.append((
        None,
        (
            f"... {state.omitted_audit} more distinct non-delete audit entries"
            f" omitted (first {_MAX_AUDIT_ACTIONS} kept); the complete timeline"
            " is in full_report_file"
        ),
    ))
  if state.omitted_audit_deletions:
    state.audit_actions.append((
        None,
        (
            f"... {state.omitted_audit_deletions} more distinct audit deletion"
            f" entries omitted (first {_MAX_AUDIT_DELETIONS} kept); the"
            " complete timeline is in full_report_file"
        ),
    ))


def extract_derived_log_diagnostics(
    lines: list[str], version_info: dict[str, Any] | None = None
) -> dict[str, Any]:
  """Extracts structured entity inventory, key diagnostic signals, and source invariants from log lines."""
  state = scan_lines(lines)
  _finalize_sections(state)
  log_facts: list[Fact] = []
  for emitter in LOG_FACT_EMITTERS:
    log_facts.extend(emitter(state))
  # Most decision-relevant sections first: agent harnesses often show only the
  # head (and tail) of a command's stdout.
  diag: dict[str, Any] = {
      "derived_log_facts": [t for _, t in log_facts],
      "key_errors_and_events": [t for _, t in state.key_events],
      "discovered_entities": {
          "workloads": sorted(state.workloads),
          "cluster_queues": sorted(state.cluster_queues),
          "local_queues": sorted(state.local_queues),
          "resource_flavors": sorted(state.resource_flavors),
          "namespaces": sorted(state.namespaces),
          "nodes": sorted(state.nodes),
      },
  }
  if state.config_excerpt:
    diag["controller_config_excerpt"] = state.config_excerpt
  if state.audit_actions:
    diag["audit_resource_actions"] = [t for _, t in state.audit_actions]
  diag["active_api_schema_reference"] = (
      kueue_schema.get_active_schema_reference(
          state.discovered_kinds, version_info=version_info
      )
  )
  # Side channel for fact ids (consumed and removed by `tag_log_facts`).
  diag["_keyed"] = {
      "derived_log_facts": log_facts,
      "key_errors_and_events": state.key_events,
      "audit_resource_actions": state.audit_actions,
  }
  return diag
