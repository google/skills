"""Controller-message signatures: which Kueue code path emits a message and what it states.

A signature maps a literal that the Kueue controller (or a Kueue Event) emits to
the source file that emits it, the mechanism it reports, the documentation page
that describes that mechanism, and the next read-only check. Scanning counts
matches per signature and keeps the first few distinct message variants. The
emitter turns each hit into one ``CONTROLLER_LOG_FACT`` whose ``mechanism_hint``
describes the mechanism, not the incident: whether the mechanism explains the
incident is
for the reader to decide from the rest of the evidence.

Every ``source`` literal is verified against the pinned Kueue release by the
unit tests (``KUEUE_LOG_LITERALS``) when
``GKE_KUEUE_TROUBLESHOOTING_TEST_KUEUE_SOURCE`` is set. Every signature links to
an official public upstream documentation page on
``https://kueue.sigs.k8s.io/docs/``.
"""

from __future__ import annotations

import dataclasses
import re

_DOCS = "https://kueue.sigs.k8s.io/docs"
_MAX_VARIANTS = 3


@dataclasses.dataclass(frozen=True)
class LogSignature:
  """Controller log or Event message pattern and its documented mechanism."""

  key: str
  pattern: re.Pattern[str]
  # Kueue source path (verified at kueue_schema.KUEUE_SOURCE_REF by unit tests).
  source: str
  symbol: str  # function / constant emitting the literal
  mechanism: str  # what the message states, in the documentation's own terms
  next_check: str  # the one read-only check that discriminates the cause
  doc: str = ""  # official upstream documentation page
  src_only: bool = False


@dataclasses.dataclass
class SignatureHits:
  count: int = 0
  first_ts: str = ""
  last_ts: str = ""
  variants: list[str] = dataclasses.field(default_factory=list)


