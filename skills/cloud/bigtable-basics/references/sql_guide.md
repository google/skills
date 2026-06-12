# Bigtable SQL Guide for Agents

This document outlines key aspects of Google Bigtable's SQL dialect which
extends GoogleSQL to support a multi-version wide-column data model. Bigtable
currently only supports SELECT statements over single tables i.e. JOIN and UNION
operations are not supported with the exception of JOINs with UNNEST(array) to
support working with nested objects.

## Table of Contents

*   [Bigtable SQL Data Structures](#bigtable-sql-data-structures) [L19-L190]
    *   [Columns](#columns) [L21-L42]
    *   [Primitive types](#primitive-types) [L43-L65]
    *   [Timestamps](#timestamps) [L66-L124]
    *   [Row keys](#row-keys) [L125-L157]
    *   [Maps](#maps) [L158-L164]
    *   [Protocol buffers (protos)](#protocol-buffers-protos) [L165-L181]
    *   [Functions and operators](#functions-and-operators) [L182-L190]

## Bigtable SQL Data Structures

### Columns

Unless table metadata indicates otherwise, columns are of **Map type** which
hold versioned key-value pairs. In legacy Bigtable APIs, SQL maps correspond to
**column families**.

*   **Access Pattern:** You cannot select a column directly as a scalar value.
    You must access the specific key within the column family.
*   **Correct Syntax Example:**

    ```sql
    -- CORRECT: Use map-like bracket notation for the column qualifier.
    SELECT cf1['text'] FROM messages;
    ```

*   **Incorrect Syntax Example:**

    ```sql
    -- INCORRECT: Dot notation is not supported and will fail.
    SELECT cf1.text FROM messages;
    ```

### Primitive types

There is often no type information associated with column values. You should
infer the type from the name of the column and include an explicit cast in
generated SQL queries.

*   *Example:* `SELECT CAST(info['address'] AS STRING) AS address FROM
    table_name`
*   *Example:* `SELECT CAST(CAST(info['age'] AS STRING) AS INT64) AS age FROM
    table_name`
*   *Example:* `SELECT SAFE_CAST(info['address'] AS STRING) FROM table_name;`
*   *Example:* `SELECT TO_INT64(cf['age']) as age FROM table_name`
*   *Example:* `SELECT CAST(CAST(cf['checkin_date'] AS STRING) AS DATE) AS
    checkin_date FROM table_name`
*   *Example:* `SELECT TIMESTAMP(CAST(CAST(cf['checkin_date'] AS STRING) AS
    DATE)) AS checkin_date_time FROM table_name`
*   *Example:* `SELECT CAST(CAST(cf['is_booked'] AS STRING) AS BOOL) AS
    is_booked FROM table_name` - if "true" or "false" was stored
*   *Example:* `SELECT CAST(TO_INT64(cf['is_booked']) AS BOOL) AS is_booked FROM
    table_name` - if 1 or 0 was stored`
*   *Example:* `SELECT CAST(SAFE_CONVERT_BYTES_TO_STRING(cf['is_booked']) AS
    BOOL) AS is_booked from table_name`, if "true" or "false" was stored

### Timestamps

By default Bigtable returns the **latest value** of each column when use with a
standard SELECT statement. You can use different flags explained below to get
prior versions. Using any flag other than "as_of" and "with_history => FALSE"
will return timestamp-value pairs. SQL interface exposes Bigtable timestamps as
SQL TIMESTAMP type. This section doesn't contain the exhaustive list of all
version management flags, for more details refer to the Google Cloud
documentation.

*   **Access Pattern:** To retrieve values as of a certain point in time (on or
    immediately prior to the provided timestamp), use the as_of flag.

```sql
SELECT * FROM table_name(as_of => TIMESTAMP("2025-03-28 14:13:40-0400"))
```

--------------------------------------------------------------------------------

*   **Access Pattern:** To retrieve all versions treat table name as a
    table-valued function and set the with_history flag to TRUE.

```sql
SELECT * FROM table_name(with_history => TRUE)
```

--------------------------------------------------------------------------------

*   **Access Pattern:** To retrieve last 5 versions treat table name as a
    table-valued function and use the with_history flag.

```sql
SELECT * FROM table_name(with_history => TRUE, latest_n => 5)
```

--------------------------------------------------------------------------------

*   **Access Pattern:** To retrieve a range of timestamps treat table name as a
    table-valued function and use the before, after, after_or_equal, and
    before_or_equal flags.

```sql
SELECT * FROM table_name(with_history => true, after => TIMESTAMP("2025-03-28 14:13:40-0400"), before_or_equal => TIMESTAMP("2025-03-28 14:15:10-04:00"))
```

--------------------------------------------------------------------------------

*   **Access Pattern:** Convert timestamped values into a flat table and perform
    time bucketing and aggregations.

```sql
SELECT TIMESTAMP_TRUNC(_timestamp, HOUR) AS hourly, AVG(temp_versioned) AS average_temperature FROM
UNPACK((SELECT metrics['temperature'] AS temp_versioned FROM sensorReadings(with_history => true, after => TIMESTAMP('2023-01-14T23:00:00.000Z'), before => TIMESTAMP('2023-01-21T01:00:00.000Z'))
WHERE _key LIKE 'sensorA%'))
GROUP BY 1
```

--------------------------------------------------------------------------------

### Row keys

Each Bigtable row is identified with a unique key. Bigtable SQL interface has a
pseudo-column named **_key** that should to query by row key.

#### Standard Scans (Opaque Key)

Success with Bigtable depends on translating logical queries into efficient
physical scans.

*   **Point Lookup:** `SELECT * FROM table_name WHERE _key = 'row_key'`
*   **Prefix Scan:** `SELECT * FROM table_name WHERE STARTS_WITH(_key,
    'prefix#')`
*   **Range Scan:** `SELECT * FROM table_name WHERE _key >= 'start#key' AND _key
    < 'end#key'`
*   **Fuzzy Match:** `SELECT * FROM table_name WHERE _key LIKE '%#pattern#%'`
    **(Warning: Causes full table scan)**

#### Querying with Structured Row Keys

If a **Structured Row Key** is defined for the table (see `schema_design.md`),
you can reference segments directly by name in the `WHERE` clause. This allows
for cleaner, more expressive queries.

*   **Syntax:** `SELECT * FROM table_name WHERE segment_name = 'value'`
*   **Example:** If your structure defines `tenant_id` and `timestamp`, you can
    query: `SELECT * FROM table_name WHERE tenant_id = '123' AND timestamp >
    1713300000`

**Agent Action:** When generating queries that are not looking for exact matches
(point lookups), key ranges, or prefixes, warn the user that the query will
result in a full table scan.

### Maps

Inspect qualifiers within a column family.

*   *Example:* `SELECT MAP_KEYS(cf1) FROM table_name`
*   *Example:* `SELECT MAP_ENTRIES(cf1) FROM table_name`

### Protocol buffers (protos)

Some users prefer to serialize data to protobufs and store them as blobs in
Bigtable. Protobufs reduce the storage footprint and are often faster to read,
advantageous for data that is not frequently updated. Protobufs can be directly
queried using SQL after their schemas are registered using `gcloud bigtable
schema-bundles create`.

*   **Example:** If you have `profile` proto that has attributes `user_name`,
    `gender` and `birth_year` registered under `accounts` bundle with
    package_name `publisher` stored under family `user`, column qualifier `info`
    you can query:

    ```sql
    SELECT CAST(user['info'] AS accounts.publisher.profile).user_name FROM accounts;
    ```

### Functions and operators

Bigtable offers a wide range of
[SQL functions](https://docs.cloud.google.com/bigtable/docs/reference/sql/functions-all)
and
[operators](https://docs.cloud.google.com/bigtable/docs/reference/sql/operators)
and
[conditional expressions](https://docs.cloud.google.com/bigtable/docs/reference/sql/conditional_expressions).
