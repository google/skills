---
name: agent-platform-eval-flywheel
description: >-
  Measure and improve the quality of AI models and agents on Google Cloud
  using the Eval Quality Flywheel methodology. Use when evaluating an agent or
  model, building an eval dataset, picking or writing evaluation metrics,
  analyzing failures, comparing results before and after a fix, or when
  guidance is needed on Agent Platform eval methodology — including
  dataset schema, LLM-as-judge scoring, and common failure causes. For
  fine-tuning, use agent-platform-tuning. For deployment, use
  agent-platform-deploy.
---

# Agent Platform Eval Flywheel Skill

Help users evaluate and iteratively improve GenAI models and agents using
the Agent Platform GenAI Evaluation SDK (`google.genai` / `agentplatform`).

## When to use this skill

-   Evaluating GenAI agents or models with the Agent Platform GenAI
    Evaluation SDK (`client.evals.evaluate()`).
-   Creating evaluation datasets from session traces, pandas DataFrames, or
    synthetic generation.
-   Selecting, configuring, or writing custom evaluation metrics.
-   Analyzing rubric verdicts, loss patterns, and clustering failures.
-   Suggesting concrete code/prompt improvements based on eval results.
-   Evaluating a model served on an Agent Platform **endpoint** (BYOM) or a
    **Model-as-a-Service (MaaS)** model by ID — including deploying the model
    first if needed. For this case, follow
    [references/deployment.md](references/deployment.md) and use the
    `endpoint_evaluation.py` / `maas_evaluation.py` scripts.

## Setup

Install the SDK:

```bash
pip install google-cloud-aiplatform[evaluation]>=1.154.0 google-genai>=1.0.0
```

Need `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`. Check env vars
first; if missing, ask the user. Newer Gemini models often need
`location="global"`.

## The Quality Flywheel

Five stages, run in order on the first pass, then loop 2 → 5 until quality
targets are met.

### Shortcuts that waste time

| Shortcut                                                 | Why it fails                                                                                              |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| "I'll tune the metric threshold down so it passes."      | Hides real failures. Fix the agent, not the bar.                                                          |
| "This case is flaky, I'll skip it."                      | Flakiness reveals non-determinism in the agent. Fix with `temperature=0` or stricter instructions.        |
| "I just need to fix the eval dataset, not the agent."    | If expected outputs keep moving, the agent has a behavior problem.                                        |
| "I can tell from the trace it works — skip Stage 3."     | Self-grading doesn't generalize. Always run `evaluate()` and read scores.                                 |
| "One iteration is enough."                               | Expect 5–10+ iterations. Stopping early leaves regressions on other metrics undetected.                   |

### 1. Prepare Data

Produce an `EvaluationDataset`. There are three input shapes, pick the one
that matches the data the user already has:

-   **`EvalCase` list (single-turn or multi-turn):**

    ```python
    from agentplatform import types
    dataset = types.EvaluationDataset(eval_cases=[
        types.EvalCase(prompt="What is 2+2?", response="4", reference="4"),
        # For multi-turn agent traces, set agent_data instead of prompt/response.
    ])
    ```

    Multi-turn agent traces wrap each conversation in `AgentData` →
    `ConversationTurn` → `AgentEvent`. See
    [references/dataset_schema.md](references/dataset_schema.md) for the
    full type hierarchy.

-   **Pandas DataFrame (tabular sources — CSV, BigQuery, Sheets):**

    ```python
    import pandas as pd
    from agentplatform import types

    df = pd.DataFrame({
        "prompt":    ["What is 2+2?", "Capital of France?"],
        "response":  ["4",            "Paris"],
        "reference": ["4",            "Paris"],
    })
    dataset = types.EvaluationDataset(eval_dataset_df=df)
    ```

    Column names must match the fields the chosen metrics expect (see
    [references/dataset_schema.md](references/dataset_schema.md) for the
    per-metric requirements table).

-   **Cold start (no data at all):** synthesize scenarios server-side with
    `client.evals.generate_user_scenarios(...)` and a
    `UserScenarioGenerationConfig` (`user_scenario_count`,
    `simulation_instruction`, `environment_data`). Stage 2 plays them out.

For ADK session dumps, use `scripts/parse_adk_traces.py` instead of writing
the conversion by hand.

### 2. Run Inference

Populate responses/traces on the dataset. **Skip this stage** if traces are
already complete (e.g., production logs or replay).

```python
# Agent eval — pass a callable wrapping the user's ADK Agent/App.
client.evals.run_inference(model=agent_callable, src=dataset)

# Model eval — pass a model ID directly.
client.evals.run_inference(model="gemini-2.5-flash", src=dataset)

# Synthesized scenarios — let the simulator drive.
client.evals.run_inference(
    model=agent_callable,
    src=dataset,
    user_simulator_config=UserSimulatorConfig(max_turn=10),
)

# DataFrame also works as src= — no EvalCase wrapping needed.
client.evals.run_inference(model="gemini-2.5-flash", src=df)
```

### 3. Grade (always run)

```python
result = client.evals.evaluate(dataset=dataset, metrics=[...])
```

