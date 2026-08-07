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
"""Unit tests for gather_agent_info.py."""

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

# Mock the import of aiplatform_v1beta1 in case it's not installed in the test
# environment. This allows the module to be executed/parsed without failing on
# import
try:
  import google.cloud.aiplatform_v1beta1
except ImportError:
  mock_aiplatform = mock.MagicMock()
  sys.modules["google.cloud.aiplatform_v1beta1"] = mock_aiplatform
  sys.modules["google.cloud"] = mock.MagicMock()

import gather_agent_info


class GatherAgentInfoTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    self.project_id = "test-project"
    self.agent_name = "test-agent"

  @mock.patch("gather_agent_info.subprocess.run")
  def test_run_command_success(self, mock_run):
    mock_result = mock.Mock()
    mock_result.stdout = "success_output\n"
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    result = gather_agent_info.run_command(["echo", "hello"])
    self.assertEqual(result, "success_output")
    mock_run.assert_called_once()

  @mock.patch("gather_agent_info.subprocess.run")
  def test_run_command_failure(self, mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd="fail", stderr="error_output\n"
    )

    result = gather_agent_info.run_command(["fail_cmd"])
    self.assertIsNone(result)

  @mock.patch(
      "gather_agent_info.aiplatform_v1beta1.ReasoningEngineServiceClient"
  )
  def test_find_reasoning_engine_found(self, mock_client_class):
    mock_client = mock_client_class.return_value
    mock_engine = mock.Mock()
    mock_engine.display_name = self.agent_name
    mock_engine.name = (
        f"projects/{self.project_id}/locations/us-central1/reasoningEngines/"
        "12345"
    )
    mock_client.list_reasoning_engines.return_value = [mock_engine]

    result = gather_agent_info.find_reasoning_engine(
        self.project_id, self.agent_name
    )

    self.assertIsNotNone(result)
    self.assertEqual(result["runtime"], "Vertex AI Reasoning Engine")
    self.assertEqual(result["id"], "12345")
    self.assertEqual(result["display_name"], self.agent_name)
    self.assertEqual(result["location"], "us-central1")

  @mock.patch(
      "gather_agent_info.aiplatform_v1beta1.ReasoningEngineServiceClient"
  )
  def test_find_reasoning_engine_not_found(self, mock_client_class):
    mock_client = mock_client_class.return_value
    mock_engine = mock.Mock()
    mock_engine.display_name = "other-agent"
    mock_client.list_reasoning_engines.return_value = [mock_engine]

    result = gather_agent_info.find_reasoning_engine(
        self.project_id, self.agent_name
    )

    self.assertIsNone(result)

  @mock.patch(
      "gather_agent_info.aiplatform_v1beta1.ReasoningEngineServiceClient"
  )
  def test_find_reasoning_engine_custom_regions(self, mock_client_class):
    mock_client = mock_client_class.return_value
    mock_engine = mock.Mock()
    mock_engine.display_name = self.agent_name
    mock_engine.name = (
        f"projects/{self.project_id}/locations/us-east4/reasoningEngines/12345"
    )
    mock_client.list_reasoning_engines.return_value = [mock_engine]

    custom_regions = ["us-east4", "us-west2"]
    result = gather_agent_info.find_reasoning_engine(
        self.project_id, self.agent_name, custom_regions
    )

    self.assertIsNotNone(result)
    self.assertEqual(result["location"], "us-east4")
    mock_client_class.assert_any_call(
        client_options={"api_endpoint": "us-east4-aiplatform.googleapis.com"}
    )

  @mock.patch("gather_agent_info.run_command")
  def test_find_cloud_run_service_found(self, mock_run_command):
    mock_services = [
        {
            "metadata": {
                "name": "other-agent",
                "labels": {"cloud.googleapis.com/location": "us-east1"},
            }
        },
        {
            "metadata": {
                "name": self.agent_name,
                "labels": {"cloud.googleapis.com/location": "us-central1"},
            }
        },
    ]
    mock_run_command.return_value = json.dumps(mock_services)

    result = gather_agent_info.find_cloud_run_service(
        self.project_id, self.agent_name
    )

    self.assertIsNotNone(result)
    self.assertEqual(result["runtime"], "Cloud Run")
    self.assertEqual(result["id"], self.agent_name)
    self.assertEqual(result["location"], "us-central1")

  @mock.patch("gather_agent_info.run_command")
  def test_find_cloud_run_service_not_found(self, mock_run_command):
    mock_services = [{"metadata": {"name": "other-agent"}}]
    mock_run_command.return_value = json.dumps(mock_services)

    result = gather_agent_info.find_cloud_run_service(
        self.project_id, self.agent_name
    )

    self.assertIsNone(result)

  @mock.patch("gather_agent_info.run_command")
  def test_check_metric_scope(self, mock_run_command):
    mock_scopes = [{"name": "locations/global/metricsScopes/12345"}]
    mock_run_command.return_value = json.dumps(mock_scopes)

    result = gather_agent_info.check_metric_scope(self.project_id)
    self.assertEqual(result, mock_scopes)

  @mock.patch("gather_agent_info.run_command")
  def test_check_bq_datasets(self, mock_run_command):
    mock_datasets = [
        {"datasetReference": {"datasetId": "a"}, "type": "DEFAULT"},
        {"datasetReference": {"datasetId": "b"}, "type": "LINKED"},
    ]
    mock_run_command.return_value = json.dumps(mock_datasets)

    result = gather_agent_info.check_bq_datasets(self.project_id)
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0]["type"], "LINKED")

  @mock.patch("gather_agent_info.run_command")
  def test_get_notification_channels(self, mock_run_command):
    mock_channels = [{"displayName": "Email", "type": "email"}]
    mock_run_command.return_value = json.dumps(mock_channels)

    result = gather_agent_info.get_notification_channels(self.project_id)
    self.assertEqual(result, mock_channels)

  @mock.patch("gather_agent_info.run_command")
  @mock.patch("gather_agent_info.os.path.exists")
  def test_check_telemetry_status(self, mock_exists, mock_run_command):
    mock_exists.return_value = True
    mock_run_command.return_value = "telemetry_ok"
    result = gather_agent_info.check_telemetry_status(
        self.project_id, "us-central1", "12345", "/tmp"
    )
    self.assertEqual(result, "telemetry_ok")
    mock_run_command.assert_called_once()

  @mock.patch(
      "gather_agent_info.aiplatform_v1beta1.OnlineEvaluatorServiceClient"
  )
  def test_check_online_evaluators(self, mock_client_class):
    mock_client = mock_client_class.return_value
    mock_evaluator = mock.Mock()
    mock_evaluator.name = "eval-1"
    mock_evaluator.display_name = "Eval 1"
    mock_evaluator.agent_resource = (
        f"projects/{self.project_id}/locations/us-central1/reasoningEngines/"
        "12345"
    )
    mock_metric = mock.Mock()
    mock_metric.metric = "quality"
    mock_evaluator.metrics = [mock_metric]
    mock_client.list_online_evaluators.return_value = [mock_evaluator]

    result = gather_agent_info.check_online_evaluators(
        self.project_id, "us-central1", mock_evaluator.agent_resource
    )
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0]["name"], "eval-1")
    self.assertEqual(result[0]["metrics"], ["quality"])

  @mock.patch("gather_agent_info.run_command")
  @mock.patch("gather_agent_info.os.path.exists")
  def test_derive_trace_table(self, mock_exists, mock_run_command):
    mock_exists.return_value = True
    mock_run_command.return_value = "trace_table_name"
    result = gather_agent_info.derive_trace_table(self.project_id, "/tmp")
    self.assertEqual(result, "trace_table_name")

  @mock.patch("gather_agent_info.run_command")
  @mock.patch("gather_agent_info.os.path.exists")
  def test_derive_log_table(self, mock_exists, mock_run_command):
    mock_exists.return_value = True
    mock_run_command.return_value = "log_table_name"
    result = gather_agent_info.derive_log_table(self.project_id, "/tmp")
    self.assertEqual(result, "log_table_name")

  @mock.patch("gather_agent_info.run_command")
  def test_find_agent_via_cais_reasoning_engine(self, mock_run_command):
    mock_assets = [{
        "assetType": "aiplatform.googleapis.com/ReasoningEngine",
        "displayName": self.agent_name,
        "location": "us-central1",
        "name": (
            "//aiplatform.googleapis.com/projects/755054710983/locations/"
            "us-central1/reasoningEngines/12345"
        ),
    }]
    mock_run_command.return_value = json.dumps(mock_assets)

    result = gather_agent_info.find_agent_via_cais(
        self.project_id, self.agent_name
    )

    self.assertIsNotNone(result)
    self.assertEqual(result["runtime"], "Vertex AI Reasoning Engine")
    self.assertEqual(result["id"], "12345")
    self.assertEqual(result["location"], "us-central1")
    self.assertEqual(
        result["resource_name"],
        "projects/755054710983/locations/us-central1/reasoningEngines/12345",
    )

  @mock.patch("gather_agent_info.run_command")
  def test_find_agent_via_cais_cloud_run(self, mock_run_command):
    mock_assets = [{
        "assetType": "run.googleapis.com/Service",
        "displayName": self.agent_name,
        "location": "us-central1",
        "name": (
            "//run.googleapis.com/projects/755054710983/locations/"
            "us-central1/services/test-agent"
        ),
    }]
    mock_run_command.return_value = json.dumps(mock_assets)

    result = gather_agent_info.find_agent_via_cais(
        self.project_id, self.agent_name
    )

    self.assertIsNotNone(result)
    self.assertEqual(result["runtime"], "Cloud Run")
    self.assertEqual(result["id"], self.agent_name)
    self.assertEqual(result["location"], "us-central1")

  @mock.patch("gather_agent_info.run_command")
  def test_find_agent_via_cais_not_found(self, mock_run_command):
    mock_assets = [{
        "assetType": "aiplatform.googleapis.com/ReasoningEngine",
        "displayName": "other-agent",
        "location": "us-central1",
        "name": (
            "//aiplatform.googleapis.com/projects/755054710983/locations/"
            "us-central1/reasoningEngines/other"
        ),
    }]
    mock_run_command.return_value = json.dumps(mock_assets)

    result = gather_agent_info.find_agent_via_cais(
        self.project_id, self.agent_name
    )

    self.assertIsNone(result)


if __name__ == "__main__":
  unittest.main()
