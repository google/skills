# Google Cloud Global Load Balancer Official Terraform Module Guidelines

This reference document provides guidelines and examples for designing and managing Google Cloud Global External Application Load Balancer architectures using the official Google-managed Terraform modules (`lb-http` and `cloud-armor`).

---

## Core Directives

1.  **Prefer Official Modules:** Whenever generating complex, production-grade configurations, prefer using the official Google-supported modules to ensure best-practices, security defaults, and ongoing updates:
    *   **Load Balancer:** [terraform-google-lb-http](https://registry.terraform.io/modules/GoogleCloudPlatform/lb-http/google/latest)
    *   **Cloud Armor WAF:** [terraform-google-cloud-armor](https://registry.terraform.io/modules/GoogleCloudPlatform/cloud-armor/google/latest)
2.  **Module Versioning:** Always lock the module version to the latest stable major version (e.g., `version = "~> 10.0"` for `lb-http` or `version = "~> 2.0"` for `cloud-armor`) to prevent breaking changes.
3.  **Backend Structure:** Map the design spec origins to the `backends` map of the `lb-http` module. Each backend entry must configure `protocol`, `enable_cdn`, `cdn_policy`, and its target endpoint groups (`groups`).

---

## Comprehensive Multi-Backend Example

The following example demonstrates a complete, production-ready `main.tf` using the official modules to configure a Global External Application Load Balancer with three distinct backends (Serverless NEG for API, GCS Bucket for static content, and Cloud Armor security policies):

```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Cloud Armor Security Policies ---

module "security_policy_api" {
  source  = "GoogleCloudPlatform/cloud-armor/google"
  version = "~> 2.0"

  project_id   = var.project_id
  policy_name  = "${var.architecture_name}-waf-api"
  description  = "Cloud Armor WAF policy for API backends"
  default_action = "allow"

  # Rate limiting rule (100 RPM)
  rate_limiting_rules = [
    {
      action        = "throttle"
      priority      = 1000
      description   = "Rate limit API requests"
      src_ip_ranges = ["*"]
      
      rate_limit_options = {
        exceed_action            = "deny(403)"
        rate_limit_threshold = {
          count        = 100
          interval_sec = 60
        }
      }
    }
  ]

  # Preconfigured OWASP rules
  preconfigured_rules = [
    {
      action        = "deny(403)"
      priority      = 9000
      description   = "OWASP SQLi protection"
      expression    = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      src_ip_ranges = ["*"]
    },
    {
      action        = "deny(403)"
      priority      = 9001
      description   = "OWASP XSS protection"
      expression    = "evaluatePreconfiguredExpr('xss-v33-stable')"
      src_ip_ranges = ["*"]
    }
  ]
}

# --- Serverless NEG (Cloud Run) ---

resource "google_compute_region_network_endpoint_group" "serverless_neg" {
  name                  = "${var.architecture_name}-serverless-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  
  cloud_run {
    service = var.cloud_run_service_name
  }
}

# --- Global Load Balancer (Official Module) ---

module "gce_lb_http" {
  source  = "GoogleCloudPlatform/lb-http/google"
  version = "~> 10.0"

  project       = var.project_id
  name          = var.architecture_name
  firewall_networks = [] # Not creating internal firewall rules for global external LB

  # Frontend Configuration
  ssl                          = true
  use_ssl_certificates        = false
  ssl_certificates             = [google_compute_managed_ssl_certificate.default.id]
  http_forward                 = true

  backends = {
    # Default External Backend (API)
    default = {
      protocol        = "HTTP"
      enable_cdn      = true
      security_policy = module.security_policy_api.policy_id

      cdn_policy = {
        cache_mode = "USE_ORIGIN_HEADERS"
        cache_key_policy = {
          include_query_string = true
        }
      }

      groups = [
        {
          group = google_compute_global_network_endpoint_group.external_neg.id
        }
      ]
    }

    # GCS Bucket Backend
    gcs = {
      protocol        = "HTTP"
      enable_cdn      = true

      cdn_policy = {
        cache_mode  = "CACHE_ALL_STATIC"
        default_ttl = 2592000
        max_ttl     = 2592000
      }

      groups = [
        {
          group = "projects/${var.project_id}/global/backendBuckets/${var.architecture_name}-gcs-backend"
        }
      ]
    }

    # Serverless Backend
    serverless = {
      protocol        = "HTTP"
      enable_cdn      = true
      security_policy = module.security_policy_api.policy_id

      cdn_policy = {
        cache_mode  = "CACHE_ALL_STATIC"
        default_ttl = 2592000
        max_ttl     = 2592000
      }

      groups = [
        {
          group = google_compute_region_network_endpoint_group.serverless_neg.id
        }
      ]
    }
  }

  # Custom Path Routing Matchers
  url_map = {
    default_service = "default"
    path_matchers = {
      main-matcher = {
        default_service = "default"
        path_rules = [
          {
            paths   = ["/api", "/api/*"]
            service = "default"
          },
          {
            paths   = ["/static", "/static/*"]
            service = "gcs"
          },
          {
            paths   = ["/app", "/app/*"]
            service = "serverless"
          }
        ]
      }
    }
  }
}

resource "google_compute_managed_ssl_certificate" "default" {
  name = "${var.architecture_name}-cert"

  managed {
    domains = [var.domain_name]
  }
}
```
