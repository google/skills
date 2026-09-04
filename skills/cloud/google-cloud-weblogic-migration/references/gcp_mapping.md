# WebLogic to GCP Resource Mapping Guide

This guide describes how to map WebLogic infrastructure resources (Datasources,
JMS) to Google Cloud Platform (GCP) services.

## Table of Contents

*   [1. Database: WebLogic Datasource to Cloud SQL](#1-database-weblogic-datasource-to-cloud-sql)
    (Line 21)
*   [2. Messaging: WebLogic JMS to GCP Pub/Sub](#2-messaging-weblogic-jms-to-gcp-pubsub)
    (Line 81)
*   [3. Secrets & Credentials: WebLogic Security Realms to GCP Secret Manager](#3-secrets--credentials-weblogic-security-realms-to-gcp-secret-manager)
    (Line 214)
*   [4. File Storage: Local File I/O to Google Cloud Storage (GCS) or Filestore](#4-file-storage-local-file-io-to-google-cloud-storage-gcs-or-filestore)
    (Line 267)
*   [5. Caching & Session State: WebLogic Sessions & Coherence to Cloud Memorystore (Redis)](#5-caching--session-state-weblogic-sessions--coherence-to-cloud-memorystore-redis)
    (Line 318)

--------------------------------------------------------------------------------

## 1. Database: WebLogic Datasource to Cloud SQL

WebLogic applications typically use JNDI to look up a `DataSource` configured in
the WebLogic console. In a serverless environment, database connection details
are provided via environment variables or configuration files, and connections
are managed by the application framework.

### Recommended Target: GCP Cloud SQL

Use Cloud SQL (PostgreSQL, MySQL, or SQL Server) and connect using the **Cloud
SQL JDBC Socket Factory** for secure, IAM-authorized connections without needing
public IPs.

### Spring Boot Configuration

Add dependency:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-sql-postgresql</artifactId>
</dependency>
```

Configure `application.properties`:

```properties
# Using Spring Cloud GCP starter which automatically configures the datasource
spring.cloud.gcp.sql.database-name=mydb
spring.cloud.gcp.sql.instance-connection-name=my-project:us-central1:my-instance
# If using IAM database authentication:
spring.datasource.username=iam-user@my-project.iam.gserviceaccount.com
# Password is not required when using IAM auth with the socket factory (it uses token)
```

### Quarkus Configuration

Add dependency:

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-jdbc-postgresql</artifactId>
</dependency>
<!-- Add Google Cloud SQL socket factory dependency manually as there is no official Quarkus extension for it yet, or use standard JDBC with Cloud SQL proxy sidecar -->
```

If using Cloud SQL Auth Proxy as a sidecar (common pattern for Cloud Run):
Configure `application.properties`:

```properties
quarkus.datasource.db-kind=postgresql
quarkus.datasource.username=dbuser
quarkus.datasource.password=dbpass
# Connect to localhost where the proxy is running
quarkus.datasource.jdbc.url=jdbc:postgresql://127.0.0.1:5432/mydb
```

--------------------------------------------------------------------------------

## 2. Messaging: WebLogic JMS to GCP Pub/Sub

WebLogic JMS (Java Message Service) queues and topics should be migrated to
**Google Cloud Pub/Sub** (or Apache Kafka on GCP if order preservation and
replayability are critical, but Pub/Sub is preferred for serverless simplicity).

### Mapping Concept

*   **WebLogic JMS Queue/Topic** -> **GCP Pub/Sub Topic**
*   **WebLogic JMS Consumer (or EJB MDB)** -> **GCP Pub/Sub Subscription** +
    **Subscriber Code**

### Spring Boot Refactoring (using Spring Cloud GCP Pub/Sub)

Add dependency:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
```

#### Refactoring a Message-Driven Bean (MDB)

**Legacy EJB MDB:**

```java
import javax.ejb.MessageDriven;
import javax.jms.Message;
import javax.jms.MessageListener;
import javax.jms.TextMessage;

@MessageDriven(name = "OrderProcessorMDB")
public class OrderProcessorMDB implements MessageListener {
    public void onMessage(Message message) {
        try {
            if (message instanceof TextMessage) {
                String body = ((TextMessage) message).getText();
                // Process order
            }
        } catch (Exception e) {
            // handle error
        }
    }
}
```

**Spring Boot Pub/Sub Subscriber:**

```java
import com.google.cloud.pubsub.v1.AckReplyConsumer;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProcessorSubscriber {

    @Autowired
    private PubSubTemplate pubSubTemplate;

    @EventListener(ApplicationReadyEvent.class)
    public void subscribe() {
        pubSubTemplate.subscribe("order-subscription", (BasicAcknowledgeablePubsubMessage message) -> {
            String payload = message.getPubsubMessage().getData().toStringUtf8();
            try {
                // Process order payload
                message.ack();
            } catch (Exception e) {
                message.nack();
            }
        });
    }
}
```

### Quarkus Refactoring (using Google Cloud Pub/Sub Client)

Add dependency:

```xml
<dependency>
    <groupId>io.quarkiverse.googlecloudservices</groupId>
    <artifactId>quarkus-google-cloud-pubsub</artifactId>
</dependency>
```

**Quarkus Pub/Sub Subscriber:**

```java
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import org.eclipse.microprofile.config.inject.ConfigProperty;

@ApplicationScoped
public class OrderProcessorSubscriber {

    @ConfigProperty(name = "gcp.project.id")
    String projectId;

    void onStart(@Observes StartupEvent ev) {
        ProjectSubscriptionName subscriptionName = ProjectSubscriptionName.of(projectId, "order-subscription");

        MessageReceiver receiver = (PubsubMessage message, com.google.cloud.pubsub.v1.AckReplyConsumer consumer) -> {
            String payload = message.getData().toStringUtf8();
            try {
                // Process order
                consumer.ack();
            } catch (Exception e) {
                consumer.nack();
            }
        };

        Subscriber subscriber = Subscriber.newBuilder(subscriptionName, receiver).build();
        subscriber.startAsync().awaitRunning();
    }
}
```

*(Note: Quarkus can also use SmallRye Reactive Messaging with a Pub/Sub
connector, which provides a more declarative model, similar to MDBs).*

--------------------------------------------------------------------------------

## 3. Secrets & Credentials: WebLogic Security Realms to GCP Secret Manager

Legacy WebLogic applications often store database passwords, third-party API
keys, and security realm credentials in plaintext properties files or domain
descriptors (`config.xml`). In a cloud-native serverless environment, hardcoded
secrets must be externalized to **Google Cloud Secret Manager**.

### Recommended Target: GCP Secret Manager

Store sensitive configuration values in Secret Manager and inject them at
runtime as environment variables in Cloud Run / Cloud Functions, or fetch them
programmatically using Spring/Quarkus Secret Manager extensions.

### Spring Boot Configuration

Add dependency:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
</dependency>
```

Configure `application.properties`:

```properties
# Reference Secret Manager secrets directly in Spring properties using sm:// syntax
spring.datasource.password=${sm://projects/my-project/secrets/db-password/versions/latest}
api.external.key=${sm://my-api-key}
```

### Quarkus Configuration

Add dependency:

```xml
<dependency>
    <groupId>io.quarkiverse.googlecloudservices</groupId>
    <artifactId>quarkus-google-cloud-secret-manager</artifactId>
</dependency>
```

Configure `application.properties`:

```properties
# Reference Secret Manager secrets using gcp-secret-manager: prefix
quarkus.datasource.password=${gcp-secret-manager:db-password}
api.external.key=${gcp-secret-manager:projects/my-project/secrets/api-key/versions/latest}
```

--------------------------------------------------------------------------------

## 4. File Storage: Local File I/O to Google Cloud Storage (GCS) or Filestore

WebLogic applications frequently write uploaded documents, generated reports, or
temporary files directly to the local filesystem (`java.io.File` or
`java.nio.file.Files`). Because serverless containers (Cloud Run / Cloud
Functions) have ephemeral, stateless local filesystems, local file I/O must be
refactored.

### Recommended Targets:

*   **Google Cloud Storage (GCS)**: Recommended for object storage (user
    uploads, images, PDFs, reports).
*   **Google Cloud Filestore (Managed NFS)**: Recommended if legacy code
    requires POSIX-compliant shared file locking or directory hierarchies
    without refactoring.
*   **Google Cloud Parallelstore**: Recommended for high-throughput scratch
    space in analytics/computing workloads.

### Refactoring to Google Cloud Storage (Spring Boot & Quarkus)

**Legacy File I/O Snippet:**

```java
File targetDir = new File("/var/app/uploads/");
FileOutputStream fos = new FileOutputStream(new File(targetDir, fileName));
fos.write(fileBytes);
fos.close();
```

**Modernized GCS Client Snippet (Java 17+ / 21+):**

```java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class CloudStorageService {
    private final Storage storage = StorageOptions.getDefaultInstance().getService();
    private final String bucketName = System.getenv().getOrDefault("GCS_BUCKET_NAME", "my-app-uploads");

    public void uploadFile(String fileName, byte[] fileBytes) {
        BlobId blobId = BlobId.of(bucketName, fileName);
        BlobInfo blobInfo = BlobInfo.newBuilder(blobId).setContentType("application/octet-stream").build();
        storage.create(blobInfo, fileBytes);
    }
}
```

--------------------------------------------------------------------------------

## 5. Caching & Session State: WebLogic Sessions & Coherence to Cloud Memorystore (Redis)

Monolithic WebLogic applications often rely on in-memory HTTP session
replication across cluster nodes or Oracle Coherence distributed caches. In
serverless cloud architectures, instances scale to zero and are completely
stateless.

### Recommended Target: Google Cloud Memorystore for Redis

Externalize HTTP session state and distributed application caching to **Cloud
Memorystore (Redis)**.

### Spring Boot Configuration (Spring Session Data Redis)

Add dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
```

Configure `application.properties`:

```properties
# Enable Spring Session backed by Redis
spring.session.store-type=redis
spring.data.redis.host=10.0.0.5
spring.data.redis.port=6379
```

### Quarkus Configuration (Quarkus Redis Cache)

Add dependency:

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-redis-client</artifactId>
</dependency>
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-cache</artifactId>
</dependency>
```

Configure `application.properties`:

```properties
# Configure Redis connection for Quarkus caching
quarkus.redis.hosts=redis://10.0.0.5:6379
quarkus.cache.type=redis
```
