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

"""Unit tests for metrics data time-series parsing.

Also tests decision tree traffic profiling decisions.
"""

import datetime
import json
import os
import sys


import time
import unittest
from unittest import mock

import analyze_traffic  # pytype: disable=import-error


class AnalyzeTrafficTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    self.mock_data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_internal"
    )
    if not os.path.exists(self.mock_data_dir):
      raise FileNotFoundError(
          f"Could not find mock data directory: {self.mock_data_dir}"
      )

  def _load_mock_data(self, filename):
    filepath = os.path.join(self.mock_data_dir, filename)
    with open(filepath, "r") as f:
      return json.load(f)

  def test_classify_seasonal(self):
    data = self._load_mock_data("mock_seasonal.json")
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Seasonal / Cyclical")
    self.assertEqual(
        results["recommended_algorithm"],
        "Seasonal Decomposition (average 1w and 1d)",
    )

  def test_classify_steady(self):
    data = self._load_mock_data("mock_steady.json")
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Steady / Consistent")
    self.assertEqual(results["recommended_algorithm"], "1w Z-Score Baseline")

  def test_classify_bursty(self):
    data = self._load_mock_data("mock_bursty.json")
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Bursty / Inconsistent")
    self.assertEqual(results["recommended_algorithm"], "Moving Averages")

  def test_classify_new_agent(self):
    data = [0.0] * 4032
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "New Agent / No Traffic")
    self.assertEqual(
        results["recommended_algorithm"], "Short-Window Z-Score (1h baseline)"
    )
    self.assertIn("No historical traffic observed", results["rationale"])

  def test_insufficient_data(self):
    with self.assertRaises(ValueError):
      analyze_traffic.compute_metrics_and_classify([1.0] * 100)

  def test_classify_constant_traffic(self):
    # Constant 10.0 traffic should be classified as Steady/Consistent
    data = [10.0] * 4032
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Steady / Consistent")
    self.assertEqual(results["recommended_algorithm"], "1w Z-Score Baseline")

  def test_classify_very_low_constant_traffic(self):
    # Constant 0.005 traffic (below 0.01 zero threshold) should still be Steady/Consistent
    # due to mean_last being non-zero (0.005 != 0.0)
    data = [0.005] * 4032
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Steady / Consistent")
    self.assertEqual(results["recommended_algorithm"], "1w Z-Score Baseline")

  def test_classify_near_zero_spike_falls_to_steady(self):
    # 4031 zeros and a single 0.05 value. mean_last is 0.05/2016 = 0.0000248 <= 0.0001,
    # so variance_ratio is forced to 0.0, and it falls back to Steady/Consistent.
    data = [0.0] * 4031 + [0.05]
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Steady / Consistent")
    self.assertEqual(results["recommended_algorithm"], "1w Z-Score Baseline")

  def test_classify_single_spike_bursty(self):
    # 4031 zeros and a single 0.5 value. mean_last is 0.5/2016 = 0.000248 > 0.0001,
    # so variance_ratio is computed (~44.88 > 2.0) and it classifies as Bursty/Inconsistent.
    data = [0.0] * 4031 + [0.5]
    results = analyze_traffic.compute_metrics_and_classify(data)
    self.assertEqual(results["profile"], "Bursty / Inconsistent")
    self.assertEqual(results["recommended_algorithm"], "Moving Averages")

  @mock.patch("sys.exit")
  @mock.patch("builtins.print")
  @mock.patch("google.cloud.monitoring_v3.MetricServiceClient")
  def test_main_live_query_request_count(
      self, mock_client_cls, mock_print, mock_exit
  ):
    # Ensure google.cloud.monitoring_v3 module import doesn't fail
    mock_client = mock_client_cls.return_value

    class MockTimestamp:

      def __init__(self, seconds):
        self.seconds = seconds

      def timestamp(self):
        return self.seconds

    class MockPoint:

      def __init__(self, seconds, val):
        self.interval = mock.MagicMock()
        self.interval.start_time = MockTimestamp(seconds)
        self.value = mock.MagicMock()
        self.value.double_value = val

    class MockSeries:

      def __init__(self, points):
        self.points = points

    now = time.time()
    start_ts = now - 14 * 24 * 3600
    mock_points = [
        MockPoint(start_ts + (i + 1) * 300, 10.0) for i in range(4032)
    ]
    mock_client.list_time_series.return_value = [MockSeries(mock_points)]

    test_argv = [
        "analyze_traffic.py",
        "--live",
        "--project-id",
        "my-project",
        "--reasoning-engine-id",
        "123",
        "--metric-type",
        "workload.googleapis.com/gen_ai.invoke_agent.duration",
    ]
    with mock.patch.object(sys, "argv", test_argv):
      analyze_traffic.main()

    mock_print.assert_called()
    printed_str = mock_print.call_args[0][0]
    results = json.loads(printed_str)
    self.assertEqual(results["profile"], "Steady / Consistent")
    self.assertEqual(results["recommended_algorithm"], "1w Z-Score Baseline")

  @mock.patch("sys.exit")
  @mock.patch("builtins.print")
  @mock.patch("google.cloud.monitoring_v3.MetricServiceClient")
  def test_main_live_query_token_usage(
      self, mock_client_cls, mock_print, mock_exit
  ):
    # Ensure google.cloud.monitoring_v3 module import doesn't fail
    mock_client = mock_client_cls.return_value

    class MockTimestamp:

      def __init__(self, seconds):
        self.seconds = seconds

      def timestamp(self):
        return self.seconds

    class MockPoint:

      def __init__(self, seconds, val):
        self.interval = mock.MagicMock()
        self.interval.start_time = MockTimestamp(seconds)
        self.value = mock.MagicMock()
        self.value.double_value = val

    class MockSeries:

      def __init__(self, points):
        self.points = points

    now = time.time()
    start_ts = now - 14 * 24 * 3600
    # Simulate high peaks and low baseline to force the Bursty profile.
    mock_points = [
        MockPoint(start_ts + (i + 1) * 300, 1000.0 if i % 50 == 0 else 1.0)
        for i in range(4032)
    ]
    mock_client.list_time_series.return_value = [MockSeries(mock_points)]

    test_argv = [
        "analyze_traffic.py",
        "--live",
        "--project-id",
        "my-project",
        "--reasoning-engine-id",
        "test-engine",
        "--metric-type",
        "workload.googleapis.com/gen_ai.client.token.usage",
    ]
    with mock.patch.object(sys, "argv", test_argv):
      analyze_traffic.main()

    mock_print.assert_called()
    printed_str = mock_print.call_args[0][0]
    results = json.loads(printed_str)
    self.assertEqual(results["profile"], "Bursty / Inconsistent")
    self.assertEqual(results["recommended_algorithm"], "Moving Averages")

  def test_align_to_grid(self):
    points = [
        (0.0, 1.0),
        (10.0, 1.5),
        (600.0, 2.0),
        (2700.0, 3.0),
        (3000.0, 4.0),
    ]
    grid = analyze_traffic.align_to_grid(points, 3000.0, num_points=10)
    self.assertEqual(grid, [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0, 4.0])


if __name__ == "__main__":
  unittest.main()
