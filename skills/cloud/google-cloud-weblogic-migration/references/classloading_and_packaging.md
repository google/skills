# WebLogic Classloading & Shared Library (`APP-INF/lib`) Modernization Guide

Enterprise WebLogic EAR deployments rely on complex classloader hierarchies
defined in `weblogic-application.xml` (`<prefer-web-inf-classes>`,
`<prefer-application-packages>`), EAR packaging (`APP-INF/lib`,
`APP-INF/classes`), and WebLogic Shared Libraries (`<library-ref>`).

When decomposing an EAR monolith into standalone cloud-native microservices
(Spring Boot Fat JARs or Quarkus Fast-JARs/Containers), classloader filtering
and shared libraries must be restructured into clean, version-managed build
dependencies.

## Table of Contents

*   [1. Restructuring APP-INF/lib and WebLogic Shared Libraries (<library-ref>)](#1-restructuring-app-inf-lib-and-weblogic-shared-libraries-library-ref) (Line 20)
*   [2. Resolving Classloader Conflicts (<prefer-web-inf-classes>)](#2-resolving-classloader-conflicts-prefer-web-inf-classes) (Line 89)

--------------------------------------------------------------------------------

## 1. Restructuring `APP-INF/lib` and WebLogic Shared Libraries (`<library-ref>`)

In WebLogic, JAR files placed in an EAR's `APP-INF/lib` directory or registered
as WebLogic Shared Libraries via `<library-ref>` in `weblogic-application.xml`
are shared across all web modules (`.war`) and EJB modules (`.jar`) in the EAR.

### Before: Legacy WebLogic EAR Structure & `<library-ref>`

```
medimed-ear.ear
├── APP-INF/
│   └── lib/
│       ├── medimed-domain.jar   # Shared DTOs and Entity classes
│       └── medimed-utils.jar    # Shared utility classes
├── META-INF/
│   ├── application.xml
│   └── weblogic-application.xml # Declares <library-ref> to shared-log4j-lib
├── patient-web.war
└── patient-ejb.jar
```

### After: Maven Multi-Module Build with Shared Domain & Utils Modules

In a cloud-native microservice architecture, replace `APP-INF/lib` and
`<library-ref>` by extracting shared domain classes and utility helpers into
standalone **internal Maven modules** or a **Bill of Materials (BOM)**.

#### Modernized Maven Multi-Module Structure

```
medimed-microservices-root/
├── pom.xml                     # Parent POM / BOM declaring dependency management
├── medimed-shared-domain/       # Extracted from APP-INF/lib/medimed-domain.jar
│   ├── pom.xml
│   └── src/main/java/...
├── medimed-shared-utils/        # Extracted from APP-INF/lib/medimed-utils.jar
│   ├── pom.xml
│   └── src/main/java/...
├── patient-service/            # Independent Spring Boot or Quarkus microservice
│   ├── pom.xml                 # Imports medimed-shared-domain and medimed-shared-utils
│   ├── Dockerfile
│   └── src/main/java/...
└── record-service/             # Independent microservice
    ├── pom.xml
    └── src/main/java/...
```

#### Microservice `pom.xml` Dependency Declaration

```xml
<dependencies>
    <!-- Internal Shared Domain Module -->
    <dependency>
        <groupId>com.acme.medimed</groupId>
        <artifactId>medimed-shared-domain</artifactId>
        <version>${project.version}</version>
    </dependency>

    <!-- Internal Shared Utils Module -->
    <dependency>
        <groupId>com.acme.medimed</groupId>
        <artifactId>medimed-shared-utils</artifactId>
        <version>${project.version}</version>
    </dependency>
</dependencies>
```

--------------------------------------------------------------------------------

## 2. Resolving Classloader Conflicts (`<prefer-web-inf-classes>`)

In WebLogic, `<prefer-web-inf-classes>` or `<prefer-application-packages>` in
`weblogic.xml` / `weblogic-application.xml` forces the WebLogic classloader to
load application-bundled JARs (such as older Hibernate versions, custom XML
parsers, or Apache Commons libraries) instead of WebLogic's internal container
libraries.

### Why Classloader Filtering is Unnecessary in Cloud-Native Containers

In Spring Boot Fat JARs and Quarkus Fast-JARs running in Docker containers:

1.  **No Application Server Collision**: There is no overarching application
    server (like WebLogic or WebSphere) injecting conflicting container
    libraries into your classpath. The only libraries present in the JVM are the
    exact libraries declared in your `pom.xml` or `build.gradle`.
2.  **Clean Dependency Shading**: If third-party transitive dependencies collide
    (e.g., two different versions of `guava` or `jackson`), resolve them
    declaratively using Maven `<dependencyManagement>` or `<exclusions>`:

```xml
<dependencyManagement>
    <dependencies>
        <!-- Force explicit version across all microservice dependencies -->
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.1</version>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.legacy.library</groupId>
        <artifactId>old-client-sdk</artifactId>
        <!-- Exclude conflicting transitive libraries -->
        <exclusions>
            <exclusion>
                <groupId>commons-logging</groupId>
                <artifactId>commons-logging</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
</dependencies>
```
