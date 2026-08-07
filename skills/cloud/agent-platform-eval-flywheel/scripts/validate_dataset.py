#!/usr/bin/env python3
"""Validate an evaluation dataset for Agent Platform Eval SDK compatibility.

Checks structural compliance with the EvaluationDataset schema,
required fields per metric type, and common formatting mistakes.

Usage:
  python validate_dataset.py --dataset dataset.json
  python validate_dataset.py --dataset dataset.json --metrics
  hallucination,multi_turn_task_success

Metric names are the unversioned form (the SDK resolves them to the latest
version). Pinned versions (e.g., general_quality_v1) are also accepted.

Exit codes: 0 = valid, 1 = invalid (with specific errors).
"""

import argparse
import json
import sys
from typing import Any

_SINGLE_TURN_METRICS = frozenset({
    "general_quality",
    "text_quality",
    "instruction_following",
    "grounding",
    "safety",
    "hallucination",
    "tool_use_quality",
    "final_response_reference_free",
    "final_response_quality",
})
_MULTI_TURN_METRICS = frozenset({
    "multi_turn_tool_use_quality",
    "multi_turn_trajectory_quality",
    "multi_turn_task_success",
    "multi_turn_general_quality",
    "multi_turn_text_quality",
})
_COMPUTATION_METRICS = frozenset({
    "bleu",
    "rouge_1",
    "rouge_l_sum",
})


_VALID_ROLES = frozenset({"user", "model", "tool"})


def _canonical_metric(name: str) -> str:
  """Strip a trailing _v<N> version suffix so versioned IDs match the sets."""
  parts = name.rsplit("_v", 1)
  if len(parts) == 2 and parts[1].isdigit():
    return parts[0]
  return name


class ValidationError:
  """A single validation error with location context."""

  def __init__(self, path: str, message: str, severity: str = "ERROR"):
    self.path = path
    self.message = message
    self.severity = severity

  def __str__(self):
    return f"[{self.severity}] {self.path}: {self.message}"


def _validate_content(content: Any, path: str) -> list[ValidationError]:
  """Validate a genai Content object."""
  errors = []
  if not isinstance(content, dict):
    errors.append(
        ValidationError(path, f"Expected dict, got {type(content).__name__}")
    )
    return errors

  role = content.get("role")
  if role and role not in _VALID_ROLES:
    errors.append(
        ValidationError(
            f"{path}.role",
            f"Invalid role '{role}'. Must be one of:"
            f" {', '.join(sorted(_VALID_ROLES))}",
        )
    )
  if role == "assistant":
    errors.append(
        ValidationError(
            f"{path}.role",
            "Use 'model' instead of 'assistant' (Agent Platform convention).",
        )
    )

  parts = content.get("parts")
  if parts is None:
    errors.append(ValidationError(f"{path}.parts", "Missing 'parts' field."))
  elif not isinstance(parts, list):
    errors.append(ValidationError(f"{path}.parts", "Must be a list."))
  elif not parts:
    errors.append(
        ValidationError(
            f"{path}.parts",
            "Empty parts list.",
            severity="WARNING",
        )
    )

  return errors


def _validate_agent_event(event: Any, path: str) -> list[ValidationError]:
  """Validate an AgentEvent object."""
  errors = []
  if not isinstance(event, dict):
    errors.append(
        ValidationError(path, f"Expected dict, got {type(event).__name__}")
    )
    return errors

  if "author" not in event:
    errors.append(ValidationError(f"{path}", "Missing 'author' field."))

  content = event.get("content")
  if content is None:
    errors.append(ValidationError(f"{path}", "Missing 'content' field."))
  else:
    errors.extend(_validate_content(content, f"{path}.content"))

  return errors


def _validate_turn(turn: Any, path: str) -> list[ValidationError]:
  """Validate a ConversationTurn object."""
  errors = []
  if not isinstance(turn, dict):
    errors.append(
        ValidationError(path, f"Expected dict, got {type(turn).__name__}")
    )
    return errors

  if "turn_index" not in turn and "turnIndex" not in turn:
    errors.append(ValidationError(f"{path}", "Missing 'turn_index' field."))

  events = turn.get("events")
  if events is None:
    errors.append(ValidationError(f"{path}", "Missing 'events' field."))
  elif not isinstance(events, list):
    errors.append(ValidationError(f"{path}.events", "Must be a list."))
  elif not events:
    errors.append(ValidationError(f"{path}.events", "Empty events list."))
  else:
    for i, event in enumerate(events):
      errors.extend(_validate_agent_event(event, f"{path}.events[{i}]"))

  return errors


def _validate_agent_data(agent_data: Any, path: str) -> list[ValidationError]:
  """Validate an AgentData object."""
  errors = []
  if not isinstance(agent_data, dict):
    errors.append(
        ValidationError(path, f"Expected dict, got {type(agent_data).__name__}")
    )
    return errors

  agents = agent_data.get("agents")
  if agents is None:
    errors.append(ValidationError(f"{path}", "Missing 'agents' field."))
  elif not isinstance(agents, dict):
    errors.append(ValidationError(f"{path}.agents", "Must be a dict."))
  elif not agents:
    errors.append(ValidationError(f"{path}.agents", "Empty agents map."))
  else:
    for agent_id, config in agents.items():
      if not isinstance(config, dict):
        errors.append(
            ValidationError(
                f"{path}.agents.{agent_id}",
                f"Expected dict, got {type(config).__name__}",
            )
        )
      elif "agent_id" not in config and "agentId" not in config:
        errors.append(
            ValidationError(
                f"{path}.agents.{agent_id}",
                "Missing 'agent_id' field.",
                severity="WARNING",
            )
        )

  turns = agent_data.get("turns")
  if turns is None:
    errors.append(ValidationError(f"{path}", "Missing 'turns' field."))
  elif not isinstance(turns, list):
    errors.append(ValidationError(f"{path}.turns", "Must be a list."))
  elif not turns:
    errors.append(ValidationError(f"{path}.turns", "Empty turns list."))
  else:
    for i, turn in enumerate(turns):
      errors.extend(_validate_turn(turn, f"{path}.turns[{i}]"))

    indices = []
    for turn in turns:
      idx = turn.get("turn_index", turn.get("turnIndex"))
      if idx is not None:
        indices.append(idx)
    if indices and indices != list(range(len(indices))):
      errors.append(
          ValidationError(
              f"{path}.turns",
              f"turn_index values are not sequential 0-based: {indices}",
              severity="WARNING",
          )
      )

  return errors


