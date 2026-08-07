"""Module for launching Agent Platform model tuning jobs."""

import argparse
import logging

from google import genai
from google.genai import types


def tune_open_model(
    project: str,
    location: str,
    base_model: str,
    train_dataset: str,
    validation_dataset: str | None,
    output_uri: str,
    epochs: int,
    learning_rate: float,
    tuning_mode: str,
    adapter_size: int | None = None,
) -> types.TuningJob:
  """Launches a Agent Platform model tuning job."""
  training_ds = types.TuningDataset(gcs_uri=train_dataset)
  validation_ds = (
      types.TuningValidationDataset(gcs_uri=validation_dataset)
      if validation_dataset
      else None
  )

  if tuning_mode == "FULL":
    mapped_tuning_mode = types.TuningMode.TUNING_MODE_FULL
  elif tuning_mode == "PEFT_ADAPTER":
    mapped_tuning_mode = types.TuningMode.TUNING_MODE_PEFT_ADAPTER
  else:
    raise ValueError(
        f"Unsupported tuning mode: {tuning_mode}. Supported modes are: FULL,"
        " PEFT_ADAPTER."
    )
  adapter_map = {
      1: "ADAPTER_SIZE_ONE",
      2: "ADAPTER_SIZE_TWO",
      4: "ADAPTER_SIZE_FOUR",
      8: "ADAPTER_SIZE_EIGHT",
      16: "ADAPTER_SIZE_SIXTEEN",
      32: "ADAPTER_SIZE_THIRTY_TWO",
  }
  mapped_adapter = adapter_map.get(adapter_size) if adapter_size else None

  config = types.CreateTuningJobConfig(
      epoch_count=epochs,
      learning_rate=learning_rate,
      validation_dataset=validation_ds,
      tuning_mode=mapped_tuning_mode,
      adapter_size=mapped_adapter,
      output_uri=output_uri,
      labels={"mg-source": "agent-platform-tuning-skill"},
  )
  with genai.Client(
      enterprise=True, project=project, location=location
  ) as client:
    tuning_job = client.tunings.tune(
        base_model=base_model,
        training_dataset=training_ds,
        config=config,
    )

  logging.info("Tuning job launched: %s", tuning_job.name)
  job_id = tuning_job.name.split("/")[-1] if tuning_job.name else "unknown"
  logging.info(
      "View job in console:"
      "https://console.cloud.google.com/agent-platform/tuning/locations/%s/tuningJob/%s/monitor?project=%s",
      location,
      job_id,
      project,
  )
  return tuning_job


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Launch Vertex AI Model Tuning Job"
  )
  parser.add_argument("--project", required=True)
  # `global` lets the service pick a region with available GPU capacity.
  parser.add_argument("--location", default="global")
  parser.add_argument("--base_model", required=True)
  parser.add_argument("--train_dataset", required=True)
  parser.add_argument(
      "--validation_dataset", help="Optional validation dataset URI"
  )
  parser.add_argument("--output_uri", required=True)
  parser.add_argument("--epochs", type=int, required=True)
  parser.add_argument("--learning_rate", type=float, required=True)
  parser.add_argument(
      "--tuning_mode", choices=("FULL", "PEFT_ADAPTER"), required=True
  )
  parser.add_argument(
      "--adapter_size",
      type=int,
      choices=(1, 4, 8, 16, 32),
      help="Adapter size for PEFT",
  )

  args = parser.parse_args()
  tune_open_model(**vars(args))
