# Bigtable Client Library User Guide

This document outlines critical technical details about Bigtable data model and
client libraries.

## Language Recommendations

For production use cases requiring the **best performance and feature
coverage**, **Java** or **Go** are highly recommended. These libraries are
mature, highly optimized, and typically receive new features first. Python is
suitable for scripting and data science but may have lower throughput for
high-concurrency production workloads.

-   [Go Example](https://docs.cloud.google.com/bigtable/docs/samples-go-hello)
-   [Java Example](https://docs.cloud.google.com/bigtable/docs/samples-java-hello-world)
-   [Python Example](https://docs.cloud.google.com/bigtable/docs/samples-python-hello)
-   [Node Example](https://docs.cloud.google.com/bigtable/docs/samples-nodejs-hello)

## Timestamp Precision & Granularity

Bigtable stores timestamps as **64-bit integers** representing **microseconds**
since the Unix epoch. However, Bigtable’s internal garbage collection and
versioning operate at **millisecond granularity**.

> [!IMPORTANT] **Implementation Rule:** When generating code to store data,
> calculate the timestamp in milliseconds and multiply by 1,000.
>
> *   **Correct:** `timestamp_micros = time_ms() * 1000`
> *   **Incorrect:** Using raw microsecond precision (e.g., `time_micros()`), as
>     this can lead to unexpected behavior with cell versioning and TTL.

## Replication & Atomic Operations

Bigtable’s replication model impacts the availability of certain "atomicity"
features. These atomic operations are generally less efficient than standard
writes.

*   **The Conflict:** **ReadModifyWrite** (increments/appends) and
    **CheckAndMutateRow** (conditional updates) require a single-point-of-truth
    to maintain consistency. They also require a read before a write, making
    them significantly slower and more resource-intensive than standard blind
    writes.
*   **The Constraint:** These operations **will not work** with multi-cluster
    routing (App Profiles set to Multi-cluster).
*   **Agent Action:** If a user’s code contains these methods, proactively warn
    them that these operations are inefficient and that they must use a
    **Single-cluster routing** App Profile or accept that these operations will
    fail in a multi-cluster configuration.
