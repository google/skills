# Copyright 2026 Google. This software is provided as-is, without warranty or
# representation for any use or purpose. Your use of it is subject to your
# agreement with Google.

import ast
import csv
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

import yaml


def split_by_comma_balanced(s):
    parts = []
    curr_part = []
    paren_count = 0
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(s):
        c = s[i]
        if c == "'" and (i == 0 or s[i - 1] != "\\"):
            in_single_quote = not in_single_quote
        elif c == '"' and (i == 0 or s[i - 1] != "\\"):
            in_double_quote = not in_double_quote

        if not in_single_quote and not in_double_quote:
            if c == "(":
                paren_count += 1
            elif c == ")":
                paren_count -= 1
            elif c == "," and paren_count == 0:
                parts.append("".join(curr_part))
                curr_part = []
                i += 1
                continue

        curr_part.append(c)
        i += 1

    parts.append("".join(curr_part))
    return parts


def translate_dateadd_expressions(sql_content):
    idx = 0
    while True:
        match = re.search(r"\bdateadd\s*\(", sql_content[idx:], re.IGNORECASE)
        if not match:
            break

        start_pos = idx + match.start()
        args_start = idx + match.end()

        paren_count = 1
        curr_pos = args_start
        while paren_count > 0 and curr_pos < len(sql_content):
            char = sql_content[curr_pos]
            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
            curr_pos += 1

        if paren_count != 0:
            idx = args_start
            continue

        args_str = sql_content[args_start : curr_pos - 1]
        args = split_by_comma_balanced(args_str)
        if len(args) == 3:
            unit = args[0].strip()
            val = args[1].strip()
            base = args[2].strip()

            unit_upper = unit.upper().strip("'\"")
            unit_map = {
                "D": "DAY",
                "DAYS": "DAY",
                "M": "MONTH",
                "MONTHS": "MONTH",
                "Y": "YEAR",
                "YEARS": "YEAR",
                "H": "HOUR",
                "HOURS": "HOUR",
                "MS": "MILLISECOND",
                "S": "SECOND",
                "SECONDS": "SECOND",
            }
            unit_bq = unit_map.get(unit_upper, unit_upper)

            bq_dateadd = f"DATE_ADD({base}, INTERVAL {val} {unit_bq})"
            sql_content = sql_content[:start_pos] + bq_dateadd + sql_content[curr_pos:]
            idx = start_pos + len(bq_dateadd)
        else:
            idx = curr_pos

    return sql_content


def translate_cast_suffixes(sql_content):
    for suffix, target_type in [("::date", "DATE"), ("::timestamp", "TIMESTAMP")]:
        idx = 0
        while True:
            pos = sql_content.lower().find(suffix, idx)
            if pos == -1:
                break

            expr_start = pos
            paren_count = 0
            bracket_count = 0
            brace_count = 0

            while expr_start > 0:
                char = sql_content[expr_start - 1]
                if char == ")":
                    paren_count += 1
                elif char == "(":
                    paren_count -= 1
                    if paren_count < 0:
                        break
                elif char == "}":
                    brace_count += 1
                elif char == "{":
                    brace_count -= 1
                    if brace_count < 0:
                        break
                elif char == "]":
                    bracket_count += 1
                elif char == "[":
                    bracket_count -= 1
                    if bracket_count < 0:
                        break

                if (
                    paren_count == 0
                    and brace_count == 0
                    and bracket_count == 0
                    and char in (" ", "\n", ",", ";", "=", "<", ">", "+", "-", "*", "/")
                    and expr_start < pos
                ):
                    break

                expr_start -= 1

            if expr_start < pos:
                expr = sql_content[expr_start:pos].strip()
                cast_expr = f"CAST({expr} AS {target_type})"
                sql_content = (
                    sql_content[:expr_start]
                    + cast_expr
                    + sql_content[pos + len(suffix) :]
                )
                idx = expr_start + len(cast_expr)
            else:
                idx = pos + len(suffix)

    return sql_content


def translate_interval_expressions(sql_content):
    pattern = re.compile(
        r"\s*([+-])\s*interval\s*\'(\d+)\s*([a-zA-Z]+)\'", re.IGNORECASE
    )
    idx = 0
    while True:
        match = re.search(pattern, sql_content[idx:])
        if not match:
            break

        match_start = idx + match.start()
        match_end = idx + match.end()

        op = match.group(1)
        val = match.group(2)
        unit = match.group(3).upper()

        expr_start = match_start
        paren_count = 0
        bracket_count = 0
        brace_count = 0

        while expr_start > 0:
            char = sql_content[expr_start - 1]
            if char == ")":
                paren_count += 1
            elif char == "(":
                paren_count -= 1
                if paren_count < 0:
                    break
            elif char == "}":
                brace_count += 1
            elif char == "{":
                brace_count -= 1
                if brace_count < 0:
                    break
            elif char == "]":
                bracket_count += 1
            elif char == "[":
                bracket_count -= 1
                if bracket_count < 0:
                    break

            if (
                paren_count == 0
                and brace_count == 0
                and bracket_count == 0
                and char in (" ", "\n", ",", ";", "=", "<", ">", "+", "-", "*", "/")
                and expr_start < match_start
            ):
                break
            expr_start -= 1

        if expr_start < match_start:
            base = sql_content[expr_start:match_start].strip()
            unit_map = {
                "DAYS": "DAY",
                "MONTHS": "MONTH",
                "YEARS": "YEAR",
                "HOURS": "HOUR",
                "MINUTES": "MINUTE",
                "SECONDS": "SECOND",
            }
            unit_bq = unit_map.get(unit, unit)

            if op == "+":
                replacement = f"DATE_ADD({base}, INTERVAL {val} {unit_bq})"
            else:
                replacement = f"DATE_SUB({base}, INTERVAL {val} {unit_bq})"

            sql_content = (
                sql_content[:expr_start] + replacement + sql_content[match_end:]
            )
            idx = expr_start + len(replacement)
        else:
            idx = match_end

    return sql_content


