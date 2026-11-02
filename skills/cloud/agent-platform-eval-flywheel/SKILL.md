---
name: agent-platform-eval-flywheel
metadata:
  version: "1.0.4"
  category: AiAndMachineLearning
description: >-
  Measures and improves the quality of AI models and agents on Google Cloud
  using the Eval Quality Flywheel methodology. Use when generating synthetic
  user scenarios, evaluating an agent or model, building an eval dataset,
  picking or writing evaluation metrics, analyzing failures, comparing results
  before and after a fix, or when guidance is needed on Agent Platform eval
  methodology — including dataset schema, LLM-as-judge scoring, and common
  failure causes. For fine-tuning, use agent-platform-tuning. For general
  production deployment, use agent-platform-deploy.
---

# Agent Platform Eval Flywheel Skill

Help users evaluate and iteratively improve GenAI models and agents using the
Agent Platform GenAI Evaluation SDK (`google.genai` / `agentplatform`).

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` and append the
attribution suffix to `User-Agent` headers:

```text
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-eval-flywheel)"
User-Agent: <existing_user_agent> agent-skills/1.0 (skill:agent-platform-eval-flywheel)
```

## When to use this skill

-   Evaluating GenAI agents or models with the Agent Platform GenAI Evaluation
    SDK (`client.evals.evaluate()`).
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

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands or scripts on behalf of the user, you MUST adhere
to the following safety tiers based on the action requested:

1.  **Tier R**: Read-only (`inspect_results.py`, `compare_results.py`,
    `validate_dataset.py`, `parse_adk_traces.py`, `render_html_report.py`)
    *   **Rule**: No confirmation needed. You may execute these helper scripts
        immediately to inspect data, validate schemas, parse traces, or compare
        evaluation results.
2.  **Tier M: Evaluation & Generation Runs (`client.evals.run_inference`,
    `client.evals.evaluate`, `client.evals.generate_conversation_scenarios`,
    `client.evals.generate_loss_clusters`)**
    *   **Rule**: For predictable user approval over dataset reads, result
        writes (`dest`), and remote compute/API usage, every call to
        `client.evals.evaluate()`, `client.evals.run_inference()`,
        `client.evals.generate_conversation_scenarios()`, or
        `client.evals.generate_loss_clusters()` — whether using remote metrics
        (LLM/rubric metrics or sandboxed `types.CodeExecutionMetric`) or local
        in-process metrics (`types.Metric` with a Python callable) — requires
        presenting a dry-run confirmation preview showing the proposed
        evaluation call and parameters and waiting for explicit 'Yes'/'No' user
        approval (do not quote remote compute charges when only local in-process
        `types.Metric` callables are used without `dest` or model inference).
    *   **Confirmation for EVERY evaluation run**: Every evaluation,
        re-evaluation, metric update, parameter change, or synthetic scenario
        generation requires its own dry-run preview and interactive
        confirmation. Never execute a second evaluation, comparison pass, or
        modified evaluation without presenting a new confirmation preview and
        obtaining user approval.
    *   **Same-turn restriction**: Do not run the evaluation in the same turn as
        presenting the confirmation prompt. End your turn after asking and wait
        for the user's reply; only execute after explicit 'Yes' / approval.
        Printing a preview and then calling the tool before the user can answer
        does not count as obtaining confirmation.
    *   **No Pre-Execution of Evaluation Calls**: NEVER execute
        `client.evals.evaluate()`, `client.evals.run_inference()`,
        `client.evals.generate_conversation_scenarios()`, or run any script
        invoking these SDK methods before user confirmation. In the initial
        turn, you may write the evaluation script to disk, but you MUST present
        the dry-run confirmation preview and obtain explicit user confirmation
        before running `client.evals.evaluate()`.
    *   **Immediate Execution Upon Approval**: Once the user explicitly approves
        (e.g., 'Yes', 'Approved', 'Go ahead', 'Proceed'), proceed directly to
        executing the previewed evaluation script via `run_command` and report
        the results. Do not conclude the turn without executing the approved
        action.

## Setup

The scripts need `vertexai` (from `google-cloud-aiplatform[evaluation]`),
`google-genai`, `pandas`, and `requests`. Do **not** create a virtual
environment — it starts empty and hides packages the environment already
provides, forcing a redundant install. Probe, and install only what is missing:

```bash
python3 -c "import vertexai, google.genai, pandas, requests" \
  || pip install 'google-cloud-aiplatform[evaluation]>=1.163.0' 'google-genai>=1.0.0'
