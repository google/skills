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

"""Unit tests for check_telemetry.py."""

import unittest
from unittest import mock

import check_telemetry


class CheckTelemetryTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    self.project_id = "test-project"
    self.location = "us-central1"
    self.agent_id = "123456789"
    self.agent_resource_name = (
        f"projects/{self.project_id}/locations/{self.location}/"
        f"reasoningEngines/{self.agent_id}"
    )

  @mock.patch("check_telemetry.aiplatform_v1beta1.ReasoningEngineServiceClient")
  def test_check_agent_telemetry_enabled(self, mock_client_class):
    mock_client = mock_client_class.return_value
    mock_engine = mock.Mock()

    env_var_1 = mock.Mock()
    env_var_1.name = "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
    env_var_1.value = "true"

    env_var_2 = mock.Mock()
    env_var_2.name = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
    env_var_2.value = "EVENT_ONLY"

    mock_engine.spec.deployment_spec.env = [env_var_1, env_var_2]
    mock_client.get_reasoning_engine.return_value = mock_engine

    result = check_telemetry.check_agent_telemetry(
        project_id=self.project_id,
        location=self.location,
        agent_resource_name=self.agent_id,
    )

    self.assertTrue(result)
    mock_client.get_reasoning_engine.assert_called_once_with(
        name=self.agent_resource_name
    )

  @mock.patch("check_telemetry.aiplatform_v1beta1.ReasoningEngineServiceClient")
  def test_check_agent_telemetry_disabled_missing_telemetry_toggle(
      self, mock_client_class
  ):
    mock_client = mock_client_class.return_value
    mock_engine = mock.Mock()

    env_var_1 = mock.Mock()
    env_var_1.name = "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
    env_var_1.value = "false"

    env_var_2 = mock.Mock()
    env_var_2.name = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
    env_var_2.value = "EVENT_ONLY"

    mock_engine.spec.deployment_spec.env = [env_var_1, env_var_2]
    mock_client.get_reasoning_engine.return_value = mock_engine

    result = check_telemetry.check_agent_telemetry(
        project_id=self.project_id,
        location=self.location,
        agent_resource_name=self.agent_id,
    )

    self.assertFalse(result)

  @mock.patch("check_telemetry.aiplatform_v1beta1.ReasoningEngineServiceClient")
  def test_check_agent_telemetry_disabled_missing_capture_toggle(
      self, mock_client_class
  ):
    mock_client = mock_client_class.return_value
    mock_engine = mock.Mock()

    env_var_1 = mock.Mock()
    env_var_1.name = "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
    env_var_1.value = "true"

    mock_engine.spec.deployment_spec.env = [env_var_1]
    mock_client.get_reasoning_engine.return_value = mock_engine

    result = check_telemetry.check_agent_telemetry(
        project_id=self.project_id,
        location=self.location,
        agent_resource_name=self.agent_id,
    )

    self.assertFalse(result)

  @mock.patch("check_telemetry.monitoring_v3")
  def test_check_token_usage_monitoring_namespaces_success(
      self, mock_monitoring_v3
  ):
    # Setup mock client and mock time series returns
    mock_client = mock.MagicMock()
    mock_monitoring_v3.MetricServiceClient.return_value = mock_client
    mock_monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.HEADERS = 1

    ts1 = mock.MagicMock()
    ts1.resource.labels = {"namespace": "staging_agent", "node_id": "node-2"}
    mock_client.list_time_series.return_value = [ts1]
    namespaces = check_telemetry.check_token_usage_monitoring_namespaces(
        self.project_id, days_lookback=3
    )
    # Verify return set contains expected unique namespaces
    self.assertEqual(namespaces, {"staging_agent"})

    # Verify exact API request structure passed to list_time_series
    self.assertTrue(mock_client.list_time_series.called)
    call_kwargs = mock_client.list_time_series.call_args[1]["request"]
    self.assertEqual(call_kwargs["name"], f"projects/{self.project_id}")
    self.assertEqual(
        call_kwargs["filter"],
        'metric.type="workload.googleapis.com/gen_ai.client.token.usage"',
    )
    self.assertEqual(call_kwargs["view"], 1)

  @mock.patch("check_telemetry.monitoring_v3")
  def test_check_token_usage_monitoring_namespaces_missing_namespace_label(
      self, mock_monitoring_v3
  ):
    mock_client = mock.MagicMock()
    mock_monitoring_v3.MetricServiceClient.return_value = mock_client
    ts_no_label = mock.MagicMock()
    ts_no_label.resource.labels = {"location": "us-central1"}
    mock_client.list_time_series.return_value = [ts_no_label]
    namespaces = check_telemetry.check_token_usage_monitoring_namespaces(
        self.project_id
    )
    self.assertIn("(namespace label not found in this resource)", namespaces)


if __name__ == "__main__":
  unittest.main()
