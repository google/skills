#!/usr/bin/env python3
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

"""Shared utility functions for alert configuration validation."""

import re

def check_balanced_chars(
    query: str, open_char: str, close_char: str
) -> str | None:
  """Checks if parenthesis or braces are balanced."""
  count = 0
  for i, char in enumerate(query):
    if char == open_char:
      count += 1
    elif char == close_char:
      count -= 1
      if count < 0:
        return f"Unbalanced '{close_char}' at position {i}"
  if count != 0:
    return f"Unbalanced '{open_char}' (net count: {count})"
  return None


def parse_promql_duration(duration_str: str) -> float | None:
  """Converts PromQL duration string to hours."""
  match = re.match(r"^(\d+)([smhdw])$", duration_str)
  if not match:
    return None
  val, unit = match.groups()
  val = int(val)
  if unit == "s":
    return val / 3600
  if unit == "m":
    return val / 60
  if unit == "h":
    return val
  if unit == "d":
    return val * 24
  if unit == "w":
    return val * 24 * 7
  return None


def get_max_lookback_hours(query: str) -> float:
  """Calculates the maximum lookback in hours from windows and offsets."""
  max_hours = 0

  # Check windows and subqueries
  window_matches = re.finditer(r"\[([^\]]+)\]", query)
  for match in window_matches:
    window_str = match.group(1)
    range_str = window_str.split(":")[0]
    hours = parse_promql_duration(range_str)
    if hours and hours > max_hours:
      max_hours = hours

  # Check offsets
  offset_matches = re.finditer(r"\boffset\s+(\S+)", query)
  for match in offset_matches:
    offset_str = match.group(1)
    hours = parse_promql_duration(offset_str)
    if hours and hours > max_hours:
      max_hours = hours

  return max_hours


def validate_policy_duration(policy: dict) -> list[str]:
  """Validates duration based on lookback window."""
  errors = []
  max_lookback = 0
  for query in policy["queries"]:
    lookback = get_max_lookback_hours(query)
    if lookback > max_lookback:
      max_lookback = lookback

  quality_metrics = [
      "final_response_quality_v1",
      "tool_use_quality_v1",
      "hallucination_v1",
  ]

  if policy["signal_type"] in quality_metrics:
    if policy["duration"] != "300s":
      errors.append(
          "Duration Error: Quality alerts MUST set duration='300s'."
          f" Found duration='{policy['duration']}'."
      )
  elif max_lookback > 25:
    if policy["duration"] is not None:
      errors.append(
          "Duration Error: Long-lookback alerts (>25h) must NOT set a"
          f" duration. Found duration='{policy['duration']}' for lookback of"
          f" {max_lookback}h."
      )
  elif max_lookback > 0:  # It's a short-lookback PromQL alert
    if policy["duration"] != "300s":
      errors.append(
          "Duration Error: Short-lookback alerts (<=25h) MUST set"
          f" duration='300s'. Found duration='{policy['duration']}'."
      )
  return errors


def lint_query(query: str) -> list[str]:
  """Runs a suite of sanity lint checks on a PromQL query."""
  errors = []

  # 1. Balanced parentheses
  paren_err = check_balanced_chars(query, "(", ")")
  if paren_err:
    errors.append(f"Parentheses error: {paren_err}")

  # 2. Balanced curly braces
  brace_err = check_balanced_chars(query, "{", "}")
  if brace_err:
    errors.append(f"Curly braces error: {brace_err}")

  # 3. Time window validations (e.g., [5m], [1w:5m], [3d], [1h])
  window_matches = re.finditer(r"\[([^\]]+)\]", query)
  for match in window_matches:
    window_str = match.group(1)
    if not re.match(r"^\d+[smhdw](:(\d+[smhdw])?)?$", window_str):
      errors.append(
          "Invalid Prometheus time window/subquery interval:"
          f" '[{window_str}]' at position {match.start()}"
      )

  # 4. Lookback offset range validation (e.g. offset 1w, offset 1d)
  offset_matches = re.finditer(r"\boffset\s+(\S+)", query)
  for match in offset_matches:
    offset_str = match.group(1)
    if not re.match(r"^\d+[smhdw]$", offset_str):
      errors.append(
          f"Invalid lookback offset format: 'offset {offset_str}' at position"
          f" {match.start()}"
      )

  # 5. Ensure the query references a supported group in a label filter
  # or grouping aggregation.
  supported_groups = ["namespace", "gen_ai_agent_name"]
  search_regex = (
      r"\b(by|without)\s*\([^)]*\b("
      + "|".join(supported_groups)
      + r")\b[^)]*\)"
  )
  has_group = bool(re.search(search_regex, query))

  has_filter = False
  brace_matches = re.finditer(r"\{([^}]+)\}", query)
  for match in brace_matches:
    for group in supported_groups:
      if group in match.group(1):
        has_filter = True
        break
    if has_filter:
      break

  if not (has_group or has_filter):
    errors.append(
        "Query is missing agent identifier reference. It must either group"
        " by it using aggregations (e.g., 'by (gen_ai_agent_name)') or filter"
        " on it (e.g., '{gen_ai_agent_name=\"...\"}')."
    )

  return errors


