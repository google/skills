# Bigtable CLI Data Access

This document provides patterns for reading and writing data in Bigtable using
the `cbt` CLI. This is primarily used for debugging and quick data validation.

## Configuring cbt for Data Access

```bash
echo project = ${BIGTABLE_PROJECT} > ~/.cbtrc
echo instance = ${BIGTABLE_INSTANCE} >> ~/.cbtrc
```

## Reading Data

### Read Single Row (Lookup)

Reads all columns and versions for a specific row.

```bash
cbt lookup {table_name} {row_key}
```

*Note: `cbt lookup` is optimized for point reads and is significantly more
efficient than using `cbt read` with a count or filter for retrieving a single
known row.*

### Read N Rows

Reads the first `N` rows from the table.

```bash
cbt read {table_name} count={n}
```

### Read Range

Reads rows between `START_KEY` (inclusive) and `END_KEY` (exclusive).

```bash
cbt read {table_name} start={start_key} end={end_key}
```

### Read using SQL

For complex queries and aggregations use SQL via the `cbt sql` command

```bash
cbt sql "SELECT * FROM my_table WHERE _key = 'user#123'"
```

### Row Count (Estimate)

Provides an estimate of the number of rows in the table.

```bash
gcloud bigtable instances tables describe {table_id}  --instance={instance_id} --view stats
```

**Note**: cbt count {table_name} would do a full table scan.

## Writing Data

### Write Cell (Set)

Writes a value to a specific cell (row, family, and column).

```bash
cbt set {table_name} {row_key} {family}:{column}={value}
```

*Example:* `cbt set my-table user123 profile:email=user@example.com`

## Deleting Data

### Delete Row

```bash
cbt deleterow {table_name} {row_key}
```
