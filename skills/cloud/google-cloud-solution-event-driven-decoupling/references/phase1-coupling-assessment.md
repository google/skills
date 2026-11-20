# Phase 1: Synchronous coupling assessment and transaction boundaries

- [1. Coupling diagnostic matrix](#1-coupling-diagnostic-matrix): Lines 19-30
- [2. Transaction boundary rules](#2-transaction-boundary-rules): Lines 31-66
- [3. Locate and measure chokepoints first](#3-locate-and-measure-chokepoints-first): Lines 67-88
- [4. Assessment workflow and Phase 1 checklist](#4-assessment-workflow-and-phase-1-checklist): Lines 89-137

Assess synchronous execution chains and draw transactional and failure-domain
boundaries **before** introducing asynchronous messaging. The output of Phase 1
is a decoupling design (measured baseline, call graph, transaction cut, outbox
or state-marker decision, event catalog, bulkhead plan) that Phase 2
(`references/phase2-pubsub-topology-and-sizing.md`) and Phase 3
(`references/phase3-consumer-and-autoscaling.md`) then implement.

Database diagnostics identity: use a database role scoped to the tables the
service owns plus the `pg_monitor` role for PostgreSQL lock/activity queries;
never use a shared admin login.

## 1. Coupling diagnostic matrix

Audit every hop of the synchronous request, batch loader, or stored-procedure
pipeline against four coupling dimensions:

| Coupling dimension | Symptom in code or architecture | Failure mode under load | Target decoupling pattern |
| --- | --- | --- | --- |
| **Temporal coupling** | Caller blocks until a downstream service, database job, or third-party API finishes. | Downstream slowness becomes upstream timeouts and cascading outages. | Durable asynchronous buffer (Pub/Sub topic with at-least-once delivery). |
| **Transactional dual write** | Code commits a database transaction and then publishes a message, or publishes inside the transaction. | Crash between commit and publish loses the event; rollback after publish emits a phantom event. | **Default:** Transactional Outbox table written in the same transaction. **Escape hatch:** post-commit idempotent publish plus a reconciliation sweeper. |
| **External reference coupling** | Hot-path transaction performs remote calls or unindexed cross-domain lookups per row. | Connection-pool exhaustion and long lock hold times. | **Default:** bounded TTL cache hydrated outside the transaction. **Escape hatch:** one batched `WHERE key IN (...)` read before the write transaction. |
| **Layer leakage** | Domain or use-case code imports messaging or database SDKs directly. | Business rules cannot be unit-tested without emulators. | Ports and adapters: domain depends on interfaces; SDKs live in adapters. |

## 2. Transaction boundary rules

Apply these rules when splitting a monolithic procedure into an atomic write
plus asynchronous events:

1.  **Never perform network calls (HTTP, gRPC, broker publish) inside an open
    database transaction.** *Why:* a network stall holds row locks and pins a
    pooled connection, creating lock convoys and exhausting the pool.
2.  **Keep the state transition of a single aggregate in one transaction.**
    *Why:* splitting invariant-bearing tables across several local
    transactions without a saga leaves partial writes when a step fails.
3.  **Resolve read-only reference data before opening the transaction.**
    *Why:* tax rates, reference attributes, or configuration change rarely;
    pre-fetching shrinks the transaction to pure DML. *Caveat:* if a
    reference value must be consistent with the write, store the value or
    its version in the row and validate it inside the transaction
    (optimistic check) instead of re-reading remotely.
4.  **Eliminate dual writes deterministically**:
    -   **Default (Transactional Outbox):** insert the domain event (payload
        **and** attributes such as `event_type` and `traceparent`) into an
        `outbox_events` table in the same transaction as the business tables,
        then relay it to Pub/Sub asynchronously with claim-then-publish so no
        lock is held during the publish.
    -   **Escape hatch (post-commit publish + reconciler):** when schema
        changes are frozen, persist a status column (for example
        `publish_status = 'PENDING'`) on the aggregate's existing root table
        inside the transaction, publish immediately after commit with a
        deterministic event ID (never failing the caller's request if the
        post-commit publish fails, because the business row is already
        committed), mark `PUBLISHED`, and run a periodic sweeper for stale
        `PENDING` rows.

See `references/phase1-outbox-and-bulkheads-go.md` for port definitions, a
tested Go Transactional Outbox repository and relay, the post-commit variant,
cache pre-fetch, bulkhead sizing, and PostgreSQL / MySQL DDL and sweeper SQL.

## 3. Locate and measure chokepoints first

Decouple what has been measured, not what feels slow. When a user asks which
steps of a slow endpoint to move to Pub/Sub without providing measurements,
**do not propose moving specific steps to Pub/Sub yet**; first ask for or
collect per-hop latency from Cloud Trace and a connection/lock signal from the
table below, and instruct them to record those baseline numbers in the design
document so the post-cut comparison is objective:

| Signal | Where | What it reveals |
| --- | --- | --- |
| Critical path and per-hop latency (p50/p99) | Cloud Trace: filter the entry span, sort by latency, open the waterfall (https://docs.cloud.google.com/trace/docs/finding-traces.md.txt) | Which downstream call dominates the request and whether it runs inside the transaction span |
| Fan-out count per request | Cloud Trace span counts per trace | N+1 lookups that belong in a batched pre-fetch |
| Request latency and instance count per revision (Cloud Run) | Cloud Monitoring: `run.googleapis.com/request_latencies`, `run.googleapis.com/container/instance_count` (https://docs.cloud.google.com/run/docs/monitoring.md.txt) | Whether latency grows with instance count (downstream-bound) or not (CPU-bound) |
| Connection-pool saturation | Cloud SQL for PostgreSQL: `cloudsql.googleapis.com/database/postgresql/num_backends` against the `max_connections` flag, and `num_backends_by_state` filtered to `state="idle_in_transaction"`; MySQL / SQL Server: `cloudsql.googleapis.com/database/network/connections`; otherwise the pool's own gauge (Go `sql.DB.Stats().WaitCount`) | Transactions left open while the application waits on something else, the symptom of locks held across network calls |
| Lock waits and long transactions | PostgreSQL: `SELECT pid, state, wait_event_type, wait_event, now() - xact_start AS tx_age, query FROM pg_stat_activity WHERE state = 'idle in transaction' OR cardinality(pg_blocking_pids(pid)) > 0;` plus Cloud SQL Query Insights lock-wait load (https://docs.cloud.google.com/sql/docs/postgres/using-query-insights.md.txt) | Which sessions hold locks while blocked, and on what |
| CPU hot spots inside the hop | Cloud Profiler (https://docs.cloud.google.com/profiler/docs/about-profiler.md.txt) | Whether the hop is slow because of compute or because of waiting |

If the service is not yet traced, apply Phase 4
(`references/phase4-distributed-tracing.md`) first; to query existing traces use
the `cloud-trace-querying` skill.

## 4. Assessment workflow and Phase 1 checklist

1.  **Trace the call graph**: list every synchronous hop from the entry
    adapter (HTTP handler, file loader, message consumer) through validation,
    reference lookups, writes, and outbound notifications. Record owner,
    measured latency, and failure behavior per hop (or outline a candidate call
    graph and ask the user to confirm missing hops when assessing conceptual
    domain boundaries).
2.  **Measure lock and connection residency**: using the signals above, flag
    every remote call, cross-schema join, or secondary process (for example a
    nightly rollup) executed while a transaction is open.
3.  **Draw the transaction cut**:
    -   Move read-only lookups **before** the transaction behind a read port
        with caching or batching.
    -   Keep atomic business writes plus the outbox row or state marker
        **inside** the transaction.
    -   Move notifications, analytics fan-out, and heavy rollups **after**
        commit as asynchronous events.
4.  **Isolate failure domains (bulkheads)**: give real-time and bulk/batch
    flows separate connection budgets, worker pools, or subscriptions so a
    batch spike never starves interactive traffic.
5.  **Name the events and owners**: for each post-commit step define (or, for
    conceptual flow assessments without a slow-endpoint incident, propose
    concrete candidate values for) the event name
    (`{domain}.{entity}.{past_tense_verb}`, for example
    `orders.order.created`), deterministic idempotency key (for example
    `order_id`), consumers, and `{owning_team}` placeholder.
6.  **Validate → fix → repeat**: verify every item below before proceeding to
    Phase 2 (`references/phase2-pubsub-topology-and-sizing.md`):
    -   [ ] No HTTP, gRPC, or Pub/Sub publish call executes between transaction
        begin and commit.
    -   [ ] Every outbound event is produced through a Transactional Outbox or
        an existing-table state marker with an idempotent sweeper.
    -   [ ] Read-only reference lookups use a bounded cache or a single batched
        pre-transaction query, not per-row queries inside the transaction.
    -   [ ] Domain and use-case packages depend only on interfaces (no
        messaging or database SDK imports).
    -   [ ] Real-time and batch flows have independent concurrency budgets.
    -   [ ] Each event has a documented name, idempotency key, and owning team.
    -   [ ] Baseline p99 latency, connection saturation, and lock-wait numbers
        are recorded for each hop that will be decoupled.

If prototype topics or subscriptions were created in a sandbox project during
assessment, delete only those sandbox resources after confirmation:

```bash
gcloud pubsub subscriptions delete {sandbox_subscription_id} --project={sandbox_project_id}
gcloud pubsub topics delete {sandbox_topic_id} --project={sandbox_project_id}
```
