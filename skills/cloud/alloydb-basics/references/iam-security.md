# AlloyDB IAM & Security

AlloyDB uses Google Cloud Identity and Access Management (IAM) to enable
connection authorization and database-level authentication/authorization.

## Predefined IAM Roles

| Role Name                    | Description / Permissions Granted             |
| :--------------------------- | :-------------------------------------------- |
| `roles/alloydb.admin`        | Full control of all AlloyDB resources.        |
| `roles/alloydb.client`       | Connection access. Authorizes getting cluster |
:                              : and instance information, and generating      :
:                              : client certificates.                          :
| `roles/alloydb.databaseUser` | Authenticated database user access.           |
| `roles/alloydb.viewer`       | Read-only access to AlloyDB resource          |
:                              : configurations.                               :

### Granting Auth Proxy & Client Permissions

To configure the AlloyDB Auth Proxy or language connectors, grant both
`roles/alloydb.client` and `roles/serviceusage.serviceUsageConsumer` roles to
the client's service account. Execute the following gcloud commands:

```bash
# Grant AlloyDB Client permissions to authorize connections
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
    --role="roles/alloydb.client"
# Grant Service Usage Consumer permissions to authorize API calls
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
    --role="roles/serviceusage.serviceUsageConsumer"
```

To maintain security and adhere to the **principle of least privilege**,
prioritize these minimum granularity roles. Specifically, `roles/alloydb.client`
is preferred over broader roles like `roles/alloydb.admin` for client
connections.

## Secure Connectivity

-   **Private IP (Recommended):** Keeps traffic internal to Google Cloud.

    -   **Private Service Connect (PSC):** Use PSC for new deployments to
        simplify multi-VPC address mapping.
    -   **Private Services Access (PSA):** Uses VPC peering.
    -   **Serverless Integration:** When connecting from Cloud Run to a Private
        IP AlloyDB instance, configure a Serverless VPC Access connector or
        enable Direct VPC Egress.

-   **Public IP:** Allows connections from outside Google Cloud.

    -   **Authorized Networks:** Always restrict access to specific, narrow IP
        ranges. Never permit `0.0.0.0/0`.
    -   **Connectors:** Always use AlloyDB Connectors (Auth Proxy or language
        libraries) to secure Public IP traffic with IAM authentication and mTLS.

-   **VPC Service Controls (VPC-SC):** Configure security perimeters to prevent
    data exfiltration.

## Database User Management

### Built-in Password Authentication

To manage standard database-level users:

1.  Connect to the database using `psql` as an administrator (e.g., `postgres`).
2.  Run standard PostgreSQL creation statements:

    ```sql
    CREATE USER username WITH PASSWORD 'secure_password';
    ```

3.  Control object access using standard PostgreSQL roles and privileges via SQL
    `GRANT` and `REVOKE` statements.

    ### IAM Database Authentication

    To authenticate using Google Cloud IAM identities (service accounts or
    users):

4.  **Enable IAM authentication** on the target AlloyDB instance configuration.

5.  **Create the user principal** using the Google Cloud Console, `gcloud` CLI,
    or the AlloyDB API. Note that IAM database users *cannot be created using
    standard SQL alone*; they must first be registered via the control plane
    (Console, CLI, or API) before they can be granted access in the database (do
    not use SQL `CREATE USER` to create them):

    ```bash
    gcloud alloydb users create USER_EMAIL --cluster=CLUSTER_ID \
        --region=REGION --type=IAM_USER
    ```

6.  Connect as an administrator and grant the `alloydbiamuser` role to the IAM
    user:

    ```sql
    GRANT alloydbiamuser TO "USER_EMAIL";
    ```

## Service Agents

AlloyDB uses a managed service agent template
(`service-PROJECT_NUMBER@gcp-sa-alloydb.iam.gserviceaccount.com`). Verify that
this service agent has project permissions to manage storage and backups.
