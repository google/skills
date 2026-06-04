"""Evaluate a Vertex AI endpoint using Vertex AI Evaluation."""

import argparse
import json
import subprocess

import pandas as pd
import requests
from vertexai import Client  # pytype: disable=import-error


def run_inference(prompt: str, endpoint_url: str, token: str) -> str:
  """Runs inference on a prompt.

  Args:
      prompt: The prompt to send to the model.
      endpoint_url: The URL of the Vertex AI endpoint.
      token: The gcloud access token.

  Returns:
      The model's response.
  """
  headers = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
  }

  payload = {
      "instances": [{
          "@requestFormat": "chatCompletions",
          "messages": [{"role": "user", "content": prompt}],
          "max_tokens": 100,
      }]
  }

  try:
    with requests.post(
        endpoint_url,
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    ) as response:
      response.raise_for_status()
      json_response = response.json()

      try:
        preds = json_response.get("predictions")
        if not preds:
          raise ValueError(f"No predictions in response: {json_response}")

        if isinstance(preds, dict):
          return str(preds["choices"][0]["message"]["content"])

        if not isinstance(preds, list):
          raise ValueError(f"Unexpected preds type: {type(preds)}")

        first_pred = preds[0]
        if isinstance(first_pred, list):
          if not first_pred:
            raise ValueError(f"Empty inner prediction list: {json_response}")
          return str(first_pred[0]["message"]["content"])
        elif isinstance(first_pred, dict):
          return str(first_pred["choices"][0]["message"]["content"])
        raise ValueError(
            f"Unable to parse prediction response: {json_response}"
        )
      except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Unable to parse prediction response: {json_response}"
        ) from e

  except requests.exceptions.RequestException as e:
    raise RuntimeError("Error calling Vertex AI endpoint.") from e


def run_evaluation(
    *,
    project_id: str,
    location: str,
    endpoint_id: str,
    dataset: str,
    dedicated_endpoint_dns: str | None = None,
    metrics: list[str],
) -> pd.DataFrame:
  """Main function to run evaluation on a Vertex AI endpoint.

  Args:
      project_id: The project ID.
      location: The location ID.
      endpoint_id: The endpoint ID.
      dataset: GCS path to the evaluation dataset (.jsonl).
      dedicated_endpoint_dns: Dedicated DNS for the endpoint.
      metrics: List of metrics to use for evaluation.

  Returns:
      Evaluation result from Vertex AI Evaluation.
  """
  client = Client(project=project_id, location=location)

  print(f"--- Running Evaluation for Endpoint: {endpoint_id} in {location} ---")

  if dedicated_endpoint_dns is not None:
    endpoint_url = f"https://{dedicated_endpoint_dns}/v1/projects/{project_id}/locations/{location}/endpoints/{endpoint_id}:predict"
  else:
    endpoint_url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/endpoints/{endpoint_id}:predict"
  try:
    token = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
  except subprocess.CalledProcessError as e:
    raise RuntimeError("Error getting gcloud access token.") from e

  try:
    jsonl_content = subprocess.run(
        ["gsutil", "cat", dataset],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
  except subprocess.CalledProcessError as e:
    raise RuntimeError(f"Error reading dataset from {dataset}.") from e

  dataset_list = []
  for line in jsonl_content.strip().split("\n"):
    if line:
      dataset_list.append(json.loads(line))

  df = pd.DataFrame(dataset_list)
  if "prompt" not in df.columns:
    raise ValueError("Dataset missing 'prompt' column in JSONL file.")

  df["response"] = df["prompt"].apply(
      lambda prompt: run_inference(prompt, endpoint_url, token)
  )

  eval_result = client.evals.evaluate(
      dataset=df,
      prompt_column="prompt",
      response_column="response",
      metrics=metrics,
  )

  return eval_result


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Evaluate a Vertex AI endpoint using Vertex AI Evaluation."
  )
  parser.add_argument(
      "--project_id", type=str, required=True, help="Project ID."
  )
  parser.add_argument("--location", type=str, required=True, help="Location.")
  parser.add_argument(
      "--endpoint_id", type=str, required=True, help="Endpoint ID."
  )
  parser.add_argument(
      "--dedicated_endpoint_dns",
      type=str,
      help="Dedicated endpoint DNS.",
  )
  parser.add_argument(
      "--dataset",
      type=str,
      required=True,
      help="GCS path to evaluation dataset.",
  )
  parser.add_argument(
      "--project_number", type=str, help="Project number for dedicated DNS."
  )
  parser.add_argument(
      "--metrics",
      type=str,
      nargs="+",
      default=["GENERAL_QUALITY"],
      help="List of metrics to use for evaluation.",
  )
  args = parser.parse_args()

  result = run_evaluation(**vars(args))

  print(f"""{"-" * 20}
Evaluation Summary Metrics:
{result.summary_metrics}
{"-" * 20}
Evaluation Details (first 5 rows):
{result.metrics_table.head(5)}""")
