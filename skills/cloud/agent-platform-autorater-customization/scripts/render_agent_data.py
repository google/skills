#!/usr/bin/env python3
"""Renders AgentData trajectories as plain text for reading, labeling, or judging.

Input: JSONL where each line is an EvalCase-shaped dict with `agent_data`
(and optionally `eval_case_id`), or a bare AgentData dict ({"turns": [...]}).

Uses: read trajectories to find failure patterns; give labelers a readable
view; pass the text as a template variable (or as `response`) to metrics that
do not read agent_data themselves (single-turn predefined metrics, LLMMetric).

Output (stdout, JSON): {"cases": [{"id": ..., "chars": N, "text": "..."}]}
With --out_dir, also writes <id>.txt per case.

Example:
  render_agent_data.py cases.jsonl --skip_thoughts --max_tool_chars 4000
"""

import argparse
import json
import os
import sys


def get(d, *names):
  for n in names:
    if isinstance(d, dict) and d.get(n) is not None:
      return d[n]
  return None


def render(agent_data, skip_thoughts, max_tool_chars):
  """Returns AgentData as readable text, one block per turn."""
  lines = []
  for i, turn in enumerate(get(agent_data, "turns") or []):
    tid = get(turn, "turn_id", "turnId")
    lines.append(
        "--- Turn"
        f" {get(turn, 'turn_index', 'turnIndex') if get(turn, 'turn_index', 'turnIndex') is not None else i}"
        + (f" ({tid})" if tid else "")
        + " ---"
    )
    for e in get(turn, "events") or []:
      author = get(e, "author") or "?"
      for p in (get(e, "content") or {}).get("parts") or []:
        if p.get("thought"):
          if not skip_thoughts:
            lines.append(f"{author} (thought): {p.get('text', '')}")
          continue
        fc = get(p, "function_call", "functionCall")
        fr = get(p, "function_response", "functionResponse")
        if fc:
          lines.append(
              f"{author} CALL {fc.get('name')}: "
              + json.dumps(fc.get("args"), ensure_ascii=False)
          )
        elif fr:
          body = json.dumps(fr.get("response"), ensure_ascii=False, default=str)
          if len(body) > max_tool_chars:
            body = (
                body[:max_tool_chars]
                + f"... [{len(body) - max_tool_chars} chars cut]"
            )
          lines.append(f"{author} RESULT {fr.get('name')}: {body}")
        elif "text" in p:
          lines.append(f"{author}: {p['text']}")
  return "\n".join(lines)


def main():
  ap = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("inp", help="JSONL of eval cases or AgentData dicts")
  ap.add_argument("--skip_thoughts", action="store_true")
  ap.add_argument("--max_tool_chars", type=int, default=4000)
  ap.add_argument("--out_dir", default="")
  a = ap.parse_args()
  out = []
  with open(a.inp) as f:
    for n, line in enumerate(f):
      if not line.strip():
        continue
      rec = json.loads(line)
      ad = rec.get("agent_data") or rec.get("agent_eval_data") or rec
      cid = rec.get("eval_case_id") or f"case_{n}"
      text = render(ad, a.skip_thoughts, a.max_tool_chars)
      out.append({"id": cid, "chars": len(text), "text": text})
      if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        with open(os.path.join(a.out_dir, f"{cid}.txt"), "w") as o:
          o.write(text)
  json.dump({"cases": out}, sys.stdout, ensure_ascii=False)
  print()


if __name__ == "__main__":
  main()
