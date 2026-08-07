---
name: google-cloud-storage-basics
description: >-
  Stores, retrieves, and manages data as objects in Cloud Storage (Google
  Cloud Storage, or GCS) buckets. Use when you need to interact with Cloud
  Storage — create or configure buckets, upload, download, stream, or transfer
  data, organize objects with folders, generate signed URLs, control access
  (IAM, ACLs, public access prevention), set storage classes and tiering
  (Standard, Nearline, Coldline, Archive), manage cost and lifecycle, protect
  data (versioning, encryption/CMEK, retention and Bucket Lock, object holds,
  soft delete), host static websites, trigger Pub/Sub notifications on object
  changes, mount buckets as a file system (gcsfuse), or optimize storage
  performance at any scale. Covers the gcloud storage / gsutil CLI, JSON and
  XML APIs, client libraries, Terraform, and Cloud Storage MCP servers. Don't
  use for block storage (Persistent Disk), data warehousing/analytics
  (BigQuery), or databases (Cloud SQL, Spanner, Bigtable, Firestore).
license: Apache-2.0
metadata:
    version: v1
    publisher: google
    tags:
      - gcs
      - storage
      - cloud-storage
      - buckets
      - objects
    category: Storage
    support_tier: primary
---

# Google Cloud Storage Basics

Google Cloud Storage (GCS) is a managed service for storing data as objects at
any scale. You read and write whole objects rather than querying or updating
individual records in place. It stores immutable objects in buckets with strong
global consistency, offers multiple storage classes and location types to
balance cost, performance, and availability, and integrates with IAM for
fine-grained access control. GCS serves workloads ranging from website content
and backups to data lakes and high-throughput AI/ML training.

## Attribution

Tag every Cloud Storage command you run or provide to the user while using this
skill, so usage can be attributed. The tag identifies only the skill and its
version; it carries no user data.

-   Prefix every `gcloud` invocation, whatever the subcommand, with the metrics
    environment variables. Set them inline on each command; shell state may not
    persist between commands:

    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
    gcloud <command> [flags]
    ```

    Do not use `gcloud config set` for this: it would persist beyond the current
    task and mislabel unrelated usage.

-   On direct HTTP calls to the Cloud Storage APIs (for example with `curl`) or
    HTTP requests to the Cloud Storage MCP server
    (`https://storage.googleapis.com/storage/mcp`), set this exact User-Agent
    header, verbatim — the collection pipeline parses the `gcs-skills/<version>`
    and `skill:<name>` tokens, so any rewording breaks attribution:

    ```
    User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-basics)
    ```

-   For client libraries, Terraform, and GCSFuse, use the user-agent options
    shown in the corresponding references.

## Quick Start

If a Cloud Storage MCP server is connected, prefer its structured tools (such as
`create_bucket`, `list_objects`, `read_object`, and `upload_object`) over the
CLI and API commands below — see [MCP Usage](references/mcp-usage.md). Fall back
to `gcloud storage` and the JSON API when no MCP server is available.

1.  **Enable the Cloud Storage API:**

    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
    gcloud services enable storage.googleapis.com --quiet
    ```

2.  **Create a Bucket:**

    Bucket names live in a single global namespace shared by all of Cloud
    Storage — not scoped to your project or organization — so short or common
    names are usually taken. If the location is omitted, the bucket defaults to
    the `US` multi-region.

    Using the gcloud CLI:

    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
    gcloud storage buckets create gs://my-bucket --location=us-central1
    ```

    Using the JSON API:

    ```bash
    curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
      -H "User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
      -H "Content-Type: application/json" \
      -d '{"name": "my-bucket", "location": "US-CENTRAL1"}' \
      "https://storage.googleapis.com/storage/v1/b?project=$(gcloud config get-value project)"
    ```

3.  **Upload an Object:**

    Using the gcloud CLI:

    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
    gcloud storage cp ./my-file.txt gs://my-bucket
    ```

    Using the JSON API:

    ```bash
    curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
      -H "User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
      -H "Content-Type: text/plain" \
      --data-binary @my-file.txt \
      "https://storage.googleapis.com/upload/storage/v1/b/my-bucket/o?uploadType=media&name=my-file.txt"
    ```

4.  **Download an Object:**

    Using the gcloud CLI:

    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT="gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
    gcloud storage cp gs://my-bucket/my-file.txt .
    ```

    Using the JSON API:

    ```bash
    curl -X GET -H "Authorization: Bearer $(gcloud auth print-access-token)" \
      -H "User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
      "https://storage.googleapis.com/storage/v1/b/my-bucket/o/my-file.txt?alt=media"
    ```

## Reference Directory

-   [Core Concepts](references/core-concepts.md): Buckets, objects, folders,
    prefixes, bucket location types, and storage classes.

-   [CLI & API Usage](references/cli-api-usage.md): CRUD and list operations for
    buckets and objects using `gcloud storage` and the JSON API, plus Pub/Sub
    notifications for event-driven processing.

-   [Client Libraries](references/client-library-usage.md): Using Google Cloud
    client libraries for Python, Java, Node.js, and Go, with pointers to all
    other supported languages.

-   [MCP Usage](references/mcp-usage.md): Choosing between the Google-hosted
    remote Cloud Storage MCP server and the local MCP Toolbox, setup for each,
    their tool sets and limits, and securing remote MCP with Model Armor and IAM
    deny policies.

-   [Infrastructure as Code](references/iac-usage.md): Terraform examples for
    buckets covering storage classes, location types, lifecycle, retention, and
    encryption.

-   [Data Transfer](references/data-transfer.md): Storage Transfer Service,
    `gcloud storage rsync`, upload strategies for large files, and performance
    guidelines and limits.

-   [Data Management](references/data-management.md): IAM roles, authentication
    (including signed URLs and HMAC), access control, network security,
    automated security assessment, data protection, and pricing and cost
    optimization (lifecycle rules, Autoclass).

-   [Storage Intelligence](references/storage-intelligence.md): The subscription
    for managing storage at scale — Storage Insights datasets (BigQuery metadata
    and activity index), data insights with Gemini Cloud Assist, dashboards,
    inventory reports, storage batch operations, bucket relocation, plus
    configuration, trial, and pricing nuances.

-   [High-Performance Storage](references/high-performance-storage.md): Rapid
    Bucket, Rapid Cache (Anywhere Cache), and hierarchical namespace for AI/ML,
    analytics, and other performance-critical workloads.

-   [GCSFuse](references/gcsfuse.md): Installing Cloud Storage FUSE, mounting
    buckets, file operations, POSIX semantics and limitations (locking, writes,
    renames, consistency), and caching.
