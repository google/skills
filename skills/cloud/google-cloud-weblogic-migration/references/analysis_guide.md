# WebLogic Migration: Analysis & Discovery Guide

This guide helps you perform a thorough analysis of a WebLogic application to
prepare for migration.

## Table of Contents

*   [Scanning Patterns](#scanning-patterns) (Line 20)
    *   [1. WebLogic Specific APIs](#1-weblogic-specific-apis) (Line 25)
    *   [2. EJB (Enterprise JavaBeans)](#2-ejb-enterprise-javabeans) (Line 35)
    *   [3. JMS (Java Message Service)](#3-jms-java-message-service) (Line 53)
    *   [4. JNDI (Java Naming and Directory Interface)](#4-jndi-java-naming-and-directory-interface) (Line 62)
    *   [5. Web/Servlet Tier](#5-webservlet-tier) (Line 70)
    *   [6. Advanced WebLogic / Java EE Features](#6-advanced-weblogic--java-ee-features) (Line 81)
    *   [7. Data Access & Security](#7-data-access--security) (Line 98)
    *   [8. Cloud-Unfriendly Patterns](#8-cloud-unfriendly-patterns) (Line 106)

--------------------------------------------------------------------------------

## Scanning Patterns

Use these patterns (e.g., with grep or code search) to identify WebLogic
dependencies and legacy JEE patterns.

### 1. WebLogic Specific APIs

Look for imports starting with:

*   `import weblogic.` (Generic WebLogic classes)
*   `import weblogic.logging.` (Logging)
*   `import weblogic.security.` (Security/JAAS)
*   `import weblogic.transaction.` (Transaction management)
*   `import weblogic.jdbc.` (Weblogic JDBC extensions)

### 2. EJB (Enterprise JavaBeans)

Look for EJB annotations and usage:

*   `@Stateless`
*   `@Stateful`
*   `@Singleton`
*   `@MessageDriven`
*   `@Local`
*   `@Remote`
*   `@EJB`
*   `import javax.ejb.` or `import jakarta.ejb.`

Also look for EJB configuration files:

*   `ejb-jar.xml`
*   `weblogic-ejb-jar.xml`

### 3. JMS (Java Message Service)

Look for JMS API usage:

*   `import javax.jms.` or `import jakarta.jms.`
*   `QueueConnectionFactory`, `TopicConnectionFactory`
*   `Queue`, `Topic`
*   `MessageListener`

### 4. JNDI (Java Naming and Directory Interface)

Look for JNDI lookups:

*   `new InitialContext()`
*   `Context.lookup(...)`
*   `lookup("java:comp/env/...")`

### 5. Web/Servlet Tier

Look for:

*   `web.xml`
*   `weblogic.xml`
*   `javax.servlet.*` or `jakarta.servlet.*`
*   `.jsp` files
*   `HttpSession` or `request.getSession()` (identifies stateful sessions to be
    migrated)

### 6. Advanced WebLogic / Java EE Features

Look for:

*   **Work Managers**: `work-manager` in XML configs or imports of
    `commonj.work.*`.
*   **Timers**: Usage of `javax.ejb.TimerService` or `commonj.timers.*`.
*   **Batch Processing**: `javax.batch.api` or Spring Batch.
*   **JMX/MBeans**: `javax.management.MBeanServer` or `weblogic.management`.
*   **Resource Adapters**: Files named `ra.xml` or `weblogic-ra.xml` (JCA
    connectors).
*   **Classloading Customizations**: `prefer-application-packages` or
    `prefer-application-resources` in `weblogic.xml` or
    `weblogic-application.xml`.
*   **Web Services**: `weblogic-webservices.xml` or JAX-WS annotations like
    `@WebService`, `@WebMethod`.

### 7. Data Access & Security

Look for:

*   **Data Access**: `java.sql.Connection`, `@Entity`, `org.hibernate.Session`,
    `persistence.xml`.
*   **Security**: `@RolesAllowed`, `@RunAs`, `isUserInRole`.

### 8. Cloud-Unfriendly Patterns

Look for:

*   **File I/O**: `java.io.FileOutputStream`, `java.nio.file.Files`.
*   **Legacy Remoting**: `java.rmi.*`, `UnicastRemoteObject`.
*   **Email**: `javax.mail.*`, `jakarta.mail.*`.
*   **Hardcoded IPs / Absolute Paths**.

--------------------------------------------------------------------------------

When Phase 1 and target alignment are complete, generate a migration plan in the
root of the workspace named `wls-migration-plan.md` using the following
structure:

```markdown
# WebLogic Migration Unified Analysis Report (Migration Plan)

## 1. Executive Summary
[Brief overview of the application size, dependencies count, and microservices target metrics.]

## 2. Build & Environment
[Discovered runtime targets, Java version mappings, Maven modules, Ant configs, and checked-in local JAR files.]

## 3. Technical Inventory
[Quantitative metrics covering EJBs, JMS/JNDI lookup usages, Data Access (JDBC/JPA), Security roles, advanced Work Managers, SOAP web services, and Web tier assets like JSPs and Servlets.]

## 4. Cloud-Unfriendly Patterns & Blockers
[List of discovered blockers requiring user decisions: Local File I/O, HTTP Sessions, Batch Jobs, RMI/CORBA, and JavaMail usage.]

## 5. Shared Utility Evaluation
[Excluded utilities confirmed via heuristics/config, followed by a list of high fan-in coupling candidates recommended for manual review.]

## 6. Web & Presentation Modernization Recommendation
[Custom modernization suggestions addressing server-rendered UI frameworks like Struts/JSPs, servlet routes mapping, and stateless token configuration.]

## 7. Proposed Decomposition (Topological Analysis)
[The Louvain graph partitioning diagram depicted in Mermaid.js, followed by package, class, and database table distributions matching each proposed microservice service boundary.]

## 8. Risks, Warnings, & Architectural Call-Outs
[Critical risks or constraints identified during discovery (e.g. shared state, legacy networking, 3rd party libraries with no source). List any security or vulnerability issues, temporary authentication bypasses, unauthorized access paths, or plaintext credentials configured for compilation that must be resolved before production deployment.]

## 9. Deployment & Infrastructure-as-Code (IaC) Plan
[Dynamically populated during Phase 2 with target Terraform, Kubernetes manifests, or gcloud deployment plans for Cloud Run, Cloud Functions, or GKE.]

## 10. Testing Strategy
[Dynamically populated during Phase 2 with generative unit/integration testing strategies (e.g. @WebMvcTest / @QuarkusTest) and documentation of disabled legacy Cactus tests.]
```
