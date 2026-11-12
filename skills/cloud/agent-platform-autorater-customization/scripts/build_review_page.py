#!/usr/bin/env python3
r"""Builds one self-contained HTML page for the user to review metric grades.

For each case the page shows the user's note or rating (if any), each metric's
score, PASS/FAIL, explanation and per-rubric verdicts, and the trajectory with
tool results collapsed. The user marks each metric verdict Agree or Disagree,
with a reason, and downloads labels.json. Marks are kept in the browser's
local storage, so the page can be closed and reopened.

Inputs:
  --cases    JSONL of EvalCase-shaped dicts (eval_case_id, agent_data, and
             optionally note / rating). Only these cases are shown, so leave
             held-back cases out.
  --results  One or more results JSON files from run_metrics.py
             ({"cases": {"<id>": {"<metric>": {...}}}}).
  --metrics  Optional comma-separated metric names to show (default: all).
  --baseline Optional comma-separated metric names shown as baseline, without
             Agree/Disagree buttons.

Use the metric's own pass threshold for --threshold (for example THRESHOLD in
a weighted-rubrics parser), so PASS and FAIL on the page match the metric.

Output: --out HTML file. The downloaded labels.json is a list of
{"case", "split": "dev", "threshold", "<metric>": 1 | 0, "<metric>_reason"},
where the label is the metric's verdict at that threshold when the user agrees
and the opposite when they disagree. agreement.py reads the threshold from the
file, so pass it only --map <metric>=<metric>.

Example:
  build_review_page.py --cases dev.jsonl --results results/v1.json \
      --threshold 0.9 --out review_v1.html
"""

import argparse
import html
import json
import os

TOOL_MAX = 6000


def esc(x):
  return html.escape(str(x))


