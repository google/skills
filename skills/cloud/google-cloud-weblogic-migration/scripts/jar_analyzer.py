"""Third-party dependency scanner for extracting metadata and versions from local checked-in JAR files.

This module inspects static `.jar` binary files stored inside the monolith
folder.
It extracts:
- Attributable manifest properties (`META-INF/MANIFEST.MF`) resolving wrapped
line breaks.
- Specification titles, vendor details, bundle names, and version fields.

It runs categorization checks to tag jars as WebLogic-specific helpers or
standard legacy Java EE modules, facilitating their replacement with modern
Maven/Gradle dependencies.
"""

import os
import zipfile

# =====================================================================
# JAR ARCHIVE MANIFEST PARSERS
# =====================================================================


def parse_manifest(manifest_content):
  """Parses manifest content lines into key-value property pairs, accounting for line wraps.

  Args:
      manifest_content (str): The raw manifest.mf content text.

  Returns:
      dict: A dictionary of manifest attributes and their values.
  """
  properties = {}
  current_key = None
  current_val = ""
  for line in manifest_content.splitlines():
    if not line:
      continue
    if line.startswith(" "):
      current_val += line[1:]
    else:
      if current_key:
        properties[current_key] = current_val.strip()
      if ":" in line:
        current_key, current_val = line.split(":", 1)
        current_key = current_key.strip()
      else:
        current_key = None
  if current_key:
    properties[current_key] = current_val.strip()
  return properties


def analyze_jar(path):
  """Opens a zip-compressed JAR archive and extracts vendor, version, and package title from its META-INF/MANIFEST.MF.

  Args:
      path (str): File path to JAR archive.

  Returns:
      dict: A dictionary containing implementation details, versions, or errors.
  """
  try:
    with zipfile.ZipFile(path, "r") as jar:
      manifest_path = "META-INF/MANIFEST.MF"
      if manifest_path in jar.namelist():
        with jar.open(manifest_path) as mf:
          content = mf.read().decode("utf-8", errors="ignore")
          props = parse_manifest(content)
          return {
              "filename": os.path.basename(path),
              "title": (
                  props.get("Implementation-Title")
                  or props.get("Specification-Title")
                  or props.get("Bundle-Name")
                  or "Unknown"
              ),
              "version": (
                  props.get("Implementation-Version")
                  or props.get("Specification-Version")
                  or props.get("Bundle-Version")
                  or "Unknown"
              ),
              "vendor": (
                  props.get("Implementation-Vendor")
                  or props.get("Specification-Vendor")
                  or props.get("Bundle-Vendor")
                  or "Unknown"
              ),
              "symbolic_name": props.get("Bundle-SymbolicName") or "Unknown",
          }
      else:
        return {
            "filename": os.path.basename(path),
            "warning": "No MANIFEST.MF found",
        }
  except Exception as e:
    return {
        "filename": os.path.basename(path),
        "error": f"Failed to read JAR: {str(e)}",
    }


# =====================================================================
# LIBRARY CLASSIFICATION AND DIRECTORY SCANNING
# =====================================================================
def categorize_jar(metadata):
  """Categorizes JAR libraries into WebLogic-specific, legacy Java EE standard, or others.

  Args:
      metadata (dict): The parsed Implementation/Bundle attributes dictionary.

  Returns:
      str: Category string ('weblogic_specific', 'java_ee_legacy', 'others', or
      'error').
  """
  if "error" in metadata:
    return "error"
  title = (metadata.get("title") or "").lower()
  vendor = (metadata.get("vendor") or "").lower()
  symbolic_name = (metadata.get("symbolic_name") or "").lower()
  filename = metadata["filename"].lower()

  wls_indicators = ["weblogic", "oracle", "wlfullclient", "wlthint3client"]
  legacy_indicators = [
      "javax.",
      "jakarta.servlet",
      "ejb",
      "jms",
      "transaction",
      "jboss",
      "glassfish",
  ]

  is_wls = any(
      ind in title or ind in vendor or ind in symbolic_name or ind in filename
      for ind in wls_indicators
  )
  is_legacy = any(
      ind in title or ind in vendor or ind in symbolic_name or ind in filename
      for ind in legacy_indicators
  )

  if is_wls:
    return "weblogic_specific"
  elif is_legacy:
    return "java_ee_legacy"
  else:
    return "others"


def analyze_local_jars(target_dir):
  """Recursively scans a target directory for check-in libraries (*.jar) and categorizes them.

  Args:
      target_dir (str): Target directory to scan.

  Returns:
      dict: Summary categorizing checked-in libraries.
  """
  report = {
      "weblogic_specific": [],
      "java_ee_legacy": [],
      "others": [],
      "errors": [],
  }

  jar_files = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.endswith(".jar"):
        jar_files.append(os.path.join(root, f))

  for jar_path in jar_files:
    meta = analyze_jar(jar_path)
    meta["relative_path"] = os.path.relpath(jar_path, target_dir)
    category = categorize_jar(meta)
    if category == "weblogic_specific":
      report["weblogic_specific"].append(meta)
    elif category == "java_ee_legacy":
      report["java_ee_legacy"].append(meta)
    elif category == "error":
      report["errors"].append(meta)
    else:
      report["others"].append(meta)

  return report
