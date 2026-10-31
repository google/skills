#!/usr/bin/env python3
"""Deterministic validator for Google SecOps YARA-L 2.0 rules (.yaral / .md).

Verifies that candidate YARA-L 2.0 rules conform to Google SecOps compiler
invariants:
  1. Canonical section ordering (meta -> events -> match -> outcome ->
     condition -> options)
  2. Balanced braces and valid rule header declaration (ignoring braces and
     '//' sequences inside string and regex literals)
  3. Explicit match: correlation window ($var over {duration})
  4. Mandatory aggregation functions (max, min, sum, count, count_distinct,
     array, array_distinct) wrapping event-dependent outcome: expressions when
     match: is used, allowing parenthesized arithmetic over defined outcome
     variables, rejecting nested outcome variables inside aggregates, and
     requiring array_distinct() or array() on repeated UDM fields even in
     single-event rules
  5. External nocase placement on re.regex() and regex literals (catching
     inline (?i) without nocase, /pattern/i flags, and nocase inside
     re.regex(..., nocase) across events: and outcome:)
  6. Proper CIDR filtering via net.ip_in_range_cidr() for inline CIDRs and
     'in cidr %list_name' for CIDR Reference Lists
"""

import argparse
from collections.abc import Sequence
import difflib
import json
import pathlib
import re
import sys

SECTION_ORDER = ("meta", "events", "match", "outcome", "condition", "options")
ALLOWED_AGGREGATIONS = (
    "max",
    "min",
    "sum",
    "count",
    "count_distinct",
    "array",
    "array_distinct",
)
ARRAY_COMPATIBLE_AGGREGATIONS = (
    "array",
    "array_distinct",
    "count",
    "count_distinct",
)
REGEX_PRECEDING_CHARS = frozenset("=(,:!&|<>~+-*/%^?;{[\n\t ")
REGEX_PRECEDING_KEYWORDS = frozenset({"and", "or", "not"})

RULE_START_RE = re.compile(r"\brule\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{")
FENCED_YARAL_RE = re.compile(r"```(?:yaral|yara)\s*\n(.*?)```", re.DOTALL)
SECTION_HEADER_RE = re.compile(
    r"^\s*(meta|events|match|outcome|condition|options)\s*:", re.MULTILINE
)
MATCH_WINDOW_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*\$[A-Za-z_][A-Za-z0-9_]*)*"
    r"\s+over\s+[0-9]+[smhd]\b"
)
OUTCOME_ASSIGN_RE = re.compile(
    r"^\s*(\$[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$"
)
AGG_FUNC_RE = re.compile(
    r"^(?:" + "|".join(ALLOWED_AGGREGATIONS) + r")\s*\(.*\)$"
)
ARRAY_AGG_FUNC_RE = re.compile(
    r"^(?:" + "|".join(ARRAY_COMPATIBLE_AGGREGATIONS) + r")\s*\(.*\)$"
)
ARITH_UNPAREN_RE = re.compile(
    r"^(?:\$[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?)"
    r"(?:\s*[+\-*/%]\s*(?:\$[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?))+$"
)
EMPTY_PARENS_RE = re.compile(r"\(\s*\)")
VAR_TOKEN_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
TRAILING_WORD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*$")
INLINE_CASE_FLAG_RE = re.compile(r"\(\?[imsx]*i[imsx]*\)")
SLASH_REGEX_I_FLAG_RE = re.compile(r"/i\b")
RE_REGEX_INTERNAL_NOCASE_RE = re.compile(
    r"\bre\.regex\s*\([^)]*,\s*nocase\s*\)"
)
REPEATED_UDM_FIELD_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_]*\.(?:"
    r"(?:principal|target|src|dest|intermediary|observer|about)\.(?:ip|nat_ip)|"
    r"(?:principal|target|src|dest|about)\.user\.email_addresses|"
    r"security_result\.category_details"
    r")\b"
)
CIDR_INLINE_LITERAL_RE = re.compile(
    r"(?:principal|target|src|dest|intermediary|observer|about)\.(?:ip|nat_ip)"
    r'\s*(?:=|!=)\s*"[0-9]{1,3}(?:\.[0-9]{1,3}){3}/[0-9]{1,2}"'
)
CIDR_BARE_LIST_RE = re.compile(
    r"\.\s*(?:ip|nat_ip)\s+in\s+%[A-Za-z0-9_]*cidr[A-Za-z0-9_]*\b"
)


