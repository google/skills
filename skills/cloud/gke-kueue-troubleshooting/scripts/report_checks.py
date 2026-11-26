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

Sections are found by one parser (`kueue_schema_yaml_checks.split_sections`):
a `####` title is matched after normalisation, so `#### Root Causes:` is the
`root cause` section for every gate, and `#####` sub-headers stay inside their
section. All patterns that scan `kubectl` commands are linear in the input
length: flags are consumed by a bounded, unambiguous loop.
"""

from __future__ import annotations

import bisect
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

_RC_RE = re.compile(r"\bRC(\d{1,2})\b")
# An entry header at the start of a line: optional bullet / number / `#####`,
# optional bold or bracket, then the id. The bullet and its trailing blanks
# are one optional group, so no two adjacent quantifiers compete for the same
# blanks.
_ENTRY_PREFIX = r"(?m)^[ \t]*(?:(?:[-*+]|\d{1,3}\.|#{1,6})[ \t]*)?\*{0,2}\[?"
_RC_START_RE = re.compile(_ENTRY_PREFIX + r"RC(\d{1,2})\b")
# Open Questions: explicit "not determinable from this evidence" entries.
_OQ_RE = re.compile(r"\bOQ(\d{1,2})\b")
_OQ_START_RE = re.compile(_ENTRY_PREFIX + r"OQ(\d{1,2})\b")
# A further id listed right after an entry's first id (`RC1 & RC2:`,
# `RC1, RC2:`, `RC1 and RC2`): the entry belongs to each of them. The blanks
# are bounded so the pattern stays linear even when it is not anchored.
_ID_LIST_NEXT_RE = re.compile(
    r"\]?\*{0,2}[ \t]{0,4}(?:,|&|/|\+|and\b)[ \t]{0,4}\*{0,2}\[?"
    r"(RC|OQ)(\d{1,2})\b"
)
# A part label of an Open Question, at the start of a line (optionally
# bulleted / bold) or inline after a non-word character. A part's body runs
# from its label to the next label or the end of the OQ, so alternatives
# written on their own lines still belong to `Candidates:`, and `Collect:`
# ends where a conditional remediation starts. The two lookaheads name the
# characters a match can start with, so most positions are rejected by one
# test.
_OQ_PART_RE = re.compile(
    r"(?im)(?=[ \t*+bcdfr-])"
    r"(?:^[ \t]*(?:[-*+][ \t]*)?|(?<![\w*-])(?=[*bcdfr]))\*{0,2}"
    r"(basis|candidates|discriminator|collect"
    r"|(?:conditional[ \t]+)?(?:remediation|fix))"
    r"\*{0,2}[ \t]*:[ \t]*"
)
# A shell line continuation; joined before any command is scanned.
_CONTINUATION_RE = re.compile(r"\\[ \t]*\r?\n[ \t]*")
# --- kubectl command patterns -------------------------------------------------
# Tokens are separated by blanks on one line (continuations are joined first).
# `_FLAGS` consumes the flags between `kubectl`, the verb and the resource:
# a flag from `_VALUE_FLAG` takes the next token as its value, any other
# `-x` / `--x[=v]` token stands alone. The two alternatives exclude each other,
# a value is never the next `kubectl`, and the loop is bounded, so matching is
# linear and `-n workloads` or `-f workload.yaml` is never read as a resource.
_KUBECTL = r"(?<![\w.-])kubectl[ \t]+(?=\S)"
_VALUE_FLAG = (
    r"(?:-[cfklnos]|--(?:as|as-group|cluster|container|context|field-manager"
    r"|field-selector|filename|kubeconfig|kustomize|namespace|output"
    r"|patch-file|replicas|request-timeout|selector|server|subresource"
    r"|timeout|token|type|user))"
)
_FLAGS = (
    rf"(?:(?:{_VALUE_FLAG}[ \t]+(?!kubectl\b)[^\s`]+"
    rf"|(?!{_VALUE_FLAG}[ \t])-[^\s`]+)[ \t]+){{0,8}}"
)
# Verbs that write to the API server or run code in the cluster.
_KUBECTL_WRITE_RE = re.compile(
    _KUBECTL
    + _FLAGS
    + r"(?:patch|edit|apply|replace|delete|create|annotate|label|scale"
    r"|autoscale|drain|cordon|uncordon|taint|set|exec|cp|run|debug|expose"
    r"|rollout[ \t]+(?:restart|undo|pause|resume)"
    r"|kueue[ \t]+(?:stop|resume|create|delete)"
    r"|certificate[ \t]+(?:approve|deny))(?![\w-])",
    re.IGNORECASE,
)
# Non-kubectl CLI mutation rules used by `check_open_questions` (`Collect:`).
# Token-based (single-pass linear lexer) so quoted filter strings never false-
# positive and arbitrary flags/values (including `@`, quotes, combined short
# flags) are handled without regex backtracking.
_GCLOUD_READ_VERBS = frozenset({
    "read",
    "list",
    "describe",
    "get",
    "show",
    "info",
    "version",
    "help",
    "tail",
    "ls",
    "cat",
    "stat",
    "du",
    "hash",
    "search",
    "inspect",
    "lookup",
    "diagnose",
    "validate",
    "wait",
    "wait-until",
    "query",
    "stream-logs",
    "test-iam-permissions",
})
_GCLOUD_READ_PREFIXES = (
    "get-",
    "print-",
    "list-",
    "describe-",
    "show-",
    "read-",
    "view-",
    "lookup-",
    "tail-",
    "search-",
    "check-",
    "wait-",
    "query-",
    "analyze-",
    "troubleshoot-",
)
_GCLOUD_WRITE_VERBS = frozenset({
    "acknowledge",
    "activate",
    "add",
    "advance",
    "apply",
    "approve",
    "archive",
    "assign",
    "attach",
    "authorize",
    "abandon",
    "abort",
    "bind",
    "bootstrap",
    "call",
    "cancel",
    "cleanup",
    "clear",
    "clone",
    "commit",
    "copy",
    "cordon",
    "create",
    "delete",
    "deny",
    "deploy",
    "deprecate",
    "destroy",
    "detach",
    "disable",
    "drain",
    "edit",
    "enable",
    "enroll",
    "evict",
    "execute",
    "failover",
    "flush",
    "grant",
    "import",
    "init",
    "insert",
    "install",
    "invoke",
    "kill",
    "lock",
    "login",
    "migrate",
    "modify",
    "move",
    "mv",
    "patch",
    "pause",
    "perform-maintenance",
    "promote",
    "provision",
    "prune",
    "publish",
    "purge",
    "push",
    "rebalance",
    "reboot",
    "recreate",
    "register",
    "reimage",
    "reinstall",
    "reject",
    "remove",
    "rename",
    "repair",
    "replace",
    "reset",
    "resize",
    "restart",
    "restore",
    "resume",
    "revoke",
    "rm",
    "rollback",
    "rotate",
    "scale",
    "scp",
    "seal",
    "seek",
    "send",
    "set",
    "setup",
    "simulate-maintenance-event",
    "snapshot",
    "ssh",
    "start",
    "stop",
    "submit",
    "subscribe",
    "suspend",
    "switchover",
    "sync",
    "taint",
    "teardown",
    "terminate",
    "trigger",
    "unarchive",
    "unassign",
    "unbind",
    "uncordon",
    "undelete",
    "undeploy",
    "unenroll",
    "uninstall",
    "unlock",
    "unregister",
    "unseal",
    "unset",
    "unsubscribe",
    "untag",
    "update",
    "upgrade",
    "upload",
    "wipe",
    "write",
})
_GCLOUD_WRITE_PREFIXES = tuple(
    f"{v}-"
    for v in sorted(
        _GCLOUD_WRITE_VERBS
        | {"complete", "expand", "force", "mark", "perform", "simulate"}
    )
)
# Resource command groups whose names start with a write prefix (`resize-`,
# `patch-`, `restore-`, `snapshot-`, etc.) but support read-only subcommands
# like `list` / `describe`. Their subcommand (next positional token) decides
# mutability.
_GCLOUD_GROUP_NAMES = frozenset({
    "deploy-policies",
    "import-jobs",
    "patch-deployments",
    "patch-jobs",
    "resize-requests",
    "restore-channels",
    "restore-plan-bindings",
    "restore-plans",
    "restore-template-executions",
    "restore-templates",
    "restore-verification-plan-associations",
    "restore-verification-plans",
    "snapshot-groups",
    "snapshot-recycle-bin-policy",
    "snapshot-schedule-policies",
    "snapshot-settings",
    "ssh-keys",
})
_SHELL_BINS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_SIMPLE_WRAPPERS = frozenset({
    "nohup",
    "time",
    "exec",
    "command",
    "if",
    "while",
    "until",
    "do",
    "then",
    "else",
    "elif",
    "{",
    "!",
})
_SIMPLE_WRAPPER_VALUE_FLAGS = frozenset({"-a"})
_STDBUF_VALUE_FLAGS = frozenset(
    {"-i", "-o", "-e", "--input", "--output", "--error"}
)
_SSH_VALUE_FLAGS = frozenset({
    "-b",
    "-c",
    "-D",
    "-E",
    "-e",
    "-F",
    "-I",
    "-i",
    "-J",
    "-L",
    "-l",
    "-m",
    "-O",
    "-o",
    "-p",
    "-Q",
    "-R",
    "-S",
    "-W",
    "-w",
})
_GCLOUD_STORAGE_VALUE_FLAGS = frozenset({
    "--content-type",
    "--cache-control",
    "--content-disposition",
    "--content-encoding",
    "--content-language",
    "--custom-time",
    "--storage-class",
    "--predefined-acl",
    "--canned-acl",
    "--encryption-key",
    "--decryption-keys",
    "--gzip-in-flight",
    "--gzip-local",
    "--exclude",
    "--include",
    "--manifest-path",
    "--source-region",
    "-a",
    "-c",
    "-i",
    "-j",
    "-s",
    "-x",
})
_SUDO_VALUE_FLAGS = frozenset({
    "-u",
    "-g",
    "-C",
    "-D",
    "-h",
    "-p",
    "-r",
    "-t",
    "-T",
    "-U",
    "--user",
    "--group",
    "--chdir",
})
_ENV_VALUE_FLAGS = frozenset({"-u", "-C", "-S", "--unset", "--chdir"})
_TIMEOUT_VALUE_FLAGS = frozenset({"-s", "-k", "--signal", "--kill-after"})
_XARGS_WATCH_VALUE_FLAGS = frozenset(
    {"-n", "-P", "-I", "-L", "-d", "-E", "-s", "-a", "--interval"}
)
_CURL_SHORT_VALUE_FLAGS = frozenset("AbcCDeEHKmortuUwxyYz")
_GCLOUD_VALUE_FLAGS = frozenset({
    "--account",
    "--access-token-file",
    "--billing-project",
    "--cluster",
    "--configuration",
    "--filter",
    "--flags-file",
    "--flatten",
    "--format",
    "--impersonate-service-account",
    "--limit",
    "--location",
    "--page-size",
    "--project",
    "--region",
    "--sort-by",
    "--universe-domain",
    "--verbosity",
    "--zone",
})
_HELM_WRITE_VERBS = frozenset({
    "install",
    "upgrade",
    "uninstall",
    "delete",
    "del",
    "un",
    "rollback",
    "create",
    "test",
})
_HELM_VALUE_FLAGS = frozenset({
    "-n",
    "--namespace",
    "--kube-context",
    "--kubeconfig",
    "--kube-apiserver",
    "--kube-token",
    "--kube-ca-file",
    "--kube-as-user",
    "--kube-as-group",
    "--registry-config",
    "--repository-cache",
    "--repository-config",
    "--burst-limit",
    "--qps",
    "-f",
    "--values",
    "--set",
    "--set-string",
    "--set-file",
    "--version",
    "--repo",
    "--ca-file",
    "--cert-file",
    "--key-file",
    "-o",
    "--output",
})
_CURL_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CURL_ALWAYS_WRITE_FLAGS = frozenset(
    {"--json", "--upload-file", "--form", "--form-string"}
)
_CURL_DATA_FLAGS = frozenset({
    "--data",
    "--data-raw",
    "--data-binary",
    "--data-urlencode",
    "--data-ascii",
})
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
# A change to a Kueue object: a manifest whose `kind:` line names a Kueue kind,
# or a writing kubectl verb whose resource is a Kueue CRD (any plural, singular
# or short name) or the controller ConfigMap.
_KUEUE_KINDS = (
    "ClusterQueue|LocalQueue|ResourceFlavor|AdmissionCheck"
    "|ProvisioningRequestConfig|Cohort|Topology|Workload"
    "|WorkloadPriorityClass|MultiKueueCluster|MultiKueueConfig"
    "|Configuration|KueueConfiguration"
)
_KUEUE_RESOURCES = (
    r"(?:clusterqueues?|cq|localqueues?|lq|queues?|resourceflavors?|flavors?"
    r"|rf|admissionchecks?|ac|provisioningrequestconfigs?|prc|cohorts?|co"
    r"|topolog(?:y|ies)|topo|workloads?|wl|kwl|kueueworkloads?"
    r"|workloadpriorityclass(?:es)?|wpc|multikueueclusters?|mkc"
    r"|multikueueconfigs?|mkconf)"
)
_KUEUE_MUTATION_RE = re.compile(
    rf"(?:^[ \t]*[\"']?kind[\"']?:[ \t]*[\"']?(?:{_KUEUE_KINDS})\b"
    rf"|{_KUBECTL}{_FLAGS}"
    r"(?:patch|edit|apply|replace|delete|create|annotate|label"
    r"|kueue[ \t]+(?:stop|resume|create|delete))[ \t]+"
    rf"{_FLAGS}"
    rf"(?:{_KUEUE_RESOURCES}(?:\.v1[a-z0-9]*)?(?:\.kueue\.x-k8s\.io)?"
    r"(?![\w.-])"
    rf"|(?:configmaps?|cm)(?:[ \t]+{_FLAGS}|/)kueue-manager-config(?![\w-])))",
    re.IGNORECASE | re.MULTILINE,
)
_KUBECTL_RE = re.compile(
    _KUBECTL
    + _FLAGS
    + r"(get|describe|patch|edit|apply|delete|create|annotate|label|scale"
    r"|replace|rollout[ \t]+\w+|explain)[ \t]+"
    r"(?:(?:-n|--namespace)[ \t]+[^\s`]+[ \t]+)?([^\s`'\",;)]+)",
    re.IGNORECASE,
)
# What a kubectl resource argument looks like (`pods`, `deploy/name`,
# `jobsets.jobset.x-k8s.io`). Placeholders, paths, quoted JSON and shell
# syntax do not match and are not checked.
_RESOURCE_TOKEN_RE = re.compile(r"[a-z][a-z0-9.-]*(?:/[a-z0-9.-]+)?")
# Plain words that follow a kubectl verb in prose ("use kubectl describe to
# confirm"); none of them is close to a resource name.
_NOT_A_RESOURCE = frozenset(
    "a about after again also an and any are as at be because been before"
    " both but by can command commands could does each every fails first for"
    " from had has have here how if in instead is it its later manually may"
    " must next not now of on once only or output reports returns should"
    " shows so still than that the their them then there these this those to"
    " until was were what when whether which while why will with would"
    " your".split()
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
_CORE_KUBECTL_RESOURCES = frozenset(
    # workloads
    "pod pods po deployment deployments deploy replicaset replicasets rs"
    " statefulset statefulsets sts daemonset daemonsets ds job jobs cronjob"
    " cronjobs cj replicationcontroller replicationcontrollers rc"
    " controllerrevision controllerrevisions podtemplate podtemplates"
    " horizontalpodautoscaler horizontalpodautoscalers hpa"
    " verticalpodautoscaler verticalpodautoscalers vpa"
    " poddisruptionbudget poddisruptionbudgets pdb"
    # configuration, identity and access
    " configmap configmaps cm secret secrets namespace namespaces ns"
    " serviceaccount serviceaccounts sa token role roles rolebinding"
    " rolebindings clusterrole clusterroles clusterrolebinding"
    " clusterrolebindings certificatesigningrequest"
    " certificatesigningrequests csr resourcequota resourcequotas quota"
    " limitrange limitranges limits priorityclass priorityclasses pc"
    " runtimeclass runtimeclasses lease leases"
    # nodes, events and metrics
    " node nodes no event events ev componentstatus componentstatuses cs"
    " podmetrics nodemetrics"
    # networking
    " service services svc endpoints ep endpointslice endpointslices"
    " ingress ingresses ing ingressclass ingressclasses networkpolicy"
    " networkpolicies netpol"
    # storage
    " persistentvolumeclaim persistentvolumeclaims pvc persistentvolume"
    " persistentvolumes pv storageclass storageclasses sc csinode csinodes"
    " csidriver csidrivers csistoragecapacity csistoragecapacities"
    " volumeattachment volumeattachments volumeattributesclass"
    " volumeattributesclasses vac"
    # dynamic resource allocation
    " resourceclaim resourceclaims resourceclaimtemplate"
    " resourceclaimtemplates resourceslice resourceslices deviceclass"
    " deviceclasses"
    # API machinery, admission and flow control
    " customresourcedefinition customresourcedefinitions crd crds apiservice"
    " apiservices flowschema flowschemas prioritylevelconfiguration"
    " prioritylevelconfigurations mutatingwebhookconfiguration"
    " mutatingwebhookconfigurations validatingwebhookconfiguration"
    " validatingwebhookconfigurations validatingadmissionpolicy"
    " validatingadmissionpolicies validatingadmissionpolicybinding"
    " validatingadmissionpolicybindings"
    # job frameworks and operators commonly installed next to Kueue
    " jobset jobsets rayjob rayjobs raycluster rayclusters rayservice"
    " rayservices pytorchjob pytorchjobs mpijob mpijobs tfjob tfjobs"
    " xgboostjob xgboostjobs paddlejob paddlejobs jaxjob jaxjobs trainjob"
    " trainjobs sparkapplication sparkapplications leaderworkerset"
    " leaderworkersets lws appwrapper appwrappers podgroup podgroups"
    " provisioningrequest provisioningrequests provreq provreqs computeclass"
    " computeclasses nodepool nodepools nodeclaim nodeclaims certificate"
    " certificates issuer issuers clusterissuer clusterissuers"
    " servicemonitor servicemonitors podmonitor podmonitors"
    # kubectl category
    " all".split()
)
_CONFIG_KIND_RE = re.compile(r"kind:\s*KueueConfiguration\b")
# The rest-of-line scan stops at the next `kubectl`, so a line holding many
# commands is not rescanned to its end from each of them.
_CONFIG_PATCH_RE = re.compile(
    _KUBECTL
    + _FLAGS
    + r"patch[ \t]+"
    + _FLAGS
    + r"(?:configmap|cm)\b(?:(?!kubectl)[^\n])*"
    r"controller_manager_config\.yaml",
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
  headers: frozenset[tuple[int, str]] = dataclasses.field(init=False)

  def __post_init__(self) -> None:
    self.sections = split_sections(self.draft_text)
    self.headers = frozenset(
        (h.level, h.title) for h in yaml_checks.draft_headers(self.draft_text)
    )

  def section(self, title: str) -> str:
    """Body of the `####` section with this title (any accepted spelling), or empty."""
    return self.sections.get(yaml_checks.section_title(title), "")


ReportGate = Callable[[DraftContext], dict[str, list[Any]]]
# The one section parser of the validator (normalised `####` titles).
split_sections = yaml_checks.split_sections


def _normalize_for_match(text: str) -> str:
  """Collapses whitespace and strips quoting/flow-YAML punctuation so YAML/JSON formatting differences do not break substring checks."""
  text = text.replace("''", "'").replace('\\"', '"')
  text = text.replace('"', "").replace("'", "").replace("`", "")
  text = re.sub(r"[\[\]{},]", " ", text)
  text = re.sub(r"(?:^|\s)-\s+", " ", text)
  return re.sub(r"\s+", " ", text).strip().lower()


def _join_continuations(text: str) -> str:
  r"""Joins shell `\`-continued lines, so a command split over lines is scanned as one."""
  return _CONTINUATION_RE.sub(" ", text)


def _mentions_id(text: str, fact_id: str) -> bool:
  return (
      re.search(rf"(?<![A-Za-z0-9-]){re.escape(fact_id)}(?![0-9])", text)
      is not None
  )


def _first_line(text: str) -> str:
  return next((ln for ln in text.splitlines() if ln.strip()), "")


# --- Gates -------------------------------------------------------------------


def check_headers(ctx: DraftContext) -> dict[str, list[str]]:
  """All required section headers exist and no required `####` section is empty.

  Headers are matched by normalised title, the same way every other gate finds
  its section, so a spelling this gate accepts is never invisible to them. A
  required section that is present but has no content fails closed: the gates
  that read it would otherwise have nothing to check.

  Args:
    ctx: Draft report context and parsed sections.

  Returns:
    A dict mapping `"missing_headers"` to the missing or empty headers.
  """
  titles = {title for _, title in ctx.headers}
  missing: list[str] = []
  for header in REQUIRED_HEADERS:
    hashes, _, raw = header.partition(" ")
    title = yaml_checks.section_title(raw)
    if len(hashes) != 4:
      if title not in titles:
        missing.append(header)
    elif (4, title) not in ctx.headers:
      missing.append(header)
    elif not ctx.section(title).strip():
      missing.append(
          f"{header} (the section is empty: write its content, or `- none`"
          " when there is nothing to list)"
      )
  return {"missing_headers": missing}


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
  obs_section = ctx.section("observations")
  if not tool_outputs or not obs_section:
    return {"fabricated_quotes": []}
  corpus = "\n".join(tool_outputs)
  norm_corpus = _normalize_for_match(corpus)
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


def _entry_ids(
    text: str, first: re.Match[str], prefix: str
) -> tuple[list[str], int]:
  """Ids an entry header lists (`RC1 & RC2:` -> RC1, RC2) and the offset just past the list."""
  ids = [f"{prefix}{int(first.group(1))}"]
  pos = first.end()
  while True:
    m = _ID_LIST_NEXT_RE.match(text, pos)
    if m is None or m.group(1) != prefix:
      return list(dict.fromkeys(ids)), pos
    ids.append(f"{prefix}{int(m.group(2))}")
    pos = m.end()


def _chunk_by_id(
    text: str,
    start_re: re.Pattern[str],
    any_re: re.Pattern[str],
    prefix: str,
    stop_re: re.Pattern[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
  """Splits a section into per-id chunks.

  Line-start entry headers are preferred over inline cross-references. An
  entry whose header lists several ids (`- RC1 & RC2: ...`, `- RC1, RC2: ...`)
  is assigned to every one of them. A chunk ends at the next entry, or at a
  line-start entry of the other family (`stop_re`), whichever comes first.

  Args:
    text: Section body.
    start_re: Matches an id at the start of a line; group 1 is its number.
    any_re: Matches an id anywhere; used when no line starts with one.
    prefix: `RC` or `OQ`.
    stop_re: Line-start pattern that ends a chunk without starting one.

  Returns:
    `(ids in order of first appearance, {id: chunk text})`.
  """
  matches = list(start_re.finditer(text)) or list(any_re.finditer(text))
  entries: list[tuple[int, list[str]]] = []
  covered = 0
  for m in matches:
    if m.start() < covered:
      continue  # already taken as part of the previous entry's id list
    entry_ids, covered = _entry_ids(text, m, prefix)
    entries.append((m.start(), entry_ids))
  bounds = sorted(
      {start for start, _ in entries}
      | {m.start() for m in (stop_re.finditer(text) if stop_re else ())}
  )
  parts: dict[str, list[str]] = {}
  for start, entry_ids in entries:
    nxt = bisect.bisect_right(bounds, start)
    end = bounds[nxt] if nxt < len(bounds) else len(text)
    for cid in entry_ids:
      parts.setdefault(cid, []).append(text[start:end])
  return list(parts), {cid: "".join(texts) for cid, texts in parts.items()}


def _chunk_by_rc(text: str) -> tuple[list[str], dict[str, str]]:
  return _chunk_by_id(text, _RC_START_RE, _RC_RE, "RC", _OQ_START_RE)


def _chunk_by_oq(text: str) -> tuple[list[str], dict[str, str]]:
  return _chunk_by_id(text, _OQ_START_RE, _OQ_RE, "OQ", _RC_START_RE)


def _has_bullets(text: str) -> bool:
  return re.search(r"(?m)^[ \t]*[-*\d]", text) is not None


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
  if rc_is_outside and _KUEUE_MUTATION_RE.search(_join_continuations(chunk)):
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


def _oq_parts(chunk: str) -> list[tuple[str, str]]:
  """Splits one OQ entry into `(label, body)` parts in order; each body spans up to the next label.

  Every occurrence is kept, so a second `Collect:` in the same entry is a part
  of its own. Labels are lower-cased with single spaces (`conditional
  remediation`).

  Args:
    chunk: Text of one `OQ<n>` entry.

  Returns:
    The labelled parts of the entry.
  """
  matches = list(_OQ_PART_RE.finditer(chunk))
  parts: list[tuple[str, str]] = []
  for i, m in enumerate(matches):
    end = matches[i + 1].start() if i + 1 < len(matches) else len(chunk)
    label = " ".join(m.group(1).lower().split())
    parts.append((label, chunk[m.end() : end].strip()))
  return parts


def _flush_token(
    seg: list[tuple[str, bool]], tok: list[str], tok_quoted: bool
) -> bool:
  """Appends the buffered token to `seg` and clears `tok`; returns reset quoted flag."""
  if tok or tok_quoted:
    seg.append(("".join(tok), tok_quoted))
    tok.clear()
  return False


def _last_closing_sq(line: str) -> int:
  """Rightmost single quote in `line` that is not an internal word apostrophe."""
  n = len(line)
  for j in range(n - 1, -1, -1):
    if line[j] != "'":
      continue
    if j > 0 and j + 1 < n and line[j - 1].isalnum() and line[j + 1].isalnum():
      continue
    return j
  return -1


def _lex_shell_line(line: str, segments: list[list[tuple[str, bool]]]) -> None:
  """Splits one line into `(token, was_quoted)` command segments in O(len(line))."""
  last_sq = _last_closing_sq(line)
  last_dq = line.rfind('"')
  seg: list[tuple[str, bool]] = []
  tok: list[str] = []
  tok_quoted = False
  quote = ""
  i, n = 0, len(line)
  while i < n:
    ch = line[i]
    if quote:
      if ch == "\\" and quote == '"' and i + 1 < n:
        tok.append(line[i + 1])
        i += 2
        continue
      if ch == quote:
        quote = ""
      else:
        tok.append(ch)
      i += 1
      continue
    if (
        ch == "'" and i < last_sq and not (i > 0 and line[i - 1].isalnum())
    ) or (ch == '"' and i < last_dq):
      quote = ch
      tok_quoted = True
      i += 1
      continue
    if ch == "\\" and i + 1 < n:
      tok.append(line[i + 1])
      i += 2
      continue
    if ch in (";", "|", "&", "`", "(", ")"):
      tok_quoted = _flush_token(seg, tok, tok_quoted)
      if seg:
        segments.append(seg)
        seg = []
      i += 1
      continue
    if ch in (" ", "\t", "\r"):
      tok_quoted = _flush_token(seg, tok, tok_quoted)
      i += 1
      continue
    tok.append(ch)
    i += 1
  _flush_token(seg, tok, tok_quoted)
  if seg:
    segments.append(seg)


def _iter_shell_segments(text: str) -> list[list[tuple[str, bool]]]:
  """Splits shell text into command segments of `(token, was_quoted)` pairs."""
  segments: list[list[tuple[str, bool]]] = []
  for line in text.splitlines():
    _lex_shell_line(line, segments)
  return segments


def _skip_flags(
    seg: list[tuple[str, bool]], idx: int, value_flags: frozenset[str]
) -> int:
  """Advances `idx` past leading flags (and their values for `value_flags`)."""
  while idx < len(seg):
    tok = seg[idx][0]
    if tok == "--":
      return idx + 1
    if not tok.startswith("-"):
      return idx
    low = tok.lower()
    idx += 2 if ("=" not in low and low in value_flags) else 1
  return idx


def _is_env_assignment(tok: str, quoted: bool) -> bool:
  """True for unquoted shell env assignments like `FOO=bar`."""
  if quoted or "=" not in tok or tok.startswith("-"):
    return False
  name = tok.split("=", 1)[0]
  return bool(name) and name.replace("_", "").isalnum()


def _find_exec_start(seg: list[tuple[str, bool]], start: int) -> int:
  """Returns the token index after `-exec`/`-execdir` in a `find` segment, or len(seg)."""
  for j in range(start, len(seg)):
    if seg[j][0] in ("-exec", "-execdir") and j + 1 < len(seg):
      return j + 1
  return len(seg)


def _build_next_exec(seg: list[tuple[str, bool]]) -> list[int]:
  """For each index `k`, returns the index after the next `-exec`/`-execdir`."""
  n = len(seg)
  nxt = [n] * (n + 1)
  pos = n
  for i in range(n - 1, -1, -1):
    if seg[i][0] in ("-exec", "-execdir") and i + 1 < n:
      pos = i + 1
    nxt[i] = pos
  return nxt


def _step_shell_wrapper(
    seg: list[tuple[str, bool]], i: int, next_exec: list[int] | None
) -> int:
  """Advances `i` past one env assignment or shell wrapper, or returns `i`."""
  tok, quoted = seg[i]
  if _is_env_assignment(tok, quoted):
    return i + 1
  if tok.startswith("-"):
    return i
  base = os.path.basename(tok).lower()
  if base in _SIMPLE_WRAPPERS:
    return _skip_flags(seg, i + 1, _SIMPLE_WRAPPER_VALUE_FLAGS)
  if base == "sudo":
    return _skip_flags(seg, i + 1, _SUDO_VALUE_FLAGS)
  if base == "env":
    return _skip_flags(seg, i + 1, _ENV_VALUE_FLAGS)
  if base in ("timeout", "ssh"):
    flags = _TIMEOUT_VALUE_FLAGS if base == "timeout" else _SSH_VALUE_FLAGS
    j = _skip_flags(seg, i + 1, flags)
    return j + 1 if j < len(seg) else j
  if base == "stdbuf":
    return _skip_flags(seg, i + 1, _STDBUF_VALUE_FLAGS)
  if base == "nice":
    return _skip_flags(seg, i + 1, frozenset({"-n", "--adjustment"}))
  if base in ("xargs", "watch"):
    return _skip_flags(seg, i + 1, _XARGS_WATCH_VALUE_FLAGS)
  if base == "find":
    if next_exec is not None:
      return next_exec[i + 1] if i + 1 < len(next_exec) else len(seg)
    return _find_exec_start(seg, i + 1)
  return i


def _strip_shell_wrappers(
    seg: list[tuple[str, bool]],
    start: int = 0,
    memo: dict[int, int] | None = None,
    next_exec: list[int] | None = None,
) -> int:
  """Returns the command-token index after leading env vars and shell wrappers."""
  i = start
  visited: list[int] = []
  while i < len(seg):
    if memo is not None and i in memo:
      i = memo[i]
      break
    nxt = _step_shell_wrapper(seg, i, next_exec)
    if nxt == i:
      break
    if memo is not None:
      visited.append(i)
    i = nxt
  if memo is not None:
    for v in visited:
      memo[v] = i
  return i


def _shell_c_script(seg: list[tuple[str, bool]], start: int) -> str:
  """Returns the `-c` script argument for a `sh`/`bash` call, or empty string."""
  i = start
  while i < len(seg):
    tok = seg[i][0]
    if tok == "--":
      return ""
    if tok in ("-o", "+o"):
      i += 2
      continue
    if tok == "-c" or (
        tok.startswith("-")
        and not tok.startswith("--")
        and len(tok) > 1
        and tok.endswith("c")
    ):
      return seg[i + 1][0] if i + 1 < len(seg) else ""
    if not tok.startswith("-"):
      return ""
    i += 1
  return ""


def _is_gcs_upload_cp(seg: list[tuple[str, bool]], start: int) -> bool:
  """True when `gcloud storage cp`/`rsync` writes to a `gs://` destination."""
  val_flags = _GCLOUD_VALUE_FLAGS | _GCLOUD_STORAGE_VALUE_FLAGS
  dest = ""
  i = start
  while i < len(seg):
    tok = seg[i][0]
    low = tok.lower()
    if low.startswith("-"):
      i += 2 if ("=" not in low and low in val_flags) else 1
      continue
    if tok not in (";", "+"):
      dest = tok
    i += 1
  return dest.lower().startswith("gs://")


def _is_mutating_gcloud(seg: list[tuple[str, bool]], start: int) -> bool:
  """True when a `gcloud` command reaches a write verb before any read verb."""
  i = start
  pos = 0
  first_pos = ""
  prev_pos = ""
  while i < len(seg) and pos < 10:
    low = seg[i][0].lower()
    if low.startswith("-"):
      i += 2 if ("=" not in low and low in _GCLOUD_VALUE_FLAGS) else 1
      continue
    pos += 1
    if pos == 1:
      first_pos = low
    if low == "deploy" and (
        pos == 1
        or (pos == 2 and first_pos in ("alpha", "beta"))
        or prev_pos == "fleet"
    ):
      prev_pos = low
      i += 1
      continue
    if low == "run" and (
        pos == 1 or (pos == 2 and first_pos in ("alpha", "beta"))
    ):
      prev_pos = low
      i += 1
      continue
    if low in _GCLOUD_GROUP_NAMES:
      prev_pos = low
      i += 1
      continue
    if low in ("cp", "rsync") and pos <= 3:
      return _is_gcs_upload_cp(seg, i + 1)
    if low in _GCLOUD_READ_VERBS or low.startswith(_GCLOUD_READ_PREFIXES):
      return False
    if (
        low == "run"
        or low in _GCLOUD_WRITE_VERBS
        or low.startswith(_GCLOUD_WRITE_PREFIXES)
    ):
      return True
    prev_pos = low
    i += 1
  return False


def _is_mutating_helm(seg: list[tuple[str, bool]], start: int) -> bool:
  """True when a `helm` command's first positional verb mutates or runs pods."""
  i = start
  while i < len(seg):
    low = seg[i][0].lower()
    if low.startswith("-"):
      i += 2 if ("=" not in low and low in _HELM_VALUE_FLAGS) else 1
      continue
    return low in _HELM_WRITE_VERBS
  return False


