# Cloud Run Serverless NFS Bridge Setup & Architecture

This guide explains how to set up, configure, and operate the **Serverless NFS
Bridge** on Cloud Run with Google Cloud Filestore.

--------------------------------------------------------------------------------

## 1. How Cloud Run NFS Volume Mounts Work

Cloud Run (2nd Generation execution environment) natively supports:

1.  **Direct VPC Egress:** Allows Cloud Run container instances to send egress
    traffic directly into a VPC network without requiring a Serverless VPC
    Access Connector.
2.  **NFS Volume Mounts:** Mounts standard NFSv3 / NFSv4.1 endpoints directly
    into the container filesystem at launch time (`/mnt/share`).

When deployed:

*   The container kernel handles NFS RPC calls directly.
*   Directory traversals and file reads execute as local Linux syscalls.
*   Cloud Run automatically scales to zero when no requests are active,
    resulting in **$0 idle compute cost**.

--------------------------------------------------------------------------------

## 2. Prerequisites & IAM Roles

To deploy the Cloud Run bridge service, the deployer needs:

*   `roles/run.admin` on the GCP Project
*   `roles/iam.serviceAccountUser` on the Cloud Run runtime service account
*   `roles/vpcaccess.user` or compute network viewing permissions

To invoke the bridge API, the caller/agent needs:

*   `roles/run.invoker` on the deployed Cloud Run service.

--------------------------------------------------------------------------------

## 3. Step-by-Step Manual Deployment

```bash
# 1. Retrieve Filestore IP & Share Name
FILESTORE_IP=$(gcloud filestore instances describe prod-filestore \
  --project=my-project \
  --location=us-central1-a \
  --format="value(networks[0].ipAddresses[0])")

FILE_SHARE=$(gcloud filestore instances describe prod-filestore \
  --project=my-project \
  --location=us-central1-a \
  --format="value(fileShares[0].name)")

# 2. Build Image via Cloud Build
gcloud builds submit scripts/bridge_server \
  --project=my-project \
  --tag=gcr.io/my-project/filestore-bridge:latest

# 3. Deploy to Cloud Run with Direct VPC Egress & NFS Mount
gcloud run deploy filestore-nfs-bridge \
  --project=my-project \
  --region=us-central1 \
  --image=gcr.io/my-project/filestore-bridge:latest \
  --network=default \
  --subnet=default \
  --vpc-egress=all-traffic \
  --add-volume="name=fs,type=nfs,location=${FILESTORE_IP}:/${FILE_SHARE}" \
  --add-volume-mount="volume=fs,mount-path=/mnt/share" \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=5
```

--------------------------------------------------------------------------------

## 4. API Endpoints Reference

| Method | Endpoint         | Query Parameters      | Description              |
| :----- | :--------------- | :-------------------- | :----------------------- |
| `GET`  | `/api/v1/health` | None                  | Checks if NFS mount is   |
:        :                  :                       : active and returns       :
:        :                  :                       : storage capacity.        :
| `GET`  | `/api/v1/tree`   | `path`, `depth`,      | Returns recursive        |
:        :                  : `max_entries`         : directory structure with :
:        :                  :                       : sizes and timestamps.    :
| `GET`  | `/api/v1/search` | `path`, `pattern`,    | Searches filenames by    |
:        :                  : `grep`, `max_results` : glob or searches file    :
:        :                  :                       : contents by regex.       :
| `GET`  | `/api/v1/read`   | `path`, `start_line`, | Reads line slices of     |
:        :                  : `end_line`, `head`,   : text files. Suppresses   :
:        :                  : `tail`                : binary files.            :
| `GET`  | `/api/v1/stat`   | `path`                | Returns POSIX metadata   |
:        :                  :                       : (size, mode, UID, GID,   :
:        :                  :                       : timestamps).             :

--------------------------------------------------------------------------------

## 5. Security & Read-Only Isolation

*   **Read-Only Invariant:** The bridge service contains no `POST`, `PUT`,
    `PATCH`, or `DELETE` routes.
*   **Path Traversal Protection:** All paths are sanitized against directory
    traversal attacks (`../`).
*   **Authentication:** All requests require valid Google Cloud OIDC tokens via
    `Authorization: Bearer {token}`.
