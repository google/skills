# Creating Remote Models
Generative and embedding functions require a remote model that points to a
specific endpoint (e.g., Gemini). Remote models are created using a connection
to interact with Vertex AI.

### Syntax

```sql
CREATE [OR REPLACE] MODEL `project.dataset.model_name`
REMOTE WITH CONNECTION { DEFAULT | `project.region.connection_id` }
OPTIONS (ENDPOINT = 'endpoint_name');
```

### Available Endpoints

BigQuery supports the following models:

*   **Generative**:
    *   `gemini-3.1-flash-lite`
    *   `gemini-3.5-flash`
    *   `gemini-3.5-flash-lite`
    *   `gemini-3.6-flash`
    *   `gemini-3.7-flash`
    *   `gemini-3.8-flash`
    *   `gemini-4-argon`
*   **Embedding**: `text-embedding-005`, `text-multilingual-embedding-002`,
    `gemini-embedding-001`, `gemini-embedding-2`.

### Connection Usage
If `REMOTE WITH CONNECTION DEFAULT` is used, BigQuery automatically attempts to
use a default connection in the model's region. Default connection should be
the default behavior. Otherwise, you must specify a fully qualified connection
ID (e.g., `my-project.us.my-connection`).
