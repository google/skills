"""Calculate tuning cost for a given dataset and model."""

import argparse
import json
import re
import sys
from typing import Any, TextIO

from google.cloud import storage

# Keyed by the publisher model resource name, the identifier --base_model
# requires and the one references/models.md tells the agent to copy verbatim.
# display_name is the label that table lists it under, kept here so errors can
# name a model the way the docs do; both spellings resolve through
# resolve_model().
#
# The catalog is wider than the price table: an entry with no modes is offered
# for tuning but has no published SKU yet, a routine state worth telling apart
# from an identifier that does not exist.
#
# cost_per_1m_tokens mirrors the public Model Tuning price table:
# https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing#model-tuning
#
# tokens_per_character is the empirical ratio of billed training tokens to
# dataset characters as counted by count_characters() below, so it absorbs
# chat template overhead. It is measured per tuning mode: PEFT and Full run
# different training containers, so the same dataset can bill a different
# number of tokens in each mode. Do not assume the two modes of a model
# share a value. It is not published anywhere: unlike the price, it has to be
# measured, and the authoritative billable token count is only reported by the
# tuning service after a job completes, which is too late to estimate from.
MODEL_DATA: dict[str, dict[str, Any]] = {
    'google/gemma4@gemma-4-e2b-it': {
        'display_name': 'Gemma 4 E2B IT',
        'modes': {
            'PEFT': {'tokens_per_character': 0.236, 'cost_per_1m_tokens': 1.40},
        },
    },
    'google/gemma4@gemma-4-e4b-it': {
        'display_name': 'Gemma 4 E4B IT',
        'modes': {
            'PEFT': {'tokens_per_character': 0.236, 'cost_per_1m_tokens': 1.73},
        },
    },
    'google/gemma4@gemma-4-26b-a4b-it': {
        'display_name': 'Gemma 4 26B A4B IT',
        'modes': {
            'PEFT': {'tokens_per_character': 0.236, 'cost_per_1m_tokens': 2.58},
        },
    },
    'google/gemma4@gemma-4-31b-it': {
        'display_name': 'Gemma 4 31B IT',
        'modes': {
            'PEFT': {'tokens_per_character': 0.236, 'cost_per_1m_tokens': 9.06},
        },
    },
    'google/gemma3@gemma-3-1b-it': {
        'display_name': 'Gemma 3 1B IT',
        'modes': {
            'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 0.47},
        },
    },
    'google/gemma3@gemma-3-4b-it': {
        'display_name': 'Gemma 3 4B IT',
        'modes': {
            'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 1.14},
        },
    },
    'google/gemma3@gemma-3-12b-it': {
        'display_name': 'Gemma 3 12B IT',
        'modes': {
            'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 1.82},
        },
    },
    'google/gemma3@gemma-3-27b-it': {
        'display_name': 'Gemma 3 27B IT',
        'modes': {
            'PEFT': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 6.83},
            'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 6.83},
        },
    },
    'google/medgemma@medgemma-1.5-4b-it': {
        'display_name': 'Medgemma 1.5 4B IT',
        'modes': {
            'Full': {'tokens_per_character': 0.231, 'cost_per_1m_tokens': 1.14},
        },
    },
    'meta/llama3_1@llama-3.1-8b': {
        'display_name': 'Llama 3.1 8B',
        'modes': {
            'PEFT': {'tokens_per_character': 0.317, 'cost_per_1m_tokens': 0.67},
            'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.67},
        },
    },
    'meta/llama3_1@llama-3.1-8b-instruct': {
        'display_name': 'Llama 3.1 8B Instruct',
        'modes': {
            'PEFT': {'tokens_per_character': 0.317, 'cost_per_1m_tokens': 0.67},
            'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.67},
        },
    },
    'meta/llama3-2@llama-3.2-1b-instruct': {
        'display_name': 'Llama 3.2 1B Instruct',
        'modes': {
            'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.28},
        },
    },
    'meta/llama3-2@llama-3.2-3b-instruct': {
        'display_name': 'Llama 3.2 3B Instruct',
        'modes': {
            'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.61},
        },
    },
    'meta/llama3-3@llama-3.3-70b-instruct': {
        'display_name': 'Llama 3.3 70B Instruct',
        'modes': {
            'PEFT': {'tokens_per_character': 0.317, 'cost_per_1m_tokens': 6.72},
            'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 6.72},
        },
    },
    'meta/llama4@llama-4-scout-17b-16e-instruct': {
        'display_name': 'Llama 4 Scout 17B 16E Instruct',
        'modes': {
            'PEFT': {'tokens_per_character': 0.295, 'cost_per_1m_tokens': 5.77},
        },
    },
    'qwen/qwen3.8@qwen3.8-27b': {
        'display_name': 'Qwen 3.8 27B',
        'modes': {
            'PEFT': {'tokens_per_character': 0.290, 'cost_per_1m_tokens': 3.69},
        },
    },
    'qwen/qwen3-6@qwen3.6-27b': {
        'display_name': 'Qwen 3.6 27B',
        'modes': {
            'PEFT': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 4.42},
        },
    },
    'qwen/qwen3-6@qwen3.6-35b-a3b': {
        'display_name': 'Qwen 3.6 35B A3B',
        'modes': {
            'PEFT': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 1.33},
        },
    },
    'qwen/qwen3-5@qwen3.5-9b': {
        'display_name': 'Qwen 3.5 9B',
        'modes': {
            'Full': {'tokens_per_character': 0.247, 'cost_per_1m_tokens': 0.60},
        },
    },
    'qwen/qwen3@qwen3-4b': {
        'display_name': 'Qwen 3 4B',
        'modes': {
            'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 1.35},
        },
    },
    'qwen/qwen3@qwen3-8b': {
        'display_name': 'Qwen 3 8B',
        'modes': {
            'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 4.18},
        },
    },
    'qwen/qwen3@qwen3-14b': {
        'display_name': 'Qwen 3 14B',
        'modes': {
            'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 8.46},
        },
    },
    'qwen/qwen3@qwen3-32b': {
        'display_name': 'Qwen 3 32B',
        'modes': {
            'PEFT': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 6.57},
            'Full': {'tokens_per_character': 0.246, 'cost_per_1m_tokens': 6.57},
        },
    },
    'zai-org/glm-4.7-flash@glm-4.7-flash': {
        'display_name': 'GLM 4.7 Flash',
        'modes': {
            'PEFT': {'tokens_per_character': 0.234, 'cost_per_1m_tokens': 1.50},
        },
    },
}


