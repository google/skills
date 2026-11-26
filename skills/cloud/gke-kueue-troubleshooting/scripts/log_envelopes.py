#!/usr/bin/env python3
"""Vendor-neutral log record normalisation for `trace_logs.py`.

Log exports arrive in many shapes depending on where they were collected:

  * raw Kueue controller output (zap JSON, one object per line) — `kubectl
  logs`;
  * Kubernetes audit events (`audit.k8s.io/v1` `Event` objects, JSONL);
  * Kubernetes Events (`v1` or `events.k8s.io/v1`, from `kubectl get events -o
  json`
    or an events exporter);
  * collector envelopes that wrap one of the above in an outer object:
      - Google Cloud Logging export / `gcloud logging read --format=json`
        (`jsonPayload` / `protoPayload` / `textPayload`, `severity`,
        `timestamp`);
      - fluent-bit / Fluentd / Filebeat (`log` or `message`, `kubernetes`,
      `time`,
        `@timestamp`);
      - Grafana Loki `logcli --output=jsonl` (`line`, `labels`, `timestamp`);
      - tabular log export rows (`LogMessage`, capitalised `audit.k8s.io`
      fields);
  * klog text lines (`I0924 12:09:02.123456 1 main.go:748] ...`).

`iter_records()` accepts a file's text in any of these shapes (JSON array, JSONL
or
plain lines) and yields one normalised line per record. Normalised records are
JSON
objects with at least `ts`, `level` and `msg`; audit records additionally carry
the
neutral tuple `verb`, `resource`, `subresource`, `namespace`, `name` under
`logger: "audit"`, regardless of whether they came from a Kubernetes audit
webhook
or from a cloud provider's audit-log format. Unrecognised lines are passed
through
unchanged so text-based matching still works.

Workload secrets can enter a log record via audit request bodies, validation
error dumps (JSON or Go `EnvVar` structs), or accidental Kubernetes `Secret`
manifests mixed into a bundle: every literal container `env[].value` is
replaced with `<REDACTED>` here (`redact_env_values`, `redact_env_text`), and
non-log Kubernetes manifests (`Secret`, `List`, etc.) or truncated JSON
fragments are dropped before a record reaches any fact, report file or ledger.
Kubernetes Event objects are stamped `source_kind: "k8s-event"` so that
downstream counting can tell them from controller log lines that merely
describe an Event.

No third-party dependencies; this module never contacts any service.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any, Callable, Iterator

_KLOG_RE = re.compile(
    r"^([IWEF])(\d{4}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\d+\s+\S+:\d+\]\s*(.*)$"
)
_KLOG_LEVELS = {"I": "info", "W": "warning", "E": "error", "F": "fatal"}

# Google Cloud audit `methodName` is the reversed API group followed by
# `<version>.<resource>[.<subresource>].<verb>`, e.g.
# `io.k8s.core.v1.namespaces.delete`, `io.k8s.batch.v1.jobs.create`,
# `io.x-k8s.kueue.v1beta2.workloads.status.patch`. It is read right to left;
# `_API_VERSION_RE` also finds the `<group>/<version>/` head of `resourceName`.
_API_VERSION_RE = re.compile(r"^v\d+(?:(?:alpha|beta)\d+)?$")
_METHOD_SEGMENT_RE = re.compile(r"^[a-z0-9-]+$")
_GCP_METHOD_ROOTS = ("k8s", "x-k8s")
# Marker stamped on normalised Kubernetes Event objects. Kueue's own controller
# log also uses `logger: "events"`, so the logger name alone does not tell an
# exported Event from a controller log line.
K8S_EVENT_SOURCE_KIND = "k8s-event"
REDACTED = "<REDACTED>"
_CRI_PREFIX_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\S+\s+(?:stdout|stderr)\s+([FP])\s+(.*)$"
)
_CRI_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\S+)\s+(stdout|stderr)\s+([FP])\s+(.*)$"
)
_MAX_CRI_PARTIAL_BYTES = 262144
_PRETTY_JSON_MEMBER_RE = re.compile(r'^"[^"\n]+"\s*:')
_TRUNCATED_JSON_ARRAY_RE = re.compile(r'^\[\s*[{"\[]')
_JSON_CLOSING_RE = re.compile(r"^[\]}]+,?$")
# Rendered container `env` entries (JSON in either key order, JSON-patch
# `/env/<idx>/value`, or Go `%#v` `EnvVar{Name:..., Value:...}` dumps), both
# plain and single-level JSON-escaped.
_ENV_TEXT_RE = re.compile(
    r'("name"\s*:\s*"(?:[^"\\]|\\.)*"\s*,\s*"value"\s*:\s*)'
    r'"(?:[^"\\]|\\.)*(?:"|$)'
)
_ENV_TEXT_VAL_FIRST_RE = re.compile(
    r'("value"\s*:\s*)"(?:[^"\\]|\\.)*"'
    r'(\s*,\s*"name"\s*:\s*"(?:[^"\\]|\\.)*")'
)
_ENV_PATCH_TEXT_RE = re.compile(
    r'("path"\s*:\s*"[^"\n]{0,512}/env/[^/"\n]{1,64}/value"\s*,\s*"value"\s*:\s*)'
    r'"(?:[^"\\]|\\.)*(?:"|$)'
)
_ESCAPED_ENV_TEXT_RE = re.compile(
    r'(\\"name\\"\s*:\s*\\"(?:[^\\]|\\[^"])*\\"\s*,\s*'
    r'\\"value\\"\s*:\s*)\\"(?:[^\\]|\\[^"])*(?:\\"|$)'
)
_ESCAPED_ENV_VAL_FIRST_RE = re.compile(
    r'(\\"value\\"\s*:\s*)\\"(?:[^\\]|\\[^"])*\\"'
    r'(\s*,\s*\\"name\\"\s*:\s*\\"(?:[^\\]|\\[^"])*\\")'
)
_ESCAPED_ENV_PATCH_TEXT_RE = re.compile(
    r'(\\"path\\"\s*:\s*\\"[^\\"\n]{0,512}/env/[^/\\"\n]{1,64}/value\\"\s*,\s*'
    r'\\"value\\"\s*:\s*)\\"(?:[^\\]|\\[^"])*(?:\\"|$)'
)
_GO_ENV_VAR_RE = re.compile(
    r'(\{\s*Name\s*:\s*"(?:[^"\\]|\\.)*"\s*,\s*Value\s*:\s*)'
    r'"(?:[^"\\]|\\.)*(?:"|$)'
)
_ESCAPED_GO_ENV_VAR_RE = re.compile(
    r'(\{\s*Name\s*:\s*\\"(?:[^\\]|\\[^"])*\\"\s*,\s*'
    r'Value\s*:\s*)\\"(?:[^\\]|\\[^"])*(?:\\"|$)'
)
_NONLOG_AUDIT_KEYS = frozenset({
    "objectRef",
    "requestObject",
    "responseObject",
    "auditID",
    "protoPayload",
    "ObjectRef",
    "RequestObject",
    "ResponseObject",
    "AuditID",
    "ProtoPayload",
})
_NONLOG_SECRET_OR_LIST_KINDS = frozenset({"Secret", "SecretList", "List"})
_VERBS = {
    "create",
    "delete",
    "deletecollection",
    "get",
    "list",
    "patch",
    "update",
    "watch",
}


def _json_or_none(text: str) -> Any:
  text = text.strip()
  if not text or text[0] not in "{[":
    return None
  try:
    return json.loads(text)
  except (json.JSONDecodeError, RecursionError):
    return None


def _first(d: dict[str, Any], *keys: str) -> Any:
  for k in keys:
    v = d.get(k)
    if v not in (None, ""):
      return v
  return None


def _redacted_env_entry(entry: Any) -> Any:
  """One `env[]` entry with its literal `value` hidden; `name`/`valueFrom` stay."""
  if isinstance(entry, dict) and "value" in entry:
    return {**entry, "value": REDACTED}
  return entry


def _redacted_env_patch_op(op: dict[str, Any]) -> dict[str, Any]:
  """A JSON-patch operation with the `env` values it writes hidden."""
  path = op.get("path")
  if not isinstance(path, str) or "value" not in op:
    return op
  segs = path.split("/")
  if "env" not in segs:
    return op
  tail = segs[len(segs) - segs[::-1].index("env") :]
  value = op["value"]
  if not tail and isinstance(value, list):
    value = [_redacted_env_entry(e) for e in value]
  elif len(tail) == 1:
    value = _redacted_env_entry(value)
  elif len(tail) == 2 and tail[1] == "value":
    value = REDACTED
  return {**op, "value": value}


def redact_env_values(node: Any) -> Any:
  """Copy of a JSON value with container `env[].value` and Secret data set to `<REDACTED>`.

  Covers pod templates and non-container CRD `env` lists at any depth,
  JSON-patch operations whose `path` writes into an `env` list, and `Secret`
  `data`/`stringData` maps. `name`, `valueFrom`, `command` and `args` are kept.
  Iterative, so that a deeply nested request body costs no interpreter stack.

  Args:
    node: Decoded JSON value (a `spec`, a request body, or a patch list).

  Returns:
    The redacted copy; `node` itself is not modified.
  """
  holder: list[Any] = [node]
  stack: list[tuple[Any, Any]] = [(holder, 0)]
  while stack:
    parent, key = stack.pop()
    cur = parent[key]
    if isinstance(cur, dict):
      cur = parent[key] = _redacted_env_patch_op(dict(cur))
      if isinstance(cur.get("env"), list):
        cur["env"] = [_redacted_env_entry(e) for e in cur["env"]]
      if cur.get("kind") == "Secret":
        for secret_field in ("data", "stringData"):
          if isinstance(cur.get(secret_field), dict):
            cur[secret_field] = {k: REDACTED for k in cur[secret_field]}
      stack.extend((cur, k) for k in cur)
    elif isinstance(cur, list):
      cur = parent[key] = list(cur)
      stack.extend((cur, i) for i in range(len(cur)))
    elif isinstance(cur, str):
      parent[key] = redact_env_text(cur)
  return holder[0]


def redact_env_text(text: str) -> str:
  """`redact_env_values` for an audit summary or error message in rendered text."""
  if (
      '"value"' not in text
      and '\\"value\\"' not in text
      and "EnvVar{" not in text
  ):
    return text
  out = text
  if '"value"' in out:
    out = _ENV_TEXT_RE.sub(lambda m: f'{m.group(1)}"{REDACTED}"', out)
    out = _ENV_TEXT_VAL_FIRST_RE.sub(
        lambda m: f'{m.group(1)}"{REDACTED}"{m.group(2)}', out
    )
    if "/env/" in out:
      out = _ENV_PATCH_TEXT_RE.sub(lambda m: f'{m.group(1)}"{REDACTED}"', out)
  if '\\"value\\"' in out:
    out = _ESCAPED_ENV_TEXT_RE.sub(
        lambda m: f'{m.group(1)}\\"{REDACTED}\\"', out
    )
    out = _ESCAPED_ENV_VAL_FIRST_RE.sub(
        lambda m: f'{m.group(1)}\\"{REDACTED}\\"{m.group(2)}', out
    )
    if "/env/" in out:
      out = _ESCAPED_ENV_PATCH_TEXT_RE.sub(
          lambda m: f'{m.group(1)}\\"{REDACTED}\\"', out
      )
  if "EnvVar{" in out:
    out = _GO_ENV_VAR_RE.sub(lambda m: f'{m.group(1)}"{REDACTED}"', out)
    if '\\"' in out:
      out = _ESCAPED_GO_ENV_VAR_RE.sub(
          lambda m: f'{m.group(1)}\\"{REDACTED}\\"', out
      )
  return out


def _request_object_parts(req: Any) -> dict[str, Any]:
  """Picks the parts of a request/response object worth keeping from audit."""
  if isinstance(req, list):
    # A JSON-patch body (list of operations) is kept whole under `request`.
    return {"request": redact_env_values(req)} if req else {}
  if not isinstance(req, dict):
    return {}
  out: dict[str, Any] = {}
  meta = req.get("metadata") if isinstance(req.get("metadata"), dict) else {}
  raw_ann = meta.get("annotations")
  ann: dict[str, Any] = {}
  if isinstance(raw_ann, dict):
    ann = {
        k: v
        for k, v in raw_ann.items()
        if k != "kubectl.kubernetes.io/last-applied-configuration"
    }
  if req.get("spec") is not None:
    out["spec"] = redact_env_values(req["spec"])
  if ann:
    out["annotations"] = ann
  if isinstance(meta.get("labels"), dict) and meta["labels"]:
    out["labels"] = meta["labels"]
  status = req.get("status") if isinstance(req.get("status"), dict) else {}
  filtered_status = {
      k: status[k]
      for k in ("conditions", "admissionChecks", "requeueState")
      if k in status
  }
  if filtered_status:
    out["status"] = filtered_status
  return out


@dataclasses.dataclass(frozen=True)
class AuditRef:
  """Neutral `(verb, resource, subresource, namespace, name, group)` tuple."""

  verb: str = ""
  resource: str = ""
  subresource: str = ""
  namespace: str = ""
  name: str = ""
  group: str = ""

  @property
  def resource_path(self) -> str:
    return (
        f"{self.resource}/{self.subresource}"
        if self.subresource
        else self.resource
    )

  @property
  def target(self) -> str:
    if self.namespace and self.name:
      return f"{self.namespace}/{self.name}"
    return self.name or self.namespace or ""


def _audit_row(
    ref: AuditRef,
    *,
    ts: str,
    level: str,
    parts: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Formats a normalized audit log record dictionary from `ref` and `parts`."""
  if ref.resource.lower() == "secrets":
    parts = {}
  summary = [f"[Audit {ref.verb} {ref.resource_path}] {ref.target}"]
  for key, limit in (
      ("spec", 1200),
      ("request", 400),
      ("annotations", 450),
      ("labels", 350),
      ("status", 600),
  ):
    if key in parts:
      summary.append(f"{key}={json.dumps(parts[key], sort_keys=True)[:limit]}")
  row: dict[str, Any] = {
      "ts": ts,
      "level": level or "info",
      "logger": "audit",
      "msg": " ".join(summary),
      "verb": ref.verb,
      "resource": ref.resource,
      "subresource": ref.subresource,
      "group": ref.group,
      "namespace": ref.namespace,
      "name": ref.name,
      "resourceName": ref.target,
  }
  row.update(parts)
  if extra:
    row.update(extra)
  return row


