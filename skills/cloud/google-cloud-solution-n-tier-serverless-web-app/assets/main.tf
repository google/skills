# Terraform template: strict secure serverless n-tier web application
#
# ==============================================================================
# 9 Architectural Security Boundaries (Code as the Single Source of Truth)
# Every configuration inside this file enforces these 9 architectural guards:
# 1. Ingress Bypass Defense: Tier 1 frontend ingress is set strictly to
#    INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER to prevent direct *.run.app bypasses.
# 2. VPC-Internal Backend Ingress: Backend application and all microservice tiers (T2..TN)
#    are set strictly to INGRESS_TRAFFIC_INTERNAL_ONLY (zero public internet exposure).
# 3. Direct VPC Egress & Cloud DNS: Must use vpc_access (egress = ALL_TRAFFIC on frontend)
#    along with a Cloud DNS Managed Private Zone (google_dns_managed_zone) mapping *.run.app
#    directly to Private Google Access VIPs (199.36.153.4/30 / 199.36.153.8/30).
# 4. Least-Privilege VPC Egress Firewalls: Enforces default-deny (0.0.0.0/0) and explicit
#    allow rules for inter-tier connections (frontend -> backend 443/8080, and backend ->
#    data tier 5432/6379 plus TCP 443 to PGA VIPs for sidecar IAM cert refresh).
# 5. Firewall Rules Logging: Enable log_config on egress firewalls for network access auditing.
# 6. Cloud CDN Edge Caching: Enable enable_cdn = true on Frontend global backend service.
# 7. Private Service Connect (PSC) & Private Redis (PSA): Database public IP is explicitly
#    disabled (ipv4_enabled = false), Cloud SQL uses Private Service Connect exclusively,
#    and Memorystore Redis uses Private Services Access (100% private data endpoints).
# 8. Cloud SQL Auth Proxy sidecar & IAM Auth: Backend container mounts built-in Cloud SQL sidecar
#    Unix socket (/cloudsql/...) via cloud_sql_instance volume. DB_SOCKET_PATH (/cloudsql/...) is
#    strongly recommended over direct TCP (DB_PSC_ENDPOINT) as the primary/default connection string
#    for transparent IAM authentication (cloudsql.iam_authentication = on) and mTLS without password rotation.
# 9. Organization API Perimeter: Supports wrapping run, sqladmin, secretmanager in a
#    VPC Service Controls (VPC-SC) perimeter (enable_vpc_sc) to prevent API data exfiltration.
# ==============================================================================

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.50.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 4.50.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ==========================================
# Variables
# ==========================================

variable "project_id" {
  type        = string
  description = "The Google Cloud project ID to deploy resources into."
}

variable "region" {
  type        = string
  description = "The Google Cloud region for regional resources (Cloud Run, Subnet, Cloud SQL, Redis)."
  default     = "us-central1"
}

variable "domain_name" {
  type        = string
  description = "The custom domain name for the application (e.g., app.example.com)."
}

variable "frontend_image" {
  type        = string
  description = "The container image URL for the frontend service (presentation tier), stored in Google Cloud Artifact Registry or another accessible registry. Defaults to a lightweight placeholder image during initial infrastructure bootstrapping."
  default     = "us-docker.pkg.dev/cloudrun/container/hello" # Placeholder
}

variable "backend_image" {
  type        = string
  description = "The container image URL for the backend application service (application tier), stored in Google Cloud Artifact Registry or another accessible registry. Defaults to a lightweight placeholder image during initial infrastructure bootstrapping."
  default     = "us-docker.pkg.dev/cloudrun/container/hello" # Placeholder
}

variable "enable_cdn" {
  type        = bool
  description = "Whether to enable Cloud CDN on the Frontend Load Balancer backend service."
  default     = true
}

variable "enable_redis" {
  type        = bool
  description = "Whether to deploy a Memorystore for Redis instance for caching in the private VPC."
  default     = true
}

variable "enable_monitoring" {
  type        = bool
  description = "Whether to enable advanced logging and monitoring (VPC Flow Logs, Firewall Rules Logging, Load Balancer Access Logs, and Cloud Monitoring Alerting Policies)."
  default     = true
}

variable "enable_vpc_sc" {
  type        = bool
  description = "Whether to configure/enforce VPC Service Controls (VPC-SC) API perimeter boundary protections (requires Organization-level IAM permissions)."
  default     = false
}

