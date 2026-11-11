# Remediation: APIs and audit logs

These templates change resources. Print them for the user to run; never run
them.

## Enable an API

Role: Service Usage Admin (`roles/serviceusage.serviceUsageAdmin`).

```bash
gcloud services enable {api} --project={project_id}
```

Source:
[Enable and disable services](https://docs.cloud.google.com/service-usage/docs/enable-disable.md.txt).

## Enable Data Access audit logs for IAP

Role: the `resourcemanager.projects.setIamPolicy` permission on the project,
for example through Project IAM Admin (`roles/resourcemanager.projectIamAdmin`).

1.  Save the project's IAM policy:

    ```bash
    gcloud projects get-iam-policy {project_id} --format=json > policy.json
    ```

2.  In `policy.json`, turn on all three Data Access log types for IAP. Don't
    change `bindings` or `etag`. This is the entry:

    ```json
    {
      "service": "iap.googleapis.com",
      "auditLogConfigs": [
        { "logType": "ADMIN_READ" },
        { "logType": "DATA_READ" },
        { "logType": "DATA_WRITE" }
      ]
    }
    ```

    If `auditConfigs` already has an `iap.googleapis.com` entry, add the
    missing `logType` values to it. Otherwise append this object, and create
    the list if it's missing. Don't edit an `allServices` entry, because that
    turns the log types on for every service. Never add a second
    `auditConfigs` key or a second `iap.googleapis.com` entry.

3.  Write the policy back. This replaces the project's whole IAM policy, so
    the file must still contain every binding. If the command fails because
    the policy changed after step 1, start again from step 1.

    ```bash
    gcloud projects set-iam-policy {project_id} policy.json
    ```

4.  Reproduce the failure, then run the IAP decision query in
    [audit-logs.md](audit-logs.md).

Data Access audit logs add log volume, which might be charged. Source:
[Configure Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access.md.txt).

## Wait time

An audit configuration change has no published figure and can take a few
minutes to apply. Retest after a few minutes, and look for a new audit entry.
