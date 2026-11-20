# Configure Automations

This document provides examples for configuring Cloud Deploy `Automation`
resources. The examples are in YAML format and are intended to be used with the
`gcloud deploy apply` command to create or update the resource. Use these
examples if it fits the users requirements.

The examples in this file use placeholders between `<` and `>`, e.g.
`<AUTOMATION_ID>`. Replace these placeholders with the actual values when
generating the YAML.

**CRITICAL**:

-   The `metadata.name` field for an `Automation` resource is made up of the
    `DeliveryPipeline` ID and the `Automation` ID, separated by a forward slash.
    For example, if the `DeliveryPipeline` ID is "hello-world" and the
    `Automation` ID is "promote" then the `metadata.name` field should be
    "hello-world/promote".
-   Automations **require** a dedicated least-privilege service account with
    `roles/clouddeploy.operator` (never use the default Compute Engine SA):

```
clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
```

## Table of Contents

-   [Automatic Rollbacks](#automatic-rollbacks) (Lines 37-83)
-   [Automatic Rollbacks with Retry](#automatic-rollbacks-with-retry) (Lines
    85-108)
-   [Automatic Promotions on a Schedule](#automatic-promotions-on-a-schedule)
    (Lines 110-131)
-   [Automatic Promotion after a Delay](#automatic-promotion-after-a-delay)
    (Lines 133-153)
-   [Automatic Canary Advance](#automatic-canary-advance) (Lines 155-174)

## Automatic Rollbacks

This `Automation` will rollback for any `Target` in the `DeliveryPipeline`
progression sequence if any job in the `Rollout` fails.

The `*` in the `selector.targets.id` field means that this `Automation` will
apply to all `Target` resources in the `DeliveryPipeline`.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Automation
metadata:
  name: <PIPELINE_ID>/<AUTOMATION_ID>
serviceAccount: clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
selector:
  targets:
  - id: "*"
rules:
- repairRolloutRule:
    id: "repair-rule"
    repairPhases:
    - rollback: {}
```

Automatic rollbacks can be triggered for a subset of `Rollout` jobs. For
example, if the user wants to rollback only if the `deploy` or `analysis` job
fail, the `Automation` would be defined as follows:

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Automation
metadata:
  name: <PIPELINE_ID>/<AUTOMATION_ID>
serviceAccount: clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
selector:
  targets:
  - id: "*"
rules:
- repairRolloutRule:
    id: "repair-rule"
    jobs: ["deploy", "analysis"]
    repairPhases:
    - rollback: {}
```

The possible values include: `predeploy`, `deploy`, `postdeploy`, `verify`, and
`analysis`.

## Automatic Rollbacks with Retry

This `Automation` will attempt to retry the failed `Rollout` job up to 3 times
with a 1 minute wait between attempts. If the `Rollout` still fails after the
retries then it will be rolled back.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Automation
metadata:
  name: <PIPELINE_ID>/<AUTOMATION_ID>
serviceAccount: clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
selector:
  targets:
  - id: "*"
rules:
- repairRolloutRule:
    id: "repair-rule"
    repairPhases:
    - retry:
        attempts: 3
        wait: 1m
    - rollback: {}
```

## Automatic Promotions on a Schedule

This `Automation` will automatically promote a release to the next `Target` in
the `DeliveryPipeline` progression sequence every Monday at 12:00 PM New York
time.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Automation
metadata:
  name: <PIPELINE_ID>/<AUTOMATION_ID>
serviceAccount: clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
selector:
  targets:
  - id: <FROM_TARGET_ID>
rules:
- timedPromoteReleaseRule:
    id: "timed-promote-rule"
    schedule: "0 12 * * 1" # Cron format.
    timeZone: "America/New_York" # IANA format.
    destinationTargetId: "@next" # promote to the next `Target` in the `DeliveryPipeline` progression sequence.
```

## Automatic Promotion after a Delay

This `Automation` will automatically promote a release to the next `Target` in
the `DeliveryPipeline` after 3 hours has passed since the release was rolled out
to the previous `Target`.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Automation
metadata:
  name: <PIPELINE_ID>/<AUTOMATION_ID>
serviceAccount: clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
selector:
  targets:
  - id: <FROM_TARGET_ID>
rules:
- promoteReleaseRule:
    id: "promote-rule"
    wait: 3h
    destinationTargetId: "@next" # promote to the next `Target` in the `DeliveryPipeline` progression sequence.
```

## Automatic Canary Advance

This `Automation` will automatically advance through each phase of a canary
`Rollout` for a specific `Target` after 1 hour has passed since the previous
phase completed.

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: Automation
metadata:
  name: <PIPELINE_ID>/<AUTOMATION_ID>
serviceAccount: clouddeploy-automation@<PROJECT_ID>.iam.gserviceaccount.com
selector:
  targets:
  - id: <TARGET_ID>
rules:
- advanceRolloutRule:
    id: "advance-rule"
    wait: 1h
```
