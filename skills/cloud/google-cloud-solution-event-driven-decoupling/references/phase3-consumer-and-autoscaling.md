# Phase 3: Event-driven workflow triggering, SIGTERM drain, and autoscaling

- [1. Runtime selection and IAM](#1-runtime-selection-and-iam): Lines 27-47
- [2. Deterministic ack, nack, and quarantine matrix and shutdown rules](#2-deterministic-ack-nack-and-quarantine-matrix-and-shutdown-rules): Lines 48-88
- [3. Go dispatcher with the ack/nack/quarantine matrix](#3-go-dispatcher-with-the-acknackquarantine-matrix): Lines 89-235
- [4. Ordered startup and SIGTERM drain](#4-ordered-startup-and-sigterm-drain): Lines 236-337
- [5. Pub/Sub adapter wiring](#5-pubsub-adapter-wiring): Lines 338-383
- [6. GKE HorizontalPodAutoscaler on Pub/Sub backlog](#6-gke-horizontalpodautoscaler-on-pubsub-backlog): Lines 384-453
- [7. Escape hatch: Cloud Run push, Eventarc, and Cloud Run functions](#7-escape-hatch-cloud-run-push-eventarc-and-cloud-run-functions): Lines 454-523
- [8. Phase 3 checklist and test cleanup](#8-phase-3-checklist-and-test-cleanup): Lines 524-549

Grounding documentation:

-   Autoscaling on Pub/Sub metrics (GKE): https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/autoscaling-metrics.md.txt
-   Scale to zero on GKE using KEDA: https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/scale-to-zero-using-keda.md.txt
-   Pub/Sub push subscriptions: https://docs.cloud.google.com/pubsub/docs/push.md.txt
-   Eventarc overview: https://docs.cloud.google.com/eventarc/docs/overview.md.txt
-   Cloud Run + Pub/Sub tutorial: https://docs.cloud.google.com/run/docs/tutorials/pubsub.md.txt
-   Cloud Run functions retry semantics: https://docs.cloud.google.com/functions/docs/bestpractices/retries.md.txt

Trigger domain workflows from asynchronous events reliably: every delivery ends
in a deterministic ack, nack, or quarantine; a rollout never aborts an
in-flight transaction; and replicas scale with backlog within the database
connection budget. The Go blocks headed `// file:` in sections 3–4 are compiled
and unit-tested (`go test -race`, standard library Go 1.21+).

## 1. Runtime selection and IAM

Enable `pubsub.googleapis.com` and `monitoring.googleapis.com` plus
`container.googleapis.com` (GKE) or `run.googleapis.com` and
`eventarc.googleapis.com` (and `cloudfunctions.googleapis.com`,
`cloudbuild.googleapis.com`, and `artifactregistry.googleapis.com` for Cloud Run
functions). Request approval before granting IAM bindings:

| Principal | Role | Purpose |
| --- | --- | --- |
| GKE consumer (Workload Identity Federation for GKE) | `roles/pubsub.subscriber` on `{subscription_id}` | Streaming pull |
| Consumer that republishes downstream events | `roles/pubsub.publisher` on the outbound topic | Outbound events |
| Metrics adapter service account (`custom-metrics-stackdriver-adapter`) | `roles/monitoring.viewer` on `{project_id}` | HPA external metrics |
| Cloud Run push / Eventarc trigger service account | `roles/run.invoker` on the service; `roles/eventarc.eventReceiver` for Eventarc | Authenticated push |
| Pub/Sub service agent (projects created before 2021-04-08 only) | `roles/iam.serviceAccountTokenCreator` | Mint push auth tokens |

| Option | Choose when | Delivery and scaling |
| --- | --- | --- |
| **Default: GKE + streaming pull** | Sustained throughput, long-lived database pools, processing longer than the 600 s push ack deadline, strict drain control | Long-lived gRPC stream; HPA `autoscaling/v2` on `pubsub.googleapis.com\|subscription\|num_undelivered_messages` |
| **Escape hatch: Cloud Run** (service via push/Eventarc, or a Cloud Run function for a single short handler) | Bursty or sporadic traffic, scale-to-zero, stateless work under the 600 s push ack deadline; teams already on Cloud Run start here | Authenticated HTTPS POST; `2xx` (`102/200/201/202/204`) = ack, anything else = nack with backoff; Cloud Run scales on request concurrency. A Cloud Run function **must** be deployed with `--retry`: by default a failed invocation is acked and the event is **dropped**. |

## 2. Deterministic ack, nack, and quarantine matrix and shutdown rules

Pub/Sub guarantees **at-least-once** delivery: duplicates and reordering are
normal. Classify every outcome with sentinel errors and `errors.Is` (or the
language equivalent), never by matching error strings. Note that the
subscription ack deadline (configured in Phase 2,
`references/phase2-pubsub-topology-and-sizing.md`) must exceed the handler's
`PerMessageTimeout`.

| Outcome | Pull action | Push HTTP status | Rationale |
| --- | --- | --- | --- |
| Success | `Ack` | `204` (any of `102/200/201/202/204`) | State committed. |
| Idempotent duplicate (natural key already processed) | **`Ack`** | `204` | Nacking a duplicate loops to the dead-letter topic with valid data and pollutes the DLQ. |
| Permanent error (malformed payload, contract violation, unroutable type) | **Default:** `Nack` when the subscription has a dead-letter policy, so the message reaches the DLQ after `max-delivery-attempts`. **Escape hatch:** persist to a quarantine store then `Ack` when the business needs an audit trail. **No DLQ:** `Ack` and alert. | `503` with a DLQ; `204` + alert without | Without `max-delivery-attempts` a poison message retries until retention expires and starves the backlog. |
| Transient error (database timeout, deadlock, connection reset, dependency 5xx) | `Nack` | `503` (or `429`) | Triggers the subscription's exponential backoff until the dependency recovers. |

Routing and graceful shutdown rules:

1.  **Attribute-first routing**: dispatch on `attributes["event_type"]` (fall
    back to an envelope header) to a typed use case per event, so one
    subscription can serve several workflows without parsing every payload.
2.  **Idempotency at the persistence boundary**: deduplicate on the event ID
    or business natural key with a unique constraint or atomic upsert before
    side effects.
3.  **Shutdown sequence on SIGTERM** (GKE streaming pull; Cloud Run push
    instances get a fixed 10 s before SIGKILL, so keep push cleanup under 10 s
    and rely on the request timeout for in-flight work):
    1.  Cancel **only** the receive context; streaming pull stops fetching and
        waits for in-flight callbacks.
    2.  Give in-flight work a detached, bounded context
        (`context.WithoutCancel` + timeout) so commits finish without
        `context canceled` errors.
    3.  Wait for `Receive` to return (every callback acked or nacked).
    4.  Stop publishers, flush telemetry, then close the database **strictly
        last**. *Why:* closing the pool before `Receive` returns forces
        mid-transaction rollbacks and duplicate redeliveries on every rollout.
    5.  Order the budgets as a chain:
        `PerMessageTimeout <= DrainTimeout < terminationGracePeriodSeconds`
        (specifically `terminationGracePeriodSeconds >= DrainTimeout + 5s`),
        sharing one single `DrainTimeout` deadline across steps 1–4.

## 3. Go dispatcher with the ack/nack/quarantine matrix

```go
// file: dispatcher/dispatcher.go
package dispatcher

import (
	"context"
	"errors"
	"log/slog"
	"time"
)

// Sentinel errors returned by workflows so the dispatcher can classify the
// outcome with errors.Is (never by string matching).
var (
	ErrDuplicateEvent = errors.New("duplicate event already processed")
	ErrInvalidPayload = errors.New("permanent payload or contract error")
)

// Outcome is the decision taken for one message. Tests assert on it; the
// Pub/Sub adapter maps it to msg.Ack() / msg.Nack() or to HTTP status codes.
type Outcome int

const (
	OutcomeAck Outcome = iota
	OutcomeNack
)

// InboundMessage abstracts *pubsub.Message so the dispatcher is unit-testable.
type InboundMessage interface {
	ID() string
	Data() []byte
	Attributes() map[string]string
	Ack()
	Nack()
}

// WorkflowFunc executes one business workflow for an event.
type WorkflowFunc func(ctx context.Context, data []byte, attrs map[string]string) error

// Dispatcher routes events by the "event_type" attribute and applies the
// deterministic ACK/NACK matrix.
type Dispatcher struct {
	Routes            map[string]WorkflowFunc
	DefaultRoute      WorkflowFunc // optional catch-all
	PerMessageTimeout time.Duration
	HasDeadLetter     bool // subscription has a dead-letter policy
	Quarantine        func(ctx context.Context, msg InboundMessage, cause error) error
	Logger            *slog.Logger
	EventTypeAttr     string // defaults to "event_type"
}

const defaultPerMessageTimeout = 30 * time.Second

// Handle processes one message and returns the decision for observability.
func (d *Dispatcher) Handle(receiveCtx context.Context, msg InboundMessage) Outcome {
	if msg == nil {
		return OutcomeAck
	}
	// Handle runs concurrently from Receive callbacks, so it never writes to d:
	// defaults are resolved into locals.
	attrKey, timeout, logger := d.effective()
	// Detach from receiveCtx so an in-flight commit finishes during SIGTERM
	// drain, while enforcing a per-message deadline shorter than the lease cap.
	workCtx, cancel := context.WithTimeout(context.WithoutCancel(receiveCtx), timeout)
	defer cancel()

	attrs := msg.Attributes()
	eventType := attrs[attrKey]
	route, ok := d.Routes[eventType]
	if !ok {
		route = d.DefaultRoute
	}
	if route == nil {
		return d.permanentFailure(workCtx, logger, msg, eventType, errors.New("unroutable event type"))
	}

	err := route(workCtx, msg.Data(), attrs)
	switch {
	case err == nil:
		msg.Ack()
		return OutcomeAck
	case errors.Is(err, ErrDuplicateEvent):
		// Never Nack an already-processed key: it loops to the DLQ with valid data.
		logger.InfoContext(workCtx, "duplicate event acknowledged", "msg_id", msg.ID(), "event_type", eventType)
		msg.Ack()
		return OutcomeAck
	case errors.Is(err, ErrInvalidPayload):
		return d.permanentFailure(workCtx, logger, msg, eventType, err)
	default:
		// Transient: database timeout, deadlock, connection reset -> retry with backoff.
		logger.ErrorContext(workCtx, "transient workflow error, nacking", "msg_id", msg.ID(), "event_type", eventType, "error", err)
		msg.Nack()
		return OutcomeNack
	}
}

// effective returns the configuration with defaults applied, without mutating d.
func (d *Dispatcher) effective() (attrKey string, timeout time.Duration, logger *slog.Logger) {
	attrKey, timeout, logger = d.EventTypeAttr, d.PerMessageTimeout, d.Logger
	if attrKey == "" {
		attrKey = "event_type"
	}
	if timeout <= 0 {
		timeout = defaultPerMessageTimeout // zero would expire every message instantly
	}
	if logger == nil {
		logger = slog.Default()
	}
	return attrKey, timeout, logger
}

// permanentFailure implements the permanent-error rule. Default: Nack so the
// dead-letter policy moves the message to the DLQ after max-delivery-attempts.
// Escape hatch: when a Quarantine store is configured (business needs an audit
// trail), persist there and Ack. Without a dead-letter policy, Ack and alert:
// a Nack would retry forever and starve the backlog.
func (d *Dispatcher) permanentFailure(ctx context.Context, logger *slog.Logger, msg InboundMessage, eventType string, cause error) Outcome {
	if d.Quarantine != nil {
		if qErr := d.Quarantine(ctx, msg, cause); qErr == nil {
			logger.WarnContext(ctx, "permanent error quarantined", "msg_id", msg.ID(), "event_type", eventType, "error", cause)
			msg.Ack()
			return OutcomeAck
		}
		// Quarantine store unavailable: fall through to the DLQ decision.
	}
	if d.HasDeadLetter {
		logger.WarnContext(ctx, "permanent error, nacking toward dead-letter topic", "msg_id", msg.ID(), "event_type", eventType, "error", cause)
		msg.Nack()
		return OutcomeNack
	}
	logger.ErrorContext(ctx, "permanent error on subscription WITHOUT dead-letter policy; acking to avoid poison loop", "msg_id", msg.ID(), "event_type", eventType, "error", cause)
	msg.Ack()
	return OutcomeAck
}

// HTTPStatusFor maps an outcome to the status a Pub/Sub push or Eventarc
// handler must return (2xx = ack, 429/5xx = nack with backoff).
func HTTPStatusFor(o Outcome) int {
	if o == OutcomeAck {
		return 204
	}
	return 503
}
```

## 4. Ordered startup and SIGTERM drain

```go
// file: dispatcher/shutdown.go
package dispatcher

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// Receiver is the subset of *pubsub.Subscriber the lifecycle needs.
type Receiver interface {
	Receive(ctx context.Context, f func(context.Context, InboundMessage)) error
}

// Lifecycle orders startup and shutdown so no in-flight transaction is cut.
// Shutdown sequence (SIGTERM):
//  1. cancel receiveCtx  -> Receive stops pulling, waits for in-flight callbacks
//  2. <-receiveDone      -> every callback has called Ack or Nack
//  3. StopPublishers()   -> flush outbound events
//  4. FlushTelemetry()   -> export remaining spans
//  5. CloseDB()          -> strictly last
//
// Steps 1-4 share ONE deadline of DrainTimeout measured from SIGTERM, so set
// DrainTimeout >= per-message timeout and terminationGracePeriodSeconds >=
// DrainTimeout + 5s.
type Lifecycle struct {
	Receiver       Receiver
	Handler        func(ctx context.Context, msg InboundMessage)
	StopPublishers func(ctx context.Context) error
	FlushTelemetry func(ctx context.Context) error
	CloseDB        func() error
	DrainTimeout   time.Duration // < terminationGracePeriodSeconds - 5s

	// Trace records the order of shutdown steps; tests assert on it.
	Trace []string
}

const defaultDrainTimeout = 25 * time.Second

// Run blocks until sigCtx is cancelled (SIGTERM/SIGINT) or Receive fails.
func (l *Lifecycle) Run(sigCtx context.Context) error {
	if l.DrainTimeout <= 0 {
		l.DrainTimeout = defaultDrainTimeout
	}
	receiveCtx, cancelReceive := context.WithCancel(context.Background())
	defer cancelReceive()

	receiveDone := make(chan error, 1)
	go func() { receiveDone <- l.Receiver.Receive(receiveCtx, l.Handler) }()

	// One deadline for the WHOLE shutdown (drain + publishers + telemetry + DB):
	// two consecutive DrainTimeout windows would exceed terminationGracePeriodSeconds.
	var deadline time.Time
	var receiveErr error
	select {
	case <-sigCtx.Done():
		l.Trace = append(l.Trace, "cancel_receive")
		deadline = time.Now().Add(l.DrainTimeout)
		cancelReceive()
		drainCtx, cancel := context.WithDeadline(context.Background(), deadline)
		defer cancel()
		select {
		case receiveErr = <-receiveDone:
			l.Trace = append(l.Trace, "receive_returned")
		case <-drainCtx.Done():
			// Last resort: callbacks are still running and the DB will be closed
			// underneath them. Size DrainTimeout so this only happens when the
			// orchestrator is about to SIGKILL the process anyway.
			l.Trace = append(l.Trace, "drain_timeout")
			receiveErr = fmt.Errorf("drain timeout after %s: %w", l.DrainTimeout, drainCtx.Err())
		}
	case receiveErr = <-receiveDone:
		l.Trace = append(l.Trace, "receive_returned")
		deadline = time.Now().Add(l.DrainTimeout)
	}

	shutdownCtx, cancel := context.WithDeadline(context.Background(), deadline)
	defer cancel()
	var errs []error
	if l.StopPublishers != nil {
		l.Trace = append(l.Trace, "stop_publishers")
		errs = append(errs, l.StopPublishers(shutdownCtx))
	}
	if l.FlushTelemetry != nil {
		l.Trace = append(l.Trace, "flush_telemetry")
		errs = append(errs, l.FlushTelemetry(shutdownCtx))
	}
	if l.CloseDB != nil {
		l.Trace = append(l.Trace, "close_db")
		errs = append(errs, l.CloseDB())
	}
	if receiveErr != nil && !errors.Is(receiveErr, context.Canceled) {
		errs = append(errs, receiveErr)
	}
	return errors.Join(errs...)
}
```

## 5. Pub/Sub adapter wiring

Adapt `*pubsub.Message` (from `cloud.google.com/go/pubsub/v2`, `go get
cloud.google.com/go/pubsub/v2@v2.8.0` or later) to `InboundMessage` and run the
lifecycle from `main`:

```go
type pubsubMessage struct{ m *pubsub.Message }

func (p pubsubMessage) ID() string                    { return p.m.ID }
func (p pubsubMessage) Data() []byte                  { return p.m.Data }
func (p pubsubMessage) Attributes() map[string]string { return p.m.Attributes }
func (p pubsubMessage) Ack()                          { p.m.Ack() }
func (p pubsubMessage) Nack()                         { p.m.Nack() }

type subscriberReceiver struct{ sub *pubsub.Subscriber }

func (r subscriberReceiver) Receive(ctx context.Context, f func(context.Context, dispatcher.InboundMessage)) error {
	return r.sub.Receive(ctx, func(ctx context.Context, m *pubsub.Message) { f(ctx, pubsubMessage{m}) })
}

func main() {
	sigCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	d := &dispatcher.Dispatcher{
		Routes:            map[string]dispatcher.WorkflowFunc{"orders.order.created": orderCreated.Handle},
		PerMessageTimeout: 45 * time.Second, // < ReceiveSettings.MaxExtension and <= DrainTimeout; for push, < ack deadline (max 600 s)
		HasDeadLetter:     true,
		Logger:            logger,
	}
	lc := &dispatcher.Lifecycle{
		Receiver:       subscriberReceiver{sub},
		Handler:        func(ctx context.Context, m dispatcher.InboundMessage) { d.Handle(ctx, m) },
		StopPublishers: func(ctx context.Context) error { publisher.Stop(); return nil },
		FlushTelemetry: tracerShutdown,
		CloseDB:        db.Close,
		DrainTimeout:   50 * time.Second, // >= PerMessageTimeout; terminationGracePeriodSeconds: 55
	}
	if err := lc.Run(sigCtx); err != nil {
		logger.Error("consumer exited", "error", err)
		os.Exit(1)
	}
}
```

## 6. GKE HorizontalPodAutoscaler on Pub/Sub backlog

Install the metrics adapter (`custom-metrics-stackdriver-adapter`,
https://github.com/GoogleCloudPlatform/k8s-stackdriver; pin the manifest to a
release tag rather than `master`) and bind its Kubernetes service account to
`roles/monitoring.viewer` through Workload Identity Federation for GKE:

```bash
gcloud projects add-iam-policy-binding "{project_id}" \
  --role="roles/monitoring.viewer" \
  --member="principal://iam.googleapis.com/projects/{project_number}/locations/global/workloadIdentityPools/{project_id}.svc.id.goog/subject/ns/custom-metrics/sa/custom-metrics-stackdriver-adapter"
```

If the consumer must scale to zero, use the KEDA `gcp-pubsub` scaler (`mode:
SubscriptionSize`) as the escape hatch instead of HPA plus adapter
(https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/scale-to-zero-using-keda.md.txt).
`AverageValue` divides the backlog across replicas; set it to 1–2× the
per-replica `MaxOutstandingMessages`. Cap `maxReplicas` so
`maxReplicas * pool_max_open_conns <= database_connection_budget`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: "{deployment_name}-hpa"
  namespace: "{namespace}"
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: "{deployment_name}"
  minReplicas: 2
  maxReplicas: 10
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 1
          periodSeconds: 60
  metrics:
    - type: External
      external:
        metric:
          name: pubsub.googleapis.com|subscription|num_undelivered_messages
          selector:
            matchLabels:
              resource.labels.subscription_id: "{subscription_id}"
        target:
          type: AverageValue
          averageValue: "50"
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 75
```

Pod spec requirements: `terminationGracePeriodSeconds: 55` (drain timeout 50 s
plus 5 s, with drain ≥ per-message timeout 45 s), readiness probe independent of
Pub/Sub connectivity, and `resources.limits.memory` matching the value used to
derive `MaxOutstandingBytes`.

## 7. Escape hatch: Cloud Run push, Eventarc, and Cloud Run functions

```bash
gcloud eventarc triggers create "{trigger_name}" \
  --location="{region}" \
  --destination-run-service="{service_name}" \
  --destination-run-region="{region}" \
  --destination-run-path="/events" \
  --event-filters="type=google.cloud.pubsub.topic.v1.messagePublished" \
  --transport-topic="projects/{project_id}/topics/{topic_id}" \
  --service-account="{trigger_sa}@{project_id}.iam.gserviceaccount.com" \
  --project="{project_id}"
```

Eventarc creates the subscription without a dead-letter policy; add one before
setting `HasDeadLetter: true` in the dispatcher:

```bash
gcloud pubsub subscriptions update "{eventarc_subscription_id}" \
  --dead-letter-topic="{dlq_topic_id}" \
  --max-delivery-attempts=5 \
  --project="{project_id}"
```

For a single short handler, deploy a Cloud Run function bound to the topic.
**Always deploy with `--retry`**: by default an event-driven Cloud Run function
does **not** retry and a returned error acknowledges and **drops** the event!
With `--retry`, returning an error is a nack (retried with backoff for up to 7
days), so either attach a dead-letter policy to the subscription or return
`nil` (success) and alert on permanent payload errors so poison events do not
loop for days:

```bash
gcloud functions deploy "{function_name}" \
  --gen2 \
  --region="{region}" \
  --runtime="{runtime}" \
  --source="{source_dir}" \
  --entry-point="{entry_point}" \
  --trigger-topic="{topic_id}" \
  --retry \
  --service-account="{function_sa}@{project_id}.iam.gserviceaccount.com" \
  --project="{project_id}"
```

Equivalent `gcloud run deploy` form (paired with the Eventarc trigger above):

```bash
gcloud run deploy "{function_name}" \
  --function="{entry_point}" \
  --source="{source_dir}" \
  --base-image="{runtime}" \
  --region="{region}" \
  --project="{project_id}"
```

HTTP handler status contract (`dispatcher.HTTPStatusFor`):

| Outcome | Status | Notes |
| --- | --- | --- |
| Success or idempotent duplicate | `204` (ack set is strictly `102/200/201/202/204`; other `2xx` codes are **not** acks) | Ack |
| Permanent error, subscription has a dead-letter topic | `503` | Counts toward `max-delivery-attempts` |
| Permanent error, no dead-letter topic | `204` + log/quarantine + alert | Never let a poison message retry until retention expires |
| Transient error | `503` (or `429`) | Nack with exponential backoff |

Cloud Run settings: per-message timeout ≤ request timeout ≤ subscription ack
deadline (≤ 600 s); `--concurrency` ≤ per-instance `pool_max_open_conns`;
`--no-cpu-throttling` when background publishing happens after the response;
SIGTERM cleanup must finish within Cloud Run's fixed 10 s grace period.

## 8. Phase 3 checklist and test cleanup

-   [ ] Tests cover success (ack), duplicate (ack), permanent with DLQ (nack),
    permanent without DLQ (ack + alert), quarantine escape hatch (ack),
    transient (nack), and zero-value configuration defaults.
-   [ ] Database close and publisher stop run strictly **after** `Receive`
    returns.
-   [ ] In-flight work uses a context detached from the receive context with a
    deadline below `MaxExtension` and `<= DrainTimeout`.
-   [ ] Cloud Run functions are deployed with `--retry`; Eventarc-created
    subscriptions get a dead-letter policy before `HasDeadLetter` is set.
-   [ ] HPA uses `autoscaling/v2`, scales on `num_undelivered_messages` with a
    scale-down stabilization window, and `maxReplicas` respects the database
    connection budget.
-   [ ] Push handlers return `102/200/201/202/204` for acks and `503`/`429` for
    nacks.

Test-only cleanup (non-production clusters/projects only, after user
confirmation):

```bash
kubectl delete hpa {test_hpa_name} -n {test_namespace}
gcloud eventarc triggers delete {test_trigger_name} --location={region} --project={test_project_id}
gcloud run services delete {test_service_name} --region={region} --project={test_project_id}
gcloud functions delete {test_function_name} --region={region} --project={test_project_id}
```
