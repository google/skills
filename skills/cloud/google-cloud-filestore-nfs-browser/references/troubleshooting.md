# Troubleshooting & Common Error Resolution

This runbook helps resolve common issues encountered while browsing Google Cloud
Filestore instances via the NFS Browser skill.

--------------------------------------------------------------------------------

## 1. Network & VPC Errors

### Error: `mount.nfs: Connection timed out`

*   **Root Cause:** VPC firewall rule is missing or blocking port 2049.
*   **Resolution:** Ensure an ingress firewall rule permits TCP/UDP port 2049
    between the client subnet (or Cloud Run Direct VPC Egress subnet) and the
    Filestore network:

    ```bash
    gcloud compute firewall-rules create allow-filestore-nfs \
      --network={vpc_network} \
      --allow=tcp:2049,udp:2049 \
      --source-ranges={client_subnet_cidr}
    ```

--------------------------------------------------------------------------------

## 2. Authentication & IAM Errors

### Error: `HTTP 401 Unauthorized` or `HTTP 403 Forbidden` on Bridge

*   **Root Cause:** Caller lacks `roles/run.invoker` on the Cloud Run service or
    identity token is expired.
*   **Resolution:**

    1.  Grant the invoker role:

        ```bash
        gcloud run services add-iam-policy-binding filestore-nfs-bridge \
          --region={region} \
          --member="user:{user_email}" \
          --role="roles/run.invoker"
        ```
    2.  Refresh the identity token:

        ```bash
        export FILESTORE_BRIDGE_TOKEN=$(gcloud auth print-identity-token)
        ```

--------------------------------------------------------------------------------

## 3. Path & File Inspection Errors

### Error: `Path not found: /xyz`

*   **Root Cause:** Path specified is relative or does not exist on the NFS
    export.
*   **Resolution:** Run `tree` with `--path=/` and `--depth=1` to explore the
    root directory structure first.

### Error: `Binary file detected. Raw content suppressed.`

*   **Root Cause:** Target file contains binary data (e.g. tarball, zip, ELF
    binary).
*   **Resolution:** Use `stat` command to view file metadata, or use specific
    line slices if viewing text embedded in files.
