"""Derived-fact emitters for `snapshot.py` (`derived_graph_diagnostics`).

Each `emit_<section>(ctx)` function appends neutral, mechanically derived
facts about one aspect of the Kueue admission graph to `ctx.notes`. The
orchestrator (`snapshot.compute_derived_facts`) builds a `FactContext` from the
snapshot items and calls the emitters in `FACT_EMITTERS` order; the order
determines the order of the facts in the digest and must not change.

The emitters describe observations and documented Kueue mechanisms only; they
never rank causes or prescribe report content.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Callable

import fair_sharing_facts
import k8s_objects as k8s
import report_output
import topology_facts
import workload_timeline
import yaml

_parse_quantity = report_output.parse_quantity
_fmt_num = report_output.fmt_num
_fmt_qty = report_output.fmt_quantity

_TAS_ANNOTATIONS = (
    "kueue.x-k8s.io/podset-required-topology",
    "kueue.x-k8s.io/podset-preferred-topology",
    "kueue.x-k8s.io/podset-unconstrained-topology",
)

# Deletion events on these kinds describe routine rollout/pod churn, not Kueue
# graph objects, and are not listed as deletion facts.
_HOUSEKEEPING_EVENT_KINDS = frozenset({
    "ReplicaSet",
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Pod",
    "Node",
    "Endpoints",
    "EndpointSlice",
    "Lease",
    "Ingress",
    "Service",
})

# Status conditions reported as facts: (kind, condition type, status) tuples.
_NEGATIVE_CONDITIONS = {
    ("Workload", "QuotaReserved", "False"),
    ("Workload", "Admitted", "False"),
    ("Workload", "Evicted", "True"),
    ("Workload", "Preempted", "True"),
    ("Workload", "Requeued", "False"),
    ("Workload", "PodsReady", "False"),
    ("Workload", "Finished", "True"),
    ("ClusterQueue", "Active", "False"),
    ("LocalQueue", "Active", "False"),
    ("AdmissionCheck", "Active", "False"),
    ("Cohort", "Active", "False"),
    ("JobSet", "Completed", "False"),
    ("JobSet", "Failed", "True"),
    ("Job", "Failed", "True"),
    ("Job", "Suspended", "True"),
}

_INVENTORY_KINDS = (
    "Workload",
    "Job",
    "JobSet",
    "Pod",
    "LocalQueue",
    "ClusterQueue",
    "Cohort",
    "ResourceFlavor",
    "AdmissionCheck",
    "ProvisioningRequestConfig",
    "ProvisioningRequest",
    "Topology",
    "Node",
    "Event",
)

# Each absent kind is paired with the question only that kind answers, so a
# report can open an Open Question of type "missing data" against a named
# object instead of guessing.
_COVERAGE_QUESTIONS = (
    (
        "ClusterQueue",
        (
            "declared nominalQuota / borrowingLimit / lendingLimit per flavor"
            " and the cohort membership"
        ),
    ),
    ("Cohort", "quota declared on the Cohort object itself and its parent"),
    (
        "ResourceFlavor",
        "nodeLabels / taints / tolerations a flavor injects into pods",
    ),
    (
        "Workload",
        "current admission status, flavor assignment and requeueState",
    ),
    ("Pod", "scheduler and kubelet outcome after admission"),
    ("Node", "physical capacity and labels behind each flavor"),
    ("Event", "Kubernetes Event history (admission, eviction, scheduling)"),
    (
        "AdmissionCheck",
        "which admission checks gate the queues and their Active state",
    ),
    (
        "ProvisioningRequest",
        "the runtime outcome of a provisioning admission check",
    ),
    (
        "ConfigMap",
        "KueueConfiguration (waitForPodsReady, clientConnection, integrations)",
    ),
)

_TAS_CITE = "https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/"


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class FactContext:
  """Snapshot objects bucketed by kind plus the lookup tables the sections share."""

  by_kind: dict[str, list[dict[str, Any]]]
  notes: list[tuple[str | None, str]] = dataclasses.field(default_factory=list)

  def __post_init__(self) -> None:
    self.workloads = self.by_kind.get("Workload", [])
    self.jobs = self.by_kind.get("Job", [])
    self.jobsets = self.by_kind.get("JobSet", [])
    self.pods = self.by_kind.get("Pod", [])
    self.lqs = self.by_kind.get("LocalQueue", [])
    self.cqs = self.by_kind.get("ClusterQueue", [])
    self.cohort_objects = self.by_kind.get("Cohort", [])
    self.acs = self.by_kind.get("AdmissionCheck", [])
    self.prcs = self.by_kind.get("ProvisioningRequestConfig", [])
    self.provreqs = self.by_kind.get("ProvisioningRequest", [])
    self.rfs = self.by_kind.get("ResourceFlavor", [])
    self.nodes = self.by_kind.get("Node", [])
    self.events = self.by_kind.get("Event", [])
    self.configmaps = self.by_kind.get("ConfigMap", [])
    self.lq_by_ref = {
        f"{k8s.namespace(lq)}/{k8s.name(lq)}": lq for lq in self.lqs
    }
    self.cq_by_name = {k8s.name(cq): cq for cq in self.cqs}
    self.rf_by_name = {k8s.name(rf): rf for rf in self.rfs}
    self.ac_by_name = {k8s.name(ac): ac for ac in self.acs}
    self.prc_by_name = {k8s.name(prc): prc for prc in self.prcs}
    # AdmissionCheck names referenced by any ClusterQueue, and ClusterQueues
    # without any.
    self.cq_referenced_acs: set[str] = set()
    self.unconfigured_cqs: list[str] = []
    for cq in self.cqs:
      this_cq_acs = _cq_admission_checks(cq)
      self.cq_referenced_acs.update(this_cq_acs)
      if k8s.name(cq) and not this_cq_acs:
        self.unconfigured_cqs.append(k8s.name(cq))
    self.cohort_map: dict[str, list[dict[str, Any]]] = {}
    for cq in self.cqs:
      cohort = _cq_cohort(cq)
      if isinstance(cohort, str) and cohort:
        self.cohort_map.setdefault(cohort, []).append(cq)
    self.pods_by_ns: dict[str, list[dict[str, Any]]] = {}
    for p in self.pods:
      self.pods_by_ns.setdefault(k8s.namespace(p), []).append(p)

  @classmethod
  def from_items(cls, items: list[dict[str, Any]]) -> "FactContext":
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for it in items:
      if isinstance(it, dict):
        by_kind.setdefault(k8s.kind(it), []).append(it)
    return cls(by_kind=by_kind)

  def add(self, key: str | None, text: str) -> None:
    self.notes.append((key, text))


def _cq_cohort(cq: dict[str, Any]) -> Any:
  sp = k8s.spec(cq)
  return sp.get("cohortName") or sp.get("cohort") or ""


def _strategy_admission_checks(cq_spec: dict[str, Any]) -> list[str]:
  """AdmissionCheck names listed under `spec.admissionChecksStrategy.admissionChecks`."""
  entries = k8s.dict_items(
      k8s.as_dict(cq_spec.get("admissionChecksStrategy")).get("admissionChecks")
  )
  return [str(e["name"]) for e in entries if e.get("name")]


def _cq_admission_checks(cq: dict[str, Any]) -> list[str]:
  """String AdmissionCheck names from `spec.admissionChecks` and `spec.admissionChecksStrategy`."""
  cq_spec = k8s.spec(cq)
  out = [n for n in cq_spec.get("admissionChecks") or [] if isinstance(n, str)]
  return out + _strategy_admission_checks(cq_spec)


# ---------------------------------------------------------------------------
# Shared helpers (quota arithmetic, events, pod sets)
# ---------------------------------------------------------------------------


def _cpu_quota(cq: dict[str, Any]) -> dict[str, Any]:
  """Aggregates per-flavor CPU quota figures for one ClusterQueue.

  `lendable` sums, per flavor, `min(lendingLimit, nominalQuota)` (or the full
  nominal when no lendingLimit is set). `borrowing_limit` is the per-flavor sum
  when every cpu flavor sets one, otherwise None (unbounded).

  Args:
    cq: Raw ClusterQueue object mapping.

  Returns:
    Dict with `nominal`, `lendable`, `borrowing_limit`, `flavors`, `unparsed`.
  """
  nominal = 0.0
  lendable = 0.0
  borrowing_sum = 0.0
  borrowing_all_set = True
  flavors: list[str] = []
  unparsed: list[str] = []
  for _, fl, res in k8s.flavor_quotas(cq):
    if res.get("name") != "cpu":
      continue
    parsed = _parse_cpu_limits(fl, res, unparsed)
    if parsed is None:
      continue
    nom, lend, borrow = parsed
    nominal += nom
    lendable += nom if lend is None else min(lend, nom)
    if borrow is None:
      borrowing_all_set = False
    else:
      borrowing_sum += borrow
    flavors.append(
        f"{fl.get('name')}: nominal={_fmt_num(nom)}"
        + (f" lendingLimit={_fmt_num(lend)}" if lend is not None else "")
        + (f" borrowingLimit={_fmt_num(borrow)}" if borrow is not None else "")
    )
  return {
      "nominal": nominal,
      "lendable": lendable,
      "borrowing_limit": (
          borrowing_sum if (flavors and borrowing_all_set) else None
      ),
      "flavors": flavors,
      "unparsed": unparsed,
  }


def _parse_cpu_limits(
    fl: dict[str, Any], res: dict[str, Any], unparsed: list[str]
) -> tuple[float, float | None, float | None] | None:
  """Parses (nominalQuota, lendingLimit, borrowingLimit); records unparsable values and returns None."""
  nom = _parse_quantity(res.get("nominalQuota"))
  if nom is None:
    unparsed.append(
        f"{fl.get('name')}: nominalQuota={res.get('nominalQuota')!r}"
    )
    return None
  lend_raw = res.get("lendingLimit")
  lend = _parse_quantity(lend_raw) if lend_raw is not None else None
  if lend_raw is not None and lend is None:
    unparsed.append(f"{fl.get('name')}: lendingLimit={lend_raw!r}")
    return None
  borrow_raw = res.get("borrowingLimit")
  borrow = _parse_quantity(borrow_raw) if borrow_raw is not None else None
  if borrow_raw is not None and borrow is None:
    unparsed.append(f"{fl.get('name')}: borrowingLimit={borrow_raw!r}")
    return None
  return nom, lend, borrow


def _resource_quota_summary(cq: dict[str, Any]) -> dict[str, list[str]]:
  """Returns per-resource flavor quota summary strings for one ClusterQueue."""
  out: dict[str, list[str]] = {}
  for _, fl, res in k8s.flavor_quotas(cq):
    name = str(res.get("name", ""))
    if not name:
      continue
    parts = [f"nominalQuota={res.get('nominalQuota')}"]
    for key in ("lendingLimit", "borrowingLimit"):
      if res.get(key) is not None:
        parts.append(f"{key}={res.get(key)}")
    out.setdefault(name, []).append(f"{fl.get('name')}: " + " ".join(parts))
  return out


def _event_summary(ev: dict[str, Any]) -> str:
  obj = ev.get("involvedObject") or {}
  ref = ""
  if isinstance(obj, dict) and obj.get("name"):
    ref = f"[{obj.get('kind', 'Object')}/{obj.get('name')}] "
  count = ev.get("count")
  count_str = f" (x{count})" if isinstance(count, int) and count > 1 else ""
  return (
      f"{ref}{ev.get('reason', '')}:"
      f" {str(ev.get('message', ''))[:300]}{count_str}"
  )


def _event_identity(ev: dict[str, Any]) -> tuple[str, str, str]:
  obj = ev.get("involvedObject") or {}
  obj_ref = ""
  if isinstance(obj, dict):
    obj_ref = str(
        obj.get("uid")
        or f"{obj.get('kind', '')}/{obj.get('namespace', '')}/{obj.get('name', '')}"
    )
  return (obj_ref, str(ev.get("reason", "")), str(ev.get("message", "")))


def _podset_topology_request(ps: dict[str, Any]) -> str:
  """Returns a short description of a pod set's topology request, or '' if none."""
  tr = ps.get("topologyRequest")
  if isinstance(tr, dict) and tr:
    parts = [
        f"{k}={v}"
        for k, v in tr.items()
        if k in (
            "required",
            "preferred",
            "unconstrained",
            "podIndexLabel",
            "subGroupIndexLabel",
        )
    ]
    return "topologyRequest{" + ", ".join(parts) + "}"
  ann = k8s.annotations(k8s.as_dict(ps.get("template")))
  hits = [
      f"{k.rsplit('/', 1)[-1]}={v}"
      for k, v in ann.items()
      if k in _TAS_ANNOTATIONS
  ]
  if hits:
    return "annotations{" + ", ".join(hits) + "}"
  return ""