def _scan_curl_short_flags(
    chars: str, seg: list[tuple[str, bool]], idx: int
) -> tuple[bool, str, bool, bool, int]:
  """Parses a bundled short-flag token like `-sG` or `-sXDELETE`."""
  has_get = False
  method = ""
  always_write = False
  has_data = False
  step = 1
  for pos, ch in enumerate(chars):
    rest = chars[pos + 1 :]
    if ch == "G":
      has_get = True
    elif ch == "X":
      if rest:
        method = rest.upper()
      elif idx + 1 < len(seg):
        method = seg[idx + 1][0].upper()
        step = 2
      break
    elif ch == "d":
      has_data = True
      if not rest and idx + 1 < len(seg):
        step = 2
      break
    elif ch in ("F", "T"):
      always_write = True
      if not rest and idx + 1 < len(seg):
        step = 2
      break
    elif ch in _CURL_SHORT_VALUE_FLAGS:
      if not rest and idx + 1 < len(seg):
        step = 2
      break
  return has_get, method, always_write, has_data, step


def _is_mutating_curl(seg: list[tuple[str, bool]], start: int) -> bool:
  """True when a `curl` command sends a write method or body without `-G`/`--get`."""
  has_get = False
  method = ""
  always_write = False
  has_data = False
  i = start
  while i < len(seg):
    tok = seg[i][0]
    low = tok.lower()
    if low == "--get":
      has_get = True
      i += 1
    elif low == "--request" and i + 1 < len(seg):
      method = seg[i + 1][0].upper()
      i += 2
    elif low.startswith("--request="):
      method = tok.split("=", 1)[1].upper()
      i += 1
    elif low.split("=", 1)[0] in _CURL_ALWAYS_WRITE_FLAGS:
      always_write = True
      i += 2 if ("=" not in low and i + 1 < len(seg)) else 1
    elif low.split("=", 1)[0] in _CURL_DATA_FLAGS:
      has_data = True
      i += 2 if ("=" not in low and i + 1 < len(seg)) else 1
    elif tok.startswith("-") and not tok.startswith("--") and len(tok) > 1:
      g, m, aw, d, step = _scan_curl_short_flags(tok[1:], seg, i)
      has_get = has_get or g
      if m:
        method = m
      always_write = always_write or aw
      has_data = has_data or d
      i += step
    else:
      i += 1
  if method in _CURL_WRITE_METHODS or always_write:
    return True
  return has_data and not has_get and method not in ("GET", "HEAD")


