---
name: google-cloud-waf-security
metadata:
  version: "1.0.2"
  category: WellArchitectedFramework
description: >-
  Evaluates Google Cloud workloads and provides actionable recommendations for
  identity management, access control, permissions and roles, network and
  perimeter security, data security and encryption, security logging and threat
  detection, software supply chain hardening, AI security, data privacy,
  regulatory compliance, and cloud sovereignty. The recommendations are aligned
  with the Security, Privacy, and Compliance pillar of the Google Cloud
  Well-Architected Framework (WAF). Use when the user asks about firewall rules,
  zero trust, shared responsibility and shared fate, audit logging, security
  monitoring, threat mitigation, shift-left CI/CD security, Secure AI
  Framework (SAIF), data residency, or hardening Google Cloud resources.
  Don't use for other Well-Architected Framework pillars (Cost Optimization,
  Operational Excellence, Reliability, Performance Optimization, or
  Sustainability).
---

# Google Cloud Well-Architected Framework skill for the Security, Privacy, and Compliance pillar

## Usage attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Overview

The Security, Privacy, and Compliance pillar of the Google Cloud
Well-Architected Framework provides design principles and recommendations for
building a robust security posture by integrating security into every layer of
the architecture of your cloud workloads. It helps you maintain the
confidentiality and integrity of data and systems while ensuring compliance and
privacy. It provides a structured approach to risk management, threat defense,
and identity control, enabling you to operate cloud workloads securely and at
scale.

## Workflow

When this skill is activated, follow these steps to evaluate and improve the
security posture of the specified Google Cloud workload:

1.  **Understand the context**: Ask targeted questions from the **Workload
    assessment questions** list to gather information about the user's current
    architecture, security requirements, and constraints.
2.  **Analyze and identify gaps**: Evaluate the workload against the **Core
    principles** and the **Validation checklist** to identify security
    vulnerabilities, missing controls, or deviations from best practices.
3.  **Formulate recommendations**: Provide actionable, prioritized guidance
    based on the Google Cloud Well-Architected Framework. Recommend specific
    products from **Relevant Google Cloud products** to address the identified
    gaps.
4.  **Explain the recommendations**: Align all recommendations with the
    appropriate **Core principles** and state the benefits that each
    recommendation provides.
5.  **Iterate and refine**: Help the user adapt the recommendations to their
    specific requirements and constraints.

## Core principles

The recommendations in the security pillar of the Well-Architected Framework
are aligned with the following core principles:

-   **Implement security by design**: Choose system components that help to
    secure your workloads, build a layered security approach, and use hardened
    and attested infrastructure and services. Google Cloud encrypts data at rest
    and in transit by default; layer customer-managed or customer-supplied
    encryption keys (CMEK or CSEK) in Cloud KMS, VPC Service Controls
    perimeters, and Sensitive Data Protection for sensitive workloads. Grounding
    document:
    https://docs.cloud.google.com/architecture/framework/security/implement-security-by-design.md.txt

-   **Implement zero trust**: Apply a *never trust, always verify* approach.
    Authenticate and authorize every user, device, and workload request
    explicitly using identity, MFA, and device/location context; enforce least
    privilege and separation of duties; segment networks and private service
    paths; and continuously monitor network flows and audit logs.
    Grounding document:
    https://docs.cloud.google.com/architecture/framework/security/implement-zero-trust.md.txt

-   **Implement shift-left security**: Implement security controls early in the
    software development lifecycle. Avoid security defects before system changes
    are made. Detect and fix security bugs early, fast, and reliably after the
    system changes are committed. Google Cloud supports this principle through
    products like Cloud Build, Binary Authorization, and Artifact Registry.
    Grounding document:
    https://docs.cloud.google.com/architecture/framework/security/implement-shift-left-security.md.txt

-   **Implement preemptive cyber defense**: Apply the *Defender's Advantage*
    framework for cyber defense (Intelligence, Detect and Respond, Validate,
    Hunt, and Mission Control) based on your current cloud maturity, resource
    topology, and specific threat landscape. Validate and improve your
    defenses continuously. Grounding document:
    https://docs.cloud.google.com/architecture/framework/security/implement-preemptive-cyber-defense.md.txt

-   **Use AI securely and responsibly**: Apply Google's Secure AI Framework
    (SAIF) alongside AI governance principles (fairness, transparency,
    accountability, privacy, and security).
    -  **Use AI securely**: Define clear goals and requirements for AI usage,
       keep data secure and prevent loss or mishandling, keep AI pipelines
       secure and robust against tampering, deploy apps on secure systems using
       secure tools and artifacts, and protect and monitor inputs.
    -  **Use AI responsibly**: Use fairness indicators, use
       explainability tools, track data lineage, establish clear
       accountability, and implement differential privacy.
    Grounding documents:
    https://docs.cloud.google.com/architecture/framework/security/use-ai-securely-and-responsibly.md.txt
    and
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/security.md.txt

