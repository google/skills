"""Evaluate a MaaS model using Vertex AI Evaluation."""

import argparse
import pandas as pd
from vertexai import Client  # pytype: disable=import-error


def run_evaluation(
    *,
    project_id: str,
    location: str,
    model_id: str,
    dataset: str,
    metrics: list[str],
) -> pd.DataFrame:
  """Main function to run evaluation on a MaaS model.

  Args:
      project_id: The project ID.
      location: The location ID.
      model_id: The MaaS model ID.
      dataset: GCS path to the evaluation dataset (.jsonl).
      metrics: List of metrics to use for evaluation.

  Returns:
      Evaluation result from Vertex AI Evaluation.
  """
  client = Client(project=project_id, location=location)

  print(f"--- Running Inference for MaaS Model: {model_id} in {location} ---")

  try:
    maas_responses = client.evals.run_inference(
        model=model_id,
        src=dataset,
    )
  except Exception as e:
    raise RuntimeError(
        f"Error running inference for MaaS model: {model_id}"
    ) from e

  print(f"\n--- Running Evaluation for MaaS Model: {model_id} ---")
  try:
    maas_eval_result = client.evals.evaluate(
        dataset=maas_responses,
        metrics=metrics,
    )
  except Exception as e:
    raise RuntimeError(
        f"Error running evaluation for MaaS model: {model_id}"
    ) from e

  return maas_eval_result


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Evaluate a MaaS model using Vertex AI Evaluation."
  )
  parser.add_argument(
      "--project_id", type=str, required=True, help="Project ID."
  )
  parser.add_argument("--location", type=str, required=True, help="Location.")
  parser.add_argument(
      "--model_id", type=str, required=True, help="MaaS Model ID."
  )
  parser.add_argument(
      "--dataset",
      type=str,
      required=True,
      help="GCS path to evaluation dataset.",
  )
  parser.add_argument(
      "--metrics",
      type=str,
      nargs="+",
      default=["GENERAL_QUALITY"],
      help="List of metrics to use for evaluation.",
  )
  args = parser.parse_args()

  results = run_evaluation(**vars(args))

  print(f"""{"-" * 20}
Evaluation Summary Metrics:
{results.summary_metrics}
{"-" * 20}
Evaluation Details (first 5 rows):
{results.metrics_table.head(5)}
{"-" * 20}
Evaluation complete. Displaying report:""")
  results.show()
