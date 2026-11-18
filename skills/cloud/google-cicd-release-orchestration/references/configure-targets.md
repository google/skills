# Configure Targets

This document provides examples for configuring Cloud Deploy `Target` resources.
The examples are in YAML format and are intended to be used with the
`gcloud deploy apply` command to create or update the resource. Use these
examples if it fits the users requirements.

The examples in this file use placeholders between `<` and `>`, e.g.
`<TARGET_ID>`. Replace these placeholders with the actual values when generating
the YAML.

## Cloud Run target

### Minimal Cloud Run target

Minimal Cloud Run `Target` only requires specifying the project and location of
the Cloud Run Service.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: <TARGET_ID>
run:
  location: projects/<CLOUD_RUN_PROJECT_ID>/locations/<CLOUD_RUN_LOCATION>
```

### Require approval

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: <TARGET_ID>
run:
  location: projects/<CLOUD_RUN_PROJECT_ID>/locations/<CLOUD_RUN_LOCATION>
requireApproval: true
```

## Google Kubernetes Engine (GKE) target

### Minimal GKE target

Minimal GKE `Target` only requires specifying the name of the GKE cluster.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: <TARGET_ID>
gke:
  cluster: projects/<CLUSTER_PROJECT_ID>/locations/<CLUSTER_LOCATION>/clusters/<CLUSTER_ID>
```

### Require approval

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: <TARGET_ID>
gke:
  cluster: projects/<CLUSTER_PROJECT_ID>/locations/<CLUSTER_LOCATION>/clusters/<CLUSTER_ID>
requireApproval: true
```
