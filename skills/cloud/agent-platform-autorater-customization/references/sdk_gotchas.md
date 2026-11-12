# SDK gotchas

## LLM metrics

-   `LLMMetric` needs `judge_model` as a full resource name
    (`projects/{project}/locations/{location}/publishers/google/models/{model}`).
-   `LLMMetric` needs `responses` even when `agent_data` is set.
-   Template variables `prompt`, `response`, `reference` and `agent_data` come
    from the case. Other variables come from extra `EvalCase` attributes with
    the same name, but only in inline runs: a registered metric run by name
    sends none of them, so the judge gets an empty value.
-   Judges sometimes return JSON that can't be parsed; rerun failed cases once.

## Code metrics

-   Use `CodeExecutionMetric` (code runs in the service's sandbox) for any code
    metric you hand over. A local callable (`types.Metric(custom_function=...)`)
    errors with "No response found" on cases without `responses`, and
    `create_evaluation_metric` rejects it as an unsupported metric type.
-   `CodeExecutionMetric` must return a float.
-   The remote sandbox gets the trajectory as `instance["agent_eval_data"]`; a
    local callable gets `instance["agent_data"]`. Read both, or every remote
    score is 0.0.
-   `prompt`, `response` and `reference` arrive as `Content`-like dicts, not
    strings.

## Rubric metrics

-   Single-turn predefined metrics (for example `FINAL_RESPONSE_REFERENCE_FREE`)
    reject multi-turn `agent_data` and grade only `response`. To grade a
    trajectory with them, pass the rendered trajectory as `response` and drop
    `agent_data`.
-   Predefined rubric metrics use your rubrics when the case has one
    `rubric_groups` entry. A custom `LLMMetric` with `rubric_group_name` puts
    the rubrics in `{question_block}` and expects `STEP 1:` / `Property:` /
    `Rationale:` / `Verdict: yes|no` blocks back; prefer the predefined metric.
-   Predefined rubric metrics with your rubrics often fail on long inputs
    ("Rubric results could not be reliably computed").
-   `return_raw_output` is rejected, so you can't see the raw judge output
    through the SDK. In a step-based metric, put what you need in the
    explanation the parser returns.

## Step-based metrics

-   `types.StepBasedLLMMetric` needs `google-cloud-aiplatform` 2.8.0 or later.
-   Prompt templates read the trace as `{agent_eval_data}`, not
    `{agent_data}`.
-   Code preprocessors define `preprocess(agent_data)` and return an AgentData
    dict. Code parsers define `parse_results(responses)`.
-   With `sampling_count` above 1, the parser gets every sample. Line up item
    ids across samples before voting, and take the explanation from a sample
    that agrees with the majority.

## Other

-   `run_inference` overwrites existing responses; don't call it when the
    trajectories already have them.
