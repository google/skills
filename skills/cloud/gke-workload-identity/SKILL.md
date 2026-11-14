---
name: gke-workload-identity
metadata:
  version: "1.0.3"
  category: Security
description: >-
  Configures and diagnoses Workload Identity Federation for GKE authentication failures for Pods
  (403 "iam.serviceAccounts.getAccessToken" / permission denied, "could not find
  default credentials", or GKE metadata server unreachable) by verifying
  cluster and node-pool Workload Identity configuration, the Kubernetes
  ServiceAccount (KSA) to IAM binding (direct principal binding and legacy Google
  ServiceAccount impersonation), target-resource IAM roles, and gke-metadata-server
  health. Use when setting up KSA/GSA bindings (`roles/iam.workloadIdentityUser`,
  `iam.gke.io/gcp-service-account`) or when a Pod cannot authenticate to Google Cloud APIs. Don't use for in-cluster
  Kubernetes RBAC errors (API-server authorization), general workload crashes
  (use gke-workload-troubleshooting), or Pod Security Standards and NetworkPolicies
  (use gke-workload-security).
---

# GKE Workload Identity Federation Troubleshooting Skill

Use this skill to systematically diagnose why a Pod using **Workload Identity
Federation for GKE** cannot authenticate to Google Cloud APIs. Typical symptoms:

-   `HTTP/403 ... Permission 'iam.serviceAccounts.getAccessToken' denied on
    resource`
-   `google.auth.exceptions ... could not find default credentials` /
    `ComputeEngineCredentials cannot find the metadata server`
-   API calls that unexpectedly use the node's default Compute Engine service
    account instead of the workload's identity.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:gke-workload-identity)"`
and append `agent-skills/1.0 (skill:gke-workload-identity)` to `User-Agent` headers.

## Read-only boundary

This skill is **diagnostic and non-interactive**. It only **reads** cluster,
IAM, and logging state and **proposes** fixes as commands or GitOps manifest
changes for a human to apply. It must **never** create or modify IAM bindings,
KSA annotations, node pools, or clusters automatically. When evidence is missing
or the fix requires a privileged change, summarize findings and hand off to a
human (see Step 7).

## Output discipline (apply to every conclusion)

When you report a diagnosis, always:

1.  **Name the single most-likely root cause** (not an open-ended list of
    possibilities).
2.  **Explicitly rule out** the other plausible causes, citing the evidence that
    excludes them. In particular, when the cause is node-pool configuration,
    state plainly that it is **not** a KSA annotation or IAM binding problem;
    when the cause is a missing role on a target resource, state that Workload
    Identity itself is **not** misconfigured.
3.  **Give the exact remediation as a proposed change for a human** — a concrete
    `gcloud` command (or GitOps manifest edit) with the real identifiers filled
    in — and never apply it automatically.

--------------------------------------------------------------------------------

## Diagnostic Workflow

### Step 0: Context discovery & time window

Collect (from the user or the failing resource): `PROJECT_ID`, `PROJECT_NUMBER`,
`CLUSTER`, cluster `LOCATION`, `NAMESPACE`, the **KSA** the Pod runs as, the
**node and node pool** the Pod is scheduled on (used in Step 2), the **target
resource / API** being called, and the **exact error string**. Define a time
window around the first observed failure for log queries.

```bash
# Resolve the project number (used in the direct-binding principal identifier).
gcloud projects describe "{PROJECT_ID}" --format="value(projectNumber)"

# Confirm which KSA the workload runs as.
kubectl get pod "{pod_name}" -n "{namespace}" \
  -o jsonpath='{.spec.serviceAccountName}'

# Identify the node the Pod runs on, then the node pool that node belongs to
# (Step 2 checks the node pool's Workload Identity mode).
NODE=$(kubectl get pod "{pod_name}" -n "{namespace}" -o jsonpath='{.spec.nodeName}')
kubectl get node "$NODE" \
  -o jsonpath='{.metadata.labels.cloud\.google\.com/gke-nodepool}'
```

--------------------------------------------------------------------------------

### Step 1: Capture the exact error signature

Read the workload's own logs and the `gke-metadata-server` logs to classify the
failure.

```bash
kubectl logs "{pod_name}" -n "{namespace}" --all-containers --prefix
kubectl describe pod "{pod_name}" -n "{namespace}"
```

Equivalent via Cloud Logging (preferred for historical events). Open it as a
**Logs Explorer deep link** — URL-encode the query and append the project and
time window:
`https://console.cloud.google.com/logs/query;query={URL_ENCODED_QUERY};timeRange={start}%2F{end}?project={project_id}`
(encode `/` as `%2F`, or use `;duration=PT1H` for a rolling hour):

```
resource.type="k8s_container"
resource.labels.namespace_name="{namespace}"
resource.labels.pod_name="{pod_name}"
severity>=WARNING
```

**Classify the signature:**

-   `iam.serviceAccounts.getAccessToken` denied / `HTTP/403` → the workload is
    using the **GSA impersonation** path. This is expected for the legacy setup,
    but if you intend to use **direct binding**, it means the KSA still carries
    a leftover `iam.gke.io/gcp-service-account` annotation (or the client SDK is
    configured to impersonate) and is unintentionally impersonating a GSA; go to
    Step 3.
-   `403 PERMISSION_DENIED` on the **target API/resource** (no `getAccessToken`
    in the error) → the resolved identity lacks the required IAM role on that
    resource; go to Step 4.
-   `could not find default credentials` / `cannot find the metadata server` →
    metadata-server connectivity or a startup race; go to Step 5.
-   Calls succeed but as the **node default service account** → Workload
    Identity is not in effect for this node pool; go to Step 2.

--------------------------------------------------------------------------------

### Step 2: Verify Workload Identity is enabled (cluster + node pool)

Both the cluster and the **node pool the Pod runs on** must have Workload
Identity enabled. A node pool with `GCE_METADATA` (instead of `GKE_METADATA`)
causes Pods to fall back to the node's default Compute Engine service account.

```bash
# Cluster must have a workload identity pool (PROJECT_ID.svc.id.goog).
gcloud container clusters describe "{cluster}" --location "{location}" \
  --format="value(workloadIdentityConfig.workloadPool)"

# Node pool must have workloadMetadataConfig.mode = GKE_METADATA.
gcloud container node-pools describe "{node_pool}" --cluster "{cluster}" \
  --location "{location}" \
  --format="value(config.workloadMetadataConfig.mode)"
```

-   Empty workload pool → Workload Identity is **not enabled on the cluster**.
-   Node-pool mode is `GCE_METADATA` (or empty) → the node pool is **not** using
    the GKE metadata server; this is the usual cause of "runs as the node
    default service account". Remediation: enable
    `--workload-metadata=GKE_METADATA` on the node pool (propose to a human;
    immediately affects running workloads and might disrupt workloads using the
    node service account). This is a **node-pool configuration** problem — not a
    KSA annotation or IAM binding problem — so do not change KSA annotations or
    bindings to fix it. When the symptom is "runs as the node default service
    account", say so explicitly: the root cause is the node pool's
    `workloadMetadataConfig.mode`, and the KSA annotation and IAM bindings are
    **ruled out** as the cause. Propose the exact fix, e.g.:

```bash
gcloud container node-pools update "{node_pool}" --cluster "{cluster}" \
  --location "{location}" --workload-metadata=GKE_METADATA
```

--------------------------------------------------------------------------------

### Step 3: Verify the KSA → identity binding

There are two supported models. **Prefer direct binding** (current default);
treat GSA impersonation as the **legacy** path.

> **How the two models fail differently:** with **direct binding** the KSA
> principal accesses resources directly, so failures show up as a plain `403
> PERMISSION_DENIED` on the target API (fix in Step 4). A `403
> iam.serviceAccounts.getAccessToken` instead means an **impersonation** attempt
> — intended under the legacy path, or *unintended* if a leftover
> `iam.gke.io/gcp-service-account` annotation remains on a KSA that was meant to
> use direct binding.

**(a) Direct KSA binding (no GSA impersonation).** The KSA principal is granted
roles directly. Construct the principal identifier and search for its bindings:

```
principal://iam.googleapis.com/projects/{PROJECT_NUMBER}/locations/global/workloadIdentityPools/{PROJECT_ID}.svc.id.goog/subject/ns/{NAMESPACE}/sa/{KSA_NAME}
```

**(b) Legacy: KSA + GSA impersonation.** The KSA must be annotated to point at a
GSA, and the KSA must hold `roles/iam.workloadIdentityUser` on that GSA.

```bash
# The KSA annotation must reference the intended GSA.
kubectl get serviceaccount "{ksa_name}" -n "{namespace}" \
  -o jsonpath='{.metadata.annotations.iam\.gke\.io/gcp-service-account}'

# The GSA's IAM policy must bind the KSA member to workloadIdentityUser.
gcloud iam service-accounts get-iam-policy \
  "{gsa_name}@{project_id}.iam.gserviceaccount.com" \
  --format=json
# Expect a binding: role roles/iam.workloadIdentityUser,
# member serviceAccount:{PROJECT_ID}.svc.id.goog[{NAMESPACE}/{KSA_NAME}]
```

> If the annotation is present but the binding is missing, the binding was
> likely removed — check the `setIamPolicy` audit logs around the failure time
> to find the responsible principal.

--------------------------------------------------------------------------------

### Step 4: Verify IAM permissions on the target resource

Even with a correct binding, the identity (the KSA principal for direct binding,
or the GSA for legacy) must hold the role required by the API call (for example
`roles/storage.objectViewer`). The standard IAM Policy Troubleshooter has
limited support for Workload Identity principals; use Cloud Asset Inventory to
search all IAM policies for the principal instead.

```bash
# Direct binding: search for the KSA principal's bindings across the project.
gcloud asset search-all-iam-policies \
  --scope="projects/{PROJECT_ID}" \
  --query='policy:"{PROJECT_ID}.svc.id.goog"'

# Legacy: search for the GSA's bindings on the target resource's project.
gcloud asset search-all-iam-policies \
  --scope="projects/{TARGET_PROJECT_ID}" \
  --query='policy:"{gsa_name}@{project_id}.iam.gserviceaccount.com"'
```

If no binding grants the required role on the target resource, **that missing
role is the root cause** (and Workload Identity itself is **not**
misconfigured). Present the fix as a **proposed change for a human to apply** —
the exact `add-iam-policy-binding` with the real principal and role — never
applying it automatically. For example, for direct binding on a project-level
resource:

```bash
gcloud projects add-iam-policy-binding "{TARGET_PROJECT_ID}" \
  --member="principal://iam.googleapis.com/projects/{PROJECT_NUMBER}/locations/global/workloadIdentityPools/{PROJECT_ID}.svc.id.goog/subject/ns/{NAMESPACE}/sa/{KSA_NAME}" \
  --role="{REQUIRED_ROLE}"   # e.g. roles/storage.objectViewer
```

--------------------------------------------------------------------------------

### Step 5: GKE metadata server & connectivity

Applies when the signature is `could not find the metadata server`, `cannot find
the metadata server`, or a connection/timeout error. The `gke-metadata-server`
DaemonSet (in `kube-system`) brokers the token exchange on each node; requests
to `169.254.169.254` are redirected to it, so a Pod fails closed if it cannot
reach a healthy metadata-server Pod on its node.

**(a) Check gke-metadata-server Pod health on the workload's node.**

```bash
# The DaemonSet Pods must be healthy on the workload's node.
kubectl get pods -n kube-system -l k8s-app=gke-metadata-server -o wide

# A gke-metadata-server Pod can be OOM-evicted when the cluster has many
# (>3,000) Kubernetes service accounts. Look for CrashLoopBackOff, then confirm
# the eviction was OOMKilled.
kubectl get pods -n kube-system | grep CrashLoopBackOff
kubectl describe pod {gke_metadata_server_pod} --namespace=kube-system | grep OOMKilled
```

**(b) Inspect the `gke-metadata-server` logs** (historical, via Cloud Logging;
open as a Logs Explorer deep link, see Step 1):

```
resource.type="k8s_container"
resource.labels.namespace_name="kube-system"
labels."k8s-pod/k8s-app"="gke-metadata-server"
severity>=WARNING
```

**(c) Connectivity test** from the affected Pod — it must reach the metadata
server and (for some client libraries) resolve its DNS name:

```bash
# Token endpoint via the hardcoded metadata IP (a healthy path returns a token).
kubectl exec {pod_name} -n {namespace} -- \
  curl -sS -H 'Metadata-Flavor: Google' \
  'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token'
```

Possible causes:

-   **Startup race**: the metadata server needs a few seconds after a Pod
    starts. Applications that authenticate immediately may fail; the fix is
    application-side retries or an `initContainer` that waits for the metadata
    server, not a cluster change.
-   **DNS**: some client libraries resolve `metadata.google.internal`; broken
    in-cluster DNS surfaces as `cannot find the metadata server`. As a
    workaround, set `GCE_METADATA_HOST=169.254.169.254` to skip DNS resolution.
-   **Network policy / egress**: a cluster network policy must allow egress to
    `169.254.169.254/32` on port `80` (GKE Dataplane V2), or
    `169.254.169.252/32` on port `988`. A default-deny egress rule that blocks
    HTTPS to the public Security Token Service (`sts.googleapis.com:443`)
    produces `504 Gateway Timeout` or `context deadline exceeded`.
-   **`gke-metadata-server` crashing / high restarts**: see (a) — reduce the
    number of Kubernetes service accounts (<3,000) to restore functionality.

--------------------------------------------------------------------------------

### Step 6: "Invalid form of account ID" edge case (legacy GSA impersonation)

> **Applies only to the legacy GSA impersonation setup** (a KSA annotated with
> `iam.gke.io/gcp-service-account`), not to direct principal binding.

Signature: an operation that requires an IAM **service account email** (for
example, manually creating a Cloud Storage signed URL) fails with:

```
ERROR: Invalid form of account ID SERVICEACCOUNT_NAME.svc.id.goog.
Should be [Gaia ID | Email | Unique ID | ] of the account
```

Cause: for a KSA linked to a GSA via annotation, the GKE metadata server by
default returns `SERVICEACCOUNT_NAME.svc.id.goog` as the identifier, which is
not a valid IAM service account email. This is **not** a missing IAM binding and
does **not** require reverting the setup.

Fix (propose to a human): add the
`iam.gke.io/return-principal-id-as-email="true"` annotation to the Pod's KSA so
the metadata server returns the identity in the expected form:

```bash
kubectl annotate serviceaccount "{ksa_name}" --namespace "{namespace}" \
  iam.gke.io/return-principal-id-as-email="true"
```

--------------------------------------------------------------------------------

### Step 7: Remediation boundary & escalation

-   Present the **root cause + evidence** (the exact error, the missing binding
    / annotation / node-pool mode, or the metadata-server state). Include a
    **Cloud Logging deep link** (see Step 1) to the supporting entries.
-   Propose the fix as a **command or GitOps manifest change** for a human to
    apply — never modify IAM, KSAs, or node pools automatically.

**Escalate** (instead of proposing more self-service diagnostics) when either:

-   the relevant logs are **unavailable** (excluded by a filter, or past the log
    bucket's retention); or
-   the identity/binding is correct, the target-resource IAM is correct, and the
    metadata server is healthy, yet the failure persists (undetermined root
    cause).

In those cases: state the limitation plainly, summarize the findings gathered
(cluster/node-pool config, bindings, annotations, metadata-server state, and any
`setIamPolicy` audit logs), and route to GKE support / engineering escalation.
Do **not** fabricate a diagnosis when evidence is missing.

--------------------------------------------------------------------------------

## References

This skill is derived from public Google Cloud documentation:

-   [Troubleshoot GKE authentication issues](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/authentication.md.txt)
    — the Workload Identity Federation section: WI-enabled check, KSA
    annotation, `roles/iam.workloadIdentityUser`,
    `iam.serviceAccounts.getAccessToken` 403,
    `iam.gke.io/return-principal-id-as-email`, metadata-server DNS and the
    [`gke-metadata-server` Pod is crashing](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/authentication.md.txt#metadata-server-crashes)
    guidance.
-   [About Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity.md.txt)
    — identities, the GKE metadata server, and why Pods don't inherit the node
    identity.
-   [Configure applications to use Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity.md.txt)
    — node-pool `--workload-metadata=GKE_METADATA`, the direct-binding
    `principal://...` identifier, and the legacy
    `serviceAccount:PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]` member format.
-   [Search IAM policies (Cloud Asset Inventory)](https://docs.cloud.google.com/asset-inventory/docs/search-allow-policies)
    — `gcloud asset search-all-iam-policies` for auditing a principal's
    bindings.
-   [View GKE logs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs.md.txt)
    — Cloud Logging queries for workload and system logs.
