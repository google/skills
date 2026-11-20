# Management Boundary Setup (Admin Governance)

## Table of Contents

- [Resource Model Overview](#resource-model-overview): Lines 21-29
- [Required IAM Roles & Permissions for Boundary Setup](#required-iam-roles-permissions-for-boundary-setup): Lines 30-55
- [Interactive Scoping Questions for Admins](#interactive-scoping-questions-for-admins): Lines 56-95
- [Best Practices & Architectural Guardrails](#best-practices-architectural-guardrails): Lines 96-152
- [Step-by-Step Boundary Provisioning Workflow](#step-by-step-boundary-provisioning-workflow): Lines 153-280
- [Safe Teardown Sequence](#safe-teardown-sequence): Lines 281-302

---

Agent Registry administrators use Cloud Resource Manager (`BoundaryConfig`,
`CapabilityConfig`, `Boundary`, and Tag Bindings) to configure hub-and-spoke
governance perimeters across a Google Cloud Folder or Organization. When member
(spoke) projects match a boundary's tag filter, Agent Registry automatically
discovers runtime agents and MCP servers deployed across those member projects
and aggregates them into the designated Management Project (hub) catalog.

## Resource Model Overview

| Resource | CLI Command Group | Purpose |
|----------|-------------------|---------|
| **`BoundaryConfig`** | `gcloud resource-manager boundary-configs` | Singleton resource on a Folder or Organization node (`folders/{id}/boundaryConfig` or `organizations/{id}/boundaryConfig`) that specifies the single partitioning `tagKey` (e.g., `222222222222/environment`) used by all boundaries under that node. |
| **`CapabilityConfig`** | `gcloud resource-manager capability-configs` | Designates a Management Project (hub) under the Folder or Organization, enables `--types=agent-management` (or `agent-management,app-management`), and associates one or more `Boundary` resources. |
| **`Boundary`** | `gcloud resource-manager boundaries` | Logical perimeter under a Folder or Organization that selects child projects matching a specific tag value (`--tag-key` and `--tag-value`) and links to a `CapabilityConfig`. |
| **Tag Bindings** | `gcloud resource-manager tags bindings` | Enrolls the Management Project and Member (Spoke) Projects into a boundary perimeter by binding the corresponding tag value (e.g., `222222222222/environment/dev`). |

## Required IAM Roles & Permissions for Boundary Setup

Before running boundary provisioning commands, verify that the administrator
holds the required IAM roles on the appropriate hierarchy nodes:

| Role | Where to Grant (Target Resource) | Underlying Permissions | Purpose |
|------|----------------------------------|------------------------|---------|
| **`roles/resourcemanager.editor`** *(Resource Manager Editor)* | **Parent Folder or Organization** (`folders/FOLDER_ID` or `organizations/ORG_ID`) | • `resourcemanager.capabilityConfigs.{create,get,update,delete,list}`<br>• `resourcemanager.boundaries.{create,get,update,delete,list,associateToCapabilityConfig}`<br>• `resourcemanager.boundaryConfigs.{get,update}`<br>• `resourcemanager.boundaryMembers.{get,list}` | Create, update, link, and delete `CapabilityConfig`, `Boundary`, and singleton `BoundaryConfig` resources under the folder/org. *(Note: There is no dedicated curated `boundaryAdmin` role; these permissions ship inside `roles/resourcemanager.editor` or a Custom Role.)* |
| **`roles/resourcemanager.viewer`** *(Resource Manager Viewer)* | **Parent Folder or Organization** (`folders/FOLDER_ID` or `organizations/ORG_ID`) | • `resourcemanager.capabilityConfigs.{get,list}`<br>• `resourcemanager.boundaries.{get,list}`<br>• `resourcemanager.boundaryConfigs.get`<br>• `resourcemanager.boundaryMembers.{get,list}` | Read-only inspection of boundary configurations, capability configs, boundaries, and effective boundary members. |
| **`roles/owner`** or **`roles/editor`** *(Project Owner / Editor)* | **Candidate Bring-Your-Own Management Project** (`projects/PROJECT_NUMBER`) | • `resourcemanager.projects.associateToCapabilityConfig` | Required on an existing project when designating it as a Management Project via `--management-project=projects/<PROJECT_NUMBER>` on `capability-configs create`. (Not needed if Cloud Resource Manager auto-provisions a Google-managed project.) |
| **`roles/resourcemanager.tagUser`** *(Tag User)* | **Both the Tag Value AND each Target Project** (Hub + Member Spoke Projects) | • `resourcemanager.tagValues.use`<br>• `resourcemanager.tagValueBindings.{create,delete}` | Required to attach or detach environment/perimeter tag bindings (`gcloud resource-manager tags bindings create/delete`) on projects. *(Creating new Tag Keys/Values requires `roles/resourcemanager.tagAdmin` on the Organization.)* |
| **`roles/agentregistry.admin`** / **`roles/agentregistry.viewer`** | **Management Project (Hub)** (`projects/MGMT_PROJECT_ID`) | • `agentregistry.*` | `roles/agentregistry.admin` to centrally register `Services` and `Bindings` on the hub; `roles/agentregistry.viewer` to query (`list`, `describe`, `search`) the aggregated agent, MCP server, and skill catalog across the boundary. |

> **Custom Role & IAM Notes:**
> - All `resourcemanager.capabilityConfigs.*`, `resourcemanager.boundaries.*`,
>   and `resourcemanager.boundaryConfigs.*` permissions support **IAM Custom
>   Roles** and **IAM Deny** policies (`create` and `list` are checked as
>   `parents_only` on the Folder or Organization).
> - The permission resource noun for the singleton `boundaryConfig` is plural
>   (`resourcemanager.boundaryConfigs.get` and
>   `resourcemanager.boundaryConfigs.update`).
> - Attaching a `Boundary` to a `CapabilityConfig` (`capability-configs update
>   --boundaries=...`) checks both `resourcemanager.capabilityConfigs.update`
>   and `resourcemanager.boundaries.associateToCapabilityConfig` on the parent
>   node.

## Interactive Scoping Questions for Admins

When an administrator asks to set up a Management Boundary or
`CapabilityConfig` (or asks what information you need and what best practices
to follow), **always present all 6 scoping questions and all best practices
below in a single response** (skipping only details they have already provided)
before constructing mutating commands:

1. **Parent Hierarchy Node (Folder vs. Organization)**:
   _"Which Folder ID (`--folder=FOLDER_ID`) or Organization ID
   (`--organization=ORG_ID`) will anchor the boundary and management
   project(s)?"_
   *(Note: A `CapabilityConfig`, its Management Project, and all associated
   `Boundary` resources must share the exact same parent node.)*
2. **Perimeter Partitioning & Tag Key Strategy**:
   _"How do you want to partition projects under this node? Do you want
   multiple isolated perimeters using an Organization Tag Key (for example,
   `<ORG_ID>/environment` with values like `dev` and `prod`, or partitioning by
   business unit), or a single catch-all boundary covering all child
   projects?"_
3. **Catalog & IAM Isolation (`1 Hub per Perimeter` vs. `Shared Hub`)**:
   _"If you have multiple perimeters (such as `dev` and `prod`), do you want
   **strict catalog and IAM isolation** with a dedicated Management Project and
   `CapabilityConfig` per perimeter (recommended so `prod` agents never appear
   in `dev` queries and vice versa), or should multiple boundaries roll up into
   a single shared Management Project?"_
4. **Management Project Selection (Bring-Your-Own vs. Google-Managed)**:
   _"Do you want to designate existing project(s) under that parent node as
   your Management Project(s)
   (`--management-project=projects/<PROJECT_NUMBER>`), or have Cloud Resource
   Manager auto-provision a new Google-managed Management Project (by omitting
   `--management-project`)?"_
5. **Capability Types (`agent-management` vs. Shared with App Hub)**:
   _"Should the `CapabilityConfig` enable `agent-management` only, or both
   `agent-management,app-management` (to share the Management Project with App
   Hub)?"_
6. **Member (Spoke) Projects**:
   _"Which project IDs or project numbers should be enrolled into each boundary
   perimeter via tag bindings?"_

## Best Practices & Architectural Guardrails

Always share relevant best practices with the administrator as you guide them
through setup:

- **Set `BoundaryConfig` Tag Key Before Attaching Boundaries**: Configure the
  partitioning `tagKey` (`gcloud resource-manager boundary-configs update`)
  *before* creating and attaching boundaries. Once any boundary under the node
  is attached to a `CapabilityConfig`, Cloud Resource Manager locks `tagKey` on
  that node (requiring all boundaries to be detached before `tagKey` can be
  changed). If `tagKey` is left unset, the node supports at most one
  filter-less boundary that matches every child project under the node.
- **Use Separate `CapabilityConfig` + Management Project for Strict `dev`/`prod`
  Isolation**: Every boundary attached to the same `CapabilityConfig` merges
  its discovered agents and MCP servers into one Management Project catalog.
  There is no `--boundary` filter on `gcloud agent-registry` queries, and
  granting `roles/agentregistry.viewer` on a Management Project exposes assets
  from all boundaries attached to it. To guarantee zero cross-perimeter leakage
  between environments (e.g., `dev` vs. `prod`), create a separate
  `CapabilityConfig`, Management Project, and `Boundary` for each environment.
- **Always Use Project Numbers (`projects/<PROJECT_NUMBER>`)**: Cloud Resource
  Manager v3 requires project **numbers** (not project IDs) for
  `--management-project=projects/<PROJECT_NUMBER>` on `capability-configs
  create` and `--parent=//cloudresourcemanager.googleapis.com/projects/<PROJECT_NUMBER>`
  on `tags bindings create`. Whenever a user provides a project ID for
  `--management-project`, always output **both** the lookup command below
  **and** the complete `gcloud resource-manager capability-configs create`
  command template using `--management-project=projects/<PROJECT_NUMBER>`
  (defaulting `--types=agent-management` when not specified) in the same
  response:
  ```bash
  gcloud projects describe PROJECT_ID --format="value(projectNumber)"
  ```
- **Tag Binding Updates Require Delete-Then-Create**: Whenever a user asks to
  move a project from one boundary/tag value to another (e.g., `dev` to
  `prod`), always explicitly warn them that GCP Tags allow at most one value
  per tag key on a resource (`tags bindings create` does not overwrite an
  existing binding and fails with `FAILED_PRECONDITION` if another value under
  the same tag key is already bound), and then provide the `tags bindings
  delete` followed by `tags bindings create` commands. Tag changes take ~2–7
  minutes to fully propagate.
- **Resource ID & Display Name Constraints**: `capability_config_id` and
  `boundary_id` must be 6–30 lowercase ASCII letters, digits, or hyphens, must
  start with a letter, and cannot end with a hyphen. `--display-name` must be
  4–30 characters.
- **Centralize Manual Registrations in the Hub (Spoke Governance)**: Automatic
  runtime discovery (e.g., Vertex AI Agent Engine / Reasoning Engine and GKE
  agents/MCP servers) works across spoke member projects even when
  `agentregistry.googleapis.com` is disabled on the spoke projects. However,
  user-defined `Services` (`gcloud agent-registry services create`) and
  `Bindings` created locally in a spoke project stay isolated to that spoke and
  **do not roll up** to the Management Project. Register third-party MCP
  servers, custom agents, endpoints, and bindings centrally in the Management
  Project, and consider disabling `agentregistry.googleapis.com` (or
  restricting `services.*` and `bindings.*` write permissions via IAM Deny /
  Org Policy `gcp.restrictServiceUsage`) on spoke workload projects.

## Step-by-Step Boundary Provisioning Workflow

Below is the canonical end-to-end setup workflow (modeling a folder
`111111111111` in organization `222222222222` partitioned by tag key
`222222222222/environment` into isolated `dev` and `prod` management
perimeters):

**Step 1: Configure Folder/Org `BoundaryConfig` and Bind Tags to Projects**
```bash
# 1a. Inspect current BoundaryConfig on the folder (or --organization=ORG_ID)
gcloud resource-manager boundary-configs describe --folder=111111111111

# 1b. Configure folder BoundaryConfig with the organization environment tag key
gcloud resource-manager boundary-configs update \
  --folder=111111111111 \
  --tag-key="222222222222/environment"

# 1c. Bind environment=dev to the dev management hub and dev spoke projects (using project numbers)
for pnum in 123456789012 333333333333 444444444444; do
  gcloud resource-manager tags bindings create \
    --tag-value=222222222222/environment/dev \
    --parent=//cloudresourcemanager.googleapis.com/projects/$pnum
done

# 1d. Bind environment=prod to the prod management hub and prod spoke projects (using project numbers)
for pnum in 555555555555 666666666666 777777777777; do
  gcloud resource-manager tags bindings create \
    --tag-value=222222222222/environment/prod \
    --parent=//cloudresourcemanager.googleapis.com/projects/$pnum
done
```

**Step 2: Create `CapabilityConfig` Resources (Designate Management Projects)**
```bash
# Create folder-scoped CapabilityConfig for the dev management project
gcloud resource-manager capability-configs create agent-governance \
  --folder=111111111111 \
  --display-name="Agent Governance Capability" \
  --types=agent-management \
  --management-project=projects/123456789012

# Create folder-scoped CapabilityConfig for the prod management project
gcloud resource-manager capability-configs create agent-governance-prod \
  --folder=111111111111 \
  --display-name="Agent Governance Capability" \
  --types=agent-management \
  --management-project=projects/555555555555
```

**Step 3: Create `Boundary` Resources**
```bash
# Create dev and prod Boundaries on the parent folder
gcloud resource-manager boundaries create agents-dev \
  --folder=111111111111 \
  --display-name="Agent Dev Boundary" \
  --tag-key="222222222222/environment" \
  --tag-value="dev"

gcloud resource-manager boundaries create agents-prod \
  --folder=111111111111 \
  --display-name="Agent Prod Boundary" \
  --tag-key="222222222222/environment" \
  --tag-value="prod"
```

**Step 4: Associate Each `Boundary` with Its `CapabilityConfig`**
```bash
# Associate agents-dev boundary with the dev CapabilityConfig
gcloud resource-manager capability-configs update agent-governance \
  --folder=111111111111 \
  --boundaries=folders/111111111111/boundaries/agents-dev

# Associate agents-prod boundary with the prod CapabilityConfig
gcloud resource-manager capability-configs update agent-governance-prod \
  --folder=111111111111 \
  --boundaries=folders/111111111111/boundaries/agents-prod
```

**Step 5: Verify Cross-Project Rollup, Filtering, and Search on the Hub**
```bash
# List all discovered agents aggregated across member projects in the boundary
gcloud agent-registry agents list --project=MANAGEMENT_PROJECT_ID --location=us-central1

# Filter aggregated agents by runtime (Vertex AI Reasoning Engine) across all member projects
gcloud agent-registry agents list --project=MANAGEMENT_PROJECT_ID --location=us-central1 \
  --filter='attributes."agentregistry.googleapis.com/system/RuntimeReference".uri:reasoningEngine'

# Narrow aggregated agents to a specific spoke project number via agentId or RuntimeIdentity
gcloud agent-registry agents list --project=MANAGEMENT_PROJECT_ID --location=us-central1 \
  --filter="agentId:333333333333"

gcloud agent-registry agents list --project=MANAGEMENT_PROJECT_ID --location=us-central1 \
  --filter='attributes."agentregistry.googleapis.com/system/RuntimeIdentity".principal:service-444444444444'

# Search aggregated agents across spoke projects by displayName prefix, spoke URN prefix, or A2A skills
gcloud agent-registry agents search --project=MANAGEMENT_PROJECT_ID --location=us-central1 \
  --search-string="displayName:MyAgent*"

gcloud agent-registry agents search --project=MANAGEMENT_PROJECT_ID --location=us-central1 \
  --search-string='agentId:"urn:agent:projects-444444444444*"'

gcloud agent-registry agents search --project=MANAGEMENT_PROJECT_ID --location=us-central1 \
  --search-string="skills.tags:productivity"
```

**Step 6: Audit or Reassign Projects Between Boundaries**
```bash
# List and describe CapabilityConfigs and Boundaries under a folder
gcloud resource-manager capability-configs list --folder=111111111111
gcloud resource-manager capability-configs describe agent-governance --folder=111111111111
gcloud resource-manager boundaries list --folder=111111111111
gcloud resource-manager boundaries describe agents-dev --folder=111111111111

# Audit all Agent Registry management projects across the organization
gcloud projects list \
  --filter="isManagementProject=true" \
  --format="table(projectId, projectNumber, parent.id, configuredCapabilities)"

# Move a member project from dev to prod (delete old binding first, then create new binding)
gcloud resource-manager tags bindings delete \
  --tag-value=222222222222/environment/dev \
  --parent=//cloudresourcemanager.googleapis.com/projects/333333333333

gcloud resource-manager tags bindings create \
  --tag-value=222222222222/environment/prod \
  --parent=//cloudresourcemanager.googleapis.com/projects/333333333333
```

## Safe Teardown Sequence

Cloud Resource Manager blocks deleting an attached `Boundary` or a
`CapabilityConfig` with attached boundaries. Whenever a user asks to delete or
tear down a boundary and capability config, **always output the complete
3-command `gcloud` teardown sequence in order**, and explicitly note that
deleting a `CapabilityConfig` preserves a Bring-Your-Own (BYO) project
(`isManagementProject` reverts to `false`), whereas a Google-managed Management
Project is deleted:

```bash
# 1. Detach boundaries from the CapabilityConfig
gcloud resource-manager capability-configs update agent-governance \
  --folder=111111111111 \
  --clear-boundaries

# 2. Delete the Boundary
gcloud resource-manager boundaries delete agents-dev --folder=111111111111

# 3. Delete the CapabilityConfig
gcloud resource-manager capability-configs delete agent-governance --folder=111111111111
```
