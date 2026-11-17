#!/usr/bin/env python3
"""Structural gates of the diagnostic-report validator (`validate_report.py`).

Every gate is `(ctx: DraftContext) -> dict[str, list]` and owns exactly one key
of the validator's JSON report; `run_report_gates(ctx)` applies `REPORT_GATES`
in
order and merges the results. Gates never judge whether a conclusion is right,
only whether the report is complete, traceable and executable:

  check_headers              -> missing_headers
  check_graph_coverage       -> uninspected_graph_objects
  check_evidence_grounding   -> fabricated_quotes
  check_fact_coverage        -> unaddressed_facts
  check_remediation_mapping  -> remediation_gaps
  check_open_questions       -> open_question_gaps
  check_ruled_out_reasons    -> weak_ruled_out
  check_config_remediation   -> config_remediation_errors
  check_kubectl_resources    -> unknown_kubectl_resources
  check_schema_warnings      -> schema_warnings
"""

from __future__ import annotations

import dataclasses
import os
import re
from typing import Any, Callable

import kueue_schema_yaml_checks as yaml_checks
import report_output

REQUIRED_HEADERS = (
    "### Diagnostic Summary",
    "#### Scope",
    "#### Observations",
    "#### Root Cause",
    "#### Ruled Out",
    "#### Remediation",
)

_SECTION_RE = re.compile(r"^####\s+(.+?)\s*$", re.MULTILINE)
_RC_RE = re.compile(r"\bRC(\d{1,2})\b")
_RC_START_RE = re.compile(
    r"(?m)^\s*(?:[-*+]|\d+\.|#{1,6})?\s*\*{0,2}\[?RC(\d{1,2})\b"
)
# Open Questions: explicit "not determinable from this evidence" entries.
_OQ_RE = re.compile(r"\bOQ(\d{1,2})\b")
_OQ_START_RE = re.compile(
    r"(?m)^\s*(?:[-*+]|\d+\.|#{1,6})?\s*\*{0,2}\[?OQ(\d{1,2})\b"
)
# A part label at the start of a line (optionally bulleted/bold). The part's
# body runs from the label to the next label or the end of the OQ, so
# alternatives written on their own lines still belong to `Candidates:`.
_OQ_PART_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*+]["
    r" \t]*)?\*{0,2}(basis|candidates|discriminator|collect)\*{0,2}[ \t]*:["
    r" \t]*"
)
_KUBECTL_WRITE_RE = re.compile(
    r"kubectl\s+(?:-\S+(?:\s+\S+)?\s+)*(?:patch|edit|apply|replace|delete|create|annotate|label|scale|drain|cordon|taint|rollout\s+restart)\b",
    re.IGNORECASE,
)
# The external-layer marker is read from the RC header line (Root Cause bullet
# or Remediation entry), never from the body, so a negated mention such as
# "this is not Outside Kueue" inside the text does not switch the rule set.
_OUTSIDE_RE = re.compile(r"(?<!\bnot\s)\boutside kueue\b", re.IGNORECASE)
_DEFECT_RE = re.compile(r"(?<!\bnot\s)\bkueue defect\b", re.IGNORECASE)
_DOC_REMEDIATION_LINK_RE = re.compile(
    r"https://(?:kueue\.sigs\.k8s\.io/docs/|docs\.cloud\.google\.com/|cloud\.google\.com/|kubernetes\.io/docs/|jobset\.sigs\.k8s\.io/docs/)",
    re.IGNORECASE,
)
_DEFECT_ISSUE_LINK_RE = re.compile(
    r"https://github\.com/kubernetes-sigs/kueue/issues\b",
    re.IGNORECASE,
)
_CONFIRM_SIGNAL_RE = re.compile(
    r"\b(?:confirm|verify|verified|until|when|once|expected|check\s+that|transitions?\s+to|becomes?\s+(?:True|Ready|Admitted))\b",
    re.IGNORECASE,
)
_KUEUE_MUTATION_RE = re.compile(
    r"(?:kind:\s*(?:ClusterQueue|LocalQueue|ResourceFlavor|AdmissionCheck|ProvisioningRequestConfig|Cohort|Topology|Workload|WorkloadPriorityClass|Configuration|KueueConfiguration)\b"
    r"|kubectl\s+(?:-\S+(?:\s+\S+)?\s+)*(?:patch|edit|apply|replace|delete|create|annotate|label)\s+(?:-\S+(?:\s+\S+)?\s+)*(?:clusterqueues?|cq|localqueues?|lq|resourceflavors?|rf|admissionchecks?|ac|provisioningrequestconfigs?|prc|cohorts?|topolog(?:y|ies)|workloads?)(?:\.kueue\.x-k8s\.io)?\b"
    r"|kubectl\s+(?:-\S+(?:\s+\S+)?\s+)*(?:patch|edit|apply|replace)\s+(?:-\S+(?:\s+\S+)?\s+)*(?:configmaps?|cm)(?:\s+|/)(?:-\S+\s+)*kueue-manager-config\b)",
    re.IGNORECASE,
)
_KUBECTL_RE = re.compile(
    r"kubectl\s+(?:(?:-n|--namespace)\s+\S+\s+)?"
    r"(get|describe|patch|edit|apply|delete|create|annotate|label|scale|replace|rollout\s+\w+|explain)\s+"
    r"(?:(?:-n|--namespace)\s+\S+\s+)?([^\s`'\",;)]+)",
    re.IGNORECASE,
)
_FACT_ID_RE = re.compile(r"\b[SL]\d{1,3}\b")
_QUOTE_FACT_PREFIX_RE = re.compile(r"^\[?[SL]\d{1,3}\]?:?\s*")
_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MIN_QUOTE_LEN, _MAX_QUOTE_LEN = 18, 160
_INSPECTED_GRAPH_KINDS = (
    "cohort",
    "clusterqueue",
    "resourceflavor",
    "admissioncheck",
)

