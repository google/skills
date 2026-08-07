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

"""Gathers all necessary information about an agent to build alerts.

Usage: python3 gather_agent_info.py --project-id {PROJECT_ID} --agent-name
{AGENT_NAME}
"""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

try:
  from google.cloud import aiplatform_v1beta1
except ImportError:
  print("Error: google-cloud-aiplatform is not installed.", file=sys.stderr)
  print(
      "Please install it: pip install google-cloud-aiplatform", file=sys.stderr
  )
  sys.exit(1)


DEFAULT_VERTEX_REGIONS = ["us-central1", "us-east1", "us-west1", "europe-west1"]


def run_command(
    cmd: Sequence[str] | str, shell: bool = False
) -> str | None:
  """Runs a command and returns output, or None if error."""
  try:
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, shell=shell
    )
    return result.stdout.strip()
  except subprocess.CalledProcessError as e:
    print(
        "Warning: Command failed:"
        f" {' '.join(cmd) if not isinstance(cmd, str) else cmd}",
        file=sys.stderr,
    )
    print(f"Error output: {e.stderr.strip()}", file=sys.stderr)
    return None
  except FileNotFoundError as e:
    cmd_name = cmd[0] if not isinstance(cmd, str) else cmd.split()[0]
    print(f"Warning: Command not found: {cmd_name}", file=sys.stderr)
    return None


def find_agent_via_cais(
    project_id: str, agent_name: str
) -> dict[str, str] | None:
  """Searches for the agent using Cloud Asset Inventory (CAIS)."""
  print("Attempting fast lookup via Cloud Asset Inventory (CAIS)...")
  cmd = [
      "gcloud",
      "asset",
      "search-all-resources",
      f"--scope=projects/{project_id}",
      (
          "--asset-types=aiplatform.googleapis.com/ReasoningEngine,"
          "run.googleapis.com/Service"
      ),
      f"--query={agent_name}",
      "--format=json",
  ]
  output = run_command(cmd)
  if not output:
    return None

  try:
    assets = json.loads(output)
    for asset in assets:
      if asset.get("displayName") == agent_name:
        location = asset.get("location", "unknown")
        asset_type = asset.get("assetType")

        if asset_type == "aiplatform.googleapis.com/ReasoningEngine":
          print(f"FOUND via CAIS: Reasoning Engine in {location}")
          full_name = asset.get("name", "")
          engine_id = full_name.split("/")[-1] if full_name else agent_name

          return {
              "runtime": "Vertex AI Reasoning Engine",
              "id": engine_id,
              "display_name": agent_name,
              "location": location,
              "resource_name": (
                  full_name.split("//aiplatform.googleapis.com/")[-1]
                  if "//aiplatform.googleapis.com/" in full_name
                  else full_name
              ),
          }
        elif asset_type == "run.googleapis.com/Service":
          print(f"FOUND via CAIS: Cloud Run service in {location}")
          return {
              "runtime": "Cloud Run",
              "id": agent_name,
              "display_name": agent_name,
              "location": location,
              "resource_name": agent_name,
          }
  except json.JSONDecodeError:
    print("Warning: Error parsing CAIS output", file=sys.stderr)

  return None


def find_reasoning_engine(
    project_id: str, agent_name: str, regions: Sequence[str] | None = None
) -> dict[str, str] | None:
  """Searches for a Reasoning Engine by display name in common regions."""
  if not regions:
    regions = DEFAULT_VERTEX_REGIONS
  print(f"Scanning Vertex AI Reasoning Engines in {regions}...")

  for location in regions:
    try:
      client = aiplatform_v1beta1.ReasoningEngineServiceClient(
          client_options={
              "api_endpoint": f"{location}-aiplatform.googleapis.com"
          }
      )
      parent = f"projects/{project_id}/locations/{location}"
      engines = list(client.list_reasoning_engines(parent=parent))

      for engine in engines:
        if engine.display_name == agent_name:
          print(f"FOUND: Reasoning Engine in {location}")
          return {
              "runtime": "Vertex AI Reasoning Engine",
              "id": engine.name.split("/")[-1],
              "display_name": engine.display_name,
              "location": location,
              "resource_name": engine.name,
          }
    except Exception as e:
      # Might be permission error or API not enabled in this region, continue to
      # next
      continue
  return None


