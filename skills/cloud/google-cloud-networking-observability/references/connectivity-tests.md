# Connectivity Tests Reference

Use Network Intelligence Center Connectivity Tests to verify reachability and
identify firewall or routing blocks along a network path.

## Critical Verification & Cleanup Rules

1.  **Instance State Verification**: Always check whether the source and
    destination VM instances are `RUNNING` (a static `REACHABLE` configuration
    trace does not mean live traffic will succeed if a VM is `TERMINATED` or
    `STOPPED`). Also resolve the source VM's `{zone}` if not provided:
    ```bash
    gcloud compute instances list --project={project_id} \
      --filter="name=({src_vm})" --format="table(name,zone.basename(),status,networkInterfaces[0].networkIP)"
    ```
2.  **Mandatory Test Deletion**: When creating a temporary Connectivity Test,
    you **MUST** delete the test resource as your final step after retrieving
    results.

## Execution Workflow

-   **MCP Tools** (when declared): `create_connectivity_test` →
    `get_connectivity_test` → `delete_connectivity_test`.
-   **CLI (`gcloud`)**:

```bash
# 1. Create and run reachability analysis (blocks until initial analysis completes unless --async is set)
gcloud network-management connectivity-tests create {test_name} \
  --source-instance=projects/{project_id}/zones/{zone}/instances/{src_vm} \
  --destination-ip-address={dest_ip} \
  --destination-port={port} \
  --protocol=TCP \
  --project={project_id}

# 2. Inspect reachabilityDetails.result (REACHABLE, UNREACHABLE, AMBIGUOUS, UNDETERMINED) and trace steps
gcloud network-management connectivity-tests describe {test_name} \
  --project={project_id} --format=json

# 3. Clean up the temporary test resource
gcloud network-management connectivity-tests delete {test_name} \
  --project={project_id} --quiet
```

*(For VM-to-VM destination by name rather than IP, replace
`--destination-ip-address={dest_ip}` with
`--destination-instance=projects/{project_id}/zones/{dest_zone}/instances/{dest_vm}`.)*

## Reference Documentation

-   [Running Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests.md.txt)
