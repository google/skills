"""Fair-sharing arithmetic per cohort: weights, weightedShare, and borrowed vs cohort lendable quota.

For every cohort whose members configure ``spec.fairSharing`` or report
``status.fairSharing``, restate per ClusterQueue: weight (default 1 when
omitted),
reported weightedShare, current reservation/usage and borrowed amount per
resource,
nominal quota, lendingLimit, and the cohort's lendable total per resource. Per
https://kueue.sigs.k8s.io/docs/concepts/preemption/ ("ClusterQueue share
value"),
Kueue summarizes a ClusterQueue's usage of borrowed resources in a single
numeric
share value weighted by ``.spec.fairSharing.weight`` (reported in
``.status.fairSharing.weightedShare``); ranking and verdicts are left to the
reader.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import k8s_objects as k8s
import report_output

_PREEMPTION_DOC = "https://kueue.sigs.k8s.io/docs/concepts/preemption/"
_CQ_DOC = "https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/"


@dataclasses.dataclass
class QueueShare:
  """Per-ClusterQueue fair-sharing weights, quotas, and usage totals."""

  name: str
  weight: Any
  weighted_share: Any
  has_fair_sharing: bool
  reclaim: str
  nominal: dict[str, float] = dataclasses.field(default_factory=dict)
  lendable: dict[str, float] = dataclasses.field(default_factory=dict)
  usage: dict[str, float] = dataclasses.field(default_factory=dict)
  borrowed: dict[str, float] = dataclasses.field(default_factory=dict)
  unparsed: list[str] = dataclasses.field(default_factory=list)


def _add(
    d: dict[str, float], key: str, value: Any, unparsed: list[str], label: str
) -> None:
  """Adds a parsed Kubernetes quantity to `d[key]` or records `unparsed`."""
  q = report_output.parse_quantity(value) if value is not None else None
  if value is not None and q is None:
    unparsed.append(f"{label}={value!r}")
  elif q is not None:
    d[key] = d.get(key, 0.0) + q


def _queue_share(cq: dict[str, Any]) -> QueueShare:
  """Extracts fair-sharing weights, quotas, usage, and borrowed totals."""
  spec, status = k8s.spec(cq), k8s.status(cq)
  fs_spec, fs_status = k8s.as_dict(spec.get("fairSharing")), k8s.as_dict(
      status.get("fairSharing")
  )
  reclaim = str(
      k8s.as_dict(spec.get("preemption")).get("reclaimWithinCohort") or "Never"
  )
  qs = QueueShare(
      name=k8s.name(cq),
      weight=fs_spec.get("weight"),
      weighted_share=fs_status.get("weightedShare"),
      has_fair_sharing=bool(fs_spec or fs_status),
      reclaim=reclaim,
  )
  for _, fl, res in k8s.flavor_quotas(cq):
    r = str(res.get("name", ""))
    _add(
        qs.nominal,
        r,
        res.get("nominalQuota"),
        qs.unparsed,
        f"{fl.get('name')}.{r}.nominalQuota",
    )
    lend = res.get("lendingLimit")
    nominal = report_output.parse_quantity(res.get("nominalQuota"))
    lend_q = report_output.parse_quantity(lend) if lend is not None else nominal
    if lend is not None and lend_q is None:
      qs.unparsed.append(f"{fl.get('name')}.{r}.lendingLimit={lend!r}")
    if lend_q is not None and nominal is not None:
      qs.lendable[r] = qs.lendable.get(r, 0.0) + min(lend_q, nominal)
  # Read flavorsReservation (falling back to flavorsUsage) from status.
  for fu in k8s.dict_items(
      status.get("flavorsReservation") or status.get("flavorsUsage")
  ):
    for ru in k8s.dict_items(fu.get("resources")):
      r = str(ru.get("name", ""))
      _add(
          qs.usage,
          r,
          ru.get("total"),
          qs.unparsed,
          f"{fu.get('name')}.{r}.total",
      )
      _add(
          qs.borrowed,
          r,
          ru.get("borrowed"),
          qs.unparsed,
          f"{fu.get('name')}.{r}.borrowed",
      )
  return qs


def _fmt(d: dict[str, float], resources: list[str]) -> str:
  """Formats resource totals in `d` across `resources` as `r=val` pairs."""
  return ", ".join(
      f"{r}={report_output.fmt_quantity(d.get(r, 0.0), r)}" for r in resources
  )


def _format_share_row(
    s: QueueShare, resources: list[str], cohort_lendable: dict[str, float]
) -> str:
  """Formats one ClusterQueue's fair-sharing metrics and borrow ratios."""
  ratios: list[str] = []
  for r in resources:
    b = s.borrowed.get(r, 0.0)
    lend = cohort_lendable.get(r, 0.0)
    if b > 0 and lend > 0:
      b_fmt = report_output.fmt_quantity(b, r)
      lend_fmt = report_output.fmt_quantity(lend, r)
      ratios.append(f"{r}: {b_fmt}/{lend_fmt}={1000 * b / lend:.0f}‰")
  return (
      f"{s.name}:"
      f" weight={s.weight if s.weight is not None else 'unset(1)'},"
      f" status.weightedShare={s.weighted_share},"
      f" reclaimWithinCohort={s.reclaim},"
      f" nominal[{_fmt(s.nominal, resources)}],"
      f" lendable[{_fmt(s.lendable, resources)}],"
      f" usage[{_fmt(s.usage, resources)}],"
      f" borrowed[{_fmt(s.borrowed, resources)}]"
      + (f", borrowed/cohortLendable {{{'; '.join(ratios)}}}" if ratios else "")
      + (f", unparsed={s.unparsed[:2]}" if s.unparsed else "")
  )


def emit_fair_sharing_arithmetic(ctx: Any) -> None:
  """Emits per-cohort fair-sharing weights and quota arithmetic (4e)."""
  for cohort, members in sorted(ctx.cohort_map.items()):
    shares = sorted((_queue_share(cq) for cq in members), key=lambda q: q.name)
    if len(shares) < 2 or not any(s.has_fair_sharing for s in shares):
      continue
    resource_set: set[str] = set()
    for s in shares:
      resource_set.update(s.nominal)
      resource_set.update(s.borrowed)
    resources = sorted(resource_set)
    cohort_lendable = {
        r: sum(s.lendable.get(r, 0.0) for s in shares) for r in resources
    }
    rows = [_format_share_row(s, resources, cohort_lendable) for s in shares]
    w_str = ", ".join(
        f"{s.name}: {s.weight if s.weight is not None else 'unset(1)'}"
        for s in shares
    )
    ctx.add(
        f"fair-sharing:{cohort}",
        f"FAIR_SHARING_ARITHMETIC (cohort {cohort}):"
        f" fairSharing.weight=[{w_str}]; cohort lendable per"
        f" resource [{_fmt(cohort_lendable, resources)}] (sum over members of"
        f" min(lendingLimit, nominalQuota); {_CQ_DOC}). Members: "
        + " | ".join(rows)
        + ". Kueue summarizes each ClusterQueue's borrowed resource usage in a"
        " share value weighted by .spec.fairSharing.weight and reported in"
        f" .status.fairSharing.weightedShare ({_PREEMPTION_DOC}); a higher"
        " weight lowers the share for the same borrowed amount, and a member"
        " that borrows nothing has share 0. During admission Kueue prefers"
        " the ClusterQueue with the lowest share, and during preemption it"
        " targets workloads in the ClusterQueue with the highest share. Fair"
        " Sharing preemption works with withinClusterQueue and"
        f" reclaimWithinCohort ({_PREEMPTION_DOC}), not borrowWithinCohort.",
    )
