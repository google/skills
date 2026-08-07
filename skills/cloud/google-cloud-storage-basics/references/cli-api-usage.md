# Cloud Storage CLI & API Usage

If Cloud Storage MCP tools are not available in your environment, prefer the
`gcloud storage` CLI as the default path for storage operations: it handles
authentication, pagination, and optimized uploads automatically. Use the JSON
API directly only when the CLI is not available — for example, in a constrained
runtime, from a language without a client library, or when you need raw HTTP
control. For programmatic access from application code, prefer a
[client library](client-library-usage.md) over hand-built API calls. Each
operation below shows the CLI command and its JSON API equivalent; note that
some CLI conveniences (such as `cat`, recursive deletes, and automatic resumable
uploads) have no single API call.

Do not use the legacy `gsutil` CLI: it is minimally maintained and does not
support newer features such as soft delete and managed folders. If existing
scripts or documentation show a `gsutil` command, use the equivalent `gcloud
storage` command instead.

The JSON API base endpoint is `https://storage.googleapis.com/storage/v1/`;
authenticate requests with an OAuth 2.0 bearer token (for example, `gcloud auth
print-access-token`). Object names in API URLs must be URL-encoded
(`logs/app.txt` becomes `logs%2Fapp.txt`). The API calls shown below are JSON
API equivalents, not necessarily the requests the CLI itself sends — the CLI
uses other API versions and transports (such as the storage v2 endpoint) for
some commands.

