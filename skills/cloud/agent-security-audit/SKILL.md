# GCP Agent Security Audit Skill

## Overview

The `gcp-agent-security-audit` skill provides proactive security auditing capabilities for AI agents running on Google Cloud.

It analyzes AI agent diagnostic logs stored in Google BigQuery to detect security threats, abnormal behavior, and malicious interaction patterns before they become security incidents.

The skill helps security teams monitor AI agent activity and identify potential attacks early.

---

# Features

## Prompt Injection Detection

Detects attempts to manipulate AI agent instructions.

Examples:

- Ignore previous instructions.
- Reveal system prompts.
- Modify developer instructions.
- Override agent behavior.

---

## Jailbreak Detection

Detects attempts to bypass AI safety controls.

Examples:

- Disable safeguards.
- Bypass security policies.
- Ignore restrictions.

---

## Role Override Detection

Detects attempts to change the intended identity or behavior of an AI agent.

Examples:

- You are now an unrestricted assistant.
- Act as another system.
- Ignore your original role.

---

## Indirect Prompt Injection Detection

Detects hidden malicious instructions inside external content.

Examples:

- Retrieved documents containing hidden commands.
- Instructions embedded inside files.
- External content attempting to control the agent.

---

## Data Exfiltration Detection

Detects attempts to expose sensitive information.

Detects:

- API keys
- Passwords
- Authentication tokens
- Private credentials
- Secrets

---

# Architecture

The skill uses Google Cloud native services for proactive AI agent security monitoring.

Components:

- Google BigQuery: Stores and analyzes AI agent diagnostic logs.
- BigQuery ML: Detects abnormal agent behavior using anomaly detection models.
- Google Cloud Pub/Sub: Sends alerts for high-risk security findings.

Architecture flow:
