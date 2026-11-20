# ComputeClass authoritative code index

This reference maps GKE ComputeClasses behaviors, lifecycle events, and priority rules directly to source files and key function symbols in the open-source repository: [https://github.com/GoogleCloudPlatform/cluster-autoscaler](https://github.com/GoogleCloudPlatform/cluster-autoscaler).

When verifying behavior or investigating edge cases, clone the repository or fetch raw source files directly from GitHub.

---

## Code mapping by behavioral domain

### 1. Prioritization, fallback ladders, and cooldowns

| Behavior / Feature | Source File Path | Key Structs & Functions | Behavioral Notes |
|---|---|---|---|
| **Priority rule evaluation & grouping** | `pkg/computeclass/organizer.go` | `organizer.organizeByRules`, `groupRulesByScore` | Sorts and evaluates `priorities[]` top-to-bottom. Rules sharing `priorityScore` evaluate as a single tier. |
| **5-minute fixed cooldown** | `pkg/backoff/gke_mig_backoff.go` | `NpcBackoffDuration = 5 * time.Minute` | Fixed non-exponential cooldown applied to failing declarative priority rungs upon stockout. |
| **Cumulative cooldown prolongation** | `pkg/backoff/npc_backoff.go` | `npcCrdBackoff.Backoff`, `npcCrdBackoff.BackoffStatus` | Reset and prolonged to `currentTime + 5m` across all previously failing rungs when a lower priority fails sequentially. |
| **Fallback floor safety guarantee** | `pkg/backoff/npc_backoff.go` | `getRuleCount`, line check `ruleIdx >= getRuleCount(npcCrd)-1` | The final priority rule (and implicit `ScaleUpAnyway` fallback tier) is never backed off by `npcCrdBackoff`. |
| **Manual `priorities[].nodepools` bypass** | `pkg/backoff/npc_backoff.go` | `len(rule.NodePoolNames()) > 0` | Manual node pool rules bypass `npcCrdBackoff` and rely strictly on standard GCE MIG backoffs. |
| **Zonal stockout backoff tracking** | `pkg/backoff/npc_backoff.go` | `rules map[int]map[string]bool` | GKE 1.36.3-gke.1244000+ tracks stockouts per zone (`ruleIdx -> zone -> isBackedOff`). |
| **Regional quota backoff handling** | `pkg/backoff/npc_backoff.go` | `if strings.Contains(errorInfo.ErrorCode, "QUOTA") { zone = "" }` | Quota errors apply rule-wide / regionally across all zones. |
| **DWS Flex Start queuing delay** | `pkg/cloudprovider/gke/gke_cloud_provider_impl.go` | `DefaultFlexStartCapacityCheckWaitTime = 15 * time.Minute` | The 15m constant is a code failsafe, not the effective default: GKE falls back once the initial attempt fails (~3 min) unless `capacityCheckWaitTimeSeconds` extends the wait (max 30m provisioning wait). |

---

### 2. Active migration, evictions, and defragmentation

| Behavior / Feature | Source File Path | Key Structs & Functions | Behavioral Notes |
|---|---|---|---|
| **Active migration drift controller** | `pkg/defrag/plugins/highprioritymigration/high_priority_migration.go` | `NewCandidate`, `IsExpansionOptionValid` | Discovers nodes on lower priority rungs (`priorityGroupIndex > 0`) and triggers scale-up of preferred tier. |
| **Voluntary eviction execution** | `pkg/defrag/processor/actuation.go` | `ScaleDownActuator.StartDeletion` | Issues graceful drain and calls Kubernetes Eviction API for candidate pods once new nodes are ready. |
| **PodDisruptionBudget (PDB) enforcement** | `pkg/defrag/processor/node_filter.go` | `nodeFilter.hasBlockingPods`, `RemainingPdbTracker` | Checks remaining disruptions; `maxUnavailable: 0` blocks active migration and scale-down node deletion. |
| **`safe-to-evict: "on-completion"` handling** | `pkg/defrag/processor/node_filter.go` | `nodeFilter.hasBlockingPods` | Workloads annotated with `"on-completion"` defer defragmentation/active migration until the pod finishes. |
| **DaemonSet exclusion during drain** | `pkg/defrag/processor/simulation.go` | `podutils.FilterRecreatablePods` | DaemonSets are stripped during simulation and do not block node drain or consolidation. |

---

### 3. Machine selection, storage, and taints

| Behavior / Feature | Source File Path | Key Structs & Functions | Behavioral Notes |
|---|---|---|---|
| **Machine family selection (NAP)** | `pkg/autoprovisioning/machineselection/machine_selection.go` | `Selector.selectMachineGroup`, `podFamily.go` | Evaluates ComputeClass priorities, pod family fallbacks, accelerator inference, and default families. |
| **Default disk type assignment** | `pkg/cloudprovider/gke/machinetypes/machine_family.go` | `family.DefaultDiskType()` | C3, C4, N4 default to `hyperdisk-balanced`; E2, N1, N2 default to `pd-balanced` / `pd-standard`. |
| **`dynamic-rwo` CSI StorageClass bypass** | `pkg/processors/storage_node_affinity_processor.go` | `StorageNodeAffinityPodListProcessor.Process` | `type: dynamic` skips `disk-type.gke.io/*` nodeSelector injection, allowing pods to span C4 (Hyperdisk) and N2 (PD). |
| **ComputeClass taint inheritance** | `pkg/podrequirements/pod_requirements.go`, `pkg/autoprovisioning/injection.go` | workload-separation taints; user-taint merge | Auto-created pools for a custom ComputeClass get the `cloud.google.com/compute-class` taint through workload separation (GKE adds the matching toleration to Pods that select the class); `nodePoolConfig.taints` and per-rule taints are merged afterwards, the user value winning on a key+effect collision (`nodePoolConfig.taints` entries with system label keys such as `cloud.google.com/*` are dropped, so only per-rule `priorities[].taints` can collide with the `cloud.google.com/compute-class` taint). |
| **GPU taints vs selector labels** | `pkg/autoprovisioning/injection.go` | `nvidia.com/gpu:NoSchedule` | Accelerator label is `cloud.google.com/gke-accelerator`; node taint is `nvidia.com/gpu:NoSchedule`. |
| **Native minimumCapacity injection** | `pkg/computeclass/processors/min_capacity_pod_list_processor.go` | `minCapacityPodListProcessor.Process` | Simulates node floors using synthetic fake pods with `FakePodAntiAffinityHostPort = 10250`. |

---

## Code verification instructions

When troubleshooting or investigating behavioral changes:
1. **Search Git Log by Symbol**:
   ```bash
   git log -S "<function_or_const_name>" -p -- <filepath>
   ```
2. **Inspect Blame on Target File**:
   ```bash
   git blame -L <start_line>,<end_line> <filepath>
   ```
3. **Trace Behavioral Evolution**:
   - Determine the commit date and message when a logic branch was altered.
   - If the exact GKE patch version is unreleased or not yet documented, communicate the commit hash, upstream PR, and date range to the user.
