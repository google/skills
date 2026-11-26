"""Typed, tolerant accessors for Kubernetes objects represented as plain dicts.

Snapshot objects come from `kubectl -o json` or hand-written bundle manifests
and may be partial or malformed. Every accessor returns an empty container
when the field is missing or has the wrong shape, so callers can chain them
without `isinstance` / `(x or {})` guards; `as_text` and `as_int` do the same
for scalar fields. Stdlib only; no project imports.
"""

from __future__ import annotations

from typing import Any

# Key of the KueueConfiguration document inside kueue-manager-config ConfigMap.
KUEUE_CONFIG_KEY = "controller_manager_config.yaml"

# Labels that identify a node group / pool, used only to de-duplicate taint
# facts per pool. Upstream labels first, then common provider labels.
NODE_POOL_LABELS = (
    "node.kubernetes.io/instance-type",
    "cloud.google.com/gke-nodepool",
    "karpenter.sh/nodepool",
    "agentpool",
)


def as_dict(value: Any) -> dict[str, Any]:
  """Returns `value` when it is a dict, otherwise an empty dict."""
  return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
  """Returns `value` when it is a list, otherwise an empty list."""
  return value if isinstance(value, list) else []


def dict_items(value: Any) -> list[dict[str, Any]]:
  """Returns the dict elements of a list-like value (anything else → [])."""
  if not isinstance(value, (list, tuple)):
    return []
  return [x for x in value if isinstance(x, dict)]


def as_text(value: Any) -> str:
  """Returns `str(value)`, or '' when the value is missing (None); `0` stays '0'."""
  return "" if value is None else str(value)


def as_int(value: Any, default: int = 0) -> int:
  """Integer value of a count-like field.

  Returns `default` only when the field is missing (None) or is not a number
  (`"two"`, a list, a boolean), so an explicit `0` stays `0`.

  Args:
    value: Raw field value as loaded from JSON or YAML.
    default: Value returned for a missing or non-numeric field.

  Returns:
    The field as an int, or `default`.
  """
  if isinstance(value, bool) or not isinstance(value, (int, float, str)):
    return default
  try:
    return int(value)
  except (ValueError, OverflowError):
    return default


def kind(obj: Any) -> str:
  return as_text(as_dict(obj).get("kind"))


def metadata(obj: Any) -> dict[str, Any]:
  return as_dict(as_dict(obj).get("metadata"))


def name(obj: Any) -> str:
  return as_text(metadata(obj).get("name"))


def namespace(obj: Any) -> str:
  return as_text(metadata(obj).get("namespace"))


def ref(obj: Any) -> str:
  """Returns `ns/name` for namespaced objects, `name` for cluster-scoped ones."""
  ns = namespace(obj)
  return f"{ns}/{name(obj)}" if ns else name(obj)


def kind_ref(obj: Any) -> str:
  """Returns `Kind/ns/name` (or `Kind/name` when the object has no namespace)."""
  return f"{kind(obj)}/{ref(obj)}"


def labels(obj: Any) -> dict[str, Any]:
  return as_dict(metadata(obj).get("labels"))


def annotations(obj: Any) -> dict[str, Any]:  # pylint: disable=function-redefined
  return as_dict(metadata(obj).get("annotations"))


def owner_refs(obj: Any) -> list[dict[str, Any]]:
  return dict_items(metadata(obj).get("ownerReferences"))


def owner_names(obj: Any) -> set[str]:
  """Names of the object's owners (entries without a name are skipped)."""
  return {str(o.get("name", "")) for o in owner_refs(obj) if o.get("name")}


def spec(obj: Any) -> dict[str, Any]:
  return as_dict(as_dict(obj).get("spec"))


def status(obj: Any) -> dict[str, Any]:
  return as_dict(as_dict(obj).get("status"))


def conditions(obj: Any) -> list[dict[str, Any]]:
  """Dict entries of `status.conditions` (non-dict entries are dropped)."""
  return dict_items(status(obj).get("conditions"))


def event_timestamp(ev: Any) -> str:
  """Best timestamp of an Event: lastTimestamp, eventTime, firstTimestamp, then creationTimestamp."""
  ev = as_dict(ev)
  for key in ("lastTimestamp", "eventTime", "firstTimestamp"):
    if ev.get(key):
      return str(ev[key])
  return str(metadata(ev).get("creationTimestamp") or "")


def condition(obj: Any, type_: str) -> dict[str, Any] | None:
  """First `status.conditions[]` entry whose `type` equals `type_`, or None."""
  for cond in conditions(obj):
    if cond.get("type") == type_:
      return cond
  return None


def condition_status(obj: Any, type_: str) -> str | None:
  """`status` of the first condition of the given type as a string, or None."""
  cond = condition(obj, type_)
  return None if cond is None else str(cond.get("status"))


def has_condition(obj: Any, type_: str, status_value: str = "True") -> bool:
  """True when any condition of `type_` carries `status_value` (duplicates included).

  The status is compared as text, so an unquoted YAML `status: True` (a
  boolean after loading) matches `"True"`, as in `condition_status`.

  Args:
    obj: Kubernetes object mapping.
    type_: Condition type to look for.
    status_value: Expected status text.

  Returns:
    Whether a matching condition exists.
  """
  return any(
      c.get("type") == type_ and as_text(c.get("status")) == status_value
      for c in conditions(obj)
  )


def resource_groups(cq: Any) -> list[dict[str, Any]]:
  """Dict entries of `spec.resourceGroups` of a ClusterQueue or Cohort."""
  return dict_items(spec(cq).get("resourceGroups"))


def flavor_quotas(cq: Any):
  """Yields `(resource_group, flavor, resource)` dict triples of a ClusterQueue."""
  for rg in resource_groups(cq):
    for fl in dict_items(rg.get("flavors")):
      for res in dict_items(fl.get("resources")):
        yield rg, fl, res


def container_statuses(pod: Any) -> list[tuple[str, dict[str, Any]]]:
  """`(field, containerStatus)` pairs for init and regular containers, in that order."""
  st = status(pod)
  out: list[tuple[str, dict[str, Any]]] = []
  for field in ("initContainerStatuses", "containerStatuses"):
    for cs in dict_items(st.get(field)):
      out.append((field, cs))
  return out


def compact_managed_fields(mf_list: Any) -> list[str]:
  """Compacts verbose managedFields into a 1-line attribution summary per manager."""
  summary: list[str] = []
  for entry in dict_items(mf_list):
    manager = entry.get("manager", "unknown")
    operation = entry.get("operation", "Update")
    subresource = entry.get("subresource", "")
    ts = entry.get("time", "")
    sub = f"/{subresource}" if subresource else ""
    summary.append(f"{manager} ({operation}{sub} @ {ts})")
  return summary
