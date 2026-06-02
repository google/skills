# Creating Prompts in Agent Platform

This guide provides instructions on how to create a new managed prompt in
Agent Platform.

## Create a Prompt (Tier M)

**Confirmation Required**: As a Tier M (Mutating) operation, the agent MUST
pause and present a confirmation prompt with the project, region, prompt display
name, and model before providing the creation code.

> [!IMPORTANT]
> **Interactive Confirmation Required (Tier M):** Before proceeding with prompt
> creation, you **MUST** present the proposed Python code in a confirmation
> prompt to the user with 'Yes' and 'No' options.
> **CRITICAL:** When presenting this confirmation prompt to the user, you MUST
> output it as a direct plain text response and stop tool execution immediately.
> Do NOT call any command execution or interactive tools in the same turn, as
> unexpected tool calls may be auto-replied by the simulation harness and cause
> an infinite loop. Yield immediately for the user's reply.

```python
from google.cloud import vertexai
from google.genai import types as genai_types
from vertexai.preview import prompts

# Define contents
part = genai_types.Part(text="Hello, how are you?")
content = genai_types.Content(role="user", parts=[part])

prompt_data = vertexai.types.PromptData(
    model="gemini-2.5-pro",
    contents=[content],
)

prompt = vertexai.types.Prompt(prompt_data=prompt_data)

create_config = vertexai.types.CreatePromptConfig(
    prompt_display_name="my_new_prompt"
)

new_prompt = prompts.create(prompt=prompt, config=create_config)
print(f"Created prompt ID: {new_prompt.prompt_id}")
```
