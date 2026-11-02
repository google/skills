# Cloud Logging, Audit Attribution, APF & API Server Traces

## Table of Contents

-   **1. API Server Slow-Request Trace Logs (`trace.go`)** (Lines 11–54)
-   **2. Heavy API Clients (`httplog.go`), Audit Attribution & Slow `LIST`s** (Lines 56–98)
-   **3. API Priority & Fairness (APF) Throttling (`429` / `504` / `404`)** (Lines 100–124)
-   **4. Hot-Object `409 Conflict`s & Leader-Election `RenewDeadline` Timeouts** (Lines 126–146)
-   **5. `pods/exec`, Konnectivity, Cloud KMS & IAM Webhook Authorizer** (Lines 148–188)

## 1. API Server Slow-Request Trace Logs (`trace.go`)

`kube-apiserver` component logs (`API_SERVER`) are an **optional feature that is
not enabled by default** and must be explicitly turned on
(`--logging=SYSTEM,WORKLOAD,API_SERVER`). State this and link to
https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs#control_plane_logs
when recommending `apiserver` log analysis.

1.  **Search for `trace` or `Trace` entries**: Query `apiserver` component logs
    (`resource.type="k8s_control_plane_component" AND
    resource.labels.component_name="apiserver"`) for `trace` or `Trace` (e.g.,
    `textPayload:"Trace["`).