_NON_KUBECTL_HINTS = ("gcloud", "helm", "curl", "sh", "eval")
_TRACKED_CMDS = frozenset({"gcloud", "helm", "curl", "eval"}) | _SHELL_BINS
_QUOTED_CMD_HEADS = _TRACKED_CMDS | frozenset({"sudo", "env", "timeout"})
_QUOTED_FILTER_PREVS = frozenset(
    {"read", "--filter", "-e", "--regexp", "grep", "rg"}
)
_TEXT_FILTER_CMDS = frozenset({
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "ag",
    "awk",
    "gawk",
    "sed",
    "jq",
    "yq",
})
_PROSE_CMD_LEADINS = frozenset({
    "run",
    "running",
    "execute",
    "executing",
    "invoke",
    "invoking",
    "use",
    "then",
})
_ORDINAL_LEADINS = frozenset({
    "first",
    "second",
    "third",
    "next",
    "finally",
    "lastly",
})
_LEADING_LIST_MARKERS = frozenset({"-", "*", "+", "$", "#", ">", "%", "•"})
_LEADIN_CMD_HEADS = _TRACKED_CMDS | _TEXT_FILTER_CMDS


def _is_prose_leadin(
    seg: list[tuple[str, bool]], j: int, start: int, allow_comma: bool = False
) -> bool:
  """True for unquoted command/step introducers (`Run`, `First,`, `Step 1:`)."""
  tok, quoted = seg[j]
  if quoted or not tok:
    return False
  if allow_comma and tok.endswith(","):
    return True
  bare = tok.rstrip(":,").lower()
  if bare in _PROSE_CMD_LEADINS:
    return True
  if bare in _ORDINAL_LEADINS and (j == start or tok[-1] in (":", ",")):
    return True
  return (
      j > 0
      and not seg[j - 1][1]
      and seg[j - 1][0].lower() == "step"
      and tok.rstrip(":.)").isdigit()
  )


