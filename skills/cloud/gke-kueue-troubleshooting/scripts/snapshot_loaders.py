"""Object loading, sanitising and grouping for `snapshot.py`.

Responsibilities:
  * reading objects from a live cluster (`kubectl`) or from an offline bundle of
    YAML/JSON manifests (`load_items`, `load_static_items`), recording every
    source that could not be read (`LoadNotes`) instead of dropping it;
  * masking Secret payloads and literal container `env[].value` entries
    (`_mask_in_place` at load, `_masked_copy` when compacting);
  * stripping Kubernetes boilerplate per kind (`sanitize_and_compact_object`);
  * filtering noise and ordering Kueue graph objects first
    (`filter_and_sort_snapshot_items`);
  * collapsing identical Nodes/Pods/Events into groups for the stdout digest
    (`group_bulk_objects`, `sample_bulk_groups`);
  * maintaining the coverage ledger (`update_ledger`).

`snapshot.py` re-exports the public names so tests keep importing them from
there.
"""

from __future__ import annotations

import argparse
import collections.abc
import dataclasses
import json
import os
import subprocess
from typing import Any, Callable

import k8s_objects as k8s
import report_output
import yaml

_GRAPH_KINDS = {
    "cohort",
    "cohorts",
    "clusterqueue",
    "clusterqueues",
    "localqueue",
    "localqueues",
    "resourceflavor",
    "resourceflavors",
    "admissioncheck",
    "admissionchecks",
    "provisioningrequestconfig",
    "provisioningrequestconfigs",
    "topology",
    "topologies",
    "workload",
    "workloads",
    "configmap",
    "configmaps",
}

# Namespaces of platform add-ons whose Pods are never part of a Kueue admission
# path: the upstream `kube-*` namespaces plus whatever the operator passes via
# --ignore-namespaces / GKE_KUEUE_TROUBLESHOOTING_IGNORE_NAMESPACES
# (see report_output).
_is_managed_addon_namespace = report_output.is_managed_addon_namespace

# Node labels shown in snapshots: anything a ResourceFlavor `nodeLabels`, a
# Topology level or a pod nodeSelector is likely to reference. Everything else
# (OS, arch, image, boot-disk, runtime, ...) is counted but not listed.
_SCHEDULING_LABEL_MARKERS = (
    "pool",
    "accelerator",
    "gpu",
    "tpu",
    "spot",
    "preemptible",
    "capacity",
    "instance",
    "topology",
    "zone",
    "region",
    "machine",
    "nodegroup",
    "placement",
    "reservation",
)

_PRIORITY_KIND_ORDER = {
    "Workload": 1,
    "LocalQueue": 2,
    "ClusterQueue": 3,
    "Cohort": 4,
    "ResourceFlavor": 5,
    "AdmissionCheck": 6,
    "ProvisioningRequestConfig": 7,
    "ProvisioningRequest": 8,
    "Topology": 9,
    "WorkloadPriorityClass": 10,
    "ConfigMap": 11,
    "Job": 12,
    "JobSet": 12,
    "LeaderWorkerSet": 12,
    "TFJob": 12,
    "PyTorchJob": 12,
    "RayJob": 12,
    "MPIJob": 12,
    "Event": 13,
    "Node": 14,
    "Pod": 15,
}

# Event involvedObject kinds that are always kept by
# `filter_and_sort_snapshot_items`.
_RELEVANT_EVENT_KINDS = (
    "workload",
    "job",
    "jobset",
    "clusterqueue",
    "localqueue",
    "admissioncheck",
    "provisioningrequest",
    "provisioningrequestconfig",
    "configmap",
)

CLUSTER_SCOPED_KINDS = (
    "clusterqueues.kueue.x-k8s.io,resourceflavors.kueue.x-k8s.io,cohorts.kueue.x-k8s.io,"
    "admissionchecks.kueue.x-k8s.io,provisioningrequestconfigs.kueue.x-k8s.io,"
    "topologies.kueue.x-k8s.io,workloadpriorityclasses.kueue.x-k8s.io,nodes"
)
NAMESPACED_KINDS = (
    "workloads.kueue.x-k8s.io,localqueues.kueue.x-k8s.io,jobs.batch,jobsets.jobset.x-k8s.io,"
    "provisioningrequests.autoscaling.x-k8s.io,pods,events"
)


def _is_scheduling_label(key: str) -> bool:
  """True for node labels that commonly drive Kueue flavor/topology matching."""
  if key in k8s.NODE_POOL_LABELS:
    return True
  prefix, sep, _ = key.partition("/")
  if (sep and prefix == "beta.kubernetes.io") or key in (
      "kubernetes.io/hostname",
      "kubernetes.io/os",
      "kubernetes.io/arch",
  ):
    return False
  low = key.lower()
  return any(marker in low for marker in _SCHEDULING_LABEL_MARKERS)


def _pod_has_failure(pod: dict[str, Any]) -> bool:
  """True when a Pod is non-Running/Succeeded or has a container waiting/terminated with an error."""
  phase = str(k8s.status(pod).get("phase") or "")
  if phase and phase not in ("Running", "Succeeded"):
    return True
  for _, cs in k8s.container_statuses(pod):
    state = k8s.as_dict(cs.get("state"))
    waiting = k8s.as_dict(state.get("waiting"))
    if waiting.get("reason") and waiting.get("reason") not in (
        "ContainerCreating",
        "PodInitializing",
    ):
      return True
    if k8s.as_dict(state.get("terminated")).get("exitCode") not in (None, 0):
      return True
    last_term = k8s.as_dict(k8s.as_dict(cs.get("lastState")).get("terminated"))
    if last_term.get("exitCode") not in (None, 0):
      return True
  return False


# ---------------------------------------------------------------------------
# Sanitising / compaction
# ---------------------------------------------------------------------------


def _compact_metadata(meta: dict[str, Any], kind: str) -> dict[str, Any]:
  """Drops noisy metadata fields; summarises managedFields for non-bulk kinds."""
  if "managedFields" in meta:
    compacted_mf = k8s.compact_managed_fields(meta.pop("managedFields"))
    if compacted_mf and kind not in ("Node", "Pod", "Event"):
      meta["managedFieldsSummary"] = compacted_mf
  for noisy_key in ("uid", "selfLink", "generation", "resourceVersion"):
    meta.pop(noisy_key, None)
  annotations = dict(k8s.as_dict(meta.get("annotations")))
  annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)
  if annotations:
    meta["annotations"] = annotations
  else:
    meta.pop("annotations", None)
  return meta


def _compact_node(out: dict[str, Any]) -> dict[str, Any]:
  """Strips non-scheduling labels, annotations, and healthy conditions on a Node."""
  meta = out["metadata"]
  status = k8s.status(out)
  all_labels = k8s.as_dict(meta.get("labels"))
  labels = {k: v for k, v in all_labels.items() if _is_scheduling_label(k)}
  hidden = len(all_labels) - len(labels)
  if hidden > 0:
    labels["<other labels omitted>"] = str(hidden)
  meta["labels"] = labels
  meta.pop("annotations", None)
  out["metadata"] = meta
  out["spec"] = {"taints": k8s.spec(out).get("taints") or []}
  allocatable = k8s.as_dict(status.get("allocatable"))
  node_conds = []
  for c in k8s.dict_items(status.get("conditions")):
    ctype = c.get("type")
    cstatus = c.get("status")
    if ctype == "Ready" or cstatus == "True":
      entry: dict[str, Any] = {"type": ctype, "status": cstatus}
      if (ctype == "Ready" and cstatus != "True") or (
          ctype != "Ready" and cstatus == "True"
      ):
        if c.get("reason"):
          entry["reason"] = c.get("reason")
        if c.get("message"):
          entry["message"] = str(c.get("message"))[:200]
      node_conds.append(entry)
  out["status"] = {
      "allocatable": {
          k: v
          for k, v in allocatable.items()
          if k in ("cpu", "memory", "pods") or "/" in k
      },
      "conditions": node_conds,
  }
  return out


