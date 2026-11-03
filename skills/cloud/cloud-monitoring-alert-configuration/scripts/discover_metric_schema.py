#!/usr/bin/env python3
"""Universal GCP Metric Schema Discovery & PromQL Validator for Generic Resources.

Queries the Cloud Monitoring v3 API (metricDescriptors and
monitoredResourceDescriptors) to discover exact PromQL metric names, units,
resource grouping labels, metric label keys, and documented label enum values
for any GCP service or custom workload. Optionally validates a PromQL query
against the live schema to catch metric name typos, unit scaling bugs (e.g.,
microseconds 'us' vs milliseconds 'ms'), and invalid label enum comparisons.
"""

import argparse
import json
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request


def get_access_token() -> str:
  """Retrieves a GCP access token using ADC or gcloud auth."""
  commands = [
      ["gcloud", "auth", "application-default", "print-access-token"],
      ["gcloud", "auth", "print-access-token"],
  ]
  for cmd in commands:
    try:
      result = subprocess.run(
          cmd,
          check=True,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          text=True,
      )
      token = result.stdout.strip()
      if token:
        return token
    except subprocess.CalledProcessError:
      continue
  raise RuntimeError(
      "Failed to obtain GCP access token via 'gcloud auth application-default"
      " print-access-token' or 'gcloud auth print-access-token'."
  )


def get_default_project() -> Optional[str]:
  """Retrieves default project ID from gcloud config if not specified."""
  try:
    result = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proj = result.stdout.strip()
    return proj if proj and proj != "(unset)" else None
  except subprocess.CalledProcessError:
    return None


def api_get(url: str, token: str) -> Dict[str, Any]:
  """Performs a GET request against the Cloud Monitoring v3 API."""
  headers = {
      "Authorization": f"Bearer {token}",
      "User-Agent": (
          "google-skills/1.0 (skill:cloud-monitoring-alert-configuration;"
          " script:discover_metric_schema)"
      ),
  }
  req = urllib.request.Request(url, headers=headers)
  try:
    with urllib.request.urlopen(req, timeout=15) as resp:
      return json.loads(resp.read().decode("utf-8"))
  except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e


def gcp_metric_to_promql(metric_type: str, value_type: str) -> str:
  """Converts a GCP metric type (<domain>/<path>) to its PromQL equivalent."""
  if "/" not in metric_type:
    return metric_type
  domain, path = metric_type.split("/", 1)
  prom_domain = domain.replace(".", "_")
  prom_path = path.replace(".", "_").replace("/", "_")
  prom_name = f"{prom_domain}:{prom_path}"
  if value_type == "DISTRIBUTION" and not prom_name.endswith("_bucket"):
    prom_name += "_bucket"
  return prom_name


def promql_to_gcp_prefix(promql_metric: str) -> str:
  """Infers a GCP metric domain/prefix from a PromQL metric identifier."""
  if ":" not in promql_metric:
    return promql_metric
  domain_part, path_part = promql_metric.split(":", 1)
  # Strip distribution suffixes for lookup
  for suffix in ("_bucket", "_count", "_sum"):
    if path_part.endswith(suffix):
      path_part = path_part[: -len(suffix)]
      break
  gcp_domain = domain_part.replace("_googleapis_com", ".googleapis.com")
  first_segment = path_part.split("_")[0] if "_" in path_part else path_part
  return f"{gcp_domain}/{first_segment}"


def format_unit_guidance(unit: str) -> str:
  """Returns clear threshold scaling guidance based on the metric unit."""
  if unit == "us":
    return (
        "MICROSECONDS ('us') -> [!] MULTIPLY MILLISECONDS BY 1,000 (e.g., 1s ="
        " 1000000, 100ms = 100000, 1ms = 1000)"
    )
  if unit == "ns":
    return (
        "NANOSECONDS ('ns') -> [!] MULTIPLY MILLISECONDS BY 1,000,000 (e.g., 1s"
        " = 1000000000)"
    )
  if unit == "ms":
    return "Milliseconds ('ms') -> (e.g., 1s = 1000)"
  if unit == "s":
    return "Seconds ('s') -> (e.g., 5 minutes = 300)"
  if unit in ("By", "By/s"):
    return f"Bytes ('{unit}') -> (1 KiB = 1024, 1 MiB = 1048576)"
  if unit in ("1", "10^2.%"):
    return f"Count / Ratio ('{unit}')"
  return f"'{unit}'"


def extract_documented_enums(description: str) -> List[str]:
  """Extracts documented enum values from a label description string."""
  # Match bracketed list e.g. ['success', 'invalid', 'internal']
  bracket_match = re.search(r"\[([^\]]+)\]", description)
  if bracket_match:
    items = re.findall(r"['\"]([^'\"]+)['\"]", bracket_match.group(1))
    if items:
      return items
  # Match parenthetical e.g. (e.g., 'success', 'not_found', 'unavailable')
  quoted = re.findall(r"['\"]([a-zA-Z0-9_\-]+)['\"]", description)
  return list(dict.fromkeys(quoted))


