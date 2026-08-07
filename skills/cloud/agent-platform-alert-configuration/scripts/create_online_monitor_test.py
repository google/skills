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

"""Unit tests for Vertex AI Reasoning Engine Online Monitor creation."""

import sys
import unittest
from unittest import mock

import create_online_monitor


class CreateOnlineMonitorTest(unittest.TestCase):

  @mock.patch(
      "create_online_monitor.aiplatform_v1beta1.OnlineEvaluatorServiceClient"
  )
  def test_create_agent_online_monitor_already_exists_noop(
      self, mock_client_class
  ):
    mock_client = mock_client_class.return_value

    mock_evaluator = mock.Mock()
    mock_evaluator.name = (
        "projects/my-project/locations/us-central-test/onlineEvaluators/999"
    )
    mock_evaluator.agent_resource = (
        "projects/my-project/locations/us-central-test/reasoningEngines/123"
    )

    mock_metric_sources = []
    for metric_name in [
        "hallucination_v1",
        "final_response_quality_v1",
        "tool_use_quality_v1",
    ]:
      m = mock.Mock()
      m.metric.predefined_metric_spec.metric_spec_name = metric_name
      mock_metric_sources.append(m)
    mock_evaluator.metric_sources = mock_metric_sources
    mock_evaluator.config.random_sampling.percentage = 15

    mock_client.list_online_evaluators.return_value = [mock_evaluator]

    evaluator_name = create_online_monitor.create_agent_online_monitor(
        project_id="my-project",
        location="us-central-test",
        agent_resource_name=(
            "projects/my-project/locations/us-central-test/reasoningEngines/123"
        ),
        sampling_percentage=15,
    )

    self.assertEqual(evaluator_name, mock_evaluator.name)
    mock_client.create_online_evaluator.assert_not_called()

  @mock.patch(
      "create_online_monitor.aiplatform_v1beta1.OnlineEvaluatorServiceClient"
  )
  def test_create_agent_online_monitor_not_exists_creates_new(
      self, mock_client_class
  ):
    mock_client = mock_client_class.return_value
    mock_client.list_online_evaluators.return_value = []

    mock_operation = mock.Mock()
    mock_client.create_online_evaluator.return_value = mock_operation

    mock_response = mock.Mock()
    mock_response.name = (
        "projects/my-project/locations/us-central-test/onlineEvaluators/999"
    )
    mock_operation.result.return_value = mock_response

    evaluator_name = create_online_monitor.create_agent_online_monitor(
        project_id="my-project",
        location="us-central-test",
        agent_resource_name=(
            "projects/my-project/locations/us-central-test/reasoningEngines/123"
        ),
        sampling_percentage=15,
    )

    # Verify Endpoint and Instantiation
    mock_client_class.assert_called_once_with(
        client_options={
            "api_endpoint": "us-central-test-aiplatform.googleapis.com"
        }
    )

    # Verify API Call
    mock_client.create_online_evaluator.assert_called_once()
    call_args = mock_client.create_online_evaluator.call_args[1]
    request = call_args["request"]

    self.assertEqual(
        request.parent, "projects/my-project/locations/us-central-test"
    )
    self.assertEqual(
        request.online_evaluator.display_name, "agent-quality-monitor"
    )
    self.assertEqual(
        request.online_evaluator.agent_resource,
        "projects/my-project/locations/us-central-test/reasoningEngines/123",
    )
    self.assertEqual(
        request.online_evaluator.config.random_sampling.percentage, 15
    )

    # Verify Metric Names are set
    metrics = [
        m.metric.predefined_metric_spec.metric_spec_name
        for m in request.online_evaluator.metric_sources
    ]
    self.assertIn("hallucination_v1", metrics)
    self.assertIn("final_response_quality_v1", metrics)
    self.assertIn("tool_use_quality_v1", metrics)

    self.assertEqual(evaluator_name, mock_response.name)

  @mock.patch(
      "create_online_monitor.aiplatform_v1beta1.OnlineEvaluatorServiceClient"
  )
  def test_create_agent_online_monitor_failure(self, mock_client_class):
    mock_client = mock_client_class.return_value
    mock_client.list_online_evaluators.return_value = []
    mock_client.create_online_evaluator.side_effect = Exception("API error")

    with self.assertRaises(Exception) as context:
      create_online_monitor.create_agent_online_monitor(
          project_id="my-project",
          location="us-central-test",
          agent_resource_name=(
              "projects/my-project/locations/us-central-test/"
              "reasoningEngines/123"
          ),
      )
    self.assertIn("API error", str(context.exception))

  @mock.patch("create_online_monitor.create_agent_online_monitor")
  def test_main_cli_parsing(self, mock_create):
    test_args = [
        "create_online_monitor.py",
        "--project-id",
        "cli-proj",
        "--agent-resource-name",
        "cli-agent",
        "--sampling-percentage",
        "30",
        "--location",
        "us-east4",
    ]
    with mock.patch.object(sys, "argv", test_args):
      create_online_monitor.main()

    mock_create.assert_called_once_with(
        project_id="cli-proj",
        location="us-east4",
        agent_resource_name="cli-agent",
        sampling_percentage=30,
    )


if __name__ == "__main__":
  unittest.main()