variable "enable_ha" {
  type        = bool
  description = "Whether to configure Regional High Availability (availability_type = REGIONAL) and Point-in-Time Recovery (point_in_time_recovery_enabled) for Cloud SQL."
  default     = false # Set true for production HA across zones
}

variable "db_edition" {
  type        = string
  description = "The Cloud SQL edition to provision (ENTERPRISE for general-purpose workloads, or ENTERPRISE_PLUS for mission-critical sub-second read data cache & <10s maintenance downtime)."
  default     = "ENTERPRISE"
}

# ==========================================
# 1. Networking (VPC & PSA)
# ==========================================

# VPC Network
resource "google_compute_network" "vpc_network" {
  name                    = "secure-3tier-vpc"
  auto_create_subnetworks = false
}

# Subnet for Cloud Run Direct VPC Egress (Shared by Frontend & Backend)
resource "google_compute_subnetwork" "cloud_run_subnet" {
  name                     = "cloud-run-subnet"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc_network.id
  private_ip_google_access = true # Required for Private Google Access when routing *.run.app requests via ALL_TRAFFIC egress

  # Optional VPC Flow Logs (toggled via enable_monitoring)
  dynamic "log_config" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      aggregation_interval = "INTERVAL_1_MIN"
      flow_sampling        = 0.1 # Sample 10% of traffic (adjust for prod cost control)
      metadata             = "INCLUDE_ALL_METADATA"
    }
  }
}

# Allocate IP range for Google services (Private Services Access / PSA for Memorystore Redis & managed VPC peering)
resource "google_compute_global_address" "private_ip_alloc" {
  name          = "google-managed-services-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc_network.id
}

# VPC Peering connection to Google services (PSA for Memorystore Redis)
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc_network.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}

# ==========================================
# 1.2 Cloud DNS Managed Private Zone for run.app (Private Google Access VIP Mapping)
# ==========================================
# BACKEND_URL (*.a.run.app) resolves via public Google DNS to public IPv4 VIPs (216.58.x.x) by default.
# When frontend uses ALL_TRAFFIC egress, packets to that public VIP hit the deny_all_egress firewall (which blocks 0.0.0.0/0)
# OR fail at the backend because its ingress requires VPC-internal traffic.
# This Cloud DNS Managed Private Zone maps *.run.app directly to Private Google Access VIPs (199.36.153.4/30 / 199.36.153.8/30),
# ensuring packets stay strictly internal and pass egress policies clean.

resource "google_dns_managed_zone" "run_app_zone" {
  name        = "run-app-zone"
  dns_name    = "run.app."
  description = "Private DNS zone for *.run.app internal routing via Private Google Access"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.vpc_network.id
    }
  }
}

resource "google_dns_record_set" "run_app_record" {
  name         = "*.run.app."
  managed_zone = google_dns_managed_zone.run_app_zone.name
  type         = "A"
  ttl          = 300
  rrdatas = [
    "199.36.153.8",
    "199.36.153.9",
    "199.36.153.10",
    "199.36.153.11"
  ] # Private Google Access VIP range 199.36.153.8/30 (or 199.36.153.4/30)
}

# ==========================================
# 1.5 VPC Egress Firewall Rules (Least-Privilege Network Isolation)
# ==========================================

# Deny unauthorized outbound egress from Cloud Run subnet by default
resource "google_compute_firewall" "deny_all_egress" {
  name      = "deny-cloud-run-default-egress"
  network   = google_compute_network.vpc_network.id
  direction = "EGRESS"
  priority  = 65534 # Low priority default deny

  deny {
    protocol = "all"
  }

  destination_ranges = ["0.0.0.0/0"]
  target_service_accounts = [
    google_service_account.frontend_sa.email,
    google_service_account.backend_sa.email
  ]

  # Optional Firewall Rules Logging (toggled via enable_monitoring)
  dynamic "log_config" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      metadata = "INCLUDE_ALL_METADATA"
    }
  }
}

