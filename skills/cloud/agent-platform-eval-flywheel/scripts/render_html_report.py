#!/usr/bin/env python3
"""Render Agent Platform Eval HTML reports from saved result / loss-cluster JSON.

Two report types are supported:

  * ``evaluation`` — rendered from a result JSON produced by
    ``result.model_dump_json()``
  * ``loss-analysis`` — rendered from a loss-clusters JSON produced by
    ``response.model_dump_json()``

Use when you have a saved JSON artifact and want a browsable HTML report
to share with the user, link in a PR description, or attach to a bug.

Usage:
  python render_html_report.py --input result.json --type evaluation --output report.html
  python render_html_report.py --input clusters.json --type loss-analysis --output clusters.html

Exit codes: 0 = HTML written, 1 = SDK import / render failure.
"""

import argparse
import json
import sys


def render_evaluation_html(result_json_str: str) -> str:
  """Render an EvaluationResult JSON string as standalone HTML."""
  # Imported here, not at module scope, so that `main` can turn a missing
  # SDK into the actionable "pip install" message below rather than the
  # script dying with a traceback before it can parse its arguments.
  from agentplatform._genai import _evals_visualization  # pylint: disable=g-import-not-at-top

  html = _evals_visualization.get_evaluation_html(result_json_str)
  if not html:
    raise RuntimeError(
        "Agent Platform Eval SDK returned empty HTML — the input may be"
        " missing fields the evaluation visualizer requires."
    )
  return str(html)


def render_loss_analysis_html(response_json_str: str) -> str:
  """Render a loss-clusters response JSON string as standalone HTML."""
  # Deferred for the same reason as in `render_evaluation_html`.
  from agentplatform._genai import _evals_visualization  # pylint: disable=g-import-not-at-top

  html = _evals_visualization.get_loss_analysis_html(response_json_str)
  if not html:
    raise RuntimeError(
        "Agent Platform Eval SDK returned empty HTML — the input may be"
        " missing fields the loss-analysis visualizer requires."
    )
  return str(html)


def main():
  parser = argparse.ArgumentParser(
      description=(
          "Render Agent Platform Eval HTML reports from saved JSON artifacts."
      )
  )
  parser.add_argument(
      "--input",
      "-i",
      required=True,
      help="Path to the input JSON file (result or loss-clusters response).",
  )
  parser.add_argument(
      "--type",
      "-t",
      choices=["evaluation", "loss-analysis"],
      required=True,
      help=(
          "evaluation = client.evals.evaluate result;"
          " loss-analysis = client.evals.generate_loss_clusters response."
      ),
  )
  parser.add_argument(
      "--output",
      "-o",
      required=True,
      help="Path to write the HTML report to.",
  )
  args = parser.parse_args()

  try:
    with open(args.input) as f:
      content = f.read()
      json.loads(content)
  except FileNotFoundError:
    print(f"ERROR: File not found: {args.input}", file=sys.stderr)
    sys.exit(1)
  except json.JSONDecodeError as e:
    print(f"ERROR: Invalid JSON in {args.input}: {e}", file=sys.stderr)
    sys.exit(1)

  try:
    if args.type == "evaluation":
      html = render_evaluation_html(content)
    else:
      html = render_loss_analysis_html(content)
  except ImportError as e:
    print(
        "ERROR: requires the agentplatform SDK to be installed"
        f" (`pip install google-cloud-aiplatform`): {e}",
        file=sys.stderr,
    )
    sys.exit(1)
  except Exception as e:
    print(f"ERROR: Failed to render HTML: {e}", file=sys.stderr)
    sys.exit(1)

  with open(args.output, "w", encoding="utf-8") as f:
    f.write(html)
  print(f"Saved {args.type} HTML report to {args.output}")


if __name__ == "__main__":
  main()