def _compact_container_statuses(statuses: Any) -> list[dict[str, Any]]:
  return [
      {
          "name": cs.get("name"),
          "ready": cs.get("ready"),
          "restartCount": cs.get("restartCount"),
          "state": cs.get("state"),
          "lastState": cs.get("lastState"),
      }
      for cs in k8s.dict_items(statuses)
  ]


def _compact_pod_spec(spec: dict[str, Any]) -> dict[str, Any]:
  """Retains scheduling fields and container image/resource specs from a Pod spec."""
  containers = [
      {
          "name": c.get("name"),
          "image": c.get("image"),
          "resources": c.get("resources"),
      }
      for c in k8s.dict_items(spec.get("containers"))
  ]
  init_containers = [
      {
          "name": c.get("name"),
          "image": c.get("image"),
          "imagePullPolicy": c.get("imagePullPolicy"),
          "resources": c.get("resources"),
      }
      for c in k8s.dict_items(spec.get("initContainers"))
  ]
  pod_spec: dict[str, Any] = {
      "nodeName": spec.get("nodeName"),
      "nodeSelector": spec.get("nodeSelector"),
      "tolerations": spec.get("tolerations"),
      "containers": containers,
  }
  if spec.get("schedulingGates"):
    pod_spec["schedulingGates"] = spec.get("schedulingGates")
  if init_containers:
    pod_spec["initContainers"] = init_containers
  return pod_spec


def _compact_pod(out: dict[str, Any]) -> dict[str, Any]:
  """Compacts a Pod's metadata, spec, and container statuses for the snapshot."""
  meta = out["metadata"]
  meta.pop("annotations", None)
  out["metadata"] = meta
  out["spec"] = _compact_pod_spec(k8s.spec(out))
  status = k8s.status(out)
  pod_status: dict[str, Any] = {"phase": status.get("phase")}
  # Pod-level reason/message carry the kubelet verdict (Evicted, NodeShutdown,
  # ...) that no condition or container status repeats.
  for field in ("reason", "message"):
    if status.get(field):
      pod_status[field] = status.get(field)
  pod_status["conditions"] = status.get("conditions")
  pod_status["containerStatuses"] = _compact_container_statuses(
      status.get("containerStatuses")
  )
  if status.get("initContainerStatuses"):
    pod_status["initContainerStatuses"] = _compact_container_statuses(
        status.get("initContainerStatuses")
    )
  out["status"] = pod_status
  return out


def _compact_event(out: dict[str, Any]) -> dict[str, Any]:
  meta = out["metadata"]
  involved = k8s.as_dict(out.get("involvedObject"))
  return {
      "kind": "Event",
      "metadata": {
          "name": meta.get("name"),
          "namespace": meta.get("namespace", "default"),
      },
      "type": out.get("type"),
      "reason": out.get("reason"),
      "involvedObject": (
          f"{involved.get('kind', '')}/{involved.get('namespace', '')}/{involved.get('name', '')}"
          .strip("/")
      ),
      "message": out.get("message"),
      "lastTimestamp": (
          out.get("lastTimestamp")
          or out.get("eventTime")
          or meta.get("creationTimestamp")
      ),
  }


_KIND_COMPACTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "Node": _compact_node,
    "Pod": _compact_pod,
    "Event": _compact_event,
}


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

REDACTED = "<REDACTED>"
_MAX_TREE_DEPTH = 100
_DEPTH_PLACEHOLDER = f"<nesting below {_MAX_TREE_DEPTH} levels omitted>"


class TreeBudgetError(Exception):
  """A manifest tree is cyclic, too deep, or larger than its budget allows."""


def _env_needs_mask(entry: Any) -> bool:
  return (
      isinstance(entry, dict)
      and "value" in entry
      and entry["value"] != REDACTED
  )


def _mask_secret_payload(secret: dict[str, Any]) -> None:
  """Masks `data` / `stringData` values of a Secret in place (keys stay)."""
  for field in ("data", "stringData"):
    payload = secret.get(field)
    if isinstance(payload, dict):
      secret[field] = {k: REDACTED for k in payload}
    elif payload is not None:
      secret[field] = REDACTED


def _mask_in_place(obj: dict[str, Any]) -> None:
  """Masks a freshly loaded manifest in place.

  Secret payloads and every literal `env[].value` (whether under `containers`,
  `initContainers`, `ephemeralContainers`, or CRD fields such as
  `spec.trainer.env` / `spec.driver.env`) become `<REDACTED>`; `name`,
  `valueFrom`, `command` and `args` stay. A node shared through YAML aliases
  is visited once and stays shared.

  Args:
    obj: A manifest the loader owns (nothing else references it yet).
  """
  if obj.get("kind") == "Secret":
    _mask_secret_payload(obj)
  seen: set[int] = set()
  stack: list[Any] = [obj]
  while stack:
    node = stack.pop()
    if not isinstance(node, (dict, list)) or id(node) in seen:
      continue
    seen.add(id(node))
    if isinstance(node, list):
      stack.extend(node)
      continue
    for key, child in node.items():
      if key == "env":
        for entry in k8s.dict_items(child):
          if "value" in entry:
            entry["value"] = REDACTED
      stack.append(child)


def _masked_env_list(env: Any) -> Any:
  """An `env` list with literal `value` masked, or the same list when clean."""
  if not isinstance(env, list) or not any(map(_env_needs_mask, env)):
    return env
  return [{**e, "value": REDACTED} if _env_needs_mask(e) else e for e in env]


def _masked_copy(value: Any, depth: int = 0) -> Any:
  """`value` with literal `env[].value` entries masked, copying only what changes.

  A subtree with nothing to mask is returned as the same object, so the
  caller's input is never modified and objects that share a subtree (YAML
  aliases in a bundle) keep sharing it.

  Args:
    value: Any part of a manifest.
    depth: Nesting level; kubectl JSON deeper than `_MAX_TREE_DEPTH` is cut.

  Returns:
    `value` itself or a partial copy with the masked entries.
  """
  if not isinstance(value, (dict, list)):
    return value
  if depth > _MAX_TREE_DEPTH:
    return _DEPTH_PLACEHOLDER
  out = value
  pairs = value.items() if isinstance(value, dict) else enumerate(value)
  for key, child in pairs:
    if isinstance(value, dict) and key == "env":
      new = _masked_env_list(child)
    else:
      new = _masked_copy(child, depth + 1)
    if new is not child:
      if out is value:
        out = dict(value) if isinstance(value, dict) else list(value)
      out[key] = new
  return out


