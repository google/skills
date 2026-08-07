# GenAI Evaluation Metric Registry

Complete catalog of evaluation metrics available in the `agentplatform` SDK.
Source of truth: `agentplatform/_genai/_evals_metric_loaders.py` and
`agentplatform/_genai/_evals_metric_handlers.py`.

Metric IDs in this file are the **unversioned** form (e.g.,
`multi_turn_task_success`, not `multi_turn_task_success_v1`). The SDK resolves
unversioned names to the latest version; pin to a specific version only when
required for reproducibility (e.g., `RubricMetric.GENERAL_QUALITY(version="v2")`).

## Metric Type Hierarchy

```
Metric (base)
├── LLMMetric           — LLM-as-a-judge with prompt_template
├── CodeExecutionMetric — Sandboxed remote Python function
└── (base Metric)       — Local callable or predefined name
```

Access predefined metrics via `types.RubricMetric.<NAME>` (preferred).
`types.PrebuiltMetric` is an alias with identical behavior.

## Predefined API Metrics (AutoRater)

Server-side evaluation via the Agent Platform AutoRater. No judge model needed.

### Agent metrics (multi-turn, adaptive rubrics)

Start here for agent evaluation. Adaptive rubrics generate criteria from the
trace at runtime.

| Metric ID                       | What it measures                                                                       | Required fields                  |
| ------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------- |
| `multi_turn_task_success`       | Whether the user's goal was fulfilled across the full multi-turn conversation.         | `agent_data` with task context   |
| `multi_turn_trajectory_quality` | Sequential logic, efficiency, and error-recovery robustness across turns.              | `agent_data` with full trajectory |
| `multi_turn_tool_use_quality`   | Technical and semantic correctness of tool calls across the multi-turn conversation.   | `agent_data` with function calls |
| `multi_turn_general_quality`    | Overall response quality within a multi-turn dialogue.                                 | `agent_data` (1+ turns)          |
| `multi_turn_text_quality`       | Linguistic text quality within a multi-turn dialogue.                                  | `agent_data` (1+ turns)          |
| `final_response_quality`        | Comprehensive evaluation of the final response and intermediate tool usage.            | `agent_data`                     |
| `final_response_match`          | Compares the agent's final response to a provided golden reference answer.             | `agent_data`, `reference`        |
| `final_response_reference_free` | Final-response quality without a reference answer (requires custom rubrics).           | `agent_data` + rubric_groups     |
| `tool_use_quality`              | Tool selection, parameter accuracy, and step sequence correctness (single-turn).       | `agent_data` with tool calls     |

### General quality metrics (single-turn, adaptive rubrics)

For model evaluation (no agent orchestration).

| Metric ID               | What it measures                                                  | Required fields      |
| ----------------------- | ----------------------------------------------------------------- | -------------------- |
| `general_quality`       | Overall response quality with auto-generated content-based criteria. Recommended starting point for non-agent eval. | `prompt`, `response` |
| `text_quality`          | Linguistic aspects: fluency, coherence, grammar.                  | `prompt`, `response` |
| `instruction_following` | How well the response adheres to specific constraints / instructions. | `prompt`, `response` |

### Static rubric metrics (fixed criteria)

Apply alongside the agent or general-quality metrics above. Fixed rubrics — no
adaptive generation.

| Metric ID       | What it measures                                                                        | Required fields                 |
| --------------- | --------------------------------------------------------------------------------------- | ------------------------------- |
| `hallucination` | Segments the response into atomic claims; verifies each against tool-returned context.  | `response`, intermediate context |
| `grounding`     | Factuality and consistency against provided context.                                    | `prompt`, `response`, `context`  |
| `safety`        | Policy compliance (PII, hate speech, dangerous content, harassment, sexual).            | `prompt`, `response`            |

### Accessing predefined metrics

```python
from agentplatform import types

# Via RubricMetric (preferred) — uppercase enum, unversioned
metric = types.RubricMetric.MULTI_TURN_TRAJECTORY_QUALITY

# Via PrebuiltMetric (alias — identical behavior)
metric = types.PrebuiltMetric.MULTI_TURN_TRAJECTORY_QUALITY

# Pin to a specific version (only when needed for reproducibility)
metric = types.RubricMetric.GENERAL_QUALITY(version="v2")
```

