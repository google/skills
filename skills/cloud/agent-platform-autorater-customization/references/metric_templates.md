# Metric templates

Working templates for each metric form, each adapted from a published recipe.
Every template here was run against the evaluation service on test trajectories
before it was added.

-   [How to use these templates](#how-to-use-these-templates) (line 20)
-   [Shared setup](#shared-setup) (line 39)
-   [Code metric: expected tool call](#code-metric-expected-tool-call) (line 55)
-   [LLM metric, static rubric: reference-guided checks](#llm-metric-static-rubric-reference-guided-checks)
    (line 143)
-   [Step-based metric: generated checklists](#step-based-metric-generated-checklists)
    (line 189)
-   [Step-based metric: weighted rubrics](#step-based-metric-weighted-rubrics)
    (line 311)
-   [Step-based metric: claim faithfulness](#step-based-metric-claim-faithfulness)
    (line 419)
-   [Sources](#sources) (line 574)

## How to use these templates

1.  Copy the template for the metric type chosen in step 4 of SKILL.md into a
    metrics file (for example `metrics.py`) that defines
    `METRICS = {"name": callable}`.
2.  Change only the lines marked `EDIT`, filling them from the approved criteria
    and rubrics.
3.  Run every metric with `scripts/run_metrics.py`. Its results file is what
    `scripts/build_review_page.py` and `scripts/agreement.py` read.
4.  Version each change (`answer_checks_v2`, ...) and keep old results.
5.  Keep each template's variable names distinct when several share one
    metrics file: the `METRICS` lambdas read them when the metric runs, so a
    later template that reuses a name replaces the earlier one's value.

Each recipe also says what it does not catch. Check that against the approved
criteria. When one form leaves a gap, split the criterion or add a check from
another form (for example generated checklists for "did it do what was asked"
plus faithfulness for "is what it said true").

## Shared setup

```python
from agentplatform import types

PROJECT = "my-project"  # EDIT: your project ID
LOCATION = "us-central1"
# LLMMetric needs the full resource name; short names fail with 400.
JUDGE = f"projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/gemini-2.5-flash"
```

Cases are EvalCase-shaped JSONL lines with `eval_case_id`, `prompt`,
`responses`, `reference` and `agent_data`. Templates read the trajectory from
`{agent_data}`: extra case attributes reach the judge only in inline runs, not
when a registered metric runs by name.

## Code metric: expected tool call

**Use when** the label is an exact rule on the trajectory: the right tool, the
right arguments, a required format.

**Recipe:** function-call checking as in the Berkeley Function Calling
Leaderboard, which compares the called function and its arguments with the
expected call. Here the expected call is written in the reference as one line,
`EXPECTED_TOOL_CALL: {"name": ..., "args": {...}}`, and extra arguments are
allowed.

Save as `tool_call_match.py`. It runs in the evaluation service's code
sandbox, and the same source can run locally while you debug:

```python
import json
import re


def _text(field):
  if isinstance(field, str):
    return field
  if not isinstance(field, dict):
    return ""
  if isinstance(field.get("response"), dict):
    field = field["response"]
  if "contents" in field:  # remote sandbox shape
    contents = field.get("contents") or {}
    if isinstance(contents, dict):
      contents = contents.get("gemini_contents") or contents.get("contents") or []
    return "".join(p.get("text", "") for c in contents for p in (c.get("parts") or []))
  return "".join(p.get("text", "") for p in (field.get("parts") or []))


def _get(d, *names):
  for n in names:
    if isinstance(d, dict) and d.get(n) is not None:
      return d[n]
  return None


def _tool_calls(agent_data):
  calls = []
  for turn in _get(agent_data, "turns") or []:
    for event in _get(turn, "events") or []:
      for part in (_get(event, "content") or {}).get("parts") or []:
        fc = _get(part, "function_call", "functionCall")
        if fc:
          calls.append((fc.get("name"), fc.get("args") or {}))
  return calls


def evaluate(instance: dict) -> float:
  m = re.search(r"EXPECTED_TOOL_CALL:\s*(\{.*\})", _text(instance.get("reference")))
  if not m:
    return 0.0
  want = json.loads(m.group(1))
  # A local callable gets agent_data; the remote sandbox gets agent_eval_data.
  agent_data = instance.get("agent_data") or instance.get("agent_eval_data") or {}
  for name, args in _tool_calls(agent_data):  # EDIT: your rule
    if name == want["name"] and all(
        str(args.get(k)).lower() == str(v).lower() for k, v in want.get("args", {}).items()):
      return 1.0
  return 0.0


def evaluate_local(instance: dict) -> dict:
  score = evaluate(instance)
  return {"score": score, "explanation": "expected tool call found" if score else "expected tool call missing"}
```

Use the remote version in `METRICS`. It grades cases that have only
`agent_data`, and it can be registered:

```python
METRICS = {
    "tool_match": lambda: types.CodeExecutionMetric(
        name="tool_match", custom_function=open("tool_call_match.py").read()),
}
```

To debug the rule on your machine, call `evaluate_local(case)` directly, or use
`types.Metric(custom_function=evaluate_local)`. That local form needs
`responses` on every case and can't be registered (see
[SDK gotchas](sdk_gotchas.md)), so don't hand it over as the final metric.

**Doesn't catch:** whether the answer built on the tool result is right.

## LLM metric, static rubric: reference-guided checks

**Use when** the same criteria apply to every case and need judgment, and a
reference answer exists.

**Recipe:** reference-guided single-answer grading from MT-Bench, where the
judge sees a reference answer before grading. Adapted to yes/no checks instead
of a 1-10 score, with tolerated differences listed and the checks answered
before the score.

```python
ANSWER_CHECKS = """You grade an AI agent's answer to a user's request. Judge content only, not style.

# User request
{prompt}

# Agent trajectory (tool calls, tool results, final answer)
{agent_data}

# Reference (one correct answer; a different answer can also be correct)
{reference}

# Checks
1. The final answer addresses every part of the request.
2. Every fact in the final answer is supported by a tool result in the trajectory.
3. The final answer agrees with the reference on the key facts. Tolerated: wording, units written
   differently, rounding.
4. The agent used the information it was asked about (for example the requested day or place).

# Output
Answer each check YES or NO with one sentence of evidence, then give the score: 1 only if all
checks are YES, else 0. Return only JSON:
{{"checks": {{"1": "YES|NO: ...", "2": "...", "3": "...", "4": "..."}}, "explanation": "<short>", "score": <1 or 0>}}
"""
# EDIT: replace the checks and tolerated differences with the approved ones.

METRICS["answer_checks"] = lambda: types.LLMMetric(
    name="answer_checks", prompt_template=ANSWER_CHECKS, judge_model=JUDGE,
    judge_model_sampling_count=1)  # use 3 or more for the final check
```

Double the braces of literal JSON in the template (`{{ }}`); single braces are
template variables.

**Doesn't catch:** requirements that differ per case and aren't in the checks.

## Step-based metric: generated checklists

**Use when** each conversation has its own requirements and there is no good
reference: what the user asked for changes from case to case, including in
later turns.

**Recipe:** TICK (Targeted Instruct-evaluation with ChecKlists), which has an
LLM turn each instruction into YES/NO questions and then judges a response
against them. Here both stages read the whole conversation: `generate` writes
the checklist from every user turn and the agent's instructions, `grade` checks
the conversation against it, and a code parser computes a score weighted by
each check's importance.

```python
CHECKLIST_GENERATE = """Write a checklist for judging how well an AI agent handled this conversation.

# Conversation (agent instructions, user messages, tool calls, tool results, agent answers)
{agent_eval_data}

Write 3 to 8 YES/NO checks. Each check is one requirement that a user message or the agent's
instructions states or clearly implies, including requirements added in later turns. Write each as
a statement about the agent's behavior. Don't add requirements about style or length unless the
user asked for them. Rate each check's importance:
- HIGH: failing it makes the answer wrong or unusable for what the user asked (for example the wrong
  place, a fact contradicting the tool results, ignoring an explicit request). Use it sparingly.
- MEDIUM: failing it makes the answer worse but still usable.
- LOW: a detail the user would barely notice.

Return only JSON:
{{"checks": [{{"id": "C1", "check": "<statement>", "importance": "HIGH|MEDIUM|LOW"}}]}}
"""

CHECKLIST_GRADE = """Grade an AI agent's conversation against a checklist. Judge each check on its own.

# Conversation (agent instructions, user messages, tool calls, tool results, agent answers)
{agent_eval_data}

# Checklist
{step.generate.output}

For each check answer YES if the conversation meets it, NO if it does not, or NA if it does not
apply. Copy the check's id, text and importance, and give one sentence of evidence quoted from the
conversation.

Return only JSON:
{{"verdicts": [{{"id": "C1", "check": "<text>", "importance": "HIGH|MEDIUM|LOW", "verdict": "YES|NO|NA", "evidence": "<quote or reason>"}}]}}
"""

CHECKLIST_PARSE = r'''
import collections, json
WEIGHTS = {"HIGH": 10, "MEDIUM": 5, "LOW": 2}  # EDIT: weight per importance
HIGH_MUST_PASS = False  # EDIT: True scores a case 0 when any HIGH check fails

def first_verdicts(text):
  # Judges often wrap JSON in Markdown code fences or quote braces in explanations,
  # so decode the first object that has "verdicts" instead of matching braces.
  decoder = json.JSONDecoder()
  for i, ch in enumerate(text):
    if ch == "{":
      try:
        d, _ = decoder.raw_decode(text[i:])
      except ValueError:
        continue
      if isinstance(d, dict) and "verdicts" in d:
        return d["verdicts"]
  return None

def parse_results(responses):
  votes, info = collections.defaultdict(list), {}
  for text in responses:
    verdicts = first_verdicts(text)
    if verdicts is None:
      continue
    for v in verdicts:
      cid, verdict = str(v.get("id", "")).strip(), str(v.get("verdict", "")).upper()
      if cid and verdict in ("YES", "NO", "NA"):
        votes[cid].append(verdict)
        info.setdefault(cid, (v.get("check", ""), str(v.get("importance", "MEDIUM")).upper()))
  if not votes:
    raise ValueError("no parsable verdicts")
  final = {c: collections.Counter(vs).most_common(1)[0][0] for c, vs in votes.items()}
  weight = {c: WEIGHTS.get(info[c][1], WEIGHTS["MEDIUM"]) for c in final}
  scored = [c for c, v in final.items() if v != "NA"]
  total = sum(weight[c] for c in scored)
  score = sum(weight[c] for c in scored if final[c] == "YES") / total if total else 1.0
  if HIGH_MUST_PASS and any(final[c] == "NO" and info[c][1] == "HIGH" for c in final):
    score = 0.0
  notes = [f"{c} {info[c][1]} {final[c]}: {info[c][0]}" for c in sorted(final)]
  return {"score": score, "explanation": "; ".join(notes)}
'''

METRICS["generated_checklist"] = lambda: types.StepBasedLLMMetric(
    name="generated_checklist",
    steps=[
        {"step_id": "generate", "prompt_template": CHECKLIST_GENERATE,
         "autorater_config": {"autorater_model": JUDGE, "sampling_count": 1}},
        {"step_id": "grade", "prompt_template": CHECKLIST_GRADE,
         "autorater_config": {"autorater_model": JUDGE, "sampling_count": 3},
         "response_parser_config": {"custom_code_parser_config": {"parsing_function": CHECKLIST_PARSE}}},
    ],
)
```

-   The checklist is generated once per case (`sampling_count` 1), so every
    grading sample votes on the same check ids. With more generation samples
    the ids would not line up across samples.
-   Generators rate most checks HIGH on short conversations, which flattens the
    weights. Set `HIGH_MUST_PASS = True` when one failed core requirement should
    fail the case, or use a pass threshold near 1.0.
-   The checklist changes between runs (4 to 8 checks on the same case in
    testing). To keep it fixed while revising, save the `generate` output from
    one run and use it as a static rubric list (see the weighted-rubrics
    template).
-   In testing on a two-turn conversation where the second turn asked for
    Fahrenheit, the checklist included that request and failed the answer
    given in Celsius; a checklist generated from the first user message alone
    can't see it.

**Doesn't catch reliably:** wrong facts. It failed an answer that invented the
weather only when the generated checklist happened to include a check against
the tool results. Pair it with a grounding check such as claim faithfulness.

## Step-based metric: weighted rubrics

**Use when** one criterion needs several checks and some matter more than
others, for example answer correctness where a wrong fact should fail the case
but a missing detail should only lower the score.

**Recipe:** the checklist scoring of the predefined rubric metrics (one verdict
per rubric, majority vote across samples, N/A rubrics left out), with weights,
must-pass rubrics and a threshold added. The judge sees only the rubrics; the
parser holds the weights, so the judge grades each rubric on its own.

```python
WEIGHTED_RUBRICS = """R1. Every fact in the final answer (numbers, conditions, dates) is stated in a tool result or follows directly from one.
R2. The final answer gives a direct recommendation for the decision the user asked about.
R3. The final answer is about the place and day the user asked about.
R4. The final answer states the temperature."""
# EDIT: the approved rubrics for this criterion, one per line with an id.

WEIGHTED_GRADE = """You grade an AI agent's conversation against a list of rubrics. Judge each rubric on its own.

# Conversation (user messages, tool calls, tool results, agent answers)
{agent_eval_data}

# Rubrics
""" + WEIGHTED_RUBRICS + """

For each rubric answer YES if the conversation meets it, NO if it does not, or NA if the rubric does
not apply to this conversation. Give one sentence of evidence quoted from the conversation.

Return only JSON:
{{"verdicts": [{{"id": "R1", "verdict": "YES|NO|NA", "evidence": "<quote or reason>"}}]}}
"""

WEIGHTED_PARSE = r'''
import collections, json
WEIGHTS = {"R1": 10, "R2": 5, "R3": 5, "R4": 2}  # EDIT: HIGH 10, MEDIUM 5, LOW 2
MUST_PASS = {"R1"}  # EDIT: a NO on any of these scores the case 0
THRESHOLD = 0.9  # EDIT: score needed to pass

def first_verdicts(text):
  # Judges often wrap JSON in Markdown code fences or quote braces in explanations,
  # so decode the first object that has "verdicts" instead of matching braces.
  decoder = json.JSONDecoder()
  for i, ch in enumerate(text):
    if ch == "{":
      try:
        d, _ = decoder.raw_decode(text[i:])
      except ValueError:
        continue
      if isinstance(d, dict) and "verdicts" in d:
        return d["verdicts"]
  return None

def parse_results(responses):
  votes, evidence = collections.defaultdict(list), {}
  for text in responses:
    verdicts = first_verdicts(text)
    if verdicts is None:
      continue
    for v in verdicts:
      rid, verdict = str(v.get("id", "")).strip(), str(v.get("verdict", "")).upper()
      if rid in WEIGHTS and verdict in ("YES", "NO", "NA"):
        votes[rid].append(verdict)
        evidence.setdefault((rid, verdict), v.get("evidence", ""))
  if not votes:
    raise ValueError("no parsable verdicts")
  final = {r: collections.Counter(vs).most_common(1)[0][0] for r, vs in votes.items()}
  scored = {r: v for r, v in final.items() if v != "NA"}
  total = sum(WEIGHTS[r] for r in scored)
  score = sum(WEIGHTS[r] for r, v in scored.items() if v == "YES") / total if total else 1.0
  failed_must = sorted(r for r in MUST_PASS if final.get(r) == "NO")
  if failed_must:
    score = 0.0
  notes = [f"{r}={final[r]}: {evidence.get((r, final[r]), '')}" for r in sorted(final)]
  head = f"{'PASS' if score >= THRESHOLD else 'FAIL'} ({score:.2f})"
  if failed_must:
    head += f", must-pass failed: {', '.join(failed_must)}"
  return {"score": score, "explanation": head + "; " + "; ".join(notes)}
'''

METRICS["answer_correctness"] = lambda: types.StepBasedLLMMetric(
    name="answer_correctness",
    steps=[{
        "step_id": "grade",
        "prompt_template": WEIGHTED_GRADE,
        "autorater_config": {"autorater_model": JUDGE, "sampling_count": 3},
        "response_parser_config": {"custom_code_parser_config": {"parsing_function": WEIGHTED_PARSE}},
    }],
)
```

Run it with `scripts/run_metrics.py` like any other metric. Add the
preprocessor from the next template when traces are long.

-   The score is the weight of passing rubrics divided by the weight of
    applicable ones. A rubric missing from every sample counts as not
    applicable, so check the explanation lists every rubric.
-   Count a case as passing when the score reaches the threshold. Report the
    threshold with the metric, since it decides the pass rate.
-   In testing, a wrong-weather answer passed R2 to R4 and would have scored
    0.55 without the must-pass rule; failing R1 set it to 0.
-   For rubrics that differ per case, put them in each case's reference and read
    them with `{reference}`; ask the judge to copy each rubric's importance into
    its verdict, and weight by that in the parser.

**Doesn't catch:** anything outside the listed rubrics. Weights only rank what
the rubrics already check.

## Step-based metric: claim faithfulness

**Use when** the question is whether the agent's answer is supported by what its
tools returned, or when grading needs several stages.

**Recipe:** the Ragas faithfulness metric: split the answer into claims, check
each claim against the retrieved context, and score supported claims divided by
all claims. Here the context is the agent's tool results, and each stage is one
step: `claims` lists the claims, `verify` checks them, and a code parser
computes the score.

```python
PREPROCESS = r'''
def preprocess(agent_data):
  keep = 20  # rows from the start and from the end of each tool result
  turns = []
  for t in agent_data.get("turns", []):
    events = []
    for e in t.get("events", []):
      parts = []
      for p in (e.get("content") or {}).get("parts", []):
        if p.get("thought"):
          continue
        fr = p.get("function_response")
        if fr:
          r = dict(fr.get("response") or {})
          rows = r.get("rows")
          if isinstance(rows, list) and len(rows) > 2 * keep:
            r["rows"] = rows[:keep] + rows[-keep:]
          parts.append({"function_response": {"name": fr.get("name"), "response": r}})
        elif p.get("function_call") or "text" in p:
          parts.append(p)
      if parts:
        events.append({"author": e.get("author"), "content": {"role": (e.get("content") or {}).get("role"), "parts": parts}})
    turns.append({"turn_index": t.get("turn_index"), "turn_id": t.get("turn_id"), "events": events})
  return {"agents": agent_data.get("agents", {}), "turns": turns}
'''

CLAIMS = """List the factual claims in the agent's final answer to the user.

# Conversation (user messages, tool calls, tool results, agent answers)
{agent_eval_data}

A claim is one checkable statement of fact (a number, a date, a name, a condition). Split
sentences that state several facts. Skip advice, opinions, and restatements of the question.

Return only JSON: {{"claims": ["<claim>", ...]}}
"""

VERIFY = """Check each claim against the tool results in the conversation.

# Conversation (user messages, tool calls, tool results, agent answers)
{agent_eval_data}

# Claims from the agent's final answer
{step.claims.output}

A claim is SUPPORTED if a tool result states it or it follows directly from a tool result
(simple arithmetic and unit changes count). It is NOT supported if no tool result covers it or
a tool result contradicts it. Use only the tool results, not your own knowledge.

Return only JSON:
{{"verdicts": [{{"claim": "<claim>", "supported": true or false, "evidence": "<tool result or why not>"}}]}}
"""

FAITHFULNESS_PARSE = r'''
import json
def first_verdicts(text):
  # Judges often wrap JSON in Markdown code fences or quote braces in explanations,
  # so decode the first object that has "verdicts" instead of matching braces.
  decoder = json.JSONDecoder()
  for i, ch in enumerate(text):
    if ch == "{":
      try:
        d, _ = decoder.raw_decode(text[i:])
      except ValueError:
        continue
      if isinstance(d, dict) and "verdicts" in d:
        return d["verdicts"]
  return None

def parse_results(responses):
  scores, notes = [], []
  for text in responses:
    verdicts = first_verdicts(text)
    if verdicts is None:
      continue
    if not verdicts:
      scores.append(1.0)
      notes.append("no factual claims")
      continue
    ok = [v for v in verdicts if v.get("supported") is True]
    scores.append(len(ok) / len(verdicts))
    notes.append("; ".join(
        f"{'SUPPORTED' if v.get('supported') is True else 'UNSUPPORTED'}: {v.get('claim')}"
        for v in verdicts))
  if not scores:
    raise ValueError("no parsable verdicts")
  return {"score": sum(scores) / len(scores), "explanation": notes[0]}
'''

METRICS["faithfulness"] = lambda: types.StepBasedLLMMetric(
    name="faithfulness",
    preprocessor={"code_config": {"code": PREPROCESS}},
    steps=[
        {"step_id": "claims", "prompt_template": CLAIMS,
         "autorater_config": {"autorater_model": JUDGE, "sampling_count": 1}},
        {"step_id": "verify", "prompt_template": VERIFY,
         "autorater_config": {"autorater_model": JUDGE, "sampling_count": 1},
         "response_parser_config": {"custom_code_parser_config": {"parsing_function": FAITHFULNESS_PARSE}}},
    ],
)
```

```shell
python3 scripts/run_metrics.py --cases cases.jsonl --metrics_file metrics.py \
    --metrics faithfulness --project my-project \
    --out results/faithfulness_v1.json
```

How the parts fit:

-   The preprocessor keeps what the judge needs and trims long tool results from
    both ends.
-   To grade one sub-agent, keep the user's messages, the hand-offs to it and
    the events whose `author` is that agent. Keep the hand-offs: without them
    the judge can't tell whether the agent was called at all. In `preprocess`,
    filter each turn's events before anything else:

    ```python
    AGENT = "my_sub_agent"  # EDIT: the sub-agent to grade

    def is_handoff(e):
      parts = (e.get("content") or {}).get("parts") or [{}]
      return (parts[0].get("function_call") or {}).get("name") == "transfer_to_agent"

    events = [e for e in t.get("events", [])
              if e.get("author") in ("user", AGENT) or is_handoff(e)]
    ```

    Tell the judge what to do when the agent wasn't called (score 1, or NA in
    a rubric), or it may fail those cases.
-   An intermediate step needs no parser; the next step reads its raw output as
    `{step.<step_id>.output}`.
-   The last step's parser must return a number or
    `{"score": ..., "explanation": ...}`. With `sampling_count` above 1 it
    receives every sample; this one averages them.

**Doesn't catch:** answers that are true but don't do what was asked, or
mistakes in which tool was called.

**Other stage patterns:** generate evaluation steps first and then grade against
them (G-Eval); extract each turn's request and what it carries over, then judge
each turn (see [Multi-turn conversations](multi_turn.md)).

## Sources

-   Berkeley Function Calling Leaderboard (BFCL), in the Gorilla project (Apache
    2.0): https://github.com/ShishirPatil/gorilla
-   MT-Bench and LLM-as-a-judge (Zheng et al., 2023,
    https://arxiv.org/abs/2306.05685), judge prompts in FastChat (Apache 2.0):
    https://github.com/lm-sys/FastChat/tree/main/fastchat/llm_judge
-   TICK, "TICKing All the Boxes: Generated Checklists Improve LLM Evaluation
    and Generation" (Cook et al., 2024): https://arxiv.org/abs/2410.03608
-   Ragas faithfulness metric (Apache 2.0):
    https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
-   G-Eval (Liu et al., 2023): https://arxiv.org/abs/2303.16634

Prompts here are written for this skill; they follow the methods above and don't
copy their text.
