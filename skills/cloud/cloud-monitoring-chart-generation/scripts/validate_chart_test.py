"""Unit test for validate_chart.py."""

from absl.testing import absltest
import validate_chart  # type: ignore[missing-import]


class ValidateChartTest(absltest.TestCase):

  def test_parse_and_validate_wrapped_widget(self):
    textproto = """
widget {
  title: "GCE Instance CPU Utilization"
  xy_chart {
    chart_options {
      mode: COLOR
    }
    data_sets {
      time_series_query {
        prometheus_query: "100 * avg(compute_googleapis_com:instance_cpu_utilization)"
        unit_override: "%"
      }
      plot_type: LINE
      target_axis: Y1
    }
    y_axis {
      label: "Utilization (%)"
      scale: LINEAR
    }
  }
}
"""
    widget = validate_chart.parse_and_validate_widget(textproto)
    self.assertEqual(widget.title, "GCE Instance CPU Utilization")
    validate_chart.validate_widget(
        widget=widget,
        expected_promql_substring="instance_cpu_utilization",
        expected_unit_override="%",
        expected_plot_type="LINE",
    )

  def test_parse_and_validate_unwrapped_widget(self):
    textproto = """
title: "Memory Percent Used"
xy_chart {
  data_sets {
    time_series_query {
      prometheus_query: "avg(agent_googleapis_com:memory_percent_used)"
      unit_override: "%"
    }
    plot_type: LINE
  }
}
"""
    widget = validate_chart.parse_and_validate_widget(textproto)
    self.assertEqual(widget.title, "Memory Percent Used")
    validate_chart.validate_widget(
        widget=widget,
        expected_promql_substring="memory_percent_used",
        expected_unit_override="%",
        expected_plot_type="LINE",
    )

  def test_validate_widget_empty_title_fails(self):
    textproto = """
xy_chart {
  data_sets {
    time_series_query {
      prometheus_query: "query"
    }
  }
}
"""
    widget = validate_chart.parse_and_validate_widget(textproto)
    with self.assertRaises(AssertionError):
      validate_chart.validate_widget(widget=widget)

  def test_main_validate_from_stdin(self):
    textproto = """
title: "Disk Read Bytes"
xy_chart {
  data_sets {
    time_series_query {
      prometheus_query: "rate(compute_googleapis_com:instance_disk_read_bytes_count[1m])"
      unit_override: "By/s"
    }
    plot_type: LINE
  }
}
"""
    import io
    import sys
    sys.stdin = io.StringIO(textproto)
    ret = validate_chart.main([
        "--input_file",
        "-",
        "--expected_promql_substring",
        "instance_disk_read_bytes_count",
        "--expected_unit_override",
        "By/s",
    ])
    self.assertEqual(ret, 0)


if __name__ == "__main__":
  absltest.main()
