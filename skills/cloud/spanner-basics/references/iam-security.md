# IAM Security

Common IAM roles for Spanner and security best practices.

## Predefined IAM Roles

*   **Cloud Spanner Admin** (`roles/spanner.admin`): Full control over all
    Spanner resources.
*   **Cloud Spanner Database Admin** (`roles/spanner.databaseAdmin`): Full
    control over databases, backups, and operations.
*   **Cloud Spanner Database Reader** (`roles/spanner.databaseReader`): Can read
    data and execute queries.
*   **Cloud Spanner Database User** (`roles/spanner.databaseUser`): Can read and
    write data.
*   **Cloud Spanner Viewer** (`roles/spanner.viewer`): Can view Spanner
    resources but cannot access data.

## Security Best Practices

*   **Principle of Least Privilege**: Grant only the minimum necessary
    permissions to users and service accounts.
*   **Use Service Accounts**: For applications, use service accounts instead of
    personal user accounts.
*   **VPC Service Controls**: Use VPC Service Controls to help mitigate data
    exfiltration risks.
*   **CMEK**: Use Customer-Managed Encryption Keys (CMEK) if required by your
    security policy.

> [!CAUTION] Granting `roles/spanner.admin` gives full access to all Spanner
> resources in the project. Use with caution.
