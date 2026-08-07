---
name: gke-workload-security
description: >-
  Audits, configures, and hardens workload-level security controls for Google
  Kubernetes Engine (GKE) applications and namespaces. Covers running cluster security
  audits (`audit_cluster.sh`), configuring Workload Identity Federation (impersonation,
  KSA/GSA binding, and pod setup), enforcing Network Policies (default-deny and Dataplane
  V2 logging), isolating high-risk pods inside GKE Sandbox (`gVisor`), enforcing Pod
  Security Standards (`restricted` labeling), and mounting Secret Manager secrets via
  CSI (`SecretProviderClass`). Use when auditing cluster security posture, isolating
  namespaces, applying pod security standards, setting up Workload Identity, or
  configuring network policies and secret volume mounts. Don't use for cluster-wide
  control plane security, RBAC hardening, Binary Authorization, Shielded Nodes,
  or enabling platform-level GKE add-ons (use gke-platform-security instead).
metadata:
  category: Security
---

# GKE Workload Security

This skill provides workflows and best practices for securing GKE workloads. It
covers security auditing, Identity and Access Management (Workload Identity),
Network Security (Network Policies), and Node Security.

## Workflows

### 1. Security Audit

Assess the current security posture of your cluster using the provided audit
script.

**Prerequisites:**

-   `gcloud` CLI authenticated.
-   `jq` command-line JSON processor installed.

**Capabilities:**

-   Checks for Workload Identity.
-   Verifies Network Policy is enabled.
-   Checks if Shielded Nodes are enabled.
-   Checks if Binary Authorization is enabled.
-   Checks for Private Cluster configuration.

**Command:**

```bash
scripts/audit_cluster.sh <cluster-name> <region> <project-id>
```

### 2. Configure Workload Identity

Workload Identity allows Kubernetes Service Accounts (KSAs) to impersonate
Google Service Accounts (GSAs). This is the recommended method for workloads to
access Google Cloud APIs.

**Steps:**

1.  **Create Namespace and KSA:**

    ```bash
    kubectl create namespace workload-identity-test-ns
    kubectl create serviceaccount <ksa-name> \
        --namespace workload-identity-test-ns
    ```

2.  **Bind KSA to GSA:**

    ```bash
    gcloud iam service-accounts add-iam-policy-binding <gsa-name>@<project-id>.iam.gserviceaccount.com \
        --role roles/iam.workloadIdentityUser \
        --member "serviceAccount:<project-id>.svc.id.goog[workload-identity-test-ns/<ksa-name>]"
    ```

3.  **Annotate KSA:**

    ```bash
    kubectl annotate serviceaccount <ksa-name> \
        --namespace workload-identity-test-ns \
        iam.gke.io/gcp-service-account=<gsa-name>@<project-id>.iam.gserviceaccount.com
    ```

4.  **Verify Example Pod:** Use existing asset
    `assets/workload-identity-pod.yaml` to test the configuration. Update the
    `<ksa-name>` in the file first.

    ```bash
    kubectl apply -f assets/workload-identity-pod.yaml -n workload-identity-test-ns
    ```

### 3. Implement Network Policies

Control traffic flow between Pods using Network Policies. By default, all
traffic is allowed.

**Enable Network Policy Enforcement:**

```bash
gcloud container clusters update <cluster-name> \
    --update-addons=NetworkPolicy=ENABLED \
    --region <region>
```

> [!NOTE] If your cluster uses Dataplane V2 (`--enable-dataplane-v2`), Network
> Policy enforcement is built-in and this step is not required (and may fail).

**Apply Default Deny Policy:** Isolate namespaces by denying all ingress and
egress traffic by default.

**Replace `<target-namespace>` with the namespace you want to isolate.**

```bash
kubectl apply -f assets/default-deny-netpol.yaml -n <target-namespace>
```

### 4. GKE Sandbox (gVisor) Pod Isolation

Run untrusted workloads in a sandbox for extra kernel isolation. *(Note:
Enabling Shielded Nodes (`--enable-shielded-nodes`) and GKE Sandbox
(`--enable-gke-sandbox`) at the cluster control plane level are platform-level
actions covered in the `gke-platform-security` skill.)*

**Run a Sandboxed Pod:** Add `runtimeClassName: gvisor` to your Pod spec:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sandboxed-pod
spec:
  runtimeClassName: gvisor
  containers:
  - name: app
    image: nginx
```

### 5. Pod Security Standards

Enforce security policies on namespaces using labels.

**Enforce Restricted Profile:**

```bash
kubectl label --overwrite ns <namespace> \
    pod-security.kubernetes.io/enforce=restricted \
    pod-security.kubernetes.io/enforce-version=latest
```

> [!NOTE] Using `latest` ensures you use the policies corresponding to the
> cluster's current version. You can pin it to a specific version (e.g.,
> `v1.30`) to lock down the namespace to policies of a specific release.

### 6. Secret Manager Integration (CSI Driver)

Mount secrets from Google Cloud Secret Manager directly as volumes in your pods.

**Prerequisites**: Secret Manager CSI driver must be enabled on the cluster.

**Example SecretProviderClass:**

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: my-secret-provider
spec:
  provider: gcp
  parameters:
    secrets: |
      - resourceName: "projects/<project-id>/secrets/my-secret/versions/latest"
        fileName: "my-secret-file"
```

**Example Pod Spec excerpt:**

```yaml
spec:
  containers:
    - name: my-app
      volumeMounts:
        - name: secrets-store-inline
          mountPath: "/mnt/secrets"
          readOnly: true
  volumes:
    - name: secrets-store-inline
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: "my-secret-provider"
```

### 7. Enable Network Policy Logging

If using GKE Dataplane V2, you can log allowed and denied connections.

**Steps:**

1.  Configure the `NetworkLogging` custom resource.

**Example NetworkLogging Manifest:**

```yaml
apiVersion: networking.gke.io/v1alpha1
kind: NetworkLogging
metadata:
  name: default
spec:
  cluster:
    allow:
      log: true
      delegate: true
    deny:
      log: true
      delegate: true
```

This will log connection details to Cloud Logging.

## Best Practices

1.  **Least Privilege:** Always use Workload Identity with minimal IAM roles.
    Avoid using Node default service accounts.
2.  **Network Isolation:** Use Network Policies to restrict Pod-to-Pod
    communication. Enable Network Policy Logging for visibility.
3.  **Image Security:** Use Binary Authorization to ensure only trusted images
    are deployed.
4.  **Secret Management**: Use Secret Manager CSI driver instead of default
    Kubernetes secrets for sensitive data.
5.  **Pod Security**: Enforce `baseline` or `restricted` Pod Security Standards
    on all non-system namespaces.
6.  **Policy Enforcement**: Consider using **Policy Controller** (Gatekeeper) to
    enforce custom security and compliance policies across the cluster.

## Resources

-   [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
-   [GKE Network Policies](https://cloud.google.com/kubernetes-engine/docs/how-to/network-policy)
-   [Pod Security Standards in GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/pod-security-standards)
-   [Google Secret Manager CSI Driver](https://cloud.google.com/kubernetes-engine/docs/how-to/secret-manager)
-   [GKE Dataplane V2 Network Logging](https://cloud.google.com/kubernetes-engine/docs/how-to/network-policy-logging)
