"""Validation utility for chart_generation widget textprotos."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
import sys
import textproto_util  # type: ignore[missing-import]


parse_and_validate_widget = textproto_util.parse_and_validate_widget


def validate_widget(
    widget: textproto_util.Widget,
    expected_promql_substring: str = "",
    expected_unit_override: str = "",
    expected_plot_type: str = "",
) -> None:
  """Validates the Widget message structure and fields."""
  assert widget.title, "Widget title must not be empty"
  assert (
      len(widget.title) <= 80
  ), f"Widget title exceeds 80 chars: {len(widget.title)}"

  assert (
      widget.HasField("xy_chart") and widget.xy_chart is not None
  ), "Widget must contain an xy_chart"
  xy_chart = widget.xy_chart

  assert (
      len(xy_chart.data_sets) > 0
  ), "xy_chart must contain at least one data_set"
  ds = xy_chart.data_sets[0]

  assert (
      ds.time_series_query.prometheus_query
  ), "data_set must contain prometheus_query"

  if expected_promql_substring:
    assert (
        expected_promql_substring in ds.time_series_query.prometheus_query
    ), (
        "PromQL query missing expected substring"
        f" '{expected_promql_substring}'. Got:"
        f" {ds.time_series_query.prometheus_query}"
    )

  if expected_unit_override:
    assert (
        ds.time_series_query.unit_override == expected_unit_override
    ), (
        f"Expected unit_override '{expected_unit_override}', got"
        f" '{ds.time_series_query.unit_override}'"
    )

  if expected_plot_type:
    assert ds.plot_type == expected_plot_type, (
        f"Expected plot_type '{expected_plot_type}', got '{ds.plot_type}'"
    )


def main(argv: Sequence[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
      description="Validate widget textproto for chart_generation skill."
  )
  parser.add_argument(
      "--input_file",
      "-i",
      required=True,
      help="Path to Widget textproto file or '-' for STDIN.",
  )
  parser.add_argument(
      "--expected_promql_substring",
      default="",
      help="Expected substring in PromQL query.",
  )
  parser.add_argument(
      "--expected_unit_override",
      default="",
      help="Expected unit_override string (for example: '%%', 'By/s').",
  )
  parser.add_argument(
      "--expected_plot_type",
      default="",
      help="Expected plot_type (for example: 'LINE', 'STACKED_AREA').",
  )

  args = parser.parse_args(argv)

  try:
    content = None
    if args.input_file == "-":
      if not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
      work_dir = os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())
      input_path = args.input_file
      if not os.path.isabs(input_path):
        input_path = os.path.join(work_dir, input_path)
      if os.path.exists(input_path):
        with open(input_path, "r", encoding="utf-8") as f:
          content = f.read()

    if not content:
      print(
          f"ERROR: Input file '{args.input_file}' not found on disk.",
          file=sys.stderr,
      )
      return 1

    widget = textproto_util.parse_and_validate_widget(content)
    validate_widget(
        widget=widget,
        expected_promql_substring=args.expected_promql_substring,
        expected_unit_override=args.expected_unit_override,
        expected_plot_type=args.expected_plot_type,
    )
    print(
        f"Successfully validated Widget textproto '{args.input_file}'. Title:"
        f" '{widget.title}'"
    )
    return 0
  except Exception as e:  # pylint: disable=broad-except
    print(
        f"ERROR: Failed to validate Widget textproto: {e}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
  sys.exit(main())
