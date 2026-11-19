#!/bin/bash

# quick-add-gcp-service.sh - Registers a single composite Service in Agent
# Registry containing all applicable Google Cloud API endpoint URL variants
# (Base, Base mTLS, and for non-global locations: Locational, Locational mTLS,
# and Regional REP) for a Governed Target GCP Service behind Agent Gateway.

set -euo pipefail

readonly DEFAULT_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-agent-registry)"

PROJECT=""
LOCATION=""
SERVICE_ID=""
SERVICE_NAME=""
DRY_RUN=0
NO_ATTRIBUTION=0

usage() {
  cat <<EOF
Usage: $0 --service=SERVICE_ID [--service-name=RESOURCE_ID] [--location=LOCATION] [--project=PROJECT_ID] [--no-attribution] [--dry-run]

Registers a single composite Service in Agent Registry containing the Google
Cloud API endpoint URL variants for a Governed Target Service (e.g.,
aiplatform, discoveryengine, storage, iam, kms):
  1. Base:            https://<SERVICE_ID>.googleapis.com
  2. Base mTLS:       https://<SERVICE_ID>.mtls.googleapis.com
  3. Locational:      https://<LOCATION>-<SERVICE_ID>.googleapis.com      (omitted when --location=global)
  4. Locational mTLS: https://<LOCATION>-<SERVICE_ID>.mtls.googleapis.com (omitted when --location=global)
  5. Regional REP:    https://<SERVICE_ID>.<LOCATION>.rep.googleapis.com  (omitted when --location=global)

Options:
  --service=SERVICE_ID        GCP service short name (e.g., aiplatform, storage, iam, kms)
  --service-name=RESOURCE_ID  Agent Registry Service ID (4-63 chars; defaults to SERVICE_ID,
                              or <SERVICE_ID>-api when SERVICE_ID is shorter than 4 chars)
  --location=LOCATION         Target GCP region, multi-region, or 'global' (defaults to gcloud compute/region or us-central1)
  --project=PROJECT_ID        Target GCP project ID (defaults to gcloud config project)
  --no-attribution            Omit CLOUDSDK_METRICS_REQUEST_ATTRIBUTION when running gcloud
  --dry-run                   Print the composite gcloud command without executing it
  --help, -h                  Show this help message
EOF
}

require_flag_value() {
  local flag="$1"
  if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == -* ]]; then
    echo "Error: Missing value for ${flag}" >&2
    usage >&2
    exit 1
  fi
}

require_nonempty_eq_value() {
  local raw="$1"
  local val="${raw#*=}"
  if [[ -z "${val}" ]]; then
    echo "Error: Empty value for ${raw%%=*}" >&2
    usage >&2
    exit 1
  fi
}

resolve_effective_attribution() {
  if (( NO_ATTRIBUTION == 1 )); then
    printf ''
  elif [[ -v CLOUDSDK_METRICS_REQUEST_ATTRIBUTION ]]; then
    printf '%s' "${CLOUDSDK_METRICS_REQUEST_ATTRIBUTION}"
  else
    printf '%s' "${DEFAULT_ATTRIBUTION}"
  fi
}

run_gcloud() {
  local effective_attr
  effective_attr="$(resolve_effective_attribution)"
  if [[ -z "${effective_attr}" ]]; then
    gcloud "$@"
  else
    CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="${effective_attr}" gcloud "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service=*)
      require_nonempty_eq_value "$1"
      SERVICE_ID="${1#*=}"
      shift
      ;;
    --service)
      require_flag_value "$@"
      SERVICE_ID="$2"
      shift 2
      ;;
    --service-name=*)
      require_nonempty_eq_value "$1"
      SERVICE_NAME="${1#*=}"
      shift
      ;;
    --service-name)
      require_flag_value "$@"
      SERVICE_NAME="$2"
      shift 2
      ;;
    --location=*)
      require_nonempty_eq_value "$1"
      LOCATION="${1#*=}"
      shift
      ;;
    --location)
      require_flag_value "$@"
      LOCATION="$2"
      shift 2
      ;;
    --project=*)
      require_nonempty_eq_value "$1"
      PROJECT="${1#*=}"
      shift
      ;;
    --project)
      require_flag_value "$@"
      PROJECT="$2"
      shift 2
      ;;
    --no-attribution)
      NO_ATTRIBUTION=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      echo "Error: Unknown flag $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -z "${SERVICE_ID}" ]]; then
        SERVICE_ID="$1"
      else
        echo "Error: Unexpected argument '$1'" >&2
        usage >&2
        exit 1
      fi
      shift
      ;;
  esac
done

# Strip .googleapis.com suffix if provided
SERVICE_ID="${SERVICE_ID%.googleapis.com}"

if [[ -z "${SERVICE_ID}" ]]; then
  echo "Error: Service ID is required. Use --service=SERVICE_ID (e.g., --service=aiplatform)." >&2
  usage >&2
  exit 1
fi

