# Phase 2: Pub/Sub topic and subscription design

- [1. Client SDKs, DLQ, and claim-check IAM](#1-client-sdks-dlq-and-claim-check-iam): Lines 27-53
- [2. Topology and 10 MB payload decision matrix](#2-topology-and-10-mb-payload-decision-matrix): Lines 54-66
- [3. Subscription and flow-control sizing rules](#3-subscription-and-flow-control-sizing-rules): Lines 67-96
- [4. Go `ReceiveSettings` derived from the database pool](#4-go-receivesettings-derived-from-the-database-pool): Lines 97-232
- [5. Provisioning: dead-letter topic, filtered subscription, backoff, IAM](#5-provisioning-dead-letter-topic-filtered-subscription-backoff-iam): Lines 233-284
- [6. Cloud Storage claim-check for large payloads](#6-cloud-storage-claim-check-for-large-payloads): Lines 285-311
- [7. Monitoring metrics, Phase 2 checklist, and test cleanup](#7-monitoring-metrics-phase-2-checklist-and-test-cleanup): Lines 312-342

Grounding documentation:

-   Overview: https://docs.cloud.google.com/pubsub/docs/overview.md.txt
-   Pull subscriptions and flow control: https://docs.cloud.google.com/pubsub/docs/pull.md.txt
-   Dead-letter topics: https://docs.cloud.google.com/pubsub/docs/dead-letter-topics.md.txt
-   Subscription filters: https://docs.cloud.google.com/pubsub/docs/subscription-message-filter.md.txt
-   Pub/Sub quotas and limits (10 MB message size): https://docs.cloud.google.com/pubsub/quotas.md.txt

Architect topic topology, dead-letter handling, retry backoff, and consumer
flow control so bursts never starve the downstream database and poison
messages are never dropped silently. If the user claims an assessment is done
and asks for `gcloud` creation commands while only naming events, enforce the
Phase 1 gate first (idempotency key, owner, outbox or state-marker decision,
and measured baseline) and withhold topic or subscription creation commands
until that gate is met.

## 1. Client SDKs, DLQ, and claim-check IAM

Pin the client library: Go `go get cloud.google.com/go/pubsub/v2@latest`
(v2.x), Python `pip install "google-cloud-pubsub>=2,<3"`, Java
`com.google.cloud:google-cloud-pubsub` managed by
`com.google.cloud:libraries-bom:{bom_version}`, Node.js
`npm install @google-cloud/pubsub@latest`. Pub/Sub topics are global; region
matters only for locational endpoints (ordering, exactly-once). Enable
`pubsub.googleapis.com` (and `storage.googleapis.com` for claim-check). Flag
every IAM binding for human approval:

| Principal | Role | Scope |
| --- | --- | --- |
| Producer service account | `roles/pubsub.publisher` | `{topic_id}` |
| Producer service account (claim-check) | `roles/storage.objectCreator` | `{claim_check_bucket}` |
| Consumer service account | `roles/pubsub.subscriber` | `{subscription_id}` |
| Consumer service account (claim-check) | `roles/storage.objectViewer` | `{claim_check_bucket}` |
| Pub/Sub service agent `service-{project_number}@gcp-sa-pubsub.iam.gserviceaccount.com` | `roles/pubsub.publisher` | `{dlq_topic_id}` |
| Pub/Sub service agent `service-{project_number}@gcp-sa-pubsub.iam.gserviceaccount.com` | `roles/pubsub.subscriber` | `{subscription_id}` |
| Cloud Storage service agent `service-{project_number}@gs-project-accounts.iam.gserviceaccount.com` (claim-check) | `roles/pubsub.publisher` | `{batch_topic_id}` |

*Why the Pub/Sub service agent needs both roles:* without
`roles/pubsub.publisher` on `{dlq_topic_id}` **and** `roles/pubsub.subscriber`
on `{subscription_id}`, Pub/Sub cannot forward exhausted messages to the
dead-letter topic and keeps redelivering them forever until message retention
(default 7 days) expires and the message is lost.

## 2. Topology and 10 MB payload decision matrix

Pub/Sub enforces a **10 MB maximum message data size** (and 10 MB per publish
request; attributes are capped separately at 100 per message). Pick one
default per workload shape:

| Workload shape | Default | Escape hatch | Rationale |
| --- | --- | --- | --- |
| Related lifecycle events of one domain (`orders.order.created`, `orders.order.cancelled`) | One domain topic plus **subscription filters** (`--message-filter='attributes.event_type="orders.order.created"'`, or `hasPrefix(attributes.event_type, "orders.")`) | Dedicated topic per event when schemas, retention, or owning teams diverge, or when filters are expected to change (a filter is immutable after creation and limited to 256 bytes; changing it means recreating the subscription) | Filtering avoids delivering and nacking events a consumer never wanted; non-matching messages are acknowledged automatically. |
| Large files or documents (over ~1 MB, or variable 1:N batches) | **Claim-check**: upload to Cloud Storage, publish an `OBJECT_FINALIZE` notification or a small pointer message (bucket, object, generation) | Compressed or chunked direct messages only when well under the 10 MB limit (headroom for attributes and growth) and object storage is prohibited | Multi-megabyte messages exhaust the byte flow-control budget, cause out-of-memory kills, and fail above 10 MB. |
| Per-entity sequencing | **Idempotent consumer** tolerant of out-of-order delivery (version or natural-key check in the database); after the check, ack duplicates, since nacking them only causes more redelivery | **Ordering keys** (`ordering_key = "{entity_id}"`) with a regional endpoint; `--enable-message-ordering` cannot be changed after creation | Ordering serializes delivery per key, so one nacked or expired message redelivers every later outstanding message of that key until it is dead-lettered. |
| Exactly-once semantics required by the business | Idempotency key in the consumer's database (unique constraint) | Subscription `--enable-exactly-once-delivery` (pull/streaming pull only, same region; not available on push, BigQuery, or Cloud Storage subscriptions) | Database-level idempotency works for push, pull, and replays; exactly-once delivery still requires idempotent side effects. |

## 3. Subscription and flow-control sizing rules

Never leave client flow control at library defaults (Go: 1000 messages and
1 GB / `1e9` bytes; Python/Java/Node.js have similar large defaults) when the
consumer writes to a relational database:

| Parameter | Formula or default | Rationale |
| --- | --- | --- |
| Per-replica DB pool | `pool_max_open_conns = floor(total_db_connection_budget / max_replicas)` | Enforces `per_replica_pool * max_replicas <= database_connection_budget`. |
| Max outstanding messages (per replica) | `floor(pool_max_open_conns * 0.8)` (e.g. 25 for a pool of 32) | More in-flight callbacks than connections only queue inside the process, extend leases, and trigger duplicate redeliveries. |
| Max outstanding bytes (per replica) | `floor(container_memory_limit * 0.15)` (e.g. ~76 MiB on 512 MiB) | Prevents out-of-memory kills while draining a backlog of large payloads. |
| Client max lease extension (streaming pull) | `2 * per_message_timeout` (library defaults: 60 min) | Streaming-pull clients extend the lease automatically up to this cap; it, not the subscription ack deadline, is what must exceed the slowest legitimate commit. |
| Ack deadline (subscription) | `max(30s, ceil(2.5 * per_message_timeout))`, at most 600s (e.g. ~100s for a 40s timeout); set `per_message_timeout` at or above p99 processing time | Governs push and unary pull; slow commits beyond it are redelivered mid-flight. |
| Retry policy | `--min-retry-delay=10s --max-retry-delay=600s` (never use non-existent flags such as `--enable-delivery-ordering`) | Immediate retry (the default) creates thundering herds against a recovering database. |
| Dead-letter policy | `--max-delivery-attempts=5` (range 5–100) plus a pull subscription on `{dlq_topic_id}` with 7–31 days retention | Bounds poison amplification and keeps failed payloads inspectable. A dead-letter topic **without a subscription discards messages**. |

Client-library field names per language:

| Language | Max outstanding messages | Max outstanding bytes | Max lease extension |
| --- | --- | --- | --- |
| Go (`pubsub/v2`) | `sub.ReceiveSettings.MaxOutstandingMessages` | `sub.ReceiveSettings.MaxOutstandingBytes` | `ReceiveSettings.MaxExtension` |
| Python | `pubsub_v1.types.FlowControl(max_messages=...)` | `FlowControl(max_bytes=...)` | `FlowControl(max_lease_duration=...)` |
| Java | `FlowControlSettings.setMaxOutstandingElementCount` | `setMaxOutstandingRequestBytes` | `Subscriber.Builder.setMaxAckExtensionPeriod` |
| Node.js | `subscription.setOptions({flowControl: {maxMessages}})` | `flowControl: {maxBytes}` | `flowControl: {maxExtensionMinutes}` |

In Python and Java, flow control bounds leased messages only; size the
callback executor to the same budget (Python
`ThreadScheduler(ThreadPoolExecutor(max_workers={budget}))`, Java
`setExecutorProvider(FixedExecutorProvider.create(...))`).

## 4. Go `ReceiveSettings` derived from the database pool

The block headed `// file:` is compiled and unit-tested by the authors against
`cloud.google.com/go/pubsub/v2` v2.8.0 (`client.Subscriber(id)`; the v1
`client.Subscription(id)` API carries the same `ReceiveSettings` fields).

```go
// file: flowcontrol/receiver.go
package flowcontrol

import (
	"context"
	"fmt"
	"time"

	"cloud.google.com/go/pubsub/v2"
	"google.golang.org/api/option"
)

// ReceiverConfig derives Pub/Sub flow-control limits from the resources the
// consumer actually has: database connections and memory. Leaving the SDK
// defaults (1000 messages / 1 GB) in place while writing to a relational
// database lets 1000 callbacks compete for a few dozen connections.
type ReceiverConfig struct {
	ProjectID      string
	SubscriptionID string

	DBMaxOpenConns    int   // Per-replica database pool size (db.SetMaxOpenConns).
	MemoryLimitBytes  int64 // Per-replica container memory limit.
	PerMessageTimeout time.Duration

	// Optional explicit overrides; zero means "derive".
	MaxOutstandingMessages int
	MaxOutstandingBytes    int
	MaxExtension           time.Duration
	NumGoroutines          int
}

const (
	dbShareNumerator   = 4 // MaxOutstandingMessages <= 80% of the DB pool.
	dbShareDenominator = 5
	memorySharePercent = 15 // MaxOutstandingBytes <= 15% of container memory.
	fallbackMessages   = 20
	fallbackBytes      = 64 << 20
)

// Normalized returns a copy with every limit resolved and clamped.
func (c ReceiverConfig) Normalized() ReceiverConfig {
	out := c

	msgBudget := fallbackMessages
	if out.DBMaxOpenConns > 0 {
		if b := out.DBMaxOpenConns * dbShareNumerator / dbShareDenominator; b >= 1 {
			msgBudget = b
		} else {
			msgBudget = 1
		}
	}
	if out.MaxOutstandingMessages <= 0 || (out.DBMaxOpenConns > 0 && out.MaxOutstandingMessages > msgBudget) {
		out.MaxOutstandingMessages = msgBudget
	}

	byteBudget := fallbackBytes
	if out.MemoryLimitBytes > 0 {
		if b := int(out.MemoryLimitBytes * memorySharePercent / 100); b >= 1<<20 {
			byteBudget = b
		}
	}
	if out.MaxOutstandingBytes <= 0 || (out.MemoryLimitBytes > 0 && out.MaxOutstandingBytes > byteBudget) {
		out.MaxOutstandingBytes = byteBudget
	}

	if out.MaxExtension <= 0 {
		// Keep extending the ack deadline for as long as a message may legitimately
		// take, plus headroom, but never beyond the service maximum (600s is the
		// longest single ack deadline; MaxExtension caps total lease time).
		out.MaxExtension = 2 * time.Minute
		if out.PerMessageTimeout > 0 {
			out.MaxExtension = out.PerMessageTimeout * 2
		}
	}
	if out.NumGoroutines <= 0 {
		out.NumGoroutines = 4
	}
	return out
}

// NewTunedSubscriber builds a pubsub/v2 Subscriber with explicit flow control.
func NewTunedSubscriber(ctx context.Context, cfg ReceiverConfig, opts ...option.ClientOption) (*pubsub.Client, *pubsub.Subscriber, error) {
	n := cfg.Normalized()
	client, err := pubsub.NewClient(ctx, n.ProjectID, opts...)
	if err != nil {
		return nil, nil, fmt.Errorf("create pubsub client for project %q: %w", n.ProjectID, err)
	}
	sub := client.Subscriber(n.SubscriptionID)
	sub.ReceiveSettings.MaxOutstandingMessages = n.MaxOutstandingMessages
	sub.ReceiveSettings.MaxOutstandingBytes = n.MaxOutstandingBytes
	sub.ReceiveSettings.MaxExtension = n.MaxExtension
	sub.ReceiveSettings.NumGoroutines = n.NumGoroutines
	return client, sub, nil
}

// AckDeadlineFor returns the subscription ack deadline (seconds) to provision
// for a given per-message processing timeout: at least 30s, roughly 2.5x the
// timeout, capped at the Pub/Sub maximum of 600s.
func AckDeadlineFor(perMessageTimeout time.Duration) int {
	secs := int(perMessageTimeout.Seconds()*2.5 + 0.999)
	if secs < 30 {
		secs = 30
	}
	if secs > 600 {
		secs = 600
	}
	return secs
}
```
Wire it in `main`:

```go
client, sub, err := flowcontrol.NewTunedSubscriber(ctx, flowcontrol.ReceiverConfig{
	ProjectID:         projectID,
	SubscriptionID:    subscriptionID,
	DBMaxOpenConns:    32,            // same value passed to db.SetMaxOpenConns
	MemoryLimitBytes:  512 << 20,     // container limit
	PerMessageTimeout: 45 * time.Second,
})
if err != nil {
	return err
}
defer client.Close()
err = sub.Receive(ctx, func(ctx context.Context, m *pubsub.Message) { /* dispatcher.Handle */ })
```

Provision the subscription ack deadline with `AckDeadlineFor(PerMessageTimeout)`
(45s → 113s, rounded up to 120s below; the service maximum is 600s).

## 5. Provisioning: dead-letter topic, filtered subscription, backoff, IAM

Run only after confirming `{project_id}` and obtaining approval for IAM
bindings. Order matters: the dead-letter topic and its pull subscription must
exist before the main subscription references them.

```bash
PROJECT_NUMBER="$(gcloud projects describe "{project_id}" --format='value(projectNumber)')"
PUBSUB_SA="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

# 1. Dead-letter topic + durable pull subscription FIRST (a DLQ topic with no
#    subscription silently discards every dead-lettered message).
gcloud pubsub topics create "{dlq_topic_id}" --project="{project_id}"
gcloud pubsub subscriptions create "{dlq_subscription_id}" \
  --topic="{dlq_topic_id}" \
  --message-retention-duration=14d \
  --ack-deadline=60 \
  --project="{project_id}"

# 2. Main topic + subscription with backoff, dead-letter policy and attribute filter.
gcloud pubsub topics create "{topic_id}" --project="{project_id}"
gcloud pubsub subscriptions create "{subscription_id}" \
  --topic="{topic_id}" \
  --ack-deadline=120 \
  --min-retry-delay=10s \
  --max-retry-delay=600s \
  --dead-letter-topic="{dlq_topic_id}" \
  --max-delivery-attempts=5 \
  --message-filter='attributes.event_type="orders.order.created"' \
  --project="{project_id}"
# Add --enable-message-ordering only when the escape hatch (ordering keys) is chosen.

# 3. Grant the Pub/Sub service agent the two roles that make dead-lettering work.
gcloud pubsub topics add-iam-policy-binding "{dlq_topic_id}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/pubsub.publisher" \
  --project="{project_id}"
gcloud pubsub subscriptions add-iam-policy-binding "{subscription_id}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/pubsub.subscriber" \
  --project="{project_id}"

# 4. Verify the policy took effect.
gcloud pubsub subscriptions describe "{subscription_id}" \
  --project="{project_id}" \
  --format='yaml(deadLetterPolicy,retryPolicy,ackDeadlineSeconds,filter)'
```

Equivalent Terraform resource names: `google_pubsub_topic`,
`google_pubsub_subscription` (`dead_letter_policy`, `retry_policy`, `filter`),
`google_pubsub_topic_iam_member`, `google_pubsub_subscription_iam_member`.

## 6. Cloud Storage claim-check for large payloads

For files or documents whose size can exceed ~1 MB (or approaches the **10 MB
Pub/Sub hard limit**):

1.  **Upload the payload** to `gs://{claim_check_bucket}/incoming/{date}/{batch_id}`.
2.  **Publish a notification** automatically from the bucket (without
    `--skip-topic-setup` this also creates the topic if missing and grants
    `roles/pubsub.publisher` to the Cloud Storage service agent; obtain
    approval first or pass `--skip-topic-setup`):

    ```bash
    gcloud storage buckets notifications create "gs://{claim_check_bucket}" \
      --topic="projects/{project_id}/topics/{batch_topic_id}" \
      --event-types=OBJECT_FINALIZE \
      --object-prefix="incoming/" \
      --payload-format=json
    ```

3.  **Stream in the consumer**: read `bucketId` and `objectId` from the
    message attributes, open the object with the Cloud Storage client, and
    parse it as a stream (`json.Decoder`, `xml.Decoder`, CSV reader) instead
    of loading the entire object into memory. Grant the consumer identity
    `roles/storage.objectViewer` on the bucket.
4.  **Lifecycle**: add an object lifecycle rule (for example delete after 30
    days) so `{claim_check_bucket}` does not grow unbounded.

## 7. Monitoring metrics, Phase 2 checklist, and test cleanup

| Metric (`pubsub.googleapis.com/`) | Alert when | Meaning |
| --- | --- | --- |
| `subscription/num_undelivered_messages` | sustained growth over 10 min | Consumers cannot keep up; scale out or fix downstream. |
| `subscription/oldest_unacked_message_age` | > ack deadline × 3 | Messages are being redelivered or stuck. |
| `subscription/dead_letter_message_count` | > 0 | Poison messages reached the DLQ; inspect `{dlq_subscription_id}`. |
| `subscription/expired_ack_deadlines_count` | > 0 sustained for 5 min | Processing time exceeds the lease or ack deadline, or flow control is too high. |

Phase 2 checklist:

-   [ ] Flow control is set explicitly in code (never the library default).
-   [ ] `max_outstanding_messages * max_replicas <= database_connection_budget`.
-   [ ] Per-message processing timeout < client max lease extension
    (streaming pull) and < subscription ack deadline (push).
-   [ ] Dead-letter topic has a pull subscription **and** the Pub/Sub service
    agent holds `roles/pubsub.publisher` on `{dlq_topic_id}` and
    `roles/pubsub.subscriber` on `{subscription_id}`.
-   [ ] Payloads that can exceed 1 MB use Cloud Storage claim-check pointers.
-   [ ] Every `gcloud` flag used exists in the current CLI (verify with
    `gcloud pubsub subscriptions create --help`).

Test-only cleanup (non-production projects only, after user confirmation; list
any claim-check test prefix before deleting):

```bash
gcloud pubsub subscriptions delete {test_subscription_id} {test_dlq_subscription_id} --project={test_project_id}
gcloud pubsub topics delete {test_topic_id} {test_dlq_topic_id} --project={test_project_id}
gcloud storage ls "gs://{claim_check_bucket}/incoming/{test_prefix}/**"
gcloud storage rm --recursive "gs://{claim_check_bucket}/incoming/{test_prefix}/**"
```
