"""Stage 1: Generates baseline title and axis labels for SDUI charts."""

import argparse
import json
import re
from typing import Any

# Built-in lookup map covering standard Google Cloud Monitored Resources.
COMMON_RESOURCE_DISPLAY_MAP = {
    "gce_instance": "VM Instance",
    "gce_disk": "Compute Engine Disk",
    "k8s_container": "Kubernetes Container",
    "k8s_pod": "Kubernetes Pod",
    "k8s_node": "Kubernetes Node",
    "k8s_cluster": "Kubernetes Cluster",
    "k8s_service": "Kubernetes Service",
    "cloudsql_database": "Cloud SQL Database",
    "spanner_instance": "Cloud Spanner Instance",
    "pubsub_topic": "Cloud Pub/Sub Topic",
    "pubsub_subscription": "Cloud Pub/Sub Subscription",
    "cloud_run_revision": "Cloud Run Revision",
    "cloud_run_job": "Cloud Run Job",
    "cloud_function": "Cloud Function",
    "cloud_composer_environment": "Cloud Composer Environment",
    "cloud_dataproc_cluster": "Cloud Dataproc Cluster",
    "cloud_tasks_queue": "Cloud Tasks Queue",
    "dataflow_job": "Dataflow Job",
    "bigquery_dataset": "BigQuery Dataset",
    "bigquery_project": "BigQuery Project",
    "bigtable_cluster": "Cloud Bigtable Cluster",
    "bigtable_table": "Cloud Bigtable Table",
    "filestore_instance": "Filestore Instance",
    "gae_app": "GAE Application",
    "gae_instance": "GAE Instance",
    "gcs_bucket": "GCS Bucket",
    "redis_instance": "Memorystore Redis Instance",
    "aws_ec2_instance": "AWS EC2 Instance",
    "vpn_gateway": "VPN Gateway",
    "generic_task": "Generic Task",
    "generic_node": "Generic Node",
    "global": "Global",
}

# Comprehensive UCUM & SDUI Display Name Mapping Dictionary.
CANONICAL_UNIT_DISPLAY_MAP = {
    "1": "",
    "%": "Utilization",
    "10^2.%": "Utilization",
    "By": "Bytes",
    "By/s": "Bytes Rate",
    "kBy": "Kilobytes",
    "MBy": "Megabytes",
    "GBy": "Gigabytes",
    "s": "Seconds",
    "ms": "Milliseconds",
    "us": "Microseconds",
    "ns": "Nanoseconds",
    "1/s": "Operations Rate",
    "s/s": "Utilization",
}

# Supported PromQL aggregation operators.
PROMQL_AGGREGATORS = (
    "sum",
    "avg",
    "count",
    "min",
    "max",
    "stddev",
    "stdvar",
    "topk",
    "bottomk",
    "count_values",
    "quantile",
)


def compute_widget_title(
    metric_display_name: str,
    resource_type: str | None = None,
    filters: dict[str, str] | None = None,
    group_by_fields: list[str] | None = None,
    aggregation_string: str | None = None,
    is_ambiguous_metric_name: bool = False,
    custom_resource_display_name: str | None = None,
) -> str:
  """Synthesizes human-readable, 80-char constrained widget titles."""
  res_name = custom_resource_display_name or COMMON_RESOURCE_DISPLAY_MAP.get(
      resource_type or "", resource_type
  )

  if res_name and is_ambiguous_metric_name:
    descriptor_part = f"{res_name} - {metric_display_name}"
  else:
    descriptor_part = metric_display_name

  filter_part = ""
  if filters:
    user_filters = [
        v
        for k, v in filters.items()
        if k
        not in ("project_id", "resource.type", "resource.labels.project_id")
    ]
    if user_filters:
      filter_part = " for " + ", ".join(user_filters[:2])

  group_part = ""
  if group_by_fields:
    cleaned_groups = [
        g.replace("metric.label.", "")
        .replace("resource.label.", "")
        .replace("metric.", "")
        .replace("resource.", "")
        for g in group_by_fields
    ]
    group_part = " by " + ", ".join(cleaned_groups)

  agg_part = f" [{aggregation_string.upper()}]" if aggregation_string else ""

  full_title = f"{descriptor_part}{filter_part}{group_part}{agg_part}".strip()

  # 80 char threshold & short mode compaction for readability.
  if len(full_title) > 80:
    if group_part and len(group_part) > 15:
      group_part = " (grouped)"
    if filter_part and len(filter_part) > 15:
      filter_part = " (filtered)"
    full_title = f"{descriptor_part}{filter_part}{group_part}{agg_part}".strip()

  if len(full_title) > 80:
    return full_title[:77] + "..."
  return full_title


def compute_axis_units(
    raw_unit: str | None, has_rate_aligner: bool = False
) -> str:
  """Sanitizes raw UCUM/MetricDescriptor units into standard display formats."""
  if not raw_unit or raw_unit == "{not_a_unit}":
    return ""

  unit = raw_unit.strip()
  unit = re.sub(r"\s+", "", unit)
  unit = unit.replace("(rate)", "/s")

  if has_rate_aligner and not unit.endswith("/s") and unit != "1/s":
    unit = f"{unit}/s" if unit != "1" else "1/s"

  unit = re.sub(r"([^\.\/\{\}]+)(\{[^\{\}]+\})", r"\1", unit)
  unit = re.sub(r"\{[^\{\}]+\}", "1", unit)

  return CANONICAL_UNIT_DISPLAY_MAP.get(unit, unit)


