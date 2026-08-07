# Cloud SQL Infrastructure as Code

Cloud SQL resources can be provisioned and managed using Terraform and other IaC
tools.

## Terraform

The Google Cloud Terraform provider supports Cloud SQL instances, databases, and
users.

### Cloud SQL Instance Example

```terraform
resource "google_sql_database_instance" "default" {
  name                = "master-instance"
  region              = "us-central1"
  database_version    = "POSTGRES_18"
  deletion_protection = false # Set to true for production to prevent accidental destruction

  settings {
    tier    = "db-custom-1-3840"
    edition = "ENTERPRISE"

    # Required database flag to enable IAM database authentication
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }
}

resource "google_sql_database" "database" {
  name     = "my-database"
  instance = google_sql_database_instance.default.name
}

# IAM Database Authentication (Requires cloudsql.iam_authentication = "on" database flag)
resource "google_sql_user" "iam_user" {
  name     = "user-email@example.com"
  instance = google_sql_database_instance.default.name
  type     = "CLOUD_IAM_USER"
}
```

### Key Terraform Configuration Notes

-   **IAM Database Authentication Flag:** Enabling IAM Database Authentication
    requires setting the database flag `cloudsql.iam_authentication = "on"`
    (for PostgreSQL) or `cloudsql_iam_authentication = "on"` (for MySQL) inside
    the `settings.database_flags` block. The user or service account must also
    be granted the `roles/cloudsql.instanceUser` IAM role.
-   **Deletion Protection:** By default, the Terraform Google provider sets
    `deletion_protection = true`. Set `deletion_protection = false` in dev/test
    environments if you intend to run `terraform destroy`.
-   **Point-in-Time Recovery (PITR):** Setting `enabled = true` in
    `backup_configuration` enables automated daily backups. Explicitly set
    `point_in_time_recovery_enabled = true` to enable continuous WAL archiving
    for PITR.
-   **Edition Selection:** Explicitly declare `edition = "ENTERPRISE"` or
    `edition = "ENTERPRISE_PLUS"` inside `settings` to define the feature set
    and SLA level.

### Reference Documentation

- [Terraform Google Provider - SQL Database Instance](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance)
- [Terraform Google Provider - SQL Database](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database)
- [Terraform Google Provider - SQL User](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_user)
