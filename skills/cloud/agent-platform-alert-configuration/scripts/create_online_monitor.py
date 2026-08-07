# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helper script to create a Vertex AI Reasoning Engine Online Monitor."""

import argparse
import sys
import typing

try:
  from google.cloud import aiplatform_v1beta1  # pytype: disable=import-error
except ImportError:
  from google.cloud.aiplatform import aiplatform_v1beta1  # pytype: disable=import-error


EXPECTED_METRICS = {
    "hallucination_v1",
    "final_response_quality_v1",
    "tool_use_quality_v1",
}


def _verify_configuration(
    evaluator: typing.Any, target_sampling_percentage: int
) -> bool:
  """Checks if the existing monitor config matches the desired settings.

  Args:
      evaluator: The OnlineEvaluator instance to verify.
      target_sampling_percentage: The expected sampling percentage.

  Returns:
      True if the configuration matches, False otherwise.
  """
  actual_metrics = set()
  for metric_source in evaluator.metric_sources:
    spec = metric_source.metric.predefined_metric_spec
    if spec and spec.metric_spec_name:
      actual_metrics.add(spec.metric_spec_name)

  if actual_metrics != EXPECTED_METRICS:
    return False

  config = evaluator.config
  actual_sampling = 10  # Platform Default
  if config and config.random_sampling:
    actual_sampling = config.random_sampling.percentage

  if int(actual_sampling) != int(target_sampling_percentage):
    return False

  return True


def create_agent_online_monitor(
    project_id: str,
    location: str,
    agent_resource_name: str,
    sampling_percentage: int = 10,
) -> str:
  """Checks for matching monitor and creates one if none exists.

  Args:
      project_id: The GCP project ID.
      location: The GCP location (region).
      agent_resource_name: The full resource name of the agent.
      sampling_percentage: The desired sampling percentage (default 10).

  Returns:
      The resource name of the matching or created Online Evaluator.
  """
  client = aiplatform_v1beta1.OnlineEvaluatorServiceClient(
      client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
  )

  parent = f"projects/{project_id}/locations/{location}"

  # 1. Look for a monitor that matches our config exactly
  request = aiplatform_v1beta1.ListOnlineEvaluatorsRequest(parent=parent)
  page_result = client.list_online_evaluators(request=request)

  matching_evaluator = None
  for evaluator in page_result:
    if evaluator.agent_resource == agent_resource_name:
      if _verify_configuration(evaluator, sampling_percentage):
        matching_evaluator = evaluator
        break

  if matching_evaluator:
    print(
        f"Found matching Online Monitor: {matching_evaluator.name}. No action"
        " needed."
    )
    return matching_evaluator.name

  # 2. If no matching monitor is found, create a new one
  print("No matching Online Monitor found for agent. Creating a new one...")
  cloud_obs_spec = aiplatform_v1beta1.OnlineEvaluator.CloudObservability
  online_evaluator = aiplatform_v1beta1.OnlineEvaluator(
      display_name="agent-quality-monitor",
      agent_resource=agent_resource_name,
      cloud_observability=cloud_obs_spec(
          open_telemetry=cloud_obs_spec.OpenTelemetry(
              semconv_version="gen_ai_latest_experimental"
          ),
          trace_scope=cloud_obs_spec.TraceScope(),
      ),
      metric_sources=[
          aiplatform_v1beta1.MetricSource(
              metric=aiplatform_v1beta1.Metric(
                  predefined_metric_spec=aiplatform_v1beta1.PredefinedMetricSpec(
                      metric_spec_name=m
                  )
              )
          )
          for m in EXPECTED_METRICS
      ],
      config=aiplatform_v1beta1.OnlineEvaluator.Config(
          random_sampling=(
              aiplatform_v1beta1.OnlineEvaluator.Config.RandomSampling(
                  percentage=sampling_percentage
              )
          )
      ),
  )

  request = aiplatform_v1beta1.CreateOnlineEvaluatorRequest(
      parent=parent,
      online_evaluator=online_evaluator,
  )

  print(f"Creating Online Monitor for agent: {agent_resource_name}...")
  operation = client.create_online_evaluator(request=request)
  response = operation.result()
  print(f"Online Monitor created successfully: {response.name}")
  return response.name


def main():
  parser = argparse.ArgumentParser(
      description="Provision a Vertex AI Reasoning Engine Online Monitor."
  )
  parser.add_argument("--project-id", required=True, help="The GCP Project ID.")
  parser.add_argument(
      "--location", default="us-central1", help="The GCP Location/Region."
  )
  parser.add_argument(
      "--agent-resource-name",
      required=True,
      help="The full resource path of the Reasoning Engine agent.",
  )
  parser.add_argument(
      "--sampling-percentage",
      type=int,
      default=10,
      help=(
          "The percentage of incoming traces to evaluate (1-100). Default"
          " is 10."
      ),
  )

  args = parser.parse_args()
  try:
    create_agent_online_monitor(
        project_id=args.project_id,
        location=args.location,
        agent_resource_name=args.agent_resource_name,
        sampling_percentage=args.sampling_percentage,
    )
  except Exception as e:
    print(f"Error creating online monitor: {e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
