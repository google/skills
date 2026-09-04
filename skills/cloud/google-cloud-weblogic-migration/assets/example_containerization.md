# Example: Containerization for Serverless (Cloud Run)

This example provides Dockerfiles optimized for running Spring Boot and Quarkus
applications on Google Cloud Run.

## 1. Spring Boot Dockerfile (Layered Jar)

Spring Boot 2.3+ supports layered jars. This allows for better caching of
dependencies in Docker layers.

### Maven Configuration (pom.xml)

Ensure layering is enabled in the Spring Boot plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <layers>
                    <enabled>true</enabled>
                </layers>
            </configuration>
        </plugin>
    </plugins>
</build>
```

### Dockerfile

```dockerfile
# Stage 1: Extract layers
FROM eclipse-temurin:21-jre-alpine AS builder
WORKDIR application
ARG JAR_FILE=target/*.jar
COPY ${JAR_FILE} application.jar
RUN java -Djarmode=layertools -jar application.jar extract

# Stage 2: Build the runtime image
FROM eclipse-temurin:21-jre-alpine
WORKDIR application
COPY --from=builder application/dependencies/ ./
COPY --from=builder application/spring-boot-loader/ ./
COPY --from=builder application/internal-dependencies/ ./
COPY --from=builder application/application/ ./

# Cloud Run sets the PORT environment variable.
# We must configure Spring Boot to listen on this port.
ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["java", "org.springframework.boot.loader.JarLauncher"]
```

--------------------------------------------------------------------------------

## 2. Quarkus Dockerfile (JVM Mode)

Optimized for fast startup in JVM mode using fast-jar.

### Dockerfile

```dockerfile
# Stage 1: Build stage (Optional if building locally, but recommended for CI)
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /code
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src src
RUN mvn package -DskipTests

# Stage 2: Runtime stage
FROM eclipse-temurin:21-jre-alpine
WORKDIR /work/
# Copy the fast-jar build outputs
COPY --from=build /code/target/quarkus-app/lib/ /work/lib/
COPY --from=build /code/target/quarkus-app/*.jar /work/
COPY --from=build /code/target/quarkus-app/app/ /work/app/
COPY --from=build /code/target/quarkus-app/quarkus/ /work/quarkus/

ENV PORT=8080
EXPOSE 8080

# Quarkus looks for HTTP port configuration or PORT env var
ENV QUARKUS_HTTP_PORT=8080

CMD ["java", "-jar", "/work/quarkus-run.jar"]
```

--------------------------------------------------------------------------------

## 3. Quarkus Dockerfile (Native Mode)

Provides the fastest startup time (milliseconds) and lowest memory footprint,
ideal for scale-to-zero serverless. Requires GraalVM to build.

### Dockerfile

```dockerfile
# Stage 1: Build the native executable
FROM quay.io/quarkus/ubi-quarkus-mandrel-builder-image:23.0-jdk21 AS build
COPY --chown=quarkus:quarkus mvnw /code/mvnw
COPY --chown=quarkus:quarkus .mvn /code/.mvn
COPY --chown=quarkus:quarkus pom.xml /code/
USER quarkus
WORKDIR /code
RUN ./mvnw dependency:go-offline
COPY src /code/src
# Build native executable (-Pnative)
RUN ./mvnw package -Pnative -DskipTests

# Stage 2: Create the runtime image (using a minimal base image)
FROM registry.access.redhat.com/ubi8/ubi-minimal:8.9
WORKDIR /work/
COPY --from=build /code/target/*-runner /work/application

# Grant execution rights
RUN chmod 775 /work /work/application \
  && chown -R 1001 /work \
  && chmod -R "g+rwX" /work \
  && chown -R 1001:root /work

EXPOSE 8080
USER 1001

ENV PORT=8080
ENV QUARKUS_HTTP_PORT=8080

CMD ["./application", "-Dquarkus.http.host=0.0.0.0"]
```

*(Note: Building native images can be slow and resource-intensive, but pays off
in serverless production).*
