"""Build system parser for scanning Maven pom.xml and Apache Ant build.xml configurations in WebLogic monoliths.

This module recursively scans legacy applications to identify and parse build
files.
It analyzes:
- pom.xml (Maven dependencies, plugins, compiler configurations, and version
properties).
- build.xml (Apache Ant scripts locations to flag build-system modernization
requirements).

It maps dependency listings, flags specific or outdated WebLogic and Java EE
library imports, and determines the target compiler Java version of the legacy
monolith modules.
"""

import os
import re
import xml.etree.ElementTree as ET

# =====================================================================
# GENERAL XML UTILITIES
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


# =====================================================================
# MAVEN POM PARSING & DEPENDENCY METRICS
# =====================================================================
def parse_pom_dependencies(root):
  """Parses pom.xml dependencies under the `<dependencies>` node.

  Args:
      root (xml.etree.ElementTree.Element): The XML root element of pom.xml.

  Returns:
      list[dict]: A list of dependency dictionaries containing groupId,
      artifactId, and version.
  """
  dependencies = []
  ns = ""
  if root.tag.startswith("{"):
    ns = root.tag.split("}")[0] + "}"

  deps_node = root.find(f"./{ns}dependencies")
  if deps_node is not None:
    for dep in deps_node.findall(f"./{ns}dependency"):
      group_id_node = dep.find(f"./{ns}groupId")
      artifact_id_node = dep.find(f"./{ns}artifactId")
      version_node = dep.find(f"./{ns}version")

      group_id = group_id_node.text.strip() if group_id_node is not None else ""
      artifact_id = (
          artifact_id_node.text.strip() if artifact_id_node is not None else ""
      )
      version = (
          version_node.text.strip() if version_node is not None else "managed"
      )

      dependencies.append(
          {"groupId": group_id, "artifactId": artifact_id, "version": version}
      )
  return dependencies


def parse_pom_properties(root):
  """Parses properties defined inside the `<properties>` block of pom.xml.

  Args:
      root (xml.etree.ElementTree.Element): The XML root element of pom.xml.

  Returns:
      dict: A dictionary of key-value property settings.
  """
  properties = {}
  ns = ""
  if root.tag.startswith("{"):
    ns = root.tag.split("}")[0] + "}"

  props_node = root.find(f"./{ns}properties")
  if props_node is not None:
    for prop in props_node:
      tag = strip_ns(prop.tag)
      properties[tag] = prop.text.strip() if prop.text else ""
  return properties


def get_java_version(root, properties):
  """Determines the target Java version from POM properties or the maven-compiler-plugin config.

  Args:
      root (xml.etree.ElementTree.Element): The XML root element of pom.xml.
      properties (dict): Already parsed POM properties mapping.

  Returns:
      str: String version identifier (e.g. '1.8', '11', '17') or 'Unknown'.
  """
  ns = ""
  if root.tag.startswith("{"):
    ns = root.tag.split("}")[0] + "}"

  java_version_keys = [
      "java.version",
      "maven.compiler.source",
      "maven.compiler.target",
      "jdk.version",
  ]
  for key in java_version_keys:
    if key in properties:
      return properties[key]

  plugins = root.findall(f".//{ns}plugin")
  for plugin in plugins:
    art_id = plugin.find(f"./{ns}artifactId")
    if art_id is not None and art_id.text == "maven-compiler-plugin":
      config = plugin.find(f"./{ns}configuration")
      if config is not None:
        source = config.find(f"./{ns}source")
        target = config.find(f"./{ns}target")
        if source is not None:
          return source.text.strip()
        if target is not None:
          return target.text.strip()
  return "Unknown"


def analyze_dependencies(dependencies):
  """Categorizes list of parsed dependencies into WebLogic-specific, legacy Java EE standard, or other third party libraries.

  Args:
      dependencies (list[dict]): List of dependencies to categorize.

  Returns:
      dict: A nested dictionary of categorized dependency lists.
  """
  analysis = {"weblogic_specific": [], "java_ee_legacy": [], "others": []}

  wls_patterns = [
      re.compile(r"com\.oracle\.weblogic"),
      re.compile(r"weblogic"),
  ]

  java_ee_patterns = [
      re.compile(r"javax\.j2ee"),
      re.compile(r"javax\.ejb"),
      re.compile(r"javax\.jms"),
      re.compile(r"javax\.servlet"),
      re.compile(r"javax\.transaction"),
      re.compile(r"glassfish"),
      re.compile(r"jboss"),
  ]

  for dep in dependencies:
    g_id = dep["groupId"]
    a_id = dep["artifactId"]

    is_wls = any(p.search(g_id) or p.search(a_id) for p in wls_patterns)
    is_legacy = any(p.search(g_id) or p.search(a_id) for p in java_ee_patterns)

    if is_wls:
      analysis["weblogic_specific"].append(dep)
    elif is_legacy:
      analysis["java_ee_legacy"].append(dep)
    else:
      analysis["others"].append(dep)

  return analysis


def parse_pom(path):
  """Parses a single pom.xml file to extract properties, Java version, and dependency analysis.

  Args:
      path (str): File path to pom.xml.

  Returns:
      dict: A summary dictionary of properties and dependencies.
  """
  try:
    tree = ET.parse(path)
    root = tree.getroot()

    properties = parse_pom_properties(root)
    java_version = get_java_version(root, properties)
    dependencies = parse_pom_dependencies(root)
    dep_analysis = analyze_dependencies(dependencies)

    return {
        "java_version": java_version,
        "properties": properties,
        "dependencies_summary": {
            "total": len(dependencies),
            "weblogic_specific_count": len(dep_analysis["weblogic_specific"]),
            "java_ee_legacy_count": len(dep_analysis["java_ee_legacy"]),
        },
        "weblogic_dependencies": dep_analysis["weblogic_specific"],
        "legacy_java_ee_dependencies": dep_analysis["java_ee_legacy"],
    }
  except Exception as e:
    return {"error": f"Failed to parse pom.xml: {str(e)}"}


# =====================================================================
# BUILD SYSTEM DISCOVERY AND RUNTIME ORCHESTRATION
# =====================================================================
def find_files(target_dir, filenames):
  """Recursively scans the directory to find files matching given file names.

  Args:
      target_dir (str): Directory path to scan.
      filenames (list[str]): File names to search.

  Returns:
      list[str]: Absolute paths to files found.
  """
  found = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.lower() in [name.lower() for name in filenames]:
        found.append(os.path.join(root, f))
  return found


def parse_build_files(target_dir):
  """Locates and parses all Maven and Ant build descriptors across the monolith directory.

  Args:
      target_dir (str): The repository root directory.

  Returns:
      dict: A compiled report dictionary categorizing project structures.
  """
  report = {"maven_projects": [], "ant_projects": []}

  poms = find_files(target_dir, ["pom.xml"])
  for pom in poms:
    report["maven_projects"].append(
        {"path": os.path.relpath(pom, target_dir), "analysis": parse_pom(pom)}
    )

  ants = find_files(target_dir, ["build.xml"])
  for ant in ants:
    report["ant_projects"].append({
        "path": os.path.relpath(ant, target_dir),
        "info": (
            "Ant build file detected. Use analyze_jars.py to scan local"
            " libraries if dependencies are checked-in."
        ),
    })

  return report
