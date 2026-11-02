# OWASP Core Rule Set (CRS) Mappings and Signatures Reference

<!-- disableFinding(LINE_OVER_80) -->

This reference provides the authoritative mapping between legacy OWASP
ModSecurity Core Rule Set (CRS) 3.0 / 3.3 rulesets and OWASP CRS 4.22 in Google
Cloud Armor.

## Table of Contents

-   [1. Ruleset Name Mappings](#1-ruleset-name-mappings): Lines 19-69
-   [2. Signature Counts and Sensitivity Expansion (Sensitivity 4)](#2-signature-counts-and-sensitivity-expansion-sensitivity-4): Lines 72-103
-   [3. Deprecated Signature IDs in CRS 4.22](#3-deprecated-signature-ids-in-crs-422): Lines 107-127
-   [4. Signature ID Format Remapping](#4-signature-id-format-remapping): Lines 131-144
-   [5. Special and Standalone Preconfigured Rulesets](#5-special-and-standalone-preconfigured-rulesets): Lines 148-183

--------------------------------------------------------------------------------

## 1. Ruleset Name Mappings

Google Cloud Armor rulesets are identified by name in CEL expressions (for
example, `evaluatePreconfiguredWaf('ruleset-name')`).

### CRS 3.0 to CRS 4.22

<!-- mdformat off -->

| Threat Category       | CRS 3.0 Stable             | CRS 4.22 Stable                 | CRS 3.0 Canary             | CRS 4.22 Canary                 |
| :-------------------- | :------------------------- | :------------------------------ | :------------------------- | :------------------------------ |
| SQL Injection         | `sqli-stable`              | `sqli-v422-stable`              | `sqli-canary`              | `sqli-v422-canary`              |
| Cross-Site Scripting  | `xss-stable`               | `xss-v422-stable`               | `xss-canary`               | `xss-v422-canary`               |
| Local File Inclusion  | `lfi-stable`               | `lfi-v422-stable`               | `lfi-canary`               | `lfi-v422-canary`               |
| Remote File Inclusion | `rfi-stable`               | `rfi-v422-stable`               | `rfi-canary`               | `rfi-v422-canary`               |
| Remote Code Execution | `rce-stable`               | `rce-v422-stable`               | `rce-canary`               | `rce-v422-canary`               |
| Method Enforcement    | `methodenforcement-stable` | `methodenforcement-v422-stable` | `methodenforcement-canary` | `methodenforcement-v422-canary` |
| Scanner Detection     | `scannerdetection-stable`  | `scannerdetection-v422-stable`  | `scannerdetection-canary`  | `scannerdetection-v422-canary`  |
| Protocol Attack       | `protocolattack-stable`    | `protocolattack-v422-stable`    | `protocolattack-canary`    | `protocolattack-v422-canary`    |
| PHP Attack            | `php-stable`               | `php-v422-stable`               | `php-canary`               | `php-v422-canary`               |
| Session Fixation      | `sessionfixation-stable`   | `sessionfixation-v422-stable`   | `sessionfixation-canary`   | `sessionfixation-v422-canary`   |

<!-- mdformat on -->

### CRS 3.3 to CRS 4.22

<!-- mdformat off -->

| Threat Category       | CRS 3.3 Stable                 | CRS 4.22 Stable                 | CRS 3.3 Canary                 | CRS 4.22 Canary                 |
| :-------------------- | :----------------------------- | :------------------------------ | :----------------------------- | :------------------------------ |
| SQL Injection         | `sqli-v33-stable`              | `sqli-v422-stable`              | `sqli-v33-canary`              | `sqli-v422-canary`              |
| Cross-Site Scripting  | `xss-v33-stable`               | `xss-v422-stable`               | `xss-v33-canary`               | `xss-v422-canary`               |
| Local File Inclusion  | `lfi-v33-stable`               | `lfi-v422-stable`               | `lfi-v33-canary`               | `lfi-v422-canary`               |
| Remote File Inclusion | `rfi-v33-stable`               | `rfi-v422-stable`               | `rfi-v33-canary`               | `rfi-v422-canary`               |
| Remote Code Execution | `rce-v33-stable`               | `rce-v422-stable`               | `rce-v33-canary`               | `rce-v422-canary`               |
| Method Enforcement    | `methodenforcement-v33-stable` | `methodenforcement-v422-stable` | `methodenforcement-v33-canary` | `methodenforcement-v422-canary` |
| Scanner Detection     | `scannerdetection-v33-stable`  | `scannerdetection-v422-stable`  | `scannerdetection-v33-canary`  | `scannerdetection-v422-canary`  |
| Protocol Attack       | `protocolattack-v33-stable`    | `protocolattack-v422-stable`    | `protocolattack-v33-canary`    | `protocolattack-v422-canary`    |
| PHP Attack            | `php-v33-stable`               | `php-v422-stable`               | `php-v33-canary`               | `php-v422-canary`               |
| Session Fixation      | `sessionfixation-v33-stable`   | `sessionfixation-v422-stable`   | `sessionfixation-canary`       | `sessionfixation-v422-canary`   |
| Java Attack           | `java-v33-stable`              | `java-v422-stable`              | `java-v33-canary`              | `java-v422-canary`              |
| Node.js / Generic     | `nodejs-v33-stable`            | `generic-v422-stable`           | `nodejs-v33-canary`            | `generic-v422-canary`           |

<!-- mdformat on -->

> **Note on Node.js**: In CRS 4.22, the Node.js attack ruleset was merged into
> and replaced by `generic-v422-stable` / `generic-v422-canary`. Consequently,
> any signature IDs ending in `-nodejs` (for example,
> `owasp-crs-v030301-id934100-nodejs`) are remapped with the `-generic` suffix
> (`owasp-crs-v042200-id934100-generic`) to match the target expression set.

--------------------------------------------------------------------------------

## 2. Signature Counts and Sensitivity Expansion (Sensitivity 4)

When `evaluatePreconfiguredWaf('ruleset-name')` is called without an explicit
`sensitivity` parameter, Cloud Armor defaults to **sensitivity level 4**
(evaluating all paranoia levels 1 through 4).

Upgrading to CRS 4.22 expands signature coverage significantly:

<!-- mdformat off -->

| Threat Category                 | CRS 3.0 Signatures | CRS 3.3 Signatures | CRS 4.22 Signatures | Coverage Delta                         |
| :------------------------------ | :----------------- | :----------------- | :------------------ | :------------------------------------- |
| **Remote Code Execution (RCE)** | 11                 | 15                 | **44**              | +29 to +33 signatures (+200-300%)      |
| **SQL Injection (SQLi)**        | 38                 | 49                 | **60**              | +11 to +22 signatures (+22-58%)        |
| **Cross-Site Scripting (XSS)**  | 25                 | 30                 | **33**              | +3 to +8 signatures (+10-32%)          |
| **PHP Injection**               | 13                 | 16                 | **20**              | +4 to +7 signatures (+25-54%)          |
| **Protocol Attack**             | 9                  | 10                 | **17**              | +7 to +8 signatures (+70-89%)          |
| **Java Attack**                 | N/A                | 9                  | **14**              | +5 signatures (+55%)                   |
| **Generic / Node.js**           | N/A                | 1                  | **10**              | +9 signatures (+900%)                  |
| **Local File Inclusion (LFI)**  | 4                  | 4                  | **5**               | +1 signature                           |
| **Remote File Inclusion (RFI)** | 4                  | 4                  | **5**               | +1 signature                           |
| **Session Fixation**            | 3                  | 3                  | **3**               | No change                              |
| **Method Enforcement**          | 1                  | 1                  | **1**               | Behavior change (PUT/PATCH/DELETE)     |
| **Scanner Detection**           | 5                  | 5                  | **1**               | Consolidated                           |

<!-- mdformat on -->

**Why this matters**: The massive increase in active signatures (especially in
RCE, SQLi, and Protocol Attack) increases protection against modern CVEs, but
also increases the possibility of triggering false positives on idiosyncratic
application payloads. This is why **Preview Mode** is strongly recommended for
transition.

--------------------------------------------------------------------------------

## 3. Deprecated Signature IDs in CRS 4.22

The following 15 CRS 3.0 / 3.3 signature IDs were retired or removed in CRS
4.22:

-   **Anomaly / Correlation Markers**:
    -   `981172`: Legacy anomaly score / correlation check
    -   `981173`: Legacy anomaly threshold trigger
    -   `980130`: Inbound anomaly marker
    -   `949110`: Inbound anomaly evaluation blocking marker
-   **SQL Injection (`sqli`)**: `942110`
-   **Remote Code Execution (`rce`)**: `932100`, `932105`, `932106`, `932110`,
    `932115`, `932150`
-   **Scanner Detection (`scannerdetection`)**: `913101`, `913102`, `913110`,
    `913120`

**Critical Requirement**: If a customer's legacy rule opted out of any of these
15 IDs (for example, `['owasp-crs-v030001-id981172-sqli']`), the ID **MUST be
omitted** from the CRS 4.22 opt-out list and `preconfiguredWafConfig`
`targetRuleIds`. Including a non-existent signature ID in CRS 4.22 will cause
Cloud Armor API or Terraform validation errors.

--------------------------------------------------------------------------------

## 4. Signature ID Format Remapping

CRS signature IDs follow a versioned prefix format:

-   **CRS 3.0**: `owasp-crs-v030001-idSIGNATURE_ID-GROUP` (or `v030000`)
-   **CRS 3.3**: `owasp-crs-v030301-idSIGNATURE_ID-GROUP`
-   **CRS 4.22**: `owasp-crs-v042200-idSIGNATURE_ID-GROUP`

**Examples**:

-   Standard: `owasp-crs-v030001-id942120-sqli` to
    `owasp-crs-v042200-id942120-sqli`
-   Node.js Suffix Remapping: `owasp-crs-v030301-id934100-nodejs` to
    `owasp-crs-v042200-id934100-generic`

--------------------------------------------------------------------------------

## 5. Special and Standalone Preconfigured Rulesets

Certain Google Cloud Armor preconfigured rules are out-of-band and do **not**
follow the standard OWASP CRS 3.0 / 3.3 to 4.22 versioning progression:

### A. CVE Canary (`cve-canary`)

The `cve-canary` preconfigured rule provides early detection and mitigation for
specific high-profile CVEs (for example, Log4j CVE-2021-44228 / CVE-2021-45046,
React RCE CVE-2025-55182, and Google Managed Rules).

-   **Ruleset Identifier**: Stays `cve-canary` (no version suffix).
-   **Supported Signatures (Log4j)**:
    -   `owasp-crs-v030001-id044228-cve` (Sensitivity 1 - Base Log4j detection)
    -   `owasp-crs-v030001-id144228-cve` (Sensitivity 1 - Obfuscation enhancements)
    -   `owasp-crs-v030001-id244228-cve` (Sensitivity 3 - Aggressive bypass detection)
    -   `owasp-crs-v030001-id344228-cve` (Sensitivity 3 - Base64 bypass detection)
-   **Google Managed Rules**: `google-mrs-vDATE-idSIGNATURE_ID-GROUP` (for
    example, `google-mrs-v202512-id000001-rce`).
-   **Upgrade Requirement**: Upgrade the evaluation syntax from
    `evaluatePreconfiguredExpr` to native `evaluatePreconfiguredWaf`.
    **Signature IDs retain their original syntax (`owasp-crs-v030001-id*-cve` or
    `google-mrs-*`)** and must **not** be remapped to `v042200` or dropped as
    dangling.

### B. JSON SQL Injection (`owasp-crs-id942550-sqli`)

The JSON-formatted content SQLi vulnerability rule (`942550`) does not carry a
version prefix (`owasp-crs-id942550-sqli`). It is preserved as-is.

### C. Preconfigured IP Lists (`sourceiplist-*`)

Expressions such as `evaluatePreconfiguredExpr('sourceiplist-cloudflare')`
reference Cloud Armor named IP lists rather than WAF threat categories. They
remain functional under `evaluatePreconfiguredWaf('sourceiplist-cloudflare')` or
`evaluatePreconfiguredExpr`.