def _can_start_slash_regex(text: str, slash_idx: int) -> bool:
  """Returns True if '/' at slash_idx begins a '/.../' regex literal."""
  if slash_idx + 1 < len(text) and text[slash_idx + 1] in ("/", "*"):
    return False
  prev_idx = slash_idx - 1
  while prev_idx >= 0 and text[prev_idx] in (" ", "\t"):
    prev_idx -= 1
  if prev_idx < 0:
    return True
  prev_ch = text[prev_idx]
  if prev_ch in REGEX_PRECEDING_CHARS:
    return True
  word_match = TRAILING_WORD_RE.search(text[: prev_idx + 1])
  if word_match is not None and word_match.group(1) in REGEX_PRECEDING_KEYWORDS:
    return True
  return False


def mask_literals_and_comments(text: str) -> str:
  """Masks string/regex literal interiors and comments with spaces.

  Preserves exact string length, delimiter positions (quotes, backticks, and
  slashes), and line breaks so character offsets and line numbers map 1-to-1
  with `text`.

  Args:
    text: Raw YARA-L text or single line.

  Returns:
    A string of identical length where literal interiors and comments are
    replaced with spaces.
  """
  out = list(text)
  n = len(text)
  idx = 0
  while idx < n:
    ch = text[idx]
    if ch == "/" and idx + 1 < n and text[idx + 1] == "/":
      while idx < n and text[idx] != "\n":
        out[idx] = " "
        idx += 1
      continue
    if ch == "/" and idx + 1 < n and text[idx + 1] == "*":
      out[idx] = " "
      out[idx + 1] = " "
      idx += 2
      while idx < n:
        if text[idx] == "*" and idx + 1 < n and text[idx + 1] == "/":
          out[idx] = " "
          out[idx + 1] = " "
          idx += 2
          break
        if text[idx] != "\n":
          out[idx] = " "
        idx += 1
      continue
    if ch == '"':
      idx += 1
      while idx < n and text[idx] != '"':
        if text[idx] == "\\" and idx + 1 < n:
          if text[idx] != "\n":
            out[idx] = " "
          idx += 1
          if text[idx] != "\n":
            out[idx] = " "
          idx += 1
          continue
        if text[idx] != "\n":
          out[idx] = " "
        idx += 1
      if idx < n:
        idx += 1
      continue
    if ch == "`":
      idx += 1
      while idx < n and text[idx] != "`":
        if text[idx] != "\n":
          out[idx] = " "
        idx += 1
      if idx < n:
        idx += 1
      continue
    if ch == "/" and _can_start_slash_regex(text, idx):
      idx += 1
      while idx < n and text[idx] not in ("/", "\n"):
        if text[idx] == "\\" and idx + 1 < n and text[idx + 1] != "\n":
          out[idx] = " "
          out[idx + 1] = " "
          idx += 2
          continue
        out[idx] = " "
        idx += 1
      if idx < n and text[idx] == "/":
        idx += 1
      continue
    idx += 1
  return "".join(out)


def strip_line_comment(line: str) -> str:
  """Strips '//' and inline '/*...*/' comments while preserving literals."""
  masked = mask_literals_and_comments(line)
  n = len(line)
  idx = 0
  while idx < n:
    if line[idx] != " " and masked[idx] == " ":
      # A non-space character in `line` became a space in `masked` either
      # because it is inside a literal or because it starts a comment.
      if line[idx : idx + 2] == "//":
        return line[:idx]
    idx += 1
  return line


def iter_logical_statements(section_body: str) -> list[tuple[int, str, str]]:
  """Joins multi-line parenthesized or operator-continued statements.

  Args:
    section_body: Raw text of an `events:` or `outcome:` section.

  Returns:
    A list of `(start_line_num, code_statement, raw_statement)` tuples.
  """
  statements: list[tuple[int, str, str]] = []
  buf_code: list[str] = []
  buf_raw: list[str] = []
  start_line = 1
  paren_depth = 0

  for line_num, raw_line in enumerate(section_body.splitlines(), start=1):
    code_part = strip_line_comment(raw_line).strip()
    if not code_part:
      continue
    if not buf_code:
      start_line = line_num
    buf_code.append(code_part)
    buf_raw.append(raw_line.strip())
    masked_part = mask_literals_and_comments(code_part)
    paren_depth += masked_part.count("(") - masked_part.count(")")
    continues = paren_depth > 0 or code_part.endswith(
        ("=", ",", "+", "-", "*", "/")
    )
    if not continues:
      statements.append((start_line, " ".join(buf_code), " ".join(buf_raw)))
      buf_code = []
      buf_raw = []
      paren_depth = 0

  if buf_code:
    statements.append((start_line, " ".join(buf_code), " ".join(buf_raw)))
  return statements