SIGNATURES: tuple[LogSignature, ...] = (
    LogSignature(
        key="flavor-assignment-per-podset",
        pattern=re.compile(
            r"couldn't assign flavors to pod set"
            r" \"?(?P<podset>[A-Za-z0-9_.-]+)\"?:?"
        ),
        source="pkg/scheduler/flavorassigner/flavorassigner.go",
        symbol="Assignment.Message",
        mechanism=(
            "flavor assignment failed for the named pod set; Kueue assigns"
            " flavors per pod set (or podSetGroupName group), and within one"
            " pod set all resources covered by the same resourceGroup receive"
            " the same flavor; all pod sets must be assigned flavors for the"
            " Workload to reserve quota"
        ),
        next_check=(
            "compare each pod set's nodeSelector / topology annotations and"
            " resource requests with ResourceFlavor.spec.nodeLabels and"
            " topologyName of every flavor in the ClusterQueue's resourceGroups"
        ),
        doc=f"{_DOCS}/concepts/cluster_queue/#resource-groups",
    ),
    LogSignature(
        key="quota-exceeds-maximum-capacity",
        pattern=re.compile(
            r"insufficient quota for (?P<resource>[a-z0-9._/-]+) in flavor"
            r" (?P<flavor>[A-Za-z0-9_.-]+),.*?maximum capacity"
        ),
        source="pkg/scheduler/flavorassigner/flavorassigner.go",
        symbol="fitsResourceQuota",
        mechanism=(
            "the request exceeds the flavor's maximum capacity (nominalQuota"
            " plus what the cohort can lend within borrowingLimit)"
        ),
        next_check=(
            "sum the pod sets' requests × count for that resource and compare"
            " with nominalQuota + borrowable cohort quota for the flavor"
        ),
        doc=f"{_DOCS}/concepts/cluster_queue/#flavors-and-borrowing-semantics",
    ),
    LogSignature(
        key="quota-temporarily-unavailable",
        pattern=re.compile(
            r"insufficient unused quota for (?P<resource>[a-z0-9._/-]+) in"
            r" flavor (?P<flavor>[A-Za-z0-9_.-]+), (?P<more>[0-9.A-Za-z]+) more"
            r" needed"
        ),
        source="pkg/scheduler/flavorassigner/flavorassigner.go",
        symbol="fitsResourceQuota",
        mechanism=(
            "the request fits the flavor's capacity but currently admitted"
            " workloads hold the quota; admission waits for usage to drop or"
            " for preemption"
        ),
        next_check=(
            "list admitted workloads in the ClusterQueue and its cohort for"
            " that flavor and check the preemption policy that would reclaim"
            " quota"
        ),
        doc=f"{_DOCS}/concepts/cluster_queue/#flavors-and-borrowing-semantics",
    ),
    LogSignature(
        key="tas-no-fit",
        pattern=re.compile(
            r"topology \"?(?P<topology>[A-Za-z0-9_.-]+)\"? doesn't allow to fit"
            r" any of (?P<total>\d+) (?P<unit>pod|slice)"
        ),
        source="pkg/cache/scheduler/tas_flavor_snapshot.go",
        symbol="FindTopologyAssignmentsForFlavor",
        mechanism=(
            "the topology-aware snapshot for the flavor has no domain able to"
            " host even one pod/slice: either no node matches the flavor's"
            " nodeLabels together with every Topology level label, or every"
            " matching node lacks free capacity for one pod"
        ),
        next_check=(
            "count nodes carrying the ResourceFlavor nodeLabels and all"
            " Topology.spec.levels keys, then their allocatable minus usage per"
            " node"
        ),
        doc=f"{_DOCS}/concepts/topology_aware_scheduling/",
    ),
    LogSignature(
        key="tas-partial-fit",
        pattern=re.compile(
            r"topology \"?(?P<topology>[A-Za-z0-9_.-]+)\"? allows to fit only"
            r" (?P<fit>\d+) out of (?P<total>\d+) (?P<unit>pod|slice)"
        ),
        source="pkg/cache/scheduler/tas_flavor_snapshot.go",
        symbol="FindTopologyAssignmentsForFlavor",
        mechanism=(
            "no single domain at the requested topology level has room for the"
            " whole pod set; capacity exists but is spread across domains (for"
            " example nodes split across zones or hosts)"
        ),
        next_check=(
            "group matching nodes by the requested level's label and compute"
            " per-domain free capacity against the pod set's count"
        ),
        doc=f"{_DOCS}/concepts/topology_aware_scheduling/",
    ),
    LogSignature(
        key="preemption-no-candidates",
        pattern=re.compile(
            r"Workload requires preemption, but there are no candidate"
            r" workloads allowed for preemption"
        ),
        source="pkg/scheduler/scheduler.go",
        symbol="schedule",
        mechanism=(
            "the Workload could fit only by preempting, but the ClusterQueue's"
            " preemption policy (withinClusterQueue / reclaimWithinCohort /"
            " borrowWithinCohort, fair-sharing strategies) admits no victim"
        ),
        next_check=(
            "read spec.preemption of the ClusterQueue and the fairSharing"
            " configuration, and compare priorities and borrowing state of the"
            " admitted workloads in the cohort"
        ),
        doc=f"{_DOCS}/concepts/preemption/",
    ),
    LogSignature(
        key="preempted-with-reason",
        pattern=re.compile(
            r"Preempted to accommodate a workload \(UID: [^)]*\) due to"
            r" (?P<reason>[^;]+)"
        ),
        source="pkg/scheduler/preemption/preemption.go",
        symbol="preemptionMessage",
        mechanism=(
            "the Workload was evicted by Kueue's preemptor with the stated"
            " reason (prioritization in the ClusterQueue, reclamation within"
            " the cohort, Fair Sharing within the cohort); the preemptor path"
            " names the ClusterQueue that triggered it"
        ),
        next_check=(
            "map preemptor and preemptee ClusterQueues to their spec.preemption"
            " and nominalQuota/borrowing state at that time"
        ),
        doc=f"{_DOCS}/concepts/preemption/",
    ),
    LogSignature(
        key="pods-ready-timeout-eviction",
        pattern=re.compile(r"Exceeded the PodsReady timeout"),
        source="pkg/controller/core/workload_controller.go",
        symbol="reconcileNotReadyTimeout",
        mechanism=(
            "the Workload was evicted when not all of its pods were Ready"
            " within waitForPodsReady.timeout after admission; it is requeued"
            " according to requeuingStrategy"
        ),
        next_check=(
            "compare the pods' scheduling/image-pull/startup duration with"
            " waitForPodsReady.timeout in the KueueConfiguration ConfigMap"
        ),
        doc=f"{_DOCS}/tasks/manage/setup_wait_for_pods_ready/",
    ),
    LogSignature(
        key="requeuing-limit-exceeded",
        pattern=re.compile(
            r"exceeding the maximum number of re-queuing retries"
        ),
        source="pkg/controller/core/workload_controller.go",
        symbol="reconcileNotReadyTimeout",
        mechanism=(
            "the Workload was deactivated (spec.active=false) after"
            " waitForPodsReady.requeuingStrategy.backoffLimitCount requeues; it"
            " stays out of the queue until reactivated"
        ),
        next_check=(
            "read status.requeueState.count and"
            " requeuingStrategy.backoffLimitCount, then what delayed the pods"
            " at each earlier PodsReady timeout"
        ),
        doc=f"{_DOCS}/tasks/manage/setup_wait_for_pods_ready/",
    ),
    LogSignature(
        key="retention-delete-finished",
        pattern=re.compile(
            r"the retention period has elapsed|Deleted finished workload due to"
            r" elapsed retention"
        ),
        source="pkg/controller/core/workload_controller.go",
        symbol="Reconcile",
        mechanism=(
            "the finished Workload object was deleted by Kueue's"
            " objectRetentionPolicies.workloads.afterFinished"
        ),
        next_check=(
            "read objectRetentionPolicies in the KueueConfiguration ConfigMap"
            " and the Job's own ttlSecondsAfterFinished"
        ),
        doc=f"{_DOCS}/tasks/manage/setup_object_retention_policy/",
    ),
    LogSignature(
        key="tas-level-not-in-topology",
        pattern=re.compile(
            r"Flavor \\?\"(?P<flavor>[A-Za-z0-9_.-]+)\\?\" does not contain the"
            r" requested level"
        ),
        source="pkg/scheduler/flavorassigner/tas_flavorassigner.go",
        symbol="checkPodSetAndFlavorMatchForTAS",
        mechanism=(
            "the pod set requests a topology level"
            " (podset-required/preferred-topology annotation) that the Topology"
            " referenced by this flavor's topologyName does not define in"
            " spec.levels; the flavor is rejected for that pod set before any"
            " node is considered"
        ),
        next_check=(
            "compare the pod set's topology annotation value with"
            " Topology.spec.levels of the flavor's topologyName"
        ),
        doc=f"{_DOCS}/concepts/topology_aware_scheduling/",
    ),
    LogSignature(
        key="tas-flavor-requires-tas-podset",
        pattern=re.compile(
            r"Flavor \\?\"(?P<flavor>[A-Za-z0-9_.-]+)\\?\" supports only"
            r" TopologyAwareScheduling"
        ),
        source="pkg/scheduler/flavorassigner/tas_flavorassigner.go",
        symbol="checkPodSetAndFlavorMatchForTAS",
        mechanism=(
            "the flavor has a topologyName and the ClusterQueue mixes TAS and"
            " non-TAS flavors (so TAS is not implied), so a pod set without a"
            " topology request cannot use this flavor for any resource covered"
            " by that resourceGroup"
        ),
        next_check=(
            "list which pod sets carry a kueue.x-k8s.io/podset-*-topology"
            " annotation and which resourceGroups cover the pod set's requested"
            " resources on TAS vs non-TAS flavors"
        ),
        doc=f"{_DOCS}/concepts/topology_aware_scheduling/",
    ),
    LogSignature(
        key="flavors-considered-nofit",
        pattern=re.compile(
            r"Flavors considered: (?P<detail>[^;\"]*NoFit[^\"]{0,200})"
        ),
        source="pkg/scheduler/scheduler.go",
        symbol="quotaReservedEventMessage",
        mechanism=(
            "a ClusterQueue defines the quotas for the flavors of resources"
            " that it manages, with rules for how the different flavors can be"
            " tried as alternatives"
        ),
        next_check=(
            "compare each listed flavor against the flavor's nodeLabels,"
            " topologyName and quota in the ClusterQueue"
        ),
        doc=f"{_DOCS}/concepts/cluster_queue/",
    ),
    LogSignature(
        key="controller-start",
        pattern=re.compile(
            r"\"msg\":\s*\"(?:Configuration loaded|Successfully loaded"
            r" configuration)\"|\b(?:Configuration loaded|Successfully loaded"
            r" configuration)\b"
        ),
        source="cmd/kueue/main.go",
        symbol="main",
        mechanism=(
            "the controller manager started (or restarted) and loaded its"
            " configuration at these times; the count and timestamps allow"
            " other events to be placed before or after a restart"
        ),
        next_check=(
            "place ConfigMap updates, AdmissionCheck / ProvisioningRequest"
            " state changes and the first admission decisions on the same"
            " timeline as these start times"
        ),
        doc=f"{_DOCS}/getting-started/installation/",
        src_only=False,
    ),
)