def fetch_resource_descriptor(
    project: str, resource_type: str, token: str
) -> Optional[Dict[str, Any]]:
  """Fetches a monitoredResourceDescriptor from the Cloud Monitoring API."""
  url = (
      f"https://monitoring.googleapis.com/v3/projects/{project}/"
      f"monitoredResourceDescriptors/{resource_type}"
  )
  try:
    return api_get(url, token)
  except RuntimeError:
    return None


def fetch_metric_descriptors(
    project: str,
    token: str,
    resource_type: Optional[str] = None,
    metric_prefix: Optional[str] = None,
) -> List[Dict[str, Any]]:
  """Lists metricDescriptors matching the given resource_type or metric_prefix."""
  filters = []
  if resource_type:
    filters.append(f'resource.type="{resource_type}"')
  if metric_prefix:
    if ":" in metric_prefix:
      metric_prefix = promql_to_gcp_prefix(metric_prefix)
    filters.append(f'metric.type=starts_with("{metric_prefix}")')

  filter_str = " AND ".join(filters)
  params = {"pageSize": "500"}
  if filter_str:
    params["filter"] = filter_str

  query_string = urllib.parse.urlencode(params)
  url = (
      f"https://monitoring.googleapis.com/v3/projects/{project}/"
      f"metricDescriptors?{query_string}"
  )
  data = api_get(url, token)
  return data.get("metricDescriptors", [])


def validate_promql_against_schema(
    promql: str, descriptors: List[Dict[str, Any]]
) -> List[str]:
  """Validates a PromQL expression against discovered metric descriptors."""
  warnings: List[str] = []
  by_prom_name: Dict[str, Dict[str, Any]] = {}
  for d in descriptors:
    mtype = d.get("type", "")
    vtype = d.get("valueType", "")
    pname = gcp_metric_to_promql(mtype, vtype)
    by_prom_name[pname] = d
    # Also register base name without _bucket
    if pname.endswith("_bucket"):
      by_prom_name[pname[:-7]] = d

  # Find all PromQL metric names in the query
  prom_metrics = re.findall(
      r"\b([a-z0-9_]+_googleapis_com:[a-z0-9_]+)\b", promql
  )
  for pm in prom_metrics:
    if pm not in by_prom_name:
      suggestions = [k for k in by_prom_name if pm.split(":")[-1][:8] in k]
      msg = (
          f"[ERROR] PromQL metric '{pm}' does NOT exist in GCP metric"
          " descriptors."
      )
      if suggestions:
        msg += f" Did you mean: {', '.join(sorted(set(suggestions))[:5])}?"
      warnings.append(msg)
      continue

    desc = by_prom_name[pm]
    vtype = desc.get("valueType", "")
    unit = desc.get("unit", "")
    if vtype == "DISTRIBUTION" and not pm.endswith(
        ("_bucket", "_count", "_sum")
    ):
      warnings.append(
          f"[ERROR] Metric '{pm}' has valueType=DISTRIBUTION; in PromQL"
          f" histogram_quantile you must query '{pm}_bucket'."
      )

    # Check threshold magnitude if unit is 'us' or 'ns'
    if unit in ("us", "ns"):
      comp_match = re.search(r"[<>]=?\s*(\d+(?:\.\d+)?)", promql)
      if comp_match:
        val = float(comp_match.group(1))
        if 0 < val < 10000:
          warnings.append(
              f"[WARNING] Metric '{pm}' has unit '{unit}'"
              f" (microseconds/nanoseconds), but threshold is '{val}'. If you"
              " meant milliseconds/seconds, scale accordingly (e.g., 1000ms ="
              " 1000000 us)."
          )

    # Check label matchers
    valid_metric_labels = {
        lbl.get("key", ""): lbl.get("description", "")
        for lbl in desc.get("labels", [])
    }
    # Extract label filters inside { ... } following this metric
    brace_match = re.search(re.escape(pm) + r"\s*\{([^}]+)\}", promql)
    if brace_match:
      matcher_str = brace_match.group(1)
      matchers = re.findall(
          r'([a-zA-Z0-9_]+)\s*(=~|!~|!=|=)\s*"([^"]*)"', matcher_str
      )
      for lkey, op, lval in matchers:
        if lkey in ("project_id", "monitored_resource", "le", "region"):
          continue
        if lkey in valid_metric_labels:
          enums = extract_documented_enums(valid_metric_labels[lkey])
          if enums and op in ("=", "!=") and lval not in enums:
            warnings.append(
                f"[WARNING] Label matcher '{lkey}{op}\"{lval}\"' uses value"
                f" '{lval}', but documented enum values for '{lkey}' are:"
                f" {enums}. Verify casing (e.g., 'success' vs 'OK')."
            )

  return warnings


