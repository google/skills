# Basic Alerting Policies for Cloud Run

This document provides examples for generating Google Cloud Observability
Alerting Policies for Cloud Run.

The examples in this file use placeholders between `<` and `>`, e.g.
`<SERVICE_NAME>`. Replace these placeholders with the actual values when
generating the JSON.

The Alert Policy Schema is defined at
https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.alertPolicies.

## Table of Contents

*   [Cloud Run Service](#cloud-run-service) (Lines 19-107)
    *   [High Error Rate](#high-error-rate) (Lines 21-68)
    *   [Latency](#latency) (Lines 70-107)

## Cloud Run Service

### High Error Rate

This alerting policy monitors the percentage of 5xx server errors relative to
total traffic for a specific Cloud Run service.

*   **Metric (Ratio)**:
    *   **Numerator**: `run.googleapis.com/request_count` filtered for `5xx`
        response codes.
    *   **Denominator**: `run.googleapis.com/request_count` (total requests).
*   **Aggregation**: Uses `ALIGN_RATE` over a 1-minute period (`60s`) for both
    numerator and denominator.
*   **Threshold**: Triggered if the ratio (5xx errors / total requests) exceeds
    **0.05 (5%)** (`thresholdValue: 0.05`) for a duration of 5 minutes (`300s`).

```json
{
  "displayName": "<SERVICE_NAME> 5xx Error Rate > 5%",
  "conditions": [
    {
      "displayName": "5xx Error Ratio > 5%",
      "conditionThreshold": {
        "filter": "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"<SERVICE_NAME>\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\"",
        "denominatorFilter": "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"<SERVICE_NAME>\" AND metric.type = \"run.googleapis.com/request_count\"",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_RATE"
          }
        ],
        "denominatorAggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_RATE"
          }
        ],
        "comparison": "COMPARISON_GT",
        "duration": "300s",
        "trigger": {
          "count": 1
        },
        "thresholdValue": 0.05
      }
    }
  ],
  "combiner": "OR",
  "enabled": true
}
```

### Latency

This alerting policy monitors the 95th percentile (p95) of request latencies for
a specific Cloud Run service.

*   **Metric**: `run.googleapis.com/request_latencies` (Distribution metric)
*   **Aggregation**: Uses `ALIGN_PERCENTILE_95` over a 1-minute period (`60s`)
    to calculate the p95 latency.
*   **Threshold**: Triggered if the p95 latency exceeds **1 second (1000 ms)**
    (`thresholdValue: 1000`) for a duration of 10 minutes.

```json
{
  "displayName": "<SERVICE_NAME> p95 Latency > 1s",
  "conditions": [
    {
      "displayName": "p95 Latency > 1s",
      "conditionThreshold": {
        "filter": "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"<SERVICE_NAME>\" AND metric.type = \"run.googleapis.com/request_latencies\"",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_PERCENTILE_95"
          }
        ],
        "comparison": "COMPARISON_GT",
        "duration": "600s",
        "trigger": {
          "count": 1
        },
        "thresholdValue": 1000
      }
    }
  ],
  "combiner": "OR",
  "enabled": true
}
```
