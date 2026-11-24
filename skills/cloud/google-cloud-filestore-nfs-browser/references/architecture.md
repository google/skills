# Multi-Engine Execution Architecture

Filestore shares are exposed via private RFC1918 IPs inside VPCs. The CLI helper
automatically routes requests through the best available engine:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          NFS BROWSER EXECUTION FLOW                         │
└─────────────────────────────────────────────────────────────────────────────┘

                  ┌─────────────────────────────────────┐
                  │ User Prompt / Agent Inspection Task │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │       scripts/nfs_browser.py        │
                  └──────────────────┬──────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
          [ Engine 1: Cloud Run ]         [ Engine 2: GCE IAP ]
            Serverless REST Bridge          GCE VM in VPC via IAP
            - Latency: <50ms                - Latency: 1-3s
            - Zero client tools             - Uses gcloud compute ssh
            - $0 idle (scales to 0)         - Existing VPC VM
```

## Engine Breakdown

### 1. Engine 1: Cloud Run Serverless NFS Bridge (Recommended)

*   **Architecture**: A lightweight FastAPI container deployed to Cloud Run with
    Direct VPC Egress and a second-generation Filestore NFS volume mount
    (`/mnt/share`).
*   **Deployment Command**:

    ```bash
    gcloud run deploy filestore-nfs-bridge \
      --region=${REGION} \
      --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/filestore-nfs-bridge/filestore-nfs-bridge:latest \
      --vpc-egress=all-traffic \
      --network=${VPC_NAME} \
      --subnet=${SUBNET_NAME} \
      --add-volume="name=fs,type=nfs,location=${FILESTORE_IP}:/${FILE_SHARE}" \
      --add-volume-mount="volume=fs,mount-path=/mnt/share" \
      --no-allow-unauthenticated
    ```
*   **IAM Permissions**:

    *   Deployer: `roles/run.admin` & `roles/iam.serviceAccountUser`.
    *   Caller / Agent: `roles/run.invoker`.
*   **Benefits**: Sub-50ms latency, zero client-side tools required, automatic
    scale-to-zero ($0 idle compute cost).
*   **Authentication**: Google Cloud OIDC identity tokens (`Authorization:
    Bearer $(gcloud auth print-identity-token)`).
*   See [references/nfs-bridge-setup.md](nfs-bridge-setup.md) for full setup
    instructions.

### 2. Engine 2: GCE Jump Host via IAP SSH (Zero-Deploy Fallback)

*   **Architecture**: Routes commands through an existing GCE VM residing in the
    target VPC using Identity-Aware Proxy (IAP) SSH tunneling.
*   **Execution**: Automatically translates browser requests into base64-encoded
    Python scripts executed remotely on the jump host VM.
*   **Benefits**: Requires zero infrastructure deployment; works out-of-the-box
    in environments with an existing VPC VM.
*   **Requirements**: GCE VM in the VPC with the NFS share mounted (default:
    `/mnt/filestore`), and IAM role `roles/iap.tunnelResourceAccessor`.
*   See [references/iap-jump-host.md](iap-jump-host.md) for configuration.

## Engine Comparison

| Feature                 | Engine 1 (Cloud Run    | Engine 2 (GCE IAP Jump  |
:                         : Bridge)                : Host)                   :
| :---------------------- | :--------------------- | :---------------------- |
| **Setup Overhead**      | One-time deployment    | Zero deployment (uses   |
:                         : (`deploy_bridge.sh`)   : existing VM)            :
| **Idle Cost**           | **$0** (scales to zero | Cost of existing GCE VM |
:                         : instances)             :                         :
| **Latency**             | **<50ms**              | 1–3s (SSH tunnel        |
:                         :                        : handshake)              :
| **Client Requirements** | None (standard         | `gcloud compute ssh`    |
:                         : curl/urllib)           :                         :
| **Security / IAM**      | OIDC token +           | IAP tunnel + OS Login / |
:                         : `roles/run.invoker`    : SSH keys                :
