#!/usr/bin/env python3
"""Print summary metrics and per-case scores from an Agent Platform Eval result.

Use after ``client.evals.evaluate(...)`` returns to read scores. The field
paths (``summary_metrics``, ``eval_case_results[].response_candidate_results``)
are deep and easy to get wrong; this helper renders the standard view.

Two input shapes are accepted:

1.  A JSON file produced by ``result.model_dump_json()`` (preferred — save
    the result to disk so it can be diffed later with ``compare_results.py``).
2.  An in-process result object, when imported as a library:

      from inspect_results import render
      render(result)

Usage:
  python inspect_results.py --result result.json
  python inspect_results.py --result result.json --failing-only
  python inspect_results.py --result result.json --metric multi_turn_task_success
  python inspect_results.py --result result.json --save-html report.html


Exit codes: 0 = at least one case present, 1 = empty / malformed result.
"""

import argparse
import json
import sys
from typing import Any


def _summary_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
  """Extract summary metric rows from a serialized result."""
  rows = []
  for s in result.get("summary_metrics") or []:
    rows.append({
        "metric_name": s.get("metric_name") or s.get("metricName"),
        "mean_score": s.get("mean_score") or s.get("meanScore"),
        "pass_rate": s.get("pass_rate") or s.get("passRate"),
        "num_cases": s.get("num_cases") or s.get("numCases"),
    })
  return rows


def _case_rows(
    result: dict[str, Any],
    metric_filter: str | None,
    failing_only: bool,
) -> list[dict[str, Any]]:
  """Extract per-case metric rows from a serialized result."""
  rows = []
  for case in result.get("eval_case_results") or []:
    case_id = case.get("eval_case_id") or case.get("evalCaseId") or "?"
    for cand in case.get("response_candidate_results") or []:
      metric_results = cand.get("metric_results") or {}
      for name, r in metric_results.items():
        if metric_filter and name != metric_filter:
          continue
        score = r.get("score") if isinstance(r, dict) else None
        if failing_only and score is not None and score >= 1.0:
          continue
        rows.append({
            "case_id": case_id,
            "metric_name": name,
            "score": score,
            "explanation": (
                (r.get("explanation") or "")[:200]
                if isinstance(r, dict)
                else ""
            ),
        })
  return rows


def _format_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
  """Render rows as a fixed-width text table."""
  if not rows:
    return "(no rows)\n"
  widths = {
      c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols
  }
  header = "  ".join(c.ljust(widths[c]) for c in cols)
  sep = "  ".join("-" * widths[c] for c in cols)
  body = "\n".join(
      "  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols) for r in rows
  )
  return f"{header}\n{sep}\n{body}\n"


def render(
    result: dict[str, Any] | Any,
    metric_filter: str | None = None,
    failing_only: bool = False,
) -> str:
  """Render summary and per-case tables. Accepts dict or SDK result object."""
  if not isinstance(result, dict):
    if hasattr(result, "model_dump"):
      result = result.model_dump()
    else:
      result = json.loads(json.dumps(result, default=lambda o: o.__dict__))

  out = []
  out.append("=== Summary Metrics ===")
  out.append(
      _format_table(
          _summary_rows(result),
          ["metric_name", "mean_score", "pass_rate", "num_cases"],
      )
  )
  out.append("=== Per-Case Scores ===")
  if failing_only:
    out.append("(failing cases only, score < 1.0)")
  if metric_filter:
    out.append(f"(filtered to metric: {metric_filter})")
  out.append(
      _format_table(
          _case_rows(result, metric_filter, failing_only),
          ["case_id", "metric_name", "score", "explanation"],
      )
  )
  return "\n".join(out)


def main():
  parser = argparse.ArgumentParser(
      description=(
          "Print summary metrics and per-case scores from an Agent"
          " Platform Eval result JSON file."
      )
  )
  parser.add_argument(
      "--result",
      "-r",
      required=True,
      help="Path to a JSON file produced by result.model_dump_json().",
  )
  parser.add_argument(
      "--metric",
      "-m",
      help="Only show per-case scores for this metric name.",
  )
  parser.add_argument(
      "--failing-only",
      action="store_true",
      help="Only show per-case scores with score < 1.0.",
  )
  parser.add_argument(
      "--save-html",
      "-o",
      dest="html_path",
      help="Also render the result as a browsable HTML report to this path.",
  )
  args = parser.parse_args()

  try:
    with open(args.result) as f:
      result = json.load(f)
  except FileNotFoundError:
    print(f"ERROR: File not found: {args.result}", file=sys.stderr)
    sys.exit(1)
  except json.JSONDecodeError as e:
    print(f"ERROR: Invalid JSON in {args.result}: {e}", file=sys.stderr)
    sys.exit(1)

  if not result.get("summary_metrics") and not result.get("eval_case_results"):
    print(
        "ERROR: result has no summary_metrics or eval_case_results."
        " Did you save result.model_dump_json() to this file?",
        file=sys.stderr,
    )
    sys.exit(1)

  print(
      render(result, metric_filter=args.metric, failing_only=args.failing_only)
  )

  if args.html_path:
    save_html(result, args.html_path)


def save_html(result: dict[str, Any], html_path: str) -> None:
  """Render the result as a standalone HTML report and write to ``html_path``."""
  try:
    # Imported here, not at module scope, so the rest of the script still
    # runs without the SDK installed; --save-html is the only feature that
    # needs it, and the handler below reports that clearly.
    from agentplatform._genai import _evals_visualization  # pylint: disable=g-import-not-at-top
  except ImportError as e:
    print(
        "ERROR: --save-html requires the agentplatform SDK to be installed"
        f" (`pip install google-cloud-aiplatform`): {e}",
        file=sys.stderr,
    )
    sys.exit(1)

  try:
    html_content = _evals_visualization.get_evaluation_html(json.dumps(result))
  except Exception as e:
    print(f"ERROR: Failed to render HTML report: {e}", file=sys.stderr)
    sys.exit(1)

  if not html_content:
    print(
        "ERROR: Agent Platform Eval SDK returned empty HTML — the result"
        " may be missing fields the visualizer requires.",
        file=sys.stderr,
    )
    sys.exit(1)

  with open(html_path, "w", encoding="utf-8") as f:
    f.write(str(html_content))
  print(f"Saved HTML report to {html_path}")


if __name__ == "__main__":
  main()