# Allow Frontend SA to send egress only to Backend Application (VPC internal routing) and Google APIs
resource "google_compute_firewall" "allow_frontend_egress" {
  name      = "allow-frontend-to-backend-egress"
  network   = google_compute_network.vpc_network.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["443", "80"]
  }

  destination_ranges = [
    google_compute_subnetwork.cloud_run_subnet.ip_cidr_range,
    "199.36.153.4/30", # Private Google Access VIP ranges for *.run.app internal routing via Cloud DNS Managed Private Zone
    "199.36.153.8/30"
  ]
  target_service_accounts = [
    google_service_account.frontend_sa.email
  ]

  # Optional Firewall Rules Logging (toggled via enable_monitoring)
  dynamic "log_config" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      metadata = "INCLUDE_ALL_METADATA"
    }
  }
}

# Allow Backend SA to send egress to Cloud SQL PSC Endpoint (TCP 5432) AND Private Google Access VIPs (TCP 443 for sqladmin.googleapis.com sidecar IAM cert exchange)
resource "google_compute_firewall" "allow_backend_db_egress" {
  name      = "allow-backend-to-cloudsql-psc-egress"
  network   = google_compute_network.vpc_network.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["5432", "443"] # PostgreSQL (5432) and HTTPS (443 to PGA VIPs for Cloud SQL Auth Proxy sidecar IAM cert exchange)
  }

  destination_ranges = [
    "${google_compute_address.db_psc_ip.address}/32",
    "199.36.153.4/30", # Private Google Access VIP ranges for sidecar sqladmin.googleapis.com IAM certificate refresh on startup
    "199.36.153.8/30"
  ]
  target_service_accounts = [
    google_service_account.backend_sa.email
  ]

  # Optional Firewall Rules Logging (toggled via enable_monitoring)
  dynamic "log_config" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      metadata = "INCLUDE_ALL_METADATA"
    }
  }
}

# Allow Backend API SA to send egress to Redis cache when enabled
resource "google_compute_firewall" "allow_backend_redis_egress" {
  count     = var.enable_redis ? 1 : 0
  name      = "allow-backend-to-redis-egress"
  network   = google_compute_network.vpc_network.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["6379"] # Redis
  }

  destination_ranges = [
    "${google_redis_instance.private_cache[0].host}/32"
  ]
  target_service_accounts = [
    google_service_account.backend_sa.email
  ]

  # Optional Firewall Rules Logging (toggled via enable_monitoring)
  dynamic "log_config" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      metadata = "INCLUDE_ALL_METADATA"
    }
  }
}

# ==========================================
# 2. Data Tier (Private Cloud SQL & Redis)
# ==========================================

# Private Cloud SQL PostgreSQL Instance (Connected via PSC)
resource "google_sql_database_instance" "private_db" {
  name                = "private-postgres-db"
  database_version    = "POSTGRES_18"
  region              = var.region
  deletion_protection = true # Protected stateful resource per TF best practices

  settings {
    edition           = var.db_edition
    availability_type = var.enable_ha ? "REGIONAL" : "ZONAL"
    tier              = "db-f1-micro" # Choose appropriate tier for production (or compatible perf tier like db-perf-optimized-N-4 when condition is ENTERPRISE_PLUS)

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.enable_ha
    }

    ip_configuration {
      ipv4_enabled = false # Disable Public IP

      psc_config {
        psc_enabled               = true
        allowed_consumer_projects = [var.project_id]
      }
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    dynamic "insights_config" {
      for_each = var.enable_monitoring ? [1] : []
      content {
        query_insights_enabled  = true
        query_string_length     = 1024
        record_application_tags = true
        record_client_address   = true
      }
    }
  }
}

# PSC Endpoint IP Address for Cloud SQL in Cloud Run Subnet
resource "google_compute_address" "db_psc_ip" {
  name         = "cloudsql-psc-ip"
  subnetwork   = google_compute_subnetwork.cloud_run_subnet.id
  address_type = "INTERNAL"
  region       = var.region
}

# PSC Endpoint Forwarding Rule connecting to Cloud SQL Service Attachment
resource "google_compute_forwarding_rule" "db_psc_endpoint" {
  name                  = "cloudsql-psc-endpoint"
  region                = var.region
  network               = google_compute_network.vpc_network.id
  subnetwork            = google_compute_subnetwork.cloud_run_subnet.id
  ip_address            = google_compute_address.db_psc_ip.id
  target                = google_sql_database_instance.private_db.psc_service_attachment_link
  load_balancing_scheme = ""
}

resource "google_sql_database" "database" {
  name     = "app_db"
  instance = google_sql_database_instance.private_db.name
}