def _dict_at(d: dict[str, Any], key: str) -> dict[str, Any]:
  """`d[key]` when it is a mapping, else `{}`."""
  value = d.get(key)
  return value if isinstance(value, dict) else {}


def _k8s_audit_extra(d: dict[str, Any], code: Any) -> dict[str, Any]:
  extra: dict[str, Any] = {"stage": str(d.get("stage") or "")}
  if code is not None:
    extra["responseCode"] = code
  user = _dict_at(d, "user")
  if user.get("username"):
    extra["user"] = str(user["username"])
  return extra


def _normalize_k8s_audit_event(d: dict[str, Any]) -> dict[str, Any] | None:
  """`audit.k8s.io/v1` Event (apiserver audit policy / webhook / kind)."""
  ref = _dict_at(d, "objectRef")
  verb = str(d.get("verb") or "").lower()
  if not verb:
    return None
  code = _dict_at(d, "responseStatus").get("code")
  level = "error" if isinstance(code, int) and code >= 400 else "info"
  return _audit_row(
      AuditRef(
          verb=verb,
          resource=str(ref.get("resource") or ""),
          subresource=str(ref.get("subresource") or ""),
          namespace=str(ref.get("namespace") or ""),
          name=str(ref.get("name") or ""),
          group=str(ref.get("apiGroup") or ""),
      ),
      ts=str(_first(d, "stageTimestamp", "requestReceivedTimestamp") or ""),
      level=level,
      parts=_request_object_parts(d.get("requestObject")),
      extra=_k8s_audit_extra(d, code),
  )


