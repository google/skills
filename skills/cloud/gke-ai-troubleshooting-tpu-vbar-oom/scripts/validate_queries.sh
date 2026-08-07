#!/bin/bash
# Validate Cloud Logging LQL queries used in SKILL.md

set -e

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: PROJECT_ID is not set and could not be determined from gcloud." >&2
  exit 1
fi
echo "Using project: ${PROJECT_ID}"

# Step 1: vbar_control_agent OOMs
FILTER_1="logName=\"projects/${PROJECT_ID}/logs/serialconsole.googleapis.com%2fserial_port_1_output\" AND SEARCH(\"Memory cgroup out of memory: Killed process\")"
echo "Validating Step 1 filter..."
gcloud logging read "${FILTER_1}" --limit=1 > /dev/null

# Step 2: tpu-device-plugin metrics fetch failures
FILTER_2="resource.type=\"k8s_container\" AND resource.labels.container_name=\"tpu-device-plugin\" AND severity=ERROR AND \"checksum didn't match with the metrics data\""
echo "Validating Step 2 filter..."
gcloud logging read "${FILTER_2}" --limit=1 > /dev/null

echo "✅ All LQL filters validated against Cloud Logging API (dry-run)."
