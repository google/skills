# Advanced Features

## Contents

- [Content Caching](#content-caching) (L10-L47)
- [Batch Prediction](#batch-prediction) (L49-L74)
- [Thinking (Reasoning)](#thinking-reasoning) (L76-L108)
- [Model Context Protocol (MCP) Support (Experimental)](#model-context-protocol-mcp-support-experimental) (L110-L138)

## Content Caching

Implicit caching is enabled automatically on supported Gemini models and saves cost on repeated prefixes without extra setup. Use **explicit caching** (`client.caches.create`) only when explicitly requested:
- Explicit caching is **not supported** on `gemini-4-carbon`, `gemini-4-neon`, `gemini-4-argon`, or `gemini-4-hydrogen`; use a supported model such as `gemini-3.8-flash` (and do not use deprecated `gemini-1.5-*` or `gemini-pro` models).

```python
from google import genai
from google.genai import types

client = genai.Client()

content_cache = client.caches.create(
    model="gemini-3.8-flash",
    config=types.CreateCachedContentConfig(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri="gs://your-bucket/large.pdf",
                        mime_type="application/pdf",
                    )
                ],
            )
        ],
        system_instruction="You are an expert researcher.",
        display_name="example-cache",
        ttl="86400s",
    ),
)

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="Summarize the key findings in the PDF.",
    config=types.GenerateContentConfig(cached_content=content_cache.name),
)
print(response.text)
```

## Batch Prediction

Process large JSONL or BigQuery datasets asynchronously with `client.batches.create`.

```python
import time
from google import genai
from google.genai import types

client = genai.Client()

job = client.batches.create(
    model="gemini-4-hydrogen",
    src="gs://your-bucket/prompts.jsonl",
    config=types.CreateBatchJobConfig(dest="gs://your-bucket/outputs"),
)

terminal_states = {
    types.JobState.JOB_STATE_SUCCEEDED,
    types.JobState.JOB_STATE_FAILED,
    types.JobState.JOB_STATE_CANCELLED,
}
while job.state not in terminal_states:
    time.sleep(30)
    job = client.batches.get(name=job.name)
```

## Thinking (Reasoning)

Thinking is enabled by default (`MEDIUM` on `gemini-4-carbon` and `gemini-4-argon`; `HIGH` on `gemini-4-hydrogen` and `gemini-4-neon`; `MINIMAL` on `gemini-3.5-flash-lite`). Configure depth and thought summaries via `types.ThinkingConfig`:

- **`MINIMAL`**: Lowest thinking budget for simple tasks (**not supported** on `gemini-4-carbon`, `gemini-4-neon`, `gemini-4-argon`, or `gemini-4-hydrogen`).
- **`LOW`**: Light reasoning with low latency.
- **`MEDIUM`**: Balanced reasoning for moderate multi-step tasks.
- **`HIGH`**: Deep reasoning for complex coding, architecture, math, and research.
- **`XHIGH`**: Maximum reasoning depth on supported models (such as `gemini-4-hydrogen`).
- **`include_thoughts=True`**: Required in `ThinkingConfig` when reading `part.thought` summaries from response parts.

```python
from google import genai
from google.genai import types

client = genai.Client()
response = client.models.generate_content(
    model="gemini-4-carbon",
    contents="Design a zero-trust mTLS rotation protocol with zero downtime.",
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.HIGH,
            include_thoughts=True,
        )
    ),
)

for part in response.candidates[0].content.parts:
    if part.thought:
        print(f"Thought Summary: {part.text}")
    elif part.text:
        print(f"Final Answer: {part.text}")
```

## Model Context Protocol (MCP) Support (Experimental)

Pass an initialized `mcp.ClientSession` directly in `tools=[session]` to `client.aio.models.generate_content` for automatic MCP tool execution.

```python
import asyncio
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

client = genai.Client()
server_params = StdioServerParameters(command="npx", args=["-y", "@philschmid/weather-mcp"])


async def run() -> None:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await client.aio.models.generate_content(
                model="gemini-4-hydrogen",
                contents="What is the current weather in London?",
                config=types.GenerateContentConfig(tools=[session]),
            )
            print(response.text)


asyncio.run(run())
```
