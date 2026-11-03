"""Unit tests for discover_metric_schema.py."""

import io
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_metric_schema  # pytype: disable=import-error  # pyrefly: ignore[missing-import]

SAMPLE_DESCRIPTORS = [
    {
        "name": (
            "projects/test-proj/metricDescriptors/pubsub.googleapis.com/topic/send_request_count"
        ),
        "type": "pubsub.googleapis.com/topic/send_request_count",
        "metricKind": "DELTA",
        "valueType": "INT64",
        "unit": "1",
        "monitoredResourceTypes": ["pubsub_topic"],
        "labels": [
            {
                "key": "response_class",
                "description": (
                    "A classification group for the response code. It can be"
                    " one of ['success', 'invalid', 'internal']."
                ),
            },
            {
                "key": "response_code",
                "description": (
                    "Operation response code string (e.g., 'success',"
                    " 'not_found', 'unavailable')."
                ),
            },
        ],
    },
    {
        "name": (
            "projects/test-proj/metricDescriptors/pubsub.googleapis.com/topic/send_request_latencies"
        ),
        "type": "pubsub.googleapis.com/topic/send_request_latencies",
        "metricKind": "DELTA",
        "valueType": "DISTRIBUTION",
        "unit": "us",
        "monitoredResourceTypes": ["pubsub_topic"],
        "labels": [
            {
                "key": "response_code",
                "description": (
                    "Operation response code string (e.g., 'success',"
                    " 'not_found', 'unavailable')."
                ),
            },
        ],
    },
]

SAMPLE_RESOURCE_DESCRIPTOR = {
    "type": "pubsub_topic",
    "labels": [
        {"key": "project_id", "description": "GCP project ID."},
        {"key": "topic_id", "description": "Pub/Sub topic ID."},
    ],
}


