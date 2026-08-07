<!-- Use this template to compile the solution validation that you generate
based on the instructions in `SKILL.md`. -->

## 1. Validation Plan & Verification Report

This validation plan outlines the dry-run, connectivity, routing, and security
checks to verify that the deployed infrastructure meets all functional and
non-functional requirements.

### 1.1. Infrastructure Dry-Run

Verify the deployment plan using preview tools before applying changes.

*   **Command**:
    ```bash
    terraform plan -out=tfplan
    ```
*   **Expected Outcome**: Preview validates resource hierarchy and shows
    exactly what resources will be created, updated, or destroyed without
    configuration errors.

### 1.2. Network Connectivity & Routing

[Draft workloads-specific connectivity checks. E.g., test load balancer
endpoints, serverless VPC path latency, private database access, or DNS
resolution rules.]

*   **Command**:
    ```bash
    curl -iv -H "Host: [Target Domain]" https://[LB-IP-Address]/healthz
    ```
*   **Expected Outcome**: Returns `HTTP 200 OK` from the correct regional
    serverless endpoint.

### 1.3. Security and Access Governance

Verify IAM role mappings, service account isolation, and network perimeter
rules.

*   **Command**:
    ```bash
    gcloud projects get-iam-policy [GCP-Project-ID] \
        --flatten="bindings[].members" \
        --format='table(bindings.role, bindings.members)' \
        --filter="bindings.members:[Service-Account-Email]"
    ```
*   **Expected Outcome**: Confirms that only the specified roles are granted,
    enforcing the principle of least privilege.

### 1.4. Data Protection & Content Inspection

Audit content filtering, input sanitization/redaction rules, and safety/PII
guardrails.

*   **Command**:
    ```bash
    # Test request with mock PII to audit redaction filters
    curl -X POST -H "Content-Type: application/json" \
         -d '{"prompt": "[Mock Sensitive Data Code/PII Pattern]"}' \
         https://[Target Domain]/chat
    ```
*   **Expected Outcome**: Request is either anonymized/masked by the security
    layer (e.g., Model Armor) or blocked with a safety intercept notice.
