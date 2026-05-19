# Workload Manager Setup Prerequisites

This file is not Workload Manager infrastructure-as-code support. Public
Terraform examples here cover only adjacent prerequisites around Workload
Manager: API enablement, IAM, BigQuery export datasets, and KMS keys.

Do not write examples that imply Terraform can manage Workload Manager
evaluations, executions, rules, deployments, actuations, or insights unless a
current provider reference explicitly documents those resources. Manage
Workload Manager resources through the public SDK or REST API.

## Terraform: Enable API

```terraform
resource "google_project_service" "workload_manager" {
  project            = var.project_id
  service            = "workloadmanager.googleapis.com"
  disable_on_destroy = false
}
```

## Terraform: Grant Evaluation Admin

```terraform
resource "google_project_iam_member" "workload_manager_evaluation_admin" {
  project = var.project_id
  role    = "roles/workloadmanager.evaluationAdmin"
  member  = "serviceAccount:${google_service_account.automation.email}"
}
```

## Terraform: BigQuery Export Dataset

```terraform
resource "google_bigquery_dataset" "workload_manager_results" {
  project    = var.project_id
  dataset_id = "workload_manager_results"
  location   = "US"
}
```

Reference this dataset from the SDK or REST API with
`Evaluation.big_query_destination.destination_dataset`.

## Terraform: CMEK Prerequisites

```terraform
resource "google_kms_key_ring" "workload_manager" {
  project  = var.project_id
  name     = "workload-manager"
  location = var.location
}

resource "google_kms_crypto_key" "evaluations" {
  name            = "evaluations"
  key_ring        = google_kms_key_ring.workload_manager.id
  rotation_period = "7776000s"
}
```

Reference the key from the SDK or REST API with `Evaluation.kms_key` in this
format:

```text
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY
```

## Automation Boundary

```mermaid
flowchart LR
    TF["Terraform prerequisites"] --> API["Enable API"]
    TF --> IAM["Grant IAM roles"]
    TF --> BQ["Create BigQuery dataset"]
    TF --> KMS["Create KMS key"]
    SDK["SDK or REST"] --> Eval["Create and run evaluations"]
    Eval --> BQ
    Eval --> KMS
```

Keep prerequisite setup and evaluation execution separate. Evaluation runs are
operational actions with long-running operation state, so they fit better in
controlled SDK or REST automation than in a Terraform plan.
