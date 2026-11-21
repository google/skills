# Quotas and Rate Limiting Reference

- [How API Gateway Quotas Work](#how-api-gateway-quotas-work): Lines 9-21
- [Critical Rule: Quotas Apply to the Whole API](#critical-rule-quotas-apply-to-the-whole-api): Lines 23-33
- [OpenAPI 2.0 Quota Configuration](#openapi-20-quota-configuration): Lines 35-83
- [OpenAPI 3.x Quota Configuration](#openapi-3x-quota-configuration): Lines 85-139
- [Quota Migration from OpenAPI 2.0 to 3.x](#quota-migration-from-openapi-20-to-3x): Lines 141-150

## How API Gateway Quotas Work

API Gateway rate limits traffic as requests per minute per consumer Google Cloud project (`1/min/{project}`).

- **API key required:** Every quota-enforced operation MUST require an API key (`api_key: []`). **Rationale:** Service Control uses the API key to identify the consumer Google Cloud project and increment its per-project request counter.
- **One project per consumer:** Because quotas are tracked per Google Cloud project rather than per end user, create or require a separate Google Cloud project for each API consumer tenant that needs an isolated rate limit. To override a quota limit for one specific consumer project, configure a consumer override using that consumer's project number under **IAM & Admin > Quotas & System Limits** in the Google Cloud console.
- **Runtime behavior (`HTTP 429`):** When a consumer project exceeds its configured limit, API Gateway rejects the request before forwarding it to the backend and returns `HTTP 429 Too Many Requests` (or gRPC `ResourceExhausted`). Instruct client applications to catch `429` responses and retry with exponential backoff.
- **Fail-closed on 4xx quota errors:** API Gateway rejects requests (fails closed) when a 4xx client-side quota check failure occurs.
- **Approximate enforcement:** The gateway aggregates and batches quota calls to keep request latency low, so quota enforcement is approximate. A consumer can get more or fewer requests than the configured limit, and the difference is not a fixed percentage. Do not use API Gateway quotas for exact billing ledgers, spike arrest, or high-accuracy rate limiting.

References:
- [About quotas in API Gateway](https://docs.cloud.google.com/api-gateway/docs/quotas-overview.md.txt)
- [About quotas in Cloud Endpoints](https://docs.cloud.google.com/endpoints/docs/openapi/quotas-overview.md.txt)

## Critical Rule: Quotas Apply to the Whole API

You declare quota `metrics` and `quota.limits` inside an API config, but API Gateway applies those definitions to the parent **API resource** across all gateways, not only to the gateway running that API config. **Each time you create an API config (`gcloud api-gateway api-configs create`), its metrics and limits immediately replace the ones declared by earlier API configs for the entire API.**

1. **Limit value changes affect all gateways immediately upon config creation:** Creating an API config with a changed limit value updates the rate limit for every gateway of that API, even before `gateways update` is called.
2. **Metric renames or removals cause HTTP 500 outages:** NEVER rename or remove a quota metric in a new API config while any gateway of the API still serves an older API config that references the old metric name in `x-google-quota`. **Rationale:** Creating the new API config overwrites the API's metric definitions in Service Control, leaving older gateways with an invalid quota configuration; every call to a quota-enforced method on those older gateways fails with `HTTP 500` and the message `Failed to call Service Control Quota`.
3. **Two safe paths for metric changes:**
   - **Path A (Additive dual-metric transition, recommended for zero-downtime multi-gateway setups):** Run `python3 scripts/check_quota_metrics.py` against all active gateways (`--project` and `--api`). Keep both the old metric and the new metric defined in `metrics` and `quota.limits` in every newly created API config until all gateways of the API have been updated to configs that no longer reference the old metric.
   - **Path B (Immediate uniform upgrade):** Update every gateway of the API to the newly created API config immediately so no gateway continues serving an earlier config that references the removed metric.

Reference: [Quotas apply to the whole API](https://docs.cloud.google.com/api-gateway/docs/quotas-overview.md.txt)

## OpenAPI 2.0 Quota Configuration

In OpenAPI 2.0, declare `metrics` and `quota.limits` under root `x-google-management` as lists of objects, and attach costs on operations using `x-google-quota.metricCosts`:

```yaml
swagger: "2.0"
info:
  title: Orders API
  version: 1.0.0
x-google-management:
  metrics:
    - name: "read-requests"
      displayName: "Read requests"
      valueType: INT64
      metricKind: DELTA
    - name: "write-requests"
      displayName: "Write requests"
      valueType: INT64
      metricKind: DELTA
  quota:
    limits:
      - name: "read-limit"
        metric: "read-requests"
        unit: "1/min/{project}"
        values:
          STANDARD: 1000
      - name: "write-limit"
        metric: "write-requests"
        unit: "1/min/{project}"
        values:
          STANDARD: 100
securityDefinitions:
  api_key:
    type: "apiKey"
    name: "x-api-key"
    in: "header"
security:
  - api_key: []
paths:
  /v1/orders:
    get:
      operationId: listOrders
      x-google-quota:
        metricCosts:
          "read-requests": 1
      responses:
        200:
          description: OK
```

## OpenAPI 3.x Quota Configuration

In OpenAPI 3.x, declare `metrics` and `quota.limits` as YAML maps under root `x-google-api-management`, and set `x-google-quota` on each operation as a `{metric_name}: {integer_cost}` map. API Gateway reads `x-google-quota` only on operations. It ignores `x-google-quota` at the root and path levels with no error, so the limits for those metrics are never enforced:

```yaml
openapi: 3.0.4
info:
  title: Orders API
  version: 1.0.0
x-google-api-management:
  backends:
    orders-backend:
      address: https://{backend_service}-{hash}.a.run.app
      jwtAudience: https://{backend_service}-{hash}.a.run.app
  metrics:
    read-requests:
      displayName: "Read requests"
    write-requests:
      displayName: "Write requests"
  quota:
    limits:
      read-limit:
        metric: read-requests
        values: 1000
      write-limit:
        metric: write-requests
        values: 100
x-google-backend: orders-backend
components:
  securitySchemes:
    api_key:
      type: apiKey
      name: x-api-key
      in: header
security:
  - api_key: []
paths:
  /v1/orders:
    get:
      operationId: listOrders
      x-google-quota:
        read-requests: 1
      responses:
        "200":
          description: OK
    post:
      operationId: createOrder
      x-google-quota:
        write-requests: 5
      responses:
        "201":
          description: Created
```

Reference: [OpenAPI 3.x extensions - x-google-quota](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)

## Quota Migration from OpenAPI 2.0 to 3.x

When converting an OpenAPI 2.0 specification to OpenAPI 3.x:

1. Move `metrics` and `quota` from `x-google-management` into `x-google-api-management`.
2. Convert `metrics` and `quota.limits` from YAML arrays (`- name: ...`) into YAML maps keyed by metric and limit name, and preserve the exact metric keys.
3. Remove `valueType`, `metricKind`, `unit`, and `STANDARD:` wrapper keys (`values` in OpenAPI 3.x is a direct `int64` integer).
4. Replace `x-google-quota: { metricCosts: { ... } }` with `x-google-quota: { {metric_name}: {cost} }`.

Reference: [Modify a gateway to use OpenAPI 3.x](https://docs.cloud.google.com/api-gateway/docs/migrate-oasv3.md.txt)