def _gcp_method_parts(method: str) -> tuple[str, str, str, str]:
  """`(group, resource, subresource, verb)` of a `methodName`, read right to left.

  The group is the one the method spells (`core` -> ``, `io.x-k8s.kueue` ->
  `kueue.x-k8s.io`); `gcp_audit_ref` prefers the group of `resourceName`.

  Args:
    method: Cloud audit `methodName`.

  Returns:
    Empty strings for every part the method does not name; a method of another
    shape yields at most its verb.
  """
  segs = method.split(".")
  verb = segs[-1] if segs[-1] in _VERBS else ""
  if segs[0] != "io" or len(segs) < 2 or segs[1] not in _GCP_METHOD_ROOTS:
    return "", "", "", verb
  for tail_len in (2, 3):  # `<resource>.<verb>`, `<resource>.<sub>.<verb>`
    ver_at = len(segs) - tail_len - 1
    tail = segs[ver_at + 1 :]
    if (
        ver_at < 3
        or not _API_VERSION_RE.match(segs[ver_at])
        or not all(_METHOD_SEGMENT_RE.match(s) for s in tail)
    ):
      continue
    group_segs = segs[2:ver_at]
    if segs[1] == "x-k8s":
      group = ".".join(reversed(group_segs)) + ".x-k8s.io"
    else:
      group = "" if group_segs == ["core"] else ".".join(group_segs)
    return group, tail[0], tail[1] if tail_len == 3 else "", tail[-1]
  return "", "", "", verb


