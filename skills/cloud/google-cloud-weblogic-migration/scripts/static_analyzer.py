"""Static code analyzer for mapping Java source files and detecting cloud-unfriendly patterns in WebLogic monoliths.

This module performs recursive source code parsing on target repository folders
using regular expressions to build a quantitative inventory of the application
assets.
Specifically, it:
- Categorizes file types (Java classes, EJB descriptors, JSPs, JSF, web
configurations).
- Identifies Enterprise JavaBean categories (Stateless, Stateful,
Message-Driven, CMP/BMP Entity Beans).
- Flags cloud-unfriendly patterns (local File I/O, HTTP Session dependencies,
legacy RMI remoting, JavaMail, JMX MBeans).
- Identifies dependencies on WebLogic-specific API imports (e.g.
`weblogic.*` classes).
- Finds SOAP WebServices, JAX-RS REST endpoints, JMS resources, JNDI Lookups,
and Security role constraints.
"""

import json
import os
import re
import subprocess
import sys
import lexical_normalizer

# =====================================================================
# REGEX SCROLLING AND PATTERN MATCHING UTILITIES
# =====================================================================


def count_pattern(
    target_dir, pattern_str, extensions=None
):
  """Scans files in a directory recursively to count occurrences of a regex pattern.

  For Java/EJB/JWS files, scans against normalized code with comments stripped.

  Args:
      target_dir (str): The target directory to scan.
      pattern_str (str): The regex pattern to count.
      extensions (list[str]): File extensions to include in the scan.

  Returns:
      int: Total number of pattern occurrences found.
  """
  if extensions is None:
    extensions = [".xml", ".properties", ".ejb"]
  pattern = re.compile(pattern_str)
  count = 0
  for root, _, files in os.walk(target_dir):
    for f in files:
      if any(f.endswith(ext) for ext in extensions):
        path = os.path.join(root, f)
        try:
          if any(f.endswith(ext) for ext in [".java", ".ejb", ".jws"]):
            content = lexical_normalizer.clean_java_code(path)
          else:
            with open(path, "r", errors="ignore") as file:
              content = file.read()
          count += len(pattern.findall(content))
        except OSError:
          pass
  return count


def get_files_with_pattern(
    target_dir, pattern_str, extensions=None
):
  """Locates files in a directory recursively that contain at least one occurrence of a regex pattern.

  For Java/EJB/JWS files, scans against normalized code with comments stripped.

  Args:
      target_dir (str): The target directory to scan.
      pattern_str (str): The regex pattern to search for.
      extensions (list[str]): File extensions to include.

  Returns:
      list[str]: Relative paths of matching files from the target directory.
  """
  if extensions is None:
    extensions = [".java", ".ejb", ".jws"]
  pattern = re.compile(pattern_str)
  found_files = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if any(f.endswith(ext) for ext in extensions):
        path = os.path.join(root, f)
        try:
          if any(f.endswith(ext) for ext in [".java", ".ejb", ".jws"]):
            content = lexical_normalizer.clean_java_code(path)
          else:
            with open(path, "r", errors="ignore") as file:
              content = file.read()
          if pattern.search(content):
            found_files.append(os.path.relpath(path, target_dir))
        except OSError:
          pass
  return found_files


# =====================================================================
# UNIFIED STATIC STRUCTURE AND BLOCKERS ANALYSIS
# =====================================================================
def combine_metric(regex_val, ast_val):
  """Returns authoritative AST metric if available and greater than 0, otherwise falls back to regex count.

  Prevents double-counting when both regex matching and AST analysis detect
  occurrences.

  Args:
      regex_val (int): The count from regex matching.
      ast_val (int): The count from AST analysis.

  Returns:
      int: The combined metric value.
  """
  return ast_val if ast_val and ast_val > 0 else regex_val


