# Copyright 2026 Google. This software is provided as-is, without warranty or
# representation for any use or purpose. Your use of it is subject to your
# agreement with Google.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///

import argparse
import re

from dbt_translator import run_bulk_translation


def main():
    parser = argparse.ArgumentParser(
        description="Bulk translate Snowflake dbt models to BigQuery using BQMS."
    )
    parser.add_argument(
        "--input", required=True, help="Input directory containing Snowflake SQL files"
    )
    parser.add_argument(
        "--output", required=True, help="Output directory for BigQuery SQL files"
    )
    parser.add_argument("--bucket", required=True, help="GCS Bucket for staging files")
    parser.add_argument(
        "--location", default="us", help="GCP Region for BQMS (default: us)"
    )
    parser.add_argument(
        "--metadata", help="Local path to metadata ZIP (deprecated in BQMS v2)"
    )
    parser.add_argument(
        "--metadata-dataset",
        help="BigQuery dataset containing migration assessment metadata",
    )
    parser.add_argument(
        "--default-database", help="Default Snowflake database for object resolution"
    )
    parser.add_argument(
        "--schema-search-path",
        help="Comma-separated list of default schemas for object resolution",
    )

    args = parser.parse_args()

    bucket_clean = re.sub(r"^gs://", "", args.bucket)

    schema_search_list = None
    if args.schema_search_path:
        schema_search_list = [s.strip() for s in args.schema_search_path.split(",")]

    msg = run_bulk_translation(
        args.input,
        args.output,
        bucket_clean,
        args.location,
        metadata_path=args.metadata,
        metadata_dataset=args.metadata_dataset,
        default_database=args.default_database,
        schema_search_path=schema_search_list,
    )
    print(msg)


if __name__ == "__main__":
    main()
