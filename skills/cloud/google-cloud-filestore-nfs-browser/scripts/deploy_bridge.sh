#!/usr/bin/env bash
# Deploy Serverless Cloud Run NFS Bridge for Google Cloud Filestore.
#
# Usage:
#   ./deploy_bridge.sh <PROJECT_ID> <REGION> <VPC_NETWORK> <SUBNET> <FILESTORE_IP> <FILE_SHARE_NAME>

set -euo pipefail

if [[ $# -lt 6 ]]; then
  echo "Usage: $0 <PROJECT_ID> <REGION> <VPC_NETWORK> <SUBNET> <FILESTORE_IP> <FILE_SHARE_NAME>"
  echo "Example: $0 my-gcp-proj us-central1 default default 10.0.0.2 vol1"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"
VPC_NETWORK="$3"
SUBNET="$4"
FILESTORE_IP="$5"
FILE_SHARE_NAME="$6"

SERVICE_NAME="filestore-nfs-bridge"
IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ATTRIBUTION_FILE="${SCRIPT_DIR}/../references/attribution.md"
ATTRIBUTION_TAG=""
if [[ -f "${ATTRIBUTION_FILE}" ]]; then
  ATTRIBUTION_TAG=$(sed -n 's/.*CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="\([^"]*\)".*/\1/p' "${ATTRIBUTION_FILE}" | head -n 1)
fi
if [[ -z "${ATTRIBUTION_TAG}" ]]; then
  ATTRIBUTION_TAG="agent-skills/1.0 (skill:google-cloud-filestore-nfs-browser)"
fi

echo "============================================================"
echo " Deploying Filestore NFS Bridge to Cloud Run"
echo " Project:    ${PROJECT_ID}"
echo " Region:     ${REGION}"
echo " Filestore:  ${FILESTORE_IP}:/${FILE_SHARE_NAME}"
echo "============================================================"

# 1. Build image using Cloud Build
echo "==> Building container image via Cloud Build..."
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="${ATTRIBUTION_TAG}" \
gcloud builds submit "$(dirname "$0")/bridge_server" \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE_TAG}"

# 2. Deploy to Cloud Run with Direct VPC Egress & NFS Volume Mount
echo "==> Deploying Cloud Run service with Direct VPC Egress..."
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="${ATTRIBUTION_TAG}" \
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_TAG}" \
  --network="${VPC_NETWORK}" \
  --subnet="${SUBNET}" \
  --vpc-egress=all-traffic \
  --add-volume="name=filestore-share,type=nfs,location=${FILESTORE_IP}:/${FILE_SHARE_NAME}" \
  --add-volume-mount="volume=filestore-share,mount-path=/mnt/share" \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=5 \
  --cpu=1 \
  --memory=512Mi

# 3. Retrieve and print Service URL
SERVICE_URL=$(CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="${ATTRIBUTION_TAG}" \
  gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")

echo "============================================================"
echo "✅ Cloud Run NFS Bridge deployed successfully!"
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "To use with the agent, set:"
echo "  export FILESTORE_BRIDGE_URL=\"${SERVICE_URL}\""
echo "============================================================"
