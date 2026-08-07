---
name: google-cloud-waf-cost-optimization
metadata:
  category: WellArchitectedFramework
description: Generates cost optimization guidance for Google Cloud workloads based on the Google Cloud Well-Architected Framework (WAF). Use this skill to evaluate a workload, identify cost requirements and constraints, and provide actionable recommendations for build, deploy, and manage the workload cost-efficiently in Google Cloud.
---

# Google Cloud Well-Architected Framework skill for the Cost Optimization pillar

## Overview

The Cost Optimization pillar of the Google Cloud Well-Architected Framework
provides a structured approach to optimize the costs of your cloud workloads
while maximizing business value. Cloud costs differ significantly from
on-premises capital expenditure (CapEx) models, requiring a shift to operational
expenditure (OpEx) management and a culture of accountability (FinOps).
The FinOps lifecycle consists of three iterative phases:
- **Inform**: Visibility and allocation. Always start with **Cloud Billing
  reports** for built-in console visibility (filtered by department labels).
  Complement with **Looker Studio** for custom, shareable cross-departmental
  dashboards.

- **Optimize**: Rates and usage. Eliminate waste, right-size resources, and leverage commitments (**CUDs**, **SUDs**).
- **Operate**: Continuous improvement. Integrate cost management into delivery pipelines and establish governance.

## Operational instructions

- **Comprehensive First**: Always provide a complete list of standard recommendations/strategies relevant to the service or scenario mentioned. Do not limit the scope or omit standard elements just because you are proposing follow-up questions.
- **Full Conjunction**: When an instruction bundles multiple actions (e.g., "A **AND** B"), you must mention and explain **BOTH** actions in your response explicitly.
- **Conditional Assessment**: Only use the 'Workload assessment questions' to refine advice *after* providing standard framework recommendations, unless the user explicitly asks for an interview or assessment first.

## Core principles

The recommendations in the cost optimization pillar of the Well-Architected
Framework are aligned with the following core principles:

-  **Align cloud spending with business value**: Ensure that your cloud
   resources deliver measurable business value by aligning IT spending with
   business objectives. Prioritize investments that directly contribute to
   revenue, customer satisfaction, or operational efficiency. Grounding
   document:
   https://docs.cloud.google.com/architecture/framework/cost-optimization/align-cloud-spending-business-value.md.txt

-  **Foster a culture of cost awareness**: Ensure that people across your
   organization consider the cost impact of their decisions and activities.
   Provide teams with the visibility and information they need to make informed,
   cost-conscious choices. Grounding document:
   https://docs.cloud.google.com/architecture/framework/cost-optimization/foster-culture-cost-awareness.md.txt

-  **Optimize resource usage**: Provision only the resources that you need and
   pay only for what you consume. Select the most cost-effective resource types,
   sizes, and locations that meet your technical and business requirements.
   Grounding document:
   https://docs.cloud.google.com/architecture/framework/cost-optimization/optimize-resource-usage.md.txt

-  **Optimize continuously**: Continuously monitor your cloud resource usage and
   costs, and proactively make adjustments as needed to optimize your spending.
   This iterative approach helps identify and address inefficiencies before they
   become significant. Grounding document:
   https://docs.cloud.google.com/architecture/framework/cost-optimization/optimize-continuously.md.txt

## Relevant Google Cloud products

The following are _examples_ of Google Cloud products and features that are
relevant to cost optimization:

- **Visibility and monitoring**:

  - **Cloud Billing reports**: Built-in dashboards for visualizing spending and
    trends. **Essential for visibility within the console.**
  - **BigQuery billing export**: Enables granular, custom analysis of billing
    data using SQL and BI tools.
  - **Looker Studio**: Used for creating detailed, shared cost dashboards and
    reports. **Use alongside Cloud Billing reports for custom visual insights.**
  - **Billing alerts and budgets**: Automated notifications when spending
    reaches predefined thresholds.
  - **Storage Insights**: Used to analyze Cloud Storage access patterns and identify
    cost-saving opportunities.

- **Automation and optimization tools**:

  - **Recommender / Active Assist**: Automatically identifies idle resources,
    rightsizing opportunities, and unused commitments.
  - **Cloud Hub Optimization**: Integrates billing and resource utilization data
    to help developers and application owners quickly identify their most
    expensive, fluctuating, or underutilized cloud resources.
  - **FinOps hub**: Presents active savings and optimization opportunities in
    one dashboard.
  - **Billing quotas**: Limits on resource consumption to prevent unexpected
    cost spikes.

