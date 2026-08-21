"""Command-line interface orchestrator for the WebLogic monolith decomposition analyzer.

This module acts as the primary entry point for the analysis and microservices
boundary mapping tool.
It orchestrates the execution of all parsing and analysis engines, including:
- Directory scans and cloud-unfriendly pattern detection (static_analyzer)
- Java EE descriptors and XML configuration parsers (config_parser)
- Maven POM and Ant build configurations (build_parser)
- WebLogic domain config and resources (domain_parser)
- Local JAR dependencies (jar_analyzer)
- Code imports and directed dependency graphing (import_analyzer)
- Database table access patterns (db_mapper)

It passes the extracted dependency graph and database maps to the clustering
engine (clusterer) to run the Louvain community detection algorithm under
multiple resolutions and custom edge-weighting knobs.
Finally, it compiles these results into a unified JSON schema or a comprehensive
Markdown report designed to be rendered as an interactive UI Artifact.

Usage:
    python3 cli.py analyze <directory> [options]

Subcommands:
    analyze                         Run the full static analysis and
    microservice decomposition pipeline.

Options:
    --base-package <package>        The base package prefix (e.g. com.example)
    to filter internal dependencies.
    --format {json,markdown}        Output format. Default is json.
    --confirmed-utilities <list>    Comma-separated list of FQCNs to exclude
    from clustering as utilities.
    --exclude-patterns <list>       Comma-separated list of regex patterns to
    exclude from the clustering graph.
    --resolution [res1 res2 ...]   List of resolution parameters for Louvain
    clustering (default: 1.0).
    --presentation-package-pattern <list> Regex patterns matching
    UI/presentation classes (smart default).
    --infrastructure-package-pattern <list> Regex patterns matching
    cross-cutting noise (smart default).
    --presentation-mode {extract_spa,vertical_slice,ignore} UI classes
    partitioning mode (default: extract_spa).
    --weight-domain-anchor <val>    Weight for strong domain anchor bonds
    (default: 5.0).
    --weight-entry-exclusive <val>  Weight for exclusive entry point bonds
    (default: 3.0).
    --weight-entry-glue <val>       Weight for orchestrator/glue entry points
    (default: 0.1).
    --weight-db-penalty <val>       Penalty weight for cross-entity foreign keys
    (default: 0.01).
    --weight-class-table <val>      Weight for class-to-database-table bindings
    (default: 5.0).
    --utility-threshold <val>       Fan-in ratio threshold for shared utilities
    (default: 0.07).
    --output <file>                 Write report to file instead of stdout.
"""

import argparse
import json
import os
import sys
import build_parser
import clusterer
import config_parser
import db_mapper
import domain_parser
import import_analyzer
import jar_analyzer

# Import modules from the same directory
import static_analyzer

# =====================================================================
# DEFAULT MODULE NAME PATTERNS FOR PRESENTATION AND INFRASTRUCTURE
# =====================================================================
DEFAULT_PRESENTATION_PATTERNS = [
    r".*\.(web|ui|actions|controllers|views|presentation|swing|client|struts|jsf|faces|mvc)\..*",
    r".*(Action|Servlet|Controller|Presenter|View|PageBean|SwingClient|Frame)$",
]
DEFAULT_INFRASTRUCTURE_PATTERNS = [
    r".*\.(util|utils|common|helpers|constants|config|logging|exceptions|filters|security)\..*",
    r".*(Exception|Error|Utils|Util|Constants|Helper|Factory|Locator|Filter|Listener|Log4jInit|Home|HomeFactory|Properties)$",
]


# =====================================================================
# CORE ANALYSIS PIPELINE ORCHESTRATION
# =====================================================================


