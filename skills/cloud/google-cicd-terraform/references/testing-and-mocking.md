# Testing and Mocking GCP Infrastructure

Leverage `terraform test` (v1.6+) and `mock_provider` (v1.7+) to validate
infrastructure logic without deploying real resources.

## 🧪 Unit Testing with `terraform test`

Use assertions to verify that variables and resource configurations meet
requirements.

```terraform
# tests/vpc_validation.tftest.hcl
run "verify_vpc_naming" {
  command = plan

  assert {
    condition     = google_compute_network.main.name == "acme-prod-vpc"
    error_message = "VPC name did not match the expected prefix/env pattern."
  }

  assert {
    condition     = google_compute_network.main.auto_create_subnetworks == false
    error_message = "Auto-creation of subnetworks must be disabled."
  }
}
```

## 🎭 Mocking the GCP Provider

Mock providers allow CI pipelines to run tests without valid GCP credentials or
network access.

```terraform
# tests/mock_setup.tftest.hcl
mock_provider "google" {
  source = "hashicorp/google"
}

run "mock_instance_test" {
  command = plan

  # Override specific attributes if needed for logic checks
  override_resource {
    target = google_compute_instance.main
    values = {
      instance_id = "mock-12345"
    }
  }
}
```

## 🔍 Integration Assertions

Verify complex configurations like GKE Workload Identity or Private Google
Access.

```terraform
run "check_gke_config" {
  command = plan

  assert {
    condition     = can(google_container_cluster.main.workload_identity_config[0].workload_pool)
    error_message = "GKE cluster is missing Workload Identity configuration."
  }

  assert {
    condition     = alltrue([for s in google_compute_subnetwork.main : s.private_ip_google_access])
    error_message = "All subnets must have Private Google Access enabled."
  }
}
```