# Resource names (singular, plural, short) that `kubectl` accepts on any
# cluster, independent of Kueue. Anything carrying an explicit API group suffix
# other than kueue.x-k8s.io (e.g. `jobsets.jobset.x-k8s.io`) is also accepted.
_CORE_KUBECTL_RESOURCES = frozenset({
    "pod",
    "pods",
    "po",
    "deployment",
    "deployments",
    "deploy",
    "replicaset",
    "replicasets",
    "rs",
    "statefulset",
    "statefulsets",
    "sts",
    "daemonset",
    "daemonsets",
    "ds",
    "job",
    "jobs",
    "cronjob",
    "cronjobs",
    "cj",
    "configmap",
    "configmaps",
    "cm",
    "secret",
    "secrets",
    "namespace",
    "namespaces",
    "ns",
    "node",
    "nodes",
    "no",
    "event",
    "events",
    "ev",
    "service",
    "services",
    "svc",
    "endpoints",
    "ep",
    "ingress",
    "ingresses",
    "ing",
    "persistentvolumeclaim",
    "persistentvolumeclaims",
    "pvc",
    "persistentvolume",
    "persistentvolumes",
    "pv",
    "serviceaccount",
    "serviceaccounts",
    "sa",
    "role",
    "roles",
    "rolebinding",
    "rolebindings",
    "clusterrole",
    "clusterroles",
    "clusterrolebinding",
    "clusterrolebindings",
    "customresourcedefinition",
    "customresourcedefinitions",
    "crd",
    "crds",
    "priorityclass",
    "priorityclasses",
    "pc",
    "resourcequota",
    "resourcequotas",
    "quota",
    "limitrange",
    "limitranges",
    "limits",
    "horizontalpodautoscaler",
    "horizontalpodautoscalers",
    "hpa",
    "lease",
    "leases",
    "podtemplate",
    "podtemplates",
    "poddisruptionbudget",
    "poddisruptionbudgets",
    "pdb",
    "jobset",
    "jobsets",
    "rayjob",
    "rayjobs",
    "raycluster",
    "rayclusters",
    "pytorchjob",
    "pytorchjobs",
    "mpijob",
    "mpijobs",
    "tfjob",
    "tfjobs",
    "xgboostjob",
    "xgboostjobs",
    "paddlejob",
    "paddlejobs",
    "jaxjob",
    "jaxjobs",
    "leaderworkerset",
    "leaderworkersets",
    "lws",
    "appwrapper",
    "appwrappers",
    "provisioningrequest",
    "provisioningrequests",
    "mutatingwebhookconfiguration",
    "mutatingwebhookconfigurations",
    "validatingwebhookconfiguration",
    "validatingwebhookconfigurations",
    "all",
})
_CONFIG_KIND_RE = re.compile(r"kind:\s*KueueConfiguration\b")
_CONFIG_PATCH_RE = re.compile(
    r"kubectl\s+(?:-n\s+\S+\s+)?patch\s+(?:configmap|cm)\b[^\n]*controller_manager_config\.yaml",
    re.IGNORECASE,
)


