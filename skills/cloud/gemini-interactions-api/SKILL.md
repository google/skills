---
name: gemini-interactions-api
description: Guides the usage of Gemini Interactions API on Gemini Enterprise Agent Platform. Use when the user wants to use the stateful, server-managed Interactions API for multi-turn conversations, background execution, streaming, structured output, and function calling on the Agent Platform.
---

# Gemini Interactions API Skill

This skill provides instructions for authenticating, connecting to, and
utilizing the stateful, server-managed **Gemini Interactions API** on Gemini
Enterprise Agent Platform.

The Interactions API is the modern, recommended way to execute Generative AI
agent conversations, background research tasks, multi-turn chats, and
structured, multi-step workflows.

> [!IMPORTANT]
>
> **CRITICAL: Unified SDK & Latest Models**
>
> *   **Unified SDK**: Use the Google Gen AI SDK (**`google-genai >= 2.0.0`**
>     for Python, **`@google/genai >= 2.0.0`** for JS/TS). Legacy SDKs like
>     `google-cloud-aiplatform`, `@google-cloud/vertexai`, and
>     `google-generativeai` are strictly unsupported for Interactions.
>     *   *Mandatory Instruction*: When explaining client initialization or
>         writing import code, you **must** explicitly state/warn the user that
>         legacy packages like `google-cloud-aiplatform` or
>         `google-generativeai` are strictly unsupported for interactions.
> *   **Latest Models Only**: Use `gemini-3.1-pro-preview`,
>     `gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-2.5-pro`, or
>     `gemini-2.5-flash`. Refer to the
>     [latest model versions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate)
>     to check for new updates. Legacy models (`gemini-2.0-*`, `gemini-1.5-*`)
>     are deprecated and do not support interactions.
>     *   *Mandatory Instruction*: In any interaction response, you **must**
>         warn the user that legacy models like `gemini-2.0` or `gemini-1.5` are
>         deprecated and unsupported for the Interactions API.
> *   **Turn-Scoped Parameters**: Parameters like `tools`, `system_instruction`,
>     and `generation_config` are turn-scoped. They **MUST** be passed with each
>     interaction request.

## 1. Authentication

Before running any code, ensure you are authenticated with Application Default
Credentials (ADC) and have the necessary API enabled.

1.  **Login**:

    ```bash
    gcloud auth application-default login
    ```

2.  **Enable API** (if not already enabled):

    ```bash
    gcloud services enable aiplatform.googleapis.com
    ```

--------------------------------------------------------------------------------

## 2. Client Initialization

You can initialize the client using environment variables (recommended) or by
passing explicit configuration parameters.

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

--------------------------------------------------------------------------------

## 3. Core Interactions API Usage

### Quick Start (Single-Turn)

Submit a single prompt and read the final text response. Under the modern
schema, output content is retrieved from the `steps` list.

#### Python

```python
interaction = client.interactions.create(
    model="gemini-3-flash-preview",
    input="Explain serverless computing in one sentence."
)
# Output text is located under steps
print(interaction.steps[-1].content[0].text)
```

#### TypeScript/JavaScript

```typescript
const interaction = await ai.interactions.create({
    model: "gemini-3-flash-preview",
    input: "Explain serverless computing in one sentence."
});
console.log(interaction.steps[interaction.steps.length - 1].content[0].text);
```

--------------------------------------------------------------------------------

### Stateful Conversation (Multi-Turn)

Interactions are stateful by default. Store the conversation state in the cloud
and reference it in the subsequent turn using `previous_interaction_id`.

#### Python

```python
# Turn 1: Introduce ourselves
turn1 = client.interactions.create(
    model="gemini-3-flash-preview",
    input="Hi! My name is John. I am working on AI agents.",
    store=True
)
print(f"Turn 1: {turn1.steps[-1].content[0].text}")

# Turn 2: Refer back to the stored turn state
turn2 = client.interactions.create(
    model="gemini-3-flash-preview",
    input="What is my name?",
    previous_interaction_id=turn1.id
)
print(f"Turn 2: {turn2.steps[-1].content[0].text}")
```

#### TypeScript/JavaScript

```typescript
// Turn 1
const turn1 = await ai.interactions.create({
    model: "gemini-3-flash-preview",
    input: "Hi! My name is John. I am working on AI agents.",
    store: true
});

// Turn 2
const turn2 = await ai.interactions.create({
    model: "gemini-3-flash-preview",
    input: "What is my name?",
    previousInteractionId: turn1.id
});
console.log(turn2.steps[turn2.steps.length - 1].content[0].text);
```

--------------------------------------------------------------------------------

### Real-Time Streaming

Stream responses in real-time. Passing `stream=True` returns an iterable chunk
generator.

#### Python

```python
response = client.interactions.create(
    model="gemini-3-flash-preview",
    input="Write a short poem about debugging.",
    stream=True
)

for chunk in response:
    if chunk.steps:
        step = chunk.steps[-1]
        if step.content and step.content[0].text:
            print(step.content[0].text, end="", flush=True)
print()
```

#### TypeScript/JavaScript

```typescript
const responseStream = await ai.interactions.create({
    model: "gemini-3-flash-preview",
    input: "Write a short poem about debugging.",
    stream: true
});

for await (const chunk of responseStream) {
    if (chunk.steps) {
        const step = chunk.steps[chunk.steps.length - 1];
        if (step.content && step.content[0].text) {
            process.stdout.write(step.content[0].text);
        }
    }
}
console.log();
```