def _validate_eval_case(
    case: Any, index: int, metrics: list[str] | None
) -> list[ValidationError]:
  """Validate a single EvalCase.

  Args:
    case: The eval case to validate, expected to be a dict.
    index: Position of the case in the dataset, used in error paths.
    metrics: Metric names the dataset will be evaluated against, or None.

  Returns:
    The validation errors found, empty if the case is well-formed.
  """
  path = f"eval_cases[{index}]"
  errors = []

  if not isinstance(case, dict):
    errors.append(
        ValidationError(path, f"Expected dict, got {type(case).__name__}")
    )
    return errors

  has_prompt = "prompt" in case
  has_agent_data = "agent_data" in case or "agentData" in case
  has_reference = "reference" in case

  if not has_prompt and not has_agent_data:
    errors.append(
        ValidationError(
            path,
            "Must have either 'prompt' (single-turn) or 'agent_data'"
            " (multi-turn).",
        )
    )

  if has_prompt and has_agent_data:
    errors.append(
        ValidationError(
            path,
            "Has both 'prompt' and 'agent_data'. Use one or the other.",
            severity="WARNING",
        )
    )

  if has_agent_data:
    ad = case.get("agent_data") or case.get("agentData")
    errors.extend(_validate_agent_data(ad, f"{path}.agent_data"))

  if metrics:
    for raw_metric in metrics:
      metric = _canonical_metric(raw_metric)
      if (
          metric in _SINGLE_TURN_METRICS
          and not has_prompt
          and not has_agent_data
      ):
        errors.append(
            ValidationError(
                path,
                f"Metric '{metric}' requires 'prompt' and 'response' fields.",
            )
        )
      if metric in _MULTI_TURN_METRICS and not has_agent_data:
        errors.append(
            ValidationError(
                path,
                f"Metric '{metric}' requires 'agent_data' with conversation"
                " turns.",
            )
        )
      if metric in _COMPUTATION_METRICS and not has_reference:
        errors.append(
            ValidationError(
                path,
                f"Metric '{metric}' requires a 'reference' field.",
                severity="WARNING",
            )
        )

  return errors


def validate_dataset(
    dataset: dict[str, Any], metrics: list[str] | None = None
) -> list[ValidationError]:
  """Validate an entire EvaluationDataset."""
  errors = []

  if not isinstance(dataset, dict):
    errors.append(
        ValidationError("root", f"Expected dict, got {type(dataset).__name__}")
    )
    return errors

  eval_cases = dataset.get("eval_cases")
  if eval_cases is None:
    errors.append(ValidationError("root", "Missing 'eval_cases' field."))
    return errors

  if not isinstance(eval_cases, list):
    errors.append(ValidationError("eval_cases", "Must be a list."))
    return errors

  if not eval_cases:
    errors.append(ValidationError("eval_cases", "Empty eval_cases list."))
    return errors

  for i, case in enumerate(eval_cases):
    errors.extend(_validate_eval_case(case, i, metrics))

  return errors


def main():
  parser = argparse.ArgumentParser(
      description="Validate an evaluation dataset for Agent Platform Eval SDK."
  )
  parser.add_argument(
      "--dataset",
      "-d",
      required=True,
      help="Path to the evaluation dataset JSON file.",
  )
  parser.add_argument(
      "--metrics",
      "-m",
      help="Comma-separated list of metrics to validate against.",
  )
  args = parser.parse_args()

  try:
    with open(args.dataset) as f:
      dataset = json.load(f)
  except FileNotFoundError:
    print(f"ERROR: File not found: {args.dataset}", file=sys.stderr)
    sys.exit(1)
  except json.JSONDecodeError as e:
    print(f"ERROR: Invalid JSON in {args.dataset}: {e}", file=sys.stderr)
    sys.exit(1)

  metrics = args.metrics.split(",") if args.metrics else None

  errors = validate_dataset(dataset, metrics)

  n_cases = len(dataset.get("eval_cases", []))
  real_errors = [e for e in errors if e.severity == "ERROR"]
  warnings = [e for e in errors if e.severity == "WARNING"]

  print(f"Dataset: {args.dataset}")
  print(f"Eval cases: {n_cases}")
  if metrics:
    print(f"Validating against metrics: {', '.join(metrics)}")
  print()

  if real_errors:
    print(f"ERRORS ({len(real_errors)}):")
    for e in real_errors:
      print(f"  {e}")
    print()

  if warnings:
    print(f"WARNINGS ({len(warnings)}):")
    for w in warnings:
      print(f"  {w}")
    print()

  if not real_errors and not warnings:
    print("VALID: No issues found.")

  if real_errors:
    sys.exit(1)


if __name__ == "__main__":
  main()
