# BigQuery AI.Forecast

`AI.FORECAST` leverages the pre-trained **TimesFM** foundation model to generate
forecasts without the need to train and manage custom models.

It has two distinct modes, which take different arguments and return different
output schemas:

*   **Univariate** (`TimesFM 2.0`, `2.5`, `3.0`): forecasts a single target
    column, specified with `data_col`. See section 1.
*   **Multivariate** (`TimesFM 3.0` only): forecasts several target columns in
    one call, specified with `target_cols`, and optionally conditions on past
    and future covariate columns. See section 2.

`data_col` and `target_cols` are mutually exclusive. Pick the matching section
below and do not mix arguments or output columns between the two modes.

Choose the mode from the number of target columns, not from the model version.
For a single target column, use univariate `data_col`, including with
`TimesFM 3.0`. Never pass a one-element array to `target_cols`. The one
exception is covariates: `past_covariate_cols` and `future_covariate_cols` are
only available in multivariate mode, so a forecast that uses covariates must use
`target_cols` even when it has a single target column.

## 1. Univariate Forecasting

### 1.1 Syntax

```sql
SELECT
  *
FROM
  AI.FORECAST(
    { TABLE `project.dataset.table` | (QUERY_STATEMENT) },
    data_col => 'DATA_COL',
    timestamp_col => 'TIMESTAMP_COL'
    [, model => 'MODEL']
    [, id_cols => ID_COLS]
    [, horizon => HORIZON]
    [, confidence_level => CONFIDENCE_LEVEL]
    [, output_historical_time_series => OUTPUT_HISTORICAL_TIME_SERIES]
    [, context_window => CONTEXT_WINDOW]
  )
```

### 1.2 Input Arguments

Argument               | Requirement  | Type          | Description
:--------------------- | :----------- | :------------ | :----------
**`input_data`**       | **Required** |               | The source table or subquery containing historical data.
**`data_col`**         | **Required** | String        | The numeric column to predict.
**`timestamp_col`**    | **Required** | String        | The column containing dates/timestamps.
**`id_cols`**          | Optional     | Array<String> | Grouping columns for multiple series (e.g., `['store_id']`).
**`horizon`**          | Optional     | Int64         | Number of future points to predict. Defaults to 10. The valid input range is [1, 10,000] for `'TimesFM 2.0'` and `'TimesFM 2.5'`, and [1, 1024] for `'TimesFM 3.0'`
**`confidence_level`** | Optional     | Float64       | Confidence interval (0 to 1). Defaults to 0.95.
**`model`**            | Optional     | String        | Model version. Allowed options are `'TimesFM 2.0'`, `'TimesFM 2.5'`, and `'TimesFM 3.0'`, with `'TimesFM 2.5'` preferred.
**`context_window`**   | Optional     | Int64         | The number of historical data points the model uses to forecast. The min value is 64 and the max value is 2048 for `'TimesFM 2.0'`. The min value is 64 and the max value is 15360 for `'TimesFM 2.5'`. For `'TimesFM 3.0'` the value must be a multiple of 32 between 64 and 2048. If not set, the model determines this automatically.

### 1.3 Output Schema

The schema adjusts based on the `output_historical_time_series` flag.

Column                                | Type       | Included if output_historical_time_series=FALSE | Included if output_historical_time_series=TRUE | Description
:------------------------------------ | :--------- | :---------------------------------------------- | :--------------------------------------------- | :----------
**`id_cols`**                         | (As Input) | Yes                                             | Yes                                            | Original identifiers for the series.
**`forecast_timestamp`**              | TIMESTAMP  | **Yes**                                         | No                                             | Timestamp for predicted points.
**`forecast_value`**                  | FLOAT64    | **Yes**                                         | No                                             | The 50% quantile (median) prediction.
**`time_series_timestamp`**           | TIMESTAMP  | No                                              | **Yes**                                        | Uniform timestamp column for both history and forecast.
**`time_series_data`**                | FLOAT64    | No                                              | **Yes**                                        | Merged column: actual values for history, median for forecast.
**`time_series_type`**                | STRING     | No                                              | **Yes**                                        | Label: `'history'` or `'forecast'`.
**`prediction_interval_lower_bound`** | FLOAT64    | Yes                                             | Yes                                            | Lower bound (NULL for historical rows).
**`prediction_interval_upper_bound`** | FLOAT64    | Yes                                             | Yes                                            | Upper bound (NULL for historical rows).
**`confidence_level`**                | FLOAT64    | Yes                                             | Yes                                            | The constant confidence level used.
**`ai_forecast_status`**              | STRING     | Yes                                             | Yes                                            | Error messages or empty string on success. A minimum of 3 data points is required.

### 1.4 Examples

Univariate forecast returning history alongside the forecast:

```sql
WITH
  citibike_trips AS (
    SELECT EXTRACT(DATE FROM starttime) AS date, usertype, COUNT(*) AS num_trips
    FROM `bigquery-public-data.new_york.citibike_trips`
    GROUP BY date, usertype
  )
SELECT *
FROM
  AI.FORECAST(
    TABLE citibike_trips,
    data_col => 'num_trips',
    timestamp_col => 'date',
    id_cols => ['usertype'],
    horizon => 30,
    model => 'TimesFM 2.5',
    output_historical_time_series => true);
```

