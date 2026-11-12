#!/usr/bin/env python3
r"""Runs SDK metrics on eval cases with client.evals.evaluate() and saves per-case results.

Inputs:
  --cases         JSONL; each line is an EvalCase-shaped dict (eval_case_id,
                  prompt, responses, reference, agent_data, plus any extra
                  attributes your code metrics or --trajectory_response use,
                  such as trajectory).
  --metrics_file  Python file defining METRICS = {"name": callable}; each
                  callable returns an SDK metric (see
                  references/metric_templates.md).
  --metrics       Comma-separated names from METRICS to run.
  --rubrics       Optional JSON {"<case id>": [rubric, ...]}, for example the
                  user's existing rubrics; attached as
                  rubric_groups[--rubric_group] for predefined rubric metrics.
  --trajectory_response  Put the case's `trajectory` text in `responses` and
                  drop `agent_data`, for metrics that grade only the response.

Output: --out JSON {"cases": {"<id>": {"<metric>": {"score", "explanation",
"error", "rubric_verdicts"}}}}, which agreement.py reads. A one-line JSON
summary goes to stdout.

Example:
  run_metrics.py --cases cases.jsonl --metrics_file my_metrics.py \
      --metrics tool_match,answer_checks --project my-project --location us-central1 \
      --out results/v1.json
"""

import argparse
import importlib.util
import json
import os
import sys
import time

import agentplatform
from agentplatform import types


def load_metrics(path, names):
  spec = importlib.util.spec_from_file_location("user_metrics", path)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  missing = [n for n in names if n not in mod.METRICS]
  if missing:
    sys.exit(f"unknown metrics {missing}; METRICS has {sorted(mod.METRICS)}")
  return [mod.METRICS[n]() for n in names]


def load_cases(path, ids, rubrics, rubric_group, trajectory_response):
  """Reads EvalCase dicts from JSONL, applying rubrics and response options."""
  cases = []
  for line in open(path):
    if not line.strip():
      continue
    c = json.loads(line)
    if ids and c["eval_case_id"] not in ids:
      continue
    if trajectory_response:
      c["responses"] = [
          {"response": {"role": "model", "parts": [{"text": c["trajectory"]}]}}
      ]
      c.pop("agent_data", None)
    if c["eval_case_id"] in rubrics:
      c["rubric_groups"] = {
          rubric_group: {"rubrics": rubrics[c["eval_case_id"]]}
      }
    cases.append(types.EvalCase(**c))
  return cases


def collect(cases, result, names):
  """Returns {case id: {metric: result dict}} from an EvaluationResult."""
  # The SDK omits cases that produced no result, so match on eval_case_index.
  by_index = {r.eval_case_index: r for r in result.eval_case_results or []}
  missing = {
      "score": None,
      "explanation": None,
      "error": "no result returned for this case",
      "rubric_verdicts": [],
  }
  out = {}
  for i, case in enumerate(cases):
    res = by_index.get(i)
    per = {}
    for cand in (res.response_candidate_results if res else None) or []:
      for name, mr in (cand.metric_results or {}).items():
        verdicts = []
        for v in mr.rubric_verdicts or []:
          rubric = v.evaluated_rubric
          prop = rubric.content.property if rubric and rubric.content else None
          verdicts.append({
              "rubric": prop.description if prop else None,
              "verdict": v.verdict,
              "reasoning": v.reasoning,
          })
        per[name] = {
            "score": mr.score,
            "explanation": mr.explanation,
            "error": mr.error_message,
            "rubric_verdicts": verdicts,
        }
    if not per:
      per = {name: dict(missing) for name in names}
    out[case.eval_case_id] = per
  return out


def main():
  ap = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("--cases", required=True)
  ap.add_argument("--metrics_file", required=True)
  ap.add_argument("--metrics", required=True)
  ap.add_argument("--project", required=True)
  ap.add_argument("--location", default="us-central1")
  ap.add_argument("--out", required=True)
  ap.add_argument("--ids", default="", help="comma-separated case ids to run")
  ap.add_argument("--rubrics", default="")
  ap.add_argument("--rubric_group", default="custom_rubrics")
  ap.add_argument("--trajectory_response", action="store_true")
  ap.add_argument(
      "--retry_errors", action="store_true", help="rerun failed cases once"
  )
  a = ap.parse_args()

  names = [n for n in a.metrics.split(",") if n]
  metrics = load_metrics(a.metrics_file, names)
  rubrics = json.load(open(a.rubrics)) if a.rubrics else {}
  ids = set(filter(None, a.ids.split(",")))
  cases = load_cases(
      a.cases, ids, rubrics, a.rubric_group, a.trajectory_response
  )
  client = agentplatform.Client(project=a.project, location=a.location)

  t0 = time.time()
  result = client.evals.evaluate(
      dataset=types.EvaluationDataset(eval_cases=cases), metrics=metrics
  )
  result_names = [getattr(m, "name", None) or n for m, n in zip(metrics, names)]
  per_case = collect(cases, result, result_names)
  if a.retry_errors:
    failed = [
        c
        for c in cases
        if any(m["error"] for m in per_case[c.eval_case_id].values())
    ]
    if failed:
      again = client.evals.evaluate(
          dataset=types.EvaluationDataset(eval_cases=failed), metrics=metrics
      )
      for cid, per in collect(failed, again, result_names).items():
        for name, m in per.items():
          if per_case[cid].get(name, {}).get("error") and not m["error"]:
            per_case[cid][name] = dict(m, retried=True)

  out = {
      "metrics": names,
      "seconds": round(time.time() - t0, 1),
      "cases": per_case,
  }
  os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
  json.dump(out, open(a.out, "w"), indent=1, default=str)
  errors = 0
  for per in per_case.values():
    errors += sum(1 for m in per.values() if m["error"])
  json.dump(
      {
          "out": a.out,
          "cases": len(cases),
          "errors": errors,
          "seconds": out["seconds"],
      },
      sys.stdout,
  )
  print()


if __name__ == "__main__":
  main()
