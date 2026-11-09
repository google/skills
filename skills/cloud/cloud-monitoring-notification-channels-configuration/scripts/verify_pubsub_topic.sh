#!/bin/bash

# Script to verify if a Pub/Sub topic is fully set up for Cloud Monitoring Notification Channels.

set -euo pipefail

# Allow overriding gcloud for testing
: "${GCLOUD:=gcloud}"

export CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration; script:verify_pubsub_topic)"

# Function to show help
show_help() {
    echo "Usage: $0 <monitoring_project_id> <topic_name_or_path>"
    echo ""
    echo "Arguments:"
    echo "  monitoring_project_id: The ID of the GCP project where the Notification Channel is being configured."
    echo "                         This project's number determines the service account name."
    echo "  topic_name_or_path:   The name of the Pub/Sub topic (assumes same project as monitoring_project_id)"
    echo "                         OR the full resource path (e.g., projects/another-project/topics/another-topic)."
    echo ""
    echo "Options:"
    echo "  -h, --help            Show this help message and exit."
}

# Function to get project number
get_project_number() {
    local project_id=$1
    local project_number
    project_number=$("$GCLOUD" projects describe "$project_id" --format="value(projectNumber)" || true)
    echo "$project_number"
}

# Function to check API enablement
check_api_enabled() {
    local project_id=$1
    local api_name=$2
    local enabled
    # We use --project to ensure we check the target project
    enabled=$("$GCLOUD" services list --enabled --project="$project_id" --filter="config.name=$api_name" --format="value(config.name)" || true)
    if [[ "$enabled" == *"$api_name" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

# Function to check topic existence
check_topic_existence() {
    local project_id=$1
    local topic_name=$2
    if "$GCLOUD" pubsub topics describe "projects/$project_id/topics/$topic_name" > /dev/null 2>&1; then
        echo "true"
    else
        echo "false"
    fi
}

# Function to check if topic defines a messageStoragePolicy or enforceInTransit
check_topic_storage_policy() {
    local project_id=$1
    local topic_name=$2
    local describe_output
    describe_output=$("$GCLOUD" pubsub topics describe "projects/$project_id/topics/$topic_name" 2>/dev/null || true)

    local has_storage_policy="false"
    local enforce_in_transit="false"

    if echo "$describe_output" | grep -qE 'messageStoragePolicy|allowedPersistenceRegions'; then
        has_storage_policy="true"
    fi
    if echo "$describe_output" | grep -qE 'enforceInTransit:[[:space:]]*true'; then
        enforce_in_transit="true"
        has_storage_policy="true"
    fi

    echo "${has_storage_policy}:${enforce_in_transit}"
}

# Function to check permissions on topic
check_topic_permissions() {
    local project_id=$1
    local topic_name=$2
    local service_account=$3
    local service_account_alt=$4
    local topic_role
    topic_role=$("$GCLOUD" pubsub topics get-iam-policy "projects/$project_id/topics/$topic_name" \
        --flatten="bindings[].members" \
        --format="value(bindings.role)" \
        --filter="bindings.members:($service_account, $service_account_alt) AND bindings.role=roles/pubsub.publisher" || true)

    if [[ -n "$topic_role" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

# Function to check permissions on project
check_project_permissions() {
    local project_id=$1
    local service_account=$2
    local service_account_alt=$3
    local project_role
    project_role=$("$GCLOUD" projects get-iam-policy "$project_id" \
        --flatten="bindings[].members" \
        --format="value(bindings.role)" \
        --filter="bindings.members:($service_account, $service_account_alt) AND bindings.role=roles/pubsub.publisher" || true)

    if [[ -n "$project_role" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

main() {
    if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
        show_help
        exit 0
    fi

    if [[ "$#" -ne 2 ]]; then
        show_help >&2
        exit 1
    fi

    local monitoring_project_id=$1
    local topic_arg=$2

    # Parse topic argument
    local topic_project_id="$monitoring_project_id"
    local topic_short_name="$topic_arg"

    if [[ "$topic_arg" =~ ^projects/([^/]+)/topics/(.+) ]]; then
        topic_project_id="${BASH_REMATCH[1]}"
        topic_short_name="${BASH_REMATCH[2]}"
        echo "Detected full topic path. Topic Project: $topic_project_id, Topic Name: $topic_short_name" >&2
    fi

    echo "Checking status for Monitoring Project: $monitoring_project_id" >&2
    echo "Target Topic: projects/$topic_project_id/topics/$topic_short_name" >&2

    # 1. Get Monitoring Project Number (needed for Service Account)
    local monitoring_project_number
    monitoring_project_number=$(get_project_number "$monitoring_project_id")
    if [[ -z "$monitoring_project_number" ]]; then
        echo "Error: Could not retrieve project number for monitoring project $monitoring_project_id. Verify project ID and permissions." >&2
        exit 1
    fi
    echo "Monitoring Project Number: $monitoring_project_number" >&2

    local service_account="service-$monitoring_project_number@gcp-sa-monitoring-notification.iam.gserviceaccount.com"
    local service_account_alt="service-$monitoring_project_number@gcp-sa-monitoring.iam.gserviceaccount.com"

    # 2. Check API Enablement in Topic Project
    echo "Checking Pub/Sub API enablement in $topic_project_id..." >&2
    local api_enabled
    api_enabled=$(check_api_enabled "$topic_project_id" "pubsub.googleapis.com")
    if [[ "$api_enabled" == "true" ]]; then
        echo "  [OK] Pub/Sub API is enabled." >&2
    else
        echo "  [WARNING] Pub/Sub API (pubsub.googleapis.com) does not appear to be enabled in $topic_project_id." >&2
    fi

    # 3. Check Topic Existence & Storage Policy Restrictions
    echo "Checking topic existence..." >&2
    local topic_exists
    topic_exists=$(check_topic_existence "$topic_project_id" "$topic_short_name")
    local has_message_storage_policy="false"
    local enforce_in_transit="false"
    if [[ "$topic_exists" == "true" ]]; then
        echo "  [OK] Topic exists." >&2
        echo "Checking topic message storage policy and in-transit enforcement..." >&2
        local policy_status
        policy_status=$(check_topic_storage_policy "$topic_project_id" "$topic_short_name")
        has_message_storage_policy="${policy_status%%:*}"
        enforce_in_transit="${policy_status##*:}"
        if [[ "$enforce_in_transit" == "true" ]]; then
            echo "  [ERROR] Topic has enforceInTransit enabled. Cloud Monitoring cannot deliver notifications to topics with in-transit enforcement." >&2
        elif [[ "$has_message_storage_policy" == "true" ]]; then
            echo "  [ERROR] Topic defines a messageStoragePolicy. Cloud Monitoring cannot deliver notifications to topics with a message storage policy." >&2
        else
            echo "  [OK] Topic has no unsupported message storage policy or in-transit enforcement." >&2
        fi
    else
        echo "  [WARNING] Topic does not exist or you don't have permission to view it." >&2
    fi

    # 4. Check Permissions
    echo "Checking permissions..." >&2
    local can_publish=false
    local permission_level="none"

    if [[ "$topic_exists" == "true" ]]; then
        echo "  Checking topic-level IAM policy on projects/$topic_project_id/topics/$topic_short_name..." >&2
        if [[ $(check_topic_permissions "$topic_project_id" "$topic_short_name" "$service_account" "$service_account_alt") == "true" ]]; then
            echo "    [OK] Service account has publisher permissions on the topic." >&2
            can_publish=true
            permission_level="topic"
        fi
    fi

    if [[ "$can_publish" == "false" ]]; then
        echo "  Checking project-level IAM policy on $topic_project_id..." >&2
        if [[ $(check_project_permissions "$topic_project_id" "$service_account" "$service_account_alt") == "true" ]]; then
            echo "    [OK] Service account has publisher permissions at the project level." >&2
            can_publish=true
            permission_level="project"
        fi
    fi

    if [[ "$can_publish" == "false" ]]; then
        echo "  [WARNING] No Pub/Sub Publisher role found for Monitoring Service Agent ($service_account) in target project." >&2
    fi

    echo "----------------------------------------" >&2
    echo "Summary:" >&2
    echo "TOPIC_EXISTS=$topic_exists"
    echo "HAS_MESSAGE_STORAGE_POLICY=$has_message_storage_policy"
    echo "ENFORCE_IN_TRANSIT=$enforce_in_transit"
    echo "CAN_PUBLISH=$can_publish"
    echo "PERMISSION_LEVEL=$permission_level"

    # Return 0 if fully set up and compatible, 1 otherwise
    if [[ "$topic_exists" == "true" ]] && [[ "$can_publish" == "true" ]] && [[ "$has_message_storage_policy" == "false" ]] && [[ "$enforce_in_transit" == "false" ]]; then
        exit 0
    else
        exit 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
