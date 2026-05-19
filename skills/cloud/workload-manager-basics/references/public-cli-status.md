# Workload Manager Public CLI Status

Public documentation does not currently describe a dedicated
`gcloud workload-manager` command group. Do not write examples that imply
Workload Manager evaluations, executions, rules, deployments, or actuations can
be managed through a service-specific `gcloud` command.

Use `gcloud` only for adjacent Google Cloud setup tasks: project configuration,
authentication, IAM, service enablement, and access tokens. Use the public SDK
or REST API for Workload Manager resources.

## Enable the API

```bash
gcloud services enable workloadmanager.googleapis.com --quiet
```

## Set Project and Location Defaults

```bash
gcloud config set project PROJECT_ID
export PROJECT_ID="$(gcloud config get-value project)"
export LOCATION="LOCATION"
```

## Authenticate for Local SDK Usage

```bash
gcloud auth application-default login
```

## Authenticate for REST Usage

```bash
export TOKEN="$(gcloud auth print-access-token)"
```

## Grant a Workload Manager Role

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:USER_EMAIL" \
  --role="roles/workloadmanager.evaluationAdmin" \
  --quiet
```

Use `roles/workloadmanager.viewer` when read-only access is enough.

## REST Bridge

```bash
curl -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://workloadmanager.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/evaluations"
```

## Operational Notes

- Do not invent service-specific CLI commands unless they appear in current
  public `gcloud` documentation.
- Do not describe `gcloud` as a Workload Manager management surface.
- `gcloud services`, `gcloud auth`, `gcloud projects add-iam-policy-binding`,
  and `gcloud logging` remain useful around the Workload Manager API.
- Enabling the API has no direct charge by itself. Evaluations can create logs,
  scan resource metadata, and optionally export detailed results to BigQuery,
  which can incur normal service charges.
