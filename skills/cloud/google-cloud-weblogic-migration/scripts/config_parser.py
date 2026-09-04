"""XML descriptor parser for mapping Java EE and WebLogic-specific configurations in a monolith.

This module scans a legacy WebLogic application root to discover and parse
standard Java EE and WebLogic deployment descriptors. Specifically,
it parses:
- web.xml & weblogic.xml (servlets, filters, mapping routes, session
configurations, and security constraints).
- ejb-jar.xml & weblogic-ejb-jar.xml (Enterprise JavaBeans definitions, JNDI
bindings, and security roles).

It strips XML namespace headers dynamically and parses tag-trees into python
dictionaries, making configuration metadata readily available for microservice
boundary mapping and refactoring.
"""

import os
import xml.etree.ElementTree as ET

# =====================================================================
# GENERAL XML PARSING AND UTILITY FUNCTIONS
# =====================================================================


def strip_ns(tag):
  """Strips the namespace prefix from an XML tag.

  Args:
      tag (str): The XML element tag string (possibly containing namespace).

  Returns:
      str: The raw tag name without namespace.
  """
  if "}" in tag:
    return tag.split("}", 1)[1]
  return tag


def parse_xml_to_dict(element):
  """Converts an XML ElementTree Element into a python dictionary.

  Recursively converts an XML ElementTree Element into a python dictionary
  representation, simplifying leaf node elements into plain strings.

  Args:
      element (xml.etree.ElementTree.Element): The XML element.

  Returns:
      dict | str: A dictionary map representing the XML node and its children,
      or a string value.
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
# SPECIFIC DEPLOYMENT DESCRIPTOR PARSERS
# =====================================================================
def parse_web_xml(path):
  """Parses a Java EE standard web.xml file.

  Parses a Java EE standard web.xml file to extract servlets, filters, resource
  references, and security constraints (URL patterns & authorization roles).

  Args:
      path (str): File path to web.xml.

  Returns:
      dict: A structured summary of servlets, filters, resource refs, and
      security parameters.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {
        "servlets": [],
        "filters": [],
        "security_constraints": [],
        "resource_refs": [],
    }

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      for s in get_as_list(data, "servlet"):
        if isinstance(s, dict):
          summary["servlets"].append({
              "name": s.get("servlet-name", ""),
              "class": s.get("servlet-class", ""),
          })
      for f in get_as_list(data, "filter"):
        if isinstance(f, dict):
          summary["filters"].append({
              "name": f.get("filter-name", ""),
              "class": f.get("filter-class", ""),
          })
      for r in get_as_list(data, "resource-ref"):
        if isinstance(r, dict):
          summary["resource_refs"].append({
              "name": r.get("res-ref-name", ""),
              "type": r.get("res-type", ""),
              "auth": r.get("res-auth", ""),
          })
      for c in get_as_list(data, "security-constraint"):
        if isinstance(c, dict):
          web_resource = c.get("web-resource-collection", {})
          auth_constraint = c.get("auth-constraint", {})
          summary["security_constraints"].append({
              "url_patterns": (
                  get_as_list(web_resource, "url-pattern")
                  if isinstance(web_resource, dict)
                  else []
              ),
              "roles": (
                  get_as_list(auth_constraint, "role-name")
                  if isinstance(auth_constraint, dict)
                  else []
              ),
          })
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse web.xml: {str(e)}"}


