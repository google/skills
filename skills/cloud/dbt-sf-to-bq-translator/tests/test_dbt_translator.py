# Copyright 2026 Google. This software is provided as-is, without warranty or
# representation for any use or purpose. Your use of it is subject to your
# agreement with Google.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

# Add scripts to path
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../scripts",
        )
    ),
)

from dbt_translator import (
    audit_macros,
    resolve_namespaces,
    run_bulk_translation,
    sanitize_jinja_and_sql_edge_cases,
    sanitize_json_extractions,
    transform_config_block,
)


class TestDbtTranslator(unittest.TestCase):
    # --- 1. Macro and Function Incompatibility ---
    def test_audit_macros(self):
        sql = """
        select
            {{ dbt_utils.safe_cast('my_col', 'type') }} as col1,
            {{ custom_snowflake_macro('arg') }} as col2,
            {{ ref('my_model') }} as col3
        """
        # We expect a warning for custom_snowflake_macro but not for standard ref/source
        warnings, _ = audit_macros(sql)
        self.assertTrue(any("custom_snowflake_macro" in w for w in warnings))
        self.assertFalse(any("ref" in w for w in warnings))

    # --- 2. Incremental Model Logic & Nested Dateadd ---
    def test_sanitize_dateadd_nested_in_jinja(self):
        sql = """
        {% if is_incremental() %}
          where event_time > dateadd(day, -3, current_date)
          and event_date > (select max(event_date) from {{ this }})
        {% endif %}
        """
        # The dateadd inside the {% if %} block should be translated
        # Also double check that {{ this }} is preserved
        sanitized = sanitize_jinja_and_sql_edge_cases(sql)
        self.assertIn("DATE_ADD(current_date, INTERVAL -3 DAY)", sanitized)
        self.assertIn("{{ this }}", sanitized)

    def test_sanitize_dateadd_complex_expr(self):
        # Test dateadd with complex expressions/nesting
        sql = "select dateadd(day, -1 * var_days, to_date(event_time))"
        # Since it has arithmetic/nesting, it should balance parentheses correctly
        sanitized = sanitize_jinja_and_sql_edge_cases(sql)
        self.assertIn(
            "DATE_ADD(to_date(event_time), INTERVAL -1 * var_days DAY)", sanitized
        )

    # --- 3. Schema/Database Qualifiers (Namespace Resolution) ---
    def test_namespace_resolution(self):
        # We simulate a project with models: 'customers', 'orders'
        known_models = {"customers", "orders"}
        known_sources = {"stripe": {"payments"}, "jaffle_shop": {"customers"}}

        # Scenario A: hardcoded db.schema.table to ref (table matches known model)
        sql_a = "select * from analytics.dw.customers"
        resolved_a = resolve_namespaces(sql_a, known_models, known_sources)
        self.assertEqual(resolved_a, "select * from {{ ref('customers') }}")

        # Scenario B: hardcoded db.schema.table to source
        sql_b = "select * from raw.stripe.payments"
        resolved_b = resolve_namespaces(sql_b, known_models, known_sources)
        self.assertEqual(resolved_b, "select * from {{ source('stripe', 'payments') }}")

        # Scenario C: 2-part name (schema.table)
        sql_c = "select * from stripe.payments"
        resolved_c = resolve_namespaces(sql_c, known_models, known_sources)
        self.assertEqual(resolved_c, "select * from {{ source('stripe', 'payments') }}")

        # Scenario D: unknown table maps to default source (schema, table)
        sql_d = "select * from raw.unknown_schema.unknown_table"
        resolved_d = resolve_namespaces(sql_d, known_models, known_sources)
        self.assertEqual(
            resolved_d, "select * from {{ source('unknown_schema', 'unknown_table') }}"
        )

    # --- 4. Configuration Block Sanitization ---
    def test_transform_config_block(self):
        config_block = """{{ config(
            materialized='incremental',
            unique_key='id',
            cluster_by=['category', 'status'],
            copy_grants=true,
            transient=false,
            pre_hook="alter iceberg table my_table refresh;",
            post_hook=["alter table foo unset secure;", "vacuum foo;"]
        ) }}"""

        # Expected outputs:
        # - transient and copy_grants removed
        # - pre_hook stripped because it's invalid iceberg refresh
        # - post_hook has "unset secure" stripped, but keeps "vacuum foo;"
        # - cluster_by mapped
        transformed = transform_config_block(config_block)

        self.assertNotIn("copy_grants", transformed)
        self.assertNotIn("transient", transformed)
        self.assertNotIn("alter iceberg table", transformed)
        self.assertNotIn("unset secure", transformed)
        self.assertIn("vacuum foo", transformed)
        self.assertIn("cluster_by", transformed)

    def test_transform_config_block_nested_jinja(self):
        config_block = """{{ config(
            pre_hook=["DELETE FROM {{ this }} WHERE primary_key in (select primary_key from {{ ref('my_ref') }})"],
            materialized='incremental',
            transient=false
        ) }}"""
        transformed = transform_config_block(config_block)
        self.assertNotIn("transient", transformed)
        self.assertIn("DELETE FROM {{ this }}", transformed)
        self.assertIn("{{ ref('my_ref') }}", transformed)
        self.assertIn("materialized='incremental'", transformed)

    # --- 5. Fix existing interval/cast sanitization ---
    def test_sanitize_dateadd(self):
        sql = "select dateadd(day, -3, current_date) as three_days_ago"
        expected = "select DATE_ADD(current_date, INTERVAL -3 DAY) as three_days_ago"
        self.assertEqual(sanitize_jinja_and_sql_edge_cases(sql), expected)

    def test_sanitize_cast_suffixes(self):
        sql = "select event_date::date, event_time::timestamp, event_date::DATE from my_table"
        expected = "select CAST(event_date AS DATE), CAST(event_time AS TIMESTAMP), CAST(event_date AS DATE) from my_table"
        self.assertEqual(sanitize_jinja_and_sql_edge_cases(sql), expected)

    def test_sanitize_intervals(self):
        sql = "select base_date - interval '5 month', base_date + interval '1 day'"
        expected = "select DATE_SUB(base_date, INTERVAL 5 MONTH), DATE_ADD(base_date, INTERVAL 1 DAY)"
        self.assertEqual(sanitize_jinja_and_sql_edge_cases(sql), expected)

        # Test complex nested intervals with balanced parentheses
        complex_sql = "LAST_DAY(DATEADD(DAY, -1, CURRENT_DATE::DATE) - INTERVAL '5 MONTH') + INTERVAL '1 DAY'"
        complex_expected = "DATE_ADD(LAST_DAY(DATE_SUB(DATE_ADD(CAST(CURRENT_DATE AS DATE), INTERVAL -1 DAY), INTERVAL 5 MONTH)), INTERVAL 1 DAY)"
        self.assertEqual(
            sanitize_jinja_and_sql_edge_cases(complex_sql), complex_expected
        )

    def test_sanitize_unknown_type_comments(self):
        sql = "select CAST(/* expression of unknown or erroneous type */ CREATED_AT as DATE) as col"
        expected = "select CAST(CREATED_AT as DATE) as col"
        self.assertEqual(sanitize_jinja_and_sql_edge_cases(sql), expected)

    # --- 6. Discover DBT Resources ---
    def test_discover_dbt_resources(self):
        import shutil
        import tempfile

        temp_dir = tempfile.mkdtemp()
        try:
            model_file = os.path.join(temp_dir, "my_model.sql")
            with open(model_file, "w") as f:
                f.write("select 1;")

            sources_file = os.path.join(temp_dir, "sources.yml")
            with open(sources_file, "w") as f:
                f.write("""
version: 2
sources:
  - name: stripe
    tables:
      - name: payments
      - name: charges
""")

            from dbt_translator import discover_dbt_resources

            known_models, known_sources = discover_dbt_resources(temp_dir)

            self.assertIn("my_model", known_models)
            self.assertIn("stripe", known_sources)
            self.assertIn("payments", known_sources["stripe"])
            self.assertIn("charges", known_sources["stripe"])

        finally:
            shutil.rmtree(temp_dir)

    # --- 7. JSON Extraction Sanitization ---
    def test_sanitize_json_extractions(self):
        sql = """
        SELECT
            json_query(json_query(SOURCE_DATA.VALUE, '$.commonDataModel'), '$.bucket') AS CREATETIME,
            substr(string(json_query(json_query(SOURCE_DATA.VALUE, '$.commonDataModel'), '$.site')), 1, 16777216) AS SITE,
            CAST(lax_float64(json_query(json_query(SOURCE_DATA.VALUE, '$.commonDataModel'), '$.vn_ton')) as BIGNUMERIC) AS VN_TON,
            lax_bool(json_query(SOURCE_DATA.VALUE, '$.is_active')) AS IS_ACTIVE
        """
        expected = """
        SELECT
            JSON_EXTRACT_SCALAR(SOURCE_DATA.VALUE, '$.commonDataModel.bucket') AS CREATETIME,
            CAST(JSON_EXTRACT_SCALAR(SOURCE_DATA.VALUE, '$.commonDataModel.site') AS STRING) AS SITE,
            CAST(JSON_EXTRACT_SCALAR(SOURCE_DATA.VALUE, '$.commonDataModel.vn_ton') AS NUMERIC) AS VN_TON,
            CAST(JSON_EXTRACT_SCALAR(SOURCE_DATA.VALUE, '$.is_active') AS BOOL) AS IS_ACTIVE
        """
        self.assertEqual(
            [s.strip() for s in sanitize_json_extractions(sql).split()],
            [s.strip() for s in expected.split()],
        )

    # --- 8. Bulk Translation YAML Copying ---
    @patch("subprocess.run")
    def test_run_bulk_translation_yaml_copy(self, mock_run):
        # Setup dummy process return code
        mock_process = Mock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        input_dir = tempfile.mkdtemp()
        output_dir = tempfile.mkdtemp()
        try:
            # Create a dummy SQL file
            sql_file = os.path.join(input_dir, "model1.sql")
            with open(sql_file, "w") as f:
                f.write("select 1;")

            # Create a dummy YAML file
            yaml_file = os.path.join(input_dir, "schema.yml")
            with open(yaml_file, "w") as f:
                f.write("version: 2")

            # Run translation
            run_bulk_translation(input_dir, output_dir, "dummy-bucket", "us")

            # Check if schema.yml was copied
            copied_yaml = os.path.join(output_dir, "schema.yml")
            self.assertTrue(os.path.exists(copied_yaml))
            with open(copied_yaml, "r") as f:
                content = f.read()
            self.assertEqual(content, "version: 2")
        finally:
            shutil.rmtree(input_dir)
            shutil.rmtree(output_dir)

    # --- 9. Metadata Pre-processing ---
    def test_preprocess_metadata(self):
        from dbt_translator import preprocess_metadata

        temp_in = tempfile.mkdtemp()
        temp_out = tempfile.mkdtemp()
        try:
            # Create a mock columns.csv
            columns_csv = os.path.join(temp_in, "columns.csv")
            with open(columns_csv, "w", encoding="utf-8") as f:
                f.write("TABLE_CATALOG,TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,DATA_TYPE\n")
                f.write("RAW,STRIPE,PAYMENTS,ID,NUMBER\n")
                f.write("RAW,STRIPE,PAYMENTS,AMOUNT,NUMBER\n")
                f.write("RAW,JAFFLE_SHOP,CUSTOMERS,ID,NUMBER\n")
                f.write("RAW,OTHER_SCHEMA,UNKNOWN_TABLE,COL,VARCHAR\n")

            # Create a mock tables.csv
            tables_csv = os.path.join(temp_in, "tables.csv")
            with open(tables_csv, "w", encoding="utf-8") as f:
                f.write("TABLE_CATALOG,TABLE_SCHEMA,TABLE_NAME,TABLE_TYPE\n")
                f.write("RAW,STRIPE,PAYMENTS,BASE TABLE\n")
                f.write("RAW,JAFFLE_SHOP,CUSTOMERS,BASE TABLE\n")
                f.write("RAW,OTHER_SCHEMA,UNKNOWN_TABLE,BASE TABLE\n")

            known_models = {"customers"}
            known_sources = {"stripe": {"payments"}}

            res = preprocess_metadata(temp_in, temp_out, known_models, known_sources)
            self.assertTrue(res)

            # Read processed columns.csv
            proc_columns = os.path.join(temp_out, "columns.csv")
            self.assertTrue(os.path.exists(proc_columns))
            with open(proc_columns, "r", encoding="utf-8") as f:
                lines = f.readlines()

            self.assertEqual(
                lines[0].strip(),
                "TABLE_CATALOG,TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,DATA_TYPE",
            )
            self.assertEqual(
                lines[1].strip(), ",,_DBT_SOURCE_stripe_DBTSEP_payments_,ID,NUMBER"
            )
            self.assertEqual(
                lines[2].strip(), ",,_DBT_SOURCE_stripe_DBTSEP_payments_,AMOUNT,NUMBER"
            )
            self.assertEqual(lines[3].strip(), ",,_DBT_REF_customers_,ID,NUMBER")
            self.assertEqual(
                lines[4].strip(), "RAW,OTHER_SCHEMA,UNKNOWN_TABLE,COL,VARCHAR"
            )

            # Read processed tables.csv
            proc_tables = os.path.join(temp_out, "tables.csv")
            self.assertTrue(os.path.exists(proc_tables))
            with open(proc_tables, "r", encoding="utf-8") as f:
                table_lines = f.readlines()
            self.assertEqual(
                table_lines[1].strip(),
                ",,_DBT_SOURCE_stripe_DBTSEP_payments_,BASE TABLE",
            )
            self.assertEqual(table_lines[2].strip(), ",,_DBT_REF_customers_,BASE TABLE")
            self.assertEqual(
                table_lines[3].strip(), "RAW,OTHER_SCHEMA,UNKNOWN_TABLE,BASE TABLE"
            )

        finally:
            shutil.rmtree(temp_in)
            shutil.rmtree(temp_out)

    # --- 10. Metadata Pre-processing (Custom headers & Missing Schema) ---
    def test_preprocess_metadata_custom_headers(self):
        from dbt_translator import preprocess_metadata

        temp_in = tempfile.mkdtemp()
        temp_out = tempfile.mkdtemp()
        try:
            # Create a mock columns.csv using the demo structure (no schema/catalog)
            columns_csv = os.path.join(temp_in, "columns.csv")
            with open(columns_csv, "w", encoding="utf-8") as f:
                f.write(
                    "TableName,ColumnName,DataType,NumericPrecision,NumericScale,OrdinalPosition\n"
                )
                f.write("payments,id,NUMBER,,,1\n")
                f.write("customers,id,NUMBER,,,1\n")
                f.write("unknown,col,VARCHAR,,,1\n")

            known_models = {"customers"}
            # stripe is the only source containing table 'payments'
            known_sources = {"stripe": {"payments"}}

            res = preprocess_metadata(temp_in, temp_out, known_models, known_sources)
            self.assertTrue(res)

            # Read processed columns.csv
            proc_columns = os.path.join(temp_out, "columns.csv")
            self.assertTrue(os.path.exists(proc_columns))
            with open(proc_columns, "r", encoding="utf-8") as f:
                lines = f.readlines()

            self.assertEqual(
                lines[0].strip(),
                "TableName,ColumnName,DataType,NumericPrecision,NumericScale,OrdinalPosition",
            )
            # payments matches 'stripe' as a unique source containing 'payments'
            self.assertEqual(
                lines[1].strip(), "_DBT_SOURCE_stripe_DBTSEP_payments_,id,NUMBER,,,1"
            )
            # customers matches known models
            self.assertEqual(lines[2].strip(), "_DBT_REF_customers_,id,NUMBER,,,1")
            # unknown remains unchanged
            self.assertEqual(lines[3].strip(), "unknown,col,VARCHAR,,,1")

        finally:
            shutil.rmtree(temp_in)
            shutil.rmtree(temp_out)


if __name__ == "__main__":
    unittest.main()
