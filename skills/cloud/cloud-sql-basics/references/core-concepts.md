# Cloud SQL Core Concepts

Cloud SQL provides managed relational databases, abstracting the underlying
infrastructure while offering standard database engines.

## Cloud SQL Editions

Cloud SQL offers tier-based pricing and feature editions tailored to different
performance, availability, and operational requirements:

-   **Cloud SQL Enterprise Edition:**
    -   **Target Workloads:** Core business applications requiring standard 
        managed database capabilities.
    -   **Availability SLA:** 99.95% (excludes planned maintenance).
    -   **Performance & Hardware:** Shared core VMs (up to 1 vCPU, 1.7 GB RAM) 
        or Dedicated core VMs (up to 96 vCPU, 624 GB RAM, or N4 up to 80 vCPU / 
        624 GB RAM).
    -   **Maintenance Downtime:** Standard maintenance impact (< 30 seconds).
    -   **Point-in-Time Recovery (PITR):** Up to 7 days of log retention.

-   **Cloud SQL Enterprise Plus Edition:**
    -   **Target Workloads:** Mission-critical workloads requiring highest 
        availability, maximum read performance, and minimal operational downtime.
    -   **Availability SLA:** 99.99% (includes planned maintenance).
    -   **Performance & Hardware:** Powered by high-performance machine series 
        (N2, C4A up to 128 vCPU / 864 GB RAM) and SSD-based Data Cache for up to 
        4x improved read performance.
    -   **Maintenance Downtime:** Sub-second downtime (< 1 second) for maintenance 
        and planned scaling operations.
    -   **Enterprise Features:** Exclusive support for Read Pools, Managed 
        Connection Pooling, Advanced Disaster Recovery (DR) with cross-region 
        write endpoints, and 35-day PITR log retention.
    -   **Upgrades:** Supports in-place edition upgrades from Enterprise with 
        minimal or sub-second downtime.

## Supported Engines

Cloud SQL supports the following database engines (see [supported
versions](https://docs.cloud.google.com/sql/docs/db-versions.md.txt)):

-   **MySQL:** Versions 5.6, 5.7, 8.0, and 8.4.

-   **PostgreSQL:** Versions 9.6, 10, 11, 12, 13, 14, 15, 16, 17, and 18
    (default).

-   **SQL Server:** 2017 (Express, Web, Standard, Enterprise), 2019, 2022, and
    2025 (Express, Enterprise, Standard).

## Instance Architecture

Each Cloud SQL instance is powered by a virtual machine (VM) running the
database program.

-   **Primary Instance:** The main read/write connection point.

-   **High Availability (HA):** Provides a standby VM in a different zone with
    automatic failover.

-   **Read Replicas:** Used to scale read traffic and provide local access in
    different regions (individual single-node instances).

-   **Read Pools:** Multi-node load-balanced groups of read nodes designed for 
    high-concurrency read workloads.
    -   **Edition Requirement:** Supported exclusively on **Cloud SQL Enterprise Plus edition** 
        on the new network architecture.
    -   **Node Capacity & Limits:**
        -   **MySQL & PostgreSQL:** 1 to 20 read pool nodes.
        -   **SQL Server:** 1 to 7 read pool nodes.
        -   The combined total of standalone read replicas and read pool nodes per primary instance cannot exceed 20 (MySQL/PostgreSQL) or 7 (SQL Server).
    -   **Scaling Options:**
        -   **Manual Scaling:** Sub-second downtime for manual scale-out/scale-in 
            (adding or removing nodes) and scale-up/scale-down (changing node machine tiers).
        -   **Autoscaling:** Dynamically adjusts node counts between specified 
            `--auto-scale-min-node-count` and `--auto-scale-max-node-count` 
            thresholds based on `AVERAGE_CPU_UTILIZATION` or `AVERAGE_DB_CONNECTIONS`. 
            Supports configurable cooldown periods (default 600s, minimum 60s) 
            and optional scale-in disabling (`--auto-scale-disable-scale-in`).
    -   **High Availability & SLA:** Pools with 2 or more nodes are covered under the Cloud SQL SLA, with nodes distributed across zones within the region.
    -   **Routing & Consistency:** Routes traffic based on node process health 
        regardless of replication lag. Logical sessions connecting across 
        requests are not guaranteed read-your-own-writes consistency across 
        different nodes (LSN/GTID progress may differ).
    -   **Topology:** Must replicate directly from the primary instance (cascading read pools or cascading replicas to read pools are not supported).


## Storage and Networking

-   **Persistent Disk:** Scalable and durable network storage attached to the
    VM.

-   **Connectivity:** Supports Private IP (using VPC peering for MySQL and
    PostgreSQL only; or using private services access or Private Service Connect
    for all Cloud SQL engines) and Public IP (with authorized networks or Auth
    Proxy).

## Pricing

Cloud SQL pricing is based on:

-   **Instance Type:** vCPUs and RAM.

-   **Storage:** Amount of data stored and IOPS.

-   **Networking:** Network egress and IP address usage.

-   **DNS pricing:** Charge is per zone per month (regardless of whether you use
    your zone). You also pay for queries against your zones.

-   **Licensing:** Applies to SQL Server only. In addition to instance and
    resource pricing, SQL Server also has a licensing component. High
    availability, or regional instances, will only incur the cost for a single
    license for the active resource. As a managed service, Cloud SQL does not
    support BYOL (Bring your own license).

For the latest pricing, visit: [Cloud SQL
Pricing](https://cloud.google.com/sql/pricing).
