# Terraform Usage

You can use Terraform to build, change, and version Spanner infrastructure.

## Google Cloud Terraform Provider

The Google Cloud Terraform Provider supports the following Spanner resources:

-   `google_spanner_instance`
-   `google_spanner_database`
-   `google_spanner_instance_iam`
-   `google_spanner_database_iam`

## Example Usage

The following Terraform configuration creates a Spanner instance and a database.

```terraform
resource "google_spanner_instance" "example" {
  name         = "example-instance"
  config       = "regional-us-central1"
  display_name = "Example Instance"
  nodes        = 1
}

resource "google_spanner_database" "example" {
  instance = google_spanner_instance.example.name
  name     = "example-database"
}
```

For more information, see the official
[Google Cloud Terraform Provider documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs).
