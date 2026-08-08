"""Dynamic Maven POM builder for generating temporary pom.xml files to support OpenRewrite refactoring.

This module scans a target legacy directory recursively to calculate Java source
roots by mapping packages. It then writes a temporary, minimal `pom.xml`
pointing to those roots.
This allows modern AST/refactoring toolkits (like OpenRewrite) to parse and
compile the codebase, even if the monolith originally used Ant or lacked
structured dependency files.
"""

import os
import sys
import xml.etree.ElementTree as ET
import build_parser
import jar_analyzer
import lexical_normalizer

# =====================================================================
# SOURCE DIRECTORY RESOLUTION UTILITIES
# =====================================================================


def extract_package(file_path):
  """Extracts package declaration from a Java source file using lexical normalization.

  Immune to commented-out package statements or multi-line comments.

  Args:
      file_path (str): File path to the Java source file.

  Returns:
      str | None: Package name or None.
  """
  return lexical_normalizer.get_package_name(file_path)


def detect_source_roots(target_dir):
  """Detects Java source roots by comparing file paths with package declarations.

  Args:
      target_dir (str): Monolith repository folder to scan.

  Returns:
      list[str]: Relative paths of identified source roots.
  """
  java_files = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.endswith(".java"):
        java_files.append(os.path.join(root, f))

  source_roots = set()

  for path in java_files:
    pkg = extract_package(path)
    if pkg:
      # Calculate package depth (number of dots + 1)
      depth = len(pkg.split("."))

      # Go up 'depth' times from the file's parent directory
      current = os.path.dirname(path)
      for _ in range(depth):
        current = os.path.dirname(current)

      source_roots.add(os.path.relpath(current, target_dir))
    else:
      # No package declaration, class is in default package.
      # Source root is the parent directory of the file.
      source_roots.add(os.path.relpath(os.path.dirname(path), target_dir))

  return list(source_roots) if source_roots else ["."]


# =====================================================================
# POM GENERATION AND WRITE OPERATIONS
# =====================================================================
def generate_pom(target_dir, source_roots):
  """Generates a minimal pom.xml inside target_dir pointing to the best source root.

  Injects local JARs and existing Maven dependencies to support OpenRewrite AST
  parsing.

  Args:
      target_dir (str): Directory where pom.xml will be written.
      source_roots (list[str]): List of detected source roots.
  """
  src_dir = "src"
  if source_roots:
    # Prefer roots containing 'src'
    src_roots = [r for r in source_roots if "src" in r]
    if src_roots:
      src_dir = src_roots[0]
    else:
      src_dir = source_roots[0]

  # Find existing dependencies and Java version
  java_version = "1.8"
  maven_deps = []

  poms = build_parser.find_files(target_dir, ["pom.xml"])
  for pom in poms:
    # Avoid reading the pom we are about to overwrite if it's already there
    if os.path.abspath(pom) == os.path.abspath(
        os.path.join(target_dir, "pom.xml")
    ):
      continue
    try:
      tree = ET.parse(pom)
      root = tree.getroot()
      deps = build_parser.parse_pom_dependencies(root)
      maven_deps.extend(deps)
      props = build_parser.parse_pom_properties(root)
      jv = build_parser.get_java_version(root, props)
      if jv != "Unknown":
        java_version = jv
    except (ET.ParseError, OSError):
      pass

  # Find local JARs
  jars_report = jar_analyzer.analyze_local_jars(target_dir)
  all_jars = (
      jars_report.get("weblogic_specific", [])
      + jars_report.get("java_ee_legacy", [])
      + jars_report.get("others", [])
  )

  deps_xml = ""
  if all_jars or maven_deps:
    deps_xml += "    <dependencies>\n"

    # Inject Maven dependencies
    for dep in maven_deps:
      g = dep.get("groupId", "unknown")
      a = dep.get("artifactId", "unknown")
      v = dep.get("version", "1.0")
      deps_xml += f"""        <dependency>
            <groupId>{g}</groupId>
            <artifactId>{a}</artifactId>
            <version>{v}</version>
        </dependency>\n"""

    # Inject local JARs as system scope
    for idx, jar_meta in enumerate(all_jars):
      jar_path = jar_meta["relative_path"]
      artifact_id = jar_meta["filename"].replace(".jar", "").replace(".", "-")
      jar_path = jar_path.replace("\\", "/")
      deps_xml += f"""        <dependency>
            <groupId>local.legacy</groupId>
            <artifactId>{artifact_id}_{idx}</artifactId>
            <version>1.0</version>
            <scope>system</scope>
            <systemPath>${{project.basedir}}/{jar_path}</systemPath>
        </dependency>\n"""

    deps_xml += "    </dependencies>\n"

  pom_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>temp-migration</groupId>
    <artifactId>temp-project</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.source>{java_version}</maven.compiler.source>
        <maven.compiler.target>{java_version}</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
{deps_xml}    <build>
        <sourceDirectory>{src_dir}</sourceDirectory>
    </build>
</project>
"""
  pom_path = os.path.join(target_dir, "pom.xml")
  with open(pom_path, "w") as f:
    f.write(pom_content)
  print(f"Generated temporary pom.xml pointing to source directory: {src_dir}")


# =====================================================================
# CLI ENTRY POINT
# =====================================================================
def main():
  """CLI main entry point."""
  if len(sys.argv) < 2:
    print("Usage: generate_temp_pom.py <target_directory>")
    sys.exit(1)

  target_dir = sys.argv[1]
  roots = detect_source_roots(target_dir)
  generate_pom(target_dir, roots)


if __name__ == "__main__":
  main()
