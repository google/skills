# Dialect and type behavior

Cross-database differences that cause validation findings, and how the tool
compares each type. Default aggregates per type are in the
[configuration reference](configuration.md#6-aggregates-and-tolerances);
compatibility notes and distance units are in the
[results reference](results.md).

## 1. How types are compared

Type family             | Row comparison                                    | Aggregates
:---------------------- | :------------------------------------------------ | :---------
Integer, decimal        | Signed difference                                 | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`
Floating point          | Signed difference; tiny noise may end as `HEALED` | `COUNT`, `MIN`, `MAX` (no `SUM`/`AVG` by default)
String                  | Edit distance                                     | `COUNT`, `SUM_LENGTH`
`DATE`                  | Days apart                                        | `MIN`, `MAX`, `COUNT`
`TIMESTAMP`, `DATETIME` | Microseconds apart                                | `MIN`, `MAX`, `COUNT`
`BOOLEAN`               | Equal or not                                      | `COUNT`, `COUNT_TRUE`, `COUNT_FALSE`, `COUNT_NULL`
`BYTES`                 | Equal or not (byte-level)                         | none by default
`JSON`                  | Equal or not                                      | none by default

## 2. Known dialect differences

Difference                    | Sources                                         | Symptom                                                            | Fix
:---------------------------- | :---------------------------------------------- | :----------------------------------------------------------------- | :--
Empty string stored as `NULL` | Oracle                                          | Column `COUNT` lower in source; one side `NULL`, other `''`        | `transform: EMPTY_TO_NULL`
Fixed-width `CHAR(n)` padding | Teradata, Oracle, SQL Server                    | `SUM_LENGTH` mismatch, edit distance equals pad length             | `transform: TRIM` (added automatically by `validation configure`)
Case-insensitive collation    | SQL Server, MySQL (default collations)          | Values differ only by case; string `MIN`/`MAX` differ              | `transform: UPPER`/`LOWER`; keep string `MIN`/`MAX` off
Time zone semantics           | All (`TIMESTAMP` with versus without time zone) | Constant timestamp distance (hours)                                | Align the BigQuery type (`TIMESTAMP` versus `DATETIME`) or use `transformExpression`
`NUMBER` without precision    | Oracle, Snowflake                               | `LOSSY_CONVERSION` or `NARROWED` to `NUMERIC`; large values differ | Use `BIGNUMERIC` in BigQuery or set a tolerance after checking values
Float versus exact decimal    | All                                             | Tiny numeric distances; `SUM` differs slightly                     | Column `tolerance`, or align types
Identifier case               | Snowflake, Oracle (uppercase) versus BigQuery   | Columns reported missing on one side                               | Map with `targetColumn`; check generated names
Large integers in floats      | All                                             | Integers above 2^53 differ after `INT64` to `FLOAT64`              | Keep integer types

Always confirm with row-level evidence (the
[investigation workflow](investigation.md)) before applying a fix. The same
symptom can come from a real data defect.