def run_full_analysis(
    target_dir,
    base_package=None,
    confirmed_utilities=None,
    exclude_patterns=None,
    resolutions=None,
    presentation_package_pattern=None,
    infrastructure_package_pattern=None,
    presentation_mode="extract_spa",
    weight_kwargs=None,
):
  """Orchestrates the entire decomposition pipeline.

  Orchestrates the entire decomposition pipeline by running all analyzer
  modules, including static code analysis, config XML parsing, build setups,
  jar dependencies, Java package imports, database tables mapping, and Louvain
  graph clustering.

  Args:
      target_dir (str): The target legacy monolith repository directory.
      base_package (str, optional): The base package filter (e.g.
        'com.acme.medimed').
      confirmed_utilities (list[str], optional): Explicit utility FQCNs to
        exclude from clustering.
      exclude_patterns (list[str], optional): Regex patterns of classes to
        exclude from clustering.
      resolutions (list[float], optional): List of Louvain resolutions to
        execute.
      presentation_package_pattern (list[str], optional): Regex patterns
        matching presentation classes.
      infrastructure_package_pattern (list[str], optional): Regex patterns
        matching infrastructure noise.
      presentation_mode (str): Mode for UI/presentation classes partitioning
        (extract_spa|vertical_slice|ignore).
      weight_kwargs (dict, optional): Custom edge weight overrides for community
        detection.

  Returns:
      dict: A compiled unified JSON dictionary containing all analysis reports
      and microservice clusters.
  """
  if resolutions is None:
    resolutions = [1.0]
  if weight_kwargs is None:
    weight_kwargs = {}

  static_report = static_analyzer.analyze_static(target_dir)
  configs_report = config_parser.parse_configurations(target_dir)
  build_report = build_parser.parse_build_files(target_dir)
  domain_report = domain_parser.parse_domain_config(target_dir)
  jars_report = jar_analyzer.analyze_local_jars(target_dir)
  imports_report = import_analyzer.analyze_imports(target_dir, base_package)
  db_report = db_mapper.map_db_usage(target_dir)

  # Run clustering using the outputs of imports and db mapping
  clustering_reports = {}
  top_level_utility_eval = {}
  for res in resolutions:
    res_report = clusterer.find_service_clusters(
        imports_report,
        db_report,
        confirmed_utilities,
        exclude_patterns,
        res,
        presentation_package_pattern,
        infrastructure_package_pattern,
        presentation_mode,
        **weight_kwargs,
    )
    if not top_level_utility_eval and "utility_evaluation" in res_report:
      top_level_utility_eval = res_report.pop("utility_evaluation")
    elif "utility_evaluation" in res_report:
      res_report.pop("utility_evaluation")
    clustering_reports[str(res)] = res_report

  return {
      "target_directory": os.path.abspath(target_dir),
      "static_analysis": static_report,
      "configuration_descriptors": configs_report,
      "build_configuration": build_report,
      "weblogic_domain_configuration": domain_report,
      "local_jars": jars_report,
      "package_dependencies": imports_report,
      "database_usage": db_report,
      "utility_evaluation": top_level_utility_eval,
      "microservices_clustering": clustering_reports,
  }


# =====================================================================
# REPORT FORMATTING AND MARKDOWN GENERATION
# =====================================================================