def compute_axis_label(
    metric_display_names: list[str],
    raw_units: list[str | None],
    has_rate_aligners: list[bool] | None = None,
) -> str:
  """Combines quantitative unit scaling and text axis label joining."""
  sanitized_units: list[str] = []
  for i, u in enumerate(raw_units):
    is_rate = has_rate_aligners[i] if has_rate_aligners else False
    su = compute_axis_units(u, is_rate)
    if su and su not in sanitized_units:
      sanitized_units.append(su)

  if len(sanitized_units) == 1 and sanitized_units[0] != "":
    return sanitized_units[0]

  valid_names: list[str] = []
  for name in metric_display_names:
    clean = name.strip() if name else ""
    if clean and clean not in valid_names:
      valid_names.append(clean)

  if valid_names:
    return ", ".join(valid_names)

  return "PromQL Metric Axis"


def extract_promql_features(promql_query: str) -> dict[str, Any]:
  """Extracts basic AST characteristics from a PromQL query string."""
  query = promql_query.strip()

  filters: dict[str, str] = {}
  for match in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', query):
    k = match.group(1)
    v = match.group(2) if match.group(2) is not None else match.group(3)
    filters[k] = v

  # Sanitize query for aggregator detection:
  # 1. Remove string literals ("...", '...', `...`)
  sanitized = re.sub(
      r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`', " ", query
  )
  # 2. Remove template variables (${...}, $var, [[...]])
  sanitized = re.sub(
      r"\$\{[^}]*\}|\$[a-zA-Z0-9_]+|\[\[[^\]]*\]\]", " ", sanitized
  )
  # 3. Remove label matcher blocks ({...})
  sanitized = re.sub(r"\{[^}]*\}", " ", sanitized)

  has_rate = bool(re.search(r"\b(rate|irate)\s*\(", sanitized, re.IGNORECASE))

  group_bys: list[str] = []
  by_match = re.search(r"\bby\s*\(([^)]+)\)", query, re.IGNORECASE)
  if by_match:
    group_bys = [g.strip() for g in by_match.group(1).split(",") if g.strip()]

  # Find the first aggregator keyword in the sanitized query.
  agg_pattern = (
      r"\b(" + "|".join(re.escape(a) for a in PROMQL_AGGREGATORS) + r")\b"
  )
  first_agg: str | None = None
  for match in re.finditer(agg_pattern, sanitized, re.IGNORECASE):
    start, end = match.span()
    # Avoid matching if part of a dotted, colon, or path metric identifier
    if start > 0 and sanitized[start - 1] in (":", ".", "/"):
      continue
    if end < len(sanitized) and sanitized[end] in (":", ".", "/"):
      continue
    first_agg = match.group(1).upper()
    break

  if has_rate:
    agg = "RATE"
  elif first_agg:
    agg = first_agg
  else:
    agg = None

  return {
      "has_rate": has_rate,
      "aggregation": agg,
      "group_by_fields": group_bys,
      "filters": filters,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Stage 1 baseline candidate label generator for Server-Driven UI (SDUI) charts."
  )
  parser.add_argument(
      "--user_prompt",
      "-p",
      default="",
      help="Natural language prompt for plot type and polish.",
  )
  parser.add_argument(
      "--metric_type",
      "-t",
      default="",
      help=(
          "Metric type (for example:"
          " 'compute.googleapis.com/instance/cpu/utilization')."
      ),
  )
  parser.add_argument(
      "--metric_display_name",
      "-m",
      default="",
      help="Metric display name (for example: 'Disk Read Bytes', 'CPU Utilization').",
  )
  parser.add_argument(
      "--resource_type",
      "-r",
      default="",
      help="Resource type (for example: 'gce_instance', 'k8s_container').",
  )
  parser.add_argument(
      "--metric_unit",
      "-u",
      default="",
      help="Raw metric unit (for example: 'By', 's', '%%').",
  )
  parser.add_argument(
      "--promql_query", "-q", default="", help="Mandatory PromQL expression."
  )
  parser.add_argument(
      "--group_by",
      "-g",
      nargs="*",
      default=None,
      help="Optional list of group by fields.",
  )

  args = parser.parse_args()

  promql_info = (
      extract_promql_features(args.promql_query) if args.promql_query else {}
  )

  metric_name = args.metric_display_name or (
      args.metric_type.split("/")[-1] if args.metric_type else "Metric Query"
  )
  group_bys = (
      args.group_by
      if args.group_by is not None
      else promql_info.get("group_by_fields", [])
  )
  filters = promql_info.get("filters", {})
  agg = promql_info.get("aggregation", None)
  has_rate = promql_info.get("has_rate", False)

  title_candidate = compute_widget_title(
      metric_display_name=metric_name,
      resource_type=args.resource_type,
      filters=filters,
      group_by_fields=group_bys,
      aggregation_string=agg,
  )

  unit_override = compute_axis_units(
      args.metric_unit, has_rate_aligner=has_rate
  )
  axis_label_candidate = compute_axis_label(
      metric_display_names=[metric_name],
      raw_units=[args.metric_unit],
      has_rate_aligners=[has_rate],
  )
  result = {
      "titleCandidate": title_candidate,
      "yAxisLabelCandidate": axis_label_candidate,
      "unitOverrideCandidate": unit_override,
  }

  print(json.dumps(result, indent=2))


if __name__ == "__main__":
  main()
