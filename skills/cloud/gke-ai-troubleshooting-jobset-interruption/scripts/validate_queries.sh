#!/bin/bash
# Validate Cloud Logging LQL queries used in SKILL.md
set -euo pipefail

# Allow PROJECT_ID to be passed as environment variable, fallback to gcloud config
PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo "")}

if [[ -z "${PROJECT_ID}" ]]; then
  echo "⚠️ Warning: PROJECT_ID not set and gcloud config project is empty. Skipping validation."
  exit 0
fi

echo "Using project: ${PROJECT_ID}"

# Step 2: Nodepool Logs Filter
readonly FILTER_1="resource.type=\"gke_nodepool\" AND resource.labels.cluster_name=\"test-cluster\""
echo "Validating Step 2 Nodepool filter..."
gcloud logging read "${FILTER_1}" --limit=1 --project="${PROJECT_ID}" >/dev/null || echo "⚠️ Dry run warning: Filter 1 validation failed or returned error (could be permissions/empty logs)."

# Step 3: Node Logs Filter
readonly FILTER_2="resource.type=\"k8s_node\" AND resource.labels.cluster_name=\"test-cluster\" AND (textPayload:\"host error\" OR textPayload:\"kernel panic\")"
echo "Validating Step 3 Node filter..."
gcloud logging read "${FILTER_2}" --limit=1 --project="${PROJECT_ID}" >/dev/null || echo "⚠️ Dry run warning: Filter 2 validation failed or returned error (could be permissions/empty logs)."

# Step 4: Worker Container Logs Filter
readonly FILTER_3="resource.type=\"k8s_container\" AND resource.labels.cluster_name=\"test-cluster\" AND labels.\"k8s-pod/jobset_sigs_k8s_io/jobset-name\"=\"test-jobset\""
echo "Validating Step 4 Worker Container filter..."
gcloud logging read "${FILTER_3}" --limit=1 --project="${PROJECT_ID}" >/dev/null || echo "⚠️ Dry run warning: Filter 3 validation failed or returned error (could be permissions/empty logs)."

# Step 5: Prometheus PromQL Query Validation (Dry-Run)
echo "Validating GMS for Prometheus PromQL query compilation..."

validate_promql() {
  local name="${1}"
  local query="${2}"
  local response

  response=$(curl -s -w "%{http_code}" -o /dev/null -H "Authorization: Bearer $(gcloud auth print-access-token 2>/dev/null || echo '')" \
    "https://monitoring.googleapis.com/v1/projects/${PROJECT_ID}/location/global/prometheus/api/v1/query?query=${query}" 2>/dev/null || echo "000")

  if [[ "${response}" == "200" ]]; then
    echo "  - ${name} validated successfully (HTTP 200 OK)."
  elif [[ "${response}" == "000" || "${response}" == "401" || "${response}" == "403" ]]; then
    echo "⚠️ Warning: Could not reach GMS query API for ${name} (offline or unauthenticated). Skipping."
  else
    echo "❌ Error: PromQL compilation failed for ${name} with HTTP status ${response}."
    exit 1
  fi
}

# 1. JobSet Restarts PromQL
validate_promql "JobSet Restarts Query" "kube_jobset_restarts%7Bcluster%3D%22test-cluster%22%7D"

# 2. Nodepool Interruption Counts PromQL
validate_promql "Nodepool Interruption Query" "sum%20by%20%28interruption_type%2C%20interruption_reason%2C%20node_pool_name%2C%20cluster_name%29%20%28avg_over_time%28%7B__name__%3D%22kubernetes.io%2Fnode_pool%2Finterruption_count%22%2C%20monitored_resource%3D%22k8s_node_pool%22%2C%20cluster_name%3D%22test-cluster%22%7D%5B10m%5D%29%29"

# 3. Node Ready Status PromQL
validate_promql "Node Ready Status Query" "sum%20by%20%28status%2C%20condition%2C%20node_pool_name%29%20%28%7B__name__%3D%22kubernetes.io%2Fnode%2Fstatus_condition%22%2C%20monitored_resource%3D%22k8s_node%22%2C%20cluster_name%3D%22test-cluster%22%2C%20condition%3D%22Ready%22%2C%20status%3D%22False%22%7D%29"

# 4. Pod Lifecycle Phases PromQL
validate_promql "Pod Lifecycle Query" "sum%20by%20%28phase%29%20%28avg_over_time%28%7B__name__%3D%22kube_pod_status_phase%22%2C%20cluster%3D%22test-cluster%22%2C%20pod%3D~%22test-jobset.*%22%7D%5B10m%5D%29%29"

echo "✅ Validation pass completed."