def format_markdown_report(report):
  """Formats the unified analysis JSON report into a readable Markdown document.

  Outputs a clean summary table for multi-resolution runs to avoid document
  bloat, and a detailed package/class boundary map and Mermaid diagram for
  single resolution runs.

  Args:
      report (dict): The compiled unified analysis JSON report dictionary.

  Returns:
      str: A Markdown formatted document.
  """
  static = report["static_analysis"]
  build = report["build_configuration"]
  domain = report["weblogic_domain_configuration"]
  jars = report["local_jars"]
  clustering_dict = report.get("microservices_clustering", {})

  clustering = report["microservices_clustering"]

  md = []
  md.append("# WebLogic Migration Unified Analysis Report")
  md.append(f"**Target Directory:** `{report['target_directory']}`\n")

  md.append("## 1. Executive Summary")
  gen = static["general"]
  web_tier = static["web_tier"]
  wls_deps = static["weblogic_api"]["imports_count"]
  first_res = list(clustering.keys())[0] if clustering else None
  proposed_count = (
      clustering.get(first_res, {})
      .get("summary", {})
      .get("proposed_services_count", 0)
      if first_res
      else 0
  )
  md.append(f"*   **Total Files Scanned:** {gen.get('total_files', 0)}")
  md.append(
      f"*   **Java Source Files (.java, .ejb):** {gen.get('java_files', 0)}"
  )
  md.append(
      f"*   **JWS Web Service Source Files (.jws):** {gen.get('jws_files', 0)}"
  )
  md.append(f"*   **XML Configurations (.xml):** {gen.get('xml_files', 0)}")
  md.append(
      "    *   **Standard Web Descriptors (web.xml):**"
      f" {web_tier.get('web_xml_count', 0)}"
  )
  md.append(
      "    *   **WebLogic Web Descriptors (weblogic.xml):**"
      f" {web_tier.get('weblogic_xml_count', 0)}"
  )
  md.append(
      f"*   **JSP/JSPX View Templates:** {web_tier.get('jsp_files_count', 0)}"
  )
  md.append(
      "*   **JSF/Facelets View Templates (.xhtml, .jsf, .faces):**"
      f" {gen.get('jsf_files', 0)}"
  )
  md.append(
      f"*   **HTML View Files (.html, .htm):** {gen.get('html_files', 0)}"
  )
  md.append(f"*   **Properties Files:** {gen.get('properties_files', 0)}")
  md.append(f"*   **WebLogic API Dependencies:** {wls_deps} occurrences")
  md.append(f"*   **Proposed Microservices:** {proposed_count}\n")

  md.append("## 2. Build & Environment")
  for proj in build.get("maven_projects", []):
    md.append(f"### Maven Project: `{proj['path']}`")
    analysis = proj["analysis"]
    if "error" in analysis:
      md.append(f"*   Error: {analysis['error']}")
    else:
      md.append(f"*   **Target Java Version:** {analysis['java_version']}")
      md.append(
          "*   **Dependencies Count:**"
          f" {analysis['dependencies_summary']['total']}"
      )
      md.append(
          "*   **WebLogic Libraries:**"
          f" {analysis['dependencies_summary']['weblogic_specific_count']}"
      )
      md.append(
          "*   **Legacy Java EE Libraries:**"
          f" {analysis['dependencies_summary']['java_ee_legacy_count']}"
      )

  for proj in build.get("ant_projects", []):
    md.append(f"### Ant Project: `{proj['path']}`")
    md.append(f"*   {proj['info']}")
  md.append("")

  if jars["weblogic_specific"] or jars["java_ee_legacy"]:
    md.append("### Checked-in Libraries (lib/ directory)")
    for jar in jars["weblogic_specific"]:
      md.append(
          f"*   `{jar['relative_path']}`: **WebLogic Specific**"
          f" ({jar.get('title')} v{jar.get('version')})"
      )
    for jar in jars["java_ee_legacy"]:
      md.append(
          f"*   `{jar['relative_path']}`: **Legacy Java EE**"
          f" ({jar.get('title')} v{jar.get('version')})"
      )
    md.append("")

  md.append("## 3. Technical Inventory")
  ejb = static["ejb"]
  md.append("### Enterprise JavaBeans (EJB)")
  md.append(f"*   Stateless Session Beans: {ejb['stateless_count']}")
  md.append(f"*   Stateful Session Beans: {ejb['stateful_count']}")
  md.append(f"*   Message-Driven Beans (MDB): {ejb['mdb_count']}")
  md.append(f"*   CMP/BMP Entity Beans: {ejb.get('entity_bean_count', 0)}")
  md.append(
      "*   EJB 2.x Home/Local Interfaces:"
      f" {ejb.get('ejb_2x_home_interfaces_count', 0)}"
  )
  md.append(f"*   EJB XML Descriptors: {ejb['ejb_descriptors_count']}")

  jms = static["jms"]
  md.append("### JMS & JNDI")
  md.append(f"*   JMS Imports: {jms['imports_count']}")
  md.append(f"*   JMS JNDI Lookups: {jms['jndi_lookups_count']}")
  md.append(f"*   JMS Senders / Producers: {jms.get('producer_count', 0)}")
  md.append(f"*   JMS Receivers / Consumers: {jms.get('consumer_count', 0)}")
  md.append(f"*   JMS Queues Referenced: {jms.get('queue_count', 0)}")
  md.append(f"*   JMS Topics Referenced: {jms.get('topic_count', 0)}")
  md.append(
      f"*   InitialContext Creations: {static['jndi']['initial_context_count']}"
  )
  md.append(f"*   Total JNDI Lookups: {static['jndi']['lookups_count']}\n")

  tx = static["transactions"]
  md.append("### Transactions & Distributed Coordination")
  md.append(
      "*   Programmatic Transactions (`UserTransaction`):"
      f" {tx['user_transaction_count']}"
  )
  md.append(
      "*   Declarative Transactions (`@Transactional`,"
      f" `@TransactionAttribute`): {tx.get('declarative_transaction_count', 0)}"
  )
  md.append(
      "*   Standard Transaction Managers Referenced:"
      f" {tx.get('standard_transaction_manager_count', 0)}"
  )
  md.append("*   XA Distributed Transactions:")
  md.append(f"    *   XA Data Sources: {tx['xa_datasource_count']}")
  md.append(
      f"    *   XA Resources (`XAResource`): {tx.get('xa_resource_count', 0)}\n"
  )

  advanced = static["advanced_features"]
  md.append("### Advanced Container Features & Web Services")
  md.append(f"*   Work Managers: {advanced['work_managers_count']}")
  md.append(f"*   Timers: {advanced['timers_count']}")
  md.append(f"*   Resource Adapters: {advanced['resource_adapters_count']}")
  md.append(f"*   Total Web Services: {advanced['web_services_count']}")
  md.append(f"    *   JAX-RPC (Legacy): {advanced.get('jax_rpc_count', 0)}")
  md.append(f"    *   JAX-WS (Standard): {advanced.get('jax_ws_count', 0)}\n")

  web_tier = static["web_tier"]
  md.append("### Web Tier & Presentation Layer")
  md.append(f"*   JSP/JSPX Files: {web_tier['jsp_files_count']}")
  md.append(
      "*   JSF/Facelets Templates (.xhtml, .jsf, .faces):"
      f" {gen.get('jsf_files', 0)}"
  )
  md.append(f"*   HTML Files (.html, .htm): {gen.get('html_files', 0)}")
  md.append(f"*   Servlets: {web_tier['servlets_count']}")
  md.append(f"*   Servlet Filters: {web_tier.get('filters_count', 0)}")
  md.append(f"*   Servlet Listeners: {web_tier.get('listeners_count', 0)}")
  md.append(
      "*   Modern REST Endpoints (JAX-RS):"
      f" {web_tier.get('jax_rs_endpoints_count', 0)}"
  )
  md.append(
      "*   Spring MVC Controllers:"
      f" {web_tier.get('spring_controllers_count', 0)}"
  )
  md.append(f"*   Struts Usages: {web_tier.get('struts_count', 0)}")
  md.append(f"*   JSF Usages (in Java Code): {web_tier.get('jsf_count', 0)}")
  md.append(
      f"*   Standard XML Descriptors (web.xml): {web_tier['web_xml_count']}"
  )
  md.append(
      "*   WebLogic XML Descriptors (weblogic.xml):"
      f" {web_tier['weblogic_xml_count']}\n"
  )

  md.append("### Cloud-Unfriendly Patterns")
  unfriendly = static.get("cloud_unfriendly_patterns", {})
  md.append(
      "*   Hardcoded IP Addresses (excluding loopback):"
      f" {unfriendly.get('hardcoded_ips_count', 0)}"
  )
  md.append(
      "*   Hardcoded Absolute File Paths:"
      f" {unfriendly.get('absolute_paths_count', 0)}"
  )
  md.append(
      "*   Raw Thread Creations (`new Thread()`):"
      f" {unfriendly.get('raw_threads_count', 0)}"
  )
  md.append(
      "*   Native OS Command Executions (`exec`/`ProcessBuilder`):"
      f" {unfriendly.get('native_processes_count', 0)}"
  )
  md.append(
      "*   Direct Socket Connections (`new Socket`):"
      f" {unfriendly.get('direct_sockets_count', 0)}"
  )
  md.append(
      "*   JAAS/Custom Security Modules (`LoginModule`):"
      f" {unfriendly.get('jaas_login_modules_count', 0)}"
  )
  md.append(
      "*   Servlet Proxies"
      " (`HttpClusterServlet`/`HttpProxyServlet`):"
      f" {unfriendly.get('specific_proxies_count', 0)}\n"
  )

  wls_api = static["weblogic_api"]
  md.append("### WebLogic Specific APIs & Middleware")
  md.append(f"*   Total WebLogic API Usages: {wls_api['imports_count']}")
  md.append(f"    *   Logging: {wls_api.get('logging_count', 0)}")
  md.append(f"    *   Security: {wls_api.get('security_count', 0)}")
  md.append(
      f"    *   Transactions (Total): {wls_api.get('transaction_count', 0)}"
  )
  md.append(
      "        *   Transaction Manager / TxHelper:"
      f" {wls_api.get('wls_transaction_manager_count', 0)}"
  )
  md.append(
      "        *   UserTransaction:"
      f" {wls_api.get('wls_user_transaction_count', 0)}"
  )
  md.append(f"    *   Coherence Caching: {wls_api.get('coherence_count', 0)}")
  md.append(f"    *   Work Manager APIs: {wls_api.get('workmanager_count', 0)}")
  md.append(
      f"    *   JWS Web Services APIs: {wls_api.get('jws_api_count', 0)}\n"
  )

  md.append("## 4. Shared Utility Evaluation")
  # Utility evaluation is resolution-independent, grab it from top-level report
  # or first candidate
  eval_data = report.get("utility_evaluation", {})
  if not eval_data:
    first_res = list(clustering_dict.keys())[0] if clustering_dict else None
    first_clustering = clustering_dict.get(first_res, {}) if first_res else {}
    eval_data = first_clustering.get("utility_evaluation", {})
  excluded = eval_data.get("excluded_utilities", [])
  candidates = eval_data.get("candidates", [])

  if excluded:
    md.append("### Excluded Shared Utilities")
    md.append(
        "The following classes were identified as utilities (via heuristics or"
        " configuration) and excluded from the microservice clustering graph:"
    )
    for ex in excluded:
      # Find the candidate to show reason if available
      reason = ""
      for c in candidates:
        if c["class_name"] == ex:
          reason = f" ({c['reason']})"
          break
      md.append(f"*   `{ex}`{reason}")
    md.append("")

  other_candidates = [c for c in candidates if not c["is_confirmed_utility"]]
  if other_candidates:
    md.append(
        "### High Fan-In Candidates for Review (LLM Semantic Evaluation"
        " Required)"
    )
    md.append(
        "The following classes have high coupling (fan-in) but were not"
        " automatically classified as utilities. You MUST semantically evaluate"
        " the source code of these candidates to distinguish true business"
        " aggregate roots from domain-agnostic utilities. Register the"
        " domain-agnostic utilities using `--confirmed-utilities`:"
    )
    for cand in other_candidates:
      md.append(
          f"*   `{cand['class_name']}` (In-Degree: {cand['in_degree']},"
          f" Out-Degree: {cand['out_degree']})"
      )
    md.append("")

  if not excluded and not other_candidates:
    md.append("*No high fan-in utility candidates detected.*\n")

  md.append("## 5. Web & Presentation Modernization Recommendation")
  if web_tier["jsp_files_count"] > 0:
    md.append("### Legacy JSP Migration Strategy")
    md.append(
        f"The application contains **{web_tier['jsp_files_count']} JSP files**,"
        " indicating a server-rendered coupled user interface."
    )
    md.append(
        "We recommend modernizing the presentation layer to align with"
        " cloud-native practices:"
    )
    md.append(
        "*   **Decoupled Frontend**: Extract presentation layout and user"
        " interactions from JSP files and re-write them into a modern SPA"
        " framework (e.g. **Angular** or **React**)."
    )
    md.append(
        "*   **REST API Layer**: Migrate server-side web components (Struts"
        " Action classes, JSF Backing beans, or legacy Servlets) into stateless"
        " REST API endpoints (Spring Boot `@RestController` or Quarkus JAX-RS)."
    )
    md.append(
        "*   **Stateless Transition**: Ensure JSP session variables are mapped"
        " to token-based authorization (JWT) or persistent distributed session"
        " stores (Redis) to allow independent microservice scaling."
    )
    md.append("")
  elif web_tier["servlets_count"] > 0:
    md.append("### Servlet Modernization Strategy")
    md.append(
        f"The application contains **{web_tier['servlets_count']} legacy"
        " Servlets**."
    )
    md.append(
        "We recommend mapping servlet request-handling logic to modern Spring"
        " Boot or Quarkus REST controllers inside the target services."
    )
    md.append("")
  else:
    md.append(
        "No server-rendered front-end files (JSPs) were detected. Modernization"
        " is focused exclusively on back-end APIs and services.\n"
    )

  md.append("## 6. Proposed Decomposition Candidates (Topological Analysis)")

  if len(clustering_dict) > 1:
    md.append(
        "Multiple resolutions were requested. Below is a high-level summary of"
        " the generated candidates:\n"
    )
    md.append(
        "| Resolution | Services Count | Total Classes | Total Tables |"
        " Excluded Utilities | Service Names |"
    )
    md.append(
        "|------------|----------------|---------------|--------------|--------------------|---------------|"
    )
    for res_val, c_report in clustering_dict.items():
      if "error" in c_report:
        md.append(f"| {res_val} | ERROR: {c_report['error']} | - | - | - | - |")
        continue
      summary = c_report.get("summary", {})
      services = c_report.get("proposed_services", [])
      service_names = ", ".join([f"`{s['service_id']}`" for s in services])
      md.append(
          f"| {res_val} | {summary.get('proposed_services_count', 0)} |"
          f" {summary.get('total_classes', 0)} |"
          f" {summary.get('total_tables', 0)} |"
          f" {summary.get('excluded_utilities_count', 0)} | {service_names} |"
      )
    md.append("\n> [!NOTE]")
    md.append(
        "> Detailed package/class boundaries and Mermaid diagrams are omitted"
        " for multi-resolution runs to prevent report bloat. Please re-run the"
        " analyzer with a single resolution parameter (e.g. `--resolution 1.0`)"
        " to generate the full markdown report with diagrams."
    )
  else:
    md.append(
        "Based on class-level dependencies and shared database table access"
        " (excluding utility classes), we have partitioned the application into"
        " the following candidate boundaries:\n"
    )
    res_val = list(clustering_dict.keys())[0]
    c_report = clustering_dict[res_val]

    if "error" in c_report:
      md.append(f"Error executing clustering algorithm: {c_report['error']}\n")
    else:
      md.append(f"### Selected Resolution: {res_val}\n")
      md.append("#### Proposed Boundaries (Mermaid Diagram)")
      md.append("```mermaid")
      md.append(c_report["mermaid_clusters"])
      md.append("```\n")

      for s in c_report.get("proposed_services", []):
        md.append(f"##### Service: `{s['service_id']}`")
        md.append("**Packages Represented:**")
        for pkg in s["packages"]:
          md.append(f"*   `{pkg}`")
        md.append("**Classes:**")
        for cls in s["classes"]:
          md.append(f"*   `{cls}`")
        md.append("**Database Tables:**")
        for tbl in s["tables"]:
          md.append(f"*   `{tbl}`")
  return "\n".join(md)


