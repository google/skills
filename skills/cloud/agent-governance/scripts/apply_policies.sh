#!/usr/bin/env bash
# apply_policies.sh
# Applies FinOps cost-tracking labels and governance policies to agent resources.

set -euo pipefail

SERVICE_NAME="${1:-}"
AGENT_ID="${2:-}"
BU="${3:-}"
ENV="${4:-}"
REGION="${5:-us-central1}"
PROJECT_ID="${6:-}"

if [[ -z "$SERVICE_NAME" || -z "$AGENT_ID" || -z "$BU" || -z "$ENV" || -z "$PROJECT_ID" ]]; then
    echo "Usage: $0 <SERVICE_NAME> <AGENT_ID> <BUSINESS_UNIT> <ENVIRONMENT> <REGION> <PROJECT_ID>"
    exit 1
fi

echo "[*] Applying FinOps Labels to Cloud Run Service: $SERVICE_NAME..."
gcloud run services update "$SERVICE_NAME" \
    --update-labels="agent-id=${AGENT_ID},business-unit=${BU},environment=${ENV}" \
    --region="$REGION" \
    --project="$PROJECT_ID"

echo "[+] Labels successfully applied."
