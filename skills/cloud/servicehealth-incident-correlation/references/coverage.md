# PSH coverage

PSH reports incidents only for onboarded Google Cloud products listed under
[Supported products](#supported-products) (if an observed product is absent, an
empty event list cannot rule out a Google Cloud issue and maps to
`INCONCLUSIVE`). Resource-level impacts (`v1beta` Preview) exist only for the
products and resource types in
[Resource-level impact coverage (Preview)](#resource-level-impact-coverage-preview).

## Contents

*   [Markers](#markers): Lines 22–31
*   [Resource-level impact coverage (Preview)](#resource-level-impact-coverage-preview): Lines 33–50
*   [Supported products](#supported-products): Lines 52–193

> [!NOTE]
> This is an offline snapshot of
> [Supported products and locations](https://docs.cloud.google.com/service-health/docs/supported-products-locations.md.txt).
> Fetch the live page first whenever web access is available: products,
> markers, and resource types are added over time.

## Markers

The **Markers** column under [Supported products](#supported-products)
mirrors the footnotes of the live page:

| Marker | Product supports | Effect on interpretation |
| :--- | :--- | :--- |
| `*` | Emerging incidents | Incidents can appear while Google is still investigating. Without `*`, incidents appear once confirmed, so `startTime` lags symptom onset more. |
| `†` | `IMPACTED` relevance | `IMPACTED` confirms project-level impact. Without `†` or `‡`, `RELATED` is the strongest relevance PSH gives. |
| `‡` | `IMPACTED` relevance with resource-level impacts (Preview) | Resource-level impacts can list affected resources of the types below (informational only). |

## Resource-level impact coverage (Preview)

`list_project_impacts` and `get_project_impact` (`projects.locations.impacts` in
the `v1beta` API, `gcloud beta service-health impacts`) identify individual
resources only for these products and Cloud Asset Inventory resource types:

| Product name (as shown in PSH) | Supported `asset.assetType` | Full resource name format (`asset.assetName`) |
| :--- | :--- | :--- |
| `Google Cloud SQL` | `sqladmin.googleapis.com/Instance` | `//cloudsql.googleapis.com/projects/{project_number}/instances/{instance_id}` |
| `Google Kubernetes Engine` | `container.googleapis.com/Cluster`, `container.googleapis.com/NodePool` | `//container.googleapis.com/projects/{project_number}/locations/{location}/clusters/{cluster_name}`, `//container.googleapis.com/projects/{project_number}/zones/{zone}/clusters/{cluster_name}`, `//container.googleapis.com/projects/{project_number}/locations/{location}/clusters/{cluster_name}/nodePools/{node_pool_name}` |
| `Google Cloud Pub/Sub` | `pubsub.googleapis.com/Topic`, `pubsub.googleapis.com/Subscription` | `//pubsub.googleapis.com/projects/{project_number}/topics/{topic_name}`, `//pubsub.googleapis.com/projects/{project_number}/subscriptions/{subscription_name}` |

Products and resource types absent from the table above are not supported yet.
For those in the table, `Impact` records exist only for incidents whose
resource-level impact the product team can detect, and PSH does not indicate
which incidents those are. `Impact` records are therefore informational only: an
empty `impacts` list never rules out impact and never changes the verdict.

## Supported products

**Product** lists the Google Cloud product name; **Product name (as shown in
PSH)** gives the exact, case-sensitive `eventImpacts[].product.productName`
value used in PSH events and `event_impacts.product.product_name` filters.
Combine multiple rows for a product with `OR` when pre-filtering.

| Product | Product name (as shown in PSH) | Markers |
| :--- | :--- | :--- |
| Access Context Manager | `Access Context Manager` |  |
| Agent Assist | `Agent Assist` |  |
| AlloyDB for PostgreSQL | `AlloyDB for PostgreSQL` |  |
| API Gateway | `API Gateway` |  |
| Apigee | `Apigee` |  |
| Apigee Hybrid | `Apigee Hybrid` |  |
| Application Integration | `Application Integration` |  |
| Artifact Registry | `Artifact Registry` |  |
| Backup and DR Service | `Backup and DR` |  |
| Backup for GKE | `Backup for GKE` |  |
| Bare Metal Solution | `Bare Metal` |  |
| Batch | `Batch` |  |
| BigQuery Data Transfer Service | `BigQuery Data Transfer Service` |  |
| Binary Authorization | `Binary Authorization` |  |
| Certificate Authority Service | `Certificate Authority Service` |  |
| Google Cloud Armor | `Cloud Armor` | `*` |
| Cloud Asset Inventory | `Cloud Asset Inventory` |  |
| Cloud Service Mesh | `Cloud ASM` |  |
| Cloud Billing | `Cloud Billing` |  |
| Cloud Build | `Cloud Build` |  |
| Cloud CDN | `Cloud CDN` |  |
| Cloud Data Fusion | `Cloud Data Fusion` |  |
| Cloud Domains | `Cloud Domains` |  |
| Cloud Endpoints | `Cloud Endpoints` |  |
| Cloud External Key Manager | `Cloud External Key Manager` |  |
| Filestore | `Cloud Filestore` |  |
| Firestore | `Cloud Firestore` | `†` |
| Cloud HSM | `Cloud HSM` |  |
| Cloud Intrusion Detection System | `Cloud IDS` | `*` |
| Cloud Key Management Service | `Cloud Key Management Service` |  |
| Cloud Load Balancing | `Cloud Load Balancing` | `*†` |
| Cloud Logging | `Cloud Logging` |  |
| Memorystore | `Cloud Memorystore` |  |
| Cloud Monitoring | `Cloud Monitoring` |  |
| Cloud NAT | `Cloud NAT` | `*` |
| Cloud Run | `Cloud Run` |  |
| Spanner | `Cloud Spanner` |  |
| Cloud Storage for Firebase | `Cloud Storage for Firebase` |  |
| Talent Solution | `Cloud Talent Solution - Job Search` |  |
| Cloud Trace | `Cloud Trace` |  |
| Cloud Translation | `Cloud Translation` |  |
| Cloud Vision | `Cloud Vision` |  |
| Workflows | `Cloud Workflows` |  |
| Cloud Workstations | `Cloud Workstations` |  |
| Colab Enterprise | `Colab Enterprise` |  |
| Google Cloud Contact Center as a Service | `Contact Center AI Platform` |  |
| Cloud Contact Center | `Contact Center Insights` |  |
| Container Registry | `Container Registry` |  |
| Database Migration Service | `Database Migration Service` |  |
| Dataform | `Dataform` |  |
| Knowledge Catalog | `Dataplex` |  |
| Dataproc Metastore | `Dataproc Metastore` |  |
| Datastream | `Datastream` |  |
| Developer Connect | `Developer Connect` |  |
| Dialogflow CX | `Dialogflow CX` |  |
| Dialogflow ES | `Dialogflow ES` |  |
| Document AI | `Document AI` |  |
| Eventarc | `Eventarc` |  |
| Gemini Enterprise | `Gemini Enterprise` |  |
| GKE Fleet | `GKE fleet management` |  |
| App Engine | `Google App Engine` |  |
| BigQuery | `Google BigQuery` |  |
| Bigtable | `Google Cloud Bigtable` | `†` |
| Managed Service for Apache Airflow | `Google Cloud Composer` |  |
| Google Cloud console | `Google Cloud Console` |  |
| Sensitive Data Protection | `Google Cloud Data Loss Prevention` |  |
| Dataflow | `Google Cloud Dataflow` |  |
| Managed Service for Apache Spark | `Google Cloud Dataproc` |  |
| Cloud Deploy | `Google Cloud Deploy` |  |
| Cloud DNS | `Google Cloud DNS` |  |
| Cloud Run functions | `Google Cloud Functions` |  |
| Google Cloud Managed Lustre | `Google Cloud Managed Lustre` |  |
| Google Cloud NetApp Volumes | `Google Cloud NetApp Volumes` |  |
| Pub/Sub | `Google Cloud Pub/Sub` | `‡` |
| Cloud Scheduler | `Google Cloud Scheduler` |  |
| Cloud Source Repositories | `Google Cloud Source Repositories` |  |
| Cloud SQL | `Google Cloud SQL` | `†‡` |
| Cloud Storage | `Google Cloud Storage` |  |
| Cloud Customer Care | `Google Cloud Support` |  |
| Cloud Tasks | `Google Cloud Tasks` |  |
| Google Cloud VMware Engine | `VMware Engine` |  |
| Compute Engine | `Google Compute Engine` | `†` |
| Google Kubernetes Engine | `Google Kubernetes Engine` | `‡` |
| Google Security Operations SIEM | `Google Security Operations SIEM` |  |
| Google Security Operations SOAR | `Google Security Operations SOAR` |  |
| Hybrid Connectivity | `Hybrid Connectivity` | `*` |
| Identity and Access Management | `Identity and Access Management` |  |
| Identity Platform | `Identity Platform` |  |
| Integration Connectors | `Integration Connectors` |  |
| Data Studio | `Looker Studio` |  |
| Google Cloud Managed Service for Apache Kafka | `Managed Service for Apache Kafka` |  |
| Managed Service for Microsoft Active Directory | `Managed Service for Microsoft Active Directory (AD)` |  |
| Media CDN | `Media CDN` | `*` |
| Memorystore for Memcached | `Memorystore for Memcached` |  |
| Memorystore for Redis | `Memorystore for Redis` |  |
| Memorystore for Redis Cluster | `Memorystore for Redis Cluster` |  |
| Memorystore for Valkey | `Memorystore for Valkey` |  |
| Migrate to Virtual Machines | `Migrate to Virtual Machines` |  |
| Model Armor | `Model Armor` |  |
| Network Connectivity Center | `Network Connectivity Center` | `*` |
| Network Intelligence Center | `Network Intelligence Center` | `*` |
| Network Telemetry | `Network Telemetry` |  |
| Persistent Disk | `Persistent Disk` | `*†` |
| Personalized Service Health | `Personalized Service Health` |  |
| Private Service Connect | `Private Service Connect` | `*` |
| Provisioned Throughput | `Provisioned Throughput` |  |
| reCAPTCHA | `reCAPTCHA Enterprise` |  |
| Recommender | `Recommender` |  |
| Cloud Resource Manager API | `Resource Manager API` |  |
| AI Commerce Search API | `Retail API` |  |
| Secret Manager | `Secret Manager` |  |
| Security Command Center | `Security Command Center` |  |
| Service Directory | `Service Directory` |  |
| Storage Transfer Service | `Storage Transfer Service` |  |
| Text-to-Speech | `Text-to-Speech` |  |
| Cloud Service Mesh | `Traffic Director` | `*` |
| Transcoder API | `Transcoder API` |  |
| Vertex AI Agent Engine | `Vertex AI Agent Engine` |  |
| Batch prediction | `Vertex AI Batch Prediction` |  |
| Vertex AI Feature Store | `Vertex AI Feature Store` |  |
| Vertex AI Model Monitoring | `Vertex AI Model Monitoring` |  |
| Vertex AI Model Registry | `Vertex AI Model Registry` |  |
| Online prediction | `Vertex AI Online Prediction` |  |
| Vertex AI Pipelines | `Vertex AI Pipelines` |  |
| Agent Search | `Vertex AI Search` |  |
| Vertex AI Training | `Vertex AI Training` |  |
| Vertex AI Workbench | `Vertex AI Workbench User Managed Notebooks` |  |
| Vertex AI API | `Vertex Gemini API` |  |
| Vertex AI Imagen API | `Vertex Imagen API` |  |
| Vertex AI Veo API | `Vertex Veo API` |  |
| Video Intelligence API | `Video Intelligence API` |  |
| Virtual Private Cloud (VPC) | `Virtual Private Cloud (VPC)` | `*†` |
| Web Risk | `Web Risk` |  |
