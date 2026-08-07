# GCP Agent Security Audit Skill

## Overview
This skill provides proactive security auditing for AI Agents on Google Cloud Platform (GCP). It uses BigQuery to analyze agent interaction logs, detecting prompt injection patterns, behavioral anomalies, and potential data exfiltration attempts.

## Key Features
- **Pattern Detection:** Pre-configured SQL regex patterns to detect jailbreaks, indirect injection, and role overrides.
- **BigQuery Integration:** Uses BigQuery ML for anomaly detection and historical log analysis.
- **Real-Time Alerting:** Integrates with GCP Cloud Monitoring to notify security teams immediately via Pub/Sub.

## Requirements
- A GCP project with BigQuery enabled.
- Agent logs streamed to a BigQuery table.
- A Service Account with the following IAM roles:
  - `roles/bigquery.jobUser`
  - `roles/bigquery.dataViewer`
  - `roles/monitoring.metricWriter`

## Usage
Run the audit script manually using environment variables:
```bash
export GCP_PROJECT_ID="your-project-id"
export BIGQUERY_DATASET="your-dataset"
export BIGQUERY_TABLE="agent_logs"
python audit.py
