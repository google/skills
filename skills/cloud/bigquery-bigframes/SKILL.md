---
name: bigquery-bigframes
metadata:
  category: BigDataAndAnalytics
description: >-
  Generates Python code using BigQuery DataFrames (BigFrames), the pandas/scikit-learn-style API over BigQuery. Use when writing BigFrames code or doing pandas-style dataframe/ML work against BigQuery (e.g. in a notebook). Don't use for SQL-first workflows or the google-cloud-bigquery client library — use bigquery-basics.
---

# BigFrames (BigQuery DataFrame) basics
BigFrames is a Python library that lets you take advantage of BigQuery
data processing by using familiar Python APIs.

## Dataframe API best practices
* **Stay in the Cloud**: Perform data cleaning, transformation, and analysis
  via BigFrames methods to leverage BigQuery's scale rather than downloading
  data.
* **Prefer partial ordering mode**: Enable partial ordering mode right after
  importing BigFrames. This speeds up data processing significantly by relaxing
  row-sequence constraints.
  ```python
  import bigframes.pandas as bpd
  bpd.options.bigquery.ordering_mode = 'partial'
  ```
* **Use `peek()` for data preview**: Use `peek(n)` to preview data instead of
  `head(n)`. `peek(n)` randomly samples `n` rows and is significantly faster.
  `head(n)` returns rows in strict order and fails in `partial` ordering mode
  unless the DataFrame has been explicitly sorted.
* **Avoid materializing data locally**: Methods like `to_pandas()` download all
  data to client memory, bypassing BigQuery’s distributed computation and
  risking Out of Memory (OOM) errors. Do not materialize data locally unless:
  * The dataset is small enough to fit safely in memory.
  * An error message explicitly requires local materialization.
* **Prefer Dataframe API over SQL queries**: Do not write raw SQL queries via
  `read_gbq()` if a DataFrame/Series method achieves the same result, as it
  breaks the Pandas abstraction and prevents lazy query execution.
* **Accessors over UDFs/Lambdas**:
    * Use built-in accessors (e.g., `df.col.str.*`, `df.col.dt.*`) instead of
      remote User Defined Functions (UDFs). UDFs require extra resources and
      time to deploy.
    * Do not use lambdas with `Series.map()` or `DataFrame.apply()`. These
      methods do not accept functions without `udf` or `remote_function`
      decorators.
    ```python
    # Avoid:
    df["upper"] = df["name"].map(lambda x: x.upper())

    # Prefer:
    df["upper"] = df["name"].str.upper()
    ```
* **Schema Verification**: Do not assume the schema of intermediate outputs.
  Proactively verify schemas using `.dtypes` and inspect sample records using
  `display()` with `.peek()`.
* **Visualization**: Plot directly from the BigFrames DataFrame/Series when
  possible. BigFrames is compatible with Matplotlib and Seaborn. If direct
  plotting fails, use the `.plot` accessor. If the dataset is too large to plot,
  aggregate or sample the data before calling
  `.to_pandas()` to plot locally.

## Machine Learning
* **Use `bigframes.bigquery.ml` package**: Do not use Scikit-learn or other ML
  libraries with BigQuery DataFrames. Standard Scikit-learn models require
  bringing data into local client memory, whereas `bigframes.bigquery.ml`
  delegates training directly to BigQuery's scalable ML engine. Import functions
  from `bigframes.bigquery.ml`.

### Reference Directory
* [Linear Regression](references/linear_regression.md): Train a linear
  regression model to predict numerical values.
* [Logistic Regression](references/logistic_regression.md): Train a logistic
  regression model to predict boolean values.

## BigFrames ML (Legacy)

The BigFrames ML package (`bigframes.ml`) is a legacy package that mimics the
scikit-learn API but is no longer recommended for new projects. Only use this
package if the user explicitly requests BigFrames ML.

* **Legacy Imports**: When legacy BigFrames ML is requested, import tools and
  classes from `bigframes.ml` instead of `bigframes.bigquery.ml`.
* **DataFrame Return on Prediction**: Unlike Scikit-learn, BigFrames'
  `predict()` method always returns a **DataFrame** containing both predictions
  and features, rather than a single series of predictions.
* **No `random_state`**: Do not pass a `random_state` argument when
  instantiating BigFrames ML models, as this parameter is not supported in the
  BigFrames ML package.
* **Automatic Scaling**: Do not use `OneHotEncoder` or `StandardScaler` unless
  explicitly requested, as scaling is handled automatically.
* **Hyperparameter Tuning**: Write custom loops for hyperparameter tuning, as
  BigFrames lacks `GridSearchCV` or `RandomizedSearchCV`.
* **ARIMA Plus** (Forecasting):
    * Import from `bigframes.ml.forecasting`.
    * Sort data chronologically and split around a timepoint before training.
    * Ensure the prediction horizon is less than or equal to the training
      horizon.
* **PCA**: BigFrames' PCA class lacks a `transform()` method. Use `predict()`
  instead.
* **Model Persistence**: To persist a model, use `model.to_gbq()`. To load a
  persisted model, use `bpd.read_gbq_model()`.
