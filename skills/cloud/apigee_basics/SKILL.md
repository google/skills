---
name: apigee-basics
description: >-
  Manages API proxies, products, developers, and apps on Apigee X/Hybrid.
  Don't use for other Google Cloud networking gateways, Apigee Edge legacy, or direct Spanner database connections.
---

# Apigee Basics

Apigee is a full-lifecycle API management platform that enables API developers
and administrators to design, secure, deploy, monitor, and scale APIs. It acts
as an L7 gateway, mediating requests between client applications and backend
services. Apigee is available in two main variants: **Apigee X** (fully-managed
cloud service on Google Cloud) and **Apigee Hybrid** (hybrid cloud deployment
with the runtime hosted in a customer-managed Kubernetes cluster).

This skill covers the core fundamentals of Apigee, including:

*   **Core Concepts**: Organizations, environments, proxies, products,
    developers, and apps.
*   **Management Interfaces**: Using the `gcloud` CLI, Helm (for Hybrid), and
    the REST API.
*   **Development**: API proxy bundle structure and programmatic client
    libraries.
*   **Automation & Security**: Infrastructure as Code (Terraform), IAM roles,
    and security policies (API Key, Spike Arrest, OAuth).
*   **AI Integration**: Exposing APIs as Model Context Protocol (MCP) tools.

## Quick Start

This quick start demonstrates how to import and deploy a basic hello-world API
proxy using the One Platform REST API. For other management methods, see
[CLI (gcloud/Helm) Usage](references/cli-usage.md) or
[Infrastructure as Code (Terraform)](references/iac-usage.md).

To deploy using the REST API:

**1. Authenticate and Set Environment Variables**

Set up your GCP project credentials and target environment:

```bash
export PROJECT_ID="your-gcp-project"
export ENV_NAME="your-apigee-environment"
export TOKEN=$(gcloud auth print-access-token)
```

**2. Import a Hello-World Proxy Bundle**

Upload a packaged proxy zip bundle to create a new proxy revision. (Assume you
have a `helloworld.zip` bundle representing a standard proxy config; see
[API Proxy Bundle Structure](references/proxy-bundle-structure.md) for the
required directory layout).

```bash
curl -X POST "https://apigee.googleapis.com/v1/organizations/${PROJECT_ID}/apis?action=import&name=helloworld" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @helloworld.zip
```

**3. Deploy the Proxy Revision**

Deploy revision 1 of the `helloworld` proxy to your designated environment:

```bash
curl -X POST "https://apigee.googleapis.com/v1/organizations/${PROJECT_ID}/environments/${ENV_NAME}/apis/helloworld/revisions/1/deployments" \
  -H "Authorization: Bearer ${TOKEN}"
```

## Reference Directory

Load the relevant reference based on trigger keywords. Prefer the most specific
match; if ambiguous, ask the user to clarify.

Task / Guide                              | Trigger Keywords                                                                                                         | Reference
----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------
Understand architecture & core resources  | Apigee X vs Hybrid, environment groups, organization, API proxy, API product, developer, developer app                   | [core-concepts.md](references/core-concepts.md)
Manage via CLI (gcloud / Helm)            | gcloud apigee, Helm, hybrid management, CLI commands, Kubernetes deployment                                              | [cli-usage.md](references/cli-usage.md)
Manage via direct REST API calls          | curl API, Apigee REST API, direct HTTP, One Platform API, lifecycle management                                           | [api-usage.md](references/api-usage.md)
Construct & package API proxy bundles     | apiproxy folder, proxy bundle, helloworld.xml, proxies/default.xml, targets/default.xml, packaging zip                   | [proxy-bundle-structure.md](references/proxy-bundle-structure.md)
Programmatically manage via Libraries     | Python SDK, Node.js client, Go client, Java client, programmatic management                                              | [client-library-usage.md](references/client-library-usage.md)
Declaratively provision via Terraform     | Terraform, IaC, google_apigee_api_proxy, google_apigee_api_product, google_apigee_developer, google_apigee_developer_app | [iac-usage.md](references/iac-usage.md)
Configure IAM & runtime security policies | VerifyAPIKey, SpikeArrest, OAuth v2.0, access token, security roles, IAM permissions                                     | [iam-security.md](references/iam-security.md)
Expose APIs as MCP tools                  | Model Context Protocol, MCP tools, MCP Discovery Proxy, openapi.yaml servers.url, API Hub MCP                            | [mcp-in-apigee.md](references/mcp-in-apigee.md)

*If you need detailed product information not found in these references, use the
[Developer Knowledge MCP server](https://developers.google.com/knowledge/mcp)
`search_documents` tool.*