class DiscoverMetricSchemaTest(unittest.TestCase):

  def test_gcp_metric_to_promql_scalar_and_distribution(self):
    self.assertEqual(
        discover_metric_schema.gcp_metric_to_promql(
            "pubsub.googleapis.com/topic/send_request_count", "INT64"
        ),
        "pubsub_googleapis_com:topic_send_request_count",
    )
    self.assertEqual(
        discover_metric_schema.gcp_metric_to_promql(
            "pubsub.googleapis.com/topic/send_request_latencies", "DISTRIBUTION"
        ),
        "pubsub_googleapis_com:topic_send_request_latencies_bucket",
    )
    # Already has _bucket
    self.assertEqual(
        discover_metric_schema.gcp_metric_to_promql(
            "custom.googleapis.com/my/dist_bucket", "DISTRIBUTION"
        ),
        "custom_googleapis_com:my_dist_bucket",
    )

  def test_promql_to_gcp_prefix(self):
    self.assertEqual(
        discover_metric_schema.promql_to_gcp_prefix(
            "pubsub_googleapis_com:topic_send_request_latencies_bucket"
        ),
        "pubsub.googleapis.com/topic",
    )
    self.assertEqual(
        discover_metric_schema.promql_to_gcp_prefix(
            "cloudsql_googleapis_com:database_cpu_utilization"
        ),
        "cloudsql.googleapis.com/database",
    )

  def test_format_unit_guidance(self):
    us_guidance = discover_metric_schema.format_unit_guidance("us")
    self.assertIn("MICROSECONDS ('us')", us_guidance)
    self.assertIn("MULTIPLY MILLISECONDS BY 1,000", us_guidance)

    ns_guidance = discover_metric_schema.format_unit_guidance("ns")
    self.assertIn("NANOSECONDS ('ns')", ns_guidance)

    ms_guidance = discover_metric_schema.format_unit_guidance("ms")
    self.assertIn("Milliseconds ('ms')", ms_guidance)

    s_guidance = discover_metric_schema.format_unit_guidance("s")
    self.assertIn("Seconds ('s')", s_guidance)

    by_guidance = discover_metric_schema.format_unit_guidance("By")
    self.assertIn("Bytes ('By')", by_guidance)

  def test_extract_documented_enums(self):
    bracket_desc = (
        "A classification group. It can be one of ['success', 'invalid',"
        " 'internal']."
    )
    self.assertEqual(
        discover_metric_schema.extract_documented_enums(bracket_desc),
        ["success", "invalid", "internal"],
    )

    paren_desc = (
        "Status code string (e.g., 'success', 'not_found', 'unavailable')."
    )
    self.assertEqual(
        discover_metric_schema.extract_documented_enums(paren_desc),
        ["success", "not_found", "unavailable"],
    )

    no_enum_desc = "Whether or not the publish contained ordering keys."
    self.assertEqual(
        discover_metric_schema.extract_documented_enums(no_enum_desc), []
    )

  def test_validate_promql_against_schema_valid_query(self):
    valid_query = (
        "histogram_quantile(0.95, sum by (topic_id, le)"
        ' (rate(pubsub_googleapis_com:topic_send_request_latencies_bucket{project_id="p",'
        ' response_code!="success"}[5m]))) > 1000000'
    )
    warnings = discover_metric_schema.validate_promql_against_schema(
        valid_query, SAMPLE_DESCRIPTORS
    )
    self.assertEqual(warnings, [])

  def test_validate_promql_catches_unknown_metric_and_suggests_match(self):
    typo_query = (
        "sum by (topic_id)"
        " (rate(pubsub_googleapis_com:topic_send_latencies_bucket[5m])) >"
        " 1000000"
    )
    warnings = discover_metric_schema.validate_promql_against_schema(
        typo_query, SAMPLE_DESCRIPTORS
    )
    self.assertEqual(len(warnings), 1)
    self.assertIn(
        "[ERROR] PromQL metric"
        " 'pubsub_googleapis_com:topic_send_latencies_bucket' does NOT exist",
        warnings[0],
    )
    self.assertIn("Did you mean:", warnings[0])
    self.assertIn(
        "pubsub_googleapis_com:topic_send_request_latencies_bucket",
        warnings[0],
    )

  def test_validate_promql_catches_missing_bucket_on_distribution(self):
    no_bucket_query = (
        "histogram_quantile(0.95, sum by (topic_id, le)"
        " (rate(pubsub_googleapis_com:topic_send_request_latencies[5m]))) >"
        " 1000000"
    )
    warnings = discover_metric_schema.validate_promql_against_schema(
        no_bucket_query, SAMPLE_DESCRIPTORS
    )
    self.assertEqual(len(warnings), 1)
    self.assertIn("valueType=DISTRIBUTION", warnings[0])
    self.assertIn(
        "pubsub_googleapis_com:topic_send_request_latencies_bucket",
        warnings[0],
    )

  def test_validate_promql_catches_microsecond_unit_trap(self):
    small_threshold_query = (
        "histogram_quantile(0.95, sum by (topic_id, le)"
        " (rate(pubsub_googleapis_com:topic_send_request_latencies_bucket[5m])))"
        " > 1000"
    )
    warnings = discover_metric_schema.validate_promql_against_schema(
        small_threshold_query, SAMPLE_DESCRIPTORS
    )
    self.assertEqual(len(warnings), 1)
    self.assertIn("has unit 'us' (microseconds/nanoseconds)", warnings[0])
    self.assertIn("threshold is '1000.0'", warnings[0])

  def test_validate_promql_catches_invalid_label_enum_casing(self):
    bad_enum_query = (
        "sum by (topic_id)"
        ' (rate(pubsub_googleapis_com:topic_send_request_count{response_code!="OK"}[5m]))'
        " > 5"
    )
    warnings = discover_metric_schema.validate_promql_against_schema(
        bad_enum_query, SAMPLE_DESCRIPTORS
    )
    self.assertEqual(len(warnings), 1)
    self.assertIn("uses value 'OK'", warnings[0])
    self.assertIn("['success', 'not_found', 'unavailable']", warnings[0])

  @mock.patch.object(subprocess, "run")
  def test_get_access_token_success(self, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="mock-oauth-token\n", stderr=""
    )
    self.assertEqual(
        discover_metric_schema.get_access_token(), "mock-oauth-token"
    )

  @mock.patch.object(discover_metric_schema, "api_get")
  def test_fetch_metric_descriptors_builds_filter(self, mock_api_get):
    mock_api_get.return_value = {"metricDescriptors": SAMPLE_DESCRIPTORS}
    res = discover_metric_schema.fetch_metric_descriptors(
        project="my-proj",
        token="tok",
        resource_type="pubsub_topic",
        metric_prefix="pubsub.googleapis.com/topic/",
    )
    self.assertEqual(res, SAMPLE_DESCRIPTORS)
    called_url = mock_api_get.call_args[0][0]
    self.assertIn("projects/my-proj/metricDescriptors", called_url)
    self.assertIn("pubsub_topic", called_url)

  @mock.patch.object(discover_metric_schema, "get_access_token")
  @mock.patch.object(discover_metric_schema, "fetch_metric_descriptors")
  @mock.patch.object(discover_metric_schema, "fetch_resource_descriptor")
  def test_main_cli_exits_zero_on_valid_promql(
      self, mock_fetch_res, mock_fetch_metrics, mock_token
  ):
    mock_token.return_value = "fake-token"
    mock_fetch_metrics.return_value = SAMPLE_DESCRIPTORS
    mock_fetch_res.return_value = SAMPLE_RESOURCE_DESCRIPTOR

    valid_q = (
        "sum by (topic_id)"
        ' (rate(pubsub_googleapis_com:topic_send_request_count{response_class!="success"}[5m]))'
        " > 0.01"
    )
    test_args = [
        "discover_metric_schema.py",
        "--project=test-proj",
        "--resource-type=pubsub_topic",
        f"--promql={valid_q}",
    ]
    with (
        mock.patch("sys.argv", test_args),
        mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
    ):
      discover_metric_schema.main()
      output = mock_stdout.getvalue()
      self.assertIn(
          "[OK] PromQL metric names, units, and label matchers verified", output
      )

  @mock.patch.object(discover_metric_schema, "get_access_token")
  @mock.patch.object(discover_metric_schema, "fetch_metric_descriptors")
  @mock.patch.object(discover_metric_schema, "fetch_resource_descriptor")
  def test_main_cli_exits_one_on_invalid_promql(
      self, mock_fetch_res, mock_fetch_metrics, mock_token
  ):
    mock_token.return_value = "fake-token"
    mock_fetch_metrics.return_value = SAMPLE_DESCRIPTORS
    mock_fetch_res.return_value = SAMPLE_RESOURCE_DESCRIPTOR

    invalid_q = (
        "sum by (topic_id)"
        ' (rate(pubsub_googleapis_com:topic_send_request_count{response_code!="OK"}[5m]))'
        " > 0.01"
    )
    test_args = [
        "discover_metric_schema.py",
        "--project=test-proj",
        f"--promql={invalid_q}",
    ]
    with (
        mock.patch("sys.argv", test_args),
        mock.patch("sys.stdout", new_callable=io.StringIO),
    ):
      with self.assertRaises(SystemExit) as cm:
        discover_metric_schema.main()
      self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
  unittest.main()
