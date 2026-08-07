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

import unittest
import config_utils

class ConfigUtilsTest(unittest.TestCase):

  def test_lint_query_valid(self):
    query = (
        "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]))"
        " by (gen_ai_agent_name)"
    )
    self.assertEqual(config_utils.lint_query(query), [])

  def test_lint_query_unbalanced_parentheses(self):
    query = (
        "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]))"
        " by (gen_ai_agent_name"
    )
    errors = config_utils.lint_query(query)
    self.assertTrue(any("Parentheses error" in e for e in errors))

  def test_lint_query_unbalanced_braces(self):
    query = (
        'sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{error_type!=""[5m]))'
        " by (gen_ai_agent_name)"
    )
    errors = config_utils.lint_query(query)
    self.assertTrue(any("Curly braces error" in e for e in errors))

  def test_lint_query_invalid_window(self):
    for invalid_suffix in ("5x", "5y"):
      query = (
          "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count"
          f"[{invalid_suffix}])) by (gen_ai_agent_name)"
      )
      errors = config_utils.lint_query(query)
      self.assertTrue(
          any("Invalid Prometheus time window" in e for e in errors)
      )

  def test_lint_query_valid_subquery_intervals(self):
    queries = [
        # With resolution
        (
            "avg_over_time((sum(rate("
            "workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]"
            ")) by (gen_ai_agent_name))[1w:5m])"
        ),
        # Without resolution
        (
            "avg_over_time((sum(rate("
            "workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]"
            ")) by (gen_ai_agent_name))[1w:])"
        ),
    ]
    for query in queries:
      self.assertEqual(config_utils.lint_query(query), [])

  def test_lint_query_invalid_subquery_intervals(self):
    queries = [
        # Invalid resolution format: number only (no unit)
        (
            "avg_over_time((sum(rate("
            "workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]"
            ")) by (gen_ai_agent_name))[1w:5])"
        ),
        # Invalid resolution format: unit only (no number)
        (
            "avg_over_time((sum(rate("
            "workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]"
            ")) by (gen_ai_agent_name))[1w:m])"
        ),
    ]
    for query in queries:
      errors = config_utils.lint_query(query)
      self.assertTrue(
          any("Invalid Prometheus time window" in e for e in errors)
      )

  def test_lint_query_missing_reference(self):
    query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]))"
    errors = config_utils.lint_query(query)
    self.assertTrue(
        any("missing agent identifier reference" in e for e in errors)
    )

  def test_lint_query_valid_with_filter(self):
    query = (
        'sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count'
        '{gen_ai_agent_name="my-agent"}[5m]))'
    )
    self.assertEqual(config_utils.lint_query(query), [])

  def test_lint_query_valid_with_regex_or_prefix_filter(self):
    query = (
        'sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count'
        '{gen_ai_agent_name!~"dev-.*"}[5m]))'
        " by (gen_ai_agent_name)"
    )
    self.assertEqual(config_utils.lint_query(query), [])

  def test_scanner_extract_valid_hcl(self):
    hcl_content = """
        resource "google_monitoring_alert_policy" "agent_latency_anomaly" {
          project      = var.project_id
          display_name = "[Agent Alert] Latency Anomaly - ${var.agent_name}"
          combiner     = "OR"

          conditions {
            display_name = "p95 Latency exceeds 3x Standard Deviation (1w baseline)"
            condition_prometheus_query_language {
              query    = <<-EOT
                sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m])) by (gen_ai_agent_name)
              EOT
              duration = "300s"
            }
          }
        }
        """
    policies = config_utils.extract_alert_policies(hcl_content)
    self.assertEqual(len(policies), 1)
    self.assertEqual(policies[0]["resource_name"], "agent_latency_anomaly")
    self.assertEqual(policies[0]["signal_type"], "latency")

  def test_scanner_extract_escaped_inline_query(self):
    hcl_content = r"""
        resource "google_monitoring_alert_policy" "agent_latency_anomaly" {
          display_name = "[Agent Alert] Latency Anomaly - ${var.agent_name}"
          conditions {
            condition_prometheus_query_language {
              query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{gen_ai_agent_name=\"12345\"}[5m]))"
            }
          }
        }
        """
    policies = config_utils.extract_alert_policies(hcl_content)
    self.assertEqual(len(policies), 1)
    self.assertEqual(len(policies[0]["queries"]), 1)
    self.assertEqual(
        policies[0]["queries"][0],
        'sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{gen_ai_agent_name="12345"}[5m]))',
    )
    self.assertEqual(policies[0]["engine_ids"], ["12345"])

    hcl_content_three_backslash = r"""
        resource "google_monitoring_alert_policy" "agent_latency_anomaly" {
          display_name = "[Agent Alert] Latency Anomaly - ${var.agent_name}"
          conditions {
            condition_prometheus_query_language {
              query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{gen_ai_agent_name=\\\"12345\\\"}[5m]))"
            }
          }
        }
        """
    policies_three = config_utils.extract_alert_policies(
        hcl_content_three_backslash
    )
    self.assertEqual(len(policies_three), 1)
    self.assertEqual(len(policies_three[0]["queries"]), 1)
    self.assertEqual(
        policies_three[0]["queries"][0],
        'sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count{gen_ai_agent_name="12345"}[5m]))',
    )
    self.assertEqual(policies_three[0]["engine_ids"], ["12345"])

  def test_scanner_extracts_quality_metric_signal_type(self):
    hcl_content = """
        resource "google_monitoring_alert_policy" "agent_final_response_quality" {
          project      = var.project_id
          display_name = "Agent Final Response Quality (Median < 0.8)"
          combiner     = "OR"
          enabled      = true

          conditions {
            display_name = "Final Response Quality Score"
            condition_threshold {
              filter          = "resource.type=\\"aiplatform.googleapis.com/OnlineEvaluator\\" AND metric.type=\\"aiplatform.googleapis.com/online_evaluator/scores\\" AND metric.labels.evaluation_metric_name=\\"final_response_quality_v1\\""
              comparison      = "COMPARISON_LT"
              threshold_value = 0.8
              duration        = "300s"
              aggregations {
                alignment_period   = "300s"
                per_series_aligner = "ALIGN_PERCENTILE_50"
              }
              trigger {
                count = 1
              }
            }
          }
        }
        """
    policies = config_utils.extract_alert_policies(hcl_content)
    self.assertEqual(len(policies), 1)
    self.assertEqual(
        policies[0]["resource_name"], "agent_final_response_quality"
    )
    self.assertEqual(policies[0]["signal_type"], "final_response_quality_v1")

  def test_validate_policy_duration_quality(self):
    # Quality metrics alerts: MUST set duration="300s".
    policy_ok = {
        "signal_type": "final_response_quality_v1",
        "queries": [],
        "duration": "300s",
    }
    self.assertEqual(config_utils.validate_policy_duration(policy_ok), [])

    policy_err = {
        "signal_type": "final_response_quality_v1",
        "queries": [],
        "duration": "600s",
    }
    self.assertEqual(
        config_utils.validate_policy_duration(policy_err),
        [
            "Duration Error: Quality alerts MUST set duration='300s'. Found"
            " duration='600s'."
        ],
    )

  def test_validate_policy_duration_long_lookback(self):
    # Long-lookback alerts (>25h): must NOT set a duration (duration is None).
    query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[2d]))"
    policy_ok = {
        "signal_type": "latency",
        "queries": [query],
        "duration": None,
    }
    self.assertEqual(config_utils.validate_policy_duration(policy_ok), [])

    policy_err = {
        "signal_type": "latency",
        "queries": [query],
        "duration": "300s",
    }
    self.assertEqual(
        config_utils.validate_policy_duration(policy_err),
        [
            "Duration Error: Long-lookback alerts (>25h) must NOT set a"
            " duration. Found duration='300s' for lookback of 48h."
        ],
    )

  def test_validate_policy_duration_short_lookback(self):
    # Short-lookback alerts (<=25h): MUST set duration="300s".
    query = "sum(rate(workload_googleapis_com:gen_ai_invoke_agent_duration_count[5m]))"
    policy_ok = {
        "signal_type": "latency",
        "queries": [query],
        "duration": "300s",
    }
    self.assertEqual(config_utils.validate_policy_duration(policy_ok), [])

    policy_err = {
        "signal_type": "latency",
        "queries": [query],
        "duration": None,
    }
    self.assertEqual(
        config_utils.validate_policy_duration(policy_err),
        [
            "Duration Error: Short-lookback alerts (<=25h) MUST set"
            " duration='300s'. Found duration='None'."
        ],
    )


if __name__ == "__main__":
  unittest.main()