def _strip_leading_markers(seg: list[tuple[str, bool]]) -> int:
  """Skips leading list bullets (`-`, `*`, `•`, `1.`, `a.`) and shell prompts."""
  i = 0
  while i < len(seg) and not seg[i][1]:
    tok = seg[i][0]
    if (
        tok in _LEADING_LIST_MARKERS
        or (len(tok) >= 2 and tok[-1] in (".", ")") and tok[:-1].isdigit())
        or (len(tok) == 2 and tok[0].isalpha() and tok[1] in (".", ")"))
    ):
      i += 1
      continue
    break
  return i


def _prose_leadin_slices(
    seg: list[tuple[str, bool]], start: int, allow_comma: bool = False
) -> list[tuple[int, int]]:
  """Returns disjoint `(cmd_idx, end)` slices after prose lead-ins in O(len(seg))."""
  has_find = any(
      not q and os.path.basename(t).lower() == "find" for t, q in seg[start:]
  )
  next_exec = _build_next_exec(seg) if has_find else None
  memo: dict[int, int] = {}
  hits: list[tuple[int, int]] = []
  j = start
  while j + 1 < len(seg):
    if _is_prose_leadin(seg, j, start, allow_comma=allow_comma):
      cmd_idx = _strip_shell_wrappers(seg, j + 1, memo, next_exec)
      if cmd_idx < len(seg) and not seg[cmd_idx][0].startswith("-"):
        if os.path.basename(seg[cmd_idx][0]).lower() in _LEADIN_CMD_HEADS:
          hits.append((j, cmd_idx))
          j = cmd_idx + 1
          continue
    j += 1
  return [
      (cmd_idx, hits[k + 1][0] if k + 1 < len(hits) else len(seg))
      for k, (_, cmd_idx) in enumerate(hits)
  ]


