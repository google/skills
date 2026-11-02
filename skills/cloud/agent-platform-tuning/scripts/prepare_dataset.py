"""Module for preparing and validating datasets for Agent Platform model tuning."""

import argparse
import json
import logging
import os
import sys
from typing import Any

# The tuning service rejects a job whose validation file exceeds this fraction
# of the training file, measured in bytes rather than rows. 0.2 is the largest
# split that satisfies it and lands exactly on the line, so the default keeps a
# margin -- see references/data_prep.md, "Sizing the validation split".
MAX_VALIDATION_RATIO = 0.25
DEFAULT_VALIDATION_SPLIT = 0.1


def _validate_example(example: dict[str, Any], format_type: str) -> bool:
  """Validates a single example against the expected format."""
  if format_type == "messages":
    if "messages" not in example or not isinstance(example["messages"], list):
      return False
    for msg in example["messages"]:
      if not all(k in msg for k in ("role", "content")):
        return False
      if not msg["content"] or str(msg["content"]).strip().lower() == "nan":
        return False
  else:
    if not all(k in example for k in ("prompt", "completion")):
      return False
    for k in ("prompt", "completion"):
      if not example[k] or str(example[k]).strip().lower() == "nan":
        return False
  return True


def _format_row(
    row, format_type: str, prompt_col: str, completion_col: str
) -> dict[str, Any]:
  """Formats a single row into the expected JSON structure."""
  prompt_text = str(row[prompt_col])
  completion_text = str(row[completion_col])

  if format_type == "messages":
    return {
        "messages": [
            {"role": "user", "content": prompt_text},
            {"role": "assistant", "content": completion_text},
        ]
    }
  return {
      "prompt": prompt_text,
      "completion": completion_text,
  }


