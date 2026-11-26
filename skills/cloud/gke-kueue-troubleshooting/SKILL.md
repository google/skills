---
name: gke-kueue-troubleshooting
description: Diagnose a GKE batch or AI workload (Job, JobSet, LeaderWorkerSet, RayJob, Kubeflow training jobs, or plain Pods) that is pending, suspended, stuck, evicted or misconfigured when Kueue manages it - from a live GKE cluster, a support bundle or exported controller/audit logs. Load it as soon as the investigation shows a Kueue footprint, even if the user never said "Kueue" - anything under kueue.x-k8s.io (labels, Pod scheduling gates, Workload/LocalQueue/ClusterQueue objects and their conditions), kueue-controller-manager events or logs, or a Job with spec.suspend=true together with a Workload object in its namespace. Scripts compact cluster state and logs into verifiable facts and validate the report, while the agent classifies the cause as Kueue configuration, Kueue defect, or outside Kueue. Don't use for workloads with no Kueue footprint (use gke-node-notready, gke-workload-scaling-troubleshooting, gke-ai-troubleshooting-tpu-reservation-stockout, or gke-ai-troubleshooting-jobset-interruption).
metadata:
  version: "1.1.1"
  category: Containers
---

# GKE Kueue troubleshooting

> **Read-only rule:** Run read-only diagnostic commands only. Never drain,
> delete, or re-create nodes, or run `kubectl patch/apply/edit/delete` or any
> other command that changes the cluster. When exporting logs for
> `trace_logs.py`, run only read-only log queries scoped to the target cluster,
> `kueue-system`, Kubernetes Event logs, Admin Activity audit logs, and the
> incident time window as described in
> [Log sources](references/log-sources.md) and
> [View GKE logs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs.md.txt).
> Give the user any fix (remediation YAML, commands, or linked documentation
> steps) to apply themselves in the final `### Diagnostic Summary`.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites

- **Tools and cluster access**: Python 3.10+ with `PyYAML` (all diagnostic
  scripts live in `scripts/` next to this file and require no cloud SDKs); if
  `python3 -c "import yaml"` fails, ask the user for approval before running
  `python3 -m pip install "PyYAML>=6,<7"`, and if the user declines or `pip`
  fails, stop and tell the user that the scripts require `PyYAML`. In `live`
  mode, follow "Before you begin" in
  [Deploy a batch system using Kueue](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/kueue-intro.md.txt)
  to initialize `gcloud` and select the target project, and follow
  [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt)
  to configure cluster credentials (`offline_data` and `logs_archive` read local
  files only).
- **Cloud Billing and APIs**: For `live` cluster inspection or Cloud Logging
  exports, ensure the project has an active Cloud Billing account and the Google
  Kubernetes Engine API (`container.googleapis.com`) and Cloud Logging API
  (`logging.googleapis.com`) are enabled.
- **Required IAM roles**: Per
  [Google Kubernetes Engine roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/container.md.txt),
  `live` cluster resource reads require Kubernetes Engine Viewer
  (`roles/container.viewer`), and reading controller pod logs via `kubectl logs`
  (`container.pods.getLogs`) or applying Kueue/cluster fixes requires Kubernetes
  Engine Developer (`roles/container.developer`) or Kubernetes Engine Admin
  (`roles/container.admin`). Exporting Cloud Logging and Admin Activity audit
  logs requires Logs Viewer (`roles/logging.viewer`).
- **Scope and related skills**: Upstream Kueue ships experimental interactive
  skills (`kueue-lineage` and `kueue-who-preempted`, documented in
  [Troubleshooting Agent Skills](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_agent_skills/))
  for quick object-tree and preemption queries on a live cluster. This skill
  adds offline support-bundle and Cloud Logging compaction, GKE infrastructure
  boundary classification (`Outside Kueue`), and report validation.

## 1. Three-step protocol

The scripts **detect the Kueue release and API version**
(`active_api_schema_reference._detected_kueue_version`, e.g.
`v0.10.x`/`v1beta1` vs `v0.19.x`/`v1beta2`) from controller deployments, CRDs,
object `apiVersion`s or startup/audit logs, and load the **CRD and
`KueueConfiguration` schema for that version**. If `detection_sources` is only
`default:v1beta2`, the version was **assumed** — pass `--kueue-version <tag>`
or confirm the served CRD version before writing remediation YAML.

