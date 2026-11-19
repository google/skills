# Structured Output and Tools

## Contents

- [Structured Output (JSON Schema)](#structured-output-json-schema) (L10-L36)
- [Function Calling](#function-calling) (L38-L92)
- [Search Grounding](#search-grounding) (L94-L132)
- [Code Execution & URL Context](#code-execution--url-context) (L134-L161)

## Structured Output (JSON Schema)

Enforce a JSON schema by passing a Pydantic `BaseModel` or Python type annotation (e.g., `list[Movie]`) to `response_schema` with `response_mime_type="application/json"`.

```python
from google import genai
from google.genai import types
from pydantic import BaseModel


class Recipe(BaseModel):
    recipe_name: str
    ingredients: list[str]


client = genai.Client()
response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="List a few popular cookie recipes.",
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=list[Recipe],
    ),
)
print(response.text)    # Valid JSON string matching the schema
print(response.parsed)  # Parsed list[Recipe] instances
```

## Function Calling

Declare Python functions with type annotations and docstrings in `GenerateContentConfig(tools=[...])`.

- **Automatic Function Calling (default when passing Python callables)**: `generate_content` (or `chat.send_message`) automatically executes the Python function and returns the final natural-language answer in `response.text` (leaving `response.function_calls` empty on the final turn).
- **Manual Function Calling (`response.function_calls`)**: Set `automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)` to inspect `response.function_calls`, run the function yourself, and return `types.Part.from_function_response`.

```python
from google import genai
from google.genai import types


def get_current_weather(location: str) -> str:
    """Returns the current weather for a city and state (e.g., Boston, MA)."""
    return "Snowing" if "boston" in location.lower() else "Sunny"


client = genai.Client()

# Option A: Manual inspection & execution via response.function_calls
manual_config = types.GenerateContentConfig(
    tools=[get_current_weather],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)
response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="What is the weather like in Boston?",
    config=manual_config,
)

if response.function_calls:
    call = response.function_calls[0]
    result = get_current_weather(**dict(call.args))
    followup = client.models.generate_content(
        model="gemini-4-hydrogen",
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text="What is the weather like in Boston?")]),
            response.candidates[0].content,
            types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=call.name, response={"result": result})],
            ),
        ],
        config=manual_config,
    )
    print(followup.text)

# Option B: Automatic execution (SDK calls get_current_weather and returns final text)
auto_response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="What is the weather like in Boston?",
    config=types.GenerateContentConfig(tools=[get_current_weather]),
)
print(auto_response.text)
```

## Search Grounding

Ground responses in Google Search (or enterprise data via Agent Search, formerly Vertex AI Search) and read `grounding_metadata` from `response.candidates[0]`.

```python
from google import genai
from google.genai import types

client = genai.Client()
response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="When is the next total solar eclipse in the US?",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    ),
)
print(response.text)
metadata = response.candidates[0].grounding_metadata
print("Search Queries:", metadata.web_search_queries)
print("Pages:", [chunk.web.title for chunk in (metadata.grounding_chunks or []) if chunk.web])

# Ground on enterprise data via Agent Search (Vertex AI Search) datastore or engine
enterprise_resp = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="What is our parental leave policy?",
    config=types.GenerateContentConfig(
        tools=[
            types.Tool(
                retrieval=types.Retrieval(
                    vertex_ai_search=types.VertexAISearch(
                        datastore="projects/your-project-id/locations/global/collections/default_collection/dataStores/your-datastore-id"
                    )
                )
            )
        ]
    ),
)
print(enterprise_resp.text)
```

## Code Execution & URL Context

```python
from google import genai
from google.genai import types

client = genai.Client()

# Server-side Python code execution
code_resp = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="Calculate the 20th fibonacci number.",
    config=types.GenerateContentConfig(
        tools=[types.Tool(code_execution=types.ToolCodeExecution())],
    ),
)
print(code_resp.executable_code, code_resp.code_execution_result)

# Retrieve and ground on public web URLs supplied in the prompt
url_resp = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="Compare https://example.com and https://www.iana.org/domains/reserved",
    config=types.GenerateContentConfig(
        tools=[types.Tool(url_context=types.UrlContext())],
    ),
)
print(url_resp.text, url_resp.candidates[0].url_context_metadata)
```
