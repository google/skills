#!/usr/bin/env python3
"""Diagnostic report verifier for the `gke-kueue-troubleshooting` skill.

Audits a draft '### Diagnostic Summary' against the coverage ledger written by
`snapshot.py` / `trace_logs.py` and the schema of the detected Kueue release
(`kueue_schema.py`):
  1. All required sections exist and are not empty (`### Diagnostic Summary`,
     `#### Scope`, `#### Observations`, `#### Root Cause`, `#### Ruled Out`,
     `#### Remediation`). Titles are matched after normalisation (case, a
     trailing `:`, singular/plural), by the same parser every gate uses.
  2. All referenced Kueue graph objects (`Cohort`, `ClusterQueue`,
     `ResourceFlavor`, `AdmissionCheck`) were inspected or named.
  3. Quoted evidence in `#### Observations` matches actual tool outputs (zero
     fabricated quotes).
  4. Root causes are numbered `RC1`, `RC2`, ... and every one has a matching
     remediation entry that links the official documentation describing the fix
     (and includes that link whenever a `kubectl` command or YAML manifest is
     given), or states an external action and confirmation signal
     (`remediation_gaps`).
     A report with no RC must open at least one `OQ<n>` under `#### Open
     Questions`.
  5. Open Questions (`OQ<n>`) keep read-only commands in every `Collect:` part
     (`open_question_gaps`); a conditional fix under its own
     `Conditional remediation:` / `Fix:` label is not part of `Collect:`.
  6. Controller configuration remediations use `kind: Configuration` and avoid
     partial `kubectl patch` of `controller_manager_config.yaml`
     (`config_remediation_errors`).
  7. `kubectl` commands in `#### Remediation` target resource kinds that exist
     (`unknown_kubectl_resources`).
  8. YAML manifests in `#### Remediation` conform to the detected API version's
     field names (`schema_warnings`).
  9. Advisory only (does not fail `passed`): root causes without a rejection or
     terminal signal in `#### Observations` (`unsupported_root_causes`).

All checks are structural: the validator never judges whether a conclusion is
right, only whether the report is complete, traceable and executable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

# pylint: disable=g-import-not-at-top,wrong-import-position
import kueue_schema
import report_checks
import report_output

# pylint: enable=g-import-not-at-top,wrong-import-position

_LEDGER_MISSING_NOTE = (
    "No tool outputs found in the coverage ledger; quote verification was"
    " skipped. Pass the same --ledger-path to snapshot.py / trace_logs.py and"
    " to this validator."
)
_UNADDRESSED_FACTS_HINT = (
    "Each listed id must appear under `#### Root Cause` (as evidence of an RC),"
    " under `#### Open Questions` (as a fact the question is about) or under"
    " `#### Ruled Out` with a one-line reason why it does not block the"
    " workload. Ids may be grouped (e.g. `- S4: concerns ClusterQueue team-b,"
    " which is not in this workload's chain`)."
)
_OPEN_QUESTION_HINT = (
    "An OQ<n> is a claim that the evidence cannot decide something — it must be"
    " as rigorous as an RC: `- OQ1 (S7, L2): <what cannot be decided>` followed"
    " by indented `Basis: missing data | indistinguishable hypotheses | owner"
    " intent — <specifics>`, `Candidates: (a) ... (b) ...`, `Discriminator:"
    " <observation that decides>`, `Collect: <read-only commands / data /"
    " question to the owner>`. `Collect:` holds read-only commands only: put"
    " a fix that depends on the answer with its candidate, or on its own"
    " `Conditional remediation:` line."
)
_WEAK_RULED_OUT_HINT = (
    "A Ruled Out bullet must state why the fact cannot be blocking this"
    " workload: name the object it concerns and why that object is outside the"
    " workload's chain, or quote the later fact (with timestamp) showing the"
    " condition cleared. Labels such as 'transient' or 'noise' are not reasons."
    " If the fact describes a stage of this workload's own admission pipeline,"
    " it is evidence for a root cause, not something to rule out."
)
# Report keys in output order; every one is produced by exactly one gate in
# `REPORT_GATES`.
_GATE_KEYS = (
    "missing_headers",
    "uninspected_graph_objects",
    "fabricated_quotes",
    "unaddressed_facts",
    "remediation_gaps",
    "open_question_gaps",
    "weak_ruled_out",
    "config_remediation_errors",
    "unknown_kubectl_resources",
    "schema_warnings",
)


def _resolve_version_info(
    ledger_vinfo: dict[str, Any] | None,
    explicit_release_version: str,
    explicit_api_version: str,
) -> dict[str, Any]:
  """The ledger's detected version unless an override is given or the ledger has none."""
  if ledger_vinfo and not explicit_release_version and not explicit_api_version:
    return ledger_vinfo
  return kueue_schema.detect_target_kueue_version(
      mode=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_MODE",
          "KUEUE_DIAGNOSE_MODE",
          "offline_data",
      ),
      explicit_release_version=explicit_release_version
      or (ledger_vinfo or {}).get("release_version", ""),
      explicit_api_version=explicit_api_version
      or (ledger_vinfo or {}).get("api_version", ""),
  )


