#!/bin/bash
# Validate Cloud Logging LQL queries used in SKILL.md

set -e

if [ -z "${PROJECT_ID:-}" ]; then
  echo "Error: PROJECT_ID environment variable must be set explicitly." >&2
  exit 1
fi

echo "Using project: $PROJECT_ID"

echo "No Cloud Logging LQL queries defined in this skill to validate."
echo "✅ Validation skipped (no queries)."
