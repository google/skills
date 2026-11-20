#!/usr/bin/env python3
"""Configures GKE Deployment YAML files for Agent Registry discovery."""

import argparse
from collections.abc import Sequence
import os
import re
import sys

_YAML_DOC_BOUNDARY_RE = re.compile(r"^(?:---|\.\.\.)(?:\s*(?:#.*)?)?$")


def _strip_yaml_comment(line: str) -> str:
  """Returns `line` with any trailing unquoted YAML `#` comment removed."""
  in_single = False
  in_double = False
  idx = 0
  length = len(line)
  while idx < length:
    ch = line[idx]
    if in_single:
      if ch == "'":
        if idx + 1 < length and line[idx + 1] == "'":
          idx += 2
          continue
        in_single = False
    elif in_double:
      if ch == "\\" and idx + 1 < length:
        idx += 2
        continue
      if ch == '"':
        in_double = False
    else:
      if ch == "'":
        in_single = True
      elif ch == '"':
        in_double = True
      elif ch == "#" and (idx == 0 or line[idx - 1].isspace()):
        return line[:idx]
    idx += 1
  return line


def _find_unquoted_colon(text: str) -> int:
  """Finds the index of the first unquoted YAML mapping `:` separator, or -1."""
  in_single = False
  in_double = False
  brace_depth = 0
  bracket_depth = 0
  idx = 0
  length = len(text)
  while idx < length:
    ch = text[idx]
    if in_single:
      if ch == "'":
        if idx + 1 < length and text[idx + 1] == "'":
          idx += 2
          continue
        in_single = False
    elif in_double:
      if ch == "\\" and idx + 1 < length:
        idx += 2
        continue
      if ch == '"':
        in_double = False
    else:
      if ch == "'":
        in_single = True
      elif ch == '"':
        in_double = True
      elif ch == "{":
        brace_depth += 1
      elif ch == "}":
        brace_depth -= 1
      elif ch == "[":
        bracket_depth += 1
      elif ch == "]":
        bracket_depth -= 1
      elif (
          ch == ":"
          and brace_depth == 0
          and bracket_depth == 0
          and (idx + 1 == length or text[idx + 1].isspace())
      ):
        return idx
    idx += 1
  return -1


def _split_flow_map_entries(inner: str) -> list[str]:
  """Splits the interior of a YAML `{k: v, ...}` flow mapping into entries."""
  if not inner.strip():
    return []

  entries: list[str] = []
  start = 0
  in_single = False
  in_double = False
  brace_depth = 0
  bracket_depth = 0
  idx = 0
  length = len(inner)

  while idx < length:
    ch = inner[idx]
    if in_single:
      if ch == "'":
        if idx + 1 < length and inner[idx + 1] == "'":
          idx += 2
          continue
        in_single = False
    elif in_double:
      if ch == "\\" and idx + 1 < length:
        idx += 2
        continue
      if ch == '"':
        in_double = False
    else:
      if ch == "'":
        in_single = True
      elif ch == '"':
        in_double = True
      elif ch == "{":
        brace_depth += 1
      elif ch == "}":
        brace_depth -= 1
      elif ch == "[":
        bracket_depth += 1
      elif ch == "]":
        bracket_depth -= 1
      elif ch == "," and brace_depth == 0 and bracket_depth == 0:
        piece = inner[start:idx].strip()
        if piece:
          entries.append(piece)
        start = idx + 1
    idx += 1

  if in_single or in_double or brace_depth != 0 or bracket_depth != 0:
    raise ValueError(f"Unbalanced YAML flow mapping: {{{inner}}}")

  tail = inner[start:].strip()
  if tail:
    entries.append(tail)

  normalized: list[str] = []
  for entry in entries:
    colon_idx = _find_unquoted_colon(entry)
    if colon_idx < 0:
      raise ValueError(f"Invalid YAML flow mapping entry: {entry!r}")
    key_str = entry[:colon_idx].strip()
    val_str = entry[colon_idx + 1 :].strip()
    normalized.append(f"{key_str}: {val_str}" if val_str else f"{key_str}:")
  return normalized