## Computation-Based Metrics

No LLM judge. Deterministic comparison of `response` vs `reference`. Use only
when you have exact reference text to compare against; for agent eval prefer
the rubric-based metrics above.

| Metric ID                  | What it measures                            | Notes          |
| -------------------------- | ------------------------------------------- | -------------- |
| `bleu`                     | BLEU score (translation/generation).        | Standard BLEU  |
| `rouge_1`                  | ROUGE-1 (unigram overlap).                  | Summarization  |
| `tool_parameter_key_match` | Whether tool parameter keys match reference. | Agent evals    |
| `tool_parameter_kv_match`  | Whether tool parameter key-value pairs match reference. | Agent evals    |

```python
metric = types.Metric(name="bleu")
metric = types.Metric(name="tool_parameter_kv_match")
```

## Translation Metrics

| Metric ID | Default version      | Notes                                   |
| --------- | -------------------- | --------------------------------------- |
| `comet`   | `COMET_22_SRC_REF`   | Requires `prompt` (source), `response`, `reference` |
| `metricx` | `METRICX_24_SRC_REF` | Requires `prompt` (source), `response`, `reference` |

## Multimodal Metrics

| Metric ID            | What it measures      | Required fields |
| -------------------- | --------------------- | --------------- |
| `gecko_text2image_v1` | Text-to-image quality | image content   |
| `gecko_text2video_v1` | Text-to-video quality | video content   |

## RubricMetric / PrebuiltMetric (Enum Access)

`RubricMetric.<NAME>` resolves first against the API predefined list, then
falls back to GCS-hosted LLM metric recipes. The names below are the
**uppercase enum form** of the unversioned IDs above; pass them as
`types.RubricMetric.<NAME>`.

`types.RubricMetric` is a `PrebuiltMetricLoader`, not an enum: it is not
iterable (despite `hasattr(..., "__iter__")` returning True), so discover
names with `dir()` or the table below. Attribute access returns a
`LazyLoadedPrebuiltMetric` exposing only `name`, `version`, `metric_kwargs`
and `resolve(api_client)`; pass it straight to `evaluate(metrics=[...])`.

| Property                        | Resolution           |
| ------------------------------- | -------------------- |
| `MULTI_TURN_TASK_SUCCESS`       | API predefined       |
| `MULTI_TURN_TRAJECTORY_QUALITY` | API predefined       |
| `MULTI_TURN_TOOL_USE_QUALITY`   | API predefined       |
| `MULTI_TURN_GENERAL_QUALITY`    | API predefined       |
| `MULTI_TURN_TEXT_QUALITY`       | API predefined       |
| `FINAL_RESPONSE_QUALITY`        | API predefined       |
| `FINAL_RESPONSE_MATCH`          | API predefined (v2)  |
| `FINAL_RESPONSE_REFERENCE_FREE` | API predefined       |
| `TOOL_USE_QUALITY`              | API predefined       |
| `GENERAL_QUALITY`               | API predefined       |
| `TEXT_QUALITY`                  | API predefined       |
| `INSTRUCTION_FOLLOWING`         | API predefined       |
| `HALLUCINATION`                 | API predefined       |
| `SAFETY`                        | API predefined       |

Any arbitrary name can be tried via `RubricMetric.<NAME>` — it will attempt
resolution against the API list and then GCS.

## Custom Metrics

### Custom Local Function

Runs client-side. Fastest iteration, no API call. Runs with the calling
process's privileges, so only use trusted code.

```python
def my_evaluator(instance: dict) -> float:
    response_text = instance.get("response", "")
    return 1.0 if "thank you" in response_text.lower() else 0.0

metric = types.Metric(
    name="politeness_check",
    custom_function=my_evaluator,
)
```

### CodeExecutionMetric (Remote Sandboxed)

Runs server-side in an Agent Platform sandbox. Must contain `def evaluate(instance)`.

