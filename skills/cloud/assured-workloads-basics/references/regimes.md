# Assured Workloads V1 Compliance Regimes & Supported Locations

This reference lists the compliance regimes (control packages) supported by Assured Workloads V1 (`gcloud assured workloads create --compliance-regime={compliance_regime}`), their modern Data Boundary enum names, legacy aliases, supported locations, and sovereign control requirements.

> **Important:** Assured Workloads V1 is a **regional/multi-regional** API. Never pass `--location=global` to `gcloud assured workloads` V1 commands. Always select a valid regional or multi-regional location matching your compliance regime below.

## Table of Contents
- [1. How Free-Tier Regional Data Boundaries Work (`REGIONAL_DATA_BOUNDARY`)](#1-how-free-tier-regional-data-boundaries-work-regional_data_boundary): Lines 17-49
- [2. United States (US) Regulatory & Support Control Packages](#2-united-states-us-regulatory--support-control-packages): Lines 53-69
- [3. European Union (EU) & Switzerland Control Packages](#3-european-union-eu--switzerland-control-packages): Lines 73-78
- [4. Canada Control Packages](#4-canada-control-packages): Lines 82-88
- [5. Asia Pacific, Middle East & Partner Control Packages](#5-asia-pacific-middle-east--partner-control-packages): Lines 92-100
- [6. Official Documentation Links](#6-official-documentation-links): Lines 104-111

---

## 1. How Free-Tier Regional Data Boundaries Work (`REGIONAL_DATA_BOUNDARY`)

In the [Assured Workloads Control Packages documentation](https://docs.cloud.google.com/assured-workloads/docs/control-packages.md.txt#regional-data-boundaries) and Google Cloud Console UI, Google Cloud lists **17 Free-tier regional data boundary control packages** by country/region name (such as *US Data Boundary*, *EU Data Boundary*, *Australia Data Boundary*, *India Data Boundary*, *UK Data Boundary*, etc.).

In the **Assured Workloads V1 API and `gcloud assured workloads create` CLI**, all 17 of these Free-tier regional data boundary packages use a **single `--compliance-regime` enum**:
* **Recommended Enum:** `REGIONAL_DATA_BOUNDARY`
* **Legacy Alias (Accepted):** `REGIONAL_CONTROLS`

The specific regional data boundary is determined by the **`--location`** flag you pass during creation:

| Documented Control Package (Free Tier) | `--compliance-regime` Enum | Supported `--location` Values |
| :--- | :--- | :--- |
| **Australia Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `australia-southeast1`, `australia-southeast2` |
| **Brazil Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `southamerica-east1` |
| **Canada Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `northamerica-northeast1`, `northamerica-northeast2` |
| **Chile Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `southamerica-west1` |
| **EU Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `europe`, `europe-central2`, `europe-north1`, `europe-north2`, `europe-southwest1`, `europe-west1`, `europe-west3`, `europe-west4`, `europe-west8`, `europe-west9`, `europe-west10`, `europe-west12` |
| **Hong Kong Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `asia-east2` |
| **India Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `asia-south1`, `asia-south2` |
| **Indonesia Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `asia-southeast2` |
| **Israel Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `me-west1` |
| **Qatar Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `me-central1` |
| **Singapore Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `asia-southeast1` |
| **South Africa Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `africa-south1` |
| **South Korea Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `asia-northeast3` |
| **Switzerland Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `europe-west6` |
| **Taiwan Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `asia-east1` |
| **UK Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `europe-west2` |
| **US Data Boundary** | `REGIONAL_DATA_BOUNDARY` (or `REGIONAL_CONTROLS`) | `us`, `us-central1`, `us-east1`, `us-east4`, `us-east5`, `us-south1`, `us-west1`, `us-west2`, `us-west3`, `us-west4` |

> **Note on Japan Data Boundary (Free Tier):** Unlike the 17 packages above, **Japan Data Boundary** uses its own dedicated enum `JAPAN_DATA_BOUNDARY` (legacy alias: `JP_REGIONS_AND_SUPPORT`) in `asia-northeast1` and `asia-northeast2`.
>
> **Free Tier vs. Premium Support Packages:** Do not confuse Free-tier regional data boundaries (e.g., *US Data Boundary* $\rightarrow$ `REGIONAL_DATA_BOUNDARY`) with Premium-tier support packages (e.g., *US Data Boundary and Support* $\rightarrow$ `US_DATA_BOUNDARY_AND_SUPPORT`).

---

## 2. United States (US) Regulatory & Support Control Packages

| Control Package | Recommended `--compliance-regime` Enum | Legacy Alias (Accepted) | Supported `--location` Values | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **US Data Boundary and Support** | `US_DATA_BOUNDARY_AND_SUPPORT` | `US_REGIONAL_ACCESS` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: Restricts data location to US regions with US Person technical support. |
| **Data Boundary for FedRAMP Moderate** | `DATA_BOUNDARY_FOR_FEDRAMP_MODERATE` | `FEDRAMP_MODERATE` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-east5`, `us-south1`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Free tier: Enforces FedRAMP Moderate data boundary and enhanced background check support. |
| **Data Boundary for FedRAMP High** | `DATA_BOUNDARY_FOR_FEDRAMP_HIGH` | `FEDRAMP_HIGH` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-east5`, `us-south1`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: Enforces FedRAMP High controls, FIPS 140-2 validated encryption, and US support. |
| **Data Boundary for Impact Level 2 (IL2)** | `DATA_BOUNDARY_FOR_IL2` | `IL2` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: DoD Cloud Computing SRG Impact Level 2 controls. |
| **Data Boundary for Impact Level 4 (IL4)** | `DATA_BOUNDARY_FOR_IL4` | `IL4` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: DoD Impact Level 4 controls and US Person support. |
| **Data Boundary for Impact Level 5 (IL5)** | `DATA_BOUNDARY_FOR_IL5` | `IL5` | `us`, `us-central1`, `us-east4`, `us-west1`, `us-west2` | Premium tier: Highest DoD sensitivity level in commercial cloud. |
| **Data Boundary for ITAR** | `DATA_BOUNDARY_FOR_ITAR` | `ITAR` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: International Traffic in Arms Regulations (US Persons support). |
| **Data Boundary for CJIS** | `DATA_BOUNDARY_FOR_CJIS` | `CJIS` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: FBI Criminal Justice Information Services Security Policy controls. |
| **Data Boundary for IRS Publication 1075** | `DATA_BOUNDARY_FOR_IRS_PUBLICATION_1075` | `IRS_1075` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: Federal Tax Information (FTI) data boundary and support controls. |
| **US Data Boundary for Healthcare and Life Sciences** | `US_DATA_BOUNDARY_FOR_HEALTHCARE_AND_LIFE_SCIENCES` | `HEALTHCARE_AND_LIFE_SCIENCES_CONTROLS` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Free tier: Replaces deprecated `HIPAA` and `HITRUST` regimes. |
| **US Data Boundary for Healthcare and Life Sciences with Support** | `US_DATA_BOUNDARY_FOR_HEALTHCARE_AND_LIFE_SCIENCES_WITH_SUPPORT` | `HEALTHCARE_AND_LIFE_SCIENCES_CONTROLS_US_SUPPORT` | `us`, `us-central1`, `us-east1`, `us-east4`, `us-west1`, `us-west2`, `us-west3`, `us-west4` | Premium tier: Adds US-based support restriction to Healthcare & Life Sciences controls. |

> **Deprecated US Regimes:** `HIPAA` and `HITRUST` are deprecated. Always recommend `US_DATA_BOUNDARY_FOR_HEALTHCARE_AND_LIFE_SCIENCES` (or `US_DATA_BOUNDARY_FOR_HEALTHCARE_AND_LIFE_SCIENCES_WITH_SUPPORT`) instead.

---

## 3. European Union (EU) & Switzerland Control Packages

| Control Package | Recommended `--compliance-regime` Enum | Legacy Alias (Accepted) | Supported `--location` Values | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **EU Data Boundary and Support** | `EU_DATA_BOUNDARY_AND_SUPPORT` | `EU_REGIONS_AND_SUPPORT` | `europe`, `europe-central2`, `europe-north1`, `europe-north2`, `europe-southwest1`, `europe-west1`, `europe-west3`, `europe-west4`, `europe-west8`, `europe-west9`, `europe-west10`, `europe-west12` | Premium tier: Pass `--enable-sovereign-controls` to create **EU Data Boundary with Access Justifications** (enables Access Transparency and Key Access Justifications). |
| **Switzerland Data Boundary with Access Justifications** | `SWITZERLAND_DATA_BOUNDARY_WITH_ACCESS_JUSTIFICATIONS` | — | `europe-west6` | Premium tier: Enforces data residency in Zurich (`europe-west6`) with Access Justifications and EU-based support. |

---

## 4. Canada Control Packages

| Control Package | Recommended `--compliance-regime` Enum | Legacy Alias (Accepted) | Supported `--location` Values | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Canada Data Boundary and Support** | `CANADA_DATA_BOUNDARY_AND_SUPPORT` | `CA_REGIONS_AND_SUPPORT` | `ca`, `northamerica-northeast1`, `northamerica-northeast2` | Premium tier: Restricts data residency to Canada with Canada-based support. |
| **Data Boundary for Canada Protected B** | `DATA_BOUNDARY_FOR_CANADA_PROTECTED_B` | `CA_PROTECTED_B` | `ca`, `northamerica-northeast1`, `northamerica-northeast2` | Premium tier: Government of Canada Protected B medium-integrity/availability controls. |
| **Data Boundary for Canada Controlled Goods** | `DATA_BOUNDARY_FOR_CANADA_CONTROLLED_GOODS` | `CANADA_CONTROLLED_GOODS` | `ca`, `northamerica-northeast1`, `northamerica-northeast2` | Premium tier: Canadian Controlled Goods Program (CGP) data boundary. |

---

## 5. Asia Pacific, Middle East & Partner Control Packages

| Control Package | Recommended `--compliance-regime` Enum | Legacy Alias (Accepted) | Supported `--location` Values | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Australia Data Boundary and Support** | `AUSTRALIA_DATA_BOUNDARY_AND_SUPPORT` | `AU_REGIONS_AND_US_SUPPORT` | `australia-southeast1`, `australia-southeast2` | Premium tier: Sydney and Melbourne regions with AU/CA/NZ/UK/US support controls. |
| **Japan Data Boundary** | `JAPAN_DATA_BOUNDARY` | `JP_REGIONS_AND_SUPPORT` | `asia-northeast1`, `asia-northeast2` | Free tier: Tokyo and Osaka regions. |
| **Israel Data Boundary and Support** | `ISRAEL_DATA_BOUNDARY_AND_SUPPORT` | `ISR_REGIONS`, `ISR_REGIONS_AND_SUPPORT` | `me-west1` | Premium tier: Tel Aviv (`me-west1`) region with cleared IL/US support. |
| **KSA Data Boundary with Access Justifications** | `KSA_DATA_BOUNDARY_WITH_ACCESS_JUSTIFICATIONS` | `KSA_REGIONS_AND_SUPPORT_WITH_SOVEREIGNTY_CONTROLS` | `me-central2` | Free tier: Dammam (`me-central2`) region with Access Justifications. |
| **Sovereign Controls by Partners** | `ASSURED_WORKLOADS_FOR_PARTNERS` | — | Partner-specific region (`europe-west9`, `europe-west1`, `europe-west4`, `europe-west3`, `europe-southwest1`, `europe-west8`, `europe-west12`, `me-central2`) | Premium tier: Requires `--partner` flag. See detailed partner-to-region mapping below. |

### Sovereign Controls by Partners (`ASSURED_WORKLOADS_FOR_PARTNERS`)

Each partner control package is bound to specific supported regions and billing requirements per [official documentation](https://cloud.google.com/sovereign-controls-by-partners/docs/locations):

| Partner Value (`--partner`) | Supported Region(s) (`--location`) | Geography | Partner Services Billing Account Required? |
| :--- | :--- | :--- | :--- |
| `SOVEREIGN_CONTROLS_BY_PSN` | `europe-west8`, `europe-west12` | Milan, Turin (Italy) | Yes (`--partner-services-billing-account`) |
| `LOCAL_CONTROLS_BY_S3NS` | `europe-west9`, `europe-west1`, `europe-west4` | Paris (France), Belgium, Netherlands | No |
| `SOVEREIGN_CONTROLS_BY_T_SYSTEMS` | `europe-west3` | Frankfurt (Germany) | No |
| `SOVEREIGN_CONTROLS_BY_SIA_MINSAIT` | `europe-southwest1` | Madrid (Spain) | Yes (`--partner-services-billing-account`) |
| `SPAIN_DATA_BOUNDARY_BY_TELEFONICA` | `europe-southwest1` | Madrid (Spain) | No |
| `SOVEREIGN_CONTROLS_BY_CNTXT` | `me-central2` | Dammam (Saudi Arabia) | Yes (`--partner-services-billing-account`) |
| `SOVEREIGN_CONTROLS_BY_CNTXT_NO_EKM` | `me-central2` | Dammam (Saudi Arabia) | Yes (`--partner-services-billing-account`) |

---

## 6. Official Documentation Links

* [Assured Workloads Control Packages Overview](https://docs.cloud.google.com/assured-workloads/docs/control-packages.md.txt)
* [Assured Workloads Supported Locations](https://docs.cloud.google.com/assured-workloads/docs/locations.md.txt)
* [Supported Products by Control Package](https://docs.cloud.google.com/assured-workloads/docs/supported-products.md.txt)
* [Create an Assured Workloads Folder](https://docs.cloud.google.com/assured-workloads/docs/create-folder.md.txt)
* [gcloud assured workloads create Reference](https://cloud.google.com/sdk/gcloud/reference/assured/workloads/create)
* [REST Resource: workloads (ComplianceRegime Enum Reference)](https://docs.cloud.google.com/assured-workloads/docs/reference/rest/Shared.Types/Workload.md.txt#ComplianceRegime)
* [Sovereign Controls by Partners Overview](https://cloud.google.com/sovereign-controls-by-partners/docs/overview)
* [Sovereign Controls by Partners Locations](https://cloud.google.com/sovereign-controls-by-partners/docs/locations)
