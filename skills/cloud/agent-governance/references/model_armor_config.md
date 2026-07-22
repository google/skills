# Model Armor Configuration Reference

Model Armor provides guardrails and content safety filtering for agent inputs and outputs, mitigating prompt injection, jailbreaks, PII exposure, and unsafe content.

---

## 1. Template Specification (`ma-template.yaml`)

```yaml
name: "projects/$PROJECT_ID/locations/$LOCATION_ID/templates/agent-safety-template"
filterConfig:
  promptInjectionFilterConfig:
    enforcement: ENFORCE # Options: AUDIT, ENFORCE
    sensitivityLevel: HIGH
  piiFilterConfig:
    enforcement: ENFORCE
    rules:
      - piiType: CREDIT_CARD_NUMBER
        action: REDACT
      - piiType: US_SOCIAL_SECURITY_NUMBER
        action: REDACT
      - piiType: EMAIL_ADDRESS
        action: INSPECT_AND_BLOCK
  contentSafetyFilterConfig:
    enforcement: ENFORCE
    harmCategories:
      - category: HARM_CATEGORY_HATE_SPEECH
        threshold: BLOCK_LOW_AND_ABOVE
      - category: HARM_CATEGORY_DANGEROUS_CONTENT
        threshold: BLOCK_MEDIUM_AND_ABOVE
```

---

## 2. Gateway Service Extension Binding (`extension-config.yaml`)

```yaml
name: "projects/$PROJECT_ID/locations/$LOCATION_ID/authzExtensions/ma-extension"
description: "Model Armor Extension for Agent Gateway"
failOpen: false
service: "modelarmor.googleapis.com"
template: "projects/$PROJECT_ID/locations/$LOCATION_ID/templates/agent-safety-template"
```

---

## 3. CLI Deployment Workflow (Tier M)

### Step 1: Import Policy Template
```bash
gcloud model-armor policies import my-policy \
    --source=ma-template.yaml \
    --location=$LOCATION_ID \
    --project=$PROJECT_ID
```

### Step 2: Bind to Gateway Authz Extension
```bash
gcloud service-extensions authz-extensions import ma-extension \
    --source=extension-config.yaml \
    --location=$LOCATION_ID \
    --project=$PROJECT_ID
```
