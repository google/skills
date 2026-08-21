"""Java import statement parser for mapping class-to-class dependency connections in a monolith.

This module statically processes Java files recursively to construct a directed
dependency graph.
It extracts:
- Package namespaces and class names.
- Explicit import dependencies (including wildcard imports and static imports).
- WebLogic Javadoc annotations mapping target EJBs (e.g. `@ejbgen:local-link` or
`@target-ejb`).

It resolves dependencies to identify internal-only coupling, filtering out
standard JDK and external libraries based on a common base package prefix to
yield a clean internal class graph.
"""

import os
import re
import lexical_normalizer

# =====================================================================
# INDIVIDUAL JAVA FILE PARSING UTILITIES
# =====================================================================


def get_class_name_from_path(file_path):
  """Extracts the simple class name from a file path.

  Args:
      file_path (str): File path of the Java source file.

  Returns:
      str: The class name (e.g. 'PatientSessionEJB').
  """
  return os.path.splitext(os.path.basename(file_path))[0]


def extract_package_and_imports(file_path):
  """Extracts package and imports from a Java file.

  Parses a Java file using lexical normalization to extract its package
  declaration, import statements, and WebLogic EJBGen target links safely across
  line breaks.

  Args:
      file_path (str): File path to Java source file.

  Returns:
      tuple[str | None, list[str]]: The package FQCN prefix, and list of
      imported FQCNs.
  """
  try:
    tokens = lexical_normalizer.tokenize_java_file(file_path)
    package = lexical_normalizer.get_package_name(file_path)

    # Extract imports from normalized code text (no string literals or comments
    # to trigger false positives)
    imports = re.findall(
        r"\bimport\s+(?:static\s+)?([a-zA-Z0-9_\.\*]+)\s*;",
        tokens["code_text_no_strings"],
    )

    # Extract WebLogic target-ejb and local-link annotations from preserved
    # Javadocs
    for javadoc in tokens["javadocs"]:
      for match in re.finditer(
          r"(?:target-ejb|@ejbgen:local-link)\s*(?:=\s*|\s+target-ejb\s*=\s*|\s+)([a-zA-Z0-9_]+)",
          javadoc,
      ):
        imports.append(match.group(1))
      for match in re.finditer(r"target-ejb\s*=\s*([a-zA-Z0-9_]+)", javadoc):
        imports.append(match.group(1))

    return package, list(set(imports))
  except OSError:
    return None, []


# =====================================================================
# BASE PACKAGE PREFIX RESOLUTION AND ORCHESTRATION
# =====================================================================
def get_longest_common_prefix(packages):
  """Determines the longest common package prefix for a list of Java packages.

  Determines the root base package namespace (e.g., 'com.medimed') of the
  monolith by calculating the longest common prefix of all scanned Java
  packages.

  Args:
      packages (list[str]): List of packages.

  Returns:
      str: The common base package prefix.
  """
  if not packages:
    return ""
  split_packages = [p.split(".") for p in packages if p]
  if not split_packages:
    return ""
  min_len = min(len(p) for p in split_packages)
  common_parts = []
  for i in range(min_len):
    part = split_packages[0][i]
    if all(p[i] == part for p in split_packages):
      common_parts.append(part)
    else:
      break
  return ".".join(common_parts)


