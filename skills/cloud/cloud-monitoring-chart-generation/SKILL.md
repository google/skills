---
name: cloud-monitoring-chart-generation
metadata:
  category: CloudObservabilityAndMonitoring
description: >-
  Generates Google Cloud Monitoring Server-Driven UI (SDUI) Widget and
  XyChart Protocol Buffer textprotos from resolved PromQL queries.
  Use when:
    - Generating valid google.monitoring.dashboard.v1.Widget textprotos,
      containing PrometheusQuery datasets, for use with the Cloud Monitoring
      Dashboards API, gcloud CLI, or declarative dashboard definitions.
    - Synthesizing Server-Driven UI (SDUI) widget titles, axis labels, and
      plot types for Prometheus queries.
  Don't use for:
    - Metric discovery or PromQL query generation. For those tasks, use the
      cloud-monitoring-metric-selection or cloud-monitoring-promql-query skills.
---

# Cloud Monitoring Chart Generation Skill (`cloud-monitoring-chart-generation`)

Transforms PromQL queries and metric metadata into valid Server-Driven UI
(SDUI) `google.monitoring.dashboard.v1.Widget` Protocol Buffer textprotos.
These generated textprotos are designed to be ingested by the Cloud Monitoring
Dashboards API, gcloud CLI, or declarative dashboard provisioning pipelines.

> [!CAUTION]
> **CRITICAL EXECUTION & WORKING DIRECTORY RULES**:
> - **DO NOT CHANGE WORKING DIRECTORY**: Keep your working directory at your
>   workspace root. Do NOT `cd` into skill subdirectories.
> - **NO DISCOVERY OR SEARCH RULE**: The metric descriptor, PromQL query,
>   unit, and resource type are ALWAYS present in the conversation context.
>   **NEVER** run file or codebase search tools, such as grep, find, directory
>   listings, or codebase queries, to discover metric metadata or inspect
>   repository structures.
> - **SCRIPT EXECUTION**: Execute the bundled Python scripts directly using
>   python3, for example: `python3 scripts/assemble_widget_proto.py ...`.
> - **OUTPUT GENERATION**: The `assemble_widget_proto` script automatically
>   generates deterministic sequential filenames like `chart.textproto` and `chart_2.textproto`
>   and saves them to the active workspace. The script will handle naming and saving
>   automatically, and will print the generated filename to the console.

## Prerequisites: Environment Setup

Install the required dependencies in your environment or sandbox:

```bash
pip install -r scripts/requirements.txt
```

## 3-Stage Pipeline Workflow

```
[ Stage 1: compute_labels ]  --->  [ Stage 2: LLM Synthesis ]  --->  [ Stage 3: assemble_widget_proto ]
  Generates candidate labels         Formulates SemanticPlotSpec       Emits validated widget textproto
```

### Stage 1: Baseline Candidate Synthesis

Run Stage 1 using python3:

```bash
python3 scripts/compute_labels.py \
  --metric_display_name "METRIC_DISPLAY_NAME" \
  --resource_type "RESOURCE_TYPE" \
  --metric_unit "UNIT" \
  --promql_query "PROMQL_QUERY"
```

### Stage 2: SemanticPlotSpec Prediction (LLM)

Review the user prompt, PromQL query structure, and Stage 1 baseline
candidates to formulate a 4-key `SemanticPlotSpec` JSON object:

1. **`title`**: Polish `titleCandidate` to ensure it is concise, human-readable,
   and under 80 characters.
2. **`yAxisLabel`**: Set this to a concise, human-readable quantitative
   descriptor or metric concept, such as `"Utilization"`, `"Bytes"`, or
   `"Bytes Rate"`. Do NOT append unit symbols or suffixes such as `"(%)"`,
   `"(/s)"`, or `"(By)"` to the label, because units are rendered automatically
   via `unitOverride`.
3. **`plotType`**: Default to `LINE`. Use `STACKED_AREA` if requested by the
   user or for distribution queries.
4. **`unitOverride`**: Set this to the Unified Code for Units of Measure
   (UCUM) unit string, derived from the PromQL query by applying the **Unit
   Override Computation Rules** below.

