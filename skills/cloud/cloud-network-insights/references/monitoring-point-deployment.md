# Monitoring Point Deployment and Troubleshooting Reference

Cloud Network Insights supports 7 distinct Monitoring Point deployment types
across container, Kubernetes, cloud virtual appliances, and on-premises
hypervisors (`container`, `helm`, `gce-vm`, `aws-ec2`, `azure-vm`, `vmware`, and
`kvm`).

## Contents

-   [1. CLI and Bundle Inspection Workflow](#1-cli-and-bundle-inspection-workflow)
-   [2. Platform Summary, Setup, and Model-Specific Troubleshooting Links](#2-platform-summary-setup-and-model-specific-troubleshooting-links)
-   [3. Registration and Status Verification](#3-registration-and-status-verification)

## 1. CLI and Bundle Inspection Workflow

1.  **Inspect Download CLI Flags**: Run `--help` to check required and optional
    flags for the target platform:

    ```bash
    gcloud network-management network-monitoring-providers monitoring-points download-install-script --help
    ```

    -   All types require `--network-monitoring-provider=PROVIDER_ID` (where
        `PROVIDER_ID` is `external` when enabled via the Google Cloud console,
        or a custom provider ID), `--location=global`,
        `--monitoring-point-type=MONITORING_POINT_TYPE`,
        `--hostname=HOSTNAME`, `--output-file=OUTPUT_FILE`, and
        `--project=PROJECT_ID`.
    -   On-premises hypervisors (`vmware`, `kvm`) additionally require
        `--password`, `--time-zone`, and either `--use-dhcp` or static IP flags
        (`--static-ip-address`, `--netmask`, `--gateway-address`,
        `--dns-server-address`).

2.  **Inspect Extracted Bundle and Official Documentation**:

    -   After downloading and extracting the archive (`.tar.gz` or `.zip`),
        inspect the files inside the bundle (`README.md`, `./setup.sh --help`,
        `template.yaml`, `main.bicep`, or Terraform variables).
    -   Consult the official Google Cloud and Broadcom TechDocs links below for
        platform prerequisites, firewall rules, installation steps, and
        model-specific troubleshooting procedures.

--------------------------------------------------------------------------------

## 2. Platform Summary, Setup, and Model-Specific Troubleshooting Links

| `--monitoring-point-type` | Target Platform | Bundle Contents and Deployment | Official Setup and Troubleshooting Documentation |
| :--- | :--- | :--- | :--- |
| `container` | Docker / Podman (`c50-Docker/Podman`) | `compose.HOSTNAME.tar.gz` → `./setup.sh install -y -z -n host` (see [Container Monitoring Point notes](#container-monitoring-point-notes)); check status via `/bin/bash setup.sh status` or `docker ps` / `sudo podman ps` | • [Google Cloud: Deploy Container MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-container-monitoring-points)<br>• [Broadcom: c50-Docker/Podman Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/docker-mp-intro/docker-setup/docker-mp-setup-cmp.html)<br>• [Broadcom: c50-Docker/Podman Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/docker-mp-intro/docker-setup/docker-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: c50-Docker/Podman View Status](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/docker-mp-intro/docker-access/docker-mp-view-monitoring-point-status.html) |
| `helm` | Kubernetes / GKE / EKS / AKS (`c50-Kubernetes (Helm)`) | `helm.HOSTNAME.tar.gz` → `helm upgrade --install appneta-mp ./chart --namespace NAMESPACE --create-namespace`; locate namespace/workload via `kubectl get statefulsets -A -l app=c50` and inspect `statefulsets` / `pods` | • [Google Cloud: Deploy Container MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-container-monitoring-points)<br>• [Broadcom: c50-Kubernetes (Helm) Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/kubernetes-mp-intro/kubernetes-setup/kubernetes-mp-setup-cmp.html)<br>• [Broadcom: c50-Kubernetes (Helm) Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/kubernetes-mp-intro/kubernetes-setup/kubernetes-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: c50-Kubernetes (Helm) View Status](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/kubernetes-mp-intro/kubernetes-access/kubernetes-mp-view-monitoring-point-status.html) |
| `gce-vm` | Compute Engine Appliance (`Google CE`) | `terraform.HOSTNAME.zip` → `terraform init && terraform apply -var="project_id=PROJECT_ID" -var="zone=ZONE" -var='networks=["NETWORK"]' -var='subnets=["SUBNET"]'` | • [Google Cloud: Deploy GCE MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-gce-monitoring-points)<br>• [Broadcom: GCE Terraform Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/gce-mp-intro/gce-setup/gce-mp-setup-cloud-mp.html#mp-setup-cmp_deploy-terraform)<br>• [Broadcom: Google CE Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/gce-mp-intro/gce-setup/gce-mp-troubleshooting-connectivity-to-appneta.html) |
| `aws-ec2` | AWS EC2 CloudFormation (`AWS EC2`) | `cloudformation.HOSTNAME.zip` (`template.yaml` + `appneta-parameters.json`) → `aws cloudformation create-stack --region REGION --stack-name STACK_NAME --template-body file://template.yaml --parameters file://appneta-parameters.json --capabilities CAPABILITY_IAM` (or AWS Quick-Create Link) | • [Google Cloud: Deploy AWS MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-aws-monitoring-points)<br>• [Broadcom: AWS EC2 Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/aws-ec2-mp-intro/aws-ec2-setup/aws-ec2-mp-setup-cloud-mp.html)<br>• [Broadcom: AWS EC2 Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/aws-ec2-mp-intro/aws-ec2-setup/aws-ec2-mp-troubleshooting-connectivity-to-appneta.html) |
| `azure-vm` | Microsoft Azure Bicep / ARM (`Azure VM`) | `bicep.HOSTNAME.zip` (`main.bicep` + `appneta.bicepparam`) → `az deployment group create --resource-group RESOURCE_GROUP --template-file main.bicep --parameters appneta.bicepparam` (verify NSG outbound TCP `443`, UDP `123`, DNS `53` if provisioning times out) | • [Google Cloud: Deploy Azure MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-azure-monitoring-points)<br>• [Broadcom: Azure Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/azure-vm-mp-intro/azure-vm-setup/azure-vm-mp-setup-cloud-mp.html)<br>• [Broadcom: Azure VM Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/azure-vm-mp-intro/azure-vm-setup/azure-vm-mp-troubleshooting-connectivity-to-appneta.html) |
| `vmware` | VMware vSphere / ESXi OVA (`v35-VMware`) | `vmware.HOSTNAME.zip` (`parameters.json` / `ovf-env.xml`) → Deploy Broadcom v35 OVA template in vSphere Client; verify via Web Admin (in **General** > **Monitoring Point Connected**, **System Status** > **System Time** and **NTP Synchronized**, **Network State** > **eth0**, and **Monitoring Point Health** > **Server Reachability**) | • [Google Cloud: Deploy VMware and KVM MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-vms-monitoring-points)<br>• [Broadcom: vSphere OVA Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-vmware-mp-intro/v35-vmware-setup/v35-vmware-mp-setup-v35-vmware.html)<br>• [Broadcom: v35-VMware Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-vmware-mp-intro/v35-vmware-setup/v35-vmware-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: v35-VMware Server Reachability Test](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-vmware-mp-intro/v35-vmware-management/v35-vmware-mp-check-server-reachability.html) |
| `kvm` | Linux KVM / QEMU QCOW2 (`v35-KVM`) | `kvm.HOSTNAME.zip` (`config.iso`) → Import Broadcom QCOW2 disk image into KVM/libvirt with `config.iso` attached; verify via Web Admin (in **General** > **Monitoring Point Connected**, **System Status** > **System Time** and **NTP Synchronized**, **Network State** > **eth0**, and **Monitoring Point Health** > **Server Reachability**) | • [Google Cloud: Deploy VMware and KVM MPs](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-vms-monitoring-points)<br>• [Broadcom: KVM QCOW2 Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-kvm-mp-intro/v35-kvm-setup/v35-kvm-mp-setup-v35-kvm.html)<br>• [Broadcom: v35-KVM Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-kvm-mp-intro/v35-kvm-setup/v35-kvm-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: v35-KVM Server Reachability Test](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-kvm-mp-intro/v35-kvm-management/v35-kvm-mp-check-server-reachability.html) |

### Container Monitoring Point notes

-   **`setup.sh install` flags**: `-y` runs non-interactively, `-z` uses the
    default timezone, `-n host` uses host networking (use `-n bridge` only if
    host networking isn't possible on the host), and `-w overwrite` replaces an
    existing configuration.
-   **Private Service Connect**: Pass `-e .private.env` immediately after the
    subcommand; otherwise `setup.sh` ignores it and uses the public `.env`:

    ```bash
    ./setup.sh install -e .private.env -y -z -n host -w overwrite
    /bin/bash setup.sh status -e .private.env
    ```

-   **Docker Compose**: `setup.sh` doesn't work with legacy `docker-compose` v1.
    If v1 is installed (such as from Debian apt), `setup.sh` prompts and fails
    with `invalid reference format`; ask the user before removing v1 or
    installing `docker-compose-plugin`, because either changes the host. With no
    Compose installed, `setup.sh` uses its built-in `compose-in-docker` runner.

--------------------------------------------------------------------------------

## 3. Registration and Status Verification

Verify that deployed Monitoring Points across any platform have registered with
Cloud Network Insights (`ONLINE` vs `OFFLINE`):

```bash
gcloud network-management network-monitoring-providers monitoring-points list \
  --network-monitoring-provider=PROVIDER_ID \
  --location=global \
  --project=PROJECT_ID
```
