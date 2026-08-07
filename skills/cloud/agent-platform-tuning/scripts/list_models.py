"""Lists Model Garden base model IDs for the tuning skill. See SKILL.md."""

import argparse
import json
import sys

import vertexai  # pyrefly: ignore[missing-import]
from vertexai import model_garden  # pyrefly: ignore[missing-import]

_TOP_K = 20


def list_model_ids(
    project: str, location: str, model_filter: str = ""
) -> dict[str, object]:
  """Returns up to `_TOP_K` Model Garden IDs matching `model_filter`."""
  vertexai.init(project=project, location=location)
  models = model_garden.list_models(model_filter=model_filter)
  selected = models[:_TOP_K]
  return {
      "models": selected,
      "total_count": len(models),
      "truncated": len(models) > len(selected),
  }


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--project", required=True)
  parser.add_argument("--location", default="us-central1")
  parser.add_argument("--filter", dest="model_filter", default="")
  args = parser.parse_args()
  json.dump(list_model_ids(**vars(args)), sys.stdout, indent=2)
  sys.stdout.write("\n")