# --- Context -----------------------------------------------------------------


@dataclasses.dataclass
class LedgerData:
  """What `snapshot.py` / `trace_logs.py` recorded in the coverage ledger (all empty when it is absent)."""

  referenced: list[str] = dataclasses.field(default_factory=list)
  inspected: list[str] = dataclasses.field(default_factory=list)
  tool_outputs: list[str] = dataclasses.field(default_factory=list)
  facts: list[dict[str, Any]] = dataclasses.field(default_factory=list)
  detected_kueue_version: dict[str, Any] | None = None

  @classmethod
  def load(cls, ledger_path: str | None) -> "LedgerData":
    """Reads the ledger JSON; a missing or unreadable file yields an empty ledger."""
    if not ledger_path or not os.path.exists(ledger_path):
      return cls()
    data = report_output.load_ledger(ledger_path, strict=True)
    vinfo = data.get("detected_kueue_version")
    return cls(
        referenced=data.get("referenced", []),
        inspected=data.get("inspected", []),
        tool_outputs=data.get("tool_outputs", []),
        facts=[x for x in data.get("facts", []) if isinstance(x, dict)],
        detected_kueue_version=vinfo if isinstance(vinfo, dict) else None,
    )


@dataclasses.dataclass
class DraftContext:
  """One draft report plus everything the gates compare it against."""

  draft_text: str
  ledger: LedgerData
  version_info: dict[str, Any]
  schema: dict[str, Any]
  sections: dict[str, str] = dataclasses.field(init=False)

  def __post_init__(self) -> None:
    self.sections = split_sections(self.draft_text)

  def section(self, title: str) -> str:
    return self.sections.get(title, "")


ReportGate = Callable[[DraftContext], dict[str, list[Any]]]


def _normalize_for_match(text: str) -> str:
  """Collapses whitespace and strips quoting/flow-YAML punctuation so YAML/JSON formatting differences do not break substring checks."""
  text = text.replace("''", "'").replace('\\"', '"')
  text = text.replace('"', "").replace("'", "").replace("`", "")
  text = re.sub(r"[\[\]{},]", " ", text)
  text = re.sub(r"(?:^|\s)-\s+", " ", text)
  return re.sub(r"\s+", " ", text).strip().lower()


def split_sections(draft_text: str) -> dict[str, str]:
  """Returns {lower-cased '#### ' header title: body text} for the draft."""
  sections: dict[str, str] = {}
  matches = list(_SECTION_RE.finditer(draft_text))
  for i, m in enumerate(matches):
    end = matches[i + 1].start() if i + 1 < len(matches) else len(draft_text)
    title = m.group(1).strip().lower()
    sections[title] = sections.get(title, "") + draft_text[m.end() : end]
  return sections


def _mentions_id(text: str, fact_id: str) -> bool:
  return (
      re.search(rf"(?<![A-Za-z0-9-]){re.escape(fact_id)}(?![0-9])", text)
      is not None
  )


def _first_line(text: str) -> str:
  return next((ln for ln in text.splitlines() if ln.strip()), "")


# --- Gates -------------------------------------------------------------------