if [[ ! "${SERVICE_ID}" =~ ^[a-z][a-z0-9-]*[a-z0-9]$ ]]; then
  echo "Error: Invalid GCP service short name '${SERVICE_ID}'. Expected lowercase letters, digits, or hyphens (e.g., aiplatform, storage, iam)." >&2
  exit 1
fi

if [[ -z "${SERVICE_NAME}" ]]; then
  if (( ${#SERVICE_ID} < 4 )); then
    SERVICE_NAME="${SERVICE_ID}-api"
  else
    SERVICE_NAME="${SERVICE_ID}"
  fi
fi

if [[ ! "${SERVICE_NAME}" =~ ^[a-z][a-z0-9-]{2,61}[a-z0-9]$ ]]; then
  echo "Error: Agent Registry Service ID '${SERVICE_NAME}' must be 4-63 characters matching ^[a-z][a-z0-9-]{2,61}[a-z0-9]$. Pass --service-name=RESOURCE_ID." >&2
  exit 1
fi

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  PROJECT=$(run_gcloud config get-value project 2>/dev/null || true)
fi

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "Error: Project not set. Use --project=PROJECT_ID." >&2
  usage >&2
  exit 1
fi

if [[ ! "${PROJECT}" =~ ^[a-z0-9][a-z0-9.:-]*[a-z0-9]$ ]]; then
  echo "Error: Invalid GCP project identifier '${PROJECT}'." >&2
  exit 1
fi

if [[ -z "${LOCATION}" || "${LOCATION}" == "(unset)" ]]; then
  LOCATION=$(run_gcloud config get-value compute/region 2>/dev/null || true)
fi

if [[ -z "${LOCATION}" || "${LOCATION}" == "(unset)" ]]; then
  LOCATION="us-central1"
fi

if [[ ! "${LOCATION}" =~ ^[a-z][a-z0-9-]*[a-z0-9]$ ]]; then
  echo "Error: Invalid location '${LOCATION}'. Expected lowercase 'global', multi-region ('us', 'eu'), or region (e.g., 'us-central1')." >&2
  exit 1
fi

interfaces_flags=(
  "--interfaces=protocolBinding=jsonrpc,url=https://${SERVICE_ID}.googleapis.com"
  "--interfaces=protocolBinding=jsonrpc,url=https://${SERVICE_ID}.mtls.googleapis.com"
)

if [[ "${LOCATION}" != "global" ]]; then
  interfaces_flags+=(
    "--interfaces=protocolBinding=jsonrpc,url=https://${LOCATION}-${SERVICE_ID}.googleapis.com"
    "--interfaces=protocolBinding=jsonrpc,url=https://${LOCATION}-${SERVICE_ID}.mtls.googleapis.com"
    "--interfaces=protocolBinding=jsonrpc,url=https://${SERVICE_ID}.${LOCATION}.rep.googleapis.com"
  )
fi

gcloud_args=(
  agent-registry services create "${SERVICE_NAME}"
  "--project=${PROJECT}"
  "--location=${LOCATION}"
  "--display-name=${SERVICE_ID}"
  "--description=Google Cloud ${SERVICE_ID} API endpoints"
  "--endpoint-spec-type=no-spec"
  "${interfaces_flags[@]}"
)

format_shell_arg() {
  local arg="$1"
  if [[ "${arg}" =~ ^[A-Za-z0-9_./:=,+-]+$ ]]; then
    printf '%s' "${arg}"
  elif [[ ! "${arg}" =~ [\"\$\\\!\`] ]]; then
    printf '"%s"' "${arg}"
  else
    printf "'%s'" "${arg//\'/\'\\\'\'}"
  fi
}

if (( DRY_RUN == 1 )); then
  echo "[DRY RUN] Would register composite Service '${SERVICE_NAME}' (${#interfaces_flags[@]} endpoint URL variants for '${SERVICE_ID}') in project '${PROJECT}' (${LOCATION}):"
  cmd_parts=()
  effective_attr="$(resolve_effective_attribution)"
  if [[ -n "${effective_attr}" ]]; then
    cmd_parts+=("CLOUDSDK_METRICS_REQUEST_ATTRIBUTION=$(format_shell_arg "${effective_attr}")")
  fi
  cmd_parts+=("gcloud")
  for arg in "${gcloud_args[@]}"; do
    cmd_parts+=("$(format_shell_arg "${arg}")")
  done
  printf '%s\n' "${cmd_parts[*]}"
else
  echo "Registering composite Service '${SERVICE_NAME}' (${#interfaces_flags[@]} endpoint URL variants for '${SERVICE_ID}') in project '${PROJECT}' (${LOCATION})..."
  run_gcloud "${gcloud_args[@]}"
  echo "Successfully registered composite Service '${SERVICE_NAME}' for '${SERVICE_ID}' in '${LOCATION}'."
fi

echo "Reminder: Bind 'roles/iap.egressor' for the Agent Identity to the projected Endpoint catalog ID ('endpoints/agentregistry-<UUID>' from 'registryResource' in 'gcloud agent-registry services describe ${SERVICE_NAME} --project=${PROJECT} --location=${LOCATION}'), not to the Service ID '${SERVICE_NAME}'."
