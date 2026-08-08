"""Graph-based mathematical community detection engine for partitioning WebLogic monoliths into microservices.

This module constructs a class-to-class and class-to-table dependency graph,
assigns weights based on domain cohesion and coupling penalty heuristics, and
runs the Louvain community detection algorithm (via NetworkX) to find clean
service boundaries.

It incorporates specific architectural guidelines:
1. "God Glue" (Shared Utility) Detection & Universal Infrastructure Pruning:
   Identifies framework base classes, horizontal helpers, or data objects with
   high fan-in (in-degree), as well as cross-cutting infrastructure noise
   (filters, listeners, logging). If not excluded, these bridge-like classes
   will cause the algorithm to fuse completely distinct domains into a single
   monolith. The module automatically computes degree thresholds and applies
   smart default regexes to flag utility candidates.
2. Presentation Tier Extraction (SPA vs. Vertical Slice):
   Supports isolating server-side UI controllers, servlets, and frames (Struts,
   Spring MVC, JSF, Swing) into a unified `ui_spa_and_api_gateway` service
   (`extract_spa` mode), or grouping them directly into their underlying backend
   business domains (`vertical_slice` mode).
3. Coupling & Cohesion Edge Weighting:
   - Domain Anchors (Session EJBs -> Entity EJBs of similar naming concepts):
   5.0 (keep core domain transactional classes together)
   - Database Tables (bound strongly to querying classes): 5.0 (keep tables
   grouped with accessing code)
   - Exclusive Entry Points (Actions importing exactly 1 Session): 3.0 (merge
   vertical UI controllers with backend)
   - Orchestrator/Glue Entry Points (Actions calling multiple Sessions): 0.1
   (penalize to prevent fusing domains)
   - Cross-Entity DB Penalty (Entity EJBs calling other entities or tables):
   0.01 (sever legacy monolithic joins)
"""

import collections
import os
import re

import networkx as nx
from networkx.algorithms import community

Counter = collections.Counter
louvain_communities = community.louvain_communities


# =====================================================================
# UTILITY DETECTION AND BASE GRAPH CONSTRUCTION
# =====================================================================


def rollup_class_to_package(class_name):
  """Rolls up a Fully Qualified Class Name (FQCN) to its package namespace.

  Identifies if the last segment starts with an uppercase letter to strip the
  class name, otherwise treats it as a package/namespace itself.

  Args:
      class_name (str): The FQCN (e.g.
        'com.acme.medimed.patient.PatientSessionEJB').

  Returns:
      str: The rolled-up package namespace (e.g. 'com.acme.medimed.patient').
  """
  parts = class_name.split(".")
  if len(parts) > 1:
    if parts[-1][0].isupper():
      return ".".join(parts[:-1])
    return ".".join(parts)
  return "default"


def build_directed_graph(class_deps, db_data):
  """Builds a directed graph of class imports and database table usages.

  Directed edges point from the dependent class to the dependency class or
  database table. This graph is primarily used to analyze class degree metrics
  (Fan-in/Fan-out) to discover utility classes.

  Args:
      class_deps (dict): A dictionary mapping FQCN to a list of
        imported/dependent FQCNs.
      db_data (dict): Database mappings containing 'class_to_tables' mappings.

  Returns:
      networkx.DiGraph: The directed dependency graph.
  """
  gr = nx.DiGraph()

  # Add class-to-class dependency edges
  for fqcn, deps in class_deps.items():
    gr.add_node(fqcn, type="class")
    for dep in deps:
      gr.add_node(dep, type="class")
      gr.add_edge(fqcn, dep)  # fqcn depends on dep

  # Add class-to-table edges
  class_to_tables = db_data.get("class_to_tables", {})
  for fqcn, tables in class_to_tables.items():
    gr.add_node(fqcn, type="class")
    for table in tables:
      gr.add_node(table, type="table")
      gr.add_edge(fqcn, table)  # class queries table

  return gr