def check_headers(ctx: DraftContext) -> dict[str, list[str]]:
  """All required section headers exist."""
  return {
      "missing_headers": [
          h for h in REQUIRED_HEADERS if h not in ctx.draft_text
      ]
  }


def check_graph_coverage(ctx: DraftContext) -> dict[str, list[str]]:
  """Referenced Kueue graph objects (Cohort, ClusterQueue, ResourceFlavor, AdmissionCheck) were inspected or at least named."""
  inspected_names = {ref.split("/")[-1].lower() for ref in ctx.ledger.inspected}
  draft_lower = ctx.draft_text.lower()
  uninspected: list[str] = []
  for ref in ctx.ledger.referenced:
    kind, _, name = ref.partition("/")
    short_name = name.split("/")[-1].lower()
    if (
        kind in _INSPECTED_GRAPH_KINDS
        and short_name not in inspected_names
        and short_name not in draft_lower
    ):
      uninspected.append(ref)
  return {"uninspected_graph_objects": uninspected}


def _is_checkable_quote(match: str) -> bool:
  return (
      _MIN_QUOTE_LEN <= len(match) <= _MAX_QUOTE_LEN
      and " " in match
      and not match.startswith(("kubectl", "python"))
  )


_DOTTED_YAML_KV_RE = re.compile(
    r"^([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)\s*([:=])\s*(.+)$"
)


def _quote_in_corpus(needle: str, corpus: str, norm_corpus: str) -> bool:
  """Returns True when an inline-quoted snippet matches the tool output corpus."""
  stripped_needle = _QUOTE_FACT_PREFIX_RE.sub("", needle).strip()
  if needle in corpus or (stripped_needle and stripped_needle in corpus):
    return True
  if _normalize_for_match(needle) in norm_corpus:
    return True
  if stripped_needle and _normalize_for_match(stripped_needle) in norm_corpus:
    return True
  # Support dotted YAML path notation in prose (e.g.
  # `spec.topologyName: example-topology` when the YAML has `spec:` and
  # `topologyName: example-topology` on separate lines).
  m = _DOTTED_YAML_KV_RE.match(stripped_needle or needle)
  if m:
    parts = m.group(1).split(".")
    leaf_kv = f"{parts[-1]}{m.group(2)} {m.group(3)}"
    if _normalize_for_match(leaf_kv) in norm_corpus and all(
        p.lower() in norm_corpus for p in parts[:-1]
    ):
      return True
  return False


def check_evidence_grounding(ctx: DraftContext) -> dict[str, list[str]]:
  """Inline-quoted evidence under `#### Observations` must occur in the recorded tool outputs."""
  tool_outputs = ctx.ledger.tool_outputs
  if not tool_outputs or "#### Observations" not in ctx.draft_text:
    return {"fabricated_quotes": []}
  corpus = "\n".join(tool_outputs)
  norm_corpus = _normalize_for_match(corpus)
  obs_section = ctx.draft_text.split("#### Observations", 1)[1].split(
      "####", 1
  )[0]
  obs_no_fences = _FENCED_BLOCK_RE.sub("", obs_section)
  fabricated = [
      match.strip()
      for match in _INLINE_CODE_RE.findall(obs_no_fences)
      if _is_checkable_quote(match)
      and not _quote_in_corpus(match.strip(), corpus, norm_corpus)
  ]
  return {"fabricated_quotes": fabricated}


def check_fact_coverage(ctx: DraftContext) -> dict[str, list[dict[str, str]]]:
  """No-op in the streamlined validator: tagged fact ids are reading aids, not a mandatory checklist."""
  del ctx
  return {"unaddressed_facts": []}


