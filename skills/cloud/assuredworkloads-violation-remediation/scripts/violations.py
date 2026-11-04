#!/usr/bin/env python3
"""Filters Assured Workloads violation lists saved from gcloud or REST.

The agent saves the output of `gcloud assured workloads violations list
--format=json` (or REST list pages) to files and passes them here. This script
calls no API and needs no credentials, so it behaves the same everywhere.

Input: one or more JSON files, or stdin when no file (or "-") is given. Each
file holds either the JSON array printed by gcloud, a REST list page
(`{"violations": [...], ...}`), or a tool-runner wrapper of the form
`{"response": {"stdout": "...", "stderr": "..."}}` around either of them.
Lines printed before the JSON (such as "Using endpoint [...]") are skipped.
Pages are merged and de-duplicated by name.

Subcommands:
  children --parent ID     Open resource violations raised under a policy
                           violation.
  siblings --violation ID  Open resource violations that share this one's
                           parent, or, with no parent, the same `category`.
  same-policy --constraint C [--exclude ID]
                           Open organization policy violations on the same
                           constraint, at any scope.

Output is JSON on stdout. Diagnostics go to stderr.

Exit codes:
  0  Success.
  1  Bad input: a file is missing, holds no JSON, or wraps a failed command.
  2  Usage error (unknown subcommand or missing flag).
"""

# This script runs on the user's machine with a plain `python3` and only the
# standard library, so it uses argparse rather than absl.
import argparse
import collections
from collections.abc import Iterable, Sequence
import json
import sys
from typing import Any

_ORGPOLICY_PREFIX = "//orgpolicy.googleapis.com/"
_SCOPE_PREFIXES = ("organizations/", "folders/", "projects/")
# gcloud starts every error line with its log level. Anything else on stderr,
# such as "Using endpoint [...]" or "Listed 0 items.", is a notice.
_FAILURE_MARKERS = ("ERROR:", "CRITICAL:", "Traceback (most recent call last)")
# Fields copied into each violation summary, when set.
_SUMMARY_FIELDS = (
    "name",
    "state",
    "violationType",
    "category",
    "resourceName",
    "resourceType",
    "associatedOrgPolicyViolationId",
    "beginTime",
)

_EXAMPLES = """\
examples:
  gcloud assured workloads violations list --organization=123 \\
      --location=us --workload=- --view=data-boundary --limit=1000 \\
      --format=json --quiet > page1.json
  python3 scripts/violations.py children --parent v-123 page1.json
  python3 scripts/violations.py siblings --violation v-456 page1.json
  python3 scripts/violations.py same-policy \\
      --constraint gcp.resourceLocations --exclude v-123 page1.json
"""

# parse_json and _unwrap_envelope are copied in policy_history.py on purpose:
# each script in the skill must run on its own.


def parse_json(text: str) -> Any:
  """Parses JSON, skipping lines printed before it and unwrapping wrappers.

  gcloud can print a line such as "Using endpoint [https://...]" first, so the
  first "[" in the text is not always the start of the JSON.

  Args:
    text: Command output.

  Returns:
    The parsed value, or None if no line starts valid JSON.
  """
  lines = text.splitlines()
  for i, line in enumerate(lines):
    if line.lstrip()[:1] in ("[", "{"):
      try:
        parsed = json.loads("\n".join(lines[i:]))
      except ValueError:
        # Not JSON from this line on; try the next line.
        continue
      return _unwrap_envelope(parsed)
  return None


def _unwrap_envelope(parsed: Any) -> Any:
  """Returns the command output inside a tool-runner wrapper.

  Some agent tool runners print {"response": {"stdout": "...", "stderr": "..."}}
  and exit 0 even when the wrapped command failed.

  Args:
    parsed: Parsed JSON.

  Returns:
    The parsed inner stdout, or `parsed` unchanged if it is not a wrapper.

  Raises:
    ValueError: If the wrapper reports a failed command.
  """
  if not isinstance(parsed, dict) or not isinstance(
      parsed.get("response"), dict
  ):
    return parsed
  response = parsed["response"]
  stdout = str(response.get("stdout") or "")
  stderr = str(response.get("stderr") or "")
  if any(marker in stderr for marker in _FAILURE_MARKERS):
    raise ValueError(f"wrapped command failed: {stderr.strip()}")
  return parse_json(stdout) if stdout.strip() else []


