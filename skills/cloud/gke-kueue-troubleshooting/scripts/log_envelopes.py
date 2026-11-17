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

# Google Cloud audit `methodName`, e.g. `io.k8s.core.v1.namespaces.delete`,
# `io.k8s.kueue.v1beta2.workloads.status.patch`, `io.k8s.batch.v1.jobs.create`.
_GCP_METHOD_RE = re.compile(
    r"^io\.k8s\.(?P<group>[a-z0-9.-]+?)\.(?P<version>v\d+(?:(?:alpha|beta)\d+)?)"
    r"\.(?P<resource>[a-z0-9-]+)(?:\.(?P<subresource>[a-z0-9-]+))?\.(?P<verb>[a-z]+)$"
)
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
  except json.JSONDecodeError:
    return None


def _first(d: dict[str, Any], *keys: str) -> Any:
  for k in keys:
    v = d.get(k)
    if v not in (None, ""):
      return v
  return None


def _request_object_parts(req: Any) -> dict[str, Any]:
  """Picks the parts of a request/response object worth keeping from audit."""
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
    out["spec"] = req["spec"]
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
  summary = [f"[Audit {ref.verb} {ref.resource_path}] {ref.target}"]
  for key, limit in (
      ("spec", 1200),
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


def _gcp_method_ref(method: str) -> AuditRef:
  """verb / resource / subresource / group from a Google Cloud audit `methodName`."""
  m = _GCP_METHOD_RE.match(method)
  if m:
    return AuditRef(
        verb=m.group("verb"),
        resource=m.group("resource"),
        subresource=m.group("subresource") or "",
        group="" if m.group("group") == "core" else m.group("group"),
    )
  tail = method.rsplit(".", 1)
  return AuditRef(verb=tail[-1] if tail and tail[-1] in _VERBS else "")


def _gcp_resource_target(res_name: str, resource: str) -> tuple[str, str]:
  """`(namespace, name)` from a Google Cloud audit `resourceName` path."""
  namespace, name = "", ""
  segs = [s for s in res_name.split("/") if s]
  if "namespaces" in segs:
    i = segs.index("namespaces")
    if i + 1 < len(segs):
      if resource == "namespaces" and i + 2 >= len(segs):
        name = segs[i + 1]
      else:
        namespace = segs[i + 1]
        if segs[-1] not in ("status",) and len(segs) >= i + 4:
          name = segs[i + 3]
  elif segs:
    name = segs[-1]
  return namespace, name


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
  method_ref = _gcp_method_ref(method)
  namespace, name = _gcp_resource_target(res_name, method_ref.resource)
  return _audit_row(
      dataclasses.replace(method_ref, namespace=namespace, name=name),
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
    for mf in meta.get("managedFields") or []:
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


def _unwrap_text_payload(text: str, depth: int) -> dict[str, Any] | None:
  """A payload string: nested JSON record, klog line, or None when it is neither."""
  inner_obj = _json_or_none(text)
  if inner_obj is None:
    return _normalize_text_line(text)
  return normalize_record(inner_obj, depth + 1)


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
  return str(obj.get("kind") or "") == "Event" and str(
      obj.get("apiVersion") or ""
  ).startswith("audit.k8s.io")


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
    inner = normalize_record(obj["jsonPayload"], depth + 1) or dict(
        obj["jsonPayload"]
    )
    _fill_envelope_defaults(inner, ts, sev)
    if "msg" not in inner and "message" in inner:
      inner["msg"] = inner["message"]
    if "object" not in inner and "involvedObject" in inner:
      inner["object"] = inner["involvedObject"]
    return inner
  text = str(obj["textPayload"])
  inner = _unwrap_text_payload(text, depth) or {"msg": text}
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
) -> dict[str, Any]:
  """Unwraps a fluent-bit, Fluentd, Filebeat, or Loki log collector envelope."""
  payload = _collector_payload(obj) or ""
  ts = str(
      _first(obj, "time", "@timestamp", "timestamp", "TimeGenerated") or ""
  )
  inner = _unwrap_text_payload(payload, depth) or {"msg": payload.rstrip("\n")}
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
      return unwrap(obj, depth)
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


def normalize_line(line: str) -> str:
  """Normalises one text line; returns the (possibly unchanged) line."""
  stripped = line.strip()
  if not stripped:
    return ""
  obj = _json_or_none(stripped)
  if isinstance(obj, dict):
    row = normalize_record(obj)
    return json.dumps(row, ensure_ascii=False) if row is not None else stripped
  klog = _normalize_text_line(stripped)
  return json.dumps(klog, ensure_ascii=False) if klog else stripped


def iter_records(text: str) -> Iterator[str]:
  """Yields normalized lines from a JSON array, JSONL, or plain-text file body.

  JSON arrays (e.g. `gcloud logging read --format=json` or `kubectl get events
  -o json` `.items`) are ordered by their timestamp field when present so
  downstream timeline compression sees records oldest-first. A single
  pretty-printed JSON document that is not a log record yields nothing.

  Args:
    text: Full text content of a log or event file.

  Yields:
    One normalized JSON or raw text line per log record.
  """
  body = text.lstrip()
  if body.startswith("["):
    arr = _json_or_none(body)
    if isinstance(arr, list):
      yield from _iter_array(arr)
      return
  elif body.startswith("{") and "\n" in body.strip():
    whole = _json_or_none(body)
    if isinstance(whole, dict):
      if isinstance(whole.get("items"), list):
        yield from _iter_array(whole["items"])
      else:
        row = normalize_record(whole)
        if row is not None:
          yield json.dumps(row, ensure_ascii=False)
      return
  for line in text.splitlines():
    out = normalize_line(line)
    if out:
      yield out


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