**Where the schema comes from** (`schema_source` / `config_schema_source`): in
`live` the cluster's served CRDs are used (`live_cluster_crds`); in
`offline_data` bundled CRD manifests are used if present (`bundled_crds`);
otherwise, or if the `live` CRDs cannot be read, release CRDs are read from
`GKE_KUEUE_TROUBLESHOOTING_KUEUE_REPO` or fetched once from GitHub
(`github_release:<tag>`) and cached under
`$XDG_CACHE_HOME/gke-kueue-troubleshooting` (override with
`GKE_KUEUE_TROUBLESHOOTING_CACHE_DIR`). `KueueConfiguration` is not a CRD; in
every mode (`live` included) its field tree is fetched from the
[KueueConfiguration v1beta2 reference](https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/)
or
[KueueConfiguration v1beta1 reference](https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/)
matching `config_api_version` (else `builtin_defaults`). `--no-remote-schema`
or `GKE_KUEUE_TROUBLESHOOTING_NO_REMOTE_SCHEMA=1` disables both downloads.

**If `schema_source` is `unavailable`** (`_schema_notice` present): CRD schemas
are never approximated; only `KueueConfiguration` may fall back to
`builtin_defaults`. Note in one sentence at the top of the report that the
release-exact schema was unavailable, name the remedy from `_schema_notice`
(cluster access, bundled CRDs, GitHub access, or `--kueue-version`), and
**continue the diagnosis** using the fields, conditions, and logs in the
snapshot (see [LocalQueue](https://kueue.sigs.k8s.io/docs/concepts/local_queue/)
and
[Topology Aware Scheduling](https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/)).
Remediation YAML still uses the detected `apiVersion`.

**Choose the data mode** (`--mode` or `GKE_KUEUE_TROUBLESHOOTING_MODE`, default
`live`):

- `live`: when `kubectl` reaches the cluster.
- `offline_data`: directory of YAML/JSON manifests (optionally with `logs/`);
  pass `--data-path <dir>`.
- `logs_archive`: exported logs only (no cluster or manifests); export to a
  local file first and pass `--data-path <file-or-dir>` (scoped per
  [Log sources](references/log-sources.md); never `cat` or page raw log exports
  into context).

Pass the **same** `--ledger-path <ledger>` inside a per-run temporary directory
to every script call so concurrent runs never collide; Step 3 verifies quotes
and schema against it. Shell state may not persist between commands: run
`mktemp -d /tmp/kueue-triage.XXXXXX` once and pass the printed literal absolute
path (not a shell variable) in every later command. **Do not read or parse the
ledger.**

**Output contract.** `snapshot.py` and `trace_logs.py` print a **digest ordered
most-important-first** (`detected_kueue_version`, derived facts,
`bulk_object_groups` with counts/names/representative, individual objects/log
excerpts, schema reference last) capped at `--max-output-bytes` (48 KB default
for snapshot, 24 KB for logs). The complete output is written to
`full_report_file` (next to the ledger). If command output is truncated to a
saved file, read that saved file once instead of re-running `--action get` or
`grep`. If the digest ends with `truncated:`, all tagged and coverage facts are
already above it; to inspect one dropped object, use
`--action get --kind <kind> --name <name> --namespace <ns>` (`--namespace` is
required for namespaced kinds; at most **4** `get` calls, never the same
`kind/name` twice) or read a ≤ 200-line slice of `full_report_file` / raw bundle
files (at most **twice**). Never read the skill's own Python scripts.

1. **Step 1 — one-shot snapshot or log timeline (schema attached)**
   - `live` / `offline_data`: run `scripts/snapshot.py` with
     `--mode <mode> --action snapshot --ledger-path <ledger>` (add
     `--namespace <ns>` if known; `--kueue-namespace` if not `kueue-system`;
     `--ignore-namespaces ns1,ns2` for extra add-on namespaces). If no active
     `Workload`/`Job` is present or controller/audit history is needed, also run
     `scripts/trace_logs.py --mode <mode> --ledger-path <ledger>` once (at most
     2 log commands total).
   - `logs_archive`: run
     `scripts/trace_logs.py --mode logs_archive --ledger-path <ledger>` with
     `--data-path <file-or-dir>` first (add `--workload <name>` to focus).
     Never call `kubectl` in this mode.
   - **Schema lookup (optional):** `scripts/snapshot.py --action explain` with
     `--kind <Kind[.field.path]> --ledger-path <ledger>`.
   - **If a script fails or skips files:** read the error once, follow
     `next_step`, and continue with available files without retrying in a loop.
     If `trace_logs.py` reports `skipped_inputs` (symlinks or non-regular files)
     or `unreadable_inputs` (unparseable or concatenated JSON exports), do not
     treat those logs as absent from the cluster: tell the user which files were
     not read (re-export each filter to its own regular file or verify symlink
     targets per [Log sources](references/log-sources.md)) and record any
     unresolved gap under `#### Open Questions`.

2. **Step 2 — reason over the facts (the scripts do not reason for you)**
   - Script outputs contain **facts, not conclusions**
     (`active_api_schema_reference`, `derived_graph_diagnostics`,
     `derived_log_diagnostics` with `mechanism_hint`, `key_errors_and_events`,
     `discovered_entities`, `audit_resource_actions`). Nothing is pre-ranked as
     a root cause.
   - **Check the whole admission and execution pipeline (stages 1–6)** — do not
     stop at the first symptom if another independent blocker exists. **For
     every Workload in the request or `workload_timeline` /
     `discovered_entities`, state its terminal state** (`Pending`, `Admitted`,
     `Evicted: <reason>`, `Requeued <n>/<limit>`, `Deactivated`, `Finished`,
     `Deleted by <owner cascade | TTL | retention policy>`) **and explain each
     terminal event.** A Workload deleted via its Job's `ownerReferences` (user
     delete, `ttlSecondsAfterFinished`, or parent JobSet) is the Job's own
     lifecycle, not a Kueue retention defect — report it as why the object is
     gone, not as an `RC<n>`. Consult the
     [Documentation catalog](references/doc-links.md) for the full per-stage
     upstream Kueue and GKE remediation links and section titles:
     1. **Object chain**: Job/JobSet/LWS → Workload → `spec.queueName` →
        `LocalQueue` (exists, `Active`) → `ClusterQueue` (exists, `Active`) →
        `Cohort` (see
        [Troubleshooting Jobs](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_jobs/)
        and
        [Troubleshooting Queues](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_queues/)).
     2. **Quota and cohort sharing**: requests per pod set × count vs
        `nominalQuota`, borrowing (`lendingLimit`/`borrowingLimit`, cohort quota
        layout, `reclaimWithinCohort` / `fairSharing`), `queueingStrategy`
        ordering, and GPU/TPU reservation alignment (see
        [ClusterQueue](https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/),
        [Cohort](https://kueue.sigs.k8s.io/docs/concepts/cohort/), and
        [Preemption](https://kueue.sigs.k8s.io/docs/concepts/preemption/)).
     3. **Flavor assignment per pod set**: `ResourceFlavor`
        `nodeLabels`/`nodeTaints`/tolerations, `topologyName` vs the pod set's
        topology request and across `resourceGroups`, and
        `resources.transformations`. Per "Implicit TAS and mixed-flavor
        ClusterQueues" in
        [Topology Aware Scheduling](https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/),
        in a `ClusterQueue` combining TAS and non-TAS flavors, implicit TAS is
        disabled (unannotated pod sets can use only non-TAS flavors and
        TAS-annotated pod sets can use only TAS flavors), and a single pod set
        cannot mix TAS and non-TAS flavors across its requested resources.
     4. **Admission checks**: `AdmissionCheck` `Active` and attached to the
        `ClusterQueue`, DWS `ProvisioningRequest` / retry configuration,
        reservation/DWS fallback, and external controllers (see
        [ProvisioningRequest AdmissionCheck](https://kueue.sigs.k8s.io/docs/concepts/admission_check/provisioning_request/)
        and
        [Run a large-scale workload with flex-start with queued provisioning](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/provisioningrequest.md.txt)).
     5. **After admission**: scheduling gates (`kueue.x-k8s.io/topology` or
        external gates; see
        [Troubleshooting Pods](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_pods/)),
        `waitForPodsReady` (`PodsReadyTimeout`, `RequeuingLimitExceeded`),
        preemption, container/Job failure policies (`backoffLimit`,
        `backoffLimitPerIndex`, `maxFailedIndexes`, `podFailurePolicy`), Cluster
        Autoscaler `noScaleUp` / stockouts, TPU slice provisioning, and GKE node
        `NotReady` (`NetworkPluginNotReady` / CNI not initialized — follow
        "Troubleshoot network connectivity" in
        [Troubleshoot nodes with the NotReady status in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/node-notready.md.txt)
        or hand off to `gke-node-notready`).
     6. **Controller health and configuration**: `KueueConfiguration`
        (`kueue-manager-config` ConfigMap) fields (`integrations.frameworks`,
        `manageJobsWithoutQueueName`, `featureGates`,
        `resources.transformations`, `objectRetentionPolicies`), client-side
        rate limiting vs `kube-apiserver` overload (HTTP 429/503, webhook
        timeouts), controller restarts, and audit-logged create/delete/patch of
        any object in the chain.
   - **Synthesize one unified Root Cause (`RC<n>`) per underlying defect — do
     not fragment symptoms:**
     - If multiple workloads fail because of the **same underlying configuration
       defect** on a `ClusterQueue` or `ResourceFlavor`, report that single
       underlying defect as one `RC1` rather than splitting each workload's
       symptom into separate root causes with conflicting fixes.
     - If an earlier event in the same layer is the **upstream precursor** of
       the current blocker, explain the causal chain together rather than
       inventing redundant competing root causes for the same failure chain.
     - Conversely, when two **genuinely independent** defects both affect the
       workload (e.g. a Kueue configuration defect *and* an independent external
       control-plane/capacity failure, or two independent Kueue configuration
       defects across different stages such as flavor/topology wiring and
       `AdmissionCheck` attachment), report each as its own `RC<n>` rather than
       dropping one or misclassifying a missing Kueue configuration field as a
       `Kueue defect`.
   - **Defaults and uninvolved settings are not root causes — configured
     mechanisms with terminal events are:** a field left at its Kueue default
     (such as `waitForPodsReady` omitted,
     `waitForPodsReady.requeuingStrategy.backoffLimitCount` unset/`null`, or
     default `leaderElection` timings) is **not** a root cause (`RC<n>`). When a
     workload repeatedly triggers a Kueue mechanism (such as `PodsReadyTimeout`
     requeuing) because its own pods or Job failure policy never reach
     completion or terminal failure, the single root cause (`RC1`) is the
     workload's failure/completion configuration (`Outside Kueue: workload
     spec`), while Kueue's default retry/requeue setting is background context.
     Do **not** propose `waitForPodsReady`, `leaderElection`, or
     `integrations.frameworks` ConfigMap changes as "hardening" on quota,
     cohort, preemption, TAS, workload-spec, or infrastructure incidents.
     **Conversely, a mechanism that is explicitly configured**
     (`waitForPodsReady.timeout`, `requeuingStrategy.backoffLimitCount`,
     `objectRetentionPolicies`, preemption policies) **and has a terminal event
     in the evidence** (`Evicted` with reason `PodsReadyTimeout`, `Deactivated`
     / `RequeuingLimitExceeded`, `Preempted`, or deletion of deactivated
     `Workload` objects by `objectRetentionPolicies.workloads`, which per
     "Notes" in
     [Setup object retention policy](https://kueue.sigs.k8s.io/docs/tasks/manage/setup_object_retention_policy/)
     may cascade to objects not created by Kueue such as a `JobSet`) **is part
     of the causal chain and must be reported** — as its own `RC<n>` when the
     configured value causes the failure, or as an explicit stage of the chain
     otherwise. "Working as designed" never justifies leaving such an event
     unexplained.
   - **Every root cause must be backed by a verbatim quote** (from
     `status.conditions`, `spec`, `Events`, or controller/audit logs) reproduced
     in `#### Observations`. **A quota or capacity claim additionally needs a
     rejection fact for that same resource** — `insufficient quota` /
     `insufficient unused quota` in a Workload condition or controller log,
     `NotTriggerScaleUp`, or a `Pending` / `FailedScheduling` reason naming the
     resource. A `nominalQuota` smaller or larger than node allocatable,
     `nominalQuota: 0` on a queue that borrows, `blockAdmission: false`, or a
     short `ttlSecondsAfterFinished` is an **observation**, not a root cause,
     unless such a rejection fact ties it to the failure.
   - **Scope boundary — classify the causal layer (`#### Scope`) before writing
     Root Cause or Remediation:** Declare one of `Kueue configuration` |
     `Kueue defect` |
     `Outside Kueue: <capacity | node | control plane | workload spec>` |
     `Mixed: <layers>` | `Undetermined: <what is missing>`. Attribute each
     blocking fact by **which component produced the signal and which object
     owns the field**, not by how the symptom looks:
     1. **Locate the blocking stage(s) in the pipeline** (stages 1–6):
        - Stages 1–4 (queue chain, quota/cohort layout, flavor/TAS assignment,
          admission check wiring) are decided by Kueue from Kueue objects
          (`Kueue configuration`, or `Kueue defect` if Kueue contradicts its
          documented behavior for the detected version).
        - Stage 5 (after `Admitted=True`) is decided by kube-scheduler, kubelet,
          node provisioner / autoscaler, admission-check controllers, and the
          workload's own pods. A blocker there is **`Outside Kueue`** unless a
          Kueue configuration caused it (e.g. `ResourceFlavor.spec.nodeLabels`
          pointing at non-existent labels, a stranded `kueue.x-k8s.io/topology`
          scheduling gate, or cohort `nominalQuota` mismatched to cluster
          capacity).
        - **Cohort `nominalQuota`, borrowing, and Fair Sharing:** Per
          [ClusterQueue](https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/)
          and [Cohort](https://kueue.sigs.k8s.io/docs/concepts/cohort/), queues
          in a cohort can borrow unused `nominalQuota` subject to `lendingLimit`
          (which caps how much unused `nominalQuota` a member lends) and
          `borrowingLimit`. Compare cohort `nominalQuota` declarations,
          `audit_resource_actions`, and Fair Sharing / preemption settings
          against observed admission, preemption, or scheduling events. A queue
          with `nominalQuota: 0` is a valid borrow-only design, not a defect on
          its own, and `#### Remediation` must modify only the resources and
          fields implicated by the rejection facts. Per "ClusterQueue share
          value" in
          [Preemption](https://kueue.sigs.k8s.io/docs/concepts/preemption/),
          Kueue summarizes borrowed usage in
          `.status.fairSharing.weightedShare` weighted by
          `.spec.fairSharing.weight` (higher weight lowers share value for the
          same borrowed usage; Kueue admits lowest share first and preempts
          highest share first; when cohort members configure different
          `.spec.fairSharing.weight` values, report each member's weight and how
          Fair Sharing weights their borrowed usage in `#### Observations`).
        - Stage 6 (controller health) splits by **signal provenance**: facts
          tagged `source side: kueue-client` reflect client-side rate limiting
          controlled by `clientConnection.qps` and `clientConnection.burst` in
          the "ClientConnection" section of the `KueueConfiguration` reference;
          facts tagged `source side: apiserver` (HTTP 429/503, API Priority and
          Fairness, webhook/etcd timeouts) belong to
          **`Outside Kueue: control plane`** (see
          [Collect and view control plane metrics](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/control-plane-metrics.md.txt)).
     2. **Independent layers → `Mixed`.** If both a Kueue-side blocker and an
        external-layer blocker independently affect the workload(s), set
        `#### Scope` to `Mixed: <layers>`, give each layer its own `RC<n>`, and
        include the literal phrase `Outside Kueue` in the external `RC<n>`
        header line (e.g. `- RC2 (Outside Kueue — control plane): ...`). Never
        write `Outside Kueue` in a Kueue-configuration RC header or its
        remediation.
     3. **Never patch across layers.** An `Outside Kueue` RC is remediated on
        the component that owns it (node pool, image, control plane, cloud
        capacity, the Job's own spec). A `Kueue configuration` RC is remediated
        on the Kueue object that owns the field.
   - **When evidence is incomplete, use `#### Open Questions` (`OQ<n>`):**
     `BUNDLE_COVERAGE` and `LOG_COVERAGE` state which object kinds and log
     sources are present and absent. If the runtime status objects and logs
     needed to confirm why a stage failed are absent from both (e.g. a static
     manifest-only bundle or a logs-only archive lacking manifests), do **not**
     assert an unverified guess as a definite `RC<n>`: record `OQ1` under
     `#### Open Questions` as `Basis:` (what is missing), `Candidates:` (each
     with its conditional remediation), `Discriminator:` (the deciding
     observation), then the read-only `Collect:` command last.
   - **Commit when the evidence decides — do not hedge a decided finding.** When
     runtime evidence (conditions, events, or logs) settles the cause, write a
     definite `RC<n>` under `#### Root Cause` with one concrete fix under
     `#### Remediation`, without listing "or possibly ..." alternatives next to
     it. Reserve `OQ<n>` for questions the available evidence genuinely cannot
     answer **and** that name one read-only command to answer them. If the
     first-listed candidate is the only one with a rejection or terminal fact in
     the evidence, it is the `RC<n>`, not an `OQ<n>`. Explicitly configured
     mechanisms with terminal events belong in the causal chain, not under
     `#### Ruled Out`.

3. **Step 3 — evidence and schema validation**
   - Number confirmed root causes `RC1`, `RC2`, … and give a matching
     remediation entry for each `RC<n>` under `#### Remediation` (conditional
     fixes for unresolved candidates go under `Candidates:` of their `OQ<n>`):
     - For a **Kueue configuration** RC: link the official Kueue or GKE
       documentation section from
       [Documentation catalog](references/doc-links.md) alongside the exact
       `kubectl` command or YAML manifest in the detected API version,
       preserving all `active_api_schema_reference` invariants and covering
       every resource requested by the workload's PodSets.
       `KueueConfiguration` is not an API resource: tell the user to follow
       "Install a custom-configured released version" and "Change the feature
       gates configuration" in
       [Installation](https://kueue.sigs.k8s.io/docs/getting-started/installation/)
       (or the GKE sections in
       [Documentation catalog](references/doc-links.md)) to edit
       `data.controller_manager_config.yaml` (`kind: Configuration`) in the
       `kueue-manager-config` ConfigMap and restart the
       `kueue-controller-manager` Deployment, showing the complete
       `controller_manager_config.yaml` document rather than a partial patch.
     - For a **Kueue defect** RC: do not invent unsupported workarounds that
       break workload semantics. Tell the user to collect snapshot and
       controller log evidence, check or file an upstream issue at
       `https://github.com/kubernetes-sigs/kueue/issues` or contact Cloud
       Customer Care per
       [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt),
       and state the confirmation signal (`Confirm by checking that ...`).
     - For an **Outside Kueue** RC: **never** propose a `ClusterQueue`,
       `ResourceFlavor`, or `KueueConfiguration` patch to mask an external
       infrastructure failure. State the external-layer remediation (linking the
       relevant GKE guide from [Documentation catalog](references/doc-links.md)
       or handing off to `gke-node-notready`,
       `gke-workload-scaling-troubleshooting`,
       `gke-ai-troubleshooting-tpu-reservation-stockout`, or
       `gke-ai-troubleshooting-jobset-interruption`), state the **confirmation
       signal** (`Confirm by checking that <object condition> transitions to
       <expected state>`), and for persistent control-plane or hardware issues
       advise contacting Cloud Customer Care per
       [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt).
   - In `#### Observations`, wrap a multi-word phrase in backticks **only** when
     it is a verbatim substring of tool output (synthesised summaries go in
     plain text).
   - Save the draft beside the ledger and run `scripts/validate_report.py` with
     `--draft-file <draft.md> --ledger-path <ledger>`. It passes only with
     `passed: true` (exit 0); exit 2 means `ledger_missing` (wrong ledger path)
     or a non-empty `missing_headers`, `uninspected_graph_objects`,
     `fabricated_quotes`, `remediation_gaps`, `open_question_gaps`,
     `config_remediation_errors`, `unknown_kubectl_resources`, or
     `schema_warnings`; fix those and re-run once. `unsupported_root_causes` is
     advisory: tie any listed `RC<n>` to a rejection/terminal signal in
     `#### Observations` or move it to `#### Open Questions`; do not re-run the
     validator for it.
   - Finish with:

```markdown
### Diagnostic Summary
#### Scope
<Kueue configuration | Kueue defect | Outside Kueue: <layer> | Mixed>
#### Observations
- Verbatim evidence from `status.conditions`, `spec`, `Events`, or
  controller/audit logs, with timestamps for historical facts.
#### Root Cause
- RC1: <precise root cause and causal mechanism>, tied to the evidence above.
- RC2 (Outside Kueue — <layer>): <if Mixed / external layer, state the external
  root cause>.
#### Open Questions
- none (or `OQ1` with `Basis:`, `Candidates:` with conditional remediation,
  `Discriminator:`, then a read-only `Collect:` command, when data is absent).
#### Ruled Out
- Brief list of secondary observations, resolved/precursor events, or
  non-blocking settings ruled out as root causes.
#### Remediation
- RC1: link the official documentation section describing the fix (plus the
  exact `kubectl` command or YAML manifest with that link for Kueue RCs), or
  external-layer remediation + confirmation signal (for external RCs).
- RC2: ...
```
