"""Topology-aware scheduling facts: how the nodes in the snapshot populate each flavor's topology domains.

For every ResourceFlavor with ``spec.topologyName`` and a matching Topology
object,
count — among the nodes that carry the flavor's ``nodeLabels`` — the distinct
domains per Topology level and the largest domain at each level. These are the
numbers Kueue's TAS snapshot works from when it reports ``doesn't allow to fit``
or ``allows to fit only N out of M``; the facts only restate them, they do not
say
whether a given pod set fits.
"""

from __future__ import annotations

from typing import Any

import k8s_objects as k8s

_TAS_DOC = "https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/"


def _topology_levels(topology: dict[str, Any]) -> list[str]:
  return [
      str(lvl.get("nodeLabel"))
      for lvl in k8s.dict_items(k8s.spec(topology).get("levels"))
      if lvl.get("nodeLabel")
  ]


def _domains_per_level(
    matching: list[dict[str, Any]], levels: list[str]
) -> list[str]:
  """Summarizes distinct and largest TAS domains per level across `matching`.

  A node enters the TAS domain count only if it carries all
  `ResourceFlavor.spec.nodeLabels` and every label key in
  `Topology.spec.levels`, while `nodes without the label` counts how many
  `nodeLabels`-matching nodes lack that specific level key.

  Args:
    matching: Snapshot Node objects matching `ResourceFlavor.spec.nodeLabels`.
    levels: Ordered `nodeLabel` keys from `Topology.spec.levels`.

  Returns:
    Formatted per-level domain summary strings.
  """
  tas_eligible = [
      n
      for n in matching
      if all(k8s.labels(n).get(lbl) is not None for lbl in levels)
  ]
  rows: list[str] = []
  for label in levels:
    counts: dict[str, int] = {}
    for n in tas_eligible:
      value = str(k8s.labels(n).get(label))
      counts[value] = counts.get(value, 0) + 1
    missing = sum(1 for n in matching if k8s.labels(n).get(label) is None)
    largest = max(counts.values()) if counts else 0
    rows.append(
        f"{label}: {len(counts)} domain(s), largest={largest} node(s)"
        + (f", nodes without the label={missing}" if missing else "")
    )
  return rows


def emit_topology_domains(ctx: Any) -> None:
  """Emits matching node counts and per-level TAS domain layouts (7b)."""
  topologies = {k8s.name(t): t for t in ctx.by_kind.get("Topology", [])}
  for rf in ctx.rfs:
    spec = k8s.spec(rf)
    topo_name = spec.get("topologyName")
    if not topo_name:
      continue
    labels = k8s.as_dict(spec.get("nodeLabels"))
    matching = [
        n
        for n in ctx.nodes
        if all(k8s.labels(n).get(k) == v for k, v in labels.items())
    ]
    topology = topologies.get(str(topo_name))
    head = (
        f"TAS_DOMAIN_FACTS ({k8s.name(rf)} -> Topology/{topo_name}):"
        f" {len(matching)} of {len(ctx.nodes)} snapshot nodes match"
        f" nodeLabels={labels or '{}'}"
    )
    if topology is None:
      ctx.add(
          f"tas-domains:{k8s.name(rf)}",
          head
          + f"; Topology object '{topo_name}' is absent from the snapshot, so"
          " the levels cannot be evaluated.",
      )
      continue
    levels = _topology_levels(topology)
    if not matching:
      ctx.add(
          f"tas-domains:{k8s.name(rf)}",
          head
          + f"; levels={levels}; with no matching node the TAS snapshot for"
          " this flavor has no domains at any level (nodes that an"
          " autoscaler or ProvisioningRequest would add later are not in the"
          f" snapshot) ({_TAS_DOC}).",
      )
      continue
    ctx.add(
        f"tas-domains:{k8s.name(rf)}",
        head
        + f"; domains per level among matching nodes ({_TAS_DOC}):"
        f" {'; '.join(_domains_per_level(matching, levels))}. A pod set with"
        " a required level fits only inside one domain of that level;"
        " 'largest' bounds how many single-node pods it can hold there"
        f" ({_TAS_DOC}).",
    )
