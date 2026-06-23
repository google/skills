#!/usr/bin/env bash
#
# Live tail of GKE cluster autoscaler visibility logs for a single cluster.
# Surfaces both successful scale events (scale-ups, node pool auto-creation node-pool creations,
# scale-downs) and failures / stalls (per-MIG scale-up errors, noScaleUp,
# noScaleDown). Polls every $POLL_INTERVAL_SECS, colorizes terminal output,
# and appends a plain-text copy to the log file.
#
# Schema reference:
#   https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-autoscaler-visibility
#
# Requires: gcloud, jq.

usage() {
  cat >&2 <<EOF
Usage: $0 [options] [cluster-name]

  Tails container.googleapis.com/cluster-autoscaler-visibility logs for the
  named GKE cluster. If cluster-name is omitted, it is inferred from the
  current kubectl context.

Options:
  --cluster NAME, -c NAME  The GKE cluster name.
  --project PROJECT_ID, -p PROJECT_ID
                           The GCP project ID. If omitted, uses the current 
                           gcloud project or infers from the kube context.
  --errors-only, -e        Only emit failures and stalls (scale-up errors,
                           noScaleUp, noScaleDown). Suppresses successful
                           scale events.
  --log-file PATH, -o PATH Append plain-text events to PATH. Without this
                           flag, output is terminal-only.
  -h, --help               Show this help.
EOF
}

ERRORS_ONLY=0
CLUSTER=""
LOG_FILE=""
PROJECT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)        usage; exit 0 ;;
    -e|--errors-only) ERRORS_ONLY=1; shift ;;
    -c|--cluster)
                      [[ -z "${2:-}" ]] && { echo "Error: $1 requires a cluster name." >&2; exit 1; }
                      CLUSTER="$2"; shift 2 ;;
    -p|--project)
                      [[ -z "${2:-}" ]] && { echo "Error: $1 requires a project ID." >&2; exit 1; }
                      PROJECT="$2"; shift 2 ;;
    -o|--log-file)
                      [[ -z "${2:-}" ]] && { echo "Error: $1 requires a path." >&2; exit 1; }
                      LOG_FILE="$2"; shift 2 ;;
    --)               shift; CLUSTER="$1"; break ;;
    -*)               echo "Unknown flag: $1" >&2; usage; exit 1 ;;
    *)                CLUSTER="$1"; shift ;;
  esac
done

