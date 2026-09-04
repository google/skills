"""Database usage mapper for extracting table references from JPA/ORM descriptors and legacy EJB/JDBC code.

This module parses persistence and ORM mappings to map classes to database
tables:
- Parses WebLogic CMP descriptors (`weblogic-cmp-rdbms-jar.xml`) to extract
EJB-to-table bindings.
- Inspects Java source files for JPA annotations (`@Table`, `@SecondaryTable`)
and parses SQL statement regexes.

This class-to-table lookup is used by the clustering engine to calculate
database access profiles and ensure cohesive database boundaries are mapped to
individual microservices.
"""

import os
import re
import xml.etree.ElementTree as ET
import lexical_normalizer

# =====================================================================
# GENERAL XML UTILITIES
# =====================================================================


def strip_ns(tag):
  """Strips XML namespaces from elements.

  Args:
      tag (str): The raw tag name.

  Returns:
      str: The tag name without namespace.
  """
  if "}" in tag:
    return tag.split("}", 1)[1]
  return tag


def parse_xml_to_dict(element):
  """Recursively converts an XML tree element to a nested dictionary representation.

  Args:
      element (xml.etree.ElementTree.Element): The XML element.

  Returns:
      dict | str: Parsed dictionary or text value.
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
# ORM DESCRIPTOR AND JAVA SOURCE PARSERS
# =====================================================================
def parse_weblogic_cmp_maps(path):
  """Parses weblogic-cmp-rdbms-jar.xml files to map entity beans to database tables.

  Args:
      path (str): File path to weblogic-cmp-rdbms-jar.xml.

  Returns:
      dict: Mapping of EJB names to their queryable database tables.
  """
  mappings = {}
  try:
    tree = ET.parse(path)
    root = tree.getroot()
    data = parse_xml_to_dict(root)

    def get_as_list(d, key):
      val = d.get(key, [])
      return val if isinstance(val, list) else [val]

    if isinstance(data, dict):
      beans = get_as_list(data, "weblogic-rdbms-bean")
      for bean in beans:
        if isinstance(bean, dict):
          ejb_name = bean.get("ejb-name")
          table_map = bean.get("table-map")
          tables = []
          if isinstance(table_map, dict):
            tables.append(table_map.get("table-name"))
          elif isinstance(table_map, list):
            for tm in table_map:
              if isinstance(tm, dict):
                tables.append(tm.get("table-name"))
          if ejb_name and tables:
            mappings[ejb_name] = [t for t in tables if t]
  except (ET.ParseError, OSError):
    pass
  return mappings


def extract_db_info_from_java(file_path):
  """Extracts database table references from a Java source file.

  Statically analyzes a Java source file using lexical normalization to identify
  package, class name, entity status, and database table references in JPA
  annotations and SQL queries.
  Safely handles inline comments, multi-line attributes, string concatenations,
  and comma-separated FROM clauses.

  Args:
      file_path (str): File path to the Java source file.

  Returns:
      tuple[str, str, bool, list[str]]: package, class name, is_entity boolean,
      and lists of referenced tables.
  """
  tables = set()
  is_entity = False
  class_name = (
      os.path.basename(file_path).replace(".java", "").replace(".ejb", "")
  )
  package = ""

  try:
    tokens = lexical_normalizer.tokenize_java_file(file_path)
    package = lexical_normalizer.get_package_name(file_path) or ""
    code_clean = tokens["code_text_with_strings"]
    code_no_str = tokens["code_text_no_strings"]

    # 1. Check entity status and JPA table annotations on comment-stripped,
    # whitespace-collapsed code
    if re.search(
        r"@(?:Entity|Table|SecondaryTable)\b|\bGenericEntityBean\b", code_no_str
    ):
      is_entity = True

    for match in re.finditer(
        r'@(?:SecondaryTable|Table|JoinTable)\s*\(\s*(?:[^)]*?\bname\s*=\s*)?"([a-zA-Z0-9_]+)"',
        code_clean,
    ):
      tables.add(match.group(1).upper())
      is_entity = True

    if is_entity and not tables and re.search(r"@Entity\b", code_no_str):
      tables.add(class_name.upper())

    for javadoc in tokens.get("javadocs", []):
      for match in re.finditer(r"table-name\s*=\s*([a-zA-Z0-9_]+)", javadoc):
        tables.add(match.group(1).upper())
        is_entity = True

    for match in re.finditer(r"table-name\s*=\s*([a-zA-Z0-9_]+)", code_clean):
      tables.add(match.group(1).upper())
      is_entity = True

    # 2. Extract tables from SQL queries in string literals (concatenations
    # already merged by normalizer)
    sql_keywords = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "WHERE",
        "AND",
        "OR",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "CROSS",
        "FULL",
        "NATURAL",
        "ON",
        "USING",
        "GROUP",
        "ORDER",
        "BY",
        "SET",
        "AS",
        "UNION",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "VALS",
        "VALUES",
        "FROM",
        "INTO",
        "CREATE",
        "DROP",
        "ALTER",
        "TABLE",
        "INDEX",
        "VIEW",
    }

    for sql_str in tokens["string_literals"]:
      if len(sql_str) < 6:
        continue
      # Match FROM, JOIN, INTO, UPDATE followed by table names/aliases up to
      # next SQL keyword or subquery '('
      # Note: 'AS' is intentionally excluded from lookahead so comma-separated
      # lists with aliases (e.g. FROM tableA AS a, tableB AS b) are captured in
      # full.
      for clause_match in re.finditer(
          r"(?i)\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z0-9_\.\s,]*[a-zA-Z0-9_])\s*(?=\b(?:WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|FULL|NATURAL|ON|USING|GROUP|ORDER|BY|SET|SELECT|UNION|HAVING|LIMIT|OFFSET|VALS|VALUES)\b|\(|;|$)",
          sql_str,
      ):
        clause_text = clause_match.group(1)
        # Split comma-separated table lists (e.g. "PATIENT p, ADDRESS a"
        # or "PATIENT AS p, ADDRESS AS a")
        for table_expr in clause_text.split(","):
          parts = table_expr.strip().split()
          if parts:
            table_name = parts[0].upper()
            if (
                table_name not in sql_keywords
                and not table_name.startswith("JAVA:")
                and len(table_name) > 1
            ):
              tables.add(table_name)
  except OSError:
    pass

  sql_keywords = {
      "SELECT",
      "INSERT",
      "UPDATE",
      "DELETE",
      "WHERE",
      "AND",
      "OR",
      "JOIN",
      "LEFT",
      "RIGHT",
      "INNER",
      "OUTER",
      "CROSS",
      "FULL",
      "NATURAL",
      "ON",
      "USING",
      "GROUP",
      "ORDER",
      "BY",
      "SET",
      "AS",
      "UNION",
      "HAVING",
      "LIMIT",
      "OFFSET",
      "VALS",
      "VALUES",
      "FROM",
      "INTO",
      "CREATE",
      "DROP",
      "ALTER",
      "TABLE",
      "INDEX",
      "VIEW",
  }
  cleaned_tables = [
      t for t in tables if t not in sql_keywords and not t.startswith("JAVA:")
  ]
  return package, class_name, is_entity, cleaned_tables


# =====================================================================
# RUNTIME FILE DISCOVERY AND DATABASE ORCHESTRATION
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


def map_db_usage(target_dir):
  """Extracts database usage mappings from a repository.

  Scans the repository to map class-to-table and table-to-class interaction
  mappings, extracting relations from both XML CMP mappings and Java code.

  Args:
      target_dir (str): The repository root path to scan.

  Returns:
      dict: A nested mapping report representing classes and tables.
  """
  class_to_tables = {}
  table_to_classes = {}

  ejb_to_tables = {}
  cmp_maps = find_files(target_dir, ["weblogic-cmp-rdbms-jar.xml"])
  for cmap in cmp_maps:
    maps = parse_weblogic_cmp_maps(cmap)
    ejb_to_tables.update(maps)

  java_files = []
  for root, _, files in os.walk(target_dir):
    for f in files:
      if f.endswith(".java") or f.endswith(".ejb"):
        java_files.append(os.path.join(root, f))

  for path in java_files:
    package, class_name, is_entity, tables = extract_db_info_from_java(path)
    if class_name in ejb_to_tables:
      tables = list(set(tables + ejb_to_tables[class_name]))
    for ejb_name, cmp_tables in ejb_to_tables.items():
      if class_name.startswith(ejb_name):
        tables = list(set(tables + cmp_tables))
    if tables:
      fq_class_name = f"{package}.{class_name}" if package else class_name
      class_to_tables[fq_class_name] = sorted(tables)
      for t in tables:
        if t not in table_to_classes:
          table_to_classes[t] = []
        table_to_classes[t].append(fq_class_name)

  for t in table_to_classes:
    table_to_classes[t] = sorted(table_to_classes[t])

  return {
      "cmp_ejb_mappings": ejb_to_tables,
      "class_to_tables": class_to_tables,
      "table_to_classes": table_to_classes,
  }
