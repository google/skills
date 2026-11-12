# gcloud CLI Usage

This document provides reference information for installing, authorizing, and
configuring the Google Cloud SDK (`gcloud` CLI) in local and automated
environments.

## Installation

If the `gcloud` binary is not installed in the execution environment, refer to
the authoritative
[Google Cloud CLI Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)
for platform-specific installation instructions (Linux, macOS, Windows, package
managers, and container images).

> [!CAUTION]
> **Explicit User Confirmation Required Before Installing `gcloud` CLI:**
> Never install the Google Cloud CLI (`gcloud` CLI) or additional `gcloud` CLI
> components (`gcloud components install` / `gcloud components update`)
> autonomously.
>
> Before executing any installation command or package manager script:
> 1. Inform the user that the `gcloud` CLI (or required component) is not
>    installed and summarize the installation method you plan to use.
> 2. Ask the user for explicit consent: `"I am ready to install the Google Cloud
>    CLI (gcloud) on your machine. Do you want me to proceed?"`
> 3. **CRITICAL**: The agent **MUST NOT** execute any `gcloud` installation or
>    component installation commands during this turn. You must ask the consent
>    query and **strictly stop** to wait for the user's positive affirmation.

### Component Management

The `gcloud components` command group manages optional CLI components (such as
additional tools, emulators, and language runtimes):

-   **List available components:**

    ```bash
    gcloud components list
    ```

-   **Install a component:**

    ```bash
    gcloud components install {component_id} --quiet
    ```

-   **Update all installed components:**

    ```bash
    gcloud components update --quiet
    ```

*(Note: If `gcloud` was installed via a system package manager like APT or DNF,
use the system package manager to install components instead of `gcloud
components install`.)*

## Authorization & Authentication

Authenticate the CLI with Google Cloud according to the operational environment:

-   **User Account (Interactive):**

    ```bash
    gcloud auth login
    ```

    Follow the browser prompts to sign in and grant access.

-   **User Account (Headless Flow):**

    For environments without an accessible web browser (containers, remote SSH):

    ```bash
    gcloud auth login --no-browser
    ```

    Copy the generated URL, open it on another machine to complete sign-in, and
    paste the authorization code back into the terminal.

-   **Application Default Credentials (ADC):**

    Configures credentials for client libraries and local applications:

    ```bash
    gcloud auth application-default login
    ```

    Append `--no-browser` in headless environments.

-   **Service Account Key (Headless Automation):**

    ```bash
    gcloud auth activate-service-account --key-file=path/to/key.json
    ```

    *Security note: Restrict file permissions on JSON keys or prefer Workload
    Identity / Impersonation.*

-   **Service Account Impersonation (Preferred for Development & Agents):**

    Allows a user identity to temporarily assume a service account identity
    without storing long-lived private key files:

    ```bash
    gcloud config set auth/impersonate_service_account {service_account_email}
    ```

    Requires the `roles/iam.serviceAccountTokenCreator` role on the target
    service account. This enforces least privilege and ensures audited access
    under the target identity.

-   **Workload Identity Federation:**

    For CI/CD and external compute environments (GitHub Actions, AWS, on-prem),
    authenticate using federated tokens without managing service account keys.
    See
    [Authenticate for the gcloud CLI](https://docs.cloud.google.com/sdk/docs/authenticate.md.txt).

## Local Configuration Management

The `gcloud config` command group manages local configuration settings,
profiles, and default properties.

### Named Configurations

Configurations allow maintaining multiple isolated sets of properties (e.g.,
dev, staging, prod):

-   **Create a new configuration:**

    ```bash
    gcloud config configurations create {config_name}
    ```

-   **List existing configurations:**

    ```bash
    gcloud config configurations list
    ```

-   **Activate a configuration:**

    ```bash
    gcloud config configurations activate {config_name}
    ```

### Setting Common Properties

Properties set default values for flags across `gcloud` invocations:

-   **Set active project:**

    ```bash
    gcloud config set core/project {project_id}
    ```

-   **Set default compute region and zone:**

    ```bash
    gcloud config set compute/region {region}
    gcloud config set compute/zone {zone}
    ```

-   **View all active configuration properties:**

    ```bash
    gcloud config list
    ```