def _expand_flow_map_line(line: str) -> list[str]:
  """Expands a single-line `key: {...}` flow mapping recursively into block lines."""
  indent = len(line) - len(line.lstrip())
  code_part = _strip_yaml_comment(line).strip()
  colon_idx = _find_unquoted_colon(code_part)
  if colon_idx < 0:
    return [line]

  key_part = code_part[:colon_idx].strip()
  val_part = code_part[colon_idx + 1 :].strip()
  if not val_part.startswith("{"):
    return [line]
  if not val_part.endswith("}"):
    raise ValueError(
        f"Multi-line flow mapping on '{key_part}:' is not supported; convert it"
        " to block YAML first."
    )

  entries = _split_flow_map_entries(val_part[1:-1])
  expanded = [" " * indent + f"{key_part}:"]
  for entry in entries:
    child_line = " " * (indent + 2) + entry
    expanded.extend(_expand_flow_map_line(child_line))
  return expanded


def _key_matches_mapping_line(code_part: str, key_name: str) -> bool:
  """Returns True if `code_part` declares mapping key `key_name:`."""
  if code_part == f"{key_name}:":
    return True
  colon_idx = _find_unquoted_colon(code_part)
  if colon_idx < 0:
    return False
  parsed_key = code_part[:colon_idx].strip().strip("\"'")
  if parsed_key != key_name:
    return False
  val_part = code_part[colon_idx + 1 :].strip()
  return not val_part or val_part.startswith("{")


def _upsert_metadata_map_key(
    meta_lines: Sequence[str],
    metadata_indent: int,
    map_name: str,
    key: str,
    value: str,
) -> list[str]:
  """Ensures `map_name.<key>: "<value>"` exists in a metadata block."""
  meta_lines = list(meta_lines)
  child_indent = metadata_indent + 2
  for line in meta_lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
      continue
    indent = len(line) - len(line.lstrip())
    if indent > metadata_indent:
      child_indent = indent
    break

  map_idx = None
  map_indent = child_indent

  for idx, line in enumerate(meta_lines):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
      continue
    indent = len(line) - len(line.lstrip())
    code_part = _strip_yaml_comment(line).strip()
    if indent == child_indent and _key_matches_mapping_line(
        code_part, map_name
    ):
      map_idx = idx
      map_indent = indent
      expanded = _expand_flow_map_line(meta_lines[idx])
      meta_lines = meta_lines[:idx] + expanded + meta_lines[idx + 1 :]
      break

  if map_idx is not None:
    # Find the end of the map_name block and its direct child indentation
    end_idx = len(meta_lines)
    entry_indent = None
    for j in range(map_idx + 1, len(meta_lines)):
      stripped = meta_lines[j].strip()
      if not stripped or stripped.startswith("#"):
        continue
      indent = len(meta_lines[j]) - len(meta_lines[j].lstrip())
      if indent <= map_indent:
        end_idx = j
        break
      if entry_indent is None:
        entry_indent = indent
    if entry_indent is None:
      entry_indent = map_indent + 2

    # Check if key already exists as a direct child in the block
    for j in range(map_idx + 1, end_idx):
      stripped = meta_lines[j].strip()
      if not stripped or stripped.startswith("#"):
        continue
      indent = len(meta_lines[j]) - len(meta_lines[j].lstrip())
      code_part = _strip_yaml_comment(meta_lines[j]).strip()
      colon_idx = _find_unquoted_colon(code_part)
      if (
          indent == entry_indent
          and colon_idx >= 0
          and code_part[:colon_idx].strip().strip("\"'") == key
      ):
        current_val = code_part[colon_idx + 1 :].strip().strip("\"'")
        if current_val != value:
          print(
              f"Warning: Updating existing {key} from '{current_val}' to"
              f" '{value}'"
          )
          meta_lines[j] = " " * indent + f'{key}: "{value}"'
        else:
          print(f"Info: {key} '{value}' already exists. Skipping update.")
        return meta_lines

    # Key not found inside existing map_name block; insert right after map_name:
    new_line = " " * entry_indent + f'{key}: "{value}"'
    return meta_lines[: map_idx + 1] + [new_line] + meta_lines[map_idx + 1 :]

  # map_name block does not exist; insert before trailing comments/blank lines
  insert_idx = 0
  for j in range(len(meta_lines) - 1, -1, -1):
    stripped = meta_lines[j].strip()
    if stripped and not stripped.startswith("#"):
      insert_idx = j + 1
      break

  new_block = [
      " " * child_indent + f"{map_name}:",
      " " * (child_indent + 2) + f'{key}: "{value}"',
  ]
  return meta_lines[:insert_idx] + new_block + meta_lines[insert_idx:]