def _chunk_by_id(
    text: str, start_re: re.Pattern[str], any_re: re.Pattern[str], prefix: str
) -> tuple[list[str], dict[str, str]]:
  """Splits a section into per-id chunks, preferring line-start headers over inline cross-references."""
  mentions = [
      (m.start(), f"{prefix}{int(m.group(1))}") for m in start_re.finditer(text)
  ]
  if not mentions:
    mentions = [
        (m.start(), f"{prefix}{int(m.group(1))}") for m in any_re.finditer(text)
    ]
  ids: list[str] = []
  chunks: dict[str, str] = {}
  for i, (start, cid) in enumerate(mentions):
    end = mentions[i + 1][0] if i + 1 < len(mentions) else len(text)
    chunks[cid] = chunks.get(cid, "") + text[start:end]
    if cid not in ids:
      ids.append(cid)
  return ids, chunks


def _chunk_by_rc(text: str) -> tuple[list[str], dict[str, str]]:
  return _chunk_by_id(text, _RC_START_RE, _RC_RE, "RC")


def _chunk_by_oq(text: str) -> tuple[list[str], dict[str, str]]:
  return _chunk_by_id(text, _OQ_START_RE, _OQ_RE, "OQ")


def _has_bullets(text: str) -> bool:
  return re.search(r"^\s*[-*\d]", text, re.MULTILINE) is not None


@dataclasses.dataclass
class _RemediationScan:
  """Per-report inputs of the RC -> remediation mapping, derived once from the sections."""

  scope_text: str
  oq_ids: list[str]
  oq_subjects: dict[
      str, str
  ]  # fact id -> OQ that declares it undecided (OQ header line only)
  rem_chunks: dict[str, str]

  @classmethod
  def from_sections(cls, ctx: DraftContext) -> "_RemediationScan":
    oq_ids, oq_chunks = _chunk_by_oq(ctx.section("open questions"))
    oq_subjects: dict[str, str] = {}
    for oq in oq_ids:
      for fid in _FACT_ID_RE.findall(_first_line(oq_chunks.get(oq, ""))):
        oq_subjects.setdefault(fid, oq)
    _, rem_chunks = _chunk_by_rc(ctx.section("remediation"))
    return cls(
        ctx.section("scope").strip().lower(), oq_ids, oq_subjects, rem_chunks
    )

  @property
  def is_pure_outside_scope(self) -> bool:
    return (
        "outside kueue" in self.scope_text
        and "mixed" not in self.scope_text
        and not self.scope_text.startswith("kueue")
    )

  @property
  def is_defect_scope(self) -> bool:
    return "kueue defect" in self.scope_text and "mixed" not in self.scope_text


def _no_rc_gaps(root: str, scan: _RemediationScan) -> list[str]:
  """Gaps for a report without any `RC<n>`: either un-numbered entries or neither RC nor OQ."""
  if _has_bullets(root) and not re.search(r"\bnone\b", root, re.IGNORECASE):
    return [
        "Root Cause entries are not numbered: start each one with RC1, RC2, ..."
        " so remediation can reference them."
    ]
  if not scan.oq_ids and not scan.scope_text.startswith("undetermined"):
    return [
        "No RC<n> under Root Cause and no OQ<n> under Open Questions: either"
        " establish a root cause from the evidence or open an Open Question"
        " that names what is missing (do not leave both empty)."
    ]
  return []


