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

Available open models can be found in Google Cloud [documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/open-model-tuning.md.txt).
This is the list of open models that are available for tuning; do not suggest
any other open models besides the one listed here.
Each model has some [limitations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/open-model-tuning.md.txt) for tuning.

## Model Resource Name Format

The names in the **Model** column below are display names. The tuning API does
not accept them. `--base_model` requires a publisher model **resource name**,
listed in the **Resource name** column of the table in
[Baseline Hyperparameter Recommendations](#baseline-hyperparameter-recommendations):

```
{publisher}/{model_id}@{version_id}
```

The longer form `publishers/{publisher}/models/{model_id}@{version_id}` is also
accepted.

> [!WARNING] Copy the resource name from the table; **do not construct it**.
> The `@{version_id}` suffix is mandatory, `{model_id}` is the *family*
> (`gemma3`, `qwen3`) rather than the variant, and the publisher is lowercase.
> Omitting the suffix is the single most common cause of
> `INVALID_ARGUMENT: Invalid open source publisher model resource name`;
> `google/gemma-3-4b-it` and `Qwen/Qwen3-8B` are both rejected.

The family segment cannot be derived from the display name:

- `meta/llama3_1` uses an underscore, but `meta/llama3-2` and `meta/llama3-3`
  use hyphens.
- Qwen 3.5 9B is `qwen/qwen3-5@qwen3.5-9b` -- hyphen in the family, dot in the
  version.
- Medgemma 1.5 4B IT is `google/medgemma@medgemma-1.5-4b-it`; the version, not
  the family, carries the `1.5`.

This format applies to `--base_model`, including the student in distillation.
Distillation teacher models use a different, unversioned form, such as
`qwen/qwen3-next-80b-a3b-thinking-maas`. See [Distillation](#distillation).

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

The **Resource name** column is the exact value to pass to `--base_model`.

Model                          | Resource name for `--base_model`             | Tuning Mode | Learning Rate | Epochs | Adapter Size (PEFT)
:----------------------------- | :------------------------------------------- | :---------- | :------------ | :----- | :------------------
Gemma 4 E2B IT                 | `google/gemma4@gemma-4-e2b-it`               | PEFT        | 2.0E-4        | 3      | 16
Gemma 4 E4B IT                 | `google/gemma4@gemma-4-e4b-it`               | PEFT        | 2.0E-4        | 3      | 16
Gemma 4 26B A4B IT             | `google/gemma4@gemma-4-26b-a4b-it`           | PEFT        | 2.0E-4        | 3      | 16
Gemma 4 31B IT                 | `google/gemma4@gemma-4-31b-it`               | PEFT        | 2.0E-4        | 3      | 16
Gemma 3 1B IT                  | `google/gemma3@gemma-3-1b-it`                | Full        | 2.0E-5        | 3      | N/A
Gemma 3 4B IT                  | `google/gemma3@gemma-3-4b-it`                | Full        | 1.0E-5        | 3      | N/A
Gemma 3 12B IT                 | `google/gemma3@gemma-3-12b-it`               | Full        | 1.0E-5        | 3      | N/A
Gemma 3 27B IT                 | `google/gemma3@gemma-3-27b-it`               | PEFT        | 2.0E-4        | 3      | 32
Gemma 3 27B IT                 | `google/gemma3@gemma-3-27b-it`               | Full        | 2.0E-4        | 3      | N/A
Medgemma 1.5 4B IT             | `google/medgemma@medgemma-1.5-4b-it`         | Full        | 1.0E-5        | 3      | N/A
Llama 3.1 8B                   | `meta/llama3_1@llama-3.1-8b`                 | PEFT        | 2.0E-4        | 3      | 16
Llama 3.1 8B                   | `meta/llama3_1@llama-3.1-8b`                 | Full        | 2.0E-4        | 3      | N/A
Llama 3.1 8B Instruct          | `meta/llama3_1@llama-3.1-8b-instruct`        | PEFT        | 2.0E-4        | 3      | 16
Llama 3.1 8B Instruct          | `meta/llama3_1@llama-3.1-8b-instruct`        | Full        | 2.0E-4        | 3      | N/A
Llama 3.2 1B Instruct          | `meta/llama3-2@llama-3.2-1b-instruct`        | Full        | 1.5E-6        | 3      | N/A
Llama 3.2 3B Instruct          | `meta/llama3-2@llama-3.2-3b-instruct`        | Full        | 1.0E-7        | 3      | N/A
Llama 3.3 70B Instruct         | `meta/llama3-3@llama-3.3-70b-instruct`       | PEFT        | 5.0E-5        | 3      | 16
Llama 3.3 70B Instruct         | `meta/llama3-3@llama-3.3-70b-instruct`       | Full        | 5.0E-5        | 3      | N/A
Llama 4 Scout 17B 16E Instruct | `meta/llama4@llama-4-scout-17b-16e-instruct` | PEFT        | 2.0E-5        | 3      | 16
Qwen 3.8 27B                   | `qwen/qwen3.8@qwen3.8-27b`                   | PEFT        | 8.0E-4        | 3      | 16
Qwen 3.6 27B                   | `qwen/qwen3-6@qwen3.6-27b`                   | PEFT        | 8.0E-4        | 3      | 16
Qwen 3.6 35B A3B               | `qwen/qwen3-6@qwen3.6-35b-a3b`               | PEFT        | 5.0E-4        | 1      | 16
Qwen 3.5 9B                    | `qwen/qwen3-5@qwen3.5-9b`                    | Full        | 2e-5          | 3      | N/A
Qwen 3 4B                      | `qwen/qwen3@qwen3-4b`                        | Full        | 7.5e-5        | 3      | N/A
Qwen 3 8B                      | `qwen/qwen3@qwen3-8b`                        | Full        | 5e-5          | 3      | N/A
Qwen 3 14B                     | `qwen/qwen3@qwen3-14b`                       | Full        | 4e-5          | 3      | N/A
Qwen 3 32B                     | `qwen/qwen3@qwen3-32b`                       | PEFT        | 2.0E-4        | 3      | 16
Qwen 3 32B                     | `qwen/qwen3@qwen3-32b`                       | Full        | 2.5e-5        | 3      | N/A
GLM 4.7 Flash                  | `zai-org/glm-4.7-flash@glm-4.7-flash`        | PEFT        | 2.0E-4        | 1      | 16

## Distillation

Distillation tunes a smaller student model on responses generated by a larger
teacher model. It is for open models only, and works best when the teacher is
much stronger than the student on the task, for example multi-step reasoning in
math, science, or medical question answering. It helps less when the student is
already close to the teacher, or on short-form tasks where the teacher's
reasoning adds nothing.

Teacher model                     | Resource name for `--teacher_model`
:-------------------------------- | :--------------------------------------
DeepSeek R1 0528 MaaS             | `deepseek-ai/deepseek-r1-0528-maas`
DeepSeek V3.2 MaaS                | `deepseek-ai/deepseek-v3.2-maas`
GLM 5.2 MaaS                      | `zai-org/glm-5.2-maas`
Kimi K2 Thinking MaaS             | `moonshotai/kimi-k2-thinking-maas`
Qwen 3 Next 80B A3B Thinking MaaS | `qwen/qwen3-next-80b-a3b-thinking-maas`

Student model  | Resource name for `--base_model`
:------------- | :-------------------------------
Qwen 3 4B      | `qwen/qwen3@qwen3-4b`
Qwen 3 8B      | `qwen/qwen3@qwen3-8b`
Qwen 3 14B     | `qwen/qwen3@qwen3-14b`
Qwen 3 32B     | `qwen/qwen3@qwen3-32b`
Gemma 3 1B IT  | `google/gemma3@gemma-3-1b-it`
Gemma 3 4B IT  | `google/gemma3@gemma-3-4b-it`
Gemma 3 12B IT | `google/gemma3@gemma-3-12b-it`
Gemma 3 27B IT | `google/gemma3@gemma-3-27b-it`

For the student's learning rate, epochs and tuning mode, start from its row in
the table above. If the user names a teacher or student that is not listed, say
it is not supported for distillation and offer the closest listed model.

## Supported Gemini Models for Supervised Fine-Tuning

| Model Display Name | Base Model Identifier for `base_model` / `source_model` | Recommended Use Case |
| :--- | :--- | :--- |
| Gemini 2.5 Flash | `gemini-2.5-flash` | **Default / Recommended** for fast turnaround, coding, math reasoning, and chat tasks. |
| Gemini 2.5 Flash Lite | `gemini-2.5-flash-lite` | Ultra-lightweight and fastest turnaround. |
| Gemini 2.5 Pro | `gemini-2.5-pro` | Complex multi-turn coding and advanced algorithmic reasoning. |

> [!CAUTION] **UNSUPPORTED / DEPRECATED GEMINI MODELS** Do NOT use or recommend
> `gemini-1.5-flash-002`, `gemini-1.5-pro-002`, or `gemini-1.5-flash` for
> tuning. The tuning service rejects them with `INVALID_ARGUMENT: Base model ...
> is not supported`. Always propose `gemini-2.5-flash` instead.
