#!/bin/bash
# Validate Cloud Logging LQL queries used in SKILL.md

set -e

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo "")}

if [ -z "$PROJECT_ID" ]; then
  echo "⚠️ Warning: No GCP project configured. Skipping dry-run validation."
  echo "To validate, set the PROJECT_ID environment variable or run 'gcloud config set project <id>'."
  exit 0
fi

echo "Using project: $PROJECT_ID"

echo "No Cloud Logging LQL queries defined in this skill to validate."
echo "✅ Validation skipped (no queries)."