In the API examples, values such as `PROJECT_ID` must be passed explicitly. The
CLI instead fills in any value you do not specify from your active
[gcloud configuration properties](https://docs.cloud.google.com/sdk/docs/properties)
— for example, the project comes from the `core/project` property — and flags
such as `--project` override a property for a single command.

## Bucket Operations

-   **Create a bucket:**

    ```bash
    gcloud storage buckets create gs://my-bucket --location=us-central1
    ```

    ```
    POST /storage/v1/b?project=PROJECT_ID
    Body: {"name": "my-bucket", "location": "US-CENTRAL1"}
    ```

-   **List buckets in a project:**

    ```bash
    gcloud storage ls
    ```

    ```
    GET /storage/v1/b?project=PROJECT_ID
    ```

-   **Describe a bucket (metadata):**

    ```bash
    gcloud storage buckets describe gs://my-bucket
    ```

    ```
    GET /storage/v1/b/my-bucket
    ```

-   **Update a bucket (e.g., labels, default storage class):**

    ```bash
    gcloud storage buckets update gs://my-bucket \
        --update-labels=env=prod --default-storage-class=nearline
    ```

    ```
    PATCH /storage/v1/b/my-bucket
    Body: {"labels": {"env": "prod"}, "storageClass": "NEARLINE"}
    ```

-   **Delete a bucket:**

    > [!CAUTION]
    >
    > **CRITICAL: You MUST stop and ask the user for explicit permission before
    > deleting a bucket or recursively deleting all of its contents.**

    ```bash
    gcloud storage buckets delete gs://my-bucket
    ```

    ```
    DELETE /storage/v1/b/my-bucket
    ```

    The bucket must be empty. To delete a bucket together with all of its
    contents (including noncurrent object versions):

    ```bash
    gcloud storage rm --recursive gs://my-bucket
    ```

## Object Operations

-   **Upload an object:**

    ```bash
    gcloud storage cp ./my-file.txt gs://my-bucket/
    ```

    ```
    POST /upload/storage/v1/b/my-bucket/o?uploadType=media&name=my-file.txt
    Body: (object bytes; set Content-Type header)
    ```

    The CLI automatically uses resumable and parallelized uploads for large
    files. `uploadType=media` is only for small uploads; when calling the API
    directly with larger files, use a resumable upload instead (see
    [Data Transfer](data-transfer.md)).

-   **List objects (optionally by prefix):**

    ```bash
    gcloud storage ls gs://my-bucket/logs/      # one level
    gcloud storage ls gs://my-bucket/**         # all objects, recursively
    ```

    ```
    GET /storage/v1/b/my-bucket/o?prefix=logs/&delimiter=/
    ```

    API list responses are paginated (up to 1,000 items per page); follow
    `nextPageToken` to fetch the remaining pages. The CLI paginates
    automatically.

-   **Download an object:**

    ```bash
    gcloud storage cp gs://my-bucket/my-file.txt .
    ```

    ```
    GET /storage/v1/b/my-bucket/o/my-file.txt?alt=media
    ```

-   **Print object contents to stdout (no temporary file needed):**

    ```bash
    gcloud storage cat gs://my-bucket/my-file.txt
    ```

-   **Read object metadata:**

    ```bash
    gcloud storage objects describe gs://my-bucket/my-file.txt
    ```

    ```
    GET /storage/v1/b/my-bucket/o/my-file.txt
    ```

-   **Update object metadata:**

    ```bash
    gcloud storage objects update gs://my-bucket/my-file.txt \
        --custom-metadata=team=storage
    ```

    ```
    PATCH /storage/v1/b/my-bucket/o/my-file.txt
    Body: {"metadata": {"team": "storage"}}
    ```

-   **Copy or move an object:**

    ```bash
    gcloud storage cp gs://my-bucket/a.txt gs://other-bucket/a.txt
    gcloud storage mv gs://my-bucket/a.txt gs://my-bucket/archive/a.txt
    ```

    ```
    POST /storage/v1/b/my-bucket/o/a.txt/rewriteTo/b/other-bucket/o/a.txt
    ```

-   **Delete an object (or a whole prefix with `--recursive`):**

    ```bash
    gcloud storage rm gs://my-bucket/my-file.txt
    gcloud storage rm --recursive gs://my-bucket/logs/
    ```

    ```
    DELETE /storage/v1/b/my-bucket/o/my-file.txt
    ```

To synchronize a local directory with a bucket (or bucket with bucket), use
`gcloud storage rsync` instead of copying objects individually (see
[Data Transfer](data-transfer.md)).

## Pub/Sub Notifications (Event-Driven Processing)

To trigger downstream processing when objects change, configure bucket
notifications to a Pub/Sub topic instead of polling:

```bash
gcloud storage buckets notifications create gs://my-bucket \
    --topic=my-topic --event-types=OBJECT_FINALIZE,OBJECT_DELETE
```

Event types: `OBJECT_FINALIZE` (upload completed), `OBJECT_DELETE`,
`OBJECT_ARCHIVE`, and `OBJECT_METADATA_UPDATE`. To run code in response, use an
Eventarc trigger targeting Cloud Run or Cloud Run functions with the
`google.cloud.storage.object.v1.finalized` event.

## Other Command Groups

Beyond the core operations above, `gcloud storage` has command groups for more
specialized features:

-   `batch-operations`: run bulk actions (such as deleting objects or updating
    metadata) across very large numbers of objects.
-   `buckets anywhere-caches`: manage Anywhere Cache instances (see
    [High-Performance Storage](high-performance-storage.md)).
-   `folders` and `managed-folders`: manage hierarchical namespace folders and
    folder-level access control (see [Data Management](data-management.md)).
-   `hmac`: manage HMAC keys for the S3-interoperable XML API.
-   `insights`: manage inventory reports and datasets.
-   `intelligence-configs`: manage Storage Intelligence configurations.

Run `gcloud storage --help` (or `gcloud storage GROUP --help`) for the full,
current list of groups and commands.

## Useful Global Flags

-   `--format=json`: Returns machine-parseable output; prefer it over parsing
    the default human-readable output. `--format="value(FIELD)"` extracts a
    single field (e.g., `--format="value(location)"`).
-   `--project`: Overrides the default project (the `core/project` property) for
    the command.
-   `--recursive` / `-r`: Applies `cp`, `rm`, and `ls` to whole prefixes.

## Documentation

-   [gcloud storage reference](https://docs.cloud.google.com/sdk/gcloud/reference/storage)
-   [JSON API reference](https://docs.cloud.google.com/storage/docs/json_api)
-   [XML API (S3-interoperable)](https://docs.cloud.google.com/storage/docs/xml-api/overview)
-   [Pub/Sub notifications for Cloud Storage](https://docs.cloud.google.com/storage/docs/pubsub-notifications)