def load(paths: Sequence[str]) -> list[dict[str, Any]]:
  """Loads and merges violation pages from files or stdin.

  Args:
    paths: File paths; "-" or an empty list reads stdin.

  Returns:
    The merged violations.

  Raises:
    ValueError: If an input holds no JSON or wraps a failed command.
    OSError: If a file cannot be read.
  """
  if not paths:
    paths = ["-"]
  merged: dict[str, dict[str, Any]] = {}
  for path in paths:
    if path == "-":
      text = sys.stdin.read()
    else:
      with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
      continue
    page = parse_json(text)
    if page is None:
      raise ValueError(f"no JSON found in {path}")
    items = page.get("violations", []) if isinstance(page, dict) else page
    for item in items:
      violation = dict(item)
      violation["name"] = normalize_name(violation.get("name", ""))
      merged[violation["name"]] = violation
  return list(merged.values())


def normalize_name(name: str) -> str:
  """Adds the `workloads/-/` segment that Data Boundary list names leave out.

  Args:
    name: A violation name.

  Returns:
    The name with a workload segment.
  """
  if "/violations/" in name and "/workloads/" not in name:
    return name.replace("/violations/", "/workloads/-/violations/", 1)
  return name


def violation_id(violation: dict[str, Any]) -> str:
  """Returns the last segment of the violation's name, such as `v-123`."""
  return violation.get("name", "").rsplit("/", 1)[-1]


def split_policy(policy: str) -> tuple[str, str]:
  """Returns (scope, constraint) from a nonCompliantOrgPolicy value.

  Handles `folders/1/policies/C`, the `//orgpolicy.googleapis.com/` prefix, and
  Data Boundary values that append a cloud control path after the constraint.

  Args:
    policy: The nonCompliantOrgPolicy field.

  Returns:
    The scope (for example `folders/1`) and the constraint name, or empty
    strings if the value has no `/policies/` segment.
  """
  if policy.startswith(_ORGPOLICY_PREFIX):
    policy = policy[len(_ORGPOLICY_PREFIX):]
  elif policy.startswith("//"):
    # Data Boundary resource violations without a parent hold the resource's
    # own name here (for example //logging.googleapis.com/...), not a policy.
    return "", ""
  head, sep, tail = policy.partition("/policies/")
  if not sep:
    return "", ""
  parts = head.split("/")
  if len(parts) != 2 or not head.startswith(_SCOPE_PREFIXES):
    return "", ""
  return head, tail.split("/", 1)[0]


def summarize(violation: dict[str, Any]) -> dict[str, Any]:
  """Returns the fields the agent needs, plus the scope and constraint.

  Args:
    violation: One violation as listed.

  Returns:
    The set fields from `_SUMMARY_FIELDS`, the violation ID and, when the
    violation names a policy, its scope and constraint.
  """
  scope, constraint = split_policy(violation.get("nonCompliantOrgPolicy", ""))
  summary = {
      field: violation[field]
      for field in _SUMMARY_FIELDS
      if violation.get(field)
  }
  summary["id"] = violation_id(violation)
  if scope:
    summary["scope"] = scope
    summary["constraint"] = constraint
  return summary


def _is_open(violation: dict[str, Any]) -> bool:
  """True for violations that still need a fix: not resolved, not accepted."""
  return violation.get("state", "UNRESOLVED") not in ("RESOLVED", "EXCEPTION")


def count_resources(violations: Iterable[dict[str, Any]]) -> int:
  """Counts distinct resources: two frameworks can flag one resource twice.

  Violations with no `resourceName` are left out here and counted by
  `count_unnamed`, so the number is never inflated by violation names.

  Args:
    violations: The violations to count.

  Returns:
    The number of distinct non-empty `resourceName` values.
  """
  return len({
      violation["resourceName"]
      for violation in violations
      if violation.get("resourceName")
  })


def count_unnamed(violations: Iterable[dict[str, Any]]) -> int:
  """Counts violations with no `resourceName`, which `count_resources` skips."""
  return sum(1 for violation in violations if not violation.get("resourceName"))


def children(
    violations: Iterable[dict[str, Any]], parent_id: str
) -> list[dict[str, Any]]:
  """Returns the open resource violations raised under a policy violation.

  Args:
    violations: The merged list.
    parent_id: The ID of the organization policy violation.

  Returns:
    The open violations whose `associatedOrgPolicyViolationId` is `parent_id`.
  """
  return [
      violation
      for violation in violations
      if violation.get("associatedOrgPolicyViolationId") == parent_id
      and _is_open(violation)
  ]


