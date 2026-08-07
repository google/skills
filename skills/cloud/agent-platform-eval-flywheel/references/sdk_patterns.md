# Agent Platform Evaluation SDK Patterns

Code patterns for common evaluation scenarios using `agentplatform._genai.evals`.

## Initialization

```python
import agentplatform
from agentplatform import types
from google.genai import types as genai_types

client = agentplatform.Client(project="{PROJECT_ID}", location="{LOCATION}")

# EvalCase prompt/reference/response values are Content objects, not plain
# strings. Use genai_types.UserContent(str) / ModelContent(str), which wrap
# the string in a Part and set the role. Each pattern below is self-contained.
```

For Gemini 3+ models, use `location="global"`.

## Pattern 1: Single-Turn Evaluation

Simplest case — evaluate prompt/response pairs against predefined metrics.

```python
dataset = types.EvaluationDataset(eval_cases=[
    types.EvalCase(
        prompt=genai_types.UserContent("What causes rain?"),
        responses=[types.ResponseCandidate(
            response=genai_types.ModelContent(
                "Rain is caused by water evaporating..."))],
        reference=types.ResponseCandidate(
            response=genai_types.ModelContent(
                "Rain forms when water vapor condenses...")),
    ),
])

result = client.evals.evaluate(
    dataset=dataset,
    metrics=[
        types.RubricMetric.GENERAL_QUALITY,
        types.Metric(name="rouge_l_sum"),
    ],
)
```

## Pattern 2: Multi-Turn Agent Evaluation

Evaluate a full agent conversation trajectory with tool calls.

```python
agent_data = types.evals.AgentData(
    agents={
        "my_agent": types.evals.AgentConfig(
            agent_id="my_agent",
            instruction="You are a helpful assistant.",
            tools=[genai_types.Tool(function_declarations=[
                genai_types.FunctionDeclaration(
                    name="search",
                    description="Search the web",
                    parameters=genai_types.Schema(
                        type="OBJECT",
                        properties={"query": genai_types.Schema(type="STRING")},
                    ),
                ),
            ])],
        ),
    },
    turns=[
        types.evals.ConversationTurn(turn_index=0, events=[
            types.evals.AgentEvent(
                author="user",
                content=genai_types.Content(role="user",
                    parts=[genai_types.Part(text="Find me the weather in NYC")]),
            ),
            types.evals.AgentEvent(
                author="my_agent",
                content=genai_types.Content(role="model",
                    parts=[genai_types.Part(function_call=genai_types.FunctionCall(
                        name="search", args={"query": "NYC weather"}))]),
            ),
            types.evals.AgentEvent(
                author="my_agent",
                content=genai_types.Content(role="tool",
                    parts=[genai_types.Part(function_response=genai_types.FunctionResponse(
                        name="search", response={"result": "72F, sunny"}))]),
            ),
            types.evals.AgentEvent(
                author="my_agent",
                content=genai_types.Content(role="model",
                    parts=[genai_types.Part(text="It's 72F and sunny in NYC.")]),
            ),
        ]),
    ],
)

result = client.evals.evaluate(
    dataset=types.EvaluationDataset(eval_cases=[
        types.EvalCase(agent_data=agent_data),
    ]),
    metrics=[
        types.RubricMetric.MULTI_TURN_TRAJECTORY_QUALITY,
        types.RubricMetric.MULTI_TURN_TASK_SUCCESS,
    ],
)
```

## Pattern 3: Synthetic Data Generation (Cold Start)

Generate user scenarios when no eval data exists.

```python
# Step 1: Generate scenarios
scenarios = client.evals.generate_conversation_scenarios(
    agents={
        "agent": types.evals.AgentConfig(
            agent_id="agent",
            instruction="You are a customer support agent for an airline.",
        ),
    },
    root_agent_id="agent",
    user_scenario_generation_config=types.evals.UserScenarioGenerationConfig(
        user_scenario_count=10,
        simulation_instruction="Simulate customers with flight booking issues.",
        environment_data="Flights available: NYC-LAX, NYC-SFO. Cancellation policy: free within 24h.",
        model_name="gemini-2.5-flash",
    ),
)

# Step 2: Run inference with user simulation
dataset_with_responses = client.evals.run_inference(
    agent=my_agent,  # Your callable agent
    src=scenarios,
    config={
        "user_simulator_config": {
            "model_name": "gemini-2.5-flash",
            "max_turn": 5,
        },
    },
)

# Step 3: Evaluate
result = client.evals.evaluate(
    dataset=dataset_with_responses,
    metrics=[types.RubricMetric.MULTI_TURN_GENERAL_QUALITY, types.RubricMetric.SAFETY],
)
```