def _gcp_resource_target(
    res_name: str, resource: str
) -> tuple[str | None, str, str]:
  """`(group, namespace, name)` from a Google Cloud audit `resourceName` path.

  The path is `<group>/<version>/[namespaces/<ns>/]<resource>/<name>[/<sub>]`.
  The name is taken by position, so a trailing subresource such as `/status`
  is never read as the object name.

  Args:
    res_name: Cloud audit `resourceName`.
    resource: Resource plural named by the method (`` when unknown).

  Returns:
    `group` is None when the path has no `<group>/<version>/` head.
  """
  segs = [s for s in res_name.split("/") if s]
  group: str | None = None
  if len(segs) > 1 and _API_VERSION_RE.match(segs[1]):
    group = "" if segs[0] == "core" else segs[0]
    segs = segs[2:]
  elif resource in segs:
    segs = segs[segs.index(resource) :]
  if not segs:
    return group, "", ""
  if segs[0] == "namespaces" and resource != "namespaces" and len(segs) > 2:
    return group, segs[1], segs[3] if len(segs) > 3 else ""
  if group is not None or segs[0] in ("namespaces", resource):
    return group, "", segs[1] if len(segs) > 1 else ""
  return group, "", segs[-1]


def gcp_audit_ref(method: str, res_name: str = "") -> AuditRef:
  """Neutral audit tuple from a Cloud audit `methodName` and `resourceName`."""
  group, resource, subresource, verb = _gcp_method_parts(method)
  path_group, namespace, name = _gcp_resource_target(res_name, resource)
  return AuditRef(
      verb=verb,
      resource=resource,
      subresource=subresource,
      namespace=namespace,
      name=name,
      group=group if path_group is None else path_group,
  )


def _gcp_audit_extra(
    pp: dict[str, Any], method: str, res_name: str
) -> dict[str, Any]:
  """Extracts method, resource, status code, and principal fields from `pp`."""
  extra: dict[str, Any] = {
      "methodName": method,
      "providerResourceName": res_name,
  }
  st = _dict_at(pp, "status")
  if st.get("code") not in (None, 0):
    extra["responseCode"] = st.get("code")
  auth = _dict_at(pp, "authenticationInfo")
  if auth.get("principalEmail"):
    extra["user"] = str(auth["principalEmail"])
  return extra


def _normalize_gcp_audit(
    pp: dict[str, Any], ts: str, severity: str
) -> dict[str, Any] | None:
  """Google Cloud audit log `protoPayload` (AuditLog) for a K8s API call."""
  method = str(pp.get("methodName") or "")
  res_name = str(pp.get("resourceName") or "")
  return _audit_row(
      gcp_audit_ref(method, res_name),
      ts=ts,
      level=severity.lower() if severity else "info",
      parts=_request_object_parts(pp.get("request")),
      extra=_gcp_audit_extra(pp, method, res_name),
  )


def extract_event_emitter(d: dict[str, Any]) -> str:
  """Component that emitted a Kubernetes Event (`''` when unknown)."""
  src = d.get("source")
  if isinstance(src, dict) and src.get("component"):
    return str(src["component"])
  if isinstance(src, str) and src and " source: " not in f" {src}":
    return src
  for key in ("reportingController", "reportingComponent"):
    if d.get(key):
      return str(d[key])
  if d.get("reportingInstance"):
    return str(d["reportingInstance"]).split("/", 1)[0]
  meta = d.get("metadata")
  if isinstance(meta, dict):
    managed = meta.get("managedFields")
    for mf in managed if isinstance(managed, list) else []:
      if (
          isinstance(mf, dict)
          and mf.get("manager")
          and not str(mf["manager"]).startswith("kubectl")
      ):
        return str(mf["manager"])
  return ""


def _normalize_k8s_event(d: dict[str, Any]) -> dict[str, Any]:
  """`v1` Event or `events.k8s.io/v1` Event."""
  obj = _first(d, "involvedObject", "regarding") or {}
  ev_type = str(d.get("type") or "")
  row: dict[str, Any] = {
      "ts": str(
          _first(d, "lastTimestamp", "eventTime", "firstTimestamp") or ""
      ),
      "level": "warning" if ev_type == "Warning" else "info",
      "logger": "events",
      "source_kind": K8S_EVENT_SOURCE_KIND,
      "type": ev_type,
      "reason": str(d.get("reason") or ""),
      "msg": str(_first(d, "message", "note") or ""),
      "object": obj if isinstance(obj, dict) else {},
  }
  if d.get("count") is not None:
    row["count"] = d.get("count")
  comp = extract_event_emitter(d)
  if comp:
    row["source"] = comp
  return row


