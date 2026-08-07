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

"""Traffic metrics analyzer for Agent Platform agents (using OpenTelemetry).

Computes zero-ratio, variance ratio, and 1-week autocorrelation on a 14-day
metrics time series (at 5-minute intervals) and classifies the traffic pattern
to recommend the optimal dynamic PromQL alerting threshold strategy.
"""

import argparse
import json
import math
import statistics
import sys
import time

from google.auth import exceptions as auth_exceptions
from google.cloud import monitoring_v3

# Number of 5-minute data points in a 7-day weekly window
# (12 points/hour * 24 hours/day * 7 days/week)
_POINTS_PER_WEEK = 2016

# Supported metric types and their corresponding resource labels.
_SUPPORTED_METRIC_TYPE_LABEL = {
    "workload.googleapis.com/gen_ai.invoke_agent.duration": (
        "metric.labels.gen_ai_agent_name"
    ),
    "workload.googleapis.com/gen_ai.client.token.usage": (
        "resource.labels.namespace"
    ),
}

# Supported metric types and their corresponding aligners.
_SUPPORTED_METRIC_TYPE_ALIGNER = {
    "workload.googleapis.com/gen_ai.invoke_agent.duration": (
        monitoring_v3.Aggregation.Aligner.ALIGN_DELTA
    ),
    "workload.googleapis.com/gen_ai.client.token.usage": (
        monitoring_v3.Aggregation.Aligner.ALIGN_DELTA
    ),
}

# Supported metric types and their filters for live queries.
_SUPPORTED_METRIC_TYPE_FILTERS = {
    "workload.googleapis.com/gen_ai.invoke_agent.duration": [],
    "workload.googleapis.com/gen_ai.client.token.usage": [],
}


class CredentialsMissingError(Exception):
  """Raised when Google Cloud credentials are not found."""

  pass


def compute_metrics_and_classify(values: list[float]) -> dict[str, float | str]:
  """Computes statistical metrics and classifies the traffic profile.

  Args:
      values: A list of floats representing the 5-minute rate telemetry. Should
        be at least 4032 points (14 days).

  Returns:
      A dictionary with statistical metrics and the classification profile.

  Raises:
      ValueError: If values contains fewer than 4032 points (14 days).
  """
  required_points = 2 * _POINTS_PER_WEEK
  if len(values) < required_points:
    raise ValueError(
        f"Insufficient data points: expected at least {required_points} (14"
        f" days at 5m interval), got {len(values)}"
    )

  # We focus on the last 7 days (latest weekly points) and previous 7 days
  # (weekly points before that)
  last_7_days = values[-_POINTS_PER_WEEK:]
  prev_7_days = values[-required_points:-_POINTS_PER_WEEK]

  # 1. Zero Ratio: proportion of 5m intervals with rate <= 0.01 in the last
  # 7 days
  zero_ratio = sum(x <= 0.01 for x in last_7_days) / _POINTS_PER_WEEK

  # 2. Mean and Standard Deviation of the last 7 days
  mean_last = statistics.mean(last_7_days)
  stddev_last = statistics.pstdev(last_7_days)

  variance_ratio = stddev_last / mean_last if mean_last > 0.0001 else 0.0

  # 3. Autocorrelation at 1-week lag
  mean_prev = statistics.mean(prev_7_days)
  stddev_prev = statistics.pstdev(prev_7_days)

  if stddev_last > 0.0001 and stddev_prev > 0.0001:
    covariance = (
        sum(
            (x - mean_last) * (y - mean_prev)
            for x, y in zip(last_7_days, prev_7_days)
        )
        / _POINTS_PER_WEEK
    )
    autocorr_1w = covariance / (stddev_last * stddev_prev)
  else:
    autocorr_1w = 0.0

  # Decision tree classification
  if mean_last == 0.0 and zero_ratio == 1.0:
    profile = "New Agent / No Traffic"
    algorithm = "Short-Window Z-Score (1h baseline)"
    rationale = (
        "No historical traffic observed. Defaulting to Short-Window Z-Score"
        " (1h baseline) dynamic thresholding to ensure quick activation"
        " (requires 1 hour of traffic history)."
    )
  elif variance_ratio > 2.0:
    profile = "Bursty / Inconsistent"
    algorithm = "Moving Averages"
    rationale = (
        f"Variance ratio is high ({variance_ratio:.2f}), indicating volatile"
        " bursty peaks. Moving averages dynamic baseline thresholds are"
        " recommended to smooth out short-term fluctuations and prevent false"
        " pages."
    )
  elif autocorr_1w > 0.75 and variance_ratio <= 2.0:
    profile = "Seasonal / Cyclical"
    algorithm = "Seasonal Decomposition (average 1w and 1d)"
    rationale = (
        f"Auto-correlation at 1w lag is high ({autocorr_1w:.2f}) with stable"
        f" variance ratio ({variance_ratio:.2f}). Comparing against the average"
        " of 1w and 1d offsets mitigates holiday false positives and prevents"
        " diurnal false alerts during off-peak periods."
    )
  else:
    profile = "Steady / Consistent"
    algorithm = "1w Z-Score Baseline"
    rationale = (
        "Stable regular traffic pattern with low variance ratio"
        f" ({variance_ratio:.2f}) and moderate/low autocorrelation"
        f" ({autocorr_1w:.2f}). 1w Z-Score baseline is ideal."
    )

  return {
      "zero_ratio": round(zero_ratio, 4),
      "variance_ratio": round(variance_ratio, 4),
      "autocorr_1w": round(autocorr_1w, 4),
      "mean": round(mean_last, 4),
      "stddev": round(stddev_last, 4),
      "profile": profile,
      "recommended_algorithm": algorithm,
      "rationale": rationale,
  }