def _scan_chained_cli_cmds(
    seg: list[tuple[str, bool]], start: int, depth: int
) -> bool:
  """Checks unquoted chained commands following a read-only CLI in one segment."""
  for cmd_idx, end in _prose_leadin_slices(seg, start, allow_comma=True):
    mut, _ = _segment_cmd_is_mutating(seg[cmd_idx:end], 0, depth)
    if mut:
      return True
  return False


def _scan_segment_prose_and_quotes(
    seg: list[tuple[str, bool]], start: int, depth: int
) -> bool:
  """Scans prose-introduced commands and quoted command tokens in one segment."""
  covered: list[tuple[int, int]] = []
  for cmd_idx, end in _prose_leadin_slices(seg, start):
    mut, skip_quoted = _segment_cmd_is_mutating(seg[cmd_idx:end], 0, depth)
    if mut:
      return True
    if skip_quoted:
      covered.append((cmd_idx, end))
  if depth >= 2:
    return False
  cov_i = 0
  for qidx, (tok, quoted) in enumerate(seg):
    while cov_i < len(covered) and qidx >= covered[cov_i][1]:
      cov_i += 1
    if cov_i < len(covered) and covered[cov_i][0] <= qidx < covered[cov_i][1]:
      continue
    if quoted and any(c.isspace() for c in tok):
      prev_low = seg[qidx - 1][0].lower() if qidx > 0 else ""
      if _quoted_cmd_is_mutating(tok, prev_low, depth):
        return True
  return False


