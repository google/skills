# WebLogic Specific APIs & Container Services Modernization Guide

This guide provides concrete refactoring recipes for modernizing
WebLogic-specific specific container APIs (Custom Security Providers, Work
Managers, Custom JMX MBeans, and XML Streaming APIs) into standard cloud-native
frameworks on GCP.

--------------------------------------------------------------------------------

## Table of Contents

*   [1. Weblogic Specific Security Providers & JAAS Interceptors](#1-weblogic-specific-security-providers--jaas-interceptors-weblogicsecurity)
    (Line 21)
*   [2. WebLogic Work Managers & Raw Threading](#2-weblogic-work-managers--raw-threading-commonjworkworkmanager)
    (Line 88)
*   [3. Custom JMX MBeans](#3-custom-jmx-mbeans-weblogicmanagement-standardmbean)
    (Line 166)
*   [4. WebLogic XML Streaming APIs](#4-weblogic-xml-streaming-apis-weblogicxmlstream)
    (Line 227)

--------------------------------------------------------------------------------

## 1. Weblogic Specific Security Providers & JAAS Interceptors (`weblogic.security.*`)

WebLogic applications frequently implement custom Authentication Providers
(extending `weblogic.security.spi.AuthenticationProvider`), custom Role Mappers
(`weblogic.security.spi.RoleMapper`), or use `weblogic.security.SubjectUtils`
and programmatic `@SecurityRoleRef` annotations.

### Before: Legacy WebLogic Programmatic Subject Check

```java
// Legacy WebLogic SubjectUtils Role Assertion
import weblogic.security.SubjectUtils;
import weblogic.security.service.PrivilegedActions;
import javax.security.auth.Subject;

public class AdminReportService {
    public void generateReport() {
        Subject currentSubject = SubjectUtils.getUserSubject();
        if (!SubjectUtils.isUserInRole(currentSubject, "MedicalAdminRole")) {
            throw new SecurityException("User lacks MedicalAdminRole in WebLogic Security Realm");
        }
        // Proceed with report generation...
    }
}
```

### After: Cloud-Native Declarative Security

In a cloud-native microservice architecture, specific realm checks are replaced
by declarative role-based access control (RBAC) inspecting claims within
cryptographically signed JSON Web Tokens (JWTs) or OAuth2 / OIDC tokens.

#### Spring Boot Security (`@PreAuthorize`)

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AdminReportService {

    // Declarative Spring Security check evaluating JWT role claims
    @PreAuthorize("hasRole('MedicalAdminRole')")
    public void generateReport() {
        // Proceed with report generation...
    }
}
```

#### Quarkus Security (`@RolesAllowed`)

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class AdminReportService {

    @RolesAllowed("MedicalAdminRole")
    public void generateReport() {
        // Proceed with report generation...
    }
}
```

--------------------------------------------------------------------------------

## 2. WebLogic Work Managers & Raw Threading (`commonj.work.WorkManager`)

Legacy Java EE 5/6 prohibited spawning raw threads (`new Thread()`). WebLogic
applications used `commonj.work.WorkManager` or configured WebLogic Work
Managers (looked up via JNDI `java:comp/env/wm/MyWorkManager`) to execute
asynchronous background tasks or parallel processing within container-managed
thread pools.

### Before: Legacy WebLogic WorkManager Execution

```java
import commonj.work.WorkManager;
import commonj.work.Work;
import javax.naming.InitialContext;

public class AsyncBillingDispatcher {
    public void dispatchInvoice(final Long invoiceId) throws Exception {
        InitialContext ctx = new InitialContext();
        WorkManager wm = (WorkManager) ctx.lookup("java:comp/env/wm/BillingWorkManager");

        wm.schedule(new Work() {
            public void run() {
                // Execute background billing calculation
            }
            public boolean isDaemon() { return false; }
            public void release() {}
        });
    }
}
```

### After: Cloud-Native Asynchronous Execution & Virtual Threads

In modern Spring Boot and Quarkus microservices running on Java 21+,
container-managed Work Managers are modernized into declarative asynchronous
tasks backed by lightweight **Java 21 Virtual Threads** (`Project Loom`) or
event-driven Pub/Sub workers.

#### Spring Boot (`@Async` with Virtual Threads)

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncBillingDispatcher {

    // Executes asynchronously on a Java 21 Virtual Thread
    @Async
    public void dispatchInvoice(Long invoiceId) {
        // Execute background billing calculation
    }
}

// In Spring Boot 3.2+ Application Configuration:
// spring.threads.virtual.enabled=true
```

#### Quarkus (`@Asynchronous` / `@RunOnVirtualThread`)

```java
import io.smallrye.common.annotation.RunOnVirtualThread;
import jakarta.enterprise.context.ApplicationScoped;
import java.util.concurrent.CompletableFuture;

@ApplicationScoped
public class AsyncBillingDispatcher {

    @RunOnVirtualThread
    public CompletableFuture<Void> dispatchInvoice(Long invoiceId) {
        // Execute background billing calculation on Java 21 Virtual Thread
        return CompletableFuture.completedFuture(null);
    }
}
```

--------------------------------------------------------------------------------

## 3. Custom JMX MBeans (`weblogic.management.*`, `StandardMBean`)

WebLogic applications frequently register custom MBeans (extending
`StandardMBean` or registering via `MBeanServer` looked up from
`java:comp/env/jmx/runtime`) to expose application performance counters, cache
eviction triggers, and dynamic configuration knobs to the WebLogic Console or
WLST (WebLogic Scripting Tool).

### After: Cloud-Native Metrics & Dynamic Operations

#### Metrics Exposition: Micrometer / SmallRye Metrics

Replace JMX metric counters with standard cloud-native metrics exposed at
`/actuator/prometheus` (Spring) or `/q/metrics` (Quarkus), scraped automatically
by **Google Cloud Managed Service for Prometheus**:

```java
// Spring Boot Micrometer Counter
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Counter;
import org.springframework.stereotype.Component;

@Component
public class PatientMetrics {
    private final Counter registrationCounter;

    public PatientMetrics(MeterRegistry registry) {
        this.registrationCounter = registry.counter("patients.registered.total");
    }

    public void incrementRegistration() {
        registrationCounter.increment();
    }
}
```

#### Dynamic Configuration: Spring Cloud Config / GCP Secret Manager

Replace JMX setter operations and WLST reload scripts with dynamic configuration
reloading via `@RefreshScope` (Spring Boot) or GCP Secret Manager environment
variable re-injection:

```java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class MedicalFeatureToggles {
    @Value("${feature.telemedicine.enabled:false}")
    private boolean telemedicineEnabled;

    public boolean isTelemedicineEnabled() {
        return telemedicineEnabled;
    }
}
```

--------------------------------------------------------------------------------

## 4. WebLogic XML Streaming APIs (`weblogic.xml.stream.*`)

Legacy monoliths often imported WebLogic's bundled XML streaming parsers
directly (`weblogic.xml.stream.XMLInputStream`, `XMLStreamReader`,
`XMLInputFactory`).

### After: Standard JDK StAX (`javax.xml.stream.*`)

WebLogic's specific XML streaming APIs map 1-to-1 with standard JDK StAX
(Streaming API for XML) included in standard Java Runtime Environments:

Legacy WebLogic XML API                  | Standard JDK StAX Equivalent
:--------------------------------------- | :------------------------------------
`weblogic.xml.stream.XMLInputFactory`    | `javax.xml.stream.XMLInputFactory`
`weblogic.xml.stream.XMLStreamReader`    | `javax.xml.stream.XMLStreamReader`
`weblogic.xml.stream.XMLStreamException` | `javax.xml.stream.XMLStreamException`
`weblogic.xml.stream.events.XMLEvent`    | `javax.xml.stream.events.XMLEvent`

```java
// Standard JDK StAX Replacement
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamReader;
import java.io.InputStream;

public class XmlParserService {
    public void parseMedicalRecord(InputStream in) throws Exception {
        XMLInputFactory factory = XMLInputFactory.newInstance();
        XMLStreamReader reader = factory.createXMLStreamReader(in);
        while (reader.hasNext()) {
            int event = reader.next();
            // Process StAX events...
        }
        reader.close();
    }
}
```
