# BigQuery Change History

BigQuery change history lets you track the history of changes made to a BigQuery
table. You can use SQL functions to see particular types of changes made during
a specified time range, so that you can process incremental changes made to a
table. Understanding what changes have been made to a table can help you do
things like incrementally maintain a table replica outside of BigQuery while
avoiding costly copies.

BigQuery provides two functions to track table modifications. The
`APPENDS` function returns all rows appended to a table for a given time range,
while the `CHANGES` function returns all rows that have changed in a table for a
given time range, including inserts, updates, and deletes.

## Enabling Change History

To use the `CHANGES` function on a table, you must set the table's
`enable_change_history` option to `TRUE`. The `APPENDS` function does not
require this option to be set.

```sql
ALTER TABLE `my_project.my_dataset.my_table`
SET OPTIONS (enable_change_history = TRUE);
```

## Querying Change History

Note: Timestamp arguments can be strings in the format `YYYY-MM-DD HH:MM:SS` or
`TIMESTAMP` objects.

### APPENDS function

The `APPENDS` function returns all rows appended to a table for a given time
range.

```sql
SELECT
  *,
  _CHANGE_TYPE AS change_type,
  _CHANGE_TIMESTAMP AS change_time
FROM
  APPENDS(TABLE `my_dataset.my_table`, '2023-12-31 08:00:00', '2023-12-31 12:00:00');
```

### CHANGES function

The `CHANGES` function returns all rows that have changed in a table for a given
time range. This includes inserts, updates, and deletes.

```sql
SELECT
  *,
  _CHANGE_TYPE AS change_type,
  _CHANGE_TIMESTAMP AS change_time,
  _CHANGE_IS_FOR_UPDATE as change_is_for_update
FROM
  CHANGES(TABLE `my_dataset.my_table`, '2023-12-31 08:00:00', '2023-12-31 12:00:00');
```

**Key Output Columns:**

-   `_CHANGE_TYPE`: A `STRING` value indicating the type of change (`INSERT`,
    `UPDATE`, `DELETE`).
-   `_CHANGE_TIMESTAMP`: A `TIMESTAMP` value indicating the commit time of the
    transaction that made the change.
-   `_CHANGE_IS_FOR_UPDATE`: A `BOOL` value that is `TRUE` for a `DELETE` event
    produced by a row update. Otherwise, the value is `FALSE` (only present in
    `CHANGES`).

## Limitations

For a full list of constraints, such as unsupported table types and time range
limits, please refer to the public documentation for BigQuery change
history:
https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/time-series-functions.md.txt