def _build_report(
    ctx: report_checks.DraftContext, findings: dict[str, list[Any]]
) -> dict[str, Any]:
  """Assembles the validator's JSON report from the merged gate findings."""
  referenced = ctx.ledger.referenced
  uninspected = findings["uninspected_graph_objects"]
  ledger_missing = not ctx.ledger.tool_outputs
  coverage_pct = (
      round(100.0 * (len(referenced) - len(uninspected)) / len(referenced), 1)
      if referenced
      else 100.0
  )
  passed = not ledger_missing and not any(findings[key] for key in _GATE_KEYS)
  report: dict[str, Any] = {
      "passed": passed,
      "ledger_missing": ledger_missing,
      "ledger_note": _LEDGER_MISSING_NOTE if ledger_missing else "",
      "detected_kueue_version": ctx.version_info,
  }
  report.update({key: findings[key] for key in _GATE_KEYS})
  # Advisory only (never affects `passed`): root causes that cite no
  # rejection/terminal signal.
  report["unsupported_root_causes"] = findings.get(
      "unsupported_root_causes", []
  )
  if report["unsupported_root_causes"]:
    report["unsupported_root_causes_hint"] = (
        "Advisory: tie each listed RC to a rejection or terminal fact (Workload"
        " condition reason, controller message, Warning event) in ####"
        " Observations, or move it to Open Questions; a quota, TTL or limit"
        " value by itself is an observation."
    )
  report["graph_coverage_pct"] = coverage_pct
  if ctx.schema.get("_schema_unavailable"):
    report["schema_notice"] = ctx.schema.get("_schema_notice", "")
  if findings["unaddressed_facts"]:
    report["unaddressed_facts_hint"] = _UNADDRESSED_FACTS_HINT
  if findings["open_question_gaps"]:
    report["open_question_hint"] = _OPEN_QUESTION_HINT
  if findings["weak_ruled_out"]:
    report["weak_ruled_out_hint"] = _WEAK_RULED_OUT_HINT
  return report


def audit_draft(
    draft_text: str,
    ledger_path: str | None,
    explicit_release_version: str = "",
    explicit_api_version: str = "",
) -> dict[str, Any]:
  """Runs deterministic verification and version-exact Kueue schema checks on a diagnostic report."""
  ledger = report_checks.LedgerData.load(ledger_path)
  vinfo = _resolve_version_info(
      ledger.detected_kueue_version,
      explicit_release_version,
      explicit_api_version,
  )
  schema, _ = kueue_schema.load_schema_for_version(version_info=vinfo)
  ctx = report_checks.DraftContext(
      draft_text=draft_text, ledger=ledger, version_info=vinfo, schema=schema
  )
  return _build_report(ctx, report_checks.run_report_gates(ctx))


def main() -> int:
  parser = argparse.ArgumentParser(
      description=(
          "Validate a draft Kueue diagnostic summary against the coverage"
          " ledger and target Kueue version schema."
      )
  )
  parser.add_argument(
      "--draft-file", required=True, help="Path to draft markdown file"
  )
  report_output.add_ledger_path_argument(parser, "Path to coverage_ledger.json")
  report_output.add_kueue_version_arguments(parser)
  report_output.add_no_remote_schema_argument(parser)
  args = parser.parse_args()
  report_output.apply_no_remote_schema(args)

  if not os.path.exists(args.draft_file):
    sys.stderr.write(f"Draft file not found: {args.draft_file}\n")
    return 1

  with open(args.draft_file, "r", encoding="utf-8") as f:
    draft_text = f.read()

  report = audit_draft(
      draft_text,
      args.ledger_path,
      explicit_release_version=args.kueue_version,
      explicit_api_version=args.api_version,
  )
  print(json.dumps(report, indent=2))
  return 0 if report["passed"] else 2


if __name__ == "__main__":
  sys.exit(main())