def is_valid_outcome_arithmetic(rhs: str, defined_outcomes: set[str]) -> bool:
  """Returns True if rhs is valid arithmetic over defined_outcomes and numbers.

  Supports balanced parentheses such as `($total * 3600) / ($time_span + 1)`.

  Args:
    rhs: Right-hand side expression of an `outcome:` assignment.
    defined_outcomes: Set of `$var` outcome names defined on prior lines.

  Returns:
    True if `rhs` is a well-formed arithmetic expression referencing only
    previously defined outcome variables and numeric literals.
  """
  if EMPTY_PARENS_RE.search(rhs):
    return False
  paren_depth = 0
  for ch in rhs:
    if ch == "(":
      paren_depth += 1
    elif ch == ")":
      paren_depth -= 1
      if paren_depth < 0:
        return False
  if paren_depth != 0:
    return False

  unparen = rhs.replace("(", " ").replace(")", " ").strip()
  if not ARITH_UNPAREN_RE.fullmatch(unparen):
    return False

  refs = VAR_TOKEN_RE.findall(unparen)
  return bool(refs) and all(ref in defined_outcomes for ref in refs)


def validate_paths(target_path: pathlib.Path) -> pathlib.Path:
  """Verifies target_path exists and suggests close matches on typo."""
  resolved = target_path.expanduser()
  if resolved.exists():
    if not resolved.is_file():
      raise ValueError(f"Path '{resolved}' exists but is not a regular file.")
    return resolved

  parent = resolved.parent if resolved.parent.exists() else pathlib.Path.cwd()
  candidates = [p.name for p in parent.iterdir()] if parent.exists() else []
  close = difflib.get_close_matches(resolved.name, candidates, n=3, cutoff=0.5)
  hint = f" Did you mean: {', '.join(close)}?" if close else ""
  raise FileNotFoundError(
      f"Candidate YARA-L file not found at '{resolved}'.{hint}"
  )


def extract_rules(
    text: str,
) -> tuple[list[tuple[str, str, int]], list[str]]:
  """Extracts (rule_name, rule_body, unclosed_depth) and structural errors."""
  masked = mask_literals_and_comments(text)
  if not RULE_START_RE.search(masked):
    return [], []

  rules: list[tuple[str, str, int]] = []
  structural_errors: list[str] = []
  pos = 0
  last_rule_name: str | None = None

  while True:
    match = RULE_START_RE.search(masked, pos)
    interstitial = masked[pos : match.start()] if match else masked[pos:]
    if interstitial.strip():
      owner = f"Rule '{last_rule_name}'" if last_rule_name else "Input"
      structural_errors.append(
          f"{owner}: Unbalanced braces or unexpected trailing tokens outside "
          "rule body."
      )
    if not match:
      break

    rule_name = match.group(1)
    last_rule_name = rule_name
    body_start = match.end()
    depth = 1
    idx = body_start
    while idx < len(masked) and depth > 0:
      ch = masked[idx]
      if ch == "{":
        depth += 1
      elif ch == "}":
        depth -= 1
      idx += 1
    if depth == 0:
      rules.append((rule_name, text[body_start : idx - 1], 0))
      pos = idx
    else:
      rules.append((rule_name, text[body_start:], depth))
      break

  return rules, structural_errors


def extract_sections(rule_body: str) -> tuple[list[str], dict[str, str]]:
  """Extracts section names in appearance order and their body text."""
  masked_body = mask_literals_and_comments(rule_body)
  matches = list(SECTION_HEADER_RE.finditer(masked_body))
  order: list[str] = []
  sections: dict[str, str] = {}
  for idx, match in enumerate(matches):
    sec_name = match.group(1)
    order.append(sec_name)
    start = match.end()
    end = matches[idx + 1].start() if idx + 1 < len(matches) else len(rule_body)
    sections[sec_name] = rule_body[start:end]
  return order, sections