def _quoted_cmd_is_mutating(tok: str, prev_low: str, depth: int) -> bool:
  """True when a quoted multi-word token holds a mutating command."""
  if depth >= 2 or prev_low in _QUOTED_FILTER_PREVS:
    return False
  parts = tok.lstrip().split(None, 1)
  if len(parts) < 2:
    return False
  if prev_low != "eval":
    if parts[0].startswith("-"):
      return False
    if os.path.basename(parts[0]).lower() not in _QUOTED_CMD_HEADS:
      return False
  return _has_mutating_non_kubectl_cmd(tok, depth + 1)


def _segment_cmd_is_mutating(
    seg: list[tuple[str, bool]], idx: int, depth: int
) -> tuple[bool, bool]:
  """Returns `(is_mutating, skip_quoted_scan)` for the command starting at `seg[idx]`."""
  if idx >= len(seg):
    return False, False
  tok = seg[idx][0]
  if tok.startswith("-"):
    return False, False
  cmd = os.path.basename(tok).lower()
  if cmd in _TEXT_FILTER_CMDS:
    return False, True
  if cmd == "gcloud":
    return _is_mutating_gcloud(seg, idx + 1), True
  if cmd == "helm":
    return _is_mutating_helm(seg, idx + 1), True
  if cmd == "curl":
    return _is_mutating_curl(seg, idx + 1), True
  if depth < 2 and cmd in _SHELL_BINS:
    script = _shell_c_script(seg, idx + 1)
    return (
        bool(script and _has_mutating_non_kubectl_cmd(script, depth + 1)),
        True,
    )
  if depth < 2 and cmd == "eval":
    joined = " ".join(t for t, _ in seg[idx + 1 :])
    return (
        bool(joined and _has_mutating_non_kubectl_cmd(joined, depth + 1)),
        True,
    )
  return False, False


