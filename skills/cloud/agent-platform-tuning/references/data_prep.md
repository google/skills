# Data Preparation for Agent Platform Model Tuning

Agent Platform Model Tuning requires training data in **JSON Lines (JSONL)**
format stored in Google Cloud Storage (GCS).

## Supported JSONL Formats for Open Models

### 1. Conversational (Messages) Format
Recommended for chat-based models (Llama 3.1/3.2/3.3 Chat, Gemma 3 IT, etc.).

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"},
    {"role": "assistant", "content": "The capital of France is Paris."}
  ]
}
```

### 2. Instruction (Prompt/Completion) Format
Suitable for base models or simple completion tasks.

```json
{
  "prompt": "Summarize the following text: [TEXT]",
  "completion": "[SUMMARY]"
}
```

### Distillation datasets

The training dataset can contain prompts only, because the teacher model writes
the responses. Use the messages format with just the user turn:

```json
{"messages": [{"role": "user", "content": "What is 17 * 24?"}]}
```

To build it from a CSV, JSON, Parquet or Hugging Face export, map only the
prompt column and pass `--prompt_only`:

```bash
python3 scripts/prepare_dataset.py \
    --input questions.csv \
    --output prompts.jsonl \
    --prompt_col question \
    --prompt_only
```

A validation dataset must still include responses, because it is used to score
the student during tuning. So don't split a prompt-only file: `--prompt_only`
writes no validation split and rejects a nonzero `--validation_split`.
Validation is optional; if the user wants it, prepare it separately from data
that has responses, using the normal conversion.

## Dataset Requirements

- **File Type**: Must be `.jsonl`.
- **Encoding**: UTF-8.
- **Location**: Must be in a GCS bucket (e.g., `gs://my-bucket/train.jsonl`).
- **Validation Split**: A separate validation file is optional but recommended. It must be no more than 25% of the training dataset **file size in bytes**, and no more than 5000 rows.

### Sizing the validation split

The 25% ceiling is measured against the training file, not against the whole
dataset, so a split fraction `s` has to satisfy `s / (1 - s) <= 0.25`, i.e.
`s <= 0.2`. An 80/20 split therefore sits exactly on the limit and is rejected
as soon as the held-out rows are slightly longer than average -- observed
overshoots run from 25.03% to 26.45%. Use `--validation_split 0.1`, which
leaves the validation file at about 11% of the training file.

`scripts/prepare_dataset.py` measures the written files and fails before
upload if the ratio is over the limit, so a rejection here never costs a
tuning job submission.

## Bucket Considerations

Artifacts must live in a bucket the user has chosen. **Never invent a bucket
name, derive one from the project number, or create a bucket unprompted.**
Creating a bucket is a mutating action and requires explicit Tier M
confirmation.

If the user has not named a bucket, stop and ask which one they want to use, and
offer to create one for them as one of the options. Only once they have
confirmed the exact name and location should you run the create command.

Because the default tuning location is `global` — the service picks whichever
region has GPU capacity — a new bucket should be a multi-region so it stays
reachable wherever the job lands. Propose `US` (or `EU` if the data must stay in
Europe):

```bash
# Run only after the user has confirmed the bucket name and location.
# Substitute the confirmed name; never run this with the placeholder as-is.
gcloud storage buckets create gs://CONFIRMED_BUCKET_NAME --location=US
```

Only pin the bucket to a single region when the tuning job itself is pinned to
that region.

## Formatting Best Practices

1. **Quality over Quantity**: 100 high-quality examples often outperform 1,000 noisy ones.
2. **Consistency**: Use consistent formatting for system prompts and instruction styles.
3. **No Empty Values**: Ensure every example has a valid prompt/user message and
   completion/assistant response. Use the [preparation script](../scripts/prepare_dataset.py) to validate this.
