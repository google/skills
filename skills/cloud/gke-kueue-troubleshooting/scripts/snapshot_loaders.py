"""Object loading, sanitising and grouping for `snapshot.py`.

Responsibilities:
  * reading objects from a live cluster (`kubectl`) or from an offline bundle of
    YAML/JSON manifests (`load_items`, `load_static_items`);
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
# --ignore-namespaces / KUEUE_DIAGNOSE_IGNORE_NAMESPACES (see report_output).
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
  if key.startswith("beta.kubernetes.io/") or key in (
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
  annotations = dict(meta.get("annotations") or {})
  annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)
  if annotations:
    meta["annotations"] = annotations
  else:
    meta.pop("annotations", None)
  return meta


def _compact_node(out: dict[str, Any]) -> dict[str, Any]:
  """Strips non-scheduling labels, annotations, and healthy conditions on a Node."""
  meta = out["metadata"]
  status = dict(out.get("status") or {})
  all_labels = meta.get("labels") or {}
  labels = {k: v for k, v in all_labels.items() if _is_scheduling_label(k)}
  hidden = len(all_labels) - len(labels)
  if hidden > 0:
    labels["<other labels omitted>"] = str(hidden)
  meta["labels"] = labels
  meta.pop("annotations", None)
  out["metadata"] = meta
  out["spec"] = {"taints": (out.get("spec") or {}).get("taints") or []}
  allocatable = status.get("allocatable") or {}
  node_conds = []
  for c in status.get("conditions") or []:
    if not isinstance(c, dict):
      continue
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
      for cs in statuses or []
      if isinstance(cs, dict)
  ]


def _compact_pod_spec(spec: dict[str, Any]) -> dict[str, Any]:
  """Retains scheduling fields and container image/resource specs from a Pod spec."""
  containers = [
      {
          "name": c.get("name"),
          "image": c.get("image"),
          "resources": c.get("resources"),
      }
      for c in spec.get("containers") or []
      if isinstance(c, dict)
  ]
  init_containers = [
      {
          "name": c.get("name"),
          "image": c.get("image"),
          "imagePullPolicy": c.get("imagePullPolicy"),
          "resources": c.get("resources"),
      }
      for c in spec.get("initContainers") or []
      if isinstance(c, dict)
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
  out["spec"] = _compact_pod_spec(dict(out.get("spec") or {}))
  status = dict(out.get("status") or {})
  pod_status: dict[str, Any] = {
      "phase": status.get("phase"),
      "conditions": status.get("conditions"),
      "containerStatuses": _compact_container_statuses(
          status.get("containerStatuses")
      ),
  }
  if status.get("initContainerStatuses"):
    pod_status["initContainerStatuses"] = _compact_container_statuses(
        status.get("initContainerStatuses")
    )
  out["status"] = pod_status
  return out


def _compact_event(out: dict[str, Any]) -> dict[str, Any]:
  meta = out["metadata"]
  involved = out.get("involvedObject") or {}
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


def sanitize_and_compact_object(obj: dict[str, Any]) -> dict[str, Any]:
  """Strips Kubernetes boilerplate while preserving diagnostic signal and field attribution."""
  if not isinstance(obj, dict):
    return obj
  out = dict(obj)
  out.pop("_yaml_duplicate_keys", None)
  kind = str(out.get("kind", ""))
  if kind == "Secret":
    if "data" in out:
      out["data"] = {k: "<REDACTED>" for k in out["data"]}
    if "stringData" in out:
      out["stringData"] = {k: "<REDACTED>" for k in out["stringData"]}
  out["metadata"] = _compact_metadata(dict(out.get("metadata") or {}), kind)
  compactor = _KIND_COMPACTORS.get(kind)
  return compactor(out) if compactor else out


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
  involved = it.get("involvedObject") or {}
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
    phase = str(((it.get("status") or {}).get("phase")) or "")
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


def _read_ledger(ledger_path: str) -> dict[str, Any]:
  return report_output.load_ledger(ledger_path, strict=False)


def _ledger_items(obj_or_list: Any) -> list[dict[str, Any]]:
  if isinstance(obj_or_list, dict):
    if obj_or_list.get("kind") == "List":
      return obj_or_list.get("items", [])
    return [obj_or_list]
  if isinstance(obj_or_list, list):
    return [x for x in obj_or_list if isinstance(x, dict)]
  return []


def _record_item_refs(
    item: dict[str, Any], action: str, referenced: set[str], inspected: set[str]
) -> None:
  """Adds the item and the graph objects it points at to the referenced/inspected sets."""
  kind = str(item.get("kind", "")).lower()
  meta = item.get("metadata") or {}
  name = meta.get("name", "")
  ns = meta.get("namespace", "")
  ref_id = f"{kind}/{ns}/{name}" if ns else f"{kind}/{name}"
  if kind in _GRAPH_KINDS and name:
    referenced.add(ref_id)
    if action == "get":
      inspected.add(ref_id)
  spec = item.get("spec") or {}
  if kind != "clusterqueue":
    return
  cohort = spec.get("cohort") or spec.get("cohortName")
  if cohort:
    referenced.add(f"cohort/{cohort}")
    if action == "get":
      inspected.add(f"cohort/{cohort}")
  for rg in spec.get("resourceGroups") or []:
    for fl in rg.get("flavors") or []:
      fl_name = fl.get("name")
      if fl_name:
        referenced.add(f"resourceflavor/{fl_name}")
  for ac in (spec.get("admissionChecksStrategy") or {}).get(
      "admissionChecks", []
  ):
    ac_name = ac.get("name")
    if ac_name:
      referenced.add(f"admissioncheck/{ac_name}")
  for ac_name in spec.get("admissionChecks") or []:
    if isinstance(ac_name, str):
      referenced.add(f"admissioncheck/{ac_name}")


def update_ledger(inputs: LedgerInputs) -> None:
  """Updates the coverage ledger with discovered and inspected Kueue graph objects and detected Kueue version."""
  if not inputs.ledger_path:
    return
  ledger = _read_ledger(inputs.ledger_path)
  if inputs.detected_version:
    ledger["detected_kueue_version"] = inputs.detected_version
  referenced = set(ledger.get("referenced", []))
  inspected = set(ledger.get("inspected", []))
  for item in _ledger_items(inputs.obj_or_list):
    _record_item_refs(item, inputs.action, referenced, inspected)
  outputs = ledger.get("tool_outputs", [])
  if inputs.raw_output_str:
    # Chunked so that every object name in the full report stays quotable; the
    # validator joins all entries into one corpus.
    for i in range(0, len(inputs.raw_output_str), 120000):
      outputs.append(inputs.raw_output_str[i : i + 120000])
  ledger["referenced"] = sorted(referenced)
  ledger["inspected"] = sorted(inspected)
  ledger["tool_outputs"] = outputs[-50:]
  os.makedirs(
      os.path.dirname(os.path.abspath(inputs.ledger_path)), exist_ok=True
  )
  tmp_path = f"{inputs.ledger_path}.tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=2)
  os.replace(tmp_path, inputs.ledger_path)


# ---------------------------------------------------------------------------
# Offline bundle loading
# ---------------------------------------------------------------------------


class _DuplicateKeyTrackingLoader(yaml.SafeLoader):
  """YAML SafeLoader that records overwritten duplicate keys on mappings."""

  def construct_mapping(
      self, node: yaml.MappingNode, deep: bool = False
  ) -> dict[Any, Any]:
    self.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    duplicates: list[str] = []
    for key_node, value_node in node.value:
      key = self.construct_object(key_node, deep=deep)
      val = self.construct_object(value_node, deep=deep)
      if key in mapping:
        duplicates.append(
            f"key {key!r} defined multiple"
            f" times{_previous_config_summary(mapping[key])}"
        )
      mapping[key] = val
    if duplicates:
      mapping["_yaml_duplicate_keys"] = duplicates
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
  paths: list[str] = []
  if os.path.isfile(data_path):
    paths.append(data_path)
  elif os.path.isdir(data_path):
    for root, dirs, files in os.walk(data_path):
      dirs.sort()
      for fname in sorted(files):
        if fname.endswith((".yaml", ".yml", ".json")):
          paths.append(os.path.join(root, fname))
  return paths


def _collect_docs(docs: Any, items: list[dict[str, Any]]) -> None:
  for doc in docs:
    if isinstance(doc, dict) and doc.get("kind") == "List":
      items.extend(doc.get("items", []))
    elif isinstance(doc, dict) and doc.get("kind"):
      items.append(doc)


def load_static_items(data_path: str) -> list[dict[str, Any]]:
  """Loads Kubernetes objects from a file or directory for offline_data."""
  items: list[dict[str, Any]] = []
  for p in _manifest_paths(data_path):
    try:
      with open(p, "r", encoding="utf-8") as f:
        if p.endswith(".json"):
          _collect_docs([json.load(f)], items)
        else:
          _collect_docs(
              yaml.load_all(f, Loader=_DuplicateKeyTrackingLoader), items
          )
    except Exception:  # pylint: disable=broad-exception-caught
      # Corrupt or unreadable files in a support bundle are skipped.
      continue
  return items


# ---------------------------------------------------------------------------
# Live cluster loading
# ---------------------------------------------------------------------------


class LoadError(Exception):
  """Raised when objects cannot be loaded; carries the user-facing message and next step."""

  def __init__(self, message: str, next_step: str) -> None:
    super().__init__(message)
    self.message = message
    self.next_step = next_step


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


def _kubectl_json(cmd: list[str]) -> tuple[dict[str, Any] | None, str]:
  res = subprocess.run(cmd, capture_output=True, text=True, check=False)
  if res.returncode != 0:
    return None, res.stderr.strip()
  if not res.stdout.strip():
    return {"kind": "List", "items": []}, ""
  try:
    return json.loads(res.stdout), ""
  except json.JSONDecodeError as exc:
    return None, f"kubectl returned non-JSON output: {exc}"


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
    raw_obj: dict[str, Any], kueue_namespace: str
) -> None:
  """Fetches `kueue-manager-config` via kubectl and appends it or a warning."""
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
  elif err:
    raw_obj.setdefault("_warnings", []).append(
        f"kueue-manager-config not read from namespace {kueue_namespace!r}:"
        f" {err}. Pass --kueue-namespace if Kueue is installed elsewhere."
    )


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
  cluster_obj, err = _kubectl_json(
      ["kubectl", "get", cluster_list, "-o", "json", "--ignore-not-found=true"]
  )
  if cluster_obj is None:
    raise LoadError(
        f"kubectl error while listing cluster-scoped Kueue objects: {err}",
        "Check `kubectl config current-context` and that Kueue CRDs are"
        " installed (`kubectl api-resources --api-group=kueue.x-k8s.io`).",
    )
  ns_cmd = ["kubectl", "get", ns_list, "-o", "json", "--ignore-not-found=true"]
  ns_cmd.extend(["-n", args.namespace] if args.namespace else ["-A"])
  ns_obj, err = _kubectl_json(ns_cmd)
  if ns_obj is None:
    raise LoadError(
        f"kubectl error while listing namespaced objects: {err}",
        "Retry with `--namespace <workload namespace>` to narrow the query, or"
        " inspect objects with plain kubectl.",
    )
  raw_obj = {
      "kind": "List",
      "items": (
          list(cluster_obj.get("items", [])) + list(ns_obj.get("items", []))
      ),
  }
  if missing_kinds:
    raw_obj.setdefault("_warnings", []).append(
        _missing_kinds_warning(missing_kinds, served_err)
    )
  _append_manager_config(raw_obj, args.kueue_namespace)
  return raw_obj


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
    raise LoadError(
        f"kubectl error: {err}",
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
    raise LoadError(
        f"kubectl error: {err}",
        "Verify the kind/name/namespace and the current kube-context.",
    )
  return raw_obj


def _offline_match(
    all_items: list[dict[str, Any]], args: argparse.Namespace, action: str
) -> dict[str, Any]:
  """Filters offline bundle items for `get`, `list`, or `events` queries."""
  target_kind = "event" if action == "events" else args.kind.lower().rstrip("s")
  matched = []
  for it in all_items:
    k = str(it.get("kind", "")).lower().rstrip("s")
    if k != target_kind:
      continue
    meta = it.get("metadata") or {}
    if (
        args.namespace
        and meta.get("namespace")
        and meta.get("namespace") != args.namespace
    ):
      continue
    if action == "get" and args.name and meta.get("name") != args.name:
      continue
    matched.append(it)
  return (
      {"kind": "List", "items": matched}
      if (action != "get" or not args.name)
      else (matched[0] if matched else {})
  )


def _offline_items(args: argparse.Namespace, action: str) -> dict[str, Any]:
  if not args.data_path or not os.path.exists(args.data_path):
    raise LoadError(
        f"data path not found: {args.data_path!r}",
        "Pass --data-path <directory with YAML/JSON manifests and optional"
        " logs/>, or use --mode live.",
    )
  all_items = load_static_items(args.data_path)
  if action == "snapshot" or args.kind.lower() == "all":
    return {"kind": "List", "items": all_items}
  return _offline_match(all_items, args, action)


def load_items(
    mode: str, args: argparse.Namespace, action: str
) -> dict[str, Any]:
  """Loads raw Kubernetes object(s) for `action` from live kubectl or offline files.

  Args:
    mode: Either `"live"` or `"offline_data"`.
    args: Parsed CLI arguments specifying kind, name, namespace, and data path.
    action: Resolved action (`"snapshot"`, `"list"`, `"get"`, or `"events"`).

  Returns:
    A `kind: List` mapping (possibly with `_warnings`) or a single object dict.

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