--------------------------------------------------------------------------------

### Structured Output (Pydantic / Polymorphic `response_format`)

Retrieve structured, type-safe JSON matching a schema. Under the modern
Interactions API, a polymorphic `response_format` argument directly takes the
target schema structure.

#### Python

```python
from pydantic import BaseModel, Field

class Book(BaseModel):
    title: str = Field(description="The title of the book")
    author: str = Field(description="The book's author")
    year_published: int

interaction = client.interactions.create(
    model="gemini-3-flash-preview",
    input="Recommend one famous sci-fi book.",
    response_format=Book
)

# The text will be a valid JSON matching the Book schema
print(interaction.steps[-1].content[0].text)
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
    model: "gemini-3-flash-preview",
    input: "Recommend one famous sci-fi book.",
    responseFormat: BookSchema
});

console.log(interaction.steps[interaction.steps.length - 1].content[0].text);
```

--------------------------------------------------------------------------------

### Function Calling (Agent Tool Use)

Define local tools (functions) and submit execution results to the stateful
interaction history.

#### Python

```python
def get_stock_price(ticker: str) -> float:
    """Gets the stock price for a given ticker symbol."""
    if ticker.upper() == "GOOG":
        return 175.50
    return 100.0

# Turn 1: Pass tools to the model
interaction = client.interactions.create(
    model="gemini-3-flash-preview",
    input="What is the stock price of GOOG?",
    tools=[get_stock_price]
)

last_step = interaction.steps[-1]
# Check if the model requested a function call
if last_step.tool_calls:
    for call in last_step.tool_calls:
        if call.name == "get_stock_price":
            ticker_arg = call.args.get("ticker")
            price = get_stock_price(ticker_arg)

            # Turn 2: Submit function execution result statefully
            final_turn = client.interactions.create(
                model="gemini-3-flash-preview",
                input=f"The stock price for {ticker_arg} is ${price}.",
                previous_interaction_id=interaction.id
            )
            print(final_turn.steps[-1].content[0].text)
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
const interaction = await ai.interactions.create({
    model: "gemini-3-flash-preview",
    input: "What is the stock price of GOOG?",
    tools: [{
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
    }]
});

const lastStep = interaction.steps[interaction.steps.length - 1];
// Check if the model requested a function call
if (lastStep.toolCalls) {
    for (const call of lastStep.toolCalls) {
        if (call.name === "getStockPrice") {
            const tickerArg = call.args.ticker as string;
            const price = getStockPrice({ ticker: tickerArg });

            // Turn 2: Submit function execution result statefully
            const finalTurn = await ai.interactions.create({
                model: "gemini-3-flash-preview",
                input: `The stock price for ${tickerArg} is $${price}.`,
                previousInteractionId: interaction.id
            });
            console.log(finalTurn.steps[finalTurn.steps.length - 1].content[0].text);
        }
    }
}
```

--------------------------------------------------------------------------------

## 4. Accessing the Interactions API via REST

For shell-based scripts, debugging, or non-Python/JS environments, you can
communicate with the stateful Interactions API directly using raw HTTP/REST
requests via `curl`.

### 1. REST Endpoint

The REST API endpoint for interactions is:

```http
POST https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/interactions
```

*   **LOCATION**: Use `global` (or custom region if required).
*   **PROJECT_ID**: Your Google Cloud Project ID.

### 2. Set up Variables & Authentication Header

Set your target agent ID (e.g., model or custom agent path) and access token
generated from Application Default Credentials:

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
      "role": "user",
      "content": [{
        "type": "text",
        "text": "Explain serverless computing in one sentence."
      }]
    }]
  }'
```

#### Response Example

A synchronous POST request returns a JSON object containing the conversation
step details and unique identifiers:

```json
{
  "id": "your-interaction-id",
  "status": "completed",
  "steps": [
    {
      "role": "model",
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

To continue an existing conversation statefully, specify the
`previous_interaction_id` in the JSON payload:

```bash
curl -X POST "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/interactions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "'"${AGENT_ID}"'",
    "store": true,
    "previous_interaction_id": "YOUR_PREVIOUS_INTERACTION_ID",
    "input": [{
      "role": "user",
      "content": [{
        "type": "text",
        "text": "Can you elaborate on that?"
      }]
    }]
  }'
```

### 5. Streaming Output Payload

To stream updates in real time (Server-Sent Events format), pass `"stream":
true` in the payload:

```bash
curl -X POST "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/interactions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "'"${AGENT_ID}"'",
    "stream": true,
    "input": [{
      "role": "user",
      "content": [{
        "type": "text",
        "text": "Write a long story about space travel."
      }]
    }]
  }'
```

The endpoint will return a chunked stream where each event begins with `data: `
containing JSON updates with the `event_type` and step contents.

> **How `curl` handles streaming:** By default, when `"stream": true` is passed,
> the server responds with `Transfer-Encoding: chunked` and `Content-Type:
> text/event-stream` (Server-Sent Events). `curl` will automatically keep the
> connection open and print the incoming data chunks to `stdout` in real time as
> they are pushed by the server. The user does not need to poll or pull further;
> the complete sequence of events streams continuously until completion.