```

The version specifiers must stay quoted: unquoted, bash reads `>=1.154.0` as a
redirect and silently writes an empty file instead of constraining the install.

Need `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.

-   **Preserve User Project and Location**: Always prioritize the user's
    explicitly provided project and location (e.g. `project='<PROJECT_NUMBER>'`,
    `location='us-central1'`). Never change or override the user's requested
    location to 'global' unless the user explicitly requested 'global'.
-   **Missing Parameters**: If the user's request omits the project or location,
    you MUST pause in your response and ask the user for the missing
    location/project before preparing or running the evaluation.

### Correct SDK entrypoints

```python
import agentplatform
client = agentplatform.Client(project=PROJECT, location=LOCATION)

client.evals.run_inference(model=..., src=...)
client.evals.evaluate(dataset=..., metrics=...)
client.evals.generate_conversation_scenarios(...)
```

Two imports that look plausible and are not:

-   `from agentplatform.types import evals` -- `ModuleNotFoundError`. `types` is
    a module, not a package; use `from agentplatform import types`.
-   `from vertexai.evaluation import PointwiseMetric, EvalTask` -- the
    superseded SDK. Its classes take different arguments (`PointwiseMetric` has
    no `system_instruction`), so code written against it fails with `TypeError`
    rather than an import error. Use `agentplatform` throughout.

## The Quality Flywheel

Five stages, run in order on the first pass, then loop 2 → 5 until quality
targets are met.

### Shortcuts that waste time

| Shortcut                             | Why it fails                         |
| ------------------------------------ | ------------------------------------ |
| "I'll tune the metric threshold down | Hides real failures. Fix the agent,  |
: so it passes."                       : not the bar.                         :
| "This case is flaky, I'll skip it."  | Flakiness reveals non-determinism in |
:                                      : the agent. Fix with `temperature=0`  :
:                                      : or stricter instructions.            :
| "I just need to fix the eval         | If expected outputs keep moving, the |
: dataset, not the agent."             : agent has a behavior problem.        :
| "I can tell from the trace it works  | Self-grading doesn't generalize.     |
: — skip Stage 3."                     : Always run `evaluate()` and read     :
:                                      : scores.                              :
| "One iteration is enough."           | Expect 5–10+ iterations. Stopping    |
:                                      : early leaves regressions on other    :
:                                      : metrics undetected.                  :

### 1. Prepare Data

Produce an `EvaluationDataset`. There are three input shapes, pick the one that
matches the data the user already has:

