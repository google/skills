#!/bin/bash
set -e
set -o pipefail

CLUSTER_NAME="${1}"
REGION="${2}"
PROJECT_ID="${3}"

if [[ -z "${CLUSTER_NAME}" ]] || [[ -z "${REGION}" ]] || [[ -z "${PROJECT_ID}" ]]; then
    echo "Usage: ${0} <cluster-name> <region> <project-id>"
    exit 1
fi

echo "Auditing Cluster: ${CLUSTER_NAME} in ${REGION} (Project: ${PROJECT_ID})"
echo "---------------------------------------------------"

# Get Cluster Details
CLUSTER_JSON=$(gcloud container clusters describe "${CLUSTER_NAME}" --region "${REGION}" --project "${PROJECT_ID}" --format=json)

# Extract all configurations in one pass for performance
# Output format: TSV (Tab Separated Values)
VALUES=$(echo "${CLUSTER_JSON}" | jq -r '
  [
    (.workloadIdentityConfig.workloadPool // "DISABLED"),
    (.networkPolicy.enabled // "FALSE" | tostring),
    (.networkConfig.datapathProvider // "LEGACY"),
    (.shieldedNodes.enabled // "FALSE" | tostring),
    (.binaryAuthorization.evaluationMode // "DISABLED"),
    (.privateClusterConfig.enablePrivateNodes // "FALSE" | tostring)
  ] | @tsv
')

read -r WI_CONFIG NETPOL_ENABLED DATAPATH_PROVIDER SHIELDED_NODES BINAUTH_CONFIG PRIVATE_NODES <<< "${VALUES}"

# Check Workload Identity
if [[ "${WI_CONFIG}" != "DISABLED" ]]; then
    echo "[PASS] Workload Identity is ENABLED (${WI_CONFIG})"
else
    echo "[FAIL] Workload Identity is DISABLED"
fi

# Check Network Policy (Explicit or DPv2)
if [[ "${NETPOL_ENABLED}" == "true" ]] || [[ "${DATAPATH_PROVIDER}" == "ADVANCED_DATAPATH" ]]; then
    echo "[PASS] Network Policy is ENABLED (Provider: ${DATAPATH_PROVIDER})"
else
    echo "[FAIL] Network Policy is DISABLED"
fi

# Check Shielded Nodes
if [[ "${SHIELDED_NODES}" == "true" ]]; then
    echo "[PASS] Shielded Nodes are ENABLED"
else
    echo "[FAIL] Shielded Nodes are DISABLED"
fi

# Check Binary Authorization
if [[ "${BINAUTH_CONFIG}" != "DISABLED" ]]; then
    echo "[PASS] Binary Authorization is ENABLED (${BINAUTH_CONFIG})"
else
    echo "[WARN] Binary Authorization is DISABLED"
fi

# Check Private Cluster
if [[ "${PRIVATE_NODES}" == "true" ]]; then
    echo "[PASS] Private Cluster (Nodes) is ENABLED"
else
    echo "[WARN] Private Cluster (Nodes) is DISABLED"
fi

echo "---------------------------------------------------"
echo "Audit Complete."