def sanitize_jinja_and_sql_edge_cases(sql_content):
    # 1. Map Snowflake schema/database qualified tables to dbt source macros
    sql_content = re.sub(
        r"\b[a-zA-Z0-9_]+\.pre_raw\.(pre_raw__([a-zA-Z0-9_]+?)__icetab__[a-zA-Z0-9_]+)",
        r"{{ source('\2', '\1') }}",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 2. Replace Snowflake date/time cast suffix ::date and ::timestamp
    sql_content = translate_cast_suffixes(sql_content)

    # 3. Translate dateadd
    sql_content = translate_dateadd_expressions(sql_content)

    # 4. Translate interval additions/subtractions
    sql_content = translate_interval_expressions(sql_content)

    # 5. Strip BQ Translation Service unknown type comments
    sql_content = re.sub(
        r"/\*\s*expression of unknown or erroneous type\s*\*/",
        "",
        sql_content,
        flags=re.IGNORECASE,
    )
    # Clean up double/multiple spaces
    sql_content = re.sub(r"[ \t]+", " ", sql_content)
    sql_content = re.sub(r"\(\s+", "(", sql_content)
    sql_content = re.sub(r"\s+\)", ")", sql_content)

    return sql_content


def sanitize_json_extractions(sql_content):
    def replace_match(m):
        cleaned_path = re.sub(r"^\$?\.?", "", m.group(3))
        return f"json_query({m.group(1)}, '{m.group(2)}.{cleaned_path}')"

    pattern = re.compile(
        r"json_query\(\s*json_query\(\s*([^,]+)\s*,\s*'([^\']+)'\)\s*,\s*'([^\']+)'\)",
        re.IGNORECASE,
    )
    while True:
        new_content, count = pattern.subn(replace_match, sql_content)
        if count == 0:
            break
        sql_content = new_content

    # 2. Replace string extraction wrappers: substr(string(json_query(col, 'path')), 1, 16777216) -> CAST(JSON_EXTRACT_SCALAR(col, 'path') AS STRING)
    sql_content = re.sub(
        r"substr\(\s*string\(\s*json_query\(\s*([^,]+),\s*'([^\']+)'\s*\)\s*\)\s*,\s*1\s*,\s*\d+\s*\)",
        r"CAST(JSON_EXTRACT_SCALAR(\1, '\2') AS STRING)",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 3. Replace numeric wrappers: CAST(lax_float64(json_query(col, 'path')) as BIGNUMERIC) -> CAST(JSON_EXTRACT_SCALAR(col, 'path') AS NUMERIC)
    sql_content = re.sub(
        r"CAST\(\s*lax_float64\(\s*json_query\(\s*([^,]+),\s*'([^\']+)'\s*\)\s*\)\s*as\s+BIGNUMERIC\)",
        r"CAST(JSON_EXTRACT_SCALAR(\1, '\2') AS NUMERIC)",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 4. Replace float wrappers: lax_float64(json_query(col, 'path')) -> CAST(JSON_EXTRACT_SCALAR(col, 'path') AS FLOAT64)
    sql_content = re.sub(
        r"lax_float64\(\s*json_query\(\s*([^,]+),\s*'([^\']+)'\s*\)\s*\)",
        r"CAST(JSON_EXTRACT_SCALAR(\1, '\2') AS FLOAT64)",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 5. Replace boolean wrappers: lax_bool(json_query(col, 'path')) -> CAST(JSON_EXTRACT_SCALAR(col, 'path') AS BOOL)
    sql_content = re.sub(
        r"lax_bool\(\s*json_query\(\s*([^,]+),\s*'([^\']+)'\s*\)\s*\)",
        r"CAST(JSON_EXTRACT_SCALAR(\1, '\2') AS BOOL)",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 6. Replace plain json_query: json_query(col, 'path') -> JSON_EXTRACT_SCALAR(col, 'path')
    sql_content = re.sub(
        r"json_query\(\s*([^,]+),\s*'([^\']+)'\s*\)",
        r"JSON_EXTRACT_SCALAR(\1, '\2')",
        sql_content,
        flags=re.IGNORECASE,
    )

    return sql_content


def audit_macros(sql_content):
    # Find all {{ ... }} occurrences
    macro_pattern = re.compile(r"({{\s*(.*?)\s*}})", re.DOTALL)
    warnings = []

    # Standard whitelisted macros
    whitelist = {
        "ref",
        "source",
        "config",
        "var",
        "env_var",
        "this",
        "target",
        "log",
        "return",
        "doc",
        "selected_resources",
        "modules",
    }

    snowflake_patterns = [
        (r"::\s*date\b", "::date cast"),
        (r"::\s*timestamp\b", "::timestamp cast"),
        (r"\bdateadd\s*\(", "dateadd function"),
        (r"\bdatesub\s*\(", "datesub function"),
        (r"\bto_date\s*\(", "to_date function"),
        (r"\bto_timestamp\s*\(", "to_timestamp function"),
    ]

    for match, expr_content in macro_pattern.findall(sql_content):
        name_match = re.match(r"^([a-zA-Z0-9_\.]+)", expr_content.strip())
        if name_match:
            macro_name = name_match.group(1)
            base_name = macro_name.split(".")[0]
            if base_name not in whitelist and not macro_name.startswith("dbt_utils."):
                warnings.append(
                    f"Potential database-specific or custom macro detected: '{macro_name}' in '{match.strip()}'"
                )

        for pattern, desc in snowflake_patterns:
            if re.search(pattern, expr_content, re.IGNORECASE):
                warnings.append(
                    f"Snowflake-specific syntax ({desc}) found inside Jinja expression: '{match.strip()}'"
                )

    return warnings, sql_content


SQL_KEYWORDS = [
    "SELECT",
    "FROM",
    "WHERE",
    "JOIN",
    "LEFT",
    "RIGHT",
    "INNER",
    "OUTER",
    "ON",
    "GROUP BY",
    "ORDER BY",
    "HAVING",
    "LIMIT",
    "UNION ALL",
    "UNION",
    "AS",
    "WITH",
    "DISTINCT",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS",
    "NULL",
    "COALESCE",
    "CAST",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "USING",
    "QUALIFY",
    "WINDOW",
]


def standardize_casing_and_joins(sql_content):
    # 1. Masking
    comments = []
    strings = []
    jinjas = []

    def mask_comment(match):
        idx = len(comments)
        comments.append(match.group(0))
        return f"@@TEMP_COMMENT_{idx}@@"

    def mask_string(match):
        idx = len(strings)
        strings.append(match.group(0))
        return f"@@TEMP_STRING_{idx}@@"

    def mask_jinja(match):
        idx = len(jinjas)
        jinjas.append(match.group(0))
        return f"@@TEMP_JINJA_{idx}@@"

    # Mask comments
    sql_temp = re.sub(r"--.*$", mask_comment, sql_content, flags=re.MULTILINE)
    sql_temp = re.sub(r"/\*.*?\*/", mask_comment, sql_temp, flags=re.DOTALL)

    # Mask Jinja blocks
    sql_temp = re.sub(r"\{\{.*?\}\}", mask_jinja, sql_temp, flags=re.DOTALL)
    sql_temp = re.sub(r"\{%.*?%\}", mask_jinja, sql_temp, flags=re.DOTALL)

    # Mask strings
    sql_temp = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", mask_string, sql_temp)
    sql_temp = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', mask_string, sql_temp)

    # --- SQL Cleanup (Masked version) ---

    # A. Simplify explicit cast to bytes for cryptographic functions:
    # sha256(CAST(expr AS BYTES)) -> sha256(expr)
    sql_temp = re.sub(
        r"\b(sha1|sha256|sha512|md5)\s*\(\s*cast\(\s*(.*?)\s+as\s+bytes\s*\)\s*\)",
        r"\1(\2)",
        sql_temp,
        flags=re.IGNORECASE,
    )

    # B. Simplify nested bignumeric cast conversions:
    # cast(cast(expr as bignumeric) as int64) -> cast(expr as int64)
    sql_temp = re.sub(
        r"\bcast\(\s*cast\(\s*(.*?)\s+as\s+bignumeric\s*\)\s*as\s+int64\s*\)",
        r"cast(\1 as int64)",
        sql_temp,
        flags=re.IGNORECASE,
    )
    # cast(cast(expr as bignumeric) as string) -> cast(expr as string)
    sql_temp = re.sub(
        r"\bcast\(\s*cast\(\s*(.*?)\s+as\s+bignumeric\s*\)\s*as\s+string\s*\)",
        r"cast(\1 as string)",
        sql_temp,
        flags=re.IGNORECASE,
    )

    # C. CTE Lowercasing
    cte_names = re.findall(r"\b([a-zA-Z0-9_]+)\s+as\s*\(", sql_temp, re.IGNORECASE)
    for cte in cte_names:
        if cte.upper() not in SQL_KEYWORDS:
            sql_temp = re.sub(rf"\b{cte}\b", cte.lower(), sql_temp)

    # D. Keyword and Function Casing to Lowercase
    # 1. Lowercase functions: any identifier followed by (
    def lowercase_function(match):
        func_name = match.group(1)
        return f"{func_name.lower()}("

    sql_temp = re.sub(r"\b([a-zA-Z0-9_]+)\s*\(", lowercase_function, sql_temp)

    # 2. Lowercase standard keywords
    for kw in SQL_KEYWORDS:
        sql_temp = re.sub(rf"\b{kw}\b", kw.lower(), sql_temp, flags=re.IGNORECASE)

    # E. Join Standardization: left/right outer join -> left/right join
    sql_temp = re.sub(
        r"\bleft\s+outer\s+join\b", "left join", sql_temp, flags=re.IGNORECASE
    )
    sql_temp = re.sub(
        r"\bright\s+outer\s+join\b", "right join", sql_temp, flags=re.IGNORECASE
    )

    # F. Date Functions: current_date() -> current_date
    sql_temp = re.sub(
        r"\bcurrent_date\s*\(\s*\)", "current_date", sql_temp, flags=re.IGNORECASE
    )
    sql_temp = re.sub(
        r"\bcurrent_timestamp\s*\(\s*\)",
        "current_timestamp",
        sql_temp,
        flags=re.IGNORECASE,
    )

    # --- Restoring ---
    def restore_string(match):
        idx = int(match.group(1))
        return strings[idx]

    def restore_jinja(match):
        idx = int(match.group(1))
        return jinjas[idx]

    def restore_comment(match):
        idx = int(match.group(1))
        return comments[idx]

    sql_restored = re.sub(r"@@TEMP_STRING_(\d+?)@@", restore_string, sql_temp)
    while True:
        next_sql = re.sub(r"@@TEMP_JINJA_(\d+?)@@", restore_jinja, sql_restored)
        if next_sql == sql_restored:
            break
        sql_restored = next_sql
    sql_restored = re.sub(r"@@TEMP_COMMENT_(\d+?)@@", restore_comment, sql_restored)

    # --- Post-restore Cleanup ---
    # Simplify cast('1' as int64) -> 1
    sql_restored = re.sub(
        r"\bcast\(\s*['\"](\d+)['\"]\s*as\s+int64\s*\)",
        r"\1",
        sql_restored,
        flags=re.IGNORECASE,
    )

    return sql_restored


def resolve_dotted_name(dotted_name, known_models, known_sources):
    parts = dotted_name.split(".")
    if len(parts) == 1:
        name = parts[0]
        if name.lower() in known_models:
            return f"{{{{ ref('{name.lower()}') }}}}"
        return dotted_name

    table_name = parts[-1].lower()
    schema_name = parts[-2].lower() if len(parts) >= 2 else None

    if table_name in known_models:
        return f"{{{{ ref('{table_name}') }}}}"

    if schema_name:
        for src_name, src_tables in known_sources.items():
            if schema_name == src_name.lower() and table_name in [
                t.lower() for t in src_tables
            ]:
                return f"{{{{ source('{src_name}', '{table_name}') }}}}"

    if len(parts) >= 2:
        return f"{{{{ source('{schema_name}', '{table_name}') }}}}"

    return dotted_name


def resolve_namespaces(sql_content, known_models=None, known_sources=None):
    if known_models is None:
        known_models = set()
    if known_sources is None:
        known_sources = {}

    # 1. Mask comments to prevent matching keywords inside comments
    comments = []

    def mask_comment(match):
        idx = len(comments)
        comments.append(match.group(0))
        return f"@@TEMP_COMMENT_{idx}@@"

    # Mask -- comments (excluding newlines)
    sql_temp = re.sub(r"--.*$", mask_comment, sql_content, flags=re.MULTILINE)
    # Mask /* */ comments
    sql_temp = re.sub(r"/\*.*?\*/", mask_comment, sql_temp, flags=re.DOTALL)

    end_keywords = r"\b(join|where|group|order|limit|union|select|having|using|on|qualify|window|as)\b|\)"

    def replace_tables(match):
        keyword = match.group(1)
        table_list_str = match.group(2)

        parts = table_list_str.split(",")
        new_parts = []
        for part in parts:
            part_clean = part.strip()
            table_match = re.match(
                r"^([a-zA-Z0-9_\.]+)(?:\s+(?:as\s+)?([a-zA-Z0-9_]+))?$",
                part_clean,
                re.IGNORECASE,
            )
            if table_match:
                dotted_name = table_match.group(1)
                alias = table_match.group(2)

                resolved = resolve_dotted_name(dotted_name, known_models, known_sources)
                if alias:
                    new_parts.append(f"{resolved} {alias}")
                else:
                    new_parts.append(resolved)
            else:
                new_parts.append(part)
        return f"{keyword} " + ", ".join(new_parts)

    pattern = re.compile(
        r"\b(from|join)\s+((?:[a-zA-Z0-9_\.\s,]+?)(?=\s*(?:"
        + end_keywords
        + r"|;)|$))",
        re.IGNORECASE | re.DOTALL,
    )

    sql_temp = pattern.sub(replace_tables, sql_temp)

    # 2. Restore comments
    def restore_comment(match):
        idx = int(match.group(1))
        return comments[idx]

    sql_resolved = re.sub(r"@@TEMP_COMMENT_(\d+?)@@", restore_comment, sql_temp)
    return sql_resolved


def is_invalid_bq_hook(hook_sql):
    hook_sql_lower = hook_sql.lower()
    if "alter iceberg table" in hook_sql_lower:
        return True
    if "unset secure" in hook_sql_lower:
        return True
    if "search optimization" in hook_sql_lower:
        return True
    return not hook_sql.strip()


def sanitize_hook_node(node):
    if isinstance(node, ast.List):
        new_elts = []
        for elt in node.elts:
            sanitized_elt = sanitize_hook_node(elt)
            if sanitized_elt is not None:
                new_elts.append(sanitized_elt)
        if not new_elts:
            return None
        node.elts = new_elts
        return node
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        val = node.value
        if is_invalid_bq_hook(val):
            return None
        val = sanitize_jinja_and_sql_edge_cases(val)
        val = sanitize_json_extractions(val)
        node.value = val
        return node
    else:
        return node


STANDARD_DBT_CONFIGS = {
    "materialized",
    "incremental_strategy",
    "tags",
    "pre_hook",
    "post_hook",
    "alias",
    "schema",
    "database",
    "enabled",
    "unique_key",
    "sql_header",
    "on_schema_change",
    "grants",
    "docs",
    "persist_docs",
}


def transform_config_block(config_content, file_path="unknown"):
    # Strip Jinja outer braces {{ ... }}
    content = config_content.strip()
    if content.startswith("{{") and content.endswith("}}"):
        content = content[2:-2].strip()

    # We expect config(...)
    match_config = re.match(r"config\s*\(", content, re.IGNORECASE)
    if not match_config:
        return config_content

    # The arguments are everything inside the outer parentheses of config(...)
    if content.endswith(")"):
        args_str = content[match_config.end() : -1].strip()
    else:
        # Fallback to regex search
        match = re.search(r"config\((.*)\)", content, re.DOTALL | re.IGNORECASE)
        if not match:
            return config_content
        args_str = match.group(1).strip()

    if not args_str:
        return config_content

    try:
        tree = ast.parse(f"config({args_str})")
        stmt = tree.body[0]
        if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
            return config_content
        call_node = stmt.value
        keywords = call_node.keywords

        standard_keywords = []
        custom_key_values = []
        meta_node = None

        for kw in keywords:
            name = kw.arg
            value_node = kw.value

            if name in ("copy_grants", "transient", "secure"):
                continue

            if name in ("pre_hook", "post_hook"):
                sanitized_value_node = sanitize_hook_node(value_node)
                if sanitized_value_node is not None:
                    kw.value = sanitized_value_node
                    standard_keywords.append(kw)
                continue

            if name == "meta":
                if isinstance(value_node, ast.Dict):
                    meta_node = value_node
                continue

            if name in STANDARD_DBT_CONFIGS:
                standard_keywords.append(kw)
            else:
                custom_key_values.append((name, value_node))

        # Handle meta node
        if custom_key_values:
            if meta_node is None:
                meta_node = ast.Dict(keys=[], values=[])

            for name, val_node in custom_key_values:
                key_node = ast.Constant(value=name)
                exists = False
                for idx, k in enumerate(meta_node.keys):
                    if isinstance(k, ast.Constant) and k.value == name:
                        meta_node.values[idx] = val_node
                        exists = True
                        break
                if not exists:
                    meta_node.keys.append(key_node)
                    meta_node.values.append(val_node)

        # Reconstruct keywords
        final_keywords = list(standard_keywords)

        if meta_node is not None and meta_node.keys:
            meta_kw = ast.keyword(arg="meta", value=meta_node)
            final_keywords.append(meta_kw)

        # Format output manually for multi-line formatting
        config_args = []
        for kw in final_keywords:
            if kw.arg == "meta":
                dict_pairs = []
                for k, v in zip(kw.value.keys, kw.value.values):
                    k_str = ast.unparse(k)
                    v_str = ast.unparse(v)
                    v_str = re.sub(r"\bTrue\b", "true", v_str)
                    v_str = re.sub(r"\bFalse\b", "false", v_str)
                    v_str = re.sub(r"\bNone\b", "none", v_str)
                    dict_pairs.append(f"            {k_str}: {v_str}")
                meta_str = "{\n" + ",\n".join(dict_pairs) + "\n        }"
                config_args.append(f"        meta={meta_str}")
            else:
                val_str = ast.unparse(kw.value)
                val_str = re.sub(r"\bTrue\b", "true", val_str)
                val_str = re.sub(r"\bFalse\b", "false", val_str)
                val_str = re.sub(r"\bNone\b", "none", val_str)
                config_args.append(f"        {kw.arg}={val_str}")

        if len(config_args) > 1:
            return "{{\n    config(\n" + ",\n".join(config_args) + "\n    )\n}}"
        elif len(config_args) == 1:
            arg = config_args[0].strip()
            if "\n" in arg:
                return "{{\n    config(\n        " + arg + "\n    )\n}}"
            return f"{{{{ config({arg}) }}}}"
        else:
            return ""

    except Exception as e:  # noqa: BLE001
        print(
            f"Warning: Failed to parse config block with AST in {file_path}: {e}. Falling back to original."
        )
        return config_content


def discover_dbt_resources(input_dir):
    known_models = set()
    known_sources = {}

    for root, dirs, files in os.walk(input_dir):
        for f in files:
            if f.endswith(".sql"):
                model_name = f[:-4].lower()
                known_models.add(model_name)
            elif f.endswith((".yml", ".yaml")):
                try:
                    with open(os.path.join(root, f), "r", encoding="utf-8") as yml_file:
                        data = yaml.safe_load(yml_file)
                        if (
                            data
                            and isinstance(data, dict)
                            and "sources" in data
                            and isinstance(data["sources"], list)
                        ):
                            for src in data["sources"]:
                                if isinstance(src, dict) and "name" in src:
                                    src_name = src["name"].lower()
                                    if src_name not in known_sources:
                                        known_sources[src_name] = set()
                                    if "tables" in src and isinstance(
                                        src["tables"], list
                                    ):
                                        for tbl in src["tables"]:
                                            if isinstance(tbl, dict) and "name" in tbl:
                                                known_sources[src_name].add(
                                                    tbl["name"].lower()
                                                )
                except (yaml.YAMLError, OSError) as e:
                    print(f"Warning: Failed to parse YAML file {f}: {e}")

    return known_models, known_sources


def extract_config_block(content):
    match = re.search(r"{{\s*config\b", content, re.IGNORECASE)
    if not match:
        return None, content

    start_idx = match.start()
    brace_count = 0
    i = start_idx
    n = len(content)

    while i < n - 1:
        if content[i : i + 2] == "{{":
            brace_count += 1
            i += 2
        elif content[i : i + 2] == "}}":
            brace_count -= 1
            i += 2
            if brace_count == 0:
                end_idx = i
                config_block = content[start_idx:end_idx]
                stripped_content = content[:start_idx] + content[end_idx:]
                return config_block, stripped_content
        else:
            i += 1

    return None, content


def zip_directory(dir_path, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dir_path)
                zipf.write(file_path, arcname)


def preprocess_metadata(metadata_path, temp_metadata_dir, known_models, known_sources):
    is_zip = False
    extract_dir = None
    if os.path.isfile(metadata_path) and metadata_path.endswith(".zip"):
        is_zip = True
        extract_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(metadata_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        source_dir = extract_dir
    elif os.path.isdir(metadata_path):
        source_dir = metadata_path
    else:
        print(
            f"Warning: Metadata path {metadata_path} is not a valid directory or zip file."
        )
        return False

    os.makedirs(temp_metadata_dir, exist_ok=True)

    files_to_process = ["columns", "tables"]
    processed_any = False

    for prefix_key in files_to_process:
        found_file = None
        for f in os.listdir(source_dir):
            f_lower = f.lower()
            if f_lower.startswith(prefix_key) and f_lower.endswith(".csv"):
                found_file = f
                break

        if not found_file:
            continue

        src_file = os.path.join(source_dir, found_file)
        dest_file = os.path.join(temp_metadata_dir, f"{prefix_key}.csv")

        with (
            open(src_file, "r", encoding="utf-8") as f_in,
            open(dest_file, "w", encoding="utf-8", newline="") as f_out,
        ):
            reader = csv.reader(f_in)
            writer = csv.writer(f_out)

            header = next(reader, None)
            if not header:
                continue

            writer.writerow(header)

            table_idx = -1
            schema_idx = -1
            catalog_idx = -1

            for idx, col in enumerate(header):
                col_clean = col.lower().replace("_", "")
                if "tablename" in col_clean or "table" == col_clean:
                    table_idx = idx
                elif (
                    "schemaname" in col_clean
                    or "tableschema" in col_clean
                    or "schema" in col_clean
                ):
                    schema_idx = idx
                elif (
                    "catalog" in col_clean
                    or "databasename" in col_clean
                    or "database" in col_clean
                ):
                    catalog_idx = idx

            if table_idx == -1:
                # Fallback to check if any header has "table" in it
                for idx, col in enumerate(header):
                    if "table" in col.lower():
                        table_idx = idx
                        break
                if table_idx == -1:
                    table_idx = 0  # Ultimate fallback to first column

            for row in reader:
                # Avoid crash if row is shorter than table index
                if len(row) <= table_idx:
                    writer.writerow(row)
                    continue
                schema_val = (
                    row[schema_idx].lower()
                    if (schema_idx != -1 and len(row) > schema_idx)
                    else ""
                )
                table_val = row[table_idx].lower()

                is_source = False

                # 1. Match by source
                if schema_idx != -1 and schema_val:
                    for src_name, src_tables in known_sources.items():
                        if schema_val == src_name.lower() and table_val in [
                            t.lower() for t in src_tables
                        ]:
                            row[table_idx] = (
                                f"_DBT_SOURCE_{src_name}_DBTSEP_{table_val}_"
                            )
                            row[schema_idx] = ""
                            if catalog_idx != -1 and len(row) > catalog_idx:
                                row[catalog_idx] = ""
                            is_source = True
                            break
                else:
                    # Fallback: schema is missing or empty. Resolve by table name if unique in known_sources.
                    matching_sources = []
                    for src_name, src_tables in known_sources.items():
                        if table_val in [t.lower() for t in src_tables]:
                            matching_sources.append(src_name)

                    if len(matching_sources) == 1:
                        src_name = matching_sources[0]
                        row[table_idx] = f"_DBT_SOURCE_{src_name}_DBTSEP_{table_val}_"
                        if catalog_idx != -1 and len(row) > catalog_idx:
                            row[catalog_idx] = ""
                        is_source = True
                    elif len(matching_sources) > 1:
                        print(
                            f"Warning: Table '{table_val}' matches multiple sources {matching_sources}. Skipping metadata schema mapping."
                        )

                # 2. Match by model if not matched by source
                if not is_source and table_val in known_models:
                    row[table_idx] = f"_DBT_REF_{table_val}_"
                    if schema_idx != -1 and len(row) > schema_idx:
                        row[schema_idx] = ""
                    if catalog_idx != -1 and len(row) > catalog_idx:
                        row[catalog_idx] = ""

                writer.writerow(row)

            processed_any = True

    for item in os.listdir(source_dir):
        item_lower = item.lower()
        is_metadata_file = False
        for prefix_key in files_to_process:
            if item_lower.startswith(prefix_key) and item_lower.endswith(".csv"):
                is_metadata_file = True
                break
        if not is_metadata_file:
            src_item = os.path.join(source_dir, item)
            dest_item = os.path.join(temp_metadata_dir, item)
            if os.path.isfile(src_item):
                shutil.copy2(src_item, dest_item)

    if is_zip and extract_dir:
        shutil.rmtree(extract_dir, ignore_errors=True)

    return processed_any


def run_bulk_translation(
    input_dir,
    output_dir,
    gcs_bucket,
    location,
    metadata_path=None,
    metadata_dataset=None,
    default_database=None,
    schema_search_path=None,
):
    # Discover models and sources
    known_models, known_sources = discover_dbt_resources(input_dir)

    prefix = os.path.basename(os.path.normpath(input_dir))
    gcs_input_uri = f"gs://{gcs_bucket}/{prefix}_migration_input"
    gcs_output_uri = f"gs://{gcs_bucket}/{prefix}_migration_output"
    gcs_metadata_uri = f"gs://{gcs_bucket}/{prefix}_migration_metadata"

    local_temp_input = f"./temp_{prefix}_input"
    local_temp_output = f"./temp_{prefix}_output"
    local_temp_metadata = f"./temp_{prefix}_metadata"

    shutil.rmtree(local_temp_input, ignore_errors=True)
    shutil.rmtree(local_temp_output, ignore_errors=True)
    shutil.rmtree(local_temp_metadata, ignore_errors=True)
    os.makedirs(local_temp_input, exist_ok=True)
    os.makedirs(local_temp_output, exist_ok=True)

    headers = {}
    jinja_exprs_by_file = {}
    jinja_blocks_by_file = {}
    file_mapping = []

    print("Pre-processing local files (Jinja compilation & placeholder masking)...")
    for root, dirs, files in os.walk(input_dir):
        for f in files:
            if f.endswith(".sql"):
                src_path = os.path.join(root, f)
                rel_path = os.path.relpath(src_path, input_dir)
                dest_temp_path = os.path.join(local_temp_input, rel_path)

                os.makedirs(os.path.dirname(dest_temp_path), exist_ok=True)

                with open(src_path, "r", encoding="utf-8") as file:
                    content = file.read()

                config_header, stripped_content = extract_config_block(content)
                if config_header is None:
                    config_header = ""

                headers[rel_path] = config_header

                jinja_exprs = []
                jinja_blocks = []

                # Replace source and ref macros
                def replace_source(match):
                    src = match.group(1)
                    tbl = match.group(2)
                    return f"_DBT_SOURCE_{src}_DBTSEP_{tbl}_"

                processed = re.sub(
                    r'{{\s*source\s*\(\s*[\'"](.*?)[\'"]\s*,\s*[\'"](.*?)[\'"]\s*\)\s*}}',
                    replace_source,
                    stripped_content,
                    flags=re.IGNORECASE,
                )

                def replace_ref(match):
                    model = match.group(1)
                    return f"_DBT_REF_{model}_"

                processed = re.sub(
                    r'{{\s*ref\s*\(\s*[\'"](.*?)[\'"]\s*\)\s*}}',
                    replace_ref,
                    processed,
                    flags=re.IGNORECASE,
                )

                # Mask CTE-style Jinja expressions inside parentheses: ({{ macro(...) }})
                def mask_cte_expr(match, jinja_exprs=jinja_exprs):
                    expr = match.group(1)
                    idx = len(jinja_exprs)
                    jinja_exprs.append(expr)
                    return f"( SELECT * FROM _DBT_EXPR_{idx}_ )"

                processed = re.sub(
                    r"\(\s*(\{\{.*?\}\})\s*\)",
                    mask_cte_expr,
                    processed,
                    flags=re.DOTALL,
                )

                # Mask other expressions {{ ... }}
                def mask_expr(match, jinja_exprs=jinja_exprs):
                    expr = match.group(0)
                    idx = len(jinja_exprs)
                    jinja_exprs.append(expr)
                    return f"_DBT_EXPR_{idx}_"

                processed = re.sub(
                    r"\{\{.*?\}\}", mask_expr, processed, flags=re.DOTALL
                )

                # Mask control blocks {% ... %} inside comments
                def mask_block(match, jinja_blocks=jinja_blocks):
                    block = match.group(0)
                    idx = len(jinja_blocks)
                    jinja_blocks.append(block)
                    return f"/* _DBT_BLOCK_{idx}_ */"

                processed = re.sub(r"\{%.*?%\}", mask_block, processed, flags=re.DOTALL)

                with open(dest_temp_path, "w", encoding="utf-8") as temp_file:
                    temp_file.write(processed)

                file_mapping.append(rel_path)
                jinja_exprs_by_file[rel_path] = jinja_exprs
                jinja_blocks_by_file[rel_path] = jinja_blocks

    print(f"Prepared {len(file_mapping)} files for translation.")

    # GCS copy
    print(f"Uploading files to {gcs_input_uri}...")
    subprocess.run(
        ["gcloud", "storage", "rm", "--recursive", f"{gcs_input_uri}/"],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["gcloud", "storage", "rm", "--recursive", f"{gcs_output_uri}/"],
        capture_output=True,
        check=False,
    )

    if metadata_path:
        print(
            "Warning: Direct metadata ZIP processing is deprecated in BQMS v2 API. Please run a migration assessment first and pass the dataset ID using metadata_dataset."
        )
        print("Pre-processing metadata (mapping sources and refs)...")
        subprocess.run(
            ["gcloud", "storage", "rm", "--recursive", f"{gcs_metadata_uri}/"],
            capture_output=True,
            check=False,
        )
        if preprocess_metadata(
            metadata_path, local_temp_metadata, known_models, known_sources
        ):
            zip_path = f"./temp_{prefix}_metadata.zip"
            print(f"Zipping processed metadata to {zip_path}...")
            zip_directory(local_temp_metadata, zip_path)

            print(f"Uploading metadata zip to {gcs_metadata_uri}/metadata.zip...")
            subprocess.run(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    zip_path,
                    f"{gcs_metadata_uri}/metadata.zip",
                ],
                check=True,
            )
        else:
            print("Warning: No metadata files were processed successfully.")

    # Upload by running copy from local_temp_input to avoid nesting
    subprocess.run(
        ["gcloud", "storage", "cp", "-r", ".", f"{gcs_input_uri}/"],
        cwd=local_temp_input,
        check=True,
    )

    # Generate config yaml
    source_env_block = ""
    if metadata_dataset or default_database or schema_search_path:
        source_env_block = "\n      sourceEnv:"
        if metadata_dataset:
            source_env_block += f"\n        metadataStoreDataset: {metadata_dataset}"
        if default_database:
            source_env_block += f"\n        defaultDatabase: {default_database}"
        if schema_search_path:
            source_env_block += "\n        schemaSearchPath:"
            for schema in schema_search_path:
                source_env_block += f"\n          - {schema}"

    config_yaml_content = f"""displayName: {prefix}-bulk-translation
tasks:
  bulk-translation-task:
    type: Translation_Snowflake2BQ
    translationConfigDetails:
      gcsSourcePath: {gcs_input_uri}/
      gcsTargetPath: {gcs_output_uri}/
      sourceDialect:
        snowflakeDialect: {{}}
      targetDialect:
        bigqueryDialect: {{}}{source_env_block}
"""
    config_file_path = f"{prefix}_migration_config.yaml"
    with open(config_file_path, "w", encoding="utf-8") as config_file:
        config_file.write(config_yaml_content)

    # Run workflow
    print(
        f"Triggering BigQuery Translation Service in location: {location} (please wait)..."
    )
    res = subprocess.run(
        [
            "gcloud",
            "bq",
            "migration-workflows",
            "create",
            f"--location={location}",
            f"--config-file={config_file_path}",
            "--no-async",
        ],
        check=False,
    )
    print(f"Workflow finished with code: {res.returncode}")

    # Download translated files
    print(f"Downloading outputs from {gcs_output_uri}...")
    subprocess.run(
        ["gcloud", "storage", "cp", "-r", f"{gcs_output_uri}/", "."],
        cwd=local_temp_output,
        check=True,
    )

    # Post-process
    print("Post-processing translated files...")
    copyright_header = """# Copyright 2026 Google. This software is provided as-is, without warranty or
# representation for any use or purpose. Your use of it is subject to your
# agreement with Google.

"""
    success_count = 0
    for rel_path in file_mapping:
        src_temp_output_path = os.path.join(
            local_temp_output, f"{prefix}_migration_output", rel_path
        )
        dest_final_path = os.path.join(output_dir, rel_path)

        if not os.path.exists(src_temp_output_path):
            print(f"Warning: Translated file for {rel_path} not found in outputs.")
            continue

        with open(src_temp_output_path, "r", encoding="utf-8") as file:
            translated_content = file.read()

        translated_content = re.sub(
            r"\b__DEFAULT_DATABASE__\.__DEFAULT_SCHEMA__\.",
            "",
            translated_content,
            flags=re.IGNORECASE,
        )

        # Restore control blocks from comments
        file_blocks = jinja_blocks_by_file.get(rel_path, [])

        def restore_block(match, file_blocks=file_blocks):
            idx = int(match.group(1))
            return file_blocks[idx]

        post_processed = re.sub(
            r"/\*\s*_DBT_BLOCK_(\d+?)_\s*\*/",
            restore_block,
            translated_content,
            flags=re.IGNORECASE,
        )

        # Restore custom expressions
        file_exprs = jinja_exprs_by_file.get(rel_path, [])

        for idx in range(len(file_exprs)):
            pattern = re.compile(
                rf"SELECT\s+\*\s+FROM\s+_DBT_EXPR_{idx}_", re.IGNORECASE
            )
            post_processed = pattern.sub(f"_DBT_EXPR_{idx}_", post_processed)

        def restore_expr(match, file_exprs=file_exprs):
            idx = int(match.group(1))
            return file_exprs[idx]

        post_processed = re.sub(
            r"_DBT_EXPR_(\d+?)_", restore_expr, post_processed, flags=re.IGNORECASE
        )

        # Restore source macros
        def restore_source(match):
            src = match.group(1)
            tbl = match.group(2)
            return f"{{{{ source('{src.lower()}', '{tbl.lower()}') }}}}"

        post_processed = re.sub(
            r"_DBT_SOURCE_([a-zA-Z0-9_]+)_DBTSEP_([a-zA-Z0-9_]+)_",
            restore_source,
            post_processed,
            flags=re.IGNORECASE,
        )

        # Restore ref macros
        def restore_ref(match):
            model = match.group(1)
            return f"{{{{ ref('{model.lower()}') }}}}"

        post_processed = re.sub(
            r"_DBT_REF_([a-zA-Z0-9_]+)_",
            restore_ref,
            post_processed,
            flags=re.IGNORECASE,
        )

        # Remove any database/schema prefix before Jinja expressions
        post_processed = re.sub(
            r"\b[a-zA-Z0-9_]+\s*\.\s*[a-zA-Z0-9_]+\s*\.\s*\{\{",
            r"{{",
            post_processed,
            flags=re.IGNORECASE,
        )
        post_processed = re.sub(
            r"\b[a-zA-Z0-9_]+\s*\.\s*\{\{",
            r"{{",
            post_processed,
            flags=re.IGNORECASE,
        )

        post_processed = re.sub(
            r"\{\{\s*source\(.*?\)\s*\}\}\.([a-zA-Z0-9_]+)", r"\1", post_processed
        )
        post_processed = re.sub(
            r"\{\{\s*ref\(.*?\)\s*\}\}\.([a-zA-Z0-9_]+)", r"\1", post_processed
        )
        post_processed = re.sub(
            r"\{\{\s*(?:ref|source)\(.*?\)\s*\}\}\.\{\{",
            r"{{",
            post_processed,
            flags=re.IGNORECASE,
        )

        # Clean config header parameters
        original_header = headers.get(rel_path, "")
        cleaned_header = transform_config_block(original_header, rel_path)

        # Apply Jinja and SQL edge cases sanitization
        post_processed_sanitized = sanitize_jinja_and_sql_edge_cases(post_processed)

        # Apply JSON extraction sanitization
        post_processed_sanitized = sanitize_json_extractions(post_processed_sanitized)

        # Apply namespace resolution
        post_processed_sanitized = resolve_namespaces(
            post_processed_sanitized, known_models, known_sources
        )

        # Apply casing, join and cast standardization
        post_processed_sanitized = standardize_casing_and_joins(
            post_processed_sanitized
        )

        # Apply macro auditing
        warnings, post_processed_sanitized = audit_macros(post_processed_sanitized)
        warning_comments = ""
        if warnings:
            warning_comments = "\n".join([f"# WARNING: {w}" for w in warnings]) + "\n\n"

        # Re-order content: copyright header MUST be the very first thing
        if cleaned_header.strip():
            final_file_content = (
                copyright_header
                + "\n"
                + cleaned_header.strip()
                + "\n\n"
                + warning_comments
                + post_processed_sanitized
            )
        else:
            final_file_content = (
                copyright_header + "\n" + warning_comments + post_processed_sanitized
            )

        os.makedirs(os.path.dirname(dest_final_path), exist_ok=True)
        with open(dest_final_path, "w", encoding="utf-8") as file:
            file.write(final_file_content)
        success_count += 1

    # Copy .yml and .yaml files from input_dir to output_dir
    yaml_count = 0
    for root, dirs, files in os.walk(input_dir):
        for f in files:
            if f.endswith((".yml", ".yaml")):
                src_path = os.path.join(root, f)
                rel_path = os.path.relpath(src_path, input_dir)
                dest_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)
                yaml_count += 1
    print(f"Copied {yaml_count} YAML configuration files.")

    shutil.rmtree(local_temp_input, ignore_errors=True)
    shutil.rmtree(local_temp_output, ignore_errors=True)
    shutil.rmtree(local_temp_metadata, ignore_errors=True)

    zip_path = f"./temp_{prefix}_metadata.zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)

    if os.path.exists(config_file_path):
        os.remove(config_file_path)

    return f"Successfully migrated {success_count} SQL files and copied {yaml_count} YAML files to {output_dir}!"
