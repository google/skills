#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -euo pipefail

echo "========================================="
echo "🛠️  Deploying Agent Platform Governance..."
echo "========================================="

# Validate essential inputs
if [[ -z "${PROJECT_ID:-}" || -z "${LOCATION_ID:-}" ]]; then
  echo "❌ Error: PROJECT_ID and LOCATION_ID environment variables must be defined."
  exit 1
fi

echo "✅ Context confirmed: Project = $PROJECT_ID, Region = $LOCATION_ID"

# Step 1: Initialize Model Armor Template
echo "Applying safety filters via Model Armor..."
if [[ -f "ma-template.yaml" ]]; then
  gcloud model-armor policies import agent-safety-policy \
      --source=ma-template.yaml \
      --location="$LOCATION_ID" \
      --project="$PROJECT_ID"
  echo "✅ Model Armor Policy applied successfully."
else
  echo "⚠️ Warning: ma-template.yaml not found. Skipping Model Armor deployment."
fi

# Step 2: Set IAP policy
echo "Checking IAP web configurations..."
if [[ -f "iap-policy.json" ]]; then
  gcloud iap web set-iam-policy iap-policy.json \
      --resource-type=AgentRegistryResource \
      --project="$PROJECT_ID"
  echo "✅ Gateway access controls applied successfully."
else
  echo "ℹ️ Note: iap-policy.json not configured. Policy unchanged."
fi

echo "========================================="
echo "🎉 Agent Governance deployment complete!"
echo "========================================="
