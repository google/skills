# Evals — Genkit Python (0.13 Only; Removed in 1.0)

> **Warning:** 0.13 is the last release with evaluators (`ai.define_evaluator`,
> `ai.define_batch_evaluator`, `ai.evaluate`, `genkit.evaluator`). Genkit 1.0
> cuts them and the `genkit-evaluators` package from the 1.0 release; evaluation
> will return as an additive feature in a later release. `genkit-evaluators`
> 0.13 requires `genkit<1`.
> - **New projects:** do not add `genkit-evaluators` or `define_evaluator`
>   unless you intend to stay pinned to `genkit==0.13.*`. Prefer `pytest`
>   assertions against your flows and prompts until evaluation returns.
> - **Migrating from 0.12:** stop and ask the developer before porting evaluator
>   code (see [Migrating from 0.12 to 0.13](migrating-from-0.12.md)).

The patterns below document the `0.13.*` evaluator API for projects staying on
the 0.13 release line.

- [Install (0.13 Only)](#install-013-only): Lines 27-31
- [Two Evaluator Types](#two-evaluator-types): Lines 33-41
- [Dataset Format](#dataset-format): Lines 43-56
- [Built-In Evaluators and Programmatic Execution](#built-in-evaluators-and-programmatic-execution): Lines 58-84
- [BYO Evaluator (EvaluatorResponse, Score, ScoreStatus, ScoreDetails)](#byo-evaluator-evaluatorresponse-score-scorestatus-scoredetails): Lines 86-131
- [LLM-Based Judge](#llm-based-judge): Lines 133-193
- [CLI Execution](#cli-execution): Lines 195-210

---

## Install (0.13 Only)

```bash
uv add 'genkit-evaluators==0.13.*'
```

## Two Evaluator Types

1. **Built-in** — provided by `genkit-evaluators`, registered via
   `register_genkit_evaluators(ai)` (`genkitEval/regex`,
   `genkitEval/deep_equal`, `genkitEval/jsonata`). They are deterministic and
   need no model plugin or `GEMINI_API_KEY`. Pass `metrics=['regex']` to
   register a subset.
2. **BYO** — custom row-by-row (`ai.define_evaluator`) or batch
   (`ai.define_batch_evaluator`) functions, including LLM judges.

## Dataset Format

`genkit eval:run` reads a JSON array:

```json
[
  {"testCaseId": "dessert", "input": "Suggest a dessert.", "output": "Banana bread", "reference": "(?i)banana"},
  {"testCaseId": "starter", "input": "Suggest a starter.", "output": "Tomato soup", "reference": "(?i)banana"}
]
```

**Fields:** `testCaseId`, `input`, `output`, `reference` (optional for
reference-free evaluators). In Python, the same rows are
`BaseDataPoint(test_case_id=..., input=..., output=..., reference=...)`.

## Built-In Evaluators and Programmatic Execution

```python
from genkit import Genkit
from genkit.evaluator import BaseDataPoint
from genkit_evaluators import register_genkit_evaluators

# 1. Register the built-in evaluators
ai = Genkit()
register_genkit_evaluators(ai)

# 2. Build the dataset
dataset = [
    BaseDataPoint(test_case_id='dessert', input='Suggest a dessert.', output='Banana bread', reference='(?i)banana'),
    BaseDataPoint(test_case_id='starter', input='Suggest a starter.', output='Tomato soup', reference='(?i)banana'),
]

# 3. Run one evaluator per call; returns list[EvaluatorResponse] in dataset order
results = await ai.evaluate(evaluator='genkitEval/regex', dataset=dataset)
for row in results:
    print(row.test_case_id, row.evaluation[0].score, row.evaluation[0].status)
# => dessert True PASS
#    starter False FAIL
```

`config=` is passed to the evaluator as its second argument (`None` when unset).
An unregistered evaluator name raises `GenkitError` with `NOT_FOUND`.

## BYO Evaluator (`EvaluatorResponse`, `Score`, `ScoreStatus`, `ScoreDetails`)

`ai.define_evaluator` takes `(name, fn)` positionally with required keyword-only
`display_name=` and `definition=`. `EvaluatorResponse` requires `test_case_id`,
and `evaluation` takes a `list[Score]`:

```python
from genkit.evaluator import (
    BaseDataPoint,
    EvaluatorResponse,
    Score,
    ScoreDetails,
    ScoreStatus,
)


async def exact_match(datapoint: BaseDataPoint, _options: object | None = None) -> EvaluatorResponse:
    output = str(datapoint.output or '').strip()
    reference = str(datapoint.reference or '').strip()
    passed = output == reference
    return EvaluatorResponse(
        test_case_id=datapoint.test_case_id or '',
        evaluation=[
            Score(
                score=1.0 if passed else 0.0,
                status=ScoreStatus.PASS if passed else ScoreStatus.FAIL,
                details=ScoreDetails(reasoning='Exact match check'),
            )
        ],
    )


ai.define_evaluator(
    'byo/exact_match',
    exact_match,
    display_name='Exact Match',
    definition='Checks exact match of output against reference.',
)
```

For batch evaluation across the whole dataset at once, register
`async def my_batch_eval(req: EvaluatorRequest) -> list[EvaluatorResponse]:`
with
`ai.define_batch_evaluator('byo/batch', my_batch_eval, display_name='...',
definition='...')` (`from genkit.evaluator import EvaluatorRequest`). The batch
function takes exactly one argument; read options from `req.options`.

## LLM-Based Judge

`prompts/judge.prompt` (load it with `Genkit(prompt_dir='prompts', ...)`;
`prompts/` is the default):

```yaml
---
model: googleai/gemini-flash-latest
input:
  schema:
    output: string
    reference: string
---
Score how well the candidate matches the reference from 0.0 to 1.0.
Reply with ONLY a number (e.g. 0.8), nothing else.

Reference: {{reference}}
Candidate: {{output}}
```

```python
from genkit import Genkit
from genkit.evaluator import BaseDataPoint, EvaluatorResponse, Score, ScoreStatus
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()])


async def llm_judge(datapoint: BaseDataPoint, _options: object | None = None) -> EvaluatorResponse:
    # 1. Run the judge prompt; the model comes from the .prompt frontmatter
    response = await ai.prompt('judge')(
        {'output': str(datapoint.output), 'reference': str(datapoint.reference)}
    )

    # 2. Parse the score; treat anything unparseable as 0.0
    try:
        score = min(max(float((response.text or '').strip()), 0.0), 1.0)
    except ValueError:
        score = 0.0

    return EvaluatorResponse(
        test_case_id=datapoint.test_case_id or '',
        evaluation=[Score(score=score, status=ScoreStatus.PASS if score >= 0.5 else ScoreStatus.FAIL)],
    )


ai.define_evaluator(
    'byo/llm_judge',
    llm_judge,
    display_name='LLM Judge',
    definition='Scores candidate vs reference with a judge model.',
    is_billed=True,
)
```

`is_billed=True` makes `genkit eval:run` ask for confirmation before calling the
model; pass `--force` in CI.

Built-in `genkitEval/regex` and `genkitEval/deep_equal` scores are `bool`
(`True` / `False`); BYO numeric scores are typically `0.0`–`1.0`. Normalize
before aggregating.

## CLI Execution

`genkit eval:run` requires an active Genkit runtime (either already running via
`genkit start` or launched inline after `--`):

```bash
# One-shot: launches the app runtime, evaluates, and exits
genkit eval:run datasets/menu_dataset.json --evaluators=genkitEval/regex,byo/exact_match -- uv run src/main.py

# Write machine-readable results to a file (--output-format json|csv, default json)
genkit eval:run datasets/menu_dataset.json --evaluators=byo/exact_match --output=eval_out.json -- uv run src/main.py
```

Omitting `--evaluators` runs every registered evaluator. `No runtimes found`
means no Genkit runtime is active — pass `-- uv run src/main.py` or run
`genkit start` in another terminal.
