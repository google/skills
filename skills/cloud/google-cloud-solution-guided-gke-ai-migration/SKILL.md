---
name: google-cloud-solution-guided-gke-ai-migration
metadata:
  category: MultiProductSolutions
description: >-
    Guides the migration of existing AI workloads (Cloud Run, Gemini API, Gemini Enterprise Agent Platform) to self-hosted GKE inference using gcloud and kubectl. Use when the user has an existing AI inference workload (on Cloud Run, the Gemini API, Gemini Enterprise Agent Platform, or a custom VM) and wants to move it to self-hosted inference on GKE, or asks follow-up questions during such a migration (hardware sizing, model staging, manifest generation, validation, traffic cutover). DO NOT use for brand new GKE inference deployments with no existing workload to migrate (use gke-inference instead). DO NOT use if the user intends to automate the migration via the Gemini Cloud Assist MCP server.
---

# Migrate AI Workloads to GKE Inference

This skill guides agents through the end-to-end process of migrating existing AI inference workloads (e.g., from Cloud Run, Gemini API, Gemini Enterprise Agent Platform) to self-hosted inference on Google Kubernetes Engine (GKE). The agent will act as an interactive architect, using a structured 4-phase workflow to discover requirements, design a Google Cloud-native solution, execute the implementation using `gcloud` and `kubectl`, and validate the deployment.

## Gemini Cloud Assist MCP off-ramp

This skill covers manual, architect-guided migration only. Automated migration is the job of the Gemini Cloud Assist MCP server. Route between them as follows:

- **The user asks to USE Gemini Cloud Assist or MCP automation for this migration** (e.g., "use the Cloud Assist MCP server to do this"): stop the manual workflow and respond with the 4 required points below.
- **The user mentions MCP only in passing, or explicitly declines it** (e.g., "no MCP, let's do this manually"): proceed with the manual workflow. Do not stop and do not ask about MCP.
- **The user does not mention MCP at all:** proceed directly to the active phase. In your first discovery response only, add one sentence noting that an automated alternative exists via the Gemini Cloud Assist MCP server and the user can switch to it at any time. Do not wait for an answer before beginning discovery.

**When stopping for an MCP request, your response MUST include these 4 points:**