def find_cloud_run_service(
    project_id: str, agent_name: str
) -> dict[str, str] | None:
  """Searches for a Cloud Run service by name."""
  print("Checking Cloud Run services...")
  cmd = [
      "gcloud",
      "run",
      "services",
      "list",
      f"--project={project_id}",
      "--format=json",
  ]
  output = run_command(cmd)
  if not output:
    return None

  try:
    services = json.loads(output)
    for svc in services:
      if svc.get("metadata", {}).get("name") == agent_name:
        location = (
            svc.get("metadata", {})
            .get("labels", {})
            .get("cloud.googleapis.com/location", "unknown")
        )
        print(f"FOUND: Cloud Run service in {location}")
        return {
            "runtime": "Cloud Run",
            "id": agent_name,
            "display_name": agent_name,
            "location": location,
            "resource_name": agent_name,
        }
  except json.JSONDecodeError:
    print("Error parsing Cloud Run services output", file=sys.stderr)
  return None


def check_metric_scope(project_id: str) -> str | list[dict[str, Any]]:
  """Checks if the project is part of a multi-project metric scope."""
  print("Checking Metric Scope...")
  cmd = [
      "gcloud",
      "beta",
      "monitoring",
      "metrics-scopes",
      "list",
      f"projects/{project_id}",
      "--format=json",
  ]
  output = run_command(cmd)
  if output:
    try:
      scopes = json.loads(output)
      return scopes
    except json.JSONDecodeError:
      pass
  return "Standard Self-Scoped"


def check_bq_datasets(project_id: str) -> list[dict[str, Any]]:
  """Lists linked BQ datasets."""
  print("Checking BigQuery Datasets...")
  cmd = ["bq", "ls", "--format=prettyjson", f"--project_id={project_id}"]
  output = run_command(cmd)
  if output:
    try:
      datasets = json.loads(output)
      linked = [d for d in datasets if d.get("type") == "LINKED"]
      return linked
    except json.JSONDecodeError:
      pass
  return []


def get_notification_channels(project_id: str) -> list[dict[str, Any]]:
  """Lists notification channels."""
  print("Checking Notification Channels...")
  cmd = [
      "gcloud",
      "beta",
      "monitoring",
      "channels",
      "list",
      f"--project={project_id}",
      "--format=json",
  ]
  output = run_command(cmd)
  if output:
    try:
      return json.loads(output)
    except json.JSONDecodeError:
      pass
  return []


def check_telemetry_status(
    project_id: str, location: str, agent_id: str, skill_path: str
) -> str | None:
  """Runs check_telemetry.py script."""
  local_dir = os.path.dirname(os.path.abspath(__file__))
  check_script = os.path.join(local_dir, "check_telemetry.py")
  if not os.path.exists(check_script):
    check_script = os.path.join(skill_path, "scripts", "check_telemetry.py")

  if os.path.exists(check_script):
    cmd = [
        "python3",
        check_script,
        "--project-id",
        project_id,
        "--location",
        location,
        "--agent-resource-name",
        agent_id,
    ]
    return run_command(cmd)
  print(
      f"Warning: check_telemetry.py not found at {check_script}",
      file=sys.stderr,
  )
  return None


def check_online_evaluators(
    project_id: str, location: str, agent_resource_name: str
) -> list[dict[str, Any]]:
  """Checks if Online Evaluators exist for the agent."""
  try:
    client = aiplatform_v1beta1.OnlineEvaluatorServiceClient(
        client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
    )
    parent = f"projects/{project_id}/locations/{location}"
    request = aiplatform_v1beta1.ListOnlineEvaluatorsRequest(parent=parent)
    page_result = client.list_online_evaluators(request=request)
    matching_evaluators = []
    for evaluator in page_result:
      if evaluator.agent_resource == agent_resource_name:
        evaluator_info = {
            "name": evaluator.name,
            "display_name": evaluator.display_name,
        }
        if hasattr(evaluator, "metrics"):
          evaluator_info["metrics"] = [m.metric for m in evaluator.metrics]
        matching_evaluators.append(evaluator_info)
    return matching_evaluators
  except Exception as e:
    print(f"Warning: Error checking Online Evaluators: {e}", file=sys.stderr)
    return []


def derive_trace_table(project_id: str, skill_path: str) -> str | None:
  """Runs list_trace_scope_table_names.py script."""
  local_dir = os.path.dirname(os.path.abspath(__file__))
  list_trace_script = os.path.join(local_dir, "list_trace_scope_table_names.py")
  if not os.path.exists(list_trace_script):
    list_trace_script = os.path.join(
        skill_path, "scripts", "list_trace_scope_table_names.py"
    )

  if os.path.exists(list_trace_script):
    cmd = ["python3", list_trace_script, "--project_id", project_id]
    return run_command(cmd)
  print(
      "Warning: list_trace_scope_table_names.py not found at"
      f" {list_trace_script}",
      file=sys.stderr,
  )
  return None


