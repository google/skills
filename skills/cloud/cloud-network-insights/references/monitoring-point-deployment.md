# Monitoring Point Deployment and Troubleshooting Reference

Cloud Network Insights supports 7 distinct Monitoring Point deployment types
across container, Kubernetes, cloud virtual appliances, and on-premises
hypervisors (`container`, `helm`, `gce-vm`, `aws-ec2`, `azure-vm`, `vmware`, and
`kvm`).

## Contents

-   [1. Download the Bundle](#1-download-the-bundle): Lines 24-51
-   [2. Platform Summary](#2-platform-summary): Lines 55-65
-   [3. Container (c50) Monitoring Point](#3-container-c50-monitoring-point): Lines 69-202
    -   [Path A: Existing Host](#path-a-existing-host): Lines 78-105
    -   [Path B: New Compute Engine VM, No SSH](#path-b-new-compute-engine-vm-no-ssh): Lines 107-177
    -   [Container Notes](#container-notes): Lines 179-202
-   [4. Compute Engine Appliance](#4-compute-engine-appliance): Lines 206-340
    -   [Step 1: gcloud](#step-1-gcloud): Lines 225-277
    -   [Step 2: Terraform Bundle](#step-2-terraform-bundle): Lines 279-287
    -   [Step 3: Google Cloud Marketplace](#step-3-google-cloud-marketplace): Lines 289-318
    -   [Appliance Notes](#appliance-notes): Lines 320-340
-   [5. Registration and Status](#5-registration-and-status): Lines 344-360
-   [6. Host Cleanup](#6-host-cleanup): Lines 364-383

## 1. Download the Bundle

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

2.  **Keep the Bundle Private**: Save it in `WORK_DIR` (a private directory from
    `mktemp -d`). It contains the Monitoring Point's keys, so never print it or
    paste it into a command.

3.  **Inspect Extracted Bundle and Official Documentation**: After extracting
    the archive (`.tar.gz` or `.zip`), read the files inside it (`README.md`,
    `./setup.sh --help`, `template.yaml`, `main.bicep`, or Terraform variables)
    and the setup guide for the type in Section 2.

--------------------------------------------------------------------------------

## 2. Platform Summary

| `--monitoring-point-type` | Target Platform | Bundle Contents and Deployment | Official Setup and Troubleshooting Documentation |
| :--- | :--- | :--- | :--- |
| `container` | Docker / Podman (`c50-Docker/Podman`) | `compose.HOSTNAME.tar.gz` (extracts to `HOSTNAME/`) → `cd HOSTNAME && ./setup.sh install -y -z -n host`, or a startup script on a new Compute Engine VM (see [Container (c50) Monitoring Point](#3-container-c50-monitoring-point)); check status via `./setup.sh status` or `docker ps` / `sudo podman ps` | • [Google Cloud: Deploy Container MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-container-monitoring-points.md.txt)<br>• [Broadcom: c50-Docker/Podman Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/docker-mp-intro/docker-setup/docker-mp-setup-cmp.html)<br>• [Broadcom: c50-Docker/Podman Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/docker-mp-intro/docker-setup/docker-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: c50-Docker/Podman View Status](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/docker-mp-intro/docker-access/docker-mp-view-monitoring-point-status.html) |
| `helm` | Kubernetes / GKE / EKS / AKS (`c50-Kubernetes (Helm)`) | `helm.HOSTNAME.tar.gz` → `helm upgrade --install appneta-mp ./chart --namespace NAMESPACE --create-namespace`; locate namespace/workload via `kubectl get statefulsets -A -l app=c50` and inspect `statefulsets` / `pods` | • [Google Cloud: Deploy Container MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-container-monitoring-points.md.txt)<br>• [Broadcom: c50-Kubernetes (Helm) Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/kubernetes-mp-intro/kubernetes-setup/kubernetes-mp-setup-cmp.html)<br>• [Broadcom: c50-Kubernetes (Helm) Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/kubernetes-mp-intro/kubernetes-setup/kubernetes-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: c50-Kubernetes (Helm) View Status](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/kubernetes-mp-intro/kubernetes-access/kubernetes-mp-view-monitoring-point-status.html) |
| `gce-vm` | Compute Engine Appliance (`Google CE`) | `gcloud` with the appliance image and a generated `mp-config` (default); `terraform.HOSTNAME.zip` → `terraform init && terraform apply -var="project_id=PROJECT_ID" -var="zone=ZONE" -var='networks=["NETWORK"]' -var='subnets=["SUBNET"]' -var='external_ipv4_addresses=["EPHEMERAL"]'`; or Google Cloud Marketplace, only on request (see [Compute Engine Appliance](#4-compute-engine-appliance)) | • [Google Cloud: Deploy GCE MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-gce-monitoring-points.md.txt)<br>• [Broadcom: GCE Terraform Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/gce-mp-intro/gce-setup/gce-mp-setup-cloud-mp.html#mp-setup-cmp_deploy-terraform)<br>• [Broadcom: GCE Marketplace Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/gce-mp-intro/gce-setup/gce-mp-setup-cloud-mp.html#mp-setup-cmp_deploy-marketplace)<br>• [Broadcom: Google CE Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/gce-mp-intro/gce-setup/gce-mp-troubleshooting-connectivity-to-appneta.html) |
| `aws-ec2` | AWS EC2 CloudFormation (`AWS EC2`) | `cloudformation.HOSTNAME.zip` (`template.yaml` + `appneta-parameters.json`) → `aws cloudformation create-stack --region REGION --stack-name STACK_NAME --template-body file://template.yaml --parameters file://appneta-parameters.json --capabilities CAPABILITY_IAM` (or AWS Quick-Create Link) | • [Google Cloud: Deploy AWS MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-aws-monitoring-points.md.txt)<br>• [Broadcom: AWS EC2 Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/aws-ec2-mp-intro/aws-ec2-setup/aws-ec2-mp-setup-cloud-mp.html)<br>• [Broadcom: AWS EC2 Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/aws-ec2-mp-intro/aws-ec2-setup/aws-ec2-mp-troubleshooting-connectivity-to-appneta.html) |
| `azure-vm` | Microsoft Azure Bicep / ARM (`Azure VM`) | `bicep.HOSTNAME.zip` (`main.bicep` + `appneta.bicepparam`) → `az deployment group create --resource-group RESOURCE_GROUP --template-file main.bicep --parameters appneta.bicepparam` (verify NSG outbound TCP `443`, UDP `123`, DNS `53` if provisioning times out) | • [Google Cloud: Deploy Azure MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-azure-monitoring-points.md.txt)<br>• [Broadcom: Azure Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/azure-vm-mp-intro/azure-vm-setup/azure-vm-mp-setup-cloud-mp.html)<br>• [Broadcom: Azure VM Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/azure-vm-mp-intro/azure-vm-setup/azure-vm-mp-troubleshooting-connectivity-to-appneta.html) |
| `vmware` | VMware vSphere / ESXi OVA (`v35-VMware`) | `vmware.HOSTNAME.zip` (`parameters.json` / `ovf-env.xml`) → Deploy Broadcom v35 OVA template in vSphere Client; log in to its Web Admin UI and check (in **General** > **Monitoring Point Connected**, **System Status** > **System Time** and **NTP Synchronized**, **Network State** > **eth0**, and **Monitoring Point Health** > **Server Reachability**) | • [Google Cloud: Deploy VMware and KVM MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-vms-monitoring-points.md.txt)<br>• [Broadcom: vSphere OVA Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-vmware-mp-intro/v35-vmware-setup/v35-vmware-mp-setup-v35-vmware.html)<br>• [Broadcom: v35-VMware Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-vmware-mp-intro/v35-vmware-setup/v35-vmware-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: v35-VMware Server Reachability Test](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-vmware-mp-intro/v35-vmware-management/v35-vmware-mp-check-server-reachability.html) |
| `kvm` | Linux KVM / QEMU QCOW2 (`v35-KVM`) | `kvm.HOSTNAME.zip` (`config.iso`) → Import Broadcom QCOW2 disk image into KVM/libvirt with `config.iso` attached; log in to its Web Admin UI and check (in **General** > **Monitoring Point Connected**, **System Status** > **System Time** and **NTP Synchronized**, **Network State** > **eth0**, and **Monitoring Point Health** > **Server Reachability**) | • [Google Cloud: Deploy VMware and KVM MPs](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/deploy-vms-monitoring-points.md.txt)<br>• [Broadcom: KVM QCOW2 Setup](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-kvm-mp-intro/v35-kvm-setup/v35-kvm-mp-setup-v35-kvm.html)<br>• [Broadcom: v35-KVM Troubleshooting](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-kvm-mp-intro/v35-kvm-setup/v35-kvm-mp-troubleshooting-connectivity-to-appneta.html)<br>• [Broadcom: v35-KVM Server Reachability Test](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-overview/v35-kvm-mp-intro/v35-kvm-management/v35-kvm-mp-check-server-reachability.html) |

--------------------------------------------------------------------------------

## 3. Container (c50) Monitoring Point

The container Monitoring Point runs two containers (`sequencer` and `talos`) on
a Linux host with Docker or Podman. It authenticates to AppNeta with the keys in
its bundle, so its host needs outbound internet access but no service account.
On Google Cloud without a suitable host, confirm with the user before creating a
small VM (for example `e2-medium` with Debian 12, in the zone they want to
measure from), and use Path B.

### Path A: Existing Host

Use this path for a host that already exists and that you can reach over SSH;
if you can't, give these commands to the user to run on the host. Ask before
installing packages on it.

1.  Download the `container` bundle for the host's name (Section 1) as
    `WORK_DIR/compose.HOSTNAME.tar.gz` and copy it to the host, for example
    with `gcloud compute scp WORK_DIR/compose.HOSTNAME.tar.gz HOSTNAME:~
    --zone=ZONE --project=PROJECT_ID --ssh-flag="-o ConnectTimeout=10"
    --quiet`.
2.  If the host has neither Docker nor Podman, install `docker.io` (Compose v2
    isn't required) and add the SSH user to the `docker` group:

    ```bash
    sudo apt-get update && sudo apt-get install -y docker.io && sudo usermod -aG docker "$USER"
    ```

3.  Reconnect (so the group change applies and `setup.sh` runs without `sudo`),
    then extract the bundle and install from inside its directory:

    ```bash
    tar -xzf compose.HOSTNAME.tar.gz && cd HOSTNAME && ./setup.sh install -y -z -n host
    ./setup.sh status
    ```

If SSH times out or is refused, don't retry it and don't open TCP 22: give the
user these commands, or use Path B with a new VM.

### Path B: New Compute Engine VM, No SSH

The VM installs the Monitoring Point on its first boot with a startup script,
and the bundle travels in instance metadata, so this path needs no SSH access,
no firewall rule, and no service account. The Monitoring Point is usually
`ONLINE` about 2-3 minutes after the VM is created. The bundle holds only this
Monitoring Point's registration keys (the Compute Engine appliance keeps the
same kind of keys in its `mp-config` metadata), and step 5 removes it. Never
put AppNeta API calls or tokens in a startup script or metadata: anyone with
read access to the VM can read its metadata.

1.  Download the `container` bundle for the VM name you will create (Section 1)
    as `WORK_DIR/compose.HOSTNAME.tar.gz`, and encode it into a file (about
    30 KB; never print it):

    ```bash
    base64 < WORK_DIR/compose.HOSTNAME.tar.gz > WORK_DIR/compose.HOSTNAME.b64
    ```

2.  Save this startup script unchanged as `WORK_DIR/c50-startup.sh`, for example
    with a file-writing tool. It installs Docker, unpacks the bundle from
    metadata, runs `setup.sh install` from inside the bundle directory, and
    retries once if the installer exits with code 5 after updating itself:

```bash
#!/bin/bash
# Installs the c50 Monitoring Point from instance metadata on first boot.
set -o pipefail
[ -f /opt/cni/.installed ] && exit 0
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get -o DPkg::Lock::Timeout=300 install -y docker.io || exit 1
mkdir -p /opt/cni && cd /opt/cni || exit 1
curl -sf --max-time 30 -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/c50-bundle-b64" \
  | base64 -d | tar -xz || exit 1
cd /opt/cni/*/ || exit 1
./setup.sh install -y -z -n host
rc=$?
if [ "$rc" -eq 5 ]; then ./setup.sh install -y -z -n host; rc=$?; fi
[ "$rc" -eq 0 ] && touch /opt/cni/.installed
exit "$rc"
```

3.  Create the VM. It gets an ephemeral external IP for outbound access (add a
    Cloud NAT subnet instead if the user forbids external IPs):

    ```bash
    gcloud services enable compute.googleapis.com --project=PROJECT_ID
    gcloud compute instances create HOSTNAME --project=PROJECT_ID --zone=ZONE \
      --machine-type=e2-medium --image-family=debian-12 --image-project=debian-cloud \
      --network=NETWORK --subnet=SUBNET \
      --metadata-from-file=c50-bundle-b64=WORK_DIR/compose.HOSTNAME.b64,startup-script=WORK_DIR/c50-startup.sh \
      --no-service-account --no-scopes
    ```

4.  Poll `monitoring-points list` every 30 seconds until `HOSTNAME` is `ONLINE`
    (Section 5). If it isn't after 5 minutes, read the startup log from the
    serial port (read-only; no SSH):

    ```bash
    gcloud compute instances get-serial-port-output HOSTNAME --zone=ZONE \
      --project=PROJECT_ID | grep startup-script | tail -n 30
    ```

5.  Once it's `ONLINE`, remove the bundle from metadata (the startup script
    skips installed hosts on later boots):

    ```bash
    gcloud compute instances remove-metadata HOSTNAME --keys=c50-bundle-b64 \
      --zone=ZONE --project=PROJECT_ID
    ```

### Container Notes

-   **Working Directory**: The archive extracts into a `HOSTNAME/`
    subdirectory, and `setup.sh` sources `.util.sh` from the current directory,
    so `cd HOSTNAME` before running it. From any other directory it fails with
    `.util.sh: No such file or directory` and `PULL_LOG_PREFIX: unbound
    variable`. `./setup.sh --help` exits with `Could not find a compatible
    container engine` until Docker or Podman is installed.
-   **`setup.sh install` flags**: `-y` runs non-interactively, `-z` uses the
    default timezone, `-n host` uses host networking (use `-n bridge` only if
    host networking isn't possible on the host), and `-w overwrite` replaces an
    existing configuration.
-   **Status**: Run `./setup.sh status`, which lists the `sequencer` and `talos`
    containers. Don't wrap it in `sudo /bin/bash`: `docker` group members don't
    need root, and security policies that block root shells reject that form.
-   **Private Service Connect**: Pass `-e .private.env` immediately after the
    subcommand; otherwise `setup.sh` ignores it and uses the public `.env`:
    `./setup.sh install -e .private.env -y -z -n host -w overwrite`, then
    `./setup.sh status -e .private.env`.
-   **Docker Compose**: `setup.sh` doesn't work with legacy `docker-compose` v1.
    If v1 is installed (such as from Debian apt), `setup.sh` prompts and fails
    with `invalid reference format`; ask the user before removing v1 or
    installing `docker-compose-plugin`, because either changes the host. With no
    Compose installed, `setup.sh` uses its built-in `compose-in-docker` runner.

--------------------------------------------------------------------------------

## 4. Compute Engine Appliance

The `gce-vm` Monitoring Point is a Broadcom appliance image that Google Cloud
Marketplace also lists. The VM name becomes the Monitoring Point name. Ask the
user which zone to deploy in, because the appliance is the source of its paths;
default to `us-central1-a` (see
[Regions and zones](https://docs.cloud.google.com/compute/docs/regions-zones.md.txt)).

Deploy it yourself with `gcloud` (Step 1): it needs no browser, no service
account, and no terms step. Only the Marketplace page shows its listing's
terms, so don't send the user there or ask about those terms unless the user
asks for Marketplace.

| Order | Path | Use when | Requires |
| :--- | :--- | :--- | :--- |
| 1 | `gcloud` with the appliance image | Default | `roles/compute.instanceAdmin.v1` |
| 2 | Terraform bundle | The user wants Terraform | Terraform 1.5.7 or later (ask before installing it); `roles/compute.admin` on the project and `roles/iam.serviceAccountUser` on the VM's service account |
| 3 | Google Cloud Marketplace | The user asks for Marketplace | Browser; `roles/config.admin` and `roles/consumerprocurement.entitlementManager` on the project; a deployment service account with `roles/config.agent`, `roles/compute.admin`, and `roles/iam.serviceAccountUser` |

### Step 1: gcloud

The appliance authenticates to AppNeta with the device key in its `mp-config`
metadata, so its VM needs no service account.

1.  Get `SOURCE_IMAGE` from the `gce-vm` bundle. Print only that line, because
    the file also holds the device key:

    ```bash
    gcloud network-management network-monitoring-providers monitoring-points download-install-script \
      --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID \
      --monitoring-point-type=gce-vm --hostname=HOSTNAME --output-file=WORK_DIR/terraform.HOSTNAME.zip
    unzip -p WORK_DIR/terraform.HOSTNAME.zip terraform.tfvars | grep '^source_image'
    ```

    Use `source_image` from `terraform.tfvars`, not the `variables.tf` default,
    which can be older. The listing's **Command-Line Deployment** tab shows the
    same image.
2.  Create `WORK_DIR/mp-config.yaml`. If the user saved the console snippet, use
    that file unchanged. Otherwise generate the configuration; the appliance
    reads a top-level `configurations:` list, so unwrap the `config` key:

    ```bash
    gcloud network-management network-monitoring-providers generate-monitoring-point-config \
      PROVIDER_ID --location=global --project=PROJECT_ID --format=json \
      | python3 -c 'import json,sys,yaml; sys.stdout.write(yaml.safe_dump(json.load(sys.stdin)["config"], default_flow_style=False, sort_keys=False))' \
      > WORK_DIR/mp-config.yaml
    ```

    If Python's `yaml` module is missing, replace `--format=json | python3 ...`
    with `--format="yaml(config)" | sed '1d; s/^  //'`. Never print any part of
    the file, because it holds the device key; to check it, run
    `grep -c '^configurations:' WORK_DIR/mp-config.yaml` (expect `1`). To add
    another appliance, reuse this file or generate it again; don't read it back
    from an existing VM's metadata.
3.  Create the VM:

    ```bash
    gcloud services enable compute.googleapis.com --project=PROJECT_ID
    gcloud compute instances create HOSTNAME --project=PROJECT_ID --zone=ZONE \
      --machine-type=e2-standard-2 --image=SOURCE_IMAGE \
      --boot-disk-size=24GB --boot-disk-type=pd-balanced \
      --network-interface=network=NETWORK,subnet=SUBNET,nic-type=GVNIC \
      --metadata-from-file=mp-config=WORK_DIR/mp-config.yaml \
      --no-service-account --no-scopes
    ```

    `--no-service-account --no-scopes` also avoids `iam.serviceAccounts.actAs`
    errors on the default service account; the trade-off is no Ops Agent logs or
    metrics.
4.  Poll `monitoring-points list` every 30 seconds (Section 5). The appliance is
    usually `ONLINE` (`type: Google CE`) about 3 minutes after the VM is
    created.

### Step 2: Terraform Bundle

Extract `terraform.HOSTNAME.zip` (Step 1, item 1) and run `terraform init &&
terraform apply` with `-var="project_id=PROJECT_ID" -var="zone=ZONE"
-var='networks=["NETWORK"]' -var='subnets=["SUBNET"]'
-var='external_ipv4_addresses=["EPHEMERAL"]'`. The module assigns no external IP
by default, so keep `external_ipv4_addresses` unless the subnet has Cloud NAT.
It uses the Compute Engine default service account unless
`service_account_email` is set. Remove it with `terraform destroy`.

### Step 3: Google Cloud Marketplace

Use this path only when the user asks for Marketplace. With a browser tool, do
these steps yourself; otherwise send them to the user and ask for the result or
the exact error:

1.  In the Google Cloud console, open **Network Intelligence Center** > **Cloud
    Network Insights** > **Monitoring Points**, click **Add Monitoring Point**,
    set **Platform Type** to **Google Cloud**, click **Continue**, enter
    `HOSTNAME` as the **Hostname**, click **Continue**, select **Google Cloud
    Marketplace** and the project, copy the **Monitoring point configuration**
    snippet with its copy button, and click **Open through Google Cloud
    Marketplace**.
2.  Click **Get Started**. If the listing asks you to accept its terms, follow
    `SKILL.md` Rule 3: with a browser tool, summarize their main points (who
    provides the product, pricing, and license), say that the listing's full
    terms are what apply, and accept them only after an explicit yes or the
    user's explicit prior approval of all terms. Then click **Deploy**, and
    enable the Infrastructure Manager API (`config.googleapis.com`) if
    prompted.
3.  Select a deployment service account and an instance service account. Under
    **Network interfaces**, assign an external IP unless the subnet has Cloud
    NAT, paste the snippet into **Monitoring Point configuration**, and click
    **Deploy**. Choosing **New account** grants IAM roles, so confirm that with
    the user first.

Success signal: the deployment finishes and `HOSTNAME` appears in
`monitoring-points list`. If the form can't detect the default service account,
reports missing `config.deployments.*` permissions, or the user can't continue,
offer Step 1 instead of retrying.

### Appliance Notes

-   **Configuration Handling**: Pass the configuration file unchanged with
    `--metadata-from-file` (or paste it into the Marketplace field). Shells can
    rewrite `$` and `!` sequences in device keys, so never inline the
    configuration in a command, and keep the snippet's `device_key: >-` block:
    flattened onto one line, the leading `!` becomes a YAML tag and parsing
    fails. Don't hand-copy `mp_config` out of `terraform.tfvars` either; it's
    HCL (unicode escapes such as `\u003d`, no commas between some keys).
-   **Networking**: The appliance needs outbound internet access to AppNeta
    (see [Broadcom Firewall Configuration](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-firewall.html)).
    `gcloud compute instances create` assigns an ephemeral external IP unless
    you add `no-address`.
-   **Firewall**: Single-ended tests need only outbound access, so create no
    inbound rule by default. Marketplace and Terraform deployments also create
    an ingress rule from `0.0.0.0/0` for the dual-ended test ports and an
    allow-all egress rule. Open inbound ports only for dual-ended tests, only
    with the user's approval, and only from the peers' ranges.
-   **Pricing**: Check the listing's **Pricing** tab; the VM, disk, and
    external IP are billed as Compute Engine resources (see
    [Compute Engine pricing](https://cloud.google.com/products/compute/pricing)).

--------------------------------------------------------------------------------

## 5. Registration and Status

Verify that deployed Monitoring Points across any platform have registered with
Cloud Network Insights (`ONLINE` vs `OFFLINE`):

```bash
gcloud network-management network-monitoring-providers monitoring-points list \
  --network-monitoring-provider=PROVIDER_ID \
  --location=global \
  --project=PROJECT_ID
```

| Deployment | Poll every | Usually `ONLINE` | If still missing |
| :--- | :--- | :--- | :--- |
| Container after `setup.sh install` on a host | 10 seconds | Within 30 seconds (`type: c50 Container`) | Run `./setup.sh status` on the host |
| Container VM with the Path B startup script | 30 seconds | About 2-3 minutes | After 5 minutes, read the serial port output (Path B, step 4) |
| Compute Engine appliance VM | 30 seconds | About 3 minutes (`type: Google CE`) | After 10 minutes, run `gcloud compute instances get-serial-port-output HOSTNAME --zone=ZONE --project=PROJECT_ID` |

--------------------------------------------------------------------------------

## 6. Host Cleanup

Monitoring Point hosts are billed until you delete them. Remove only hosts and
rules created for Cloud Network Insights, only after the user confirms them
(`SKILL.md` Rule 4), and in the order of the cleanup scope in `SKILL.md` (after
the policies, or after turning Cloud Network Insights off):

-   **Compute Engine VMs** (container hosts and `gcloud` appliances): `gcloud
    compute instances delete HOSTNAME --zone=ZONE --project=PROJECT_ID --quiet`
-   **Marketplace deployment**: find it with `gcloud infra-manager deployments
    list --location=REGION --project=PROJECT_ID`, then run `gcloud
    infra-manager deployments delete DEPLOYMENT --location=REGION
    --project=PROJECT_ID --quiet`, which also deletes the VM and the firewall
    rules that the deployment created. Don't delete its VM separately.
-   **Terraform**: `terraform destroy`. **Helm**: `helm uninstall appneta-mp
    --namespace NAMESPACE`. **Container on a host that stays**: `./setup.sh
    uninstall` in the bundle directory. **AWS or Azure**: delete the
    CloudFormation stack or the Azure deployment.
-   **Firewall rules**: delete only rules you created, such as `gcloud compute
    firewall-rules delete RULE_NAME --project=PROJECT_ID --quiet`.
