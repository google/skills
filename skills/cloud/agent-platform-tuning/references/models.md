# Agent Platform Supported Models and Recommendations

This reference catalog provides technical specifications, tuning
recommendations, and deployment hardware requirements for supported models in
Agent Platform.

## Supported Models Catalog

> [!WARNING] **CRITICAL AGENT INSTRUCTION**
> Do NOT use this catalog to recommend a specific model to the user until they
> have explicitly confirmed their **Model Category** as Open Model.
> Furthermore, do NOT recommend any model that is not explicitly listed in this
> catalog, as the tuning service does not support it.
> When a user asks for a model that is not listed, do not stop at refusing it.
> Say it is not supported for tuning, then offer the closest model that is
> listed, preferring the same family and the nearest size, and let the user
> decide. A model missing from this catalog is usually a release that is newer
> than the tuning service supports, so the previous release of that same family
> is normally the right suggestion.

Available open models can be found in Google Cloud [documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/open-model-tuning.md.txt).
This is the list of open models that are available for tuning; do not suggest
any other open models besides the one listed here.
Each model has some [limitations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/open-model-tuning.md.txt) for tuning.

## Model Selection Guidelines

**Identify Task**: Check a few samples from the dataset to identify the task.

Choose a model family based on your task type:

- **Qwen**: Best for code generation or complex math-based tasks.
- **Gemma**: Optimized for chat-based interactions, creative writing and multilingual tasks.
- **Llama (Instruct)**: Strong general-purpose chat/instruction models.
- **Llama (Base/Scout)**: Best for continuation tasks or building custom instruction-tuned models.

**Complexity Heuristics**:

- **Simple (QA, Extraction)**: 1B - 3B models.
- **Intermediate (Summarization, Reasoning)**: 8B - 17B models.
- **Complex (Multi-turn, Tool use, Deep reasoning)**: 27B - 70B models.

## Baseline Hyperparameter Recommendations

These values are starting points and should be adjusted based on your dataset
size.

| Model | Tuning Mode | Learning Rate | Epochs | Adapter Size (PEFT) |
| :--- | :--- | :--- | :--- | :--- |
| Gemma 4 E2B IT | PEFT | 2.0E-4 | 3 | 16 |
| Gemma 4 E4B IT | PEFT | 2.0E-4 | 3 | 16 |
| Gemma 4 26B A4B IT | PEFT | 2.0E-4 | 3 | 16 |
| Gemma 4 31B IT | PEFT | 2.0E-4 | 3 | 16 |
| Gemma 3 1B IT | Full | 2.0E-5 | 3 | N/A |
| Gemma 3 4B IT | Full | 1.0E-5 | 3 | N/A |
| Gemma 3 12B IT | Full | 1.0E-5 | 3 | N/A |
| Gemma 3 27B IT | PEFT | 2.0E-4 | 3 | 32 |
| Gemma 3 27B IT | Full | 2.0E-4 | 3 | N/A |
| Llama 3.1 8B | PEFT | 2.0E-4 | 3 | 16 |
| Llama 3.1 8B | Full | 2.0E-4 | 3 | N/A |
| Llama 3.1 8B Instruct | PEFT | 2.0E-4 | 3 | 16 |
| Llama 3.1 8B Instruct | Full | 2.0E-4 | 3 | N/A |
| Llama 3.2 1B Instruct | Full | 1.5E-6 | 3 | N/A |
| Llama 3.2 3B Instruct | Full | 1.0E-7 | 3 | N/A |
| Llama 3.3 70B Instruct | PEFT | 5.0E-5 | 3 | 16 |
| Llama 3.3 70B Instruct | Full | 5.0E-5 | 3 | N/A |
| Llama 4 Scout 17B 16E | PEFT | 2.0E-5 | 3 | 16 |
| Qwen 3.5 9B | Full | 2e-5 | 3 | N/A |
| Qwen 3 4B | Full | 7.5e-5 | 3 | N/A |
| Qwen 3 8B | Full | 5e-5 | 3 | N/A |
| Qwen 3 14B | Full | 4e-5 | 3 | N/A |
| Qwen 3 32B | PEFT | 2.0E-4 | 3 | 16 |
| Qwen 3 32B | Full | 2.5e-5 | 3 | N/A |