"""
GCP Agent Security Audit Skill - Core Logic
"""
import os
import json
import re
from datetime import datetime
from typing import List, Dict, Any

from google.cloud import bigquery
from google.api_core import exceptions

class AgentSecurityAuditor:
    """
    مدقق أمني استباقي لوكلاء الذكاء الاصطناعي.
    يفحص سجلات BigQuery بحثاً عن أنماط الهجوم باستخدام ملفات patterns/
    """
    
    DEFAULT_MAX_ROWS = 500
    SNIPPET_LENGTH = 60
    
    def __init__(self, project_id: str):
        self.client = bigquery.Client(project=project_id)
        self.patterns = self._load_threat_patterns()
        
    def _load_threat_patterns(self) -> Dict[str, str]:
        """تحميل أنماط التهديد من ملفات SQL الموجودة في مجلد patterns/"""
        patterns_dir = os.path.join(os.path.dirname(__file__), "patterns")
        patterns = {}
        
        if os.path.exists(patterns_dir):
            for file_name in os.listdir(patterns_dir):
                if file_name.endswith(".sql"):
                    file_path = os.path.join(patterns_dir, file_name)
                    try:
                        with open(file_path, 'r') as f:
                            content = f.read().strip()
                            if content:
                                pattern_name = file_name.replace(".sql", "").upper()
                                patterns[pattern_name] = content
                    except Exception:
                        pass 
            
        # إذا لم يتم تحميل أي شيء، نستخدم أنماطاً افتراضية (Fallback)
        if not patterns:
            patterns = {
                "PROMPT_INJECTION": r"(?i)(ignore\s+(all\s+)?previous\s+instructions|you\s+are\s+now\s+a\s+|system\s+prompt|reveal\s+your\s+instructions)",
                "DATA_EXFILTRATION": r"(?i)(send\s+data\s+to|upload\s+to|https?://|api[_\s]?key|password)",
            }
            
        return patterns

    def _sanitize_identifier(self, name: str) -> str:
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', name)
        if not sanitized:
            raise ValueError(f"Invalid identifier: '{name}'")
        return sanitized
    
    def _build_query(self, dataset: str, table: str, max_rows: int) -> str:
        return f"""
        SELECT interaction_log, timestamp, session_id
        FROM `{dataset}.{table}`
        WHERE interaction_log IS NOT NULL
        LIMIT {max_rows}
        """
    
    def _analyze_log(self, log: str, timestamp: Any, session_id: Any) -> List[Dict[str, str]]:
        findings = []
        for threat_type, pattern in self.patterns.items():
            if re.search(pattern, log, re.IGNORECASE):
                findings.append({
                    "threat_type": threat_type,
                    "snippet": log[:self.SNIPPET_LENGTH] + "..." if len(log) > self.SNIPPET_LENGTH else log,
                    "timestamp": str(timestamp),
                    "session_id": str(session_id)
                })
                break
        return findings
    
    def _format_response(self, status: str, **kwargs) -> str:
        response = {
            "status": status,
            "audit_time": datetime.now().isoformat(),
            **kwargs
        }
        return json.dumps(response, indent=2, ensure_ascii=False)
    
    def run_audit(self, dataset_id: str, table_id: str, max_rows: int = DEFAULT_MAX_ROWS) -> str:
        try:
            ds = self._sanitize_identifier(dataset_id)
            tb = self._sanitize_identifier(table_id)
            
            query = self._build_query(ds, tb, max_rows)
            query_job = self.client.query(query)
            
            all_findings = []
            for row in query_job.result():
                log = row.interaction_log
                timestamp = row.timestamp
                session_id = row.get("session_id", "unknown")
                all_findings.extend(self._analyze_log(log, timestamp, session_id))
            
            return self._format_response(
                "AUDIT_COMPLETE",
                threats_found=len(all_findings),
                findings=all_findings,
                patterns_used=list(self.patterns.keys())
            )
            
        except exceptions.GoogleAPIError as e:
            return self._format_response("ERROR", message=str(e))
        except ValueError as e:
            return self._format_response("ERROR", message=f"Validation error: {str(e)}")
        except Exception as e:
            return self._format_response("ERROR", message=f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    auditor = AgentSecurityAuditor(project_id="your-gcp-project-id")
    report = json.loads(auditor.run_audit("your_dataset", "your_table"))
    print(f"Audit Status: {report['status']}")
    print(f"Patterns Used: {report['patterns_used']}")
    print(f"Threats Found: {report['threats_found']}")