def main() -> None:
  parser = argparse.ArgumentParser(
      description=(
          "Discovers GCP Metric & Monitored Resource Descriptors and validates"
          " PromQL schema."
      )
  )
  parser.add_argument(
      "--project",
      "-p",
      type=str,
      help="GCP Project ID (defaults to gcloud config project).",
  )
  parser.add_argument(
      "--resource-type",
      "-r",
      type=str,
      help="Monitored resource type (e.g., pubsub_topic, cloudsql_database).",
  )
  parser.add_argument(
      "--metric-prefix",
      "-m",
      type=str,
      help=(
          "Metric type prefix or PromQL name (e.g.,"
          " pubsub.googleapis.com/topic/ or pubsub_googleapis_com:topic_...)."
      ),
  )
  parser.add_argument(
      "--promql",
      "-q",
      type=str,
      help="Optional PromQL query string to validate against the schema.",
  )
  args = parser.parse_args()

  project = args.project or get_default_project()
  if not project:
    print(
        "Error: --project must be specified or configured via gcloud config.",
        file=sys.stderr,
    )
    sys.exit(1)

  if not args.resource_type and not args.metric_prefix and not args.promql:
    parser.error(
        "At least one of --resource-type (-r), --metric-prefix (-m), or"
        " --promql (-q) must be specified."
    )

  token = get_access_token()

  # Infer metric prefix from PromQL if not explicitly provided
  metric_prefix = args.metric_prefix
  if not metric_prefix and args.promql:
    found = re.findall(
        r"\b([a-z0-9_]+_googleapis_com:[a-z0-9_]+)\b", args.promql
    )
    if found:
      metric_prefix = promql_to_gcp_prefix(found[0])

  descriptors = fetch_metric_descriptors(
      project=project,
      token=token,
      resource_type=args.resource_type,
      metric_prefix=metric_prefix,
  )

  print("=" * 80)
  print(f"GCP METRIC & RESOURCE SCHEMA DISCOVERY (Project: {project})")
  print("=" * 80)

  # 1. Discover Monitored Resource Labels
  resource_types = set()
  if args.resource_type:
    resource_types.add(args.resource_type)
  for d in descriptors:
    for rt in d.get("monitoredResourceTypes", []):
      resource_types.add(rt)

  if resource_types:
    print(
        "\n[1] MONITORED RESOURCE TYPES & GROUPING LABELS (for 'sum by (...)')"
    )
    print("-" * 80)
    for rt in sorted(resource_types):
      rdesc = fetch_resource_descriptor(project, rt, token)
      if rdesc:
        rlabels = [lbl.get("key", "") for lbl in rdesc.get("labels", [])]
        print(f"  * Resource Type : {rt}")
        print(f"    Grouping Keys : {', '.join(rlabels)}")
      else:
        print(f"  * Resource Type : {rt}")

  # 2. Print Metric Descriptors Table
  print(f"\n[2] DISCOVERED METRIC DESCRIPTORS ({len(descriptors)} matches)")
  print("-" * 80)
  for d in descriptors:
    mtype = d.get("type", "")
    vtype = d.get("valueType", "")
    mkind = d.get("metricKind", "")
    unit = d.get("unit", "1")
    prom_name = gcp_metric_to_promql(mtype, vtype)
    print(f"  * GCP Metric Type : {mtype}")
    print(f"    PromQL Name     : {prom_name}")
    print(f"    Kind / Type     : {mkind} / {vtype}")
    print(f"    Unit Guidance   : {format_unit_guidance(unit)}")
    labels = d.get("labels", [])
    if labels:
      print("    Metric Labels   :")
      for lbl in labels:
        lkey = lbl.get("key", "")
        ldesc = lbl.get("description", "")
        enums = extract_documented_enums(ldesc)
        enum_str = f" [Documented Enums: {enums}]" if enums else ""
        print(f"      - {lkey}: {ldesc}{enum_str}")
    print()

  # 3. Validate PromQL Query if provided
  if args.promql:
    print("[3] PROMQL SCHEMA & SEMANTIC VALIDATION")
    print("-" * 80)
    print(f"  Query: {args.promql.strip()}\n")
    warnings = validate_promql_against_schema(args.promql, descriptors)
    if warnings:
      for w in warnings:
        print(f"  {w}")
      sys.exit(1)
    else:
      print(
          "  [OK] PromQL metric names, units, and label matchers verified"
          " against live GCP schema!"
      )

  print("=" * 80)


if __name__ == "__main__":
  main()
