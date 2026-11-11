# Google Cloud Filestore Instance Tiers & Architecture

This reference provides architectural context for Cloud Filestore service tiers.

## Simplified Naming (Console) vs. API Enums
Google Cloud rebranded Filestore tiers in the UI. For API/CLI operations, legacy enums are still widely used:
- **Basic HDD / SSD** (`BASIC_HDD`, `BASIC_SSD`): Single-node architecture. Standard or Premium performance.
- **Zonal** (`ZONAL`, legacy: `HIGH_SCALE_SSD`): Scale-out single-zone cluster.
- **Regional** (`REGIONAL`, legacy: `ENTERPRISE`): Scale-out multi-zone HA cluster.

## Architecture Profiles

### Basic Tiers (Scale-Up Only)
- **Architecture**: A single Compute Engine VM attached to Persistent Disk (Standard or SSD).
- **Behavior**: You can increase the capacity of a Basic tier instance, but you **cannot decrease it**. The underlying disk cannot be shrunk.
- **Performance**: Predictable IOPS and throughput scaling linearly with capacity.

### Scale-Out Tiers (Zonal & Regional)
- **Architecture**: ECFS (Elastifile Cloud File System) multi-node cluster.
- **Behavior**: These tiers support both **Scale-up** and **Scale-down**, providing significant flexibility for cost optimization.
- **Capacity Bands**:
  - Regional Small Band: 100 GiB - 10,239 GiB (1 GiB increments).
  - Zonal Small Band: 1 TiB - 9.75 TiB (256 GiB increments).
  - Large Band: 10 TiB - 100 TiB.
  - *Instances cannot currently cross the boundary between small and large bands.*
- **Availability**:
  - Zonal: Data is replicated within a single GCP zone.

### Sample Mock Fleet Instances (For Read-Only Analysis & Evals)

When Filestore API / MCP tools are not present:
- **Project `analytics-prod`**:
  - `prod-vol`: Basic HDD tier (`BASIC_HDD`), 10 TiB capacity, 9 TiB used space (10% free space / 90% utilized).


## Tier & Capacity Limits Matrix

Filestore tiers enforce specific boundaries and behaviors. The skill must accept both modern UI names (`Basic`, `Zonal`, `Regional`) and legacy API enums interchangeably.

| Service Tier (UI & API Enums) | Min Capacity | Max Capacity | Scaling Step Increment | Scale-Up? | Scale-Down? |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Basic HDD** (`BASIC_HDD` / `STANDARD`) | **1 TiB** (100 GiB on GKE) | **63.9 TiB** | **1 GiB** | Yes | **No (Scale-Up Only)** |
| **Basic SSD** (`BASIC_SSD` / `PREMIUM`) | **2.5 TiB** | **63.9 TiB** | **1 GiB** | Yes | **No (Scale-Up Only)** |
| **Regional (Small Band)** (`REGIONAL`) | **100 GiB** | **10,239 GiB** | **1 GiB** | Yes | **Yes** (Floor: 100 GiB, usage) |
| **Regional (Large Band)** (`REGIONAL`) | **10 TiB** | **100 TiB** | **2.5 TiB** | Yes | **Yes** (Floor: 10 TiB, usage) |
| **Zonal (Small Band)** (`ZONAL`) | **1 TiB** | **9.75 TiB** | **256 GiB** | Yes | **Yes** (Floor: 1 TiB, usage) |
| **Zonal (Large Band)** (`ZONAL`, `HIGH_SCALE_SSD`)| **10 TiB** | **100 TiB** | **2.5 TiB** | Yes | **Yes** (Floor: 10 TiB, usage) |
| **Enterprise** (`ENTERPRISE`) | **1 TiB** | **10 TiB** | **256 GiB** | Yes | **Yes** (Floor: 1 TiB, usage) |