def _check_regex_and_nocase_line(
    rule_name: str,
    section_name: str,
    line_num: int,
    code_part: str,
    masked_line: str,
    stripped_raw: str,
) -> list[str]:
  """Checks a single line in events: or outcome: for regex/nocase violations."""
  line_errors: list[str] = []
  if INLINE_CASE_FLAG_RE.search(code_part) and "nocase" not in masked_line:
    line_errors.append(
        f"Rule '{rule_name}' ({section_name} line {line_num}): Inline '(?i)' "
        f"used without trailing 'nocase' token: {stripped_raw}"
    )
  if SLASH_REGEX_I_FLAG_RE.search(masked_line):
    line_errors.append(
        f"Rule '{rule_name}' ({section_name} line {line_num}): Invalid "
        "'/pattern/i' regex modifier; place 'nocase' outside the regex "
        f"literal ('/pattern/ nocase'): {stripped_raw}"
    )
  if RE_REGEX_INTERNAL_NOCASE_RE.search(masked_line):
    line_errors.append(
        f"Rule '{rule_name}' ({section_name} line {line_num}): 'nocase' must "
        "be placed outside 're.regex(...)' after the closing parenthesis, "
        f"not as a function argument: {stripped_raw}"
    )
  return line_errors


def validate_single_rule(
    rule_name: str,
    rule_body: str,
    unclosed_depth: int = 0,
) -> list[str]:
  """Validates a single YARA-L 2.0 rule body and returns error strings."""
  errors: list[str] = []

  masked_body = mask_literals_and_comments(rule_body)
  inner_brace_delta = masked_body.count("{") - masked_body.count("}")
  if unclosed_depth != 0 or inner_brace_delta != 0:
    net_depth = unclosed_depth if unclosed_depth != 0 else inner_brace_delta
    errors.append(
        f"Rule '{rule_name}': Unbalanced braces inside rule body "
        f"(net depth: {net_depth})."
    )

  order, sections = extract_sections(rule_body)
  for req in ("events", "condition"):
    if req not in sections:
      errors.append(f"Rule '{rule_name}': Missing required '{req}:' section.")

  filtered_expected = [s for s in SECTION_ORDER if s in order]
  if order != filtered_expected:
    errors.append(
        f"Rule '{rule_name}': Invalid section order {order}; expected "
        f"{filtered_expected}."
    )

  events_body = sections.get("events", "")
  for line_num, raw_line in enumerate(events_body.splitlines(), start=1):
    code_part = strip_line_comment(raw_line).strip()
    if not code_part:
      continue
    masked_line = mask_literals_and_comments(code_part)
    stripped_raw = raw_line.strip()
    errors.extend(
        _check_regex_and_nocase_line(
            rule_name, "events", line_num, code_part, masked_line, stripped_raw
        )
    )
    if (
        CIDR_INLINE_LITERAL_RE.search(code_part)
        and "net.ip_in_range_cidr" not in masked_line
    ):
      errors.append(
          f"Rule '{rule_name}' (events line {line_num}): Inline CIDR check "
          'must use net.ip_in_range_cidr($e.field, "x.x.x.x/N"): '
          f"{stripped_raw}"
      )
    elif CIDR_BARE_LIST_RE.search(masked_line):
      errors.append(
          f"Rule '{rule_name}' (events line {line_num}): CIDR Reference List "
          "check must use '$e.field in cidr %list_name' (or "
          'net.ip_in_range_cidr($e.field, "x.x.x.x/N") for inline CIDRs): '
          f"{stripped_raw}"
      )

  has_match = "match" in sections
  if has_match:
    match_body = sections["match"]
    active_match_lines = [
        strip_line_comment(ln).strip()
        for ln in match_body.splitlines()
        if strip_line_comment(ln).strip()
    ]
    if not active_match_lines or not MATCH_WINDOW_RE.search(
        " ".join(active_match_lines)
    ):
      errors.append(
          f"Rule '{rule_name}': 'match:' section must specify a valid window "
          "(e.g., '$host over 15m')."
      )

  if "outcome" in sections:
    outcome_body = sections["outcome"]
    defined_outcomes: set[str] = set()
    for line_num, code_part, stripped_raw in iter_logical_statements(
        outcome_body
    ):
      masked_line = mask_literals_and_comments(code_part)
      errors.extend(
          _check_regex_and_nocase_line(
              rule_name,
              "outcome",
              line_num,
              code_part,
              masked_line,
              stripped_raw,
          )
      )
      assign_match = OUTCOME_ASSIGN_RE.fullmatch(code_part)
      if not assign_match:
        errors.append(
            f"Rule '{rule_name}' (outcome line {line_num}): Malformed outcome "
            f"assignment: {code_part}"
        )
        continue
      var_name, rhs = assign_match.group(1), assign_match.group(2)
      masked_rhs = mask_literals_and_comments(rhs).strip()

      if AGG_FUNC_RE.fullmatch(rhs):
        nested_outcomes = [
            ref
            for ref in VAR_TOKEN_RE.findall(masked_rhs)
            if ref in defined_outcomes
        ]
        if nested_outcomes:
          errors.append(
              f"Rule '{rule_name}' (outcome line {line_num}): Cannot nest "
              f"outcome variable '{nested_outcomes[0]}' inside an aggregation "
              f"function in '{var_name} = {rhs}'; aggregate raw event fields "
              "first and combine via top-level arithmetic."
          )

      if REPEATED_UDM_FIELD_RE.search(
          masked_rhs
      ) and not ARRAY_AGG_FUNC_RE.fullmatch(rhs):
        errors.append(
            f"Rule '{rule_name}' (outcome line {line_num}): Repeated UDM "
            f"field in '{var_name} = {rhs}' must be wrapped in "
            "'array_distinct()' or 'array()' (even in single-event rules "
            "without 'match:')."
        )

      is_valid_arith = is_valid_outcome_arithmetic(masked_rhs, defined_outcomes)
      if has_match and not (AGG_FUNC_RE.fullmatch(rhs) or is_valid_arith):
        errors.append(
            f"Rule '{rule_name}' (outcome line {line_num}): Outcome variable "
            f"'{var_name} = {rhs}' must be wrapped in an aggregation function "
            f"{ALLOWED_AGGREGATIONS} when 'match:' is present."
        )
      defined_outcomes.add(var_name)

  return errors


