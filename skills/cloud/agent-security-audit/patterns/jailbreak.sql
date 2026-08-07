SELECT 
    timestamp,
    agent_id,
    user_input
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
WHERE REGEXP_CONTAINS(LOWER(user_input), r'ignore\s+(all\s+)?previous\s+instructions|you\s+are\s+now\s+a\s+|jailbreak|system\s+prompt')