def scan_signature_text(
    text: str, hits: dict[str, SignatureHits], ts: str = ""
) -> None:
  """Records every signature that matches `text` (one raw line or message)."""
  for sig in SIGNATURES:
    m = sig.pattern.search(text)
    if not m:
      continue
    h = hits.setdefault(sig.key, SignatureHits())
    h.count += 1
    if ts:
      h.first_ts = min(h.first_ts, ts) if h.first_ts else ts
      h.last_ts = max(h.last_ts, ts) if h.last_ts else ts
    variant = m.group(0)[:160]
    if variant not in h.variants and len(h.variants) < _MAX_VARIANTS:
      h.variants.append(variant)


def _citation(sig: LogSignature) -> str:
  return f"doc: {sig.doc}" if sig.doc else f"doc: {_DOCS}/concepts/"


def emit_signature_facts(
    hits: dict[str, SignatureHits],
) -> list[tuple[str | None, str]]:
  """One fact per matched signature: count, window, message variants, mechanism, next check, citation."""
  facts: list[tuple[str | None, str]] = []
  for sig in SIGNATURES:
    h = hits.get(sig.key)
    if not h:
      continue
    window = (
        f" between {h.first_ts} and {h.last_ts}"
        if h.first_ts and h.last_ts and h.first_ts != h.last_ts
        else (f" at {h.first_ts}" if h.first_ts else "")
    )
    facts.append((
        f"logfact:signature:{sig.key}",
        f"CONTROLLER_LOG_FACT: {h.count} line(s){window} match"
        f" '{h.variants[0]}'"
        + (f" (also: {h.variants[1:]})" if len(h.variants) > 1 else "")
        + f". mechanism_hint: {sig.mechanism}. next_check: {sig.next_check}."
        f" ({_citation(sig)})",
    ))
  return facts
