# BigQuery ML.DESCRIBE_DATA

`ML.DESCRIBE_DATA` generates descriptive statistics for the columns in a table
or subquery.

## Syntax Reference

```sql
SELECT
  *
FROM
  ML.DESCRIBE_DATA(
    { TABLE project.dataset.table | (QUERY_STATEMENT) },
    STRUCT(
      [NUM_QUANTILES AS num_quantiles]
      [, NUM_ARRAY_LENGTH_QUANTILES AS num_array_length_quantiles]
      [, TOP_K AS top_k])
  )
```

### Input Arguments

Argument                         | Requirement  | Type    | Description
:------------------------------- | :----------- | :------ | :----------
**`input_data`**                 | **Required** |         | The source table or subquery containing the data to analyze.
**`NUM_QUANTILES`**              | Optional     | `INT64` | Specifies the number of quantiles to return for numerical, `ARRAY<numerical>`, and `ARRAY<STRUCT<INT64, numerical>>` columns. This affects the number of results shown in the quantiles output column. These quantiles describe the distribution of the data in the column. Specify a lower value for coarser-grained distribution information and a higher value for finer-grained distribution information. The NUM_QUANTILES value must be in the range [1, 100,000]. The default value is 2.
**`NUM_ARRAY_LENGTH_QUANTILES`** | Optional     | `INT64` | Specifies the number of quantiles to return for ARRAY columns. This affects the number of results shown in the array_length_quantiles output column. These quantiles describe the distribution of the length of the arrays in the column. Specify a lower value for coarser-grained distribution information and a higher value for finer-grained distribution information. The NUM_ARRAY_LENGTH_QUANTILES value must be in the range [1, 100,000]. The default value is 10.
**`TOP_K`**                      | Optional     | `INT64` | Specifies the number of top values to return for categorical and `ARRAY<categorical>` columns. This affects the number of results shown in the top_values output column. The top values are the values that are shown most frequently in the column. The TOP_K value must be in the range [1, 10,000]. The default value is 1.

Input data for the `ML.DESCRIBE_DATA` function can only contain columns of the
following data types: Numeric types, `STRING`, `BOOL`, `BYTES`, `DATE`,
`DATETIME`, `TIME`, `TIMESTAMP`. It also supports `ARRAY` columns or `STRUCT`
columns that contain any of the previous primitive types. Columns with
unsupported data types, such as `GEOGRAPHY`, must be excluded from the input
data.

### Output Schema

Returns a table with one row per input column with the following fields:

Column Name                  | Type                           | Description
:--------------------------- | :----------------------------- | :----------
**`name`**                   | `STRING`                       | The name of the input column.
**`num_rows`**               | `INT64`                        | The total number of rows for the input column.
**`num_nulls`**              | `INT64`                        | The number of NULL values found in the column.
**`num_zeros`**              | `INT64`                        | The number of 0 values found in the column.
**`min`**                    | `STRING`                       | The MIN value for the numerical column.
**`max`**                    | `STRING`                       | The MAX value for the numerical column.
**`mean`**                   | `FLOAT64`                      | The Mean value for the numerical column.
**`stddev`**                 | `FLOAT64`                      | The standard deviation value calculated for the numerical column.
**`median`**                 | `FLOAT64`                      | The median value calculated for the numerical column.
**`quantiles`**              | `ARRAY<FLOAT64>`               | The quantiles in an input column.
**`unique`**                 | `INT64`                        | The number of unique values in an input column.
**`avg_string_length`**      | `FLOAT64`                      | The average length of the values in the categorical column.
**`num_values`**             | `INT64`                        | The number of array elements for ARRAY columns, and the number of values in the column for other types of columns.
**`top_values`**             | `ARRAY<STRUCT<STRING, INT64>>` | The top values and number of occurrences in an input column
**`min_array_length`**       | `INT64`                        | The minimum length of an array in the column.
**`max_array_length`**       | `INT64`                        | The maximum length of an array in the column.
**`avg_array_length`**       | `FLOAT64`                      | The average length of arrays in the column.
**`total_array_length`**     | `INT64`                        | The sum of the size of the arrays in the column.
**`array_length_quantiles`** | `ARRAY<INT64>`                 | The quantiles for the array length in an input column, as computed by the APPROX_QUANTILES function.
**`dimension`**              | `INT64`                        | The dimension of array elements for ARRAY columns.

## Examples

### Calculate statistics for a table

```sql
SELECT *
FROM ML.DESCRIBE_DATA(
  TABLE `bigquery-public-data.ml_datasets.penguins`
);
```
