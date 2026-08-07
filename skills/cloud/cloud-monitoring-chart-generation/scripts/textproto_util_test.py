"""Comprehensive unit tests for textproto_util.py."""

from absl.testing import absltest
from dataclasses import asdict
import textproto_util  # type: ignore[missing-import]



class TextprotoUtilTest(absltest.TestCase):

  def test_tokenize_basic(self):
    text = 'widget { title: "Hello World" }'
    tokens = textproto_util.tokenize_textproto(text)
    self.assertEqual(
        tokens,
        [
            ("SYM", "widget"),
            ("{", "{"),
            ("SYM", "title"),
            (":", ":"),
            ("STR", "Hello World"),
            ("}", "}"),
        ],
    )

  def test_tokenize_with_comments(self):
    text = """
    # This is a comment
    widget { # inline comment
      title: "Test" # another comment
    }
    """
    tokens = textproto_util.tokenize_textproto(text)
    self.assertEqual(
        tokens,
        [
            ("SYM", "widget"),
            ("{", "{"),
            ("SYM", "title"),
            (":", ":"),
            ("STR", "Test"),
            ("}", "}"),
        ],
    )

  def test_tokenize_escaped_strings(self):
    text = 'title: "Line 1 \\"quoted\\" \\\\ path"'
    tokens = textproto_util.tokenize_textproto(text)
    self.assertEqual(
        tokens,
        [
            ("SYM", "title"),
            (":", ":"),
            ("STR", 'Line 1 "quoted" \\ path'),
        ],
    )

  def test_parse_textproto_tokens_nested(self):
    text = """
    xy_chart {
      chart_options {
        mode: COLOR
      }
      y_axis {
        label: "Utilization"
        scale: LINEAR
      }
    }
    """
    tokens = textproto_util.tokenize_textproto(text)
    obj, _ = textproto_util.parse_textproto_tokens(tokens)
    self.assertEqual(
        obj,
        {
            "xy_chart": {
                "chart_options": {"mode": "COLOR"},
                "y_axis": {"label": "Utilization", "scale": "LINEAR"},
            }
        },
    )

  def test_parse_textproto_repeated_fields(self):
    text = """
    data_sets { plot_type: LINE }
    data_sets { plot_type: STACKED_AREA }
    """
    tokens = textproto_util.tokenize_textproto(text)
    obj, _ = textproto_util.parse_textproto_tokens(tokens)
    self.assertIsInstance(obj["data_sets"], list)
    self.assertEqual(len(obj["data_sets"]), 2)
    self.assertEqual(obj["data_sets"][0]["plot_type"], "LINE")
    self.assertEqual(obj["data_sets"][1]["plot_type"], "STACKED_AREA")

  def test_parse_and_validate_widget_wrapped(self):
    text = """
    widget {
      title: "CPU Utilization"
      xy_chart {
        chart_options { mode: COLOR }
        data_sets {
          time_series_query {
            prometheus_query: "avg(cpu)"
            unit_override: "%"
          }
          plot_type: LINE
          target_axis: Y1
        }
        y_axis {
          label: "CPU (%)"
          scale: LINEAR
        }
      }
    }
    """
    widget = textproto_util.parse_and_validate_widget(text)
    self.assertEqual(widget.title, "CPU Utilization")
    self.assertTrue(widget.HasField("xy_chart"))
    self.assertIsNotNone(widget.xy_chart)
    assert widget.xy_chart is not None
    self.assertEqual(widget.xy_chart.chart_options.mode, "COLOR")
    self.assertEqual(len(widget.xy_chart.data_sets), 1)
    ds = widget.xy_chart.data_sets[0]
    self.assertEqual(ds.time_series_query.prometheus_query, "avg(cpu)")
    self.assertEqual(ds.time_series_query.unit_override, "%")
    self.assertEqual(ds.plot_type, "LINE")
    self.assertEqual(widget.xy_chart.y_axis.label, "CPU (%)")
    self.assertEqual(widget.xy_chart.y_axis.scale, "LINEAR")

  def test_parse_and_validate_widget_unwrapped(self):
    text = """
    title: "Memory Used"
    xy_chart {
      data_sets {
        time_series_query {
          prometheus_query: "memory_query"
        }
      }
    }
    """
    widget = textproto_util.parse_and_validate_widget(text)
    self.assertEqual(widget.title, "Memory Used")
    self.assertTrue(widget.HasField("xy_chart"))
    self.assertIsNotNone(widget.xy_chart)
    assert widget.xy_chart is not None
    self.assertEqual(
        widget.xy_chart.data_sets[0].time_series_query.prometheus_query,
        "memory_query",
    )
    self.assertEqual(widget.xy_chart.data_sets[0].plot_type, "LINE")
    self.assertEqual(widget.xy_chart.y_axis.scale, "LINEAR")

  def test_parse_and_validate_widget_missing_fields(self):
    text = 'title: "Empty Chart"'
    widget = textproto_util.parse_and_validate_widget(text)
    self.assertEqual(widget.title, "Empty Chart")
    self.assertFalse(widget.HasField("xy_chart"))

  def test_parse_and_validate_widget_multiple_datasets(self):
    text = """
    title: "Multi Metric"
    xy_chart {
      data_sets {
        time_series_query { prometheus_query: "query1" }
        plot_type: LINE
      }
      data_sets {
        time_series_query { prometheus_query: "query2" }
        plot_type: STACKED_AREA
      }
    }
    """
    widget = textproto_util.parse_and_validate_widget(text)
    self.assertIsNotNone(widget.xy_chart)
    assert widget.xy_chart is not None
    self.assertEqual(len(widget.xy_chart.data_sets), 2)
    self.assertEqual(
        widget.xy_chart.data_sets[0].time_series_query.prometheus_query,
        "query1",
    )
    self.assertEqual(widget.xy_chart.data_sets[1].plot_type, "STACKED_AREA")

  def test_readable_dict_comparison_basic(self):
    """Easy-to-read structural comparison of parsed textproto against expected dict."""
    textproto = """
    widget {
      title: "GCE Instance CPU Utilization"
      xy_chart {
        chart_options { mode: COLOR }
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
    widget = textproto_util.parse_and_validate_widget(textproto)
    expected_dict = {
        "title": "GCE Instance CPU Utilization",
        "xy_chart": {
            "chart_options": {"mode": "COLOR"},
            "data_sets": [
                {
                    "time_series_query": {
                        "prometheus_query": (
                            "100 *"
                            " avg(compute_googleapis_com:instance_cpu_utilization)"
                        ),
                        "unit_override": "%",
                    },
                    "plot_type": "LINE",
                    "target_axis": "Y1",
                }
            ],
            "y_axis": {
                "label": "Utilization (%)",
                "scale": "LINEAR",
            },
        },
    }
    self.assertEqual(asdict(widget), expected_dict)

  def test_readable_dict_comparison_unwrapped_stacked_area(self):
    """Easy-to-read structural comparison for unwrapped STACKED_AREA charts without unit override."""
    textproto = """
    title: "Memory Percent Used"
    xy_chart {
      data_sets {
        time_series_query {
          prometheus_query: "avg(agent_googleapis_com:memory_percent_used)"
        }
        plot_type: STACKED_AREA
      }
    }
    """
    widget = textproto_util.parse_and_validate_widget(textproto)
    expected_dict = {
        "title": "Memory Percent Used",
        "xy_chart": {
            "chart_options": {"mode": "COLOR"},
            "data_sets": [
                {
                    "time_series_query": {
                        "prometheus_query": (
                            "avg(agent_googleapis_com:memory_percent_used)"
                        ),
                        "unit_override": "",
                    },
                    "plot_type": "STACKED_AREA",
                    "target_axis": "Y1",
                }
            ],
            "y_axis": {
                "label": "",
                "scale": "LINEAR",
            },
        },
    }
    self.assertEqual(asdict(widget), expected_dict)

  def test_readable_dict_comparison_multi_metric(self):
    """Easy-to-read structural comparison for multi-series charts."""
    textproto = """
    title: "Network Traffic"
    xy_chart {
      data_sets {
        time_series_query {
          prometheus_query: "rate(net_in[1m])"
          unit_override: "By/s"
        }
        plot_type: LINE
      }
      data_sets {
        time_series_query {
          prometheus_query: "rate(net_out[1m])"
          unit_override: "By/s"
        }
        plot_type: STACKED_AREA
      }
      y_axis {
        label: "Bytes/s"
        scale: LOG10
      }
    }
    """
    widget = textproto_util.parse_and_validate_widget(textproto)
    expected_dict = {
        "title": "Network Traffic",
        "xy_chart": {
            "chart_options": {"mode": "COLOR"},
            "data_sets": [
                {
                    "time_series_query": {
                        "prometheus_query": "rate(net_in[1m])",
                        "unit_override": "By/s",
                    },
                    "plot_type": "LINE",
                    "target_axis": "Y1",
                },
                {
                    "time_series_query": {
                        "prometheus_query": "rate(net_out[1m])",
                        "unit_override": "By/s",
                    },
                    "plot_type": "STACKED_AREA",
                    "target_axis": "Y1",
                },
            ],
            "y_axis": {
                "label": "Bytes/s",
                "scale": "LOG10",
            },
        },
    }
    self.assertEqual(asdict(widget), expected_dict)


if __name__ == "__main__":
  absltest.main()
