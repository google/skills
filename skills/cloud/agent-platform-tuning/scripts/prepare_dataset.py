"""Module for preparing and validating datasets for Agent Platform model tuning."""

import argparse
import json
import logging
import os
import sys
from typing import Any

import datasets


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


def convert_to_jsonl(
    input_file: str,
    output_file: str,
    format_type: str,
    prompt_col: str,
    completion_col: str,
    validation_split: float | None = 0.2,
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
  """
  if not os.path.exists(input_file):
    logging.error("Input file not found: %s", input_file)
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

  for col in [prompt_col, completion_col]:
    if col not in dataset.column_names:  # pyrefly: ignore[not-iterable]
      logging.error(
          "Column '%s' not found. Available columns: %s",
          col,
          dataset.column_names,
      )
      sys.exit(1)

  # Remove rows with empty values in critical columns
  def is_valid(example):
    prompt_text = str(example[prompt_col]).strip().lower()
    completion_text = str(example[completion_col]).strip().lower()
    return (
        len(prompt_text) > 0
        and len(completion_text) > 0
        and prompt_text != "nan"
        and completion_text != "nan"
        and prompt_text != "none"
        and completion_text != "none"
    )

  initial_len = len(dataset)  # pyrefly: ignore[bad-argument-type]
  dataset = dataset.filter(is_valid)
  if len(dataset) < initial_len:  # pyrefly: ignore[bad-argument-type]
    logging.warning(
        "Dropped %d rows with empty or NaN values", initial_len - len(dataset)  # pyrefly: ignore[bad-argument-type]
    )

  def format_example(example):
    prompt_text = str(example[prompt_col])
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
      format_example, remove_columns=dataset.column_names  # pyrefly: ignore[bad-argument-type]
  )

  if validation_split and validation_split > 0:
    if not (0 < validation_split < 1):
      logging.error("validation_split must be between 0 and 1")
      sys.exit(1)

    # Use the datasets library to perform the split as requested
    split_dict = formatted_dataset.train_test_split(  # pyrefly: ignore[missing-attribute]
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
  else:
    formatted_dataset.to_json(output_file, force_ascii=False, lines=True)  # pyrefly: ignore[missing-attribute]
    logging.info(
        "Successfully saved %d examples to %s",
        len(formatted_dataset),  # pyrefly: ignore[bad-argument-type]
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
      default=0.2,
      help="Fraction of data to use for validation (e.g. 0.2)",
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
    if not all([args.input, args.prompt_col, args.completion_col]):
      logging.error(
          "--input, --prompt_col, and --completion_col are required for"
          " conversion"
      )
      sys.exit(1)
    convert_to_jsonl(
        args.input,
        args.output,
        args.format,
        args.prompt_col,
        args.completion_col,
        args.validation_split,
    )