def _podset_requests(ps: dict[str, Any]) -> dict[str, str]:
  """Aggregates container requests of one pod template (per pod, not multiplied by count)."""
  tmpl_spec = k8s.spec(k8s.as_dict(ps.get("template")))
  totals: dict[str, float] = {}
  raw: dict[str, str] = {}
  for c in (tmpl_spec.get("containers") or []) + (
      tmpl_spec.get("initContainers") or []
  ):
    if not isinstance(c, dict):
      continue
    reqs = (c.get("resources") or {}).get("requests") or {}
    if not isinstance(reqs, dict):
      continue
    for name, val in reqs.items():
      q = _parse_quantity(val)
      if q is None:
        raw[str(name)] = str(val)
      else:
        totals[str(name)] = totals.get(str(name), 0.0) + q
  out = {k: _fmt_num(v) for k, v in sorted(totals.items())}
  out.update(raw)
  return out


def _nodes_matching_labels(
    nodes: list[dict[str, Any]], rf_labels: dict[str, Any]
) -> list[dict[str, Any]]:
  """Nodes whose labels carry every `rf_labels` key with the same value (label equality)."""
  return [
      n
      for n in nodes
      if all(k8s.labels(n).get(k) == v for k, v in rf_labels.items())
  ]


def _rf_node_labels(rf: Any) -> Any:
  """`spec.nodeLabels` of a ResourceFlavor as stored (callers check that it is a mapping)."""
  return (k8s.spec(rf).get("nodeLabels") or {}) if isinstance(rf, dict) else {}


# ---------------------------------------------------------------------------
# 1. Inventory and coverage
# ---------------------------------------------------------------------------


def emit_inventory(ctx: FactContext) -> None:
  """1. Inventory: object counts per kind and the no-workload case."""
  inventory = ", ".join(
      f"{kind}={len(ctx.by_kind.get(kind, []))}"
      for kind in _INVENTORY_KINDS
      if kind in ctx.by_kind
  )
  ctx.add(None, f"SNAPSHOT_INVENTORY: {inventory}")
  if not ctx.workloads and not ctx.jobs and not ctx.jobsets:
    ctx.add(
        "inventory:no-workloads",
        "SNAPSHOT_INVENTORY: no Workload, Job, or JobSet objects are present"
        f" in the snapshot; {len(ctx.lqs)} LocalQueue object(s) present. Any"
        " workload history must come from Events, controller logs, or audit"
        " logs rather than from live objects.",
    )


def emit_coverage(ctx: FactContext) -> None:
  """Emits section 1a evidence-coverage facts for present and absent kinds."""
  absent = [
      f"{kind} (answers: {q})"
      for kind, q in _COVERAGE_QUESTIONS
      if not ctx.by_kind.get(kind)
  ]
  present = [kind for kind, _ in _COVERAGE_QUESTIONS if ctx.by_kind.get(kind)]
  ctx.add(
      None,
      f"BUNDLE_COVERAGE: present={present}; absent={absent or 'none'}. A"
      " question whose answer lives only in an absent kind cannot be settled"
      " from this snapshot; name that kind when reporting it as not"
      " determinable.",
  )


def emit_status_conditions(ctx: FactContext) -> None:
  """1b. Status conditions of Kueue objects (verbatim reason/message)."""
  for kind in (
      "ClusterQueue",
      "LocalQueue",
      "AdmissionCheck",
      "Cohort",
      "Workload",
      "JobSet",
      "Job",
  ):
    for obj in ctx.by_kind.get(kind, []):
      ref = f"{kind}/{k8s.ref(obj)}"
      for cond in k8s.conditions(obj):
        ctype = str(cond.get("type", ""))
        cstatus = str(cond.get("status", ""))
        if (kind, ctype, cstatus) not in _NEGATIVE_CONDITIONS:
          continue
        reason = str(cond.get("reason", ""))
        ctx.add(
            f"condition:{kind}:{ctype}:{reason}",
            f"STATUS_CONDITION: [{ref}] {ctype}={cstatus} reason={reason}:"
            f" {str(cond.get('message', ''))[:300]}",
        )


# ---------------------------------------------------------------------------
# 1c. Workload -> LocalQueue -> ClusterQueue resolution and per-pod-set facts
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _FlavorCoverage:
  """Which ClusterQueue flavors are topology-aware and which resources each group covers."""

  tas_flavors: list[str]
  plain_flavors: list[str]
  tas_res: set[str]
  plain_res: set[str]

  @property
  def any(self) -> bool:
    return bool(self.tas_flavors or self.plain_flavors)


def _flavor_coverage(
    ctx: FactContext, cq: dict[str, Any] | None
) -> _FlavorCoverage:
  """Classifies a ClusterQueue's flavors into TAS and non-TAS coverage sets."""
  cov = _FlavorCoverage([], [], set(), set())
  if cq is None:
    return cov
  for rg in k8s.resource_groups(cq):
    rg_res = {str(r) for r in rg.get("coveredResources") or [] if r}
    for fl in rg.get("flavors") or []:
      if isinstance(fl, dict) and fl.get("name"):
        rf = ctx.rf_by_name.get(str(fl["name"]))
        has_topology = bool(k8s.spec(rf).get("topologyName")) if rf else False
        if has_topology:
          cov.tas_flavors.append(str(fl["name"]))
          cov.tas_res.update(rg_res)
        else:
          cov.plain_flavors.append(str(fl["name"]))
          cov.plain_res.update(rg_res)
  return cov


def _resolve_workload_cq(
    ctx: FactContext, wl: dict[str, Any], wl_ref: str
) -> dict[str, Any] | None:
  """Emits the WORKLOAD_QUEUE_CHAIN fact and returns the resolved ClusterQueue, if any."""
  ns = k8s.namespace(wl)
  queue_name = str(k8s.spec(wl).get("queueName") or "")
  lq = ctx.lq_by_ref.get(f"{ns}/{queue_name}") if queue_name else None
  if not queue_name:
    ctx.add(
        f"queue-chain:{wl_ref}",
        f"WORKLOAD_QUEUE_CHAIN: [{wl_ref}] spec.queueName is empty; the"
        " workload is not assigned to any LocalQueue.",
    )
    return None
  if lq is None:
    ctx.add(
        f"queue-chain:{wl_ref}",
        f"WORKLOAD_QUEUE_CHAIN: [{wl_ref}] spec.queueName={queue_name}; no"
        f" LocalQueue named {queue_name!r} exists in namespace {ns!r} in the"
        " snapshot.",
    )
    return None
  cq_name = str(k8s.spec(lq).get("clusterQueue") or "")
  cq = ctx.cq_by_name.get(cq_name)
  ctx.add(
      None,
      f"WORKLOAD_QUEUE_CHAIN: [{wl_ref}] queueName={queue_name} -> ClusterQueue"
      f" {cq_name or '<unset>'}"
      + (
          ""
          if cq is not None
          else f" (no ClusterQueue named {cq_name!r} in the snapshot)"
      ),
  )
  return cq