2.  **Structure & interpretation**: `kube-apiserver` uses upstream
    [`k8s.io/utils/trace`](https://github.com/kubernetes/utils/blob/master/trace/README.md)
    (`trace.go`) to log requests exceeding a latency threshold (typically
    500ms). The header records the operation (`"List"`, `"Get"`, `"Create"`,
    `"Patch"`), `url`, `user-agent`, `audit-id`, `client` IP, start timestamp,
    and `total time`. Nested sub-traces appear in brackets `[...]` and steps
    exceeding the step threshold appear as `---"<StepName>" <duration>ms`.
3.  **Distinguishing storage bottlenecks vs. slow-client serialization**:
    -   **Slow backend storage (`etcd`) read or write**: `cacher.GetList`,
        `List(recursive=true) etcd3`, or `GuaranteedUpdate etcd3` (with `initial
        value restored` / `Txn call completed`) dominates `total time`:
        ```text
        I1015 11:36:56.835120      10 trace.go:236] Trace[123456789]: "List" url:/api/v1/pods,user-agent:my-controller/v1.0.0,audit-id:11111111-2222-3333-4444-555555555555,client:10.0.0.1 (15-Oct-2026 11:36:49.460) (total time: 7374ms):
        Trace[123456789]: ["List(recursive=true) etcd3" 6890ms (11:36:49.461)]
        Trace[123456789]: ---"Objects listed" 6891ms (11:36:56.352)
        Trace[123456789]: ---"SerializeObject" 480ms (11:36:56.832)
        ```
    -   **Slow client / response serialization bottleneck**: `"Objects listed"`
        is fast, while `"SerializeObject"` and `---"Write call succeeded"` (or
        `---"Write call failed"`) dominate `total time` because a slow or
        bandwidth-constrained client takes seconds to read a large payload:
        ```text
        I1015 11:40:12.104512      10 trace.go:236] Trace[987654321]: "List" url:/api/v1/pods,user-agent:slow-watcher/v0.1,audit-id:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee,client:10.0.0.2 (15-Oct-2026 11:40:01.002) (total time: 11102ms):
        Trace[987654321]: ---"Objects listed" 45ms (11:40:01.047)
        Trace[987654321]: ["SerializeObject" 11055ms (11:40:01.047)]
        Trace[987654321]: ---"Write call succeeded" 11054ms (11:40:12.101)
        ```
4.  **Upstream docs & future evolution (cite both)**: Link to
    https://github.com/kubernetes/utils/blob/master/trace/README.md for
    `trace.go` and mention
    https://github.com/kubernetes/enhancements/tree/master/keps/sig-instrumentation/647-apiserver-tracing
    (KEP-647: APIServer Tracing via OpenTelemetry) as a possible future change.

## 2. Heavy API Clients (`httplog.go`), Audit Attribution & Slow `LIST`s

1.  **`httplog.go` HTTP access logs**: Requires enabling `API_SERVER` component
    logs (`--logging=SYSTEM,WORKLOAD,API_SERVER`; link to
    https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs#control_plane_logs).
    State explicitly that the **`httplog.go` log structure is very stable**
    across Kubernetes releases (making regex extraction and Log Analytics
    queries reliable), and include this example log line:
    ```text
    I1015 11:36:56.835535      10 httplog.go:137] "HTTP" verb="GET" URI="/api/v1/namespaces/default/pods" latency="7.374935s" userAgent="my-controller/v1.0.0 (linux/amd64)" audit-ID="11111111-2222-3333-4444-555555555555" srcIP="10.0.0.1:12345" apf_pl="workload-low" apf_fs="everybody" apf_iseats=1 apf_fseats=0 apf_additionalLatency="0s" apf_execution_time="7.374765s" resp=200
    ```
    -   **Key fields**: `user_agent` (`userAgent` in raw text) identifies the
        client binary/operator; `verb` separates expensive `LIST` or mutating
        `PATCH`/`UPDATE` calls from lightweight `GET`s; `apf_iseats` (with
        `apf_fseats` and `apf_execution_time`) measures API Priority and
        Fairness (APF) concurrency seats occupied (`apf_iseats *
        apf_execution_time` reveals top concurrency consumers).
2.  **Noisy-neighbor attribution & slow/heavy `LIST` queries**: Because
    Prometheus metrics omit caller/user-agent labels to prevent cardinality
    explosion, always pair **`apiserver_request_total`** (grouped by `verb`,
    `resource`, and `code` to quantify QPS/error spikes) with **GKE Cloud Audit
    Logs** (which attribute requests to callers out-of-the-box even when
    optional `API_SERVER` logs are off):
    ```promql
    sum by (verb, resource, code) (rate(apiserver_request_total[5m]))
    ```
    -   Query GKE Cloud Audit Logs (`cloudaudit.googleapis.com/activity` and
        `data_access`) and `kube-apiserver` `Trace[` / `httplog.go` logs,
        aggregating by `protoPayload.authenticationInfo.principalEmail`,
        `protoPayload.requestMetadata.callerSuppliedUserAgent`, and target
        resource/namespace.
    -   Correlate audit log offender attribution with `apiserver_request_total`
        (grouped by `verb`, `resource`, and `code`),
        `apiserver_request_duration_seconds` (`verb="LIST"`),
        `apiserver_response_sizes` (`verb="LIST"`), per-resource storage size
        (`apiserver_resource_size_estimate_bytes` or
        `kubernetes.io/master/apiserver/resource_size_estimate_bytes`, grouped
        by `group` and `resource`), and
        `apiserver_watch_list_duration_seconds`.
    -   **Remediation**: Throttle or fix high-QPS client workloads, refactor or
        paginate expensive cluster-wide `LIST` queries (e.g., `external-dns`,
        `argocd-server`, or custom operators listing all pods), use
        `resourceVersion="0"` (watch cache reads), or switch to cached
        `SharedInformer` watches.

## 3. API Priority & Fairness (APF) Throttling (`429` / `504` / `404`)

When workloads, batch job scripts, or CI runners fail with HTTP `429 Too Many
Requests` or `504 Gateway Timeout` (`context canceled`):

-   **Metrics to query**: Query `apiserver_flowcontrol_rejected_requests_total`,
    `apiserver_flowcontrol_current_inqueue_requests`,
    `apiserver_flowcontrol_request_wait_duration_seconds`, and
    `apiserver_flowcontrol_priority_level_seat_utilization` grouped by
    `priority_level` and `flow_schema`, plus `apiserver_request_total` by status
    code (`404`, `429`, `504`) and verb (`GET`, `LIST`).
-   **Log attribution (`API_SERVER` logs)**: Enable control-plane logging
    (`API_SERVER` via `--logging=SYSTEM,WORKLOAD,API_SERVER`) to pull detailed
    information on `user_agent` (`userAgent`), target resources (`URI` /
    `requestURI`), and source IPs (`src_ip` / `srcIP` / `sourceIPs`) from
    `kube-apiserver` logs (or Cloud Audit Logs) for unpaginated `LIST` calls,
    tight `404` `GET` polling loops, or single-digit millisecond `?timeout=`
    requests.
-   **How APF works & remediation**: APF throttles noisy clients in
    lower-priority lanes (such as `workload-low`) to protect critical system
    traffic (`system`, `leader-election`, `node-high`). Pace client burst QPS,
    replace tight `GET`/`LIST` polling with `SharedInformer` watches, add
    exponential backoff and client-side caching on `404`s, increase overly short
    client request timeouts, or isolate noisy service accounts into a dedicated
    `FlowSchema` and `PriorityLevelConfiguration`.

## 4. Hot-Object `409 Conflict`s & Leader-Election `RenewDeadline` Timeouts

-   **Hot-object write contention (`409 Conflict` & slow `PATCH`/`PUT`)**: When
    runaway controllers fight over or hot-loop updates against a single
    `ConfigMap`, `CustomResourceDefinition`, or `Lease`, query Cloud Audit Logs
    (`cloudaudit.googleapis.com/activity`) grouped by
    `protoPayload.resourceName`, `protoPayload.methodName` (`update` or
    `patch`), and `protoPayload.requestMetadata.callerSuppliedUserAgent` (or
    `protoPayload.authenticationInfo.principalEmail`) and inspect
    `kube-apiserver` `GuaranteedUpdate` `Trace[` logs to pinpoint the hot object
    and responsible agent. Mitigate by reducing the operator's checkpoint/sync
    frequency (e.g., increasing `refreshInterval`) and lowering client QPS.
-   **Leader-election `RenewDeadline / 2` (`?timeout=5s`) timeouts**: When
    third-party operators (e.g., KEDA, VictoriaMetrics) lose Lease leadership
    with `context deadline exceeded` after 5s despite higher general client
    timeouts, explain that `client-go`'s `leaderelection` package sets the
    per-request HTTP timeout on Lease `PUT` renewals to `RenewDeadline / 2` (so
    default `RenewDeadline: 10s` enforces `?timeout=5s` on `requestURI` in Cloud
    Audit Logs and `Trace[` logs). Increase the operator's leader-election flags
    (e.g., `--leader-elect-lease-duration=60s` and
    `--leader-elect-renew-deadline=40s`).

## 5. `pods/exec`, Konnectivity, Cloud KMS & IAM Webhook Authorizer

-   **Excessive `pods/exec` saturating webhooks & Konnectivity**: When
    `warden-validating.common-webhooks.networking.gke.io` admission timeouts
    (`10s`) or `500 error dialing backend: dial timeout, backstop` errors occur
    on `kubectl exec`, query Cloud Audit Logs for `io.k8s.core.v1.pods.exec.get`
    (`connect`) volume and correlate with
    `apiserver_admission_webhook_admission_duration_seconds` for
    `warden-validating` (high `pods/exec` volume evaluates against admission
    webhooks and Konnectivity tunnels). Replace `kubectl exec`-based metrics
    scraping and health checks with Kubelet `/metrics/cadvisor`, Cloud
    Monitoring container metrics (`k8s_container`), and direct pod-to-pod
    HTTP/gRPC endpoints.
-   **Konnectivity (`No agent available`), firewall, & `ip-masq-agent`**: When
    webhook calls or `kubectl exec`/`logs` fail with `No agent available` or
    `context deadline exceeded`, check `kube-apiserver` logs
    (`resource.type="k8s_control_plane_component"`) for `No agent available` or
    dial failures, inspect `konnectivity-agent` pods (`kubectl get pods -n
    kube-system -l k8s-app=konnectivity-agent`), verify VPC firewall rules
    between the control-plane CIDR and node/pod CIDRs (ports `10250`, `8132`,
    and webhook ports), and check the `ip-masq-agent` ConfigMap so
    pod-to-API-server and API-server-to-webhook traffic is not masqueraded or
    blocked.
-   **Disabled Cloud KMS keys breaking encryption (`kms-provider-0` / `failed to
    get dek primitive`)**: Inspect `gcloud container clusters describe`
    (`databaseEncryption` config and error status) and query Cloud Audit Logs
    for `cloudkms.googleapis.com` (`DisableCryptoKeyVersion`,
    `DestroyCryptoKeyVersion`, or `PermissionDenied` on `Encrypt`/`Decrypt`).
    Re-enable the disabled `CryptoKeyVersion`, verify the GKE service agent has
    `roles/cloudkms.cryptoKeyEncrypterDecrypter`, and follow
    https://docs.cloud.google.com/kubernetes-engine/docs/how-to/encrypting-secrets#reencrypt-secrets
    to re-encrypt existing Secrets.
-   **In-cluster GCP IAM OAuth tokens saturating the GKE IAM webhook authorizer
    (`Failed to make webhook authorizer request`)**: When high-QPS in-cluster
    clients (`Helm`, operators) authenticate with GCP IAM OAuth Bearer tokens
    without matching Kubernetes RBAC bindings, `kube-apiserver` invokes the
    external GKE IAM webhook authorizer on every request, which throttles/times
    out under load. Inspect Cloud Audit Logs (`authenticationInfo` and
    `authorizationInfo`) and migrate in-cluster workloads to native Kubernetes
    `ServiceAccount` tokens bound via Kubernetes RBAC (`RoleBinding` /
    `ClusterRoleBinding`) so authorization is evaluated locally in memory.
