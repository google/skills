"""WebLogic domain configuration parser for extracting database connection pools, JMS settings, and WLST automation scripts.

This module parses WebLogic domain configurations (like `config.xml` and its
sub-descriptors) to identify infrastructure and middleware setups:
- JDBC connection configurations (database drivers, connection pool sizes,
database URLs, JNDI names).
- JMS System resources (queues, topics, connection factories).
- WLST scripting setups (discovering `.py` scripts containing automation
routines).

It provides structured dictionaries mapped to the original WebLogic configs to
assist in provisioning matching GCP services like Cloud SQL, Cloud Memorystore,
or Cloud Pub/Sub.
"""

import os
import xml.etree.ElementTree as ET

# =====================================================================
# GENERAL XML UTILITIES
# =====================================================================


def strip_ns(tag):
  """Strips namespace tags from XML elements.

  Args:
      tag (str): The raw XML tag name.

  Returns:
      str: The tag name without namespace.
  """
  if "}" in tag:
    return tag.split("}", 1)[1]
  return tag


def parse_xml_to_dict(element):
  """Converts XML elements to simplified nested dictionaries.

  Args:
      element (xml.etree.ElementTree.Element): The XML element to parse.

  Returns:
      dict | str: Parsed configuration dictionary or element value.
  """
  res = {}
  tag = strip_ns(element.tag)
  children = list(element)
  if children:
    child_dicts = {}
    for child in children:
      child_tag = strip_ns(child.tag)
      child_val = parse_xml_to_dict(child)
      if child_tag in child_dicts:
        if not isinstance(child_dicts[child_tag], list):
          child_dicts[child_tag] = [child_dicts[child_tag]]
        child_dicts[child_tag].append(child_val)
      else:
        child_dicts[child_tag] = child_val
    res = child_dicts
  else:
    res = element.text.strip() if element.text else ""
  return res


# =====================================================================
# WEBLOGIC DOMAIN RESOURCE DESCRIPTOR PARSERS
# =====================================================================
def parse_jdbc_descriptor(path):
  """Parses a WebLogic JDBC system resource descriptor XML file to extract JNDI name and URL details.

  Args:
      path (str): File path to the JDBC descriptor XML.

  Returns:
      dict: A dictionary of parsed JDBC configurations.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {}
    if isinstance(data, dict):
      ds = data.get("jdbc-data-source-params", {})
      if isinstance(ds, dict):
        summary["jndi_names"] = ds.get("jndi-name", "")
      driver = data.get("jdbc-driver-params", {})
      if isinstance(driver, dict):
        summary["url"] = driver.get("url", "")
        summary["driver_name"] = driver.get("driver-name", "")
        props = driver.get("properties", {})
        if isinstance(props, dict):
          prop_list = props.get("property", [])
          if not isinstance(prop_list, list):
            prop_list = [prop_list]
          for p in prop_list:
            if isinstance(p, dict) and p.get("name") == "user":
              summary["username"] = p.get("value", "")
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse JDBC descriptor {path}: {str(e)}"}


def parse_jms_descriptor(path):
  """Parses a WebLogic JMS system resource descriptor XML file to extract queues, topics, and connection factories.

  Args:
      path (str): File path to the JMS descriptor XML.

  Returns:
      dict: A dictionary listing queues, topics, and connection factories.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {"queues": [], "topics": [], "connection_factories": []}

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      for q in get_as_list(data, "queue"):
        if isinstance(q, dict):
          summary["queues"].append(
              {"name": q.get("name"), "jndi_name": q.get("jndi-name")}
          )
      for t in get_as_list(data, "topic"):
        if isinstance(t, dict):
          summary["topics"].append(
              {"name": t.get("name"), "jndi_name": t.get("jndi-name")}
          )
      for cf in get_as_list(data, "connection-factory"):
        if isinstance(cf, dict):
          summary["connection_factories"].append(
              {"name": cf.get("name"), "jndi_name": cf.get("jndi-name")}
          )
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse JMS descriptor {path}: {str(e)}"}