def _is_top_level_deployment_line(line: str) -> bool:
  """Returns True if line is a top-level `kind: Deployment` declaration."""
  if len(line) - len(line.lstrip()) != 0:
    return False
  code_part = _strip_yaml_comment(line).strip()
  return code_part in (
      "kind: Deployment",
      'kind: "Deployment"',
      "kind: 'Deployment'",
  )


def _find_and_expand_child_block(
    lines: list[str],
    start_idx: int,
    end_idx: int,
    parent_indent: int,
    key_name: str,
) -> tuple[list[str], tuple[int, int, int] | None]:
  """Finds (and expands if inline `{...}`) a direct child mapping block.

  Args:
    lines: Document lines to search.
    start_idx: Inclusive start line index of the parent block body.
    end_idx: Exclusive end line index of the parent block body.
    parent_indent: Indentation of the parent mapping key (-1 for document root).
    key_name: Mapping key name to find (e.g., 'metadata', 'spec', 'template').

  Returns:
    A pair `(updated_lines, (block_start_idx, block_end_idx, block_indent))` if
    found, or `(lines, None)` if the key does not exist as a direct child.
  """
  child_indent = 0 if parent_indent < 0 else parent_indent + 2
  if parent_indent >= 0:
    for idx in range(start_idx, end_idx):
      stripped = lines[idx].strip()
      if not stripped or stripped.startswith("#"):
        continue
      indent = len(lines[idx]) - len(lines[idx].lstrip())
      if indent > parent_indent:
        child_indent = indent
      break

  for idx in range(start_idx, end_idx):
    stripped = lines[idx].strip()
    if not stripped or stripped.startswith("#"):
      continue
    indent = len(lines[idx]) - len(lines[idx].lstrip())
    code_part = _strip_yaml_comment(lines[idx]).strip()
    if indent == child_indent and _key_matches_mapping_line(
        code_part, key_name
    ):
      expanded = _expand_flow_map_line(lines[idx])
      delta = len(expanded) - 1
      updated_lines = lines[:idx] + expanded + lines[idx + 1 :]
      new_end_idx = end_idx + delta
      block_end = new_end_idx
      for j in range(idx + 1, new_end_idx):
        j_stripped = updated_lines[j].strip()
        if not j_stripped or j_stripped.startswith("#"):
          continue
        j_indent = len(updated_lines[j]) - len(updated_lines[j].lstrip())
        if j_indent <= indent:
          block_end = j
          break
      return updated_lines, (idx, block_end, indent)
  return lines, None