## 2. Multivariate Forecasting (TimesFM 3.0)

Multivariate forecasting predicts several target columns in a single call, and
can condition the forecast on covariate columns. It requires
`model => 'TimesFM 3.0'`.

Use this mode when there are two or more target columns, or when the forecast
conditions on `past_covariate_cols` or `future_covariate_cols`. For a single
target column without covariates, use section 1 instead.

### 2.1 Syntax

```sql
SELECT
  *
FROM
  AI.FORECAST(
    { TABLE `project.dataset.table` | (QUERY_STATEMENT) },
    target_cols => TARGET_COLS,
    timestamp_col => 'TIMESTAMP_COL',
    model => 'TimesFM 3.0'
    [, id_cols => ID_COLS]
    [, horizon => HORIZON]
    [, past_covariate_cols => PAST_COVARIATE_COLS]
    [, future_covariate_cols => FUTURE_COVARIATE_COLS]
    [, confidence_level => CONFIDENCE_LEVEL]
    [, output_historical_time_series => OUTPUT_HISTORICAL_TIME_SERIES]
    [, context_window => CONTEXT_WINDOW]
  )
```

### 2.2 Input Arguments

Argument                            | Requirement  | Type            | Description
----------------------------------- | ------------ | --------------- | -----------
**`input_data`**                    | **Required** | Table/Query     | The source table or subquery containing the data to forecast.
**`target_cols`**                   | **Required** | Array of String | The list of numeric target columns to predict simultaneously, for example `['num_trips', 'avg_duration']`. Must not be combined with `data_col`.
**`timestamp_col`**                 | **Required** | String          | The column containing dates/timestamps. Supported types are `TIMESTAMP`, `DATE`, and `DATETIME`.
**`model`**                         | **Required** | String          | Must be `'TimesFM 3.0'`.
**`id_cols`**                       | Optional     | Array of String | Grouping column names for multiple time series, for example `['store_id']`. The referenced columns in the source table can be `STRING` or `INT64`.
**`past_covariate_cols`**           | Optional     | Array of String | Historical-only covariate columns, for example `['foot_traffic']`. Values are only known over the historical period.
**`future_covariate_cols`**         | Optional     | Array of String | Covariate columns known in advance, for example `['is_holiday']`. Values must be populated across both the historical period and the forecast horizon.
**`horizon`**                       | Optional     | Int64           | Number of future time series points to predict. Defaults to 10. The valid range is `[1, 1024]`.
**`confidence_level`**              | Optional     | Float64         | Percentage of future values falling in the prediction interval. The valid range is `[0, 1)`. Defaults to 0.95.
**`output_historical_time_series`** | Optional     | Bool            | Determines whether input data is returned along with forecasted data. Defaults to `FALSE`.
**`context_window`**                | Optional     | Int64           | Number of historical points the model uses. Any multiple of 32 between 64 and 2048. Defaults to 2048.

### 2.3 Output Schema

The multivariate output returns one `STRUCT` column per entry in `target_cols`,
named after that target column:

Column                   | Type       | Description
------------------------ | ---------- | -----------
**`id_cols`**            | (As Input) | Original identifiers for the series.
**`<timestamp_col>`**    | TIMESTAMP  | Timestamp for the data point. Keeps the original name of the timestamp column from the input table, for example `date`.
**`<target_col>`**       | STRUCT     | One `STRUCT` per target column, with fields `value` (`FLOAT64`, the 50% quantile prediction, or the historical value when historical output is enabled), `prediction_interval_lower_bound` (`FLOAT64`, NULL for historical rows), and `prediction_interval_upper_bound` (`FLOAT64`, NULL for historical rows).
**`time_series_type`**   | STRING     | Included when `output_historical_time_series=TRUE`. Label of either `'history'` or `'forecast'`.
**`confidence_level`**   | FLOAT64    | The constant confidence level used. Defaults to 0.95.
**`ai_forecast_status`** | STRING     | Error messages, or an empty string on success.

Note that multivariate output keeps the original timestamp column name, while
univariate output renames it to `forecast_timestamp` or `time_series_timestamp`.

### 2.4 Examples

Forecasting two target columns at once, unnesting each `STRUCT`:

```sql
WITH
  citibike_trips AS (
    SELECT
      EXTRACT(DATE FROM starttime) AS date,
      usertype,
      COUNT(*) AS num_trips,
      AVG(tripduration) AS avg_duration
    FROM `bigquery-public-data.new_york.citibike_trips`
    GROUP BY date, usertype
  )
SELECT
  date,
  usertype,
  num_trips.value AS num_trips_forecast,
  num_trips.prediction_interval_lower_bound AS trips_lower_bound,
  num_trips.prediction_interval_upper_bound AS trips_upper_bound,
  avg_duration.value AS avg_duration_forecast,
  avg_duration.prediction_interval_lower_bound AS duration_lower_bound,
  avg_duration.prediction_interval_upper_bound AS duration_upper_bound
FROM
  AI.FORECAST(
    TABLE citibike_trips,
    target_cols => ['num_trips', 'avg_duration'],
    timestamp_col => 'date',
    id_cols => ['usertype'],
    horizon => 30,
    model => 'TimesFM 3.0');
```