def _podset_flavor_note(
    cov: _FlavorCoverage, treq: str, req_keys: set[str], wl_finished: bool
) -> tuple[str | None, str]:
  """Returns (key, suffix) describing the TAS / non-TAS flavor fit of one pod set."""
  needs_tas_res = bool(req_keys & (cov.tas_res - cov.plain_res))
  needs_plain_res = bool(req_keys & (cov.plain_res - cov.tas_res))
  if treq and not cov.tas_flavors:
    return "podset-flavor", (
        ". A pod set with a topology request is only assigned flavors whose"
        " ResourceFlavor sets topologyName ("
        + _TAS_CITE
        + ")."
    )
  if treq and cov.tas_flavors and cov.plain_flavors and needs_plain_res:
    only_plain = sorted(req_keys & (cov.plain_res - cov.tas_res))
    on_tas = sorted(req_keys & cov.tas_res)
    return "podset-flavor", (
        ". Requested resources covered only by flavors without topologyName:"
        f" {only_plain}; covered by flavors with topologyName: {on_tas}. With"
        " an explicit topology request, a flavor without topologyName is"
        " accepted only when its resourceGroup covers none of the pod's"
        " requested resources; otherwise it is rejected with 'does not support"
        " TopologyAwareScheduling' ("
        + _TAS_CITE
        + ")."
    )
  if (
      not treq
      and cov.tas_flavors
      and cov.plain_flavors
      and not wl_finished
      and (needs_tas_res or not (cov.tas_res - cov.plain_res))
  ):
    on_tas_only = sorted(req_keys & (cov.tas_res - cov.plain_res))
    on_plain = sorted(req_keys & cov.plain_res)
    return "podset-flavor", (
        ". Requested resources covered only by flavors with topologyName:"
        f" {on_tas_only}; covered by flavors without topologyName: {on_plain}."
        " Without a topology request, a flavor whose ResourceFlavor sets"
        " topologyName is rejected with 'supports only"
        " TopologyAwareScheduling' unless every flavor of the ClusterQueue is"
        " topology-aware ("
        + _TAS_CITE
        + ")."
    )
  return None, ""


def _emit_podset_facts(
    ctx: FactContext, wl: dict[str, Any], wl_ref: str, cov: _FlavorCoverage
) -> None:
  """Emits per-podSet resource, topology, and flavor-compatibility facts."""
  wl_finished = any(
      c.get("type") == "Finished" and c.get("status") == "True"
      for c in k8s.conditions(wl)
  )
  for ps in k8s.dict_items(k8s.spec(wl).get("podSets")):
    ps_name = str(ps.get("name", ""))
    treq = _podset_topology_request(ps)
    ps_reqs = _podset_requests(ps)
    tmpl_spec = k8s.spec(k8s.as_dict(ps.get("template")))
    line = (
        f"WORKLOAD_PODSET_FACTS: [{wl_ref}] podSet {ps_name!r}:"
        f" count={ps.get('count')}, requests/pod={ps_reqs}, topology"
        f" request={treq or 'none'},"
        f" tolerations={len(tmpl_spec.get('tolerations') or [])},"
        f" nodeSelector={tmpl_spec.get('nodeSelector') or {}}"
    )
    key = None
    if cov.any:
      line += (
          f"; ClusterQueue flavors with topologyName={cov.tas_flavors or []},"
          f" without={cov.plain_flavors or []}"
      )
      marker, suffix = _podset_flavor_note(
          cov, treq, set(ps_reqs.keys()), wl_finished
      )
      if marker:
        key = None if wl_finished else f"podset-flavor:{wl_ref}:{ps_name}"
        line += suffix
    ctx.add(key, line)


def emit_queue_chain(ctx: FactContext) -> None:
  """Emits section 1c Workload -> LocalQueue -> ClusterQueue chain facts."""
  for wl in ctx.workloads:
    wl_ref = f"Workload/{k8s.namespace(wl)}/{k8s.name(wl)}"
    cq = _resolve_workload_cq(ctx, wl, wl_ref)
    _emit_podset_facts(ctx, wl, wl_ref, _flavor_coverage(ctx, cq))


# ---------------------------------------------------------------------------
# 1c-bis. Job and JobSet static spec inspection
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _JobTotals:
  pods: int = 0
  requests: dict[str, float] = dataclasses.field(default_factory=dict)


def _job_specs_to_check(
    kind_name: str, j_ref: str, j_spec: dict[str, Any]
) -> list[tuple[str, dict[str, Any], int]]:
  """(ref, batch Job spec, replicas) for a Job or every replicatedJob of a JobSet."""
  if kind_name == "Job":
    return [(j_ref, j_spec, 1)]
  out: list[tuple[str, dict[str, Any], int]] = []
  for rj in k8s.dict_items(j_spec.get("replicatedJobs")):
    rj_name = str(rj.get("name", ""))
    rj_replicas = int(rj.get("replicas") or 1)
    rj_job_spec = k8s.spec(k8s.as_dict(rj.get("template")))
    out.append((f"{j_ref}:replicatedJob[{rj_name}]", rj_job_spec, rj_replicas))
  return out


def _emit_job_sub_specs(
    ctx: FactContext, specs: list[tuple[str, dict[str, Any], int]]
) -> _JobTotals:
  """Emits Indexed/backoffLimitPerIndex facts and sums pods and requests over the sub specs."""
  totals = _JobTotals()
  for sub_ref, sub_spec, replicas in specs:
    comp_mode = str(sub_spec.get("completionMode") or "")
    blpi = sub_spec.get("backoffLimitPerIndex")
    mfi = sub_spec.get("maxFailedIndexes")
    parallelism = int(sub_spec.get("parallelism") or 1) * replicas
    totals.pods += parallelism
    pod_reqs = _podset_requests({"template": sub_spec.get("template") or {}})
    for r_k, r_v in pod_reqs.items():
      q_val = _parse_quantity(r_v)
      if q_val is not None:
        totals.requests[r_k] = (
            totals.requests.get(r_k, 0.0) + q_val * parallelism
        )
    if comp_mode == "Indexed" and blpi is not None and mfi is None:
      ctx.add(
          f"job-spec:{sub_ref}:indexed-backoff",
          f"JOB_SPEC_FACT: [{sub_ref}] has completionMode=Indexed and"
          f" backoffLimitPerIndex={blpi} while "
          "maxFailedIndexes is unset (null). batch/v1 semantics: when a pod for"
          " an index exhausts backoffLimitPerIndex, "
          "that index stops retrying; with maxFailedIndexes unset the Job is"
          " only marked Failed if all indexes fail "
          "(whereas setting maxFailedIndexes marks the Job Failed once failed"
          " indexes exceed maxFailedIndexes). "
          "Kueue's PodsReady condition for a Job tracks whether the Job's pods"
          " have reached Ready/Succeeded "
          "(https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/).",
      )
  return totals


def _cq_quota_and_flavors(
    ctx: FactContext, cq: dict[str, Any]
) -> tuple[dict[str, float], list[str], bool]:
  """Summed nominalQuota per resource, per-flavor nodeLabels summary and whether every ResourceFlavor is present."""
  cq_quotas: dict[str, float] = {}
  rf_summary: list[str] = []
  all_rfs_present = True
  for rg in k8s.resource_groups(cq):
    for fl in k8s.dict_items(rg.get("flavors")):
      if not fl.get("name"):
        continue
      rf_o = ctx.rf_by_name.get(str(fl["name"]))
      if rf_o is None:
        all_rfs_present = False
      rf_summary.append(
          f"{fl['name']}(nodeLabels={(k8s.spec(rf_o).get('nodeLabels') or {})})"
      )
      for r_entry in k8s.dict_items(fl.get("resources")):
        if r_entry.get("name"):
          r_nom = _parse_quantity(r_entry.get("nominalQuota"))
          if r_nom is not None:
            r_n = str(r_entry["name"])
            cq_quotas[r_n] = cq_quotas.get(r_n, 0.0) + r_nom
  return cq_quotas, rf_summary, all_rfs_present


def _admission_check_details(
    ctx: FactContext, cq_acs: list[str]
) -> tuple[list[str], bool]:
  """Describes each AdmissionCheck with its ProvisioningRequestConfig; False when one is missing."""
  ac_details: list[str] = []
  all_acs_present = True
  for ac_n in cq_acs:
    ac_obj = ctx.ac_by_name.get(str(ac_n))
    if ac_obj is None:
      all_acs_present = False
      continue
    ac_sp = k8s.spec(ac_obj)
    p_ref = ac_sp.get("parametersRef") or ac_sp.get("parameters") or {}
    prc_n = str(p_ref.get("name", "")) if isinstance(p_ref, dict) else ""
    prc_obj = ctx.prc_by_name.get(prc_n)
    if prc_n and prc_obj is None:
      all_acs_present = False
    prc_sp = k8s.spec(prc_obj)
    ac_details.append(
        f"{ac_n}(controller={ac_sp.get('controllerName')}, prc={prc_n}, "
        f"provisioningClassName={prc_sp.get('provisioningClassName')})"
    )
  return ac_details, all_acs_present


def _emit_static_queue_chain(
    ctx: FactContext, job_obj: dict[str, Any], j_ref: str, totals: _JobTotals
) -> None:
  """JOB_QUEUE_CHAIN_FACTS for one Job/JobSet when the snapshot has no Workload objects."""
  j_ns = k8s.namespace(job_obj)
  q_name = str(
      k8s.labels(job_obj).get("kueue.x-k8s.io/queue-name")
      or k8s.annotations(job_obj).get("kueue.x-k8s.io/queue-name")
      or ""
  )
  lq = ctx.lq_by_ref.get(f"{j_ns}/{q_name}") if q_name else None
  cq_name = str(k8s.spec(lq).get("clusterQueue") or "") if lq else ""
  cq = ctx.cq_by_name.get(cq_name) if cq_name else None
  req_summary = {k: _fmt_num(v) for k, v in sorted(totals.requests.items())}
  chain_msg = (
      f"JOB_QUEUE_CHAIN_FACTS: [{j_ref}] queue-name={q_name or '<unset>'} ->"
      f" ClusterQueue={cq_name or '<unresolved>'}; totalPods={totals.pods},"
      f" totalRequests={req_summary}"
  )
  chain_key: str | None = None
  if cq is not None:
    # Unlike 1d, every `spec.admissionChecks` entry counts here (a non-string
    # entry cannot be resolved and therefore suppresses the static-chain key).
    cq_acs = list(
        k8s.spec(cq).get("admissionChecks") or []
    ) + _strategy_admission_checks(k8s.spec(cq))
    cq_quotas, rf_summary, all_rfs_present = _cq_quota_and_flavors(ctx, cq)
    fits_quota = bool(totals.requests) and all(
        r_k in cq_quotas and totals.requests[r_k] <= cq_quotas[r_k]
        for r_k in totals.requests
    )
    if (
        cq_acs
        and not ctx.provreqs
        and not ctx.nodes
        and all_rfs_present
        and fits_quota
    ):
      ac_details, all_acs_present = _admission_check_details(ctx, cq_acs)
      if all_acs_present:
        chain_key = f"provreq:static-chain:{j_ref}"
        chain_msg += (
            f"; ClusterQueue nominalQuota covers totalRequests ({req_summary})"
            f" and admission is gated on AdmissionCheck {ac_details} targeting"
            f" ResourceFlavor {rf_summary}. The bundle contains no"
            " ProvisioningRequest, Node, or Workload status objects, so the"
            " runtime outcome of the admission check (ProvisioningRequest"
            " conditions, node provisioning) is not observable from this"
            " bundle; it must come from controller/autoscaler logs or events"
            " if present."
        )
  ctx.add(chain_key, chain_msg)


