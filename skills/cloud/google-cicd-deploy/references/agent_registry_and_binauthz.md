# Agent Registry Registration, SBOM Export, and Binary Authorization

## Table of Contents

-   [1. Rule 7: Automatic Agent Registry Registration](#1-rule-7-automatic-agent-registry-registration)
    (Lines 12-77)
-   [2. Rule 8: SBOM Generation and Binary Authorization](#2-rule-8-sbom-generation-and-binary-authorization)
    (Lines 81-187)

--------------------------------------------------------------------------------

## 1. Rule 7: Automatic Agent Registry Registration

Whenever the application being deployed is an **AI Agent** (e.g., uses
`google-adk`, `@google/adk`, `genkit`, `langchain`, `langgraph`, `crewai`,
`autogen`, `a2a-sdk`, `agent.py`, `AGENTS.md`, `manifest.yaml`,
`[tool.agent-starter-pack]`, or `agent_card.json`) or an **MCP Server** (e.g.,
uses `mcp`, `@modelcontextprotocol/sdk`, `fastmcp`, or `mcp-spec.json`), you
**MUST** use native runtime auto-registration so that **Google Cloud Agent
Registry** discovers the workload with its actual compute runtime
(`//run.googleapis.com/...` for Cloud Run or `//container.googleapis.com/...`
for GKE) rather than a manual `//agentregistry.googleapis.com/.../services/...`
entry:

*   **Cloud Run Native Auto-Registration (`--functional-type` +
    `--identity-type`)**:
    *   Deploy (or update an existing service that was deployed without
        functional-type) using `gcloud beta run deploy` (or
        `gcloud beta run services update`) with
        `--functional-type=agent --identity-type=agent-identity` (or
        `--functional-type=mcp-server` for MCP Servers), setting `<AUTH_FLAG>`
        to `--allow-unauthenticated` when `public_access` is `true` or
        confirmed by the user and `--no-allow-unauthenticated` when private or
        `prod`:

        ```bash
        gcloud beta run deploy "<SERVICE_NAME>" \
          --image="<IMAGE_URI>" \
          --region="<REGION>" \
          --project="<PROJECT_ID>" \
          --port="<PORT>" \
          --functional-type=agent \
          --identity-type=agent-identity \
          <AUTH_FLAG> \
          --quiet
        ```

        *(This registers the service directly from the Cloud Run control plane
        with `agentId: urn:agent:...:run:services:<SERVICE_NAME>` and
        `RuntimeReference.uri:
        //run.googleapis.com/projects/<PROJECT_NUMBER>/locations/<REGION>/services/<SERVICE_NAME>`.
        Do **NOT** run `gcloud agent-registry services create` for Cloud Run
        workloads unless native `--functional-type` is unsupported, as manual
        `services create` sets the runtime reference to `agentregistry` instead
        of `run.googleapis.com`.)*

*   **GKE Native Auto-Registration**:
    *   In Kubernetes `Deployment` manifests for AI Agents or MCP Servers,
        automatically add:
        *   `metadata.labels["registry.gke.io/functional-type"]: "AGENT"` (or
            `"MCP_SERVER"`)
        *   `metadata.annotations["apphub.cloud.google.com/functional-type"]:
            "AGENT"` (or `"MCP_SERVER"`)
        *   `spec.template.metadata.annotations["iam.gke.io/spiffe-identity-type"]:
            "agent-identity"`

*   **Verification**:
    *   Verify that the agent appears in Agent Registry with its Cloud Run / GKE
        runtime by running:

        ```bash
        gcloud agent-registry agents list --location="<REGION>" --project="<PROJECT_ID>" --filter="agentId:<SERVICE_NAME>" --format="table(name.basename(),displayName,agentId,attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri)" --quiet
        ```

    *   Include the registered Agent Registry resource name, `agentId` URN, and
        `RuntimeReference.uri` in the final deployment summary shown to the
        user.

--------------------------------------------------------------------------------

## 2. Rule 8: SBOM Generation and Binary Authorization

*   **SBOM Generation (Do Not Block Build/Dev Deploy)**: After building and
    pushing a container image to Artifact Registry via Cloud Build or Docker,
    generate the SPDX 2.3 SBOM (`artifactanalysis-2-3.spdx.json`) using
    `gcloud artifacts sbom export`. Deploy `dev` Cloud Run services **without**
    `--binary-authorization` so `dev` deployments are never blocked:

    ```bash
    DIGEST_URI=$(gcloud artifacts docker images describe "<IMAGE_URI>" \
      --project="<PROJECT_ID>" \
      --format="value(image_summary.fully_qualified_digest)" \
      --quiet)

    # Wait briefly if the automatic push DISCOVERY occurrence is still initializing, then export SBOM
    for i in 1 2 3 4 5; do
      gcloud artifacts sbom export --uri="${DIGEST_URI}" --project="<PROJECT_ID>" --quiet && break
      sleep 3
    done
    ```

*   **Cloud Run `prod` Promotion Gate (Binary Authorization + Provenance &
    Severe Vulnerability Check)**:
    *   When deploying or promoting an image to the **Cloud Run `prod`
        instance** (where `binary_authorization` is `"default"` in
        `deployment-config.json`), always pass `--binary-authorization=default`
        on `gcloud run deploy` / `gcloud beta run deploy`.
    *   Before deploying to `prod`, evaluate the image digest against the Binary
        Authorization policy (`prod-policy`, which checks for **Google Cloud
        Build SLSA provenance** and **no `HIGH` or `CRITICAL`
        vulnerabilities**):

        ```bash
        EVAL_OUTPUT=$(gcloud beta container binauthz policy evaluate "${BINARY_AUTHZ_POLICY:-prod-policy}" \
          --platform=cloudRun \
          --project="<PROJECT_ID>" \
          --image="${DIGEST_URI}" \
          --format=yaml \
          --quiet)
        echo "$EVAL_OUTPUT"
        ```

    *   **If `verdict: CONFORMANT`**: Sign and attach the `prod-attestor`
        attestation so Cloud Run's `--binary-authorization=default` admits the
        `prod` deployment:

        ```bash
        gcloud beta container binauthz attestations sign-and-create \
          --artifact-url="https://${DIGEST_URI}" \
          --attestor="projects/<PROJECT_ID>/attestors/prod-attestor" \
          --keyversion-project="<PROJECT_ID>" \
          --keyversion-location="<REGION>" \
          --keyversion-keyring="binauthz-keyring" \
          --keyversion-key="prod-attestor-key" \
          --keyversion="1" \
          --project="<PROJECT_ID>" \
          --quiet
        ```

    *   **If `verdict: NON_CONFORMANT`**: Do **NOT** sign the `prod-attestor`
        attestation, so that deploying with `--binary-authorization=default` is
        blocked by Binary Authorization.

*   **Interpreting Binary Authorization (`BinAuthz`) Failures on
    Promotion/Deployment to Production**:
    *   Whenever a `prod` deployment or promotion fails due to Binary
        Authorization (`verdict: NON_CONFORMANT`, Cloud Run
        `BinaryAuthorizationCheckFailed` / revision not ready, or Cloud Deploy
        rollout failure), you **MUST** automatically inspect and interpret the
        Binary Authorization results to explain the exact cause of the block:
        1.  **Inspect Policy Evaluation & BinAuthz Audit Logs**:

            ```bash
            # Evaluate the provenance & vulnerability checkset against the image digest
            gcloud beta container binauthz policy evaluate "${BINARY_AUTHZ_POLICY:-prod-policy}" \
              --platform="${PLATFORM:-cloudRun}" --project="<PROJECT_ID>" --image="${DIGEST_URI}" --format=yaml --quiet

            # Check Cloud Audit Logs for the BinAuthz admission denial message
            gcloud logging read 'logName:"cloudaudit.googleapis.com%2Fpolicy" OR protoPayload.serviceName="binaryauthorization.googleapis.com" OR protoPayload.status.message:"Binary Authorization"' \
              --project="<PROJECT_ID>" --limit=10 --format=json --quiet
            ```

        2.  **Cross-Check Attestations, Provenance, and Vulnerability Findings
            on the Image Digest**:

            ```bash
            # Check existing BinAuthz attestations on the image digest
            gcloud container binauthz attestations list --artifact-url="https://${DIGEST_URI}" --project="<PROJECT_ID>" --quiet

            # Check SLSA build provenance and package vulnerability scan results
            gcloud artifacts docker images describe "${DIGEST_URI}" \
              --show-provenance --show-package-vulnerability \
              --project="<PROJECT_ID>" --quiet
            ```

        3.  **Explain the Root Cause Clearly to the User**:
            *   Identify **which check failed**:
                *   `SlsaCheck` (`Require Google Cloud Build SLSA Provenance`):
                    Explain whether the image is missing verified Cloud Build
                    provenance (`provenance_summary: null` or built outside
                    Cloud Build).
                *   `VulnerabilityCheck` (`Block HIGH and CRITICAL
                    Vulnerabilities`): State how many vulnerabilities violated
                    the `MEDIUM` threshold (`HIGH` / `CRITICAL` CVEs) and list
                    the offending CVEs (`package`, `installedVersion`,
                    `fixedVersion`, `severity`, `cvssScore`) along with
                    remediation steps.
