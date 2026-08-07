"""Stage 3: Assembles and validates google.monitoring.dashboard.v1.Widget textproto."""

import argparse
import json
import os
import sys


def format_proto_string(val: str) -> str:
  """Escapes and quotes a string for protobuf text format."""
  escaped = val.replace("\\", "\\\\").replace('"', '\\"')
  return f'"{escaped}"'


def assemble_widget_textproto(
    title: str,
    promql_query: str,
    plot_type: str = "LINE",
    y_axis_label: str = "",
    unit_override: str = "",
    scale: str = "LINEAR",
) -> str:
  """Assembles a valid Widget protobuf textproto string with omitted legend_template."""
  clean_title = title.strip()
  clean_promql = promql_query.strip()
  clean_plot_type = plot_type.strip().upper() if plot_type else "LINE"
  clean_scale = scale.strip().upper() if scale else "LINEAR"

  if clean_plot_type not in ("LINE", "STACKED_AREA", "STACKED_BAR", "HEATMAP"):
    clean_plot_type = "LINE"

  lines = [
      "widget {",
      f"  title: {format_proto_string(clean_title)}",
      "  xy_chart {",
      "    chart_options {",
      "      mode: COLOR",
      "    }",
      "    data_sets {",
      "      time_series_query {",
      f"        prometheus_query: {format_proto_string(clean_promql)}",
  ]

  if unit_override and unit_override.strip():
    lines.append(
        f"        unit_override: {format_proto_string(unit_override.strip())}"
    )

  lines.extend([
      "      }",
      f"      plot_type: {clean_plot_type}",
      "      target_axis: Y1",
      "    }",
      "    y_axis {",
  ])

  if y_axis_label and y_axis_label.strip():
    lines.append(f"      label: {format_proto_string(y_axis_label.strip())}")

  lines.extend([
      f"      scale: {clean_scale}",
      "    }",
      "  }",
      "}",
  ])

  return "\n".join(lines)


def get_auto_output_path(work_dir: str) -> str:
  """Automatically assigns deterministic sequential filenames (chart.textproto, chart_2.textproto)."""
  # Adjust for Google3 environments where the agent may run from the CitC client root
  # rather than the google3/ directory. This check is safely bypassed in public (GitHub)
  # environments because the google3/ directory will not exist. Internally, the workspace
  # contains a parent CitC directory (causing flakiness if the agent runs from there). Externally,
  # the Git checkout is the true root, so agents won't accidentally run from a parent wrapper.
  if not work_dir.endswith("google3") and os.path.basename(work_dir) != "google3":
    if os.path.exists(os.path.join(work_dir, "google3")):
      work_dir = os.path.join(work_dir, "google3")
  idx = 1
  while True:
    filename = "chart.textproto" if idx == 1 else f"chart_{idx}.textproto"
    candidate = os.path.join(work_dir, filename)
    if not os.path.exists(candidate):
      return candidate
    idx += 1


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Stage 3 Server-Driven UI (SDUI) widget textproto assembler."
  )
  parser.add_argument(
      "--promql_query", "-q", required=True, help="PromQL query expression."
  )
  parser.add_argument("--title", "-t", default="", help="Widget chart title.")
  parser.add_argument(
      "--plot_type",
      "-p",
      default="LINE",
      help="Plot type (for example: LINE, STACKED_AREA).",
  )
  parser.add_argument(
      "--y_axis_label", "-y", default="", help="Y-axis label string."
  )
  parser.add_argument(
      "--unit_override",
      "-u",
      default="",
      help="Unit override string (for example: '%%', 'By/s').",
  )
  parser.add_argument(
      "--scale", "-s", default="LINEAR", help="Y-axis scale (LINEAR or LOG10)."
  )
  parser.add_argument(
      "--spec_json",
      "-j",
      default="",
      help="JSON string of SemanticPlotSpec from Stage 2.",
  )

  args = parser.parse_args()

  title = args.title
  plot_type = args.plot_type
  y_axis_label = args.y_axis_label
  unit_override = args.unit_override

  if args.spec_json:
    try:
      spec = json.loads(args.spec_json)
      if isinstance(spec, dict):
        title = spec.get("title", title)
        plot_type = spec.get("plotType", plot_type)
        y_axis_label = spec.get("yAxisLabel", y_axis_label)
        unit_override = spec.get("unitOverride", unit_override)
    except Exception:
      pass

  if not title:
    title = "Monitoring Chart"

  proto_text = assemble_widget_textproto(
      title=title,
      promql_query=args.promql_query,
      plot_type=plot_type,
      y_axis_label=y_axis_label,
      unit_override=unit_override,
      scale=args.scale,
  )

  print(proto_text)
  work_dir = os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())
  output_path = get_auto_output_path(work_dir)

  with open(output_path, "w", encoding="utf-8") as f:
    f.write(proto_text)
  print(f"Wrote widget textproto to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
  main()
