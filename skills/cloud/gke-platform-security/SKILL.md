---
name: gke-platform-security
description: >-
  Plans, configures, and hardens platform-level Google Kubernetes Engine (GKE)
  cluster security. Covers cluster add-ons (Secret Manager enablement), RBAC
  hardening (disabling insecure bindings, audit tools), Binary Authorization,
  enabling Shielded Nodes, GKE Sandbox cluster enablement, GKE IAM roles, and
  cross-service authentication IAM patterns. Use when securing cluster control
  planes, hardening GKE RBAC, enabling Shielded Nodes, enabling GKE Sandbox runtime,
  enabling cluster-wide security add-ons, or managing GKE IAM roles. Don't use
  for workload-level security (Workload Identity, SecretProviderClass, PSS, NetPol,
  gVisor pod runtimeClassName; use gke-workload-security instead).
metadata:
  category: Security
---

# GKE Platform Security

This reference covers platform-level security hardening and cluster
configuration for Google Kubernetes Engine (GKE). For workload-level security
controls (such as Workload Identity Service Account bindings,
SecretProviderClass volume mounts, Network Policies, and Pod Security
Standards), refer to the `gke-workload-security` skill.

> **MCP Tools:** `gke:get_cluster`, `k8s:check_k8s_auth`,
> `k8s:get_k8s_resource`, `k8s:apply_k8s_manifest`, `gke:update_cluster`

## Golden Path Security Defaults

Setting                                                        | Golden Path Value                       | Day-0/1 | Notes
-------------------------------------------------------------- | --------------------------------------- | ------- | -----
`workloadIdentityConfig.workloadPool`                          | `<PROJECT>.svc.id.goog`                 | Day-0   | Workload Identity Federation for cluster pods
`secretManagerConfig.enabled`                                  | `true`                                  | Day-1   | Google Secret Manager cluster add-on integration
`secretManagerConfig.rotationConfig`                           | `enabled: true, rotationInterval: 120s` | Day-1   | Automatic secret rotation at the cluster level
`rbacBindingConfig.enableInsecureBindingSystemAuthenticated`   | `false`                                 | Day-0   | Blocks legacy `system:authenticated` bindings
`rbacBindingConfig.enableInsecureBindingSystemUnauthenticated` | `false`                                 | Day-0   | Blocks legacy `system:unauthenticated` bindings
`nodeConfig.shieldedInstanceConfig.enableSecureBoot`           | `true`                                  | Day-0   | Verifiable boot integrity
`nodeConfig.shieldedInstanceConfig.enableIntegrityMonitoring`  | `true`                                  | Day-0   | Runtime integrity checks
`nodeConfig.workloadMetadataConfig.mode`                       | `GKE_METADATA`                          | Day-0   | Blocks legacy metadata API, enforces Workload Identity
Private cluster + Dataplane V2 settings                        | See the `gke-networking` skill          | Day-0   | Private nodes, private endpoint enforcement, ADVANCED_DATAPATH

## Secret Manager Add-on Enablement

The golden path enables Secret Manager at the cluster level with automatic
secret rotation.

```bash
# Verify Secret Manager is enabled on cluster
gcloud container clusters describe <CLUSTER_NAME> --region <REGION> \
  --format="value(secretManagerConfig.enabled)" \
  --quiet

# Enable if not already (Day-1 change)
gcloud container clusters update <CLUSTER_NAME> --region <REGION> \
  --enable-secret-manager \
  --secret-manager-rotation-interval=120s \
  --quiet
```

> **Note:** For configuring `SecretProviderClass` manifests and mounting secrets
> as volumes inside application deployments, see the `gke-workload-security`
> skill.

## RBAC Hardening

The golden path disables insecure legacy RBAC bindings that grant broad access
to `system:authenticated` and `system:unauthenticated` groups.

```bash
# Verify insecure bindings are disabled
gcloud container clusters describe <CLUSTER_NAME> --region <REGION> \
  --format="yaml(rbacBindingConfig)" \
  --quiet
```

**Best practices for RBAC:**

-   Use namespace-scoped Roles over cluster-wide ClusterRoles.
-   Bind to specific Groups or ServiceAccounts, never to `system:authenticated`
    or `system:unauthenticated`.
-   Audit permissions via MCP: `k8s:check_k8s_auth(parent="...", verb="list",
    resourceType="pods", namespace="...")` (or `kubectl auth can-i --list
    --as=<user>`).