def resolve_descriptor_path(config_path, desc_file):
  """Resolves a descriptor file path relative to config.xml directory or domain root.

  Handles cases where descriptor-file-name includes or excludes the 'config/'
  prefix.

  Args:
      config_path (str): File path to config.xml.
      desc_file (str): Descriptor file name.

  Returns:
      str: Resolved file path to the descriptor or empty string if not found.
  """
  if not desc_file:
    return ""
  candidates = [
      os.path.join(os.path.dirname(config_path), desc_file),
      os.path.join(os.path.dirname(os.path.dirname(config_path)), desc_file),
  ]
  if desc_file.startswith("config/"):
    candidates.append(os.path.join(os.path.dirname(config_path), desc_file[7:]))
  for cand in candidates:
    if os.path.exists(cand):
      return cand
  return candidates[0]


def parse_config_xml(path):
  """Parses WebLogic domain config.xml to extract JDBC, JMS, and deployment configurations.

  Parses the domain configuration config.xml file to identify defined JDBC/JMS
  resources and deployments, automatically loading referenced system resource
  descriptors.

  Args:
      path (str): File path to config.xml.

  Returns:
      dict: Summary of defined domain configurations.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {
        "domain_name": root.attrib.get("name", "Unknown"),
        "jdbc_resources": [],
        "jms_resources": [],
        "deployments": [],
    }

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      for jdbc in get_as_list(data, "jdbc-system-resource"):
        if isinstance(jdbc, dict):
          name = jdbc.get("name")
          desc_file = jdbc.get("descriptor-file-name")
          desc_path = resolve_descriptor_path(path, desc_file)
          details = {}
          if desc_path and os.path.exists(desc_path):
            details = parse_jdbc_descriptor(desc_path)
          else:
            details = {"warning": f"Descriptor file {desc_file} not found"}
          summary["jdbc_resources"].append(
              {"name": name, "descriptor_file": desc_file, "details": details}
          )
      for jms in get_as_list(data, "jms-system-resource"):
        if isinstance(jms, dict):
          name = jms.get("name")
          desc_file = jms.get("descriptor-file-name")
          desc_path = resolve_descriptor_path(path, desc_file)
          details = {}
          if desc_path and os.path.exists(desc_path):
            details = parse_jms_descriptor(desc_path)
          else:
            details = {"warning": f"Descriptor file {desc_file} not found"}
          summary["jms_resources"].append(
              {"name": name, "descriptor_file": desc_file, "details": details}
          )
      for app in get_as_list(data, "app-deployment"):
        if isinstance(app, dict):
          summary["deployments"].append({
              "name": app.get("name"),
              "source_path": app.get("source-path"),
              "targets": app.get("target"),
          })
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse config.xml: {str(e)}"}


# =====================================================================
# AUTOMATION SCRIPT SCANNERS AND DOMAIN ORCHESTRATION
# =====================================================================
def scan_for_wlst(target_dir):
  """Scans the repository recursively to locate Python WLST administration scripts.

  Args:
      target_dir (str): The repository root.

  Returns:
      list[str]: Relative paths of identified WLST scripts.
  """
  wlst_files = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.endswith(".py"):
        path = os.path.join(root, f)
        try:
          with open(path, "r", errors="ignore") as file:
            content = file.read()
            if (
                "connect(" in content
                or "cmo." in content
                or "wlst" in content.lower()
            ):
              wlst_files.append(os.path.relpath(path, target_dir))
        except OSError:
          pass
  return wlst_files


def parse_domain_config(target_dir):
  """Scans the directory for WebLogic config/config.xml configurations and maps WLST scripts.

  Args:
      target_dir (str): Target repository directory path.

  Returns:
      dict: A compiled report mapping domains and WLST scripts.
  """
  report = {"domains": [], "wlst_scripts": []}

  config_files = []
  for root, dirs, files in os.walk(target_dir):
    if "config.xml" in files:
      if os.path.basename(root) == "config":
        config_files.append(os.path.join(root, "config.xml"))

  for config in config_files:
    report["domains"].append({
        "path": os.path.relpath(config, target_dir),
        "analysis": parse_config_xml(config),
    })

  report["wlst_scripts"] = scan_for_wlst(target_dir)
  return report