1. **STOP the manual workflow & clarify scope:** State that `google-cloud-solution-guided-gke-ai-migration` is strictly intended for manual, architect-guided migration using native CLIs (`gcloud` and `kubectl`), and that this manual skill workflow is being stopped.
2. **Explain MCP capabilities:** Explain that the Gemini Cloud Assist MCP server assists in automated infrastructure analysis (`gemini_cloud_assist:ask_cloud_assist`) or direct Google Cloud resource mutation (`gemini_cloud_assist:invoke_operation`).
3. **Link to MCP Documentation:** Provide a valid hyperlink to the [Gemini Cloud Assist MCP Documentation](https://docs.cloud.google.com/cloud-assist/configure-mcp).
4. **Link to Intent to Infrastructure Codelab:** Provide a valid hyperlink to the [Intent to Infrastructure Codelab](https://github.com/GoogleCloudPlatform/next-26-keynotes/tree/main/devkey/intent-to-infrastructure) for guidance on setting up the MCP server.

## Scope Check: New Deployments vs. Migrations

**This skill is specifically intended for migrating existing AI workloads (from Cloud Run, Gemini API, Agent Platform, or other platforms) to GKE.**

If the user wants to deploy a new AI model server from scratch on GKE (and does NOT have an existing deployment to migrate), **STOP** and recommend using the **`gke-inference`** skill instead. Explain that `google-cloud-solution-guided-gke-ai-migration` focuses on migration workflows (discovering existing Cloud Run/Agent Platform configurations, traffic cutover, etc.), while `gke-inference` is optimized for fresh GKE AI model server deployments using AI Profiles and golden path manifests.

## Core Architectural Principles (The "Golden Path")
When designing the solution, always default to the latest GKE AI best practices:

- **Execution:**
  - **Execution policy (who runs commands):**
    - **Phase 1 (Discovery):** after the user grants permission, execute read-only `gcloud` inspection commands (`list`, `describe`) directly and summarize the results.
    - **Phases 2-4:** write manifests to disk, then present the exact `gcloud` and `kubectl` commands for the user to run. Do not execute mutating commands (`apply`, `create`, `delete`, cluster or IAM changes) unless the user explicitly asks you to run them, in which case execute them and report each command's actual output.
    - **Informational and troubleshooting questions:** answer with markdown guidance, manifests, and recommended commands only; execute nothing.
  - Favor raw Kubernetes manifests, native CLIs (`gcloud` for infrastructure, `kubectl` for workloads), and opinionated templates.
  - Save YAML files to the user's current directory and apply them using `kubectl`.
  - Write ad-hoc scripts (e.g., for VRAM calculation) only if absolutely necessary.
- **Node Provisioning:**
  - Utilize **Custom Compute Classes (CCC)** to maximize accelerator obtainability (e.g., dynamically choosing spot vs. on-demand or specific GPU profiles).
  - Use GKE's managed GPU driver installations.
  - Select appropriate node topologies: use a single node in a static pool for a simple job, or multiple nodes with LWS/CCC for larger jobs.
- **Inference Stack & Versioning:**
  - Default to **vLLM** (`vllm/vllm-openai`) as the standard LLM serving engine. If migrating from Vertex AI, the user may opt to retain the Vertex AI Model Garden image (e.g., `pytorch-vllm-serve`), which is permissible.
  - **Explicit Entrypoint Override:** Regardless of the chosen image, the vLLM Deployment MUST explicitly set `command: ["python", "-m", "vllm.entrypoints.openai.api_server"]` to bypass potentially problematic entrypoint scripts (like `gcs_download_launcher.sh` in Vertex AI images) that crash when passed standard vLLM arguments.
  - Always pin an explicit, stable vLLM image tag, never `:latest`. Resolve the current stable release at design time (check the vLLM releases page, or take the tag from `gcloud container ai profiles manifests create` output) and record it in `migration-state.md`; do not reuse a tag remembered from a previous migration or from documentation examples.
  - Expose the service through the GKE Gateway API. Default to a regional internal Application Load Balancer (`gatewayClassName: gke-l7-rilb`) with an HTTPRoute that sends `/v1` requests to the vLLM ClusterIP service (`{workload_name}-vllm-svc`) on port 8000, based on `assets/gke-inference-gateway.yaml.tmpl`.
  - If the user needs LLM-aware load balancing (routing on KV-cache utilization, queue depth, or LoRA adapter placement), offer the GKE Inference Gateway as an upgrade: it requires an `InferencePool` resource as the HTTPRoute backend instead of a Service, and it is only supported on the `gke-l7-rilb` and `gke-l7-regional-external-managed` GatewayClasses. Fetch [About GKE Inference Gateway](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-gke-inference-gateway.md.txt) before generating InferencePool manifests; do not improvise them from memory.
  - For multi-node models, use **LeaderWorkerSet (LWS)** with vLLM.
- **Security & Access:**
  - Always use **GKE Workload Identity** for Google Cloud API access.
  - **Gated Model Secret Security:** For gated models (e.g., Llama 3, Gemma) requiring Hugging Face tokens (`HF_TOKEN`):
    - NEVER write literal token values into Deployment or Pod specifications; reference the secret securely using `env.valueFrom.secretKeyRef` (e.g., pointing to `hf-secret`).
    - Always warn the user about the security risks of exposing sensitive API tokens in plain text prompts or manifest files.
    - NEVER write a Kubernetes `Secret` manifest to disk, and do NOT include it in templates. Instead, explicitly instruct the user to create the Secret directly via CLI *before* applying any other manifests: `kubectl create secret generic hf-secret --namespace={namespace} --from-literal=hf_api_token=<YOUR_HF_TOKEN>` with the user substituting the real value themselves.
    - If the user has already pasted a token into the conversation, treat that token as exposed: use a `<YOUR_HF_TOKEN>` placeholder in every command and manifest you produce, and advise the user to revoke and reissue the token at https://huggingface.co/settings/tokens once the migration is complete.
  - **Endpoint exposure:** Default the Gateway to the internal class (`gke-l7-rilb`). The vLLM OpenAI-compatible endpoint has no built-in authentication; if the user requires external exposure, warn them explicitly that an unauthenticated external listener is an open inference API on their GPU bill, and require an explicit decision plus a fronting control (IAP, an authenticating API gateway, or strict client allowlisting) before generating an externally-exposed Gateway manifest.
- **Model Storage & Cold Starts:**
  - Stage the chosen model in a Cloud Storage bucket to save on downloading more than once.
  - **Execute staging via a Job on the cluster**: Explain to the user that staging weights via a cluster Job avoids downloading heavy weights to their local workstation and avoids re-downloading on every container restart. Always save the staging manifest as `model-staging-job.yaml` and instruct the user to run `kubectl apply -f model-staging-job.yaml`.
  - **Staging Logic based on Source/Target:**
    - **Source is Hugging Face ( gCS FUSE or Lustre target):** Use the staging Job to download weights directly to the PVC.
    - **Source is GCS (GCS FUSE target):** The staging Job is **OPTIONAL**. If the PVC mounts the GCS bucket directly via FUSE, the weights are already accessible and no staging step is needed.
    - **Source is GCS (Lustre target):** Use the staging Job to copy weights from the source GCS bucket to the Lustre PVC (e.g., using `gcloud storage cp`).
  - Favor Cloud Storage staging via **Cloud Storage FUSE** for most workloads, or **Managed Lustre** for ultra-low latency, PiB-scale needs.
  - Every pod that mounts a Cloud Storage FUSE volume MUST carry the pod annotation `gke-gcsfuse/volumes: "true"` (this injects the FUSE sidecar) and MUST run as the Kubernetes ServiceAccount bound to a Google service account with `roles/storage.objectUser` on the model bucket via Workload Identity. A pod missing either one will fail to mount or fail to read; check both before troubleshooting anything else storage-related.
- **Observability:**
  - Default to **Google Cloud Managed Service for Prometheus** with DCGM metrics for deep GPU visibility.
- **Autoscaling:**
  - Do NOT assume the user wants Horizontal Pod Autoscaling (HPA); you MUST ask them during discovery.
  - If HPA is declined, omit all autoscaling manifests.
  - If HPA is desired, warn the user about the **LLM Autoscaling Trap**: standard CPU, Memory, and GPU Memory utilization metrics are unreliable because vLLM preallocates VRAM for KV caching, appearing highly utilized constantly.
  - Recommend scaling based on custom server metrics reflecting actual concurrency or queue depth (e.g., `vllm:num_requests_waiting` or batch size).
  - Include a reasonable default in the form of **Queue Size** unless the user specifically mentions a different metric.
  - Implementation can use either GKE Custom Metrics (Stackdriver Adapter) or KEDA.

## Workflow


The solution design and implementation workflow consists of the following 4 phases:

- **Phase 1: Discovery:** Inspect existing infrastructure via `gcloud` and gather model/traffic requirements.
- **Phase 2: Solution Design:** Calculate VRAM requirements, select hardware/storage, and generate Kubernetes manifests.
- **Phase 3: Implementation:** Provision resources, stage model weights via an ephemeral pod, and apply workload manifests using `kubectl`.
- **Phase 4: Validation and Cutover:** Verify pod health and endpoint inference, then provide traffic migration guidance.

At the start of **every architectural response**, print a simple visual progress indicator line to keep both the user and model aligned on the current phase:

```markdown
**Migration Progress:** [● Discovery] ➔ [○ Solution Design] ➔ [○ Implementation] ➔ [○ Validation]
```

*(Update `●` to mark the current active phase, e.g., `[● Solution Design]` during Phase 2).*

### Phase Routing Rules
Determine the active phase based on the user's prompt context:

If `migration-state.md` exists in the current directory, read it before anything else and resume from the recorded phase with the recorded values; only re-ask a discovery question if its value is missing from the file or contradicted by the user's prompt.

- **Phase 1 (Discovery):** Use for new migration requests without prior discovery.
- **Phase 2 (Solution Design):** Use when the prompt indicates discovery is complete or asks for architecture design / YAML manifest generation.
- **Phase 3 (Implementation):** Use when the prompt indicates model weights are staged or asks directly for deployment steps/commands. Progress indicator: `**Migration Progress:** [○ Discovery] ➔ [○ Solution Design] ➔ [● Implementation] ➔ [○ Validation]`.
- **Phase 4 (Validation):** Use when the prompt indicates the workload is running or asks for health checks/testing steps.

### Phase 1: Discovery

The goal of Phase 1 is to discover all workload specifications necessary to design and build the target GKE inference infrastructure.

**Phase 1 Response Requirements:** Every response during Phase 1 MUST begin with the visual progress indicator: `**Migration Progress:** [● Discovery] ➔ [○ Solution Design] ➔ [○ Implementation] ➔ [○ Validation]`.

#### Discovery Checklist (Attributes to Identify)
The agent must discover or confirm the following 6 core attribute categories:

- **Source Platform & Service Configuration:**
  - Source platform (Cloud Run, Gemini API, Gemini Enterprise Agent Platform, custom VM).
  - Container image tag, environment variables, CPU/RAM allocations, and secret bindings.
- **Model Specifications:**
  - Model name and parameter size (e.g., Gemma 2 9B, Llama 3 70B).
  - Target precision & quantization tolerance (FP16/BF16 vs INT8/INT4 AWQ). *Must inquire about quantization tolerance during discovery.*
  - Gated model status (whether Hugging Face token `HF_TOKEN` access is required).
  - **Model-Specific Architecture Requirements:** Explicitly check the model card (e.g., on Hugging Face) or `config.json` for custom configuration requirements. For example, determine if the architecture requires `--trust-remote-code` (like Qwen models), specific rope scaling arguments, or other custom flags.
- **Target GKE & Hardware Infrastructure:**
  - Target GKE cluster name and region (or confirm creating a new cluster).
  - Accelerator preference (L4, A100, H100, TPU v5e) and provisioning model (Spot/CCC vs On-Demand).
  - Regional quota availability for requested GPUs/TPUs.
- **Model Storage & Staging:**
  - Current location of model weights (GCS bucket, Hugging Face Hub, external URL).
  - Preferred storage integration (Cloud Storage FUSE vs Managed Lustre).
- **Traffic Profile & Load Balancing:**
  - Expected traffic volume, concurrency, and request patterns (spiky vs consistent baseline).
  - Load balancing needs (GKE Inference Gateway, standard Ingress/Service).
  - **Autoscaling Requirements:** Ask the user if they need Horizontal Pod Autoscaling (HPA). Do not assume they do. If they do, identify target metrics (defaulting to Queue Size) and discuss the LLM Autoscaling Trap.

- **Model Equivalence (Gemini API / Agent Platform sources only):**
  - Which Gemini model and API features are in use (function calling, system instructions, context length, multimodal inputs).
  - Which open-weights model will replace it, and how the user plans to evaluate output quality against the current system before cutover.
  - Client impact: the vLLM endpoint is OpenAI-compatible, not Gemini-API-compatible; identify the client code and SDK calls that must change.

#### Discovery Execution (Automated & Interactive)

- **Request Infrastructure Access & Permission First:** You MUST explicitly request permission from the user to inspect existing environment resources via CLI commands (such as `gcloud run services list` or `gcloud run services describe`) before executing any discovery commands.
- **Inspection Upon Approval:** Once the user grants permission, execute `gcloud` CLI commands, inspect environment variables, and review local workspace files to populate checklist items automatically:
  - **Cloud Run Workloads:** Run `gcloud run services list --format="table(metadata.name,status.url,status.latestReadyRevisionName)"` to enumerate services, then `gcloud run services describe {service_name} --format="yaml(spec.template.spec.containers,spec.template.metadata.annotations,spec.template.spec.serviceAccountName,spec.template.spec.containerConcurrency)"` to extract only the container image, env vars, resource limits, concurrency, and secret bindings. Prefer `--format` filters on all discovery commands; never pull a full unfiltered resource description into the conversation.
  - **Existing GKE Clusters:** Run `gcloud container clusters list` and `gcloud container clusters describe {cluster_name}` to inspect active cluster config, Workload Identity setup, and available accelerator pools.
  - **Vertex AI / Storage:** Run `gcloud ai endpoints list` or `gcloud storage buckets list` to locate model artifacts and storage buckets.
  - **Workspace & Environment:** Inspect local configuration files or environment variables in the active workspace directory.
- **Summarize, Query Missing Items, and Confirm:** Present a consolidated summary of all discovered configuration data and prompt the user for any remaining missing attributes. If any checklist item is unresolved or ambiguous, obtain explicit user confirmation before moving to Phase 2. If every checklist item was resolved without ambiguity, you MAY present the discovery summary and the Phase 2 solution design in the same response, under a single combined approval gate; the design approval then covers both.
- **Persist discovery state:** After the user confirms the discovery summary, write it to `migration-state.md` in the current directory: one section per checklist category with the confirmed values, plus a final line `Current phase: <phase name>`. Update the `Current phase:` line every time the workflow advances a phase.

### Phase 2: Solution Design

Based on the discovery phase, design the architecture and manifests needed to accomplish the migration.

**Phase 2 Response Requirements:** Every response during Phase 2 MUST begin with the visual progress indicator: `**Migration Progress:** [○ Discovery] ➔ [● Solution Design] ➔ [○ Implementation] ➔ [○ Validation]`.

**Just-in-Time Context Loading:** When evaluating specific architectural choices below (e.g., storage options, load balancing, or autoscaling), fetch and read the relevant reference documentation link from the **Supporting links** section as needed.

1. **Map components and alternatives:** For each major component (e.g., Load Balancing, Autoscaling, Single vs Multi-node), present your recommended "Golden Path" option along with alternatives. If the user requested HPA, ensure the design addresses the LLM Autoscaling Trap and recommends custom metrics (defaulting to Queue Size).
2.  **Accelerator Selection:** Refer to
    [GPU platforms](https://docs.cloud.google.com/compute/docs/gpus.md.txt) or
    [Plan your TPU configuration in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/plan-tpus.md.txt) to
    recommend the best accelerator for the target model.
    *(Note: the manifest templates in `assets/` are GPU-only. If the user selects Cloud TPU, state this explicitly, and base the serving manifests on the GKE TPU serving documentation instead of the templates in this skill.)*
3. **Storage Selection:** Refer to [GCP AI Storage Options](https://docs.cloud.google.com/ai-hypercomputer/docs/storage.md.txt) to recommend the best storage solution for model staging and serving.
4. **Hardware & VRAM Sizing:** Accurately calculate VRAM using the [Deterministic VRAM Sizing Formula](#deterministic-vram-sizing-formula) below, based on parameters, context window, and quantization. Map to appropriate GPUs (L4, A100, H100).
5. **Cluster & Node Setup:** Design the appropriate cluster for the job. Add appropriate sized nodes for the task using Custom Compute Classes (CCC). Design Workload Identity if required. The vLLM Deployment MUST select nodes with `nodeSelector: cloud.google.com/compute-class: {compute_class_name}` so the workload actually schedules through the ComputeClass. If the user declines CCC and wants on-demand nodes only, replace this selector with `cloud.google.com/gke-accelerator: {accelerator_type}` and skip `ccc-profile.yaml` entirely; do not apply a ComputeClass that no workload references.
6. **Model Staging Design:** Determine if a staging Job is required based on the source location of the model weights and the target storage solution. If the source is Hugging Face, or if the target is Lustre and source is GCS, plan for a Job to download/copy weights. If the source is GCS and target is GCS FUSE, skip staging. Plan for using Cloud Storage FUSE or Lustre CSI to mount this storage to the workload.
7. **Draft solution architecture and manifests:** Read the manifest templates in `assets/` (`assets/vllm-deployment.yaml.tmpl`, `assets/ccc-profile.yaml.tmpl`, `assets/gke-inference-gateway.yaml.tmpl`, `assets/storage-config.yaml.tmpl`, and `assets/model-staging-job.yaml.tmpl`), substitute the parameters discovered in Phase 1, and save the resulting YAML manifests (`vllm-deployment.yaml`, `ccc-profile.yaml`, `gke-inference-gateway.yaml`, `storage-config.yaml`, `model-staging-job.yaml`) to disk in the current directory. When creating `vllm-deployment.yaml`, explicitly inject any required model-specific architecture flags discovered in Phase 1 (e.g., `--trust-remote-code`) into the container `args` array. When creating `gke-inference-gateway.yaml`, base it on `assets/gke-inference-gateway.yaml.tmpl`: use `gatewayClassName: gke-l7-rilb` for the Gateway resource unless the user has explicitly chosen external exposure or the InferencePool-based GKE Inference Gateway, and route `/v1` traffic to the vLLM ClusterIP service (`{workload_name}-vllm-svc` on port 8000) in the HTTPRoute resource. If using a storage class other than `gcsfuse-csi` (e.g., `lustre-csi`), remove the `gcsfuse.cloud.google.com` annotations from `storage-config.yaml`.
8. **Request review and iterate:** Present the generated solution architecture and diagram to the user and request their feedback. Iterate on the design until the user approves it before moving to Phase 3.

#### Deterministic VRAM Sizing Formula

To accurately calculate VRAM requirements for model serving/inference, use the following deterministic formula:

**Hardware & Sizing Recommendation Requirements:** When calculating VRAM sizing or recommending hardware:

- Explain the VRAM calculation explicitly using the formula below (parameter size, KV cache, 20% safety margin).
- Recommend a specific accelerator type (e.g., NVIDIA L4 with 24GB VRAM for 8B models in FP16/BF16).
- Recommend using **Custom Compute Classes (CCC)** to maximize accelerator obtainability.
- Inquire about or confirm the user's **quantization tolerance** (FP16/BF16 vs INT8/INT4) in the Discovery phase.

$$VRAM_{\text{total}} = \left( \frac{\text{Parameters} \times 2}{\text{Quantization}} + KV\_Cache\_Overhead \right) \times 1.2$$

Where:

*   **Parameters**: Model size in billions of parameters (e.g., `8` for 8B, `70` for 70B).
*   **Quantization**: Divisor based on target precision relative to 16-bit (FP16/BF16):
    *   `1` for 16-bit (FP16 / BF16, 2 bytes/param)
    *   `2` for 8-bit (FP8 / INT8, 1 byte/param)
    *   `4` for 4-bit (INT4 / AWQ / GPTQ, 0.5 bytes/param)
*   **$KV\_Cache\_Overhead$**: Memory (GB) reserved for key-value cache during generation:
    $$KV\_Cache\_Overhead \,(GB) = \frac{2 \times n_{\text{layers}} \times n_{\text{kv\_heads}} \times d_{\text{head}} \times \text{Context Length} \times \text{Batch Size} \times \text{Precision Bytes}}{10^9}$$
    *(Rule of thumb: If model layer architecture details are unknown, estimate $KV\_Cache\_Overhead \approx 0.2 \times \text{Model Weight Memory}$).*
*   **`1.2` Multiplier**: 20% safety margin for CUDA context, activation memory, and serving engine overhead.

When mapping the result to an accelerator, compare $VRAM_{\text{total}}$ against the card's full memory (e.g., 24 GB for an L4), not against memory discounted by `--gpu-memory-utilization`. The 1.2 multiplier and vLLM's utilization cap reserve headroom for the same overheads; applying both double-counts the margin and pushes sizing one accelerator tier too high.

### Phase 3: Implementation

Carry out the approved design per the Execution policy: generate the commands below and either hand them to the user or, if the user has asked you to run them, execute them and report the output.

1. **Identify deployment prerequisites:** Ensure billing, APIs, and IAM permissions are in place.
2. **Infrastructure Provisioning:** Provide explicit `gcloud` commands to provision storage and cluster prerequisites (such as enabling the Cloud Storage FUSE CSI driver) and configure Workload Identity IAM bindings. **Gateway API Pre-flight Check:** Explicitly instruct the user to verify the Gateway API is enabled on their cluster. Recommend running `gcloud container clusters update <CLUSTER_NAME> --gateway-api=standard` before they attempt to apply the routing manifests to prevent CRD-not-found errors.
3. **Storage Provisioning:** Create the necessary storage resources (Cloud Storage bucket or Managed Lustre file system).
4. **Model Staging:** Apply conditional logic based on the design from Phase 2.
    - **Skipped:** If the model is already in GCS and using GCS FUSE, skip to step 5.
    - **Hugging Face Source:** If using a gated model (e.g., Llama 3, Gemma), explicitly instruct the user to run the `kubectl create secret generic hf-secret ...` command locally **before** applying any jobs or deployments (see Gated Model Secret Security rules). Once the secret is created, instruct the user to run `kubectl apply -f model-staging-job.yaml`.
    - **GCS to Lustre Source:** Instruct the user to run `kubectl apply -f model-staging-job.yaml` (which should be configured to use `gcloud storage cp` or similar).
    - **Completion Gate:** For any active staging Job, gate on completion with `kubectl wait --for=condition=complete job/{workload_name}-model-staging --timeout=90m` (scale the timeout to the model size). If the Job fails, inspect it with `kubectl logs job/{workload_name}-model-staging` before retrying. Explain that staging through a cluster Job avoids downloading heavy weights to the user's workstation and avoids re-downloading on every container restart.
5. **Workload Deployment:** Provide explicit `kubectl apply` commands to deploy the storage config (`kubectl apply -f storage-config.yaml`), ComputeClass (`kubectl apply -f ccc-profile.yaml`), vLLM deployment (`kubectl apply -f vllm-deployment.yaml`), and Inference Gateway (`kubectl apply -f gke-inference-gateway.yaml`). Ensure the vLLM deployment spec mounts the staged model weights from the PVC into `/models`. Ensure that if a Secret was created for a gated model, it is referenced correctly in the Deployment manifest. Set vLLM's `--model` flag to the staged local path (`/models/{model_name}`), never to the Hugging Face repo ID; a repo ID makes vLLM re-download the full weights on every pod start and silently defeats the staging step. Preserve the model's public name for API clients with `--served-model-name={model_id}`.
6. **Verify the rollout:** Confirm success with `kubectl rollout status deployment/{workload_name}-vllm --timeout=30m` and `kubectl get pods -l app={workload_name}-vllm -o wide`. If the rollout fails or times out, go directly to Troubleshooting Guidance with the observed error; do not ask the user whether the deployment succeeded when the command output already answers it. Ask the user only about outcomes the cluster cannot verify (for example, whether response quality matches the source system).

### Phase 4: Validation and Cutover

Verify that the deployed infrastructure meets the workload's requirements and provide instructions for traffic migration.

**Phase 4 Response Requirements:** Every response during Phase 4 MUST begin with the visual progress indicator: `**Migration Progress:** [○ Discovery] ➔ [○ Solution Design] ➔ [○ Implementation] ➔ [● Validation]`.

1. **Health Checks:** Recommend explicit health check commands to verify pod, node, and gateway status (`kubectl get pods`, `kubectl get nodes`, and `kubectl get gateway`).
2. **Testing Inference:** Verify the service is serving the model. Provide a `kubectl port-forward` command (`kubectl port-forward svc/{workload_name}-vllm-svc 8000:8000`) and a sample `curl` request to `/v1/chat/completions` to test endpoint inference. Compare responses with the previous infrastructure if applicable.
3. **Traffic Cutover Guidance:** Do NOT attempt to implement traffic migration automatically. Instead:
    * Provide the internal GKE endpoint that is ready to receive traffic.
    * Offer suggestions based on the relevant codebase (if any) for how to migrate the traffic over.
    * Suggest a standard GKE rollout (e.g., updating the existing deployment manifest to point to the new service) without fancy canary tests or blue/green deployments.
    * Offer more advanced traffic migration options only if the user explicitly asks for them.
4. **Rollback readiness:** Before any traffic moves, confirm the source service stays deployed (scaled down is fine, deleted is not) until the GKE endpoint has served production traffic for a period the user chooses. Provide the single command or config change that restores traffic to the source. Only after the user declares the migration stable, provide the commands to decommission the source service.
5. **Compile Validation Report & Request Final Approval:** Compile a validation report summarizing all health check outcomes and inference test results. You MUST explicitly request final user approval to finalize and complete the migration workflow.

### Troubleshooting Guidance

When users report issues where pods are created but the inference endpoint is not responding (or request troubleshooting help):

1. Recommend specific diagnostic commands: `kubectl logs {pod_name}` (to check container startup logs) and `kubectl describe pod {pod_name}` (to inspect pod initialization state).
2. Suggest verifying Google Cloud accelerator quotas (GPU/TPU) in the target region to ensure required resources can be provisioned.
3. **Check for JIT Compilation / Startup Delays:** If `curl` returns `Connection refused` but the Pod is `Running`, the serving engine (e.g., vLLM) may still be executing JIT compilation (such as Triton PTX or Torch Inductor) or capturing CUDA graphs. This can take several minutes *after* model weights are loaded. Advise the user to check `kubectl logs {pod_name}` and explicitly wait for the `Uvicorn running on http://0.0.0.0:8000` (or equivalent) log message before assuming there is a networking issue.
4. Recommend checking GKE Workload Identity bindings, PVC mount health (Cloud Storage FUSE), and GKE Inference Gateway listener configurations.

## Supporting links

Use these references as needed to ground your design choices, answer user questions, and generate implementation manifests:

*   [GPU platforms](https://docs.cloud.google.com/compute/docs/gpus.md.txt)
*   [Plan your TPU configuration in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/plan-tpus.md.txt)
*   [Gemini Cloud Assist MCP Documentation](https://docs.cloud.google.com/cloud-assist/configure-mcp)
*   [About AI/ML model inference on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/machine-learning/inference.md.txt)
*   [Choose a load balancing strategy for AI/ML model inference on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/machine-learning/choose-lb-strategy.md.txt)
*   [Best practices for autoscaling large language model inference workloads with GPUs on Google Kubernetes Engine](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference/autoscaling.md.txt)
*   [Google Cloud AI Storage Options](https://docs.cloud.google.com/ai-hypercomputer/docs/storage.md.txt)
*   [Optimize AI/ML workloads with Cloud Storage FUSE](https://docs.cloud.google.com/architecture/optimize-ai-ml-workloads-cloud-storage-fuse.md.txt)
*   [Optimize AI/ML workloads with Managed Lustre](https://docs.cloud.google.com/architecture/optimize-ai-ml-workloads-managed-lustre.md.txt)