-   Review bindings via MCP: `k8s:get_k8s_resource(parent="...",
    resourceType="clusterrolebinding")` (or `kubectl get
    clusterrolebindings,rolebindings --all-namespaces`).

> See the `gke-multitenancy` skill for enterprise RBAC planning and
> https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/rbac.md.txt

## Binary Authorization

Not enabled in golden path by default but recommended for enforcing production
image provenance across the cluster:

```bash
# Enable Binary Authorization
gcloud container clusters update <CLUSTER_NAME> --region <REGION> \
  --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE \
  --quiet
```

## Shielded Nodes & GKE Sandbox Enablement

Enabling verifiable node boot integrity and kernel isolation features at the
cluster level:

```bash
# Enable Shielded Nodes on an existing cluster
gcloud container clusters update <CLUSTER_NAME> --region <REGION> \
  --enable-shielded-nodes \
  --quiet

# Enable GKE Sandbox (gVisor) runtime on an existing cluster
gcloud container clusters update <CLUSTER_NAME> --region <REGION> \
  --enable-gke-sandbox \
  --quiet
```

> **Note:** To run workloads inside the gVisor sandbox, specify
> `runtimeClassName: gvisor` in your Pod specs as detailed in the
> `gke-workload-security` skill.

## Common IAM Roles

The five most common predefined IAM roles for GKE platform and cluster access:

| Role                            | Purpose             | When to Use          |
| ------------------------------- | ------------------- | -------------------- |
| `roles/container.admin`         | Full control over   | Platform team admins |
:                                 : clusters and        : managing cluster     :
:                                 : Kubernetes          : lifecycle            :
:                                 : resources           :                      :
| `roles/container.clusterAdmin`  | Manage clusters but | Cluster operators    |
:                                 : not project-level   : who create/delete    :
:                                 : IAM                 : clusters             :
| `roles/container.developer`     | Deploy workloads    | Application          |
:                                 : (pods, services,    : developers deploying :
:                                 : deployments)        : to existing clusters :
| `roles/container.viewer`        | Read-only access to | Monitoring,          |
:                                 : clusters and        : auditing, or         :
:                                 : Kubernetes          : read-only dashboards :
:                                 : resources           :                      :
| `roles/container.clusterViewer` | List and get        | CI/CD pipelines that |
:                                 : cluster details     : need cluster         :
:                                 : only                : metadata             :

> **Principle of least privilege**: Start with `roles/container.viewer` or
> `roles/container.developer` and escalate only as needed. Avoid granting
> `roles/container.admin` broadly across teams.

## Service Accounts & Agents

-   **GKE Service Agent**
    (`service-<PROJECT_NUMBER>@container-engine-robot.iam.gserviceaccount.com`):
    Automatically created. Manages nodes, networking, and cluster operations on
    your behalf. Do not remove or modify its permissions.
-   **Node Service Account**: By default, nodes use the Compute Engine default
    service account. For production platforms, create a dedicated Google Service
    Account with minimal required permissions (`roles/monitoring.metricWriter`,
    `roles/logging.logWriter`) and assign it at node pool creation time.
-   **Workload Identity**: For binding Google Service Accounts to Kubernetes
    Service Accounts (`roles/iam.workloadIdentityUser`), refer to the
    `gke-workload-security` skill.

## Cross-Service Authentication Patterns

Common project-level IAM policy binding patterns for granting backend Google
Service Accounts (GSAs) access to external Google Cloud services before linking
via Workload Identity:

```bash
# Grant a GSA access to Cloud Storage objects
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member "serviceAccount:<GSA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role "roles/storage.objectViewer" \
  --quiet

# Grant a GSA access to Cloud SQL databases
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member "serviceAccount:<GSA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role "roles/cloudsql.client" \
  --quiet

# Grant a GSA access to Pub/Sub subscriptions
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member "serviceAccount:<GSA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role "roles/pubsub.subscriber" \
  --quiet

## Resources

- [GKE Cluster Hardening Guide](https://cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster)
- [GKE RBAC Best Practices](https://cloud.google.com/kubernetes-engine/docs/best-practices/rbac)
- [Secret Manager Add-on for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/secret-manager)
- [Binary Authorization on GKE](https://cloud.google.com/binary-authorization/docs/getting-started-gke)
- [Shielded GKE Nodes](https://cloud.google.com/kubernetes-engine/docs/how-to/shielded-gke-nodes)
- [GKE Sandbox (gVisor)](https://cloud.google.com/kubernetes-engine/docs/concepts/sandbox)
```
