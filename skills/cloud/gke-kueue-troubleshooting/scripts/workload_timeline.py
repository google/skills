"""Per-workload lifecycle timeline derived from Kubernetes Events and Workload status.

Facts only: the ordered milestone list of each Workload (quota reservation,
admission, evictions with their reason, preemption, requeue count, deactivation,
finish, deletion) and whether the Workload object itself is still present in the
snapshot. Nothing here ranks explanations; the reader decides which terminal
event
matters. Reason names come from Kueue's documented event and metric vocabulary
(https://kueue.sigs.k8s.io/docs/concepts/workload/,
https://kueue.sigs.k8s.io/docs/reference/metrics/).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import k8s_objects as k8s

# Event reasons recorded as lifecycle milestones. Everything else stays in the
# generic WARNING_EVENT list. ``Evicted`` is a prefix match (EvictedDueTo<X>).
_MILESTONE_REASONS = (
    "Pending",
    "QuotaReserved",
    "Admitted",
    "Preempted",
    "PreemptedWorkload",
    "Finished",
    "Deactivated",
    "Requeued",
)
_EVICTED_RE = re.compile(r"^Evicted(?:DueTo)?(?P<reason>[A-Za-z]*)$")
# EvictedDueToDeactivatedDueToRequeuingLimitExceeded ->
# ("Deactivated", "RequeuingLimitExceeded").
_CAUSE_RE = re.compile(r"^(?P<reason>[A-Za-z]+?)DueTo(?P<detail>[A-Za-z]+)$")
_EVICT_CITE = "https://kueue.sigs.k8s.io/docs/concepts/workload/"
_MAX_WORKLOADS = 8
_MAX_MILESTONES = 14


@dataclasses.dataclass(frozen=True)
class Milestone:
  """Single timestamped lifecycle Event milestone for a Workload."""

  ts: str
  reason: str
  count: int
  message: str


@dataclasses.dataclass
class WorkloadLifecycle:
  """Aggregated lifecycle milestones and current state for a single Workload."""

  ref: str
  milestones: list[Milestone] = dataclasses.field(default_factory=list)
  present: bool = False
  requeue_count: Any = None
  active: Any = None

  def _evictions_and_deactivated(self) -> tuple[dict[str, int], str]:
    """Counts evictions by reason and captures the last deactivation cause."""
    evictions: dict[str, int] = {}
    deactivated = ""
    for m in self.milestones:
      ev = _EVICTED_RE.match(m.reason)
      if not ev:
        continue
      reason = ev.group("reason") or "Unspecified"
      cause = _CAUSE_RE.match(reason)
      if cause:
        reason = cause.group("reason")
        if reason == "Deactivated":
          deactivated = cause.group("detail")
      evictions[reason] = evictions.get(reason, 0) + m.count
    return evictions, deactivated

  def outcome_key(self) -> str:
    """Groups workloads sharing the same terminal outcome shape into one key."""
    evictions, deactivated = self._evictions_and_deactivated()
    last = self.milestones[-1].reason if self.milestones else "none"
    ev_sig = ",".join(f"{k}:{v}" for k, v in sorted(evictions.items()))
    return (
        f"workload-lifecycle:present={self.present}:ev={ev_sig}"
        f":deact={deactivated}:active={self.active}:last={last}"
    )

  def summary(self) -> str:
    """Formats a one-line summary of admissions, evictions, and state."""
    admitted = sum(m.count for m in self.milestones if m.reason == "Admitted")
    evictions, deactivated = self._evictions_and_deactivated()
    last = self.milestones[-1] if self.milestones else None
    parts = [
        f"admitted={admitted}",
        "evicted=" + (str(evictions) if evictions else "{}"),
    ]
    if deactivated:
      parts.append(f"deactivated={deactivated}")
    if self.requeue_count is not None:
      parts.append(f"requeueState.count={self.requeue_count}")
    if self.active is not None:
      parts.append(f"spec.active={self.active}")
    parts.append(f"last={last.reason}@{last.ts}" if last else "last=none")
    parts.append(
        "object_present="
        + ("yes" if self.present else "no (deleted or outside snapshot)")
    )
    return " ".join(parts)


def _is_milestone(reason: str) -> bool:
  return reason in _MILESTONE_REASONS or bool(_EVICTED_RE.match(reason))


def collect_lifecycles(ctx) -> list[WorkloadLifecycle]:
  """Builds one lifecycle per Workload seen in Events or present in the snapshot."""
  by_ref: dict[str, WorkloadLifecycle] = {}
  for wl in ctx.workloads:
    lc = by_ref.setdefault(
        f"{k8s.namespace(wl)}/{k8s.name(wl)}",
        WorkloadLifecycle(ref=f"{k8s.namespace(wl)}/{k8s.name(wl)}"),
    )
    lc.present = True
    rq = k8s.status(wl).get("requeueState")
    lc.requeue_count = (
        k8s.as_dict(rq).get("count") if isinstance(rq, dict) else None
    )
    lc.active = k8s.spec(wl).get("active")
  for ev in ctx.events:
    obj = k8s.as_dict(ev.get("involvedObject"))
    if str(obj.get("kind", "")) != "Workload" or not obj.get("name"):
      continue
    reason = str(ev.get("reason", ""))
    if not _is_milestone(reason):
      continue
    ref = f"{obj.get('namespace', '')}/{obj.get('name')}"
    lc = by_ref.setdefault(ref, WorkloadLifecycle(ref=ref))
    count = (
        ev.get("count")
        if isinstance(ev.get("count"), int) and ev.get("count") > 0
        else 1
    )
    lc.milestones.append(
        Milestone(
            k8s.event_timestamp(ev),
            reason,
            count,
            str(ev.get("message", ""))[:160],
        )
    )
  for lc in by_ref.values():
    lc.milestones.sort(key=lambda m: m.ts)
  # Workloads with evictions / deactivation first, then by milestone count.
  return sorted(
      by_ref.values(),
      key=lambda lc: (
          -sum(1 for m in lc.milestones if _EVICTED_RE.match(m.reason)),
          -len(lc.milestones),
          lc.ref,
      ),
  )


def _has_lifecycle(lc: WorkloadLifecycle) -> bool:
  """A Workload earns a timeline once it moved past a single Pending/QuotaReserved event or had a terminal event."""
  reasons = {m.reason for m in lc.milestones}
  terminal = any(
      _EVICTED_RE.match(r) or r in ("Finished", "Deactivated", "Preempted")
      for r in reasons
  )
  return (
      terminal
      or len(reasons - {"Pending", "QuotaReserved"}) >= 1
      and len(lc.milestones) >= 2
  )


def emit_workload_timeline(ctx: Any) -> None:
  """Emits ordered lifecycle milestones and summaries per Workload (1g)."""
  lifecycles = [lc for lc in collect_lifecycles(ctx) if _has_lifecycle(lc)]
  if not lifecycles:
    return
  for lc in lifecycles[:_MAX_WORKLOADS]:
    shown = lc.milestones[-_MAX_MILESTONES:]
    omitted = len(lc.milestones) - len(shown)
    chain = " -> ".join(
        f"{m.ts} {m.reason}" + (f"(x{m.count})" if m.count > 1 else "")
        for m in shown
    )
    # Untagged: chain is context; LIFECYCLE / TERMINAL_EVENT carry tagged facts.
    ctx.add(
        None,
        f"WORKLOAD_TIMELINE: [Workload/{lc.ref}] "
        + (f"({omitted} earlier milestones omitted) " if omitted > 0 else "")
        + chain,
    )
    has_terminal = any(
        _EVICTED_RE.match(m.reason) or m.reason in ("Finished", "Deactivated")
        for m in shown
    )
    ctx.add(
        lc.outcome_key() if (has_terminal or not lc.present) else None,
        f"WORKLOAD_LIFECYCLE: [Workload/{lc.ref}] {lc.summary()}",
    )
    for m in shown:
      if _EVICTED_RE.match(m.reason) or m.reason in ("Finished", "Deactivated"):
        # WORKLOAD_LIFECYCLE already tags the terminal outcome; keep verbatim
        # event lines untagged.
        ctx.add(
            None,
            f"WORKLOAD_TERMINAL_EVENT: [Workload/{lc.ref}] {m.ts} {m.reason}:"
            f" {m.message} (event reason vocabulary: {_EVICT_CITE})",
        )
  if len(lifecycles) > _MAX_WORKLOADS:
    ctx.add(
        None,
        f"WORKLOAD_TIMELINE: ... {len(lifecycles) - _MAX_WORKLOADS} more"
        " Workloads omitted (fewest evictions first)",
    )
