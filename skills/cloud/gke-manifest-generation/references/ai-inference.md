# AI/LLM Inference Workload Example (vLLM & GCS FUSE)

This reference example demonstrates deploying an AI/LLM model serving workload
(such as Gemma 2 27B) on GKE.

It includes:

-   Workload Identity annotation for GCP authentication
-   GPU resource allocation (`nvidia.com/gpu`) and `nodeSelector` targeting
    accelerator types
-   GCS FUSE CSI driver volume mount (`csi.storage.gke.io`) for read-only model
    weight loading
-   Shared memory volume mount at `/dev/shm` (`emptyDir` with `medium: Memory`)
-   Extended `startupProbe` failure threshold to accommodate slow model
    initialization

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: gemma-ns
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gemma-sa
  namespace: gemma-ns
  annotations:
    iam.gke.io/gcp-service-account: {gcp_service_account_email}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gemma-27b-deployment
  namespace: gemma-ns
  labels:
    app.kubernetes.io/name: gemma-27b
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: gemma-27b
  template:
    metadata:
      labels:
        app.kubernetes.io/name: gemma-27b
      annotations:
        gke-gcsfuse/volumes: "true"
    spec:
      serviceAccountName: gemma-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 10000
        runAsGroup: 10000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: gemma-server
          image: vllm/vllm-openai:gemma2 # Example optimized image
          args: ["--model", "/models", "--tensor-parallel-size", "4"]
          ports:
            - name: http-api
              containerPort: 8000
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: "32"
              memory: "128Gi"
              nvidia.com/gpu: 4
            limits:
              cpu: "32"
              memory: "128Gi"
              nvidia.com/gpu: 4
          livenessProbe:
            httpGet:
              path: /healthz
              port: http-api
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /healthz
              port: http-api
            periodSeconds: 10
          startupProbe:
            httpGet:
              path: /healthz
              port: http-api
            failureThreshold: 60
            periodSeconds: 10
          volumeMounts:
            - name: model-weights
              mountPath: /models
              readOnly: true
            - name: dshm
              mountPath: /dev/shm
      nodeSelector:
        cloud.google.com/gke-accelerator: "nvidia-l4"
      volumes:
        - name: model-weights
          csi:
            driver: gcsfuse.csi.storage.gke.io
            readOnly: true
            volumeAttributes:
              bucketName: {gcs_bucket_name}
              mountOptions: "implicit-dirs"
        - name: dshm
          emptyDir:
            medium: Memory
```
