# Per-stage Kueue and GKE documentation catalog

Use these official upstream Kueue and Google Kubernetes Engine (GKE)
documentation pages and sections when diagnosing pipeline stages 1–6 or citing
remediation steps in `#### Remediation`. Run only read-only diagnostic sections
yourself; for any section that creates, edits, or restarts cluster resources,
tell the user to follow the instructions in that section.

## Table of Contents

- [Stage 1: Object chain and queue
  wiring](#stage-1-object-chain-and-queue-wiring): Lines 27-48
- [Stage 2: Quota, cohort sharing, and
  reservations](#stage-2-quota-cohort-sharing-and-reservations): Lines 49-67
- [Stage 3: Flavor assignment, TAS, and
  transformations](#stage-3-flavor-assignment-tas-and-transformations):
  Lines 68-85
- [Stage 4: Admission checks and DWS
  ProvisioningRequests](#stage-4-admission-checks-and-dws-provisioningrequests):
  Lines 86-103
- [Stage 5: Post-admission scheduling, autoscaling, TPUs, and
  nodes](#stage-5-post-admission-scheduling-autoscaling-tpus-and-nodes):
  Lines 104-141
- [Stage 6: Controller configuration, logs, and
  support](#stage-6-controller-configuration-logs-and-support): Lines 142-168

## Stage 1: Object chain and queue wiring

- Missing `Workload` or `Workload` stuck without a valid `LocalQueue` or
  `ClusterQueue`:
  [Troubleshooting Jobs](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_jobs/),
  [Troubleshooting Queues](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_queues/),
  [Workload](https://kueue.sigs.k8s.io/docs/concepts/workload/),
  [LocalQueue](https://kueue.sigs.k8s.io/docs/concepts/local_queue/),
  [ClusterQueue](https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/), and
  [Cohort](https://kueue.sigs.k8s.io/docs/concepts/cohort/).
- Creating or fixing `ResourceFlavor`, `ClusterQueue`, and `LocalQueue` wiring
  on GKE: "Create the ResourceFlavor", "Create the ClusterQueue", "Create the
  LocalQueue", and "Create Jobs and observe the admitted workloads" in
  [Deploy a batch system using Kueue](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/kueue-intro.md.txt).
- Multislice TPU `JobSet` queue setup on GKE: "Create the Kueue resources",
  "Define your Multislice workloads with JobSets", and "Verify Kueue admitted
  the workloads" in
  [Orchestrate Multislice workloads using JobSet and Kueue](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/tpu-multislice-kueue.md.txt).
- Job TTL cleanup (`ttlSecondsAfterFinished`): "TTL mechanism for finished Jobs"
  in
  [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/).

## Stage 2: Quota, cohort sharing, and reservations

- `nominalQuota`, `lendingLimit`, `borrowingLimit`, `borrowWithinCohort`,
  `reclaimWithinCohort`, and Fair Sharing ("ClusterQueue share value"):
  [ClusterQueue](https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/),
  [Cohort](https://kueue.sigs.k8s.io/docs/concepts/cohort/), and
  [Preemption](https://kueue.sigs.k8s.io/docs/concepts/preemption/).
- Reconfiguring GKE cohort quotas or preemption policies:
  - "Create the ClusterQueue and LocalQueue" and "Borrow unused quota with
    cohorts" in
    [Implement a Job queuing system with quota sharing between namespaces on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/kueue-cohort.md.txt).
  - "Enable Kueue workload priorities and preemption" in
    [Orchestrate Multislice workloads using JobSet and Kueue](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/tpu-multislice-kueue.md.txt).
  - "Test Kueue preemption and dynamic allocation on your mixed workload" in
    [Optimize GKE resource utilization for mixed AI/ML training and inference workloads](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/mixed-workloads.md.txt).
- Consuming reserved GPU or TPU capacity on GKE: "Consuming GPU reservations" or
  "Consuming TPU reservations" in
  [Consuming reserved zonal resources](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/consuming-reservations.md.txt).

## Stage 3: Flavor assignment, TAS, and transformations

- `ResourceFlavor` `nodeLabels`, `nodeTaints`, tolerations, and `topologyName`
  (including "Implicit TAS and mixed-flavor ClusterQueues"):
  [ResourceFlavor](https://kueue.sigs.k8s.io/docs/concepts/resource_flavor/) and
  [Topology Aware Scheduling](https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/).
- GKE flavor and dynamic slice TAS setup:
  - "Create the ResourceFlavors" in
    [Implement a Job queuing system with quota sharing between namespaces on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/kueue-cohort.md.txt).
  - "Create a dynamic slice with Kueue and TAS" and "Monitor the status of the
    slice" in
    [Schedule dynamic slices with Kueue and TAS](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/use-gke-dynamic-slicing.md.txt).
- Extended resource rewrites via `resources.transformations`
  (`ResourceTransformation` in `KueueConfiguration`):
  [KueueConfiguration v1beta2 reference](https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/)
  or
  [KueueConfiguration v1beta1 reference](https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/).

## Stage 4: Admission checks and DWS ProvisioningRequests

- `AdmissionCheck` and `ProvisioningRequestConfig` wiring and status:
  [AdmissionCheck](https://kueue.sigs.k8s.io/docs/concepts/admission_check/),
  [ProvisioningRequest AdmissionCheck](https://kueue.sigs.k8s.io/docs/concepts/admission_check/provisioning_request/),
  and
  [Troubleshooting ProvisioningRequest](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_provreq/).
- GKE Dynamic Workload Scheduler (DWS) read-only diagnostics ("Troubleshooting",
  "Observe the status of a Provisioning Request", "Troubleshoot quota issues",
  and "Check if the Provisioning Request request is limited by quota") and Kueue
  setup ("Flex-start with queued provisioning for Jobs with Kueue", "Create the
  Kueue resources for the Dynamic Workload Scheduler node pool only setup", and
  "Create the Kueue resources for Reservation and Dynamic Workload Scheduler
  node pool setup"):
  [Run a large-scale workload with flex-start with queued provisioning](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/provisioningrequest.md.txt).
- TPU DWS and Kueue configuration rules ("Define the configuration rules"):
  [Optimize AI training on TPUs with DWS and Kueue](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/ray-kueue-dws.md.txt).

## Stage 5: Post-admission scheduling, autoscaling, TPUs, and nodes

- External and topology scheduling gates (`kueue.x-k8s.io/topology`): "Why is my
  Pod not being scheduled if I am using external scheduling gates" in
  [Troubleshooting Pods](https://kueue.sigs.k8s.io/docs/tasks/troubleshooting/troubleshooting_pods/)
  and
  [Topology Aware Scheduling](https://kueue.sigs.k8s.io/docs/concepts/topology_aware_scheduling/).
- `waitForPodsReady` (`PodsReadyTimeout`, `RequeuingLimitExceeded`) and
  preemption:
  [Setup All-or-nothing with ready Pods](https://kueue.sigs.k8s.io/docs/tasks/manage/setup_wait_for_pods_ready/)
  and [Preemption](https://kueue.sigs.k8s.io/docs/concepts/preemption/).
- Job and JobSet failure policies (`backoffLimit`, `backoffLimitPerIndex`,
  `maxFailedIndexes`, `podFailurePolicy`):
  [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
  and
  [JobSet Troubleshooting](https://jobset.sigs.k8s.io/docs/troubleshooting/).
- Cluster Autoscaler `noScaleUp` and stockouts ("View errors in events",
  "ScaleUp errors", "Reasons for a noScaleUp event", "Pod doesn't fit on node",
  and "Unhealthy clusters prevent scale-up"):
  [Troubleshoot cluster autoscaler not scaling up](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/cluster-autoscaler-scale-up.md.txt).
- GKE TPU quota, capacity, and slice scheduling ("Insufficient quota to satisfy
  the TPU request", "Insufficient TPU resources to satisfy the TPU request",
  "GKE doesn't automatically provision TPU slice nodes", "Scheduling errors when
  deploying Pods that consume TPUs in GKE", and "Troubleshooting common issues
  with JobSets in GKE"):
  [Troubleshoot TPUs in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/tpus.md.txt).
- GKE `NotReady` nodes (`NetworkPluginNotReady` / CNI not initialized) and node
  auto-repair: "Check the node's status and conditions", "Troubleshoot network
  connectivity", "Troubleshoot core component failures", and "Verify that the
  node has recovered" in
  [Troubleshoot nodes with the NotReady status in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/node-notready.md.txt),
  plus "Settings for Autopilot and Standard", "Verify node auto-repair is
  enabled for a Standard node pool", and "Enable auto-repair for an existing
  Standard node pool" in
  [Auto-repair nodes](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/node-auto-repair.md.txt)
  (Autopilot clusters always have node auto-repair enabled; the verification and
  enablement sections apply only to Standard node pools).

## Stage 6: Controller configuration, logs, and support

- `KueueConfiguration` fields (`waitForPodsReady`, `clientConnection`,
  `integrations`, `resources.transformations`, `objectRetentionPolicies`):
  [KueueConfiguration v1beta2 reference](https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta2/),
  [KueueConfiguration v1beta1 reference](https://kueue.sigs.k8s.io/docs/reference/kueue-config.v1beta1/),
  and
  [Setup object retention policy](https://kueue.sigs.k8s.io/docs/tasks/manage/setup_object_retention_policy/).
- Modifying `data.controller_manager_config.yaml` (`kind: Configuration`) in
  `kueue-manager-config` and restarting `kueue-controller-manager`: "Install a
  custom-configured released version" and "Change the feature gates
  configuration" in
  [Installation](https://kueue.sigs.k8s.io/docs/getting-started/installation/),
  "Configure Kueue" in
  [Optimize GKE resource utilization for mixed AI/ML training and inference workloads](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/mixed-workloads.md.txt),
  and "Enable Slice reuse" in
  [Schedule dynamic slices with Kueue and TAS](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/use-gke-dynamic-slicing.md.txt).
- Control plane metrics ("Traffic and error rate", "Saturation") and Cloud
  Logging ("Accessing your logs", "Understanding your logs", "Resource types",
  "System logs", "Kubernetes Event logs", "Application logs", "Control plane
  component logs"):
  [Collect and view control plane metrics](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/control-plane-metrics.md.txt)
  and
  [View GKE logs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/view-logs.md.txt).
- Escalating Kueue defects or persistent GKE infrastructure issues: "Before you
  contact support" and "Recommendations for efficient support" in
  [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt).
