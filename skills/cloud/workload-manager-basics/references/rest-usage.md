# Workload Manager REST Usage

Use REST when the SDK does not cover a needed resource, when debugging raw
requests, or when building language-agnostic automation.

## Setup

```bash
export PROJECT_ID="PROJECT_ID"
export LOCATION="LOCATION"
export TOKEN="$(gcloud auth print-access-token)"
export BASE_URL="https://workloadmanager.googleapis.com/v1"
```

## List Rules

```bash
curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/rules"
```

Filter by evaluation type when selecting rules for a specific workload:

```bash
curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/rules?evaluationType=SQL_SERVER"
```

## Create an Evaluation

```bash
export EVALUATION_ID="sql-server-prod"
export REQUEST_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

curl -sS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/evaluations?evaluationId=${EVALUATION_ID}&requestId=${REQUEST_ID}" \
  -d @- <<'JSON'
{
  "description": "SQL Server production validation",
  "evaluationType": "SQL_SERVER",
  "resourceFilter": {
    "scopes": ["projects/PROJECT_ID"],
    "inclusionLabels": {
      "env": "prod"
    }
  },
  "ruleNames": [
    "projects/PROJECT_ID/locations/LOCATION/rules/RULE_ID"
  ],
  "labels": {
    "owner": "platform",
    "workload": "sql-server"
  }
}
JSON
```

Replace `PROJECT_ID`, `LOCATION`, and `RULE_ID` inside the JSON before running.
The API returns a long-running operation.

## Poll an Operation

```bash
export OPERATION_NAME="projects/${PROJECT_ID}/locations/${LOCATION}/operations/OPERATION_ID"

curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/${OPERATION_NAME}"
```

The operation response contains `done: true` when complete. If an error is
present, fix that error before retrying with a new request ID.

## Run an Evaluation

```bash
export EVALUATION_ID="sql-server-prod"
export EXECUTION_ID="manual-run-001"
export REQUEST_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

curl -sS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/evaluations/${EVALUATION_ID}/executions:run" \
  -d @- <<JSON
{
  "executionId": "${EXECUTION_ID}",
  "execution": {
    "labels": {
      "trigger": "manual"
    }
  },
  "requestId": "${REQUEST_ID}"
}
JSON
```

## List Executions

```bash
curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/evaluations/${EVALUATION_ID}/executions"
```

## List Execution Results

```bash
export EXECUTION_ID="EXECUTION_ID"

curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/evaluations/${EVALUATION_ID}/executions/${EXECUTION_ID}/results"
```

## List Scanned Resources

```bash
curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/evaluations/${EVALUATION_ID}/executions/${EXECUTION_ID}/scannedResources"
```

## Delete an Evaluation

Use `force=true` only when associated child resources should also be deleted.

```bash
export REQUEST_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

curl -sS -X DELETE \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/evaluations/${EVALUATION_ID}?requestId=${REQUEST_ID}&force=true"
```

## REST-Only Resources

If client libraries do not expose a Workload Manager resource yet, consult the
REST reference for endpoints such as deployments, actuations, discovered
profiles, insights, and operations. Keep automation defensive because generated
client libraries and REST resources can land at different times.