## Pattern 4: Custom LLM-as-a-Judge with MetricPromptBuilder

For domain-specific evaluation with structured rubrics.

```python
metric = types.LLMMetric(
    name="domain_expertise",
    prompt_template=types.MetricPromptBuilder(
        metric_definition="Evaluates domain expertise in the response.",
        criteria={
            "Accuracy": "Claims are factually correct for the domain",
            "Depth": "Response shows understanding beyond surface level",
            "Actionability": "Advice is specific and actionable",
        },
        rating_scores={
            "1": "Incorrect or misleading information",
            "2": "Partially correct but superficial",
            "3": "Correct and shows reasonable understanding",
            "4": "Accurate with good depth",
            "5": "Expert-level accuracy, depth, and actionability",
        },
    ),
    judge_model="gemini-2.5-flash",
    judge_model_sampling_count=3,
)
```

## Pattern 5: CodeExecutionMetric for Structured Validation

For programmatic checks that go beyond text comparison.

```python
# Validate JSON output structure
json_validator = types.CodeExecutionMetric(
    name="json_structure_check",
    custom_function='''
import json
def evaluate(instance: dict) -> dict:
    try:
        data = json.loads(instance.get("response", ""))
        required_keys = {"name", "status", "result"}
        missing = required_keys - set(data.keys())
        if missing:
            return {"score": 0.0, "explanation": f"Missing keys: {missing}"}
        return {"score": 1.0, "explanation": "All required keys present"}
    except json.JSONDecodeError as e:
        return {"score": 0.0, "explanation": f"Invalid JSON: {e}"}
''',
)
```

## Pattern 6: Pairwise Model Comparison

Compare two models using `calculate_win_rates()`.

```python
# Same dataset, two different model responses
dataset_a = types.EvaluationDataset(eval_cases=[
    types.EvalCase(prompt=genai_types.UserContent("Explain quantum computing"),
                   responses=[types.ResponseCandidate(
                       response=genai_types.ModelContent(
                           "Model A response..."))]),
])
dataset_b = types.EvaluationDataset(eval_cases=[
    types.EvalCase(prompt=genai_types.UserContent("Explain quantum computing"),
                   responses=[types.ResponseCandidate(
                       response=genai_types.ModelContent(
                           "Model B response..."))]),
])

result_a = client.evals.evaluate(dataset=dataset_a, metrics=[types.RubricMetric.GENERAL_QUALITY])
result_b = client.evals.evaluate(dataset=dataset_b, metrics=[types.RubricMetric.GENERAL_QUALITY])

# Compare
from agentplatform._genai._evals_metric_handlers import calculate_win_rates
win_rates = calculate_win_rates(result_a, result_b)
```

## Pattern 7: Parsing Results

```python
result = client.evals.evaluate(dataset=dataset, metrics=metrics)

# Summary level
for summary in result.summary_metrics:
    print(f"{summary.metric_name}: mean={summary.mean_score}, pass_rate={summary.pass_rate}")

# Per-case level
for case in result.eval_case_results:
    for candidate in case.response_candidate_results:
        for metric_name, metric_result in candidate.metric_results.items():
            print(f"  {metric_name}: score={metric_result.score}")
            print(f"    explanation: {metric_result.explanation}")

            # Rubric verdicts (for rubric-based metrics)
            if metric_result.rubric_verdicts:
                for v in metric_result.rubric_verdicts:
                    print(f"    rubric {v.evaluated_rubric.rubric_id}: "
                          f"{'PASS' if v.verdict else 'FAIL'} - {v.reasoning}")
```

## Error Handling

```python
try:
    result = client.evals.evaluate(dataset=dataset, metrics=metrics)
except Exception as e:
    error_type = type(e).__name__
    if "PermissionDenied" in error_type:
        print("Check: GCP project permissions, API enabled, billing active")
    elif "InvalidArgument" in error_type:
        print("Check: dataset format, metric compatibility with data type")
    elif "ResourceExhausted" in error_type:
        print("Check: API quota, reduce dataset size or add delay")
    else:
        raise
```
