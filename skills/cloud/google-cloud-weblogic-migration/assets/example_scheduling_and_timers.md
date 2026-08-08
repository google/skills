# EJB Timer Service, WebLogic Timers, & Clustered Quartz Modernization Guide

Legacy WebLogic monoliths execute background jobs and periodic tasks using the
**EJB Timer Service** (`@Schedule`, `@Timeout`, `TimerService.createTimer()`),
`weblogic.timers.Timer`, or embedded **Quartz Scheduler** clustered via Oracle
database tables (`QRTZ_*`).

In serverless container environments (Google Cloud Run / Google Cloud
Functions), running embedded polling loops inside web instances wastes CPU and
causes duplicate execution across horizontally scaled replicas. All scheduling
must be decoupled into managed cloud task orchestrators.

--------------------------------------------------------------------------------

## 1. EJB Timer Service (`@Schedule`) to Google Cloud Scheduler

In WebLogic, `@Schedule` annotations execute cron-like periodic tasks within the
EJB container.

### Before: Legacy EJB Timer (`@Schedule`)

```java
import javax.ejb.Schedule;
import javax.ejb.Stateless;

@Stateless
public class DailyReportTimer {

    @Schedule(hour = "2", minute = "30", second = "0", persistent = true)
    public void generateDailySummary() {
        // Heavy daily report calculation...
    }
}
```

### After: Google Cloud Scheduler + IAM-Protected Cloud Run Endpoint

Remove `@Schedule` and expose the business logic as a secure REST endpoint
protected by Google Cloud IAM service account authentication, triggered
externally by **Google Cloud Scheduler**:

#### Spring Boot / Quarkus Secure Endpoint

```java
// Spring Boot REST Endpoint (or Quarkus JAX-RS @Path)
@RestController
@RequestMapping("/internal/jobs")
public class DailyReportJobController {
    @Autowired
    private DailyReportService dailyReportService;

    @PostMapping("/daily-summary")
    public ResponseEntity<Void> triggerDailySummary() {
        dailyReportService.generateDailySummary();
        return ResponseEntity.ok().build();
    }
}
```

#### Google Cloud Scheduler Configuration (Terraform / gcloud)

```hcl
resource "google_service_account" "scheduler_sa" {
  account_id   = "report-scheduler-sa"
  display_name = "Cloud Scheduler Service Account for Daily Reports"
}

resource "google_cloud_run_service_iam_member" "invoker" {
  service  = google_cloud_run_service.report_service.name
  location = google_cloud_run_service.report_service.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

resource "google_cloud_scheduler_job" "daily_summary_job" {
  name             = "daily-report-summary-job"
  description      = "Triggers daily summary report on Cloud Run"
  schedule         = "30 2 * * *" # Daily at 02:30 AM
  time_zone        = "America/New_York"
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_service.report_service.status[0].url}/internal/jobs/daily-summary"

    oidc_token {
      service_account_email = google_service_account.scheduler_sa.email
      audience              = google_cloud_run_service.report_service.status[0].url
    }
  }
}
```

--------------------------------------------------------------------------------

## 2. Clustered Quartz Schedulers to Google Cloud Run Jobs

When legacy WebLogic applications use embedded Quartz Schedulers backed by
Oracle database tables (`QRTZ_*`) for long-running batch computing or analytical
data processing, extract the job into a standalone entry point designed to run
as a **Google Cloud Run Job**.

### After: Google Cloud Run Job Execution

Unlike Cloud Run Services (which listen on an HTTP port), Cloud Run Jobs run to
completion and automatically shut down, saving compute costs:

```hcl
resource "google_cloud_run_v2_job" "batch_analytics_job" {
  name     = "medimed-batch-analytics"
  location = "us-central1"

  template {
    template {
      containers {
        image = "gcr.io/my-project/medimed-analytics-job:latest"
        resources {
          limits = {
            memory = "4Gi"
            cpu    = "2"
          }
        }
        env {
          name  = "SPRING_PROFILES_ACTIVE"
          value = "batch-job"
        }
      }
    }
  }
}

# Trigger Cloud Run Job via Cloud Scheduler
resource "google_cloud_scheduler_job" "trigger_batch_job" {
  name        = "trigger-medimed-batch-analytics"
  schedule    = "0 0 * * 0" # Weekly on Sunday at midnight

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/my-project/locations/us-central1/jobs/medimed-batch-analytics:run"

    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }
}
```
