"""
GCP Agent Security Audit Skill

Proactive AI Agent security auditing using:
- Google BigQuery
- BigQuery ML anomaly detection
- Cloud Monitoring / PubSub alerts
"""

import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, List, Any

from google.cloud import bigquery
from google.cloud import pubsub_v1


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


class AgentSecurityAuditor:
    """
    Security auditor for AI Agent logs.
    """


    MAX_ROWS = 10000


    def __init__(
        self,
        project_id: str,
        alert_topic: str = None
    ):

        self.project_id = project_id

        self.bigquery = bigquery.Client(
            project=project_id
        )

        self.publisher = pubsub_v1.PublisherClient()

        self.alert_topic = alert_topic

        self.patterns = self.load_patterns()



    # --------------------------------
    # Load Security Patterns
    # --------------------------------


    def load_patterns(self):

        patterns = {}

        path = os.path.join(
            os.path.dirname(__file__),
            "patterns"
        )


        if os.path.exists(path):

            for file in os.listdir(path):

                if file.endswith(".sql"):

                    with open(
                        os.path.join(path, file),
                        "r",
                        encoding="utf-8"
                    ) as f:

                        patterns[
                            file.replace(
                                ".sql",
                                ""
                            ).upper()
                        ] = f.read().strip()



        if not patterns:

            logging.warning(
                "No patterns found"
            )


        return patterns



    # --------------------------------
    # BigQuery Logs
    # --------------------------------


    def fetch_logs(
        self,
        table_id: str,
        limit: int = 500
    ):


        limit = min(
            limit,
            self.MAX_ROWS
        )


        query = f"""

        SELECT *
        FROM `{table_id}`
        LIMIT {limit}

        """


        result = self.bigquery.query(
            query
        ).result()


        return [
            dict(row)
            for row in result
        ]



    # --------------------------------
    # Threat Detection
    # --------------------------------


    def scan_text(
        self,
        text: str
    ):


        findings = []


        for name, pattern in self.patterns.items():

            try:

                if re.search(
                    pattern,
                    text
                ):

                    findings.append(
                        {
                            "type": name,
                            "severity":
                            self.severity(name)
                        }
                    )

            except re.error as error:

                logging.error(
                    "Invalid pattern %s: %s",
                    name,
                    error
                )


        return findings



    def audit_logs(
        self,
        logs: List[Dict[str,Any]]
    ):


        findings = []


        for index, log in enumerate(logs):

            content = json.dumps(
                log,
                ensure_ascii=False
            )


            issues = self.scan_text(
                content
            )


            if issues:

                findings.append(
                    {
                        "row": index,
                        "timestamp":
                        datetime.utcnow().isoformat(),
                        "issues": issues
                    }
                )


        return findings



    # --------------------------------
    # BigQuery ML
    # --------------------------------


    def anomaly_detection(
        self,
        model_id: str
    ):


        query = f"""

        SELECT *
        FROM ML.DETECT_ANOMALIES(
            MODEL `{model_id}`,
            STRUCT(
                0.95 AS contamination
            )
        )

        """


        try:

            result = self.bigquery.query(
                query
            ).result()


            return [
                dict(row)
                for row in result
            ]


        except Exception as error:

            logging.warning(
                "BigQuery ML anomaly detection unavailable: %s",
                error
            )


            return {
                "status":
                "not_configured"
            }



    # --------------------------------
    # Save Report
    # --------------------------------


    def save_report(
        self,
        table_id: str,
        report: dict
    ):


        rows = [

            {
                "timestamp":
                datetime.utcnow().isoformat(),

                "report":
                json.dumps(report)
            }

        ]


        errors = self.bigquery.insert_rows_json(
            table_id,
            rows
        )


        return not errors



    # --------------------------------
    # Alert System
    # --------------------------------


    def send_alert(
        self,
        report
    ):


        if not self.alert_topic:

            return


        topic = (
            f"projects/{self.project_id}/topics/"
            f"{self.alert_topic}"
        )


        self.publisher.publish(
            topic,
            json.dumps(
                report
            ).encode("utf-8")
        )



    # --------------------------------
    # Main Audit
    # --------------------------------


    def run_audit(
        self,
        logs_table: str,
        report_table: str = None,
        ml_model: str = None
    ):


        logs = self.fetch_logs(
            logs_table
        )


        findings = self.audit_logs(
            logs
        )


        anomalies = {}


        if ml_model:

            anomalies = self.anomaly_detection(
                ml_model
            )


        risk = (
            "HIGH"
            if findings
            else "LOW"
        )


        report = {

            "generated":
            datetime.utcnow().isoformat(),

            "risk":
            risk,

            "findings":
            findings,

            "anomalies":
            anomalies

        }



        if report_table:

            self.save_report(
                report_table,
                report
            )



        if risk == "HIGH":

            self.send_alert(
                report
            )


        return report



    @staticmethod
    def severity(
        name
    ):


        if name in [
            "DATA_EXFILTRATION",
            "JAILBREAK"
        ]:

            return "HIGH"


        return "MEDIUM"
