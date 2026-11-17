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
import json
import re
from typing import Any, Callable

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
_FRAMEWORKS_JSON_RE = re.compile(r'"frameworks"\s*:\s*\[([^\]]*)\]')


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
# said it; it does not assert why.
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
        r"unable to handle the request|\b503\b",
    ),
    (
        "apiserver",
        "HTTP 429 / too many requests",
        r"too many requests|\b429\b",
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


def _ref_namespace(value: Any, default: Any = "") -> Any:
  """Namespace of a klog ObjectRef dict; `default` for strings and other shapes."""
  if isinstance(value, dict):
    return value.get("namespace", default)
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
      wl_full = _qualified(wl.get("namespace", ""), str(wl["name"]))
    elif isinstance(wl, str) and wl:
      wl_full = wl
    # The job reconciler logs with `job=<ns>/<name>` (ReconcileGenericJob),
    # not `workload`.
    job = d.get("job")
    job_ref = ""
    if isinstance(job, str):
      job_ref = job
    elif isinstance(job, dict) and job.get("name"):
      job_ref = _qualified(job.get("namespace", ""), str(job.get("name")))
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
    return self.raw.get("kind") == "Event" or bool(
        self.raw.get("involvedObject") and self.reason
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
  empty_lq_workloads: set[str] = dataclasses.field(default_factory=set)
  in_cohort_preemptions: list[str] = dataclasses.field(default_factory=list)
  has_insufficient_quota_pending: bool = False
  # Audit trail.
  audit_actions: list[tuple[str | None, str]] = dataclasses.field(
      default_factory=list
  )
  seen_audit: set[str] = dataclasses.field(default_factory=set)
  omitted_audit: int = 0
  workload_status_by_name: dict[str, str] = dataclasses.field(
      default_factory=dict
  )
  audit_namespace_deletions: dict[str, str] = dataclasses.field(
      default_factory=dict
  )
  audit_cq_quota_patches: list[str] = dataclasses.field(default_factory=list)
  audit_cq_quota_patch_detail: list[tuple[str, str, str, str]] = (
      dataclasses.field(default_factory=list)
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
_WEBHOOK_TIMEOUT_RE = re.compile(
    r'failed calling webhook\s+\\?"([^"\\]+)\\?".*?(?:context deadline'
    r" exceeded|timeout|connection refused|EOF)",
    re.IGNORECASE,
)


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
  wh_m = _WEBHOOK_TIMEOUT_RE.search(text)
  if wh_m:
    state.webhook_timeout_targets.add(wh_m.group(1))
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
  adm_cq = d.get("clusterQueue")
  adm_cq_name = (
      str(adm_cq.get("name")) if isinstance(adm_cq, dict) else str(adm_cq or "")
  )
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
        _qualified(lq.get("namespace", d.get("namespace", "")), str(lq["name"]))
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
  if obj is not None and obj.get("kind", "") == "Workload":
    wl_ref_obj = _qualified(obj.get("namespace", ""), obj.get("name", ""))
    state.workloads.add(wl_ref_obj)


@dataclasses.dataclass(frozen=True)
class _AuditRef:
  verb: str
  resource: str
  subresource: str
  res_name: str


_AUDIT_MSG_RE = re.compile(
    r"\[Audit\s+([a-zA-Z]+)\s+([a-zA-Z0-9._/-]+)\]\s*(\S+)?"
)


def _audit_ref(rec: LogRecord) -> _AuditRef:
  """Verb / resource / subresource / name of an audit entry from its fields, methodName or `[Audit ...]` prefix."""
  d = rec.raw
  verb = _first_str(d, "verb")
  resource = _first_str(d, "resource")
  res_name = _first_str(d, "resourceName")
  if (not verb or not resource) and d.get("methodName"):
    parts = str(d.get("methodName")).split(".")
    if len(parts) >= 3:
      verb = verb or parts[-1]
      resource = resource or parts[-2]
  if (not verb or not resource) and rec.msg.startswith("[Audit "):
    am = _AUDIT_MSG_RE.match(rec.msg)
    if am:
      verb = verb or am.group(1)
      resource = resource or am.group(2)
      res_name = res_name or (am.group(3) or "")
  return _AuditRef(verb, resource, _first_str(d, "subresource"), res_name)


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


def _record_quota_patches(
    rec: LogRecord, state: LogScanState, res_name: str
) -> None:
  """nominalQuota operations of a `clusterqueues.patch` audit entry, with the principal that issued them."""
  d = rec.raw
  cq_short = res_name.rsplit("/", 1)[-1] if res_name else _first_str(d, "name")
  principal = _audit_principal(d)
  for op in d.get("request") or []:
    if isinstance(op, dict) and "nominalQuota" in str(op.get("path") or ""):
      state.audit_cq_quota_patches.append(f"{cq_short}={op.get('value')}")
      state.audit_cq_quota_patch_detail.append(
          (rec.ts_field, cq_short, str(op.get("value")), principal)
      )


def _record_indexed_job(
    rec: LogRecord, state: LogScanState, res_name: str
) -> None:
  """Job / JobSet creations with backoffLimitPerIndex set and maxFailedIndexes unset."""
  spec_d = rec.raw["spec"]
  target = str(res_name or rec.raw.get("name") or "")
  candidates: list[tuple[str, dict[str, Any]]] = [(target, spec_d)]
  for rj in spec_d.get("replicatedJobs") or []:
    if isinstance(rj, dict):
      rj_spec = (
          (rj.get("template") or {}).get("spec")
          if isinstance(rj.get("template"), dict)
          else None
      )
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
  """Namespace deletions, nominalQuota patches and Indexed Job creations seen in the audit trail."""
  d = rec.raw
  if (
      ref.verb == "delete"
      and ref.resource == "namespaces"
      and (d.get("name") or ref.res_name)
  ):
    state.audit_namespace_deletions.setdefault(
        str(d.get("name") or ref.res_name), rec.ts_field
    )
  if (
      ref.verb == "patch"
      and ref.resource == "clusterqueues"
      and isinstance(d.get("request"), list)
  ):
    _record_quota_patches(rec, state, ref.res_name)
  if (
      ref.verb == "create"
      and ref.resource in ("jobs", "jobsets")
      and isinstance(d.get("spec"), dict)
  ):
    _record_indexed_job(rec, state, ref.res_name)


_AUDIT_SPEC_SEGMENT_RE = re.compile(
    r" spec=.*?(?=(?: (?:annotations|labels|status)=|$))"
)


def _audit_action_line(rec: LogRecord) -> str:
  """Audit summary text: message plus full spec / request body / principal when the message lacks or truncates them."""
  d = rec.raw
  msg = rec.msg
  if isinstance(d.get("spec"), dict):
    spec_json = json.dumps(d["spec"], sort_keys=True)[:1200]
    if " spec=" in msg:
      msg = _AUDIT_SPEC_SEGMENT_RE.sub(
          lambda _: f" spec={spec_json}", msg, count=1
      )
    else:
      msg = f"{msg} spec={spec_json}"
  req_extra = ""
  if isinstance(d.get("request"), (dict, list)) and "request=" not in msg:
    req_extra = f" request={json.dumps(d['request'])[:400]}"
  if d.get("principalEmail") and "principal=" not in msg:
    req_extra = f" principal={d.get('principalEmail')}{req_extra}"
  return msg + req_extra


def _scan_audit_actions(
    rec: LogRecord, state: LogScanState, ref: _AuditRef
) -> None:
  """Workload status patches and deduplicated, capped audit mutations."""
  d = rec.raw
  if (
      ref.resource == "workloads"
      and ref.subresource == "status"
      and d.get("status")
  ):
    state.workload_status_by_name[ref.res_name] = str(rec.msg)[:850]
    return
  if (
      ref.verb not in ("create", "delete", "patch", "update")
      or ref.subresource
      or ref.resource not in _AUDITED_RESOURCES
      or (
          ref.resource == "configmaps"
          and (
              report_output.is_managed_addon_namespace(
                  str(d.get("namespace") or "")
              )
              or str(d.get("name") or ref.res_name).rsplit("/", 1)[-1]
              == "kube-root-ca.crt"
          )
      )
  ):
    return
  line = _audit_action_line(rec)
  dedup_audit_key = line[:260]
  if dedup_audit_key in state.seen_audit:
    return
  state.seen_audit.add(dedup_audit_key)
  if len(state.audit_actions) >= _MAX_AUDIT_ACTIONS:
    state.omitted_audit += 1
    return
  audit_key = (
      f"audit:{ref.verb}:{ref.resource}"
      if (ref.verb == "delete" or ref.resource in _GRAPH_CONFIG_RESOURCES)
      else None
  )
  ts = rec.ts_field
  state.audit_actions.append(
      (audit_key, (f"{ts} " if ts else "") + line[:1400])
  )


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
      rec.obj.get("namespace")
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
      or (json.dumps(d.get("spec"))[:500] if d.get("spec") else "")
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
  return [
      (
          f"logfact:namespace-delete:{ns_name}",
          "AUDIT_LOG_FACT: the audit log records a `delete namespaces` request"
          f" for namespace `{ns_name}`"
          + (f" at {ts}" if ts else "")
          + " (whether the request succeeded is not determinable from this"
          " entry). A completed namespace deletion removes every namespaced"
          " object in it (Jobs, Workloads, LocalQueues, Pods).",
      )
      for ns_name, ts in sorted(state.audit_namespace_deletions.items())
  ]


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
  return [
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


def emit_waiting_pods_ready(state: LogScanState) -> list[Fact]:
  stuck_waiting = sorted(
      state.waiting_pods_ready_workloads - state.pods_ready_true_workloads
  )
  return [
      (
          f"logfact:waiting-pods-ready:{wl_wait}",
          (
              "CONTROLLER_LOG_FACT: the job reconciler logged 'Updating the"
              f" PodsReady condition' with status=False for '{wl_wait}' and no"
              " later status=True for the same reference"
              " (https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/)."
              " The condition is evaluated after admission, so the blocker is"
              " in pod scheduling, node readiness/provisioning, or the pods"
              " themselves — inspect the pods and nodes for that workload."
          ),
      )
      for wl_wait in stuck_waiting
  ]


def emit_quota_patch_provenance(state: LogScanState) -> list[Fact]:
  """Per-ClusterQueue provenance: who patched nominalQuota and what the latest patched value was."""
  if not (
      state.audit_cq_quota_patches and state.has_insufficient_quota_pending
  ):
    return []
  latest_by_cq: dict[str, tuple[str, str, str]] = {}
  principals_by_cq: dict[str, set[str]] = {}
  for ts_p, cq_p, val_p, who_p in sorted(
      state.audit_cq_quota_patch_detail, key=lambda t: t[0]
  ):
    latest_by_cq[cq_p] = (ts_p, val_p, who_p)
    principals_by_cq.setdefault(cq_p, set()).add(who_p or "<unknown principal>")
  prov_rows = [
      f"{cq_p}: latest nominalQuota patch={val}"
      + (f" at {ts_p}" if ts_p else "")
      + f" by {sorted(principals_by_cq[cq_p])}"
      for cq_p, (ts_p, val, _) in sorted(latest_by_cq.items())
  ]
  admitted_without_audit = sorted(
      set(state.admitted_count_by_cq) - set(latest_by_cq)
  )
  unpatched_note = ""
  if admitted_without_audit:
    unpatched_note = (
        "ClusterQueues that admitted workloads in this log but have no"
        f" nominalQuota patch in the audit trail: {admitted_without_audit}. "
    )
  return [(
      "logfact:audit-cq-quota-patch",
      "AUDIT_LOG_FACT: audit log records clusterqueues.patch updates to"
      " nominalQuota while workloads emit Pending ('insufficient unused"
      f" quota'). Per ClusterQueue: {'; '.join(prov_rows[:8])}. "
      + unpatched_note
      + "Kueue treats each ClusterQueue's nominalQuota as guaranteed capacity"
      " and admits against the cohort's summed nominalQuota, independent of"
      " node allocatable"
      " (https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/); compare"
      " these values with COHORT_RESOURCE_ARITHMETIC when a snapshot is"
      " available.",
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
    except json.JSONDecodeError:
      state.source_counts["unstructured"] += 1
      continue
    if not isinstance(d, dict):
      continue
    rec = LogRecord.from_dict(d)
    for scanner in RECORD_SCANNERS:
      scanner(rec, state)
  return state


def _finalize_sections(state: LogScanState) -> None:
  """Appends workload status patches and truncation trailers to capped sections."""
  for wl_stat in state.workload_status_by_name.values():
    if (
        wl_stat[:220] not in state.seen_audit
        and len(state.audit_actions) < _MAX_AUDIT_ACTIONS_WITH_STATUS
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
            f"... {state.omitted_audit} more distinct audit entries omitted"
            f" (first {_MAX_AUDIT_ACTIONS} kept); the complete timeline is in"
            " full_report_file"
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