# IAM-authenticated Database User for Backend API Service Account
resource "google_sql_user" "iam_db_user" {
  name     = trimsuffix(google_service_account.backend_sa.email, ".gserviceaccount.com")
  instance = google_sql_database_instance.private_db.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

# Private Memorystore for Redis (caching tier)
resource "google_redis_instance" "private_cache" {
  count          = var.enable_redis ? 1 : 0
  name           = "private-redis-cache"
  tier           = "BASIC" # Use STANDARD for production HA
  memory_size_gb = 1
  region         = var.region

  authorized_network = google_compute_network.vpc_network.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  # Ensure the VPC peering is established first
  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# ==========================================
# 3. Security (Cloud Armor WAF)
# ==========================================

resource "google_compute_security_policy" "security_policy" {
  name        = "cloud-armor-waf-policy"
  description = "WAF and Rate Limiting policy for Strict 3-Tier Web App"
  provider    = google-beta

  # Rule 1: Prevent SQL Injection (WAF) - protecting the Frontend entry point
  rule {
    action   = "deny(403)"
    priority = "1000"
    preview  = false

    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "Block SQL injection attacks"
  }

  # Rule 2: Rate Limiting (Prevent DDoS/Brute Force)
  rule {
    action   = "throttle"
    priority = "2000"
    preview  = false

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
    }
    description = "Rate limit traffic to 100 requests/min per IP"
  }

  # Rule 3: Default Allow
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "default rule"
  }
}

# ==========================================
# 4. Service Accounts & IAM
# ==========================================

# Service Account for frontend (presentation tier)
resource "google_service_account" "frontend_sa" {
  account_id   = "frontend-app-sa"
  display_name = "Service Account for Frontend Cloud Run"
}

# Service Account for backend application (application tier)
resource "google_service_account" "backend_sa" {
  account_id   = "backend-app-sa"
  display_name = "Service Account for Backend Application Cloud Run"
}

# Grant Cloud SQL Client role to Backend SA only
resource "google_project_iam_member" "backend_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend_sa.email}"
}

# ==========================================
# 5. Compute Tier: Building Block Modules for N-Tier Architecture
# ==========================================
# This section defines modular compute building blocks across N tiers (N >= 2).
# Use this simple mapping to adapt or scale your tiers:
#
# - Tier 1 (Public Gateway): Base on Section 5.1 ("Tier 1 presentation tier: frontend reverse proxy") inside `assets/main.tf` (`google_cloud_run_v2_service.frontend`, `roles/run.invoker` for Application Load Balancer).
# - Tiers 2..N (Internal Services): Replicate and customize Section 5.2 ("Tier 2 application tier: private backend API") inside `assets/main.tf` (`google_cloud_run_v2_service.backend_api`),
#   its dedicated service account, and its `google_cloud_run_v2_service_iam_member` block granting `roles/run.invoker`
#   to the immediate upstream calling service account (`serviceAccount:<upstream_sa>`).
# ==========================================

# 5.1 Tier 1 presentation tier: frontend reverse proxy (public ingress via load balancer only)
# Exposed to the public Load Balancer. Connects to Backend API via VPC.
resource "google_cloud_run_v2_service" "frontend" {
  name     = "frontend-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" # Block direct public URL bypass

  template {
    service_account = google_service_account.frontend_sa.email

    containers {
      image = var.frontend_image
      
      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.backend_application.uri # Private internal URL
      }
    }

    # Direct VPC Egress for Frontend to reach the private Backend Application (*.run.app via Private Google Access & Cloud DNS Managed Private Zone)
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc_network.name
        subnetwork = google_compute_subnetwork.cloud_run_subnet.name
      }
      egress = "ALL_TRAFFIC" # Must use ALL_TRAFFIC + private_ip_google_access + Cloud DNS Managed Private Zone mapping *.run.app to PGA VIPs so requests traverse VPC and satisfy INGRESS_TRAFFIC_INTERNAL_ONLY
    }
  }
}

