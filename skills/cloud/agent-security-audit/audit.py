"""
GCP Agent Security Audit Skill

Proactive AI Agent security auditing using:
- Google BigQuery
- BigQuery ML anomaly detection
- Cloud Monitoring / PubSub alerts
"""

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


    MAX_ROWS = 10000


    SECURITY_PATTERNS = {

        "PROMPT_INJECTION":
        r"(?i)(ignore previous instructions|ignore all previous|system prompt|developer message|reveal instructions)",


        "JAILBREAK":
        r"(?i)(jailbreak|bypass safety|disable safeguards|ignore policy)",


        "ROLE_OVERRIDE":
        r"(?i)(you are now|act as|pretend to be)",


        "INDIRECT_PROMPT_INJECTION":
        r"(?i)(hidden instruction|embedded command|retrieved document instruction|follow these instructions)",


        "DATA_EXFILTRATION":
        r"(?i)(api[_ -]?key|secret|password|token|private key|credentials)"

    }



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



    # -------------------------------
    # BigQuery Logs
    # -------------------------------


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


        rows = self.bigquery.query(
            query
        ).result()


        return [
            dict(row)
            for row in rows
        ]



    # -------------------------------
    # Threat Detection
    # -------------------------------


    def scan_text(
        self,
        text: str
    ):


        findings = []


        for name, pattern in self.SECURITY_PATTERNS.items():


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


        return findings



    def audit_logs(
        self,
        logs
    ):


        results = []


        for index, log in enumerate(logs):


            content = json.dumps(
                log,
                ensure_ascii=False
            )


            issues = self.scan_text(
                content
            )


            if issues:

                results.append(
                    {
                        "row": index,
                        "time":
                        datetime.utcnow().isoformat(),
                        "issues": issues
                    }
                )


        return results



    # -------------------------------
    # BigQuery ML Anomaly
    # -------------------------------


    def anomaly_detection(
        self,
        table_id
    ):


        query = f"""

        SELECT *
        FROM ML.DETECT_ANOMALIES(
            MODEL `{table_id}_model`,
            STRUCT(0.95 AS contamination)
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


        except Exception as e:


            logging.warning(
                "BigQuery ML unavailable: %s",
                e
            )


            return {
                "status":
                "not_configured"
            }



    # -------------------------------
    # Save Security Report
    # -------------------------------


    def save_report(
        self,
        table_id,
        report
    ):


        errors = self.bigquery.insert_rows_json(
            table_id,
            [
                {
                    "timestamp":
                    datetime.utcnow().isoformat(),

                    "report":
                    json.dumps(report)
                }
            ]
        )


        return errors == []



    # -------------------------------
    # Alerts
    # -------------------------------


    def send_alert(
        self,
        message
    ):


        if not self.alert_topic:

            return


        topic = (
            f"projects/{self.project_id}/topics/"
            f"{self.alert_topic}"
        )


        self.publisher.publish(
            topic,
            json.dumps(message).encode(
                "utf-8"
            )
        )


    # -------------------------------
    # Final Audit
    # -------------------------------


    def run_audit(
        self,
        logs_table,
        report_table=None
    ):


        logs = self.fetch_logs(
            logs_table
        )


        findings = self.audit_logs(
            logs
        )


        anomalies = self.anomaly_detection(
            logs_table
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
