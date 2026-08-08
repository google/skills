# WebLogic to Cloud-Native Incremental Refactoring Guide

This guide provides detailed procedural instructions for executing Phase 3
(Incremental Refactoring) of the WebLogic migration workflow.

## Table of Contents

*   [1. Initialize Target Workspace & Copy Files](#1-initialize-target-workspace--copy-files) (Line 23)
*   [2. Dependency Validation (CRITICAL)](#2-dependency-validation-critical) (Line 42)
*   [3. Automated Bulk Refactoring (Scope & Limitations)](#3-automated-bulk-refactoring-scope--limitations) (Line 52)
*   [4. Replace JNDI Lookups](#4-replace-jndi-lookups) (Line 88)
*   [5. Refactor EJBs](#5-refactor-ejbs) (Line 93)
*   [6. Refactor Security (Align with Legacy Constraints)](#6-refactor-security-align-with-legacy-constraints) (Line 99)
*   [7. Update APIs & Weblogic-specific Helpers](#7-update-apis--weblogic-specific-helpers) (Line 125)
*   [8. Modernize Web Tier (Presentation Layer)](#8-modernize-web-tier-presentation-layer) (Line 130)
*   [9. Refactor Cloud-Unfriendly Patterns (Deterministic Handling)](#9-refactor-cloud-unfriendly-patterns-deterministic-handling) (Line 144)
*   [10. Port and Refactor Legacy Tests](#10-port-and-refactor-legacy-tests) (Line 160)
*   [11. Track Refactoring Decisions](#11-track-refactoring-decisions) (Line 187)
*   [12. Verify Refactored Code (Compilation & Test Suite Execution)](#12-verify-refactored-code-compilation--test-suite-execution) (Line 195)

--------------------------------------------------------------------------------

## 1. Initialize Target Workspace & Copy Files

*   Create a target folder named `wls_migration` in the root of the workspace
    directory to keep migrated modules isolated:

    ```bash
    mkdir -p wls_migration
    ```

*   Initialize the target microservices structure under `wls_migration/` (e.g.,
    creating subdirectories for each microservice candidate identified in
    `wls-migration-plan.md` Section 7).

*   **Isolate and Copy Source Files**: Copy the Java classes, resources, XML
    configuration files, and web assets mapped to each microservice from the
    original monolith directories into the target source directories inside
    `wls_migration/` (e.g., copy EJB classes mapped to `patient-service` to
    `wls_migration/patient-service/src/main/java/...`).

## 2. Dependency Validation (CRITICAL)

> [!IMPORTANT] **Mandatory Dependency Scanning**: Before any new external
> package, library, or framework (e.g., Spring Boot, Quarkus, JWT libraries, DB
> drivers) is imported or added to the microservices' `pom.xml` or
> `build.gradle`, you MUST invoke the `scan_dependencies` skill to validate its
> safety. The `scan_dependencies` skill is the exclusive authority for package
> validation. Do not generate code with new imports until the tool confirms
> safety and provides the approved versioning.

## 3. Automated Bulk Refactoring (Scope & Limitations)

Run OpenRewrite *inside the target sub-project folders in `wls_migration/`* to
automate boilerplate migrations (like `javax.*` to `jakarta.*` packages, or
upgrading Java version):

```bash
<script_install_folder>/scripts/run_openrewrite.sh wls_migration/[service_name] [recipe_type]
```

*   Use recipe `jakarta` for Java EE to Jakarta EE migration.
*   Use recipe `java17` to upgrade Java syntax to Java 17.
*   Use recipe `spring3` if migrating to Spring Boot 3.x.
*   *Note: If no pom.xml is present (e.g., in Ant projects), the script will
    automatically detect the Java source root, generate a temporary pom.xml for
    OpenRewrite execution, and clean it up afterwards.*

> [!IMPORTANT] **OpenRewrite Core Limitations**: Do NOT rely on OpenRewrite to
> handle weblogic configurations or structural rewrites. The following must be
> performed manually:
>
> 1.  **EJBGen (`.ejb` files)**: WebLogic's javadoc-style EJBGen annotations
>     (like `@ejbgen:entity` or `@ejbgen:relation`) are not supported by
>     standard recipes. Translate these annotations to JPA (`@Entity`, `@Table`)
>     and Spring annotations manually.
> 2.  **EJB 2.x CMP Entity Beans to JPA**: Converting legacy CMP classes
>     extending `GenericEntityBean` into modern POJOs with `@Entity` annotations
>     and Spring Data JPA Repositories is a manual architectural rewrite.
> 3.  **Weblogic Specific APIs**: Usages of weblogic libraries like
>     `weblogic.xml.stream.*` must be manually rewritten to standard Java StAX
>     parsing (`javax.xml.stream.*`). 4. **Microservice Decomposition**:
>     OpenRewrite cannot design microservice boundaries or setup REST/PubSub
>     inter-service communications. Run OpenRewrite only to clean syntax and
>     packages within the already isolated target modules under
>     `wls_migration/`.

## 4. Replace JNDI Lookups

Replace remaining dynamic JNDI lookups with Dependency Injection (DI) using
`@Autowired` (Spring) or `@Inject` (Quarkus/CDI).

## 5. Refactor EJBs

*   Convert Stateless Session Beans to standard Spring Services (`@Service`) or
    Quarkus Beans. See [example_ejb_migration.md](../assets/example_ejb_migration.md) for a concrete before-and-after mapping.
*   Convert Message-Driven Beans (MDBs) to GCP Pub/Sub listeners or Spring JMS listeners. See [example_jms_migration.md](../assets/example_jms_migration.md) for a concrete before-and-after mapping.

## 6. Refactor Security (Align with Legacy Constraints)

Replace WebLogic-specific security (JAAS, WebLogic helper classes, web.xml
constraints) with Spring Security or Quarkus Security.

*   **Align with Monolith Security Maps**: Security constraints (requiring
    authentication/authorization) must only be applied to endpoints and services
    that were secured in the legacy monolith (e.g., routes protected by
    `web.xml` security constraints, EJB roles, or JAAS intercepts). Endpoints
    that were public/open in the legacy monolith **must remain public** in the
    new microservices to avoid breaking client compatibility.
*   **Flag Mock Security**: Mock tokens or plaintext security configurations
    (such as temporary mock token generation endpoints or `NoOpPasswordEncoder`
    for database passwords) are acceptable *for baseline compatibility*, but
    they **must be flagged** as warning items in the final `walkthrough.md`
    report.
*   **Token Sign & Validate**: For secured endpoints, use token-based
    authentication (JWT or OIDC integration). If a custom token service (e.g.,
    custom auth-service) is implemented, it must issue cryptographically signed
    JWTs (e.g., HS256/RS256). All secured downstream services must validate this
    token signature and verify credentials (such as expiration, scopes, and
    signature keys).
*   Refer to
    [example_security_migration.md](../assets/example_security_migration.md) for
    Spring Security configuration steps.

## 7. Update APIs & Weblogic-specific Helpers

Replace WebLogic-specific helper APIs with standard Java or target framework
APIs.

## 8. Modernize Web Tier (Presentation Layer)

*   **Decouple JSPs/JSF**: For server-rendered user interfaces (JSP/JSF),
    isolate the presentation logic and migrate pages to a standalone SPA
    framework (e.g., **React** or **Angular**).
*   **Convert MVC to REST**: Rewrite legacy controller classes (Struts Actions,
    JSF Backing Beans, or HttpServlet subclasses) into stateless REST
    controllers:
    *   Spring: `@RestController` with `@RequestMapping`
    *   Quarkus/CDI: JAX-RS resource classes with `@Path`, `@GET`, `@POST`
*   **Session Management**: Remove dependency on stateful server-side sessions
    (`HttpSession`). Transition to token-based security (JWT) or store session
    state in an external cache (e.g., Redis) based on user decision.

## 9. Refactor Cloud-Unfriendly Patterns (Deterministic Handling)

*   **File I/O**: Replace `java.io` and `java.nio` local file operations with
    the GCP Storage Client Library to read/write from Cloud Storage buckets (or
    map to Filestore/Parallelstore as aligned).
*   **Batch Processing**: Extract `javax.batch` or Spring Batch jobs into
    standalone entry points designed to run as GCP Cloud Run Jobs.
*   **JavaMail**: Replace direct SMTP implementations (`javax.mail`) with REST
    API calls to modern email providers (e.g., SendGrid API) based on user
    preference.
*   **RMI/CORBA**: Replace binary remote communication with standard RESTful
    endpoints (`@RestController` or JAX-RS) and JSON payloads.
*   **JMX/MBeans**: Remove custom MBeans and replace with Micrometer (Spring
    Boot) or SmallRye Metrics (Quarkus) for standard Prometheus/Cloud Monitoring
    exposition.

## 10. Port and Refactor Legacy Tests

Locate all legacy unit, integration, and E2E tests related to the migrated
classes in the monolith.

*   **Copy to Target**: Copy these test source files into the corresponding test
    folders in the target sub-project (e.g.,
    `wls_migration/[service_name]/src/test/java/...`).
*   **Modernize Frameworks**: Refactor legacy JUnit 3/4 syntax to JUnit 5
    (`org.junit.jupiter.api.*`).
*   **Mock Dependencies**: Replace legacy in-memory database setups or local
    mock connectors with Spring Boot test mocks (`@SpringBootTest`, `@MockBean`)
    or Quarkus test mocks (`@QuarkusTest`, `@InjectMock`).
*   **Handle Network Calls**: If legacy integration tests made local invocations
    to classes that are now separated into other microservices, refactor them to
    use HTTP mock servers (e.g., `WireMock` or Spring `MockRestServiceServer`)
    to stub the HTTP communication.
*   **Generative Testing for Net-New Endpoints**: For newly created REST
    controllers or Pub/Sub listeners that replace legacy EJB/Servlet entry
    points, you MUST generatively author new Spring Boot (`@WebMvcTest`) or
    Quarkus tests to validate their behavior.
*   **Disabled Tests Documentation**: If legacy tests cannot be ported or
    replaced (e.g., container-bound Cactus tests that are fundamentally
    incompatible with modern serverless targets), you must disable them (e.g.,
    using `@Disabled` or commenting them out) and carefully document exactly
    which tests were disabled and why in the final `walkthrough.md` report.

## 11. Track Refactoring Decisions

Keep track of any deviations, architectural trade-offs, or custom modifications
made during refactoring (e.g., custom bean registrations or specific package
shifts). Do NOT modify the approved `wls-migration-plan.md` plan. Instead,
document these details for inclusion in the final validation walkthrough report
(`walkthrough.md`) in Phase 6.

## 12. Verify Refactored Code (Compilation & Test Suite Execution)

After migrating each class or module, immediately verify its correctness:

*   **Compile Code**: Run compilation (e.g., `./mvnw compile` or `./gradlew
    compileJava` inside the microservice subdirectory under `wls_migration/`) to
    ensure no compilation issues or syntax regressions.
*   **Run Test Suite**: Run the ported unit and integration tests (e.g., `./mvnw
    test`). Ensure they all pass. If tests are completely missing for a migrated
    service, author a lightweight JUnit test using Mockito to mock
    database/network resources and assert that migrated business functions
    return identical logical results.
