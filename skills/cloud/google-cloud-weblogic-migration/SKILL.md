---
name: google-cloud-weblogic-migration
description: |
  Migrates legacy WebLogic applications to cloud-native serverless microservices on GCP (Spring Boot or Quarkus on Cloud Run or Cloud Functions).
  Use when analyzing, decomposing, or refactoring legacy Java EE/WebLogic monoliths (EJBs, JMS, JNDI, Struts, CMP/BMP entity beans) into modern cloud microservices.
  Don't use for general-purpose Java bug fixing, standard Spring Boot feature development, or non-WebLogic/non-Java EE application migrations.
---

# WebLogic Monolith to Cloud-Native Migration Skill

This skill guides the agent through migrating a legacy WebLogic monolith
application to a modern, cloud-native serverless microservice architecture on
Google Cloud Platform (GCP). It supports migrating to either Spring Boot or
Quarkus, running on GKE, Cloud Run or Cloud Functions.

## Workflow Overview

The migration process is divided into seven phases:

1.  **Environment & Prerequisites Check**: Verify JDK compatibility (LTS JDK 11,
    17, or 21 is required for AST parsing) and resolve environmental blockers.
2.  **Analysis & Discovery**: Analyze the codebase to identify WebLogic-specific
    APIs, EJB, JMS, JNDI, and configs, and discover clusters mathematically to
    propose microservices boundaries.
3.  **Technical Stack Alignment & Decomposition Review**: Align with the user on
    target cloud modernization choices and present the customized architecture
    plan as an interactive UI Artifact or markdown file for review and approval.
4.  **Incremental Refactoring**: Refactor the code to remove WebLogic
    dependencies and implement modern patterns.
5.  **Configuration & Infrastructure Mapping**: Map WebLogic resources
    (datasources, JMS, caching, file storage) to GCP services (Cloud SQL,
    Pub/Sub, Memorystore, Cloud Storage).
6.  **Containerization & Deployment**: Generate Dockerfiles and deployment
    configurations.
7.  **Verification, Audit, & Traceability**: Verify that the migration was
    performed correctly, validate security gates, and establish complete
    endpoint traceability in a walkthrough audit report.

--------------------------------------------------------------------------------

## Phase 0: Environment & Prerequisites Check

Before initiating the codebase analysis, verify that the environment meets the
technical prerequisites to ensure accurate static analysis.

> [!IMPORTANT] You **MUST** run a pre-flight check of the environment: 1. Verify
> that Maven is installed and accessible. 2. The AST parsing engine requires a
> compatible LTS JDK version (JDK 11, 17, or 21). The tools will automatically
> attempt to locate a compatible JDK under `/usr/lib/jvm/` or
> `/usr/local/buildtools/java/` and override `JAVA_HOME` if the default JDK is
> incompatible (e.g. JDK 26+). 3. Verify that Python dependencies are installed
> by executing: `pip install -r scripts/requirements.txt` 4. **Catastrophic
> Failure Halt**: If a compatible JDK is not found, if Maven compilation of the
> `ast_parser` project fails, or if more than 10% of the Java files yield
> `ParseError` during analysis, you **MUST STOP** and align with the user. Do
> **NOT** proceed to Phase 1 with disabled or failing AST parsing. Present the
> error to the user and ask them to resolve the environment issue (e.g.,
> installing a compatible JDK 11/17/21 or fixing Maven settings).

--------------------------------------------------------------------------------

## Phase 1: Analysis & Discovery

Scan the legacy monolith codebase iteratively to understand its structure,
identify migration blockers, and calculate optimal microservice boundaries
mathematically using the Louvain community detection engine.

> [!IMPORTANT] You **MUST** read and follow
> [decomposition_guide.md](./references/decomposition_guide.md) for instructions
> on executing multi-resolution exploration, utilizing generalization knobs,
> filtering "God Glue" shared utilities, and iterating internally until
> achieving a stable mathematical optimum.

--------------------------------------------------------------------------------

## Phase 2: Technical Stack Alignment & Decomposition Review

Align with the user on target cloud modernization choices, then present the
customized architecture plan as an interactive UI Artifact (if supported by the
environment) or a standard markdown file for their review and approval.

> [!IMPORTANT] You **MUST** read and follow
> [migration_plan_guide.md](./references/migration_plan_guide.md) for: 1.
> Conducting dynamic, context-relevant technical stack alignment with the user
> (adding custom questions for unique discovered blockers and omitting
> irrelevant ones). 2. Generating the customized `wls-migration-plan.md`
> artifact once and only once after all discovery and alignment are complete. 3.
> Managing the interactive human feedback and refinement loop (overwriting
> `wls-migration-plan.md` and stopping tool execution upon reviewer comments
> until explicitly approved).

--------------------------------------------------------------------------------

## Phase 3: Incremental Refactoring

Refactor the legacy codebase incrementally, service by service or module by
module, based on the approved migration plan.

> [!IMPORTANT] **Autonomy & Continuity**: Once the user approves Phase 2, you
> MUST proceed autonomously through the entire refactoring phase. Do NOT stop to
> ask for permission between services or files. Continuously refactor all
> services until Phase 3 is fully complete, unless a critical architectural
> ambiguity blocks your progress.