def emit_job_specs(ctx: FactContext) -> None:
  """Emits section 1c-bis Job/JobSet static spec and queue-chain facts."""
  for kind_name, job_objs in (("Job", ctx.jobs), ("JobSet", ctx.jobsets)):
    for job_obj in job_objs:
      j_ref = f"{kind_name}/{k8s.namespace(job_obj)}/{k8s.name(job_obj)}"
      totals = _emit_job_sub_specs(
          ctx, _job_specs_to_check(kind_name, j_ref, k8s.spec(job_obj))
      )
      if not ctx.workloads:
        _emit_static_queue_chain(ctx, job_obj, j_ref, totals)


# ---------------------------------------------------------------------------
# 1d / 1e. Admission checks and ProvisioningRequests
# ---------------------------------------------------------------------------


def _ac_referencing_cqs(ctx: FactContext, ac_name: str) -> list[str]:
  return sorted(
      k8s.name(cq) for cq in ctx.cqs if ac_name in _cq_admission_checks(cq)
  )


def emit_admission_checks(ctx: FactContext) -> None:
  """1d. Workload admissionChecks, requeueState, and AdmissionCheck wiring."""
  for ac in ctx.acs:
    ac_name, ac_spec = k8s.name(ac), k8s.spec(ac)
    p_ref = ac_spec.get("parametersRef") or ac_spec.get("parameters")
    if ac_name and ac_name not in ctx.cq_referenced_acs:
      ctx.add(
          f"unreferenced-ac:{ac_name}",
          f"ADMISSIONCHECK_FACTS ({ac_name}):"
          f" controllerName={ac_spec.get('controllerName')},"
          f" parametersRef={p_ref}; NOT referenced by any"
          " ClusterQueue.spec.admissionChecks / admissionChecksStrategy in the"
          " snapshot (ClusterQueues without"
          f" admissionChecks={ctx.unconfigured_cqs}). An AdmissionCheck applies"
          " only to workloads of ClusterQueues that list it in"
          " spec.admissionChecks or spec.admissionChecksStrategy"
          " (https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/,"
          " https://kueue.sigs.k8s.io/docs/concepts/admission_check/);"
          " workloads of other ClusterQueues are admitted on quota alone, and"
          " no ProvisioningRequest is created for them.",
      )
    elif ac_name:
      ctx.add(
          None,
          f"ADMISSIONCHECK_FACTS ({ac_name}):"
          f" controllerName={ac_spec.get('controllerName')},"
          f" parametersRef={p_ref}, referenced by"
          f" ClusterQueue(s)={_ac_referencing_cqs(ctx, ac_name)}",
      )
  for wl in ctx.workloads:
    wl_ref = f"Workload/{k8s.namespace(wl)}/{k8s.name(wl)}"
    status = k8s.status(wl)
    requeue = k8s.as_dict(status.get("requeueState"))
    for ac_st in k8s.dict_items(status.get("admissionChecks")):
      ac_name = str(ac_st.get("name", ""))
      state = str(ac_st.get("state", ""))
      msg = str(ac_st.get("message", ""))[:300]
      retry_count = ac_st.get("retryCount")
      requeue_str = f", requeueState={requeue}" if requeue else ""
      retry_str = (
          f", retryCount={retry_count}" if retry_count is not None else ""
      )
      key = (
          f"provreq:wl-ac:{ac_name}:{state}"
          if state in ("Retry", "Rejected") or (state == "Pending" and msg)
          else None
      )
      ctx.add(
          key,
          f"WORKLOAD_ADMISSIONCHECK_FACTS: [{wl_ref}] admissionCheck={ac_name}"
          f" state={state}{retry_str}{requeue_str}"
          + (f": {msg}" if msg else ""),
      )


def emit_provisioning_requests(ctx: FactContext) -> None:
  """1e. ProvisioningRequest objects and conditions."""
  for pr in ctx.provreqs:
    pr_name = k8s.name(pr)
    pr_ref = f"ProvisioningRequest/{k8s.ref(pr)}"
    owners = [
        f"{o.get('kind')}/{o.get('name')}"
        for o in k8s.owner_refs(pr)
        if o.get("name")
    ]
    status = k8s.status(pr)
    cond_parts: list[str] = []
    bad_reasons: list[str] = []
    for c in k8s.conditions(pr):
      ct = str(c.get("type", ""))
      cs = str(c.get("status", ""))
      cr = str(c.get("reason", ""))
      cm = str(c.get("message", ""))[:240]
      cond_parts.append(
          f"{ct}={cs} (reason={cr}: {cm})" if cm else f"{ct}={cs} (reason={cr})"
      )
      if (ct in ("Provisioned", "Accepted") and cs == "False") or (
          ct in ("Failed", "BookingExpired", "CapacityRevoked") and cs == "True"
      ):
        bad_reasons.append(f"{ct}={cs}:{cr}")
    details = status.get("provisioningClassDetails") or {}
    key = f"provreq:{pr_name}:{','.join(bad_reasons)}" if bad_reasons else None
    ctx.add(
        key,
        f"PROVISIONINGREQUEST_FACTS: [{pr_ref}] owner={owners or 'none'} "
        f"provisioningClassName={k8s.spec(pr).get('provisioningClassName')} "
        f"conditions=[{'; '.join(cond_parts) or 'none'}]"
        + (f" provisioningClassDetails={details}" if details else ""),
    )


# ---------------------------------------------------------------------------
# 1f. Workload -> Pod correlation & Pod failure/gate facts
# ---------------------------------------------------------------------------


def _pods_of_workload(
    ctx: FactContext, wl: dict[str, Any]
) -> list[dict[str, Any]]:
  """Pods in the workload's namespace that reference it by label, annotation, owner or owner-name prefix."""
  wl_name = k8s.name(wl)
  wl_uid = str(k8s.metadata(wl).get("uid", ""))
  owner_names = k8s.owner_names(wl)
  matching: list[dict[str, Any]] = []
  for p in ctx.pods_by_ns.get(k8s.namespace(wl), []):
    p_name = k8s.name(p)
    p_labels = k8s.labels(p)
    if (
        p_labels.get("kueue.x-k8s.io/workload") == wl_name
        or k8s.annotations(p).get("kueue.x-k8s.io/workload") == wl_name
        or (
            wl_uid
            and p_labels.get("kueue.x-k8s.io/prebuilt-workload-name") == wl_name
        )
        or bool(owner_names & k8s.owner_names(p))
        or any(
            on and (p_name == on or p_name.startswith(on + "-"))
            for on in owner_names
        )
    ):
      matching.append(p)
  return matching


def _pod_gates(p: dict[str, Any]) -> list[str]:
  return [
      str(g.get("name", ""))
      for g in k8s.dict_items(k8s.spec(p).get("schedulingGates"))
      if g.get("name")
  ]


def _topology_gate_note(
    ctx: FactContext, status: dict[str, Any], sample_gates: list[str]
) -> tuple[bool, str]:
  """(topologyAssignment present, explanatory note when the TAS gate is held without an assignment)."""
  psa = (status.get("admission") or {}).get("podSetAssignments") or []
  has_topo_assign = any(
      isinstance(a, dict) and bool(a.get("topologyAssignment")) for a in psa
  )
  assigned_no_topo_rfs: list[str] = []
  for a in psa:
    if isinstance(a, dict):
      for fl_v in (a.get("flavors") or {}).values():
        rf_o = ctx.rf_by_name.get(str(fl_v))
        if (
            rf_o is not None
            and not (k8s.spec(rf_o).get("topologyName"))
            and str(fl_v) not in assigned_no_topo_rfs
        ):
          assigned_no_topo_rfs.append(str(fl_v))
  if "kueue.x-k8s.io/topology" not in sample_gates or has_topo_assign:
    return has_topo_assign, ""
  rf_clause = ""
  if assigned_no_topo_rfs:
    rf_clause = (
        f"; assigned ResourceFlavor(s) {assigned_no_topo_rfs} have"
        " spec.topologyName unset"
    )
  return has_topo_assign, (
      " Workload status.admission.podSetAssignments[].topologyAssignment is"
      f" absent/empty{rf_clause}. "
      "Kueue removes only the scheduling gates that it manages when it admits"
      " the workload"
      " (https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_pods/)."
  )


