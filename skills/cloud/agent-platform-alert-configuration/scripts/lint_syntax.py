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

"""Lints a single specific HCL file for PromQL syntax and duration compliance."""

import argparse
import sys
from config_utils import extract_alert_policies, lint_query, validate_policy_duration

def main():
  parser = argparse.ArgumentParser(
      description="Lints a single specific HCL file for PromQL syntax and duration compliance."
  )
  parser.add_argument(
      "file",
      type=str,
      help="Path to the HCL file to lint.",
  )
  args = parser.parse_args()

  try:
    with open(args.file, "r") as f:
      content = f.read()
    policies = extract_alert_policies(content)
    errors = []
    for p in policies:
      if not p.get("is_sql"):
        for q in p["queries"]:
          errors.extend(lint_query(q))
        errors.extend(validate_policy_duration(p))
    if errors:
      print(f"Validation failed for '{args.file}':", file=sys.stderr)
      for err in errors:
        print(f"  - {err}", file=sys.stderr)
      sys.exit(1)
    else:
      print(f"Validation passed for '{args.file}'!")
      sys.exit(0)
  except Exception as e:
    print(f"Error reading file '{args.file}': {e}", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
  main()