def _process_single_doc(
    doc_lines: Sequence[str], functional_type: str
) -> list[str]:
  """Processes a single YAML document's lines."""
  is_deployment = any(_is_top_level_deployment_line(line) for line in doc_lines)
  if not is_deployment:
    return list(doc_lines)

  doc_lines = list(doc_lines)
  doc_lines, meta_block = _find_and_expand_child_block(
      doc_lines, 0, len(doc_lines), -1, "metadata"
  )
  if meta_block is not None:
    meta_start, meta_end, metadata_indent = meta_block
    meta_body = doc_lines[meta_start + 1 : meta_end]
    meta_body = _upsert_metadata_map_key(
        meta_body,
        metadata_indent,
        "labels",
        "registry.gke.io/functional-type",
        functional_type,
    )
    meta_body = _upsert_metadata_map_key(
        meta_body,
        metadata_indent,
        "annotations",
        "apphub.cloud.google.com/functional-type",
        functional_type,
    )
    doc_lines = doc_lines[: meta_start + 1] + meta_body + doc_lines[meta_end:]
  else:
    kind_idx = next(
        idx
        for idx, line in enumerate(doc_lines)
        if _is_top_level_deployment_line(line)
    )
    new_top_meta = [
        "metadata:",
        "  labels:",
        f'    registry.gke.io/functional-type: "{functional_type}"',
        "  annotations:",
        f'    apphub.cloud.google.com/functional-type: "{functional_type}"',
    ]
    doc_lines = (
        doc_lines[: kind_idx + 1] + new_top_meta + doc_lines[kind_idx + 1 :]
    )

  doc_lines, spec_block = _find_and_expand_child_block(
      doc_lines, 0, len(doc_lines), -1, "spec"
  )
  if spec_block is not None:
    spec_start, spec_end, spec_indent = spec_block
    doc_lines, template_block = _find_and_expand_child_block(
        doc_lines, spec_start + 1, spec_end, spec_indent, "template"
    )
    if template_block is not None:
      template_start, template_end, template_indent = template_block
      doc_lines, pod_meta_block = _find_and_expand_child_block(
          doc_lines,
          template_start + 1,
          template_end,
          template_indent,
          "metadata",
      )
      if pod_meta_block is not None:
        pod_meta_start, pod_meta_end, pod_meta_indent = pod_meta_block
        pod_meta_body = doc_lines[pod_meta_start + 1 : pod_meta_end]
        pod_meta_body = _upsert_metadata_map_key(
            pod_meta_body,
            pod_meta_indent,
            "annotations",
            "iam.gke.io/spiffe-identity-type",
            "agent-identity",
        )
        doc_lines = (
            doc_lines[: pod_meta_start + 1]
            + pod_meta_body
            + doc_lines[pod_meta_end:]
        )
      else:
        template_child_indent = template_indent + 2
        for idx in range(template_start + 1, template_end):
          stripped = doc_lines[idx].strip()
          if not stripped or stripped.startswith("#"):
            continue
          indent = len(doc_lines[idx]) - len(doc_lines[idx].lstrip())
          if indent > template_indent:
            template_child_indent = indent
          break
        new_pod_meta = [
            " " * template_child_indent + "metadata:",
            " " * (template_child_indent + 2) + "annotations:",
            " " * (template_child_indent + 4)
            + 'iam.gke.io/spiffe-identity-type: "agent-identity"',
        ]
        doc_lines = (
            doc_lines[: template_start + 1]
            + new_pod_meta
            + doc_lines[template_start + 1 :]
        )

  return doc_lines


def process_yaml(content: str, functional_type: str) -> str:
  """Updates all Deployment documents in a multi-document YAML string.

  Args:
    content: Raw YAML string containing one or more Kubernetes documents.
    functional_type: Functional type to set ('AGENT' or 'MCP_SERVER').

  Returns:
    The updated YAML string.
  """
  lines = content.split("\n")
  result_lines: list[str] = []
  current_doc: list[str] = []

  for line in lines:
    if _YAML_DOC_BOUNDARY_RE.match(line):
      if current_doc:
        result_lines.extend(_process_single_doc(current_doc, functional_type))
        current_doc = []
      result_lines.append(line)
    else:
      current_doc.append(line)

  if current_doc:
    result_lines.extend(_process_single_doc(current_doc, functional_type))

  return "\n".join(result_lines)


