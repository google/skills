# TPU vBAR Failure Signatures

This document provides anonymized examples of logs and signals associated with
the `vbar_control_agent` race condition and OOMs on TPU v6e nodes.

## 1. Serial Console: `vbar_control_agent` OOM/Segfault

When the agent crashes, the serial console often contains process death messages
followed by a stack trace.

**Example Log:**

```text
[ 1234.567890] Memory cgroup out of memory: Killed process 5678 (vbar_control_ag) total-vm:4194304kB, anon-rss:2097152kB, file-rss:0kB, shmem-rss:0kB, UID:0 pgtables:8192kB oom_score_adj:0
```

## 2. Container Logs: Deserialize Failures

The `tpu-device-plugin` will report errors when it receives corrupt data from
the control agent.

**Example Log (LQL Filter Match):**

```sql
resource.type="k8s_container"
resource.labels.container_name="tpu-device-plugin"
severity=ERROR

"metrics fetch failed for 3 deviceID and /sys/bus/pci/devices/0000:00:08.0 device path with error: checksum didn't match with the metrics data. Corrupt data found"
```

## 3. High-Frequency Polling (Custom Scripts)

If the user is running `tpumonitoring` in a loop, you may see frequent
successful calls followed by a sudden gap and the crash.

**Observation Pattern:**

-   Successful `GetHostMetrics` calls (e.g. every 3s).
-   Device reset event (Node reboot or maintenance).
-   `vbar_control_agent` crash during next polling cycle.
