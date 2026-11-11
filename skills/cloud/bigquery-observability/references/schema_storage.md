# BigQuery Storage & Catalog INFORMATION_SCHEMA Reference

A comprehensive dictionary, column definition guide, and physical unit
specification for all Storage, Table, Column, Partition, Snapshot, and Dataset
views in BigQuery `INFORMATION_SCHEMA`.

## Table of Contents

-   [View Scoping & Qualification Matrix](#view-scoping-qualification-matrix)
    (Lines 47-62)
-   [3. Storage Footprint, Partitions & Table Metadata Views](#3-storage-footprint-partitions-table-metadata-views)
    (Lines 63-434)
    -   [`INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_FOLDER`)](#information_schematable_storage_usage_timeline-and-_by_project-_by_organization-_by_folder)
        (Lines 65-114)
    -   [`INFORMATION_SCHEMA.TABLE_STORAGE` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_FOLDER`)](#information_schematable_storage-and-_by_project-_by_organization-_by_folder)
        (Lines 115-166)
    -   [`INFORMATION_SCHEMA.TABLES` (and `_BY_PROJECT`)](#information_schematables-and-_by_project)
        (Lines 167-213)
    -   [`INFORMATION_SCHEMA.TABLE_OPTIONS`](#information_schematable_options)
        (Lines 214-241)
    -   [`INFORMATION_SCHEMA.TABLE_SNAPSHOTS`](#information_schematable_snapshots)
        (Lines 242-268)
    -   [`INFORMATION_SCHEMA.PARTITIONS`](#information_schemapartitions) (Lines
        269-300)
    -   [`INFORMATION_SCHEMA.COLUMNS`](#information_schemacolumns) (Lines
        301-345)
    -   [`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`](#information_schemacolumn_field_paths)
        (Lines 346-378)
    -   [`INFORMATION_SCHEMA.VIEWS`](#information_schemaviews) (Lines 379-405)
    -   [`INFORMATION_SCHEMA.MATERIALIZED_VIEWS`](#information_schemamaterialized_views)
        (Lines 406-434)
-   [4. Datasets, Replication & Sharing Views](#4-datasets-replication-sharing-views)
    (Lines 435-619)
    -   [`INFORMATION_SCHEMA.SCHEMATA`](#information_schemaschemata) (Lines
        437-466)
    -   [`INFORMATION_SCHEMA.SCHEMATA_OPTIONS`](#information_schemaschemata_options)
        (Lines 467-492)
    -   [`INFORMATION_SCHEMA.SCHEMATA_REPLICAS` (and `_BY_FAILOVER_RESERVATION`)](#information_schemaschemata_replicas-and-_by_failover_reservation)
        (Lines 493-527)
    -   [`INFORMATION_SCHEMA.SCHEMATA_LINKS` & `SHARED_DATASET_USAGE`](#information_schemaschemata_links-shared_dataset_usage)
        (Lines 528-559)
    -   [`INFORMATION_SCHEMA.TABLE_CONSTRAINTS`](#information_schematable_constraints)
        (Lines 560-589)
    -   [`INFORMATION_SCHEMA.KEY_COLUMN_USAGE`](#information_schemakey_column_usage)
        (Lines 590-619)

## View Scoping & Qualification Matrix

Storage, table, and dataset views fall into **Dual-Scoped**, **Region-Only**,
and **Dataset-Only** qualification categories:

<!-- mdformat off -->
| View Family | INFORMATION_SCHEMA View(s) | Qualification Scope | Syntax Pattern & Scoping Rules |
| :--- | :--- | :--- | :--- |
| **Storage Footprints** | `TABLE_STORAGE*` (`_BY_PROJECT`, `_BY_FOLDER`, `_BY_ORGANIZATION`), `TABLE_STORAGE_USAGE_TIMELINE*` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.TABLE_STORAGE*``<br>• Storage billing models (Logical vs Physical) and daily usage integrals (`MiB * seconds`). |
| **Tables & Metadata** | `TABLES`, `TABLE_OPTIONS`, `COLUMNS`, `COLUMN_FIELD_PATHS`, `VIEWS`, `MATERIALIZED_VIEWS` | **Dual-Scoped** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view_name}``<br>OR<br>`` `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.{view_name}`` |
| **Table Partitions** | `PARTITIONS` | **Dataset-Only** | `` `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.PARTITIONS``<br>• Partition boundaries and storage tiers. Must be qualified with `{dataset_id}`. |
| **Table Snapshots** | `TABLE_SNAPSHOTS` | **Dual-Scoped** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.TABLE_SNAPSHOTS``<br>OR<br>`` `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.TABLE_SNAPSHOTS`` |
| **Datasets & Replication** | `SCHEMATA*`, `SCHEMATA_OPTIONS`, `SCHEMATA_REPLICAS*`, `SCHEMATA_LINKS`, `SHARED_DATASET_USAGE` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.SCHEMATA*``<br>• Dataset catalog, cross-region replication, and failover status. |
| **Table Constraints** | `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE` | **Dual-Scoped** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view_name}``<br>OR<br>`` `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.{view_name}`` |
<!-- mdformat on -->

## 3. Storage Footprint, Partitions & Table Metadata Views

### `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_FOLDER`)

#### High-Level Description

Daily historical storage usage time integral. This view is the definitive source
of truth for Cloud Billing invoice storage charges across Active vs. Long-term
and Logical vs. Physical billing tiers.

#### Required IAM Permissions & Predefined Roles

*   **Project-Level (Least Privilege):** Requires `bigquery.tables.get` and
    `bigquery.tables.list` on the project. Granted by **BigQuery Metadata
    Viewer** (`roles/bigquery.metadataViewer`), **BigQuery Data Viewer**
    (`roles/bigquery.dataViewer`), **BigQuery Data Editor**
    (`roles/bigquery.dataEditor`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_FOLDER`:** Requires `bigquery.tables.get` and `bigquery.tables.list`
    on the parent folder.
*   **`_BY_ORGANIZATION`:** Requires `bigquery.tables.get` and
    `bigquery.tables.list` on the organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `billable_active_logical_usage` | `INT64` | **MiB-seconds** | Active logical usage time integral (<90 days unmutated). |
| `billable_active_physical_usage` | `INT64` | **MiB-seconds** | Active physical usage time integral. |
| `billable_long_term_logical_usage` | `INT64` | **MiB-seconds** | Long-term logical usage time integral (>=90 days unmutated). |
| `billable_long_term_physical_usage` | `INT64` | **MiB-seconds** | Long-term physical usage time integral. |
| `billable_total_logical_usage` | `INT64` | **MiB-seconds** | Total logical usage time integral. |
| `billable_total_physical_usage` | `INT64` | **MiB-seconds** | Total physical compressed usage time integral. |
| `folder_numbers` | `ARRAY<INT64>` | Array | Folder hierarchy IDs containing the project (only in `_BY_FOLDER`). |
| `project_id` | `STRING` | Project ID | Project containing the table. |
| `project_number` | `INT64` | Numeric ID | Numeric project ID. |
| `table_catalog` | `STRING` | Project ID | Table catalog / project name. |
| `table_name` | `STRING` | Table ID | Table identifier. |
| `table_schema` | `STRING` | Dataset ID | Dataset containing the table. |
| `usage_date` | `DATE` | **PST Date** | Daily snapshot partition aligned strictly to US Pacific Time (`PST8PDT`). |
<!-- mdformat on -->

> [!CAUTION] **Dimensional Unit Invariant:** `TABLE_STORAGE_USAGE_TIMELINE`
> stores storage continuously integrated over time in **MiB-seconds**. To
> compute daily average billable GiB, always divide by 86,400 (seconds in a day)
> and then by 1,024: `(usage / 86400) / 1024`.

> [!NOTE] **Access Requirements:** Accessing `TABLE_STORAGE_USAGE_TIMELINE`
> requires `bigquery.tables.get` and `bigquery.tables.list` IAM permissions
> (granted by `roles/bigquery.metadataViewer`, `roles/bigquery.dataViewer`,
> `roles/bigquery.dataEditor`, or `roles/bigquery.admin`) on the project. Does
> not require `enable_info_schema_storage` opt-in.

### `INFORMATION_SCHEMA.TABLE_STORAGE` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_FOLDER`)

#### High-Level Description

Real-time point-in-time snapshot of table storage sizes, active vs. long-term
uncompressed bytes, compressed physical bytes, Time Travel retention overhead,
and Fail-Safe bytes. Requires storage metadata opt-in or Resource Admin IAM
roles for new projects.

#### Required IAM Permissions & Predefined Roles

*   **Project-Level (Least Privilege):** Requires `bigquery.tables.get` and
    `bigquery.tables.list` on the project. Granted by **BigQuery Metadata
    Viewer** (`roles/bigquery.metadataViewer`), **BigQuery Data Viewer**
    (`roles/bigquery.dataViewer`), **BigQuery Data Editor**
    (`roles/bigquery.dataEditor`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_FOLDER`:** Requires `bigquery.tables.get` and `bigquery.tables.list`
    on the parent folder.
*   **`_BY_ORGANIZATION`:** Requires `bigquery.tables.get` and
    `bigquery.tables.list` on the organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description & Conversion Formula |
| :--- | :--- | :--- | :--- |
| `active_logical_bytes` | `INT64` | **Bytes** | Uncompressed active logical bytes (<90 days unmutated). **GiB:** `active_logical_bytes / POWER(1024, 3)`. |
| `active_physical_bytes` | `INT64` | **Bytes** | Compressed active physical bytes (includes active baseline + time travel). **GiB:** `active_physical_bytes / POWER(1024, 3)`. |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Table creation timestamp. |
| `current_physical_bytes` | `INT64` | **Bytes** | Baseline physical bytes before Time Travel / Fail-Safe additions. |
| `deleted` | `BOOLEAN` | Boolean | `true` if the table has been deleted and is currently retained in Time Travel or Fail-Safe. |
| `fail_safe_physical_bytes` | `INT64` | **Bytes** | Physical storage consumed by 7-day non-configurable Fail-Safe disaster recovery. Billed at active physical rates under Physical model; free under Logical model. |
| `folder_numbers` | `ARRAY<INT64>` | Array | Folder hierarchy IDs containing the project (only populated in `_BY_FOLDER`). |
| `last_metadata_index_refresh_time` | `TIMESTAMP` | UTC Timestamp | Last metadata indexing refresh timestamp. |
| `long_term_logical_bytes` | `INT64` | **Bytes** | Uncompressed long-term logical bytes (>=90 days unmutated). **GiB:** `long_term_logical_bytes / POWER(1024, 3)`. |
| `long_term_physical_bytes` | `INT64` | **Bytes** | Compressed long-term physical bytes (>=90 days unmutated). **GiB:** `long_term_physical_bytes / POWER(1024, 3)`. |
| `managed_table_type` | `STRING` | Enum | `'NATIVE'` or `'ICEBERG'`. |
| `project_id` | `STRING` | Project ID | Project containing table. |
| `project_number` | `INT64` | Numeric ID | Numeric project ID. |
| `storage_last_modified_time` | `TIMESTAMP` | UTC Timestamp | Last storage mutation timestamp. |
| `table_catalog` | `STRING` | Project ID | Table catalog / project name. |
| `table_deletion_reason` | `STRING` | Enum / Reason | Reason for deletion: `'TABLE EXPIRATION'`, `'DATASET DELETION'`, `'USER_DELETED'`. |
| `table_deletion_time` | `TIMESTAMP` | UTC Timestamp | Exact timestamp when the table was deleted. |
| `table_name` | `STRING` | Table ID | Table name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
| `time_travel_physical_bytes` | `INT64` | **Bytes** | Physical storage consumed by Time Travel retention (1 to 7 days). Billed at active physical rates under Physical model; free under Logical model. |
| `total_logical_bytes` | `INT64` | **Bytes** | Sum of `active_logical_bytes` + `long_term_logical_bytes`. |
| `total_partitions` | `INT64` | Count | Number of partitions. |
| `total_physical_bytes` | `INT64` | **Bytes** | Sum of `active_physical_bytes` + `long_term_physical_bytes`. |
| `total_rows` | `INT64` | Count | Current row count. |
| `table_type` | `STRING` | Enum | `'BASE TABLE'`, `'CLONE'`, `'SNAPSHOT'`, `'VIEW'`, `'MATERIALIZED VIEW'`. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.TABLES` (and `_BY_PROJECT`)

#### High-Level Description

Lists all tables, views, clones, snapshots, and BigLake tables in the dataset or
project, along with creation times, DDL definitions, and replication statuses.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` (and
    `bigquery.routines.get`/`list` for routines) on the target dataset or
    project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), **BigQuery Data Editor**
    (`roles/bigquery.dataEditor`), **BigQuery Data Owner**
    (`roles/bigquery.dataOwner`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `base_table_catalog` | `STRING` | Project ID | For table snapshots and clones, the base table project ID. |
| `base_table_name` | `STRING` | Table ID | For table snapshots and clones, the base table name. |
| `base_table_schema` | `STRING` | Dataset ID | For table snapshots and clones, the base table dataset ID. |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when the table was created. |
| `ddl` | `STRING` | SQL String | Complete GoogleSQL DDL statement to reproduce the table. |
| `default_collation_name` | `STRING` | String | Default string collation specification. |
| `is_change_history_enabled` | `STRING` | `'YES'` / `'NO'` | Indicates whether BigQuery change data capture (CDC) history is retained. |
| `is_fine_grained_mutations_enabled` | `STRING` | `'YES'` / `'NO'` | Indicates whether fine-grained mutations are enabled on the table. |
| `is_insertable_into` | `STRING` | `'YES'` / `'NO'` | Indicates whether the table supports DML `INSERT` operations. |
| `is_typed` | `STRING` | `'NO'` | Always `'NO'` for BigQuery tables. |
| `managed_table_type` | `STRING` | Enum | `'NATIVE'` or `'ICEBERG'` (for BigLake Managed Tables). |
| `replica_source_catalog` | `STRING` | Project ID | For read-only table replicas, the source table project ID. |
| `replica_source_name` | `STRING` | Table ID | For read-only table replicas, the source table name. |
| `replica_source_schema` | `STRING` | Dataset ID | For read-only table replicas, the source dataset ID. |
| `replication_error` | `RECORD` | Error Struct | Replication error details if table replication fails (`reason`, `location`, `message`). |
| `replication_status` | `STRING` | Enum | Table replication status (`'ACTIVE'`, `'FAILED'`, `'OUT_OF_SYNC'`). |
| `snapshot_time_ms` | `TIMESTAMP` | UTC Timestamp | For snapshots/clones, the exact base table snapshot point in time. |
| `sync_status` | `RECORD` | Sync Struct | Metadata sync status for Apache Iceberg and BigLake tables (`status`, `last_sync_time`, `message`). |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_name` | `STRING` | Table ID | Table name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
| `table_type` | `STRING` | Enum | `'BASE TABLE'`, `'VIEW'`, `'MATERIALIZED VIEW'`, `'EXTERNAL'`, `'SNAPSHOT'`, `'CLONE'`. |
| `upsert_stream_apply_watermark` | `TIMESTAMP` | UTC Timestamp | CDC merge watermark timestamp for BigQuery Storage Write API UPSERT streams. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.TABLE_OPTIONS`

#### High-Level Description

Lists all table-level configuration options specified in the DDL `OPTIONS(...)`
clause, such as partition expiration, KMS encryption keys, and mandatory
partition filter requirements.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Key Values | Description |
| :--- | :--- | :--- | :--- |
| `option_name` | `STRING` | `'partition_expiration_days'`, `'require_partition_filter'`, `'kms_key_name'`, `'friendly_name'`, `'description'` | Table configuration parameter. |
| `option_type` | `STRING` | SQL Type | GoogleSQL type of the option. |
| `option_value` | `STRING` | String | Active option value. |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_name` | `STRING` | Table ID | Table name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.TABLE_SNAPSHOTS`

#### High-Level Description

Detailed metadata for BigQuery Table Snapshots, tracking base table lineages,
snapshot creation timestamps, and snapshot retention.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.list` on the target dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `base_table_catalog` | `STRING` | Project ID | Project ID of the base table. |
| `base_table_name` | `STRING` | Table ID | Base table name. |
| `base_table_schema` | `STRING` | Dataset ID | Dataset ID of the base table. |
| `snapshot_time` | `TIMESTAMP` | UTC Timestamp | Base table snapshot point-in-time timestamp. |
| `table_catalog` | `STRING` | Project ID | Project containing the snapshot. |
| `table_name` | `STRING` | Table ID | Snapshot table name. |
| `table_schema` | `STRING` | Dataset ID | Dataset containing the snapshot. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.PARTITIONS`

#### High-Level Description

Provides partition-level metadata for partitioned tables, including row counts,
uncompressed logical bytes, billable bytes, mutation timestamps, and storage
tiers.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.getData` on the table or dataset. *(Note: Unlike
    metadata views, PARTITIONS requires table data access).*
*   **Predefined Roles:** **BigQuery Data Viewer**
    (`roles/bigquery.dataViewer`), **BigQuery Data Editor**
    (`roles/bigquery.dataEditor`), **BigQuery Data Owner**
    (`roles/bigquery.dataOwner`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `last_modified_time` | `TIMESTAMP` | UTC Timestamp | Last write/mutation timestamp. Partitions unmutated for >= 90 days drop to discounted Long-Term rates. |
| `partition_id` | `STRING` | Partition Key | Partition key string (e.g. `'20260815'`, `'__NULL__'`). |
| `storage_tier` | `STRING` | Enum | `'ACTIVE'` (<90 days unmutated) or `'LONG_TERM'` (>= 90 days unmutated). |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_name` | `STRING` | Table ID | Table identifier. |
| `table_schema` | `STRING` | Dataset ID | Dataset identifier. |
| `total_billable_bytes` | `INT64` | **Bytes** | Billable bytes for partition. |
| `total_logical_bytes` | `INT64` | **Bytes** | Uncompressed logical size of partition. |
| `total_rows` | `INT64` | Count | Number of rows in partition. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.COLUMNS`

#### High-Level Description

Defines schema column specifications, GoogleSQL data types, ordinal ordering,
nullability constraints, partitioning columns, clustering positions, policy
tags, and data masking policies.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `async_generation_status` | `RECORD` | Status Struct | For stored generated columns, the status of background asynchronous population (`status`, `message`, `end_time`). |
| `clustering_ordinal_position` | `INT64` | Position | 1-indexed position in the table's clustering key specification. |
| `collation_name` | `STRING` | Collation | Active string collation rule. |
| `column_default` | `STRING` | SQL Literal | Default value expression. |
| `column_name` | `STRING` | Field Name | Top-level column name. |
| `data_governance_tags` | `RECORD` | Tags Struct | IAM and Data Governance tags attached to column. |
| `data_policies` | `RECORD` | Policy Struct | Data policy masking definitions applied to column. |
| `data_type` | `STRING` | SQL Type | GoogleSQL type (`'INT64'`, `'ARRAY<STRING>'`, `'STRUCT<...>'`). |
| `generation_expression` | `STRING` | SQL Expression | GoogleSQL expression used to calculate generated column values. |
| `is_generated` | `STRING` | `'ALWAYS'` / `'NEVER'` | Indicates whether the column is a generated column. |
| `is_hidden` | `STRING` | `'YES'` / `'NO'` | `'YES'` if column is hidden from `SELECT *` expansion. |
| `is_identity` | `STRING` | `'YES'` / `'NO'` | Indicates whether the column is an auto-generated sequence identity. |
| `is_nullable` | `STRING` | `'YES'` / `'NO'` | Nullability constraint. |
| `is_partitioning_column` | `STRING` | `'YES'` / `'NO'` | `'YES'` if this column partitions the table. |
| `is_stored` | `STRING` | `'YES'` / `'NO'` | Indicates whether a generated column is stored on disk or evaluated at query time. |
| `is_system_defined` | `STRING` | `'YES'` / `'NO'` | `'YES'` if the column is created and managed automatically by BigQuery. |
| `is_updatable` | `STRING` | `'YES'` / `'NO'` | Always `'YES'` for BigQuery tables. |
| `ordinal_position` | `INT64` | Position | 1-indexed column ordinal position. |
| `policy_tags` | `STRING` | Resource Path | Cloud Data Catalog policy tag resource paths for Column-Level Security (CLS). |
| `rounding_mode` | `STRING` | Enum | Rounding mode for `NUMERIC` / `BIGNUMERIC` columns. |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_name` | `STRING` | Table ID | Table name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`

#### High-Level Description

Defines nested field path specifications for `RECORD` and `STRUCT` columns in
BigQuery tables.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
| `table_name` | `STRING` | Table ID | Table name. |
| `column_name` | `STRING` | Field Name | Top-level column name. |
| `field_path` | `STRING` | Dot Path | Dot-delimited nested leaf path. |
| `data_type` | `STRING` | SQL Type | GoogleSQL type of the nested field. |
| `description` | `STRING` | Text | Field description. |
| `collation_name` | `STRING` | Collation | Collation rule. |
| `rounding_mode` | `STRING` | Enum | Rounding mode. |
| `policy_tags` | `STRING` | Resource Path | Policy tags attached to nested field. |
| `data_governance_tags` | `RECORD` | Struct | Data governance tags. |
| `data_policies` | `RECORD` | Struct | Masking policies applied to field. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.VIEWS`

#### High-Level Description

Tracks definitions for logical SQL views, including underlying queries, check
options, and SQL dialect flags.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
| `table_name` | `STRING` | Table ID | View name. |
| `view_definition` | `STRING` | SQL Query | Query expression defining the logical view. |
| `check_option` | `STRING` | String | View check option. |
| `use_standard_sql` | `STRING` | `'YES'` / `'NO'` | `'YES'` for GoogleSQL views. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.MATERIALIZED_VIEWS`

#### High-Level Description

Monitors Materialized Views, automatic background refresh statuses, and refresh
watermarks.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `table_catalog` | `STRING` | Project ID | Project name. |
| `table_schema` | `STRING` | Dataset ID | Dataset name. |
| `table_name` | `STRING` | Table ID | Materialized View name. |
| `last_refresh_time` | `TIMESTAMP` | UTC Timestamp | Last completed Materialized View refresh timestamp. |
| `refresh_watermark` | `TIMESTAMP` | UTC Timestamp | Upstream base table data watermark incorporated into the MV cache. |
| `last_refresh_status` | `RECORD` | Struct | Error details if the last automatic MV refresh failed (`reason`, `message`). |
<!-- mdformat on -->

<a id="sec-datasets"></a>

## 4. Datasets, Replication & Sharing Views

### `INFORMATION_SCHEMA.SCHEMATA`

#### High-Level Description

Defines dataset-level metadata, physical location regions, creation timestamps,
DDL statements, and default collation rules.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.datasets.get` on the target dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), **BigQuery Data Owner**
    (`roles/bigquery.dataOwner`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Key Values | Description |
| :--- | :--- | :--- | :--- |
| `catalog_name` | `STRING` | Project ID | Project name. |
| `schema_name` | `STRING` | Dataset ID | Dataset identifier. |
| `schema_owner` | `STRING` | String | Owning identity. |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Dataset creation timestamp. |
| `last_modified_time` | `TIMESTAMP` | UTC Timestamp | Last metadata modification timestamp. |
| `location` | `STRING` | Region | Physical geographic storage region (e.g. `'US'`, `'EU'`, `'us-central1'`). |
| `default_collation_name` | `STRING` | Collation | Default collation rule inherited by new tables. |
| `ddl` | `STRING` | SQL String | DDL statement to reproduce the dataset. |
| `sync_status` | `JSON` | JSON | Cross-region replication sync health details. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.SCHEMATA_OPTIONS`

#### High-Level Description

Lists configured dataset options including storage billing models, Time Travel
durations, and default partition expiration days.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.datasets.get` on the target dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), **BigQuery Data Owner**
    (`roles/bigquery.dataOwner`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Key Values | Description |
| :--- | :--- | :--- | :--- |
| `catalog_name` | `STRING` | Project ID | Project name. |
| `schema_name` | `STRING` | Dataset ID | Dataset identifier. |
| `option_name` | `STRING` | `'storage_billing_model'`, `'max_time_travel_hours'`, `'default_table_expiration_days'`, `'default_partition_expiration_days'` | Dataset configuration option. |
| `option_type` | `STRING` | SQL Type | Type of option. |
| `option_value` | `STRING` | `'LOGICAL'`, `'PHYSICAL'`, `'48'`, `'14'` | Configured option value. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.SCHEMATA_REPLICAS` (and `_BY_FAILOVER_RESERVATION`)

#### High-Level Description

Monitors cross-region dataset replication configurations, secondary replica
health, lag staleness, failover reservations, and backfill progress.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.datasets.get` on the target dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), **BigQuery Data Owner**
    (`roles/bigquery.dataOwner`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `catalog_name` | `STRING` | Project ID | Project name. |
| `creation_complete` | `BOOLEAN` | Boolean | `TRUE` if initial backfill is complete and replica is fully synchronized. |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when replica creation started. |
| `failover_reservation_name` | `STRING` | Reservation ID | Failover reservation name (only in `_BY_FAILOVER_RESERVATION`). |
| `failover_reservation_project_id` | `STRING` | Project ID | Admin project hosting the failover compute reservation (only in `_BY_FAILOVER_RESERVATION`). |
| `location` | `STRING` | Region | Geographic region where replica is hosted. |
| `replica_name` | `STRING` | Replica ID | Unique replica identifier. |
| `replica_primary_assigned` | `BOOLEAN` | Boolean | `TRUE` if this replica has the primary assignment. |
| `replica_primary_assignment_complete` | `BOOLEAN` | Boolean | `TRUE` if primary role assignment has completed. |
| `replica_primary_assignment_completion_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when primary switch to replica was completed. |
| `replica_primary_assignment_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when primary switch to replica was initiated. |
| `replication_time` | `TIMESTAMP` | UTC Timestamp | Replication watermark for the most stale table within the dataset. |
| `schema_name` | `STRING` | Dataset ID | Dataset name. |
| `sync_status` | `JSON` | JSON | Sync health details between primary and secondary replicas. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.SCHEMATA_LINKS` & `SHARED_DATASET_USAGE`

#### High-Level Description

Tracks linked datasets created via Analytics Hub data exchanges, Data Clean
Rooms (DCR), and Cross-Project Shared Dataset usage.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.datasets.get` on the target dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), **BigQuery Data Owner**
    (`roles/bigquery.dataOwner`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `catalog_name` | `STRING` | Project ID | Source dataset project name. |
| `schema_name` | `STRING` | Dataset ID | Source dataset name. |
| `linked_schema_catalog_name` | `STRING` | Project ID | Subscriber project hosting the linked dataset. |
| `linked_schema_catalog_number` | `INT64` | Numeric ID | Subscriber project number. |
| `linked_schema_name` | `STRING` | Dataset ID | Subscriber linked dataset identifier. |
| `linked_schema_org_display_name` | `STRING` | String | Organization name of the subscriber. |
| `linked_schema_creation_time` | `TIMESTAMP` | UTC Timestamp | Creation timestamp of linked dataset. |
| `shared_asset_id` | `STRING` | Asset ID | Analytics Hub listing or DCR asset identifier. |
| `link_type` | `STRING` | Enum | `'ANALYTICS_HUB'`, `'DATA_CLEAN_ROOM'`. |
<!-- mdformat on -->

<a id="sec-routines"></a>

### `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`

#### High-Level Description

Defines primary key and foreign key relational constraints on base tables.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` (for primary/foreign key definitions) and
    `bigquery.tables.list` on the target dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `constraint_catalog` | `STRING` | Project ID | Project name. |
| `constraint_schema` | `STRING` | Dataset ID | Dataset name. |
| `constraint_name` | `STRING` | Constraint ID | Unique constraint identifier. |
| `table_catalog` | `STRING` | Project ID | Table project name. |
| `table_schema` | `STRING` | Dataset ID | Table dataset name. |
| `table_name` | `STRING` | Table ID | Table name. |
| `constraint_type` | `STRING` | Enum | `'PRIMARY KEY'` or `'FOREIGN KEY'`. |
| `is_deferrable` | `STRING` | `'NO'` | Indicates deferrability. |
| `initially_deferred` | `STRING` | `'NO'` | Indicates initial deferral status. |
| `enforced` | `STRING` | `'NO'` | `'NO'` for informational GoogleSQL constraints. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.KEY_COLUMN_USAGE`

#### High-Level Description

Defines column-level participation in primary and foreign key constraints.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `constraint_catalog` | `STRING` | Project ID | Project name. |
| `constraint_schema` | `STRING` | Dataset ID | Dataset name. |
| `constraint_name` | `STRING` | Constraint ID | Constraint identifier. |
| `table_catalog` | `STRING` | Project ID | Table project ID. |
| `table_schema` | `STRING` | Dataset ID | Table dataset ID. |
| `table_name` | `STRING` | Table ID | Table name. |
| `column_name` | `STRING` | Column Name | Column participating in constraint. |
| `ordinal_position` | `INT64` | Position | 1-indexed position in composite constraint. |
| `position_in_unique_constraint` | `INT64` | Position | Referenced position in target primary key. |
<!-- mdformat on -->

<a id="sec-insights"></a>
