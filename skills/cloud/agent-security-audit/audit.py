bigquery
import json

class AgentSecurityAuditor:
    def __init__(self, project_id):
        self.client = bigquery.Client(project=project_id)

    def run_audit(self, dataset_id, table_id):
        """
        يقوم بفحص سجلات الوكيل بحثاً عن أنماط مشبوهة
        """
        query = f"""
        SELECT interaction_log, timestamp
        FROM `{dataset_id}.{table_id}`
        WHERE interaction_log LIKE '%DROP TABLE%' 
           OR interaction_log LIKE '%UNION SELECT%'
        LIMIT 100
        """
        query_job = self.client.query(query)
        results = [dict(row) for row in query_job.result()]
        
        return json.dumps({"status": "AUDIT_COMPLETE", "threats_found": len(results), "data": results
