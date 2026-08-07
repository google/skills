---
name: cloud-logging-query-generation
metadata:
  category: CloudObservabilityAndMonitoring
description: >-
  Generates Logging Query Language (LQL) queries for Google Cloud Logging from natural language. Use this skill when you need to query log data or when you are debugging issues. You can filter log data by Google Cloud service. Don't use this skill to query other databases, such as SQL or Cloud Spanner.
---

# Generate Logging Query Language queries

Use this skill to generate correct Logging Query Language (LQL) queries for
Cloud Logging.

## Core rules

1.  **Strict syntax requirements:**

    *   **Always use double quotes (`"`)** for string literals. Do not use
        single quotes (`'`).
    *   Write boolean operators in all capitals: `AND`, `OR`, `NOT`.
    *   Always use parentheses to group terms and explicitly enforce precedence.

2.  **Common pitfalls:**

    *   **Instance ID vs. Instance Name:** For the `gce_instance` resource type,
        do NOT compare instance names to instance IDs. Instance names are
        strings (for example, `my-instance`). Instance IDs are numeric. If you
        only have the name, then search by instance name,
        `SEARCH("my-instance")`, or use `resource.labels.instance_name` if that
        label is available for the resource.
    *   **Resource Type Accuracy:** Do not guess resource types. You must look
        up the correct `resource.type` value in the service-specific reference
        files. For example, use `internal_http_lb_rule` for Internal HTTP(S)
        Load Balancer rules when filtering by forwarding rule name or region
        (instead of `http_load_balancer`).

3.  **Output format and placeholders:**

    *   Output **only** the raw LQL query text. Do not include conversational
        filler. Do not wrap the query in markdown code blocks unless explicitly
        requested by the user. Valid LQL comments (using `--`) are allowed, and
        are the ONLY acceptable way to include explanations or warnings.
    *   **Never block on missing variables.** If the user's request lacks
        specific identifiers (like a project ID, instance name, or IP address),
        do not ask them for clarification. If the variable is required for a
        functional query (like a log bucket name for a regional log), insert an
        uppercase placeholder string wrapped in angle brackets (for example,
        `"<PROJECT_ID>"`). **CRITICALLY**: If you include a placeholder for a
        variable the user omitted, it will act as an explicit filter that causes
        logs to be missed. Therefore, you MUST omit the entire filter/line
        containing the placeholder if the field is not strictly required. For
        example, completely omit `resource.labels.instance_id="..."` if the user
        didn't specify an instance, but you MUST include
        `logName=".../projects/<PROJECT_ID>/..."` with a placeholder if
        constructing a regional log bucket query where a project ID is strictly
        required.

4.  **Preferred fields:**

    *   Include `resource.type` and `log_id` restrictions when the query targets
        specific Google Cloud services or resources. Global queries (for
        example, "latest error logs") do not require these restrictions.

## Detailed reference

Refer to `references/api_reference.md` for LQL syntax rules, including
Operators, NULL handling, SEARCH, and Regex.

## Service reference files

Before generating a query, you MUST read the examples for the specific service.
LQL schemas and `resource.type` values are service-specific. **Do not stop
reading after finding the Base Schema in the file. You must verify if there are
specific requirements for state tracking (like `previousState`) or
resource-specific log IDs detailed in the paragraphs or specific query examples
below the schema block.**

**For the following services, read the exact file listed:**

*   [App Engine](references/query_app_engine.md)
*   [BigQuery](references/query_bigquery.md)
*   [Cloud Deployment Manager](references/query_deployment_manager.md)
*   [Cloud Functions](references/query_cloud_functions.md)
*   [Cloud Observability (Monitoring, Logging, Trace)](references/query_cloud_observability.md)
*   [Cloud Run](references/query_cloud_run.md)
*   [Cloud Source Repositories](references/query_cloud_source_repositories.md)
*   [Cloud Spanner](references/query_spanner.md)
*   [Cloud SQL](references/query_cloud_sql.md)
*   [Cloud Storage](references/query_cloud_storage.md)
*   [Cloud Tasks](references/query_cloud_tasks.md)
*   [Compute Engine (GCE)](references/query_compute_engine.md)
*   [Dataflow](references/query_dataflow.md)
*   [Dataproc](references/query_dataproc.md)
*   [Kubernetes Engine (GKE)](references/query_gke.md)
*   [IAM & Service Accounts](references/query_iam.md)
*   [Networking (VPC, Load Balancing, and others)](references/query_networking.md)
*   [Security (Audit logging)](references/query_security.md)
*   [Service Usage (Enable/Disable API, Quotas)](references/query_service_usage.md)
*   [Third Party (for example, Nginx, Apache)](references/query_third_party.md)

**For Google Cloud services that aren't listed:** If the service is not listed
above, write the LQL query based on your general knowledge.

## Query generation rules

1.  **Resource Types:** Explicitly define the `resource.type` in your queries
    when focusing on specific services. For some queries, you may need to search
    across multiple types (for example, `resource.type=("bigquery_project" OR
    "bigquery_dataset")`).
2.  **Audit and Admin Logs:** If the user asks for audit logs, admin logs, API
    logs, or logs about who created, updated, deleted, read, or accessed a
    resource:
    *   You MUST read
        [references/query_audit_logs.md](references/query_audit_logs.md) for the
        correct `protoPayload` schema paths and common examples.
    *   If a specific example is not listed, guess the `protoPayload.methodName`
        by combining the service and verb. When guessing, you MUST use the
        scoped `SEARCH()` function (e.g., `SEARCH(protoPayload.methodName,
        "compute.instances.insert")`) instead of the exact match operator (`=`)
        to avoid version prefix mismatches. Do NOT use the colon operator (`:`)
        as it may cause substring false positives.
    *   For generic API enable/disable events (e.g., a service was disabled),
        always use `resource.type="audited_resource"`.
3.  **Handling Unknown Schemas (Crucial):** If the user asks to filter by a
    specific field or condition, and if you cannot find a matching example or
    schema in the reference files, **then you must generate a query using global
    search.**
    *   Only specify `jsonPayload.*` or `protoPayload.*` field structures when
        you are certain of their exact name.
    *   Use the `SEARCH()` function to find the keyword globally within the
        correct `resource.type`.
    *   **Mandatory LQL Comment:** When delivering a query that uses `SEARCH`,
        you MUST add an LQL comment (using `--`) at the top of the query
        indicating you used a global keyword search because the exact schema
        wasn't in your references. Do NOT output conversational text, strictly
        adhere to the Output Format rule.

## Supporting links

*   [Cloud Logging query language documentation](https://docs.cloud.google.com/logging/docs/view/logging-query-language)
*   [Monitored resource types catalog](https://docs.cloud.google.com/logging/docs/api/v2/resource-list)
*   [Cloud Logging query library](https://docs.cloud.google.com/logging/docs/view/query-library)