def _emit_workload_pod_correlation(
    ctx: FactContext, wl: dict[str, Any]
) -> None:
  """Emits missing-pod and scheduling-gate facts for an admitted Workload."""
  wl_ref = f"Workload/{k8s.namespace(wl)}/{k8s.name(wl)}"
  status = k8s.status(wl)
  conds = {str(c.get("type")): str(c.get("status")) for c in k8s.conditions(wl)}
  admitted = conds.get("Admitted") == "True" or bool(status.get("admission"))
  if (
      not admitted
      or conds.get("PodsReady") == "True"
      or conds.get("Finished") == "True"
  ):
    return
  expected_pods = sum(
      int(ps.get("count") or 0)
      for ps in k8s.dict_items(k8s.spec(wl).get("podSets"))
  )
  matching_pods = _pods_of_workload(ctx, wl)
  if expected_pods > 0 and not matching_pods:
    ctx.add(
        f"workload-pods:{wl_ref}:zero-pods",
        f"WORKLOAD_POD_FACTS: [{wl_ref}] Admitted=True (expected"
        f" {expected_pods} pod(s) across spec.podSets), but 0 matching Pod"
        f" objects exist in namespace {k8s.namespace(wl)!r} in the snapshot.",
    )
    return
  gated_count = 0
  gate_names: set[str] = set()
  for p in matching_pods:
    gates = _pod_gates(p)
    if gates:
      gated_count += 1
      gate_names.update(gates)
  if not gated_count:
    return
  sample_gates = sorted(gate_names)
  has_topo_assign, topo_note = _topology_gate_note(ctx, status, sample_gates)
  ctx.add(
      f"workload-pods:{wl_ref}:gated",
      f"WORKLOAD_POD_FACTS: [{wl_ref}] Admitted=True;"
      f" {gated_count}/{len(matching_pods)} pod(s) remain Pending with"
      f" spec.schedulingGates={sample_gates} (topologyAssignment"
      f" present={has_topo_assign}).{topo_note}",
  )


def _emit_pod_status_facts(ctx: FactContext, p: dict[str, Any]) -> None:
  """Emits container waiting and non-zero termination facts for one Pod."""
  p_ns = k8s.namespace(p)
  p_ref = f"Pod/{p_ns}/{k8s.name(p)}"
  node_name = k8s.spec(p).get("nodeName")
  for field, cs in k8s.container_statuses(p):
    cname = str(cs.get("name", ""))
    st = k8s.as_dict(cs.get("state"))
    waiting = k8s.as_dict(st.get("waiting"))
    w_reason = str(waiting.get("reason", ""))
    if w_reason and w_reason not in ("ContainerCreating", "PodInitializing"):
      w_msg = str(waiting.get("message", ""))[:240]
      ctx.add(
          f"pod-status:{p_ns}:{cname}:{w_reason}",
          f"POD_STATUS_FACT: [{p_ref}] (node={node_name}) {field}.{cname}"
          f" waiting reason={w_reason}: {w_msg}",
      )
    for t_source, t_dict in (
        ("state.terminated", st.get("terminated")),
        (
            "lastState.terminated",
            k8s.as_dict(cs.get("lastState")).get("terminated"),
        ),
    ):
      if isinstance(t_dict, dict) and t_dict.get("exitCode") not in (None, 0):
        t_reason = str(t_dict.get("reason", ""))
        t_msg = str(t_dict.get("message", ""))[:200]
        ctx.add(
            f"pod-status:{p_ns}:{cname}:exit-{t_dict.get('exitCode')}",
            f"POD_STATUS_FACT: [{p_ref}] (node={node_name}) {field}.{cname}"
            f" {t_source} exit_code={t_dict.get('exitCode')} reason={t_reason}"
            f" restartCount={cs.get('restartCount')}"
            + (f": {t_msg}" if t_msg else ""),
        )


def emit_workload_pods(ctx: FactContext) -> None:
  """1f. Workload -> Pod correlation & Pod failure/gate facts."""
  for wl in ctx.workloads:
    _emit_workload_pod_correlation(ctx, wl)
  for p in ctx.pods:
    _emit_pod_status_facts(ctx, p)


# ---------------------------------------------------------------------------
# 2 / 3. Events
# ---------------------------------------------------------------------------


def emit_warning_events(ctx: FactContext) -> None:
  """Emits section 2 deduplicated Warning events ordered newest first."""
  seen_ids: set[tuple[str, str, str]] = set()
  warnings: list[tuple[str, str, str]] = []
  for ev in ctx.events:
    if str(ev.get("type", "")) != "Warning":
      continue
    ident = _event_identity(ev)
    if ident in seen_ids:
      continue
    seen_ids.add(ident)
    # Kind is deliberately left out of the key so the same event seen in the
    # controller log (trace_logs.py) shares the id.
    group = report_output.fact_group_key(
        "event", "", str(ev.get("reason", "")), str(ev.get("message", ""))
    )
    warnings.append((k8s.event_timestamp(ev), _event_summary(ev), group))
  warnings.sort(key=lambda t: t[0], reverse=True)
  for ts, line, group in warnings[:25]:
    ctx.add(group, f"WARNING_EVENT: {ts + ' ' if ts else ''}{line}")
  if len(warnings) > 25:
    ctx.add(
        None,
        f"WARNING_EVENT: ... {len(warnings) - 25} more Warning events omitted"
        " (oldest)",
    )


def emit_deletion_events(ctx: FactContext) -> None:
  """Emits section 3 non-housekeeping object deletion Events newest first."""
  deletions: list[tuple[str, str, str]] = []
  for ev in ctx.events:
    msg = str(ev.get("message", ""))
    reason = str(ev.get("reason", ""))
    obj = k8s.as_dict(ev.get("involvedObject"))
    if str(obj.get("kind", "")) in _HOUSEKEEPING_EVENT_KINDS:
      continue
    if re.search(r"\bdelet(?:ed|ing|ion)\b", msg, re.IGNORECASE) or re.search(
        r"(?<![a-z])delet", reason, re.IGNORECASE
    ):
      deletions.append((
          k8s.event_timestamp(ev),
          _event_summary(ev),
          f"deletion:{obj.get('kind', '')}:{reason}",
      ))
  deletions.sort(key=lambda t: t[0], reverse=True)
  for ts, line, group in deletions[:10]:
    ctx.add(group, f"DELETION_EVENT: {ts + ' ' if ts else ''}{line}")
  if len(deletions) > 10:
    ctx.add(
        None,
        f"DELETION_EVENT: ... {len(deletions) - 10} more deletion-related"
        " events omitted (oldest)",
    )


# ---------------------------------------------------------------------------
# 4. ClusterQueue facts
# ---------------------------------------------------------------------------


def _cq_status_parts(status: dict[str, Any]) -> list[str]:
  """Formats workload counts, fair-sharing share, and borrowed quota."""
  status_parts: list[str] = []
  if "admittedWorkloads" in status or "pendingWorkloads" in status:
    status_parts.append(
        f"admittedWorkloads={status.get('admittedWorkloads', 0)},"
        f" pendingWorkloads={status.get('pendingWorkloads', 0)}"
    )
  fs_ws = (
      (status.get("fairSharing") or {}).get("weightedShare")
      if isinstance(status.get("fairSharing"), dict)
      else None
  )
  if fs_ws is not None:
    status_parts.append(f"fairSharing.weightedShare={fs_ws}")
  borrowed_parts: list[str] = []
  for fu in k8s.dict_items(
      status.get("flavorsUsage") or status.get("flavorsReservation") or []
  ):
    fl_n = fu.get("name", "")
    for r_u in k8s.dict_items(fu.get("resources")):
      if r_u.get("borrowed") and str(r_u.get("borrowed")) != "0":
        borrowed_parts.append(
            f"{fl_n}.{r_u.get('name')}:"
            f" total={r_u.get('total')}/borrowed={r_u.get('borrowed')}"
        )
  if borrowed_parts:
    status_parts.append(f"borrowed=[{', '.join(borrowed_parts)}]")
  return status_parts


def emit_clusterqueues(ctx: FactContext) -> None:
  """Emits section 4 ClusterQueue strategy, cohort, quota, and preemption."""
  for cq in ctx.cqs:
    cq_name = k8s.name(cq)
    spec = k8s.spec(cq)
    q_strat = spec.get("queueingStrategy", "BestEffortFIFO")
    cohort = _cq_cohort(cq)
    quotas = _resource_quota_summary(cq)
    quota_str = "; ".join(
        f"{res}: [{', '.join(v)}]" for res, v in sorted(quotas.items())
    )
    status_parts = _cq_status_parts(k8s.status(cq))
    status_suffix = (
        f"; status: {', '.join(status_parts)}" if status_parts else ""
    )
    fs_w = k8s.as_dict(spec.get("fairSharing")).get("weight")
    fs_str = f"; fairSharing.weight={fs_w}" if fs_w is not None else ""
    ctx.add(
        None,
        f"CLUSTERQUEUE_FACTS ({cq_name}): queueingStrategy={q_strat};"
        f" cohort={cohort or 'none'}{fs_str};"
        f" {quota_str or 'no resourceGroups'}{status_suffix}",
    )
    if q_strat == "StrictFIFO":
      ctx.add(
          None,
          f"CLUSTERQUEUE_FACTS ({cq_name}): StrictFIFO semantics — the head"
          " workload is admitted before any workload behind it is considered;"
          " while the head cannot fit, the workloads queued behind it (ordered"
          " by priority, then creation time) in the same ClusterQueue remain"
          " pending even if they would fit.",
      )
    preemption = (
        spec.get("preemption")
        if isinstance(spec.get("preemption"), dict)
        else None
    )
    if preemption:
      bwc_obj = preemption.get("borrowWithinCohort")
      bwc = bwc_obj.get("policy") if isinstance(bwc_obj, dict) else None
      reclaim = preemption.get("reclaimWithinCohort")
      within = preemption.get("withinClusterQueue")
      ctx.add(
          None,
          f"CLUSTERQUEUE_FACTS ({cq_name}):"
          f" preemption.withinClusterQueue={within or 'Never (default)'},"
          f" preemption.reclaimWithinCohort={reclaim or 'Never (default)'},"
          f" preemption.borrowWithinCohort.policy={bwc or 'Never (default)'}."
          " Preemption settings govern evicting running workloads; they do not"
          " enable or disable borrowing of idle cohort quota.",
      )