**Pick metrics by what you want to measure.** Full catalog in
[references/metric_registry.md](references/metric_registry.md).

**Agent metrics (multi-turn, adaptive rubrics)** — start here for agent eval.

| Goal                                          | Metric                          |
| --------------------------------------------- | ------------------------------- |
| Did the agent achieve the user's goal?        | `multi_turn_task_success`       |
| Was the reasoning path logical and efficient? | `multi_turn_trajectory_quality` |
| Tool/function calling quality across turns    | `multi_turn_tool_use_quality`   |
| Overall conversational quality                | `multi_turn_general_quality`    |
| Final response quality (no reference needed)  | `final_response_quality`        |
| Final response vs. a golden reference         | `final_response_match`          |
| Single-turn tool use                          | `tool_use_quality`              |

**General quality metrics (single-turn, adaptive rubrics)** — for model eval.

| Goal                                                  | Metric                  |
| ----------------------------------------------------- | ----------------------- |
| Overall response quality (recommended starting point) | `general_quality`       |
| Linguistic quality (fluency, coherence, grammar)      | `text_quality`          |
| Adherence to specific constraints / instructions      | `instruction_following` |

**Static rubric metrics (fixed criteria)** — apply alongside the above.

| Goal                                              | Metric          |
| ------------------------------------------------- | --------------- |
| Catch hallucinated claims (RAG, factual answers)  | `hallucination` |
| Factuality / consistency against provided context | `grounding`     |
| Safety policy compliance                          | `safety`        |

**Domain-specific check no built-in covers:** write a custom metric.

-   **Predefined:** `types.RubricMetric.<NAME>` — server-side AutoRater, no
    judge model needed.
-   **Custom LLM-as-a-judge:** `types.LLMMetric` with `prompt_template` or
    `types.MetricPromptBuilder` for structured rubrics.
-   **Custom code:** `types.CodeExecutionMetric` with a `custom_function`
    string containing `def evaluate(instance: dict)` for remote sandboxed
    execution; or `types.Metric` with `custom_function=<callable>` for
    local execution.

**Always persist the result** so Stage 4 and 5 can read it. Save both JSON
(machine-readable, diffable) and HTML (human-readable, linkable):

```python
import datetime
from pathlib import Path

from agentplatform._genai import _evals_visualization

out_dir = Path("artifacts/grade_results")
out_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

result_json = result.model_dump_json()
(out_dir / f"results_{ts}.json").write_text(result_json)

html = _evals_visualization.get_evaluation_html(result_json)
(out_dir / f"results_{ts}.html").write_text(str(html))
```

Or after the fact: `scripts/render_html_report.py --type evaluation` or
`scripts/inspect_results.py --save-html`.

### 4. Analyze Failures

Read `summary_metrics` and `eval_case_results` — never fabricate scores.
Use `scripts/inspect_results.py --failing-only` to filter to failures.

For each failed metric, see
[references/failure_patterns.md](references/failure_patterns.md) for deeper
diagnoses. The compact mapping:

| Failing metric                       | What to change                                                                                                            |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `multi_turn_task_success` low        | The agent isn't completing the goal — fix orchestration, missing tool calls, premature termination, wrong tool selection. |
| `multi_turn_trajectory_quality` low  | The agent reaches the goal inefficiently — refine planning prompts, remove redundant tool calls.                          |
| `multi_turn_tool_use_quality` low    | Fix tool descriptions, parameter docstrings, or agent instructions for tool selection.                                    |
| `final_response_quality` low         | Read auto-generated rubric verdicts; refine instructions to address the worst-scoring criterion.                          |
| `final_response_match` low           | The agent's final answer doesn't match the golden reference — adjust response format or update the reference.             |
| `hallucination` low                  | Tighten instructions to stay grounded in tool output; verify the tool actually returned the claimed data.                 |
| `grounding` low                      | The response contradicts the provided context — add explicit "cite only from context" instructions.                       |
| `safety` low                         | Add safety guardrails; review the violating content category in the rubric verdict.                                       |
| `general_quality` / `text_quality` low | Adjust system instruction wording; the model's default phrasing is too generic for the task.                            |
| `instruction_following` low          | The agent is ignoring constraints — restate them in the system instruction or use stricter wording.                       |
| Agent calls wrong tools              | Fix tool descriptions, agent instructions, or `tool_config`.                                                              |
| Agent calls extra tools              | Add explicit stop instructions, or switch to `multi_turn_tool_use_quality` to surface the extra calls in the rubric.      |

**For 10+ failures on the same metric**, use the **Error Analysis service**
to cluster failures into themes (L1/L2 taxonomy categories) instead of
reading every trace:

```python
# Only supports multi_turn_task_success and multi_turn_tool_use_quality.
# Service runs in the global region.
analysis_client = agentplatform.Client(project="PROJECT_ID", location="global")
response = analysis_client.evals.generate_loss_clusters(
    eval_result=result,
    metric="multi_turn_task_success",
    config={"max_top_cluster_count": 5},
)
for r in response.results:
    for cluster in r.clusters:
        print(
            f"[{cluster.taxonomy_entry.l1_category}/"
            f"{cluster.taxonomy_entry.l2_category}] "
            f"{cluster.item_count} cases — {cluster.taxonomy_entry.description}"
        )
```

