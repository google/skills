from google.cloud import bigquery
from google.api_core import exceptions
import json
import re
from datetime import datetime
from typing import List, Dict, Any

class AgentSecurityAuditor:
    """
    مدقق أمني استباقي لوكلاء الذكاء الاصطناعي.
    يفحص سجلات BigQuery بحثاً عن أنماط الهجوم.
    """
    
    DEFAULT_MAX_ROWS = 500
    SNIPPET_LENGTH = 60
    
    THREAT_PATTERNS = {
        "PROMPT_INJECTION": r"(?i)(ignore\s+(all\s+)?previous\s+instructions|you\s+are\s+now\s+a\s+|system\s+prompt|reveal\s+your\s+instructions)",
        "DATA_EXFILTRATION": r"(?i)(send\s+data\s+to|upload\s+to|https?://|api[_\s]?key|password)",
        "SQL_INJECTION": r"(?i)(DROP\s+TABLE|UNION\s+SELECT|--)"
    }
    
    def __init__(self, project_id: str):
        self.client = bigquery.Client(project=project_id)
        
    def _sanitize_identifier(self, name: str) -> str:
        """تنظيف اسم المعرف لمنع حقن SQL"""
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', name)
        if not sanitized:
            raise ValueError(f"Invalid identifier: '{name}'")
        return sanitized
    
    def _build_query(self, dataset: str, table: str, max_rows: int) -> str:
        """بناء استعلام BigQuery الآمن"""
        return f"""
        SELECT interaction_log, timestamp, session_id
        FROM `{dataset}.{table}`
        WHERE interaction_log IS NOT NULL
        LIMIT {max_rows}
        """
    
    def _analyze_log(self, log: str, timestamp: Any, session_id: Any) -> List[Dict[str, str]]:
        """تحليل سجل واحد بحثاً عن جميع التهديدات المطابقة"""
        findings = []
        for threat_type, pattern in self.THREAT_PATTERNS.items():
            if re.search(pattern, log):
                findings.append({
                    "threat_type": threat_type,
                    "snippet": log[:self.SNIPPET_LENGTH] + "..." if len(log) > self.SNIPPET_LENGTH else log,
                    "timestamp": str(timestamp),
                    "session_id": str(session_id)
                })
                break
        return findings
    
    def _format_response(self, status: str, **kwargs) -> str:
        """تنسيق الرد النهائي بصيغة JSON"""
        response = {
            "status": status,
            "audit_time": datetime.now().isoformat(),
            **kwargs
        }
        return json.dumps(response, indent=2, ensure_ascii=False)
    
    def run_audit(self, dataset_id: str, table_id: str, max_rows: int = DEFAULT_MAX_ROWS) -> str:
        """
        تشغيل عملية التدقيق الأمني.
        
        Args:
            dataset_id: اسم مجموعة البيانات في BigQuery
            table_id: اسم الجدول
            max_rows: أقصى عدد للصفوف المفحوصة (افتراضي: 500)
        
        Returns:
            JSON string تحتوي على نتائج التدقيق
        """
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
                findings=all_findings
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
    print(f"Time: {report['audit_time']}")
    print(f"Threats Found: {report['threats_found']}")
    for f in report.get("findings", []):
        print(f"  - [{f['threat_type']}] {f['snippet']}")