if [[ -z "$CLUSTER" ]]; then
  if ! command -v kubectl &>/dev/null; then
    echo "Error: <cluster-name> not provided and 'kubectl' not found to infer it." >&2
    usage
    exit 1
  fi
  CONTEXT=$(kubectl config current-context 2>/dev/null)
  if [[ -z "$CONTEXT" ]]; then
    echo "Error: <cluster-name> not provided and 'kubectl config current-context' returned nothing." >&2
    usage
    exit 1
  fi

  # Robustly parse GKE context: gke_PROJECT_LOCATION_CLUSTER
  IFS='_' read -ra PARTS <<< "$CONTEXT"
  if [[ "${PARTS[0]}" == "gke" && ${#PARTS[@]} -ge 4 ]]; then
    PROJECT_FROM_CTX="${PARTS[1]}"
    CLUSTER_FROM_CTX="${PARTS[${#PARTS[@]}-1]}"
    if [[ -z "$PROJECT" ]]; then
      PROJECT="$PROJECT_FROM_CTX"
    fi
    CLUSTER="$CLUSTER_FROM_CTX"
    echo "Inferred cluster '$CLUSTER' (project '$PROJECT') from kubectl context '$CONTEXT'." >&2
  else
    echo "Error: <cluster-name> not provided and could not be determined from current kube context '$CONTEXT'." >&2
    echo "Expected format: gke_PROJECT_LOCATION_CLUSTER" >&2
    usage
    exit 1
  fi
fi

for cmd in gcloud jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: Required command '$cmd' is not installed." >&2
    exit 1
  fi
done

GCLOUD_OPTS=()
[[ -n "$PROJECT" ]] && GCLOUD_OPTS+=(--project "$PROJECT")

# Verify permissions before starting
echo "Verifying permissions..."
CHECK_PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [[ -n "$CHECK_PROJECT" ]]; then
  if ! gcloud projects get-iam-policy "$CHECK_PROJECT" --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:$(gcloud config get-value account)" | grep -q "roles/logging.viewer\|roles/owner\|roles/editor"; then
    echo "Warning: You may not have 'roles/logging.viewer' permissions in project '$CHECK_PROJECT'. The tail may fail silently." >&2
  fi
fi

POLL_INTERVAL_SECS=10
[[ -n "$LOG_FILE" ]] && touch "$LOG_FILE"

# ANSI colors
C_RED=$'\033[31m'    # errors
C_YELLOW=$'\033[33m' # stalls (noScaleUp / noScaleDown)
C_GREEN=$'\033[32m'  # successful scale-up
C_CYAN=$'\033[36m'   # node-pool created (node pool auto-creation)
C_BLUE=$'\033[34m'   # scale-down
C_RESET=$'\033[0m'

emit() {
  # $1 = color, $2 = line
  printf '%s%s%s\n' "$1" "$2" "$C_RESET"
  [[ -n "$LOG_FILE" ]] && echo "$2" >>"$LOG_FILE"
}

# Initial cursor: 1 minute ago. Portable across GNU date (Linux) and BSD date (macOS).
LAST_TIMESTAMP=$(date -u -d '1 minute ago' +'%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
  || date -u -v-1M +'%Y-%m-%dT%H:%M:%SZ')

echo "========================================================================="
echo " GKE cluster autoscaler event monitor"
echo "   cluster: $CLUSTER"
[[ -n "$PROJECT" ]] && echo "   project: $PROJECT"
if (( ERRORS_ONLY )); then
  echo "   mode:    errors-only (suppressing successful scale events)"
else
  echo "   mode:    all events"
fi
if [[ -n "$LOG_FILE" ]]; then
  echo "   output:  terminal + $LOG_FILE"
else
  echo "   output:  terminal only (use --log-file PATH to also append to a file)"
fi
echo "   start:   $LAST_TIMESTAMP"
echo "   press Ctrl-C to stop"
echo "========================================================================="

while true; do
  # Visibility log shapes (per docs):
  #   decision.scaleUp                 successful scale-up of existing MIGs
  #   decision.nodePoolCreated         node pool auto-creation created a new node pool
  #   decision.scaleDown               scale-down (node removal)
  #   noDecisionStatus.noScaleUp       pending pods nothing could host
  #   noDecisionStatus.noScaleDown     scale-down blocked (per-node reasons)
  #   resultInfo.results[].errorMsg    per-MIG scale-up failure (quota/stockout/IP/…)
  #
  # The existence-tests (`:*`) keep the filter tight; substring fallbacks would
  # match unrelated lines and inflate the response. In errors-only mode we
  # exclude the success shapes server-side to cut bandwidth and quota.
  if (( ERRORS_ONLY )); then
    QUERY="log_id(\"container.googleapis.com/cluster-autoscaler-visibility\")
           AND resource.labels.cluster_name = \"$CLUSTER\"
           AND timestamp > \"$LAST_TIMESTAMP\"
           AND ( jsonPayload.resultInfo.results.errorMsg.messageId:*
                 OR jsonPayload.noDecisionStatus.noScaleUp:*
                 OR jsonPayload.noDecisionStatus.noScaleDown:* )"
  else
    QUERY="log_id(\"container.googleapis.com/cluster-autoscaler-visibility\")
           AND resource.labels.cluster_name = \"$CLUSTER\"
           AND timestamp > \"$LAST_TIMESTAMP\"
           AND ( jsonPayload.decision.scaleUp:*
                 OR jsonPayload.decision.scaleDown:*
                 OR jsonPayload.decision.nodePoolCreated:*
                 OR jsonPayload.resultInfo.results.errorMsg.messageId:*
                 OR jsonPayload.noDecisionStatus.noScaleUp:*
                 OR jsonPayload.noDecisionStatus.noScaleDown:* )"
  fi

  LOGS_JSON=$(gcloud "${GCLOUD_OPTS[@]}" logging read "$QUERY" --order=asc --format=json 2>/dev/null)
  if [[ -z "$LOGS_JSON" || "$LOGS_JSON" == "[]" ]]; then
    sleep "$POLL_INTERVAL_SECS"
    continue
  fi

  # Advance the cursor BEFORE the per-line loop. The pipeline below runs the
  # loop body in a subshell, so any LAST_TIMESTAMP update inside it would not
  # survive to the next iteration — replaying the same window every tick.
  NEW_TIMESTAMP=$(echo "$LOGS_JSON" | jq -r '[.[].timestamp] | max // empty')
  [[ -n "$NEW_TIMESTAMP" ]] && LAST_TIMESTAMP="$NEW_TIMESTAMP"

  echo "$LOGS_JSON" | jq -c '.[]' | while read -r entry; do
    ts=$(echo "$entry" | jq -r '.timestamp')

    # ---- Successes -------------------------------------------------------
    if (( ! ERRORS_ONLY )); then
      # 1. Successful scale-up of one or more existing MIGs
      echo "$entry" | jq -c '.jsonPayload.decision.scaleUp.increasedMigs[]?' \
        | while read -r mig; do
            pool=$(echo  "$mig" | jq -r '.mig.nodepool       // "unknown"')
            name=$(echo  "$mig" | jq -r '.mig.name           // "unknown"')
            zone=$(echo  "$mig" | jq -r '.mig.zone           // "unknown"')
            count=$(echo "$mig" | jq -r '.requestedNodes     // 0')
            line="[$ts] SCALE_UP: pool=$pool mig=$name zone=$zone +$count nodes"
            emit "$C_GREEN" "$line"
          done

      # 2. node pool auto-creation created a new node pool
      echo "$entry" | jq -c '.jsonPayload.decision.nodePoolCreated.nodePools[]?' \
        | while read -r np; do
            name=$(echo "$np" | jq -r '.name // "unknown"')
            migs=$(echo "$np" | jq -r '[.migs[]?.name] | join(",")')
            line="[$ts] POOL_CREATED: $name migs=[$migs]"
            emit "$C_CYAN" "$line"
          done

      # 3. Scale-down (node removal)
      echo "$entry" | jq -c '.jsonPayload.decision.scaleDown.nodesToBeRemoved[]?' \
        | while read -r n; do
            node=$(echo "$n" | jq -r '.node.name             // "unknown"')
            cpu=$(echo  "$n" | jq -r '.node.cpuRatio         // "?"')
            mem=$(echo  "$n" | jq -r '.node.memRatio         // "?"')
            evicted=$(echo "$n" | jq -r '.evictedPodsTotalCount // 0')
            line="[$ts] SCALE_DOWN: node=$node cpuRatio=$cpu memRatio=$mem evicted=$evicted pods"
            emit "$C_BLUE" "$line"
          done
    fi

    # ---- Failures and stalls --------------------------------------------
    # 4. Per-MIG scale-up errors
    echo "$entry" | jq -c '.jsonPayload.resultInfo.results[]? | select(.errorMsg)' \
      | while read -r res; do
          mid=$(echo    "$res" | jq -r '.errorMsg.messageId // "UNKNOWN"')
          params=$(echo "$res" | jq -r '[.errorMsg.parameters[]?] | join(", ")')
          line="[$ts] SCALE_UP_ERROR: $mid | $params"
          emit "$C_RED" "$line"
        done

    # 5. noScaleUp per-pod-group rejections (each rejected MIG has its own reason)
    # Path migrated to noDecisionStatus.noScaleUp; fall back to legacy noScaleUp
    # for older log entries.
    echo "$entry" | jq -c '
        ( .jsonPayload.noDecisionStatus.noScaleUp.unhandledPodGroups[]?,
          .jsonPayload.noScaleUp.unhandledPodGroups[]? )' \
      | while read -r grp; do
          ns=$(echo  "$grp" | jq -r '.podGroup.samplePod.namespace // "default"')
          pod=$(echo "$grp" | jq -r '.podGroup.samplePod.name      // "unknown"')
          echo "$grp" | jq -c '.rejectedMigs[]?' | while read -r mig; do
            mig_name=$(echo "$mig" | jq -r '.mig.name                  // "unknown"')
            reason=$(echo   "$mig" | jq -r '.reason.messageId          // "no-reason"')
            params=$(echo   "$mig" | jq -r '[.reason.parameters[]?] | join(", ")')
            line="[$ts] NOSCALEUP: $ns/$pod | MIG: $mig_name | $reason | $params"
            emit "$C_YELLOW" "$line"
          done
        done

    # 6. noScaleDown per-node reasons
    echo "$entry" | jq -c '.jsonPayload.noDecisionStatus.noScaleDown.nodes[]?' \
      | while read -r n; do
          node=$(echo "$n" | jq -r '.node.name        // "unknown"')
          reason=$(echo "$n" | jq -r '.reason.messageId // "no-reason"')
          params=$(echo "$n" | jq -r '[.reason.parameters[]?] | join(", ")')
          line="[$ts] NOSCALEDOWN: node=$node | $reason | $params"
          emit "$C_YELLOW" "$line"
        done
  done

  sleep "$POLL_INTERVAL_SECS"
done