# =====================================================================
# CLI ENTRY POINT
# =====================================================================
def main():
  """Main entry point for CLI execution.

  Parses command-line arguments and routes commands to appropriate analysis
  processes.
  """
  parser = argparse.ArgumentParser(
      description="WebLogic Monolith Migration Tool"
  )
  subparsers = parser.add_subparsers(dest="command")

  # 1. 'analyze' subcommand
  analyze_parser = subparsers.add_parser(
      "analyze",
      help=(
          "Run the full static analysis and microservice decomposition"
          " pipeline."
      ),
  )
  analyze_parser.add_argument(
      "directory", help="The target project root directory to analyze."
  )
  analyze_parser.add_argument(
      "--base-package",
      help=(
          "The base package prefix (e.g. com.example) to filter internal"
          " dependencies. Auto-detected if omitted."
      ),
  )
  analyze_parser.add_argument(
      "--format",
      choices=["json", "markdown"],
      default="json",
      help="Output format. Default is json.",
  )
  analyze_parser.add_argument(
      "--confirmed-utilities",
      help=(
          "Comma-separated list of FQCNs to exclude from clustering as"
          " utilities."
      ),
  )
  analyze_parser.add_argument(
      "--exclude-patterns",
      help=(
          "Comma-separated list of regex patterns (applied to FQCNs) to"
          " aggressively exclude from the clustering graph (e.g."
          " '.*\\.beans\\..*,.*Base.*')."
      ),
  )
  analyze_parser.add_argument(
      "--resolution",
      nargs="+",
      type=float,
      default=[1.0],
      help=(
          "List of resolution parameters for Louvain clustering (e.g. 0.5 1.0"
          " 1.5)."
      ),
  )
  analyze_parser.add_argument(
      "--presentation-package-pattern",
      nargs="+",
      default=DEFAULT_PRESENTATION_PATTERNS,
      help=(
          "Regex patterns matching UI/presentation layer classes. Uses smart"
          " defaults for Struts, Spring MVC, JSF, Servlets, and Swing."
      ),
  )
  analyze_parser.add_argument(
      "--infrastructure-package-pattern",
      nargs="+",
      default=DEFAULT_INFRASTRUCTURE_PATTERNS,
      help=(
          "Regex patterns matching cross-cutting infrastructure noise. Uses"
          " smart defaults for filters, logging, and utilities."
      ),
  )
  analyze_parser.add_argument(
      "--presentation-mode",
      choices=["extract_spa", "vertical_slice", "ignore"],
      default="extract_spa",
      help=(
          "UI/presentation classes mode: extract_spa (default), vertical_slice,"
          " or ignore."
      ),
  )

  # Weights for coupling and cohesion heuristics
  analyze_parser.add_argument(
      "--weight-domain-anchor",
      type=float,
      default=5.0,
      help=(
          "Weight for strong domain anchor bonds (e.g. Session -> Entity"
          " matches)."
      ),
  )
  analyze_parser.add_argument(
      "--weight-entry-exclusive",
      type=float,
      default=3.0,
      help=(
          "Weight for exclusive entry point bonds (e.g. Action calling only 1"
          " Session)."
      ),
  )
  analyze_parser.add_argument(
      "--weight-entry-glue",
      type=float,
      default=0.1,
      help=(
          "Weight for orchestrator/glue entry points calling multiple Sessions."
      ),
  )
  analyze_parser.add_argument(
      "--weight-db-penalty",
      type=float,
      default=0.01,
      help=(
          "Penalty weight for cross-entity foreign keys to break monolithic"
          " databases."
      ),
  )
  analyze_parser.add_argument(
      "--weight-class-table",
      type=float,
      default=5.0,
      help="Weight for class-to-database-table state associations.",
  )
  analyze_parser.add_argument(
      "--utility-threshold",
      type=float,
      default=0.07,
      help=(
          "Fan-in ratio threshold (0.0 to 1.0) for automatically detecting"
          " shared utility candidates."
      ),
  )

  analyze_parser.add_argument(
      "--output", help="Write report to file instead of stdout."
  )

  args = parser.parse_args()

  if args.command == "analyze":
    confirmed_utils = None
    if args.confirmed_utilities:
      confirmed_utils = [x.strip() for x in args.confirmed_utilities.split(",")]

    exclude_patterns = (
        args.exclude_patterns.split(",") if args.exclude_patterns else None
    )

    weight_kwargs = {
        "weight_domain_anchor": args.weight_domain_anchor,
        "weight_entry_exclusive": args.weight_entry_exclusive,
        "weight_entry_glue": args.weight_entry_glue,
        "weight_db_penalty": args.weight_db_penalty,
        "weight_class_table": args.weight_class_table,
        "utility_threshold": args.utility_threshold,
    }

    report = run_full_analysis(
        args.directory,
        args.base_package,
        confirmed_utils,
        exclude_patterns,
        args.resolution,
        args.presentation_package_pattern,
        args.infrastructure_package_pattern,
        args.presentation_mode,
        weight_kwargs,
    )

    if args.format == "markdown":
      output_content = format_markdown_report(report)
    else:
      output_content = json.dumps(report, indent=2)

    if args.output:
      with open(args.output, "w") as f:
        f.write(output_content)
      print(f"Report written to {args.output}")
    else:
      print(output_content)
  else:
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
  main()