def get_compatible_jdk_env():
  """Checks the default Java version and returns an env dict with JAVA_HOME set to a compatible JDK (11, 17, or 21) if needed."""
  env = os.environ.copy()
  if "JAVA_HOME" in env:
    return env

  try:
    version_res = subprocess.run(
        ["java", "-version"], capture_output=True, text=True, check=True
    )
    version_output = version_res.stderr or version_res.stdout
    match = re.search(r'(?:version\s+"([^"]+)")', version_output)
    if match:
      version_str = match.group(1)
      if version_str.startswith("1."):
        major = int(version_str.split(".")[1])
      else:
        major = int(version_str.split(".")[0])

      if 11 <= major <= 21:
        return env
  except (subprocess.SubprocessError, OSError):
    pass

  common_paths = [
      "/usr/lib/jvm/java-21-openjdk-amd64",
      "/usr/lib/jvm/openjdk-21",
      "/usr/lib/jvm/java-17-openjdk-amd64",
      "/usr/lib/jvm/java-11-openjdk-amd64",
  ]

  for path in common_paths:
    if os.path.exists(path) and os.path.exists(
        os.path.join(path, "bin", "java")
    ):
      env["JAVA_HOME"] = path
      env["PATH"] = (
          os.path.join(path, "bin") + os.path.pathsep + env.get("PATH", "")
      )
      print(
          f"Note: Overriding JAVA_HOME to compatible JDK: {path}",
          file=sys.stderr,
      )
      return env

  print(
      "Warning: Could not find a compatible JDK (11, 17, or 21) in common"
      " paths. AST parsing may fail.",
      file=sys.stderr,
  )
  return env


