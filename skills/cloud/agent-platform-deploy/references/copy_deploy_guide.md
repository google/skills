# Agent Platform 1P Tuned model copy and deployment

> [!NOTE]
> **1P Specific**: This guide and its automated workflows are specifically
> designed for **1P (First-Party) Tuned Models** on Agent Platform.

In tuned model tuning and inferencing, Eng need to copy a tuned model to other
regions or projects and deploy it to a newly created endpoint to test. Eng can
benefit from the endpoint creation, model deployment and verification automation
with minimal user input and intervention.

The tasks can be described as follows:

-   `[]` Configure `gcloud` profile for prod environment.
-   `[]` Add IAM policy binding for P4SA (Service Agent) to the source project
-   `[]` Copy the tuned model to the destination project
-   `[]` Wait for copy operation to complete
-   `[]` Create a new shared endpoint
-   `[]` Deploy copied model to the endpoint
-   `[]` Wait for model deployment to complete
-   `[]` Test the endpoint with test prompts

## Step 0: Env selection and preparation

Ensure the foundational environment is ready before proceeding.
If user is copying model in different region, skip the P4SA setup section.

### 0.0 Pick a development environment & Confirm Destination Context

-   **CRITICAL: Ask for Confirmation.** You MUST present a clear confirmation
    prompt to confirm the development
    environment (e.g., `prod`), destination project (`dest-proj`), and region
    (`us-central1`) with the user. You MUST halt execution and wait for the
    user's explicit confirmation response before running any `gcloud` or `curl`
    commands. If you are generating a script for the user instead of running
    commands live, you MUST explicitly include a note in your response
    explaining that confirming the development environment (e.g., prod) and
    destination context with the user is required before running the script
    live.
-   Execute the following command to set the global variable.
    `export ENV="prod"`

### 0.1 Authentication & Project Context

-   Check if `gcloud` CLI is installed. If it is not installed, prompt the user for permission to install it before proceeding.
-   Verify `gcloud auth list`. If not authenticated, run `gcloud auth login`.
-   Execute the following command to set the global variable.
    `export PROJECT_ID=${PROJECT_ID} REGION=${REGION}`
-   Check if ${USER_EMAIL} have value (the full account email), or ask user to
    set one.

### 0.2 GCloud CLI setup

-   use `scripts/config_gcloud_cli.sh ${ENV} ${PROJECT_ID} ${REGION} ${USER_EMAIL}`

### 0.3 P4SA Setup

#### 0.3.0 Goal

To copy a model from source project ${SOURCE_PROJECT} to the destination project
${PROJECT_ID}, and ${REGION}, follow

https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/copy-model, add the

P4SA of the destination project as a new principal to the source project and
assign the Vertex AI Service Agent role to it.

#### 0.3.1 P4SA selection

-   Get project number ${PROJECT_NUMBER} using gcloud:
    `gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)"`
-   Destination project P4SA:
    `service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com`

#### 0.3.2 P4SA assignment

-   The ${MODEL} to copy should in format of
    `projects/${SOURCE_PROJECT}/locations/${SOURCE_REGION}/models/${MODEL_ID}`

-   Get source project name `${SOURCE_PROJECT}` from the model to copy.

-   Check IAM binding: if destination project `${P4SA}` exists and has
    `Vertex AI Service Agent` role. Sample command:

    ```bash
    gcloud projects get-iam-policy ${SOURCE_PROJECT} \
    --flatten="bindings[].members" \
    --format="table(bindings.role)" \
    --filter="bindings.members:service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com"
    ```

-   If not, add it with the sample command, save and wait for 2 minutes.

    ```bash
    gcloud projects add-iam-policy-binding ${SOURCE_PROJECT} \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com" \
    --role="roles/aiplatform.serviceAgent"
    ```

-   If failed, try to add user's account to destination project.

    ```bash
    gcloud projects add-iam-policy-binding ${DEST_PROJECT_ID} \
    --member="user:${USER_EMAIL}" --role="roles/aiplatform.admin"
    ```

-   If failed again, prompt user to do it.

## Step 1: Verify the source model exists and valid

```bash
curl -X GET -H "Authorization: Bearer $(gcloud auth print-access-token)" ${ENDPOINT}/ui/${MODEL}
```

## Step 2: Copy source model to destination project

If user is copying to different project and different region, try copy the model
to the desired region in the source project first, then copy across project.

### Step 2.0 Verify the iam binding exists

Make sure the destination project P4SA is added to source project as
`roles/aiplatform.serviceAgent` before proceeding.

### Step 2.1 Run copy model command and poll for LRO completion

Copying a model is a Long-Running Operation (LRO). You MUST capture the
operation ID from the initial `models:copy` response and implement a polling
loop to check the operation status over time. You MUST NOT proceed to create
the endpoint until the operation status is `done: true` and contains the
copied model metadata. If the copy operation fails (e.g., with
`403 PERMISSION_DENIED` or `error`), you MUST halt execution immediately and
report the exact error to the user.

