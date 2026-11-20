# Configure Delivery Pipelines

This document provides examples for configuring Cloud Deploy `DeliveryPipeline`
resources. The examples are in YAML format and are intended to be used with the
`gcloud deploy apply` command to create or update the resource. Use these
examples if it fits the users requirements.

The examples in this file use placeholders between `<` and `>`, e.g.
`<PIPELINE_ID>`. Replace these placeholders with the actual values when
generating the YAML.

## Table of Contents

-   [Pipeline with a single target](#pipeline-with-a-single-target) (Lines
    23-37)
-   [Pipeline with multiple targets](#pipeline-with-multiple-targets) (Lines
    39-56)
-   [Pipeline with the canary deployment strategy](#pipeline-with-the-canary-deployment-strategy)
    (Lines 58-115)
-   [Pipeline with Google Observability metrics analysis (Cloud Run)](#pipeline-with-google-observability-metrics-analysis-cloud-run)
    (Lines 117-189)

## Pipeline with a single target

This is the minimal `DeliveryPipeline` that can be defined. It only contains a
single target.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
 name: <PIPELINE_ID>
serialPipeline:
 stages:
 - targetId: <TARGET_ID>
   profiles: [<TARGET_ID>]
```

## Pipeline with multiple targets

This `DeliveryPipeline` contains multiple targets in the progression sequence.
Cloud Deploy will deploy to the targets in the order they are listed in the
`stages` field.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
 name: <PIPELINE_ID>
serialPipeline:
 stages:
 - targetId: <TARGET_ID1> # e.g. "Dev" target.
   profiles: [<TARGET_ID1>]
 - targetId: <TARGET_ID2> # e.g. "Production" target.
   profiles: [<TARGET_ID2>]
```

## Pipeline with the canary deployment strategy

The `percentages` field is a list of percentages to use for the canary
deployment strategy. For example, deploy 10% of traffic to the canary, then 50%,
before the stable phase. The `percentages` field **cannot** contain 100 since
that is assumed by the stable phase.

### Cloud Run

For Cloud Deploy to automatically handle canarying for Cloud Run the
`canary.runtimeConfig.cloudRun.automaticTrafficControl` field **must** be set to
`true`.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
 name: <PIPELINE_ID>
serialPipeline:
  stages:
  - targetId: <TARGET_ID>
    profiles: [<TARGET_ID>]
    strategy:
      canary:
        runtimeConfig:
          cloudRun:
            automaticTrafficControl: true
        canaryDeployment:
          percentages: [10, 50]
```

### GKE

Cloud Deploy requires the Kubernetes `Deployment` and `Service` names to
automatically handle canarying for GKE. Check the local workspace for Kubernetes
manifests to determine the `Deployment` and `Service` names, or ask the user to
provide them. If the former, confirm with the user that the right `Deployment`
and `Service` were determined.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
 name: <PIPELINE_ID>
serialPipeline:
  stages:
  - targetId: <TARGET_ID>
    profiles: [<TARGET_ID>]
    strategy:
      canary:
        runtimeConfig:
          kubernetes:
            serviceNetworking:
              service: <SERVICE_NAME>
              deployment: <DEPLOYMENT_NAME>
        canaryDeployment:
          percentages: [10, 50]
```

## Pipeline with Google Observability metrics analysis (Cloud Run)

The examples in this section leverage `labels` to filter the incidents for the
alert policies to only take into account the Cloud Run `Service` and `Revision`
that is being deployed. The `duration` is set to 30 minutes (`1800s`) to give
the alerting policies time to evaluate the metrics and potentially trigger
incidents.

### Standard deployment strategy with analysis

This `DeliveryPipeline` is configured to monitor a single Google Cloud
Observability alert policy for any incidents over a 30 minute (`1800s`) period
after the application has been deployed.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
 name: <PIPELINE_ID>
serialPipeline:
  stages:
  - targetId: <TARGET_ID>
    profiles: [<TARGET_ID>]
    strategy:
      standard:
        analysis:
          duration: 1800s
          googleCloud:
            alertPolicyChecks:
            - id: alert-check-1
              alertPolicies:
              - projects/<PROJECT_ID>/alertPolicies/<ALERT_POLICY_ID>
              labels:
                service_name: '${{ render.metadata.cloud_run.service.id }}'
                revision_name: '${{ render.metadata.cloud_run.revision.id }}'
```

### Canary deployment strategy with analysis

This `DeliveryPipeline` is configured to monitor a single Google Cloud
Observability alert policy for any incidents over a 30 minute (`1800s`) period
after deploying in each phase of the `Rollout`. In this case Cloud Deploy will
monitor the alert policy after deploying 50% of the traffic to the new version
and after deploying 100% of the traffic to the new version during the stable
phase.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
 name: <PIPELINE_ID>
serialPipeline:
  stages:
  - targetId: <TARGET_ID>
    profiles: [<TARGET_ID>]
    strategy:
      canary:
        runtimeConfig:
          cloudRun:
            automaticTrafficControl: true
        canaryDeployment:
          percentages: [50]
          analysis:
            duration: 1800s
            googleCloud:
              alertPolicyChecks:
              - id: alert-check-1
                alertPolicies:
                - projects/<PROJECT_ID>/alertPolicies/<ALERT_POLICY_ID>
                labels:
                  service_name: '${{ render.metadata.cloud_run.service.id }}'
                  revision_name: '${{ render.metadata.cloud_run.revision.id }}'
```