def validate_yaral_text(text: str) -> tuple[int, list[str]]:
  """Validates all full YARA-L rules in a .yaral or .md text payload."""
  errors: list[str] = []
  blocks = FENCED_YARAL_RE.findall(text)
  search_targets = blocks if blocks else [text]

  rule_count = 0
  for target in search_targets:
    extracted_rules, structural_errors = extract_rules(target)
    errors.extend(structural_errors)
    for rule_name, rule_body, unclosed_depth in extracted_rules:
      rule_count += 1
      errors.extend(validate_single_rule(rule_name, rule_body, unclosed_depth))

  if rule_count == 0:
    errors.append(
        "No complete 'rule {rule_name} { ... }' block found in input."
    )

  return rule_count, errors


def main(argv: Sequence[str] | None = None) -> int:
  """CLI entrypoint for validating YARA-L 2.0 rules in .yaral or .md files.

  Args:
    argv: Optional sequence of command-line arguments.

  Returns:
    Exit code (0 for valid, 1 for validation errors, 2 for usage/file errors).
  """
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "pos_input",
      nargs="?",
      help="Optional positional path to a .yaral or .md file.",
  )
  parser.add_argument(
      "--input",
      required=False,
      help="Path to a .yaral file or Markdown file containing YARA-L blocks.",
  )
  parser.add_argument(
      "--json",
      action="store_true",
      help="Emit structured validation results as JSON on stdout.",
  )
  args = parser.parse_args(argv)
  input_arg = args.input or args.pos_input
  if not input_arg:
    parser.error(
        "the following arguments are required: --input (or positional path)"
    )

  try:
    target_path = validate_paths(pathlib.Path(input_arg))
  except (FileNotFoundError, ValueError) as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 2

  text = target_path.read_text(encoding="utf-8")
  rule_count, errors = validate_yaral_text(text)

  if args.json:
    print(
        json.dumps(
            {
                "file": str(target_path),
                "valid": not errors,
                "rule_count": rule_count,
                "errors": errors,
            },
            indent=2,
        )
    )
    return 1 if errors else 0

  if errors:
    print(
        f"INVALID YARA-L 2.0 ({target_path}): {len(errors)} error(s) found:",
        file=sys.stderr,
    )
    for err in errors:
      print(f"  - {err}", file=sys.stderr)
    return 1

  print(
      f"VALID: {target_path} ({rule_count} full YARA-L 2.0 rule(s)) passed all "
      "section-order, match-window, outcome-aggregation, nocase, and CIDR "
      "checks."
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
