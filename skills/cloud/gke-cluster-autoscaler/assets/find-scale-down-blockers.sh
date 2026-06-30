#!/usr/bin/env bash
#
# Surface pods and nodes that block GKE cluster autoscaler scale-down.
# Categorizes by reason so you can prioritize the fix:
#   1. safe-to-evict: "false"  — explicit pin (often defensive, audit each)
#   2. bare pods               — no controller, autoscaler won't evict them
#   3. local-storage pods      — emptyDir / hostPath that would lose data on eviction
#   4. PDB tightness           — currently disruptionsAllowed = 0
#   5. Node pool minimums      — pool has reached its min-nodes floor
#   6. Node-level blocks       — annotations or scheduling constraints
#   7. System pod blocks       — non-daemonset kube-system pods
#
# Reads the current kube context. Run after `gcloud container clusters
# get-credentials` for the target cluster.
#
# Requires: kubectl, jq.

set -euo pipefail

cleanup() {
  rm -f .tmp_pool_counts.$$
}
trap cleanup EXIT

usage() {
  cat >&2 <<EOF
Usage: $0 [-n NAMESPACE]

  Categorizes scale-down blockers across the current kube context.

Options:
  -n NAMESPACE   Restrict the scan to one namespace. Default: all namespaces.
  -h, --help     Show this help.
EOF
}

NS_FLAG=(-A)
NAMESPACE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -n)        [[ -z "${2:-}" ]] && { echo "Error: -n requires a namespace." >&2; exit 1; }
               NAMESPACE="$2"
               NS_FLAG=(-n "$2"); shift 2 ;;
    *)         echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

for cmd in kubectl jq; do
  command -v "$cmd" >/dev/null || { echo "Error: '$cmd' not installed." >&2; exit 1; }
done

PODS_JSON=$(kubectl get pods "${NS_FLAG[@]}" -o json)
PDBS_JSON=$(kubectl get pdb  "${NS_FLAG[@]}" -o json)
NODES_JSON=$(kubectl get nodes -o json)

section() { printf '\n=== %s ===\n' "$1"; }

# 1. safe-to-evict: "false" annotations
section 'safe-to-evict: "false" (explicit scale-down pin)'
echo "$PODS_JSON" | jq -r '
  .items[]
  | select(.metadata.annotations["cluster-autoscaler.kubernetes.io/safe-to-evict"] == "false")
  | "\(.metadata.namespace)/\(.metadata.name)\ton node: \(.spec.nodeName // "<unscheduled>")"
' | column -t -s $'\t' || echo '(none)'