_LONG_RESOURCE_NAME = re.compile(r'publishers/([^/]+)/models/(.+)')


def _normalize(name: str) -> str:
  """Folds a model identifier to the key form used by _MODEL_ALIASES."""
  name = name.strip().lower()
  # models.md documents `publishers/{publisher}/models/{model}@{version}` as
  # an accepted long form of `{publisher}/{model}@{version}`.
  match = _LONG_RESOURCE_NAME.fullmatch(name)
  if match:
    name = f'{match.group(1)}/{match.group(2)}'
  return name


def _build_aliases() -> dict[str, str]:
  """Maps every accepted spelling of a model to its MODEL_DATA key."""
  aliases = {}
  for resource_name, entry in MODEL_DATA.items():
    aliases[_normalize(resource_name)] = resource_name
    aliases[_normalize(entry['display_name'])] = resource_name
  return aliases


_MODEL_ALIASES = _build_aliases()


def resolve_model(name: str) -> str | None:
  """Resolves any accepted spelling of a model to its MODEL_DATA key.

  Args:
    name: Either a display name ("Qwen 3 8B") or a publisher model resource name
      ("qwen/qwen3@qwen3-8b", optionally in the longer
      "publishers/qwen/models/qwen3@qwen3-8b" form). Matching ignores case and
      surrounding whitespace.

  Returns:
    The MODEL_DATA key, or None if the model is not in the catalog. A returned
    key is not a promise that the model is priced -- an entry with no modes is
    catalogued but has no published SKU.
  """
  return _MODEL_ALIASES.get(_normalize(name))


def _priced_model_listing() -> str:
  """Renders the priced models as indented `Display name (resource name)`."""
  return '\n'.join(
      f'  {entry["display_name"]} ({resource_name})'
      for resource_name, entry in MODEL_DATA.items()
      if entry['modes']
  )


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
      if 'messages' in data:
        for message in data['messages']:
          content = message.get('content', '') or ''
          total_character_count += len(content)
      elif 'prompt' in data:
        total_character_count += len(data.get('prompt', '') or '')
        total_character_count += len(data.get('completion', '') or '')
      elif 'input' in data:
        total_character_count += len(data.get('input', '') or '')
        total_character_count += len(data.get('output', '') or '')
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
    model: MODEL_DATA key for the model, as returned by resolve_model().
    tuning_mode: Tuning mode.
    epochs: Number of epochs.

  Returns:
    Estimated tuning cost.
  """
  model_data = MODEL_DATA[model]['modes'][tuning_mode]
  tokens_per_character = model_data['tokens_per_character']
  cost_per_1m_tokens = model_data['cost_per_1m_tokens']
  num_tokens = count * tokens_per_character * epochs
  return (num_tokens / 1000000) * cost_per_1m_tokens


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='Calculate tuning cost for a given dataset and model.'
  )
  parser.add_argument('--input', help='Input jsonl file.', required=True)
  # No choices= here on purpose. references/models.md and MODEL_DATA are two
  # hand-maintained lists that drift, and a model present in the catalog but
  # absent from the price table is a routine, expected state while a tuning
  # SKU is pending. argparse would reject it with a usage dump; the explicit
  # check below reports it in a form the caller can act on.
  parser.add_argument(
      '--model',
      help=(
          'Model to use for tuning. Accepts either the display name'
          ' ("Qwen 3 8B") or the publisher model resource name'
          ' ("qwen/qwen3@qwen3-8b") that --base_model takes.'
      ),
      required=True,
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

  resolved_model = resolve_model(args.model)

  if resolved_model is None:
    print(
        f'Error: Unrecognized model {args.model}. Pass a display name or the'
        ' publisher model resource name given to --base_model. Models with a'
        f' published tuning price:\n{_priced_model_listing()}'
    )
    sys.exit(1)

  model_entry = MODEL_DATA[resolved_model]

  if not model_entry['modes']:
    print(
        'Error: No published tuning price for model'
        f' {model_entry["display_name"]}, so its cost cannot be estimated.'
        f' Models with a published price:\n{_priced_model_listing()}'
    )
    sys.exit(1)

  if args.tuning_mode not in model_entry['modes']:
    print(
        f'Error: Tuning mode {args.tuning_mode} not supported for model'
        f' {model_entry["display_name"]}. Supported:'
        f' {", ".join(model_entry["modes"])}'
    )
    sys.exit(1)

  character_count = count_characters(args.input)
  cost = calculate_cost(
      character_count, resolved_model, args.tuning_mode, args.epochs
  )
  print(f'Total character count: {character_count}')
  print(f'Estimated tuning cost: ${cost:.2f}')
