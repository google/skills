---
name: agent-platform-agent-registry
description: >-
  Manages Google Cloud Agent Registry (agentregistry.googleapis.com) resources
  using gcloud CLI and Kubernetes manifests, including agents, MCP servers,
  endpoints, services, bindings, AI applications, skills and skill revisions,
  resource-level IAM policies, Cloud Run and GKE automatic workload
  registration, Cloud Resource Manager management boundaries, 5-endpoint Quick
  Add for Agent Gateway, and Python ADK integration. Use when registering,
  discovering, searching, filtering, or governing agents, MCP servers,
  endpoints, skills, AI applications, or management boundaries in Google Cloud
  Agent Registry. Don't use for the preview AI Platform Skill Registry Python
  scripts (use agent-platform-skill-registry), deploying raw Vertex AI Agent
  Engine code (use agent-platform-deploy), or runtime trace debugging (use
  agent-platform-troubleshooting).
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

<!-- disableFinding(LINE_OVER_80) -->

# Google Cloud Agent Registry

Interact with Google Cloud Agent Registry using `gcloud agent-registry` (`agents`, `mcp-servers`, `services`, `endpoints`, `bindings`, `skills`, `findings`, `publishers`, `ai-applications`, `operations`), `gcloud beta run` (`--functional-type` and `--identity-type` for automatic registration of Cloud Run services and jobs), Kubernetes manifests and [scripts/annotate_gke.py](scripts/annotate_gke.py) (GKE automatic registration), `gcloud resource-manager` (`boundary-configs`, `capability-configs`, `boundaries`, and `tags bindings` for management boundaries), and Python ADK (`google-adk`).

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST read and follow the instructions in [Usage Attribution](references/attribution.md).

## Workflow

1. **Resolve session context** — at the start of each session, silently run:
   ```bash
   gcloud config get-value project 2>/dev/null
   gcloud config get-value compute/region 2>/dev/null
   ```
   Store the results as `SESSION_PROJECT` and `SESSION_LOCATION` and use them as defaults.