def identify_utility_candidates(
    gr, class_to_file, utility_threshold=0.07, infrastructure_patterns=None
):
  """Scans the directed dependency graph to identify high fan-in classes that act as shared utilities.

  Scans the directed dependency graph to identify high fan-in classes that act
  as shared utilities, framework base classes, or data transfer objects.
  Applies standard naming-pattern heuristics and structural coupling metrics.

  Args:
      gr (networkx.DiGraph): The directed dependency graph of the monolith.
      class_to_file (dict): Mapping from FQCN to its physical file path on disk.
      utility_threshold (float): Ratio threshold (0.0 to 1.0) of total classes
        to qualify as high fan-in utility.
      infrastructure_patterns (list[str], optional): Custom regex patterns to
        aggressively match infrastructure/utility classes.

  Returns:
      list[dict]: A list of candidate utility dictionaries containing metadata,
                  degree counts, auto-exclusion verdicts, and classification
                  reasons.
  """
  candidates = []
  total_classes = sum(1 for n in gr.nodes if gr.nodes[n].get("type") == "class")
  if total_classes == 0:
    return []

  # Compile infrastructure pattern regexes with smart defaults
  default_infra_patterns = [
      r".*\.(util|utils|common|helpers|constants|config|logging|exceptions|filters|security)\..*",
      r".*(Exception|Error|Utils|Util|Constants|Helper|Factory|Locator|Filter|Listener|Log4jInit|Home|HomeFactory|Properties)$",
  ]
  if infrastructure_patterns:
    default_infra_patterns.extend(infrastructure_patterns)
  infra_regexes = [re.compile(p, re.IGNORECASE) for p in default_infra_patterns]

  # Threshold: in-degree >= utility_threshold ratio of total classes,
  # minimum of 4 references
  threshold = max(4, int(total_classes * utility_threshold))

  for node in gr.nodes:
    if gr.nodes[node].get("type") != "class":
      continue

    in_deg = gr.in_degree(node)
    out_deg = gr.out_degree(node)

    file_path = class_to_file.get(node)
    is_util = False
    reason = ""

    name = node.split(".")[-1]

    # Heuristic 1: Naming patterns & Custom regexes
    is_infra_match = False
    if infra_regexes:
      is_infra_match = any(r.match(node) for r in infra_regexes)

    if is_infra_match:
      is_util = True
      reason = "Custom Infrastructure/Lifecycle pattern match"
    elif name.endswith("Exception") or name.endswith("Error"):
      is_util = True
      reason = "Exception Class (by name)"
    elif (
        name.endswith("Utils")
        or name.endswith("Util")
        or name.endswith("Constants")
        or name.endswith("Helper")
        or name.endswith("Factory")
        or name.endswith("Locator")
        or name.endswith("Filter")
        or name.endswith("Log4jInit")
        or name.endswith("Init")
        or name.endswith("Listener")
        or name.endswith("MessageProperties")
        or name.endswith("Home")
        or name.endswith("HomeFactory")
        or name == "StartBrowser"
    ):
      is_util = True
      reason = "Utility/Factory/Locator/Infrastructure/Filter Class (by name)"
    elif (
        name.endswith("VO")
        or name.endswith("DTO")
        or ".value." in node
        or ".dto." in node
        or ".beans." in node
        or (
            name.endswith("Bean")
            and not name.endswith("SessionBean")
            and not name.endswith("MessageDrivenBean")
        )
    ):
      is_util = True
      reason = "Value Object / DTO / Bean (by name/package)"
    elif (
        name.startswith("Base")
        or name.startswith("Abstract")
        or name.endswith("Base")
    ):
      is_util = True
      reason = "Base/Abstract Class (by name)"

    # Fallback to high fan-in heuristics
    if not is_util and in_deg >= threshold:
      if file_path and os.path.exists(file_path):
        try:
          with open(file_path, "r", errors="ignore") as f:
            content = f.read()
            # Heuristic 2: Exception extension
            if (
                "extends Exception" in content
                or "extends RuntimeException" in content
                or "extends Throwable" in content
            ):
              is_util = True
              reason = "Exception Class (extends Exception)"
            # Heuristic 3: Simple POJO / Value Object / DTO
            # High in-degree but has no outgoing dependencies to other classes
            # in our graph
            elif out_deg <= 1:
              is_util = True
              reason = (
                  "Data Transfer Object / Value Object (Low Out-Degree:"
                  f" {out_deg})"
              )
        except OSError:
          pass

      if not is_util:
        reason = (
            f"High Fan-In Candidate (In-Degree: {in_deg}, Out-Degree:"
            f" {out_deg})"
        )

    # Track if it's confirmed or if it hits the high fan-in threshold
    if is_util or in_deg >= threshold:
      candidates.append({
          "class_name": node,
          "in_degree": in_deg,
          "out_degree": out_deg,
          "is_confirmed_utility": is_util,
          "reason": reason,
      })

  return candidates


# =====================================================================
# WEIGHTED GRAPH BUILDING & HEURISTIC EDGE WEIGHTING
# =====================================================================


