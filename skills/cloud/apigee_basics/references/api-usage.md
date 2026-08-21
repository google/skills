# Apigee Direct REST API Usage

Enterprise automation pipelines often call the **Apigee Management API**
directly. This document provides examples of how to interact with Apigee X and
Hybrid resources using HTTP REST calls and `curl`.

--------------------------------------------------------------------------------

## Base Configuration

*   **API Endpoint**: `https://apigee.googleapis.com/v1`
*   **Authentication**: Standard Google Cloud OAuth 2.0 Bearer tokens.

**Set Authorization Header**

```bash
export ORG="your-apigee-org"
export TOKEN=$(gcloud auth print-access-token)
export AUTH_HEADER="Authorization: Bearer ${TOKEN}"
```

--------------------------------------------------------------------------------

## 1. API Proxies

### List API Proxies

Returns a list of all API proxies configured in the organization.

```bash
curl -X GET "https://apigee.googleapis.com/v1/organizations/${ORG}/apis" \
  -H "${AUTH_HEADER}"
```

### Import an API Proxy Bundle

Uploads a local ZIP file containing the API proxy configuration files to create
a new proxy revision.

*   `helloworld-bundle.zip` must follow the
    [API Proxy Bundle Structure](proxy-bundle-structure.md) directory hierarchy.

```bash
curl -X POST "https://apigee.googleapis.com/v1/organizations/${ORG}/apis?action=import&name=helloworld" \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @helloworld-bundle.zip
```

### Deploy an API Proxy Revision

Deploys a specific revision of a proxy to a target environment.

```bash
export ENV="prod"
export REVISION="1"

curl -X POST "https://apigee.googleapis.com/v1/organizations/${ORG}/environments/${ENV}/apis/helloworld/revisions/${REVISION}/deployments" \
  -H "${AUTH_HEADER}"
```

### Undeploy an API Proxy Revision

Safely undeploys a revision from an environment.

```bash
curl -X DELETE "https://apigee.googleapis.com/v1/organizations/${ORG}/environments/${ENV}/apis/helloworld/revisions/${REVISION}/deployments" \
  -H "${AUTH_HEADER}"
```

--------------------------------------------------------------------------------

## 2. API Products

### Create an API Product

Creates an API Product that bundles specific resources and sets access rules.

```bash
curl -X POST "https://apigee.googleapis.com/v1/organizations/${ORG}/apiproducts" \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "InternalServicesProduct",
    "displayName": "Internal Services Product",
    "approvalType": "auto",
    "attributes": [
      {"name": "access", "value": "public"}
    ],
    "environments": ["prod"],
    "proxies": ["helloworld"],
    "quota": "100",
    "quotaInterval": "1",
    "quotaTimeUnit": "minute"
  }'
```

--------------------------------------------------------------------------------

## 3. Developers & Developer Apps

### Register a Developer

Registers a developer within the organization database.

```bash
curl -X POST "https://apigee.googleapis.com/v1/organizations/${ORG}/developers" \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "firstName": "Alice",
    "lastName": "Smith",
    "userName": "asmith"
  }'
```

### Create a Developer App

Creates an application registered by the developer and binds it to one or more
API Products. This triggers the generation of the client credentials (API Key).

```bash
curl -X POST "https://apigee.googleapis.com/v1/organizations/${ORG}/developers/alice@example.com/apps" \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AliceMobileApp",
    "apiProducts": ["InternalServicesProduct"],
    "callbackUrl": "https://example.com/callback"
  }'
```

### Fetch App Credentials (API Key)

Retrieve the Consumer Key and Consumer Secret generated for the Developer App.

```bash
curl -X GET "https://apigee.googleapis.com/v1/organizations/${ORG}/developers/alice@example.com/apps/AliceMobileApp" \
  -H "${AUTH_HEADER}"
```

*   Look for the `credentials` object in the JSON response. The `consumerKey`
    value is the key clients must supply when making API calls.
