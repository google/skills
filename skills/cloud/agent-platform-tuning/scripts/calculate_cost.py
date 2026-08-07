"""Calculate tuning cost for a given dataset and model."""

import argparse
import json
import sys
from typing import TextIO

from google.cloud import storage

# Data from
# https://docs.google.com/spreadsheets/d/1pOXzfQBSCaKJYcemvRKv4b30qmUBx3yG28yScH-pnVI/edit?resourcekey=0-0kJGshytd3yrxB41YM4OFg&gid=0#gid=0
MODEL_DATA = {
    'Gemma 3 1B IT': {
        'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 0.47},
    },
    'Gemma 3 4B IT': {
        'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 1.14},
    },
    'Gemma 3 12B IT': {
        'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 1.82},
    },
    'Gemma 3 27B IT': {
        'PEFT': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 6.83},
        'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 6.83},
    },
    'Llama 3.1 8B': {
        'PEFT': {'tokens_per_character': 0.317, 'cost_per_1m_tokens': 0.67},
        'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.67},
    },
    'Llama 3.1 8B Instruct': {
        'PEFT': {'tokens_per_character': 0.317, 'cost_per_1m_tokens': 0.67},
        'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.67},
    },
    'Llama 3.2 1B Instruct': {
        'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.28},
    },
    'Llama 3.2 3B Instruct': {
        'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.61},
    },
    'Llama 3.3 70B Instruct': {
        'PEFT': {'tokens_per_character': 0.317, 'cost_per_1m_tokens': 6.72},
        'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 6.72},
    },
    'Llama 4 Scout 17B 16E': {
        'PEFT': {'tokens_per_character': 0.295, 'cost_per_1m_tokens': 5.77},
    },
    'Qwen 3 4B': {
        'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 1.35},
    },
    'Qwen 3 8B': {
        'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 4.18},
    },
    'Qwen 3 14B': {
        'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 8.46},
    },
    'Qwen 3 32B': {
        'PEFT': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 6.57},
        'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 6.57},
    },
}


def _open_jsonl(input_file: str) -> TextIO:
  """Opens a local or ``gs://`` jsonl file for streaming text reads.

  Args:
    input_file: A local filesystem path or a ``gs://bucket/object`` URI.

  Returns:
    An open text-mode file object; the caller is responsible for closing it.

  Raises:
    ValueError: If the path uses a scheme other than ``gs://``, or is a
      malformed ``gs://`` URI.
  """
  if input_file.startswith('gs://'):
    bucket_name, _, blob_name = input_file[len('gs://') :].partition('/')
    if not bucket_name or not blob_name:
      raise ValueError(
          f'Malformed GCS path: {input_file}. Expected gs://<bucket>/<object>.'
      )
    return storage.Client().bucket(bucket_name).blob(blob_name).open('r')
  if '://' in input_file:
    raise ValueError(
        f'Unsupported file path: {input_file}. '
        'Only local paths and gs:// paths are supported.'
    )
  return open(input_file, 'r')


def count_characters(input_file: str) -> int:
  """Counts the characters in a jsonl dataset.

  It is expected that each line in the jsonl file is a json object
  with a "messages" key, which is a list of dictionaries. Each
  dictionary in the "messages" list should have a "content" key.
  This function counts the characters in the "content" field of each
  dictionary in the "messages" list.

  Args:
    input_file: Path to the input jsonl file.

  Returns:
    Total character count.
  """
  total_character_count = 0
  with _open_jsonl(input_file) as f:
    for line in f:
      data = json.loads(line)
      for message in data['messages']:
        content = message['content']
        total_character_count += len(content)
  return total_character_count


def calculate_cost(
    count: int,
    model: str,
    tuning_mode: str,
    epochs: int,
) -> float:
  """Calculates the tuning cost.

  Args:
    count: Total character count of the dataset.
    model: Model to use for tuning.
    tuning_mode: Tuning mode.
    epochs: Number of epochs.

  Returns:
    Estimated tuning cost.
  """
  model_data = MODEL_DATA[model][tuning_mode]
  tokens_per_character = model_data['tokens_per_character']
  cost_per_1m_tokens = model_data['cost_per_1m_tokens']
  num_tokens = count * tokens_per_character * epochs
  return (num_tokens / 1000000) * cost_per_1m_tokens


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='Calculate tuning cost for a given dataset and model.'
  )
  parser.add_argument('--input', help='Input jsonl file.', required=True)
  parser.add_argument(
      '--model',
      help='Model to use for tuning.',
      required=True,
      choices=MODEL_DATA.keys(),
  )
  parser.add_argument(
      '--tuning_mode',
      help='Tuning mode.',
      required=True,
      choices=['PEFT', 'Full'],
  )
  parser.add_argument(
      '--epochs',
      help='Number of epochs.',
      required=True,
      type=int,
  )
  args = parser.parse_args()

  if (
      args.model not in MODEL_DATA
      or args.tuning_mode not in MODEL_DATA[args.model]
  ):
    print(
        f'Error: Tuning mode {args.tuning_mode} not supported for model'
        f' {args.model}'
    )
    sys.exit(1)

  character_count = count_characters(args.input)
  cost = calculate_cost(
      character_count, args.model, args.tuning_mode, args.epochs
  )
  print(f'Total character count: {character_count}')
  print(f'Estimated tuning cost: ${cost:.2f}')
