# Evaluation Dataset Schema

Canonical formats for evaluation datasets in the Google GenAI Evaluation SDK.
Source of truth: `agentplatform/_genai/types/evals.py` and
`agentplatform/_genai/types/common.py`.

## Core Types

```
EvaluationDataset
├── eval_cases: list[EvalCase]       # Primary: list of cases
└── eval_dataset_df: pd.DataFrame    # Alternative: pandas DataFrame

EvalCase
├── prompt: genai_types.Content            # Single-turn: user query (NOT a str)
├── responses: list[ResponseCandidate]     # Model replies (NOTE: plural, a list)
├── reference: ResponseCandidate           # Ground truth (reference-based metrics)
├── system_instruction: genai_types.Content  # System instruction for the model
├── conversation_history: list[Message]    # Prior messages (chat history)
├── eval_case_id: str                      # Unique identifier for the case
├── agent_data: AgentData                  # Multi-turn: full conversation trajectory
├── ... also: rubric_groups, intermediate_events, agent_info, user_scenario,
│            interactions_data_source
└── (extra fields allowed)                 # Custom fields for custom metrics

ResponseCandidate
└── response: genai_types.Content          # The model-generated Content

NOTE: When constructing EvalCase objects directly:
  * prompt is a Content (NOT a str). Passing a str raises
    pydantic.ValidationError -- fails loudly.
  * there is NO singular `response=` field -- use
    `responses=[ResponseCandidate(...)]`. EvalCase sets extra="allow", so
    `response=` does NOT raise; it is silently stored, never read, and the
    candidate scores as missing -- fails quietly.
  * reference is a ResponseCandidate (NOT a str)
Simpler: use the pandas DataFrame form, whose converter accepts plain
`prompt`/`response`/`reference` string columns and wraps them for you.

AgentData
├── agents: dict[str, AgentConfig]   # Agent definitions
└── turns: list[ConversationTurn]    # Ordered conversation turns

ConversationTurn
├── turn_index: int                  # 0-based turn number
└── events: list[AgentEvent]         # Events within this turn

AgentEvent
├── author: str                      # "user", agent_id, or "tool"
└── content: genai_types.Content     # Content with role and parts
```

## Single-Turn Dataset

For simple prompt-response evaluation (e.g., QA, summarization). **The pandas
DataFrame form (below) is the recommended, least error-prone way** -- it accepts
plain strings. Direct `EvalCase` construction is shown here for reference; see
the NOTE under Core Types above for the exact types.

```python
from agentplatform import types
from google.genai import types as genai_types

dataset = types.EvaluationDataset(eval_cases=[
    types.EvalCase(
        prompt=genai_types.UserContent("What is the capital of France?"),
        responses=[types.ResponseCandidate(
            response=genai_types.ModelContent(
                "The capital of France is Paris."))],
        reference=types.ResponseCandidate(
            response=genai_types.ModelContent("Paris")),
    ),
    types.EvalCase(
        prompt=genai_types.UserContent("Summarize this article: ..."),
        responses=[types.ResponseCandidate(
            response=genai_types.ModelContent("The article discusses..."))],
    ),
])
```

### From pandas DataFrame

```python
import pandas as pd
from agentplatform import types

df = pd.DataFrame({
    "prompt": ["What is 2+2?", "Name the planets"],
    "response": ["4", "Mercury, Venus, Earth, ..."],
    "reference": ["4", "Mercury, Venus, Earth, Mars, ..."],
})
dataset = types.EvaluationDataset(eval_dataset_df=df)
```

### Required columns (DataFrame / JSONL form)

These are DataFrame/JSONL *column* names, which the converter maps onto the
`EvalCase` attributes above -- a `response` column becomes
`responses=[ResponseCandidate(...)]`. There is still no singular `response=`
constructor argument.

Metric category          | Required columns
------------------------ | -------------------------------------------
Predefined (single-turn) | `prompt`, `response`
Computation-based        | `response`, `reference`
Translation              | `prompt` (source), `response`, `reference`
Custom LLM/code          | Fields referenced in your template/function

## Multi-Turn Dataset (AgentData)

For evaluating multi-turn agent conversations with tool calls.