def clip(t):
  if len(t) <= TOOL_MAX:
    return t
  return (
      t[: TOOL_MAX // 2]
      + f"\n… [{len(t) - TOOL_MAX} chars cut] …\n"
      + t[-TOOL_MAX // 2 :]
  )


def get(d, *names):
  for n in names:
    if isinstance(d, dict) and d.get(n) is not None:
      return d[n]
  return None


def render_trajectory(agent_data):
  """Returns the trajectory as HTML, with tool results and thoughts collapsed."""
  out = []
  for i, turn in enumerate(get(agent_data, "turns") or []):
    out.append(f'<div class="turn"><div class="th">Turn {i + 1}</div>')
    for ev in get(turn, "events") or []:
      au = esc(get(ev, "author") or "")
      for p in (get(ev, "content") or {}).get("parts") or []:
        fc = get(p, "function_call", "functionCall")
        fr = get(p, "function_response", "functionResponse")
        if fc:
          args = clip(json.dumps(fc.get("args") or {}, ensure_ascii=False))
          out.append(
              f'<div class="call">{au} called <b>{esc(fc.get("name"))}'
              f"</b> <code>{esc(args)}</code></div>"
          )
        elif fr:
          body = clip(
              json.dumps(fr.get("response") or {}, ensure_ascii=False, indent=1)
          )
          out.append(
              f'<details class="res"><summary>{au}: result of '
              f'{esc(fr.get("name"))} ({len(body)} chars)</summary>'
              f"<pre>{esc(body)}</pre></details>"
          )
        elif p.get("thought"):
          out.append(
              f'<details class="res"><summary>{au}: thinking'
              f'</summary><pre>{esc(p.get("text", ""))}</pre></details>'
          )
        elif p.get("text"):
          cls = "user" if au == "user" else "ans"
          out.append(
              f'<div class="{cls}"><b>{au}</b><pre>{esc(p["text"])}</pre></div>'
          )
    out.append("</div>")
  return "\n".join(out)


def render_rubrics(verdicts):
  if not verdicts:
    return ""
  rows = []
  for v in verdicts:
    if isinstance(v, dict):
      text = get(v, "rubric", "property", "text", "id") or ""
      verdict = get(v, "verdict", "passed", "score")
      rows.append(f"<li>{esc(verdict)}: {esc(text)}</li>")
    else:
      rows.append(f"<li>{esc(v)}</li>")
  return f"<ul class=rub>{''.join(rows)}</ul>"


def main():
  ap = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("--cases", required=True)
  ap.add_argument("--results", required=True, nargs="+")
  ap.add_argument("--metrics", default="")
  ap.add_argument("--baseline", default="")
  ap.add_argument(
      "--threshold", type=float, default=0.5, help="score >= threshold is PASS"
  )
  ap.add_argument("--title", default="Metric review")
  ap.add_argument("--out", required=True)
  a = ap.parse_args()

  cases = [json.loads(l) for l in open(a.cases) if l.strip()]
  res = {}
  for path in a.results:
    for cid, ms in json.load(open(path)).get("cases", {}).items():
      res.setdefault(cid, {}).update(ms)
  baseline = [m for m in a.baseline.split(",") if m]
  graded = set()
  for ms in res.values():
    graded.update(ms)
  metrics = [m for m in a.metrics.split(",") if m] or sorted(
      graded - set(baseline)
  )

  toc, body = [], []
  for c in cases:
    cid = str(c.get("eval_case_id"))
    r = res.get(cid, {})
    chips, blocks = [], []
    for m in metrics + baseline:
      x = r.get(m) or {}
      score = x.get("score")
      if x.get("error") or score is None:
        verdict, cls = "ERROR", "err"
      else:
        verdict = "PASS" if score >= a.threshold else "FAIL"
        cls = verdict.lower()
      chips.append(f'<span class="chip {cls}">{esc(m)}: {verdict}</span>')
      buttons = ""
      if m in metrics and cls != "err":
        pred = 1 if verdict == "PASS" else 0
        key = esc(f"{cid}|{m}")
        buttons = (
            f'<div class="mark" data-key="{key}" data-pred="{pred}">'
            f'<label><input type=radio name="{key}" value=agree> Agree</label>'
            f'<label><input type=radio name="{key}" value=disagree> Disagree'
            "</label><input class=why placeholder='Why? (needed when you "
            "disagree)'></div>"
        )
      tag = " (baseline)" if m in baseline else ""
      blocks.append(
          f'<div class="metric {cls}"><b>{esc(m)}{tag}</b>: {verdict} '
          "(score"
          f' {esc(score)})<p>{esc(x.get("explanation") or x.get("error") or "")}'
          f'</p>{render_rubrics(x.get("rubric_verdicts"))}{buttons}</div>'
      )
    note = " · ".join(
        f"<b>{k}:</b> {esc(c[k])}" for k in ("rating", "note") if c.get(k)
    )
    toc.append(
        f'<tr><td><a href="#{esc(cid)}">{esc(cid)}</a></td>'
        f'<td>{"".join(chips)}</td><td class=done data-case="{esc(cid)}">'
        "</td></tr>"
    )
    body.append(
        f'<section id="{esc(cid)}"><h2>{esc(cid)}</h2>'
        f'{f"<p>{note}</p>" if note else ""}{"".join(blocks)}'
        "<details class=traj><summary>Trajectory</summary>"
        f'{render_trajectory(c.get("agent_data") or {})}</details>'
        '<p><a href="#top">Back to top</a></p></section>'
    )

  page = f"""<!doctype html><meta charset="utf-8"><title>{esc(a.title)}</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;max-width:1100px;margin:auto;padding:16px}}
pre{{white-space:pre-wrap;word-break:break-word;margin:4px 0}}
code{{font-size:12px;word-break:break-all}}
section{{border-top:2px solid #444;margin-top:28px}}
.turn{{border-left:3px solid #ccc;padding-left:10px;margin:10px 0}}
.th{{font-weight:bold;color:#555}} .user{{background:#eef4ff;padding:4px 8px}}
.ans{{background:#f1fff0;padding:4px 8px}} .call{{color:#7a4a00}} .res{{color:#555}}
.metric{{border:1px solid #ddd;padding:6px 10px;margin:8px 0}}
.pass{{background:#efe}} .fail{{background:#fee}} .err{{background:#eee}}
.chip{{display:inline-block;padding:1px 6px;margin:1px;border-radius:3px}}
.mark{{margin-top:6px}} .why{{width:60%;margin-left:8px}}
#bar{{position:sticky;top:0;background:#fff;padding:6px 0;border-bottom:1px solid #ccc}}
table td{{padding:2px 8px;vertical-align:top}}
</style><a id="top"></a><div id="bar"><b>{esc(a.title)}</b> ·
<span id="progress"></span> · <button id="dl">Download labels.json</button></div>
<p>For each metric verdict, choose Agree or Disagree, and say why when you
disagree. Your marks are saved in this browser. When you are done, download
labels.json and give it back.</p>
<table>{"".join(toc)}</table>{"".join(body)}
<script>
const KEY = "review:" + document.title + ":" + location.pathname;
const saved = JSON.parse(localStorage.getItem(KEY) || "{{}}");
const marks = [...document.querySelectorAll(".mark")];
function save() {{
  const s = {{}};
  let done = 0;
  for (const m of marks) {{
    const v = m.querySelector("input[type=radio]:checked");
    const why = m.querySelector(".why").value;
    if (v || why) s[m.dataset.key] = {{v: v ? v.value : null, why}};
    if (v && (v.value === "agree" || why)) done++;
  }}
  localStorage.setItem(KEY, JSON.stringify(s));
  document.getElementById("progress").textContent = done + " of " + marks.length + " verdicts marked";
  for (const td of document.querySelectorAll("td.done")) {{
    const mine = marks.filter(m => m.dataset.key.startsWith(td.dataset.case + "|"));
    const ok = mine.filter(m => {{ const v = s[m.dataset.key]; return v && v.v && (v.v === "agree" || v.why); }});
    td.textContent = mine.length && ok.length === mine.length ? "done" : "";
  }}
  return s;
}}
for (const m of marks) {{
  const s = saved[m.dataset.key];
  if (s) {{
    if (s.v) m.querySelector(`input[value=${{s.v}}]`).checked = true;
    m.querySelector(".why").value = s.why || "";
  }}
  m.addEventListener("input", save);
}}
document.getElementById("dl").onclick = () => {{
  const s = save(), out = {{}};
  for (const m of marks) {{
    const v = s[m.dataset.key];
    if (!v || !v.v) continue;
    const [cid, metric] = m.dataset.key.split("|");
    const pred = Number(m.dataset.pred);
    const rec = out[cid] || (out[cid] = {{case: cid, split: "dev", threshold: {a.threshold}}});
    rec[metric] = v.v === "agree" ? pred : 1 - pred;
    rec[metric + "_reason"] = v.why;
  }}
  const blob = new Blob([JSON.stringify(Object.values(out), null, 1)], {{type: "application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "labels.json";
  a.click();
}};
save();
</script>"""
  os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
  open(a.out, "w").write(page)
  print(
      json.dumps({
          "out": a.out,
          "cases": len(cases),
          "metrics": metrics,
          "baseline": baseline,
          "verdicts_to_mark": page.count('class="mark"'),
      })
  )


if __name__ == "__main__":
  main()
