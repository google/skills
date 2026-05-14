"""Validates that required environment variables are set."""

import os
import sys


def validate_env():
  print("Validating core environment variables...")
  required = ["GCP_PROJECT_ID", "GCP_LOCATION"]
  missing = [v for v in required if not os.environ.get(v)]
  if missing:
    print(f"ERROR: Missing core variables: {', '.join(missing)}")
    sys.exit(1)
  print("SUCCESS: Core environment validated.")


if __name__ == "__main__":
  validate_env()