class _TreeMeter:
  """Measures manifests the way the full report writes them: every YAML alias expanded.

  Through aliases a small file can describe an arbitrarily large or a cyclic
  tree. The meter counts the nodes of the expanded tree in time proportional
  to the nodes actually stored, and raises `TreeBudgetError` for a cycle, for
  nesting deeper than `_MAX_TREE_DEPTH`, and once the manifests charged so far
  exceed `budget` nodes (no limit when `budget` is None).
  """

  def __init__(self, budget: int | None = None) -> None:
    self._left = budget
    self._known: dict[int, tuple[int, int]] = {}  # id -> (nodes, height)
    self._open: set[int] = set()

  @property
  def exhausted(self) -> bool:
    return self._left is not None and self._left < 0

  def charge(self, obj: Any) -> None:
    """Counts one manifest against the budget."""
    self._open = set()
    nodes, _ = self._measure(obj, 0)
    if self._left is not None:
      self._left -= nodes
      if self._left < 0:
        raise TreeBudgetError("YAML aliases expand past the size of the file")

  def _measure(self, node: Any, depth: int) -> tuple[int, int]:
    """Counts nodes and subtree height under `node`, rejecting deep or cyclic trees."""
    if not isinstance(node, (dict, list)):
      return 1, 0
    if depth > _MAX_TREE_DEPTH:
      raise TreeBudgetError(f"nesting deeper than {_MAX_TREE_DEPTH} levels")
    known = self._known.get(id(node))
    if known is None:
      if id(node) in self._open:
        raise TreeBudgetError("a YAML alias refers to its own ancestor")
      self._open.add(id(node))
      nodes, height = 1, 0
      for child in node.values() if isinstance(node, dict) else node:
        child_nodes, child_height = self._measure(child, depth + 1)
        nodes += child_nodes
        height = max(height, child_height + 1)
      self._open.discard(id(node))
      known = self._known[id(node)] = (nodes, height)
    if depth + known[1] > _MAX_TREE_DEPTH:
      raise TreeBudgetError(f"nesting deeper than {_MAX_TREE_DEPTH} levels")
    return known


def sanitize_and_compact_object(obj: dict[str, Any]) -> dict[str, Any]:
  """Strips Kubernetes boilerplate while preserving diagnostic signal and field attribution.

  Secret payloads and literal container `env[].value` entries are masked in
  the result; the input object is not modified.

  Args:
    obj: A raw Kubernetes object mapping.

  Returns:
    The compacted, masked object (non-mapping input is returned unchanged).
  """
  if not isinstance(obj, dict):
    return obj
  out = dict(obj)
  out.pop("_yaml_duplicate_keys", None)
  kind = str(out.get("kind", ""))
  out["metadata"] = _compact_metadata(dict(k8s.metadata(out)), kind)
  compactor = _KIND_COMPACTORS.get(kind)
  if compactor:
    out = compactor(out)
  if kind == "Secret":
    _mask_secret_payload(out)
  return _masked_copy(out)


# ---------------------------------------------------------------------------
# Bulk grouping
# ---------------------------------------------------------------------------

_BULK_NAME_SAMPLE = 5


def _signature(value: Any) -> str:
  return json.dumps(value, sort_keys=True, default=str)


def _sample_names(names: list[str]) -> list[str]:
  if len(names) <= _BULK_NAME_SAMPLE:
    return names
  return names[:_BULK_NAME_SAMPLE] + [
      f"... {len(names) - _BULK_NAME_SAMPLE} more"
  ]


_POD_STATUS_VOLATILE_KEYS = frozenset({
    "lastTransitionTime",
    "lastProbeTime",
    "startedAt",
    "finishedAt",
    "containerID",
    "imageID",
})


def _strip_volatile(value: Any) -> Any:
  """Removes timestamps and ids from a status tree so identical failures compare equal."""
  if isinstance(value, dict):
    return {
        k: _strip_volatile(v)
        for k, v in value.items()
        if k not in _POD_STATUS_VOLATILE_KEYS
    }
  if isinstance(value, list):
    return [_strip_volatile(v) for v in value]
  return value


def _pod_failure_signature(status: dict[str, Any]) -> dict[str, Any]:
  return _strip_volatile({
      "reason": status.get("reason"),
      "conditions": status.get("conditions") or [],
      "containerStatuses": status.get("containerStatuses") or [],
      "initContainerStatuses": status.get("initContainerStatuses") or [],
  })


def _group_node(groups: dict[str, dict[str, Any]], it: dict[str, Any]) -> None:
  sig = {
      "labels": k8s.metadata(it).get("labels") or {},
      "taints": k8s.spec(it).get("taints") or [],
      "allocatable": k8s.status(it).get("allocatable") or {},
      "conditions": k8s.status(it).get("conditions") or [],
  }
  g = groups.setdefault(
      _signature(sig), {"kind": "NodeGroup", "count": 0, "names": [], **sig}
  )
  g["count"] += 1
  g["names"].append(k8s.name(it))


def _group_pod(groups: dict[str, dict[str, Any]], it: dict[str, Any]) -> None:
  """Adds a compacted Pod to its matching PodGroup bucket by failure signature."""
  spec = k8s.spec(it)
  status = k8s.status(it)
  owners = [
      f"{o.get('kind', '')}/{o.get('name', '')}" for o in k8s.owner_refs(it)
  ]
  sig = {
      "namespace": k8s.namespace(it),
      "owners": owners,
      "phase": status.get("phase"),
      "scheduled": bool(spec.get("nodeName")),
      "nodeSelector": spec.get("nodeSelector"),
      "tolerations": spec.get("tolerations"),
      "schedulingGates": spec.get("schedulingGates"),
      "containers": spec.get("containers"),
      "initContainers": spec.get("initContainers"),
      "failureSignature": _pod_failure_signature(status),
  }
  g = groups.setdefault(
      _signature(sig),
      {
          "kind": "PodGroup",
          "count": 0,
          "names": [],
          "nodeNames": [],
          **{k: v for k, v in sig.items() if k != "failureSignature"},
          "representativeStatus": status,
      },
  )
  g["count"] += 1
  g["names"].append(k8s.name(it))
  node_name = spec.get("nodeName")
  if node_name and node_name not in g["nodeNames"]:
    g["nodeNames"].append(str(node_name))


def _group_event(groups: dict[str, dict[str, Any]], it: dict[str, Any]) -> None:
  """Adds a compacted Event to its matching EventGroup bucket and updates timestamps."""
  sig = {
      "type": it.get("type"),
      "reason": it.get("reason"),
      "message": it.get("message"),
  }
  ts = str(it.get("lastTimestamp") or "")
  g = groups.setdefault(
      _signature(sig),
      {
          "kind": "EventGroup",
          "count": 0,
          "involvedObjects": [],
          "firstTimestamp": ts,
          "lastTimestamp": ts,
          **sig,
      },
  )
  g["count"] += 1
  inv = str(it.get("involvedObject", ""))
  if inv not in g["involvedObjects"]:
    g["involvedObjects"].append(inv)
  if ts:
    g["firstTimestamp"] = min(g["firstTimestamp"] or ts, ts)
    g["lastTimestamp"] = max(g["lastTimestamp"], ts)


_GROUPERS = {
    "Node": ("nodes", _group_node),
    "Pod": ("pods", _group_pod),
    "Event": ("events", _group_event),
}


