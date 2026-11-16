"""Estimate the hourly deployment cost for a Model Garden deployment.

Sandbox-executable Python script that computes an hourly $ estimate for a
`gcloud ai model-garden models deploy` invocation, given `--machine-type`.

Prices are hardcoded from live `CostEstimationService.CalculateEstimate`
RPC responses (autopush blade, us-central1) captured on LAST_UPDATED.
Machine type → GPU count → hourly $ is a fixed mapping in Model Garden's
`deployment_machine_specs` config, so each machine_type has exactly one
valid pairing and one price. Actual bill may differ due to region,
discounts, reservations, or subsequent SKU repricing.

This is a stopgap; the long-term plan is to have the root agent call
`CostEstimationService.CalculateEstimate` directly (which resolves live
SKUs via Cloud Billing) and pass the result into the sandbox. See design
doc referenced in the CL description.
"""

import argparse
import datetime
import sys

LAST_UPDATED = "2026-07-08"

# Threshold beyond which LAST_UPDATED is treated as stale enough to warn
# the caller loudly. `SKILL.md` §3.2 requires the agent to present the
# script's estimate to the user, so a silently-stale table would quote
# outdated prices with the same confidence as fresh ones. 90 days is a
# quarter — long enough to survive a refresh gap, short enough to catch a
# forgotten refresh before it becomes materially wrong.
_STALENESS_THRESHOLD_DAYS = 90

# Machine type → (accelerator_type, accelerator_count, hourly_$_us_central1)
# in USD. Verified against CostEstimationService.CalculateEstimate. Every
# entry ships as a fixed bundle from Model Garden's deployment_machine_specs;
# users cannot override the accelerator pairing per machine type.
_MACHINE_SPECS = {
    # A3
    "a3-ultragpu-8g": ("NVIDIA_H200_141GB", 8, 96.0156),
    "a3-megagpu-8g": ("NVIDIA_H100_MEGA_80GB", 8, 106.6547),
    "a3-highgpu-8g": ("NVIDIA_H100_80GB", 8, 101.0074),
    "a3-highgpu-4g": ("NVIDIA_H100_80GB", 4, 50.5037),
    "a3-highgpu-2g": ("NVIDIA_H100_80GB", 2, 25.2518),
    "a3-highgpu-1g": ("NVIDIA_H100_80GB", 1, 12.6259),
    "a3-edgegpu-8g": ("NVIDIA_H100_80GB", 8, 101.0074),
    # A2 Ultra (A100 80GB)
    "a2-ultragpu-8g": ("NVIDIA_A100_80GB", 8, 46.2548),
    "a2-ultragpu-4g": ("NVIDIA_A100_80GB", 4, 23.1274),
    "a2-ultragpu-2g": ("NVIDIA_A100_80GB", 2, 11.5637),
    "a2-ultragpu-1g": ("NVIDIA_A100_80GB", 1, 5.7818),
    # A2 Standard (Tesla A100)
    "a2-megagpu-16g": ("NVIDIA_TESLA_A100", 16, 64.1021),
    "a2-highgpu-8g": ("NVIDIA_TESLA_A100", 8, 33.7960),
    "a2-highgpu-4g": ("NVIDIA_TESLA_A100", 4, 16.8980),
    "a2-highgpu-2g": ("NVIDIA_TESLA_A100", 2, 8.4490),
    "a2-highgpu-1g": ("NVIDIA_TESLA_A100", 1, 4.2245),
    # G4 (RTX Pro 6000)
    "g4-standard-384": ("NVIDIA_RTX_PRO_6000", 8, 41.4007),
    "g4-standard-192": ("NVIDIA_RTX_PRO_6000", 4, 20.7004),
    "g4-standard-96": ("NVIDIA_RTX_PRO_6000", 2, 10.3502),
    "g4-standard-48": ("NVIDIA_RTX_PRO_6000", 1, 5.1751),
    # G2 (L4)
    "g2-standard-96": ("NVIDIA_L4", 8, 9.2055),
    "g2-standard-48": ("NVIDIA_L4", 4, 4.6028),
    "g2-standard-32": ("NVIDIA_L4", 1, 1.9951),
    "g2-standard-24": ("NVIDIA_L4", 2, 2.3014),
    "g2-standard-16": ("NVIDIA_L4", 1, 1.3196),
    "g2-standard-12": ("NVIDIA_L4", 1, 1.1507),
    "g2-standard-8": ("NVIDIA_L4", 1, 0.9818),
    "g2-standard-4": ("NVIDIA_L4", 1, 0.8129),
}


def calculate_hourly_cost(machine_type: str) -> tuple[str, int, float]:
  """Returns the (accelerator_type, count, hourly_$) for a machine type.

  Args:
    machine_type: e.g. "g2-standard-48".

  Returns:
    Tuple of (accelerator_type, accelerator_count, hourly_$_us_central1).

  Raises:
    KeyError: machine_type not in the price table.
  """
  return _MACHINE_SPECS[machine_type]


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Estimate hourly deployment cost for a Model Garden deploy."
  )
  # No `choices=` here on purpose. `_MACHINE_SPECS` is a hand-maintained
  # price snapshot and Model Garden's `deployment_machine_specs` catalog
  # drifts independently — a machine_type present in the catalog but
  # absent here is a routine, expected state (e.g. A4/B200 today, pending
  # a snapshot refresh). `argparse` with `choices=` would reject it with
  # an unactionable usage dump; the explicit check below reports it in a
  # form the caller can act on and lets the SKILL.md fallback (§3(c),
  # pricing page URL) fire when the machine is unknown to this table.
  parser.add_argument(
      "--machine-type",
      required=True,
      help="Machine type, e.g. g2-standard-48.",
  )
  parser.add_argument(
      "--hours",
      required=False,
      type=float,
      default=1.0,
      help="Duration in hours for the total. Defaults to 1.",
  )
  args = parser.parse_args()

  if args.machine_type not in _MACHINE_SPECS:
    supported = ", ".join(sorted(_MACHINE_SPECS.keys()))
    print(
        f"Error: unknown machine type: {args.machine_type}. This table"
        f" covers: {supported}. If the machine is in Model Garden's catalog"
        " but not here, fall back to the pricing page (see SKILL.md §3(c)).",
        file=sys.stderr,
    )
    sys.exit(1)

  accel_type, accel_count, hourly = calculate_hourly_cost(args.machine_type)

  # Warn loudly when the snapshot is older than the staleness threshold, so
  # the agent (per SKILL.md §3.2) can relay this to the user instead of
  # quoting outdated numbers with false confidence.
  age_days = (
      datetime.date.today() - datetime.date.fromisoformat(LAST_UPDATED)
  ).days
  if age_days > _STALENESS_THRESHOLD_DAYS:
    print(
        f"WARNING: price snapshot is {age_days} days old"
        f" (>{_STALENESS_THRESHOLD_DAYS} days threshold;"
        f" LAST_UPDATED={LAST_UPDATED}). Refresh LAST_UPDATED and"
        " _MACHINE_SPECS before quoting these numbers.",
        file=sys.stderr,
    )

  total = hourly * args.hours
  print(f"Machine type:       {args.machine_type}")
  print(f"Accelerator:        {accel_count} x {accel_type}")
  print(f"Hourly estimate:    ${hourly:.4f}/hr")
  print(f"Duration:           {args.hours} hr")
  print(f"Total estimate:     ${total:.2f}")
  print()
  print(f"NOTE: List price in us-central1 as of {LAST_UPDATED}, verified")
  print("against CostEstimationService. Actual bill may differ due to")
  print("region, discounts, or reservations.")