def emit_cohort_cpu_arithmetic(ctx: FactContext) -> None:
  """Emits section 4b sibling ClusterQueue CPU quota arithmetic per cohort."""
  for cohort, members in sorted(ctx.cohort_map.items()):
    if len(members) < 2:
      continue
    quotas_by_name = {k8s.name(m): _cpu_quota(m) for m in members}
    unparsed = [
        f"{name} ({'; '.join(q['unparsed'])})"
        for name, q in quotas_by_name.items()
        if q["unparsed"]
    ]
    if unparsed:
      ctx.add(
          None,
          f"COHORT_CPU_ARITHMETIC (cohort={cohort}): not computed — unparsable"
          f" cpu quantity on {', '.join(unparsed)}",
      )
      continue
    total_lendable = sum(q["lendable"] for q in quotas_by_name.values())
    rows: list[str] = []
    for name, q in sorted(quotas_by_name.items()):
      from_siblings = total_lendable - q["lendable"]
      bl = q["borrowing_limit"]
      borrowable = from_siblings if bl is None else min(from_siblings, bl)
      bound = q["nominal"] + borrowable
      rows.append(
          f"{name}: nominal={_fmt_num(q['nominal'])}"
          f" lendable={_fmt_num(q['lendable'])} "
          f"borrowingLimit={'unset' if bl is None else _fmt_num(bl)} "
          f"-> nominal+borrowable-from-siblings={_fmt_num(q['nominal'])}+{_fmt_num(borrowable)}={_fmt_num(bound)}"
      )
    shown = rows[:20]
    more = f"; ... {len(rows) - 20} more members" if len(rows) > 20 else ""
    if ctx.cohort_objects:
      cohort_obj_note = (
          f" {len(ctx.cohort_objects)} Cohort object(s) present in snapshot —"
          " quota defined on a Cohort or inherited from a parent cohort is NOT"
          " included below."
      )
    else:
      cohort_obj_note = (
          " No Cohort objects in snapshot; quota defined on a Cohort or"
          " parent cohort (if any) is not included."
      )
    ctx.add(
        None,
        f"COHORT_CPU_ARITHMETIC (cohort={cohort}, members={len(members)}):"
        " per-flavor cpu totals; lendable = sum over flavors of"
        " min(lendingLimit, nominalQuota); borrowable-from-siblings = min(sum"
        " of siblings' lendable, own borrowingLimit), assuming siblings are"
        f" idle.{cohort_obj_note} "
        + "; ".join(shown)
        + more,
    )


def _node_capacity_summary(
    matching_nodes: list[dict[str, Any]],
) -> tuple[int, int, list[str]]:
  """(ready count, unschedulable count, per-resource max/sum of allocatable) over the given nodes."""
  ready = 0
  unschedulable = 0
  per_res: dict[str, list[float]] = {}
  for n in matching_nodes:
    if k8s.spec(n).get("unschedulable"):
      unschedulable += 1
    if any(
        c.get("type") == "Ready" and str(c.get("status")) == "True"
        for c in k8s.conditions(n)
    ):
      ready += 1
    for r_name, r_val in (k8s.status(n).get("allocatable") or {}).items():
      if (
          r_name in ("cpu", "memory", "ephemeral-storage")
          or "/" in str(r_name)
          or str(r_name).startswith("hugepages-")
      ):
        q = _parse_quantity(r_val)
        if q is not None:
          per_res.setdefault(str(r_name), []).append(q)
  res_parts = [
      f"{r}: max/node={_fmt_qty(max(vals), r)}, sum={_fmt_qty(sum(vals), r)}"
      for r, vals in sorted(per_res.items())
  ]
  return ready, unschedulable, res_parts


def emit_flavor_node_capacity(ctx: FactContext) -> None:
  """Emits section 4c observational Node capacity per ResourceFlavor."""
  if not ctx.nodes:
    return
  for fl_name, rf in sorted(ctx.rf_by_name.items()):
    rf_labels = _rf_node_labels(rf)
    if not isinstance(rf_labels, dict):
      ctx.add(
          None,
          f"FLAVOR_NODE_CAPACITY (flavor={fl_name}): spec.nodeLabels is not a"
          f" mapping ({type(rf_labels).__name__}); node matching skipped.",
      )
      continue
    matching_nodes = _nodes_matching_labels(ctx.nodes, rf_labels)
    if not matching_nodes:
      ctx.add(
          None,
          f"FLAVOR_NODE_CAPACITY (flavor={fl_name}):"
          f" nodeLabels={rf_labels or {}}; 0 matching Node(s) in the snapshot.",
      )
      continue
    ready, unschedulable, res_parts = _node_capacity_summary(matching_nodes)
    ctx.add(
        None,
        f"FLAVOR_NODE_CAPACITY (flavor={fl_name}):"
        f" nodeLabels={rf_labels or {}}; {len(matching_nodes)} matching Node(s)"
        " (label equality,"
        " https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/;"
        " a TAS flavor additionally requires its Topology level labels),"
        f" Ready={ready}, unschedulable={unschedulable}; allocatable"
        f" {'; '.join(res_parts) or 'n/a'}. Snapshot observation: nodeLabels"
        " select the Node set the flavor's pods may land on"
        " (https://kueue.sigs.k8s.io/docs/concepts/resource_flavor/); these"
        " figures carry no verdict without a scheduler or controller message"
        " on this workload's pods or Workload.",
    )


# ---------------------------------------------------------------------------
# 4d. Cohort quota layout and cohort nominalQuota vs Node allocatable
# ---------------------------------------------------------------------------

_FlavorRes = tuple[str, str]
_MemberEntry = tuple[str, float, dict[str, Any]]


@dataclasses.dataclass
class _CohortLayout:
  """Aggregated nominal quota and member entries for one cohort."""

  cohort: str
  members: list[dict[str, Any]]
  nominal: dict[_FlavorRes, float] = dataclasses.field(default_factory=dict)
  pairs: dict[_FlavorRes, list[_MemberEntry]] = dataclasses.field(
      default_factory=dict
  )

  def __post_init__(self) -> None:
    for m in self.members:
      m_name = k8s.name(m)
      for _, fl, res in k8s.flavor_quotas(m):
        if not fl.get("name") or not res.get("name"):
          continue
        key = (str(fl["name"]), str(res["name"]))
        nom = _parse_quantity(res.get("nominalQuota"))
        if nom is not None:
          self.nominal[key] = self.nominal.get(key, 0.0) + nom
          self.pairs.setdefault(key, []).append((m_name, nom, m))

  @property
  def has_reclaim_or_fs(self) -> bool:
    return any(
        (
            k8s.as_dict(k8s.spec(m).get("preemption")).get(
                "reclaimWithinCohort"
            )
            in ("Any", "LowerPriority")
        )
        or bool(k8s.spec(m).get("fairSharing"))
        for m in self.members
    )

  def member_layout(self, fl_name: str, r_name: str) -> list[str]:
    """Per-member nominal/borrowingLimit/lendingLimit and status reservation for one flavor+resource."""
    out_rows: list[str] = []
    for m_name, m_nom, m_cq in self.pairs.get((fl_name, r_name), []):
      bl_v = ld_v = None
      for _, fl, res in k8s.flavor_quotas(m_cq):
        if str(fl.get("name")) == fl_name and str(res.get("name")) == r_name:
          bl_v = _parse_quantity(res.get("borrowingLimit"))
          ld_v = _parse_quantity(res.get("lendingLimit"))
      m_status = k8s.status(m_cq)
      reserved, borrowed = _flavor_reservation(m_status, fl_name, r_name)
      out_rows.append(
          f"{m_name}(nominal={_fmt_qty(m_nom, r_name)},"
          f" borrowingLimit={'unset' if bl_v is None else _fmt_qty(bl_v, r_name)},"
          f" lendingLimit={'unset' if ld_v is None else _fmt_qty(ld_v, r_name)},"
          f" reserved={_fmt_qty(reserved, r_name)},"
          f" borrowed={_fmt_qty(borrowed, r_name)},"
          f" admitted={int(m_status.get('admittedWorkloads') or 0)},"
          f" pending={int(m_status.get('pendingWorkloads') or 0)})"
      )
    return out_rows


def _flavor_reservation(
    cq_status: dict[str, Any], fl_name: str, r_name: str
) -> tuple[float | None, float | None]:
  """(total, borrowed) of `status.flavorsReservation` for one flavor+resource (last match wins)."""
  reserved = borrowed = None
  for fr in k8s.dict_items(cq_status.get("flavorsReservation")):
    if str(fr.get("name")) == fl_name:
      for rr in k8s.dict_items(fr.get("resources")):
        if str(rr.get("name")) == r_name:
          reserved = _parse_quantity(rr.get("total"))
          borrowed = _parse_quantity(rr.get("borrowed"))
  return reserved, borrowed


def _borrowing_active(
    entries: list[_MemberEntry], fl_name: str, r_name: str
) -> bool:
  """True when a zero-nominal member has workloads or any member reports borrowed > 0."""
  for _, s_nom, s_cq in entries:
    s_st = k8s.status(s_cq)
    if s_nom == 0 and (
        int(s_st.get("admittedWorkloads") or 0) > 0
        or int(s_st.get("pendingWorkloads") or 0) > 0
    ):
      return True
    for fr in k8s.dict_items(s_st.get("flavorsReservation")):
      if str(fr.get("name")) == fl_name:
        for rr in k8s.dict_items(fr.get("resources")):
          if (
              str(rr.get("name")) == r_name
              and (_parse_quantity(rr.get("borrowed")) or 0) > 0
          ):
            return True
  return False


def _emit_cohort_layout_facts(ctx: FactContext, layout: _CohortLayout) -> None:
  for (fl_name, r_name), total_nom in sorted(layout.nominal.items()):
    if total_nom <= 0 or not layout.has_reclaim_or_fs:
      continue
    entries = layout.pairs.get((fl_name, r_name), [])
    if len(entries) < 2:
      continue
    borrowing_active = _borrowing_active(entries, fl_name, r_name)
    ctx.add(
        f"cohort-layout:{layout.cohort}:layout:{fl_name}:{r_name}"
        if borrowing_active
        else None,
        f"COHORT_QUOTA_LAYOUT (cohort={layout.cohort}, flavor={fl_name},"
        f" resource={r_name}): cohort nominalQuota total"
        f" {_fmt_qty(total_nom, r_name)}; reclaimWithinCohort or fairSharing is"
        " set on at least one member. Members:"
        f" {'; '.join(layout.member_layout(fl_name, r_name))}. A ClusterQueue"
        " admits beyond its nominalQuota by borrowing nominalQuota that is"
        " unused by cohort members or defined on the Cohort / parent Cohorts"
        " (Cohort.spec.resourceGroups, not included in the totals above), and"
        " workloads admitted on borrowed quota are preemption candidates when"
        " a sibling reclaims (spec.preemption.reclaimWithinCohort) or fair"
        " sharing rebalances"
        " (https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/,"
        " https://kueue.sigs.k8s.io/docs/concepts/preemption/).",
    )