def build_undirected_weighted_graph(
    class_deps, db_data, utilities_to_exclude, **weight_kwargs
):
  """Builds the filtered, undirected, and weighted graph representing class and database table interactions.

  Excludes specified shared utilities and applies coupling and cohesion edge
  weight heuristics to adjust the mathematical coupling of various layers (UI,
  Backend Services, JPA Entities, Database Tables).

  Args:
      class_deps (dict): A dictionary mapping FQCN to a list of
        imported/dependent FQCNs.
      db_data (dict): Database mappings containing 'class_to_tables' mappings.
      utilities_to_exclude (set): A set of FQCNs representing utilities and base
        classes to be filtered out.
      **weight_kwargs: Optional edge weighting override parameters.

  Returns:
      networkx.Graph: The undirected weighted graph prepared for Louvain
      clustering.
  """
  gr = nx.Graph()

  # Extract configurable weights with defaults
  weight_domain_anchor = weight_kwargs.get("weight_domain_anchor", 5.0)
  weight_entry_exclusive = weight_kwargs.get("weight_entry_exclusive", 3.0)
  weight_entry_glue = weight_kwargs.get("weight_entry_glue", 0.1)
  weight_db_penalty = weight_kwargs.get("weight_db_penalty", 0.01)
  weight_class_table = weight_kwargs.get("weight_class_table", 5.0)

  # Add class-to-class edges
  for fqcn, deps in class_deps.items():
    if fqcn in utilities_to_exclude:
      continue
    gr.add_node(fqcn, type="class")
    for dep in deps:
      if dep in utilities_to_exclude:
        continue
      gr.add_node(dep, type="class")

      # Determine edge weight based on naming conventions
      # (vertical vs horizontal)
      weight = 1.0
      fqcn_name = fqcn.split(".")[-1]
      dep_name = dep.split(".")[-1]

      # Count how many Sessions this class imports to determine Exclusivity
      session_deps = [
          d
          for d in deps
          if "Session" in d.split(".")[-1] and d not in utilities_to_exclude
      ]

      # Heuristic: Penalize cross-entity foreign keys to force domain separation
      if ("EJB" in fqcn_name and "Session" not in fqcn_name) and (
          "EJB" in dep_name and "Session" not in dep_name
      ):
        weight = weight_db_penalty
      # Heuristic: Penalize horizontal UI coupling to prevent horizontal UI
      # monoliths
      elif ("Action" in fqcn_name and "Action" in dep_name) or (
          "WS" in fqcn_name and "WS" in dep_name
      ):
        weight = weight_db_penalty
      # Heuristic: Mathematical Exclusivity for Entry Points
      elif (
          "Action" in fqcn_name
          or "Controller" in fqcn_name
          or "WS" in fqcn_name
      ) and "Session" in dep_name:
        if len(session_deps) == 1:
          # Exclusive Entry Point -> Bind to its backend (but weaker than DB)
          weight = weight_entry_exclusive
        else:
          # Orchestrator / Glue -> Penalize to avoid merging domains
          weight = weight_entry_glue
      # Heuristic: Strongly bind Backend Business Logic (Sessions to Entities)
      elif "Session" in fqcn_name and (
          "EJB" in dep_name or "Entity" in dep_name
      ):
        session_core = fqcn_name.replace("SessionEJB", "").replace(
            "Session", ""
        )
        entity_core = dep_name.replace("EJB", "").replace("Entity", "")
        if (
            session_core
            and entity_core
            and (session_core in entity_core or entity_core in session_core)
        ):
          weight = weight_domain_anchor  # Domain Anchor -> STRONGEST BOND
        else:
          weight = weight_db_penalty

      gr.add_edge(fqcn, dep, weight=weight)

  # Add class-to-table edges
  class_to_tables = db_data.get("class_to_tables", {})
  for fqcn, tables in class_to_tables.items():
    if fqcn in utilities_to_exclude:
      continue
    gr.add_node(fqcn, type="class")
    for table in tables:
      gr.add_node(table, type="table")
      # Tables represent state; bind highly to class
      # (weight = weight_class_table)
      if gr.has_edge(fqcn, table):
        gr[fqcn][table]["weight"] = weight_class_table
      else:
        gr.add_edge(fqcn, table, weight=weight_class_table)

  return gr


