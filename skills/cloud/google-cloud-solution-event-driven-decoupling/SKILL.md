---
name: google-cloud-solution-event-driven-decoupling
metadata:
  version: "1.0.0"
  category: MultiProductSolutions
description: >-
  Decouples tightly coupled services or monoliths with Google Cloud Pub/Sub so
  services scale and fail independently, using Go reference implementations
  adaptable to Java, Python, Node.js, and other stacks. Use when breaking apart
  synchronous chains, defining transaction boundaries, bulkheads, and
  Transactional Outbox or post-commit publishing; sizing Pub/Sub topics,
  subscription filters, dead-letter policies, backoff, 10 MB Cloud Storage
  claim-check, or database-bounded flow control; building idempotent consumers
  with ack/nack/quarantine handling, SIGTERM draining, GKE HPA, Cloud Run push,
  Eventarc, or Cloud Run functions (--retry); or instrumenting OpenTelemetry W3C
  Trace Context across HTTP, gRPC, and Pub/Sub with Cloud Trace OTLP export and
  Cloud Logging correlation. Don't use for querying existing traces (use
  cloud-trace-querying), Kafka or non-Google brokers, or orchestration engines
  such as Workflows or Managed Service for Apache Airflow.
---

# Event-driven decoupling with Pub/Sub

Break a distributed monolith or tightly coupled service chain apart with
asynchronous messaging on Pub/Sub so services scale and fail independently.
This skill uses **progressive disclosure** across **Phases 0–5** (with Phase 0
inline below and modular `references/` files for Phases 1–5): run the full
end-to-end migration sequence for architecture journeys, or load **only** the
single phase reference needed for a focused design, code, or troubleshooting
request.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Progressive disclosure: load only the phase you need

