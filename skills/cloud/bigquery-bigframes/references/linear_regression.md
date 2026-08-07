# BigQuery DataFrame Linear Regression

This example trains a linear regression model to predict the weight of penguins.

```python
import bigframes.pandas as bpd
import bigframes.bigquery as bbq

PROJECT_ID = 'my_project'
DATASET_ID = 'my_dataset'

bpd.options.bigquery.project = PROJECT_ID
bpd.options.bigquery.ordering_mode = 'partial'

# Data Loading
df = bpd.read_gbq("bigquery-public-data.ml_datasets.penguins")

# Data Cleaning
adelie_data = df[df.species == "Adelie Penguin (Pygoscelis adeliae)"]
adelie_data = adelie_data.drop(columns=["species"])
training_data = adelie_data.dropna()

# Use `ml.create_model` function from the `bbq` package to train a model.
model_name = f"{PROJECT_ID}.{DATASET_ID}.penguin_weight"
model_metadata = bbq.ml.create_model(
    model_name,
    replace=True,
    options={
        "model_type": "LINEAR_REG",
    },
    # Explicitly identify the column for prediction
    training_data=training_data.rename(columns={"body_mass_g": "label"})
)
print(model_metadata)

# Use `ml.evaluate` function from the `bbq` package for model evaluation
evaluation = bbq.ml.evaluate(model_name)
print(evaluation)

# Use `ml.predict` function from the `bbq` package for data prediction
df = bpd.read_gbq("bigquery-public-data.ml_datasets.penguins")
biscoe = df[df["island"].str.contains("Biscoe")]
predictions = bbq.ml.predict(model_name, biscoe)
print(predictions)
```