def validate_jsonl(file_path: str, format_type: str) -> bool:
  """Validates an existing JSONL file."""
  if not os.path.exists(file_path):
    logging.error("File not found: %s", file_path)
    return False

  valid_count = 0
  invalid_count = 0
  with open(file_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
      try:
        example = json.loads(line)
        if _validate_example(example, format_type):
          valid_count += 1
        else:
          invalid_count += 1
          logging.warning("Invalid format/empty content at line %d", i + 1)
      except json.JSONDecodeError:
        invalid_count += 1
        logging.warning("Invalid JSON at line %d", i + 1)

  logging.info("Validation complete for %s", file_path)
  logging.info("Valid: %d, Invalid: %d", valid_count, invalid_count)
  return invalid_count == 0


def validation_ratio_error(train_bytes: int, val_bytes: int) -> str | None:
  """Returns a message if the written split would be rejected, else None.

  The service weighs the two files by size, so a row-count split fraction
  cannot predict the outcome; only the written bytes can.

  Args:
    train_bytes: Size of the written training file.
    val_bytes: Size of the written validation file.

  Returns:
    An actionable error message, or None if the split is within the ceiling.
  """
  if val_bytes <= MAX_VALIDATION_RATIO * train_bytes:
    return None
  ratio = val_bytes / train_bytes if train_bytes else float("inf")
  return (
      f"Validation file is {ratio:.1%} of the training file ({val_bytes} vs"
      f" {train_bytes} bytes), above the {MAX_VALIDATION_RATIO:.0%} the tuning"
      " service allows. Re-run with a smaller --validation_split"
      f" (default {DEFAULT_VALIDATION_SPLIT})."
  )


def convert_to_jsonl(
    input_file: str,
    output_file: str,
    format_type: str,
    prompt_col: str,
    completion_col: str | None,
    validation_split: float | None = None,
    prompt_only: bool = False,
):
  """Converts a file to JSONL format for Agent Platform tuning.

  Supports CSV, JSON, or Parquet files.

  Args:
    input_file: Path to the input CSV, JSON, or Parquet file.
    output_file: Path where the formatted JSONL file will be saved.
    format_type: Target format ("messages" or "prompt").
    prompt_col: Name of the column containing the prompt/user message.
    completion_col: Name of the column containing the completion/response.
    validation_split: Optional fraction of data to split for validation.
    prompt_only: Write the prompt only, as distillation training data. The
      teacher model writes the responses.
  """
  if not os.path.exists(input_file):
    logging.error("Input file not found: %s", input_file)
    sys.exit(1)

  if prompt_only:
    if format_type != "messages":
      logging.error("--prompt_only requires --format messages")
      sys.exit(1)
    if validation_split:
      # A validation file is scored against its responses, so a prompt-only
      # one is unusable; it has to come from separate data that has them.
      logging.error(
          "A prompt-only dataset can't be split for validation, because a"
          " validation file needs responses. Pass --validation_split 0 and"
          " prepare a separate validation file with responses if you want one."
      )
      sys.exit(1)
  elif not completion_col:
    logging.error("completion_col is required unless prompt_only is set")
    sys.exit(1)

  try:
    import datasets  # pylint: disable=g-import-not-at-top
  except ImportError:
    logging.error(
        "The 'datasets' package is required for format conversion. Please"
        " install it using: pip install datasets"
    )
    sys.exit(1)

  try:
    if input_file.endswith(".csv"):
      dataset = datasets.load_dataset(
          "csv", data_files=input_file, split="train"
      )
    elif input_file.endswith(".json"):
      dataset = datasets.load_dataset(
          "json", data_files=input_file, split="train"
      )
    elif input_file.endswith(".parquet"):
      dataset = datasets.load_dataset(
          "parquet", data_files=input_file, split="train"
      )
    else:
      logging.error("Unsupported file format. Use .csv, .json, or .parquet")
      sys.exit(1)
  except Exception as e:  # pylint: disable=broad-exception-caught
    logging.exception("Failed to read input file: %s", e)
    sys.exit(1)

  columns = [prompt_col] if prompt_only else [prompt_col, completion_col]
  for col in columns:
    if col not in dataset.column_names:
      logging.error(
          "Column '%s' not found. Available columns: %s",
          col,
          dataset.column_names,
      )
      sys.exit(1)

  # Remove rows with empty values in critical columns
  def is_valid(example):
    prompt_text = str(example[prompt_col]).strip().lower()
    if prompt_only:
      return prompt_text not in ("", "nan", "none")
    completion_text = str(example[completion_col]).strip().lower()
    return (
        len(prompt_text) > 0
        and len(completion_text) > 0
        and prompt_text != "nan"
        and completion_text != "nan"
        and prompt_text != "none"
        and completion_text != "none"
    )

  initial_len = len(dataset)
  dataset = dataset.filter(is_valid)
  if len(dataset) < initial_len:
    logging.warning(
        "Dropped %d rows with empty or NaN values", initial_len - len(dataset)
    )

  def format_example(example):
    prompt_text = str(example[prompt_col])
    if prompt_only:
      return {"messages": [{"role": "user", "content": prompt_text}]}
    completion_text = str(example[completion_col])
    if format_type == "messages":
      return {
          "messages": [
              {"role": "user", "content": prompt_text},
              {"role": "assistant", "content": completion_text},
          ]
      }
    else:
      return {
          "prompt": prompt_text,
          "completion": completion_text,
      }

  formatted_dataset = dataset.map(
      format_example, remove_columns=dataset.column_names
  )

  if validation_split and validation_split > 0:
    if not (0 < validation_split < 1):
      logging.error("validation_split must be between 0 and 1")
      sys.exit(1)

    # Use the datasets library to perform the split as requested
    split_dict = formatted_dataset.train_test_split(
        seed=42, test_size=validation_split
    )
    train_ds = split_dict["train"]
    val_ds = split_dict["test"]

    val_output_file = output_file.replace(".jsonl", "_validation.jsonl")
    if val_output_file == output_file:
      val_output_file = output_file + ".validation.jsonl"

    train_ds.to_json(output_file, force_ascii=False, lines=True)
    val_ds.to_json(val_output_file, force_ascii=False, lines=True)

    logging.info(
        "Successfully saved %d training examples to %s",
        len(train_ds),
        output_file,
    )
    logging.info(
        "Successfully saved %d validation examples to %s",
        len(val_ds),
        val_output_file,
    )

    # Catch an oversized validation file here rather than letting the tuning
    # service reject the job after the dataset has been uploaded to GCS.
    ratio_error = validation_ratio_error(
        os.path.getsize(output_file), os.path.getsize(val_output_file)
    )
    if ratio_error:
      logging.error("%s", ratio_error)
      sys.exit(1)
  else:
    formatted_dataset.to_json(output_file, force_ascii=False, lines=True)
    logging.info(
        "Successfully saved %d examples to %s",
        len(formatted_dataset),
        output_file,
    )


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
  parser = argparse.ArgumentParser(
      description="Prepare or Validate dataset for Agent Platform Model Tuning"
  )
  parser.add_argument(
      "--input",
      help="Input CSV, JSON, Parquet, or JSONL file",
  )
  parser.add_argument(
      "--output",
      default="tuning_dataset.jsonl",
      help="Output JSONL file (only for conversion)",
  )
  parser.add_argument(
      "--format",
      choices=["messages", "prompt"],
      default="messages",
      help="Target format (messages or prompt/completion)",
  )
  parser.add_argument(
      "--prompt_col",
      help="Column name for prompt/user message (CSV/JSON/Parquet only)",
  )
  parser.add_argument(
      "--completion_col",
      help=(
          "Column name for completion/assistant response (CSV/JSON/Parquet"
          " only)"
      ),
  )
  parser.add_argument(
      "--validation_split",
      type=float,
      help=(
          "Fraction of data to hold out for validation. Keep it at or below"
          f" {DEFAULT_VALIDATION_SPLIT}, the default; see"
          " references/data_prep.md. Defaults to 0 with --prompt_only."
      ),
  )
  parser.add_argument(
      "--prompt_only",
      action="store_true",
      help=(
          "Write prompts only, as distillation training data. Needs no"
          " --completion_col and cannot be split for validation."
      ),
  )
  parser.add_argument(
      "--validate_only",
      action="store_true",
      help="Only validate the input JSONL file without converting",
  )

  args = parser.parse_args()

  if args.validate_only:
    if not args.input:
      logging.error("--input is required for validation")
      sys.exit(1)
    success = validate_jsonl(args.input, args.format)
    sys.exit(0 if success else 1)
  else:
    if args.prompt_only:
      if not all([args.input, args.prompt_col]):
        logging.error(
            "--input and --prompt_col are required for --prompt_only"
            " conversion"
        )
        sys.exit(1)
    elif not all([args.input, args.prompt_col, args.completion_col]):
      logging.error(
          "--input, --prompt_col, and --completion_col are required for"
          " conversion"
      )
      sys.exit(1)
    if args.validation_split is None:
      args.validation_split = (
          0 if args.prompt_only else DEFAULT_VALIDATION_SPLIT
      )
    convert_to_jsonl(
        args.input,
        args.output,
        args.format,
        args.prompt_col,
        args.completion_col,
        args.validation_split,
        prompt_only=args.prompt_only,
    )
