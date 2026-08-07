# Cloud SQL IAM & Security

Cloud SQL uses Identity and Access Management (IAM) to control access to
instances and databases for all supported engines of Cloud SQL. All three engines
such as PostgreSQL, MySQL and SQL Server can be created and secured.

## Predefined IAM Roles

| Predefined Role | Usage |
| :--- | :--- |
| `roles/cloudsql.admin` | Full control over all Cloud SQL resources. |
| `roles/cloudsql.editor` | Manage Cloud SQL resources. Cannot see or modify

 permissions, nor modify users or ssl Certs. Cannot import data or restore from
a backup, nor clone, delete, or promote instances. Cannot start or stop
  replicas. Cannot delete databases, replicas, or backups. |
| `roles/cloudsql.viewer` | Read-only access to Cloud SQL resources. |
| `roles/cloudsql.client` | Connectivity access to Cloud SQL instances from App
 Engine and the Cloud SQL Auth Proxy. Not required for accessing an instance
  using IP addresses. |
| `roles/cloudsql.instanceUser` | Permission to log in to a Cloud SQL
  instance. |
| `roles/cloudsql.schemaViewer` | Role allowing access to a Cloud SQL instance
  schema in Knowledge Catalog. |
| `roles/cloudsql.studioUser` | Role allowing access to Cloud SQL Studio. |

## IAM Best Practices & Least Privilege

To secure Cloud SQL, follow the **Principle of Least Privilege (PoLP)**. Grant
members only the minimum permissions necessary to perform their tasks, and
restrict powerful roles.

-   **Important:** Administrative roles such as `roles/cloudsql.admin` grant full
    control over instances (including deletion and credential management).
    These roles should be granted with extreme caution and reserved exclusively
    for automated deployment pipelines or designated database administrators. Do
    not grant them to general developers or application runtimes.
-   **Separation of Duties:**
    -   Use `roles/cloudsql.admin` for provisioning and instance creation.
    -   Use `roles/cloudsql.client` and `roles/cloudsql.instanceUser` for
        application connectivity and access.
    -   Avoid broad project-level roles like `roles/editor` or `roles/owner` for
        database access.
-   **`setIamPolicy` Risk & Privilege Escalation:**
    -   **Included Roles:** Roles containing `cloudsql.instances.setIamPolicy`
        include `roles/cloudsql.admin`, `roles/resourcemanager.projectIamAdmin`,
        and `roles/owner` (note that `roles/cloudsql.editor` does **not**
        include `setIamPolicy`).
    -   **Escalation Risk:** Any identity with `setIamPolicy` permissions can
        modify IAM policies and grant themselves or others elevated roles,
        leading to complete privilege escalation.
    -   **Best Practices:**
        -   Never grant `setIamPolicy` permissions to application runtimes or
            general developers.
        -   Restrict `setIamPolicy` exclusively to automated CI/CD deployment
            pipelines or designated security administrators.
        -   Enable Data Access audit logging for IAM policy changes and use
            IAM Role Recommendations to detect over-privileged bindings.

### Example: Granting Permissions to Create Instances

To allow a deployment service account to provision Cloud SQL instances, grant
it the `roles/cloudsql.admin` role at the project level:

```bash
gcloud projects add-iam-policy-binding project_id \
    --member="serviceAccount:deployment_sa@project_id.iam.gserviceaccount.com" \
    --role="roles/cloudsql.admin"
```

## Secure Connectivity

-   **Cloud SQL Auth Proxy:** The recommended way to connect securely. It
    provides IAM-based authentication and end-to-end encryption without
    requiring SSL/TLS certificates or authorized networks.

-   **Private IP:** Use VPC, private services access, or Private Service Connect
    (PSC) to keep database traffic within the Google Cloud network.

-   **Authorized Networks:** If using Public IP, restrict access to specific
    CIDR ranges.
-   **VPC Service Controls (VPC-SC):** Establish a security perimeter around
    your database instances to prevent data exfiltration.