def _emit_cohort_node_arithmetic(
    ctx: FactContext, layout: _CohortLayout
) -> None:
  """Emits cohort nominalQuota vs matching Node allocatable facts."""
  cohort = layout.cohort
  for (fl_name, r_name), total_nom in sorted(layout.nominal.items()):
    rf = ctx.rf_by_name.get(fl_name)
    if rf is None:
      ctx.add(
          None,
          f"COHORT_RESOURCE_ARITHMETIC (cohort={cohort}, flavor={fl_name},"
          f" resource={r_name}): ResourceFlavor object not in snapshot; node"
          " arithmetic skipped.",
      )
      continue
    rf_labels = k8s.spec(rf).get("nodeLabels") or {}
    if not isinstance(rf_labels, dict):
      continue
    matching_nodes = _nodes_matching_labels(ctx.nodes, rf_labels)
    if not matching_nodes:
      continue
    match_note = (
        " (nodeLabels unset: every Node counts)" if not rf_labels else ""
    )
    node_alloc = sum(
        _parse_quantity((k8s.status(n).get("allocatable") or {}).get(r_name))
        or 0.0
        for n in matching_nodes
    )
    if node_alloc > 0 and total_nom > node_alloc:
      ctx.add(
          f"cohort-overcommit:{cohort}:overcommit:{fl_name}:{r_name}",
          f"COHORT_RESOURCE_ARITHMETIC (cohort={cohort}, flavor={fl_name},"
          f" resource={r_name}): sum of member ClusterQueue nominalQuota is"
          f" {_fmt_qty(total_nom, r_name)}; allocatable {r_name} on the"
          f" {len(matching_nodes)} matching Node(s){match_note} in the snapshot"
          f" is {_fmt_qty(node_alloc, r_name)}. Members:"
          f" {'; '.join(layout.member_layout(fl_name, r_name))}. Quota defined"
          " on the Cohort or parent Cohorts (Cohort.spec.resourceGroups), if"
          " any, is not included in the sum. For non-TAS flavors admission is"
          " decided against declared quota, not node allocatable. nominalQuota"
          " is the quantity of this resource that is available for a"
          " ClusterQueue at a specific time"
          " (https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/); whether"
          " capacity beyond the snapshot's nodes is reachable is not visible"
          " from the snapshot.",
      )


def emit_cohort_layout(ctx: FactContext) -> None:
  """Emits section 4d cohort quota layout and Node allocatable comparisons."""
  for cohort, members in sorted(ctx.cohort_map.items()):
    if len(members) < 2:
      continue
    layout = _CohortLayout(cohort, members)
    _emit_cohort_layout_facts(ctx, layout)
    if ctx.nodes:
      _emit_cohort_node_arithmetic(ctx, layout)


# ---------------------------------------------------------------------------
# 5 / 6. ProvisioningRequestConfig and KueueConfiguration
# ---------------------------------------------------------------------------


def emit_provisioning_request_configs(ctx: FactContext) -> None:
  """5. ProvisioningRequestConfig facts."""
  for prc in ctx.prcs:
    prc_name = k8s.name(prc)
    spec = k8s.spec(prc)
    retry = k8s.as_dict(spec.get("retryStrategy"))
    is_default_retry = (
        retry.get("backoffLimitCount") == 3
        and retry.get("backoffBaseSeconds") == 60
        and retry.get("backoffMaxSeconds") == 1800
    )
    if is_default_retry:
      retry_desc: Any = (
          f"{retry} (standard Kueue default values — normal retry behavior, not"
          " a misconfiguration)"
      )
    else:
      retry_desc = (
          retry
          or "unset (defaults: backoffLimitCount=3, backoffBaseSeconds=60, backoffMaxSeconds=1800)"
      )
    ctx.add(
        None,
        f"PROVISIONINGREQUESTCONFIG_FACTS ({prc_name}):"
        f" provisioningClassName={spec.get('provisioningClassName')};"
        f" managedResources={spec.get('managedResources')};"
        f" retryStrategy={retry_desc}",
    )
    if retry.get("backoffBaseSeconds") == 0:
      ctx.add(
          None,
          f"PROVISIONINGREQUESTCONFIG_FACTS ({prc_name}):"
          " retryStrategy.backoffBaseSeconds=0, so the exponential retry delay"
          " (min(backoffBaseSeconds^n, backoffMaxSeconds),"
          " https://kueue.sigs.k8s.io/docs/concepts/admission_check/provisioning_request/)"
          " evaluates to 0 seconds for every attempt.",
      )


def _load_manager_config(
    ctx: FactContext, cm: dict[str, Any]
) -> dict[str, Any] | None:
  """Parses `controller_manager_config.yaml`; emits parse facts and returns None when there is nothing to inspect."""
  dup_info = cm.get("_yaml_duplicate_keys")
  if isinstance(dup_info, list) and dup_info:
    ctx.add(
        "config:duplicate-yaml-key",
        "KUEUECONFIGURATION_FACTS: ConfigMap kueue-manager-config YAML source"
        " contains duplicate mapping key(s): "
        + "; ".join(str(x) for x in dup_info)
        + ".",
    )
  cfg_raw = k8s.as_dict(cm.get("data")).get(k8s.KUEUE_CONFIG_KEY) or ""
  if not cfg_raw:
    return None
  try:
    cfg = yaml.safe_load(cfg_raw)
  except yaml.YAMLError as exc:
    ctx.add(
        "config:parse-error",
        "KUEUECONFIGURATION_FACTS: controller_manager_config.yaml failed to"
        f" parse as YAML: {exc}",
    )
    return None
  if not isinstance(cfg, dict):
    ctx.add(
        None,
        "KUEUECONFIGURATION_FACTS: controller_manager_config.yaml top level is"
        f" {type(cfg).__name__}, not a mapping",
    )
    return None
  return cfg


def _emit_config_general_facts(ctx: FactContext, cfg: dict[str, Any]) -> None:
  """Emits general integrations, client, leader-election, and retention facts."""
  if "manageJobsWithoutQueueName" in cfg:
    ctx.add(
        None,
        "KUEUECONFIGURATION_FACTS:"
        f" manageJobsWithoutQueueName={cfg.get('manageJobsWithoutQueueName')}, "
        f"integrations.frameworks={(cfg.get('integrations') or {}).get('frameworks') if isinstance(cfg.get('integrations'), dict) else None}",
    )
  if any(
      k in cfg for k in ("clientConnection", "leaderElection", "fairSharing")
  ):
    cc = k8s.as_dict(cfg.get("clientConnection"))
    le = k8s.as_dict(cfg.get("leaderElection"))
    fs = k8s.as_dict(cfg.get("fairSharing"))
    parts_cfg: list[str] = []
    if cc:
      parts_cfg.append(
          f"clientConnection={{qps: {cc.get('qps')}, burst: {cc.get('burst')}}}"
      )
    if le:
      parts_cfg.append(
          f"leaderElection={{leaderElect: {le.get('leaderElect')},"
          f" leaseDuration: {le.get('leaseDuration')}, renewDeadline:"
          f" {le.get('renewDeadline')}, retryPeriod: {le.get('retryPeriod')}}}"
      )
    if fs:
      parts_cfg.append(f"fairSharing={fs}")
    if parts_cfg:
      ctx.add(None, "KUEUECONFIGURATION_FACTS: " + ", ".join(parts_cfg))
  if "objectRetentionPolicies" in cfg:
    orp = k8s.as_dict(cfg.get("objectRetentionPolicies"))
    w_orp = k8s.as_dict(orp.get("workloads"))
    ctx.add(
        None,
        "KUEUECONFIGURATION_FACTS:"
        f" objectRetentionPolicies.workloads={w_orp or orp} "
        "(Kueue deletes finished Workloads after afterFinished and"
        " Kueue-deactivated Workloads after "
        "afterDeactivatedByKueue —"
        " https://kueue.sigs.k8s.io/docs/tasks/manage/setup_object_retention_policy/)",
    )


def _emit_config_wait_for_pods_ready(
    ctx: FactContext, cfg: dict[str, Any]
) -> None:
  """Emits waitForPodsReady configuration and requeuingStrategy facts."""
  if "waitForPodsReady" not in cfg:
    return
  wfpr = cfg.get("waitForPodsReady")
  if not isinstance(wfpr, dict):
    ctx.add(
        None,
        f"KUEUECONFIGURATION_FACTS: waitForPodsReady is {type(wfpr).__name__}"
        f" ({wfpr!r}); the API expects a mapping"
        " (https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/).",
    )
    return
  req_strat = k8s.as_dict(wfpr.get("requeuingStrategy"))
  blc = req_strat.get("backoffLimitCount")
  # config v1beta1 has 'enable'; v1beta2 removed it (presence of the block
  # enables the feature).
  if str(cfg.get("apiVersion") or "").endswith("v1beta1"):
    enabled = bool(wfpr.get("enable", False))
    enable_str = f"enable={wfpr.get('enable')}"
  else:
    enabled = True
    enable_str = (
        "present (config v1beta2 has no `enable` field; the block being present"
        " turns the feature on)"
    )
  blc_note = ""
  if enabled and blc is None:
    blc_note = (
        " (unset is the Kueue default — null means requeues after a"
        " PodsReadyTimeout eviction are unbounded; "
        "this field only matters if workloads actually show Evicted"
        " reason=PodsReadyTimeout with a growing "
        "status.requeueState.count —"
        " https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/)"
    )
  ctx.add(
      None,
      f"KUEUECONFIGURATION_FACTS: waitForPodsReady {enable_str},"
      f" timeout={wfpr.get('timeout')},"
      f" blockAdmission={wfpr.get('blockAdmission')},"
      f" recoveryTimeout={wfpr.get('recoveryTimeout')},"
      f" requeuingStrategy.backoffLimitCount={'unset' if blc is None else blc}"
      + blc_note,
  )