# 2. Bare pods — no controller ownerReference
section 'Bare pods (no controller — autoscaler will not evict)'
echo "$PODS_JSON" | jq -r '
  .items[]
  | select((.metadata.ownerReferences // []) | length == 0)
  | "\(.metadata.namespace)/\(.metadata.name)\ton node: \(.spec.nodeName // "<unscheduled>")"
' | column -t -s $'\t' || echo '(none)'

# 3. Pods with local storage that would lose data on eviction.
#    emptyDir volumes (any medium) and hostPath PVCs both block consolidation.
#    Skip if safe-to-evict is explicitly "true".
section 'Local-storage pods (emptyDir / hostPath — eviction loses data)'
echo "$PODS_JSON" | jq -r '
  .items[]
  | select(.metadata.annotations["cluster-autoscaler.kubernetes.io/safe-to-evict"] != "true")
  | select(
      (.spec.volumes // []) | any(
        (.emptyDir != null) or (.hostPath != null)
      )
    )
  | "\(.metadata.namespace)/\(.metadata.name)\ton node: \(.spec.nodeName // "<unscheduled>")"
' | column -t -s $'\t' || echo '(none)'

# 4. PDBs currently allowing zero disruptions — block voluntary eviction.
section 'PodDisruptionBudgets currently blocking eviction (disruptionsAllowed = 0)'
echo "$PDBS_JSON" | jq -r '
  .items[]
  | select((.status.disruptionsAllowed // 0) == 0)
  | "\(.metadata.namespace)/\(.metadata.name)\tcurrentHealthy=\(.status.currentHealthy // 0)\tdesiredHealthy=\(.status.desiredHealthy // 0)\texpectedPods=\(.status.expectedPods // 0)"
' | column -t -s $'\t' || echo '(none)'

# 5. Node-level blocks (Annotations)
section 'Nodes with scale-down disabled via annotation'
echo "$NODES_JSON" | jq -r '
  .items[]
  | select(.metadata.annotations["cluster-autoscaler.kubernetes.io/scale-down-disabled"] == "true")
  | "\(.metadata.name)\t(annotation: scale-down-disabled=true)"
' | column -t -s $'\t' || echo '(none)'

# 6. Scheduling constraints (Hostname affinity)
section 'Pods pinned to specific nodes (hostname nodeSelector/affinity)'
echo "$PODS_JSON" | jq -r '
  .items[]
  | select(
      (.spec.nodeSelector["kubernetes.io/hostname"] != null) or
      ((.spec.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms // []) | any(
        .matchExpressions // [] | any(.key == "kubernetes.io/hostname")
      ))
    )
  | "\(.metadata.namespace)/\(.metadata.name)\ton node: \(.spec.nodeName // "<unscheduled>")"
' | column -t -s $'\t' || echo '(none)'

# 7. kube-system pods (non-DaemonSet)
section 'Kube-system pods (non-DaemonSet — block scale-down unless annotated)'
echo "$PODS_JSON" | jq -r '
  .items[]
  | select(.metadata.namespace == "kube-system")
  | select(.metadata.annotations["cluster-autoscaler.kubernetes.io/safe-to-evict"] != "true")
  | select((.metadata.ownerReferences // []) | any(.kind == "DaemonSet") | not)
  | "\(.metadata.namespace)/\(.metadata.name)\ton node: \(.spec.nodeName // "<unscheduled>")"
' | column -t -s $'\t' || echo '(none)'

# 8. Node pool min size
section 'Node pool at minimum size floor'
# GKE cluster autoscaler exposes pool minimums via the cluster-autoscaler-status ConfigMap.
# This avoids needing gcloud auth or guessing cluster names from the kube context.
CA_STATUS=$(kubectl get configmap cluster-autoscaler-status -n kube-system -o jsonpath='{.data.status}' 2>/dev/null || true)
if [[ -n "$CA_STATUS" ]]; then
  echo "$CA_STATUS" | awk '
    /^  Name:/ { pool=$2 }
    /^  Health:/ {
      target = ""; min = ""
      if (match($0, /cloudProviderTarget=[0-9]+/)) {
         split(substr($0, RSTART, RLENGTH), t, "=")
         target = t[2]
      }
      if (match($0, /minSize=[0-9]+/)) {
         split(substr($0, RSTART, RLENGTH), m, "=")
         min = m[2]
      }
      if (target != "" && min != "" && target <= min) {
         print pool "\t(blocked: current nodes (" target ") is at or below min-nodes (" min "))"
      }
    }
  ' | column -t -s $'\t' || echo '(none)'
else
  # Fallback to gcloud if configmap is unavailable (e.g. lack of RBAC)
  CONTEXT=$(kubectl config current-context 2>/dev/null || echo "")
  if [[ "$CONTEXT" =~ ^gke_([^_]+)_([^_]+)_(.+)$ ]]; then
    PROJECT="${BASH_REMATCH[1]}"
    LOCATION="${BASH_REMATCH[2]}"
    CLUSTER="${BASH_REMATCH[3]}"
    
    POOLS_JSON=$(gcloud container node-pools list --cluster="$CLUSTER" --location="$LOCATION" --project="$PROJECT" --format="json(name,autoscaling.minNodeCount)" 2>/dev/null || echo "[]")
    if [[ "$POOLS_JSON" != "[]" ]]; then
      echo "$NODES_JSON" | jq -r '.items[] | .metadata.labels["cloud.google.com/gke-nodepool"]' | grep -v "^null$" | sort | uniq -c > .tmp_pool_counts.$$ || true
      
      echo "$POOLS_JSON" | jq -r '.[] | "\(.name)\t\(.autoscaling.minNodeCount // 0)"' | while IFS=$'\t' read -r POOL MIN_NODES; do
        if [[ -n "$MIN_NODES" && "$MIN_NODES" != "null" && "$MIN_NODES" -gt 0 ]]; then
          CURRENT=$(grep " $POOL$" .tmp_pool_counts.$$ | awk '{print $1}')
          if [[ -n "$CURRENT" && "$CURRENT" -le "$MIN_NODES" ]]; then
            echo -e "$POOL\t(blocked: current nodes ($CURRENT) is at or below min-nodes ($MIN_NODES))"
          fi
        fi
      done | column -t -s $'\t' || echo '(none)'
      rm -f .tmp_pool_counts.$$
    else
      echo "(Could not fetch node pool details via gcloud)"
    fi
  else
    echo "(Skipping node pool limits check: missing RBAC for ConfigMap and kube context is not in gke_PROJECT_LOCATION_CLUSTER format for gcloud fallback)"
  fi
fi

cat <<'EOF'

---
Next steps:
  - safe-to-evict pins: confirm each one is genuinely irreplaceable; remove
    the annotation otherwise. Every annotated pod is a permanent scale-down
    blocker on its host node.
  - Bare pods: wrap in a Deployment/Job/StatefulSet so the autoscaler can
    reschedule them.
  - Local-storage pods: move to a network volume (PVC) where the data can
    survive node deletion, or add "safe-to-evict: true" if data is disposable.
  - PDBs: tight is fine for SLO protection; if disruptionsAllowed stays at 0
    indefinitely, the PDB is mis-sized for the replica count.
  - Node pool limits: decrease the min-nodes setting on the node pool or ComputeClass if the floor is too high.
  - Node-level blocks: remove the "scale-down-disabled" annotation to allow
    the autoscaler to consider the node for removal.
  - System pods: isolate non-DaemonSet kube-system pods to a "system" pool
    using the namespace annotation:
    cloud.google.com/default-compute-class-non-daemonset: "system-class"

For per-node scale-down reasons from the autoscaler itself, run:
  ./assets/log-autoscaler-events.sh <cluster-name>
and look for NOSCALEDOWN lines in the visibility logs.
EOF