-   **Use AI for security**: Enhance threat detection and response with AI,
    simplify security for experts and non-experts, automate time-consuming
    security tasks with AI, incorporate AI into risk management and governance
    processes, and implement secure development practices for AI systems.
    Grounding document:
    https://docs.cloud.google.com/architecture/framework/security/use-ai-for-security.md.txt

-   **Meet regulatory, compliance, and privacy needs**: Identify and mitigate
    organizational risks, automate implementation of compliance requirements
    and monitor compliance, manage operational and software sovereignty, and
    control data residency, classify confidential data, and protect sensitive
    data. Grounding document:
    https://docs.cloud.google.com/architecture/framework/security/meet-regulatory-compliance-and-privacy-needs.md.txt

-   **Shared responsibilities and shared fate on Google Cloud**: Understand the
    division between security *of* the cloud (owned by Google: physical security
    of data centers, hardware, hypervisors, core networking, and storage, and
    inherited controls like default encryption) and security *in* the cloud
    (owned by you: data, access policies, and workload-specific configurations
    shaped by your requirements and industry regulations), reinforced by
    Google's active Shared Fate partnership (attested blueprints and Risk
    Protection Program). Customer operational responsibility varies by service
    model—it is greater in IaaS (such as patching guest OSs on Compute Engine
    VMs) than in managed PaaS or serverless services (such as Cloud Run).
    Grounding document:
    https://docs.cloud.google.com/architecture/framework/security/shared-responsibility-shared-fate.md.txt

## Relevant Google Cloud products

The following are _examples_ of Google Cloud products and features that are
relevant to security:

- **Identity and access management**

  - **Cloud Identity**: Manage user lifecycles, authentication, and identity
    federation.
  - **Identity and Access Management (IAM)**: Fine-grained access control for
    Google Cloud resources.
  - **Identity-Aware Proxy (IAP)**: Secure access to applications and VMs
    without public IP addresses or a VPN.
  - **Chrome Enterprise Premium**: Endpoint security and context-aware access.
  - **IAM Recommender**: Policy intelligence to identify and remove
    over-privileged access.

- **Network and perimeter security**

  - **Google Cloud Armor**: DDoS protection and Web Application Firewall (WAF).
  - **VPC Service Controls**: Security perimeters to prevent data exfiltration.
  - **Cloud Next-Generation Firewall (NGFW)**: Advanced threat protection for
    network traffic.
  - **Shared VPC**: Centralized network management across projects.
  - **Cloud Interconnect and IPsec VPN**: Secure, private connectivity.
  - **Private Service Connect**: Private access to managed services.

- **Data security**

  - **Cloud Key Management Service (KMS)**: Manage encryption keys.
  - **Sensitive Data Protection (formerly Cloud DLP)**: Discover and redact
    sensitive data.
  - **Confidential Computing**: Encrypt data in use (memory).

- **Security operations (SecOps)**

  - **Google SecOps (Chronicle)**: Threat detection and security analytics.
  - **Security Command Center (SCC)**: Centralized vulnerability and threat
    management.
  - **Cloud Logging and Cloud Monitoring**: Visibility into administrative and
    data-access activity and log-based alerts for unauthorized access events.
  - **BigQuery**: Storing exported logs for long-term security analysis.

- **Automation and supply chain**

  - **Cloud Build**: Secure CI/CD pipelines.
  - **Artifact Analysis**: Vulnerability scanning for container images.
  - **Binary Authorization**: Deploy-time policy enforcement.
  - **Assured open source software**: Use secured OSS packages.

## Workload assessment questions

Ask appropriate questions to understand the security-related requirements and
constraints of the workload and the user's organization. Choose questions from
the following list:

- **Security by design**:

  - How do you incorporate security considerations into your project's initial
    planning and design phases?
  - How do you define and document security requirements for new applications
    and services?
  - How do you ensure that security is integrated into your development
    lifecycle?
  - What tools and techniques do you use to perform threat modeling during the
    design phase?
  - How do you manage and prioritize security vulnerabilities discovered during
    the design and development process?
  - How do you handle security updates and patches for your applications and
    infrastructure?
  - How do you document and communicate security design decisions to your team
    and stakeholders?
  - How do you ensure that security configurations are consistently applied
    across your environments?
  - How do you validate the effectiveness of your security controls and
    measures?
  - How do you handle security exceptions and deviations from your security
    design?

- **Zero trust**:

  - How do you verify and authenticate users and devices accessing your Google
    Cloud resources?
  - How do you implement the principle of least privilege for access control?
  - How do you monitor and control network traffic within your Google Cloud
    environment?
  - How do you secure data in transit and at rest in your Google Cloud
    environment?
  - How do you implement continuous monitoring and logging of user and device
    activity?
  - How do you handle and respond to security incidents and breaches in a Zero
    Trust environment?
  - How do you manage and update security policies and controls in a Zero Trust
    environment?
  - How do you ensure that third-party applications and services comply with
    your Zero Trust principles?
  - How do you handle remote access and BYOD devices in a Zero Trust
    environment?
  - How do you educate and train your employees on Zero Trust principles and
    practices?