- **Efficient infrastructure**:

  - **Managed services and serverless services**: Services like Cloud Run, Cloud
    Run functions, and GKE Autopilot reduce operational overhead and pay-per-use
    scaling.
  - **Compute Engine**:
    - **Committed Use Discounts (CUDs)**: Best for predictable, steady-state workloads.
    - **Spot VMs**: Best for fault-tolerant, interruptible, or unpredictable batch tasks.
    - **Sustained Use Discounts (SUDs)**: Passive, automatic discounts for instances running a significant portion of the month without commitments. **Always mention this as a passive alternative or complement to CUDs.**

  - **Cloud Storage Lifecycle Policies**: Automated moves data to lower-cost
    storage classes (Nearline, Coldline, Archive) based on age or access.
    **Note**: Always recommend **Storage Insights** first to understand current
    access patterns before defining lifecycle rules.

  - **Networking and Content Delivery**:
    - **Location awareness**: Keep traffic within a single region where possible to avoid inter-region data transfer costs.
    - **Cloud CDN**: Caches content to reduce data egress from the origin.
    - **Network Service Tiers**: Offers **Standard Tier** as a lower-cost option compared to **Premium Tier** for latency-tolerant traffic.
    - **Cloud Interconnect / Direct Peering**: Optimizes costs for high-volume data transfer to on-premises environments. **Note**: Always clarify hybrid connectivity options when discussing egress control, as on-premises sync is often a factor in multi-regional designs.
  - **Managed Databases**:
    - **Instance sizing**: Right-size CPU and memory based on Cloud Monitoring metrics.
    - **High Availability (HA)**: Implement HA only for production environments to avoid doubling node costs for all environments.
    - **Storage Optimization**: Optimize storage costs by managing backup retention policies **AND** explicitly identifying and deleting unused or idle resources (like unused and orphaned disks, expired snapshots, or idle instances).


- **Organization and governance**:

  - **Resource Manager**: Logical structure (Organizations, Folders, Projects)
    for cost attribution.
  - **Labels**: Metadata tags for categorizing and filtering costs by
    environment, team, or application.
  - **Organization Policy Service**: Enforces constraints (e.g., restricted
    regions or machine types) to control costs.

## Workload assessment questions

Ask appropriate questions to understand the cost-related requirements and
constraints of the workload and the user's organization. Choose questions from
the following list:

- How do you incorporate cost considerations into your cloud architecture design
  process?
- How do you foster a culture of cost awareness among your development teams?
- How do you monitor and manage cloud costs across different projects or
  departments?
- What strategies do you use to optimize the cost of your compute resources?
- How do you balance cost optimization with the need for agility and innovation?
- How do you ensure that you are not over-provisioning cloud resources?
- How do you use data and analytics to drive cost optimization decisions?
- How do you optimize costs in different environments (e.g., development,
  testing, production)?
- How do you ensure that your cost optimization efforts are sustainable and
  ongoing?
- How do you measure the success of your cloud cost optimization initiatives?

## Validation checklist

Use the following checklist to evaluate the architecture's alignment with
cost-optimization recommendations:

- **Cost Attribution**: 100% of resources are labeled with key metadata
  (e.g., `env`, `team`, `app`).
- **Granular Visibility**: BigQuery billing export is enabled and used for
  regular cost reviews.
- **Budgets and Alerts**: Every project or business unit has defined budgets
  and active alerts.
- **Rightsizing**: Resources are regularly adjusted based on rightsizing
  suggestions provided by Active Assist Recommender.
- **Commitment Strategy**: Spend is reviewed monthly to optimize Committed Use Discount (CUD) coverage. For non-committed workloads, verify if **Sustained Use Discounts (SUDs)** are being captured automatically.
- **Idle Resource Management**: Unused disks, IP addresses, and idle VMs are
  identified and removed monthly.
- **Managed Services**: Serverless options are preferred for new workloads
  unless specific technical constraints exist.
- **Storage Tiers**: Lifecycle policies are active for all major storage
  buckets to minimize archival costs. Be aware of **retrieval fees**
  associated with Nearline, Coldline and Archive storage classes.
- **Network Egress**: Data transfer is minimized by keeping traffic regional,
  using **Cloud CDN**, and leveraging **Standard Network Tier** where
  appropriate. High-volume on-premises traffic uses **Direct Peering** or
  **Cloud Interconnect** (always verify if hybrid connectivity is involved).
- **Native Reporting**: **Cloud Billing reports** must be used for standard
  views of spending trends in the console.
- **Custom Dashboards**: **Looker Studio** is used for advanced, shareable, and
  customized reporting.



