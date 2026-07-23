# Model Armor Filter Templates

Deploy these schemas to prevent prompt injection and secure egress payloads from exfiltrating sensitive company details.

### Standard PII & Jailbreak Filter Template (`ma-template.yaml`)

This template blocks common PII formats, enforces basic safety limits, and activates real-time injection protection.

```yaml
policy:
  rules:
  - ruleId: block_pii
    displayName: Exfiltration Block
    infoTypes: [EMAIL_ADDRESS, PHONE_NUMBER, US_SOCIAL_SECURITY_NUMBER]
    blockingConfig: {}
  - ruleId: safety_filter
    displayName: Core Safety Filters
    raiSettingsFilters:
    - filterType: HATE_SPEECH
      confidenceLevel: MEDIUM_AND_ABOVE
    - filterType: HARASSMENT
      confidenceLevel: MEDIUM_AND_ABOVE
  - ruleId: jailbreak_prevention
    displayName: Prompt Injection Guard
    piAndJailbreakFilterSettings:
      enforcement: ENABLED
```

### Gateway Integration config (`extension-config.yaml`)

This configuration registers the service extension with the gateway.

```yaml
name: projects/PROJECT_ID/locations/LOCATION_ID/authorizationExtensions/ma-extension
authority: projects/PROJECT_ID/locations/LOCATION_ID/authorities/my-auth-service
forwardHeaders: ["Authorization"]
failOpen: false
timeout: 0.5s
```
