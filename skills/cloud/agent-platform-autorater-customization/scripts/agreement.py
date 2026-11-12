#!/usr/bin/env python3
"""Computes agreement between metric scores and labels, overall and per pattern.

Inputs:
  --labels   JSON list of label records, one per case:
             {"case": "id", "split": "dev", "patterns": ["P1"], "<label_key>": 1
             | 0 | 0.4 | null, ...}
             null means not applicable; those cases are skipped for that label.
  --results  One or more results JSON files shaped like
             {"cases": {"<case>": {"<metric>": {"score": 0.8, "error": null,
             "explanation": "..."}}}}
             (run_eval-style output; later files override earlier ones per case
             and metric).
  --map      metric=label_key pairs, e.g. routing_any_local=routing_provisional.

A score and a label agree when both are on the same side of the threshold
(score >= threshold means PASS). The threshold is --threshold if given, else
the "threshold" field the review page writes into labels.json, else 0.5.
Labels made on the review page are only valid at the page's threshold.
Fractional labels (per-turn rates in
multi-turn cases) also report the mean absolute difference.

Output (stdout, JSON): per metric: n, agree, accuracy, cohen_kappa, confusion
(label x prediction), errors, mean_abs_diff, per_pattern, disagreements.

Per-turn mode (multi-turn): --turn_map metric=per_turn_label_key compares a
label list ([1, 0, null, ...], one entry per user turn) with per-turn verdicts
parsed from the metric's explanation by --turn_regex (default matches
"turn 3: ... PASS" / "turn 3: FAIL"). Turns the metric did not report count as
missing, not as disagreements.

Example:
  agreement.py --labels labels.json --results r1.json --map
  data_v1=data_provisional --split dev
"""

import argparse
import json
import re
import sys


def kappa(tp, tn, fp, fn):
  n = tp + tn + fp + fn
  if not n:
    return None
  po = (tp + tn) / n
  pe = ((tp + fp) * (tp + fn) + (tn + fn) * (tn + fp)) / (n * n)
  return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def main():
  ap = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("--labels", required=True)
  ap.add_argument("--results", required=True, nargs="+")
  ap.add_argument("--map", default=[], nargs="*", help="metric=label_key")
  ap.add_argument(
      "--turn_map", default=[], nargs="*", help="metric=per_turn_label_key"
  )
  ap.add_argument("--turn_regex", default=r"turn (\d+)\b[^;]*?\b(PASS|FAIL)\b")
  ap.add_argument(
      "--threshold",
      type=float,
      default=None,
      help="default: the labels' threshold field, else 0.5",
  )
  ap.add_argument(
      "--split", default="", help="only cases with this split value"
  )
  ap.add_argument("--pattern_key", default="patterns")
  a = ap.parse_args()

  labels = {l["case"]: l for l in json.load(open(a.labels))}
  if a.threshold is None:
    found = {l["threshold"] for l in labels.values() if "threshold" in l}
    if len(found) > 1:
      sys.exit(
          f"labels have different thresholds {sorted(found)}; pass --threshold"
      )
    a.threshold = found.pop() if found else 0.5
  scores = {}
  for path in a.results:
    for case, per in json.load(open(path))["cases"].items():
      scores.setdefault(case, {}).update(per)

  report = {"threshold": a.threshold, "split": a.split or "all", "metrics": {}}
  for pair in a.map:
    metric, key = pair.split("=", 1)
    tp = tn = fp = fn = errors = 0
    diffs, dis, per_pattern = [], [], {}
    for case, lab in labels.items():
      if a.split and lab.get("split") != a.split:
        continue
      y = lab.get(key)
      if y is None:
        continue
      res = scores.get(case, {}).get(metric)
      if res is None:
        continue
      if res.get("error") or res.get("score") is None:
        errors += 1
        dis.append({
            "case": case,
            "label": y,
            "score": None,
            "error": str(res.get("error"))[:200],
        })
        continue
      s = float(res["score"])
      yb, sb = y >= a.threshold, s >= a.threshold
      tp += yb and sb
      tn += (not yb) and (not sb)
      fp += (not yb) and sb
      fn += yb and (not sb)
      diffs.append(abs(s - y))
      for p in lab.get(a.pattern_key) or ["(none)"]:
        pp = per_pattern.setdefault(p, {"n": 0, "agree": 0})
        pp["n"] += 1
        pp["agree"] += yb == sb
      if yb != sb:
        dis.append({
            "case": case,
            "label": y,
            "score": s,
            "patterns": lab.get(a.pattern_key),
            "explanation": (res.get("explanation") or "")[:300],
        })
    n = tp + tn + fp + fn
    report["metrics"][metric] = {
        "label_key": key,
        "n": n,
        "agree": tp + tn,
        "accuracy": round((tp + tn) / n, 3) if n else None,
        "cohen_kappa": kappa(tp, tn, fp, fn),
        "confusion": {
            "label_pass_pred_pass": tp,
            "label_pass_pred_fail": fn,
            "label_fail_pred_pass": fp,
            "label_fail_pred_fail": tn,
        },
        "errors": errors,
        "mean_abs_diff": round(sum(diffs) / len(diffs), 3) if diffs else None,
        "per_pattern": per_pattern,
        "disagreements": dis,
    }
  for pair in a.turn_map:
    metric, key = pair.split("=", 1)
    tp = tn = fp = fn = missing = shifted = 0
    dis = []
    for case, lab in labels.items():
      if a.split and lab.get("split") != a.split:
        continue
      ys = lab.get(key)
      res = scores.get(case, {}).get(metric)
      if not ys or not res or res.get("error"):
        continue
      got = {
          int(k): v.upper() == "PASS"
          for k, v in re.findall(
              a.turn_regex, res.get("explanation") or "", re.I
          )
      }
      if (
          got and min(got) == 1 and max(got) == len(ys)
      ):  # judge numbered turns from 1
        got = {k - 1: v for k, v in got.items()}
        shifted += 1
      for k, y in enumerate(ys):
        if y is None:
          continue
        if k not in got:
          missing += 1
          continue
        yb, sb = y >= a.threshold, got[k]
        tp += yb and sb
        tn += (not yb) and (not sb)
        fp += (not yb) and sb
        fn += yb and (not sb)
        if yb != sb:
          dis.append({
              "case": case,
              "turn": k,
              "label": y,
              "pred": "PASS" if sb else "FAIL",
          })
    n = tp + tn + fp + fn
    report["metrics"][metric + " (per turn)"] = {
        "label_key": key,
        "n": n,
        "agree": tp + tn,
        "accuracy": round((tp + tn) / n, 3) if n else None,
        "cohen_kappa": kappa(tp, tn, fp, fn),
        "confusion": {
            "label_pass_pred_pass": tp,
            "label_pass_pred_fail": fn,
            "label_fail_pred_pass": fp,
            "label_fail_pred_fail": tn,
        },
        "missing_turns": missing,
        "cases_renumbered_from_1": shifted,
        "disagreements": dis,
    }
  json.dump(report, sys.stdout, indent=1)
  print()


if __name__ == "__main__":
  main()
