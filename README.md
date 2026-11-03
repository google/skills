# Agent Skills

[![Install via skills.sh](https://img.shields.io/badge/skills.sh-install-green)](https://skills.sh/google/skills)

This repository contains [Agent Skills](https://agentskills.io/home) for Google
products and technologies, including [Google Cloud](https://cloud.google.com).

## Installation

```bash
npx skills add google/skills
```

When prompted, select specific skills or all skills, the target agents to
configure, and the installation scope (project or global).

If `npx` is not available in your environment, install
[Node.js](https://nodejs.org/en/download), which includes `npm` and `npx`.

## Updating Skills

To update previously installed skills to the latest versions, run the following
command.

```bash
npx skills update
```

This command gives you an option to also remove obsolete skills.

## Available Skills

<!-- BEGIN SKILLS -->
- **Getting started with Google Cloud**
  - [**Authenticating and Authorizing to Google Cloud (IAM)**](./skills/cloud/google-cloud-recipe-auth)
  - [**Google Cloud Recipe: Foundation Builder**](./skills/cloud/google-cloud-recipe-foundation-builder)
  - [**Onboarding to Google Cloud**](./skills/cloud/google-cloud-recipe-onboarding)
- **Multi-product solution skills**
  - [**Google Cloud solution-architecture workflow**](./skills/cloud/google-cloud-solution-architecture)
  - [**Agent Gateway multi-agent security**](./skills/cloud/google-cloud-solution-multi-agent-security)
  - [**Agentic analytics across cloud providers and data types**](./skills/cloud/google-cloud-solution-agentic-analytics-spark-knowledge-catalog)
  - [**Borderless open data lakehouse agentic AI system**](./skills/cloud/google-cloud-solution-agentic-ai-borderless-data-lakehouse)
  - [**Build and deploy AI agents on Google Cloud**](./skills/cloud/google-cloud-solution-build-deploy-agents)
  - [**Data science workflow with AI agents solution**](./skills/cloud/google-cloud-solution-agentic-ai-data-science-workflow)
  - [**Dynamic Hybrid Search using AlloyDB**](./skills/cloud/google-cloud-solution-hybrid-search-alloydb)
  - [**Google Skill Finder**](./skills/developers/finding-google-skills)
  - [**Live bidirectional multimodal streaming agentic AI solution**](./skills/cloud/google-cloud-solution-agentic-ai-bidirectional-streaming)
  - [**Migrate AI Workloads to GKE Inference**](./skills/cloud/google-cloud-solution-guided-gke-ai-migration)
  - [**RAG for enterprise search using GKE and AlloyDB**](./skills/cloud/google-cloud-solution-rag-enterprise-search-gke-sqldb)
  - [**Secure n-tier serverless web application with strict private application tiers**](./skills/cloud/google-cloud-solution-n-tier-serverless-web-app)
- **AI/ML**
  - [**Agent Access Audit**](./skills/cloud/agent-platform-access-audit)
  - [**Agent Platform Alert Configuration**](./skills/cloud/agent-platform-alert-configuration)
  - [**Agent Platform Endpoint Management**](./skills/cloud/agent-platform-endpoint-management)
  - [**Agent Platform Eval Flywheel Skill**](./skills/cloud/agent-platform-eval-flywheel)
  - [**Agent Platform GenAI Inference Skill**](./skills/cloud/agent-platform-inference)
  - [**Agent Platform Model Garden Deploy Skill**](./skills/cloud/agent-platform-deploy)
  - [**Agent Platform Model Registry Management**](./skills/cloud/agent-platform-model-registry)
  - [**Agent Platform Model Tuning**](./skills/cloud/agent-platform-tuning)
  - [**Agent Platform Prompt Management**](./skills/cloud/agent-platform-prompt-management)
  - [**Agent Platform RAG Engine Management**](./skills/cloud/agent-platform-rag-engine-management)
  - [**Agent Platform Troubleshooting**](./skills/cloud/agent-platform-troubleshooting)
  - [**Agent Platform Tuning Management**](./skills/cloud/agent-platform-tuning-management)
  - [**API Gateway Remote MCP Server (Public Preview)**](./skills/cloud/api-gateway-mcp-server)
  - [**Apigee as an Agent Gateway Service Extension**](./skills/cloud/apigee-agent-gateway-governance)
  - [**BigQuery AI & ML**](./skills/cloud/bigquery-ai-ml)
  - [**Gemini API in Agent Platform**](./skills/cloud/gemini-api)
  - [**Gemini Enterprise Agent Platform - Managed Agents API Skill**](./skills/cloud/gemini-agents-api)
  - [**Gemini Interactions API Skill**](./skills/cloud/gemini-interactions-api)
  - [**Gemini platform Architecture and Engineering Guide**](./skills/cloud/agent-platform-architecture)
  - [**Genkit Dart**](./skills/cloud/developing-genkit-dart)
  - [**Genkit Go**](./skills/cloud/developing-genkit-go)
  - [**Genkit JS**](./skills/cloud/developing-genkit-js)
  - [**Genkit Python**](./skills/cloud/developing-genkit-python)
  - [**LiveAPI Service Skill**](./skills/cloud/gemini-live-api)
  - [**Migrating from Gemini API in AI Studio to Agent Platform**](./skills/cloud/agent-platform-migrate-from-ai-studio)
  - [**Skill Registry**](./skills/cloud/agent-platform-skill-registry)
  - [**Troubleshoot GKE TPU multi-slice hangs with the MXLA Hang Analyzer**](./skills/cloud/gke-ai-troubleshooting-tpu-mxla-hang)
  - [**Troubleshoot GKE TPU performance degradation with ML Diagnostics Workload Monitoring**](./skills/cloud/gke-ai-troubleshooting-tpu-performance-degradation)
- **Infrastructure**
  - [**Cloud Network Insights**](./skills/cloud/cloud-network-insights)
  - [**Cloud Storage Basics**](./skills/cloud/google-cloud-storage-basics)
  - [**Cloud Storage Bucket Architect**](./skills/cloud/google-cloud-storage-bucket-architect)
  - [**Cloud Storage Diagnostic**](./skills/cloud/google-cloud-storage-diagnostic)
  - [**Cloud Storage FUSE**](./skills/cloud/google-cloud-storage-fuse)
  - [**Designing and Deploying GCP Infrastructure with Application Design Center**](./skills/cloud/application-design-center-design-deploy)
  - [**Filestore Auditing Skill**](./skills/cloud/google-cloud-filestore-auditing)
  - [**Filestore Autoscale**](./skills/cloud/google-cloud-filestore-autoscale)
  - [**Filestore Log-Based Troubleshooting**](./skills/cloud/google-cloud-filestore-log-troubleshooting)
  - [**Filestore NFS File Browser**](./skills/cloud/google-cloud-filestore-nfs-browser)
  - [**GKE AI/ML Inference**](./skills/cloud/gke-inference)
  - [**GKE Alert Configuration**](./skills/cloud/gke-alert-configuration)
  - [**GKE App Onboarding**](./skills/cloud/gke-app-onboarding)
  - [**GKE Backup & Disaster Recovery**](./skills/cloud/gke-backup-dr)
  - [**GKE Basics & Critical Gotchas**](./skills/cloud/gke-basics)
  - [**GKE Batch & HPC Workloads**](./skills/cloud/gke-batch-hpc)
  - [**GKE Cluster Autoscaler**](./skills/cloud/gke-cluster-autoscaler)
  - [**GKE Cluster Creation**](./skills/cloud/gke-cluster-creation)
  - [**GKE ComputeClasses**](./skills/cloud/gke-compute-classes)
  - [**GKE Golden Base Image Discovery Expert**](./skills/cloud/gke-custom-golden-image-discovery)
  - [**GKE Golden Path Configuration**](./skills/cloud/gke-golden-path)
  - [**GKE JobSet Interruption Troubleshooting**](./skills/cloud/gke-ai-troubleshooting-jobset-interruption)
  - [**GKE Manifest Generation Skill**](./skills/cloud/gke-manifest-generation)
  - [**GKE Multi-Tenancy**](./skills/cloud/gke-multitenancy)
  - [**GKE Networking**](./skills/cloud/gke-networking)
  - [**GKE Node NotReady Troubleshooting Skill**](./skills/cloud/gke-node-notready)
  - [**GKE Productionize Skill**](./skills/cloud/gke-productionize)
  - [**GKE Reliability**](./skills/cloud/gke-reliability)
  - [**GKE Service Networking Skill**](./skills/cloud/gke-service-networking)
  - [**GKE Storage**](./skills/cloud/gke-storage)
  - [**GKE Storage Troubleshooting Skill**](./skills/cloud/gke-storage-troubleshooting)
  - [**GKE TPU Dynamic Slices Monitoring & Management**](./skills/cloud/gke-ai-troubleshooting-tpu-dynamic-slices-monitoring)
  - [**GKE Upgrades & Maintenance**](./skills/cloud/gke-upgrades)
  - [**GKE Workload Scaling**](./skills/cloud/gke-workload-scaling)
  - [**GKE Workload Scaling Troubleshooting Skill**](./skills/cloud/gke-workload-scaling-troubleshooting)
  - [**GKE Workload Troubleshooting Skill**](./skills/cloud/gke-workload-troubleshooting)
  - [**Google Cloud global external Application Load Balancer Configuration Skill**](./skills/cloud/google-cloud-global-frontend-configuration)
  - [**Google Cloud Networking Observability Expert**](./skills/cloud/google-cloud-networking-observability)
  - [**Troubleshoot GKE TPU reservation stockouts caused by leaked node pool capacity**](./skills/cloud/gke-ai-troubleshooting-tpu-reservation-stockout)
  - [**Troubleshoot GKE TPU slice creation blocked by an unstable MIG**](./skills/cloud/gke-ai-troubleshooting-tpu-slice-mig-stuck-updating)
  - [**Troubleshoot GKE TPU VMs stuck in Compute Engine repair (`REPAIRING`)**](./skills/cloud/gke-ai-troubleshooting-tpu-vm-repair-stuck)
  - [**Troubleshoot TPU slice creation failures caused by partition overlap**](./skills/cloud/gke-ai-troubleshooting-tpu-partition-overlap)
  - [**Troubleshoot unresponsive GKE TPU and GPU nodes (`NodeStatusUnknown`)**](./skills/cloud/gke-ai-troubleshooting-node-unresponsive-timeout)
- **Databases and analytics**
  - [**AlloyDB Basics**](./skills/cloud/alloydb-basics)
  - [**BigFrames (BigQuery DataFrame) basics**](./skills/cloud/bigquery-bigframes)
  - [**BigQuery Asset Impact Analysis**](./skills/cloud/datalineage-bigquery-asset-impact-analysis)
  - [**BigQuery Basics**](./skills/cloud/bigquery-basics)
  - [**BigQuery Migration Service (BQMS) SQL Translator**](./skills/cloud/bigquery-migration-sql-translator)
  - [**BigQuery Observability**](./skills/cloud/bigquery-observability)
  - [**BigQuery Optimization Workflow**](./skills/cloud/bigquery-optimization)
  - [**BigQuery Troubleshooting**](./skills/cloud/bigquery-troubleshooting)
  - [**BigQuery User-Defined Functions (UDFs)**](./skills/cloud/bigquery-udfs)
  - [**Bigtable Basics**](./skills/cloud/bigtable-basics)
  - [**Cloud SQL Basics**](./skills/cloud/cloud-sql-basics)
  - [**Data Lineage Summary**](./skills/cloud/datalineage-summary)
  - [**dbt Snowflake to BigQuery Translator**](./skills/cloud/dbt-sf-to-bq-translator)
  - [**GCP Managed Airflow DAG Authoring Guide**](./skills/cloud/managed-airflow-dag-authoring)
  - [**Google Cloud Database Onboarding Skill**](./skills/cloud/cloud-databases-onboarding)
  - [**Managed Service for Apache Airflow (formerly Cloud Composer) DAG troubleshooting guide**](./skills/cloud/managed-airflow-dag-troubleshooting)
  - [**Managed Service for Apache Airflow (formerly Cloud Composer) Migration Guide**](./skills/cloud/managed-airflow-migrations)
  - [**Managed Service for Apache Airflow (formerly Cloud Composer) recommendations**](./skills/cloud/managed-airflow-recommendations)
  - [**Spanner Basics**](./skills/cloud/spanner-basics)
- **Developer tools**
  - [**Cloud Build Basics**](./skills/cloud/cloud-build-basics)
  - [**Cloud Operator**](./skills/cloud/cloud-operator)
  - [**Developer Device Platform**](./skills/cloud/developer-device-platform-basics)
  - [**gcloud CLI Skill for AI Agents**](./skills/cloud/gcloud)
  - [**Google Agents CLI Onboarding**](./skills/cloud/google-agents-cli-onboarding)
  - [**Google Developer Knowledge**](./skills/developers/retrieving-developer-knowledge)
- **Application development**
  - [**Application Integration Authoring**](./skills/cloud/application-integration-authoring)
  - [**Application Integration Basics**](./skills/cloud/application-integration-basics)
  - [**Application Integration Troubleshooting**](./skills/cloud/application-integration-troubleshooting)
  - [**Migrate Legacy Codebases to Safe Rust**](./skills/developers/migrate-to-rust)
- **Management tools**
  - [**Cloud Logging Finops**](./skills/cloud/cloud-logging-finops)
  - [**Cloud Monitoring Chart Generation Skill (`cloud-monitoring-chart-generation`)**](./skills/cloud/cloud-monitoring-chart-generation)
  - [**Cloud Monitoring ListTimeSeries Request Generator**](./skills/cloud/cloud-monitoring-list-time-series-request)
  - [**Cloud Monitoring Notification Channels Configuration**](./skills/cloud/cloud-monitoring-notification-channels-configuration)
  - [**Cloud Monitoring PromQL Generator**](./skills/cloud/cloud-monitoring-promql-query)
  - [**Cloud Trace Querying Skill (`cloud-trace-querying`)**](./skills/cloud/cloud-trace-querying)
  - [**Configure Cloud Monitoring Alerts**](./skills/cloud/cloud-monitoring-alert-configuration)
  - [**Configuring Cloud Logging**](./skills/cloud/cloud-logging-configuration-basics)
  - [**Configuring Cross-Project Logging**](./skills/cloud/cloud-logging-cross-project-configuration)
  - [**Generate Logging Query Language queries**](./skills/cloud/cloud-logging-query-generation)
  - [**GKE Cost Analysis**](./skills/cloud/gke-cost-analysis)
  - [**GKE Cost Optimization**](./skills/cloud/gke-cost-optimization)
  - [**GKE Observability**](./skills/cloud/gke-observability)
  - [**GKE TPU Metrics Monitoring Guide**](./skills/cloud/gke-ai-troubleshooting-tpu-metrics-monitoring)
  - [**Handle Disruption on GPUs and TPUs Troubleshooting**](./skills/cloud/gke-ai-troubleshooting-handle-disruption-gpu-tpu)
  - [**Metric Selection (Service Query & Local Keyword Filtering)**](./skills/cloud/cloud-monitoring-metric-selection)
  - [**SLO Alert Configuration Setup Wizard**](./skills/cloud/google-cloud-slo-alert-configuration)
  - [**TPU Connection Failure and VBAR OOM Troubleshooting**](./skills/cloud/gke-ai-troubleshooting-tpu-vbar-oom)
  - [**Workload Manager Basics**](./skills/cloud/workload-manager-basics)
- **Well-Architected Framework**
  - [**Google Cloud Well-Architected Framework skill for the Cost Optimization pillar**](./skills/cloud/google-cloud-waf-cost-optimization)
  - [**Google Cloud Well-Architected Framework skill for the Operational Excellence pillar**](./skills/cloud/google-cloud-waf-operational-excellence)
  - [**Google Cloud Well-Architected Framework skill for the Performance Optimization pillar**](./skills/cloud/google-cloud-waf-performance-optimization)
  - [**Google Cloud Well-Architected Framework skill for the Reliability pillar**](./skills/cloud/google-cloud-waf-reliability)
  - [**Google Cloud Well-Architected Framework skill for the Security pillar**](./skills/cloud/google-cloud-waf-security)
  - [**Google Cloud Well-Architected Framework skill for the Sustainability pillar**](./skills/cloud/google-cloud-waf-sustainability)
- **Security and identity**
  - [**API Gateway Backend Security and Rate Limiting**](./skills/cloud/api-gateway-backend-security-and-rate-limiting)
  - [**Cloud Armor OWASP Rule Upgrader (CRS 3.0/3.3 -> 4.22)**](./skills/cloud/cloud-armor-crs-rule-upgrader)
  - [**Compliance Environment Assessor Skill**](./skills/cloud/assuredworkloads-environment-assessor)
  - [**Custom Resource Authoring & Synthesis Skill (`assuredworkloads-frameworks-author`)**](./skills/cloud/assuredworkloads-frameworks-author)
  - [**Data Boundary Framework Navigator (`assuredworkloads-frameworks-navigator`)**](./skills/cloud/assuredworkloads-frameworks-navigator)
  - [**DPoP Adoption & Identity Security Architecture**](./skills/identity/dpop-adoption)
  - [**GKE Platform Security**](./skills/cloud/gke-platform-security)
  - [**GKE Workload Identity Federation Troubleshooting Skill**](./skills/cloud/gke-workload-identity)
  - [**GKE Workload Security**](./skills/cloud/gke-workload-security)
  - [**Google Cloud Assured Workloads Basics (V1 GA)**](./skills/cloud/assured-workloads-basics)
  - [**Google Cloud Security Command Center Remediation**](./skills/cloud/google-cloud-scc-remediation)
  - [**Google SecOps Case Management Skill for AI Agents**](./skills/cloud/secops-cases)
  - [**Google SecOps Detection Engineering Skill**](./skills/cloud/secops-detection-engineering)
  - [**Google SecOps Incident & Entity Investigation Skill**](./skills/cloud/secops-investigate)
  - [**Google SecOps Security Alert Triage Specialist**](./skills/cloud/secops-triage)
  - [**Google SecOps Threat Hunting Skill**](./skills/cloud/secops-hunt)
  - [**IAM Access Troubleshooter & Remediation Orchestrator on Google Cloud**](./skills/cloud/iam-helper-for-troubleshooting)
  - [**IAM Helper for Policy Management**](./skills/cloud/iam-helper-for-policy-management)
  - [**IAM Policy Simulator (v1 Allow)**](./skills/cloud/iam-helper-for-policy-simulator)
  - [**Privileged Access Manager (PAM)**](./skills/cloud/iam-helper-for-privileged-access-management)
  - [**SecOps Detection Coverage Skill**](./skills/cloud/detection-engineering-coverage-evaluation)
  - [**Security Command Center Query Skill on Google Cloud**](./skills/cloud/google-cloud-scc-query)
  - [**Sign In With Google (SiwG) Integration & Security Architecture**](./skills/identity/sign-in-with-google-web)
- **Web and app hosting**
  - [**Cloud Run Alert Configuration**](./skills/cloud/cloud-run-alert-configuration)
  - [**Cloud Run Basics**](./skills/cloud/cloud-run-basics)
  - [**Firebase Basics**](./skills/cloud/firebase-basics)
- **Advertising**
  - [**AI Migration Agent Instructions for the Google Mobile Ads SDK**](./skills/ads/google-mobile-ads-android-migrate-to-next-gen)
  - [**Data Manager API Audience Ingestion**](./skills/ads/data-manager-api-audience-ingestion)
  - [**Data Manager API Event Ingestion**](./skills/ads/data-manager-api-event-ingestion)
  - [**Data Manager API Setup**](./skills/ads/data-manager-api-setup)
  - [**Google Ads API Account Performance Diagnostics Skill**](./skills/ads/google-ads-api-account-diagnostics)
  - [**Google Ads API MCP Server Installation**](./skills/ads/google-ads-api-mcp-setup)
  - [**Google Ads API Quickstart**](./skills/ads/google-ads-api-quickstart)
  - [**Google Mobile Ads SDK - Banner Ads**](./skills/ads/google-mobile-ads-banner)
  - [**Google Mobile Ads SDK - Install**](./skills/ads/google-mobile-ads-get-started)
  - [**Google Mobile Ads SDK - Interstitial Ads**](./skills/ads/google-mobile-ads-interstitial)
  - [**Google Mobile Ads SDK - Rewarded Ads**](./skills/ads/google-mobile-ads-rewarded)
  - [**IMA DAI SDK**](./skills/ads/ima-dai-sdk)
  - [**IMA SDK client-side**](./skills/ads/ima-sdk-client-side)
  - [**Validate Google Mobile Ads SDK Integration**](./skills/ads/google-mobile-ads-validate)
- **Others**
  - [**Getting Started with Google Analytics Admin API**](./skills/analytics/google-analytics-admin-api-basics)
  - [**Getting Started with Google Analytics Data API**](./skills/analytics/google-analytics-data-api-basics)
<!-- END SKILLS -->

## Additional Google skills

-   [**Advanced Google Cloud Storage Skills**](https://github.com/gemini-cli-extensions/google-cloud-storage)
-   [**Agent Development Kit (ADK) Skills**](https://github.com/google/agents-cli)
-   [**Android Skills**](https://github.com/android/skills)
-   [**Dart Skills**](https://github.com/dart-lang/skills)
-   [**Firestore Skills**](https://github.com/firebase/agent-skills/tree/main/skills/firebase-firestore)
-   [**Flutter Skills**](https://github.com/flutter/skills)
-   [**Google Maps Platform Skills**](https://github.com/googlemaps/agent-skills)

## Plugins

This repo also bundles Google product plugins (Skills + MCP servers) for agent harnesses.

| Agent harness | Install |
| :--- | :--- |
| **Claude Code** | `claude plugin marketplace add google/skills`, then `claude plugin install <plugin>@google-plugins` |
| **Codex** | `codex plugin marketplace add google/skills`, then install from the `/plugins` browser |
| **Antigravity CLI** | `agy plugin install https://github.com/google/skills/<plugin-path>` |

## Support

If you need help or encounter issues with these skills, search for existing
issues or open a new one in the
[GitHub Issue Tracker](https://github.com/google/skills/issues).

## Contributing

We welcome contributions to improve our skills. You can help by:

*   [Reporting bugs or inaccuracies](https://github.com/google/skills/issues) in
    the skill Markdown files.
*   Suggesting new skills to add to this repository (for example, Google
    technologies or recipes) by filing a feature request.

## License

You are free to copy, modify, and distribute these skills under the terms of the
Apache 2.0 license. See the `LICENSE` file for details.
