# BigQuery Platform, Governance & Ingestion INFORMATION_SCHEMA Reference

A comprehensive dictionary, column definition guide, and physical unit
specification for all remaining BigQuery `INFORMATION_SCHEMA` views, covering BI
Engine Acceleration, Security, Streaming Ingestion, Routines, Search/Vector
Indexes, Configurations, and Recommendations.

## Table of Contents

-   [View Scoping & Qualification Matrix](#view-scoping-qualification-matrix)
    (Lines 61-78)
-   [5. Routines, Functions, Stored Procedures & ML Views](#5-routines-functions-stored-procedures-ml-views)
    (Lines 79-178)
    -   [`INFORMATION_SCHEMA.ROUTINES`](#information_schemaroutines) (Lines
        81-119)
    -   [`INFORMATION_SCHEMA.PARAMETERS`](#information_schemaparameters) (Lines
        120-150)
    -   [`INFORMATION_SCHEMA.ROUTINE_OPTIONS`](#information_schemaroutine_options)
        (Lines 151-178)
-   [6. Streaming & Ingestion Views](#6-streaming-ingestion-views) (Lines
    179-248)
    -   [`INFORMATION_SCHEMA.STREAMING_TIMELINE_BY_PROJECT` (and `_BY_ORGANIZATION`, `_BY_FOLDER`)](#information_schemastreaming_timeline_by_project-and-_by_organization-_by_folder)
        (Lines 181-213)
    -   [`INFORMATION_SCHEMA.WRITE_API_TIMELINE_BY_PROJECT` (and `_BY_ORGANIZATION`, `_BY_FOLDER`)](#information_schemawrite_api_timeline_by_project-and-_by_organization-_by_folder)
        (Lines 214-248)
-   [7. Search, Vector, AI Indexes & BI Engine Views](#7-search-vector-ai-indexes-bi-engine-views)
    (Lines 249-404)
    -   [`INFORMATION_SCHEMA.SEARCH_INDEXES` (and `_OPTIONS`)](#information_schemasearch_indexes-and-_options)
        (Lines 251-289)
    -   [`INFORMATION_SCHEMA.SEARCH_INDEX_COLUMNS`](#information_schemasearch_index_columns)
        (Lines 290-315)
    -   [`INFORMATION_SCHEMA.VECTOR_INDEXES` (and `_OPTIONS`)](#information_schemavector_indexes-and-_options)
        (Lines 316-353)
    -   [`INFORMATION_SCHEMA.VECTOR_INDEX_COLUMNS`](#information_schemavector_index_columns)
        (Lines 354-379)
    -   [`INFORMATION_SCHEMA.BI_CAPACITIES` & `BI_CAPACITY_CHANGES`](#information_schemabi_capacities-bi_capacity_changes)
        (Lines 380-404)
-   [8. Security, Access Control, Governance & Policy Views](#8-security-access-control-governance-policy-views)
    (Lines 405-441)
    -   [`INFORMATION_SCHEMA.OBJECT_PRIVILEGES`](#information_schemaobject_privileges)
        (Lines 407-432)
    -   [Row-Level Access Policies (CLI / REST API Only)](#row-level-access-policies-cli-rest-api-only)
        (Lines 433-441)
-   [9. Recommendations & Insights Views](#9-recommendations-insights-views)
    (Lines 442-518)
    -   [`INFORMATION_SCHEMA.RECOMMENDATIONS` (and `_BY_PROJECT`, `_BY_ORGANIZATION`)](#information_schemarecommendations-and-_by_project-_by_organization)
        (Lines 444-480)
    -   [`INFORMATION_SCHEMA.INSIGHTS` (and `_BY_PROJECT`)](#information_schemainsights-and-_by_project)
        (Lines 481-518)
-   [10. Project & Organization Configuration Views](#10-project-organization-configuration-views)
    (Lines 519-615)
    -   [`INFORMATION_SCHEMA.PROJECT_OPTIONS`](#information_schemaproject_options)
        (Lines 521-547)
    -   [`INFORMATION_SCHEMA.EFFECTIVE_PROJECT_OPTIONS`](#information_schemaeffective_project_options)
        (Lines 548-573)
    -   [`INFORMATION_SCHEMA.ORGANIZATION_OPTIONS`](#information_schemaorganization_options)
        (Lines 574-595)
    -   [`INFORMATION_SCHEMA.ORGANIZATION_OPTIONS_CHANGES`](#information_schemaorganization_options_changes)
        (Lines 596-615)

## View Scoping & Qualification Matrix

Platform, acceleration, and governance views fall into **Dual-Scoped**,
**Region-Only**, and **Dataset-Only** qualification categories:

<!-- mdformat off -->
| View Family | INFORMATION_SCHEMA View(s) | Qualification Scope | Syntax Pattern & Scoping Rules |
| :--- | :--- | :--- | :--- |
| **BI Engine Acceleration** | `BI_CAPACITIES`, `BI_CAPACITY_CHANGES` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.BI_CAPACITIES*``<br>• In-memory RAM capacity and allocation modification logs. |
| **Search Indexes** | `SEARCH_INDEXES`, `SEARCH_INDEX_COLUMNS`, `SEARCH_INDEX_OPTIONS`, `SEARCH_INDEX_COLUMN_OPTIONS`<br><br>`SEARCH_INDEXES_BY_ORGANIZATION` | **Dataset-Only**<br><br><br>**Region-Only** | • Dataset views require `{dataset_id}`.<br>• Org view requires `region-{region}`. |
| **Vector Indexes** | `VECTOR_INDEXES`, `VECTOR_INDEX_COLUMNS`, `VECTOR_INDEX_OPTIONS` | **Dual-Scoped** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.VECTOR_INDEXES*``<br>OR<br>`` `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.VECTOR_INDEXES*`` |
| **Access Control** | `OBJECT_PRIVILEGES` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.OBJECT_PRIVILEGES``<br>• IAM permissions on datasets, tables, and views. |
| **Streaming Ingestion** | `STREAMING_TIMELINE_BY_PROJECT*`, `WRITE_API_TIMELINE_BY_PROJECT*` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view_name}``<br>• Streaming buffer and Storage Write API append throughput. |
| **Configurations** | `PROJECT_OPTIONS*`, `EFFECTIVE_PROJECT_OPTIONS`, `ORGANIZATION_OPTIONS*` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view_name}``<br>• Default option settings and audit history. |
| **Insights & Recommendations** | `RECOMMENDATIONS*`, `INSIGHTS` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view_name}``<br>• Slot rightsizing and partitioning recommendations. |
| **Routines & Parameters** | `ROUTINES`, `PARAMETERS`, `ROUTINE_OPTIONS` | **Dual-Scoped** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.ROUTINES*``<br>OR<br>`` `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.ROUTINES*`` |
<!-- mdformat on -->

## 5. Routines, Functions, Stored Procedures & ML Views

### `INFORMATION_SCHEMA.ROUTINES`

#### High-Level Description

Defines user-defined functions (UDFs), stored procedures, remote functions,
table functions (TVFs), parameter signatures, return types, determinism, and
Cloud Function connection endpoints.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.routines.get` and `bigquery.routines.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `specific_catalog` | `STRING` | Project ID | Project name. |
| `specific_schema` | `STRING` | Dataset ID | Dataset name. |
| `specific_name` | `STRING` | Routine ID | Unique routine identifier. |
| `routine_catalog` | `STRING` | Project ID | Catalog name. |
| `routine_schema` | `STRING` | Dataset ID | Schema name. |
| `routine_name` | `STRING` | Name | Function/procedure name. |
| `routine_type` | `STRING` | Enum | `'FUNCTION'`, `'PROCEDURE'`, `'TABLE FUNCTION'`. |
| `data_type` | `STRING` | SQL Type | Return data type (or `NULL` for procedures). |
| `routine_body` | `STRING` | Enum | `'SQL'` or `'EXTERNAL'`. |
| `routine_definition` | `STRING` | SQL Code | Routine body expression or JavaScript/Python function text. |
| `external_language` | `STRING` | Enum | `'JAVASCRIPT'`, `'PYTHON'`, or `NULL` (when defined with SQL). |
| `is_deterministic` | `STRING` | `'YES'` / `'NO'` | Indicates whether identical inputs always return identical results (`NULL` if unknown). |
| `security_type` | `STRING` | Nullable | Security type of the routine (always `NULL`). |
| `created` | `TIMESTAMP` | UTC Timestamp | Creation timestamp. |
| `last_altered` | `TIMESTAMP` | UTC Timestamp | Last modification timestamp. |
| `ddl` | `STRING` | SQL String | DDL statement to recreate the routine. |
| `connection` | `STRING` | Resource Path | Cloud Resource connection path for BigQuery Remote Functions. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.PARAMETERS`

#### High-Level Description

Defines parameter signatures, modes, positions, and defaults for BigQuery
routines.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.routines.get` and `bigquery.routines.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `specific_catalog` | `STRING` | Project ID | Project name. |
| `specific_schema` | `STRING` | Dataset ID | Dataset name. |
| `specific_name` | `STRING` | Routine ID | Unique routine identifier. |
| `ordinal_position` | `INT64` | Position | 1-indexed parameter position (0 = return value). |
| `parameter_mode` | `STRING` | Enum | `'IN'`, `'OUT'`, `'INOUT'`. |
| `is_result` | `STRING` | `'YES'` / `'NO'` | `'YES'` if row represents function return value. |
| `parameter_name` | `STRING` | Param Name | Parameter identifier. |
| `data_type` | `STRING` | SQL Type | GoogleSQL data type of parameter. |
| `parameter_default` | `STRING` | SQL Literal | Default value expression. |
| `is_aggregate` | `STRING` | `'YES'` / `'NO'` | Indicates aggregate parameter status. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.ROUTINE_OPTIONS`

#### High-Level Description

Lists routine-level configuration options defined in `OPTIONS(...)` clauses.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.routines.get` and `bigquery.routines.list` on the target
    dataset or project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `specific_catalog` | `STRING` | Project ID | Project name. |
| `specific_schema` | `STRING` | Dataset ID | Dataset name. |
| `specific_name` | `STRING` | Routine ID | Unique routine identifier. |
| `option_name` | `STRING` | Option Name | Option key. |
| `option_type` | `STRING` | SQL Type | GoogleSQL type of option. |
| `option_value` | `STRING` | Option Value | Configured option value. |
<!-- mdformat on -->

<a id="sec-streaming"></a>

## 6. Streaming & Ingestion Views

### `INFORMATION_SCHEMA.STREAMING_TIMELINE_BY_PROJECT` (and `_BY_ORGANIZATION`, `_BY_FOLDER`)

#### High-Level Description

Provides 1-minute discrete telemetry for real-time data ingestion via BigQuery
Storage Write API and legacy streaming. Tracks ingested payloads, row counts,
and streaming error rates.

#### Required IAM Permissions & Predefined Roles

*   **Project-Level (Least Privilege):** Requires `bigquery.tables.list` on the
    project. Granted by **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer`), **BigQuery Data Viewer**
    (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_FOLDER`:** Requires `bigquery.tables.list` on the parent folder.
*   **`_BY_ORGANIZATION`:** Requires `bigquery.tables.list` on the organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description & Conversion Formula |
| :--- | :--- | :--- | :--- |
| `dataset_id` | `STRING` | Dataset ID | Target dataset. |
| `error_code` | `STRING` | Error Code | Ingestion error classification code. |
| `folder_numbers` | `ARRAY<INT64>` | Array | Folder hierarchy IDs containing the project (only in `_BY_FOLDER`). |
| `project_id` | `STRING` | Project ID | Project receiving streamed rows. |
| `project_number` | `INT64` | Numeric ID | Numeric project identifier. |
| `start_timestamp` | `TIMESTAMP` | UTC Timestamp | 1-minute discrete interval timestamp. |
| `table_id` | `STRING` | Table ID | Target table. |
| `total_input_bytes` | `INT64` | **Bytes** | Raw ingested byte payload. |
| `total_requests` | `INT64` | Count | Number of streaming append requests. |
| `total_rows` | `INT64` | Count | Total records ingested. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.WRITE_API_TIMELINE_BY_PROJECT` (and `_BY_ORGANIZATION`, `_BY_FOLDER`)

#### High-Level Description

Monitors BigQuery Storage Write API traffic, throughput, and committed vs.
default stream modes.

#### Required IAM Permissions & Predefined Roles

*   **Project-Level (Least Privilege):** Requires `bigquery.tables.list` on the
    project. Granted by **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer`), **BigQuery Data Viewer**
    (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_FOLDER`:** Requires `bigquery.tables.list` on the parent folder.
*   **`_BY_ORGANIZATION`:** Requires `bigquery.tables.list` on the organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `dataset_id` | `STRING` | Dataset ID | Target dataset ID. |
| `error_code` | `STRING` | Error Code | Write API error code. |
| `folder_numbers` | `ARRAY<INT64>` | Array | Folder hierarchy IDs containing the project (only in `_BY_FOLDER`). |
| `project_id` | `STRING` | Project ID | Project containing the target tables. |
| `project_number` | `INT64` | Numeric ID | Numeric project identifier. |
| `start_timestamp` | `TIMESTAMP` | UTC Timestamp | 1-minute discrete interval timestamp. |
| `stream_type` | `STRING` | Enum | `'COMMITTED'`, `'PENDING'`, `'BUFFERED'`, `'DEFAULT'`. |
| `table_id` | `STRING` | Table ID | Target table ID. |
| `total_input_bytes` | `INT64` | **Bytes** | Total bytes processed by the Storage Write API. |
| `total_requests` | `INT64` | Count | Number of append requests. |
| `total_rows` | `INT64` | Count | Total rows appended. |
<!-- mdformat on -->

<a id="sec-indexes"></a>

## 7. Search, Vector, AI Indexes & BI Engine Views

### `INFORMATION_SCHEMA.SEARCH_INDEXES` (and `_OPTIONS`)

#### High-Level Description

Monitors BigQuery text Search Indexes, indexing coverage percentages, storage
footprints, text analyzers, and unindexed row backlogs.

#### Required IAM Permissions & Predefined Roles

*   **Dataset/Project Scope (Least Privilege):** Requires `bigquery.tables.get`
    and `bigquery.tables.list` on the dataset or project. Granted by **BigQuery
    Metadata Viewer** (`roles/bigquery.metadataViewer`), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_ORGANIZATION`:** Requires `bigquery.tables.get` and
    `bigquery.tables.list` on the organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `analyzer` | `STRING` | Enum | Text analyzer: `'LOG_ANALYZER'`, `'NO_OP_ANALYZER'`, `'TEXT_ANALYZER'`. |
| `coverage_percentage` | `INT64` | Percent | Percentage of base table data currently indexed (0–100). |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when index was created. |
| `ddl` | `STRING` | SQL String | DDL statement to recreate search index. |
| `disable_reason` | `STRING` | Reason String | Reason index was disabled. |
| `disable_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when index was disabled. |
| `index_catalog` | `STRING` | Project ID | Project name. |
| `index_name` | `STRING` | Index Name | Search index name. |
| `index_schema` | `STRING` | Dataset ID | Dataset name. |
| `index_status` | `STRING` | Enum | `'ACTIVE'`, `'PENDING'`, `'STALE'`, `'DISABLED'`. |
| `last_index_alteration_info` | `RECORD` | Alteration Struct | Details of latest user-triggered index alteration (`status`, `message`, `new_coverage_percentage`, `start_time`, `end_time`, `ddl`). |
| `last_modification_time` | `TIMESTAMP` | UTC Timestamp | Last index modification timestamp. |
| `last_refresh_time` | `TIMESTAMP` | UTC Timestamp | Last completed index build timestamp. |
| `table_name` | `STRING` | Table ID | Base table identifier. |
| `total_logical_bytes` | `INT64` | **Bytes** | Logical storage consumed by search index structures. |
| `total_storage_bytes` | `INT64` | **Bytes** | Physical storage consumed by search index structures. |
| `unindexed_row_count` | `INT64` | Count | Number of base table rows not yet indexed. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.SEARCH_INDEX_COLUMNS`

#### High-Level Description

Defines columns participating in BigQuery text Search Indexes.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.tables.get` and `bigquery.tables.list` on the dataset or
    project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Data
    Viewer** (`roles/bigquery.dataViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `index_catalog` | `STRING` | Project ID | Project name. |
| `index_schema` | `STRING` | Dataset ID | Dataset name. |
| `table_name` | `STRING` | Table ID | Table name. |
| `index_name` | `STRING` | Index Name | Search index name. |
| `index_column_name` | `STRING` | Column Name | Name of indexed column. |
| `index_field_path` | `STRING` | Field Path | Field path for struct columns. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.VECTOR_INDEXES` (and `_OPTIONS`)

#### High-Level Description

Monitors Vector Indexes (e.g. IVF, HNSW, Tree-AH) for vector similarity search
and embedding lookups (`VECTOR_SEARCH`).

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
| `coverage_percentage` | `INT64` | Percent | Base table vector data indexing coverage percentage (0–100). |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when vector index was created. |
| `ddl` | `STRING` | SQL String | DDL statement to recreate vector index. |
| `disable_reason` | `STRING` | Reason String | Reason index was disabled. |
| `disable_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when index was disabled. |
| `index_catalog` | `STRING` | Project ID | Project name. |
| `index_name` | `STRING` | Index Name | Vector index name. |
| `index_schema` | `STRING` | Dataset ID | Dataset name. |
| `index_status` | `STRING` | Enum | `'ACTIVE'`, `'PENDING DISABLEMENT'`, `'TEMPORARILY DISABLED'`, `'PERMANENTLY DISABLED'`. |
| `last_index_alteration_info` | `RECORD` | Alteration Struct | Details of latest user-triggered index alteration (`status`, `message`, `new_coverage_percentage`, `start_time`, `end_time`, `ddl`). |
| `last_model_build_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when index model build was initiated. |
| `last_modification_time` | `TIMESTAMP` | UTC Timestamp | Last index modification timestamp. |
| `last_refresh_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when index weights were last updated. |
| `table_name` | `STRING` | Table ID | Base table name. |
| `total_logical_bytes` | `INT64` | **Bytes** | Logical index size. |
| `total_storage_bytes` | `INT64` | **Bytes** | Physical compressed index size. |
| `unindexed_row_count` | `INT64` | Count | Number of vectors pending indexing. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.VECTOR_INDEX_COLUMNS`

#### High-Level Description

Defines columns participating in BigQuery Vector Indexes.

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
| `index_catalog` | `STRING` | Project ID | Project name. |
| `index_column_name` | `STRING` | Column Name | Vector embedding column name. |
| `index_field_path` | `STRING` | Field Path | Field path for struct columns. |
| `index_name` | `STRING` | Index Name | Vector index name. |
| `index_schema` | `STRING` | Dataset ID | Dataset name. |
| `table_name` | `STRING` | Table ID | Table name. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.BI_CAPACITIES` & `BI_CAPACITY_CHANGES`

#### High-Level Description

Tracks BigQuery BI Engine in-memory acceleration reservations, configured RAM
capacities, and capacity alteration events.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.bireservations.get` on the project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `bi_capacity_name` | `STRING` | Resource Path | BI Engine capacity identifier. |
| `preferred_tables` | `ARRAY<STRING>` | Array | Pinned tables prioritized for memory caching (`NULL` = all tables in project). |
| `project_id` | `STRING` | Project ID | Project hosting the BI Engine capacity. |
| `project_number` | `INT64` | Numeric ID | Project number. |
| `size` | `INT64` | **Bytes** | Configured in-memory RAM capacity allocation. |
<!-- mdformat on -->

## 8. Security, Access Control, Governance & Policy Views

### `INFORMATION_SCHEMA.OBJECT_PRIVILEGES`

#### High-Level Description

Lists explicit IAM role bindings across datasets, tables, views, and external
tables.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.datasets.get` on datasets or
    `bigquery.tables.getIamPolicy` on tables and views.
*   **Predefined Roles:** **BigQuery Data Owner** (`roles/bigquery.dataOwner`),
    **BigQuery Admin** (`roles/bigquery.admin`), or **Security Admin**
    (`roles/iam.securityAdmin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `grantee` | `STRING` | Principal | Grantee identity (`'user:alice@example.com'`, `'group:analysts@example.com'`, `'serviceAccount:app@proj.iam.gserviceaccount.com'`). |
| `object_catalog` | `STRING` | Project ID | Project containing the resource. |
| `object_name` | `STRING` | Resource Name | Name of table, view, or dataset. |
| `object_schema` | `STRING` | Dataset ID | Dataset containing the resource. |
| `object_type` | `STRING` | Enum | `'SCHEMA'`, `'TABLE'`, `'VIEW'`, `'EXTERNAL'`. |
| `privilege_type` | `STRING` | Role ID | IAM Role ID granted (e.g. `'roles/bigquery.dataViewer'`). |
<!-- mdformat on -->

### Row-Level Access Policies (CLI / REST API Only)

BigQuery does not expose `INFORMATION_SCHEMA` views for row-level access
policies. List row-level access policies on a table using `bq ls
--row_access_policies {dataset_id}.{table_id}` or the `RowAccessPolicies.List`
REST API method (requires `bigquery.rowAccessPolicies.list`, plus
`bigquery.rowAccessPolicies.getIamPolicy` to view policy grantees, granted by
`roles/bigquery.dataOwner` or `roles/bigquery.admin`).

## 9. Recommendations & Insights Views

### `INFORMATION_SCHEMA.RECOMMENDATIONS` (and `_BY_PROJECT`, `_BY_ORGANIZATION`)

#### High-Level Description

Surfaces automated BigQuery Recommender recommendations for cost savings,
performance optimization, partition/cluster suggestions, and reservation
rightsizing.

#### Required IAM Permissions & Predefined Roles

*   **Project-Level (Least Privilege):** Requires
    `recommender.bigqueryCapacityCommitmentsRecommendations.get` and
    `recommender.bigqueryCapacityCommitmentsRecommendations.list` on the
    project. Granted by **Recommender Viewer** (`roles/recommender.viewer` /
    `roles/recommender.bigqueryViewer`) or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_ORGANIZATION`:** Requires recommender permissions at the organization
    level.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `additional_details` | `RECORD` | Struct | JSON details and recommended DDL/CLI operations (`operations.action`, `operations.path`, `operations.value`). |
| `associated_insight_ids` | `ARRAY<STRING>` | IDs | IDs of `INSIGHTS` supporting this recommendation. |
| `description` | `STRING` | Text | Human-readable recommendation text and rationale. |
| `last_updated_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when recommendation was generated or refreshed. |
| `primary_impact` | `RECORD` | Struct | Cost, performance, or security impact (`category`, `cost_projection.duration_seconds`). |
| `priority` | `STRING` | Enum | `'P1'`, `'P2'`, `'P3'`, `'P4'`. |
| `project_id` | `STRING` | Project ID | Project ID. |
| `project_number` | `INT64` | Numeric ID | Project number. |
| `recommendation_id` | `STRING` | Base64 ID | Unique recommendation identifier. |
| `recommender` | `STRING` | String | Recommender type (e.g. `'google.bigquery.table.PartitionClusterRecommender'`). |
| `state` | `STRING` | Enum | `'ACTIVE'`, `'CLAIMED'`, `'SUCCEEDED'`, `'DISMISSED'`. |
| `subtype` | `STRING` | String | Subtype classification (e.g. `'PARTITION'`, `'CLUSTER'`). |
| `target_resources` | `ARRAY<STRING>` | Resource Paths | Fully qualified GCP resources affected by recommendation. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.INSIGHTS` (and `_BY_PROJECT`)

#### High-Level Description

Surfaces underlying workload signals, slot bottlenecks, table scan patterns, and
stats that trigger recommender actions.

#### Required IAM Permissions & Predefined Roles

*   **Project-Level (Least Privilege):** Requires
    `recommender.bigqueryCapacityCommitmentsInsights.get/list` or
    `recommender.bigqueryPartitionClusterInsights.get/list` on the project.
    Granted by **Recommender Viewer** (`roles/recommender.viewer` /
    `roles/recommender.bigqueryViewer`) or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`_BY_ORGANIZATION`:** Requires insight permissions at the organization
    level.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `additional_details` | `RECORD` | Struct | JSON details and observation period (`observation_period_seconds`). |
| `associated_recommendation_ids` | `ARRAY<STRING>` | IDs | Full recommendation names/IDs associated with this insight. |
| `category` | `STRING` | Enum | `'COST'`, `'PERFORMANCE'`, `'SECURITY'`. |
| `description` | `STRING` | Text | Description of observed performance signal. |
| `insight_id` | `STRING` | Base64 ID | Unique insight identifier. |
| `insight_type` | `STRING` | String | Insight type (e.g. `'google.bigquery.table.StatsInsight'`). |
| `last_updated_time` | `TIMESTAMP` | UTC Timestamp | Generation timestamp. |
| `project_id` | `STRING` | Project ID | Project ID. |
| `project_number` | `INT64` | Numeric ID | Project number. |
| `severity` | `STRING` | Enum | `'LOW'`, `'MEDIUM'`, `'HIGH'`, `'CRITICAL'`. |
| `state` | `STRING` | Enum | `'ACTIVE'`, `'ACCEPTED'`, `'DISMISSED'`. |
| `subtype` | `STRING` | String | Subtype classification (`'TABLE_STATS'`). |
| `target_resources` | `ARRAY<STRING>` | Resource Paths | Targeted GCP resources. |
<!-- mdformat on -->

<a id="sec-config"></a>

## 10. Project & Organization Configuration Views

### `INFORMATION_SCHEMA.PROJECT_OPTIONS`

#### High-Level Description

Lists configured project-level default options (e.g. default time travel
duration, KMS keys, default query priority, and default reservation
assignments).

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.config.get` on the project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Resource
    Viewer** (`roles/bigquery.resourceViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `project_number` | `INT64` | Numeric ID | Project number. |
| `project_id` | `STRING` | Project ID | Project identifier. |
| `option_name` | `STRING` | Option Name | Option identifier (e.g. `'default_time_travel_hours'`, `'default_query_job_timeout_ms'`). |
| `option_description` | `STRING` | Text | Description of the option's behavior. |
| `option_type` | `STRING` | SQL Type | GoogleSQL data type. |
| `option_value` | `STRING` | Value String | Configured parameter value. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.EFFECTIVE_PROJECT_OPTIONS`

#### High-Level Description

Lists effective project options accounting for organization and folder
inheritance hierarchy.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.config.get` on the project.
*   **Predefined Roles:** **BigQuery Metadata Viewer**
    (`roles/bigquery.metadataViewer` - Least Privilege), **BigQuery Resource
    Viewer** (`roles/bigquery.resourceViewer`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `project_number` | `INT64` | Numeric ID | Project number. |
| `project_id` | `STRING` | Project ID | Project identifier. |
| `option_name` | `STRING` | Option Name | Option identifier. |
| `option_value` | `STRING` | Value String | Effective option value. |
| `option_set_level` | `STRING` | Enum | Definition level: `'DEFAULT'`, `'ORGANIZATION'`, `'FOLDER'`, `'PROJECT'`, `'USER'`. |
| `option_set_on_id` | `STRING` | Resource ID | GCP resource ID where the setting was overridden. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.ORGANIZATION_OPTIONS`

#### High-Level Description

Defines organization-level default configuration settings across BigQuery
projects.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.config.get` on the organization.
*   **Predefined Roles:** **BigQuery Admin** (`roles/bigquery.admin`) on the
    organization resource.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `option_name` | `STRING` | Option Name | Organization setting name. |
| `option_description` | `STRING` | Text | Option description. |
| `option_type` | `STRING` | SQL Type | Option data type. |
| `option_value` | `STRING` | Value String | Configured organization-wide value. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.ORGANIZATION_OPTIONS_CHANGES`

#### High-Level Description

Maintains an audit log of organization-level setting updates.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.config.get` on the organization.
*   **Predefined Roles:** **BigQuery Admin** (`roles/bigquery.admin`) on the
    organization resource.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `project_id` | `STRING` | Project ID | Project where change originated. |
| `update_time` | `TIMESTAMP` | UTC Timestamp | Timestamp of option change. |
| `username` | `STRING` | User Identity | Identity of administrator who committed change. |
| `updated_options` | `JSON` | JSON Struct | JSON object containing old and new setting values. |
<!-- mdformat on -->