Save `response.model_dump_json()` and render with
`scripts/render_html_report.py --type loss-analysis`.

### 5. Optimize & Iterate

Apply a fix targeting the failing metric. Re-run Stage 3. Compare with
`scripts/compare_results.py --baseline <prev> --candidate <new>` to confirm
the target improved AND no other metric regressed.

Track progress across iterations:

| Iteration | Metric A | Metric B | Change made             |
| --------- | -------- | -------- | ----------------------- |
| Baseline  | 0.62     | 0.55     | —                       |
| v2        | 0.78     | 0.68     | Added grounding prompt  |
| v3        | 0.81     | 0.72     | Fixed tool selection    |

Expect 5–10+ iterations per failing case. Only after a case passes should
you expand coverage with more eval cases.

## Proving your work

Never claim eval results you didn't read from an actual `result` object.

-   After running eval, print the `summary_metrics` table
    (`scripts/inspect_results.py`).
-   After a fix, show before/after via `scripts/compare_results.py`.
-   Before declaring success, confirm ALL cases pass — not just the one you
    were working on.

If you can't produce the evidence (SDK call failed, result truncated,
metric unsupported), say so explicitly. Don't paper over gaps.

## Rules of Engagement

1.  **Always Plan First:** Before writing a script, output a `<plan>` block
    detailing the steps you are about to take.
2.  **Step-by-Step Execution:** Write the script, execute it, wait for
    output, then analyze. Don't do everything in one response.
3.  **Standard Python:** Use standard Python imports (`import
    agentplatform`, `from google.genai import types`). Don't use internal
    import paths.
4.  **Verify Before Guessing:** When unsure about SDK types or metrics,
    check the SDK source code rather than guessing or hallucinating.

## SDK Quick Reference

```python
import agentplatform
from agentplatform import types
from google.genai import types as genai_types
import pandas as pd

# Initialize client
client = agentplatform.Client(project="PROJECT_ID", location="LOCATION")

# --- SINGLE-TURN EVAL (EvalCase list) ---
dataset = types.EvaluationDataset(eval_cases=[
    types.EvalCase(prompt="Query here", response="Model response here"),
])

# --- SINGLE-TURN EVAL (pandas DataFrame) ---
df = pd.DataFrame({
    "prompt":   ["Q1", "Q2"],
    "response": ["A1", "A2"],
})
dataset = types.EvaluationDataset(eval_dataset_df=df)

# --- MULTI-TURN AGENT EVAL ---
agent_data = types.evals.AgentData(
    agents={"my_agent": types.evals.AgentConfig(
        agent_id="my_agent", instruction="You are helpful.")},
    turns=[types.evals.ConversationTurn(turn_index=0, events=[
        types.evals.AgentEvent(author="user",
            content=genai_types.Content(role="user",
                parts=[genai_types.Part(text="Hello")])),
        types.evals.AgentEvent(author="my_agent",
            content=genai_types.Content(role="model",
                parts=[genai_types.Part(text="Hi! How can I help?")])),
    ])],
)
dataset = types.EvaluationDataset(
    eval_cases=[types.EvalCase(agent_data=agent_data)])

# --- METRICS ---
predefined = types.RubricMetric.MULTI_TURN_TRAJECTORY_QUALITY
custom_llm = types.LLMMetric(name="tone",
    prompt_template="Is this polite? Response: {response}")
custom_code = types.CodeExecutionMetric(name="check",
    custom_function='def evaluate(instance): return {"score": 1.0}')

# --- EVALUATE ---
result = client.evals.evaluate(dataset=dataset, metrics=[predefined])

# --- RESULTS ---
for s in result.summary_metrics:
    print(f"{s.metric_name}: mean={s.mean_score}, pass_rate={s.pass_rate}")
for case in result.eval_case_results:
    for cand in case.response_candidate_results:
        for name, r in cand.metric_results.items():
            print(f"  {name}: score={r.score}, explanation={r.explanation}")
```

See [references/sdk_patterns.md](references/sdk_patterns.md) for advanced
patterns: synthetic data generation, pairwise comparison,
`MetricPromptBuilder`, multi-agent evaluation.

## Bundled scripts

Script                   | When to use
------------------------ | -----------
`validate_dataset.py`    | Before Stage 3 — catch malformed `EvaluationDataset` JSON.
`parse_adk_traces.py`    | Stage 1 — convert ADK session dumps to the canonical dataset shape.
`inspect_results.py`     | Stages 3/4 — render summary + per-case scores. `--save-html` for a browsable report.
`compare_results.py`     | Stage 5 — diff baseline vs. candidate, detect regressions.
`render_html_report.py`  | Render HTML from a saved result JSON or loss-clusters JSON.
`endpoint_evaluation.py` | Stages 2/3 against a deployed Agent Platform endpoint (BYOM). See [references/deployment.md](references/deployment.md).
`maas_evaluation.py`     | Stages 2/3 against a Model-as-a-Service model by ID. See [references/deployment.md](references/deployment.md).