def _looks_like_zap(d: dict[str, Any]) -> bool:
  kind = d.get("kind")
  if isinstance(kind, str) and kind in _NONLOG_SECRET_OR_LIST_KINDS:
    return False
  return ("msg" in d or "message" in d) and (
      "level" in d or "ts" in d or "logger" in d
  )


_MAX_ENVELOPE_DEPTH = 4


def _fill_envelope_defaults(
    inner: dict[str, Any], ts: str, severity: str
) -> dict[str, Any]:
  """Adds the envelope's timestamp / severity to an inner record that lacks them."""
  if not inner.get("ts"):
    inner["ts"] = ts
  if not inner.get("level"):
    inner["level"] = severity.lower() or "info"
  return inner


def _unwrap_text_payload(
    text: str, depth: int
) -> tuple[bool, dict[str, Any] | None]:
  """Unwraps a string payload; returns `(dropped, record_or_none)`."""
  inner_obj = _json_or_none(text)
  if inner_obj is None:
    return False, _normalize_text_line(text)
  if isinstance(inner_obj, list):
    return True, None
  if isinstance(inner_obj, dict):
    row = normalize_record(inner_obj, depth + 1)
    if row is not None:
      return False, row
    if _is_nonlog_k8s_or_audit_dict(inner_obj):
      return True, None
  return False, None


# --- Capitalised audit.k8s.io rows -------------------------------------------


def _is_capitalized_audit(obj: dict[str, Any]) -> bool:
  return "Verb" in obj and "ObjectRef" in obj and "verb" not in obj


def _unwrap_capitalized_audit(
    obj: dict[str, Any], depth: int
) -> dict[str, Any] | None:
  """Normalizes capitalized audit.k8s.io fields and JSON-encoded children."""
  del depth
  lowered: dict[str, Any] = {}
  for k, v in obj.items():
    if isinstance(v, str) and v[:1] in "{[":
      parsed = _json_or_none(v)
      v = parsed if parsed is not None else v
    lowered[k[:1].lower() + k[1:]] = v
  lowered.setdefault("stageTimestamp", lowered.get("timeGenerated", ""))
  return _normalize_k8s_audit_event(lowered)


# --- Kubernetes audit Event / Kubernetes Event -------------------------------


def _is_k8s_audit_event(obj: dict[str, Any]) -> bool:
  return (
      str(obj.get("kind") or "") == "Event"
      and str(obj.get("apiVersion") or "").partition("/")[0] == "audit.k8s.io"
  )


def _unwrap_k8s_audit_event(
    obj: dict[str, Any], depth: int
) -> dict[str, Any] | None:
  """Normalizes a standard `audit.k8s.io` Event object."""
  del depth
  return _normalize_k8s_audit_event(obj)


def _is_k8s_event(obj: dict[str, Any]) -> bool:
  """Returns True for a Kubernetes core/events Event object."""
  api = str(obj.get("apiVersion") or "")
  kind = str(obj.get("kind") or "")
  has_object = "involvedObject" in obj or "regarding" in obj
  if kind == "Event":
    return has_object or api in ("v1", "events.k8s.io/v1")
  return not kind and "reason" in obj and has_object


def _unwrap_k8s_event(obj: dict[str, Any], depth: int) -> dict[str, Any]:
  """Normalizes a Kubernetes core/events Event object."""
  del depth
  return _normalize_k8s_event(obj)


# --- Google Cloud Logging envelope -------------------------------------------


def _is_gcp_logging(obj: dict[str, Any]) -> bool:
  """Returns True for a Cloud Logging entry carrying a supported payload."""
  if not any(k in obj for k in ("jsonPayload", "protoPayload", "textPayload")):
    return False
  if not ("timestamp" in obj or "insertId" in obj or "logName" in obj):
    return False
  return (
      isinstance(obj.get("protoPayload"), dict)
      or isinstance(obj.get("jsonPayload"), dict)
      or obj.get("textPayload") is not None
  )


def _unwrap_gcp_logging(
    obj: dict[str, Any], depth: int
) -> dict[str, Any] | None:
  """Unwraps a Google Cloud Logging audit, JSON, or text payload envelope."""
  ts = str(obj.get("timestamp") or "")
  sev = str(obj.get("severity") or "")
  if isinstance(obj.get("protoPayload"), dict):
    return _normalize_gcp_audit(obj["protoPayload"], ts, sev)
  if isinstance(obj.get("jsonPayload"), dict):
    jp = obj["jsonPayload"]
    inner = normalize_record(jp, depth + 1)
    if inner is None:
      if _is_nonlog_k8s_or_audit_dict(jp):
        return None
      inner = dict(jp)
    _fill_envelope_defaults(inner, ts, sev)
    if "msg" not in inner and "message" in inner:
      inner["msg"] = inner["message"]
    if "object" not in inner and "involvedObject" in inner:
      inner["object"] = inner["involvedObject"]
    return inner
  text = str(obj["textPayload"])
  dropped, parsed = _unwrap_text_payload(text, depth)
  if dropped:
    return None
  inner = parsed or {"msg": text}
  if not inner.get("ts") or ts:
    inner["ts"] = ts or inner.get("ts", "")
  return _fill_envelope_defaults(inner, "", sev)