def _has_mutating_non_kubectl_cmd(text: str, depth: int = 0) -> bool:
  """Checks command-position segments, prose lead-ins, and quoted commands."""
  low_text = text.lower()
  if not any(h in low_text for h in _NON_KUBECTL_HINTS):
    return False
  for seg in _iter_shell_segments(text):
    start = _strip_leading_markers(seg)
    idx = _strip_shell_wrappers(seg, start)
    mut, is_known_cli = _segment_cmd_is_mutating(seg, idx, depth)
    if mut:
      return True
    if is_known_cli:
      cmd = os.path.basename(seg[idx][0]).lower() if idx < len(seg) else ""
      if cmd not in _TEXT_FILTER_CMDS and _scan_chained_cli_cmds(
          seg, idx + 1, depth
      ):
        return True
      continue
    if _scan_segment_prose_and_quotes(seg, idx, depth):
      return True
  return False


def _is_mutating(text: str) -> bool:
  """True when `text` holds a writing CLI command (`kubectl`/`gcloud`/`helm`/`curl`) or Kueue manifest."""
  joined = _join_continuations(text)
  return bool(
      _KUBECTL_WRITE_RE.search(joined)
      or _KUEUE_MUTATION_RE.search(joined)
      or _has_mutating_non_kubectl_cmd(joined)
  )


