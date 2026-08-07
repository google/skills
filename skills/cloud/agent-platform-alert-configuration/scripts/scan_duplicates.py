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

"""Scans a directory of Terraform files to detect duplicate alert policy targets."""

import argparse
import glob
import json
import os
from config_utils import extract_alert_policies

def validate_directory_tf_files(
    directory: str, expected_engine_var: str | None = None
) -> dict:
  """Scans and validates all *.tf files in a given directory for duplicates."""
  tf_files = glob.glob(os.path.join(directory, "*.tf"))
  all_errors = []
  all_policies = []
  duplicates = []

  target_map = {}

  for filepath in tf_files:
    filename = os.path.basename(filepath)
    try:
      with open(filepath, "r") as f:
        content = f.read()
    except Exception as e:
      all_errors.append(f"File error in '{filename}': {e}")
      continue

    policies = extract_alert_policies(content)
    for policy in policies:
      policy["filename"] = filename
      all_policies.append(policy)

      engine_key = (
          policy["engine_ids"][0]
          if policy["engine_ids"]
          else expected_engine_var or "default"
      )
      key = (engine_key, policy["signal_type"])

      if key not in target_map:
        target_map[key] = []
      target_map[key].append(policy)

  for (engine, signal_type), matches in target_map.items():
    if len(matches) > 1 and signal_type != "unknown":
      duplicates.append({
          "engine_id": engine,
          "signal_type": signal_type,
          "policies": [
              {
                  "filename": p["filename"],
                  "resource_name": p["resource_name"],
                  "display_name": p["display_name"],
              }
              for p in matches
          ],
      })

  for dup in duplicates:
    policy_list = ", ".join(
        f"'{p['resource_name']}' in '{p['filename']}'" for p in dup["policies"]
    )
    all_errors.append(
        "Duplicate Target Error: Multiple alert policies are targeting the"
        f" same engine '{dup['engine_id']}' and signal '{dup['signal_type']}':"
        f" [{policy_list}]. Please apply the in-place upgrade protocol instead"
        " of appending new blocks!"
    )

  return {
      "valid": len(all_errors) == 0,
      "errors": all_errors,
      "policies_scanned_count": len(all_policies),
      "duplicates_found": duplicates,
  }


def main():
  parser = argparse.ArgumentParser(
      description="Scans a directory of Terraform files to detect duplicate alert policy targets."
  )
  parser.add_argument(
      "directory",
      type=str,
      nargs="?",
      default=".",
      help="Directory containing *.tf files to scan.",
  )
  parser.add_argument(
      "--engine-var",
      type=str,
      default="${var.gen_ai_agent_name}",
      help="The expected variable or literal for the agent identifier.",
  )
  args = parser.parse_args()

  results = validate_directory_tf_files(args.directory, args.engine_var)
  print(json.dumps(results, indent=2))
  if not results["valid"]:
    sys.exit(1)


if __name__ == "__main__":
  main()
