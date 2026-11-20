# Solution checklist and hand-off template

Copy this table into the project runbook and update it at each phase gate.

| Phase | Owner | Artifacts left behind | Gate status |
| --- | --- | --- | --- |
| 0. Frame | Architect | Acceptance criteria, constraints (runtime, language, schema freeze, residency) | open / passed |
| 1. Assess | Architect + service team | Measured baseline (p99 per hop, pool saturation, lock waits), call graph, transaction cut, event catalog (`name`, `owner`, `idempotency_key`, `payload_owner`), outbox vs state-marker decision, bulkhead plan | open / passed |
| 2. Design messaging | Platform team | Topic and subscription inventory, filters, dead-letter policy, flow-control budgets per replica, claim-check decision, IAM matrix | open / passed |
| 3. Build consumers | Service team | Handler with ack/nack matrix tests, shutdown test (pool closes after `Receive` returns), HPA or Cloud Run settings, load-test evidence | open / passed |
| 4. Observe | Service team + SRE | Trace continuity test, log correlation sample, sampling policy per environment, dashboards for backlog and dead-letter count | open / passed |
| 5. Cut over | Service team | Dual-run comparison report, `{feature_flag}` removal change, `{soak_period}` dead-letter evidence | open / passed |

## Event catalog template (illustrative values)

| Event name | Producer | Consumers | Idempotency key | Payload size p99 | Delivery strategy | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| `orders.order.created` | `{producer_service}` | `{consumer_a}`, `{consumer_b}` | `order_id` + `version` | `{p99_bytes}` | inline, filtered subscription | `{owning_team}` |
| `files.batch.finalized` | `{upload_service}` | `{importer_service}` | `object_generation` | `{p99_bytes}` (over 1 MB) | Cloud Storage claim-check | `{owning_team}` |

## Budget worksheet

Derive every number with Phase 2
(`references/phase2-pubsub-topology-and-sizing.md`, section 3 flow-control
sizing table) and Phase 3 (`references/phase3-consumer-and-autoscaling.md`,
section 6 HPA manifest); record the results as Phase 2 and Phase 3 artifacts.
Invariant at this level:
`per_replica_pool * max_replicas <= database_connection_budget`.

| Input | Value | Derived by |
| --- | --- | --- |
| Database connection budget for consumers | `{total_conns}` | you |
| Max consumer replicas | `{max_replicas}` | you, or derived from the two others |
| Per-replica pool (Go: `SetMaxOpenConns`) | `{pool}` | Phase 2 (`references/phase2-pubsub-topology-and-sizing.md`) |
| Max outstanding messages, bytes, lease cap, ack deadline | | Phase 2 (`references/phase2-pubsub-topology-and-sizing.md`) |
| HPA `averageValue`, `maxReplicas` | | Phase 3 (`references/phase3-consumer-and-autoscaling.md`) |

## How to run each validation check

1.  **Independent failure**: stop the consumer during a burst; read producer
    p99 from Cloud Trace or `run.googleapis.com/request_latencies`; watch
    `pubsub.googleapis.com/subscription/num_undelivered_messages` grow; after
    restart, compare row counts between the old and new paths.
2.  **No dual writes**: inject a failure in the relay between commit and
    publish; the event appears after the relay or sweeper runs; downstream
    row counts show no duplicate side effect.
3.  **Poison handling**: publish a malformed payload; it reaches the
    dead-letter subscription after the configured attempts
    (`subscription/dead_letter_message_count` > 0); healthy messages keep
    flowing.
4.  **Rolling restart under load**: zero cancelled-context errors (Go:
    `context canceled`) in commit paths; zero duplicate side effects (duplicate
    key rejections logged, no extra rows downstream).
5.  **Trace continuity**: pick ten producer requests; each has one trace
    through the consumer with correlated log lines
    (`logging.googleapis.com/trace`).
