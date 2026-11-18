# Configure Skaffold YAML

This document provides examples for configuring a `skaffold.yaml` file used when
creating a Cloud Deploy `Release` for a `DeliveryPipeline`.

**TIP**: Try not to deviate from these examples since most Skaffold
configuration is **not applicable** to Cloud Deploy. For example, the top-level
`build` stanza in a `skaffold.yaml` does nothing with Cloud Deploy.

## Table of Contents

-   [Deploy to Cloud Run](#deploy-to-cloud-run) (Lines 15-59)
-   [Deploy to GKE](#deploy-to-gke) (Lines 61-136)

## Deploy to Cloud Run

**CRITICAL** when deploying to Cloud Run:

-   **MUST** include the `cloudrun` deployer.
-   **ALWAYS** use `rawYaml` under `manifests` unless the user specifies
    otherwise.

Minimal `skaffold.yaml` file for deploying to Cloud Run. Requires a reference to
the Cloud Run manifest file that contains the Cloud Run resource.

```yaml
apiVersion: skaffold/v4beta13
kind: Config
deploy:
  cloudrun: {}
profiles:
- name: <TARGET_ID>
  manifests:
    rawYaml:
    - <MANIFEST_FILE_NAME>
```

### With different files per target

Uses different Cloud Run manifests for each `Target` in the `DeliveryPipeline`.
Since the Cloud Run resource name is defined within the manifest files, this is
generally the expected configuration when deploying to Cloud Run to multiple
`Target`s.

```yaml
apiVersion: skaffold/v4beta13
kind: Config
deploy:
  cloudrun: {}
profiles:
- name: <TARGET_ID_1>
  manifests:
    rawYaml:
    - <MANIFEST_FILE_NAME_1>
- name: <TARGET_ID_2>
  manifests:
    rawYaml:
    - <MANIFEST_FILE_NAME_2>
```

## Deploy to GKE

Minimal `skaffold.yaml` file for deploying to GKE. Requires a reference to the
Kubernetes manifests file that contains resources such as a `Deployment` and
`Service`.

```yaml
apiVersion: skaffold/v4beta13
kind: Config
deploy:
  kubectl: {}
profiles:
- name: <TARGET_ID>
  manifests:
    rawYaml:
    - <MANIFEST_FILE_NAME>
```

### With different files per target

Uses different Kubernetes manifests for each `Target` in the `DeliveryPipeline`.
This is useful when the Kubernetes resource configurations are not identical
across environments.

```yaml
apiVersion: skaffold/v4beta13
kind: Config
deploy:
  kubectl: {}
profiles:
- name: <TARGET_ID_1>
  manifests:
    rawYaml:
    - <MANIFEST_FILE_NAME_1>
- name: <TARGET_ID_2>
  manifests:
    rawYaml:
    - <MANIFEST_FILE_NAME_2>
```

### Helm chart

Minimal `skaffold.yaml` file for deploying to GKE when the Kubernetes resources
are defined in a Helm chart.

```yaml
apiVersion: skaffold/v4beta13
kind: Config
deploy:
  kubectl: {}
profiles:
- name: <TARGET_ID>
  manifests:
    helm:
      releases:
      - name: <APPLICATION_NAME>
        chartPath: <PATH_TO_HELM_CHART>
```

### Kustomize

Minimal `skaffold.yaml` file for deploying to GKE when the Kubernetes resources
are defined in Kustomization file.

```yaml
apiVersion: skaffold/v4beta13
kind: Config
deploy:
  kubectl: {}
profiles:
- name: <TARGET_ID>
  manifests:
    kustomize:
      paths:
      - <PATH_TO_KUSTOMIZE_DIR>
```
