# GCP Naming Conventions for Terraform

Standardizing resource names ensures compatibility with GCP's heterogeneous
naming requirements and maintains consistency across environments.

## 🏗️ Core Principles

1.  **Lowercase Only**: Most GCP resources (GCE, GCS, GKE) require lowercase
    alphanumeric characters and hyphens.
2.  **DNS Compliance (RFC 1035)**: Names must start with a letter, end with a
    letter or digit, and use only `-` (no underscores).
3.  **Object Naming (Underscores)**: Name all configuration objects
    (resource/data source identifiers) using **underscores**.
4.  **Resource Names (Hyphens)**: Use **hyphens** for the actual resource names
    within GCP.

Recommended:

```terraform
resource "google_compute_instance" "web_server" {
  name = "web-server"
}
```

## 📌 Resource-Specific Rules

Resource Type             | Regex Pattern                         | Max Length | Notes
:------------------------ | :------------------------------------ | :--------- | :----
`google_compute_instance` | `^[a-z]([-a-z0-9]*[a-z0-9])?$`        | 63         | RFC 1035 compliant.
`google_storage_bucket`   | `^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$` | 63         | Global namespace; no underscores.
`google_project`          | `^[a-z][a-z0-9-]{4,28}[a-z0-9]$`      | 30         | Must be globally unique.

## 🧩 The Singleton Pattern (`main`)

To simplify references to a resource that is the only one of its type in a
module, name the identifier `main`.

-   **Keep it singular**: Resource names should be singular.
-   **No redundancy**: Don't repeat the resource type in the identifier.

Recommended:

```terraform
resource "google_compute_network" "main" {
  name = "${var.prefix}-${var.environment}-vpc"
}
```

Not Recommended:

```terraform
resource "google_compute_network" "main_vpc" { ... }
```

## 🌍 Multi-Environment Prefixing

Always use a prefixing logic to prevent collisions and identify ownership.

```terraform
variable "prefix" {
  type        = string
  description = "Project or team prefix (e.g., 'acme')"
}

variable "environment" {
  type        = string
  description = "Target environment (e.g., 'prod', 'staging')"
}

# Implementation
resource "google_service_account" "app_sa" {
  account_id   = "${var.prefix}-${var.environment}-app"
  display_name = "Application Service Account for ${var.environment}"
}
```