def align_to_grid(
    points: list[tuple[float, float]],
    end_time: float,
    num_points: int = 4032,
    interval_sec: int = 300,
) -> list[float]:
  """Aligns sparse telemetry points to a uniform time grid of fixed size.

  We anchor the grid at end_time aligned to interval_sec and look backward.

  Args:
      points: A list of tuples (timestamp, value).
      end_time: The end timestamp of the grid window.
      num_points: The exact number of points in the target grid.
      interval_sec: The grid interval in seconds.

  Returns:
      A list of floats representing the aligned values in order of time.
  """
  aligned_end = math.floor(end_time / interval_sec) * interval_sec
  aligned_start = aligned_end - num_points * interval_sec

  grid = [0.0] * num_points

  for ts, val in points:
    rounded_ts = round(ts / interval_sec) * interval_sec
    idx = int((rounded_ts - aligned_start) / interval_sec) - 1
    if 0 <= idx < num_points:
      grid[idx] += val

  return grid


def query_live_metrics(
    project_id: str,
    metric_type: str,
    engine_id: str,
) -> list[float]:
  """Queries live metrics (e.g., OTel latency or token usage) for 14 days.

  Args:
      project_id: The GCP project ID.
      metric_type: The metric type to query.
      engine_id: The agent identifier value.

  Returns:
      A list of 4032 floats representing the 5m rate telemetry aligned to grid.

  Raises:
      CredentialsMissingError: If GCP credentials are not found.
  """
  try:
    client = monitoring_v3.MetricServiceClient()
    name = f"projects/{project_id}"

    now = time.time()
    seconds_per_day = 24 * 3600
    start_time = now - 14 * seconds_per_day

    interval = monitoring_v3.TimeInterval({
        "end_time": {"seconds": int(now)},
        "start_time": {"seconds": int(start_time)},
    })

    filter_str = (
        f'metric.type = "{metric_type}" AND'
        f" {_SUPPORTED_METRIC_TYPE_LABEL[metric_type]} ="
        f' "{engine_id}"'
    )
    for metric_filter in _SUPPORTED_METRIC_TYPE_FILTERS[metric_type]:
      filter_str += f" AND {metric_filter}"

    results = client.list_time_series(
        request={
            "name": name,
            "filter": filter_str,
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            "aggregation": {
                "alignment_period": {"seconds": 300},
                "per_series_aligner": _SUPPORTED_METRIC_TYPE_ALIGNER[
                    metric_type
                ],
                "cross_series_reducer": (
                    monitoring_v3.Aggregation.Reducer.REDUCE_SUM
                ),
                "group_by_fields": [
                    _SUPPORTED_METRIC_TYPE_LABEL[metric_type]
                ],
            },
        }
    )
  except auth_exceptions.DefaultCredentialsError as e:
    raise CredentialsMissingError(
        "No valid Google Cloud credentials found. Please run 'gcloud auth"
        " application-default login' to authenticate your local environment."
    ) from e

  points = []
  for series in results:
    for point in series.points:
      st = point.interval.start_time
      ts = (
          st.timestamp()
          if hasattr(st, "timestamp")
          else st.ToDatetime().timestamp()
      )
      pb = getattr(point.value, "_pb", point.value)
      val_type = pb.WhichOneof("value")
      if val_type == "distribution_value":
        # Calculate total tokens consumed across all buckets in the interval
        val = float(
            point.value.distribution_value.mean
            * point.value.distribution_value.count
        )
      elif val_type == "int64_value":
        val = float(point.value.int64_value)
      else:
        val = float(point.value.double_value)
      points.append((
          ts,
          val,
      ))

  if not points:
    # No traffic detected at all. Return a 14-day grid filled with 0.0.
    return [0.0] * (2 * _POINTS_PER_WEEK)

  # Align sparse points to the 14-day 5-minute grid
  return align_to_grid(points, now, num_points=2 * _POINTS_PER_WEEK)