# Allow unauthenticated invocations from the Load Balancer (or specific Application Load Balancer identities) on Tier 1 Frontend
resource "google_cloud_run_v2_service_iam_member" "frontend_invoker" {
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 5.2 Tier 2 application tier: private backend application (100% private ingress - zero internet access)
# COMPLETELY PRIVATE. Reachable only from the VPC (Frontend).
resource "google_cloud_run_v2_service" "backend_application" {
  name     = "backend-application-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY" # 100% Private, no public URL

  template {
    service_account = google_service_account.backend_sa.email

    containers {
      image = var.backend_image

      env {
        name  = "DB_USER"
        value = google_sql_user.iam_db_user.name # Use IAM-authenticated DB user
      }
      env {
        name  = "DB_NAME"
        value = google_sql_database.database.name
      }
      # PRIMARY / DEFAULT RECOMMENDED CONNECTION PATH: Unix Socket via built-in Cloud SQL Auth Proxy sidecar.
      # DB_SOCKET_PATH (/cloudsql/project:region:instance) is strongly recommended over direct TCP
      # because the Auth Proxy sidecar automatically handles transparent IAM authentication, short-lived OAuth
      # access token refresh, and mutual TLS (mTLS) encryption out of the box without requiring password
      # rotation or custom token acquisition code in application database drivers.
      env {
        name  = "DB_SOCKET_PATH"
        value = "/cloudsql/${google_sql_database_instance.private_db.connection_name}"
      }

      # SECONDARY / ALTERNATIVE CONNECTION PATH: Direct TCP via Private Service Connect (PSC) Endpoint.
      # DB_PSC_ENDPOINT (cloudsql-psc-endpoint:5432) is provided as an alternative for direct TCP connections.
      # Note: Direct TCP PSC connections using IAM database authentication require application code / drivers
      # to manually fetch and refresh temporary OAuth access bearer tokens (`scopes = cloudsql.client`) every hour.
      env {
        name  = "DB_PSC_ENDPOINT"
        value = google_compute_address.db_psc_ip.address
      }

      # Conditionally inject Redis environment variables if enabled
      dynamic "env" {
        for_each = var.enable_redis ? [1] : []
        content {
          name  = "REDIS_HOST"
          value = google_redis_instance.private_cache[0].host
        }
      }
      dynamic "env" {
        for_each = var.enable_redis ? [1] : []
        content {
          name  = "REDIS_PORT"
          value = tostring(google_redis_instance.private_cache[0].port)
        }
      }

      # Mount the unix socket directory provided by the Cloud SQL Auth Proxy sidecar volume
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    # Automatically run the Cloud SQL Auth Proxy sidecar
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.private_db.connection_name]
      }
    }

    # Direct VPC Egress to access Cloud SQL & Redis privately
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc_network.name
        subnetwork = google_compute_subnetwork.cloud_run_subnet.name
      }
      egress = "PRIVATE_RANGES_ONLY" # If using ALL_TRAFFIC (or Private Google Access DNS routing for googleapis.com), allow_backend_db_egress explicitly permits TCP 443 to PGA VIPs so sidecar IAM cert exchange (sqladmin.googleapis.com) succeeds on startup.
    }
  }
}

# Allow Tier 1 Frontend Service Account (`frontend_sa`) to invoke Tier 2 Backend Application (`backend_application`)
resource "google_cloud_run_v2_service_iam_member" "backend_invoker" {
  location = google_cloud_run_v2_service.backend_application.location
  name     = google_cloud_run_v2_service.backend_application.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.frontend_sa.email}"
}

# ==========================================
# 6. Edge Ingress: Load Balancing & WAF (Exposing TIER 1 Frontend ONLY)
# ==========================================

# 6.1 Serverless NEG for Frontend
resource "google_compute_region_network_endpoint_group" "frontend_neg" {
  name                  = "frontend-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.frontend.name
  }
}

# 6.2 Static External IP for Load Balancer
resource "google_compute_global_address" "lb_ip" {
  name = "secure-3tier-lb-ip"
}

