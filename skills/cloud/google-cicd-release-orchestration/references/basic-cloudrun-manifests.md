# Basic Cloud Run manifests

This document provides examples for generating Cloud Run resource manifests that
are used with Cloud Deploy to deploy to Cloud Run. The Cloud Run YAML reference
is available at: https://docs.cloud.google.com/run/docs/reference/yaml/v1.

The examples in this file use placeholders between `<` and `>`, e.g.
`<SERVICE_NAME>`. Replace these placeholders with the actual values when
generating the YAML.

Cloud Deploy performs build artifact substitutions on the image field so a
placeholder like `app-image` is used. When a Cloud Deploy `Release` is created
the user supplies the actual image and associates it with the `app-image` key.

## Cloud Run Service (Standard / Dev)

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: <SERVICE_NAME>
spec:
  template:
    spec:
      containers:
      - image: app-image
        ports:
        - containerPort: 8080
```

## Cloud Run Service (Production with Binary Authorization)

When deploying to a production Cloud Run target (`prod`) with Binary
Authorization enabled (`"binary_authorization": "default"` in
`deployment-config.json`), include the `run.googleapis.com/binary-authorization`
annotation:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: <SERVICE_NAME>
  annotations:
    run.googleapis.com/binary-authorization: default
spec:
  template:
    spec:
      containers:
      - image: app-image
        ports:
        - containerPort: 8080
```

## Cloud Run Service (AI Agent or MCP Server with Agent Registry Auto-Registration)

When deploying an **AI Agent** (`functional-type: agent`) or **MCP Server**
(`functional-type: mcp-server`), include the Agent Registry auto-registration
labels in `metadata.labels`:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: <SERVICE_NAME>
  labels:
    functional-type: agent # Or mcp-server
    agent-registry-auto-register: "true"
spec:
  template:
    spec:
      containers:
      - image: app-image
        ports:
        - containerPort: 8080
```

## Cloud Run Worker Pool

```yaml
apiVersion: run.googleapis.com/v1
kind: WorkerPool
metadata:
  name: <WORKER_POOL_NAME>
spec:
  template:
    spec:
      containers:
      - image: app-image
```
