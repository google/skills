# Client Library Usage

Instructions on how to install the Google Cloud SDK can be found at
[Install the Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).

## Client Libraries

Google Cloud client libraries provide an idiomatic way to interact with Spanner
from your preferred programming language.

### Python

-   **Installation:**

    ```bash
    pip install google-cloud-spanner
    ```

-   **Usage Example:**

    ```python
    from google.cloud import spanner

    spanner_client = spanner.Client()
    instance = spanner_client.instance("my-instance-id")
    database = instance.database("my-database-id")
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql("SELECT 1")
        for row in results:
            print(row)
    ```

-   [Python Reference](https://docs.cloud.google.com/python/docs/reference/spanner/latest.md.txt)

### Java

-   **Maven Dependency:**

    ```xml
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-spanner</artifactId>
    </dependency>
    ```

-   **Usage Example:**

    ```java
    SpannerOptions options = SpannerOptions.newBuilder().build();
    Spanner spanner = options.getService();
    DatabaseClient dbClient = spanner.getDatabaseClient(DatabaseId.of(options.getProjectId(), "my-instance-id", "my-database-id"));
    ResultSet resultSet = dbClient.singleUse().executeQuery(Statement.of("SELECT 1"));
    while (resultSet.next()) {
        System.out.println(resultSet.getLong(0));
    }
    ```

-   [Java Reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-spanner/latest/overview.md.txt)

### Node.js

-   **Installation:**

    ```bash
    npm install @google-cloud/spanner
    ```

-   **Usage Example:**

    ```javascript
    const {Spanner} = require("@google-cloud/spanner");

    const spanner = new Spanner({projectId: "my-project-id"});
    const instance = spanner.instance("my-instance-id");
    const database = instance.database("my-database-id");
    const [rows] = await database.run({sql: "SELECT 1"});
    ```

-   [Node.js Reference](https://docs.cloud.google.com/nodejs/docs/reference/spanner/latest)

### Go

-   **Installation:**

    ```bash
    go get cloud.google.com/go/spanner
    ```

-   **Usage Example:**

    ```go
    ctx := context.Background()
    client, err := spanner.NewClient(ctx, "projects/my-project-id/instances/my-instance-id/databases/my-database-id")
    if err != nil {
        log.Fatalf("Failed to create client: %v", err)
    }
    defer client.Close()
    iter := client.Single().Query(ctx, spanner.Statement{SQL: "SELECT 1"})
    defer iter.Stop()
    ```

-   [Go Reference](https://docs.cloud.google.com/go/docs/reference/cloud.google.com/go/spanner/latest.md.txt)

## Additional Libraries

### LangChain Integration

Spanner integrates with LangChain to help you build LLM-powered applications.

-   **Vector Store**: Use `SpannerVectorStore` to store and search vector
    embeddings.
-   **Document Loader**: Use `SpannerLoader` to load data from Spanner.
-   **Chat Message History**: Use `SpannerChatMessageHistory` to store
    conversation history.

For more information, see the
[Spanner guide for LangChain](https://docs.cloud.google.com/spanner/docs/langchain.md.txt).

### Spring Data Spanner

For Java applications using the Spring Framework, the Spring Data Spanner module
provides a familiar Spring Data interface.

For more information, see
[Add Spring Data Spanner to your application](https://docs.cloud.google.com/spanner/docs/adding-spring.md.txt).