```python
from agentplatform import types
from google.genai import types as genai_types

agent_data = types.evals.AgentData(
    agents={
        "support_agent": types.evals.AgentConfig(
            agent_id="support_agent",
            instruction="You are a helpful support agent.",
            tools=[genai_types.Tool(function_declarations=[
                genai_types.FunctionDeclaration(
                    name="lookup_order",
                    description="Look up order status by ID",
                    parameters=genai_types.Schema(
                        type="OBJECT",
                        properties={"order_id": genai_types.Schema(type="STRING")},
                    ),
                )
            ])],
        )
    },
    turns=[
        types.evals.ConversationTurn(
            turn_index=0,
            events=[
                # User message
                types.evals.AgentEvent(
                    author="user",
                    content=genai_types.Content(
                        role="user",
                        parts=[genai_types.Part(text="Where is my order #12345?")]
                    ),
                ),
                # Agent calls tool
                types.evals.AgentEvent(
                    author="support_agent",
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part(
                            function_call=genai_types.FunctionCall(
                                name="lookup_order",
                                args={"order_id": "12345"},
                            )
                        )]
                    ),
                ),
                # Tool response
                types.evals.AgentEvent(
                    author="support_agent",
                    content=genai_types.Content(
                        role="tool",
                        parts=[genai_types.Part(
                            function_response=genai_types.FunctionResponse(
                                name="lookup_order",
                                response={"status": "shipped", "eta": "tomorrow"},
                            )
                        )]
                    ),
                ),
                # Agent final response
                types.evals.AgentEvent(
                    author="support_agent",
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part(
                            text="Your order #12345 has been shipped and should arrive tomorrow!"
                        )]
                    ),
                ),
            ],
        ),
    ],
)

eval_case = types.EvalCase(agent_data=agent_data)
dataset = types.EvaluationDataset(eval_cases=[eval_case])
```

## Multi-Agent Dataset

For evaluating systems with multiple collaborating agents.

```python
agent_data = types.evals.AgentData(
    agents={
        "router": types.evals.AgentConfig(
            agent_id="router",
            agent_type="RouterAgent",
            instruction="Route requests to the appropriate specialist.",
        ),
        "flight_bot": types.evals.AgentConfig(
            agent_id="flight_bot",
            agent_type="SpecialistAgent",
            instruction="Search and book flights.",
            tools=[genai_types.Tool(function_declarations=[
                genai_types.FunctionDeclaration(name="search_flights")
            ])],
        ),
    },
    turns=[
        types.evals.ConversationTurn(
            turn_index=0,
            events=[
                types.evals.AgentEvent(
                    author="user",
                    content=genai_types.Content(
                        role="user",
                        parts=[genai_types.Part(text="Book a flight to NYC")]
                    ),
                ),
                # Router delegates
                types.evals.AgentEvent(
                    author="router",
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part(
                            function_call=genai_types.FunctionCall(
                                name="delegate_to_agent",
                                args={"agent_name": "flight_bot"},
                            )
                        )]
                    ),
                ),
            ],
        ),
        types.evals.ConversationTurn(
            turn_index=1,
            events=[
                # Specialist works
                types.evals.AgentEvent(
                    author="flight_bot",
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part(
                            function_call=genai_types.FunctionCall(
                                name="search_flights",
                                args={"destination": "NYC"},
                            )
                        )]
                    ),
                ),
            ],
        ),
    ],
)
```

## Synthetic Data Generation

### Generate User Scenarios (Cold Start)

```python
scenarios = client.evals.generate_conversation_scenarios(
    agents={
        "my_agent": types.evals.AgentConfig(
            agent_id="my_agent",
            instruction="You are a helpful customer support agent.",
        )
    },
    root_agent_id="my_agent",
    user_scenario_generation_config=types.evals.UserScenarioGenerationConfig(
        user_scenario_count=10,
        simulation_instruction="Simulate a customer asking about order status.",
        environment_data="Orders can be: pending, shipped, delivered, cancelled.",
        model_name="gemini-2.5-flash",
    ),
)
```

### Run Inference (Populate Responses)

```python
dataset_with_responses = client.evals.run_inference(
    agent=my_agent_callable,
    src=scenarios,
    config={
        "user_simulator_config": {
            "model_name": "gemini-2.5-flash",
            "max_turn": 5,
        }
    },
)
```

## Common Mistakes

| Mistake                          | Fix                                    |
| -------------------------------- | -------------------------------------- |
| Using `role="assistant"`         | Use `role="model"` (Agent Platform convention) |
| Missing `turn_index`             | Always set sequential 0-based indices  |
| Tool response without            | Wrap in `genai_types.FunctionResponse` |
: `function_response`              :                                        :
| Using `response` field for       | Use `agent_data` with full trajectory  |
: multi-turn                       :                                        :
| Mixing `prompt` and `agent_data` | Use one or the other per EvalCase      |