# --- Collector envelopes: fluent-bit / Fluentd / Filebeat / Loki -------------


def _collector_payload(obj: dict[str, Any]) -> str | None:
  """The wrapped line of a collector envelope, or None when `obj` is not one."""
  payload = _first(obj, "log", "line", "LogMessage")
  if (
      payload is None
      and isinstance(obj.get("message"), str)
      and not _looks_like_zap(obj)
  ):
    payload = obj.get("message")
  if not isinstance(payload, str):
    return None
  if any(
      k in obj
      for k in (
          "kubernetes",
          "labels",
          "time",
          "@timestamp",
          "timestamp",
          "stream",
          "TimeGenerated",
      )
  ):
    return payload
  return None


def _is_collector_envelope(obj: dict[str, Any]) -> bool:
  return _collector_payload(obj) is not None


def _unwrap_collector_envelope(
    obj: dict[str, Any], depth: int
) -> dict[str, Any] | None:
  """Unwraps a fluent-bit, Fluentd, Filebeat, or Loki log collector envelope."""
  payload = _collector_payload(obj) or ""
  ts = str(
      _first(obj, "time", "@timestamp", "timestamp", "TimeGenerated") or ""
  )
  dropped, parsed = _unwrap_text_payload(payload, depth)
  if dropped:
    return None
  inner = parsed or {"msg": payload.rstrip("\n")}
  inner.setdefault("ts", ts)
  inner.setdefault(
      "level", str(obj.get("level") or obj.get("severity") or "info").lower()
  )
  return inner


# --- Plain zap / structured record -------------------------------------------


def _unwrap_zap(obj: dict[str, Any], depth: int) -> dict[str, Any]:
  """Normalizes a zap or structured JSON log record."""
  del depth
  row = dict(obj)
  if "msg" not in row and "message" in row:
    row["msg"] = row["message"]
  if "ts" not in row:
    ts = _first(row, "time", "timestamp", "@timestamp")
    if ts is not None:
      row["ts"] = str(ts)
  if "level" not in row and row.get("severity"):
    row["level"] = str(row["severity"]).lower()
  if isinstance(row.get("msg"), str) and row["msg"].startswith("[Audit "):
    # An audit row normalised by an earlier run or another exporter.
    row["msg"] = redact_env_text(row["msg"])
    for key in ("spec", "request"):
      if isinstance(row.get(key), (dict, list)):
        row[key] = redact_env_values(row[key])
  return row


EnvelopeMatcher = Callable[[dict[str, Any]], bool]
EnvelopeUnwrapper = Callable[[dict[str, Any], int], "dict[str, Any] | None"]

# Tried in order; the first matching envelope decides the record (its result is
# final even when it is None, e.g. an audit row without a verb).
ENVELOPE_UNWRAPPERS: tuple[tuple[EnvelopeMatcher, EnvelopeUnwrapper], ...] = (
    (_is_capitalized_audit, _unwrap_capitalized_audit),
    (_is_k8s_audit_event, _unwrap_k8s_audit_event),
    (_is_k8s_event, _unwrap_k8s_event),
    (_is_gcp_logging, _unwrap_gcp_logging),
    (_is_collector_envelope, _unwrap_collector_envelope),
    (_looks_like_zap, _unwrap_zap),
)


def normalize_record(obj: Any, depth: int = 0) -> dict[str, Any] | None:
  """Turns one parsed record of any supported shape into a normalized dict.

  Args:
    obj: Decoded JSON value to inspect and unwrap.
    depth: Current envelope nesting depth (bounded by `_MAX_ENVELOPE_DEPTH`).

  Returns:
    A normalized log record dict, or None when `obj` is not a recognized dict.
  """
  if not isinstance(obj, dict) or depth > _MAX_ENVELOPE_DEPTH:
    return None
  for matches, unwrap in ENVELOPE_UNWRAPPERS:
    if matches(obj):
      row = unwrap(obj, depth)
      if row is not None and depth == 0:
        row = redact_env_values(row)
      return row
  return None


def _normalize_text_line(line: str) -> dict[str, Any] | None:
  m = _KLOG_RE.match(line.strip())
  if not m:
    return None
  return {
      "level": _KLOG_LEVELS.get(m.group(1), "info"),
      "ts": (
          f"{m.group(2)[:2]}-{m.group(2)[2:]}T{m.group(3)}"
      ),  # MM-DDTHH:MM:SS; klog omits the year
      "msg": m.group(4),
  }


def _is_nonlog_k8s_or_audit_dict(obj: dict[str, Any]) -> bool:
  """True when an unrecognized JSON object contains a K8s manifest/Secret/List or audit payload."""
  stack: list[Any] = [obj]
  while stack:
    cur = stack.pop()
    if isinstance(cur, dict):
      kind = cur.get("kind")
      if isinstance(kind, str) and (
          kind in _NONLOG_SECRET_OR_LIST_KINDS
          or (
              isinstance(cur.get("apiVersion"), str)
              and (cur is obj or isinstance(cur.get("metadata"), dict))
          )
      ):
        return True
      if any(k in cur for k in _NONLOG_AUDIT_KEYS):
        return True
      stack.extend(cur.values())
    elif isinstance(cur, list):
      stack.extend(cur)
  return False