def _remediation_entry_gaps(
    rc: str, chunk: str, rc_is_outside: bool, rc_is_defect: bool = False
) -> list[str]:
  """The remediation entry links the documentation (required whenever YAML or a kubectl command is present), or (Outside Kueue / Kueue defect) states an action + confirmation signal."""
  if rc_is_outside and _KUEUE_MUTATION_RE.search(chunk):
    return [
        f"{rc}: Root Cause / Scope is 'Outside Kueue', but remediation mutates"
        " a Kueue object. Do not blame or patch Kueue to mask an external"
        " failure; state the external component/layer action and confirmation"
        " signal (or classify the RC as a Kueue configuration issue if a Kueue"
        " change is genuinely required)."
    ]
  has_doc_link = _DOC_REMEDIATION_LINK_RE.search(chunk) is not None
  has_code_or_cmd = "```" in chunk or "kubectl " in chunk
  if rc_is_defect:
    if (
        has_doc_link or _DEFECT_ISSUE_LINK_RE.search(chunk) is not None
    ) and _CONFIRM_SIGNAL_RE.search(chunk):
      return []
    return [
        f"{rc}: Kueue defect remediation must link the relevant"
        " documentation, https://github.com/kubernetes-sigs/kueue/issues, or"
        " support path and state a confirmation signal."
    ]
  if has_code_or_cmd and not has_doc_link:
    return [
        f"{rc}: remediation includes a YAML manifest or kubectl command without"
        " a documentation link (link the official"
        " https://kueue.sigs.k8s.io/docs/,"
        " https://docs.cloud.google.com/kubernetes-engine/docs/, or"
        " https://kubernetes.io/docs/ section that describes the fix)."
    ]
  if has_doc_link:
    return []
  if rc_is_outside and _CONFIRM_SIGNAL_RE.search(chunk):
    return []
  if rc_is_outside:
    return [
        f"{rc}: Outside Kueue remediation without a documentation link must"
        " state a verification/confirmation signal (e.g. 'Confirm by checking"
        " that ProvisioningRequest Provisioned=True and Workload"
        " Admitted=True')."
    ]
  return [
      f"{rc}: remediation has no concrete command, manifest, or documentation"
      " link (link the official documentation section describing the fix, and"
      " include that link with any kubectl command or YAML block)."
  ]


def _rc_gaps(rc: str, rc_root_text: str, scan: _RemediationScan) -> list[str]:
  """Returns remediation gaps for a single RC<n> root-cause entry."""
  chunk = scan.rem_chunks.get(rc)
  rc_head = _first_line(rc_root_text)
  if chunk is None:
    return [f"{rc}: no remediation entry references {rc}."]
  rc_is_outside = (
      scan.is_pure_outside_scope
      or _OUTSIDE_RE.search(rc_head) is not None
      or _OUTSIDE_RE.search(_first_line(chunk)) is not None
  )
  rc_is_defect = (
      scan.is_defect_scope
      or _DEFECT_RE.search(rc_head) is not None
      or _DEFECT_RE.search(_first_line(chunk)) is not None
  )
  return _remediation_entry_gaps(rc, chunk, rc_is_outside, rc_is_defect)


def check_remediation_mapping(ctx: DraftContext) -> dict[str, list[str]]:
  """Checks that every RC<n> has valid remediation or an OQ<n> is opened."""
  scan = _RemediationScan.from_sections(ctx)
  root = ctx.section("root cause")
  gaps: list[str] = []
  rc_ids, root_chunks = _chunk_by_rc(root)
  if scan.scope_text.startswith("undetermined") and not scan.oq_ids:
    gaps.append(
        "Scope is 'Undetermined' but `#### Open Questions` has no OQ<n> entry:"
        " state what cannot be decided, the candidate explanations, the"
        " discriminating observation and the read-only data to collect."
    )
  if not rc_ids:
    return {"remediation_gaps": gaps + _no_rc_gaps(root, scan)}
  for rc in rc_ids:
    gaps.extend(_rc_gaps(rc, root_chunks.get(rc, ""), scan))
  return {"remediation_gaps": gaps}


def _oq_parts(chunk: str) -> dict[str, str]:
  """Splits one OQ entry into its labelled parts; each body spans up to the next label."""
  matches = list(_OQ_PART_RE.finditer(chunk))
  parts: dict[str, str] = {}
  for i, m in enumerate(matches):
    end = matches[i + 1].start() if i + 1 < len(matches) else len(chunk)
    parts.setdefault(m.group(1).lower(), chunk[m.end() : end].strip())
  return parts


def check_open_questions(ctx: DraftContext) -> dict[str, list[str]]:
  """Streamlined Open Questions check: only rejects mutating commands inside Collect lines."""
  text = ctx.section("open questions")
  oq_ids, chunks = _chunk_by_oq(text)
  gaps: list[str] = []
  for oq in oq_ids:
    parts = _oq_parts(chunks.get(oq, ""))
    if "collect" in parts and (
        _KUBECTL_WRITE_RE.search(parts["collect"])
        or _KUEUE_MUTATION_RE.search(parts["collect"])
    ):
      gaps.append(
          f"{oq}: `Collect:` must be read-only; it contains a mutating command"
          " or manifest."
      )
  return {"open_question_gaps": gaps}