def derive_log_table(project_id: str, skill_path: str) -> str | None:
  """Runs list_log_scope_table_names.py script."""
  local_dir = os.path.dirname(os.path.abspath(__file__))
  list_log_script = os.path.join(local_dir, "list_log_scope_table_names.py")
  if not os.path.exists(list_log_script):
    list_log_script = os.path.join(
        skill_path, "scripts", "list_log_scope_table_names.py"
    )

  if os.path.exists(list_log_script):
    cmd = ["python3", list_log_script, "--project_id", project_id]
    return run_command(cmd)
  print(
      f"Warning: list_log_scope_table_names.py not found at {list_log_script}",
      file=sys.stderr,
  )
  return None


def main():
  parser = argparse.ArgumentParser(description="Gather Agent Info for Alerting")
  parser.add_argument("--project-id", required=True, help="GCP Project ID")
  parser.add_argument(
      "--agent-name", required=True, help="Agent Display Name or Service Name"
  )
  default_skill_path = os.path.dirname(
      os.path.dirname(os.path.abspath(__file__))
  )
  parser.add_argument(
      "--skill-path",
      help="Path to agent-platform-alert-configuration skill",
      default=default_skill_path,
  )
  parser.add_argument(
      "--regions",
      help=(
          "Comma-separated list of regions to scan (e.g., us-central1,us-east1)"
      ),
      default=None,
  )
  args = parser.parse_args()

  project_id = args.project_id
  agent_name = args.agent_name
  skill_path = args.skill_path
  regions = args.regions.split(",") if args.regions else None

  print(
      f"=== GATHERING INFO FOR AGENT: {agent_name} IN PROJECT: {project_id} ==="
  )

  # 1. Try to find agent
  agent_info = find_agent_via_cais(project_id, agent_name)

  if not agent_info:
    print(
        "Fast lookup failed or returned no results. Falling back to regional"
        " polling..."
    )
    agent_info = find_reasoning_engine(project_id, agent_name, regions)
    if not agent_info:
      agent_info = find_cloud_run_service(project_id, agent_name)

  if not agent_info:
    print(
        f"\n❌ CRITICAL: Agent '{agent_name}' not found as Reasoning Engine or"
        f" Cloud Run service in project '{project_id}'."
    )
    print("Please verify the name and project.")
    sys.exit(1)

  print("\n=== AGENT IDENTIFICATION ===")
  print(json.dumps(agent_info, indent=2))

  # 2. Check Telemetry and Online Evaluators if Vertex AI
  if agent_info["runtime"] == "Vertex AI Reasoning Engine":
    print("\n=== TELEMETRY STATUS ===")
    output = check_telemetry_status(
        project_id, agent_info["location"], agent_info["id"], skill_path
    )
    if output:
      print(output)

    print("\n=== ONLINE EVALUATORS ===")
    evaluators = check_online_evaluators(
        project_id, agent_info["location"], agent_info["resource_name"]
    )
    print(f"Found {len(evaluators)} Online Evaluators for this agent.")
    if evaluators:
      print(json.dumps(evaluators[:5], indent=2))
      if len(evaluators) > 5:
        print(f"... and {len(evaluators) - 5} more evaluators.")

  # 3. Environment Checks
  print("\n=== ENVIRONMENT CHECKS ===")

  # Metric Scope
  scopes = check_metric_scope(project_id)
  print(
      "Metric Scope Status:"
      f" {scopes if isinstance(scopes, str) else 'Multi-Project'}"
  )
  if isinstance(scopes, list):
    print(json.dumps(scopes[:5], indent=2))
    if len(scopes) > 5:
      print(f"... and {len(scopes) - 5} more scope projects.")

  # BQ Datasets
  linked_datasets = check_bq_datasets(project_id)
  print(f"Linked BigQuery Datasets: {len(linked_datasets)} found")
  if linked_datasets:
    print(json.dumps(linked_datasets[:5], indent=2))
    if len(linked_datasets) > 5:
      print(f"... and {len(linked_datasets) - 5} more datasets.")

  # Trace Table Name
  print("\n=== TRACE TABLE ===")
  output = derive_trace_table(project_id, skill_path)
  if output:
    print(f"Derived Trace Table(s):\n{output}")

  # Log Table Name
  print("\n=== LOG TABLE ===")
  output = derive_log_table(project_id, skill_path)
  if output:
    print(f"Derived Log Table(s):\n{output}")

  # Notification Channels
  channels = get_notification_channels(project_id)
  print("\n=== NOTIFICATION CHANNELS ===")
  print(f"{len(channels)} found")
  if channels:
    # Print a summary of types/names
    summary = [
        {"displayName": c.get("displayName"), "type": c.get("type")}
        for c in channels
    ]
    print(json.dumps(summary[:5], indent=2))
    if len(channels) > 5:
      print(f"... and {len(channels) - 5} more channels.")

  print("\n=== SUMMARY COMPLETE ===")


if __name__ == "__main__":
  main()
