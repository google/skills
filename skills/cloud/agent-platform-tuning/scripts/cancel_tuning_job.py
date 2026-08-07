"""Cancels a Agent Platform Supervised Tuning Job.

This script provides a function to cancel an ongoing SupervisedTuningJob
on Agent Platform given the project, location, and job ID.
"""

import argparse
import vertexai  # pyrefly: ignore[missing-import]
from vertexai.tuning import sft  # pyrefly: ignore[missing-import]


def cancel_job(project, location, job_id):
  vertexai.init(project=project, location=location)
  job_resource = f"projects/{project}/locations/{location}/tuningJobs/{job_id}"
  job = sft.SupervisedTuningJob(job_resource)
  print(f"Cancelling job: {job_resource}")
  job.cancel()
  print("Cancellation request sent.")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Cancel Vertex AI Supervised Tuning Job"
  )
  parser.add_argument("--project", required=True)
  # Must match the location the job was submitted with, which is `global` for
  # open model jobs that did not pin a region.
  parser.add_argument("--location", required=True)
  parser.add_argument("--job_id", required=True)

  args = parser.parse_args()
  cancel_job(args.project, args.location, args.job_id)
