# Model Tuning

Run Supervised Fine-Tuning (SFT, default) or Preference Tuning on JSONL datasets in Cloud Storage using `client.tunings.tune`.

- **Endpoint location**: Tuning jobs require a regional endpoint (for example, `location="us-central1"`), not `location="global"`.
- **Supported models**: Not all models support tuning (commonly tuned base models include `gemini-3.1-flash-lite` and `gemini-3.5-flash-lite`). Check [Supervised Tuning documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/supervised-tuning.md.txt) for current model and region support.
- **Key `types.CreateTuningJobConfig` options**: `tuned_model_display_name`, `epoch_count`, `learning_rate_multiplier`, `adapter_size`, `validation_dataset` (`types.TuningValidationDataset(gcs_uri=...)`), and `method` (`SUPERVISED_FINE_TUNING` or `PREFERENCE_TUNING`).

```python
import time
from google import genai
from google.genai import types

# Use a supported regional location for tuning jobs
client = genai.Client(enterprise=True, project="your-project-id", location="us-central1")

tuning_job = client.tunings.tune(
    base_model="gemini-3.1-flash-lite",
    training_dataset=types.TuningDataset(
        gcs_uri="gs://your-bucket/sft_train_data.jsonl",
    ),
    config=types.CreateTuningJobConfig(
        tuned_model_display_name="example-tuned-model",
        epoch_count=3,
    ),
)

running_states = {
    types.JobState.JOB_STATE_QUEUED,
    types.JobState.JOB_STATE_PENDING,
    types.JobState.JOB_STATE_RUNNING,
}
while tuning_job.state in running_states:
    time.sleep(60)
    tuning_job = client.tunings.get(name=tuning_job.name)

if tuning_job.state != types.JobState.JOB_STATE_SUCCEEDED:
    raise RuntimeError(f"Tuning failed with state {tuning_job.state}: {tuning_job.error}")

# Run inference by passing tuning_job.tuned_model.endpoint directly as model
response = client.models.generate_content(
    model=tuning_job.tuned_model.endpoint,
    contents="Why is the sky blue?",
)
print(response.text)
```
