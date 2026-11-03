#!/usr/bin/env python3
"""Generic PromQL Linter for Alerting Policies.

Checks for balanced brackets, valid time windows, and basic syntax issues.
"""

import argparse
import re
import sys


def check_balanced_chars(query, open_char, close_char):
  """Checks if parentheses or braces are balanced."""
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


def lint_query(query):
  """Runs generic sanity checks on a PromQL query."""
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
          f"Invalid Prometheus time window/subquery interval: '[{window_str}]'"
      )

  # 4. Lookback offset range validation (e.g. offset 1w, offset 1d)
  offset_matches = re.finditer(r"\boffset\s+(\S+)", query)
  for match in offset_matches:
    offset_str = match.group(1)
    if not re.match(r"^\d+[smhdw]$", offset_str):
      errors.append(f"Invalid lookback offset format: 'offset {offset_str}'")

  return errors


def main():
  parser = argparse.ArgumentParser(description="Lints a PromQL query string.")
  parser.add_argument(
      "query", nargs="?", type=str, help="The PromQL query to lint."
  )
  parser.add_argument(
      "--query",
      dest="query_flag",
      type=str,
      help="The PromQL query to lint (optional flag form).",
  )
  args = parser.parse_args()
  query_str = args.query_flag if args.query_flag is not None else args.query
  if not query_str:
    parser.error(
        "A PromQL query string must be provided positionally or via --query."
    )

  errors = lint_query(query_str)
  if errors:
    print("Linting failed:", file=sys.stderr)
    for err in errors:
      print(f"  - {err}", file=sys.stderr)
    sys.exit(1)
  else:
    print("Linting passed!")
    sys.exit(0)


if __name__ == "__main__":
  main()