def process_file(
    filepath: str, functional_type: str, dry_run: bool = False
) -> bool:
  """Processes a single YAML file and writes changes unless dry_run is True.

  Args:
    filepath: Path to the YAML file on disk.
    functional_type: Functional type to set ('AGENT' or 'MCP_SERVER').
    dry_run: If True, previews changes without writing to disk.

  Returns:
    True if the file was processed without errors, False otherwise.
  """
  try:
    with open(filepath, "r", encoding="utf-8") as f:
      content = f.read()

    has_deployment = any(
        _is_top_level_deployment_line(line) for line in content.splitlines()
    )
    if has_deployment:
      updated_content = process_yaml(content, functional_type)

      if content != updated_content:
        if dry_run:
          print(f"[DRY RUN] Would update {filepath}")
        else:
          with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated_content)
          print(f"Successfully updated {filepath}")
      else:
        print(
            f"No changes needed for {filepath} (Labels/annotations already"
            " exist)"
        )
    else:
      print(f"Skipping {filepath} (no Deployment found)")
    return True
  except (OSError, ValueError) as e:
    print(f"Error processing {filepath}: {e}", file=sys.stderr)
    return False


def process_directory(
    directory: str, functional_type: str, dry_run: bool = False
) -> None:
  """Recursively processes all .yaml and .yml files in a directory.

  Args:
    directory: Root directory path to scan.
    functional_type: Functional type to set ('AGENT' or 'MCP_SERVER').
    dry_run: If True, previews changes without writing to disk.
  """
  if not os.path.isdir(directory):
    print(f"Error: Directory '{directory}' does not exist.", file=sys.stderr)
    sys.exit(1)

  all_ok = True
  for root, dirnames, files in os.walk(directory):
    dirnames[:] = sorted(
        d for d in dirnames if not d.startswith(".") and d != "node_modules"
    )
    for file in sorted(files):
      if file.endswith(".yaml") or file.endswith(".yml"):
        filepath = os.path.join(root, file)
        print(f"Processing {filepath}...")
        if not process_file(filepath, functional_type, dry_run=dry_run):
          all_ok = False
  if not all_ok:
    sys.exit(1)


def main() -> None:
  """CLI entrypoint for annotating GKE Deployment manifests."""
  parser = argparse.ArgumentParser(
      description=(
          "Configure GKE Deployment YAML files for Agent Registry automatic"
          " discovery (sets registry.gke.io/functional-type label,"
          " apphub.cloud.google.com/functional-type annotation, and Pod"
          " template iam.gke.io/spiffe-identity-type annotation)."
      )
  )
  parser.add_argument(
      "path",
      help="YAML file or directory of YAML files to process",
  )
  parser.add_argument(
      "--type",
      "-t",
      choices=["AGENT", "MCP_SERVER"],
      required=True,
      help="The functional type to set (AGENT or MCP_SERVER)",
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help="Preview changes without modifying files on disk",
  )

  args = parser.parse_args()

  path = os.path.abspath(args.path)
  if not os.path.exists(path):
    print(f"Error: Path '{path}' does not exist.", file=sys.stderr)
    sys.exit(1)

  print(f"Setting functional type: {args.type}")

  if os.path.isfile(path):
    if path.endswith(".yaml") or path.endswith(".yml"):
      print(f"Processing file: {path}")
      if not process_file(path, args.type, dry_run=args.dry_run):
        sys.exit(1)
    else:
      print(f"Error: File '{path}' is not a YAML file.", file=sys.stderr)
      sys.exit(1)
  elif os.path.isdir(path):
    print(f"Scanning directory: {path}")
    process_directory(path, args.type, dry_run=args.dry_run)
  else:
    print(
        f"Error: Path '{path}' is neither a regular file nor a directory.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
  main()