2. **Parse** the user's request to identify the target resource and action.
3. **Construct** the `gcloud` command or Kubernetes manifest using session defaults. See [gcloud Command Reference](references/gcloud-command.md) for full flag synopses, command summary tables, and 60+ natural-language-to-command examples.
4. **Documentation Fallback** — if a user asks about a feature, flag, schema, or error message not covered in this skill, query the `developerknowledge` MCP server or public `.md.txt` documentation (see [Documentation Fallback](#documentation-fallback-developerknowledge-mcp-server)).
5. **Approval**:
   - **Read-only commands** (`list`, `describe`, `search`, `get-iam-policy`): Execute immediately without asking for approval.
   - **Mutating commands** (`create`, `delete`, `update`, `deploy`, `set-iam-policy`, `add-iam-policy-binding`, `remove-iam-policy-binding`): Display the exact command and ask: _"Ready to run this command? (yes/no)"_
   - **Multi-task requests**: Always output the commands for **every** requested task in the same response before asking for approval.
6. **Execute** and display the output.

## Prerequisites, Auth, Billing, Region & IAM Permissions

- **Cloud SDK**: Requires `gcloud` **560.0.0+** (`beta` **2026.03.09+** for Cloud Run automatic registration; ensure `gcloud` is up to date for GA `gcloud agent-registry skills`). Do **not** install or update tools or packages on the host without explicit user approval; if `gcloud` is missing, share `https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt` and fall back to `.md.txt` documentation.
- **Billing & Pricing**: The target project must be linked to an active Google Cloud Billing account. For Cloud Run, GKE, or Vertex AI pricing, direct users to `https://cloud.google.com/pricing`.
- **Region & Location Availability**: Configure a default region (`gcloud config set compute/region us-central1`) and verify supported regions at `https://docs.cloud.google.com/agent-registry/locations.md.txt` and `https://cloud.google.com/about/locations` (note: Skills only support `global`, `us`, or `eu`).
- **Authentication**: Check active credentials first with `gcloud auth list`. Because `gcloud auth login` and `gcloud auth application-default login` launch interactive browser flows and stop responding in non-interactive shells, **never** execute them directly — if unauthenticated, ask the user to run `gcloud auth login` (for CLI sessions) or `gcloud auth application-default login` (for local Python ADK Application Default Credentials) in their own terminal, or configure `GOOGLE_APPLICATION_CREDENTIALS`.

```bash
# Check active authentication status first (read-only)
gcloud auth list

# If unauthenticated, ask the user to run these interactively in their terminal:
# gcloud auth login
# gcloud auth application-default login
gcloud config set project PROJECT_ID
gcloud config set compute/region us-central1
gcloud services enable agentregistry.googleapis.com
```

| Role | Access Level |
|------|--------------|
| `roles/agentregistry.admin` | Full administrative access across all Agent Registry resources, including bindings, skill scan findings, and resource-level IAM policies (`aiApplications.{getIamPolicy,setIamPolicy}` and `skills.{getIamPolicy,setIamPolicy}`) |
| `roles/agentregistry.editor` | Register and update agents, MCP servers, endpoints, services, skills, skill revisions, and AI Applications (excludes bindings, scan findings, and IAM policy mutations) |
| `roles/agentregistry.viewer` | Read-only access (`get`, `list`, `search`) to agents, MCP servers, endpoints, services, bindings, skills, skill revisions, publishers, and AI Applications |
| `roles/agentregistry.user` | **Agent Registry User** — least-privilege GA role granting read-only viewer access across Agent Registry plus permissions to create, update, and delete standalone skills, skill revisions, and scanning settings without edit access to agents, MCP servers, or endpoints |
| `roles/run.admin` + `roles/apphub.admin` + `roles/iam.serviceAccountUser` | Deploy or update Cloud Run services and jobs with `--functional-type` and `--identity-type` |
| `roles/resourcemanager.editor` | Create and update `BoundaryConfig`, `CapabilityConfig`, and `Boundary` on the parent folder or organization |
| `roles/resourcemanager.viewer` | Read `BoundaryConfig`, `CapabilityConfig`, and `Boundary` resources |
| `roles/resourcemanager.tagUser` | Bind or unbind tag values (`tags bindings create/delete`) on projects |
| `roles/owner` or `roles/editor` | Required on a candidate Bring-Your-Own project to associate it as a Management Project |

---

## Resource Types & Registration

- **Manual Registration (`services create`)**: `gcloud agent-registry services create` creates a writable `Service` resource to manually register external or cross-project `Agent`, `McpServer`, and `Endpoint` resources in Agent Registry, and automatically projects a corresponding read-only `Agent`, `McpServer`, or `Endpoint` catalog entry (`agentregistry-{ID}`, returned in `registryResource` on `services describe`) used for runtime discovery and IAP/Agent Gateway policies.

### 1. MCP Servers

If the user has not provided the MCP tool spec JSON yet, ask: _"Please paste the contents of your MCP server spec JSON file."_ and preview the command template using `'PASTE_MCP_SPEC_JSON_HERE'`:

```bash
# Register an MCP Server (mutating — ask for approval first)
gcloud agent-registry services create my-mcp-service \
  --location=us-central1 \
  --display-name="My MCP Server" \
  --description="Connects to an external MCP server" \
  --mcp-server-spec-type=tool-spec \
  --mcp-server-spec-content='PASTE_MCP_SPEC_JSON_HERE' \
  --interfaces='[{"protocolBinding": "jsonrpc", "url": "https://mcp.example.com/v1"}]'

# List Regional or Global MCP Servers (read-only — execute immediately)
gcloud agent-registry mcp-servers list --location=us-central1
gcloud agent-registry mcp-servers list --location=global
```

### 2. Agents

For A2A agents, if the user has not pasted `agent_card.json` yet, ask: _"Please paste the contents of your `agent_card.json` file."_ and preview the command template using `'PASTE_AGENT_CARD_JSON_HERE'`:

```bash
# Register a Standard Agent (no-spec)
gcloud agent-registry services create my-custom-agent \
  --location=us-central1 \
  --display-name="My Custom Agent" \
  --description="Custom HTTP JSON agent" \
  --agent-spec-type=no-spec \
  --interfaces='[{"protocolBinding": "http-json", "url": "https://agent.example.com/v1"}]'

# Register an A2A Agent (a2a-agent-card)
gcloud agent-registry services create my-a2a-agent \
  --location=us-central1 \
  --display-name="My A2A Agent" \
  --description="Sample A2A Agent" \
  --agent-spec-type=a2a-agent-card \
  --agent-spec-content='PASTE_AGENT_CARD_JSON_HERE'

# List Regional or Global Agents
gcloud agent-registry agents list --location=us-central1
gcloud agent-registry agents list --location=global
```

### 3. Endpoints, Services & Quick Add GCP Service (Composite Agent Gateway Registration)

```bash
# Register a single Endpoint, list/describe/update/delete Services, and inspect Operations
gcloud agent-registry services create gemini-models --location=us-central1 \
  --display-name="Vertex AI Model Garden" --description="List of all models in Vertex AI Model Garden" \
  --endpoint-spec-type=no-spec \
  --interfaces='[{"protocolBinding": "jsonrpc", "url": "https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/*/models"}]'
gcloud agent-registry endpoints list --location=us-central1
gcloud agent-registry services list --location=us-central1
gcloud agent-registry services describe gemini-models --location=us-central1
gcloud agent-registry services update gemini-models --display-name="Model Garden on Vertex AI" --location=us-central1
gcloud agent-registry services delete gemini-models --location=us-central1
gcloud agent-registry operations list --location=us-central1
gcloud agent-registry operations describe OPERATION_ID --location=us-central1
```

#### Quick Add GCP Service (All 5 Endpoint URL Variants)

When an agent runs behind a governed **Agent Gateway** (default-deny egress), Google Cloud SDKs dynamically resolve endpoints across up to 5 hostname variants:
1. **Base**: `https://${SERVICE_ID}.googleapis.com`
2. **Base mTLS**: `https://${SERVICE_ID}.mtls.googleapis.com`
3. **Locational**: `https://${LOCATION}-${SERVICE_ID}.googleapis.com` *(omit when `--location=global`)*
4. **Locational mTLS**: `https://${LOCATION}-${SERVICE_ID}.mtls.googleapis.com` *(omit when `--location=global`)*
5. **Regional REP**: `https://${SERVICE_ID}.${LOCATION}.rep.googleapis.com` *(omit when `--location=global`)*

Register a **single composite `Service`** containing all applicable variants using [scripts/quick-add-gcp-service.sh](scripts/quick-add-gcp-service.sh) or `gcloud agent-registry services create` (always previewing and asking for approval first):
- **Service ID Length (`4–63` chars)**: Service IDs must match `^[a-z][a-z0-9-]{2,61}[a-z0-9]$`. For 3-letter APIs (`iam`, `kms`, `run`, `dns`), suffix the `Service` ID (e.g., `${SERVICE_ID}-api`) while keeping `${SERVICE_ID}` in the endpoint URLs.
- **Global Location Guardrail**: When `--location=global`, include only `Base` and `Base mTLS` so invalid regional DNS names are not registered.
- **IAP Egress Policy Target**: Bind **`roles/iap.egressor`** for the Agent Identity to the projected `Endpoint` catalog ID (`endpoints/agentregistry-{UUID}` from `registryResource` on `services describe`), **not** the user-chosen `Service` ID.

```bash
# Option A: Bundled Quick Add helper script (handles 3-letter APIs, --location=global, and --dry-run)
./scripts/quick-add-gcp-service.sh --service=aiplatform --location=us-central1 --project=PROJECT_ID

# Option B: Single composite gcloud command (all 5 variants for a regional location)
SERVICE_ID="aiplatform" && SERVICE_NAME="aiplatform" && LOCATION="us-central1" && PROJECT_ID="PROJECT_ID"
gcloud agent-registry services create "${SERVICE_NAME}" --project="${PROJECT_ID}" --location="${LOCATION}" \
  --display-name="${SERVICE_ID}" --description="Google Cloud ${SERVICE_ID} API endpoints" --endpoint-spec-type=no-spec \
  --interfaces="protocolBinding=jsonrpc,url=https://${SERVICE_ID}.googleapis.com" \
  --interfaces="protocolBinding=jsonrpc,url=https://${SERVICE_ID}.mtls.googleapis.com" \
  --interfaces="protocolBinding=jsonrpc,url=https://${LOCATION}-${SERVICE_ID}.googleapis.com" \
  --interfaces="protocolBinding=jsonrpc,url=https://${LOCATION}-${SERVICE_ID}.mtls.googleapis.com" \
  --interfaces="protocolBinding=jsonrpc,url=https://${SERVICE_ID}.${LOCATION}.rep.googleapis.com"
```

### 4. GKE Agents & MCP Servers (Automatic Registration)

Configure GKE `Deployment` manifests for automatic discovery in Agent Registry (using `metadata.name` as the display name):

| Component Type | `metadata.labels` (Deployment) | `metadata.annotations` (Deployment) | `spec.template.metadata.annotations` (Pod) |
|----------------|--------------------------------|-------------------------------------|--------------------------------------------|
| **GKE Agent** | `registry.gke.io/functional-type: "AGENT"` *(plus `apphub.cloud.google.com/functional-type: "AGENT"` in annotations for compatibility)* | `a2a-protocol.org/agent-card`: Declares `card.endpoint` (`/.well-known/agent-card.json`), `card.protocol` (`HTTP`), `card.port` (`8080`) | `iam.gke.io/spiffe-identity-type: agent-identity` |
| **GKE MCP Server** | `registry.gke.io/functional-type: "MCP_SERVER"` *(plus `apphub.cloud.google.com/functional-type: "MCP_SERVER"` in annotations for compatibility)* | `modelcontextprotocol.info/urls`: In-cluster URL list (`- https://my-mcp-server.default.svc.cluster.local/mcp`)<br>`modelcontextprotocol.info/capabilities`: `card.endpoint` (`"/mcp"`), `card.protocol` (`"HTTP"`) | `iam.gke.io/spiffe-identity-type: agent-identity` |

Use [scripts/annotate_gke.py](scripts/annotate_gke.py) to automatically add `registry.gke.io/functional-type`, `apphub.cloud.google.com/functional-type`, and the Pod template `iam.gke.io/spiffe-identity-type: "agent-identity"` annotation to existing YAML files (target path is required; supports `--dry-run`):

```bash
./scripts/annotate_gke.py /path/to/folder_or_file.yaml --type AGENT
./scripts/annotate_gke.py /path/to/folder_or_file.yaml --type MCP_SERVER
```

**GKE Agent (`Deployment` + `Service`) & MCP Server (`Deployment`) Templates:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-agent
  labels:
    registry.gke.io/functional-type: "AGENT"
  annotations:
    apphub.cloud.google.com/functional-type: "AGENT"
    a2a-protocol.org/agent-card: |
      card:
        endpoint: /.well-known/agent-card.json
        protocol: HTTP
        port: 8080
spec:
  selector:
    matchLabels:
      app: my-agent
  template:
    metadata:
      labels:
        app: my-agent
      annotations:
        iam.gke.io/spiffe-identity-type: agent-identity
    spec:
      containers:
      - name: server
        image: us-central1-docker.pkg.dev/PROJECT_ID/my-repo/my-agent:1.0.0
        ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: my-agent-service
spec:
  type: ClusterIP
  ports:
  - port: 8080
    targetPort: 8080
    protocol: TCP
    name: http
  selector:
    app: my-agent
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-mcp-server
  labels:
    registry.gke.io/functional-type: "MCP_SERVER"
  annotations:
    apphub.cloud.google.com/functional-type: "MCP_SERVER"
    modelcontextprotocol.info/urls: |
      - https://my-mcp-server.default.svc.cluster.local/mcp
    modelcontextprotocol.info/capabilities: |
      card:
        endpoint: "/mcp"
        protocol: "HTTP"
spec:
  selector:
    matchLabels:
      app: my-mcp-server
  template:
    metadata:
      labels:
        app: my-mcp-server
      annotations:
        iam.gke.io/spiffe-identity-type: agent-identity
    spec:
      containers:
      - name: server
        image: us-central1-docker.pkg.dev/PROJECT_ID/my-repo/my-mcp-server:1.0.0
```

### 5. Cloud Run Agents & MCP Servers (Automatic Registration via `--functional-type`)

Register Cloud Run services and jobs automatically using `gcloud beta run`:

> [!WARNING]
> **Critical Cloud Run Guardrails:**
> 1. **Immutability**: Once `--functional-type` or `--identity-type` is set on a Cloud Run service or job, it is **immutable** and cannot be changed or cleared.
> 2. **`--functional-type=agent` Requires `--identity-type=agent-identity`**: Always include `--identity-type=agent-identity` whenever `--functional-type=agent` is used (certificates are provisioned by default; opt out with `--no-identity-certificate`).
> 3. **Updating Existing Services (`--no-traffic` Guardrail)**: Transitioning an existing service to `--identity-type=agent-identity` assigns a new SPIFFE Agent Identity principal (`principal://agents.global.org-ORGANIZATION_ID.system.id.goog/resources/run/projects/PROJECT_NUMBER/locations/REGION/services/SERVICE_NAME`) that **does not inherit** the previous service account's IAM permissions. Recommend `--no-traffic` on `gcloud beta run services update` to stage IAM bindings before shifting traffic.
> 4. **Cloud Run Jobs Cannot Be MCP Servers**: Only Cloud Run **services** support `--functional-type=mcp-server`; Cloud Run **jobs** only support `--functional-type=agent`.

```bash
# Deploy or update a Cloud Run service as an AI Agent or MCP Server
gcloud beta run deploy SERVICE_NAME --image=IMAGE_URL --region=us-central1 \
  --functional-type=agent --identity-type=agent-identity
gcloud beta run services update SERVICE_NAME --region=us-central1 \
  --functional-type=agent --identity-type=agent-identity --no-traffic
gcloud beta run deploy SERVICE_NAME --image=IMAGE_URL --region=us-central1 \
  --functional-type=mcp-server --identity-type=IDENTITY_TYPE
gcloud beta run services update SERVICE_NAME --region=us-central1 --functional-type=mcp-server

# Create or update a Cloud Run Job as an AI Agent
gcloud beta run jobs create JOB_NAME --image=IMAGE_URL --region=us-central1 \
  --functional-type=agent --identity-type=agent-identity
gcloud beta run jobs update JOB_NAME --region=us-central1 \
  --functional-type=agent --identity-type=agent-identity

# Inspect Agent Identity or delete Cloud Run workloads
gcloud beta run revisions describe REVISION_NAME --region=us-central1
gcloud beta run jobs executions describe EXECUTION_NAME --region=us-central1
gcloud run services delete SERVICE_NAME --region=us-central1
gcloud run jobs delete JOB_NAME --region=us-central1
```

### 6. Bindings

Connect a source agent to a target resource or an Auth Provider connector:

```bash
gcloud agent-registry bindings create BINDING_NAME --location=us-central1 \
  --display-name="My Custom Binding" --source-identifier="SOURCE_ID" --target-identifier="TARGET_ID"
gcloud agent-registry bindings create BINDING_NAME --location=us-central1 \
  --display-name="Auth Provider Binding" --source-identifier="SOURCE_ID" \
  --auth-provider="projects/PROJECT_ID/locations/REGION/connectors/AUTH_PROVIDER_ID"
gcloud agent-registry bindings list --location=us-central1
gcloud agent-registry bindings describe BINDING_NAME --location=us-central1
gcloud agent-registry bindings update BINDING_NAME --display-name="New Display Name" --location=us-central1
gcloud agent-registry bindings delete BINDING_NAME --location=us-central1
```

### 7. Skills & Skill Revisions

Manage reusable AI Skills, Skill Revisions, and Skill IAM policies using `gcloud agent-registry skills`.

> [!IMPORTANT]
> **Skills Guardrails (`--location`, `private-` Prefix & `--target-state`):**
> - **Supported Locations**: Skills only work in `"global"`, `"us"`, or `"eu"` multi-regions. If a user asks for any single region (e.g. `us-central1`), **do not pass that region to `gcloud`**. Explain that Skills are only supported in `global`, `us`, or `eu`, preview the command using a concrete supported multi-region (e.g. `--location=us`, `--location=eu`, or `--location=global`), and ask them to confirm which multi-region to use.
> - **Automatic `private-` Prefix**: Running `gcloud agent-registry skills create my-skill` automatically prepends `private-`, creating `skills/private-my-skill`. Subsequent `describe`, `update`, `delete`, `revisions`, and `*-iam-policy` commands **must** pass `private-my-skill` (passing `my-skill` fails with `NOT_FOUND`).
> - **Target State & Scanning**: `--target-state=active|disabled|draft` sets the desired lifecycle state on creation (`active` requires an initial revision via `--payload` or `--gcs-source-uri`; `deprecated` and `decommissioned` are also valid on `update`). Under the default `enabled-blocking` scanning policy, `--target-state=active` enters `DRAFT` (`STATE_DRAFT`) until the background security scan passes with no findings.

```bash
# List, create (local ZIP or GCS URI), describe, update, and delete Skills
gcloud agent-registry skills list --location=us
gcloud agent-registry skills create my-skill --location=us \
  --display-name="My Custom Skill" --description="Skill description" --type=simple --target-state=active --payload=/path/to/archive.zip
gcloud agent-registry skills create my-skill --location=us \
  --display-name="My Custom Skill" --target-state=disabled --gcs-source-uri=gs://my-bucket/skill.zip
gcloud agent-registry skills describe private-my-skill --location=us
gcloud agent-registry skills update private-my-skill --location=us --display-name="Updated Skill Name" --target-state=active
gcloud agent-registry skills delete private-my-skill --location=us

# Manage Skill Revisions and Resource-Level IAM Policies (using private-my-skill)
gcloud agent-registry skills revisions create REVISION_ID --skill=private-my-skill --location=us --payload=/path/to/archive.zip
gcloud agent-registry skills revisions list --skill=private-my-skill --location=us
gcloud agent-registry skills revisions describe REVISION_ID --skill=private-my-skill --location=us
gcloud agent-registry skills revisions download REVISION_ID --skill=private-my-skill --location=us --destination=./skill-payload.zip
gcloud agent-registry skills revisions delete REVISION_ID --skill=private-my-skill --location=us
gcloud agent-registry skills get-iam-policy private-my-skill --location=us
gcloud agent-registry skills set-iam-policy private-my-skill policy.json --location=us
gcloud agent-registry skills add-iam-policy-binding private-my-skill --location=us \
  --member='user:test-user@example.com' --role='roles/agentregistry.viewer'
gcloud agent-registry skills remove-iam-policy-binding private-my-skill --location=us \
  --member='user:test-user@example.com' --role='roles/agentregistry.viewer'
```

### 8. AI Applications (`ai-applications`)

An **AI Application** (`projects/{project}/locations/{location}/aiApplications/{ai_application}`, including the regional `default` AI Application) groups agents, MCP servers, and endpoints under a governance perimeter.

```bash
# List, filter, describe, and search AI Applications
gcloud agent-registry ai-applications list --location=us-central1
gcloud agent-registry ai-applications list --location=us-central1 \
  --filter="attributes.environment.type=production AND attributes.criticality.type=high"
gcloud agent-registry ai-applications describe my-app --location=us-central1
gcloud agent-registry ai-applications describe default --location=us-central1
gcloud agent-registry ai-applications search --location=us-central1 --search-string="displayName:Support*"

# Create, update, and delete an AI Application
gcloud agent-registry ai-applications create my-app --location=us-central1 \
  --display-name="Customer Support App" --description="AI Application orchestrating customer support agents" \
  --environment-type=production --criticality-type=high \
  --business-owners=email=biz-owner@example.com --developer-owners=email=dev-owner@example.com --operator-owners=email=ops-owner@example.com
gcloud agent-registry ai-applications update my-app --location=us-central1 \
  --display-name="Updated Support App" --environment-type=staging --criticality-type=medium
gcloud agent-registry ai-applications delete my-app --location=us-central1 --force

# Inspect & search subresources scoped to an AI Application (agents, mcp-servers, endpoints)
gcloud agent-registry ai-applications agents list --ai-application=my-app --location=us-central1
gcloud agent-registry ai-applications agents describe AGENT_ID --ai-application=my-app --location=us-central1
gcloud agent-registry ai-applications agents search --ai-application=my-app --location=us-central1 --search-string="displayName:Assistant*"
gcloud agent-registry ai-applications mcp-servers list --ai-application=my-app --location=us-central1
gcloud agent-registry ai-applications endpoints list --ai-application=my-app --location=us-central1

# Manage Resource-Level IAM Policies on an AI Application
gcloud agent-registry ai-applications get-iam-policy my-app --location=us-central1
gcloud agent-registry ai-applications set-iam-policy my-app policy.json --location=us-central1
gcloud agent-registry ai-applications add-iam-policy-binding my-app --location=us-central1 \
  --member='group:support-team@example.com' --role='roles/agentregistry.viewer'
gcloud agent-registry ai-applications remove-iam-policy-binding my-app --location=us-central1 \
  --member='group:support-team@example.com' --role='roles/agentregistry.viewer'
```

### 9. Management Boundary Setup (Admin Governance)

Configure Folder/Organization hub-and-spoke perimeters using `gcloud resource-manager` (`boundary-configs`, `capability-configs`, `boundaries`, and `tags bindings`). Read [Management Boundaries Guide](references/management-boundaries.md) for the full IAM table, 6 interactive scoping questions, and 6-step provisioning workflow.

- **Always Use Project Numbers (`projects/<PROJECT_NUMBER>`)**: Cloud Resource Manager v3 requires project **numbers** (not project IDs) for `--management-project=projects/<PROJECT_NUMBER>` and `--parent=//cloudresourcemanager.googleapis.com/projects/<PROJECT_NUMBER>`. When given a project ID, output **both** `gcloud projects describe PROJECT_ID --format="value(projectNumber)"` and the `capability-configs create` command template (`--types=agent-management` by default) in the same response.
- **Set `BoundaryConfig` Before Attaching Boundaries & Isolate `dev`/`prod` Hubs**: Set `boundary-configs update --tag-key=...` before attaching boundaries. Use separate `CapabilityConfig` + Management Project + `Boundary` per environment (`dev` vs. `prod`) for strict catalog and IAM isolation.
- **Tag Rebinding Requires Delete-Then-Create**: Moving a project between tag values (e.g., `dev` to `prod`) fails with `FAILED_PRECONDITION` if you only run `create`; always run `tags bindings delete` first, then `tags bindings create`.
- **Safe 3-Step Teardown Order**: Always output all 3 commands in order when deleting a boundary and capability config (noting that BYO projects are preserved with `isManagementProject=false`, while Google-managed hubs are deleted):
  ```bash
  gcloud resource-manager capability-configs update CAPABILITY_CONFIG_ID --folder=FOLDER_ID --clear-boundaries
  gcloud resource-manager boundaries delete BOUNDARY_ID --folder=FOLDER_ID
  gcloud resource-manager capability-configs delete CAPABILITY_CONFIG_ID --folder=FOLDER_ID
  ```

---

## Advanced Filtering & Search

### Filtering (`list --filter`)

- **URN Substring Filtering (`agentId` & `mcpServerId`)**:
  - `agentId`: `urn:agent:projects-{project-number}:projects:{project-number}:locations:{location}:{platform-segments}`
  - `mcpServerId`: `urn:mcp:projects-{project-number}:projects:{project-number}:locations:{location}:{platform-segments}`
  - Platform segments: `aiplatform:reasoningEngines:{id}` (Vertex AI Reasoning Engine), `container:clusters:{cluster}:k8s:namespaces:{ns}:apps:deployments:{deploy}` (GKE), `run:services:{svc}` or `run:jobs:{job}` (Cloud Run).
- **Attribute Mapping**:
  - **"runtime"** ("agent engine", "reasoning engine", "vertex ai" -> `reasoningEngine`): `attributes."agentregistry.googleapis.com/system/RuntimeReference".uri`
  - **"identity"**: `attributes."agentregistry.googleapis.com/system/RuntimeIdentity".principal`
  - **"tool" / "tool name"** (on `mcp-servers list`): `tools.name`

```bash
# Filter agents by runtime (Vertex AI Reasoning Engine) or identity principal
gcloud agent-registry agents list --location=us-central1 \
  --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri:reasoningEngine"
gcloud agent-registry agents list --location=us-central1 \
  --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeIdentity\".principal:service-123456789012"

# Filter by agentId / mcpServerId substring or MCP tool name
gcloud agent-registry agents list --location=us-central1 --filter="agentId:reason"
gcloud agent-registry mcp-servers list --location=us-central1 --filter="mcpServerId:run"
gcloud agent-registry mcp-servers list --location=us-central1 --filter="tools.name:search_documents"
```

### Searching Agents, MCP Servers, and Skills (`search`)

- **Agents (`gcloud agent-registry agents search`)**: Supports `--search-string` with exact (`=`), token (`:`), and prefix (`*`) matching across `agentId`, `displayName`, `skills.name`, `skills.id`, `skills.tags`, `skills.description`, and boolean `OR`/`AND`. **Note:** Values with colons (URNs) must be quoted, and wildcard `*` is **not** supported on `skills.description` (use token match `:` instead).
- **MCP Servers (`gcloud agent-registry mcp-servers search`)**: Supports `--search-string` across `mcpServerId`, `name`, and `displayName`.
- **Skills (`gcloud agent-registry skills search`)**: Supports `--query` and `--search-type=keyword` or `--search-type=semantic` in `global`, `us`, or `eu`.

```bash
# Search Agents
gcloud agent-registry agents search --location=us-central1 --search-string="agentId:\"urn:agent:projects-123456789012*\""
gcloud agent-registry agents search --location=us-central1 --search-string="displayName:MyAgent*"
gcloud agent-registry agents search --location=us-central1 --search-string="skills.name:translation"
gcloud agent-registry agents search --location=us-central1 --search-string="skills.id:translate-text"
gcloud agent-registry agents search --location=us-central1 --search-string="skills.tags:productivity"
gcloud agent-registry agents search --location=us-central1 --search-string="skills.description:database"
gcloud agent-registry agents search --location=us-central1 --search-string="analytics OR reporting"

# Search MCP Servers
gcloud agent-registry mcp-servers search --location=us-central1 --search-string="mcpServerId:\"urn:mcp:projects-123456789012*\""
gcloud agent-registry mcp-servers search --location=us-central1 --search-string="displayName:MyMcp*"

# Search Skills (Keyword and Semantic)
gcloud agent-registry skills search --location=us --query="sql" --search-type=keyword
gcloud agent-registry skills search --location=us --query="summarize support tickets" --search-type=semantic
```

---

## Python ADK Integration

Whenever the user asks to discover or connect to registered Agents (`get_remote_a2a_agent`) or MCP Servers (`get_mcp_toolset`) in Python using Google's Agent Development Kit (`google-adk[a2a,agent-identity,mcp]`), read and follow [ADK Integration Guide](references/adk-docs.md).

---

## Documentation Fallback (`developerknowledge` MCP Server)

For CLI synopses, read [gcloud Command Reference](references/gcloud-command.md). If a user asks about a feature, Terraform resource (`google_agent_registry_service`), or error not covered in `SKILL.md` or `references/`, query the `developerknowledge` MCP server (`search_documents` + `get_documents`, or `answer_query`) or fetch the public `.md.txt` documentation pages:
- `https://docs.cloud.google.com/agent-registry/overview.md.txt`
- `https://docs.cloud.google.com/agent-registry/automatic-registration.md.txt`
- `https://docs.cloud.google.com/agent-registry/manual-registration.md.txt`
- `https://docs.cloud.google.com/agent-registry/register-agents.md.txt`
- `https://docs.cloud.google.com/agent-registry/register-mcp-servers.md.txt`
- `https://docs.cloud.google.com/agent-registry/register-endpoints.md.txt`
- `https://docs.cloud.google.com/agent-registry/register-skills.md.txt`
- `https://docs.cloud.google.com/agent-registry/manage-skills.md.txt`
- `https://docs.cloud.google.com/agent-registry/skills-architecture.md.txt`
- `https://docs.cloud.google.com/agent-registry/scan-skills.md.txt`
- `https://docs.cloud.google.com/agent-registry/boundaries-and-topology.md.txt`
- `https://docs.cloud.google.com/agent-registry/access-control.md.txt`
- `https://docs.cloud.google.com/agent-registry/roles-permissions.md.txt`
- `https://docs.cloud.google.com/agent-registry/a2a-protocol.md.txt`
- `https://docs.cloud.google.com/agent-registry/resolve-endpoints-and-build-orchestrators.md.txt`
- `https://docs.cloud.google.com/agent-registry/search-agents-and-tools.md.txt`
- `https://docs.cloud.google.com/agent-registry/identity-and-identifiers.md.txt`
- `https://docs.cloud.google.com/agent-registry/troubleshooting.md.txt`
- `https://docs.cloud.google.com/run/docs/ai/agent-platform-features.md.txt`

## Error Handling

1. Verify Cloud SDK version (**560.0.0+**, updated for GA `skills`) and `beta` component (**2026.03.09+** for Cloud Run).
2. Verify `--location` / `--region`: Google Cloud remote MCP servers are discovered in `global`; Skills only support `global`, `us`, or `eu`.
3. Ensure JSON strings passed to `--interfaces`, `--agent-spec-content`, or `--mcp-server-spec-content` are properly single-quoted for the shell.
4. Confirm required APIs (`agentregistry.googleapis.com`, `run.googleapis.com`, `apphub.googleapis.com`) and IAM roles are enabled on the target project.