def extract_alert_policies(hcl_content: str) -> list[dict]:
  """Extracts resource 'google_monitoring_alert_policy' blocks and metadata."""
  policies = []
  pattern = re.compile(
      r'resource\s+"google_monitoring_alert_policy"\s+"([^"]+)"\s*\{'
  )

  for match in pattern.finditer(hcl_content):
    resource_name = match.group(1)
    start_pos = match.start()

    brace_count = 0
    end_pos = -1
    in_string = False
    escape = False

    for i in range(match.end() - 1, len(hcl_content)):
      char = hcl_content[i]
      if escape:
        escape = False
        continue
      if char == "\\":
        escape = True
        continue
      if char == '"':
        in_string = not in_string
        continue
      if not in_string:
        if char == "{":
          brace_count += 1
        elif char == "}":
          brace_count -= 1
          if brace_count == 0:
            end_pos = i + 1
            break

    if end_pos == -1:
      continue

    block_content = hcl_content[start_pos:end_pos]

    # Extract display_name
    display_name_match = re.search(
        r'display_name\s*=\s*"([^"]+)"', block_content
    )
    display_name = display_name_match.group(1) if display_name_match else ""

    # Extract duration
    duration_match = re.search(r'duration\s*=\s*"([^"]+)"', block_content)
    duration = duration_match.group(1) if duration_match else None

    # Extract PromQL queries
    queries = [
        q.group(1)
        for q in re.finditer(
            r"query\s*=\s*<<-?EOT\n(.*?)\n\s*EOT",
            block_content,
            re.DOTALL,
        )
    ]
    if not queries:
      for match in re.finditer(
          r"query\s*=\s*\"((?:[^\"\\]|\\[\s\S])*)\"", block_content
      ):
        raw_query = match.group(1)
        clean_query = re.sub(r"\\+\"", '"', raw_query).replace("\\\\", "\\")
        queries.append(clean_query)

    # Extract threshold filters
    filters = []
    filter_matches = re.finditer(
        r'filter\s*=\s*"((?:[^"\\]|\\.)*)"', block_content
    )
    for f_match in filter_matches:
      filters.append(f_match.group(1))

    # Infer signal type
    signal_type = "unknown"
    res_lower, disp_lower = resource_name.lower(), display_name.lower()
    rules = [
        ("latency", "latency", "latency"),
        ("slo_burn_rate_fast", "fast", "slo_fast"),
        ("slo_burn_rate_slow", "slow", "slo_slow"),
    ]
    for res_pat, disp_pat, sig in rules:
      if res_pat in res_lower or disp_pat in disp_lower:
        signal_type = sig
        break
    else:
      # Check threshold filters for quality metric name
      for flt in filters:
        metric_match = re.search(
            r"metric\.labels\.evaluation_metric_name"
            r"\s*=\s*\\*\"([^\"\\]+)\\*\"",
            flt,
        )
        if metric_match:
          signal_type = metric_match.group(1)
          break

    engine_ids = []
    for query in queries:
      for engine_id in re.findall(
          r'(?:reasoning_engine_id|gen_ai_agent_name|namespace)'
          r'\s*=\s*"([^"]+)"',
          query,
      ):
        if engine_id not in engine_ids:
          engine_ids.append(engine_id)
    for flt in filters:
      id_matches = re.findall(
          r'(?:reasoning_engine_id|gen_ai_agent_name|namespace)'
          r'\s*=\s*\\*"([^"\\]+)\\*"',
          flt,
      )
      for engine_id in id_matches:
        if engine_id not in engine_ids:
          engine_ids.append(engine_id)
      resource_matches = re.findall(r"reasoningEngines/([0-9]+)", flt)
      for engine_id in resource_matches:
        if engine_id not in engine_ids:
          engine_ids.append(engine_id)

    policies.append({
        "resource_name": resource_name,
        "display_name": display_name,
        "signal_type": signal_type,
        "engine_ids": engine_ids,
        "queries": queries,
        "filters": filters,
        "duration": duration,
        "is_sql": "condition_sql" in block_content,
        "start_pos": start_pos,
        "end_pos": end_pos,
        "block_content": block_content,
    })

  return policies
