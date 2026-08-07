# Google Cloud Resource Discovery Guidelines

This reference document details how to execute gcloud commands to discover and list existing Google Cloud resources (Cloud Storage buckets, Compute Engine Managed Instance Groups, GKE clusters, and Cloud Run services) in the project to assist with load balancer configuration.

## Target Environment Assumptions
This resource discovery flow assumes it is executed in an environment (such as Gemini CLI, Antigravity, or a configured gLinux terminal) where the Google Cloud SDK (`gcloud`) is installed and has active credentials for the target project. If `gcloud` is not available, the agent must skip discovery and prompt the user to input their resource names manually.

---

## Core Directives

1. **Discovery UX:** Prioritize a clean, numbered-list UX for all resource discovery. Never ask for manual string input for existing resources. Always present lists starting with: **1. Create New**, **2. NA**.
2. **Project ID Detection:** Auto-detect the target Google Cloud project ID using `gcloud config get-value project`.
3. **Resource Fetching Guidelines:**
    When requested by the main configuration skill, fetch the specific resource types:
    *   **Google Cloud Storage Buckets:** Run `gcloud storage buckets list --format="value(name,location)"`
    *   **Compute Engine Managed Instance Groups (MIGs):** Run `gcloud compute instance-groups managed list --format="value(name,region,zone)"`
    *   **Cloud Run Services:** Run `gcloud run services list --format="value(name,region)"`
    *   *(Only fetch the resource types that the user explicitly selected in their Origin Types.)*

4. **Return Format:** Return the discovered items clearly labeled with their region/zone where applicable.
