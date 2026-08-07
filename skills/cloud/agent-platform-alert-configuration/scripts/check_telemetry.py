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

"""Helper script to check telemetry status on a Vertex AI Reasoning Engine."""

import argparse
import datetime
import sys

from google.cloud import monitoring_v3

try:
  from google.cloud import aiplatform_v1beta1  # pytype: disable=import-error
except ImportError:
  from google.cloud.aiplatform import aiplatform_v1beta1  # pytype: disable=import-error


def check_agent_telemetry(
    project_id: str, location: str, agent_resource_name: str
) -> bool:
  """Verifies if telemetry is correctly enabled on the reasoning engine."""
  client = aiplatform_v1beta1.ReasoningEngineServiceClient(
      client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
  )

  # Check if agent_resource_name is already a full path or needs formatting
  if not agent_resource_name.startswith("projects/"):
    name = (
        f"projects/{project_id}/locations/{location}/"
        f"reasoningEngines/{agent_resource_name}"
    )
  else:
    name = agent_resource_name

  engine = client.get_reasoning_engine(name=name)

  env_vars = {}
  for env_var in engine.spec.deployment_spec.env:
    env_vars[env_var.name] = env_var.value.strip()

  has_telemetry_toggle = (
      env_vars.get("GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", "").lower()
      == "true"
  )
  has_capture_toggle = bool(
      env_vars.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "")
  )
  is_enabled = has_telemetry_toggle and has_capture_toggle

  print(
      f"Agent {engine.display_name} Telemetry Status:"
      f" {'ENABLED' if is_enabled else 'DISABLED'}"
  )
  if not is_enabled:
    val_telemetry = env_vars.get(
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", "MISSING"
    )
    val_capture = env_vars.get(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "MISSING"
    )
    print(
        "Missing/Incorrect variables: "
        f"ENABLE_TELEMETRY={val_telemetry}, "
        f"CAPTURE_MESSAGE_CONTENT={val_capture}"
    )
  return is_enabled


def check_token_usage_monitoring_namespaces(
    project_id: str, days_lookback: int = 1
) -> set[str]:
  """Queries Cloud Monitoring for distinct namespaces.

  Specifically, look for the workload.googleapis.com/gen_ai.client.token.usage
  metric.
  """
  client = monitoring_v3.MetricServiceClient()
  now = datetime.datetime.now(datetime.timezone.utc)
  start_time = now - datetime.timedelta(days=days_lookback)
  interval = monitoring_v3.TimeInterval({
      "end_time": {"seconds": int(now.timestamp())},
      "start_time": {"seconds": int(start_time.timestamp())},
  })
  filter_str = 'metric.type="workload.googleapis.com/gen_ai.client.token.usage"'
  print(f"Filter: {filter_str}")
  namespaces = set()
  try:
    results = client.list_time_series(
        request={
            "name": f"projects/{project_id}",
            "filter": filter_str,
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.HEADERS,
        }
    )
    count = 0
    for ts in results:
      count += 1
      res_labels = ts.resource.labels
      ns = res_labels.get(
          "namespace", "(namespace label not found in this resource)"
      )
      namespaces.add(ns)
    print(f"\nFound {count} matching time series descriptors.")
    return namespaces
  except Exception as e:
    print(f"Error querying Cloud Monitoring metadata: {e}", file=sys.stderr)
    sys.exit(1)


def main():
  parser = argparse.ArgumentParser(
      description=(
          "Check if telemetry is enabled on a Vertex AI Reasoning Engine."
      )
  )
  parser.add_argument("--project-id", required=True, help="The GCP Project ID.")
  parser.add_argument(
      "--location", default="us-central1", help="The GCP Location/Region."
  )
  parser.add_argument(
      "--agent-resource-name",
      required=True,
      help="The agent ID or full resource path of the Reasoning Engine.",
  )
  parser.add_argument(
      "--query-monitoring-metadata",
      action=argparse.BooleanOptionalAction,
      default=True,
      help=(
          "If set, it will also query Cloud Monitoring for related metric"
          " metadata."
      ),
  )

  args = parser.parse_args()
  print(
      f"--- [1] Checking agent {args.agent_resource_name} telemetry status ---"
  )
  try:
    telemetry_ok = check_agent_telemetry(
        project_id=args.project_id,
        location=args.location,
        agent_resource_name=args.agent_resource_name,
    )
    if not telemetry_ok:
      sys.exit(1)
  except Exception as e:
    print(f"Error checking telemetry status: {e}", file=sys.stderr)
    sys.exit(1)

  if args.query_monitoring_metadata:
    print("--- [2] Querying Cloud Monitoring metadata ---")
    try:
      namespaces = check_token_usage_monitoring_namespaces(args.project_id)
      if namespaces:
        print("Distinct namespaces identified in Cloud Monitoring:")
        for ns in sorted(namespaces):
          print(f"==> {ns}")
      else:
        print(
            "No time series found matching the metric filter in the chosen time"
            " window."
        )
    except Exception as e:
      print(f"Error querying Cloud Monitoring metadata: {e}", file=sys.stderr)
      sys.exit(1)


if __name__ == "__main__":
  main()
