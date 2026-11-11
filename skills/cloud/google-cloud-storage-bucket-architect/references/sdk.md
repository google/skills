# Cloud Storage SDK Reference

> [!IMPORTANT]
>
> **DO NOT RUN THESE CONFIGURATIONS AUTOMATICALLY.** Present the generated SDK
> code snippets to the user for review and integration. Read the target
> language's dedicated reference file (`references/sdk_python.md`,
> `references/sdk_go.md`, `references/sdk_java.md`, or `references/sdk_cpp.md`)
> for its complete **Translation Mapping Table** and code examples.

## Official Documentation Reference

### Cloud Storage (Data Plane)

*   [Cloud Storage C++ Client Library](https://cloud.google.com/cpp/docs/reference/storage/latest)
*   [Cloud Storage Go Package Reference](https://pkg.go.dev/cloud.google.com/go/storage)
*   [Cloud Storage Java Client Library](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview)
*   [Cloud Storage Python Client Library](https://cloud.google.com/python/docs/reference/storage/latest)

### Cloud Storage Control (Control Plane — Hierarchical Namespace, Folders, Rapid Cache)

*   [Cloud Storage Control C++ Client Library](https://cloud.google.com/cpp/docs/reference/storagecontrol/latest)
*   [Cloud Storage Control Go Package Reference](https://pkg.go.dev/cloud.google.com/go/storage/control/apiv2)
*   [Cloud Storage Control Java Client Library](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.storage.control.v2.StorageControlClient)
*   [Cloud Storage Control Python Client Library](https://cloud.google.com/python/docs/reference/google-cloud-storage-control/latest/google.cloud.storage_control_v2.services.storage_control.StorageControlClient)

--------------------------------------------------------------------------------

## SDK Language Guides & Version Gates Summary

Language   | Language Guide                    | `EncryptionEnforcementConfig` Min Version | Unexposed Features (Require REST / `gcloud` / Terraform)
:--------- | :-------------------------------- | :---------------------------------------- | :-------------------------------------------------------
**Python** | [Python SDK Guide](sdk_python.md) | `google-cloud-storage >= 3.10.0`          | All core bucket settings exposed (`StorageControlClient` for Rapid Cache / HNS folders)
**Go**     | [Go SDK Guide](sdk_go.md)         | `cloud.google.com/go/storage >= v1.61.0`  | **IP Filtering** (`ipFilter` / `allowCrossOrgVpcs` not exposed in Go v1 client)
**Java**   | [Java SDK Guide](sdk_java.md)     | `google-cloud-storage >= 2.55.0`          | All core bucket settings exposed (`StorageControlClient` for Rapid Cache / HNS folders)
**C++**    | [C++ SDK Guide](sdk_cpp.md)       | `google-cloud-cpp >= 2.46.0`              | **IP Filtering** (`ipFilter` / `allowCrossOrgVpcs` not exposed in C++ client)

> [!IMPORTANT]
>
> Whenever `EncryptionEnforcementConfig` (restricting CSEK/CMEK/GMEK) is
> configured in an SDK snippet, you **MUST** include a warning specifying the
> minimum supported SDK version from the table above and noting that users on
> older SDK versions must configure encryption enforcement via the
> [REST API](rest.md), [gcloud](gcloud.md), or [Terraform](terraform.md). When
> generating SDK code snippets for the user, do **not** run local shell or
> language commands (e.g., `python3`, `pip`, `go list`) to inspect the host
> machine's installed SDK version unless the user explicitly asks to inspect or
> execute in their local environment.

--------------------------------------------------------------------------------

## Handling Unexposed Features

When a required setting is marked as *Not exposed* in the target language's
client library (or the user is on an older SDK version), recommend one of these
integration patterns:

1.  **Pattern 1: Separate Provisioning from Application Logic (Recommended)**:
    Use [Terraform](terraform.md) or [gcloud](gcloud.md) to create and configure
    the bucket (including IP Filtering or Encryption Enforcement), and use the
    SDK in application code for data-plane operations.
2.  **Pattern 2: Hybrid SDK + Direct REST API Call**: Use the SDK to create the
    bucket and obtain an OAuth2 token from the SDK credentials helper, then send
    a `PATCH https://storage.googleapis.com/storage/v1/b/BUCKET_NAME` request
    with the JSON payload, `Authorization: Bearer <token>`, and
    `User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)`
    headers (see [REST API Reference](rest.md)).
3.  **Pattern 3: Hybrid SDK + Auto-Generated API Client (Go Only)**: Combine the
    standard `cloud.google.com/go/storage` client with the raw auto-generated
    `google.golang.org/api/storage/v1` client for unexposed fields (both clients
    can share the same authenticated HTTP client for connection reuse).
