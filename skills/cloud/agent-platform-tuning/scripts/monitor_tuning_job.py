"""Monitors a Agent Platform Supervised Tuning Job."""

import argparse
import logging
import time

from google import genai


def monitor_job(
    project: str, location: str, job_id: str, poll_interval_secs: int = 60
):
  """Monitors a Agent Platform Supervised Tuning Job.

  This function polls the job status until it reaches a terminal state.

  Args:
    project: The Google Cloud project ID.
    location: The Google Cloud location.
    job_id: The ID of the SupervisedTuningJob.
    poll_interval_secs: The interval in seconds to poll the job status.
  """
  job_resource = (
      f"projects/{project}/locations/{location}/tuningJobs/{job_id}"
  )

  logging.info("Starting monitoring for tuning job: %s", job_resource)
  logging.info(
      "View job in console: https://console.cloud.google.com/agent-platform/"
      "tuning/locations/%s/tuningJob/%s/monitor?project=%s",
      location,
      job_id,
      project,
  )
  with genai.Client(
      enterprise=True, project=project, location=location
  ) as client:
    while True:
      job = client.tunings.get(name=job_resource)
      status = job.state
      status_name = status.name if status else "unknown"

      if status_name in (
          "JOB_STATE_SUCCEEDED",
          "JOB_STATE_FAILED",
          "JOB_STATE_CANCELLED",
          "JOB_STATE_PARTIALLY_SUCCEEDED",
      ):
        logging.info("Job finished with terminal state: %s", status_name)
        break
      else:
        logging.info("Current job status: %s", status_name)

      time.sleep(poll_interval_secs)


if __name__ == "__main__":
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
  )
  parser = argparse.ArgumentParser(
      description="Monitor Agent Platform Supervised Tuning Job"
  )
  parser.add_argument("--project", required=True)
  # Must match the location the job was submitted with, which is `global` for
  # open model jobs that did not pin a region.
  parser.add_argument("--location", required=True)
  parser.add_argument("--job_id", required=True)
  parser.add_argument(
      "--poll_interval_secs",
      type=int,
      default=60,
      help="Seconds to wait between polls",
  )

  args = parser.parse_args()
  monitor_job(args.project, args.location, args.job_id, args.poll_interval_secs)
