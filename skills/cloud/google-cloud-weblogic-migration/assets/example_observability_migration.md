# WebLogic Diagnostics (WLDF), Structured Logging, & Traceability Modernization Guide

Legacy WebLogic applications use **WLDF (WebLogic Diagnostics Framework)**
watches/notifications, `weblogic.logging.NonCatalogLogger`, `weblogic.i18n.*`,
or raw `log4j` / `java.util.logging` writing to local filesystem log files
(`AdminServer.log`, `access.log`).

In Google Cloud Run and Google Kubernetes Engine (GKE), container logs are
captured from `stdout` / `stderr`. This guide explains how to modernize logging
into structured JSON for **Google Cloud Logging** and implement distributed
tracing for **Google Cloud Trace**.

--------------------------------------------------------------------------------

## 1. Structured JSON Logging for Google Cloud Logging

When microservices output standard unstructured text logs, Cloud Logging treats
the entire log line as a text payload, making filtering by severity, timestamp,
or exception trace difficult. By switching to **Structured JSON Logging**,
Google Cloud Logging automatically parses severity levels, timestamps, thread
IDs, and custom MDC attributes.

### Spring Boot with Logback JSON (`logback-spring.xml`)

Add the Logback JSON encoder dependency:

```xml
<!-- pom.xml -->
<dependency>
    <groupId>net.logstash.logback</groupId>
    <artifactId>logstash-logback-encoder</artifactId>
    <version>7.4</version>
</dependency>
```

Create `src/main/resources/logback-spring.xml` configured for Google Cloud
Logging JSON structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE_JSON" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <!-- Map standard SLF4J severity levels to Google Cloud Logging severity names -->
            <fieldNames>
                <level>severity</level>
                <timestamp>time</timestamp>
                <message>message</message>
                <logger>logger</logger>
                <thread>thread</thread>
            </fieldNames>
            <includeMdcKeyName>trace_id</includeMdcKeyName>
            <includeMdcKeyName>span_id</includeMdcKeyName>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE_JSON" />
    </root>
</configuration>
```

### Quarkus Logging JSON (`application.properties`)

In Quarkus, add the `quarkus-logging-json` extension:

```xml
<!-- pom.xml -->
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-logging-json</artifactId>
</dependency>
```

```properties
# application.properties
quarkus.log.console.json=true
quarkus.log.console.json.record-separator=\n
quarkus.log.console.json.date-format=iso-8601
# Map Quarkus log fields to GCP Cloud Logging schema
quarkus.log.console.json.field-level=severity
quarkus.log.console.json.field-message=message
```

--------------------------------------------------------------------------------

## 2. Distributed Tracing with OpenTelemetry & Google Cloud Trace

When a WebLogic monolith is decomposed into multiple microservices (e.g.,
`patient-service` calling `record-service` via REST and publishing to
`audit-topic` via Pub/Sub), tracing a single user transaction across network
hops requires **Distributed Tracing**.

### Spring Boot with Micrometer Tracing & GCP Trace

Add Spring Cloud GCP Trace starters:

```xml
<!-- pom.xml -->
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-trace</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
```

```properties
# application.properties
spring.cloud.gcp.trace.enabled=true
spring.cloud.gcp.trace.sampling.probability=1.0 # Sample 100% in Dev/Test, reduce in Prod
```

### Quarkus with OpenTelemetry (`quarkus-opentelemetry`)

In Quarkus, add the OpenTelemetry extension and configure the GCP OTLP exporter
sidecar or direct OTLP endpoint:

```xml
<!-- pom.xml -->
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-opentelemetry</artifactId>
</dependency>
```

```properties
# application.properties
quarkus.otel.enabled=true
quarkus.otel.exporter.otlp.traces.endpoint=http://localhost:4317 # Cloud Trace OTLP collector
quarkus.otel.traces.sampler=always_on
```

### Automatic W3C Trace Context Propagation

Both Spring Cloud GCP and Quarkus OpenTelemetry automatically inject and extract
standard W3C `traceparent` headers across HTTP requests and Google Cloud Pub/Sub
message attributes:

```http
GET /api/v1/records/1042 HTTP/1.1
Host: record-service.run.app
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

This enables Google Cloud Trace to render end-to-end latency waterfall diagrams
across your entire migrated microservices landscape.
