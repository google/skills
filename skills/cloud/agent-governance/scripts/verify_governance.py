#!/usr/bin/env python3
"""
verify_governance.py
Audits and verifies Agent Platform Governance, Security, and Cost-Tracking Labels.
"""

import json
import subprocess
import sys

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        return None

def verify_labels(service_name, region, project_id):
    print(f"[*] Checking labels for Cloud Run service: {service_name}...")
    cmd = f"gcloud run services describe {service_name} --region={region} --project={project_id} --format=json"
    output = run_cmd(cmd)
    if not output:
        print(f"[-] Failed to fetch metadata for {service_name}")
        return False
    
    data = json.loads(output)
    labels = data.get("metadata", {}).get("labels", {})
    required_labels = ["agent-id", "business-unit", "environment"]
    missing = [l for l in required_labels if l not in labels]
    
    if missing:
        print(f"[!] Warning: Missing FinOps labels: {missing}")
        return False
    
    print(f"[+] All required FinOps labels present: {labels}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 verify_governance.py <SERVICE_NAME> <REGION> <PROJECT_ID>")
        sys.exit(1)
    
    service, reg, proj = sys.argv[1], sys.argv[2], sys.argv[3]
    verify_labels(service, reg, proj)
