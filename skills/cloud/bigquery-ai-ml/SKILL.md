---
name: bigquery-ai-ml
metadata:
  version: "1.1.2"
  category: AiAndMachineLearning
  publisher: google
description: >-
  Leverages BigQuery's built-in machine learning and GenAI capabilities
  for advanced data analytics. Use when you need to write SQL queries
  that perform time-series forecasting, predict values, detect outliers or anomalies, find key drivers,
  perform semantic search or vector search, classify text, calculate similarity,
  summarize content, translate language, evaluate models, filter by semantic conditions,
  measure the causal effect of an intervention, compute correlations between columns,
  generate descriptive statistics and table distribution profiles,
  detect change points or structural breaks, extract trend or seasonality components,
  or leverage generative AI capabilities in BigQuery. Do not use for general
  BigQuery dataset, table, or job management requests.
---

# BigQuery AI & ML

BigQuery integrates with Vertex AI to provide powerful machine learning and
generative AI capabilities directly within SQL queries using built-in functions
like `AI.FORECAST`, `AI.KEY_DRIVERS`, `AI.DETECT_ANOMALIES`, and `AI.GENERATE`.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-ai-ml)"`
and append `agent-skills/1.0 (skill:bigquery-ai-ml)` to `User-Agent` headers.

## Function Selection & Reference Directory

