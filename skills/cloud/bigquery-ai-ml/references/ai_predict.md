# BigQuery AI.Predict

`AI.PREDICT` leverages the pre-trained **TabFM** foundation model to perform
prediction (classification or regression) tasks on tabular data without the need
to train and manage custom models. Under the hood, this function applies an
In-Context Learning (ICL) approach: it embeds the training data to construct a
temporary model representation (kv cache) and uses it to predict labels for the
prediction data within the lifetime of a single query execution.

## Syntax Reference

```sql
SELECT
  *
FROM
  AI.PREDICT(
    { TABLE `project.dataset.training_table` | (TRAINING_QUERY) },
    { TABLE `project.dataset.prediction_table` | (PREDICTION_QUERY) }
    [, label_col => 'LABEL_COL']
    [, model => 'MODEL']
  )
```

### Input Arguments

| Argument               | Requirement  | Type     | Description        |
| :--------------------- | :----------- | :------- | :----------------- |
| **`training_table`**   | **Required** | Relation | The source table   |
:                        :              :          : or subquery        :
:                        :              :          : containing         :
:                        :              :          : training data.     :
:                        :              :          : This data MUST     :
:                        :              :          : contain the label  :
:                        :              :          : column. Only       :
:                        :              :          : Numerical (e.g.,   :
:                        :              :          : INT64, FLOAT64),   :
:                        :              :          : STRING, and BOOL   :
:                        :              :          : columns are        :
:                        :              :          : supported.         :
| **`prediction_table`** | **Required** | Relation | The source table   |
:                        :              :          : or subquery        :
:                        :              :          : containing         :
:                        :              :          : prediction data.   :
:                        :              :          : Every column in    :
:                        :              :          : the                :
:                        :              :          : `training_table`   :
:                        :              :          : (except the        :
:                        :              :          : `label_col`) MUST  :
:                        :              :          : exist in the       :
:                        :              :          : `prediction_table` :
:                        :              :          : with the exact     :
:                        :              :          : same               :
:                        :              :          : case-insensitive   :
:                        :              :          : name and matching  :
:                        :              :          : types. Only        :
:                        :              :          : Numerical (e.g.,   :
:                        :              :          : INT64, FLOAT64),   :
:                        :              :          : STRING, and BOOL   :
:                        :              :          : columns are        :
:                        :              :          : supported.         :
| **`label_col`**        | Optional     | String   | The name of the    |
:                        :              :          : label column in    :
:                        :              :          : the training data. :
:                        :              :          : Defaults to        :
:                        :              :          : `'label'`.         :
| **`model`**            | Optional     | String   | The model version. |
:                        :              :          : If specified, the  :
:                        :              :          : value MUST be the  :
:                        :              :          : literal `'TabFM    :
:                        :              :          : 1.0'`. Defaults to :
:                        :              :          : `'TabFM 1.0'`.     :

### Constraints & Limitations

> [!WARNING] **Same Table Split (Avoid Label Leakage)**: If you use the EXACT
> same table (or query) for both the `training_table` and `prediction_table`
> arguments, you MUST split the data into non-overlapping sets to avoid label
> leakage. You can use a helper column with `RAND() <= 0.8` to split the data
> (e.g., 80% for training, 20% for prediction).
>
> Example:
>
> ```sql
> WITH prepared_data AS (
>   SELECT *, RAND() <= 0.8 AS training
>   FROM `bigquery-public-data.ml_datasets.penguins`
>   WHERE body_mass_g > 0
> )
> SELECT
>   *
> FROM
>   AI.PREDICT(
>     # Training data
>     (SELECT * EXCEPT(training) FROM prepared_data WHERE training),
>     # Prediction data
>     (SELECT * EXCEPT(training) FROM prepared_data WHERE NOT training),
>     label_col => 'body_mass_g'
>   );
> ```

-   **Feature Column Limit**: The training and prediction data can include up to
    50 feature columns.
-   **Classification Category Limit**: For classification tasks, you can
    classify data into at most 10 different categories.
-   **Task Type Detection**:
    -   **CLASSIFICATION**: Automatically triggered if the label column is of
        type STRING or BOOL.
    -   **REGRESSION**: Automatically triggered if the label column is of a
        Numerical type.

### Output Schema

The output schema includes:

Column                                  | Type                                                    | Description
:-------------------------------------- | :------------------------------------------------------ | :----------
**`predicted_<label_col>`**             | STRING or BOOL (Classification) or Numeric (Regression) | The predicted label. The data type is the same as the label column in the training data.
**`predicted_<label_col>_probs`**       | ARRAY<STRUCT<label STRING, prob FLOAT64>>               | (Classification only) An array of structs containing `label` (STRING) and `prob` (FLOAT64) representing the probability of each class.
**All columns from `prediction_table`** | (As Input)                                              | All columns from the input `prediction_table` relation.

## Examples

### Classification Example (Inline Data)

```sql
SELECT *
FROM
  AI.PREDICT(
    (
      SELECT
        'Alice' AS customer,
        150.0 AS spend,
        2 AS calls,
        24 AS tenure,
        TRUE AS churned
      UNION ALL
      SELECT
        'Bob' AS customer,
        850.0 AS spend,
        1 AS calls,
        48 AS tenure,
        FALSE AS churned
    ),
    (
      SELECT
        'Bob' AS customer,
        850.0 AS spend,
        1 AS calls,
        48 AS tenure
      UNION ALL
      SELECT
        'Charlie' AS customer,
        200.0 AS spend,
        4 AS calls,
        12 AS tenure
    ),
    label_col => 'churned'
  );
```

### Classification Example (Tables)

```sql
SELECT *
FROM
  AI.PREDICT(
    TABLE `my_project.my_dataset.customer_train`,
    TABLE `my_project.my_dataset.customer_test`,
    label_col => 'churned'
  );
```

### Regression Example (Tables)

```sql
SELECT *
FROM
  AI.PREDICT(
    TABLE `my_project.my_dataset.housing_train`,
    TABLE `my_project.my_dataset.housing_test`,
    label_col => 'price'
  );
```

### Same Table Split Example (Regression)

If you must use the same table for both training and prediction, you MUST split
the data to avoid label leakage. This example predicts the numeric `body_mass_g`
column (Regression).

```sql
WITH prepared_data AS (
  SELECT *, RAND() <= 0.8 AS training
  FROM `bigquery-public-data.ml_datasets.penguins`
  WHERE body_mass_g > 0
)
SELECT
  *
FROM
  AI.PREDICT(
    # Training data
    (SELECT * EXCEPT(training) FROM prepared_data WHERE training),
    # Prediction data
    (SELECT * EXCEPT(training) FROM prepared_data WHERE NOT training),
    label_col => 'body_mass_g'
  );
```

### Same Table Split Example (Classification)

If you must use the same table for both training and prediction, you MUST split
the data to avoid label leakage. This example predicts the string `species`
column (Classification).

```sql
WITH prepared_data AS (
  SELECT *, RAND() <= 0.8 AS training
  FROM `bigquery-public-data.ml_datasets.penguins`
  WHERE species IS NOT NULL
)
SELECT
  *
FROM
  AI.PREDICT(
    # Training data
    (SELECT * EXCEPT(training) FROM prepared_data WHERE training),
    # Prediction data
    (SELECT * EXCEPT(species, training) FROM prepared_data WHERE NOT training),
    label_col => 'species'
  );
```