def main():
  parser = argparse.ArgumentParser(
      description=(
          "Analyze 14-day traffic metrics to select dynamic thresholding"
          " algorithm."
      )
  )
  parser.add_argument(
      "--metric-type",
      required=True,
      type=str,
      help="The metric type to query.",
  )
  parser.add_argument(
      "--metrics-file",
      type=str,
      help="Path to JSON file containing list of numbers. Use '-' for stdin.",
  )
  parser.add_argument(
      "--live",
      action="store_true",
      help="Force live GCP metrics query validation check.",
  )
  parser.add_argument(
      "--project-id",
      type=str,
      help="GCP project ID (required for live queries).",
  )
  parser.add_argument(
      "--reasoning-engine-id",
      type=str,
      help=(
          "Agent Identifier (e.g., gen_ai_agent_name or namespace) "
          "required for live queries."
      ),
  )
  args = parser.parse_args()

  data = None

  if args.metric_type not in _SUPPORTED_METRIC_TYPE_LABEL:
    print(
        f"Error: Metric type {args.metric_type} is not supported.",
        file=sys.stderr,
    )
    sys.exit(1)

  if args.live:
    if not args.project_id or not args.reasoning_engine_id:
      print(
          "Error: Live GCP queries require --project-id and"
          " --reasoning-engine-id to be specified.",
          file=sys.stderr,
      )
      sys.exit(1)

    try:
      data = query_live_metrics(
          args.project_id, args.metric_type, args.reasoning_engine_id
      )
    except CredentialsMissingError as e:
      print(f"Error: {e}", file=sys.stderr)
      sys.exit(1)
    except Exception as e:
      print(f"Error executing live query: {e}", file=sys.stderr)
      sys.exit(1)

  else:
    # File/Stdin input mode
    if not args.metrics_file and sys.stdin.isatty():
      print(
          "Error: Must specify --metrics-file or pipe metrics data to stdin"
          " when not using --live.",
          file=sys.stderr,
      )
      sys.exit(1)

    try:
      if args.metrics_file == "-" or not args.metrics_file:
        data = json.load(sys.stdin)
      else:
        with open(args.metrics_file, "r") as f:
          data = json.load(f)
    except Exception as e:
      print(f"Error reading metrics data: {e}", file=sys.stderr)
      sys.exit(1)

  if not data or not isinstance(data, list):
    print(
        "Error: Metrics data must be a JSON list of numbers or parsed"
        " successfully from a source",
        file=sys.stderr,
    )
    sys.exit(1)

  try:
    results = compute_metrics_and_classify(data)
    print(json.dumps(results, indent=2))
  except ValueError as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