#### Unit Override Computation Rules:
- **Rate Functions (`rate(...)`, `irate(...)`)**: Convert cumulative counters
  into per-second rates. Append `/s` to the raw metric unit. For example, a raw
  metric unit of `By` with `rate(...)` results in `unitOverride: "By/s"`.
- **Ratios & Percentages (`100 * ... / ...`)**: Ratios of identical metric
  units multiplied by 100 represent percentages, resulting in
  `unitOverride: "%"`.
- **Normalizations**: Normalize `10^2.%` to `"%"`, per the Unified Code for
  Units of Measure (UCUM) standard.
- **Preserved Units**: For aggregation functions like `avg_over_time(...)` or
  `sum by (...)`, retain and output the underlying metric unit without
  modification. For example, output `"%"`, `"By"`, or `"s"` unchanged.

- **Legend Template**: Do NOT configure the `legend_template` field. It is
  intentionally omitted so that the Cloud Monitoring frontend dynamically
  renders its multi-column table legend at runtime.

Example `SemanticPlotSpec`:
```json
{
  "title": "VM CPU Utilization (us-central1-a)",
  "yAxisLabel": "Utilization",
  "plotType": "LINE",
  "unitOverride": "%"
}
```

### Stage 3: Protobuf Assembly & Output

Run Stage 3 using python3 to generate and save the widget textproto:

```bash
python3 scripts/assemble_widget_proto.py \
  --promql_query "PROMQL_QUERY" \
  --spec_json 'SEMANTIC_PLOT_SPEC_JSON'
```

> [!IMPORTANT]
> **MANDATORY FILE OUTPUT CONTRACT**:
> The script automatically names and saves output files like `chart.textproto` and `chart_2.textproto` directly in your workspace root without subdirectories.

- **Assigned Filename Feedback**: Whenever an output file is saved, the script logs the file path to stderr, for example: `Wrote widget textproto to: .../chart.textproto`. Read your command execution logs for the exact filename created so you can target it in Stage 4 validation.
- **Text Chat Output**: Enclose the generated SDUI widget textproto inside a ```` ```textproto ```` code block in your response:

```textproto
title: "..."
xy_chart {
  ...
}
```

### Stage 4: Mandatory Self-Verification & Auto-Retry Loop

> [!CAUTION]
> **DO NOT FINISH YOUR TURN UNTIL FILE VERIFICATION PASSES**:
> 1. **Run Validation Check**: Execute the validator script against the
>    generated file, such as `chart.textproto` or the sequential filename like
>    `chart_2.textproto` output from Stage 3:
>    ```bash
>    python3 scripts/validate_chart.py --input_file "GENERATED_FILE.textproto"
>    ```
> 2. **Auto-Retry if Missing or Failed**: If `validate_chart` reports that the
>    file is missing or invalid, verify your script parameters and immediately re-run Stage 3:
>    ```bash
>    python3 scripts/assemble_widget_proto.py \
>      --promql_query "PROMQL_QUERY" \
>      --spec_json 'SEMANTIC_PLOT_SPEC_JSON'
>    ```
> 3. **Validation & Retries**: Run `validate_chart` to verify the generated
>    textproto. If validation fails due to a schema or syntax error, correct
>    the parameters and retry up to 2 times. If validation still fails after 2
>    retries, stop retrying, notify the user of the validation error, and
>    present the best-effort textproto.
> 4. **Execution vs. Validation Errors**: Note that schema/syntax validation
>    errors from `validate_chart.py` are distinct from OS or environment
>    execution restrictions, such as `Permission denied` or `Command not found`,
>    which are handled below in **Graceful Sandbox Fallback**.

#### Graceful Sandbox Fallback
If `compute_labels.py`, `assemble_widget_proto.py`, or `validate_chart.py`
cannot be executed due to environment or sandbox restrictions, do the
following:
1. Notify the user which script cannot be executed and why.
2. **Synthesize and output the complete widget textproto directly in your
   response**, following all formatting and unit rules.
3. Provide a **"Local Verification"** section containing the standalone python3
   commands so the user can run and validate the schema locally if desired.

## Supporting Links

- [Dashboards API](https://docs.cloud.google.com/monitoring/dashboards/api-dashboard)
- [Prometheus Docs](https://prometheus.io/docs/prometheus/latest/querying/)