-   **Server Certificate Authorities (CA):** Choose a CA hierarchy (`serverCaMode`)
    to sign database server certificates:
    - `GOOGLE_MANAGED_INTERNAL_CA` (Per-instance CA): Dedicated unique CA per
      instance.
    - `GOOGLE_MANAGED_CAS_CA` (Shared CA): Regional shared CA managed by Google.
    - `CUSTOMER_MANAGED_CAS_CA` (Customer-managed CA): Integrates with your own
      CA Service pool.
    - **Recommendation:** Use **Customer-managed CA** for maximum security to
      maintain ownership of the trust anchor, utilize modern ECDSA 256-bit keys,
      and support custom DNS naming.

-   **SSL/TLS Enforcement:** Enforce encryption for all incoming connections
    by configuring the instance `sslMode` (or `--ssl-mode` in CLI / `ssl_mode` 
    in Terraform):
    - `ALLOW_UNENCRYPTED_AND_ENCRYPTED`: Default mode; allows both unencrypted 
       and encrypted connections.
    - `ENCRYPTED_ONLY`: Restricts connections to SSL/TLS encrypted traffic only.
    - `TRUSTED_CLIENT_CERTIFICATE_REQUIRED`: Enforces Mutual TLS (mTLS), 
       requiring client certificates.
    - **Recommendation:** Use **`ENCRYPTED_ONLY`** or
      **`TRUSTED_CLIENT_CERTIFICATE_REQUIRED`** to prevent transmission of 
      credentials in clear text.
    - *Note:* Enforcing SSL requires an automatic instance restart for MySQL and 
      SQL Server. For PostgreSQL, the change applies to new connections without 
      restarting, but existing unencrypted connections remain active until a 
      manual restart.

## Data Security

-   **Encryption at Rest:** All data is encrypted by default. Use
    Customer-Managed Encryption Keys (CMEK) for additional control.

-   **IAM Database Authentication:** Authenticate to the database using IAM
    users or service accounts instead of static passwords (available for MySQL
    and PostgreSQL).

-   **Least Privilege IAM Roles:**
    - Grant the application's service account the roles/cloudsql.client role.
    - Grant database login rights using roles/cloudsql.instanceUser.
    - Avoid assigning admin roles like roles/cloudsql.admin to applications.

-   **Password Policies:** Enforce security requirements for built-in database users:
    - **Instance-level policy:** Configure a `password_validation_policy` (via
      Terraform or CLI) to enforce minimum length, complexity checks
      (`COMPLEXITY_DEFAULT`), password reuse restrictions, and to disallow
      username substrings.
    - **User-level policy (MySQL 8.0+):** Enforce password expiration, account
      locking after failed attempts (`--password-policy-allowed-failed-attempts`),
      and current password verification using `gcloud sql users set-password-policy`.
    - **Recommendation:** Use IAM Database Authentication where possible to
      bypass database passwords entirely. For built-in accounts, enable the
      instance-level password validation policy.

-   **Client-Side Encryption:** Protect sensitive data at the column level (e.g.,
    credit card numbers, PII) before writing to the database:
    -   Encrypt data using cryptographic libraries like **Tink** combined with
        keys stored in **Cloud KMS**.
    -   Enforces double access control: a client must have both database query
        access and IAM permissions to decrypt the Cloud KMS key.

## Audit Logging

Cloud SQL supports both Google Cloud-level auditing and database engine-level
auditing to track administrative and database access events.

-   **Cloud Audit Logs:** Admin Activity logs are enabled by default. To track
    data access, you must explicitly enable **Data Access audit logs** for the
    Cloud SQL Admin API in your project's IAM configuration.
-   **Database Auditing:** Enable database-specific plugins to log SQL queries,
    logins, and local actions to Cloud Logging:
    -   **MySQL:** Enable the `cloudsql_mysql_audit` database flag (requires an
        instance restart).
    -   **PostgreSQL:** Set the `cloudsql.enable_pgaudit` flag to `on` (requires
        an instance restart), run `CREATE EXTENSION pgaudit;` in the database,
        and configure the `pgaudit.log` flag (e.g., set to `all` or `write`).
    -   **SQL Server:** Specify a Cloud Storage bucket using the
        `--audit-bucket-path` flag to upload audit logs (requires an instance
        restart).