def get_ast_metrics(target_dir):
  """Executes the OpenRewrite AST analyzer to extract true AST metrics from Java files."""
  ast_parser_dir = os.path.join(
      os.path.dirname(os.path.abspath(__file__)), "ast_parser"
  )
  env = get_compatible_jdk_env()

  # 1. Compile the ast_parser project
  try:
    subprocess.run(
        ["mvn", "-q", "compile"],
        cwd=ast_parser_dir,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
  except FileNotFoundError as e:
    raise RuntimeError(
        "Maven ('mvn') executable not found. Please install Maven to use the "
        + "AST parser."
    ) from e
  except subprocess.CalledProcessError as e:
    print(
        f"Error: Maven compilation failed with exit status {e.returncode}.",
        file=sys.stderr,
    )
    if e.stdout:
      print(f"Maven compilation stdout:\n{e.stdout}", file=sys.stderr)
    if e.stderr:
      print(f"Maven compilation stderr:\n{e.stderr}", file=sys.stderr)
    raise RuntimeError(
        "AST parser compilation failed. Cannot proceed with static analysis."
    ) from e

  # 2. Run the analyzer
  try:
    exec_cmd = [
        "mvn",
        "-q",
        "exec:java",
        "-Dexec.mainClass=OpenRewriteAstAnalyzer",
        f"-Dexec.args={os.path.abspath(target_dir)}",
    ]
    result = subprocess.run(
        exec_cmd,
        cwd=ast_parser_dir,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
  except subprocess.CalledProcessError as e:
    print(
        f"Error: AST parser execution failed with exit status {e.returncode}.",
        file=sys.stderr,
    )
    if e.stdout:
      print(f"AST parser execution stdout:\n{e.stdout}", file=sys.stderr)
    if e.stderr:
      print(f"AST parser execution stderr:\n{e.stderr}", file=sys.stderr)
    raise RuntimeError(
        "AST parser execution failed. Cannot proceed with static analysis."
    ) from e

  # 3. Parse JSON output
  output = result.stdout.strip()
  json_start = output.find("{")
  json_end = output.rfind("}") + 1
  if json_start != -1 and json_end != -1:
    try:
      return json.loads(output[json_start:json_end])
    except json.JSONDecodeError as e:
      print(
          "Error: Failed to parse AST parser JSON output. Raw output"
          f" was:\n{output}",
          file=sys.stderr,
      )
      raise RuntimeError("AST parser generated invalid JSON output.") from e
  else:
    raise RuntimeError(
        f"AST parser did not output a valid JSON block. Raw output:\n{output}"
    )


def analyze_static(target_dir):
  """Runs the full static analysis scanning suite on the target monolith repository.

  Aggregates metrics for files, weblogic APIs, EJBs, JMS, JNDI, transactions,
  databases, security roles, MVC frameworks, and cloud-unfriendly patterns (e.g.
  raw Thread/Socket).

  Args:
      target_dir (str): The target monolith repository directory path.

  Returns:
      dict: A nested dictionary containing structural and inventory metrics.
  """
  report = {}

  # 1. General Metrics
  java_files = 0
  xml_files = 0
  jsp_files = 0
  jsf_files = 0
  jws_files = 0
  html_files = 0
  properties_files = 0
  total_files = 0
  for _, _, files in os.walk(target_dir):
    for f in files:
      total_files += 1
      ext = os.path.splitext(f)[1].lower()
      if ext in [".java", ".ejb"]:
        java_files += 1
      elif ext == ".jws":
        jws_files += 1
      elif ext == ".xml":
        xml_files += 1
      elif ext in [".jsp", ".jspx"]:
        jsp_files += 1
      elif ext in [".xhtml", ".jsf", ".faces"]:
        jsf_files += 1
      elif ext in [".html", ".htm"]:
        html_files += 1
      elif ext == ".properties":
        properties_files += 1

  report["general"] = {
      "total_files": total_files,
      "java_files": java_files,
      "xml_files": xml_files,
      "jsp_files": jsp_files,
      "jsf_files": jsf_files,
      "jws_files": jws_files,
      "html_files": html_files,
      "properties_files": properties_files,
  }

  # Fetch AST metrics for .java files
  ast = get_ast_metrics(target_dir)
  ast_wls = ast.get("weblogic_api", {})
  ast_ejb = ast.get("ejb", {})
  ast_jms = ast.get("jms", {})
  ast_jndi = ast.get("jndi", {})
  ast_tx = ast.get("transactions", {})
  ast_da = ast.get("data_access", {})
  ast_sec = ast.get("security", {})
  ast_web = ast.get("web_tier", {})
  ast_adv = ast.get("advanced_features", {})
  ast_cloud = ast.get("cloud_unfriendly_patterns", {})

  # 2. WebLogic Specific APIs
  report["weblogic_api"] = {
      "imports_count": combine_metric(
          count_pattern(
              target_dir,
              r"import weblogic\.|GenericSessionBean|GenericMessageDrivenBean",
          ),
          ast_wls.get("imports_count", 0),
      ),
      "logging_count": combine_metric(
          count_pattern(target_dir, r"weblogic\.logging|NonCatalogLogger"),
          ast_wls.get("logging_count", 0),
      ),
      "security_count": combine_metric(
          count_pattern(target_dir, r"weblogic\.security"),
          ast_wls.get("security_count", 0),
      ),
      "transaction_count": combine_metric(
          count_pattern(target_dir, r"weblogic\.transaction"),
          ast_wls.get("transaction_count", 0),
      ),
      "wls_transaction_manager_count": combine_metric(
          count_pattern(
              target_dir,
              r"weblogic\.transaction\.(TransactionManager|TxHelper)",
          ),
          ast_wls.get("wls_transaction_manager_count", 0),
      ),
      "wls_user_transaction_count": combine_metric(
          count_pattern(target_dir, r"weblogic\.transaction\.UserTransaction"),
          ast_wls.get("wls_user_transaction_count", 0),
      ),
      "coherence_count": combine_metric(
          count_pattern(target_dir, r"com\.tangosol\.|coherence\.xml"),
          ast_wls.get("coherence_count", 0),
      ),
      "workmanager_count": combine_metric(
          count_pattern(
              target_dir,
              r"weblogic\.work\.WorkManager|weblogic\.work\.WorkManagerFactory",
          ),
          ast_wls.get("workmanager_count", 0),
      ),
      "jws_api_count": combine_metric(
          count_pattern(target_dir, r"weblogic\.jws"),
          ast_wls.get("jws_api_count", 0),
      ),
      "files_with_imports": get_files_with_pattern(
          target_dir,
          r"import weblogic\.|GenericSessionBean|GenericMessageDrivenBean",
      )[:10],
  }

  # 3. EJB
  report["ejb"] = {
      "stateless_count": combine_metric(
          count_pattern(target_dir, r"@Stateless|type\s*=\s*Stateless"),
          ast_ejb.get("stateless_count", 0),
      ),
      "stateful_count": combine_metric(
          count_pattern(target_dir, r"@Stateful|type\s*=\s*Stateful"),
          ast_ejb.get("stateful_count", 0),
      ),
      "singleton_count": combine_metric(
          count_pattern(target_dir, r"@Singleton"),
          ast_ejb.get("singleton_count", 0),
      ),
      "mdb_count": combine_metric(
          count_pattern(
              target_dir,
              r"@MessageDriven|GenericMessageDrivenBean|@ejbgen:message-driven",
          ),
          ast_ejb.get("mdb_count", 0),
      ),
      "entity_bean_count": combine_metric(
          count_pattern(
              target_dir,
              r"implements EntityBean|extends EntityBean|@ejbgen:entity",
          ),
          ast_ejb.get("entity_bean_count", 0),
      ),
      "ejb_2x_home_interfaces_count": combine_metric(
          count_pattern(
              target_dir,
              r"extends EJBHome|extends EJBLocalHome|extends EJBObject|extends"
              r" EJBLocalObject",
          ),
          ast_ejb.get("ejb_2x_home_interfaces_count", 0),
      ),
      "ejb_descriptors_count": len(
          get_files_with_pattern(target_dir, r"ejb-jar\.xml", [".xml"])
      ),
  }

  # 4. JMS
  report["jms"] = {
      "imports_count": combine_metric(
          count_pattern(target_dir, r"import (javax|jakarta)\.jms\."),
          ast_jms.get("imports_count", 0),
      ),
      "jndi_lookups_count": combine_metric(
          count_pattern(target_dir, r"jms/"), ast_jndi.get("lookups_count", 0)
      ),
      "producer_count": combine_metric(
          count_pattern(
              target_dir,
              r"(javax|jakarta)\.jms\.(MessageProducer|QueueSender|TopicPublisher)",
          ),
          ast_jms.get("producer_count", 0),
      ),
      "consumer_count": combine_metric(
          count_pattern(
              target_dir,
              r"(javax|jakarta)\.jms\.(MessageConsumer|QueueReceiver|TopicSubscriber)",
          ),
          ast_jms.get("consumer_count", 0),
      ),
      "queue_count": combine_metric(
          count_pattern(target_dir, r"(javax|jakarta)\.jms\.Queue\b"),
          ast_jms.get("queue_count", 0),
      ),
      "topic_count": combine_metric(
          count_pattern(target_dir, r"(javax|jakarta)\.jms\.Topic\b"),
          ast_jms.get("topic_count", 0),
      ),
  }

  # 5. JNDI
  report["jndi"] = {
      "initial_context_count": combine_metric(
          count_pattern(target_dir, r"new InitialContext\("),
          ast_jndi.get("initial_context_count", 0),
      ),
      "lookups_count": combine_metric(
          count_pattern(target_dir, r"\.lookup\("),
          ast_jndi.get("lookups_count", 0),
      ),
  }

  # 6. Transactions
  report["transactions"] = {
      "user_transaction_count": combine_metric(
          count_pattern(target_dir, r"UserTransaction"),
          ast_tx.get("user_transaction_count", 0),
      ),
      "xa_datasource_count": combine_metric(
          count_pattern(target_dir, r"XADataSource|javax\.sql\.XA"),
          ast_tx.get("xa_datasource_count", 0),
      ),
      "xa_resource_count": combine_metric(
          count_pattern(
              target_dir, r"XAResource|(javax|jakarta)\.transaction\.xa"
          ),
          ast_tx.get("xa_resource_count", 0),
      ),
      "declarative_transaction_count": combine_metric(
          count_pattern(target_dir, r"@Transactional|@TransactionAttribute"),
          ast_tx.get("declarative_transaction_count", 0),
      ),
      "standard_transaction_manager_count": combine_metric(
          count_pattern(
              target_dir, r"(javax|jakarta)\.transaction\.TransactionManager"
          ),
          ast_tx.get("standard_transaction_manager_count", 0),
      ),
  }

  # 7. Data Access
  report["data_access"] = {
      "jdbc_connections_count": combine_metric(
          count_pattern(
              target_dir, r"java\.sql\.Connection|javax\.sql\.DataSource"
          ),
          ast_da.get("jdbc_connections_count", 0),
      ),
      "jpa_entities_count": combine_metric(
          count_pattern(target_dir, r"@Entity"),
          ast_da.get("jpa_entities_count", 0),
      ),
      "hibernate_sessions_count": combine_metric(
          count_pattern(target_dir, r"org\.hibernate\.Session"),
          ast_da.get("hibernate_sessions_count", 0),
      ),
      "spring_data_repositories_count": combine_metric(
          count_pattern(target_dir, r"org\.springframework\.data\.repository"),
          ast_da.get("spring_data_repositories_count", 0),
      ),
      "persistence_xml_count": len(
          get_files_with_pattern(target_dir, r"persistence\.xml", [".xml"])
      ),
  }

  # 8. Security
  report["security"] = {
      "roles_allowed_count": combine_metric(
          count_pattern(target_dir, r"@RolesAllowed"),
          ast_sec.get("roles_allowed_count", 0),
      ),
      "run_as_count": combine_metric(
          count_pattern(target_dir, r"@RunAs"), ast_sec.get("run_as_count", 0)
      ),
      "user_in_role_count": combine_metric(
          count_pattern(target_dir, r"\.isUserInRole\("),
          ast_sec.get("user_in_role_count", 0),
      ),
      "user_principal_count": combine_metric(
          count_pattern(target_dir, r"\.getUserPrincipal\("),
          ast_sec.get("user_principal_count", 0),
      ),
  }

  # 9. Web Tier
  report["web_tier"] = {
      "jsp_files_count": len(
          get_files_with_pattern(target_dir, r".*", [".jsp", ".jspx"])
      ),
      "servlets_count": combine_metric(
          count_pattern(target_dir, r"extends HttpServlet|@WebServlet"),
          ast_web.get("servlets_count", 0),
      ),
      "filters_count": combine_metric(
          count_pattern(target_dir, r"implements Filter|@WebFilter"),
          ast_web.get("filters_count", 0),
      ),
      "listeners_count": combine_metric(
          count_pattern(target_dir, r"ServletContextListener|@WebListener"),
          ast_web.get("listeners_count", 0),
      ),
      "jax_rs_endpoints_count": combine_metric(
          count_pattern(target_dir, r"@Path|(javax|jakarta)\.ws\.rs\."),
          ast_web.get("jax_rs_endpoints_count", 0),
      ),
      "spring_controllers_count": combine_metric(
          count_pattern(target_dir, r"@Controller|@RestController"),
          ast_web.get("spring_controllers_count", 0),
      ),
      "struts_count": combine_metric(
          count_pattern(target_dir, r"org\.apache\.struts"),
          ast_web.get("struts_count", 0),
      ),
      "jsf_count": combine_metric(
          count_pattern(
              target_dir, r"javax\.faces|jakarta\.faces|@ManagedBean"
          ),
          ast_web.get("jsf_count", 0),
      ),
      "web_xml_count": len(
          get_files_with_pattern(target_dir, r"web\.xml", [".xml"])
      ),
      "weblogic_xml_count": len(
          get_files_with_pattern(target_dir, r"weblogic\.xml", [".xml"])
      ),
      "http_sessions_count": combine_metric(
          count_pattern(target_dir, r"HttpSession|request\.getSession\("),
          ast_web.get("http_sessions_count", 0),
      ),
  }

  # 10. Advanced Features
  report["advanced_features"] = {
      "work_managers_count": combine_metric(
          count_pattern(target_dir, r"work-manager|commonj\.work"),
          ast_adv.get("work_managers_count", 0),
      ),
      "timers_count": combine_metric(
          count_pattern(
              target_dir, r"javax\.ejb\.TimerService|commonj\.timers"
          ),
          ast_adv.get("timers_count", 0),
      ),
      "resource_adapters_count": len(
          get_files_with_pattern(
              target_dir, r"weblogic-ra\.xml|ra\.xml", [".xml"]
          )
      ),
      "classloading_custom_count": count_pattern(
          target_dir,
          r"prefer-application-packages|prefer-application-resources",
      ),
      "web_services_count": combine_metric(
          count_pattern(
              target_dir, r"weblogic-webservices\.xml|@WebService|@WebMethod"
          ),
          ast_adv.get("web_services_count", 0),
      ),
      "jax_rpc_count": combine_metric(
          count_pattern(target_dir, r"javax\.xml\.rpc"),
          ast_adv.get("jax_rpc_count", 0),
      ),
      "jax_ws_count": combine_metric(
          count_pattern(target_dir, r"javax\.jws|jakarta\.jws"),
          ast_adv.get("jax_ws_count", 0),
      ),
      "batch_processing_count": combine_metric(
          count_pattern(
              target_dir, r"javax\.batch\.api|org\.springframework\.batch"
          ),
          ast_adv.get("batch_processing_count", 0),
      ),
      "jmx_mbeans_count": combine_metric(
          count_pattern(
              target_dir, r"javax\.management\.MBeanServer|weblogic\.management"
          ),
          ast_adv.get("jmx_mbeans_count", 0),
      ),
  }

  # 11. Cloud-Unfriendly Patterns
  ip_regex = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
  total_ips = count_pattern(target_dir, ip_regex)
  loopback_ips = count_pattern(target_dir, r"\b127\.0\.0\.1\b|\b0\.0\.0\.0\b")
  hardcoded_ips = max(0, total_ips - loopback_ips)

  path_regex = r"\"/(opt|var|usr|etc|bin|srv)/|\"[a-zA-Z]:\\\\"
  absolute_paths = count_pattern(target_dir, path_regex)
  raw_threads = combine_metric(
      count_pattern(target_dir, r"new Thread\("),
      ast_cloud.get("raw_threads_count", 0),
  )
  native_processes = combine_metric(
      count_pattern(
          target_dir, r"Runtime\.getRuntime\(\)\.exec\b|ProcessBuilder\b"
      ),
      ast_cloud.get("native_processes_count", 0),
  )
  direct_sockets = combine_metric(
      count_pattern(target_dir, r"new\s+(Server)?Socket\("),
      ast_cloud.get("direct_sockets_count", 0),
  )
  jaas_login_modules = combine_metric(
      count_pattern(
          target_dir,
          r"implements\s+LoginModule|extends\s+UsernamePasswordLoginModule",
      ),
      ast_cloud.get("jaas_login_modules_count", 0),
  )
  specific_proxies = combine_metric(
      count_pattern(target_dir, r"HttpClusterServlet|HttpProxyServlet"),
      ast_cloud.get("specific_proxies_count", 0),
  )
  file_io = combine_metric(
      count_pattern(
          target_dir,
          r"java\.io\.FileOutputStream|java\.io\.FileWriter|java\.nio\.file\.Files\.write|java\.io\.RandomAccessFile",
      ),
      ast_cloud.get("file_io_count", 0),
  )
  rmi_corba = combine_metric(
      count_pattern(
          target_dir,
          r"java\.rmi\.|javax\.rmi\.|UnicastRemoteObject|Naming\.lookup",
      ),
      ast_cloud.get("rmi_corba_count", 0),
  )
  java_mail = combine_metric(
      count_pattern(target_dir, r"javax\.mail\.|jakarta\.mail\."),
      ast_cloud.get("java_mail_count", 0),
  )

  report["cloud_unfriendly_patterns"] = {
      "hardcoded_ips_count": hardcoded_ips,
      "absolute_paths_count": absolute_paths,
      "raw_threads_count": raw_threads,
      "native_processes_count": native_processes,
      "direct_sockets_count": direct_sockets,
      "jaas_login_modules_count": jaas_login_modules,
      "specific_proxies_count": specific_proxies,
      "file_io_count": file_io,
      "rmi_corba_count": rmi_corba,
      "java_mail_count": java_mail,
  }

  return report
