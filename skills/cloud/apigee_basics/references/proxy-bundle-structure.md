# Apigee API Proxy Bundle Structure

Apigee API proxies are deployed as zip archives called **API Proxy Bundles**. To
programmatically generate or manually author a valid, deployable API proxy, you
must follow a strict directory structure and use correct XML configuration
files.

This document details the folder hierarchy, standard XML templates, and
packaging steps for a basic "hello-world" API proxy.

--------------------------------------------------------------------------------

## 1. Directory Hierarchy

An API Proxy Bundle must have `apiproxy` as its root folder. The standard
structure is:

```text
apiproxy/
├── helloworld.xml        # Base Configuration (must match name attribute & folder parent)
├── proxies/
│   └── default.xml       # ProxyEndpoint Configuration (defines ingress & routing)
└── targets/
    └── default.xml       # TargetEndpoint Configuration (defines egress target URL)
```

*   **Optional Folders**:
    *   `apiproxy/policies/`: XML policy configuration files (e.g.,
        `VerifyAPIKey.xml`, `SpikeArrest.xml`).
    *   `apiproxy/resources/`: Contains custom scripts (e.g., `jsc/` for
        JavaScript, `py/` for Python, `java/` for custom JARs).

--------------------------------------------------------------------------------

## 2. Base XML Templates

Below are the exact XML configurations required to build a valid, deployable
hello-world API proxy named `helloworld` routing to
`https://mocktarget.apigee.net`.

### A. Base Configuration: `apiproxy/helloworld.xml`

This defines the proxy name and references all proxy and target endpoints. The
filename **must** match the `<APIProxy name="...">` attribute.

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<APIProxy revision="1" name="helloworld">
    <ConfigurationVersion majorVersion="4" minorVersion="0"/>
    <Description>Hello World API Proxy facade routing to Mock Target</Description>
    <DisplayName>helloworld</DisplayName>
    <ProxyEndpoints>
        <ProxyEndpoint>default</ProxyEndpoint>
    </ProxyEndpoints>
    <TargetEndpoints>
        <TargetEndpoint>default</TargetEndpoint>
    </TargetEndpoints>
</APIProxy>
```

### B. ProxyEndpoint: `apiproxy/proxies/default.xml`

Defines the client-facing ingress interface and routing rules. * `<BasePath>`
specifies the URI fragment clients target (e.g. `/helloworld`). * `<RouteRule>`
maps the request to a named target endpoint (in this case, `default`).

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ProxyEndpoint name="default">
    <Description>Default Proxy Endpoint</Description>
    <PreFlow name="PreFlow">
        <Request/>
        <Response/>
    </PreFlow>
    <Flows/>
    <PostFlow name="PostFlow">
        <Request/>
        <Response/>
    </PostFlow>
    <HTTPProxyConnection>
        <BasePath>/helloworld</BasePath>
    </HTTPProxyConnection>
    <RouteRule name="default">
        <TargetEndpoint>default</TargetEndpoint>
    </RouteRule>
</ProxyEndpoint>
```

### C. TargetEndpoint: `apiproxy/targets/default.xml`

Defines the backend-facing egress interface and target connection URL. * `<URL>`
specifies the destination backend address.

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<TargetEndpoint name="default">
    <Description>Default Target Endpoint</Description>
    <PreFlow name="PreFlow">
        <Request/>
        <Response/>
    </PreFlow>
    <Flows/>
    <PostFlow name="PostFlow">
        <Request/>
        <Response/>
    </PostFlow>
    <HTTPTargetConnection>
        <URL>https://mocktarget.apigee.net</URL>
    </HTTPTargetConnection>
</TargetEndpoint>
```

--------------------------------------------------------------------------------

## 3. Packaging the Bundle

To package these files into a deployable zip archive, navigate to the parent
directory containing the `apiproxy` folder and run the standard `zip` utility:

```bash
zip -r helloworld.zip apiproxy/
```

*   **Important Packaging Rules**:
    *   The `apiproxy` folder must be at the root of the zip archive. Do not zip
        the outer parent folder (e.g., zipping `my-project/apiproxy` from
        outside will cause deployment errors; you must be inside `my-project`
        and run `zip -r helloworld.zip apiproxy/`).
    *   Ensure there are no hidden folders (like `.git`) included inside the
        `apiproxy/` directories.
