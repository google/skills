# Basic Hardened Nginx Deployment and Service Example

This reference example demonstrates a production-ready, security-hardened
Deployment and Service manifest on GKE.

It includes:

-   Explicit namespace and dedicated `ServiceAccount`
-   Non-root pod execution and read-only root filesystem with `emptyDir` mounts
-   Probes (`livenessProbe`, `readinessProbe`, `startupProbe`)
-   Anti-affinity for node distribution
-   `PodDisruptionBudget` for high availability during node maintenance

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: nginx-ns
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nginx-sa
  namespace: nginx-ns
  labels:
    app.kubernetes.io/name: nginx
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  namespace: nginx-ns
  labels:
    app.kubernetes.io/name: nginx
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: nginx
  template:
    metadata:
      labels:
        app.kubernetes.io/name: nginx
    spec:
      serviceAccountName: nginx-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 10000
        runAsGroup: 10000
        fsGroup: 10000
        seccompProfile:
          type: RuntimeDefault
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app.kubernetes.io/name
                      operator: In
                      values:
                        - nginx
                topologyKey: "kubernetes.io/hostname"
      containers:
        - name: nginx
          image: nginxinc/nginx-unprivileged:1.25
          ports:
            - name: http-web
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "250m"
              memory: "256Mi"
          volumeMounts:
            - name: nginx-cache
              mountPath: /var/cache/nginx
            - name: nginx-run
              mountPath: /var/run
            - name: nginx-tmp
              mountPath: /tmp
          livenessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          startupProbe:
            httpGet:
              path: /
              port: 8080
            failureThreshold: 30
            periodSeconds: 10
      volumes:
        - name: nginx-cache
          emptyDir: {}
        - name: nginx-run
          emptyDir: {}
        - name: nginx-tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
  namespace: nginx-ns
  labels:
    app.kubernetes.io/name: nginx
spec:
  selector:
    app.kubernetes.io/name: nginx
  ports:
    - name: http-web
      protocol: TCP
      port: 80
      targetPort: http-web
  type: ClusterIP
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: nginx-pdb
  namespace: nginx-ns
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: nginx
```
