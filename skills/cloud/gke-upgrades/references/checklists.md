# Checklist Templates

Adapt these to the user's environment. Fill in cluster names, versions, and remove items that don't apply.

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard / Autopilot | Channel: ___
- [ ] Current version: ___ | Target version: ___

Compatibility
- [ ] Target version available in release channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for breaking changes between current → target
- [ ] Node version skew within 2 minor versions of control plane
- [ ] Third-party operators/controllers compatible with target version
- [ ] Admission webhooks tested against target version

Workload Readiness
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Resource requests/limits set on all containers (mandatory for Autopilot)
- [ ] GPU driver compatibility confirmed with target node image (if applicable)
- [ ] Postgres/database operator compatibility verified (if applicable)

Infrastructure (Standard only)
- [ ] Node pool upgrade strategy chosen (surge / blue-green)
- [ ] Surge settings configured per pool: maxSurge=___ maxUnavailable=___
- [ ] Sufficient compute quota for surge nodes
- [ ] Maintenance window configured (off-peak hours)
- [ ] Maintenance exclusions set for freeze periods (if applicable)

Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring / Prometheus)
- [ ] Baseline metrics captured (error rates, latency, throughput)
- [ ] Upgrade window communicated to stakeholders
- [ ] Rollback plan documented
- [ ] On-call team aware and available
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist

Cluster Health
- [ ] Control plane at target version: `gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"`
- [ ] All node pools at target version: `gcloud container node-pools list --cluster CLUSTER --zone ZONE`
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces`

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/load balancers responding
- [ ] Application health checks and smoke tests passing

Observability
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to aggregation
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline

Cleanup
- [ ] Old node pools removed (if blue-green)
- [ ] Surge quota released (automatic for surge upgrades)
- [ ] Upgrade documented in changelog
- [ ] Lessons learned captured
```