def group_bulk_objects(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
  """Collapses diagnostically identical Nodes, Pods, and Events into groups.

  Every field shown on a group is copied verbatim from its members, so quotes
  taken from a group remain checkable against the ledger.

  Args:
    items: Sanitised and compacted Kubernetes object mappings.

  Returns:
    A `(remaining_items, groups)` tuple with complete member lists.
  """
  remaining: list[dict[str, Any]] = []
  by_group: dict[str, dict[str, dict[str, Any]]] = {
      "nodes": {},
      "pods": {},
      "events": {},
  }
  for it in items:
    if not isinstance(it, dict):
      continue
    grouper = _GROUPERS.get(k8s.kind(it))
    if grouper is None:
      remaining.append(it)
      continue
    group_key, fn = grouper
    fn(by_group[group_key], it)
  groups = {
      k: sorted(v.values(), key=lambda g: -g["count"])
      for k, v in by_group.items()
  }
  return remaining, {k: v for k, v in groups.items() if v}


_GROUP_LIST_KEYS = ("names", "nodeNames", "involvedObjects")


def sample_bulk_groups(
    groups: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
  """Returns a copy of `groups` with member lists shortened to a sample.

  The full report and the ledger keep the complete lists so that every object
  name remains quotable; only the digest is sampled.

  Args:
    groups: Bulk object groups keyed by `"nodes"`, `"pods"`, `"events"`.

  Returns:
    A shallow copy of `groups` with sampled member name lists.
  """
  out: dict[str, list[dict[str, Any]]] = {}
  for group_key, group_list in groups.items():
    sampled: list[dict[str, Any]] = []
    for g in group_list:
      g2 = dict(g)
      for lk in _GROUP_LIST_KEYS:
        if isinstance(g2.get(lk), list):
          g2[lk] = _sample_names(list(g2[lk]))
      sampled.append(g2)
    out[group_key] = sampled
  return out


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _event_is_relevant(it: dict[str, Any]) -> bool:
  involved = k8s.as_dict(it.get("involvedObject"))
  inv_kind = str(involved.get("kind", "")).lower()
  inv_name = str(involved.get("name", "")).lower()
  msg = str(it.get("message", "")).lower()
  return (
      str(it.get("type", "")) == "Warning"
      or inv_kind in _RELEVANT_EVENT_KINDS
      or "kueue" in inv_name
      or "kueue" in msg
      or "provision" in msg
      or "fairsh" in msg
      or "quota" in msg
      or "admit" in msg
  )


def _keep_snapshot_item(it: dict[str, Any]) -> bool:
  """Returns True when an object should be kept in the compacted snapshot."""
  kind = k8s.kind(it)
  ns = k8s.namespace(it)
  name = k8s.name(it)
  if kind == "Pod":
    has_fail = _pod_has_failure(it)
    if _is_managed_addon_namespace(ns) and not has_fail:
      return False
    phase = str(k8s.status(it).get("phase") or "")
    if (
        phase in ("Running", "Succeeded")
        and "kueue" not in name
        and not has_fail
    ):
      return False
  elif kind == "ConfigMap":
    if name != "kueue-manager-config":
      return False
  elif kind == "Event":
    if not _event_is_relevant(it) and _is_managed_addon_namespace(ns):
      return False
  return True


def filter_and_sort_snapshot_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Filters noisy kube-system Pods/Events and orders Kueue graph objects first."""
  filtered = [
      it for it in items if isinstance(it, dict) and _keep_snapshot_item(it)
  ]
  filtered.sort(
      key=lambda x: _PRIORITY_KIND_ORDER.get(str(x.get("kind", "")), 50)
  )
  return filtered


# ---------------------------------------------------------------------------
# Coverage ledger
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class LedgerInputs:
  """One ledger update: which action ran, what it returned and what was printed."""

  ledger_path: str | None
  action: str
  obj_or_list: Any
  raw_output_str: str
  detected_version: dict[str, Any] | None = None


def _ledger_items(obj_or_list: Any) -> list[dict[str, Any]]:
  if isinstance(obj_or_list, dict):
    if obj_or_list.get("kind") == "List":
      return k8s.dict_items(obj_or_list.get("items"))
    return [obj_or_list]
  return k8s.dict_items(obj_or_list)


def _record_item_refs(
    item: dict[str, Any], action: str, referenced: set[str], inspected: set[str]
) -> None:
  """Adds the item and the graph objects it points at to the referenced/inspected sets."""
  kind = k8s.kind(item).lower()
  meta = k8s.metadata(item)
  name = meta.get("name") or ""
  ns = meta.get("namespace") or ""
  ref_id = f"{kind}/{ns}/{name}" if ns else f"{kind}/{name}"
  if kind in _GRAPH_KINDS and name:
    referenced.add(ref_id)
    if action == "get":
      inspected.add(ref_id)
  if kind != "clusterqueue":
    return
  spec = k8s.spec(item)
  cohort = spec.get("cohort") or spec.get("cohortName")
  if isinstance(cohort, str) and cohort:
    referenced.add(f"cohort/{cohort}")
    if action == "get":
      inspected.add(f"cohort/{cohort}")
  for rg in k8s.resource_groups(item):
    for fl in k8s.dict_items(rg.get("flavors")):
      if fl.get("name"):
        referenced.add(f"resourceflavor/{fl.get('name')}")
  strategy = k8s.as_dict(spec.get("admissionChecksStrategy"))
  for ac in k8s.dict_items(strategy.get("admissionChecks")):
    if ac.get("name"):
      referenced.add(f"admissioncheck/{ac.get('name')}")
  for ac_name in k8s.as_list(spec.get("admissionChecks")):
    if isinstance(ac_name, str):
      referenced.add(f"admissioncheck/{ac_name}")


_LEDGER_CHUNK_CHARS = 120000
_LEDGER_MAX_CHUNKS = 50


def _ledger_strings(value: Any) -> list[str]:
  return [x for x in k8s.as_list(value) if isinstance(x, str)]


def _apply_ledger_update(ledger: dict[str, Any], inputs: LedgerInputs) -> None:
  """Merges one script run into the loaded ledger mapping in place."""
  if inputs.detected_version:
    ledger["detected_kueue_version"] = inputs.detected_version
  referenced = set(_ledger_strings(ledger.get("referenced")))
  inspected = set(_ledger_strings(ledger.get("inspected")))
  for item in _ledger_items(inputs.obj_or_list):
    _record_item_refs(item, inputs.action, referenced, inspected)
  outputs = _ledger_strings(ledger.get("tool_outputs"))
  if inputs.raw_output_str:
    # Chunked so that every object name in the full report stays quotable; the
    # validator joins all entries into one corpus.
    for i in range(0, len(inputs.raw_output_str), _LEDGER_CHUNK_CHARS):
      outputs.append(inputs.raw_output_str[i : i + _LEDGER_CHUNK_CHARS])
  ledger["referenced"] = sorted(referenced)
  ledger["inspected"] = sorted(inspected)
  ledger["tool_outputs"] = outputs[-_LEDGER_MAX_CHUNKS:]


def update_ledger(inputs: LedgerInputs) -> None:
  """Updates the coverage ledger with discovered and inspected Kueue graph objects and detected Kueue version.

  The read-modify-write runs under the lock every ledger writer takes
  (`report_output.mutate_ledger`), so a `trace_logs.py` run in parallel keeps
  its entries and this one keeps its own.

  Args:
    inputs: What the current run loaded and printed.
  """
  if not inputs.ledger_path:
    return
  report_output.mutate_ledger(
      inputs.ledger_path,
      lambda ledger: _apply_ledger_update(ledger, inputs),
      strict=False,
  )


# ---------------------------------------------------------------------------
# Offline bundle loading
# ---------------------------------------------------------------------------


class LoadError(Exception):
  """Raised when objects cannot be loaded; carries the user-facing message and next step."""

  def __init__(self, message: str, next_step: str) -> None:
    super().__init__(message)
    self.message = message
    self.next_step = next_step


_MAX_LOAD_WARNINGS = 30


@dataclasses.dataclass
class LoadNotes:
  """What a load could not read: full texts for `warnings`, short labels for the coverage line."""

  warnings: list[str] = dataclasses.field(default_factory=list)
  skipped: list[str] = dataclasses.field(default_factory=list)

  def warn(self, text: str) -> None:
    self.warnings.append(text)

  def skip(self, source: str, detail: str) -> None:
    """Records a source (file, document, kind) whose objects are missing from the result."""
    self.skipped.append(source)
    self.warnings.append(f"{source} not loaded: {detail}")

  def summary(self) -> str:
    """Suffix for error messages: how many sources were skipped and the first reason."""
    if not self.skipped:
      return ""
    first = next((w for w in self.warnings if " not loaded: " in w), "")
    return f" ({len(self.skipped)} source(s) skipped; first: {first[:300]})"

  def attach(self, raw_obj: dict[str, Any]) -> dict[str, Any]:
    """Stores the notes on a `kind: List` result as `_warnings` / `_skipped_sources`."""
    if self.warnings:
      shown = self.warnings[:_MAX_LOAD_WARNINGS]
      hidden = len(self.warnings) - len(shown)
      if hidden:
        shown.append(f"... {hidden} more load warnings")
      raw_obj.setdefault("_warnings", []).extend(shown)
    if self.skipped:
      raw_obj["_skipped_sources"] = list(self.skipped)
    return raw_obj


class _DuplicateKeyTrackingLoader(yaml.SafeLoader):
  """YAML SafeLoader that records overwritten duplicate keys on the document root.

  Mappings are built depth-first, so an overwritten value is complete when it
  is summarised. Only keys written in the mapping itself are compared: a key
  merged in through `<<` may be overridden without being a duplicate. The
  findings of a document are stored on its root mapping as
  `_yaml_duplicate_keys` (dotted key paths), never inside nested mappings.
  """

  def __init__(self, stream: Any) -> None:
    super().__init__(stream)
    self._key_path: list[str] = []
    self._duplicates: list[str] = []

  def construct_document(self, node: yaml.Node) -> Any:
    self._key_path, self._duplicates = [], []
    data = super().construct_document(node)
    if self._duplicates and isinstance(data, dict):
      data["_yaml_duplicate_keys"] = self._duplicates
    return data

  def construct_mapping(
      self, node: yaml.MappingNode, deep: bool = False
  ) -> dict[Any, Any]:
    own_keys = {id(key_node) for key_node, _ in node.value}
    self.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    seen: set[Any] = set()
    for key_node, value_node in node.value:
      key = self.construct_object(key_node, deep=True)
      if not isinstance(key, collections.abc.Hashable):
        raise yaml.constructor.ConstructorError(
            "while constructing a mapping",
            node.start_mark,
            "found unhashable key",
            key_node.start_mark,
        )
      self._key_path.append(str(key))
      try:
        val = self.construct_object(value_node, deep=True)
      finally:
        self._key_path.pop()
      if id(key_node) in own_keys:
        if key in seen:
          self._duplicates.append(
              f"key {'.'.join(self._key_path + [str(key)])!r} defined"
              f" multiple times{_previous_config_summary(mapping.get(key))}"
          )
        seen.add(key)
      mapping[key] = val
    return mapping


def _previous_config_summary(prev: Any) -> str:
  """Summarises an overwritten `controller_manager_config.yaml` block, or '' for other values."""
  if not (isinstance(prev, dict) and k8s.KUEUE_CONFIG_KEY in prev):
    return ""
  try:
    prev_cfg = yaml.safe_load(str(prev.get(k8s.KUEUE_CONFIG_KEY) or ""))
    if isinstance(prev_cfg, dict):
      return (
          " (earlier block had"
          f" manageJobsWithoutQueueName={prev_cfg.get('manageJobsWithoutQueueName')}, "
          f"waitForPodsReady={'present' if 'waitForPodsReady' in prev_cfg else 'absent'}, "
          f"integrations.frameworks={(prev_cfg.get('integrations') or {}).get('frameworks') if isinstance(prev_cfg.get('integrations'), dict) else None})"
      )
  except Exception:  # pylint: disable=broad-exception-caught
    # Malformed YAML in an overwritten block must not abort manifest loading.
    pass
  return ""


def _manifest_paths(data_path: str) -> list[str]:
  """Returns sorted manifest paths and symlinked subdirs; `_read_manifest` skips and records non-regular entries."""
  paths: list[str] = []
  if os.path.isfile(data_path):
    # Operator named this path explicitly: follow a symlink to a regular file.
    paths.append(os.path.realpath(data_path))
  elif os.path.isdir(data_path):
    for root, dirs, files in os.walk(data_path):
      kept_dirs: list[str] = []
      for dname in sorted(dirs):
        if dname == report_output.REPORT_DIR_NAME:
          continue
        full_dir = os.path.join(root, dname)
        if os.path.islink(full_dir):
          paths.append(full_dir)
        else:
          kept_dirs.append(dname)
      dirs[:] = kept_dirs
      for fname in sorted(files):
        if fname.endswith((".yaml", ".yml", ".json")):
          paths.append(os.path.join(root, fname))
  return paths


def _load_error_text(exc: Exception, line_offset: int = 0) -> str:
  """One-line description of a parse error with file-absolute line numbers."""
  mark = getattr(exc, "problem_mark", None)
  if mark is None:
    text = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {text[:300]}"
  parts = [getattr(exc, "context", None), getattr(exc, "problem", None)]
  text = " ".join(str(p) for p in parts if p) or type(exc).__name__
  line = line_offset + mark.line + 1
  return f"{text} (line {line}, column {mark.column + 1})"


def _split_yaml_documents(text: str) -> list[tuple[int, str]]:
  """Splits YAML text at `---` markers into `(first line index, document text)` pairs."""
  lines = text.split("\n")
  chunks: list[tuple[int, str]] = []
  start = 0
  for idx, line in enumerate(lines):
    if idx and (line.rstrip() == "---" or line.startswith(("--- ", "---\t"))):
      chunks.append((start, "\n".join(lines[start:idx])))
      start = idx
  chunks.append((start, "\n".join(lines[start:])))
  return [(first, chunk) for first, chunk in chunks if chunk.strip()]


def _yaml_documents(text: str, source: str, notes: LoadNotes) -> list[Any]:
  """Parses every YAML document of a file; a document that fails is recorded and skipped.

  The file is parsed in one pass first. Only when that fails is it split at
  the `---` markers and parsed document by document, so the documents before
  and after a broken one are still loaded.

  Args:
    text: The file content.
    source: Label of the file for `notes`.
    notes: Collector for skipped documents.

  Returns:
    The parsed documents, in file order.
  """
  try:
    return list(yaml.load_all(text, Loader=_DuplicateKeyTrackingLoader))
  except Exception:  # pylint: disable=broad-exception-caught
    # Any loader failure (syntax, unacceptable character, nesting depth) is
    # attributed to its document in the second pass below.
    pass
  docs: list[Any] = []
  for number, (first, chunk) in enumerate(_split_yaml_documents(text), 1):
    try:
      docs.extend(yaml.load_all(chunk, Loader=_DuplicateKeyTrackingLoader))
    except Exception as exc:  # pylint: disable=broad-exception-caught
      notes.skip(
          f"{source} (document {number}, from line {first + 1})",
          _load_error_text(exc, first),
      )
  return docs


def _is_json_lines(text: str) -> bool:
  """True for JSON Lines content (log exports), which is not a manifest file."""
  head, _, rest = text.lstrip().partition("\n")
  if not rest.strip():
    return False
  try:
    json.loads(head)
  except (ValueError, RecursionError):
    return False
  return True


def _json_documents(text: str, source: str, notes: LoadNotes) -> list[Any]:
  """Parses a `.json` file; invalid JSON is recorded, JSON Lines logs are left to `trace_logs.py`."""
  try:
    return [json.loads(text)]
  except (ValueError, RecursionError) as exc:
    if not _is_json_lines(text):
      notes.skip(source, _load_error_text(exc))
    return []


def _stamped_list_item(
    member: dict[str, Any], item_kind: str, api_version: Any
) -> dict[str, Any]:
  """A typed-list item with the `kind` / `apiVersion` the API server leaves out."""
  stamp: dict[str, Any] = {}
  if item_kind and api_version and not member.get("apiVersion"):
    stamp["apiVersion"] = api_version
  if item_kind and not member.get("kind"):
    stamp["kind"] = item_kind
  if not stamp:
    return member
  return {**stamp, **{k: v for k, v in member.items() if k not in stamp}}


def _document_objects(doc: Any, depth: int = 0) -> list[dict[str, Any]]:
  """Kubernetes objects of one parsed document, with `List` and `<Kind>List` documents expanded.

  Items of a typed list (`PodList`, `SecretList`, ...) get the list kind
  without its `List` suffix and the list `apiVersion` when they carry none.
  A list whose `items` is null or not a list yields nothing.

  Args:
    doc: One parsed YAML/JSON document.
    depth: Nesting level of lists inside lists.

  Returns:
    The mappings that have a `kind`.
  """
  if not isinstance(doc, dict):
    return []
  kind = doc.get("kind")
  if not isinstance(kind, str) or not kind:
    return []
  if not (kind.endswith("List") and ("items" in doc or kind == "List")):
    return [doc]
  out: list[dict[str, Any]] = []
  if depth > 2:
    return out
  for member in k8s.dict_items(doc.get("items")):
    member = _stamped_list_item(member, kind[:-4], doc.get("apiVersion"))
    out.extend(_document_objects(member, depth + 1))
  return out


def _is_kubeconfig(obj: dict[str, Any]) -> bool:
  return obj.get("kind") == "Config" and any(
      key in obj for key in ("users", "clusters", "contexts")
  )


def _collect_docs(
    docs: Any,
    items: list[dict[str, Any]],
    source: str = "",
    notes: LoadNotes | None = None,
    budget: int | None = None,
) -> None:
  """Appends the objects of parsed documents to `items`: lists expanded, secrets masked, kubeconfigs dropped."""
  notes = notes if notes is not None else LoadNotes()
  meter = _TreeMeter(budget)
  for doc in docs:
    for obj in _document_objects(doc):
      if _is_kubeconfig(obj):
        notes.warn(
            f"{source}: kubeconfig document (kind: Config) holds credentials"
            " and was left out"
        )
        continue
      try:
        meter.charge(obj)
      except TreeBudgetError as exc:
        notes.skip(f"{source} ({k8s.kind(obj)} {_obj_name(obj)!r})", str(exc))
        if meter.exhausted:
          notes.warn(f"{source}: the documents after that object were not read")
          return
        continue
      _mask_in_place(obj)
      items.append(obj)


def _obj_name(obj: Any) -> str:
  """`metadata.name` as a string; '' when missing or null."""
  return str(k8s.metadata(obj).get("name") or "")


def _obj_namespace(obj: Any) -> str:
  return str(k8s.metadata(obj).get("namespace") or "")


# Node budget of one manifest file relative to its size: a parsed tree has
# fewer nodes than the file has characters unless YAML aliases multiply it.
# The full report writes aliases out, so this bounds its size as well.
_NODES_PER_CHAR = 4
_MIN_NODE_BUDGET = 100000


def _read_manifest(path: str, source: str, notes: LoadNotes) -> str | None:
  if not report_output.is_regular_file(path):
    notes.skip(source, "non-regular file or symlink")
    return None
  try:
    with open(path, "r", encoding="utf-8-sig") as f:
      return f.read()
  except (OSError, UnicodeError) as exc:
    notes.skip(source, _load_error_text(exc))
    return None


def load_static_items(
    data_path: str, notes: LoadNotes | None = None
) -> list[dict[str, Any]]:
  """Loads Kubernetes objects from a file or directory for offline_data.

  Unreadable files and unparsable documents are skipped and recorded in
  `notes`; everything else in the bundle is still loaded.

  Args:
    data_path: A manifest file or a directory that is walked recursively.
    notes: Optional collector for skipped sources and warnings.

  Returns:
    The loaded objects with secrets masked. Subtrees a file shares through
    YAML aliases stay shared.
  """
  notes = notes if notes is not None else LoadNotes()
  items: list[dict[str, Any]] = []
  prefix = data_path.rstrip(os.sep) + os.sep
  for p in _manifest_paths(data_path):
    source = p[len(prefix) :] if p.startswith(prefix) else os.path.basename(p)
    text = _read_manifest(p, source, notes)
    if text is None:
      continue
    parse = _json_documents if p.endswith(".json") else _yaml_documents
    budget = max(_MIN_NODE_BUDGET, _NODES_PER_CHAR * len(text))
    _collect_docs(parse(text, source, notes), items, source, notes, budget)
  return items


# ---------------------------------------------------------------------------
# Live cluster loading
# ---------------------------------------------------------------------------


def _served_resource_names() -> tuple[set[str] | None, str]:
  """Returns the resource names the API server serves as `{plural, plural.group}` or `(None, err)`."""
  try:
    res = subprocess.run(
        ["kubectl", "api-resources", "-o", "name"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
  except (OSError, subprocess.SubprocessError) as exc:
    return None, str(exc)
  names: set[str] = set()
  for line in res.stdout.splitlines():
    name = line.strip()
    if not name:
      continue
    names.add(name)
    names.add(name.split(".", 1)[0])
  if not names:
    return None, res.stderr.strip() or "kubectl api-resources returned nothing"
  # Partial discovery failures (one broken aggregated API) still list the rest.
  return names, res.stderr.strip() if res.returncode != 0 else ""


def _filter_served(kinds_csv: str, served: set[str]) -> tuple[str, list[str]]:
  """Splits a `kubectl get` kind list into (served csv, missing kinds)."""
  kept: list[str] = []
  missing: list[str] = []
  for kind in kinds_csv.split(","):
    kind = kind.strip()
    if not kind:
      continue
    if kind in served or kind.split(".", 1)[0] in served:
      kept.append(kind)
    else:
      missing.append(kind)
  return ",".join(kept), missing


# Upper bound for one kubectl call. Listing every Pod of a large cluster takes
# minutes; a call that exceeds this is reported like any other kubectl error
# (optional kinds are skipped, required ones end the run).
_KUBECTL_TIMEOUT_SECONDS = 300
_KUBECTL_NOT_RUN = "kubectl could not be run"


def _kubectl_json(
    cmd: list[str], timeout: float = _KUBECTL_TIMEOUT_SECONDS
) -> tuple[dict[str, Any] | None, str]:
  """Runs a `kubectl ... -o json` command.

  Args:
    cmd: Full kubectl command argv.
    timeout: Maximum seconds to wait for kubectl to exit.

  Returns:
    `(object, "")` on success, or `(None, error text)` on failure.
  """
  try:
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        timeout=timeout,
    )
  except subprocess.TimeoutExpired:
    return None, f"`{' '.join(cmd[:3])}` did not finish within {timeout:g}s"
  except (OSError, subprocess.SubprocessError) as exc:
    return None, f"{_KUBECTL_NOT_RUN}: {type(exc).__name__}: {exc}"
  if res.returncode != 0:
    return None, res.stderr.strip() or f"kubectl exit code {res.returncode}"
  if not res.stdout.strip():
    return {"kind": "List", "items": []}, ""
  try:
    parsed = json.loads(res.stdout)
  except ValueError as exc:
    return None, f"kubectl returned non-JSON output: {exc}"
  if not isinstance(parsed, dict):
    return None, "kubectl returned JSON that is not an object"
  return parsed, ""


def _kubectl_load_error(what: str, err: str, next_step: str) -> LoadError:
  """`LoadError` for a failed kubectl call; a missing binary gets its own next step."""
  if err.startswith(_KUBECTL_NOT_RUN):
    next_step = (
        "Verify that kubectl is installed and on PATH; for a saved bundle pass"
        " --mode offline_data --data-path <directory>."
    )
  return LoadError(f"{what}: {err}", next_step)


def _served_kind_lists() -> tuple[str, str, list[str], str]:
  """(cluster-scoped csv, namespaced csv, missing kinds, discovery error) after API discovery."""
  # Not every cluster serves every optional group (JobSet, ProvisioningRequest,
  # Topology on older Kueue). A single `kubectl get a,b,c` aborts on the first
  # unknown type, so query the API server once and keep only the served kinds.
  served, served_err = _served_resource_names()
  if served is None:
    return CLUSTER_SCOPED_KINDS, NAMESPACED_KINDS, [], served_err
  cluster_list, miss_c = _filter_served(CLUSTER_SCOPED_KINDS, served)
  ns_list, miss_n = _filter_served(NAMESPACED_KINDS, served)
  return cluster_list, ns_list, miss_c + miss_n, served_err


def _missing_kinds_warning(missing_kinds: list[str], served_err: str) -> str:
  if served_err:
    # Discovery was incomplete (e.g. one broken aggregated API); the
    # kinds may well exist, so do not assert that they are not served.
    return (
        "Resource types not listed by API discovery (skipped): "
        + ", ".join(missing_kinds)
        + f". Discovery was incomplete: {served_err[:300]}. Verify with"
        " `kubectl get <kind>` before concluding anything about these kinds."
    )
  return (
      "Resource types not served by this cluster (skipped): "
      + ", ".join(missing_kinds)
      + ". A workload of such a kind cannot be managed here until its"
      " CRDs/operator are installed."
  )


def _append_manager_config(
    raw_obj: dict[str, Any], kueue_namespace: str, notes: LoadNotes
) -> None:
  """Fetches `kueue-manager-config` via kubectl and appends it, or records why it is missing."""
  cm_obj, err = _kubectl_json([
      "kubectl",
      "get",
      "configmap",
      "kueue-manager-config",
      "-n",
      kueue_namespace,
      "-o",
      "json",
      "--ignore-not-found=true",
  ])
  if isinstance(cm_obj, dict) and cm_obj.get("kind") == "ConfigMap":
    raw_obj["items"].append(cm_obj)
    return
  # `--ignore-not-found` exits 0 with empty output when the ConfigMap does not
  # exist, which is what a wrong --kueue-namespace looks like.
  notes.skip(
      f"configmap kueue-manager-config (namespace {kueue_namespace!r})",
      (err or "no ConfigMap of that name exists in that namespace")
      + ". Pass --kueue-namespace if Kueue is installed elsewhere.",
  )


_CLUSTER_NEXT_STEP = (
    "Check `kubectl config current-context` and that Kueue CRDs are installed"
    " (`kubectl api-resources --api-group=kueue.x-k8s.io`)."
)


def _fetch_cluster_scoped_items(
    cluster_list: str, notes: LoadNotes
) -> list[dict[str, Any]]:
  """Fetches cluster-scoped Kueue CRDs and nodes in separate kubectl calls.

  The Kueue kinds are required. Nodes are optional: a role without node list
  permission still gets a snapshot, with the gap recorded in `notes`.

  Args:
    cluster_list: Comma-separated served cluster-scoped kinds.
    notes: Collector for kinds that could not be listed.

  Returns:
    The fetched objects.

  Raises:
    LoadError: When the Kueue cluster-scoped kinds cannot be listed.
  """
  cluster_kinds = [k for k in cluster_list.split(",") if k]
  kueue_cluster_kinds = [k for k in cluster_kinds if k != "nodes"]
  cluster_items: list[dict[str, Any]] = []
  if kueue_cluster_kinds:
    cluster_obj, err = _kubectl_json([
        "kubectl",
        "get",
        ",".join(kueue_cluster_kinds),
        "-o",
        "json",
        "--ignore-not-found=true",
    ])
    if cluster_obj is None:
      raise _kubectl_load_error(
          "kubectl error while listing cluster-scoped Kueue objects",
          err,
          _CLUSTER_NEXT_STEP,
      )
    cluster_items.extend(k8s.dict_items(cluster_obj.get("items")))
  if "nodes" in cluster_kinds:
    nodes_obj, err = _kubectl_json(
        ["kubectl", "get", "nodes", "-o", "json", "--ignore-not-found=true"]
    )
    if nodes_obj is None:
      notes.skip("nodes", f"kubectl: {err[:300]}")
    else:
      cluster_items.extend(k8s.dict_items(nodes_obj.get("items")))
  return cluster_items


def _fetch_namespaced_items(
    ns_list: str, args: argparse.Namespace, notes: LoadNotes
) -> list[dict[str, Any]]:
  """Lists the namespaced kinds in one kubectl call, or kind by kind when that call fails.

  One kind the caller may not list (pods, events, ...) fails the combined
  call as a whole. On the retry only `workloads` is required; every other
  kind that cannot be listed is recorded in `notes` and left out.

  Args:
    ns_list: Comma-separated served namespaced kinds.
    args: Parsed CLI arguments (`namespace` selects one namespace).
    notes: Collector for kinds that could not be listed.

  Returns:
    The fetched objects.

  Raises:
    LoadError: When Workloads cannot be listed.
  """
  scope = ["-n", args.namespace] if args.namespace else ["-A"]
  base = ["kubectl", "get", "-o", "json", "--ignore-not-found=true", *scope]
  ns_obj, err = _kubectl_json(base[:2] + [ns_list] + base[2:])
  if ns_obj is not None:
    return k8s.dict_items(ns_obj.get("items"))
  kinds = [k for k in ns_list.split(",") if k]
  items: list[dict[str, Any]] = []
  for kind in kinds:
    if len(kinds) > 1:
      ns_obj, err = _kubectl_json(base[:2] + [kind] + base[2:])
    if ns_obj is not None:
      items.extend(k8s.dict_items(ns_obj.get("items")))
    elif kind.startswith("workloads"):
      raise _kubectl_load_error(
          f"kubectl error while listing {kind}",
          err,
          "Retry with `--namespace <workload namespace>` to narrow the query,"
          " or inspect objects with plain kubectl.",
      )
    else:
      notes.skip(kind, f"kubectl: {err[:300]}")
  return items


def _live_snapshot(args: argparse.Namespace) -> dict[str, Any]:
  """Collects cluster-scoped, namespaced, and ConfigMap objects via kubectl."""
  cluster_list, ns_list, missing_kinds, served_err = _served_kind_lists()
  if not any(
      k.startswith(("clusterqueues", "workloads"))
      for k in (cluster_list + "," + ns_list).split(",")
  ):
    raise LoadError(
        "Kueue CRDs (clusterqueues/workloads.kueue.x-k8s.io) are not served by"
        " this cluster"
        + (f" ({served_err})" if served_err else ""),
        "Check `kubectl config current-context` and that Kueue is installed"
        " (`kubectl api-resources --api-group=kueue.x-k8s.io`).",
    )
  notes = LoadNotes()
  cluster_items = _fetch_cluster_scoped_items(cluster_list, notes)
  raw_obj = {
      "kind": "List",
      "items": cluster_items + _fetch_namespaced_items(ns_list, args, notes),
  }
  if missing_kinds:
    notes.warn(_missing_kinds_warning(missing_kinds, served_err))
  _append_manager_config(raw_obj, args.kueue_namespace, notes)
  return notes.attach(raw_obj)


def _live_list(args: argparse.Namespace, action: str) -> dict[str, Any]:
  """Lists resources or events from the live cluster via kubectl."""
  cmd = [
      "kubectl",
      "get",
      "events" if action == "events" else args.kind,
      "-o",
      "json",
  ]
  if args.namespace:
    cmd.extend(["-n", args.namespace])
  else:
    cmd.append("-A")
  raw_obj, err = _kubectl_json(cmd)
  if raw_obj is None:
    raise _kubectl_load_error(
        "kubectl error",
        err,
        "Verify the kind/namespace, RBAC and the current kube-context.",
    )
  return raw_obj


def _live_get(args: argparse.Namespace) -> dict[str, Any]:
  """Fetches a specific resource or kind list from the live cluster via kubectl."""
  cmd = ["kubectl", "get", args.kind]
  if args.name:
    cmd.append(args.name)
  cmd.extend(["-o", "json"])
  if args.namespace:
    cmd.extend(["-n", args.namespace])
  elif not args.name:
    cmd.append("-A")
  raw_obj, err = _kubectl_json(cmd)
  if raw_obj is None:
    raise _kubectl_load_error(
        "kubectl error",
        err,
        "Verify the kind/name/namespace and the current kube-context.",
    )
  return raw_obj


# kubectl short names of the kinds a Kueue investigation looks up, mapped to
# the lower-case singular kind. Plurals and `<resource>.<group>` forms are
# resolved by `_kind_candidates`.
_KIND_SHORT_NAMES = {
    "ac": "admissioncheck",
    "co": "cohort",
    "cq": "clusterqueue",
    "flavor": "resourceflavor",
    "rf": "resourceflavor",
    "kwl": "workload",
    "kueueworkload": "workload",
    "wl": "workload",
    "lq": "localqueue",
    "queue": "localqueue",
    "mkc": "multikueuecluster",
    "mkconf": "multikueueconfig",
    "prc": "provisioningrequestconfig",
    "provreq": "provisioningrequest",
    "wpc": "workloadpriorityclass",
    "cm": "configmap",
    "ev": "event",
    "no": "node",
    "ns": "namespace",
    "pc": "priorityclass",
    "po": "pod",
    "quota": "resourcequota",
    "limits": "limitrange",
}


def _kind_candidates(requested: str) -> set[str]:
  """Lower-case singular kinds a `--kind` value can name.

  Accepts what kubectl accepts: the kind in any case, its plural, a short
  name, and the `<resource>.<group>` / `<resource>.<version>.<group>` forms.

  Args:
    requested: The `--kind` value.

  Returns:
    Candidate kinds, compared against the lower-cased `kind` of each object.
  """
  base = requested.strip().lower().split(".", 1)[0]
  forms = {base}
  if base.endswith("ies"):
    forms.add(base[:-3] + "y")
  if base.endswith("es"):
    forms.add(base[:-2])
  if base.endswith("s"):
    forms.add(base[:-1])
  return {_KIND_SHORT_NAMES.get(form, form) for form in forms}


def _single_offline_match(
    matched: list[dict[str, Any]], args: argparse.Namespace, context: str
) -> dict[str, Any]:
  """The object a named offline `get` selects; a missing or ambiguous name is an error."""
  where = f" in namespace {args.namespace!r}" if args.namespace else ""
  if not matched:
    raise LoadError(
        f"no object of kind {args.kind!r} named {args.name!r}{where} in"
        f" {args.data_path!r}{context}",
        f"Check the name with `--action list --kind {args.kind}`; the kind"
        " accepts singular, plural and kubectl short forms.",
    )
  namespaces = sorted({_obj_namespace(it) for it in matched})
  if len(namespaces) > 1:
    raise LoadError(
        f"{len(matched)} objects of kind {args.kind!r} are named"
        f" {args.name!r}, in namespaces {namespaces}",
        "Pass --namespace <namespace> to select one of them.",
    )
  return matched[0]


def _offline_match(
    all_items: list[dict[str, Any]],
    args: argparse.Namespace,
    action: str,
    notes: LoadNotes,
) -> dict[str, Any]:
  """Filters offline bundle items for `get`, `list`, or `events` queries."""
  wanted = {"event"} if action == "events" else _kind_candidates(args.kind)
  named = action == "get" and bool(args.name)
  matched = [
      it
      for it in all_items
      if k8s.kind(it).lower() in wanted
      and (not args.namespace or _obj_namespace(it) in ("", args.namespace))
      and (not named or _obj_name(it) == args.name)
  ]
  if not named:
    return notes.attach({"kind": "List", "items": matched})
  context = ""
  if not matched:
    present = sorted({k8s.kind(it) for it in all_items})
    context = f"; kinds in the bundle: {', '.join(present)}{notes.summary()}"
  return _single_offline_match(matched, args, context)


def _offline_items(args: argparse.Namespace, action: str) -> dict[str, Any]:
  """Loads static bundle items and filters them for `action`."""
  if not args.data_path or not os.path.exists(args.data_path):
    raise LoadError(
        f"data path not found: {args.data_path!r}",
        "Pass --data-path <directory with YAML/JSON manifests and optional"
        " logs/>, or use --mode live.",
    )
  notes = LoadNotes()
  all_items = load_static_items(args.data_path, notes)
  if not all_items:
    raise LoadError(
        f"no Kubernetes objects were loaded from {args.data_path!r}"
        f"{notes.summary()}",
        "Verify that --data-path holds YAML/JSON manifests (documents with a"
        " `kind`); for a bundle that has only logs pass --mode logs_archive.",
    )
  if action == "snapshot" or args.kind.lower() == "all":
    return notes.attach({"kind": "List", "items": all_items})
  return _offline_match(all_items, args, action, notes)


def load_items(
    mode: str, args: argparse.Namespace, action: str
) -> dict[str, Any]:
  """Loads raw Kubernetes object(s) for `action` from live kubectl or offline files.

  Args:
    mode: Either `"live"` or `"offline_data"`.
    args: Parsed CLI arguments specifying kind, name, namespace, and data path.
    action: Resolved action (`"snapshot"`, `"list"`, `"get"`, or `"events"`).

  Returns:
    A `kind: List` mapping (possibly with `_warnings` and `_skipped_sources`)
    or a single object dict.

  Raises:
    LoadError: When objects cannot be loaded from the selected source.
  """
  if mode == "live":
    if action == "snapshot" or args.kind.lower() == "all":
      return _live_snapshot(args)
    if action in ("events", "list"):
      return _live_list(args, action)
    return _live_get(args)
  return _offline_items(args, action)