def _decode_json_objects(body: str) -> list[dict[str, Any]] | None:
  """Decodes one or more top-level JSON objects, or None when not a pure JSON object stream."""
  decoder = json.JSONDecoder()
  idx = 0
  n = len(body)
  objs: list[dict[str, Any]] = []
  while idx < n:
    while idx < n and body[idx].isspace():
      idx += 1
    if idx >= n:
      break
    try:
      obj, end = decoder.raw_decode(body, idx)
    except (json.JSONDecodeError, RecursionError, ValueError):
      return None
    if not isinstance(obj, dict):
      return None
    objs.append(obj)
    idx = end
  return objs if objs else None


def _reassemble_cri_lines(lines: list[str]) -> list[str]:
  """Joins CRI partial (`P`) chunks per stream up to their terminating `F` line.

  Kubelet splits container log lines over 16 KiB across `stdout P` / `stderr P`
  chunks followed by a final `F` line. Reassembling them before classification
  restores valid JSON records and ensures an unterminated partial JSON line at
  EOF is dropped as one fragment rather than leaking tail chunks.

  Args:
    lines: Raw lines split from a log file.

  Returns:
    Lines with CRI `P...F` sequences joined into single lines.
  """
  out: list[str] = []
  pending: dict[str, tuple[str, list[str], int]] = {}
  for line in lines:
    m = _CRI_LINE_RE.match(line.lstrip("\ufeff"))
    if not m:
      out.append(line)
      continue
    ts, stream, flag, payload = m.groups()
    if flag == "P":
      if stream in pending:
        first_ts, chunks, size = pending[stream]
        if size < _MAX_CRI_PARTIAL_BYTES:
          room = _MAX_CRI_PARTIAL_BYTES - size
          chunks.append(payload[:room])
          size += min(len(payload), room)
        pending[stream] = (first_ts, chunks, size)
      else:
        chunk = payload[:_MAX_CRI_PARTIAL_BYTES]
        pending[stream] = (ts, [chunk], len(chunk))
      continue
    if stream in pending:
      first_ts, chunks, _ = pending.pop(stream)
      out.append(f"{first_ts} {stream} F {''.join(chunks)}{payload}")
    else:
      out.append(line)
  for stream, (first_ts, chunks, _) in pending.items():
    out.append(f"{first_ts} {stream} P {''.join(chunks)}")
  return out


def _looks_like_json_fragment_payload(text: str) -> bool:
  """True when an unterminated CRI `P` payload carries partial JSON syntax."""
  return (
      text.startswith(("{", "["))
      or bool(_PRETTY_JSON_MEMBER_RE.match(text))
      or bool(_JSON_CLOSING_RE.match(text))
      or '":' in text
      or '" :' in text
  )


def _is_bare_json_array_item(stripped: str) -> bool:
  """True for a standalone JSON primitive line inside a pretty-printed array."""
  item = stripped[:-1] if stripped.endswith(",") else stripped
  if not item:
    return False
  if item in ("true", "false", "null"):
    return True
  if (len(item) >= 2 and item[0] == '"' and item[-1] == '"') or (
      item[0] in "-0123456789"
  ):
    try:
      return isinstance(json.loads(item), (str, int, float))
    except (json.JSONDecodeError, RecursionError):
      return False
  return False


def _classify_non_json_line(stripped: str) -> tuple[str, str]:
  """Classifies a non-JSON line as JSON fragment/close, klog record, or raw."""
  if stripped.startswith('{"'):
    return "", "json_obj_frag"
  if stripped in ("{", "[") or _TRUNCATED_JSON_ARRAY_RE.match(stripped):
    return "", "json_opener"
  if _PRETTY_JSON_MEMBER_RE.match(stripped):
    return "", "json_member"
  if stripped.startswith("{"):
    return "", "fragment"
  if _JSON_CLOSING_RE.match(stripped):
    return "", "json_close"
  klog = _normalize_text_line(stripped)
  if klog:
    klog["msg"] = redact_env_text(klog["msg"])
    return json.dumps(klog, ensure_ascii=False), "record"
  return redact_env_text(stripped), "raw"


def _classify_line(line: str) -> tuple[str, str]:
  """Normalises one log line and classifies it as record, raw, JSON piece, or empty."""
  stripped = line.lstrip("\ufeff").strip()
  if not stripped:
    return "", "empty"
  cri = _CRI_PREFIX_RE.match(stripped)
  if cri:
    flag, candidate = cri.group(1), cri.group(2).strip()
    if flag == "P" and _looks_like_json_fragment_payload(candidate):
      return "", "fragment"
    if (
        candidate.startswith(("{", "["))
        or _PRETTY_JSON_MEMBER_RE.match(candidate)
        or _JSON_CLOSING_RE.match(candidate)
        or _KLOG_RE.match(candidate)
    ):
      stripped = candidate
  obj = _json_or_none(stripped)
  if isinstance(obj, dict):
    if not obj:
      return "", "json_close"
    row = normalize_record(obj)
    if row is not None:
      return json.dumps(row, ensure_ascii=False), "record"
    if any(matches(obj) for matches, _ in ENVELOPE_UNWRAPPERS):
      return "", "empty"
    if _is_nonlog_k8s_or_audit_dict(obj):
      return "", "empty"
    return json.dumps(redact_env_values(obj), ensure_ascii=False), "raw_json"
  if isinstance(obj, list):
    return "", "empty"
  return _classify_non_json_line(stripped)


def normalize_line(line: str) -> str:
  """Returns one normalised JSON line (or plain text) for a single raw input line."""
  return _classify_line(line)[0]


