#!/usr/bin/env python3
import os
import sys
import subprocess
import json

def check_env():
    """Verify standard deployment parameters exist."""
    required = ["PROJECT_ID", "LOCATION_ID"]
    missing = [var for var in required if not os.environ.get(var)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

def audit_labels(service_name, region):
    """Confirm whether mandatory cost-tracking tags are configured."""
    print(f"🔍 Auditing cost labels on Cloud Run service: {service_name}...")
    try:
        cmd = [
            "gcloud", "run", "services", "describe", service_name,
            f"--region={region}", "--format=json"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        config = json.loads(result.stdout)
        labels = config.get("metadata", {}).get("labels", {})
        
        required_labels = ["agent-id", "business-unit", "environment"]
        missing_labels = [l for l in required_labels if l not in labels]
        
        if missing_labels:
            print(f"❌ FinOps Compliance Failure: Missing labels: {', '.join(missing_labels)}")
        else:
            print("✅ FinOps Compliance: All cost-tracking labels are properly configured.")
            for k in required_labels:
                print(f"   * {k}: {labels[k]}")
    except Exception as e:
        print(f"⚠️ Error querying Cloud Run labels: {e}")

if __name__ == "__main__":
    check_env()
    project = os.environ["PROJECT_ID"]
    location = os.environ["LOCATION_ID"]
    
    print("=========================================")
    print(f"🛡️  Auditing Agent Governance: {project}")
    print("=========================================")
    
    # Audit target agent runtime service
    audit_labels("agent-runtime-service", location)
