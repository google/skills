# VPC Flow Logs Cost Estimation Reference

Use this reference to estimate the monthly cost of VPC Flow Logs across
Subnetworks, VPCs, or entire Projects. This logic implements the cost estimation
calculations for VPC Flow Logs using the standard tiered pricing model.

## Table of Contents

-   [Agent Instructions](#agent-instructions): Lines 22-33
-   [Step 1: Scope and Capabilities (Boundaries)](#step-1-scope-and-capabilities-boundaries):
    Lines 37-67
-   [Step 2: Configuration Defaults](#step-2-configuration-defaults): Lines
    71-78
-   [Step 3: Resource Resolution (Discover Target Subnets)](#step-3-resource-resolution-discover-target-subnets):
    Lines 82-138
-   [Step 4: Retrieve Metrics (Batch Query)](#step-4-retrieve-metrics-batch-query):
    Lines 142-215
-   [Step 5: Cost Calculations (CLI Calculator)](#step-5-cost-calculations-cli-calculator):
    Lines 219-293
-   [Step 6: Format Report](#step-6-format-report): Lines 297-338

## Agent Instructions

When a user requests a cost estimation, the agent MUST follow this procedure
step-by-step.

> [!IMPORTANT] **In-Memory Execution Only**:
>
> -   Do not create persistent `.py`, `.sh`, or `.json` files in the working
>     directory.
> -   Run `gcloud` and `curl` directly, parse JSON responses in-memory with
>     `jq` or `python3 -c`, and format the final markdown report in your
>     response.

---

### Step 1: Scope and Capabilities (Boundaries)

Before starting, validate that the request is supported.

> [!IMPORTANT] **Supported Scopes**: Subnetworks, VPC Networks, or the entire
> GCP Project.

-   **ALWAYS** reject cost estimation requests for Cloud VPN, Cloud
    Interconnect, or Organization-level configurations, and use the standardized
    refusal response.
-   **ALWAYS** show your step-by-step mathematical calculations in the final
    cost estimation report to ensure transparency and allow manual verification.

> **UNSUPPORTED Features & Scopes (Strictly Reject)**:
>
> -   Cloud VPN (VPN Tunnels)
> -   Cloud Interconnect (Interconnect attachments)
> -   Organization-level configurations
> -   Custom log aggregation intervals (other than default 5 seconds)
> -   Custom metadata fields
> -   Enterprise or Committed Use Discounts (estimates must use standard list
>     prices only)
>
> If the user requests estimation for an unsupported feature or resource,
> decline immediately without running `gcloud` or Monitoring API queries,
> substituting the unsupported feature or resource name in the response (e.g.,
> `Cloud VPN`, `Cloud Interconnect`, `Organization`):
>
> ```text
> I'm sorry, {feature_resource} is not supported. I only support estimation for Subnets, VPCs, or Projects.
> ```

---

### Step 2: Configuration Defaults

If not specified by the user, use these default parameters:

-   **Sampling Rate**: 100% (`1.0` multiplier).
-   **Metadata**: Include Metadata (`True`).
    -   *If the user explicitly requests "No Metadata" or "Exclude Metadata",
        set Metadata to `False`.*

---

### Step 3: Resource Resolution (Discover Target Subnets)

Resolve the target scope to identify the subnetworks we need to estimate and get
the **total count** of subnetworks in that scope (needed for the inactive count
in the report).

Use `gcloud` based on the scope:

#### Step 3.A: Subnetwork Scope (User specified a subnet)

If the user specified a subnet, but did not provide the VPC or Region, ask them
for clarification using the Ambiguity response:

```text
I found multiple matches for {subnet_name}. Please specify the Region or VPC to continue.
```

Once all details are known, describe the subnet to verify it exists and get its
ID:

```bash
gcloud compute networks subnets describe {subnet_name} --region={region} --project={project_id} --format="json(name, id, region, network)"
```

*If not found, immediately respond with:*
`"I was unable to find {subnet_name}. Please verify the name and try again."`

-   **Total Subnets Count**: 1

#### Step 3.B: VPC Scope (User specified a VPC)

Find all subnetworks in the VPC and get their details:

```bash
gcloud compute networks subnets list --filter="network:https://www.googleapis.com/compute/v1/projects/{project_id}/global/networks/{vpc_name}" --project={project_id} --format="json(name, id, region, network)"
```

*If 0 subnetworks are found, immediately respond with:*
`"I found no subnets for {vpc_name}. Nothing to estimate."`

-   **Total Subnets Count**: Count the number of subnetworks returned in this
    list.

#### Step 3.C: Project Scope (User specified the entire project)

Find all subnetworks in the project and get their details:

```bash
gcloud compute networks subnets list --project={project_id} --format="json(name, id, region, network)"
```

*If 0 subnetworks are found, immediately respond with:*
`"I found no subnets for {project_id}. Nothing to estimate."`

-   **Total Subnets Count**: Count the number of subnetworks returned in this
    list. Use this list to group the active vs inactive subnets by their VPC
    later in the report.

---

### Step 4: Retrieve Metrics (Batch Query)

To avoid per-subnet API quota exhaustion and high latency on large projects, do
**not** query the Monitoring API in a loop. Instead, run one project-wide batch
query and filter the results in-memory.

#### Step 4.A: Calculate Time Window (Last 30 Days)

Use the terminal to calculate the RFC 3339 timestamps for 30 days ago and now:

```bash
project_id={project_id}
end_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
start_time=$(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ)
```

#### Step 4.B: Execute Batch Query

Query the predicted log count for **all** subnetworks in the project in a single
call, grouping by subnetwork. Format the output as clean JSON lines for easy
reading:

```bash
URL="https://monitoring.googleapis.com/v3/projects/${project_id}/timeSeries?filter=metric.type%3D%22networking.googleapis.com/vpc_flow/predicted_max_vpc_flow_logs_count%22%20AND%20resource.type%3D%22gce_subnetwork%22&interval.startTime=${start_time}&interval.endTime=${end_time}&aggregation.alignmentPeriod=2592000s&aggregation.perSeriesAligner=ALIGN_SUM&aggregation.crossSeriesReducer=REDUCE_SUM&aggregation.groupByFields=resource.labels.subnetwork_name&aggregation.groupByFields=resource.labels.subnetwork_id&aggregation.groupByFields=resource.labels.location"

RESPONSE=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token 2>/dev/null)" "$URL")
if echo "$RESPONSE" | grep -q "401"; then
  RESPONSE=$(curl -s -H "Authorization: Bearer $(gcloud auth application-default print-access-token 2>/dev/null)" "$URL")
fi

printf '%s\n' "$RESPONSE" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    if "error" in data:
        print("API_ERROR:", json.dumps(data["error"]), file=sys.stderr)
        sys.exit(1)
    for ts in data.get("timeSeries", []):
        labels = ts.get("resource", {}).get("labels", {})
        points = ts.get("points", [])
        if points:
            val_dict = points[0].get("value", {})
            logs = val_dict.get("doubleValue", val_dict.get("int64Value", 0))
            print(json.dumps({
                "name": labels.get("subnetwork_name"),
                "id": labels.get("subnetwork_id"),
                "region": labels.get("location"),
                "logs": int(logs)
            }))
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
'
```

*If the `curl` command returns an API error (e.g. `UNAUTHENTICATED`,
`ACCESS_TOKEN_TYPE_UNSUPPORTED`), immediately respond with:*
`"ERROR: Monitoring API Request failed. Please check your token/permissions."`
*and STOP. Do not proceed to cost calculation.*

This will return a list of active subnetworks (those with traffic). If a
subnetwork is not in this list, its log count is `0`.

#### Step 4.C: Filter Results In-Context

Match the active subnetworks from the query output against your target scope
(from Step 3):

-   **Project Scope**: Use all subnetworks returned by the query.
-   **VPC Scope**: Keep only the subnetworks from the query whose `id` or `name`
    matches the subnetworks list resolved for the VPC in Step 3.
-   **Subnetwork Scope**: Keep only the single subnetwork specified by the user.

Any target subnetwork not present in the query output has `0` logs (No traffic).

---

### Step 5: Cost Calculations (CLI Calculator)

To prevent arithmetic errors, you **MUST** use `python3 -c` as an in-memory
calculator to perform all mathematical steps.

#### Step 5.A: Determine Parameters

-   **Sampling Rate**: $S$ (e.g., `1.0` for 100%, `0.5` for 50%)
-   **Bytes per Log**: $B = 1418$ (if Metadata=True) else $B = 542$ (if
    Metadata=False)

#### Step 5.B: Calculate Subnetwork Volume

For each active subnetwork in your filtered list, calculate the volume in GB:

```bash
python3 -c "print(({L_raw} * {S} * {B}) / (1024**3))"
```

Keep track of these individual $V_{subnet}$ values for the report breakdown.

#### Step 5.C: Calculate Aggregate Totals & Tiered Pricing

Sum all effective logs ($L_{raw} \times S$) to get $L_{total}$. Sum all
$V_{subnet}$ to get $V_{total}$.

Run the following Python command (filling in $V_{total}$ and $L_{total}$) to
calculate the monthly tiered generation and Cloud Logging storage costs:

```bash
python3 -c '
total_gb = {V_total}
total_logs = {L_total}

# Tiered Generation Pricing (Network Telemetry)
remaining_gb = total_gb
generation_cost = 0.0
TIB = 1024.0

# Tier 1: 0-10 TiB @ $0.25/GB
tier1_limit = 10 * TIB
tier1_volume = min(remaining_gb, tier1_limit)
generation_cost += tier1_volume * 0.25
remaining_gb -= tier1_volume

if remaining_gb > 0:
    # Tier 2: 10-30 TiB @ $0.15/GB
    tier2_limit = 20 * TIB
    tier2_volume = min(remaining_gb, tier2_limit)
    generation_cost += tier2_volume * 0.15
    remaining_gb -= tier2_volume

    if remaining_gb > 0:
        # Tier 3: 30-50 TiB @ $0.075/GB
        tier3_limit = 20 * TIB
        tier3_volume = min(remaining_gb, tier3_limit)
        generation_cost += tier3_volume * 0.075
        remaining_gb -= tier3_volume

        if remaining_gb > 0:
            # Tier 4: > 50 TiB @ $0.05/GB
            generation_cost += remaining_gb * 0.05

# Storage Pricing (Cloud Logging)
storage_cost = total_gb * 0.25

total_cost = generation_cost + storage_cost

print(f"TOTAL_LOGS: {total_logs:,.0f}")
print(f"TOTAL_GB: {total_gb:.4f}")
print(f"GEN_COST: {generation_cost:.4f}")
print(f"STORE_COST: {storage_cost:.4f}")
print(f"TOTAL_COST: {total_cost:.4f}")
'
```

---

### Step 6: Format Report

Format your final report exactly like this. You must sort the VPCs
alphabetically, and sort the subnets within each VPC by Monthly Volume (GB)
descending.

-   **Active Subnets**: Show their logs and volume in the table.
-   **Inactive Subnets**: Do not list them in the table. Instead, calculate `N =
    Total Subnets Count - Active Subnets Count` and show them in the note
    `*(Note: N other subnets...)*`.

```markdown
**VPC Flow Logs Cost Estimation Report**

**Scope:** [Scope Name, e.g., Project 'my-project' or VPC 'my-vpc']

**Configuration:** Sampling [Sampling Rate]%, Metadata: [Yes/No]

**Summary:**
- **Total Monthly Logs:** [TOTAL_LOGS]
- **Total Monthly Data Volume:** [TOTAL_GB] GB
- **Estimated Monthly Cost:**
    - **Generation (Network Telemetry):** $[GEN_COST]
    - **Storage (Cloud Logging):** $[STORE_COST]
    - **Total List Price:** $[TOTAL_COST]

**Detailed Breakdown:**

### VPC: [VPC Name]
| Subnet Name | Region | Monthly Logs | Monthly Volume (GB) |
| :--- | :--- | :---: | :---: |
| [subnet-a] | [us-central1] | [L_eff formatted] | [V_subnet formatted to 4 decimals] |

*(Note: [N] other subnets in the '[VPC Name]' VPC showed no traffic during the analysis period.)*

---
**DISCLAIMER:** This is an estimation only.
1. **Unsupported Resources:** Interconnects and VPNs are excluded from this estimate.
2. **Aggregation:** This assumes the default 5s aggregation interval; volumes may vary with custom intervals.
3. **Pricing:** Estimates use standard list prices and do not include enterprise or committed use discounts.
4. **Analysis period:** Based on a 30-day analysis period.
```