-   **`EvalCase` list (single-turn or multi-turn):**

    ```python
    from agentplatform import types
    from google.genai import types as genai_types

    # prompt/reference/response values are Content, not str. UserContent and
    # ModelContent wrap a plain string and set the right role.
    dataset = types.EvaluationDataset(eval_cases=[
        types.EvalCase(
            prompt=genai_types.UserContent("What is 2+2?"),
            responses=[types.ResponseCandidate(
                response=genai_types.ModelContent("4"))],
            reference=types.ResponseCandidate(
                response=genai_types.ModelContent("4")),
        ),
        # For multi-turn agent traces, set agent_data instead of prompt/responses.
    ])
    ```

    Multi-turn agent traces wrap each conversation in `AgentData` →
    `ConversationTurn` → `AgentEvent`. See
    [references/dataset_schema.md](references/dataset_schema.md) for the full
    type hierarchy.

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
    `client.evals.generate_conversation_scenarios(agent=..., config=...)` -- the
    parameter is `agent` or `agent_info`, not `agents`, and `config` is
    required. The config class is `types.evals.UserScenarioGenerationConfig`,
    not `types.UserScenarioGenerationConfig`. Set its `user_scenario_count`
    (1-100): it defaults to None, the client accepts that, and the server
    rejects the call with `400 INVALID_ARGUMENT`. `count` is a separate field
    and does not substitute for it. Stage 2 plays the scenarios out.
    *   **CRITICAL - Multi-turn user-simulation scenarios must use this API**:
        When the user asks to synthesize multi-turn **user scenarios** to
        simulate customers interacting with an agent (as opposed to writing a
        local single-turn test dataset in the sandbox), never author the
        conversation scenarios yourself in prose or a handwritten file. Calling
        `client.evals.generate_conversation_scenarios` is a server-side Tier M
        API call (using the user's project, location, model, and environment
        data) and requires a confirmation card; local single-turn dataset files
        written in the sandbox without calling Agent Platform APIs are Tier R.
    *   **CRITICAL - Underspecified Requests**: When asked to synthesize
        scenarios, if the request omits required parameters (such as `location`,
        `environment_data`, `simulation_instruction`, or `model_name`), do NOT
        assume defaults or guess values. You MUST pause in your first turn and
        explicitly ask the user for the missing information (e.g., "Please
        provide the missing simulation instructions, environment data, model
        name, and location"). Only proceed with the dry-run preview after the
        user provides them. `location` has no safe default: neither
        `us-central1` nor a location you assumed on your own for another call is
        a substitute for a location the user has not given.
    *   **Friction & Parameter Changes**: When asked to generate synthetic user
        scenarios, if the user modifies requested parameters (such as scenario
        count, model, or instructions) or pushes back, you MUST present a
        revised dry-run confirmation card with the updated parameters and wait
        for explicit user approval before executing generation code via
        `run_command`.

-   **Managed Agents (Gemini Agents API):** evaluate agents created with the
    [Managed Agents API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/managed-agents).
    Use `generate_conversation_scenarios` to create test scenarios from the
    agent's configuration, `run_inference` to execute the agent, and `evaluate`
    to score the traces. These functions now accept managed agents and
    interaction ids as input. You can also evaluate existing interactions
    recorded via the Interactions API using `InteractionsDataSource`. See
    [references/sdk_patterns.md](references/sdk_patterns.md) Pattern 8 for the
    full code pattern.

For ADK session dumps, use `scripts/parse_adk_traces.py` instead of writing the
conversion by hand.

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

# Managed Agent — pass an agent resource name.
AGENT_RESOURCE = f"projects/{PROJECT_ID}/locations/global/agents/{AGENT_ID}"
client.evals.run_inference(
    agent=AGENT_RESOURCE,
    src=scenarios,
    config={"user_simulator_config": {"max_turn": 3}},
)
```

### 3. Grade (always run)

```python
result = client.evals.evaluate(dataset=dataset, metrics=[...])
result.show()  # Interactive HTML report with scores, rubrics, and traces.
```

**Pick metrics by what you want to measure.** Full catalog in
[references/metric_registry.md](references/metric_registry.md).

**If the user names a metric, use it directly.** Every identifier in the tables
below (`general_quality`, `text_quality`, `instruction_following`,
`hallucination`, `grounding`, `safety`, `multi_turn_*`, `final_response_*`,
`tool_use_quality`) is a `types.RubricMetric.<UPPERCASE_NAME>` accessor — pass
it straight into `metrics=[types.RubricMetric.GENERAL_QUALITY, ...]`. Do not
scaffold a custom `LLMMetric` for a name that appears here, and do not reach for
`vertexai.evaluation.EvalTask` / `PointwiseMetric` /
`MetricPromptTemplateExamples` — that SDK is superseded (see Setup).

**`judge_model` format and handling user-named models:**

*   **Full resource name required for `judge_model`**: Both `LLMMetric` and
    `RubricMetric` send `judge_model` as `autorater_config.autorater_model` to
    the backend (even though `agentplatform` logs a client-side "ignored"
    warning on `RubricMetric`). Short names like `"gemini-2.5-flash"` or
    `"gemini-2.5-pro"` fail with `400 INVALID_ARGUMENT ("Invalid autorater model
    resource name")`. Always pass the full publisher model resource name:
    `f"projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{MODEL_NAME}"`
    (prefer `gemini-2.5-flash` as autorater; `gemini-2.5-pro` can intermittently
    fail server-side with `"Rubric results could not be reliably computed"`).
*   **Datasets without vs. with responses**:
    *   If the dataset contains **prompts only** (no `response` column), call
        `run_inference(model="<the named model>", src=dataset)` to generate the
        candidate model's responses first, then grade them with `evaluate()`.
    *   If the user **already supplies `response`s** in the dataset, **do NOT
        call `run_inference`** — `run_inference` overwrites the existing
        `response` column with the model's generated output and discards the
        user's responses! Instead, grade the user's supplied `response`s
        directly with `evaluate(dataset=dataset, ...)`, passing the named model
        as the full resource path in `judge_model` (or if a predefined
        `RubricMetric` cannot reliably compute rubric results with that
        autorater model, fall back to the default autorater and explain why).

**Agent metrics (multi-turn, adaptive rubrics)** — start here for agent eval.

Goal                                          | Metric
--------------------------------------------- | -------------------------------
Did the agent achieve the user's goal?        | `multi_turn_task_success`
Was the reasoning path logical and efficient? | `multi_turn_trajectory_quality`
Tool/function calling quality across turns    | `multi_turn_tool_use_quality`
Overall conversational quality                | `multi_turn_general_quality`
Final response quality (no reference needed)  | `final_response_quality`
Final response vs. a golden reference         | `final_response_match`
Single-turn tool use                          | `tool_use_quality`

**General quality metrics (single-turn, adaptive rubrics)** — for model eval.

Goal                                                  | Metric
----------------------------------------------------- | -----------------------
Overall response quality (recommended starting point) | `general_quality`
Linguistic quality (fluency, coherence, grammar)      | `text_quality`
Adherence to specific constraints / instructions      | `instruction_following`

**Static rubric metrics (fixed criteria)** — apply alongside the above.

Goal                                              | Metric
------------------------------------------------- | ---------------
Catch hallucinated claims (RAG, factual answers)  | `hallucination`
Factuality / consistency against provided context | `grounding`
Safety policy compliance                          | `safety`

**Domain-specific check no built-in covers:** write a custom metric.

-   **Predefined:** `types.RubricMetric.<NAME>` — server-side AutoRater, no
    judge model needed.
-   **Custom LLM-as-a-judge:** `types.LLMMetric` with `prompt_template` or
    `types.MetricPromptBuilder` for structured rubrics. Always set
    `judge_model`; it defaults to `None` and every case then fails with `400
    INVALID_ARGUMENT: Error parsing JSON`.
    *   **Judge Model Selection**: If the user specifies a judge model (e.g.
        `gemini-2.5-pro`), use it. If the user omits the judge model or states
        they do not have information / preference for one, default to
        `gemini-2.5-flash` as the judge model in the dry-run preview card and
        ask for confirmation to run the evaluation. Do NOT halt or refuse to
        evaluate when the user does not specify a judge model.
-   **Custom code:** `types.CodeExecutionMetric` with a `custom_function` string
    containing `def evaluate(instance: dict)` for remote sandboxed execution; or
    `types.Metric` with `custom_function=<callable>` for local execution. The
    `instance` dict's `prompt` / `response` / `reference` are `Content` dicts,
    not strings; read
    [references/metric_registry.md](references/metric_registry.md) ("What the
    function receives") before writing the body, rather than discovering the
    shape by running the evaluation.

**Always persist the result** so Stage 4 and 5 can read it. Save both JSON
(machine-readable, diffable) and HTML (human-readable, linkable):

```python
import datetime
from pathlib import Path

from agentplatform._genai import _evals_visualization

out_dir = Path("artifacts/grade_results")
out_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# fallback=str, or a DataFrame-backed dataset raises PydanticSerializationError.
result_json = result.model_dump_json(fallback=str)
(out_dir / f"results_{ts}.json").write_text(result_json)

html = _evals_visualization.get_evaluation_html(result_json)
(out_dir / f"results_{ts}.html").write_text(str(html))
```

Or after the fact: `scripts/render_html_report.py --type evaluation` or
`scripts/inspect_results.py --save-html`.

### 4. Analyze Failures

Read `summary_metrics` and `eval_case_results` — never fabricate scores. Use
`scripts/inspect_results.py --failing-only` to filter to failures.

For each failed metric, see
[references/failure_patterns.md](references/failure_patterns.md) for deeper
diagnoses. The compact mapping:

| Failing metric                      | What to change                         |
| ----------------------------------- | -------------------------------------- |
| `multi_turn_task_success` low       | The agent isn't completing the goal —  |
:                                     : fix orchestration, missing tool calls, :
:                                     : premature termination, wrong tool      :
:                                     : selection.                             :
| `multi_turn_trajectory_quality` low | The agent reaches the goal             |
:                                     : inefficiently — refine planning        :
:                                     : prompts, remove redundant tool calls.  :
| `multi_turn_tool_use_quality` low   | Fix tool descriptions, parameter       |
:                                     : docstrings, or agent instructions for  :
:                                     : tool selection.                        :
| `final_response_quality` low        | Read auto-generated rubric verdicts;   |
:                                     : refine instructions to address the     :
:                                     : worst-scoring criterion.               :
| `final_response_match` low          | The agent's final answer doesn't match |
:                                     : the golden reference — adjust response :
:                                     : format or update the reference.        :
| `hallucination` low                 | Tighten instructions to stay grounded  |
:                                     : in tool output; verify the tool        :
:                                     : actually returned the claimed data.    :
| `grounding` low                     | The response contradicts the provided  |
:                                     : context — add explicit "cite only from :
:                                     : context" instructions.                 :
| `safety` low                        | Add safety guardrails; review the      |
:                                     : violating content category in the      :
:                                     : rubric verdict.                        :
| `general_quality` / `text_quality`  | Adjust system instruction wording; the |
: low                                 : model's default phrasing is too        :
:                                     : generic for the task.                  :
| `instruction_following` low         | The agent is ignoring constraints —    |
:                                     : restate them in the system instruction :
:                                     : or use stricter wording.               :
| Agent calls wrong tools             | Fix tool descriptions, agent           |
:                                     : instructions, or `tool_config`.        :
| Agent calls extra tools             | Add explicit stop instructions, or     |
:                                     : switch to                              :
:                                     : `multi_turn_tool_use_quality` to       :
:                                     : surface the extra calls in the rubric. :

**For 10+ failures on the same metric**, use the **Error Analysis service** to
cluster failures into themes (L1/L2 taxonomy categories) instead of reading
every trace:

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

Save `response.model_dump_json()` and render with `scripts/render_html_report.py
--type loss-analysis`.

### 5. Optimize & Iterate

Apply a fix targeting the failing metric. Re-run Stage 3. Compare with
`scripts/compare_results.py --baseline <prev> --candidate <new>` to confirm the
target improved AND no other metric regressed.

Track progress across iterations:

Iteration | Metric A | Metric B | Change made
--------- | -------- | -------- | ----------------------
Baseline  | 0.62     | 0.55     | —
v2        | 0.78     | 0.68     | Added grounding prompt
v3        | 0.81     | 0.72     | Fixed tool selection

Expect 5–10+ iterations per failing case. Only after a case passes should you
expand coverage with more eval cases.

## Proving your work

Never claim eval results you didn't read from an actual `result` object.

-   After running eval, print the `summary_metrics` table
    (`scripts/inspect_results.py`).
-   After a fix, show before/after via `scripts/compare_results.py`.
-   Before declaring success, confirm ALL cases pass — not just the one you were
    working on.

If you can't produce the evidence (SDK call failed, result truncated, metric
unsupported), say so explicitly. Don't paper over gaps.

## Rules of Engagement

1.  **Always Plan First:** Before writing a script, output a `<plan>` block
    detailing the steps you are about to take.
2.  **Step-by-Step Execution:** Prepare the data and evaluation script, present
    the dry-run confirmation card with full parameters, wait for user approval,
    execute only after explicit confirmation, then inspect and analyze results.
    Do NOT run evaluation calls before user confirmation.
3.  **Standard Python:** Use standard Python imports (`import agentplatform`,
    `from google.genai import types`). Don't use internal import paths.
4.  **Verify Before Guessing:** When unsure about SDK types or metrics, check
    the SDK source code rather than guessing or hallucinating.
5.  **Never End a Turn Silently:** Every turn must end with a non-empty,
    informative text reply to the user summarizing the actions taken or
    presenting the next steps. Returning nothing reads as a failure no matter
    what the tools did.

## SDK Quick Reference

```python
import agentplatform
from agentplatform import types
from google.genai import types as genai_types
import pandas as pd

# Initialize client
client = agentplatform.Client(project="PROJECT_ID", location="LOCATION")

# --- SINGLE-TURN EVAL (pandas DataFrame) -- RECOMMENDED ---
# The converter wraps plain strings for you.
df = pd.DataFrame({
    "prompt":   ["Q1", "Q2"],
    "response": ["A1", "A2"],
})
dataset = types.EvaluationDataset(eval_dataset_df=df)

# --- SINGLE-TURN EVAL (direct EvalCase) ---
# Verbose and easy to get wrong; see references/dataset_schema.md for the
# exact types before using this form.
dataset = types.EvaluationDataset(eval_cases=[
    types.EvalCase(
        prompt=genai_types.UserContent("Query here"),
        responses=[types.ResponseCandidate(
            response=genai_types.ModelContent("Model response here"))],
        reference=types.ResponseCandidate(
            response=genai_types.ModelContent("Ground truth here")),
    ),
])

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
patterns: synthetic data generation, pairwise comparison, `MetricPromptBuilder`,
multi-agent evaluation.

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
