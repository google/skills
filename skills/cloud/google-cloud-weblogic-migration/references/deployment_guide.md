# WebLogic to Cloud-Native Containerization & Deployment Guide

This guide provides detailed procedural instructions for executing Phase 5
(Containerization & Deployment) of the WebLogic migration workflow.

## 1. Generate Dockerfile

Create a multi-stage `Dockerfile` optimized for the target framework (including
native compilation instructions for Quarkus if requested).

*   Use multi-stage builds to separate the Maven/Gradle compilation artifact
    from the lightweight production runtime image.
*   Ensure proper JVM memory flags and non-root container user execution.

## 2. Generate Build Config

Create `cloudbuild.yaml` for GCP Cloud Build to automate continuous integration
and image tagging.

## 3. Generate Deployment Manifests (Generative IaC)

Once containerization is complete, you must generatively author the
Infrastructure-as-Code (IaC) scripts to deploy the microservices based on the
approved architecture in `wls-migration-plan.md`.

*   **Serverless Targets (Cloud Run / Cloud Functions)**: Generate comprehensive
    Terraform configs (`main.tf`, `variables.tf`, `outputs.tf`) or declarative
    `gcloud` deployment scripts that wire up the new serverless containers,
    configuring CPU/memory limits, concurrency, and VPC connectors.
*   **Kubernetes Targets (Google Kubernetes Engine - GKE)**: If GKE was selected
    during Phase 2 alignment, generate standard Kubernetes manifests
    (`deployment.yaml`, `service.yaml`, `hpa.yaml`, `configmap.yaml`,
    `secret-provider-class.yaml`) or Terraform GKE module configs to provision
    cluster resources and workload identity bindings.
*   **Supporting GCP Infrastructure**: Ensure the Terraform scripts provision
    necessary supporting infrastructure mapped in Phase 4 (e.g., Cloud SQL /
    AlloyDB instances, Pub/Sub topics/subscriptions, Secret Manager secrets,
    Cloud Memorystore Redis clusters, Cloud Storage buckets).

## 4. Document Cloud-Native Setup

Create a new `README.md` file inside the root `wls_migration/` folder and inside
each microservice module's subdirectory. This document serves as the operational
guide for the new cloud-native application, detailing:

*   The microservices module layout and local execution scripts (e.g.,
    Maven/Gradle wrappers).
*   Environment variables required (including GCP Secret Manager references for
    database credentials and API keys).
*   **Security Documentation**: Detail the authentication and authorization
    setup, including JWT cryptographic signature details (e.g., HS256/RS256,
    public/private keys configurations), OIDC JWKS cert endpoints (where
    applicable), or explicitly flag if any temporary mock security is currently
    active.
*   Instructions on how to trigger deployments using the generated Cloud Build
    or Terraform configs.