def parse_weblogic_xml(path):
  """Parses a weblogic.xml file.

  Parses a weblogic.xml file to extract security role assignments
  and mapping descriptions for EJB JNDI names.

  Args:
      path (str): File path to weblogic.xml.

  Returns:
      dict: A structured summary of assignments and descriptions.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {
        "security_role_assignments": [],
        "ejb_reference_descriptions": [],
    }

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      for ra in get_as_list(data, "security-role-assignment"):
        if isinstance(ra, dict):
          summary["security_role_assignments"].append({
              "role_name": ra.get("role-name", ""),
              "principals": get_as_list(ra, "principal-name"),
          })
      for ejb_ref in get_as_list(data, "ejb-reference-description"):
        if isinstance(ejb_ref, dict):
          summary["ejb_reference_descriptions"].append({
              "ejb_ref_name": ejb_ref.get("ejb-ref-name", ""),
              "jndi_name": ejb_ref.get("jndi-name", ""),
          })
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse weblogic.xml: {str(e)}"}


def parse_ejb_jar_xml(path):
  """Parses a Java EE standard ejb-jar.xml file.

  Parses a Java EE standard ejb-jar.xml descriptor to extract stateless,
  stateful, and message-driven enterprise beans (EJB) configuration details.

  Args:
      path (str): File path to ejb-jar.xml.

  Returns:
      dict: A dictionary list containing parsed enterprise beans.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {"enterprise_beans": []}

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      ejb_container = data.get("enterprise-beans", {})
      if isinstance(ejb_container, dict):
        for sb in get_as_list(ejb_container, "session"):
          if isinstance(sb, dict):
            summary["enterprise_beans"].append({
                "name": sb.get("ejb-name", ""),
                "type": "Session (" + sb.get("session-type", "Stateless") + ")",
                "class": sb.get("ejb-class", ""),
                "business_local": sb.get("local", ""),
                "business_remote": sb.get("remote", ""),
            })
        for mdb in get_as_list(ejb_container, "message-driven"):
          if isinstance(mdb, dict):
            summary["enterprise_beans"].append({
                "name": mdb.get("ejb-name", ""),
                "type": "Message-Driven",
                "class": mdb.get("ejb-class", ""),
                "destination_type": mdb.get(
                    "messaging-type", "javax.jms.MessageListener"
                ),
            })
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse ejb-jar.xml: {str(e)}"}


def parse_weblogic_ejb_jar_xml(path):
  """Parses a weblogic-ejb-jar.xml file.

  Parses a weblogic-ejb-jar.xml descriptor to map EJBs to their
  actual JNDI names.

  Args:
      path (str): File path to weblogic-ejb-jar.xml.

  Returns:
      dict: A mapping of enterprise beans to their JNDI descriptors.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)
    summary = {"weblogic_enterprise_beans": []}

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      wles = get_as_list(data, "weblogic-enterprise-bean")
      for wle in wles:
        if isinstance(wle, dict):
          summary["weblogic_enterprise_beans"].append({
              "name": wle.get("ejb-name", ""),
              "jndi_name": wle.get("jndi-name", ""),
              "local_jndi_name": wle.get("local-jndi-name", ""),
          })
    return summary
  except (ET.ParseError, OSError) as e:
    return {"error": f"Failed to parse weblogic-ejb-jar.xml: {str(e)}"}


# =====================================================================
# CONFIGURATION SCANNING AND ORCHESTRATION
# =====================================================================
def find_files(target_dir, filenames):
  """Helper to recursively find specific configuration file names in a repository.

  Args:
      target_dir (str): The directory to search.
      filenames (list[str]): The names of files to match (case-insensitive).

  Returns:
      list[str]: Absolute paths to matching files.
  """
  found = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.lower() in [name.lower() for name in filenames]:
        found.append(os.path.join(root, f))
  return found


def parse_configurations(target_dir):
  """Orchestrates the parsing of standard and descriptors across a repository directory.

  Args:
      target_dir (str): The target repository directory path.

  Returns:
      dict: A dictionary containing lists of parsed descriptors mapped to their
      relative file paths.
  """
  report = {
      "web_xml": [],
      "weblogic_xml": [],
      "ejb_jar_xml": [],
      "weblogic_ejb_jar_xml": [],
  }

  for path in find_files(target_dir, ["web.xml"]):
    report["web_xml"].append(
        {"path": os.path.relpath(path, target_dir), "data": parse_web_xml(path)}
    )

  for path in find_files(target_dir, ["weblogic.xml"]):
    report["weblogic_xml"].append({
        "path": os.path.relpath(path, target_dir),
        "data": parse_weblogic_xml(path),
    })

  for path in find_files(target_dir, ["ejb-jar.xml"]):
    report["ejb_jar_xml"].append({
        "path": os.path.relpath(path, target_dir),
        "data": parse_ejb_jar_xml(path),
    })

  for path in find_files(target_dir, ["weblogic-ejb-jar.xml"]):
    report["weblogic_ejb_jar_xml"].append({
        "path": os.path.relpath(path, target_dir),
        "data": parse_weblogic_ejb_jar_xml(path),
    })

  return report
