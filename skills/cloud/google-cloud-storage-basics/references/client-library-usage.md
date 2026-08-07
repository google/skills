# Cloud Storage Client Libraries

Google Cloud client libraries are the recommended way to access Cloud Storage
from application code — prefer them over hand-built JSON API calls. They handle
authentication, retries with exponential backoff, and resumable/parallel uploads
automatically.

## Authentication

Application Default Credentials (ADC) is the **recommended** method for
authenticating with Google Cloud client libraries. While ADC should be preferred
for most use cases, other options such as API keys (where supported), service
account keys, or Workload Identity Federation are also supported.

### Application Default Credentials (ADC)

In local development, install the Google Cloud CLI
([install](https://docs.cloud.google.com/sdk/docs/install-sdk)) and set up ADC
once:

```bash
gcloud auth application-default login
```

On Google Cloud compute (Cloud Run, GKE, Compute Engine, etc.), ADC resolves
automatically from the attached service account — no key files needed. Avoid
downloading service account keys; use attached identities or workload identity
federation instead. See
[Set up ADC](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc).

### Other Authentication Methods

Depending on your environment, you can also use other credentials:

-   **API Keys**: Some APIs support authentication using API keys provided by
    external entities, passed to client options.
-   **Service Account Keys**: Directly initializing the client using a
    downloaded JSON key file path (strongly discouraged for security reasons).
-   **External Credential Configurations**: Loading credentials config (e.g.,
    Workload Identity Federation) from external sources.

For details, see
[Authenticate with client libraries](https://docs.cloud.google.com/docs/authentication/client-libraries).

## Python

```bash
pip install --upgrade google-cloud-storage
```

```python
from google.cloud import storage

client = storage.Client()

# Upload a file.
bucket = client.bucket("my-bucket")
blob = bucket.blob("my-file.txt")
blob.upload_from_filename("./my-file.txt")

# Download to memory.
contents = bucket.blob("my-file.txt").download_as_bytes()
```

-   [Python reference](https://docs.cloud.google.com/python/docs/reference/storage/latest)

## Java

Add the `com.google.cloud:google-cloud-storage` dependency to your build. Google
recommends managing the version with the
[Google Cloud libraries BOM](https://github.com/googleapis/java-cloud-bom)
instead of pinning it per-dependency. See
[Cloud Storage client libraries](https://docs.cloud.google.com/storage/docs/reference/libraries)
for the Maven and Gradle configuration.

```java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.file.Paths;

Storage storage = StorageOptions.getDefaultInstance().getService();

// Upload a file.
BlobId blobId = BlobId.of("my-bucket", "my-file.txt");
BlobInfo blobInfo = BlobInfo.newBuilder(blobId).build();
storage.createFrom(blobInfo, Paths.get("./my-file.txt"));

// Download to memory.
byte[] contents = storage.readAllBytes(blobId);
```

-   [Java reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview)

## Node.js

```bash
npm install @google-cloud/storage
```

```javascript
const {Storage} = require('@google-cloud/storage');
const storage = new Storage();

// Upload a file.
await storage.bucket('my-bucket').upload('./my-file.txt');

// Download to a local file.
await storage
  .bucket('my-bucket')
  .file('my-file.txt')
  .download({destination: './my-file.txt'});
```

-   [Node.js reference](https://docs.cloud.google.com/nodejs/docs/reference/storage/latest)

## Go

```bash
go get cloud.google.com/go/storage
```

```go
import (
    "context"
    "io"
    "os"

    "cloud.google.com/go/storage"
)

ctx := context.Background()
client, err := storage.NewClient(ctx)
if err != nil {
    return err
}
defer client.Close()

// Upload a file.
f, err := os.Open("./my-file.txt")
if err != nil {
    return err
}
defer f.Close()
w := client.Bucket("my-bucket").Object("my-file.txt").NewWriter(ctx)
if _, err := io.Copy(w, f); err != nil {
    return err
}
if err := w.Close(); err != nil {
    return err
}

// Download to memory.
r, err := client.Bucket("my-bucket").Object("my-file.txt").NewReader(ctx)
if err != nil {
    return err
}
defer r.Close()
contents, err := io.ReadAll(r)
if err != nil {
    return err
}
```

-   [Go reference](https://docs.cloud.google.com/go/docs/reference/cloud.google.com/go/storage/latest)

## Other Languages

Cloud Storage also has supported client libraries for C++, C#, PHP, and Ruby.
For installation and references, see
[Cloud Storage client libraries](https://docs.cloud.google.com/storage/docs/reference/libraries).