```python
metric = types.CodeExecutionMetric(
    name="link_validator",
    custom_function='''
import re
def evaluate(instance: dict) -> dict:
    text = instance.get("response", "")
    links = re.findall(r"https?://\\S+", text)
    valid = all(link.startswith("https://") for link in links)
    return {"score": 1.0 if valid else 0.0, "explanation": f"Found {len(links)} links"}
''',
)
```

### LLMMetric (LLM-as-a-Judge)

Uses a judge model to evaluate with a custom prompt template.

```python
metric = types.LLMMetric(
    name="helpfulness",
    prompt_template="""
Evaluate whether the response is helpful for the given query.

Query: {prompt}
Response: {response}

Score 1 if helpful, 0 if not. Explain your reasoning.
""",
    judge_model="gemini-2.5-flash",
    judge_model_sampling_count=3,
)

# Load from YAML/JSON file
metric = types.LLMMetric.load("path/to/metric_config.yaml")
```

### MetricPromptBuilder (Structured Judge Prompt)

Builds structured LLM judge prompts from criteria, rating scores, and evaluation
steps. Preferred over raw `prompt_template` strings for complex rubrics.

`criteria` and `rating_scores` are both mandatory; supplying only one raises
`ValidationError: Both 'criteria' and 'rating_scores' are required to
construct the LLM-based metric prompt template text`.

```python
metric = types.LLMMetric(
    name="structured_quality",
    prompt_template=types.MetricPromptBuilder(
        criteria={
            "Accuracy": "Response contains factually correct information",
            "Completeness": "Response addresses all aspects of the query",
        },
        rating_scores={
            "1": "Poor — fails on both criteria",
            "3": "Acceptable — meets one criterion",
            "5": "Excellent — meets both criteria",
        },
    ),
    judge_model="gemini-2.5-flash",
)
```

### Registered Metric (Server-Side Resource)

For reusable metrics shared across teams.

```python
# Create once
resource = client.evals.create_evaluation_metric(metric_config)

# Use by resource name
metric = types.Metric(
    name="team_quality",
    metric_resource_name="projects/.../evaluationMetrics/...",
)
```

## Metric Selection Guide

| Agent Type                    | Recommended Metrics                                                    |
| ----------------------------- | ---------------------------------------------------------------------- |
| **RAG agent**                 | `hallucination`, `grounding`, `final_response_quality`, `safety`       |
| **Tool-use agent (multi-turn)** | `multi_turn_task_success`, `multi_turn_tool_use_quality`, `multi_turn_trajectory_quality` |
| **Tool-use agent (single-turn)** | `tool_use_quality`, `final_response_quality`                        |
| **Multi-turn conversational** | `multi_turn_general_quality`, `multi_turn_text_quality`, `safety`      |
| **Goal-oriented agent**       | `multi_turn_task_success`, `final_response_quality`                    |
| **Single-turn model eval**    | `general_quality`, `text_quality`, `instruction_following`             |
| **Translation**               | `comet`, `metricx`                                                     |
| **Code generation**           | Custom `CodeExecutionMetric` + `instruction_following`                 |

## Pairwise Comparison

There is no `PairwiseMetric` class. For model comparison, provide multiple
`EvaluationDataset` instances and use `calculate_win_rates()`:

```python
result_a = client.evals.evaluate(dataset=dataset_a, metrics=[...])
result_b = client.evals.evaluate(dataset=dataset_b, metrics=[...])
win_rates = calculate_win_rates(result_a, result_b)
```

## Handler Dispatch Order

When the SDK receives a metric, it checks in this order:

1.  `CodeExecutionMetric` with `custom_function` (str) or
    `remote_custom_function`
2.  `Metric` with `custom_function` (local `Callable`)
3.  `Metric` with `metric_resource_name` (registered)
4.  Name in computation metrics (`bleu`, `rouge_1`, etc.)
5.  Name in translation metrics (`comet`, `metricx`)
6.  Name in predefined API metrics (`general_quality`, `multi_turn_task_success`, etc.)
7.  `LLMMetric` with `prompt_template` (custom LLM judge)