| Phase & module | Reference to load | Produces | Load when |
| --- | --- | --- | --- |
| **0. Frame the goal** | Inline in `SKILL.md` (see [End-to-end workflow and phase gates](#end-to-end-workflow-and-phase-gates)) | Business outcome, runtime/DB constraints, measurable acceptance criteria | Starting any end-to-end decoupling journey before design begins |
| **1. Assess** (Synchronous coupling assessment) | [Coupling assessment & transaction boundaries](references/phase1-coupling-assessment.md); plus [Go & SQL outbox, post-commit, and bulkheads](references/phase1-outbox-and-bulkheads-go.md) when authoring producer/outbox code | Measured baseline, call graph, transaction cut, outbox vs state-marker decision, event catalog, bulkhead plan | Auditing synchronous HTTP/gRPC/DB chains, Cloud Trace / Cloud SQL lock waits, dual writes, schema freezes, reference-lookup caching, or deciding what becomes an event |
| **2. Design messaging** (Pub/Sub topic and subscription design) | [Pub/Sub topology, flow-control sizing, DLQ, and claim-check](references/phase2-pubsub-topology-and-sizing.md) | Domain topics vs dedicated topics, subscription filters, dead-letter policy + service-agent IAM, backoff, DB-bounded flow control, 10 MB claim-check | Sizing `MaxOutstandingMessages`, ack deadlines, or retry delays; choosing filtered vs per-event topics; handling payloads near/above 1–10 MB; or fixing DLQ delivery |
| **3. Build consumers** (Event-driven workflow triggering) | [Consumer ack/nack matrix, SIGTERM drain, GKE HPA, and Cloud Run](references/phase3-consumer-and-autoscaling.md) | Idempotent Go dispatcher, sentinel-error ack/nack/quarantine matrix, single-deadline SIGTERM drain, GKE `autoscaling/v2` HPA, Cloud Run / Eventarc / Cloud Run functions (`--retry`) | Writing or reviewing consumer handlers, fixing rollout `context canceled` or duplicate bugs, scaling GKE on `num_undelivered_messages`, or configuring Cloud Run / Eventarc triggers |
| **4. Observe** (Distributed trace instrumentation) | [OpenTelemetry propagation, OTLP export, and Cloud Logging correlation](references/phase4-distributed-tracing.md) | `otelhttp`/`otelgrpc` wrapping, Pub/Sub built-in tracing or attribute carrier, `telemetry.googleapis.com:443` OTLP + Cloud Run sampler, `slog` correlation, `InMemoryExporter` tests | Propagating traces across Pub/Sub, instrumenting synchronous HTTP/gRPC-only services, fixing missing Cloud Run traces or unlinked `slog` logs, or **before Phase 1** when a service has no traces |
| **5. Cut over & validate** (Cut-over & acceptance) | [Solution checklist and hand-off template](references/solution-checklist.md) | Phase gate table, event catalog template, budget worksheet, observable acceptance checks | Defining measurable acceptance criteria, tracking phase hand-offs, executing Strangler dual-run cut-over, or validating post-cut-over gates |

**Routing rules**:

-   **End-to-end requests**: run Phases 0–5 sequentially, loading each phase's
    reference only when that phase begins. Two exceptions apply:
    -   *Greenfield consumers*: run Phases 3 and 4 together so new consumers
        ship with distributed tracing from day one.
    -   *Missing observability*: if the user's primary problem is missing
        latency visibility or absent distributed traces, run Phase 4
        ([references/phase4-distributed-tracing.md](references/phase4-distributed-tracing.md))
        first to establish a trace baseline before proposing Pub/Sub changes,
        then resume Phases 1–3.
-   **Focused single-phase requests**: load **only** the matching phase
    reference, name which phase file applies, and never dump unrelated phases:
    -   *Flow-control / subscription configuration questions*
        (`MaxOutstandingMessages`, ack deadline, `max-delivery-attempts`,
        backoff): load **only** Phase 2
        ([references/phase2-pubsub-topology-and-sizing.md](references/phase2-pubsub-topology-and-sizing.md)).
        Relate flow control to the database connection pool and ack deadline to
        the per-message processing timeout; do **not** present the Phase 1
        coupling matrix, Transactional Outbox, or Phase 3 consumer handler code.
    -   *Consumer handler ack/nack questions*: load **only** Phase 3
        ([references/phase3-consumer-and-autoscaling.md](references/phase3-consumer-and-autoscaling.md)).
        Provide the handler logic (never provisioning commands alone) and note
        that the subscription ack deadline must exceed the handler's processing
        timeout.
-   **Non-Go languages and other SQL engines**: Phases 1, 3, and 4 provide
    compiled Go (`cloud.google.com/go/pubsub/v2`, `database/sql`, OpenTelemetry
    Go) and PostgreSQL reference code, while Phase 2 maps flow-control fields
    across Go, Python, Java, and Node.js. When the user's workload uses another
    language (such as Java, Python, or Node.js) or database (such as MySQL or
    Oracle), keep every architectural invariant and phase gate unchanged,
    translate the patterns into idiomatic SDK and SQL constructs for the
    requested stack, and state explicitly that you are adapting the Go reference
    patterns.

## Prerequisites

Use the Google Cloud CLI (install guide:
https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) and, for GKE,
`kubectl`. Never install host tools or grant IAM bindings without explicit user
approval: both alter the user's host or production access. If `gcloud` is
unavailable, produce design artifacts, code, Kubernetes YAML, or Terraform
directly.

1.  **Billing** is attached to `{project_id}`. Pub/Sub, Cloud Trace, and Cloud
    Logging have free allotments, but an active billing account is still
    required (https://cloud.google.com/pricing,
    https://cloud.google.com/pubsub/pricing,
    https://cloud.google.com/run/pricing,
    https://cloud.google.com/kubernetes-engine/pricing,
    https://cloud.google.com/stackdriver/pricing).
2.  **Project, region, authentication, and APIs** (default `us-central1`,
    https://cloud.google.com/about/locations):

    ```bash
    gcloud config set project {project_id}
    gcloud config set compute/region {region}
    gcloud auth login                            # Local CLI
    gcloud auth application-default login        # SDK / ADC; workloads use Workload Identity Federation for GKE or GOOGLE_APPLICATION_CREDENTIALS
    gcloud services enable pubsub.googleapis.com cloudtrace.googleapis.com telemetry.googleapis.com logging.googleapis.com monitoring.googleapis.com
    # Add per workload: cloudprofiler.googleapis.com (Phase 1), storage.googleapis.com (claim-check),
    # container.googleapis.com (GKE, default), or run.googleapis.com eventarc.googleapis.com cloudfunctions.googleapis.com (Cloud Run)
    ```

3.  **Least-privilege IAM**: one service account per producer and consumer;
    never `roles/editor` (*why:* basic roles grant project-wide write across
    every service).

    | Principal | Role | Scope | Phase |
    | --- | --- | --- | --- |
    | Assessor identity (read-only) | `roles/cloudtrace.user`, `roles/monitoring.viewer`, `roles/cloudprofiler.user` | `{project_id}` | 1 |
    | Producer service account | `roles/pubsub.publisher` (`+ roles/storage.objectCreator` on `{claim_check_bucket}` if claim-check) | `{topic_id}` | 2 |
    | Consumer service account | `roles/pubsub.subscriber` (`+ roles/storage.objectViewer` on `{claim_check_bucket}` if claim-check) | `{subscription_id}` | 2–3 |
    | Pub/Sub service agent `service-{project_number}@gcp-sa-pubsub.iam.gserviceaccount.com` | `roles/pubsub.publisher` on `{dlq_topic_id}` **and** `roles/pubsub.subscriber` on `{subscription_id}` | dead-lettering | 2 |
    | Metrics adapter (`custom-metrics-stackdriver-adapter`) | `roles/monitoring.viewer` | `{project_id}` | 3 |
    | Push / Eventarc trigger service account (Cloud Run path) | `roles/run.invoker`, `roles/eventarc.eventReceiver` | service / trigger | 3 |
    | Producer and consumer service accounts | `roles/telemetry.tracesWriter`, `roles/logging.logWriter` | `{project_id}` | 4 |

## End-to-end workflow and phase gates

1.  **Phase 0 - Frame the goal**: capture the business outcome (independent
    scaling, isolated failure, shorter p99, removable batch windows) and
    constraints (schema freeze, language, runtime GKE vs Cloud Run, data
    residency) as measurable acceptance criteria before designing.
2.  **Phase 1 - Assess** ([phase1-coupling-assessment.md](references/phase1-coupling-assessment.md),
    [phase1-outbox-and-bulkheads-go.md](references/phase1-outbox-and-bulkheads-go.md)).
    **Gate**: baseline p99 latency, connection saturation, and lock-wait
    numbers recorded per hop; every outbound event has a name, owning team,
    idempotency key, and Transactional Outbox vs state-marker decision; zero
    network calls remain inside a database transaction. **Gate enforcement**:
    if the user claims assessment is finished and asks for `gcloud` topic or
    subscription creation commands while only naming events without confirming
    those Phase 1 gate items, **do not** emit `gcloud pubsub topics create` or
    `subscriptions create` commands and **do not** invent payload schemas or
    owners; ask to confirm the missing Phase 1 gate items first and state that
    Phase 2
    ([references/phase2-pubsub-topology-and-sizing.md](references/phase2-pubsub-topology-and-sizing.md))
    is the next step once the gate is met.
3.  **Phase 2 - Design messaging** ([phase2-pubsub-topology-and-sizing.md](references/phase2-pubsub-topology-and-sizing.md)).
    **Gate**: per-replica flow control derived from the database pool;
    dead-letter topic paired with its own pull subscription and both Pub/Sub
    service-agent IAM bindings; Cloud Storage claim-check decision for any
    payload that can exceed 1 MB (Pub/Sub hard limit: 10 MB).
4.  **Phase 3 - Build consumers** ([phase3-consumer-and-autoscaling.md](references/phase3-consumer-and-autoscaling.md)).
    **Gate**: unit tests for every branch of the ack/nack/quarantine matrix;
    shutdown test proving the database pool closes strictly after `Receive`
    returns and in-flight commits finish; GKE HPA `maxReplicas` or Cloud Run
    concurrency capped within the database connection budget.
5.  **Phase 4 - Observe** ([phase4-distributed-tracing.md](references/phase4-distributed-tracing.md)).
    **Gate**: one continuous trace ID from producer request through Pub/Sub to
    consumer database stages, structured logs correlated via
    `logging.googleapis.com/trace`, explicit sampling policy per environment.
6.  **Phase 5 - Cut over incrementally**: Strangler pattern per event type.
    Dual-run (synchronous path plus event) behind `{feature_flag}` so a single
    flip restores the synchronous call, compare outcomes, and remove the
    synchronous call only after `{dlq_subscription_id}` stays empty for
    `{soak_period}` (default: one full business cycle, at least 7 days).
7.  **Validate → fix → repeat**: re-verify all phase gates post-cut-over using
    [solution-checklist.md](references/solution-checklist.md).

## Cross-cutting rules and scope boundaries

-   **One default, one escape hatch per decision**: every phase names one
    default and one escape hatch; do not add a third option.
-   **Idempotency is non-negotiable**: Pub/Sub delivers at least once. Every
    consumer deduplicates on an event ID or natural key before side effects and
    **acks** duplicates (nacking duplicates loops valid data into the DLQ).
-   **Budgets flow downstream**: database connection budget → per-replica pool
    → `MaxOutstandingMessages` → HPA `maxReplicas`. Enforce the invariant
    `per_replica_pool * max_replicas <= database_connection_budget` (derive
    whichever of the three values is unknown, tie HPA `maxReplicas` to that
    budget, never leave client flow-control defaults of 1000 messages / 1 GiB
    in place, and derive per-replica flow control with Phase 2
    ([references/phase2-pubsub-topology-and-sizing.md](references/phase2-pubsub-topology-and-sizing.md))
    and the HPA manifest with Phase 3
    ([references/phase3-consumer-and-autoscaling.md](references/phase3-consumer-and-autoscaling.md))).
-   **Never leave a dead-letter topic without a subscription**: it silently
    discards messages; alert on `subscription/dead_letter_message_count`.
-   **Other brokers (Kafka, RabbitMQ, SQS, self-managed queues)**: state
    plainly that this skill is specific to Google Cloud Pub/Sub, offer only
    broker-agnostic principles explicitly labeled as such (or redirect to
    broker-specific docs), never present Pub/Sub flags, flow-control settings,
    or fabricated `gcloud` commands as Kafka config, and never suggest
    migrating to Pub/Sub as the answer to a Kafka tuning question.
-   **Synchronous HTTP/gRPC-only services (no Pub/Sub)**: load only Phase 4
    (`TracerProvider` + Cloud Run `WithRemoteParentNotSampled` sampler,
    `otelhttp`, `otelgrpc` stats handlers, DB stage spans, `slog` correlation);
    never introduce Pub/Sub topics or message carriers.
-   **Querying existing traces** (*"find traces slower than 2s"*): state that
    this is a Cloud Trace query task rather than instrumentation; point to the
    Cloud Trace console/API
    (https://docs.cloud.google.com/trace/docs/finding-traces.md.txt) or the
    `cloud-trace-querying` skill. Never emit OpenTelemetry SDK setup code,
    never require re-instrumenting first, and never invent a trace query DSL.
-   **Orchestration engines & sagas**: Workflows, Managed Service for Apache
    Airflow (`managed-airflow-*`), Application Integration
    (`application-integration-basics`), and multi-service compensating sagas
    are out of scope; keep each aggregate's state change in one transaction.

## Validation checklist

-   [ ] Producer and consumer deploy, scale, and fail independently: with the
    consumer stopped, producer p99 is unchanged, `num_undelivered_messages`
    grows, and the backlog drains on restart with matching row counts.
-   [ ] No dual writes: a fault injected between commit and publish is
    recovered by the outbox relay or sweeper with zero duplicate side effects.
-   [ ] A malformed message lands in `{dlq_subscription_id}` after
    `max-delivery-attempts` (or in quarantine when chosen) while healthy
    messages keep flowing (`subscription/dead_letter_message_count` > 0).
-   [ ] Rolling consumer restarts under load produce zero `context canceled`
    commits and zero duplicate side effects.
-   [ ] One trace ID links producer request, Pub/Sub hop, consumer processing,
    and database stages, with `logging.googleapis.com/trace` on log lines.
-   [ ] Every acceptance criterion names an observable signal (metric, log
    field, row count, or test assertion), never a qualitative claim like
    *"services are decoupled"*.

## Resource cleanup

Remove **only temporary test or dual-run resources** in a non-production
project. Before running or proposing any delete command after a migration,
explicitly ask the user to confirm the exact test resource names and
`{test_project_id}`, distinguish test/dual-run resources from live production
topics and subscriptions, and **never** delete production resources carrying
live traffic:

```bash
gcloud pubsub subscriptions delete {test_subscription_id} --project={test_project_id}
gcloud pubsub topics delete {test_topic_id} --project={test_project_id}
```