def _transform_candidate_cqs(
    ctx: FactContext, inp: str, outputs: list[str]
) -> set[str]:
  """ClusterQueue names targeted by Workloads/Events using `inp`/`outputs` via LocalQueues."""
  targets = {t for t in (inp, *outputs) if t}
  cqs: set[str] = set()
  for wl in ctx.workloads:
    q_name = str(k8s.spec(wl).get("queueName") or "")
    lq = ctx.lq_by_ref.get(f"{k8s.namespace(wl)}/{q_name}") if q_name else None
    cq_n = str(k8s.spec(lq).get("clusterQueue") or "") if lq else ""
    if cq_n and any(
        t in str(k8s.spec(wl)) or t in str(k8s.status(wl)) for t in targets
    ):
      cqs.add(cq_n)
  for ev in ctx.events:
    msg = str(ev.get("message") or "")
    if any(t in msg for t in targets):
      ev_ns = str(
          k8s.as_dict(ev.get("involvedObject")).get("namespace")
          or k8s.namespace(ev)
      )
      for lq in ctx.lqs:
        if not ev_ns or k8s.namespace(lq) == ev_ns:
          cq_n = str(k8s.spec(lq).get("clusterQueue") or "")
          if cq_n:
            cqs.add(cq_n)
  if not cqs:
    cqs = {
        str(k8s.spec(lq).get("clusterQueue") or "")
        for lq in ctx.lqs
        if k8s.spec(lq).get("clusterQueue")
    }
  return cqs


def _emit_config_transformations(ctx: FactContext, cfg: dict[str, Any]) -> None:
  """Emits resources.transformations facts and missing ClusterQueue outputs."""
  transforms = k8s.as_dict(cfg.get("resources")).get("transformations") or []
  for tr in k8s.dict_items(transforms):
    inp = tr.get("input", "")
    strategy = tr.get("strategy", "Retain")
    outputs = list(k8s.as_dict(tr.get("outputs")).keys())
    replace_note = ""
    if strategy == "Replace":
      replace_note = (
          " (with strategy Replace the input resource is removed from the"
          " effective request and only the outputs are counted against quota)"
      )
    ctx.add(
        None,
        f"KUEUECONFIGURATION_FACTS: resources.transformations entry input={inp}"
        f" strategy={strategy} outputs={outputs}"
        + replace_note,
    )
    if strategy != "Replace":
      continue
    candidate_cqs = _transform_candidate_cqs(ctx, inp, outputs)
    for cq in ctx.cqs:
      covered: list[str] = []
      for rg in k8s.resource_groups(cq):
        covered.extend(str(r) for r in rg.get("coveredResources") or [])
      participates = (
          inp in covered
          or any(o in covered for o in outputs)
          or k8s.name(cq) in candidate_cqs
      )
      missing = [o for o in outputs if o not in covered]
      if participates and missing:
        ctx.add(
            None,
            f"KUEUECONFIGURATION_FACTS: ClusterQueue {k8s.name(cq)} covers"
            f" input {inp!r}: {inp in covered}; coveredResources={covered} does"
            f" not include transformation output(s) {missing}",
        )


def emit_kueue_configuration(ctx: FactContext) -> None:
  """6. KueueConfiguration (kueue-manager-config) facts."""
  for cm in ctx.configmaps:
    if k8s.metadata(cm).get("name") != "kueue-manager-config":
      continue
    cfg = _load_manager_config(ctx, cm)
    if cfg is None:
      continue
    _emit_config_general_facts(ctx, cfg)
    _emit_config_wait_for_pods_ready(ctx, cfg)
    _emit_config_transformations(ctx, cfg)


# ---------------------------------------------------------------------------
# 7 / 8. ResourceFlavor <-> Node label matching, Node taints and conditions
# ---------------------------------------------------------------------------


def _rf_label_breakdown(
    nodes: list[dict[str, Any]], labels: dict[str, Any]
) -> tuple[list[str], bool, bool]:
  """Per-key match counts; (rows, some key matches a node, some key matches none)."""
  per_key: list[str] = []
  some_match = False
  zero_match = False
  for k, v in labels.items():
    exact = sum(1 for n in nodes if k8s.labels(n).get(k) == v)
    other_vals = sorted({
        str(k8s.labels(n).get(k))
        for n in nodes
        if k in k8s.labels(n) and k8s.labels(n).get(k) != v
    })
    if exact > 0:
      some_match = True
    else:
      zero_match = True
    if other_vals:
      per_key.append(
          f"{k}={v!r} on {exact}/{len(nodes)} nodes (other values on nodes:"
          f" {other_vals[:4]})"
      )
    else:
      per_key.append(f"{k}={v!r} on {exact}/{len(nodes)} nodes")
  return per_key, some_match, zero_match


def _emit_rf_node_match(
    ctx: FactContext, rf: dict[str, Any], base: str, labels: dict[str, Any]
) -> None:
  """Emits Node label-matching count and per-key breakdown for one flavor."""
  rf_name = k8s.name(rf)
  matching = _nodes_matching_labels(ctx.nodes, labels)
  rf_key = None
  detail = (
      f"; {len(matching)} of {len(ctx.nodes)} nodes in the snapshot carry all"
      " of these labels."
  )
  if not matching and len(labels) >= 1:
    per_key, _, zero_match = _rf_label_breakdown(ctx.nodes, labels)
    detail += " Per-key breakdown: " + ", ".join(per_key) + "."
    mf = k8s.compact_managed_fields(k8s.metadata(rf).get("managedFields") or [])
    if mf:
      detail += f" managedFieldsSummary={mf}."
    if zero_match:
      rf_key = f"nodeselector:rf:{rf_name}"
  ctx.add(rf_key, base + detail)


def emit_flavor_node_labels(ctx: FactContext) -> None:
  """Emits section 7 ResourceFlavor <-> Node label matching facts."""
  if ctx.rfs:
    ctx.add(
        None,
        f"RESOURCEFLAVOR_FACTS: {len(ctx.rfs)} ResourceFlavor(s); label"
        f" matching below uses the {len(ctx.nodes)} Node object(s) in the"
        " snapshot only — nodes created later by an autoscaler or a"
        " ProvisioningRequest are not represented.",
    )
  for rf in ctx.rfs:
    spec = k8s.spec(rf)
    labels = k8s.as_dict(spec.get("nodeLabels"))
    taints = k8s.as_list(spec.get("nodeTaints"))
    tolerations = k8s.as_list(spec.get("tolerations"))
    base = (
        f"RESOURCEFLAVOR_FACTS ({k8s.name(rf)}): nodeLabels={labels or '{}'};"
        f" topologyName={spec.get('topologyName')}; nodeTaints={len(taints)};"
        f" tolerations={len(tolerations)}"
    )
    if not labels:
      ctx.add(
          None,
          base
          + "; empty nodeLabels places no node-label constraint (matches any"
          " node).",
      )
    elif ctx.nodes:
      _emit_rf_node_match(ctx, rf, base, labels)
    else:
      ctx.add(
          None,
          base
          + "; no Node objects in the snapshot, label matching not evaluated.",
      )


def _node_pool(n: dict[str, Any]) -> Any:
  n_labels = k8s.labels(n)
  return next(
      (n_labels[k] for k in k8s.NODE_POOL_LABELS if n_labels.get(k)),
      k8s.metadata(n).get("name", ""),
  )


def emit_node_taints_and_conditions(ctx: FactContext) -> None:
  """8. Node taints and non-Ready / pressure conditions (one fact per pool)."""
  seen_taints: set[str] = set()
  seen_node_conds: set[str] = set()
  for n in ctx.nodes:
    pool = _node_pool(n)
    for t in k8s.dict_items(k8s.spec(n).get("taints")):
      if t.get("effect") in ("NoSchedule", "NoExecute"):
        t_str = f"{t.get('key')}={t.get('value')}:{t.get('effect')}"
        key = f"{pool}|{t_str}"
        if key in seen_taints:
          continue
        seen_taints.add(key)
        ctx.add(
            None,
            f"NODE_TAINT_FACTS ({pool}): taint {t_str}; pods and"
            " ResourceFlavors without a matching toleration cannot land on"
            " these nodes.",
        )
    for c in k8s.conditions(n):
      ct = str(c.get("type", ""))
      cs = str(c.get("status", ""))
      if (ct == "Ready" and cs != "True") or (ct != "Ready" and cs == "True"):
        cr = str(c.get("reason", ""))
        cm = str(c.get("message", ""))[:200]
        cond_id = f"{pool}|{ct}={cs}|{cr}"
        if cond_id in seen_node_conds:
          continue
        seen_node_conds.add(cond_id)
        ctx.add(
            f"node-cond:{pool}:{ct}:{cs}",
            f"NODE_CONDITION_FACTS ({pool}, sample"
            f" node={k8s.metadata(n).get('name', '')}): {ct}={cs} reason={cr}"
            + (f": {cm}" if cm else ""),
        )


# Registry: the orchestrator iterates this tuple; order == order of facts in
# the digest.
FACT_EMITTERS: tuple[Callable[[FactContext], None], ...] = (
    emit_inventory,  # 1
    emit_coverage,  # 1a
    emit_status_conditions,  # 1b
    emit_queue_chain,  # 1c
    emit_job_specs,  # 1c-bis
    emit_admission_checks,  # 1d
    emit_provisioning_requests,  # 1e
    emit_workload_pods,  # 1f
    workload_timeline.emit_workload_timeline,  # 1g
    emit_warning_events,  # 2
    emit_deletion_events,  # 3
    emit_clusterqueues,  # 4
    emit_cohort_cpu_arithmetic,  # 4b
    emit_flavor_node_capacity,  # 4c
    emit_cohort_layout,  # 4d
    fair_sharing_facts.emit_fair_sharing_arithmetic,  # 4e
    emit_provisioning_request_configs,  # 5
    emit_kueue_configuration,  # 6
    emit_flavor_node_labels,  # 7
    topology_facts.emit_topology_domains,  # 7b
    emit_node_taints_and_conditions,  # 8
)
