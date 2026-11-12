<!-- disableFinding(LINE_OVER_80) -->
<!-- disableFinding(LIST_NO_LINE) -->
<!-- disableFinding(LINK_ID) -->

# Google Cloud Filestore VPC Network & Firewall Specification

This reference details the networking architecture, port requirements, Private
Services Access (PSA) peering, and firewall rules required for seamless Google
Cloud Filestore operation.

## Table of Contents

*   [1. Required Network Ports for Filestore NFS](#1-required-network-ports-for-filestore-nfs):
    Lines 23-76
*   [2. Private Services Access (PSA) & Peering Architecture](#2-private-services-access-psa--peering-architecture):
    Lines 79-100
*   [3. Shared VPC (Cross-Project Networking)](#3-shared-vpc-cross-project-networking):
    Lines 104-132
*   [4. Attributed Ingress Firewall Rule Remediation](#4-attributed-ingress-firewall-rule-remediation):
    Lines 136-148

--------------------------------------------------------------------------------

## 1. Required Network Ports for Filestore NFS

Filestore supports **NFSv3** across all service tiers (`Basic HDD`, `Basic SSD`,
`Zonal`, `Regional`, `Enterprise`) and **NFSv4.1** on `Zonal`, `Regional`, and
`Enterprise` tiers. The following ports must be reachable between client VMs/GKE
nodes and the Filestore instance IP range:

| Port       | Protocol      | Service                  | Protocol Version & |
:            :               :                          : Purpose            :
| :--------- | :------------ | :----------------------- | :----------------- |
| **`2049`** | **TCP / UDP** | **NFS Server (`nfsd`)**  | **Mandatory (NFSv3 |
:            :               :                          : & NFSv4.1)**.      :
:            :               :                          : Primary NFS file   :
:            :               :                          : operations (mount, :
:            :               :                          : read, write,       :
:            :               :                          : lookup). Note\:    :
:            :               :                          : NFSv4.1 requires   :
:            :               :                          : **only TCP         :
:            :               :                          : `2049`**.          :
| **`111`**  | **TCP / UDP** | **RPCbind / Portmapper** | **Mandatory for    |
:            :               :                          : NFSv3**. Dynamic   :
:            :               :                          : port discovery for :
:            :               :                          : `mountd`, `statd`, :
:            :               :                          : and `nlockmgr`.    :
| **`2046`** | **TCP / UDP** | **`statd` (Status        | **Required for     |
:            :               : Monitor)**               : NFSv3 File         :
:            :               :                          : Locking**. Network :
:            :               :                          : status monitor     :
:            :               :                          : used for lock      :
:            :               :                          : recovery after     :
:            :               :                          : reboots.           :
| **`2050`** | **TCP / UDP** | **`mountd` (Mount        | **Required for     |
:            :               : Daemon)**                : NFSv3**. Handles   :
:            :               :                          : initial NFSv3      :
:            :               :                          : mount requests and :
:            :               :                          : export path        :
:            :               :                          : validation.        :
| **`4045`** | **TCP / UDP** | **`nlockmgr` (Lock       | **Required for     |
:            :               : Manager)**               : NFSv3 File         :
:            :               :                          : Locking**. Network :
:            :               :                          : Lock Manager       :
:            :               :                          : (`NLM`) protocol   :
:            :               :                          : for advisory file  :
:            :               :                          : locks              :
:            :               :                          : (`fcntl`/`flock`). :

> **Best Practice & Directionality**: - **Baseline Connectivity (`2049` &
> `111`)**: Opening TCP/UDP ports `2049` and `111` resolves 99% of initial mount
> timeouts (`ETIMEDOUT` / `RPC: Program not registered`). - **Full NFSv3 Locking
> (`111,2046,2049,2050,4045`)**: Workloads using file locking on NFSv3 require
> all five ports (`111,2046,2049,2050,4045`) open in both **Egress** (client VM
> to Filestore IP) and **Ingress** (Filestore IP / client subnet for lock
> callbacks and `statd` notifications).

--------------------------------------------------------------------------------

## 2. Private Services Access (PSA) & Peering Architecture

Filestore instances do not live directly inside customer Compute Engine subnets.
Instead:

1.  Filestore instances are provisioned within a **Google-managed service tenant
    project**.
2.  The tenant VPC is connected to the customer VPC via a **Private Services
    Access (PSA)** VPC Network Peering connection
    (`servicenetworking-googleapis-com`).
3.  The instance receives a private RFC 1918 internal IP from the reserved IP
    range allocated for Google services.

### Cross-VPC / Hybrid Connectivity (VPN & Cloud Interconnect):

If clients mounting Filestore reside on-premises or in a peered VPC:

*   The customer VPC peering connection to `servicenetworking-googleapis-com`
    must have **"Export custom routes"** enabled.
*   The Cloud Router / BGP sessions must advertise the Filestore IP range to
    on-premises networks.

--------------------------------------------------------------------------------

## 3. Shared VPC (Cross-Project Networking)

In enterprise Google Cloud landing zones, Filestore instances are frequently
deployed in a **Service Project** while attached to a VPC network hosted in a
centralized **Host Project**:

```
┌────────────────────────────────────────────────────────┐
│ Host Project (projects/network-hub-prod)               │
│                                                        │
│   VPC Network: prod-vpc                                │
│   Firewall Rules: Managed HERE!                        │
└──────────────────────────┬─────────────────────────────┘
                           │ Shared VPC Attachment
                           ▼
┌────────────────────────────────────────────────────────┐
│ Service Project (projects/analytics-prod)              │
│                                                        │
│   Filestore Instance: finance-share                    │
│   Network: projects/network-hub-prod/global/networks/… │
└────────────────────────────────────────────────────────┘
```

### Critical Firewall Administration Rule for Shared VPC:

*   Firewall rules evaluated by the VPC network live in the **Host Project**
    (`network-hub-prod`).
*   Querying or creating firewall rules in the Service Project
    (`analytics-prod`) will have **no effect** and will report empty rules.
*   Remediation commands must target `--project={HOST_PROJECT_ID}`.

--------------------------------------------------------------------------------

## 4. Ingress Firewall Rule Remediation

```bash
gcloud compute firewall-rules create allow-{network_name}-filestore-nfs \
    --network="{network_name}" \
    --direction=INGRESS \
    --priority=1000 \
    --action=ALLOW \
    --rules=tcp:2049,udp:2049,tcp:111,udp:111 \
    --source-ranges="{client_subnet_cidr}" \
    --project="{host_project_id}"
```
