"""Unit tests for compute_labels.py."""

from absl.testing import absltest
import compute_labels  # type: ignore[missing-import]


class ComputeLabelsTest(absltest.TestCase):

  def test_compute_widget_title_standard(self):
    title = compute_labels.compute_widget_title(
        metric_display_name="Disk Read Bytes",
        resource_type="gce_instance",
        filters={"zone": "us-east1-d"},
        group_by_fields=["metric.label.device_name"],
        aggregation_string="SUM",
    )
    self.assertEqual(
        title, "Disk Read Bytes for us-east1-d by device_name [SUM]"
    )

  def test_compute_widget_title_ambiguous(self):
    title = compute_labels.compute_widget_title(
        metric_display_name="CPU Utilization",
        resource_type="gce_instance",
        is_ambiguous_metric_name=True,
    )
    self.assertEqual(title, "VM Instance - CPU Utilization")

  def test_common_resource_display_map(self):
    self.assertEqual(
        compute_labels.COMMON_RESOURCE_DISPLAY_MAP["gce_disk"],
        "Compute Engine Disk",
    )
    self.assertEqual(
        compute_labels.COMMON_RESOURCE_DISPLAY_MAP["gae_app"],
        "GAE Application",
    )
    self.assertEqual(
        compute_labels.COMMON_RESOURCE_DISPLAY_MAP["cloud_run_job"],
        "Cloud Run Job",
    )

  def test_compute_widget_title_long_truncation(self):
    title = compute_labels.compute_widget_title(
        metric_display_name=(
            "Very Long Metric Display Name That Exceeds Normal Length"
            " Constraints Significantly"
        ),
        resource_type="gce_instance",
        filters={"zone": "us-central1-a-very-long-filter-name-here"},
        group_by_fields=["metric.label.long_group_by_field_name_xyz"],
        aggregation_string="RATE",
    )
    self.assertLessEqual(len(title), 80)
    self.assertTrue(title.endswith("..."))

  def test_compute_axis_units_ucum(self):
    self.assertEqual(
        compute_labels.compute_axis_units("10^2.%"), "Utilization"
    )
    self.assertEqual(
        compute_labels.compute_axis_units("By", has_rate_aligner=True),
        "Bytes Rate",
    )
    self.assertEqual(
        compute_labels.compute_axis_units("s{CPU}/s"),
        "Utilization",
    )

  def test_compute_axis_label_single_unit(self):
    label = compute_labels.compute_axis_label(
        metric_display_names=["Disk Read Bytes"],
        raw_units=["By"],
        has_rate_aligners=[True],
    )
    self.assertEqual(label, "Bytes Rate")

  def test_compute_axis_label_multiple_units_fallback_names(self):
    label = compute_labels.compute_axis_label(
        metric_display_names=["Disk Read Bytes", "Read Latency"],
        raw_units=["By", "ms"],
    )
    self.assertEqual(label, "Disk Read Bytes, Read Latency")

  def test_compute_axis_label_no_unit_metric_name(self):
    label = compute_labels.compute_axis_label(
        metric_display_names=["Disk Read Bytes"],
        raw_units=[None],
    )
    self.assertEqual(label, "Disk Read Bytes")

  def test_compute_axis_label_default_fallback(self):
    label = compute_labels.compute_axis_label(
        metric_display_names=[],
        raw_units=["{not_a_unit}"],
    )
    self.assertEqual(label, "PromQL Metric Axis")

  def test_extract_promql_features_standard(self):
    query = (
        "sum by (device_name)"
        ' (rate(compute_googleapis_com:instance_disk_read_bytes_count{zone="us-east1-d"}[1m]))'
    )
    features = compute_labels.extract_promql_features(query)
    self.assertTrue(features["has_rate"])
    self.assertEqual(features["aggregation"], "RATE")
    self.assertEqual(features["group_by_fields"], ["device_name"])
    self.assertEqual(features["filters"], {"zone": "us-east1-d"})

  def test_extract_promql_features_aggregators(self):
    aggregators_map = {
        "sum(metric)": "SUM",
        "avg(metric)": "AVG",
        "count(metric)": "COUNT",
        "min(metric)": "MIN",
        "max(metric)": "MAX",
        "stddev(metric)": "STDDEV",
        "stdvar(metric)": "STDVAR",
        "topk(5, metric)": "TOPK",
        "bottomk(5, metric)": "BOTTOMK",
        'count_values("version", metric)': "COUNT_VALUES",
        "quantile(0.9, metric)": "QUANTILE",
    }
    for query, expected_agg in aggregators_map.items():
      features = compute_labels.extract_promql_features(query)
      self.assertEqual(
          features["aggregation"],
          expected_agg,
          msg=f"Failed for query: {query}",
      )

  def test_extract_promql_features_ignore_metric_names_and_templates(self):
    query_metric_name = (
        "compute_googleapis_com:instance_cpu_maximum_utilization"
    )
    features1 = compute_labels.extract_promql_features(query_metric_name)
    self.assertIsNone(features1["aggregation"])

    query_template_and_string = (
        'rate(http_requests_total{status="sum", env="${max_var}", label="it\'s'
        ' a value"}[5m])'
    )
    features2 = compute_labels.extract_promql_features(
        query_template_and_string
    )
    self.assertTrue(features2["has_rate"])
    self.assertEqual(features2["aggregation"], "RATE")
    self.assertEqual(
        features2["filters"],
        {"status": "sum", "env": "${max_var}", "label": "it's a value"},
    )

  def test_extract_promql_features_first_aggregator_detected(self):
    query = "max(sum(metric))"
    features = compute_labels.extract_promql_features(query)
    self.assertEqual(features["aggregation"], "MAX")

    query_with_rate = "max(sum(rate(metric[1m])))"
    features_rate = compute_labels.extract_promql_features(query_with_rate)
    self.assertEqual(features_rate["aggregation"], "RATE")

  def test_compute_widget_title_with_extracted_features(self):
    query = (
        "sum by (device_name)"
        ' (rate(compute_googleapis_com:instance_disk_read_bytes_count{zone="us-east1-d"}[1m]))'
    )
    features = compute_labels.extract_promql_features(query)
    title = compute_labels.compute_widget_title(
        metric_display_name="Disk Read Bytes",
        resource_type="gce_instance",
        filters=features["filters"],
        group_by_fields=features["group_by_fields"],
        aggregation_string=features["aggregation"],
    )
    self.assertEqual(
        title, "Disk Read Bytes for us-east1-d by device_name [RATE]"
    )


if __name__ == "__main__":
  absltest.main()
