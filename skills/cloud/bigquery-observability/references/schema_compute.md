# BigQuery Compute & Capacity INFORMATION_SCHEMA Reference

A comprehensive dictionary, column definition guide, and physical unit
specification for all Compute, Job, Session, Reservation, Capacity Commitment,
and Assignment views in BigQuery `INFORMATION_SCHEMA`.

## Table of Contents

-   [View Scoping & Qualification Matrix](#view-scoping-qualification-matrix)
    (Lines 38-57)
-   [1. Jobs & Compute Telemetry Views](#1-jobs-compute-telemetry-views) (Lines
    58-268)
    -   [`INFORMATION_SCHEMA.JOBS` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_USER`, `_BY_FOLDER`)](#information_schemajobs-and-_by_project-_by_organization-_by_user-_by_folder)
        (Lines 60-177)
    -   [`INFORMATION_SCHEMA.JOBS_TIMELINE` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_USER`, `_BY_FOLDER`)](#information_schemajobs_timeline-and-_by_project-_by_organization-_by_user-_by_folder)
        (Lines 178-233)
    -   [`INFORMATION_SCHEMA.SESSIONS_BY_USER` (and `_BY_PROJECT`)](#information_schemasessions_by_user-and-_by_project)
        (Lines 234-268)
-   [2. Capacity, Reservations & Commitments Views](#2-capacity-reservations-commitments-views)
    (Lines 269-588)
    -   [`INFORMATION_SCHEMA.RESERVATIONS` (and `_BY_PROJECT`)](#information_schemareservations-and-_by_project)
        (Lines 271-309)
    -   [`INFORMATION_SCHEMA.RESERVATION_CHANGES` (and `_BY_PROJECT`)](#information_schemareservation_changes-and-_by_project)
        (Lines 310-352)
    -   [`INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` (and `_BY_PROJECT`)](#information_schemareservations_timeline-and-_by_project)
        (Lines 353-426)
    -   [`INFORMATION_SCHEMA.CAPACITY_COMMITMENTS` (and `_BY_PROJECT`)](#information_schemacapacity_commitments-and-_by_project)
        (Lines 427-457)
    -   [`INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` (and `_CHANGES`)](#information_schemacapacity_commitment_changes_by_project-and-_changes)
        (Lines 458-496)
    -   [`INFORMATION_SCHEMA.ASSIGNMENTS` (and `_BY_PROJECT`)](#information_schemaassignments-and-_by_project)
        (Lines 497-527)
    -   [`INFORMATION_SCHEMA.ASSIGNMENT_CHANGES_BY_PROJECT` (and `_CHANGES`)](#information_schemaassignment_changes_by_project-and-_changes)
        (Lines 528-562)
    -   [`INFORMATION_SCHEMA.BI_CAPACITIES` (and `BI_CAPACITY_CHANGES`)](#information_schemabi_capacities-and-bi_capacity_changes)
        (Lines 563-588)

## View Scoping & Qualification Matrix

BigQuery Compute and Capacity views are **Region-Only** scoped. They require the
`region-{region}` dataset qualifier (e.g. ``
`{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view_name}``) and cannot be
scoped to a single dataset:

<!-- mdformat off -->
| View Family | INFORMATION_SCHEMA View(s) | Qualification Scope | Syntax Pattern & Scoping Rules |
| :--- | :--- | :--- | :--- |
| **Jobs & Scripts** | `JOBS*` (`_BY_PROJECT`, `_BY_USER`, `_BY_FOLDER`, `_BY_ORGANIZATION`) | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS*``<br>• Real-time & historical job metadata (180 days retention).<br>• `_BY_USER` variant requires least privilege (`roles/bigquery.user`). |
| **Job Timeline** | `JOBS_TIMELINE*` (`_BY_PROJECT`, `_BY_USER`, `_BY_FOLDER`, `_BY_ORGANIZATION`) | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_TIMELINE*``<br>• 1-second continuous slot time-series slices for fine-grained workload profiling. |
| **SQL Sessions** | `SESSIONS_BY_USER`, `SESSIONS_BY_PROJECT` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.SESSIONS*``<br>• Active and interactive multi-statement SQL sessions and notebook lifetimes. |
| **Reservations** | `RESERVATIONS*`, `RESERVATION_CHANGES*` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.RESERVATIONS*``<br>• Current baseline slot limits, edition tier bindings, and reservation lifecycle changes (`RESERVATION_CHANGES`). |
| **Reservation Timeline** | `RESERVATIONS_TIMELINE*` (`_BY_PROJECT`) | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.RESERVATIONS_TIMELINE*``<br>• 1-minute discrete timeline of assigned baseline slots and periodic autoscale slot-seconds (`period_autoscale_slot_seconds`). Retention is 180 days. |
| **Capacity Commitments** | `CAPACITY_COMMITMENTS*`, `CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.CAPACITY_COMMITMENTS*``<br>• 1-Year / 3-Year commitment purchases, active states, renewal plans, and lifecycle changes (`CAPACITY_COMMITMENT_CHANGES`). |
| **Workload Assignments** | `ASSIGNMENTS*`, `ASSIGNMENT_CHANGES_BY_PROJECT` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.ASSIGNMENTS*``<br>• Mapping of projects/folders/orgs to specific reservations (`assignee_id`, `job_type`) and assignment lifecycle changes. |
| **BI Engine Capacities** | `BI_CAPACITIES*`, `BI_CAPACITY_CHANGES*` | **Region-Only** | `` `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.BI_CAPACITIES*``<br>• BI Engine RAM allocation sizes (bytes) and preferred table routing rules. |
<!-- mdformat on -->

## 1. Jobs & Compute Telemetry Views

### `INFORMATION_SCHEMA.JOBS` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_USER`, `_BY_FOLDER`)

#### High-Level Description

Provides real-time and historical metadata for all query, load, extract, and
copy jobs executed in the project or organization. Contains critical compute
telemetry including bytes billed, execution durations, slot consumption,
parent-child script hierarchy, and error classifications. Retention is 180 days.

#### Required IAM Permissions & Predefined Roles

*   **`JOBS_BY_USER` (Least Privilege):** Requires `bigquery.jobs.list` on the
    project. Granted by **BigQuery User** (`roles/bigquery.user`), **BigQuery
    Job User** (`roles/bigquery.jobUser`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`JOBS` / `JOBS_BY_PROJECT`:** Requires `bigquery.jobs.listAll` on the
    project. Granted by **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Studio Admin**
    (`roles/bigquery.studioAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`JOBS_BY_FOLDER`:** Requires `bigquery.jobs.listAll` on the parent folder.
*   **`JOBS_BY_ORGANIZATION`:** Requires `bigquery.jobs.listAll` on the
    organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description & Conversion Formula |
| :--- | :--- | :--- | :--- |
| `bi_engine_statistics` | `RECORD` | Struct | BI Engine execution mode (`bi_engine_mode`, `acceleration_mode`, `bi_engine_reasons`). |
| `cache_hit` | `BOOLEAN` | Boolean | `TRUE` if query results were served from deterministic cache (0 billed bytes). |
| `continuous` | `BOOLEAN` | Boolean | Whether the job is a continuous query. |
| `continuous_query_info.output_watermark` | `TIMESTAMP` | UTC Timestamp | Point up to which continuous query has successfully processed data. |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | (Partitioning column) Job submission timestamp in UTC. Pad by `-2 / +1` days relative to target PST billing window for partition pruning. |
| `destination_table` | `RECORD` | Struct | Destination table reference (`project_id`, `dataset_id`, `table_id`). |
| `dml_statistics` | `RECORD` | Struct | DML row modifications (`inserted_row_count`, `deleted_row_count`, `updated_row_count`). Only in `_BY_PROJECT`, `_BY_USER`, `_BY_FOLDER`. |
| `edition` | `STRING` | Enum | Edition tier executing the job (`'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`). |
| `end_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when job completed execution (`DONE` state). Used for PST billing alignment: `EXTRACT(DATE FROM end_time AT TIME ZONE 'PST8PDT')`. |
| `error_result` | `RECORD` | Struct | Job failure details (`reason`, `location`, `message`). Query is billable if `error_result IS NULL OR error_result.reason = 'stopped'`. |
| `external_service_costs` | `ARRAY<RECORD>` | Struct Array | Array of external service costs incurred by the query job. |
| `folder_numbers` | `ARRAY<INT64>` | Array | Folder hierarchy IDs containing the project (only populated in `JOBS_BY_FOLDER`). |
| `job_creation_reason.code` | `STRING` | Enum | High-level job creation reason: `'REQUESTED'`, `'LONG_RUNNING'`, `'LARGE_RESULTS'`, `'OTHER'`. |
| `job_id` | `STRING` | UUID | Unique job identifier within project and region (e.g. `bquxjob_1234`). |
| `job_stages` | `ARRAY<RECORD>` | Struct Array | Query execution plan stages, read/compute/write ratios, records read, and shuffle spill statistics. Empty for queries that read from tables with row-level access policies. |
| `job_type` | `STRING` | Enum | Job type: `'QUERY'`, `'LOAD'`, `'EXTRACT'`, `'COPY'`, or `NULL` (background job). |
| `labels` | `ARRAY<RECORD>` | Struct Array | Key-value labels applied to the job for cost attribution. |
| `materialized_view_statistics` | `RECORD` | Struct | Statistics of materialized views considered and chosen for query rewrite. |
| `metadata_cache_statistics` | `RECORD` | Struct | Statistics for metadata column index usage on external tables. |
| `parent_job_id` | `STRING` | UUID | Job ID of parent multi-statement query script or workflow. |
| `priority` | `STRING` | Enum | Scheduling priority: `'INTERACTIVE'` or `'BATCH'`. |
| `principal_subject` | `STRING` | Principal | IAM principal subject string identity. |
| `project_id` | `STRING` | Project ID | (Clustering column) GCP project ID that submitted and was billed for the job. |
| `project_number` | `INT64` | Numeric ID | GCP project number. |
| `query` | `STRING` | SQL String | Raw SQL query text (available in `_BY_PROJECT` and `_BY_USER`). |
| `query_dialect` | `STRING` | Enum | Dialect used: `'GOOGLE_SQL'`, `'LEGACY_SQL'`, `'DEFAULT_LEGACY_SQL'`, `'DEFAULT_GOOGLE_SQL'`. |
| `query_info.optimization_details` | `RECORD` | Struct | History-based optimizations applied to the job (only in `JOBS_BY_PROJECT`). |
| `query_info.performance_insights` | `RECORD` | Struct | Optimization opportunities surfaced by the engine (e.g. Stage Performance, Join Spill). |
| `query_info.query_hashes.normalized_literals` | `STRING` | Hash String | Abstract query signature with literal values stripped. Used to group identical recurring query templates. |
| `query_info.resource_warning` | `STRING` | Warning | System warning if resource usage during query processing exceeded internal thresholds. |
| `referenced_tables` | `ARRAY<RECORD>` | Struct Array | List of all base tables, views, and external assets referenced by query (`project_id`, `dataset_id`, `table_id`). |
| `reservation_id` | `STRING` | Resource Path | Capacity reservation path (`ADMIN_PROJECT:LOCATION.RESERVATION_NAME`). `NULL` for on-demand queries. |
| `reservation_group_path` | `ARRAY<STRING>` | Array | Hierarchical reservation group path (e.g. `['my-group']`). |
| `search_statistics` | `RECORD` | Struct | Statistics for search queries utilizing search indexes. |
| `session_info` | `RECORD` | Struct | Multi-query session context (`session_id`). |
| `start_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when compute resources transitioned from `PENDING` to `RUNNING`. |
| `state` | `STRING` | Enum | Lifecycle execution state: `'PENDING'`, `'RUNNING'`, `'DONE'`. |
| `statement_type` | `STRING` | Enum | SQL statement category (e.g. `'SELECT'`, `'CREATE_MODEL'`, `'SCRIPT'`, `'INSERT'`, `'UPDATE'`, `'DELETE'`). |
| `timeline` | `ARRAY<RECORD>` | Struct Array | Slice-level stage progression snapshots (`elapsed_ms`, `total_slot_ms`, `pending_units`, `completed_units`, `active_units`). |
| `total_bytes_billed` | `INT64` | **Bytes** | Raw billable bytes. **Formula to convert to TB:** `(total_bytes_billed / POWER(1024, 4)) * CASE statement_type WHEN 'CREATE_MODEL' THEN 50 ELSE 1 END`. Returns `NULL` if Row-Level Security (RLS) is active. |
| `total_bytes_processed` | `INT64` | **Bytes** | Total uncompressed bytes scanned before partition/column pruning. |
| `total_modified_partitions` | `INT64` | Count | Number of distinct table partitions updated by DML or load job. |
| `total_services_sku_slot_ms` | `INT64` | **Slot-ms** | Slot-ms consumed by external service workloads billed on the Services SKU. |
| `total_slot_ms` | `INT64` | **Slot-ms** | Total slot compute time consumed across entire duration including retries. **Formula for Slot-Hours:** `total_slot_ms / 1000.0 / 3600.0`. |
| `transaction_id` | `STRING` | UUID | Transaction ID in which this job ran, if any. |
| `transferred_bytes` | `INT64` | **Bytes** | Network egress/ingress bytes for BigQuery Omni and cross-region queries. |
| `user_email` | `STRING` | Email | (Clustering column) Email address or service account of the user who ran the job. |
| `vector_search_statistics` | `RECORD` | Struct | Statistics for vector search queries. |
<!-- mdformat on -->

#### Nested `job_stages` Schema (Field in `JOBS`)

The `job_stages` column in `JOBS` is an `ARRAY<RECORD>` where each element
represents a discrete execution stage (Input, Compute, Shuffle, Join, Output) in
the query plan (note that `job_stages` is empty for queries that read from
tables with row-level access policies):

*   `id` (`INT64`): Unique 0-indexed execution stage identifier.
*   `name` (`STRING`): Stage identifier (e.g. `'S00: Input'`, `'S01:
    Aggregate'`).
*   `input_stages` (`ARRAY<INT64>`): Stage IDs whose outputs feed into this
    stage.
*   `start_ms` (`INT64`): Millisecond timestamp when the stage began.
*   `end_ms` (`INT64`): Millisecond timestamp when the stage completed.
*   `slot_ms` (`INT64`): Slot compute time consumed by this stage.
*   `shuffle_output_bytes` (`INT64`): Bytes written to distributed shuffle.
*   `shuffle_output_bytes_spilled` (`INT64`): Bytes spilled to disk due to
    shuffle RAM pressure.
*   `records_read` (`INT64`): Number of input records consumed.
*   `records_written` (`INT64`): Number of output records produced.
*   `parallel_inputs` (`INT64`): Maximum parallel worker shards allocated.
*   `completed_parallel_inputs` (`INT64`): Shards successfully finished.
*   `wait_ratio_avg`, `wait_ratio_max` (`FLOAT64`): Fraction (`0.0-1.0`) of
    time the average or slowest worker in the stage spent waiting to be
    scheduled on available slots relative to the longest time any worker in any
    stage spent in any phase.
*   `wait_ms_avg`, `wait_ms_max` (`INT64`): Milliseconds the average or slowest
    worker in the stage spent waiting to be scheduled on available slots.
*   `read_ratio_avg`, `read_ratio_max`, `read_ms_avg`, `read_ms_max`
    (`FLOAT64` / `INT64`): Relative ratio and duration (ms) workers spent
    reading input table or shuffle data.
*   `compute_ratio_avg`, `compute_ratio_max`, `compute_ms_avg`, `compute_ms_max`
    (`FLOAT64` / `INT64`): Relative ratio and duration (ms) workers spent in CPU
    computation.
*   `write_ratio_avg`, `write_ratio_max`, `write_ms_avg`, `write_ms_max`
    (`FLOAT64` / `INT64`): Relative ratio and duration (ms) workers spent
    writing intermediate shuffle or final output data.
*   `status` (`STRING`): `'COMPLETE'`, `'RUNNING'`, `'FAILED'`, `'CANCELLED'`.
*   `steps` (`ARRAY<RECORD>`): Pipeline operations (`kind`, `substeps`).

### `INFORMATION_SCHEMA.JOBS_TIMELINE` (and `_BY_PROJECT`, `_BY_ORGANIZATION`, `_BY_USER`, `_BY_FOLDER`)

#### High-Level Description

Exposes fine-grained 1-second continuous telemetry for running BigQuery jobs.
Tracks instantaneous slot utilization, shuffle memory pressure, and concurrency
queue depth. Ideal for diagnosing latency spikes, scheduler throttling, and slot
starvation.

#### Required IAM Permissions & Predefined Roles

*   **`JOBS_BY_USER` (Least Privilege):** Requires `bigquery.jobs.list` on the
    project. Granted by **BigQuery User** (`roles/bigquery.user`), **BigQuery
    Job User** (`roles/bigquery.jobUser`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`JOBS` / `JOBS_BY_PROJECT`:** Requires `bigquery.jobs.listAll` on the
    project. Granted by **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Studio Admin**
    (`roles/bigquery.studioAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`JOBS_BY_FOLDER`:** Requires `bigquery.jobs.listAll` on the parent folder.
*   **`JOBS_BY_ORGANIZATION`:** Requires `bigquery.jobs.listAll` on the
    organization.

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description & Conversion Formula |
| :--- | :--- | :--- | :--- |
| `cache_hit` | `BOOLEAN` | Boolean | Whether query results were served from cache. |
| `edition` | `STRING` | Enum | Target Edition tier (`'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`). |
| `error_result` | `RECORD` | Struct | Details of error (if any) as an `ErrorProto` (`reason`, `location`, `message`). |
| `job_creation_time` | `TIMESTAMP` | UTC Timestamp | (Partitioning column) Timestamp when job was submitted in UTC. |
| `job_end_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when job completed execution. |
| `job_id` | `STRING` | UUID | Unique job identifier (e.g. `bquxjob_1234`). |
| `job_start_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when compute resources began execution. |
| `job_type` | `STRING` | Enum | `'QUERY'`, `'LOAD'`, `'EXTRACT'`, `'COPY'`, or `NULL` (background). |
| `labels` | `ARRAY<RECORD>` | Struct Array | Array of key-value labels applied to the job. |
| `parent_job_id` | `STRING` | UUID | ID of the parent multi-statement query script, if any. |
| `period_estimated_runnable_units` | `INT64` | Count | Number of worker units ready to execute immediately but queued waiting for available slots. |
| `period_shuffle_ram_usage_ratio` | `FLOAT64` | Ratio (0.0–1.0) | Peak shuffle RAM utilization ratio during slice (0.0 if running on autoscaling with 0 baseline slots). |
| `period_slot_ms` | `INT64` | **Slot-ms** | Compute consumed within this 1-second slice. **Instantaneous Slots:** `period_slot_ms / 1000.0`. |
| `period_start` | `TIMESTAMP` | UTC Timestamp | Start time of this 1-second interval. |
| `principal_subject` | `STRING` | Principal | IAM principal subject string representation. |
| `priority` | `STRING` | Enum | Job scheduling priority: `'INTERACTIVE'` or `'BATCH'`. |
| `project_id` | `STRING` | Project ID | (Clustering column) ID of the project submitting the job. |
| `project_number` | `INT64` | Numeric ID | Numeric project number. |
| `reservation_group_path` | `ARRAY<STRING>` | Array | Hierarchical reservation group path (e.g. `['my-group']`). |
| `reservation_id` | `STRING` | Resource Path | Name of primary reservation assigned to job at end of period (`ADMIN_PROJECT:LOCATION.RESERVATION_NAME`). |
| `state` | `STRING` | Enum | Running state of the job at end of slice: `'PENDING'`, `'RUNNING'`, `'DONE'`. |
| `statement_type` | `STRING` | Enum | Statement category (e.g. `'SELECT'`, `'INSERT'`, `'UPDATE'`, `'DELETE'`). |
| `total_bytes_billed` | `INT64` | **Bytes** | Cumulative bytes billed by job up to slice (populated for completed jobs). |
| `total_bytes_processed` | `INT64` | **Bytes** | Cumulative bytes processed by job up to slice. |
| `transaction_id` | `STRING` | UUID | ID of the transaction in which this job ran, if any. |
| `user_email` | `STRING` | Email | (Clustering column) Email address or service account of the user who ran the job. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.SESSIONS_BY_USER` (and `_BY_PROJECT`)

#### High-Level Description

Lists multi-statement and interactive notebook sessions created by users and
service accounts. Tracks active session IDs, session lifetimes, and temporary
table allocations.

#### Required IAM Permissions & Predefined Roles

*   **`SESSIONS_BY_USER` (Least Privilege):** Requires `bigquery.jobs.list` on
    the project. Granted by **BigQuery User** (`roles/bigquery.user`),
    **BigQuery Job User** (`roles/bigquery.jobUser`), or **BigQuery Admin**
    (`roles/bigquery.admin`).
*   **`SESSIONS_BY_PROJECT`:** Requires `bigquery.jobs.listAll` on the project.
    Granted by **BigQuery Resource Viewer** (`roles/bigquery.resourceViewer`),
    **BigQuery Resource Admin** (`roles/bigquery.resourceAdmin`), or **BigQuery
    Admin** (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `session_id` | `STRING` | ID String | Unique session identifier. |
| `project_id` | `STRING` | Project ID | Project hosting the session. |
| `project_number` | `INT64` | Numeric ID | Numeric project identifier. |
| `user_email` | `STRING` | Email | User identity who initiated the session. |
| `principal_subject` | `STRING` | Principal | IAM principal subject. |
| `is_active` | `BOOLEAN` | Boolean | `TRUE` if the session is currently active and can receive new statements. |
| `creation_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when the session was created. |
| `expiration_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when the session expires and temp tables are dropped. |
| `last_modified_time` | `TIMESTAMP` | UTC Timestamp | Timestamp of the most recent query in this session. |
<!-- mdformat on -->

<a id="sec-reservations"></a>

## 2. Capacity, Reservations & Commitments Views

### `INFORMATION_SCHEMA.RESERVATIONS` (and `_BY_PROJECT`)

#### High-Level Description

Contains a near real-time list of all capacity reservations in the
administration project, including baseline slot allocations, autoscale limits,
Edition tiers, scaling modes, and disaster recovery replica locations.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.reservations.list` on the administration project.
*   **Predefined Roles:** **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), **BigQuery Resource Editor**
    (`roles/bigquery.resourceEditor`), **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery User**
    (`roles/bigquery.user`), or **BigQuery Admin** (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `autoscale.current_slots` | `INT64` | **Slots** | Real-time dynamically provisioned autoscale slots added to reservation. |
| `autoscale.max_slots` | `INT64` | **Slots** | Maximum configured autoscale slot ceiling. |
| `ddl` | `STRING` | SQL String | GoogleSQL DDL statement used to create this reservation. |
| `edition` | `STRING` | Enum | Edition tier: `'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`. |
| `ignore_idle_slots` | `BOOLEAN` | Boolean | When `FALSE`, reservation can borrow unused idle slots from other commitments. |
| `labels` | `ARRAY<RECORD>` | Struct Array | Array of key-value labels associated with the reservation. |
| `max_slots` | `INT64` | **Slots** | Total maximum slot limit (baseline + idle + autoscale) for reservation predictability. |
| `original_primary_location` | `STRING` | Region | Region where the reservation was originally created (for Disaster Recovery). |
| `primary_location` | `STRING` | Region | Current location of reservation's primary replica in Disaster Recovery. |
| `project_id` | `STRING` | Project ID | ID of the reservation administration project. |
| `project_number` | `INT64` | Numeric ID | Number of the administration project. |
| `reservation_group_path` | `ARRAY<STRING>` | Array | Reservation group hierarchy path (e.g. `['my-group']`). |
| `reservation_name` | `STRING` | Resource Path | User-provided reservation name. |
| `scaling_mode` | `STRING` | Enum | Scaling mode determining progression from baseline to `max_slots` (`'ALL_SLOTS'`, `'IDLE_SLOTS_ONLY'`, `'AUTOSCALE_ONLY'`, `'SCALING_MODE_UNSPECIFIED'`). |
| `secondary_location` | `STRING` | Region | Current location of reservation's secondary replica in Disaster Recovery. |
| `slot_capacity` | `INT64` | **Slots** | Baseline slot capacity configured for the reservation. |
| `target_job_concurrency` | `INT64` | Count | Target maximum concurrent queries before queueing (0 = dynamic auto-concurrency). |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.RESERVATION_CHANGES` (and `_BY_PROJECT`)

#### High-Level Description

Contains a near real-time audit log of all changes made to reservations within
the administration project (creation, modification of baseline/autoscale, and
deletion). This view contains current reservations and deleted reservations
(deleted reservations are kept for a maximum of 41 days after which they are
removed from the view).

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.reservations.list` on the administration project.
*   **Predefined Roles:** **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), **BigQuery Resource Editor**
    (`roles/bigquery.resourceEditor`), **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery User**
    (`roles/bigquery.user`), or **BigQuery Admin** (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `action` | `STRING` | Enum | Event action type: `'CREATE'`, `'UPDATE'`, `'DELETE'`. |
| `autoscale.current_slots` | `INT64` | **Slots** | Number of autoscale slots added to reservation at event time. |
| `autoscale.max_slots` | `INT64` | **Slots** | Maximum configured autoscale slot ceiling at event time. |
| `change_timestamp` | `TIMESTAMP` | UTC Timestamp | Timestamp when the reservation modification occurred. |
| `edition` | `STRING` | Enum | Edition tier: `'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`. |
| `ignore_idle_slots` | `BOOLEAN` | Boolean | Slot sharing status (`FALSE` allows borrowing idle capacity). |
| `labels` | `ARRAY<RECORD>` | Struct Array | Array of key-value labels associated with the reservation. |
| `max_slots` | `INT64` | **Slots** | Maximum slot limit for reservation predictability. |
| `original_primary_location` | `STRING` | Region | Location where reservation was originally created. |
| `primary_location` | `STRING` | Region | Location of primary replica in Disaster Recovery. |
| `project_id` | `STRING` | Project ID | ID of the administration project. |
| `project_number` | `INT64` | Numeric ID | Number of the administration project. |
| `reservation_group_path` | `ARRAY<STRING>` | Array | Reservation group hierarchy path. |
| `reservation_name` | `STRING` | Resource Path | User-provided reservation name. |
| `scaling_mode` | `STRING` | Enum | Scaling mode (`'ALL_SLOTS'`, `'IDLE_SLOTS_ONLY'`, `'AUTOSCALE_ONLY'`, `'SCALING_MODE_UNSPECIFIED'`). |
| `secondary_location` | `STRING` | Region | Location of secondary replica in Disaster Recovery. |
| `slot_capacity` | `INT64` | **Slots** | Baseline slot capacity configured at event time. |
| `target_job_concurrency` | `INT64` | Count | Target query concurrency limit. |
| `user_email` | `STRING` | Email | Administrator or service identity who initiated the change (`'google'` if automated). |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` (and `_BY_PROJECT`)

#### High-Level Description

Minute-by-minute discrete timeline of reservation capacity and autoscale
telemetry. Serves as the authoritative source for reconciling Edition
Pay-As-You-Go (PAYG) and baseline slot consumption against Cloud Billing
invoices. Retention is 180 days (and one row per minute with changes for older
records).

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.reservations.list` or `bigquery.reservations.get` on the
    administration project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), **BigQuery Resource Editor**
    (`roles/bigquery.resourceEditor`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description & Conversion Formula |
| :--- | :--- | :--- | :--- |
| `autoscale.current_slots` | `INT64` | **Slots** | Active autoscaled slots provisioned during the interval. |
| `autoscale.max_slots` | `INT64` | **Slots** | Maximum configured autoscaler limit ceiling. |
| `edition` | `STRING` | Enum | Target edition tier: `'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`. |
| `ignore_idle_slots` | `BOOLEAN` | Boolean | `FALSE` if slot sharing is enabled across commitments. |
| `is_creation_region` | `BOOLEAN` | Boolean | `TRUE` if current region is the original creation region where baseline reservation slots are billed. `FALSE` in secondary failover regions. |
| `labels` | `ARRAY<RECORD>` | Struct Array | Array of labels associated with the reservation. |
| `max_slots` | `INT64` | **Slots** | Total maximum slot limit for reservation predictability. |
| `period_autoscale_slot_seconds` | `INT64` | **Slot-seconds** | Cumulative dynamic autoscaled compute consumed in that 1-minute slice. **Formula for Billable Autoscale Slot-Hours:** `period_autoscale_slot_seconds / 3600.0`. |
| `period_start` | `TIMESTAMP` | UTC Timestamp | Start time of this 1-minute discrete interval. |
| `per_second_details` | `ARRAY<RECORD>` | Struct Array | Array of 60 per-second capacity and usage snapshots (`start_time`, `autoscale_current_slots`, `autoscale_max_slots`, `slots_assigned`, `slots_max_assigned`, `borrowed_slots`, `lent_slots`). |
| `project_id` | `STRING` | Project ID | ID of the reservation administration project. |
| `project_number` | `INT64` | Numeric ID | Numeric project ID. |
| `reservation_group_path` | `ARRAY<STRING>` | Array | Hierarchical reservation group path. |
| `reservation_id` | `STRING` | Resource Path | Formatted reservation path (`project_id:location.reservation_name`) for joining with `JOBS_TIMELINE`. |
| `reservation_name` | `STRING` | Resource Path | Name of the reservation. |
| `scaling_mode` | `STRING` | Enum | Scaling mode (`'ALL_SLOTS'`, `'IDLE_SLOTS_ONLY'`, `'AUTOSCALE_ONLY'`, `'SCALING_MODE_UNSPECIFIED'`). |
| `slot_capacity` | `INT64` | **Slots** | Total configured baseline slot capacity. **Formula for Billable Baseline Slots:** `IF(is_creation_region, slot_capacity, 0)`. |
| `slots_assigned` | `INT64` | **Slots** | Instantaneous active baseline allocation. Shifts to secondary region during DR failover events (for invoicing, use `slot_capacity` with `is_creation_region`). |
| `slots_max_assigned` | `INT64` | **Slots** | Maximum slot capacity for reservation including idle sharing (`slots_assigned` if `ignore_idle_slots = TRUE`). |
<!-- mdformat on -->

#### Nested `per_second_details` Schema (Field in `RESERVATIONS_TIMELINE`)

The `per_second_details` column is an `ARRAY<STRUCT>` providing 1-second
discrete capacity and usage snapshots within the 1-minute period:

*   `start_time` (`TIMESTAMP`): The exact UTC timestamp of the second.
*   `autoscale_current_slots` (`INT64`): Autoscaling slots available to the
    reservation at this second (excludes baseline slots). Reflects accurate
    second-by-second scaling when autoscaler adjusts multiple times within a
    minute.
*   `autoscale_max_slots` (`INT64`): Maximum autoscaling slots configured at
    this second (excludes baseline slots).
*   `slots_assigned` (`INT64`): Baseline slot capacity assigned to this
    reservation at this second.
*   `slots_max_assigned` (`INT64`): Maximum slot capacity including idle slot
    sharing (`slots_assigned` if `ignore_idle_slots = TRUE`).
*   `borrowed_slots` (`INT64`): Number of slots consumed from the shared idle
    slot pool. Populated only when `ignore_idle_slots = FALSE` and idle slots
    were used during this second.
*   `lent_slots` (`INT64`): Number of baseline slots borrowed by other
    reservations from this reservation's baseline pool. Populated only when
    `ignore_idle_slots = FALSE` and idle slots were shared during this second.

> [!NOTE] **Array Population Invariant:** When there are autoscale or
> reservation changes during the minute, `per_second_details` is populated with
> 60 elements (one per second). For steady-state reservations with no changes
> during that minute, `per_second_details` is an empty array to prevent
> redundant repeating data. To analyze second-level telemetry, use `LEFT JOIN
> UNNEST(per_second_details) AS s`.

### `INFORMATION_SCHEMA.CAPACITY_COMMITMENTS` (and `_BY_PROJECT`)

#### High-Level Description

Lists all currently active dedicated slot commitments, commitment plans, renewal
parameters, and remaining commitment lifecycles.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.capacityCommitments.list` or
    `bigquery.capacityCommitments.get` on the administration project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `capacity_commitment_id` | `STRING` | ID String | Unique commitment identifier string. |
| `commitment_plan` | `STRING` | Enum | Commitment duration tier: `'ANNUAL'`, `'THREE_YEAR'`. |
| `ddl` | `STRING` | SQL String | GoogleSQL DDL statement used to create this capacity commitment. |
| `edition` | `STRING` | Enum | Target Edition: `'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`. |
| `is_flat_rate` | `BOOLEAN` | Boolean | `TRUE` for legacy flat-rate commitments; `FALSE` for Edition commitments. |
| `project_id` | `STRING` | Project ID | ID of the administration project. |
| `project_number` | `INT64` | Numeric ID | Number of the administration project. |
| `renewal_plan` | `STRING` | Enum | Plan upon expiry: `'ANNUAL'`, `'THREE_YEAR'`, `'NONE'`. |
| `slot_count` | `INT64` | **Slots** | Dedicated capacity slot quantity. |
| `state` | `STRING` | Enum | Lifecycle state: `'PENDING'`, `'ACTIVE'`. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` (and `_CHANGES`)

#### High-Level Description

Complete audit log of all commitment purchase, modification, renewal, and
deletion lifecycle events. This view contains current capacity commitments and
deleted capacity commitments (deleted commitments are kept for a maximum of 41
days after which they are removed from the view). Used to construct
running-total historical capacity curves for CUD reconciliation.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.capacityCommitments.list` or
    `bigquery.capacityCommitments.get` on the administration project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `action` | `STRING` | Enum | Event action: `'CREATE'`, `'UPDATE'`, `'DELETE'`. Used with `LAG`/`LEAD` to compute point-in-time deltas. |
| `capacity_commitment_id` | `STRING` | ID String | Unique commitment identifier string. |
| `change_timestamp` | `TIMESTAMP` | UTC Timestamp | Timestamp when the commitment lifecycle event occurred. |
| `commitment_end_time` | `TIMESTAMP` | UTC Timestamp | Expiration timestamp when commitment plan expires or renews (`NULL` if not `ACTIVE`). |
| `commitment_plan` | `STRING` | Enum | Duration plan: `'ANNUAL'`, `'THREE_YEAR'`. |
| `commitment_start_time` | `TIMESTAMP` | UTC Timestamp | Timestamp when commitment became active (`NULL` if not `ACTIVE`). |
| `edition` | `STRING` | Enum | Target Edition: `'STANDARD'`, `'ENTERPRISE'`, `'ENTERPRISE_PLUS'`. |
| `failure_status` | `RECORD` | Struct | Failure reason for a `FAILED` commitment plan (`code`, `message`). |
| `is_flat_rate` | `BOOLEAN` | Boolean | `TRUE` for legacy flat-rate commitments; `FALSE` for Edition commitments. |
| `project_id` | `STRING` | Project ID | ID of the administration project. |
| `project_number` | `INT64` | Numeric ID | Number of the administration project. |
| `renewal_plan` | `STRING` | Enum | Plan upon expiry: `'ANNUAL'`, `'THREE_YEAR'`, `'NONE'`. |
| `slot_count` | `INT64` | **Slots** | Dedicated capacity slot quantity. |
| `state` | `STRING` | Enum | Lifecycle state: `'PENDING'`, `'ACTIVE'`, `'DELETED'`. |
| `user_email` | `STRING` | Email | Administrator or identity who initiated change (`'google'` if automated). |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.ASSIGNMENTS` (and `_BY_PROJECT`)

#### High-Level Description

Defines the active mapping of GCP organizations, folders, and projects to
capacity reservations. Controls which compute pool processes query, pipeline,
and ML workloads.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.reservationAssignments.list` or
    `bigquery.reservationAssignments.get` on the administration project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `assignee_id` | `STRING` | Resource Path | GCP resource path (`projects/123`, `folders/456`, `organizations/789`). |
| `assignee_number` | `INT64` | Numeric ID | Numeric assignee resource ID. |
| `assignee_type` | `STRING` | Enum | Resource level: `'PROJECT'`, `'FOLDER'`, `'ORGANIZATION'`. |
| `assignment_id` | `STRING` | ID String | Unique assignment identifier string. |
| `ddl` | `STRING` | SQL String | GoogleSQL DDL statement used to create this assignment. |
| `job_type` | `STRING` | Enum | Assigned traffic type: `'QUERY'`, `'PIPELINE'`, `'CONTINUOUS'`, `'ML_EXTERNAL'`, `'BACKGROUND'`. |
| `project_id` | `STRING` | Project ID | ID of the administration project. |
| `project_number` | `INT64` | Numeric ID | Number of the administration project. |
| `reservation_name` | `STRING` | Resource Path | Name of the reservation that the assignment uses. |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.ASSIGNMENT_CHANGES_BY_PROJECT` (and `_CHANGES`)

#### High-Level Description

Audit log of all assignment creation, update, and deletion events within the
administration project. This view contains current assignments and deleted
assignments (deleted assignments are kept for a maximum of 41 days after which
they are removed from the view).

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.reservationAssignments.list` on the administration
    project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `action` | `STRING` | Enum | Event type: `'CREATE'`, `'UPDATE'`, `'DELETE'`. |
| `assignee_id` | `STRING` | Resource Path | Unique ID of the assignee resource (`projects/123`, `folders/456`, `organizations/789`). |
| `assignee_number` | `INT64` | Numeric ID | Numeric assignee resource ID. |
| `assignee_type` | `STRING` | Enum | Resource type: `'PROJECT'`, `'FOLDER'`, `'ORGANIZATION'`. |
| `assignment_id` | `STRING` | ID String | Unique assignment identifier string. |
| `change_timestamp` | `TIMESTAMP` | UTC Timestamp | Timestamp when the change occurred. |
| `job_type` | `STRING` | Enum | Job type: `'QUERY'`, `'PIPELINE'`. |
| `project_id` | `STRING` | Project ID | ID of the administration project. |
| `project_number` | `INT64` | Numeric ID | Number of the administration project. |
| `reservation_name` | `STRING` | Resource Path | Name of the reservation that the assignment uses. |
| `state` | `STRING` | Enum | State of the assignment: `'PENDING'`, `'ACTIVE'`. |
| `user_email` | `STRING` | Email | Administrator or identity who made the change (`'google'` if automated). |
<!-- mdformat on -->

### `INFORMATION_SCHEMA.BI_CAPACITIES` (and `BI_CAPACITY_CHANGES`)

#### High-Level Description

Defines BI Engine memory capacity allocations and table routing preferences for
sub-second SQL acceleration.

#### Required IAM Permissions & Predefined Roles

*   Requires `bigquery.bireservations.get` on the project.
*   **Predefined Roles:** **BigQuery Resource Viewer**
    (`roles/bigquery.resourceViewer`), **BigQuery Resource Admin**
    (`roles/bigquery.resourceAdmin`), or **BigQuery Admin**
    (`roles/bigquery.admin`).

<!-- mdformat off -->
| Column Name | Data Type | Physical Unit | Description |
| :--- | :--- | :--- | :--- |
| `bi_capacity_name` | `STRING` | String | Name of the capacity object (always `'default'`). |
| `preferred_tables` | `ARRAY<STRING>` | Array | Set of preferred table paths for BI Engine caching (`NULL` = all tables in project). |
| `project_id` | `STRING` | Project ID | Project containing the BI Engine capacity. |
| `project_number` | `INT64` | Numeric ID | Project number containing the BI Engine capacity. |
| `size` | `INT64` | **Bytes** | BI Engine allocated RAM capacity in bytes. **GiB:** `size / POWER(1024, 3)`. |
| `change_timestamp` | `TIMESTAMP` | UTC Timestamp | (In `BI_CAPACITY_CHANGES`) Timestamp when the update was made. |
| `user_email` | `STRING` | Email | (In `BI_CAPACITY_CHANGES`) Administrator or service identity who made the change. |
<!-- mdformat on -->