def analyze_imports(target_dir, base_package=None):
  """Scans Java files to build a complete, resolved dependency graph.

  Builds a complete, resolved dependency graph of internal classes by scanning
  package scopes, wildcard imports, static nested classes, implicit imports, and
  FQCN references in code bodies.
  Filters the output to include only packages under the root base_package.

  Args:
      target_dir (str): Monolith repository directory.
      base_package (str, optional): Package prefix. Auto-detected if omitted.

  Returns:
      dict: Summary containing detected base package, class-to-class dependency
      graph, and FQCN class-to-file path maps.
  """
  java_files = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.endswith(".java") or f.endswith(".ejb"):
        java_files.append(os.path.join(root, f))

  fqcn_to_file = {}
  package_to_class_names = {}
  class_data = {}
  all_packages = set()

  # Pass 1: Gather all FQCNs and package structures
  for path in java_files:
    pkg, imps = extract_package_and_imports(path)
    if not pkg:
      continue

    class_name = get_class_name_from_path(path)
    fqcn = f"{pkg}.{class_name}"
    fqcn_to_file[fqcn] = path
    all_packages.add(pkg)

    if pkg not in package_to_class_names:
      package_to_class_names[pkg] = []
    package_to_class_names[pkg].append(class_name)

    try:
      content = lexical_normalizer.clean_java_code(path)
    except OSError:
      content = ""

    class_data[fqcn] = {
        "package": pkg,
        "class_name": class_name,
        "imports": imps,
        "content": content,
    }

  if not base_package:
    base_package = get_longest_common_prefix(list(all_packages))

  # Pass 2: Resolve references
  class_graph = {}
  for fqcn in class_data.keys():
    class_graph[fqcn] = set()

  for fqcn, data in class_data.items():
    pkg = data["package"]
    class_name = data["class_name"]
    content = data["content"]
    imports = data["imports"]

    def is_referenced(target_class_name):
      pattern = re.compile(r"\b" + re.escape(target_class_name) + r"\b")
      if bool(pattern.search(content)):
        return True
      # Also check if the code references EJBGen interfaces of this class
      if target_class_name.endswith("EJB"):
        base = target_class_name[:-3]
        for suffix in ["", "Home", "Local", "LocalHome"]:
          if bool(re.search(r"\b" + re.escape(base + suffix) + r"\b", content)):
            return True
      return False

    # A. Resolve imports
    for imp in imports:
      if imp.endswith(".*"):
        # Wildcard imports
        imp_package = imp[:-2]
        if imp_package in package_to_class_names:
          for target_c in package_to_class_names[imp_package]:
            target_fqcn = f"{imp_package}.{target_c}"
            if target_fqcn != fqcn and is_referenced(target_c):
              class_graph[fqcn].add(target_fqcn)
      else:
        # Direct FQCN imports
        if imp in fqcn_to_file:
          class_graph[fqcn].add(imp)
        else:
          # In case of static imports or nested classes
          resolved = False
          for potential_fqcn in fqcn_to_file.keys():
            if imp.startswith(potential_fqcn + "."):
              class_graph[fqcn].add(potential_fqcn)
              resolved = True
              break

          # EJBGen interface resolution (Foo, FooHome, FooLocal -> FooEJB)
          if not resolved:
            for suffix in ["", "Home", "Local", "LocalHome"]:
              if imp.endswith(suffix):
                base_imp = imp if suffix == "" else imp[: -len(suffix)]
                ejb_fqcn = base_imp + "EJB"
                if ejb_fqcn in fqcn_to_file:
                  class_graph[fqcn].add(ejb_fqcn)
                  break

    # B. Resolve same-package classes (implicit import)
    if pkg in package_to_class_names:
      for target_c in package_to_class_names[pkg]:
        if target_c != class_name:
          target_fqcn = f"{pkg}.{target_c}"
          if is_referenced(target_c):
            class_graph[fqcn].add(target_fqcn)

    # C. Resolve fully qualified name references in code body
    for target_fqcn in fqcn_to_file.keys():
      if target_fqcn != fqcn and target_fqcn in content:
        class_graph[fqcn].add(target_fqcn)

  # Filter by base package
  filtered_graph = {}
  filtered_class_to_file = {}
  for fqcn, deps in class_graph.items():
    if base_package and not fqcn.startswith(base_package):
      continue
    filtered_class_to_file[fqcn] = fqcn_to_file[fqcn]
    filtered_deps = set()
    for dep in deps:
      if base_package and not dep.startswith(base_package):
        continue
      filtered_deps.add(dep)
    filtered_graph[fqcn] = sorted(list(filtered_deps))

  return {
      "detected_base_package": base_package,
      "class_dependencies": filtered_graph,
      "class_to_file": filtered_class_to_file,
  }