def _yield_decoded_objects(objs: list[dict[str, Any]]) -> Iterator[str]:
  """Emits normalized lines for top-level JSON objects, dropping non-log manifests."""
  for whole in objs:
    if isinstance(whole.get("items"), list):
      yield from _iter_array(whole["items"])
    else:
      row = normalize_record(whole)
      if row is not None:
        yield json.dumps(row, ensure_ascii=False)


def _extract_whole_json(body: str) -> list[str] | None:
  """Decodes a complete JSON array or object document, or None when invalid."""
  if body.startswith("["):
    arr = _json_or_none(body)
    if isinstance(arr, list):
      return list(_iter_array(arr))
    return None
  if body.startswith("{"):
    stripped = body.strip()
    if "\n" not in stripped:
      whole = _json_or_none(stripped)
      if isinstance(whole, dict):
        return list(_yield_decoded_objects([whole]))
      return None
    first_line = stripped.split("\n", 1)[0]
    if _json_or_none(first_line) is None:
      objs = _decode_json_objects(stripped)
      if objs is not None:
        return list(_yield_decoded_objects(objs))
  return None


_JSON_DOC_START_RE = re.compile(r'^(?:\{\s*(?:"|\}|$)|\[\s*(?:\{|\[|"|\]|$))')


_JSON_FRAGMENT_KINDS = frozenset(
    {"fragment", "json_opener", "json_member", "json_obj_frag"}
)


def _scan_line_records(
    text: str, looks_like_json_doc: bool
) -> tuple[list[str], bool]:
  """Line-by-line fallback extraction with broken pretty-JSON detection."""
  records: list[str] = []
  recognized = 0
  raw_json_count = 0
  dropped_fragments = False
  has_opener = False
  has_member = False
  has_bare_opener = False
  has_pretty_member = False
  json_lines = 0
  non_json_raw = 0
  for line in _reassemble_cri_lines(text.splitlines()):
    stripped = line.lstrip("\ufeff").strip()
    if stripped.startswith("["):
      arr = _json_or_none(stripped)
      if isinstance(arr, list):
        emitted = list(_iter_array(arr))
        records.extend(emitted)
        recognized += len(emitted)
        continue
    out, kind = _classify_line(line)
    if kind in _JSON_FRAGMENT_KINDS:
      dropped_fragments = True
      json_lines += 1
      has_opener = has_opener or kind in ("json_opener", "json_obj_frag")
      has_member = has_member or kind in ("json_member", "json_obj_frag")
      has_bare_opener = has_bare_opener or kind == "json_opener"
      has_pretty_member = has_pretty_member or kind == "json_member"
    elif kind == "json_close":
      json_lines += 1
    elif kind == "record":
      recognized += 1
      records.append(out)
    elif kind == "raw_json":
      raw_json_count += 1
      records.append(out)
    elif out:
      records.append(out)
      if not _is_bare_json_array_item(stripped):
        non_json_raw += 1
  if recognized == 0 and dropped_fragments:
    if raw_json_count > 0 and not (has_bare_opener or has_pretty_member):
      return records, False
    if looks_like_json_doc or (
        has_opener and has_member and json_lines >= non_json_raw
    ):
      return [], True
  return records, False


def extract_file_records(text: str) -> tuple[list[str], bool]:
  """Extracts normalised log lines from one file and flags unreadable JSON exports.

  When a JSON export drops fragments (for example a truncated export, two
  pretty-printed JSON arrays appended into one file, or a pretty-printed JSON
  export prefixed by non-JSON CLI warnings) and yields zero valid log records,
  leftover bare strings and preamble lines are discarded and `unreadable` is
  returned as True so the caller does not count fragments as log lines.
  Plain-text logs without a dominant pretty-printed JSON body keep their
  surrounding raw lines even if an isolated line starts with `{`.

  Args:
    text: Full text content of a log or event file.

  Returns:
    `(records, unreadable)` where `unreadable` is True when a broken JSON
    export dropped fragments and yielded zero recognised records.
  """
  body = text.lstrip("\ufeff \t\r\n")
  whole = _extract_whole_json(body)
  if whole is not None:
    return whole, False
  return _scan_line_records(text, bool(_JSON_DOC_START_RE.match(body)))


def iter_records(text: str) -> Iterator[str]:
  """Yields normalized lines from a JSON array, JSONL, or plain-text file body.

  JSON arrays (e.g. `gcloud logging read --format=json` or `kubectl get events
  -o json` `.items`) are ordered by their timestamp field when present so
  downstream timeline compression sees records oldest-first. Single or
  concatenated JSON documents that are not log records yield nothing; broken
  pretty-printed JSON exports yield nothing instead of leftover fragments.

  Args:
    text: Full text content of a log or event file.

  Yields:
    One normalized JSON or raw text line per log record.
  """
  records, _ = extract_file_records(text)
  yield from records


def _iter_array(arr: list[Any]) -> Iterator[str]:
  """Normalizes and timestamp-sorts records from a parsed JSON array."""
  rows: list[tuple[str, str]] = []
  for item in arr:
    if isinstance(item, dict):
      row = normalize_record(item)
      if row is None:
        continue
      # Envelope receive timestamp orders the export; inner `ts` is kept for
      # display even if formatted differently.
      sort_ts = str(
          _first(item, "timestamp", "time", "@timestamp", "TimeGenerated")
          or row.get("ts")
          or ""
      )
      rows.append((sort_ts, json.dumps(row, ensure_ascii=False)))
    elif isinstance(item, str):
      out = normalize_line(item)
      if out:
        rows.append(("", out))
  if rows and all(r[0] for r in rows):
    rows.sort(key=lambda r: r[0])
  for _, line in rows:
    yield line