- **Shift-left security**:

  - How do you integrate security testing into your development pipeline early
    in the process?
  - What types of security testing do you perform during the development phase?
  - How do you provide developers with feedback on security vulnerabilities and
    best practices?
  - How do you empower developers to take ownership of security in their code?
  - How do you ensure that security requirements are clearly defined and
    communicated to developers?
  - How do you measure the effectiveness of your Shift Left security
    initiatives?
  - How do you handle security dependencies and third-party libraries in your
    code?
  - How do you manage and update security configurations in your development
    environment?
  - How do you handle security exceptions and deviations from your security
    policies in development?
  - How do you promote a culture of security awareness and responsibility among
    developers?

- **Preemptive cyber defense**:

  - How do you proactively identify and mitigate potential security threats
    before they impact your systems?
  - What tools and techniques do you use for continuous security monitoring and
    analysis?
  - How do you respond to and remediate security alerts and incidents?
  - How do you simulate and test your incident response plans?
  - How do you stay up-to-date with the latest security threats and
    vulnerabilities?
  - How do you handle and mitigate DDoS attacks against your applications and
    services?
  - How do you protect your sensitive data from insider threats?
  - How do you ensure that your security controls are effective against advanced
    persistent threats (APTs)?
  - How do you handle security vulnerabilities in your supply chain?
  - How do you adapt your security posture to evolving threats and technologies?

- **Security of AI workloads**:

  - How do you ensure the security of your AI models and data?
  - How do you address potential biases and ethical concerns in your AI models?
  - How do you protect your AI models from adversarial attacks and data
    poisoning?
  - How do you ensure the privacy of data used in your AI models?
  - How do you explain and interpret the decisions made by your AI models?
  - How do you manage and control access to your AI models and data?
  - How do you ensure compliance with regulations and standards related to
    AI and ML?
  - How do you monitor and detect anomalies in the behavior of your AI models?
  - How do you handle and respond to security incidents involving your AI
    models?
  - How do you educate and train your employees on the secure and responsible
    use of AI and ML?

- **AI for security**:

  - How do you leverage AI and ML to enhance your security posture?
  - What types of AI models do you use for security purposes?
  - How do you train and validate your AI models for security applications?
  - How do you ensure the accuracy and reliability of AI-based security
    systems?
  - How do you handle false positives and false negatives from AI-based
    security systems?
  - How do you integrate AI-based security systems with your existing security
    infrastructure?
  - How do you manage and update your AI models for security applications?
  - How do you explain and interpret the decisions made by your AI models for
    security applications?
  - How do you ensure the ethical and responsible use of AI and ML for security
    purposes?
  - How do you measure the effectiveness of AI and ML in improving your security
    posture?

- **Regulatory compliance and privacy**:

  - What regulatory compliance frameworks and privacy standards do you need to
    adhere to?
  - How do you assess and manage compliance risks in your Google Cloud
    environment?
  - How do you ensure the privacy of sensitive data stored and processed in
    Google Cloud?
  - How do you handle data subject requests (DSRs) related to privacy
    regulations?
  - How do you document and track compliance activities and evidence?
  - How do you ensure that third-party vendors and partners comply with your
    regulatory and privacy requirements?
  - How do you handle data breaches and security incidents related to compliance
    regulations?
  - How do you stay up-to-date with changes in regulatory compliance and privacy
    standards?
  - How do you educate and train your employees on regulatory compliance and
    privacy requirements?
  - How do you demonstrate and prove compliance to auditors and regulators?

## Validation checklist

Use the following checklist to evaluate the architecture's alignment with
security recommendations:

- **Security by design**:

  - Are system components selected based on their security features and
    hardening?
  - Is defense-in-depth implemented at the network, host, and application
    layers?
  - Are safe libraries and application frameworks used to prevent common
    vulnerabilities?
  - Is a risk assessment performed using industry standards?

- **Zero trust**:

  - Is Cloud Identity used as a centralized identity provider for managing user
    lifecycles and federation?
  - Is access control enforced based on user identity and context (device,
    location)?
  - Are private connectivity methods (Cloud Interconnect, VPN) used for internal
    traffic?
  - Are default networks disabled in all projects?
  - Are VPC Service Controls perimeters established around sensitive data?

- **Shift-left security**:

  - Is infrastructure provisioned using Infrastructure as Code
    (e.g., Terraform)?
  - Are automated security scans integrated into the CI/CD pipeline?
  - Is there a process for scanning and patching vulnerabilities in
    dependencies?
  - Is Binary Authorization used to ensure only trusted images are deployed?

- **Preemptive cyber defense**:

  - Is threat intelligence integrated into security operations?
  - Is security logging enabled and centralized for all critical resources?
  - Are automated responses configured for common security threats?
  - Are defenses validated through periodic testing or red-teaming?

- **AI security and governance**:

  - Are AI pipelines secured against tampering and data poisoning?
  - Is differential privacy or data masking used for training data where
    appropriate?
  - Are explainability techniques such as feature attributions used for model
    governance?