# =====================================================================
# LOUVAIN COMMUNITY DETECTION & BOUNDARY CLUSTERING
# =====================================================================
def find_communities(gr, resolution=1.0):
  """Executes the Louvain community detection algorithm via NetworkX.

  Executes the Louvain community detection algorithm (via NetworkX native
  module) to partition the graph nodes into cohesive microservice boundaries.
  Automatically assigns service names based on dominant domain naming patterns
  within each cluster.

  Args:
      gr (networkx.Graph): The undirected weighted graph.
      resolution (float): The Louvain resolution parameter. Higher values yield
        more, smaller communities.

  Returns:
      list[dict]: A list of dictionaries representing the proposed services,
      containing the service_id,
                  associated classes, rolled-up packages, and queryable database
                  tables.
  """
  # Execute native NetworkX Louvain community detection
  communities = louvain_communities(
      gr, weight="weight", resolution=resolution, seed=42
  )

  clusters = []
  for i, comm in enumerate(communities):
    classes = []
    tables = []
    for node in comm:
      node_type = gr.nodes[node].get("type", "unknown")
      if node_type == "class":
        classes.append(node)
      elif node_type == "table":
        tables.append(node)

    packages = sorted(list(set(rollup_class_to_package(c) for c in classes)))

    # Calculate a meaningful service name based on dominant class concepts
    def get_domain_words(class_name):
      simple_name = class_name.split(".")[-1]
      # Strip common technical suffixes
      for suffix in [
          "EJB",
          "Action",
          "WS",
          "DAO",
          "Bean",
          "Service",
          "Impl",
          "Factory",
          "Controller",
          "Session",
          "BaseLookupDispatchAction",
          "BaseAction",
          "Log4jInit",
      ]:
        if simple_name.endswith(suffix):
          simple_name = simple_name[: -len(suffix)]
      # Split camel case into words
      words = [
          w for w in re.split(r"(?<=[a-z])(?=[A-Z])", simple_name) if len(w) > 2
      ]
      return words

    concept_counts = Counter()
    for c in classes:
      for w in get_domain_words(c):
        concept_counts[w] += 1

    if concept_counts:
      # Get the most common domain concept (e.g. 'Patient', 'Admin', 'Record')
      dominant_concept = concept_counts.most_common(1)[0][0].lower()
      service_name = f"{dominant_concept}_service_{i+1}"
    else:
      # Fallback to package if no concepts found
      pkg_counts = Counter(rollup_class_to_package(c) for c in classes)
      if pkg_counts:
        dominant_pkg = pkg_counts.most_common(1)[0][0]
        pkg_name = dominant_pkg.split(".")[-1]
        service_name = f"{pkg_name}_service_{i+1}"
      else:
        service_name = f"core_service_{i+1}"

    clusters.append({
        "service_id": service_name,
        "classes": sorted(classes),
        "packages": packages,
        "tables": sorted(tables),
    })
  return clusters


def generate_mermaid_clusters(clusters):
  """Generates a Mermaid graph TD flowchart representing the microservice boundaries.

  Renders subgraphs for each microservice containing class and table nodes.

  Args:
      clusters (list[dict]): List of generated service boundary dictionaries.

  Returns:
      str: A multi-line Mermaid diagram string.
  """
  lines = ["graph TD"]
  for cluster in clusters:
    service_id = cluster["service_id"]
    lines.append(f"    subgraph {service_id}")
    for cls in cluster["classes"]:
      simple_name = cls.split(".")[-1]
      node_id = cls.replace(".", "_")
      lines.append(f'        {node_id}["{simple_name} (Class)"]')
    for table in cluster["tables"]:
      lines.append(f'        {table}["{table} (DB Table)"]')
    lines.append("    end")
  return "\n".join(lines)


