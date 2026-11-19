# `gcloud agent-registry` & Related CLI Command Reference

## Table of Contents

- [Main Command: `gcloud agent-registry`](#main-command-gcloud-agent-registry): Lines 31-75
- [Subcommands](#subcommands): Lines 79-485
  - [`agents`](#agents): Lines 81-123
  - [`bindings`](#bindings): Lines 125-149
  - [`endpoints`](#endpoints): Lines 151-166
  - [`findings`](#findings): Lines 168-177
  - [`mcp-servers`](#mcp-servers): Lines 179-216
  - [`operations`](#operations): Lines 218-226
  - [`publishers`](#publishers): Lines 228-237
  - [`services`](#services): Lines 239-263
  - [`skills`](#skills): Lines 267-385
  - [`ai-applications`](#ai-applications): Lines 389-485
- [Cloud Resource Manager: Management Boundary Commands](#cloud-resource-manager-management-boundary-commands): Lines 489-538
  - [`boundary-configs`](#boundary-configs): Lines 491-502
  - [`capability-configs`](#capability-configs): Lines 504-525
  - [`boundaries`](#boundaries): Lines 527-538
- [Cloud Run: Agent Registry Automatic Registration Flags (`gcloud beta run`)](#cloud-run-agent-registry-automatic-registration-flags-gcloud-beta-run): Lines 542-582
- [Command Summary & Flag Reference Tables](#command-summary-flag-reference-tables): Lines 586-639
- [Natural Language to Command Examples](#natural-language-to-command-examples): Lines 643-711

---

Documentation for `gcloud agent-registry` (GA), `gcloud resource-manager`
(Management Boundaries), and `gcloud beta run` (Cloud Run automatic
registration).

## Main Command: `gcloud agent-registry`

```text
NAME
    gcloud agent-registry - manage Agent Registry resources

SYNOPSIS
    gcloud agent-registry GROUP [GCLOUD_WIDE_FLAG ...]

DESCRIPTION
    Manage Agent Registry resources.

GROUPS
    GROUP is one of the following:

     agents
        Manage Agent resources.

     ai-applications
        Manage Ai Application resources.

     bindings
        Manage Binding resources.

     endpoints
        Manage Endpoint resources.

     findings
        Manage Finding resources.

     mcp-servers
        Manage Mcp Server resources.

     operations
        Manage Operation resources.

     publishers
        Manage Publisher resources.

     services
        Manage Service resources.

     skills
        Manage Skill resources.
```

---

## Subcommands

### `agents`

```text
NAME
    gcloud agent-registry agents - manage Agent resources

SYNOPSIS
    gcloud agent-registry agents COMMAND [GCLOUD_WIDE_FLAG ...]

COMMANDS
     describe
        Describe agents.

     list
        List agents.

     search
        Search agents.
```

#### `agents search`

```text
SYNOPSIS
    gcloud agent-registry agents search --location=LOCATION
        [--search-string=SEARCH_STRING] [--search-type=SEARCH_TYPE]
        [GCLOUD_WIDE_FLAG ...]

REQUIRED FLAGS
     --location=LOCATION
        ID of the location or fully qualified identifier for the location.

OPTIONAL FLAGS
     --search-string=SEARCH_STRING
        Search criteria used to select the Agents to return.
        Search expressions can be used to restrict results based upon skills,
        agentId, description, name, displayName, and trust, where the operators
        =, :, NOT, AND, and OR can be used along with the suffix wildcard *.
        Note: Wildcard * is NOT supported on skills.description (use token match :).

     --search-type=SEARCH_TYPE
        The type of search. If set, must be set to keyword.
```

### `bindings`

```text
NAME
    gcloud agent-registry bindings - manage Binding resources

SYNOPSIS
    gcloud agent-registry bindings COMMAND [GCLOUD_WIDE_FLAG ...]

COMMANDS
     create
        Create bindings.

     delete
        Delete bindings.

     describe
        Describe bindings.

     list
        List bindings.

     update
        Update bindings.
```

### `endpoints`

```text
NAME
    gcloud agent-registry endpoints - manage Endpoint resources

SYNOPSIS
    gcloud agent-registry endpoints COMMAND [GCLOUD_WIDE_FLAG ...]

COMMANDS
     describe
        Describe endpoints.

     list
        List endpoints.
```

### `findings`

```text
NAME
    gcloud agent-registry findings - manage Finding resources

SYNOPSIS
    gcloud agent-registry findings (list | describe) --location=LOCATION
        [--filter=EXPRESSION] [GCLOUD_WIDE_FLAG ...]
```

### `mcp-servers`

```text
NAME
    gcloud agent-registry mcp-servers - manage Mcp Server resources

SYNOPSIS
    gcloud agent-registry mcp-servers COMMAND [GCLOUD_WIDE_FLAG ...]

COMMANDS
     describe
        Describe mcpServers.

     list
        List mcpServers.

     search
        Search mcpServers.
```

#### `mcp-servers search`

```text
SYNOPSIS
    gcloud agent-registry mcp-servers search --location=LOCATION
        [--search-string=SEARCH_STRING] [--search-type=SEARCH_TYPE]
        [GCLOUD_WIDE_FLAG ...]

REQUIRED FLAGS
     --location=LOCATION
        ID of the location or fully qualified identifier for the location.

OPTIONAL FLAGS
     --search-string=SEARCH_STRING
        Search expressions can be used to restrict results based upon
        mcpServerId, name, and displayName, where the operators =, :, NOT, AND,
        and OR can be used along with the suffix wildcard symbol *.
```

### `operations`

```text
NAME
    gcloud agent-registry operations - manage Operation resources

SYNOPSIS
    gcloud agent-registry operations (list | describe) [GCLOUD_WIDE_FLAG ...]
```

### `publishers`

```text
NAME
    gcloud agent-registry publishers - manage Publisher resources

SYNOPSIS
    gcloud agent-registry publishers (list | describe) --location=LOCATION
        [GCLOUD_WIDE_FLAG ...]
```

### `services`

```text
NAME
    gcloud agent-registry services - manage Service resources

SYNOPSIS
    gcloud agent-registry services COMMAND [GCLOUD_WIDE_FLAG ...]

COMMANDS
     create
        Create services (projects read-only Agent, McpServer, or Endpoint catalog entries: agentregistry-{ID}).

     delete
        Delete services.

     describe
        Describe services (includes registryResource showing the projected agentregistry-{ID} resource name).

     list
        List services.

     update
        Update services.
```

---

### `skills`

```text
NAME
    gcloud agent-registry skills - manage Skill resources

SYNOPSIS
    gcloud agent-registry skills GROUP | COMMAND [GCLOUD_WIDE_FLAG ...]

GROUPS
     revisions
        Manage Skill Revision resources.

COMMANDS
     add-iam-policy-binding
        Add IAM policy binding for a skill.

     create
        Create skills.

     delete
        Delete skills.

     describe
        Describe skills.

     get-iam-policy
        Get the IAM policy for a skill.

     list
        List skills.

     remove-iam-policy-binding
        Remove IAM policy binding from a skill.

     search
        Search skills.

     set-iam-policy
        Set the IAM policy for a skill.

     update
        Update skills.
```

#### `skills create`

```text
SYNOPSIS
    gcloud agent-registry skills create SKILL [--async]
        [--default-revision=DEFAULT_REVISION] [--description=DESCRIPTION]
        [--display-name=DISPLAY_NAME] [--location=LOCATION]
        [--publisher=PUBLISHER] [--request-id=REQUEST_ID]
        [--scanning-policy=SCANNING_POLICY] [--target-state=TARGET_STATE]
        [--type=TYPE]
        [--initial-revision-name=INITIAL_REVISION_NAME --payload=PAYLOAD
          | [--gcs-source-uri=GCS_SOURCE_URI
          : --gcs-source-generation=GCS_SOURCE_GENERATION]]
        [GCLOUD_WIDE_FLAG ...]

NOTES
    - Supported locations: global, us, and eu only.
    - Automatic 'private-' prefix: Running 'skills create my-skill' creates
      'skills/private-my-skill'. Subsequent describe, update, delete,
      revisions, and *-iam-policy commands must pass 'private-my-skill'.
    - Target state & scanning: --target-state accepts active, disabled, or
      draft on create ('active' requires an initial revision via --payload or
      --gcs-source-uri; deprecated and decommissioned are also accepted on
      update). Under the default 'enabled-blocking' scanning policy,
      '--target-state=active' enters DRAFT until the security scan completes
      with no findings.
    - Cloud Storage source: When passing --gcs-source-uri, grant
      'storage.objects.get' on the bucket to the Agent Registry service agent
      ('service-PROJECT_NUMBER@gcp-sa-agentregistry.iam.gserviceaccount.com').
```

#### `skills search`

```text
SYNOPSIS
    gcloud agent-registry skills search --location=LOCATION
        [--query=QUERY] [--search-type=SEARCH_TYPE] [--filter=EXPRESSION]
        [--limit=LIMIT] [--page-size=PAGE_SIZE] [--sort-by=[FIELD,...]]
        [GCLOUD_WIDE_FLAG ...]
```

#### `skills revisions`

```text
SYNOPSIS
    gcloud agent-registry skills revisions (create | delete | describe | list)
        --skill=SKILL --location=LOCATION [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry skills revisions download
        (REVISION : --location=LOCATION --skill=SKILL)
        --destination=DESTINATION [--allow-overwrite] [GCLOUD_WIDE_FLAG ...]
```

#### `skills` Resource-Level IAM Commands

```text
SYNOPSIS
    gcloud agent-registry skills get-iam-policy (SKILL : --location=LOCATION)
        [--filter=EXPRESSION] [--limit=LIMIT] [--page-size=PAGE_SIZE]
        [--sort-by=[FIELD,...]] [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry skills set-iam-policy (SKILL : --location=LOCATION)
        POLICY_FILE [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry skills add-iam-policy-binding
        (SKILL : --location=LOCATION) --member=PRINCIPAL --role=ROLE
        [--condition=[KEY=VALUE,...] | --condition-from-file=PATH_TO_FILE]
        [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry skills remove-iam-policy-binding
        (SKILL : --location=LOCATION) --member=PRINCIPAL --role=ROLE
        [--all | --condition=[KEY=VALUE,...]
          | --condition-from-file=PATH_TO_FILE] [GCLOUD_WIDE_FLAG ...]
```

---

### `ai-applications`

```text
NAME
    gcloud agent-registry ai-applications - manage Ai Application resources

SYNOPSIS
    gcloud agent-registry ai-applications GROUP | COMMAND [GCLOUD_WIDE_FLAG ...]

GROUPS
     agents
        Manage Agent resources scoped to an AI Application.

     endpoints
        Manage Endpoint resources scoped to an AI Application.

     mcp-servers
        Manage Mcp Server resources scoped to an AI Application.

COMMANDS
     add-iam-policy-binding
     create
     delete
     describe
     get-iam-policy
     list
     remove-iam-policy-binding
     search
     set-iam-policy
     update
```

#### `ai-applications` CRUD & IAM Commands

```text
SYNOPSIS
    gcloud agent-registry ai-applications list --location=LOCATION
        [--filter=EXPRESSION] [--limit=LIMIT] [--page-size=PAGE_SIZE]
        [--sort-by=[FIELD,...]] [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications describe
        (AI_APPLICATION : --location=LOCATION) [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications search --location=LOCATION
        [--search-string=SEARCH_STRING] [--filter=EXPRESSION]
        [--limit=LIMIT] [--page-size=PAGE_SIZE] [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications create
        (AI_APPLICATION : --location=LOCATION) [--async]
        [--description=DESCRIPTION] [--display-name=DISPLAY_NAME]
        [--environment-type=ENVIRONMENT_TYPE]
        [--criticality-type=CRITICALITY_TYPE]
        [--business-owners=[email=EMAIL,...]]
        [--developer-owners=[email=EMAIL,...]]
        [--operator-owners=[email=EMAIL,...]]
        [--labels=[KEY=VALUE,...]] [--members=[MEMBERS,...]]
        [--request-id=REQUEST_ID] [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications update
        (AI_APPLICATION : --location=LOCATION) [--async]
        [--description=DESCRIPTION] [--display-name=DISPLAY_NAME]
        [--environment-type=ENVIRONMENT_TYPE]
        [--criticality-type=CRITICALITY_TYPE]
        [--labels=[KEY=VALUE,...]] [--members=[MEMBERS,...]]
        [--request-id=REQUEST_ID] [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications delete
        (AI_APPLICATION : --location=LOCATION) [--async] [--etag=ETAG]
        [--force] [--request-id=REQUEST_ID] [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications get-iam-policy
        (AI_APPLICATION : --location=LOCATION) [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications set-iam-policy
        (AI_APPLICATION : --location=LOCATION) POLICY_FILE [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications add-iam-policy-binding
        (AI_APPLICATION : --location=LOCATION) --member=PRINCIPAL --role=ROLE
        [--condition=[KEY=VALUE,...] | --condition-from-file=PATH_TO_FILE]
        [GCLOUD_WIDE_FLAG ...]

    gcloud agent-registry ai-applications remove-iam-policy-binding
        (AI_APPLICATION : --location=LOCATION) --member=PRINCIPAL --role=ROLE
        [--all | --condition=[KEY=VALUE,...]
          | --condition-from-file=PATH_TO_FILE] [GCLOUD_WIDE_FLAG ...]
```

#### `ai-applications` Subgroups (`agents`, `mcp-servers`, `endpoints`)

```text
SYNOPSIS
    gcloud agent-registry ai-applications (agents | mcp-servers | endpoints)
        (list | describe | search)
        --ai-application=AI_APPLICATION --location=LOCATION
        [--search-string=SEARCH_STRING] [--filter=EXPRESSION]
        [GCLOUD_WIDE_FLAG ...]
```

---

## Cloud Resource Manager: Management Boundary Commands

### `boundary-configs`

```text
SYNOPSIS
    gcloud resource-manager boundary-configs describe
        (--folder=FOLDER_ID | --organization=ORGANIZATION_ID)

    gcloud resource-manager boundary-configs update
        (--clear-tag-key | --tag-key=TAG_KEY)
        (--folder=FOLDER_ID | --organization=ORGANIZATION_ID) [--async]
        [--etag=ETAG] [GCLOUD_WIDE_FLAG ...]
```

### `capability-configs`

```text
SYNOPSIS
    gcloud resource-manager capability-configs create
        (CAPABILITY_CONFIG
          : --folder=FOLDER --organization=ORGANIZATION --project=PROJECT)
        --types=[TYPES,...] [--async] [--boundaries=[BOUNDARIES,...]]
        [--display-name=DISPLAY_NAME] [--management-project=MANAGEMENT_PROJECT]
        [GCLOUD_WIDE_FLAG ...]

    gcloud resource-manager capability-configs update
        (CAPABILITY_CONFIG
          : --folder=FOLDER --organization=ORGANIZATION --project=PROJECT)
        [--async] [--display-name=DISPLAY_NAME] [--etag=ETAG]
        [--types=[TYPES,...]]
        [--boundaries=[BOUNDARIES,...] | --clear-boundaries]
        [GCLOUD_WIDE_FLAG ...]

    gcloud resource-manager capability-configs (list | describe | delete)
        (--folder=FOLDER | --organization=ORGANIZATION | --project=PROJECT)
```

### `boundaries`

```text
SYNOPSIS
    gcloud resource-manager boundaries create
        (BOUNDARY : --folder=FOLDER --organization=ORGANIZATION) [--async]
        [--display-name=DISPLAY_NAME] [--tag-key=TAG_KEY]
        [--tag-value=TAG_VALUE] [GCLOUD_WIDE_FLAG ...]

    gcloud resource-manager boundaries (list | describe | update | delete)
        (--folder=FOLDER | --organization=ORGANIZATION)
```

---

## Cloud Run: Agent Registry Automatic Registration Flags (`gcloud beta run`)

```text
SYNOPSIS
    gcloud beta run deploy [[SERVICE] --namespace=NAMESPACE]
        [--image=IMAGE_URL | --source=SOURCE] [--region=REGION]
        [--functional-type=FUNCTIONAL_TYPE] [--identity-type=IDENTITY_TYPE]
        [--[no-]identity-certificate] [GCLOUD_WIDE_FLAG ...]

    gcloud beta run services update [SERVICE] [--region=REGION]
        [--functional-type=FUNCTIONAL_TYPE] [--identity-type=IDENTITY_TYPE]
        [--[no-]identity-certificate] [--no-traffic] [GCLOUD_WIDE_FLAG ...]

    gcloud beta run jobs (create | deploy | update) [JOB] [--image=IMAGE_URL]
        [--region=REGION] [--functional-type=agent]
        [--identity-type=agent-identity] [--[no-]identity-certificate]
        [GCLOUD_WIDE_FLAG ...]

    gcloud beta run revisions describe REVISION_NAME [--region=REGION]
    gcloud beta run jobs executions describe EXECUTION_NAME [--region=REGION]

FLAGS
     --functional-type=FUNCTIONAL_TYPE
        Specifies the function of the resource for automatic registration in
        Agent Registry (sets annotation apphub.cloud.google.com/functional-type).
        Once configured on a resource, this property is immutable and cannot be
        changed or cleared.
        - Services support: agent, mcp-server
        - Jobs support: agent only

     --identity-type=IDENTITY_TYPE
        Configures the type of identity assigned to the resource. Once set,
        this property is immutable and cannot be changed or unset.
        - agent-identity: Assigns a SPIFFE agent identity (required when --functional-type=agent)
        - service-account: Uses a standard Google Cloud service account (default for mcp-server)

     --[no-]identity-certificate
        Enables automatic provisioning of identity certificates from the trust
        domain into the container environment (enabled by default when
        --identity-type=agent-identity). Use --no-identity-certificate to opt out.
```

---

## Command Summary & Flag Reference Tables

All `gcloud agent-registry` commands support `--location` (required) and
`--project` (optional). Cloud Run commands (`gcloud beta run`) use `--region`
(or `--project`). Cloud Resource Manager boundary governance commands (`gcloud
resource-manager`) are scoped to `--folder` or `--organization`.

| Group | Commands | CLI Track |
|-------|----------|-----------|
| `agents` | `list`, `describe`, `search` | GA (`gcloud agent-registry agents`) |
| `mcp-servers` | `list`, `describe`, `search` | GA (`gcloud agent-registry mcp-servers`) |
| `endpoints` | `list`, `describe` | GA (`gcloud agent-registry endpoints`) |
| `services` | `create`, `list`, `describe`, `update`, `delete` | GA (`gcloud agent-registry services`) |
| `bindings` | `create`, `list`, `describe`, `update`, `delete` | GA (`gcloud agent-registry bindings`) |
| `operations` | `list`, `describe` | GA (`gcloud agent-registry operations`) |
| `skills` | `create`, `list`, `describe`, `update`, `delete`, `search`, `get-iam-policy`, `set-iam-policy`, `add-iam-policy-binding`, `remove-iam-policy-binding` | GA (`gcloud agent-registry skills`) |
| `skills revisions` | `create`, `list`, `describe`, `delete`, `download` | GA (`gcloud agent-registry skills revisions`) |
| `findings` | `list`, `describe` | GA (`gcloud agent-registry findings`) |
| `publishers` | `list`, `describe` | GA (`gcloud agent-registry publishers`) |
| `ai-applications` | `list`, `describe`, `search`, `create`, `update`, `delete`, `get-iam-policy`, `set-iam-policy`, `add-iam-policy-binding`, `remove-iam-policy-binding` | GA (`gcloud agent-registry ai-applications`) |
| `ai-applications agents` | `list`, `describe`, `search` | GA (`gcloud agent-registry ai-applications agents`) |
| `ai-applications mcp-servers` | `list`, `describe`, `search` | GA (`gcloud agent-registry ai-applications mcp-servers`) |
| `ai-applications endpoints` | `list`, `describe`, `search` | GA (`gcloud agent-registry ai-applications endpoints`) |
| `run` (`deploy`, `services update`, `jobs`) | `deploy`, `services update`, `multi-region-services update`, `jobs create`, `jobs deploy`, `jobs update`, `revisions describe`, `jobs executions describe` | Beta (`gcloud beta run` with `--functional-type` & `--identity-type`) |
| `boundary-configs` | `describe`, `update` | GA (`gcloud resource-manager boundary-configs`) |
| `capability-configs` | `create`, `list`, `describe`, `update`, `delete` | GA (`gcloud resource-manager capability-configs`) |
| `boundaries` | `create`, `list`, `describe`, `update`, `delete` | GA (`gcloud resource-manager boundaries`) |
| `tags bindings` | `create`, `list`, `delete` | GA (`gcloud resource-manager tags bindings`) |

### Service Creation Flags (`gcloud agent-registry services create`)

Service IDs must be 4–63 characters (`^[a-z][a-z0-9-]{2,61}[a-z0-9]$`; suffix
3-letter GCP APIs such as `iam` -> `iam-api`). Downstream IAP egress policies
(`roles/iap.egressor`) bind to the projected `Endpoint` catalog ID
(`agentregistry-{UUID}`), not the `Service` ID.

| Flag | Description |
|------|-------------|
| `--display-name` | Human-readable name (up to 63 chars) |
| `--description` | Brief summary of the service |
| `--interfaces` | Repeated `protocolBinding=...,url=...` flags or JSON array of protocol bindings and URLs (supports composite multi-URL endpoints) |
| `--mcp-server-spec-type` | Type: `no-spec`, `tool-spec` |
| `--mcp-server-spec-content` | JSON content of the MCP tool spec |
| `--agent-spec-type` | Type: `no-spec`, `a2a-agent-card` |
| `--agent-spec-content` | JSON content for `a2a-agent-card` |
| `--endpoint-spec-type` | Type: `no-spec` |

### Cloud Run Automatic Registration Flags (`gcloud beta run`)

| Flag | Values | Description |
|------|--------|-------------|
| `--functional-type` | `agent`, `mcp-server` | Declares the workload's function for automatic registration in Agent Registry (sets `apphub.cloud.google.com/functional-type`). **Immutable once set.** Cloud Run jobs only support `agent`. |
| `--identity-type` | `agent-identity`, `service-account` | Configures the identity assigned to the Cloud Run resource. **Required as `agent-identity` when `--functional-type=agent`. Immutable once set.** |
| `--[no-]identity-certificate` | Boolean | Enabled by default when `--identity-type=agent-identity`. Pass `--no-identity-certificate` to opt out of automatic SPIFFE certificate provisioning. |

---

## Natural Language to Command Examples

| User says | Command |
|-----------|---------|
| "List my MCP servers" | `gcloud agent-registry mcp-servers list --location=us-central1` |
| "Configure this GKE deployment as an agent" | `./scripts/annotate_gke.py /path/to/folder_or_file.yaml --type AGENT` |
| "Make my deployments in this folder MCP Servers" | `./scripts/annotate_gke.py /path/to/folder_or_file.yaml --type MCP_SERVER` |
| "Show me a GKE manifest for an MCP server in Agent Registry" | Provide `Deployment` YAML with `registry.gke.io/functional-type: "MCP_SERVER"`, `modelcontextprotocol.info/urls`, `modelcontextprotocol.info/capabilities`, and `iam.gke.io/spiffe-identity-type: agent-identity` |
| "Show me a GKE manifest for an A2A agent in Agent Registry" | Provide `Deployment` + `Service` YAML with `registry.gke.io/functional-type: "AGENT"`, `a2a-protocol.org/agent-card`, and `iam.gke.io/spiffe-identity-type: agent-identity` |
| "Deploy a Cloud Run service my-agent as an agent in us-central1" | `gcloud beta run deploy my-agent --image=IMAGE_URL --region=us-central1 --functional-type=agent --identity-type=agent-identity` |
| "Register my existing Cloud Run service my-agent as an agent" | `gcloud beta run services update my-agent --region=us-central1 --functional-type=agent --identity-type=agent-identity --no-traffic` |
| "Deploy a Cloud Run service my-mcp as an MCP server" | `gcloud beta run deploy my-mcp --image=IMAGE_URL --region=us-central1 --functional-type=mcp-server` |
| "Update existing Cloud Run service my-mcp to register as an MCP server" | `gcloud beta run services update my-mcp --region=us-central1 --functional-type=mcp-server` |
| "Create a Cloud Run job my-agent-job registered as an agent" | `gcloud beta run jobs create my-agent-job --image=IMAGE_URL --region=us-central1 --functional-type=agent --identity-type=agent-identity` |
| "View the assigned agent identity for Cloud Run revision my-agent-00001" | `gcloud beta run revisions describe my-agent-00001 --region=us-central1` |
| "Show me information on agent X" | `gcloud agent-registry agents describe X --location=us-central1` |
| "Register a new MCP server my-mcp-service with this spec..." | `gcloud agent-registry services create my-mcp-service ... --mcp-server-spec-content='...'` |
| "Check status of operation Y" | `gcloud agent-registry operations describe Y --location=us-central1` |
| "List all registered services" | `gcloud agent-registry services list --location=us-central1` |
| "Delete registered service Z" | `gcloud agent-registry services delete Z --location=us-central1` |
| "Show all agents where the runtime is reasoningEngine" | `gcloud agent-registry agents list --location=us-central1 --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri:reasoningEngine"` |
| "Show agents with identity containing 'service-123456789012'" | `gcloud agent-registry agents list --location=us-central1 --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeIdentity\".principal:service-123456789012"` |
| "Create a new A2A agent called my-a2a" | `gcloud agent-registry services create my-a2a --agent-spec-type=a2a-agent-card ...` |
| "Show me all MCP servers where the runtime is my-runtime" | `gcloud agent-registry mcp-servers list --location=us-central1 --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri:my-runtime"` |
| "List all global agents" | `gcloud agent-registry agents list --location=global` |
| "List global MCP servers" | `gcloud agent-registry mcp-servers list --location=global` |
| "Change display name of gemini-models to 'Vertex AI Model Garden'" | `gcloud agent-registry services update gemini-models --display-name="..." --location=us-central1` |
| "Quickly add the aiplatform GCP service in us-central1 (composite 5-URL service)" | `./scripts/quick-add-gcp-service.sh --service=aiplatform --location=us-central1` |
| "Quick add storage API endpoints for Agent Gateway in us-central1" | `./scripts/quick-add-gcp-service.sh --service=storage --location=us-central1` |
| "Which agents in us-central1 are based on reasoning engine?" | `gcloud agent-registry agents list --location=us-central1 --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri:reasoningEngine"` |
| "List all vertex ai agents" | `gcloud agent-registry agents list --location=us-central1 --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri:reasoningEngine"` |
| "Show agents with agent engine runtime" | `gcloud agent-registry agents list --location=us-central1 --filter="attributes.\"agentregistry.googleapis.com/system/RuntimeReference\".uri:reasoningEngine"` |
| "Which MCP Server has a tool named search_documents?" | `gcloud agent-registry mcp-servers list --location=us-central1 --filter="tools.name:search_documents"` |
| "Find all servers with the get_document tool" | `gcloud agent-registry mcp-servers list --location=us-central1 --filter="tools.name:get_document"` |
| "Search for all reasoning engine agents by agent ID" | `gcloud agent-registry agents list --location=us-central1 --filter="agentId:reason"` |
| "Search for Cloud Run MCP servers by MCP Server ID" | `gcloud agent-registry mcp-servers list --location=us-central1 --filter="mcpServerId:run"` |
| "Search for agents by skill name translation" | `gcloud agent-registry agents search --location=us-central1 --search-string="skills.name:translation"` |
| "Search for agents with display name starting with MyAgent" | `gcloud agent-registry agents search --location=us-central1 --search-string="displayName:MyAgent*"` |
| "Search for MCP servers starting with display name MyMcp" | `gcloud agent-registry mcp-servers search --location=us-central1 --search-string="displayName:MyMcp*"` |
| "Create a binding between agent A and server B" | `gcloud agent-registry bindings create my-binding --source-identifier="URN_A" --target-identifier="URN_B" --location=us-central1` |
| "List all bindings" | `gcloud agent-registry bindings list --location=us-central1` |
| "Show details for binding X" | `gcloud agent-registry bindings describe X --location=us-central1` |
| "Delete binding Y" | `gcloud agent-registry bindings delete Y --location=us-central1` |
| "List all skills" | `gcloud agent-registry skills list --location=us` |
| "Create a skill named my-skill from /path/to/archive.zip" | `gcloud agent-registry skills create my-skill --location=us --display-name="My Skill" --target-state=active --payload=/path/to/archive.zip` *(creates `skills/private-my-skill`)* |
| "Show details of custom skill my-skill" | `gcloud agent-registry skills describe private-my-skill --location=us` |
| "Upload a new revision v2 for custom skill my-skill" | `gcloud agent-registry skills revisions create v2 --skill=private-my-skill --location=us --payload=/path/to/archive.zip` |
| "List security scan findings in us" | `gcloud agent-registry findings list --location=us` |
| "Search skills matching query" | `gcloud agent-registry skills search --location=us --query="QUERY"` |
| "Get IAM policy on custom skill my-skill" | `gcloud agent-registry skills get-iam-policy private-my-skill --location=us` |
| "Grant user alice@example.com viewer role on custom skill my-skill" | `gcloud agent-registry skills add-iam-policy-binding private-my-skill --location=us --member="user:alice@example.com" --role="roles/agentregistry.viewer"` |
| "Set IAM policy on custom skill my-skill from policy.yaml" | `gcloud agent-registry skills set-iam-policy private-my-skill policy.yaml --location=us` |
| "List all AI applications" | `gcloud agent-registry ai-applications list --location=us-central1` |
| "Describe the default AI application" | `gcloud agent-registry ai-applications describe default --location=us-central1` |
| "Search AI applications with display name Customer*" | `gcloud agent-registry ai-applications search --location=us-central1 --search-string="displayName:Customer*"` |
| "List agents under the default AI application" | `gcloud agent-registry ai-applications agents list --ai-application=default --location=us-central1` |
| "List MCP servers under AI application my-ai-app" | `gcloud agent-registry ai-applications mcp-servers list --ai-application=my-ai-app --location=us-central1` |
| "Get IAM policy for AI application my-ai-app" | `gcloud agent-registry ai-applications get-iam-policy my-ai-app --location=us-central1` |
| "Grant group ai-team@example.com viewer access on AI application my-ai-app" | `gcloud agent-registry ai-applications add-iam-policy-binding my-ai-app --location=us-central1 --member="group:ai-team@example.com" --role="roles/agentregistry.viewer"` |
| "Set IAM policy on AI application my-ai-app from policy.yaml" | `gcloud agent-registry ai-applications set-iam-policy my-ai-app policy.yaml --location=us-central1` |
| "Configure folder 111111111111 boundary config to use environment tag" | `gcloud resource-manager boundary-configs update --folder=111111111111 --tag-key="222222222222/environment"` |
| "Create a capability config for agent management on folder 111111111111" | `gcloud resource-manager capability-configs create agent-governance --folder=111111111111 --display-name="Agent Governance Capability" --types=agent-management --management-project=projects/123456789012` |
| "Create a dev boundary under folder 111111111111 for environment=dev" | `gcloud resource-manager boundaries create agents-dev --folder=111111111111 --display-name="Agent Dev Boundary" --tag-key="222222222222/environment" --tag-value="dev"` |
| "Associate boundary agents-dev with capability config agent-governance" | `gcloud resource-manager capability-configs update agent-governance --folder=111111111111 --boundaries=folders/111111111111/boundaries/agents-dev` |
| "Bind tag environment=dev to project 333333333333" | `gcloud resource-manager tags bindings create --tag-value=222222222222/environment/dev --parent=//cloudresourcemanager.googleapis.com/projects/333333333333` |
| "List all boundaries under folder 111111111111" | `gcloud resource-manager boundaries list --folder=111111111111` |
| "List all capability configs under folder 111111111111" | `gcloud resource-manager capability-configs list --folder=111111111111` |
| "Filter aggregated agents in management project by spoke project number 333333333333" | `gcloud agent-registry agents list --project=MANAGEMENT_PROJECT_ID --location=us-central1 --filter="agentId:333333333333"` |
| "Search aggregated agents by skill tag productivity" | `gcloud agent-registry agents search --project=MANAGEMENT_PROJECT_ID --location=us-central1 --search-string="skills.tags:productivity"` |
