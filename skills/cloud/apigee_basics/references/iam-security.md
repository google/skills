# Apigee IAM & Security Policies

Securing an API involves both control plane access (who can configure proxies)
and data plane enforcement (how proxy traffic is protected). This document
details standard IAM roles and runtime security policies in Apigee.

--------------------------------------------------------------------------------

## 1. Control Plane: IAM Roles

GCP IAM controls access to Apigee management resources. The following predefined
roles are standard:

*   **Apigee Admin (`roles/apigee.admin`)**:
    *   Full access to create, edit, and delete all resources (proxies,
        products, environments, keystores, service accounts).
    *   Assign this to DevOps engineers, administrators, and deployment service
        accounts.
*   **Apigee API Creator (`roles/apigee.apiCreator`)**:
    *   Permissions to create and import API proxies. Cannot create environment
        groups, environments, or deploy proxies to environment-level resources.
    *   Assign to standard API developers.
*   **Apigee Deployer (`roles/apigee.deployer`)**:
    *   Permission to deploy and undeploy API proxy revisions to environments.
    *   Assign to CI/CD pipelines and operations engineers.
*   **Apigee Developer (`roles/apigee.developer`)**:
    *   Permissions to read proxies, products, and manage developers and
        developer apps.
    *   Ideal for portal administrators managing app credentials.

--------------------------------------------------------------------------------

## 2. Data Plane: Security Policies

API proxies use specialized **Policies** (XML configurations) to secure runtime
traffic.

### A. API Key Verification (`VerifyAPIKey`)

The most common way to authenticate client apps. The policy verifies that a
supplied key is valid and registered for the API Product being accessed.

**Policy Configuration (`VerifyAPIKey-HelloWorld.xml`)**:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VerifyAPIKey async="false" continueOnError="false" enabled="true" name="VerifyAPIKey-HelloWorld">
    <DisplayName>Verify API Key - HelloWorld</DisplayName>
    <!-- Look for the key in the request query parameter named `apikey` -->
    <APIKey ref="request.queryparam.apikey"/>
</VerifyAPIKey>
```

**Flow Placement**: Always place this step in the **ProxyEndpoint PreFlow** to
block unauthorized calls immediately:

```xml
<ProxyEndpoint name="default">
    <PreFlow name="PreFlow">
        <Request>
            <Step>
                <Name>VerifyAPIKey-HelloWorld</Name>
            </Step>
        </Request>
        <Response/>
    </PreFlow>
</ProxyEndpoint>
```

--------------------------------------------------------------------------------

### B. Spike Arrest (`SpikeArrest`)

Spike Arrest protects backend target servers from sudden traffic spikes, denial
of service (DoS) attacks, or malfunctioning client code.

**Policy Configuration (`SpikeArrest-10ps.xml`)**:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<SpikeArrest async="false" continueOnError="false" enabled="true" name="SpikeArrest-10ps">
    <DisplayName>Spike Arrest - 10ps</DisplayName>
    <!-- Limit traffic to 10 requests per second -->
    <Rate>10ps</Rate>
</SpikeArrest>
```

*   *Note*: Spike Arrest operates on a sliding window. A rate of `10ps` means
    Apigee permits one request roughly every 100 milliseconds. Requests
    exceeding this micro-interval are immediately blocked with a `429 Too Many
    Requests` error.

**Flow Placement**: Place at the very beginning of the **ProxyEndpoint PreFlow**
(even before authentication) to drop excessive traffic before consuming gateway
CPU resources.

--------------------------------------------------------------------------------

### C. OAuth v2.0 Access Token Verification (`OAuthV2`)

Used to verify OAuth 2.0 Bearer tokens supplied in the `Authorization` header.

**Policy Configuration (`VerifyAccessToken.xml`)**:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<OAuthV2 async="false" continueOnError="false" enabled="true" name="VerifyAccessToken">
    <DisplayName>Verify Access Token</DisplayName>
    <Operation>VerifyAccessToken</Operation>
</OAuthV2>
```

*   *Note on Optional Scopes*: By default, omitting the `<Scope>` element
    verifies the token validity only (Authentication-only). To enforce
    fine-grained authorization, you can add the `<Scope>` element under the
    operation (e.g., `<Scope>read:products</Scope>`).

**Flow Placement**: Place in the **ProxyEndpoint PreFlow** prior to routing.
Once verified, details about the authenticated application and developer are
exposed in context variables (e.g., `developer.app.name`, `developer.email`).