```bash
# 1. Start Copy Operation
COPY_RESP=$(curl -s -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json; charset=utf-8" -d '{ "sourceModel":"'"${MODEL}"'"}' "${ENDPOINT}/v1/projects/${PROJECT_ID}/locations/${REGION}/models:copy")
echo "Copy response: $COPY_RESP"
OPERATION_ID=$(echo "$COPY_RESP" | grep -o '"name": "[^"]*' | grep -o '[^"]*$')

if [ -z "$OPERATION_ID" ]; then
    echo "Error: Failed to initiate model copy. Response: $COPY_RESP"
    exit 1
fi

echo "Polling copy operation: $OPERATION_ID..."
while true; do
    OP_STATUS=$(curl -s -X GET -H "Authorization: Bearer $(gcloud auth print-access-token)" "${ENDPOINT}/v1/${OPERATION_ID}")
    IS_DONE=$(echo "$OP_STATUS" | grep -o '"done": true')
    HAS_ERROR=$(echo "$OP_STATUS" | grep -o '"error":')

    if [ -n "$HAS_ERROR" ]; then
        echo "Error during model copy: $OP_STATUS"
        exit 1
    fi

    if [ -n "$IS_DONE" ]; then
        echo "Model copy completed successfully!"
        MODEL_COPY=$(echo "$OP_STATUS" | grep -o '"model": "[^"]*' | grep -o '[^"]*$' | head -n 1)
        break
    fi
    echo "Copy in progress... waiting 10 seconds."
    sleep 10
done
```

### Step 2.2 Run describe model command

Get the copied model ${MODEL_COPY} from the LRO polling output. Describe it.

```bash
curl -X GET -H "Authorization: Bearer $(gcloud auth print-access-token)" ${ENDPOINT}/ui/${MODEL_COPY}
```

## Step 3: Create an endpoint

Prompt user `Creating a Public Shared endpoint in selected region: ${REGION}`.
Ask the user desired endpoint display name ${NAME}, prefer
`${<publisher_model_id>-tuned}` like "gemini-3.8-flash-tuned", default is
`copy-tuned`. If user wants to create a Dedicated Endpoint, say function to be
add.

```bash
gcloud ai endpoints create --region=${REGION} --display-name=${NAME}
gcloud ai endpoints list --region=${REGION}   --filter=display_name=${NAME}
```

Get the created endpoint id ${NEW_ENDPOINT}, it should be in format of
`projects/${PROJECT_NUMBER}/locations/${REGION}/endpoints/${NEW_ENDPOINT_ID}`.

## Step 4: Deploy the model to the endpoint

```bash
curl -X POST -H "Content-Type: application/json" \
 -H "Authorization: Bearer $(gcloud auth print-access-token)" \
 "${ENDPOINT}/v1/${NEW_ENDPOINT}:deployModel" \
 -d "{\"deployedModel\": {\"model\": \"${MODEL_COPY}\", \"displayName\": \"${NAME}\"}}"
```

Get the deploy model operation ${OPERATION} status.

`curl -X GET -H "Authorization: Bearer $(gcloud auth print-access-token)"
${ENDPOINT}/ui/${OPERATION}`

Once operation is done, check the endpoint status.

```bash
gcloud ai endpoints describe ${NEW_ENDPOINT}
```

## Step 5: Send a request and verify the endpoint

```bash
curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)"  -H "Content-Type: application/json" ${ENDPOINT}/v1/${NEW_ENDPOINT}:generateContent -d '{  "contents":  {    "role": "USER",   "parts" : { "text" : "Hello world" }  },}'
```

## Workflow-Specific Safety Rules

The system instruction's Tier M/D confirmation gates apply to every mutating
command in this workflow. The rules below cover behaviors specific to the 1P
tuned model copy-and-deploy flow that are not in the system instruction.

1.  **Tier Assignments**: `gcloud ai models copy`, `gcloud ai endpoints create`,
    and `gcloud ai endpoints deploy-model` are **Tier M** (mutating,
    reversible). `gcloud ai endpoints delete` and `gcloud ai models delete` are
    **Tier D** (destructive, irreversible). The Tier M dry-run preview card for
    this workflow must include: development environment, source model ID,
    destination project and region, endpoint display name, and exact proposed
    commands.

2.  **Hardware Renegotiation / Error Recovery**: If deployment fails with a 500
    error or quota error, note that tuned Gemini models can only be deployed to
    shared public endpoints (dedicated GPU hardware cannot host tuned Gemini
    models).

3.  **Verification with Test Prediction**: When requested to send a test
    prediction:

    -   If the endpoint is still provisioning or not yet serving, explain that
        deployment is currently in progress and report the operation ID.
    -   If ready, execute the test prediction request to the dedicated endpoint
        DNS and return the response verbatim.

4.  **In-Progress Operation Lock**: When the user requests cleanup while a
    deployment is still provisioning, explicitly state that teardown is
    **BLOCKED by the in-progress operation lock** on the endpoint until
    provisioning completes. Present the Tier D confirmation prompt so the user
    can approve cleanup for when the operation finishes.

## Clean Up

Prompt asking whether or not user want to clean up each resources created during
execution.

### 1. Endpoint

If user want to delete the created endpoint, undeploy the model first, then
delete the endpoint

```bash
gcloud ai endpoints undeploy-model ${NEW_ENDPOINT} --deployed-model-id=${DEPLOYED_MODEL_ID} --region=${REGION}
gcloud ai endpoints delete ${NEW_ENDPOINT} --region=${REGION}
```

### 2. Model

```bash
gcloud ai models delete ${MODEL_COPY}
```

### 3. Env variables

Only execute these commands after confirm use does no want to or already
finished clean up copied model and endpoint.

```bash
gcloud config configurations delete ${ENV}-cdmodel
unset MODEL_COPY
unset MODEL
unset NEW_ENDPOINT
unset ENDPOINT
unset PROJECT_ID
unset PROJECT_NUMBER
unset ENV
unset REGION
unset OPERATION
unset NAME
```
