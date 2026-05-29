#!/bin/bash

# Usage: ./billing_caps.sh <PROJECT_ID> <BILLING_ACCOUNT_ID> <BUDGET_AMOUNT> [REGION] [TOPIC_ID]
# NOTE: Deploying this solution will incur minor Cloud Run and Pub/Sub costs for continuous monitoring.

if [[ "$#" -lt 3 ]]; then
    echo "Usage: $0 <PROJECT_ID> <BILLING_ACCOUNT_ID> <BUDGET_AMOUNT> [REGION] [TOPIC_ID]"
    exit 1
fi

PROJECT_ID="$1"
BILLING_ACCOUNT_ID="$2"
BUDGET_AMOUNT="$3"
REGION="${4:-us-central1}"
TOPIC_ID="${5:-billing-alerts-topic}"

echo "Deploying Billing Disconnect with parameters:"
echo "Project ID: ${PROJECT_ID}"
echo "Billing Account ID: ${BILLING_ACCOUNT_ID}"
echo "Budget Amount: ${BUDGET_AMOUNT}"
echo "Region: ${REGION}"
echo "Topic ID: ${TOPIC_ID}"

# 2. Enable Required APIs
gcloud services enable billingbudgets.googleapis.com \
    cloudbilling.googleapis.com \
    cloudbuild.googleapis.com \
    cloudfunctions.googleapis.com \
    eventarc.googleapis.com \
    run.googleapis.com \
    pubsub.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}"

# 3. Create Pub/Sub Topic
gcloud pubsub topics describe "${TOPIC_ID}" --project="${PROJECT_ID}" &>/dev/null || gcloud pubsub topics create "${TOPIC_ID}" --project="${PROJECT_ID}"

# 4. Create Source Files for the Function
mkdir -p billing_function
cat <<'EOF' > billing_function/package.json
{
  "name": "cloud-functions-billing",
  "private": "true",
  "version": "0.0.1",
  "description": "Examples of integrating Cloud Functions with billing",
  "main": "index.js",
  "engines": {
    "node": ">=18.0.0"
  },
  "author": "Google LLC",
  "license": "Apache-2.0",
  "dependencies": {
    "@google-cloud/billing": "^4.0.0"
  },
  "devDependencies": {
    "@google-cloud/functions-framework": "^3.0.0",
    "c8": "^10.0.0",
    "gaxios": "^6.0.0",
    "mocha": "^10.0.0",
    "promise-retry": "^2.0.0",
    "proxyquire": "^2.1.0",
    "sinon": "^18.0.0",
    "wait-port": "^1.0.4"
  }
}
EOF

cat <<'EOF' > billing_function/index.js
const {CloudBillingClient} = require('@google-cloud/billing');

const PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT;
const PROJECT_NAME = `projects/${PROJECT_ID}`;
const billing = new CloudBillingClient();

exports.stopBilling = async pubsubEvent => {
  const pubsubData = JSON.parse(
    Buffer.from(pubsubEvent.data.message.data, 'base64').toString()
  );
  if (pubsubData.costAmount <= pubsubData.budgetAmount) {
    return `No action necessary. (Current cost: ${pubsubData.costAmount})`;
  }

  if (!PROJECT_ID) {
    return 'No project specified';
  }

  const billingEnabled = await _isBillingEnabled(PROJECT_NAME);
  if (billingEnabled) {
    return _disableBillingForProject(PROJECT_NAME);
  } else {
    return 'Billing already disabled';
  }
};

const _isBillingEnabled = async projectName => {
  try {
    const [res] = await billing.getProjectBillingInfo({name: projectName});
    return res.billingEnabled;
  } catch (e) {
    console.log(
      'Unable to determine if billing is enabled on specified project, assuming billing is enabled'
    );
    return true;
  }
};

const _disableBillingForProject = async projectName => {
  const [res] = await billing.updateProjectBillingInfo({
    name: projectName,
    resource: {billingAccountName: ''}, // Disable billing
  });
  return `Billing disabled: ${JSON.stringify(res)}`;
};
EOF

# 5. Deploy the Cloud Run Function
gcloud functions deploy stop-billing-function \
    --gen2 \
    --runtime=nodejs22 \
    --region="${REGION}" \
    --trigger-topic="${TOPIC_ID}" \
    --entry-point=stopBilling \
    --set-env-vars GOOGLE_CLOUD_PROJECT="${PROJECT_ID}" \
    --source=./billing_function \
    --project="${PROJECT_ID}"

# 6. Configure Service Account Permissions
SERVICE_ACCOUNT=$(gcloud functions describe stop-billing-function --region="${REGION}" --format="value(serviceConfig.serviceAccountEmail)" --project="${PROJECT_ID}")

gcloud billing accounts add-iam-policy-binding "${BILLING_ACCOUNT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/billing.user"

# 7. Create the Budget and Link to Topic
gcloud billing budgets create \
    --billing-account="${BILLING_ACCOUNT_ID}" \
    --display-name="Budget for ${PROJECT_ID}" \
    --budget-amount="${BUDGET_AMOUNT}" \
    --threshold-rule=percent=100 \
    --notifications-rule-pubsub-topic="projects/${PROJECT_ID}/topics/${TOPIC_ID}"

echo "Setup complete. Billing will be disabled if costs exceed ${BUDGET_AMOUNT}."