def check_ruled_out_reasons(ctx: DraftContext) -> dict[str, list[str]]:
  """No-op in the streamlined validator: Ruled Out bullets do not require a minimum word count."""
  del ctx
  return {"weak_ruled_out": []}


def check_config_remediation(ctx: DraftContext) -> dict[str, list[str]]:
  """Controller-configuration remediations that cannot work as written."""
  rem = ctx.section("remediation")
  problems: list[str] = []
  if _CONFIG_KIND_RE.search(rem):
    problems.append(
        "The controller configuration document is `kind: Configuration`"
        " (apiVersion config.kueue.x-k8s.io/...), not `kind:"
        " KueueConfiguration` (see"
        " https://kueue.sigs.k8s.io/docs/getting-started/installation/ and"
        " https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/)."
    )
  if _CONFIG_PATCH_RE.search(rem):
    problems.append(
        "`kubectl patch configmap ... controller_manager_config.yaml` replaces"
        " the whole `controller_manager_config.yaml` string; unless the patch"
        " carries the complete document every other setting is lost. Show the"
        " complete edited document (`kubectl edit configmap` or `kubectl apply`"
        " of the full ConfigMap) instead."
    )
  return {"config_remediation_errors": problems}


def _known_kubectl_resources(schema: dict[str, Any]) -> set[str]:
  """Returns lowercase kubectl resource names and shortNames known to the cluster."""
  known = set(_CORE_KUBECTL_RESOURCES)
  for kind, entry in schema.items():
    if kind.startswith("_") or kind == "KueueConfiguration":
      continue
    low = kind.lower()
    known.update({low, low + "s"})
    if low.endswith("y"):
      known.add(low[:-1] + "ies")
    # plural / singular / shortNames as declared by the release's CRDs
    # (e.g. `cq`, `lq`, `rf`, `ac`, `queue`, `flavor`).
    if isinstance(entry, dict):
      known.update(str(n).lower() for n in entry.get("kubectl_names") or [])
  return known


def check_kubectl_resources(ctx: DraftContext) -> dict[str, list[str]]:
  """kubectl commands whose resource argument is not a known kind."""
  schema = ctx.schema
  known = _known_kubectl_resources(schema)
  problems: list[str] = []
  seen: set[str] = set()
  for m in _KUBECTL_RE.finditer(ctx.section("remediation")):
    verb, target = m.group(1), m.group(2).strip("`'\"")
    if target.startswith("-") or target.startswith("<"):
      continue
    resource = target.split("/", 1)[0].lower()
    base, _, group = resource.partition(".")
    if group and not group.startswith("kueue.x-k8s.io"):
      continue
    if base in known or base in seen:
      continue
    seen.add(base)
    hint = ""
    if base in (
        "configuration",
        "kueueconfiguration",
        "config",
        "configurations",
    ):
      hint = (
          " KueueConfiguration is not an API resource: edit the controller"
          " ConfigMap (data.controller_manager_config.yaml) and restart the"
          " controller deployment."
      )
    elif schema.get("_schema_unavailable"):
      # Without a release schema the set of Kueue kinds is unknown; only the
      # structural KueueConfiguration mistake above can be asserted.
      continue
    problems.append(
        f"`kubectl {verb} {target}`: unknown resource {base!r}.{hint}"
    )
  return {"unknown_kubectl_resources": problems}


