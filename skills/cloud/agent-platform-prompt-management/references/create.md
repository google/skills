# Creating Prompts in Agent Platform

This guide provides instructions on how to create a new managed prompt in
Agent Platform.

## Create a Prompt (Tier M)

**Confirmation Required**: As a Tier M (Mutating) operation, the agent MUST
pause and present a confirmation prompt with the project, region, prompt display
name, and model before executing the creation code. After the user approves with
'Yes', execute the creation snippet using `run_command` in the execution
environment.

> [!IMPORTANT] **Interactive Confirmation Required (Tier M):** Before executing
> prompt creation via `run_command`, you **MUST** pause and present an
> interactive confirmation showing the exact `prompts.create_version(...)`
> Python snippet with every parameter resolved (target project, location,
> display name, target model, and prompt template text) alongside 'Yes' and 'No'
> options. **CRITICAL:** Do NOT execute the prompt creation Python snippet
> (`run_command`) in the same turn as presenting the confirmation. End your turn
> and wait for the user's explicit confirmation ('Yes' / approval) before
> running `run_command`.
>
```python
import vertexai
from vertexai.preview import prompts
from vertexai.preview.prompts import Prompt

vertexai.init(project="PROJECT_ID", location="LOCATION_ID")

# Construct a local Prompt object. `prompt_name` is the display name shown
# in Agent Platform Studio; `prompt_data` is the prompt text/template
# (use `{variable_name}` placeholders for variables passed to
# `assemble_contents()`); `model_name` is the target model -- ask the user
# which model to use, do not default to whatever this example happens to show.
local_prompt = Prompt(
    prompt_name="my_new_prompt",
    prompt_data="Hello, how are you? {text}",
    model_name="MODEL_ID",
)

# Persist the local Prompt as a new managed prompt resource. This creates
# the prompt AND its first version in a single call. The returned
# `persisted_prompt` is a Prompt object with `prompt_id` and `version_id`
# populated.
persisted_prompt = prompts.create_version(prompt=local_prompt)
print(f"Created prompt ID: {persisted_prompt.prompt_id}")
print(f"Version ID: {persisted_prompt.version_id}")
```

### Execution After Confirmation
Once the user confirms prompt creation (replies 'Yes' or approves):

1. Immediately execute the `prompts.create_version` snippet via `run_command`
   in the execution environment.
2. Capture and report the newly created prompt ID and version ID to the user.
3. NEVER call `answer_knowledge_question` or output code text claiming lack
   of access after confirmation.