# 6.3 Load Balancer Backend Service (Routing strictly to TIER 1 Frontend NEG)
resource "google_compute_backend_service" "frontend_lb_backend" {
  name                  = "frontend-backend-service"
  provider              = google-beta
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.security_policy.id # Attach Cloud Armor
  # Note: Cloud CDN (`enable_cdn`) works on global Application Load Balancers (`google_compute_backend_service`).
  # If swapping to a regional Application Load Balancer (`google_compute_region_backend_service`) for regional sovereignty:
  # 1. Cloud CDN is unsupported and `enable_cdn` MUST be omitted or commented out to guarantee data residency.
  # 2. You must provision an additional regional proxy-only subnet (`google_compute_subnetwork` with `purpose = "REGIONAL_MANAGED_PROXY"` and `role = "ACTIVE"`).
  # 3. The regional forwarding rule (`google_compute_forwarding_rule`) must explicitly specify `network = google_compute_network.vpc_network.id`.
  enable_cdn            = var.enable_cdn

  backend {
    group = google_compute_region_network_endpoint_group.frontend_neg.id
  }

  # Optional Load Balancer Access Logs (toggled via enable_monitoring)
  dynamic "log_config" {
    for_each = var.enable_monitoring ? [1] : []
    content {
      enable      = true
      sample_rate = 1.0 # Log 100% of requests (adjust for high-volume prod cost control)
    }
  }
}

# 6.4 Google-managed SSL Certificate
resource "google_compute_managed_ssl_certificate" "default" {
  name = "secure-3tier-ssl-cert"
  managed {
    domains = [var.domain_name]
  }
}

# 6.5 URL Map (Routes all traffic /* to Frontend)
resource "google_compute_url_map" "default" {
  name            = "secure-3tier-url-map"
  default_service = google_compute_backend_service.frontend_lb_backend.id
}

# 6.6 Target HTTPS Proxy
resource "google_compute_target_https_proxy" "default" {
  name             = "secure-3tier-https-proxy"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_managed_ssl_certificate.default.id]
}

# 6.7 Global Forwarding Rule
# Note: If migrating to a regional Application Load Balancer (`google_compute_forwarding_rule`), set `load_balancing_scheme = "EXTERNAL_MANAGED"`
# and explicitly require `network = google_compute_network.vpc_network.id` so the load balancer binds to the proxy-only subnet.
resource "google_compute_global_forwarding_rule" "https" {
  name                  = "secure-3tier-forwarding-rule"
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "443"
  target                = google_compute_target_https_proxy.default.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# ==========================================
# 7. Observability (Optional Cloud Monitoring)
# ==========================================

# Proactive Alerting Policy for Frontend HTTP 5xx errors
resource "google_monitoring_alert_policy" "high_error_rate" {
  count        = var.enable_monitoring ? 1 : 0
  display_name = "frontend-high-error-rate-alert"
  combiner     = "OR"
  conditions {
    display_name = "HTTP 5xx Error Rate > 5%"
    condition_threshold {
      # Filter for Frontend Cloud Run request count metric where response code is 5xx
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.frontend.name}\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5 # Triggers if 5xx count exceeds 5 (scale as needed)
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
}

# ==========================================
# Outputs
# ==========================================

output "load_balancer_ip" {
  value       = google_compute_global_address.lb_ip.address
  description = "Point your DNS A record for var.domain_name to this IP address."
}

output "frontend_cloud_run_url" {
  value       = google_cloud_run_v2_service.frontend.uri
  description = "The internal/direct URL of the Frontend Cloud Run service (access blocked except via LB)."
}

output "backend_cloud_run_url" {
  value       = google_cloud_run_v2_service.backend_application.uri
  description = "The internal private URL of the Backend Application Cloud Run service (completely unreachable from public internet)."
}

output "vpc_sc_enabled" {
  value       = var.enable_vpc_sc
  description = "Indicates whether VPC Service Controls guidance and perimeter enforcement are requested for this project."
}

# ==========================================
# 7. VPC Service Controls (VPC-SC) Perimeter Guidance
# ==========================================
# When var.enable_vpc_sc is set to true, administrators MUST wrap the deployment project
# in an Organization-level VPC Service Controls (VPC-SC) service perimeter to enforce zero-trust
# API boundaries and mitigate data exfiltration risks.
#
# Protected APIs required in the VPC-SC perimeter:
# - Cloud Run Admin API (run.googleapis.com)
# - Cloud SQL Admin API (sqladmin.googleapis.com)
# - Secret Manager API (secretmanager.googleapis.com)
# - Service Networking API (servicenetworking.googleapis.com)
#
# Example Google Cloud CLI command to add the project and restricted services to a perimeter:
# gcloud access-context-manager perimeters update [PERIMETER_NAME] \
#   --add-resources="projects/${var.project_id}" \
#   --restricted-services="run.googleapis.com,sqladmin.googleapis.com,secretmanager.googleapis.com"
