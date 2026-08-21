# Apigee Infrastructure as Code (Terraform)

You can automate the deployment of Apigee proxies, products, developers, and
apps using the Google Cloud Terraform Provider.

> [!NOTE] Terraform is supported for provisioning and managing Apigee resources.
> For a complete overview, see the
> [Google Cloud Terraform Overview](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/terraform-overview).
> This document serves as a reference configuration for automating a basic
> developer setup (proxies, products, developers, and apps) and requires the
> Terraform CLI and appropriate GCP permissions to execute.

This document outlines the primary resources and provides a comprehensive
configuration example. We assume that the **Apigee Organization** and
**Environment** are already provisioned.

--------------------------------------------------------------------------------

## 1. Primary Terraform Resources

*   **`google_apigee_api_proxy`**: Registers and imports an API Proxy
    configuration from a local zipped bundle.
*   **`google_apigee_api_product`**: Bundles proxies and resources, exposing
    them under specified environments and quotas.
*   **`google_apigee_developer`**: Registers developers within the Apigee
    identity database.
*   **`google_apigee_developer_app`**: Registers application profiles, binding
    developers to products, and triggers credential generation.

--------------------------------------------------------------------------------

## 2. Configuration Example

The following Terraform configuration imports a hello-world proxy zip bundle,
creates an API Product allowing access to it in the `prod` environment,
registers a developer, and creates a developer app to generate the consumer API
key.

```hcl
# Configure variables
variable "gcp_project" {
  type        = string
  description = "The GCP Project ID"
  default     = "my-apigee-project"
}

variable "apigee_org_id" {
  type        = string
  description = "The Apigee Organization ID (usually matches project ID)"
  default     = "my-apigee-project"
}

variable "apigee_env_name" {
  type        = string
  description = "The Apigee Environment to deploy to"
  default     = "prod"
}

# 1. Import the API Proxy from a local ZIP bundle
# Ensure `helloworld-proxy.zip` is generated and contains the standard `apiproxy` directory.
resource "google_apigee_api_proxy" "helloworld" {
  org_id      = var.apigee_org_id
  name        = "helloworld"
  config_bundle = "${path.module}/helloworld-proxy.zip"
}

# 2. Create the API Product bundling the helloworld proxy
resource "google_apigee_api_product" "internal_services" {
  org_id       = var.apigee_org_id
  name         = "InternalServicesProduct"
  display_name = "Internal Services Product"
  description  = "API Product to access helloworld services in prod."

  approval_type = "auto"
  environments  = [var.apigee_env_name]

  # Link the imported proxy
  proxies = [google_apigee_api_proxy.helloworld.name]

  # Set usage limits (Quota: 500 calls every 5 minutes)
  quota       = "500"
  quota_type  = "calendar"
  interval    = "5"
  time_unit   = "minute"

  attributes = {
    access = "public"
  }
}

# 3. Register a Developer
resource "google_apigee_developer" "alice" {
  org_id     = var.apigee_org_id
  email      = "alice@example.com"
  first_name = "Alice"
  last_name  = "Smith"
  user_name  = "asmith"
}

# 4. Create a Developer App associated with the Developer and Product
# This resource generates the client credentials (Consumer Key).
resource "google_apigee_developer_app" "alice_mobile_app" {
  org_id       = var.apigee_org_id
  developer_email = google_apigee_developer.alice.email
  name         = "AliceMobileApp"
  callback_url = "https://example.com/callback"

  # Bind the developer app to the API Product
  api_products = [google_apigee_api_product.internal_services.name]
}

# 5. Output the generated Consumer Key (API Key)
output "alice_api_key" {
  value       = google_apigee_developer_app.alice_mobile_app.client_id
  description = "Alice's generated API Key. Supply this in query parameter or header to access helloworld API."
  sensitive   = true
}
```

### Steps to Run

**1. Package your local proxy configuration into `helloworld-proxy.zip`**

```bash
zip -r helloworld-proxy.zip apiproxy/
```

**2. Initialize and apply the configuration using Terraform CLI**

```bash
terraform init
terraform apply -var="gcp_project=$PROJECT_ID" -var="apigee_org_id=$PROJECT_ID"
```

**3. Fetch the generated sensitive key**

```bash
terraform output -raw alice_api_key
```
