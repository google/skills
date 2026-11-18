# Terraform Style and Structure Best Practices

This document outlines the standard style and directory structure for GCP
Terraform configurations, ensuring they are maintainable, readable, and follow
Google Cloud's recommended patterns.

## 📂 Standard Module Structure

Follow this layout for both reusable modules and root configurations:

-   `main.tf`: Default location for resources.
-   `variables.tf`: All variable declarations with types and descriptions.
-   `outputs.tf`: All output declarations with descriptions.
-   `README.md`: Module documentation (use `terraform-docs` for automation).
-   `examples/`: Subdirectories for each usage example with their own READMEs.
-   `scripts/`: Custom scripts called by Terraform provisioners.
-   `helpers/`: Scripts not called by Terraform.
-   `files/`: Static files (e.g., startup scripts).
-   `templates/`: Template files (use `.tftpl` extension).
-   `docs/`: Additional long-form documentation.

### Logical Grouping

Group resources by shared purpose rather than giving every resource its own
file.

-   `network.tf`: VPCs, subnets, firewall rules.
-   `instances.tf`: Compute Engine VMs, Managed Instance Groups.
-   `iam.tf`: Service accounts and IAM bindings.

## 🔢 Variables and Outputs

### Variables

-   **Units in Names**: Include units for numeric values (e.g., `ram_size_gb`,
    `disk_size_mib`).
-   **Binary vs Decimal**: Use binary prefixes (KiB, MiB, GiB) for storage and
    decimal (KB, MB, GB) for other measurements.
-   **Positive Booleans**: Name booleans positively (e.g.,
    `enable_external_access` instead of `disable_private_endpoint`).
-   **Mandatory Descriptions**: All variables must have `description` and
    `type`.
-   **Default Values**: Provide defaults for environment-independent values;
    omit them for environment-specific values (like `project_id`) to force
    explicit input.

### Outputs

-   **Resource Attributes**: Always reference resource attributes in outputs,
    not input variables, to preserve the dependency graph.
-   **Descriptions**: All outputs must have a `description`.

## 🛠️ Logic and Complexity

-   **Formatting**: Always run `terraform fmt`.
-   **Ternaries**: Never use more than one ternary operator on a single line.
-   **Complexity**: Split complex interpolated expressions into multiple `local`
    values.
-   **Count vs For Each**:
    -   Use `count` for conditional resource creation.
    -   Use `for_each` for multiple instances of a resource based on a map or
        set.

## 🔒 State Preservation

For stateful resources (Cloud SQL, Spanner, etc.), always enable deletion
protection.

```terraform
resource "google_sql_database_instance" "main" {
  name             = "primary-instance"
  database_version = "POSTGRES_15"

  settings {
    tier = "db-f1-micro"
  }

  deletion_protection = true

  lifecycle {
    prevent_destroy = true
  }
}
```