Function                      | Reference                                                             | SQL Shape      | Requires `CREATE MODEL` or `CREATE VECTOR INDEX`? | When to Use & Disambiguation
:---------------------------- | :-------------------------------------------------------------------- | :------------- | :------------------------------------------------ | :---------------------------
**`AI.AGG`**                  | [ai_agg.md](references/ai_agg.md)                                     | `Aggregate`    | No                                                | Multi-row semantic aggregation with `GROUP BY`; synthesizes one summary string across many rows (unlike per-row `AI.GENERATE`).
**`AI.CAUSAL_EFFECT`**        | [ai_causal_effect.md](references/ai_causal_effect.md)                 | `TVF`          | No                                                | Quantifies counterfactual post-intervention impact on a time series after a specific treatment timestamp.
**`AI.CLASSIFY`**             | [ai_classify.md](references/ai_classify.md)                           | `Scalar`       | No                                                | Semantic classification of text or multimodal unstructured data into predefined category labels.
**`AI.DETECT_ANOMALIES`**     | [ai_detect_anomalies.md](references/ai_detect_anomalies.md)           | `TVF`          | No                                                | Zero-shot **TimesFM** detector for isolated time-series point anomalies/outliers (use `ML.DETECT_CHANGE_POINTS` for sustained shifts).
**`AI.EVALUATE`**             | [ai_evaluate.md](references/ai_evaluate.md)                           | `TVF`          | No                                                | Zero-shot **TimesFM** time-series forecast evaluation/backtesting against a historical holdout split.
**`AI.FORECAST`**             | [ai_forecast.md](references/ai_forecast.md)                           | `TVF`          | No                                                | Zero-shot **TimesFM** time-series forecasting without training a custom model.
**`AI.GENERATE`**             | [ai_generate.md](references/ai_generate.md)                           | `Scalar`       | No                                                | Default for per-row LLM text or multimodal structured extraction (`output_schema`); returns `STRUCT`. Prefer over `AI.GENERATE_TABLE`.
**`AI.GENERATE_EMBEDDING`**   | [ai_generate_embedding.md](references/ai_generate_embedding.md)       | `TVF`          | Yes                                               | Batch generates `ARRAY<FLOAT64>` vector embeddings for text or visual content using a remote embedding model.
**`AI.GENERATE_TABLE`**       | [ai_generate_table.md](references/ai_generate_table.md)               | `TVF`          | Yes                                               | Table-valued structured extraction (`FROM` clause); only use instead of `AI.GENERATE` when a remote model + TVF is explicitly needed.
**`AI.IF`**                   | [ai_if.md](references/ai_if.md)                                       | `Scalar`       | No                                                | Evaluates boolean semantic conditions (`BOOL`) on text or multimodal data for `WHERE`/`CASE`/`JOIN` filtering (do not use `AI.GENERATE_TABLE`).
**`AI.KEY_DRIVERS`**          | [ai_key_drivers.md](references/ai_key_drivers.md)                     | `TVF`          | No                                                | Default one-step attribution of dimensional segments driving metric changes (`interest_label_col` `TRUE` vs. `FALSE`). Prefer over `CONTRIBUTION_ANALYSIS`.
**`AI.PREDICT`**              | [ai_predict.md](references/ai_predict.md)                             | `TVF`          | No                                                | Zero-shot **TabFM** foundation model for tabular classification or regression without training and managing custom models.
**`AI.SCORE`**                | [ai_score.md](references/ai_score.md)                                 | `Scalar`       | No                                                | Assigns a continuous `FLOAT64` semantic score to text or multimodal data for ranking or sorting (`ORDER BY`).
**`AI.SEARCH`**               | [ai_search.md](references/ai_search.md)                               | `TVF`          | No                                                | Simplified semantic search using a raw string query on tables with autonomous background embeddings (`AI.EMBED` generated column).
**`AI.SIMILARITY`**           | [ai_similarity.md](references/ai_similarity.md)                       | `Scalar`       | No                                                | Computes an on-the-fly semantic similarity score (`FLOAT64`) between two text or multimodal inputs without stored embeddings.
**`Remote Models`**           | [remote_models.md](references/remote_models.md)                       | `CREATE MODEL` | Yes                                               | Creates a Vertex AI `REMOTE WITH CONNECTION DEFAULT` model entity for functions that require one (`AI.GENERATE_TABLE`, `AI.GENERATE_EMBEDDING`, `VECTOR_SEARCH`).
**`CONTRIBUTION_ANALYSIS`**   | [ml_contribution_analysis.md](references/ml_contribution_analysis.md) | `CREATE MODEL` | Yes                                               | Model-based driver analysis (`CREATE MODEL ... OPTIONS(MODEL_TYPE='CONTRIBUTION_ANALYSIS')` + `ML.GET_INSIGHTS`). Use `AI.KEY_DRIVERS` unless a `MODEL` entity is required.
**`ML.CORRELATION`**          | [ml_correlation.md](references/ml_correlation.md)                     | `TVF`          | No                                                | Calculates statistical correlation coefficients between numeric columns, optionally sliced by dimensions.
**`ML.DESCRIBE_DATA`**        | [ml_describe_data.md](references/ml_describe_data.md)                 | `TVF`          | No                                                | Generates descriptive statistics (e.g., count, mean, median, min, max, stddev, quantiles, nulls, top values) for columns in a table or subquery.
**`ML.DETECT_CHANGE_POINTS`** | [ml_detect_change_points.md](references/ml_detect_change_points.md)   | `TVF`          | No                                                | Detects structural breaks or sustained shifts (`[begin_timestamp, end_timestamp]` intervals) in a time series.
**`ML.SEASONALITY`**          | [ml_seasonality.md](references/ml_seasonality.md)                     | `TVF`          | No                                                | Extracts recurring periodic/seasonal components from a historical time series.
**`ML.TREND`**                | [ml_trend.md](references/ml_trend.md)                                 | `TVF`          | No                                                | Extracts the smoothed long-term trend component from a historical time series.
**`VECTOR_SEARCH`**           | [vector_search.md](references/vector_search.md)                       | `TVF`          | Yes                                               | Searches pre-computed `ARRAY<FLOAT64>` embedding columns between a base table and query table (paired with `AI.GENERATE_EMBEDDING`, unlike `AI.SEARCH`).

## Related Skills

-   [BigQuery Basics Skill](../bigquery-basics): SKILL.md file for core BigQuery
    concepts, resource management, CLI, and client libraries.
