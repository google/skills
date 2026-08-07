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

## Dataset Requirements

- **File Type**: Must be `.jsonl`.
- **Encoding**: UTF-8.
- **Location**: Must be in a GCS bucket (e.g., `gs://my-bucket/train.jsonl`).
- **Validation Split**: A separate validation file is optional but recommended. It must be no more than 25% of the training dataset size.

## Bucket Considerations

If a bucket does not exist, create one. Because the default tuning location is
`global` — the service picks whichever region has GPU capacity — the bucket
should be a multi-region so it stays reachable wherever the job lands. Use `US`
(or `EU` if the data must stay in Europe):

```bash
gcloud storage buckets create gs://YOUR_BUCKET_NAME --location=US
```

Only pin the bucket to a single region when the tuning job itself is pinned to
that region.

## Formatting Best Practices

1. **Quality over Quantity**: 100 high-quality examples often outperform 1,000 noisy ones.
2. **Consistency**: Use consistent formatting for system prompts and instruction styles.
3. **No Empty Values**: Ensure every example has a valid prompt/user message and
   completion/assistant response. Use the [preparation script](../scripts/prepare_dataset.py) to validate this.
