---
name: gemini-interactions-api
metadata:
  category: AiAndMachineLearning
description: Guides the usage of Gemini Interactions API on Gemini Enterprise Agent Platform. Use when the user wants to use the stateful, server-managed Interactions API for multi-turn conversations, background execution, streaming, structured output, and function calling on the Agent Platform.
---

# Gemini Interactions API Skill

This skill provides instructions for authenticating, connecting to, and utilizing the stateful, server-managed **Gemini Interactions API** on Gemini Enterprise Agent Platform.


The Interactions API is the modern, recommended way to execute Generative AI agent conversations, background research tasks, multi-turn chats, and structured, multi-step workflows.

> [!IMPORTANT] **CRITICAL: Unified SDK, Latest Models & GEAP Targeting** *
> **Unified SDK**: Use the Google Gen AI SDK (**`google-genai >= 2.3.0`** for
> Python, **`@google/genai >= 2.3.0`** for JS/TS). SDK versions `>= 2.0.0` are
> the minimum floor at which the steps schema activates, but `>= 2.3.0` is the
> supported/recommended floor. Legacy SDKs like `google-cloud-aiplatform`,
> `@google-cloud/vertexai`, and `google-generativeai` are strictly unsupported
> for Interactions. * *Mandatory Instruction*: When explaining client
> initialization or writing import code, you **must** explicitly state/warn the
> user that legacy packages like `google-cloud-aiplatform` or
> `google-generativeai` are strictly unsupported for interactions. * **Latest
> Models Only**: Use `gemini-3.5-flash` (fast, balanced, multimodal — the
> recommended default), `gemini-3.1-pro-preview` (complex reasoning, coding,
> research), or `gemini-3.1-flash-lite` (cost-efficient, high-frequency
> lightweight tasks). Refer to the
> [latest model versions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate)
> to check for new updates. Legacy models (`gemini-3-flash-preview`,
> `gemini-2.5-*`, `gemini-2.0-*`, `gemini-1.5-*`) are deprecated and do not
> support interactions. * *Mandatory Instruction*: In any interaction response,
> you **must** warn the user that legacy models like `gemini-2.5-*`,
> `gemini-2.0-*`, or `gemini-1.5-*` are deprecated and unsupported for the
> Interactions API. * **GEAP requires a provisioned agent (no direct base-model
> calls yet)**: On Gemini Enterprise Agent Platform (GEAP), direct/base-model
> calls (`model="..."`) via the Interactions API are **not supported yet**. You
> **must** target a provisioned agent or endpoint with the `agent="<AGENT_ID>"`
> parameter instead of `model="..."`. The code examples in this skill use
> `agent=...` for this reason. (This is the primary difference from the
> [ai.google.dev](https://ai.google.dev/gemini-api/docs/interactions)
> documentation for Interactions, which uses `model=...` — while `model=...` is
> valid for other Gemini API contexts, it is **not supported on the Agent
> Platform**.) Provision an agent per the
> [Agent Platform docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform)
> and pass its ID as `agent`. * **Turn-Scoped Parameters**: Parameters like
> `tools`, `system_instruction`, and `generation_config` are turn-scoped. They
> **MUST** be passed with each interaction request.

## 1. Authentication

Before running any code, ensure you are authenticated with Application Default Credentials (ADC) and have the necessary API enabled.

1.  **Login**:
    
    ```bash
    gcloud auth application-default login
    ```
2.  **Enable API** (if not already enabled):
    
    ```bash
    gcloud services enable aiplatform.googleapis.com
    ```

---

## 2. Client Initialization

You can initialize the client using environment variables (recommended) or by passing explicit configuration parameters.

### Option A: Environment Variables (Recommended)

Configure environment variables to let the SDK automatically resolve settings:

```bash
export GOOGLE_GENAI_USE_ENTERPRISE=true
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="global"
```

#### Python

```python
from google import genai

# The SDK automatically picks up the environment variables
client = genai.Client()
```

#### TypeScript/JavaScript

```typescript
import { GoogleGenAI } from "@google/genai";

// The SDK automatically picks up the environment variables
const ai = new GoogleGenAI();
```

### Option B: Explicit Inline Parameters

Alternatively, pass configuration values directly inside your code:

#### Python

```python
from google import genai
import google.auth

_, project_id = google.auth.default()
client = genai.Client(enterprise=True, project=project_id, location="global")
```

#### TypeScript/JavaScript

```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({
    enterprise: {
        project: "your-project-id",
        location: "global"
    }
});
```

---

## 3. Core Interactions API Usage

### Quick Start (Single-Turn)

Submit a single prompt and read the final text response. Under the modern schema, output content is retrieved from the `steps` list.

#### Python

```python
interaction = client.interactions.create(
    agent="your-agent-id",  # GEAP: target a provisioned agent, not a base model
    input="Explain serverless computing in one sentence."
)
# Use the output_text convenience accessor (combined text from the trailing model_output steps)
print(interaction.output_text)
```

#### TypeScript/JavaScript

```typescript
const interaction = await ai.interactions.create({
    agent: "your-agent-id", // GEAP: target a provisioned agent, not a base model
    input: "Explain serverless computing in one sentence."
});
console.log(interaction.output_text);
```

---

### Stateful Conversation (Multi-Turn)

Interactions are stateful by default. Store the conversation state in the cloud and reference it in the subsequent turn using `previous_interaction_id`.

#### Python

```python
# Turn 1: Introduce ourselves
# Interactions are stored by default (store=True); pass store=False to disable
# server-side retention (which also disables previous_interaction_id and background).
turn1 = client.interactions.create(
    agent="your-agent-id",
    input="Hi! My name is John. I am working on AI agents.",
    store=True
)
print(f"Turn 1: {turn1.output_text}")

# Turn 2: Refer back to the stored turn state
turn2 = client.interactions.create(
    agent="your-agent-id",
    input="What is my name?",
    previous_interaction_id=turn1.id
)
print(f"Turn 2: {turn2.output_text}")
```

#### TypeScript/JavaScript

```typescript
// Turn 1 (interactions are stored by default; pass store: false to disable)
const turn1 = await ai.interactions.create({
    agent: "your-agent-id",
    input: "Hi! My name is John. I am working on AI agents.",
    store: true
});

// Turn 2
const turn2 = await ai.interactions.create({
    agent: "your-agent-id",
    input: "What is my name?",
    previousInteractionId: turn1.id
});
console.log(turn2.output_text);
```

---

### Real-Time Streaming

Stream responses in real-time. Passing `stream=True` returns an iterable chunk generator.

#### Python

```python
# The stream yields typed events, not full interaction snapshots. The sequence is:
# interaction.created -> (step.start -> step.delta(s) -> step.stop)+ -> interaction.completed
for event in client.interactions.create(
    agent="your-agent-id",
    input="Write a short poem about debugging.",
    stream=True
):
    if event.event_type == "step.delta":
        if event.delta.type == "text":
            print(event.delta.text, end="", flush=True)
    elif event.event_type == "interaction.completed":
        print()
```

#### TypeScript/JavaScript

```typescript
// The stream yields typed events, not full interaction snapshots. The sequence is:
// interaction.created -> (step.start -> step.delta(s) -> step.stop)+ -> interaction.completed
const responseStream = await ai.interactions.create({
    agent: "your-agent-id",
    input: "Write a short poem about debugging.",
    stream: true
});

for await (const event of responseStream) {
    if (event.event_type === "step.delta") {
        if (event.delta.type === "text") {
            process.stdout.write(event.delta.text);
        }
    } else if (event.event_type === "interaction.completed") {
        console.log();
    }
}
```

---

### Structured Output (Pydantic / Polymorphic `response_format`)

Retrieve structured, type-safe JSON matching a schema. Under the modern Interactions API, a polymorphic `response_format` argument directly takes the target schema structure.

#### Python

```python
from pydantic import BaseModel, Field

class Book(BaseModel):
    title: str = Field(description="The title of the book")
    author: str = Field(description="The book's author")
    year_published: int

interaction = client.interactions.create(
    agent="your-agent-id",
    input="Recommend one famous sci-fi book.",
    response_format=Book
)

# The text will be a valid JSON matching the Book schema
print(interaction.output_text)
```

#### TypeScript/JavaScript

```typescript
import { Type } from "@google/genai";

const BookSchema = {
    type: Type.OBJECT,
    properties: {
        title: { type: Type.STRING, description: "The title of the book" },
        author: { type: Type.STRING, description: "The book's author" },
        yearPublished: { type: Type.INTEGER }
    },
    required: ["title", "author", "yearPublished"]
};

const interaction = await ai.interactions.create({
    agent: "your-agent-id",
    input: "Recommend one famous sci-fi book.",
    responseFormat: BookSchema
});

console.log(interaction.output_text);
```

---

### Function Calling (Agent Tool Use)

Define local tools (functions) and submit execution results to the stateful interaction history.

#### Python

```python
import json

def get_stock_price(ticker: str) -> float:
    """Gets the stock price for a given ticker symbol."""
    if ticker.upper() == "GOOG":
        return 175.50
    return 100.0

# Turn 1: Pass tools to the model
interaction = client.interactions.create(
    agent="your-agent-id",
    input="What is the stock price of GOOG?",
    tools=[get_stock_price]
)

# In the flat steps schema, a tool request is a top-level step of type
# "function_call" with flat `name` and `arguments` fields (no nested tool_calls).
for step in interaction.steps:
    if step.type == "function_call" and step.name == "get_stock_price":
        ticker_arg = step.arguments.get("ticker")
        price = get_stock_price(ticker_arg)

        # Turn 2: Submit the result back as a function_result step. Reference the
        # originating call via call_id=step.id, and pass tools again (turn-scoped).
        final_turn = client.interactions.create(
            agent="your-agent-id",
            input=[
                {
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": [{"type": "text", "text": json.dumps(price)}],
                }
            ],
            tools=[get_stock_price],
            previous_interaction_id=interaction.id
        )
        print(final_turn.output_text)
```

#### TypeScript/JavaScript

```typescript
import { Type } from "@google/genai";

// Define local tool
function getStockPrice({ ticker }: { ticker: string }): number {
    if (ticker.toUpperCase() === "GOOG") {
        return 175.50;
    }
    return 100.00;
}

// Turn 1: Pass tools to the model
const toolDeclaration = {
    functionDeclarations: [{
        name: "getStockPrice",
        description: "Gets the stock price for a given ticker symbol.",
        parameters: {
            type: Type.OBJECT,
            properties: {
                ticker: { type: Type.STRING, description: "The stock ticker symbol" }
            },
            required: ["ticker"]
        }
    }]
};

const interaction = await ai.interactions.create({
    agent: "your-agent-id",
    input: "What is the stock price of GOOG?",
    tools: [toolDeclaration]
});

// In the flat steps schema, a tool request is a top-level step of type
// "function_call" with flat `name` and `arguments` fields (no nested toolCalls).
const fcStep = interaction.steps.find(s => s.type === "function_call");
if (fcStep && fcStep.name === "getStockPrice") {
    const tickerArg = fcStep.arguments.ticker as string;
    const price = getStockPrice({ ticker: tickerArg });

    // Turn 2: Submit the result back as a function_result step. Reference the
    // originating call via call_id=fcStep.id, and pass tools again (turn-scoped).
    const finalTurn = await ai.interactions.create({
        agent: "your-agent-id",
        input: [{
            type: "function_result",
            name: fcStep.name,
            call_id: fcStep.id,
            result: [{ type: "text", text: JSON.stringify(price) }]
        }],
        tools: [toolDeclaration],
        previousInteractionId: interaction.id
    });
    console.log(finalTurn.output_text);
}
```

---

## 4. Accessing the Interactions API via REST

For shell-based scripts, debugging, or non-Python/JS environments, you can communicate with the stateful Interactions API directly using raw HTTP/REST requests via `curl`.

### 1. REST Endpoint

The REST API endpoint for interactions is:

```http
POST https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/interactions
```

*   **LOCATION**: Use `global` (or custom region if required).
*   **PROJECT_ID**: Your Google Cloud Project ID.

### 2. Set up Variables & Authentication Header

Set your target agent ID (e.g., model or custom agent path) and access token generated from Application Default Credentials:

```bash
AGENT_ID="your-agent-id"
ACCESS_TOKEN=$(gcloud auth print-access-token)
```

### 3. Single-Turn Interaction Payload

Send a request to start an interaction using the agent variable:

```bash
curl -X POST "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/interactions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "'"${AGENT_ID}"'",
    "input": [{
      "type": "user_input",
      "content": [{
        "type": "text",
        "text": "Explain serverless computing in one sentence."
      }]
    }]
  }'
```

#### Response Example
A synchronous POST request returns a JSON object containing the conversation step details and unique identifiers:

```json
{
  "id": "your-interaction-id",
  "status": "completed",
  "steps": [
    {
      "type": "model_output",
      "content": [
        {
          "type": "text",
          "text": "Serverless computing is a cloud execution model where the cloud provider dynamically manages the allocation and provisioning of servers, charging customers based on actual usage rather than pre-purchased capacity."
        }
      ]
    }
  ],
  "usage": {
    "total_tokens": 24751,
    "total_input_tokens": 23894,
    "total_output_tokens": 857
  },
  "created": "2026-05-08T10:44:43Z",
  "updated": "2026-05-08T10:44:43Z",
  "environment_id": "your-environment-id",
  "object": "interaction"
}
```

### 4. Multi-Turn Stateful Interaction Payload

To continue an existing conversation statefully, specify the `previous_interaction_id` in the JSON payload:

```bash
curl -X POST "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/interactions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "'"${AGENT_ID}"'",
    "store": true,
    "previous_interaction_id": "YOUR_PREVIOUS_INTERACTION_ID",
    "input": [{
      "type": "user_input",
      "content": [{
        "type": "text",
        "text": "Can you elaborate on that?"
      }]
    }]
  }'
```

### 5. Streaming Output Payload
To stream updates in real time (Server-Sent Events format), pass `"stream": true` in the payload:

```bash
curl -X POST "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/interactions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "'"${AGENT_ID}"'",
    "stream": true,
    "input": [{
      "type": "user_input",
      "content": [{
        "type": "text",
        "text": "Write a long story about space travel."
      }]
    }]
  }'
```

The endpoint will return a chunked stream where each event begins with `data: ` containing JSON updates with the `event_type` and step contents.

> **How `curl` handles streaming:**
> By default, when `"stream": true` is passed, the server responds with `Transfer-Encoding: chunked` and `Content-Type: text/event-stream` (Server-Sent Events). `curl` will automatically keep the connection open and print the incoming data chunks to `stdout` in real time as they are pushed by the server. The user does not need to poll or pull further; the complete sequence of events streams continuously until completion.

--------------------------------------------------------------------------------

## 5. Data Model & Step Types Reference

An `Interaction` response contains `steps`, an array of typed step objects
representing a structured timeline of the interaction turn. Read the current
step `type` rather than assuming the last step is text — the trailing step may
be a `function_call` or a `thought`.

### Step Types

**User steps:**

*   `user_input`: User input (text, audio, multimodal). Contains a `content`
    array. (This is why REST input payloads use `"type": "user_input"`, **not**
    `"role": "user"`.)

**Model/server steps:**

*   `model_output`: Final model generation. Contains a `content` array with
    `text`, `image`, `audio`, etc. (REST responses use `"type": "model_output"`,
    **not** `"role": "model"`.)
*   `thought`: Model reasoning / chain of thought. Has a `signature` field and
    optional `summary`.
*   `function_call`: Tool call request, with flat `id`, `name`, and `arguments`
    fields (there is **no** nested `tool_calls` list).
*   `function_result`: Tool result you send back, with `call_id`, `name`, and
    `result` fields.
*   `google_search_call` / `google_search_result`, `code_execution_call` /
    `code_execution_result`, `url_context_call` / `url_context_result`,
    `mcp_server_tool_call` / `mcp_server_tool_result`, `file_search_call` /
    `file_search_result`: built-in and remote tool steps.

### Content types (inside the `content` array on `model_output` and `user_input` steps)

*   `text`: Text content (`text` field).
*   `image` / `audio` / `document` / `video`: Content with `data`, `mime_type`,
    or `uri`.

### Convenience accessor

*   `output_text`: The combined text from the trailing `model_output` steps.
    Prefer this over hand-walking `steps[-1].content[0].text`, which breaks when
    the last step is a tool call or a thought.

### Streaming Event Types

| Event                   | Description                                       |
| ----------------------- | ------------------------------------------------- |
| `interaction.created`   | Interaction created; includes metadata.           |
| `step.start`            | A new step begins. Contains the step `type` and   |
:                         : initial metadata.                                 :
| `step.delta`            | Incremental data for the current step. Contains a |
:                         : typed `delta` object (e.g. `delta.type == "text"` :
:                         : with `delta.text`).                               :
| `step.stop`             | The step is complete. Contains `index`.           |
| `interaction.completed` | Interaction finished. Contains final `usage`.     |

### Storage & retention

Interactions are stored by default (`store=True`), which enables stateful
features like `previous_interaction_id` and background execution. Passing
`store=False` disables server-side retention and therefore also disables
`previous_interaction_id` and `background` — in that mode you must pass the full
conversation history in `input` on each turn.
