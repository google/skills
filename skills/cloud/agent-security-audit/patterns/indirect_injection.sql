SELECT 
    timestamp,
    agent_id,
    retrieved_documents
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
WHERE retrieved_documents IS NOT NULL
AND (
    REGEXP_CONTAINS(LOWER(retrieved_documents), r'ignore\s+above|do\s+not\s+follow|new\s+instruction')
    OR 
    REGEXP_CONTAINS(LOWER(retrieved_documents), r'https?://|curl|wget|exfiltrate')
)
