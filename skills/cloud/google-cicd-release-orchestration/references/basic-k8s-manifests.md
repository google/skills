# Basic Kubernetes manifests

This document provides examples for generating Kubernetes `Deployment` and
`Service` resource manifests that are used with Cloud Deploy to deploy to GKE.

The examples in this file use placeholders between `<` and `>`, e.g.
`<DEPLOYMENT_NAME>`. Replace these placeholders with the actual values when
generating the YAML.

Cloud Deploy performs build artifact substitutions on the image field so a
placeholder like `app-image` is used. When a Cloud Deploy `Release` is created
the user supplies the actual image and associates it with the `app-image` key.

## Kubernetes Deployment (Standard Web Service)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <DEPLOYMENT_NAME>
  labels:
    app: <APPLICATION_NAME>
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <APPLICATION_NAME>
  template:
    metadata:
      labels:
        app: <APPLICATION_NAME>
    spec:
      containers:
      - name: <APPLICATION_NAME>
        image: app-image
        ports:
        - containerPort: 8080
```

## Kubernetes Deployment (AI Agent or MCP Server with Agent Registry Discovery)

When deploying an **AI Agent** (`"AGENT"`) or **MCP Server** (`"MCP_SERVER"`) to
GKE, include the Agent Registry functional-type label, App Hub annotation, and
SPIFFE identity annotation:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <DEPLOYMENT_NAME>
  labels:
    app: <APPLICATION_NAME>
    registry.gke.io/functional-type: "AGENT" # Or "MCP_SERVER"
  annotations:
    apphub.cloud.google.com/functional-type: "AGENT" # Or "MCP_SERVER"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <APPLICATION_NAME>
  template:
    metadata:
      labels:
        app: <APPLICATION_NAME>
      annotations:
        iam.gke.io/spiffe-identity-type: "agent-identity"
    spec:
      containers:
      - name: <APPLICATION_NAME>
        image: app-image
        ports:
        - containerPort: 8080
```

## Kubernetes Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: <SERVICE_NAME>
  labels:
    app: <APPLICATION_NAME>
spec:
  selector:
    app: <APPLICATION_NAME>
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: LoadBalancer
```