> [!IMPORTANT] **Java Version Policy**: ALWAYS target LTS Java versions (Java
> 17, Java 21, or Java 25). Do NOT use unreleased or experimental versions (e.g.
> Java 26).

> [!IMPORTANT] You **MUST** read and follow
> [refactoring_guide.md](./references/refactoring_guide.md) for detailed
> procedural steps on: * Initializing target workspace modules
> (`wls_migration/`). * Executing automated bulk refactoring via OpenRewrite and
> understanding its strict manual limitations. * Replacing JNDI lookups and
> migrating EJBs (Session beans and MDBs). * Aligning security constraints with
> legacy monolith maps and configuring token validation. * Decoupling
> presentation tiers (JSP/Struts to Angular/React SPAs and REST controllers). *
> Modernizing cloud-unfriendly patterns (File I/O, Batch, JavaMail, RMI, JMX). *
> Porting test suites and verifying compilation and functional equivalence.

> [!TIP] Use the following specialized reference guides for target code
> transformation patterns: *
> [refactoring_spring.md](./references/refactoring_spring.md) *
> [refactoring_quarkus.md](./references/refactoring_quarkus.md) *
> [web_modernization.md](./references/web_modernization.md) *
> [distributed_transactions.md](./references/distributed_transactions.md) *
> [legacy_remoting_and_jca.md](./references/legacy_remoting_and_jca.md) (for T3,
> RMI, CORBA, and JCA `.rar` adapters) *
> [sql_dialect_migration.md](./references/sql_dialect_migration.md) (for
> Oracle/PointBase SQL to ANSI SQL/PostgreSQL/MySQL) *
> [weblogic_specific_apis.md](./references/weblogic_specific_apis.md) (for
> custom security SPIs, JMX MBeans, Work Managers, and XML StAX) *
> [classloading_and_packaging.md](./references/classloading_and_packaging.md)
> (for EAR restructuring, `APP-INF/lib`, and `<library-ref>`) *
> [example_advanced_jms_migration.md](./assets/example_advanced_jms_migration.md)
> (for Unit-of-Order, Selectors, DLQs, and Messaging Bridges) *
> [example_soap_webservices_migration.md](./assets/example_soap_webservices_migration.md)
> (for SOAP, JAX-WS, CXF, and WS-Security) *
> [example_caching_and_clustering.md](./assets/example_caching_and_clustering.md)
> (for SFSBs, Coherence, and HTTP session replication to Redis) *
> [example_scheduling_and_timers.md](./assets/example_scheduling_and_timers.md)
> (for EJB timers, Quartz, and Cloud Scheduler/Jobs) *
> [example_observability_migration.md](./assets/example_observability_migration.md)
> (for structured JSON logging and OpenTelemetry tracing) *
> [example_servlet_filter_migration.md](./assets/example_servlet_filter_migration.md)
> (for filters, listeners, and `web.xml` / `weblogic.xml`) * View code templates
> in the `assets/` directory following the pattern `example_*.md`.

--------------------------------------------------------------------------------

## Phase 4: Configuration & Infrastructure Mapping

Map WebLogic infrastructure resources, descriptors, and services to native GCP
managed services.

> [!IMPORTANT] You **MUST** read and follow
> [gcp_mapping.md](./references/gcp_mapping.md) for detailed configuration steps
> and code snippets for mapping: * WebLogic Datasources to GCP Cloud SQL or
> AlloyDB (including dialect updates and SQL query conversions). * Plaintext
> secrets and credentials to GCP Secret Manager and environment variables. *
> WebLogic JMS Queues and Topics to GCP Pub/Sub Topics and Subscriptions. * File
> storage and caching to Google Cloud Storage (GCS), Filestore, Parallelstore,
> and Cloud Memorystore (Redis).

--------------------------------------------------------------------------------

## Phase 5: Containerization & Deployment

Prepare the refactored microservices for serverless container execution and
automated CI/CD pipelines.

> [!IMPORTANT] You **MUST** read and follow
> [deployment_guide.md](./references/deployment_guide.md) and
> [example_containerization.md](./assets/example_containerization.md) for
> detailed instructions on: * Authoring multi-stage framework-optimized
> Dockerfiles (including Quarkus native builds). * Generating Google Cloud Build
> configurations (`cloudbuild.yaml`). * Authoring Terraform manifests
> (`main.tf`, `variables.tf`) or declarative `gcloud` deployment commands for
> Cloud Run and Cloud Functions. * Documenting operational setup, Secret Manager
> variables, and JWT/security configurations in module READMEs.

--------------------------------------------------------------------------------

## Phase 6: Verification, Audit, & Traceability

Verify that the migration was performed correctly, validate security gates, and
establish complete endpoint traceability.

> [!IMPORTANT] You **MUST** read and follow
> [verification_guide.md](./references/verification_guide.md) for detailed
> instructions on: * Constructing the comprehensive Before/After Endpoint
> Traceability Matrix. * Executing local integration assertions and security
> access verification gates on secured vs. public routes. * Generating the
> mandatory `walkthrough.md` audit report artifact (`RequestFeedback: true` and
> `UserFacing: true`) documenting structural comparisons, refactoring
> deviations, compilation/test suite logs, and security warnings.

