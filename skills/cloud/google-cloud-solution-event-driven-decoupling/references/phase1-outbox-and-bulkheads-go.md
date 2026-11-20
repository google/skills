# Outbox, post-commit, and bulkhead patterns (Go reference)

- [1. Ports that keep the domain SDK-free](#1-ports-that-keep-the-domain-sdk-free): Lines 18-69
- [2. Default: Transactional Outbox in one transaction](#2-default-transactional-outbox-in-one-transaction): Lines 70-162
- [3. Outbox relay (poller)](#3-outbox-relay-poller): Lines 163-344
- [4. Escape hatch: post-commit publish with state marker](#4-escape-hatch-post-commit-publish-with-state-marker): Lines 345-427
- [5. Reference-data pre-fetch and bulkheads](#5-reference-data-pre-fetch-and-bulkheads): Lines 428-494
- [6. Schema and sweeper SQL](#6-schema-and-sweeper-sql): Lines 495-539
The Go blocks headed `// file:` are compiled and unit-tested by the authors
(`database/sql` + sqlmock, `go test -race`). The SQL is PostgreSQL 13+
(`ON CONFLICT`, `UPDATE ... RETURNING`, `FOR UPDATE SKIP LOCKED`, `JSONB`,
`make_interval`). For MySQL 8+ use `INSERT IGNORE`, split the claim into
`SELECT ... FOR UPDATE SKIP LOCKED` + `UPDATE`, and use `JSON`/`BLOB`/`?`
placeholders; other engines need their own `SKIP LOCKED` equivalent. Event
names follow `{domain}.{entity}.{past_tense_verb}`, for example
`orders.order.created`. Replace `LedgerEntry` with the real aggregate.

## 1. Ports that keep the domain SDK-free

Keep domain and use-case packages free of `cloud.google.com/go/pubsub/v2` and
database drivers. Only adapters import SDKs; pin them in `go.mod`
(`go get cloud.google.com/go/pubsub/v2@v2.8.0` or later).

The Pub/Sub adapter behind `EventPublisher` must block on the publish result:

```go
res := publisher.Publish(ctx, &pubsub.Message{Data: ev.Payload, Attributes: ev.Attributes, OrderingKey: orderingKey})
_, err := res.Get(ctx) // the client publishes asynchronously; return only after the broker acked
return err
```

```go
// file: outbox/port.go
package outbox

import "context"

// OutboundEvent is the integration event persisted next to the business
// write and relayed to Pub/Sub after commit.
type OutboundEvent struct {
	ID          string            // Deterministic idempotency key (for example a UUIDv5 of the aggregate ID + version).
	AggregateID string            // Business entity the event belongs to.
	Type        string            // Event name, e.g. "orders.order.created".
	Payload     []byte            // Serialized body (JSON, Avro, Protobuf).
	Attributes  map[string]string // Routing attributes (event_type, schema_version, traceparent).
}

// LedgerEntry is a minimal example aggregate; replace with the real domain type.
type LedgerEntry struct {
	ID          string
	AmountCents int64
	Status      string
}

// ReferenceDataReader resolves read-only reference data outside the write transaction.
type ReferenceDataReader interface {
	Resolve(ctx context.Context, codes []string) (map[string]string, error)
}

// TransactionStore persists the business record and the outbound event atomically.
type TransactionStore interface {
	SaveWithOutbox(ctx context.Context, entry *LedgerEntry, ev OutboundEvent) error
}

// EventPublisher emits events from a secondary adapter after commit.
type EventPublisher interface {
	Publish(ctx context.Context, ev OutboundEvent) error
}
```
## 2. Default: Transactional Outbox in one transaction

The business row and the outbox row commit or roll back together. The
`ON CONFLICT ... DO NOTHING` guard makes redelivered commands idempotent and
surfaces `ErrDuplicate` so the caller acknowledges the triggering message.

```go
// file: outbox/repository.go
package outbox

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
)

// ErrDuplicate is returned when the natural key already exists; callers ACK
// the triggering message instead of retrying.
var ErrDuplicate = errors.New("outbox: duplicate aggregate")

// Repository implements TransactionStore with the Transactional Outbox pattern.
// SQL is PostgreSQL (placeholders $1, ON CONFLICT, ::jsonb); see the reference for
// the MySQL adaptations.
type Repository struct {
	db *sql.DB
}

func NewRepository(db *sql.DB) *Repository { return &Repository{db: db} }

// aggregateID prefers the event's explicit AggregateID and falls back to the
// entry ID so there is a single source of truth for the business key.
func aggregateID(ev OutboundEvent, entry *LedgerEntry) string {
	if ev.AggregateID != "" {
		return ev.AggregateID
	}
	return entry.ID
}

// SaveWithOutbox writes the business row and the outbox row in ONE transaction.
// No network call happens between BeginTx and Commit.
func (r *Repository) SaveWithOutbox(ctx context.Context, entry *LedgerEntry, ev OutboundEvent) (err error) {
	tx, err := r.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback()
		}
	}()

	res, err := tx.ExecContext(ctx,
		`INSERT INTO ledger_entries (entry_id, amount_cents, status)
		 VALUES ($1, $2, $3)
		 ON CONFLICT (entry_id) DO NOTHING`,
		entry.ID, entry.AmountCents, entry.Status,
	)
	if err != nil {
		return fmt.Errorf("insert ledger entry: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		// Idempotent redelivery: the aggregate (and its outbox row) already exist.
		err = ErrDuplicate
		return err
	}

	// Attributes (event_type, schema_version, traceparent) travel with the row so
	// the relay can set them on the Pub/Sub message: subscription filters and
	// trace propagation only work through attributes.
	attrs, err := json.Marshal(ev.Attributes)
	if err != nil {
		return fmt.Errorf("encode attributes: %w", err)
	}
	if _, err = tx.ExecContext(ctx,
		`INSERT INTO outbox_events (event_id, aggregate_id, event_type, payload, attributes, status)
		 VALUES ($1, $2, $3, $4, $5::jsonb, 'PENDING')`,
		ev.ID, aggregateID(ev, entry), ev.Type, ev.Payload, string(attrs),
	); err != nil {
		return fmt.Errorf("insert outbox event: %w", err)
	}

	if err = tx.Commit(); err != nil {
		return fmt.Errorf("commit write+outbox: %w", err)
	}
	return nil
}
```
## 3. Outbox relay (poller)

A background relay (goroutine, sidecar, or Cloud Run job) **claims** a batch
in a short transaction (`PENDING` → `CLAIMED`, `FOR UPDATE SKIP LOCKED` so
replicas do not collide), commits, publishes each event with a bounded
timeout **outside** any transaction, and marks rows `PUBLISHED`. No row lock
is ever held across a network call. Rows left `CLAIMED` by a crash or
timeout are requeued by `ResetStaleClaims`; consumers deduplicate on
`event_id` because a republish is possible. Attributes persisted with the
row (`event_type`, `schema_version`, `traceparent`) are restored onto the
message so subscription filters and trace propagation keep working. Rows
that fail `maxAttempts` times are parked as `FAILED` so a poison event never
blocks its batch forever, and `PurgePublished` keeps the table bounded.

Ordering: with several relay replicas and `SKIP LOCKED`, two events of one
aggregate can be published out of order. If consumers need per-aggregate
order, set `OrderingKey = AggregateID` and run one relay replica (or claim
with `DISTINCT ON (aggregate_id)`); otherwise document that consumers must
tolerate reordering.

```go
// file: outbox/relay.go
package outbox

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
)

// Relay publishes outbox rows with a claim-then-publish protocol so no row
// lock is ever held across a network call:
//
//  1. short transaction: claim up to batchSize PENDING rows (status=CLAIMED,
//     FOR UPDATE SKIP LOCKED so replicas do not fight) and commit;
//  2. publish each claimed event with a bounded timeout, outside any
//     transaction;
//  3. mark each successfully published row PUBLISHED (autocommit).
//
// A crash or publish failure leaves rows CLAIMED; ResetStaleClaims returns them
// to PENDING (or parks them as FAILED after maxAttempts) so the next drain
// republishes them. Consumers therefore MAY see a duplicate and must
// deduplicate on event_id (at-least-once end to end). The outbox is a queue, not
// a ledger: PurgePublished deletes old PUBLISHED rows.
type Relay struct {
	db             *sql.DB
	publisher      EventPublisher
	batchSize      int
	publishTimeout time.Duration
	maxAttempts    int
}

// NewRelay builds a relay. batchSize defaults to 100, publishTimeout to 10s and
// maxAttempts to 10; rows that exceed maxAttempts are parked as FAILED so a
// poison event cannot block its batch forever.
func NewRelay(db *sql.DB, p EventPublisher, batchSize int, publishTimeout time.Duration) *Relay {
	if batchSize <= 0 {
		batchSize = 100
	}
	if publishTimeout <= 0 {
		publishTimeout = 10 * time.Second
	}
	return &Relay{db: db, publisher: p, batchSize: batchSize, publishTimeout: publishTimeout, maxAttempts: 10}
}

// WithMaxAttempts overrides the poison threshold (must be >= 1).
func (r *Relay) WithMaxAttempts(n int) *Relay {
	if n >= 1 {
		r.maxAttempts = n
	}
	return r
}

// DrainOnce claims and publishes one batch. It returns how many events were
// durably marked PUBLISHED, even when a later event in the batch failed.
func (r *Relay) DrainOnce(ctx context.Context) (published int, err error) {
	batch, err := r.claim(ctx)
	if err != nil {
		return 0, err
	}
	for _, ev := range batch {
		pubCtx, cancel := context.WithTimeout(ctx, r.publishTimeout)
		pubErr := r.publisher.Publish(pubCtx, ev)
		cancel()
		if pubErr != nil {
			// Row stays CLAIMED; ResetStaleClaims will requeue it.
			return published, fmt.Errorf("publish %s: %w", ev.ID, pubErr)
		}
		if _, err = r.db.ExecContext(ctx,
			`UPDATE outbox_events SET status = 'PUBLISHED', published_at = NOW() WHERE event_id = $1`,
			ev.ID); err != nil {
			return published, fmt.Errorf("mark published %s: %w", ev.ID, err)
		}
		published++
	}
	return published, nil
}

func (r *Relay) claim(ctx context.Context) (batch []OutboundEvent, err error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin claim tx: %w", err)
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback()
		}
	}()
	rows, err := tx.QueryContext(ctx,
		`UPDATE outbox_events
		    SET status = 'CLAIMED', claimed_at = NOW(), attempts = attempts + 1
		  WHERE event_id IN (
		        SELECT event_id FROM outbox_events
		         WHERE status = 'PENDING' AND attempts < $2
		         ORDER BY created_at
		         LIMIT $1
		         FOR UPDATE SKIP LOCKED)
		  RETURNING event_id, aggregate_id, event_type, payload, attributes`, r.batchSize, r.maxAttempts)
	if err != nil {
		return nil, fmt.Errorf("claim pending rows: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var ev OutboundEvent
		var attrs []byte
		if err = rows.Scan(&ev.ID, &ev.AggregateID, &ev.Type, &ev.Payload, &attrs); err != nil {
			return nil, fmt.Errorf("scan outbox row: %w", err)
		}
		if len(attrs) > 0 {
			if err = json.Unmarshal(attrs, &ev.Attributes); err != nil {
				return nil, fmt.Errorf("decode attributes for %s: %w", ev.ID, err)
			}
		}
		if ev.Attributes == nil {
			ev.Attributes = map[string]string{}
		}
		// Subscription filters only see attributes, so the event type MUST be
		// an attribute even if it is also inside the payload.
		ev.Attributes["event_type"] = ev.Type
		batch = append(batch, ev)
	}
	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate claimed rows: %w", err)
	}
	if err = tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit claim: %w", err)
	}
	return batch, nil
}

// ResetStaleClaims requeues rows claimed longer than olderThan ago (a relay
// crashed or a publish timed out) and parks rows that already reached
// maxAttempts as FAILED for manual inspection. Run it periodically alongside
// DrainOnce with olderThan > batchSize * publishTimeout.
func (r *Relay) ResetStaleClaims(ctx context.Context, olderThan time.Duration) (int64, error) {
	res, err := r.db.ExecContext(ctx,
		`UPDATE outbox_events
		    SET status = CASE WHEN attempts >= $2 THEN 'FAILED' ELSE 'PENDING' END,
		        claimed_at = NULL
		  WHERE status = 'CLAIMED' AND claimed_at < NOW() - make_interval(secs => $1)`,
		olderThan.Seconds(), r.maxAttempts)
	if err != nil {
		return 0, fmt.Errorf("reset stale claims: %w", err)
	}
	return res.RowsAffected()
}

// PurgePublished deletes PUBLISHED rows older than retention. Schedule it daily
// so the outbox table does not grow without bound.
func (r *Relay) PurgePublished(ctx context.Context, retention time.Duration) (int64, error) {
	res, err := r.db.ExecContext(ctx,
		`DELETE FROM outbox_events
		  WHERE status = 'PUBLISHED' AND published_at < NOW() - make_interval(secs => $1)`,
		retention.Seconds())
	if err != nil {
		return 0, fmt.Errorf("purge published: %w", err)
	}
	return res.RowsAffected()
}
```
## 4. Escape hatch: post-commit publish with state marker

When database governance forbids a new table, mark the existing header row
`publish_status = 'PENDING'` inside the transaction, publish right after
commit, and let a sweeper republish stale rows. The publish context is
detached from the caller's cancellation (`context.WithoutCancel`, Go 1.21+)
but bounded by `PublishTimeout`.

```go
// file: outbox/postcommit.go
package outbox

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"
)

// AtomicStore is the escape-hatch port: the write marks the row
// publish_status = 'PENDING' inside the transaction and returns the event to
// publish. On a duplicate natural key it must return the SAME deterministic
// event with ErrDuplicate so the caller can still publish idempotently.
type AtomicStore interface {
	SaveAtomic(ctx context.Context, entry *LedgerEntry, refs map[string]string) (OutboundEvent, error)
	// MarkPublished flips publish_status to PUBLISHED after a successful publish so
	// the sweeper does not republish the row.
	MarkPublished(ctx context.Context, eventID string) error
}

// PostCommitUseCase implements "post-commit publish + reconciler" when adding
// an outbox table is not possible.
type PostCommitUseCase struct {
	ReferenceData  ReferenceDataReader
	Store          AtomicStore
	Publisher      EventPublisher
	Logger         *slog.Logger
	PublishTimeout time.Duration
}

func (uc *PostCommitUseCase) Execute(ctx context.Context, entry *LedgerEntry, refCodes []string) error {
	publishTimeout := uc.PublishTimeout
	if publishTimeout <= 0 {
		publishTimeout = 10 * time.Second // a zero timeout would expire immediately and defer every publish
	}
	logger := uc.Logger
	if logger == nil {
		logger = slog.Default()
	}

	// Step 1: resolve read-only reference data BEFORE any write transaction.
	refs, err := uc.ReferenceData.Resolve(ctx, refCodes)
	if err != nil {
		return fmt.Errorf("resolve reference data: %w", err)
	}

	// Step 2: atomic write with a PENDING marker; zero network calls inside.
	ev, err := uc.Store.SaveAtomic(ctx, entry, refs)
	if err != nil && !errors.Is(err, ErrDuplicate) {
		return fmt.Errorf("save atomic: %w", err)
	}

	// Step 3: best-effort publish AFTER commit, detached from caller cancellation
	// so a shutdown mid-flight does not abort the publish, but bounded in time.
	pubCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), publishTimeout)
	defer cancel()
	if pubErr := uc.Publisher.Publish(pubCtx, ev); pubErr != nil {
		// Do NOT fail the request: the row is committed. The sweeper republishes
		// stale PENDING rows; the deterministic event ID keeps consumers idempotent.
		logger.WarnContext(ctx, "post-commit publish deferred to sweeper",
			"event_id", ev.ID, "error", pubErr)
		return nil
	}
	// Step 4: mark the row PUBLISHED. If this fails the row stays PENDING and the
	// sweeper republishes the same deterministic event; consumers deduplicate.
	if markErr := uc.Store.MarkPublished(pubCtx, ev.ID); markErr != nil {
		logger.WarnContext(ctx, "mark published failed; sweeper will reconcile",
			"event_id", ev.ID, "error", markErr)
	}
	return nil
}
```
## 5. Reference-data pre-fetch and bulkheads

1.  **Hybrid cache plus batch fallback**:
    -   Small, slow-changing tables (under ~10,000 rows: tax codes, regions,
        currencies) live in an in-memory snapshot refreshed by a background
        ticker (`atomic.Pointer[Snapshot]`).
    -   High-cardinality reference sets (millions of entity or account IDs)
        are resolved with one parameterized `WHERE id IN (...)` query per
        request, deduplicated, executed **before** the write transaction with a
        short read timeout.
2.  **Workload bulkheads**: give real-time and batch flows separate concurrency
    budgets whose sum stays below `db.SetMaxOpenConns`, so a burst of large
    batch files cannot starve interactive traffic or cause ack-deadline
    expirations.

```go
// file: outbox/bulkhead.go
package outbox

import "context"

// Bulkhead bounds concurrency for one workload class. Create one per class
// (for example realtime and batch) so a batch burst cannot consume the whole
// database pool. Size them so the sum stays below db.SetMaxOpenConns.
type Bulkhead struct{ slots chan struct{} }

func NewBulkhead(size int) *Bulkhead {
	if size < 1 {
		size = 1
	}
	return &Bulkhead{slots: make(chan struct{}, size)}
}

// Acquire blocks until a slot is free or ctx is done. Call the returned
// release function exactly once.
func (b *Bulkhead) Acquire(ctx context.Context) (release func(), err error) {
	select {
	case b.slots <- struct{}{}:
		return func() { <-b.slots }, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// SplitPool returns realtime and batch sizes for a pool of maxOpenConns,
// reserving realtimeShare (0..1) for interactive traffic. This split is a
// different knob from the "max outstanding messages <= 80% of the pool"
// flow-control rule; tune them independently.
func SplitPool(maxOpenConns int, realtimeShare float64) (realtime, batch int) {
	if maxOpenConns < 2 {
		return 1, 1
	}
	if realtimeShare <= 0 || realtimeShare >= 1 {
		realtimeShare = 0.8
	}
	realtime = int(float64(maxOpenConns) * realtimeShare)
	if realtime < 1 {
		realtime = 1
	}
	batch = maxOpenConns - realtime
	if batch < 1 {
		batch = 1
		realtime = maxOpenConns - 1
	}
	return realtime, batch
}
```
## 6. Schema and sweeper SQL

```sql
CREATE TABLE outbox_events (
  event_id      TEXT PRIMARY KEY,          -- deterministic idempotency key
  aggregate_id  TEXT        NOT NULL,
  event_type    TEXT        NOT NULL,      -- e.g. orders.order.created
  payload       BYTEA       NOT NULL,
  attributes    JSONB       NOT NULL DEFAULT '{}'::jsonb, -- event_type, schema_version, traceparent
  status        TEXT        NOT NULL DEFAULT 'PENDING',   -- PENDING | CLAIMED | PUBLISHED | FAILED
  attempts      INT         NOT NULL DEFAULT 0,           -- poison guard, see Relay.maxAttempts
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  claimed_at    TIMESTAMPTZ,
  published_at  TIMESTAMPTZ
);
CREATE INDEX outbox_events_pending_idx
  ON outbox_events (created_at) WHERE status = 'PENDING';
CREATE INDEX outbox_events_claimed_idx
  ON outbox_events (claimed_at) WHERE status = 'CLAIMED';
```

Schedule `ResetStaleClaims(ctx, window)` next to `DrainOnce` with
`window > batchSize * publishTimeout` (default 100 × 10 s, so lower
`batchSize` or raise the window) so an in-progress batch is never requeued by
a peer, and `PurgePublished(ctx, 7*24*time.Hour)` daily. Alert on rows in
`FAILED` and on `PENDING` rows older than the window.

Sweeper for the escape hatch (run every 1-5 minutes; claim, republish, mark):

```sql
SELECT aggregate_id, event_id
  FROM {aggregate_table}
 WHERE publish_status = 'PENDING'
   AND updated_at < NOW() - INTERVAL '2 minutes'
 ORDER BY updated_at
 LIMIT 500
   FOR UPDATE SKIP LOCKED;

-- after each successful publish:
UPDATE {aggregate_table} SET publish_status = 'PUBLISHED' WHERE aggregate_id = $1;
```

Keep `event_id` deterministic (for example
`uuid5(namespace, aggregate_id || version)`) so a sweeper republish after a
crash produces the same message the consumer already deduplicated.