def find_service_clusters(
    imports_report,
    db_report,
    confirmed_utilities=None,
    exclude_patterns=None,
    resolution=1.0,
    presentation_package_pattern=None,
    infrastructure_package_pattern=None,
    presentation_mode="extract_spa",
    **weight_kwargs,
):
  """Orchestrates microservice boundary recommendation via Louvain clustering.

  Orchestrates directed dependency evaluation, utility extraction, undirected
  weighted graph construction, and Louvain community detection to output a
  fully packaged microservice boundary recommendation.

  Args:
      imports_report (dict): JSON report from import_analyzer containing package
        class dependencies.
      db_report (dict): JSON report from db_mapper containing
        class-to-database-table mappings.
      confirmed_utilities (list[str]): List of FQCNs explicitly confirmed as
        utilities to be excluded.
      exclude_patterns (list[str]): Regex strings matching FQCNs to be
        aggressively excluded.
      resolution (float): The Louvain parameter resolution.
      presentation_package_pattern (list[str], optional): Regex patterns
        matching presentation classes.
      infrastructure_package_pattern (list[str], optional): Regex patterns
        matching infrastructure classes.
      presentation_mode (str): Mode for UI/presentation classes partitioning
        (extract_spa|vertical_slice|ignore).
      **weight_kwargs: Configurable edge weighting configurations.

  Returns:
      dict: A dictionary mapping of results containing summary stats, utility
      evaluations,
            proposed service lists, and Mermaid graphs.
  """
  class_deps = imports_report.get("class_dependencies", {})
  class_to_file = imports_report.get("class_to_file", {})

  if not class_deps:
    return {"error": "No class dependency data available."}

  # 1. Build directed graph to evaluate fan-in
  di_graph = build_directed_graph(class_deps, db_report)

  # 2. Identify candidate utilities
  utility_threshold = weight_kwargs.get("utility_threshold", 0.07)
  candidates = identify_utility_candidates(
      di_graph,
      class_to_file,
      utility_threshold=utility_threshold,
      infrastructure_patterns=infrastructure_package_pattern,
  )

  # 3. Determine exclusions
  # (confirmed utilities from heuristics + externally confirmed)
  utilities_to_exclude = set()
  for cand in candidates:
    if cand["is_confirmed_utility"]:
      utilities_to_exclude.add(cand["class_name"])

  if confirmed_utilities:
    for fqcn in confirmed_utilities:
      utilities_to_exclude.add(fqcn)

  if exclude_patterns:
    patterns = [re.compile(p) for p in exclude_patterns]
    for fqcn in class_deps.keys():
      for p in patterns:
        if p.match(fqcn):
          utilities_to_exclude.add(fqcn)
          break

  # 4. Extract Presentation Tier (UI SPA / API Gateway) classes before backend
  # domain clustering
  # Default covers Struts (*Action, *Form, .actions.),
  # JSF (*Page, *Bean, .jsf.), Spring MVC (*Controller, .mvc.),
  # desktop Swing/AWT (*Frame, *Client, .swing.)
  default_prep_patterns = [
      r".*\.(web|ui|actions|controllers|views|presentation|swing|client|struts|jsf|faces|mvc)\..*",
      r".*(Action|Servlet|Controller|Presenter|View|PageBean|SwingClient|Frame)$",
  ]
  if presentation_package_pattern:
    default_prep_patterns.extend(presentation_package_pattern)
  prep_regexes = [re.compile(p, re.IGNORECASE) for p in default_prep_patterns]

  ui_spa_classes = []
  backend_class_deps = {}
  for fqcn, deps in class_deps.items():
    if fqcn in utilities_to_exclude:
      continue
    is_presentation = any(r.match(fqcn) for r in prep_regexes)
    if presentation_mode == "extract_spa" and is_presentation:
      ui_spa_classes.append(fqcn)
    else:
      backend_class_deps[fqcn] = deps

  # 5. Build weighted undirected graph for backend domain partitioning
  undir_graph = build_undirected_weighted_graph(
      backend_class_deps, db_report, utilities_to_exclude, **weight_kwargs
  )

  if len(undir_graph) == 0 and not ui_spa_classes:
    return {"error": "The filtered dependency graph is empty."}

  # 6. Run Louvain partitioning on backend domain
  clusters = []
  if len(undir_graph) > 0:
    clusters = find_communities(undir_graph, resolution=resolution)

  # 7. Prepend the UI SPA & API Gateway presentation service if UI classes exist
  if ui_spa_classes:
    ui_spa_service = {
        "service_id": "ui_spa_and_api_gateway",
        "service_type": "Presentation Tier (UI SPA & API Gateway)",
        "classes": sorted(ui_spa_classes),
        "packages": sorted(
            list(set(rollup_class_to_package(c) for c in ui_spa_classes))
        ),
        "tables": [],
    }
    clusters.insert(0, ui_spa_service)

  return {
      "summary": {
          "total_classes": (
              sum(
                  1
                  for n in undir_graph.nodes
                  if undir_graph.nodes[n].get("type") == "class"
              )
              + len(ui_spa_classes)
          ),
          "total_tables": sum(
              1
              for n in undir_graph.nodes
              if undir_graph.nodes[n].get("type") == "table"
          ),
          "proposed_services_count": len(clusters),
          "excluded_utilities_count": len(utilities_to_exclude),
      },
      "utility_evaluation": {
          "candidates": candidates,
          "excluded_utilities": sorted(list(utilities_to_exclude)),
      },
      "proposed_services": clusters,
      "mermaid_clusters": generate_mermaid_clusters(clusters),
  }