def siblings(
    violations: Sequence[dict[str, Any]], own_id: str
) -> tuple[str | None, list[dict[str, Any]]]:
  """Returns the parent ID and the other open violations that go with this one.

  With a parent, siblings are the other open violations under it. Without one
  (Data Boundary resource violations from controls with no organization
  policy, or with no open policy violation above the resource), siblings are
  the other open resource violations with the same `category` in the list.

  Args:
    violations: The merged list.
    own_id: This violation's ID.

  Returns:
    The parent ID (None without a parent) and the sibling violations.
  """
  own = next(
      (
          violation
          for violation in violations
          if violation_id(violation) == own_id
      ),
      None,
  )
  if own is None:
    return None, []
  parent = own.get("associatedOrgPolicyViolationId")
  if parent:
    return parent, [
        violation
        for violation in children(violations, parent)
        if violation_id(violation) != own_id
    ]
  category = own.get("category")
  if not category or own.get("violationType") != "RESOURCE":
    return None, []
  return None, [
      violation
      for violation in violations
      if violation.get("violationType") == "RESOURCE"
      and violation.get("category") == category
      and _is_open(violation)
      and violation_id(violation) != own_id
  ]


def same_policy(
    violations: Iterable[dict[str, Any]],
    constraint: str,
    exclude_id: str | None = None,
) -> list[dict[str, Any]]:
  """Returns open organization policy violations on the same constraint.

  Args:
    violations: The merged list.
    constraint: The constraint name, with or without `constraints/`.
    exclude_id: A violation ID to leave out, or None to keep them all.

  Returns:
    The matching violations, at any scope.
  """
  constraint = constraint.removeprefix("constraints/")
  matches = []
  for violation in violations:
    if violation.get("violationType") != "ORG_POLICY" or not _is_open(
        violation
    ):
      continue
    if exclude_id and violation_id(violation) == exclude_id:
      continue
    policy = violation.get("nonCompliantOrgPolicy", "")
    if split_policy(policy)[1] == constraint:
      matches.append(violation)
  return matches


def _by_type(violations: Iterable[dict[str, Any]]) -> dict[str, int]:
  """Counts violations per `resourceType`, most common first."""
  counts = collections.Counter(
      violation.get("resourceType", "unknown") for violation in violations
  )
  return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _resource_counts(found: Sequence[dict[str, Any]]) -> dict[str, Any]:
  """Returns the count fields shared by `children` and `siblings` output."""
  return {
      "count": len(found),
      "resources": count_resources(found),
      "withoutResourceName": count_unnamed(found),
      "byResourceType": _by_type(found),
  }


def _parser() -> argparse.ArgumentParser:
  """Builds the command-line parser."""
  parser = argparse.ArgumentParser(
      description=__doc__.splitlines()[0],
      epilog=_EXAMPLES,
      formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  subparsers = parser.add_subparsers(dest="command", required=True)
  subparser = subparsers.add_parser(
      "children", help="Open resource violations under a parent."
  )
  subparser.add_argument("--parent", required=True, help="Policy violation ID.")
  subparser.add_argument(
      "files", nargs="*", help="Saved list pages (default: stdin)."
  )
  subparser = subparsers.add_parser(
      "siblings", help="Open violations that go with this one."
  )
  subparser.add_argument(
      "--violation", required=True, help="Resource violation ID."
  )
  subparser.add_argument(
      "files", nargs="*", help="Saved list pages (default: stdin)."
  )
  subparser = subparsers.add_parser(
      "same-policy", help="Open policy violations on the same constraint."
  )
  subparser.add_argument(
      "--constraint", required=True, help="For example gcp.resourceLocations."
  )
  subparser.add_argument("--exclude", help="Violation ID to leave out.")
  subparser.add_argument(
      "files", nargs="*", help="Saved list pages (default: stdin)."
  )
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Runs the command and returns the process exit code."""
  args = _parser().parse_args(argv)
  try:
    violations = load(args.files)
  except (OSError, ValueError) as e:
    print(f"error: {e}", file=sys.stderr)
    return 1
  if args.command == "children":
    found = children(violations, args.parent)
    result = {"parent": args.parent, **_resource_counts(found)}
  elif args.command == "siblings":
    parent, found = siblings(violations, args.violation)
    result = {
        "parent": parent,
        "basis": "parent" if parent else "same category",
        **_resource_counts(found),
    }
  else:
    found = same_policy(violations, args.constraint, args.exclude)
    result = {"constraint": args.constraint, "count": len(found)}
  result["violations"] = [summarize(violation) for violation in found]
  result["scanned"] = len(violations)
  json.dump(result, sys.stdout, indent=1)
  sys.stdout.write("\n")
  return 0


if __name__ == "__main__":
  sys.exit(main())