def check_open_questions(ctx: DraftContext) -> dict[str, list[str]]:
  """Streamlined Open Questions check: rejects mutating commands inside any `Collect:` part.

  Every `Collect:` part of an entry is checked, whether its label starts a line
  or sits inline. A conditional remediation written after `Collect:` under its
  own label (`Conditional remediation:`, `Remediation:`, `Fix:`) is a separate
  part and may carry a writing command.

  Args:
    ctx: Draft report context and parsed sections.

  Returns:
    A dict mapping `"open_question_gaps"` to one message per offending OQ.
  """
  text = ctx.section("open questions")
  oq_ids, chunks = _chunk_by_oq(text)
  gaps: list[str] = []
  for oq in oq_ids:
    if any(
        label == "collect" and _is_mutating(body)
        for label, body in _oq_parts(chunks.get(oq, ""))
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
  rem = _join_continuations(ctx.section("remediation"))
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


def _kubectl_resource(target: str) -> str:
  r"""The resource part of a kubectl argument, lower-cased, or "" when not a resource.

  `deployment/name` -> `deployment`, `pods|grep` -> `pods`. Flags, `<name>`
  placeholders, file paths, a bare `\` and plain English words that follow a
  verb in prose yield "", and are not checked against the known kinds.

  Args:
    target: The token after the kubectl verb.

  Returns:
    The resource name (possibly group-qualified), or "".
  """
  token = re.split(r"[|>&]", target.strip("`'\""), maxsplit=1)[0].lower()
  if not _RESOURCE_TOKEN_RE.fullmatch(token) or token in _NOT_A_RESOURCE:
    return ""
  return token.split("/", 1)[0]


def check_kubectl_resources(ctx: DraftContext) -> dict[str, list[str]]:
  """kubectl commands whose resource argument is not a known kind."""
  schema = ctx.schema
  known = _known_kubectl_resources(schema)
  problems: list[str] = []
  seen: set[str] = set()
  remediation = _join_continuations(ctx.section("remediation"))
  for m in _KUBECTL_RE.finditer(remediation):
    verb, target = m.group(1), m.group(2).strip("`'\"")
    resource = _kubectl_resource(target)
    if not resource:
      continue
    base, _, group = resource.partition(".")
    if (
        group
        and group != "kueue.x-k8s.io"
        and not group.endswith(".kueue.x-k8s.io")
    ):
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
    # First letters of the alternatives below: one cheap test per position
    # before the alternation is tried (keep in sync when adding a term).
    r"(?=[acdefilnpqrsuw])(?:"
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
    r"reason=Pending|WARNING_EVENT|WORKLOAD_TERMINAL_EVENT|\bWarning\b)",
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
  rc_section = ctx.section("root cause")
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
