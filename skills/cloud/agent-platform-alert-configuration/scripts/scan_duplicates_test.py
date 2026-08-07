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

"""Unit tests for duplicate detection in scan_duplicates."""

import os
import tempfile
import unittest
import scan_duplicates

class ScanDuplicatesTest(unittest.TestCase):

  def test_validator_detects_duplicates(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      tf_content_1 = """
            resource "google_monitoring_alert_policy" "agent_latency_anomaly_1" {
              display_name = "[Agent Alert] Latency Anomaly - ${var.agent_name}"
              conditions {
                condition_prometheus_query_language {
                  query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m])) by (gen_ai_agent_name)"
                }
              }
            }
            """
      tf_content_2 = """
            resource "google_monitoring_alert_policy" "agent_latency_anomaly_2" {
              display_name = "[Agent Alert] Latency Anomaly - Alternative"
              conditions {
                condition_prometheus_query_language {
                  query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m])) by (gen_ai_agent_name)"
                }
              }
            }
            """
      with open(os.path.join(tmpdir, "policy1.tf"), "w") as f:
        f.write(tf_content_1)
      with open(os.path.join(tmpdir, "policy2.tf"), "w") as f:
        f.write(tf_content_2)

      results = scan_duplicates.validate_directory_tf_files(
          tmpdir, "${var.gen_ai_agent_name}"
      )
      self.assertFalse(results["valid"])
      self.assertEqual(len(results["duplicates_found"]), 1)
      self.assertEqual(results["duplicates_found"][0]["signal_type"], "latency")

  def test_validator_detects_quality_duplicates(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      tf_content_1 = """
            resource "google_monitoring_alert_policy" "q1" {
              display_name = "Quality Alert 1"
              conditions {
                condition_threshold {
                  filter = "resource.type=\\"aiplatform.googleapis.com/OnlineEvaluator\\" AND metric.type=\\"aiplatform.googleapis.com/online_evaluator/scores\\" AND metric.labels.evaluation_metric_name=\\"tool_use_quality_v1\\""
                }
              }
            }
            """
      tf_content_2 = """
            resource "google_monitoring_alert_policy" "q2" {
              display_name = "Quality Alert 2"
              conditions {
                condition_threshold {
                  filter = "resource.type=\\"aiplatform.googleapis.com/OnlineEvaluator\\" AND metric.type=\\"aiplatform.googleapis.com/online_evaluator/scores\\" AND metric.labels.evaluation_metric_name=\\"tool_use_quality_v1\\""
                }
              }
            }
            """
      with open(os.path.join(tmpdir, "policy1.tf"), "w") as f:
        f.write(tf_content_1)
      with open(os.path.join(tmpdir, "policy2.tf"), "w") as f:
        f.write(tf_content_2)

      results = scan_duplicates.validate_directory_tf_files(
          tmpdir, "${var.gen_ai_agent_name}"
      )
      self.assertFalse(results["valid"])
      self.assertEqual(len(results["duplicates_found"]), 1)
      self.assertEqual(
          results["duplicates_found"][0]["signal_type"], "tool_use_quality_v1"
      )


if __name__ == "__main__":
  unittest.main()
