# Workload Manager Client Libraries

Use client libraries when working with evaluation lifecycle resources. The
public Python client is currently beta and supports Python 3.9 or later.

## Python Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade google-cloud-workloadmanager
gcloud auth application-default login
```

## Python: List Rules

```python
from google.cloud import workloadmanager_v1

project_id = "PROJECT_ID"
location = "LOCATION"
parent = f"projects/{project_id}/locations/{location}"

client = workloadmanager_v1.WorkloadManagerClient()
response = client.list_rules(
    request=workloadmanager_v1.ListRulesRequest(
        parent=parent,
        evaluation_type=workloadmanager_v1.Evaluation.EvaluationType.SQL_SERVER,
    )
)

for rule in response.rules:
    print(rule.name, rule.display_name, rule.severity)
```

## Python: Create an Evaluation

Fetch valid rule names first, then create the evaluation. Keep the resource
filter narrow until the workflow is proven.

```python
from google.cloud import workloadmanager_v1

project_id = "PROJECT_ID"
location = "LOCATION"
evaluation_id = "sql-server-prod"
parent = f"projects/{project_id}/locations/{location}"

client = workloadmanager_v1.WorkloadManagerClient()

rule_response = client.list_rules(
    request=workloadmanager_v1.ListRulesRequest(
        parent=parent,
        evaluation_type=workloadmanager_v1.Evaluation.EvaluationType.SQL_SERVER,
    )
)
rule_names = [rule.name for rule in rule_response.rules]

evaluation = workloadmanager_v1.Evaluation(
    description="SQL Server production validation",
    evaluation_type=workloadmanager_v1.Evaluation.EvaluationType.SQL_SERVER,
    resource_filter=workloadmanager_v1.ResourceFilter(
        scopes=[f"projects/{project_id}"],
        inclusion_labels={"env": "prod"},
    ),
    rule_names=rule_names,
    labels={"owner": "platform", "workload": "sql-server"},
)

operation = client.create_evaluation(
    request=workloadmanager_v1.CreateEvaluationRequest(
        parent=parent,
        evaluation_id=evaluation_id,
        evaluation=evaluation,
    )
)
created = operation.result(timeout=600)
print(created.name)
```

## Python: Run an Evaluation

```python
import uuid

from google.cloud import workloadmanager_v1

project_id = "PROJECT_ID"
location = "LOCATION"
evaluation_id = "sql-server-prod"
execution_id = "manual-run-001"
evaluation_name = (
    f"projects/{project_id}/locations/{location}/evaluations/{evaluation_id}"
)

client = workloadmanager_v1.WorkloadManagerClient()
operation = client.run_evaluation(
    request=workloadmanager_v1.RunEvaluationRequest(
        name=evaluation_name,
        execution_id=execution_id,
        execution=workloadmanager_v1.Execution(
            labels={"trigger": "manual"},
        ),
        request_id=str(uuid.uuid4()),
    )
)
execution = operation.result(timeout=1200)
print(execution.name, execution.state)
```

## Python: Read Findings

```python
from google.cloud import workloadmanager_v1

execution_name = (
    "projects/PROJECT_ID/locations/LOCATION/evaluations/EVALUATION_ID/"
    "executions/EXECUTION_ID"
)

client = workloadmanager_v1.WorkloadManagerClient()
for result in client.list_execution_results(
    request=workloadmanager_v1.ListExecutionResultsRequest(
        parent=execution_name,
        filter='severity="HIGH"',
    )
):
    print(result.rule, result.severity, result.resource.name)
    print(result.violation_message)
    print(result.documentation_url)
```

## Python: Update an Evaluation Schedule

```python
from google.cloud import workloadmanager_v1
from google.protobuf import field_mask_pb2

evaluation_name = (
    "projects/PROJECT_ID/locations/LOCATION/evaluations/EVALUATION_ID"
)

client = workloadmanager_v1.WorkloadManagerClient()
evaluation = client.get_evaluation(name=evaluation_name)
evaluation.schedule = "0 0 */1 * *"

operation = client.update_evaluation(
    request=workloadmanager_v1.UpdateEvaluationRequest(
        evaluation=evaluation,
        update_mask=field_mask_pb2.FieldMask(paths=["schedule"]),
    )
)
updated = operation.result(timeout=600)
print(updated.schedule)
```

## Go Setup

```bash
go get cloud.google.com/go/workloadmanager/apiv1
```

## Go: List Evaluations

```go
package main

import (
	"context"
	"fmt"
	"log"

	workloadmanager "cloud.google.com/go/workloadmanager/apiv1"
	workloadmanagerpb "cloud.google.com/go/workloadmanager/apiv1/workloadmanagerpb"
	"google.golang.org/api/iterator"
)

func main() {
	ctx := context.Background()
	client, err := workloadmanager.NewClient(ctx)
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close()

	req := &workloadmanagerpb.ListEvaluationsRequest{
		Parent: "projects/PROJECT_ID/locations/LOCATION",
	}
	it := client.ListEvaluations(ctx, req)
	for {
		evaluation, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			log.Fatal(err)
		}
		fmt.Println(evaluation.GetName())
	}
}
```

## Practical Guardrails

- Check the current client reference before using resources outside the
  evaluation lifecycle; some REST resources may not be generated into every
  client library yet.
- Treat long-running operations as asynchronous. Always call `operation.result`
  with a timeout or poll explicitly.
- Use request objects instead of mixing request objects and flattened keyword
  arguments in the same call.
- Store execution result exports in a dedicated BigQuery dataset when using
  `BigQueryDestination`.
