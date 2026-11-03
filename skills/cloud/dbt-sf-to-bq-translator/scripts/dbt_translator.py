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
    for suffix, target_type in [
        ("::date", "DATE"),
        ("::timestamp", "TIMESTAMP"),
        ("::float", "FLOAT64"),
    ]:
        idx = 0
        while True:
            pos = sql_content.lower().find(suffix, idx)
            if pos == -1:
                break
            end_pos = pos + len(suffix)
            if end_pos < len(sql_content) and (
                sql_content[end_pos].isalnum() or sql_content[end_pos] == "_"
            ):
                idx = end_pos
                continue

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
    # 0. Translate residual Snowflake TRY_CAST(...) to SAFE_CAST(...)
    # while preserving standard CAST(...) and Jinja macros
    sql_content = re.sub(
        r"(?<!\.)\btry_cast\s*\(", "SAFE_CAST(", sql_content, flags=re.IGNORECASE
    )

    # 1. Replace Snowflake date/time cast suffix ::date and ::timestamp
    sql_content = translate_cast_suffixes(sql_content)

    # 2. Translate dateadd
    sql_content = translate_dateadd_expressions(sql_content)

    # 3. Translate interval additions/subtractions
    sql_content = translate_interval_expressions(sql_content)

    # 4. Strip BQ Translation Service unknown type comments
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

    # Strip BQMS table-qualified Jinja prefixes: {{ ref(...) }}.col, {{ source(...) }}.col, {{ this }}.col, {{ table }}.col, {{ model }}.col
    sql_content = re.sub(
        r"\{\{\s*(?:ref\s*\(.*?\)|source\s*\(.*?\)|this|table|model|dest_model)\s*\}\}\s*\.\s*(?=[a-zA-Z0-9_`]|(?:\{\{))",
        "",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Fix displaced SELECT before {% for ... %} or {% if ... %} at start of CTE
    sql_content = re.sub(
        r"\bas\s*\(\s*select\s*(\{%-?\s*for\b.*?%-?\})",
        r"as (\n  \1\n  select",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    sql_content = re.sub(
        r"\bas\s*\(\s*select\s*(\{%-?\s*if\b.*?%-?\})(?=(?:(?!\{%-?\s*endif).)*?\{%-?\s*else\s*%-?\}\s*select\b)",
        r"as (\n  \1\n  select",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Fix displaced ORDER BY before loop union / {% endfor %}
    sql_content = re.sub(
        r"\border\s+by\s*((?:\{%-?\s*if\b[^%]*?%-?\}\s*union\s+all\s*\{%-?\s*endif\s*%-?\}\s*)?\{%-?\s*endfor\s*%-?\})",
        r"\1\n  order by",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Fix displaced CTE closing parenthesis and next CTE / main select around {% if ... %} block
    # Case 1a: ... ), next_cte as(select {% endif %}
    sql_content = re.sub(
        r"\)\s*(,\s*[a-zA-Z0-9_]+\s+as\s*\(\s*select\b)\s*(\{%-?\s*endif\s*%-?\})",
        r"\n  \2\n)\1",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Case 1b: {% if ... %} ... )) select {% endif %} or ) select {% endif %}
    sql_content = re.sub(
        r"(\{%-?\s*if\s+[^%]+?%-?\}(?:(?!\{%-?\s*endif\b).)*?)\)\s*select\s*(\{%-?\s*endif\s*%-?\})",
        r"\1\n  \2\n)\n\nselect",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Case 2a: {% endif %} displaced from before GROUP BY ALL to after GROUP BY ALL / end of statement
    for _ in range(2):
        sql_content = re.sub(
            r"(\{%-?\s*if\s+[^%]+?%-?\}\s*(?:where|and)\b(?:(?!\{%-?\s*(?:if|endif)\b|\bgroup\s+by\b).)*?)\n(\s*group\s+by\s+all\b[\s\S]*?)\s*(\{%-?\s*endif\s*%-?\})",
            r"\1\n  \3\n\2",
            sql_content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    # Case 2b: where CTE closing paren was swallowed into subquery and next CTE or main select was placed before {% endif %}
    for _ in range(2):
        sql_content = re.sub(
            r"(\{%-?\s*if\s+[^%]+?%-?\}\s*(?:where|and)\s+(?:(?!\{%-?\s*(?:if|endif)\b).)*?\))\s*\)\s*(,\s*[a-zA-Z0-9_]+\s+as\s*\([\s\S]*?)\s*(\{%-?\s*endif\s*%-?\})",
            r"\1\n  \3\n)\2",
            sql_content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        sql_content = re.sub(
            r"(\{%-?\s*if\s+[^%]+?%-?\}\s*(?:where|and)\s+(?:(?!\{%-?\s*(?:if|endif)\b).)*?\))\s*\)\s*(select\s+[\s\S]*?;)\s*(\{%-?\s*endif\s*%-?\})",
            r"\1\n  \3\n)\n\n\2",
            sql_content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    sql_content = re.sub(
        r"(\{%-?\s*if\s+[^%]+?%-?\}\s*where\s+[^\(\n]+?)\)\s*(select\s+.*?;)\s*(\{%-?\s*endif\s*%-?\})",
        r"\1\n  \3\n)\n\n\2",
        sql_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 6. Strip semicolon before loop unions, UNION ALL, or closing Jinja tags
    sql_content = re.sub(
        r";\s*(\{%-?\s*if\s+[^%]*?loop\.last[^%]*?%-?\}|\bUNION\s+ALL\b)",
        r"\n\1",
        sql_content,
        flags=re.IGNORECASE,
    )
    sql_content = re.sub(
        r";\s*(\{%-?\s*(?:endif|endfor)\s*%-?\})",
        r"\n\1\n;",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 7. Strip BQMS 16MB string length wrappers: substr(string(expr), 1, 16777216) -> cast(expr as STRING)
    def replace_substr_16mb(m):
        expr = m.group(1).strip()
        if re.match(r"^cast\(.*?\sas\s+string\)$", expr, re.IGNORECASE):
            return expr
        return f"cast({expr} as STRING)"

    sql_content = re.sub(
        r"\bsubstr\(\s*string\(\s*([a-zA-Z0-9_\.]+)\s*\)\s*,\s*1\s*,\s*16777216\s*\)",
        replace_substr_16mb,
        sql_content,
        flags=re.IGNORECASE,
    )

    return sql_content


def sanitize_struct_access(sql_content, struct_columns=None):
    """Converts JSON extractions on BigQuery STRUCT columns to dot notation.

    Args:
        sql_content: The translated SQL string.
        struct_columns: Optional list of additional STRUCT column names.

    Returns:
        The SQL string with STRUCT field access converted to `col.field`.
    """
    default_cols = [
        r"[a-zA-Z0-9_]*_STRUCT\b",
        r"\bSTRUCT_COL\b",
        r"[a-zA-Z0-9_]*_RECORD\b",
        r"\bRECORD_COL\b",
        r"[a-zA-Z0-9_]*_OBJ\b",
        r"\bOBJ_COL\b",
    ]
    if struct_columns:
        default_cols.extend(re.escape(c) for c in struct_columns)
    struct_pattern = r"(?:" + "|".join(default_cols) + r")"

    def replace_struct_field(m):
        full_col = m.group(1).strip()
        m_col = re.match(
            r"^(?:cast\(\s*)?(?:to_json\()?\s*(.*?)(?:\s+as\s+JSON\s*\))?\s*\)?$",
            full_col,
            re.IGNORECASE,
        )
        if m_col:
            full_col = m_col.group(1).strip()
        raw_path = m.group(2).strip().strip("'\"")
        raw_path = raw_path.replace(r"\'", "'").replace(r"\"", '"')
        if raw_path.startswith("$."):
            field = raw_path[2:]
        elif raw_path.startswith("$[") and raw_path.endswith("]"):
            field = raw_path[2:-1].strip("'\"")
        else:
            field = raw_path.lstrip("$.").strip("'\"")
        field = field.strip("'\"")
        return f"{full_col}.{field}"

    pattern = re.compile(
        rf"\b(?:(?:safe\.)?(?:json_value|json_extract_scalar))\(\s*(?:cast\(\s*)?(?:to_json\()?\s*((?:[a-zA-Z0-9_]+\.)?{struct_pattern}(?:\s+as\s+JSON\s*\))?)\s*\)?\s*,\s*('[^']+'|\"[^\"]+\")\s*\)",
        re.IGNORECASE,
    )
    return pattern.sub(replace_struct_field, sql_content)


def sanitize_unimplemented_opcodes(sql_content, struct_columns=None):
    """Sanitizes BQMS error_unimplemented markers from Snowflake bracket notation.

    Args:
        sql_content: The translated SQL string.
        struct_columns: Optional list of additional STRUCT column names.

    Returns:
        The SQL string with error_unimplemented replaced by dot notation or
        json_value.
    """
    default_cols = [
        r"[a-zA-Z0-9_]*_STRUCT\b",
        r"\bSTRUCT_COL\b",
        r"[a-zA-Z0-9_]*_RECORD\b",
        r"\bRECORD_COL\b",
        r"[a-zA-Z0-9_]*_OBJ\b",
        r"\bOBJ_COL\b",
    ]
    if struct_columns:
        default_cols.extend(re.escape(c) for c in struct_columns)
    struct_pattern = re.compile(
        r"(?:" + "|".join(default_cols) + r")",
        re.IGNORECASE,
    )

    def is_struct_col(col_str):
        clean = col_str.strip().split(".")[-1]
        return bool(struct_pattern.search(clean))

    error_regex = r"error_unimplemented\(\s*/\*(?:.*?)\*/\s*([^,]+?)\s*,\s*['\"]([^'\"]+)['\"]\s*\)"

    def replace_substr_error(m):
        col = m.group(1).strip()
        field = m.group(2).strip()
        if is_struct_col(col):
            return f"cast({col}.{field} as STRING)"
        else:
            return f"json_value({col}, '$.{field}')"

    sql_content = re.sub(
        rf"substr\(\s*string\(\s*{error_regex}\s*\)\s*,\s*1\s*,\s*16777216\s*\)",
        replace_substr_error,
        sql_content,
        flags=re.IGNORECASE,
    )

    def replace_cast_json_value_error(m):
        col = m.group(1).strip()
        field = m.group(2).strip()
        target_type = m.group(3).upper()
        if is_struct_col(col):
            return f"cast({col}.{field} as {target_type})"
        else:
            return f"cast(json_value({col}, '$.{field}') as {target_type})"

    sql_content = re.sub(
        rf"cast\(\s*json_value\(\s*{error_regex}\s*\)\s*as\s+([a-zA-Z0-9_]+)\s*\)",
        replace_cast_json_value_error,
        sql_content,
        flags=re.IGNORECASE,
    )

    def replace_cast_lax_float_error(m):
        col = m.group(1).strip()
        field = m.group(2).strip()
        target_type = m.group(3).upper()
        if target_type == "BIGNUMERIC":
            target_type = "NUMERIC"
        if is_struct_col(col):
            return f"cast({col}.{field} as {target_type})"
        else:
            return f"cast(json_value({col}, '$.{field}') as {target_type})"

    sql_content = re.sub(
        rf"cast\(\s*lax_float64\(\s*{error_regex}\s*\)\s*as\s+([a-zA-Z0-9_]+)\s*\)",
        replace_cast_lax_float_error,
        sql_content,
        flags=re.IGNORECASE,
    )

    def replace_plain_error(m):
        col = m.group(1).strip()
        field = m.group(2).strip()
        if is_struct_col(col):
            return f"{col}.{field}"
        else:
            return f"json_value({col}, '$.{field}')"

    sql_content = re.sub(
        error_regex,
        replace_plain_error,
        sql_content,
        flags=re.IGNORECASE,
    )

    return sql_content


def clean_json_col(col):
    col = col.strip()
    m = re.match(r"^cast\(\s*(.*?)\s+as\s+JSON\s*\)$", col, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return col


def clean_json_path(path):
    path = path.strip()
    path_unescaped = path.replace(r"\'", "'")
    path_unescaped = re.sub(r"\.\[", "[", path_unescaped)
    m = re.match(r"^\$\[['\"](.*?)['\"]\]$", path_unescaped)
    if m:
        inner = m.group(1)
        return f'$."{inner}"'
    return path_unescaped


def make_json_extract(col, path, as_type=None, safe=False):
    """Builds a standardized BigQuery JSON or ARRAY<STRUCT> extraction."""
    cast_fn = "SAFE_CAST" if safe else "CAST"
    col_clean = clean_json_col(col)
    path_clean = clean_json_path(path)
    m_arr_struct = re.match(r"^\$\[(\d+)\]\.([a-zA-Z0-9_\.]+)$", path_clean)
    if (
        m_arr_struct
        and "parse_json" not in col_clean.lower()
        and "to_json" not in col_clean.lower()
    ):
        idx_str, field_path = m_arr_struct.group(1), m_arr_struct.group(2)
        expr = f"{col_clean}[SAFE_OFFSET({idx_str})].{field_path}"
        if as_type and as_type.upper() != "STRING":
            return f"{cast_fn}({expr} AS {as_type.upper()})"
        return expr
    if "parse_json" in col_clean.lower():
        if as_type and as_type.upper() != "STRING":
            return (
                f"{cast_fn}(JSON_EXTRACT_SCALAR({col_clean}, '{path_clean}')"
                f" AS {as_type.upper()})"
            )
        elif as_type:
            return (
                f"{cast_fn.lower()}(JSON_EXTRACT_SCALAR({col_clean},"
                f" '{path_clean}') as STRING)"
            )
        else:
            return f"JSON_EXTRACT_SCALAR({col_clean}, '{path_clean}')"
    else:
        if as_type and as_type.upper() != "STRING":
            return (
                f"{cast_fn}(json_value({col_clean}, '{path_clean}')"
                f" AS {as_type.upper()})"
            )
        else:
            return f"json_value({col_clean}, '{path_clean}')"


def sanitize_json_extractions(sql_content):
    escaped_str = r"'((?:[^'\\]|\\.)*)'"

    def replace_match(m):
        cleaned_path = re.sub(r"^\$?\.?", "", m.group(3))
        sep = "" if cleaned_path.startswith("[") else "."
        return f"json_query({m.group(1)}, '{m.group(2)}{sep}{cleaned_path}')"

    pattern = re.compile(
        rf"json_query\(\s*json_query\(\s*([^,]+)\s*,\s*{escaped_str}\)\s*,\s*{escaped_str}\)",
        re.IGNORECASE,
    )
    while True:
        new_content, count = pattern.subn(replace_match, sql_content)
        if count == 0:
            break
        sql_content = new_content

    # 1.5. Replace json_value wrappers: json_value(json_query(col, 'path')) and json_value(json_query(col, 'path1'), 'path2')
    def replace_json_value_query_2arg(m):
        cleaned_path = re.sub(r"^\$?\.?", "", m.group(3))
        sep = "" if cleaned_path.startswith("[") else "."
        return make_json_extract(m.group(1), f"{m.group(2)}{sep}{cleaned_path}")

    sql_content = re.sub(
        rf"json_value\(\s*json_query\(\s*([^,]+)\s*,\s*{escaped_str}\s*\)\s*,\s*{escaped_str}\s*\)",
        replace_json_value_query_2arg,
        sql_content,
        flags=re.IGNORECASE,
    )

    def replace_json_value_query(m):
        return make_json_extract(m.group(1), m.group(2))

    sql_content = re.sub(
        rf"json_value\(\s*json_query\(\s*(.*?),\s*{escaped_str}\s*\)\s*\)",
        replace_json_value_query,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 2. Replace string extraction wrappers: substr(string(json_query(col, 'path')), 1, 16777216)
    def replace_substr_json_query(m):
        return make_json_extract(m.group(1), m.group(2))

    sql_content = re.sub(
        rf"substr\(\s*string\(\s*json_query\(\s*([^,]+),\s*{escaped_str}\s*\)\s*\)\s*,\s*1\s*,\s*\d+\s*\)",
        replace_substr_json_query,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 3. Replace numeric wrappers: CAST(lax_float64(json_query(col, 'path')) as BIGNUMERIC)
    def replace_lax_bignumeric(m):
        return make_json_extract(m.group(1), m.group(2), as_type="NUMERIC")

    sql_content = re.sub(
        rf"CAST\(\s*lax_float64\(\s*json_query\(\s*([^,]+),\s*{escaped_str}\s*\)\s*\)\s*as\s+BIGNUMERIC\)",
        replace_lax_bignumeric,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 4. Replace float wrappers: lax_float64(json_query(col, 'path'))
    def replace_lax_float(m):
        return make_json_extract(m.group(1), m.group(2), as_type="FLOAT64")

    sql_content = re.sub(
        rf"lax_float64\(\s*json_query\(\s*([^,]+),\s*{escaped_str}\s*\)\s*\)",
        replace_lax_float,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 5. Replace boolean wrappers: lax_bool(json_query(col, 'path'))
    def replace_lax_bool(m):
        return make_json_extract(m.group(1), m.group(2), as_type="BOOL")

    sql_content = re.sub(
        rf"lax_bool\(\s*json_query\(\s*([^,]+),\s*{escaped_str}\s*\)\s*\)",
        replace_lax_bool,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 6. Replace plain json_query: json_query(col, 'path')
    def replace_plain_json_query(m):
        return make_json_extract(m.group(1), m.group(2))

    sql_content = re.sub(
        rf"json_query\(\s*([^,]+),\s*{escaped_str}\s*\)",
        replace_plain_json_query,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 6.5. Replace (safe_)cast(json_extract_scalar(col, path) as TYPE)
    # if not parse_json
    def replace_cast_json_extract_scalar(m):
        is_safe = m.group(1).lower() == "safe_cast"
        col = m.group(2)
        path = m.group(3)
        target_type = m.group(4).upper()
        if "parse_json" not in col.lower():
            return make_json_extract(
                col, path, as_type=target_type, safe=is_safe
            )
        return m.group(0)

    cast_scalar_re = (
        rf"\b(safe_cast|cast)\(\s*json_extract_scalar\(\s*([^,]+),"
        rf"\s*{escaped_str}\s*\)\s*as\s+([a-zA-Z0-9_]+)\s*\)"
    )
    sql_content = re.sub(
        cast_scalar_re,
        replace_cast_json_extract_scalar,
        sql_content,
        flags=re.IGNORECASE,
    )

    # Replace plain json_extract_scalar if not parse_json
    def replace_plain_json_extract_scalar(m):
        col = m.group(1)
        path = m.group(2)
        if "parse_json" not in col.lower():
            return make_json_extract(col, path)
        return m.group(0)

    sql_content = re.sub(
        rf"json_extract_scalar\(\s*([^,]+),\s*{escaped_str}\s*\)",
        replace_plain_json_extract_scalar,
        sql_content,
        flags=re.IGNORECASE,
    )

    # Clean redundant cast(... as JSON) inside json_value
    sql_content = re.sub(
        r"json_value\(\s*cast\(\s*(.*?)\s+as\s+JSON\s*\)\s*,",
        r"json_value(\1,",
        sql_content,
        flags=re.IGNORECASE,
    )

    # Clean any residual dot before bracket in JSONPath strings: $.items.[1] -> $.items[1]
    sql_content = re.sub(
        rf"(\b(?:json_value|json_extract_scalar|json_query)\s*\(\s*[^,]+,\s*){escaped_str}",
        lambda m: f"{m.group(1)}'{m.group(2).replace('.[', '[')}'",
        sql_content,
        flags=re.IGNORECASE,
    )

    # Convert json_value(col, '$[idx].field') on ARRAY<STRUCT> columns to col[SAFE_OFFSET(idx)].field
    def replace_array_struct_json_value(m):
        col = m.group(1).strip()
        idx_str = m.group(2)
        field_path = m.group(3)
        if "parse_json" not in col.lower() and "to_json" not in col.lower():
            return f"{clean_json_col(col)}[SAFE_OFFSET({idx_str})].{field_path}"
        return m.group(0)

    sql_content = re.sub(
        r"\bjson_value\(\s*([^,]+?)\s*,\s*['\"]\$\[(\d+)\]\.([a-zA-Z0-9_\.]+)['\"]\s*\)",
        replace_array_struct_json_value,
        sql_content,
        flags=re.IGNORECASE,
    )

    # 7. Replace untyped ARRAY<JSON> casts from BQMS: cast(col as ARRAY<JSON>) -> cast(col as ARRAY<STRING>)
    sql_content = re.sub(
        r"\bcast\(\s*(.*?)\s+as\s+ARRAY<JSON>\s*\)",
        r"cast(\1 as ARRAY<STRING>)",
        sql_content,
        flags=re.IGNORECASE,
    )

    # 8. Clean up redundant json_value wrappers over json_value
    idx = 0
    while True:
        m = re.search(r"\bjson_value\s*\(", sql_content[idx:], re.IGNORECASE)
        if not m:
            break
        start = idx + m.start()
        args_start = idx + m.end()
        paren = 1
        pos = args_start
        while paren > 0 and pos < len(sql_content):
            if sql_content[pos] == "(":
                paren += 1
            elif sql_content[pos] == ")":
                paren -= 1
            pos += 1
        if paren == 0:
            inner = sql_content[args_start : pos - 1].strip()
            if re.match(r"^(?:safe\.)?json_value\b", inner, re.IGNORECASE):
                sql_content = sql_content[:start] + inner + sql_content[pos:]
                idx = start + len(inner)
                continue
        idx = args_start

    # 9. Fix Invalid datetime string on ISO-8601 JSON timestamps (ending in 'Z')
    # In BigQuery, CAST(json_extract_scalar(...) AS DATETIME) fails on "YYYY-MM-DDTHH:MM:SS.sssZ".
    # Convert JSON extraction casts from DATETIME to TIMESTAMP.
    idx = 0
    while True:
        m = re.search(
            r"\b(safe_cast|cast)\s*\(", sql_content[idx:], re.IGNORECASE
        )
        if not m:
            break
        start = idx + m.start()
        args_start = idx + m.end()
        paren = 1
        pos = args_start
        while paren > 0 and pos < len(sql_content):
            if sql_content[pos] == "(":
                paren += 1
            elif sql_content[pos] == ")":
                paren -= 1
            pos += 1
        if paren == 0:
            inside = sql_content[args_start : pos - 1]
            m_dt = re.search(r"\s+as\s+datetime\s*$", inside, re.IGNORECASE)
            if m_dt:
                expr_part = inside[: m_dt.start()].strip()
                if re.search(
                    r"json_extract_scalar|json_value|json_query|parse_json",
                    expr_part,
                    re.IGNORECASE,
                ):
                    cast_fn = m.group(1).lower()
                    new_cast = f"{cast_fn}({expr_part} as TIMESTAMP)"
                    sql_content = (
                        sql_content[:start] + new_cast + sql_content[pos:]
                    )
                    idx = start + len(new_cast)
                    continue
        idx = args_start

    return sql_content


def sanitize_array_casts(sql_content, array_cast_mode="string"):
    """Sanitizes BQMS-generated CAST(... AS ARRAY<JSON>) constructs.

    Args:
        sql_content: The translated SQL string.
        array_cast_mode: Mode to map untyped arrays:
            - 'string': cast(col as STRING)
            - 'array_string': cast(col as ARRAY<STRING>)
            - 'json_extract_string_array': json_extract_string_array(col)
            - None or 'preserve': leave as ARRAY<JSON>

    Returns:
        The SQL string with ARRAY<JSON> casts converted according to
        array_cast_mode.
    """
    if not array_cast_mode or array_cast_mode == "preserve":
        return sql_content

    def replace_array_cast(match):
        expr = match.group(1).strip()
        if array_cast_mode == "string":
            return f"cast({expr} as STRING)"
        elif array_cast_mode == "array_string":
            return f"cast({expr} as ARRAY<STRING>)"
        elif array_cast_mode == "json_extract_string_array":
            return f"json_extract_string_array({expr})"
        return match.group(0)

    pattern = re.compile(
        r"\bcast\(\s*(.*?)\s+as\s+ARRAY<JSON>\s*\)",
        re.IGNORECASE,
    )
    return pattern.sub(replace_array_cast, sql_content)


def audit_macros(sql_content):
    # Find all {{ ... }} occurrences
    macro_pattern = re.compile(r"({{\s*(.*?)\s*}})", re.DOTALL)
    warnings = []

    # Standard allowlisted macros
    allowlist = {
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
        name_match = re.match(r"([a-zA-Z0-9_\.]+)", expr_content.strip())
        if name_match:
            macro_name = name_match.group(1)
            base_name = macro_name.split(".")[0]
            if base_name not in allowlist and not macro_name.startswith("dbt_utils."):
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
    sql_temp = re.sub(r"/\*.*?\*/", mask_comment, sql_content, flags=re.DOTALL)
    sql_temp = re.sub(r"--.*$", mask_comment, sql_temp, flags=re.MULTILINE)

    # Mask Jinja blocks
    sql_temp = re.sub(r"\{\{.*?\}\}", mask_jinja, sql_temp, flags=re.DOTALL)
    sql_temp = re.sub(r"\{%.*?%\}", mask_jinja, sql_temp, flags=re.DOTALL)

    # Mask strings
    sql_temp = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", mask_string, sql_temp)
    sql_temp = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', mask_string, sql_temp)

    # --- SQL Cleanup (Masked version) ---

    # 0. Translate residual Snowflake TRY_CAST(...) to safe_cast(...)
    sql_temp = re.sub(
        r"\btry_cast\s*\(", "safe_cast(", sql_temp, flags=re.IGNORECASE
    )

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

    # Standardize ID column BIGNUMERIC casts to INT64
    def replace_id_bignumeric(m):
        col = m.group(1).strip()
        alias = m.group(2).strip()
        if re.search(r"(?:^|_)id$", alias, re.IGNORECASE) or re.search(
            r"(?:^|_)id$", col, re.IGNORECASE
        ):
            return f"cast({col} as int64) as {alias}"
        return m.group(0)

    sql_temp = re.sub(
        r"\bcast\(\s*([a-zA-Z0-9_\.]+)\s+as\s+bignumeric\s*\)\s+as\s+([a-zA-Z0-9_]+)\b",
        replace_id_bignumeric,
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
        if func_name.upper() in ("SAFE_OFFSET", "OFFSET", "SAFE_ORDINAL", "ORDINAL"):
            return f"{func_name.upper()}("
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
    while re.search(r"@@TEMP_COMMENT_(\d+?)@@", sql_restored):
        sql_restored = re.sub(r"@@TEMP_COMMENT_(\d+?)@@", restore_comment, sql_restored)

    # --- Post-restore Cleanup ---
    # Simplify cast('1' as int64) -> 1
    sql_restored = re.sub(
        r"\bcast\(\s*['\"](\d+)['\"]\s*as\s+int64\s*\)",
        r"\1",
        sql_restored,
        flags=re.IGNORECASE,
    )

    # Simplify to_json_string(struct(... as _f1, ... as _f2)) in PARTITION BY
    def simplify_partition_struct(match):
        struct_content = match.group(1)
        cols = []
        for part in struct_content.split(","):
            col_match = re.search(r"^(.*?)\s+as\s+_f\d+$", part.strip(), re.IGNORECASE)
            if col_match:
                cols.append(col_match.group(1).strip())
            else:
                cols.append(part.strip())
        return f"partition by {', '.join(cols)}"

    sql_restored = re.sub(
        r"\bpartition\s+by\s+to_json_string\s*\(\s*struct\s*\((.*?)\)\s*\)",
        simplify_partition_struct,
        sql_restored,
        flags=re.IGNORECASE,
    )

    # Simplify = numeric '1' -> = 1
    sql_restored = re.sub(
        r"=\s*numeric\s*['\"](\d+)['\"]",
        r"= \1",
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

    # Mask /* */ comments
    sql_temp = re.sub(r"/\*.*?\*/", mask_comment, sql_content, flags=re.DOTALL)
    # Mask -- comments (excluding newlines)
    sql_temp = re.sub(r"--.*$", mask_comment, sql_temp, flags=re.MULTILINE)

    end_keywords = r"\b(join|where|group|order|limit|union|select|having|using|on|qualify|window|as)\b|\)"

    def replace_tables(match):
        keyword = match.group(1)
        table_list_str = match.group(2)

        parts = table_list_str.split(",")
        new_parts = []
        for part in parts:
            part_clean = part.strip()
            table_match = re.fullmatch(
                r"([a-zA-Z0-9_\.]+)(?:\s+(?:as\s+)?([a-zA-Z0-9_]+))?",
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

    while re.search(r"@@TEMP_COMMENT_(\d+?)@@", sql_temp):
        sql_temp = re.sub(r"@@TEMP_COMMENT_(\d+?)@@", restore_comment, sql_temp)
    return sql_temp


def is_invalid_bq_hook(hook_sql):
    hook_sql_lower = hook_sql.lower()
    for pat in (
        "alter iceberg table",
        "unset secure",
        "search optimization",
        "copy into",
        "set change_tracking",
        "set data_retention_time_in_days",
    ):
        if pat in hook_sql_lower:
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


def _escape_newlines_in_strings(s):
    out = []
    in_sq = False
    in_dq = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append(c)
            out.append(s[i + 1])
            i += 2
            continue
        if c == "'" and not in_dq:
            in_sq = not in_sq
            out.append(c)
        elif c == '"' and not in_sq:
            in_dq = not in_dq
            out.append(c)
        elif c == "\n" and (in_sq or in_dq):
            out.append("\\n")
        elif c == "\r" and (in_sq or in_dq):
            pass
        else:
            out.append(c)
        i += 1
    return "".join(out)


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

    args_str_escaped = _escape_newlines_in_strings(args_str)

    try:
        tree = ast.parse(f"config({args_str_escaped})")
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


def discover_dbt_resources(input_dir, output_dir=None):
    known_models = set()
    known_sources = {}
    abs_output = os.path.abspath(output_dir) if output_dir else None

    for root, dirs, files in os.walk(input_dir):
        if abs_output:
            dirs[:] = [
                d
                for d in dirs
                if os.path.abspath(os.path.join(root, d)) != abs_output
                and d
                not in (
                    ".git",
                    "target",
                    "dbt_packages",
                    "logs",
                    "venv",
                    ".venv",
                    "migration_plan",
                )
                and not d.startswith(".")
            ]
        else:
            dirs[:] = [
                d
                for d in dirs
                if d
                not in (
                    ".git",
                    "target",
                    "dbt_packages",
                    "logs",
                    "venv",
                    ".venv",
                    "migration_plan",
                )
                and not d.startswith(".")
            ]
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


def _json_path_to_sf_colon(col, raw_path, cast_type="varchar"):
    """Converts a BigQuery JSONPath expression back to Snowflake colon notation."""
    path = raw_path.strip().lstrip("$").lstrip(".")
    path = re.sub(r"\.\[", "[", path)
    segments = []
    for seg in path.split("."):
        seg = seg.strip()
        if not seg:
            continue
        m_arr = re.match(r"^([^\[\]]+)((?:\[\d+\])+)$", seg)
        if m_arr:
            base_seg = m_arr.group(1).strip("'\"")
            idx_part = m_arr.group(2)
            segments.append(f'"{base_seg}"{idx_part}')
        elif seg.startswith("[") and seg.endswith("]"):
            inner = seg[1:-1].strip("'\"")
            if inner.isdigit() and segments:
                segments[-1] = f"{segments[-1]}[{inner}]"
            else:
                segments.append(f'"{inner}"')
        else:
            seg = seg.strip("'\"")
            segments.append(f'"{seg}"')
    if not segments:
        return f"{col}::{cast_type}"
    return f"{col}:{':'.join(segments)}::{cast_type}"


def _mask_else_branches(processed, jinja_blocks):
    """Masks {% else %} before SELECT or WHERE so both branches remain valid SQL."""

    def mask_else_select(match):
        block = match.group(1)
        intervening = match.group(2)
        idx = len(jinja_blocks)
        jinja_blocks.append(block)
        return f"UNION ALL /* _DBT_BLOCK_{idx}_ */ {intervening}SELECT"

    processed = re.sub(
        r"(\{%\s*else\s*%\})(\s*(?:\{%.*?%\}\s*)*)SELECT\b",
        mask_else_select,
        processed,
        flags=re.IGNORECASE,
    )

    def mask_else_where(match):
        block = match.group(0)
        idx = len(jinja_blocks)
        jinja_blocks.append(block)
        return f"/* _DBT_BLOCK_{idx}_ */ AND"

    processed = re.sub(
        r"\{%\s*else\s*%\}\s*WHERE\b",
        mask_else_where,
        processed,
        flags=re.IGNORECASE,
    )
    return processed


def _clean_else_branches(translated_content, file_blocks):
    """Cleans temporary UNION ALL and AND markers around {% else %} blocks."""

    def is_else_block(idx_str):
        idx = int(idx_str)
        return 0 <= idx < len(file_blocks) and bool(
            re.match(r"^\s*\{%-?\s*else\b", file_blocks[idx], re.IGNORECASE)
        )

    def clean_reordered_else_union(m):
        blocks_chunk = m.group(1)
        indices = re.findall(r"_DBT_BLOCK_(\d+?)_", blocks_chunk)
        if any(is_else_block(i) for i in indices):
            return f"{blocks_chunk}\nSELECT\n"
        return m.group(0)

    translated_content = re.sub(
        r"UNION\s+ALL\s*\n\s*SELECT\s*\n(\s*(?:/\*\s*_DBT_BLOCK_\d+?_\s*\*/\s*)+)",
        clean_reordered_else_union,
        translated_content,
        flags=re.IGNORECASE,
    )

    def clean_else_union(m):
        if is_else_block(m.group(1)):
            has_trailing_select = bool(m.group(2))
            return f"/* _DBT_BLOCK_{m.group(1)}_ */" + (
                "\nSELECT" if has_trailing_select else ""
            )
        return m.group(0)

    translated_content = re.sub(
        r"UNION\s+ALL\s*(?:SELECT\s*)?/\*\s*_DBT_BLOCK_(\d+?)_\s*\*/\s*(SELECT\b)?",
        clean_else_union,
        translated_content,
        flags=re.IGNORECASE,
    )

    def clean_else_and(m):
        if is_else_block(m.group(1)):
            return f"/* _DBT_BLOCK_{m.group(1)}_ */"
        return m.group(0)

    translated_content = re.sub(
        r"/\*\s*_DBT_BLOCK_(\d+?)_\s*\*/\s*AND\b",
        clean_else_and,
        translated_content,
        flags=re.IGNORECASE,
    )
    return translated_content


def run_bulk_translation(
    input_dir,
    output_dir,
    gcs_bucket,
    location,
    metadata_path=None,
    metadata_dataset=None,
    default_database=None,
    schema_search_path=None,
    array_cast_mode=None,
    struct_columns=None,
):
    # Discover models and sources
    known_models, known_sources = discover_dbt_resources(input_dir, output_dir)

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

    abs_output = os.path.abspath(output_dir) if output_dir else None
    print("Pre-processing local files (Jinja compilation & placeholder masking)...")
    for root, dirs, files in os.walk(input_dir):
        if abs_output:
            dirs[:] = [
                d
                for d in dirs
                if os.path.abspath(os.path.join(root, d)) != abs_output
                and d
                not in (
                    ".git",
                    "target",
                    "dbt_packages",
                    "logs",
                    "venv",
                    ".venv",
                    "migration_plan",
                )
                and not d.startswith(".")
            ]
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

                # Strip copyright header or # comments from stripped_content before passing to Snowflake parser
                stripped_content = re.sub(
                    r"^\s*#\s*Copyright.*?agreement with Google\.\s*",
                    "",
                    stripped_content,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                # Strip pre-existing translation metadata comments
                stripped_content = re.sub(
                    r"--\s*(?:Translation time|Translation job ID|Source|Translated from|Translated to):.*?\n",
                    "",
                    stripped_content,
                    flags=re.IGNORECASE,
                )

                jinja_exprs = []
                jinja_blocks = []

                # Mask control blocks {% ... %} and Jinja comments {# ... #} inside SQL block comments
                def mask_block(match, jinja_blocks=jinja_blocks):
                    block = match.group(0)
                    idx = len(jinja_blocks)
                    jinja_blocks.append(block)
                    return f"/* _DBT_BLOCK_{idx}_ */"

                # Mask Jinja comments {# ... #} FIRST before any # line comment conversion or {{ ... }} masking
                stripped_content = re.sub(
                    r"\{#.*?#\}", mask_block, stripped_content, flags=re.DOTALL
                )

                # Convert any remaining # comments (excluding #}) to -- comments so Snowflake parser won't fail
                stripped_content = re.sub(
                    r"^\s*#(?!\})(.*)$",
                    r"--\1",
                    stripped_content,
                    flags=re.MULTILINE,
                )

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

                # Mask CTE-style Jinja expressions inside parentheses: AS ({{ macro(...) }})
                def mask_cte_expr(match, jinja_exprs=jinja_exprs):
                    kw = match.group(1)
                    expr = match.group(2)
                    idx = len(jinja_exprs)
                    jinja_exprs.append(expr)
                    return f"{kw}( SELECT * FROM _DBT_CTE_EXPR_{idx}_ )"

                processed = re.sub(
                    r"(\b(?:AS|FROM|JOIN)\s*)\(\s*(\{\{.*?\}\})\s*\)",
                    mask_cte_expr,
                    processed,
                    flags=re.DOTALL | re.IGNORECASE,
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

                # Mask loop unions like {% if not loop.last %}UNION ALL{% endif %} or {% if x != 48 %}union all{% endif %}
                processed = re.sub(
                    r"\{%-?\s*if\s+[^%]*?%-?\}\s*union\s+all\s*\{%-?\s*endif\s*%-?\}",
                    mask_block,
                    processed,
                    flags=re.IGNORECASE,
                )

                # Mask {% else %} before SELECT or WHERE
                processed = _mask_else_branches(processed, jinja_blocks)

                processed = re.sub(r"\{%.*?%\}", mask_block, processed, flags=re.DOTALL)

                # Normalize ::variant:field to (::variant):field for BQMS grammar
                processed = re.sub(
                    r"\b([a-zA-Z0-9_]+)::variant:([a-zA-Z0-9_\"]+)",
                    r"(\1::variant):\2",
                    processed,
                )

                # Normalize prior reserved keyword in table aliases and column references
                processed = re.sub(
                    r"\b(JOIN\s+[a-zA-Z0-9_]+)\s+prior\b",
                    r'\1 AS "prior"',
                    processed,
                    flags=re.IGNORECASE,
                )
                processed = re.sub(r"\bprior\.", r'"prior".', processed)

                # Convert 'col LIKE ANY (SELECT ...)' to 'EXISTS (SELECT 1 ... AND col LIKE ...)'
                def replace_like_any_subquery(match):
                    col = match.group(1)
                    subq = match.group(2)
                    m = re.match(
                        r"SELECT\s+([a-zA-Z0-9_]+)\s+FROM\s+(.*)",
                        subq,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if m:
                        target_col = m.group(1)
                        rest = m.group(2)
                        return f"EXISTS (SELECT 1 FROM {rest} AND {col} LIKE {target_col})"
                    return match.group(0)

                processed = re.sub(
                    r"([a-zA-Z0-9_]+)\s+LIKE\s+ANY\s*\(\s*(SELECT\s+.*?)\)",
                    replace_like_any_subquery,
                    processed,
                    flags=re.IGNORECASE | re.DOTALL,
                )

                # Convert Snowflake bracket notation on object/variant columns:
                # col['prop'] -> col:prop, col['prop']['sub'] -> col:prop:sub
                # This prevents BQMS from failing with JsonFieldJsonNumericAsJsonOpcode (error_unimplemented)
                while True:
                    new_processed = re.sub(
                        r"\b([a-zA-Z0-9_:]+)\[['\"]([a-zA-Z0-9_]+)['\"]\]",
                        r"\1:\2",
                        processed,
                    )
                    if new_processed == processed:
                        break
                    processed = new_processed

                # Normalize already-translated BigQuery constructs for idempotent re-translation
                if re.search(r"--\s*Translated to:\s*BigQuery", content, re.IGNORECASE):
                    processed = re.sub(
                        r"\b([a-zA-Z0-9_]+)\[\s*SAFE_OFFSET\(\s*(\d+)\s*\)\s*\]\.([a-zA-Z0-9_]+)",
                        r"\1[\2]:\3::varchar",
                        processed,
                        flags=re.IGNORECASE,
                    )

                    processed = re.sub(
                        r"\bcast\(\s*json_value\(\s*([a-zA-Z0-9_]+)\s*,\s*'(\$\.[^']+)'\s*\)\s*as\s+([a-zA-Z0-9_]+)\s*\)",
                        lambda m: _json_path_to_sf_colon(
                            m.group(1), m.group(2), m.group(3)
                        ),
                        processed,
                        flags=re.IGNORECASE,
                    )
                    processed = re.sub(
                        r"\bjson_value\(\s*([a-zA-Z0-9_]+)\s*,\s*'(\$\.[^']+)'\s*\)",
                        lambda m: _json_path_to_sf_colon(
                            m.group(1), m.group(2), "varchar"
                        ),
                        processed,
                        flags=re.IGNORECASE,
                    )

                    if not re.search(
                        r"\b(?:FROM|JOIN|AS)\s+(?:STRUCT_COL|RECORD_COL|OBJ_COL)\b",
                        processed,
                        re.IGNORECASE,
                    ):
                        processed = re.sub(
                            r"\b(STRUCT_COL|RECORD_COL|OBJ_COL)\.([a-zA-Z_][a-zA-Z0-9_]*)\b",
                            r'\1:"\2"::varchar',
                            processed,
                        )

                    processed = re.sub(
                        r"\bAS\s+BOOL\b",
                        "AS BOOLEAN",
                        processed,
                        flags=re.IGNORECASE,
                    )
                    processed = re.sub(
                        r"\bAS\s+TIMESTAMP\b",
                        "AS TIMESTAMP_LTZ",
                        processed,
                        flags=re.IGNORECASE,
                    )
                    processed = re.sub(
                        r"\bAS\s+NUMERIC\b",
                        "AS NUMBER(10,0)",
                        processed,
                        flags=re.IGNORECASE,
                    )
                    processed = re.sub(
                        r"\bINTERVAL\s+(\d+)\s+([a-zA-Z]+)\b",
                        r"INTERVAL '\1 \2'",
                        processed,
                        flags=re.IGNORECASE,
                    )
                    processed = re.sub(
                        r"\border\s+by\s+([a-zA-Z0-9_\.]+)\s+DESC\b(?!\s+NULLS)",
                        r"ORDER BY \1 DESC NULLS LAST",
                        processed,
                        flags=re.IGNORECASE,
                    )

                is_macro_or_dynamic_test = bool(
                    re.match(r"^\s*\{%-?\s*macro\b", content, re.IGNORECASE)
                    or (
                        re.match(r"^\s*\{%-?\s*test\b", content, re.IGNORECASE)
                        and re.search(
                            r"\{%-?\s*set\s+\w+_clause\b", content, re.IGNORECASE
                        )
                    )
                )
                has_sql = not is_macro_or_dynamic_test and bool(
                    re.sub(
                        r"/\*.*?\*/|--[^\n]*|_DBT_EXPR_\d+_",
                        "",
                        processed,
                        flags=re.DOTALL,
                    ).strip()
                )
                if not has_sql:
                    processed = f"SELECT 1 AS __dbt_dummy; /* __DBT_PURE_MACRO__\n{processed}\n*/"

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
            src_orig_path = os.path.join(input_dir, rel_path)
            if os.path.exists(src_orig_path):
                with open(src_orig_path, "r", encoding="utf-8") as orig_file:
                    orig_content = orig_file.read()
                if not orig_content.strip():
                    final_file_content = copyright_header
                    os.makedirs(os.path.dirname(dest_final_path), exist_ok=True)
                    with open(dest_final_path, "w", encoding="utf-8") as file:
                        file.write(final_file_content)
                    success_count += 1
                    continue
            print(f"Warning: Translated file for {rel_path} not found in outputs.")
            continue

        with open(src_temp_output_path, "r", encoding="utf-8") as file:
            translated_content = file.read()

        m_pure = re.search(
            r"/\*\s*__DBT_PURE_MACRO__\s*(.*?)\s*\*/",
            translated_content,
            flags=re.DOTALL,
        )
        if m_pure:
            translated_content = m_pure.group(1)

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

        translated_content = _clean_else_branches(
            translated_content, file_blocks
        )

        post_processed = re.sub(
            r"/\*\s*_DBT_BLOCK_(\d+?)_\s*\*/",
            restore_block,
            translated_content,
            flags=re.IGNORECASE,
        )
        post_processed = re.sub(
            r"\b_DBT_BLOCK_(\d+?)_\b",
            restore_block,
            post_processed,
            flags=re.IGNORECASE,
        )

        # Restore custom expressions
        file_exprs = jinja_exprs_by_file.get(rel_path, [])

        for idx in range(len(file_exprs)):
            pattern = re.compile(
                rf"SELECT\s+\*\s+FROM\s+_DBT_CTE_EXPR_{idx}_", re.IGNORECASE
            )
            post_processed = pattern.sub(f"_DBT_EXPR_{idx}_", post_processed)

        post_processed = re.sub(
            r"_DBT_CTE_EXPR_(\d+?)_",
            r"_DBT_EXPR_\1_",
            post_processed,
            flags=re.IGNORECASE,
        )

        # Strip BQMS table-qualified placeholder prefixes before restoring Jinja expressions
        post_processed = re.sub(
            r"\b_DBT_(?:SOURCE|REF|EXPR)_[a-zA-Z0-9_]+_\s*\.\s*(?=[a-zA-Z0-9_`])",
            "",
            post_processed,
            flags=re.IGNORECASE,
        )

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
            r"\{\{\s*(?:source|ref)\s*\(.*?\)\s*\}\}\s*\.\s*(?=[a-zA-Z0-9_`]|(?:\{\{))",
            "",
            post_processed,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Clean config header parameters
        original_header = headers.get(rel_path, "")
        cleaned_header = transform_config_block(original_header, rel_path)

        # Apply Jinja and SQL edge cases sanitization
        post_processed_sanitized = sanitize_jinja_and_sql_edge_cases(post_processed)

        # Apply Unimplemented opcodes sanitization (e.g. JsonFieldJsonNumericAsJsonOpcode on col['key'])
        post_processed_sanitized = sanitize_unimplemented_opcodes(
            post_processed_sanitized, struct_columns
        )

        # Apply JSON extraction sanitization
        post_processed_sanitized = sanitize_json_extractions(post_processed_sanitized)

        # Apply Struct access sanitization
        post_processed_sanitized = sanitize_struct_access(
            post_processed_sanitized, struct_columns
        )

        # Apply Array cast sanitization if configured
        if array_cast_mode:
            post_processed_sanitized = sanitize_array_casts(
                post_processed_sanitized, array_cast_mode
            )

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
        if abs_output:
            dirs[:] = [
                d
                for d in dirs
                if os.path.abspath(os.path.join(root, d)) != abs_output
                and d
                not in (
                    ".git",
                    "target",
                    "dbt_packages",
                    "logs",
                    "venv",
                    ".venv",
                    "migration_plan",
                )
                and not d.startswith(".")
            ]
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
