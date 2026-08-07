# BigQuery DataFrame Logistic Regression

This example trains a logistic regression model to predict the species of 
penguins.

```python
import bigframes.pandas as bpd
import bigframes.bigquery as bbq

PROJECT_ID = 'my_project'
DATASET_ID = 'my_dataset'

bpd.options.bigquery.project = PROJECT_ID
bpd.options.bigquery.ordering_mode = 'partial'

# Data Loading
df = bpd.read_gbq("bigquery-public-data.ml_datasets.penguins").dropna()
df['is_adelie'] = df['species'] == "Adelie Penguin (Pygoscelis adeliae)"
df = df.drop(columns=['species'])

# Use `ml.create_model` function from the `bbq` package to train a model.
model_name = f"{PROJECT_ID}.{DATASET_ID}.penguin_species"
model_metadata = bbq.ml.create_model(
    model_name,
    replace=True,
    options={
        "model_type": "LOGISTIC_REG",
    },
    # Explicitly identify the column for prediction
    training_data=df.rename(columns={"is_adelie": "label"})
)
print(model_metadata)

# Use `ml.evaluate` function from the `bbq` package for model evaluation
evaluation = bbq.ml.evaluate(model_name)
print(evaluation)
```