# Terms that, in a root-cause chunk, indicate a rejection or terminal signal
# rather than a configuration observation. Taken from Kueue's own condition
# reasons and controller messages (Workload conditions, flavorassigner / TAS /
# preemption / PodsReady messages) and from kube-scheduler / autoscaler event
# reasons.
_REJECTION_SIGNAL_RE = re.compile(
    r"insufficient (?:unused )?quota|couldn't assign flavors|doesn't allow to"
    r" fit|allows to fit only|"
    r"does not contain the requested level|supports only"
    r" TopologyAwareScheduling|unavailable in ClusterQueue|"
    r"Inadmissible|QuotaReserved=False|Admitted=False|Evicted|PodsReadyTimeout|RequeuingLimitExceeded|Deactivated|"
    r"Preempted|NotTriggerScaleUp|FailedScheduling|Unschedulable|ImagePullBackOff|CrashLoopBackOff|"
    r"strict decoding error|unknown field|failed calling"
    r" webhook|ProvisioningRequest.{0,40}(?:Failed|Expired|not"
    r" ready|Provisioned=False)|"
    r"NotReady|LocalQueue .{0,40}(?:doesn't exist|not"
    r" found|Inactive)|ClusterQueue .{0,40}Inactive|"
    r"reason=Pending|WARNING_EVENT|WORKLOAD_TERMINAL_EVENT|\bWarning\b",
    re.IGNORECASE,
)
# Observations that are not rejections by themselves.
_OBSERVATION_ONLY_RE = re.compile(
    r"nominalQuota|allocatable|ttlSecondsAfterFinished|blockAdmission|borrowingLimit|lendingLimit|weight",
    re.IGNORECASE,
)


def check_root_cause_evidence(ctx: DraftContext) -> dict[str, list[str]]:
  """Warns when an `RC<n>` chunk cites no rejection or terminal signal.

  A root cause written only from configuration observations (quota sizes, TTLs,
  limits) with no rejection fact in its chunk or in the Observations it points
  to is reported under `unsupported_root_causes`. This never fails the draft; it
  tells the author which RC still lacks a fact that ties the setting to the
  failure.

  Args:
    ctx: Draft report context and parsed sections.

  Returns:
    A dict mapping `"unsupported_root_causes"` to advisory warning strings.
  """
  rc_section = ctx.section("root cause") or ctx.section("root causes")
  if not rc_section:
    return {"unsupported_root_causes": []}
  observations = ctx.section("observations")
  ids, chunks = _chunk_by_rc(rc_section)
  unsupported: list[str] = []
  for rc_id in ids:
    chunk = chunks.get(rc_id, "")
    if _REJECTION_SIGNAL_RE.search(chunk):
      continue
    # Follow fact ids ([S12], [L3]) cited in the chunk into Observations.
    cited = re.findall(r"(?<![A-Za-z0-9-])([SL]\d{1,3})(?![0-9])", chunk)
    cited_text = " ".join(
        line
        for line in observations.splitlines()
        if any(_mentions_id(line, c) for c in cited)
    )
    if cited and _REJECTION_SIGNAL_RE.search(cited_text):
      continue
    if _OBSERVATION_ONLY_RE.search(chunk) or not cited:
      unsupported.append(
          f"{rc_id}: no rejection or terminal signal (condition reason,"
          " controller message, Warning event) is cited in this root cause"
          + (" or in the Observations it references" if cited else "")
          + "; a configuration value alone is an observation."
      )
  return {"unsupported_root_causes": unsupported}


def check_schema_warnings(ctx: DraftContext) -> dict[str, list[str]]:
  """YAML manifests under `#### Remediation` conform to the detected release's field names."""
  return {
      "schema_warnings": yaml_checks.check_remediation_yaml(
          ctx.draft_text, ctx.schema, ctx.version_info
      )
  }


REPORT_GATES: tuple[ReportGate, ...] = (
    check_headers,
    check_graph_coverage,
    check_evidence_grounding,
    check_fact_coverage,
    check_remediation_mapping,
    check_open_questions,
    check_ruled_out_reasons,
    check_config_remediation,
    check_kubectl_resources,
    check_root_cause_evidence,
    check_schema_warnings,
)


def run_report_gates(ctx: DraftContext) -> dict[str, list[Any]]:
  """Applies `REPORT_GATES` in order; each gate contributes its own report key(s)."""
  merged: dict[str, list[Any]] = {}
  for gate in REPORT_GATES:
    merged.update(gate(ctx))
  return merged
