# GCP Networking Patterns

GCP's global VPC architecture requires specific patterns for Shared VPCs,
Private Access, and Security Perimeters.

## 🤝 Shared VPC Configuration

In a Shared VPC topology, distinguish clearly between the **Host Project**
(manages the network) and the **Service Project** (hosts resources like GKE or
VMs).

### 1. Enabling the Host Project

```terraform
resource "google_compute_shared_vpc_host_project" "host" {
  project = var.host_project_id
}
```

### 2. Attaching a Service Project

```terraform
resource "google_compute_shared_vpc_service_project" "service" {
  host_project    = google_compute_shared_vpc_host_project.host.project
  service_project = var.service_project_id
}
```

## 🔒 Private Service Access (PSA)

Required for connecting to managed services like Cloud SQL or Redis via internal
IP addresses.

```terraform
# 1. Reserve an internal IP range
resource "google_compute_global_address" "private_ip_alloc" {
  name          = "google-managed-services-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

# 2. Establish the peering connection
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}
```

## 🛡️ VPC Service Controls (VPC-SC)

VPC-SC perimeters protect data in services like GCS and BigQuery. Ensure
Terraform has the necessary `access_context_manager` permissions to modify
perimeters.

```terraform
resource "google_access_context_manager_service_perimeter" "perimeter" {
  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/${var.perimeter_name}"
  title  = var.perimeter_name

  status {
    restricted_services = ["storage.googleapis.com", "bigquery.googleapis.com"]
    resources           = ["projects/${var.project_number}"]

    access_levels = [google_access_context_manager_access_level.main.name]
  }
}
```
