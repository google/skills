#!/usr/bin/env python3
import argparse
import json
import sys


def main():
  parser = argparse.ArgumentParser(
      description=(
          "Search the loaded DB resources for matching frameworks and cloud"
          " controls."
      )
  )
  parser.add_argument(
      "--resources_json", required=True, help="Path to loaded_db_resources.json"
  )
  parser.add_argument(
      "--query", required=True, help="Keyword to search for (case-insensitive)"
  )
  args = parser.parse_args()

  try:
    with open(args.resources_json, "r") as f:
      data = json.load(f)
  except PermissionError as e:
    print(f"ERROR: PERMISSION_DENIED: {e}", file=sys.stderr)
    sys.exit(1)
  except Exception as e:
    print(f"ERROR: Could not read {args.resources_json}: {e}", file=sys.stderr)
    sys.exit(1)

  query = args.query.lower()

  print(f"--- Search Results for '{args.query}' ---")

  frameworks = data.get("frameworks", {})
  matched_fws = []
  for fw_id, fw in frameworks.items():
    search_text = (
        f"{fw_id} {fw.get('displayName', '')} {fw.get('description', '')}"
        .lower()
    )
    if query in search_text:
      matched_fws.append((fw_id, fw.get("displayName", "")))

  print(f"\nFrameworks found ({len(matched_fws)}):")
  for fw_id, name in matched_fws:
    print(f" - ID: {fw_id} | Name: {name}")

  cloud_controls = data.get("cloud_controls", {})
  matched_ccs = []
  for cc_id, cc in cloud_controls.items():
    search_text = (
        f"{cc_id} {cc.get('displayName', '')} {cc.get('description', '')}"
        .lower()
    )
    if query in search_text:
      matched_ccs.append((cc_id, cc.get("displayName", "")))

  print(f"\nCloud Controls found ({len(matched_ccs)}):")
  for cc_id, name in matched_ccs:
    print(f" - ID: {cc_id} | Name: {name}")


if __name__ == "__main__":
  main()