## Brute-Force Protection & Threat Detection

Cloud SQL provides built-in mechanisms and integration with Security Command
Center (SCC) to detect and protect instances against brute-force attacks:

-   **Automated Login Throttling:** Cloud SQL tracks failed connection attempts.
    When consecutive failures exceed a threshold, Cloud SQL logs a warning with
    the IP address and username, and automatically introduces real-time
    response delays (throttling) to slow down attack attempts.
-   **Account Lockout (MySQL 8.0+):** Enforce user password policies to lock
    accounts after a set number of failed attempts using
    `--password-policy-allowed-failed-attempts`.
-   **Security Command Center (SCC):** Event Threat Detection analyzes Cloud
    Logging to alert on repeated failed login attempts, unexpected superuser
    queries, or data exfiltration events.
-   **Recommended Mitigation:** Use IAM Database Authentication or the Cloud
    SQL Auth Proxy to bypass database passwords entirely and eliminate static
    credential brute-force vectors.

## Organization Policies

-   **Cloud SQL organization policies:** Organization policies let organization
    administrators set restrictions on how users can configure instances under
    that organization.

## Resource Manager Tags

Resource Manager tags are key-value pairs that can be attached to Cloud SQL
instances to manage access, IAM conditions, and organization policies.

-   **IAM Enforcement:** Unlike labels (which are for billing/grouping), tags
    integrate with IAM policies. You can restrict actions (e.g., preventing
    instance deletion) based on tags like `environment/production`.
-   **IAM Conditions:** Combine tags with IAM conditions to grant permissions
    only to instances with specific tag bindings.
-   **Tag Format:** In `gcloud` commands, reference tags using either:
    -   **Resource IDs (Recommended):** `tagKeys/TAG_KEY_ID=tagValues/TAG_VALUE_ID`
        (e.g., `tagKeys/123456789012=tagValues/987654321098`)
    -   **Namespaced Path:** `ORGANIZATION_ID/KEY_SHORT_NAME/VALUE_SHORT_NAME`
        (e.g., `123456789012/environment/production`)
-   **gcloud configuration:** Attach tags when creating instances using the
    `--tags` flag:
    ```bash
    gcloud sql instances create instance_name \
        --tags="tagKeys/123456789012=tagValues/987654321098" \
        --database-version=POSTGRES_18 \
        --cpu=2 \
        --memory=7680MiB \
        --region=region
    ```

## Service Accounts

-   **Service Identity:** Cloud SQL uses an instance service account
    (`p[PROJECT_NUMBER]-[UNIQUE_ID]@gcp-sa-cloud-sql.iam.gserviceaccount.com`)
    for tasks like exporting a SQL dump file to Cloud Storage. Service agent
    accounts (`service-PROJECT_NUMBER@gcp-sa-cloud-sql.iam.gserviceaccount.com`)
    are used only for internal management tasks.


For more information, see:

- [About Access Control - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/instance-access-control.md.txt)
- [About Access Control - Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/instance-access-control.md.txt)
- [About Access Control - Cloud SQL for SQL Server](https://docs.cloud.google.com/sql/docs/sqlserver/instance-access-control.md.txt)
- [Configure SSL/TLS & CAs - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/configure-ssl-instance.md.txt)
- [Configure SSL/TLS & CAs - Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/configure-ssl-instance.md.txt)
- [Customer-Managed CAs - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/customer-managed-ca.md.txt)
- [Database Audit Logging - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/use-db-audit.md.txt)
- [Database Audit Logging (pgAudit) - Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/pg-audit.md.txt)
- [Database Audit Logging - Cloud SQL for SQL Server](https://docs.cloud.google.com/sql/docs/sqlserver/db-audit.md.txt)
- [Client-Side Encryption - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/client-side-encryption.md.txt)
- [Manage Resource Manager Tags - Cloud SQL](https://docs.cloud.google.com/sql/docs/mysql/manage-tags.md.txt)
- [Brute-Force Protection - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/use-brute-force-protection.md.txt)
- [Brute-Force Protection - Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/use-brute-force-protection.md.txt)