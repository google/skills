---
name: agent-platform-rag-engine-management
description: >-
  Manage and query Agent Platform RAG Engine Corpora and retrieve grounded
  contexts using the Google GenAI SDK. Use when listing RAG corpora or files,
  inspecting a corpus, retrieving contexts, or generating content grounded in a
  RAG corpus. Do not use for standard database queries (use SQL/Spanner skills),
  Google Workspace RAG, or other RAG products like gRAG.
---

# Agent Platform RAG Engine Management

This skill provides instructions on how to interact with Agent Platform RAG
Engine using the Agent Platform Python SDK. You MUST use the `vertexai` Python
SDK to perform RAG Engine operations, rather than raw REST calls or MCP tools,
because this code is intended to be run by external clients.

## Safety & Confirmation Tiers (CRITICAL)

Before executing any commands or scripts on behalf of the user, you must adhere
to the following safety tiers based on the action requested:

1.  **Tier R: Read-only (`list_corpora`, `list_files`, `get_corpus`, `retrieval_query`)**
    *   No confirmation needed. Execute immediately to gather information or retrieve grounded contexts.
2.  **Tier RC: Read-only but consumes Compute Resources (`client.models.generate_content`)**
    *   Requires **interactive confirmation** with 'Yes'/'No' options before
    executing grounded content generation. The confirmation prompt MUST
    clearly explain the proposed generation execution and its key parameters
    (e.g., target corpus ID, query text, target model). Natural-language
    paraphrases without specifying exact parameters are insufficient, as
    explicit parameter listing is required to ensure unambiguous user approval
    of the specific resource and configuration.
    *   **Same-turn restriction**: Do not execute the generation code in the
    same turn as presenting the confirmation prompt. Stop and wait for the
    user's reply; only execute after explicit 'Yes' / approval.
    *   **Gold Standard Example**:
        > I will perform grounded content generation with the following
        > parameters. Please confirm this information before I proceed:
        > *   **Target Corpus ID**: `projects/123/locations/us/ragCorpora/abc`
        > *   **Target Model**: `gemini-2.5-pro`
        > *   **Query Text**: "What are the company policies on remote work?"
        > Do you confirm? [Yes/No]

## Phase 0: Environment Setup

**CRITICAL**: Before running any of the Python snippets below, you must ensure
the environment is correctly initialized by following these steps:

1.  **Google Cloud Authentication**: Authenticate with your Google Cloud
    credentials and configure active Application Default Credentials (ADC) for
    Agent Platform access:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

2.  **Virtual Environment**: Create and activate a dedicated virtual
    environment:

    ```bash
    python3 -m venv ~/rag_agent_venv
    source ~/rag_agent_venv/bin/activate
    ```

3.  **Install Dependencies**: Install the required Agent Platform SDKs:

    ```bash
    pip install google-cloud-aiplatform google-genai
    ```

4.  **Execution**: Advise the user that every time they execute a Python
    snippet, they must ensure this virtual environment is activated first.

## Workflow Decision Tree

1.  **Information Gathering**: Has the user provided the Project ID, Region, and
    Corpus ID?

    *   **No** -> Proceed to [1. Listing Corpora and Files] to discover the
        necessary Resource Names and IDs. Only ask the user if discovery fails.
    *   **Yes** -> Proceed.

2.  **Task Type**: What does the user want to do?

    *   **List Corpora and Files** -> Proceed to [1. Listing Corpora and Files].
    *   **Inspect a Corpus** -> Proceed to [2. Getting / Inspecting a RAG Engine
        Corpus].
    *   **Search for Contexts** -> Proceed to [3. Retrieving Contexts].
    *   **Answer questions using RAG Engine** -> Proceed to [4. Answering the
        User with Retrieved Context].

> [!TIP]
>
> **Placeholder Parameter Replacement:** The Python scripts below use bracketed
> string placeholders (like `"{project_id}"`, `"{region}"`, and
> `"{corpus_id}"`). You **MUST** dynamically replace these placeholders with the
> actual Project ID, Region, and Corpus ID values provided in the user's prompt
> (or active context) before generating, providing, or executing the scripts.

## 1. Listing Corpora and Files (Discovery)

If you do not know the Resource Name of the corpus or file, you MUST list them
first to discover them. The SDK handles pagination automatically when converted
to a list, but you can also use manual pagination for large sets.

### 1.1 Listing and Discovering Corpora

```python
import vertexai
from vertexai.preview import rag

vertexai.init(project="{project_id}", location="{region}")

# Approach A: List ALL (Automatic Pagination)
# The SDK's Pager iterates through all pages for you.
all_corpora = list(rag.list_corpora())
print(f"Found {len(all_corpora)} corpora in total.")
for c in all_corpora:
    print(f"Corpus Name: {c.name} | Display Name: {c.display_name}")

# Approach B: Manual Pagination (for very large projects)
pager = rag.list_corpora(page_size=10)
# Process first page
for c in pager:
    print(f"Corpus: {c.display_name}")

# Get next page if needed
if pager.next_page_token:
    second_page = rag.list_corpora(
        page_size=10, page_token=pager.next_page_token
    )
```

### 1.2 Listing and Discovering Files

To understand what files (and types) are in a corpus, list them and inspect the
`display_name` (usually includes the extension).

```python
import vertexai
from vertexai.preview import rag

vertexai.init(project="{project_id}", location="{region}")
corpus_name = (
    "projects/{project_id}/locations/{region}/ragCorpora/{corpus_id}"
)

# List files with automatic pagination
files = list(rag.list_files(corpus_name=corpus_name))
print(f"Found {len(files)} files.")

for f in files:
    # High-level SDK RagFile objects usually have name, display_name,
    # description
    print(f"File: {f.display_name} | Resource: {f.name}")
    # Tip: Check extension to understand file type (PDF, TXT, etc.)
    if f.display_name.lower().endswith(".pdf"):
        print("  Type: PDF")
    elif f.display_name.lower().endswith(".txt"):
        print("  Type: Plain Text")
```

## 2. Getting / Inspecting an Agent Platform RAG Engine Corpus

To retrieve details about an existing Agent Platform RAG Engine corpus:

```python
import vertexai
from vertexai.preview import rag

vertexai.init(project="{project_id}", location="{region}")

# To get details of a specific corpus
corpus_name = (
    "projects/{project_id}/locations/{region}/ragCorpora/{corpus_id}"
)
corpus = rag.get_corpus(name=corpus_name)
print(f"Corpus Name: {corpus.name}")
print(f"Display Name: {corpus.display_name}")
```

## 3. Retrieving Contexts

To retrieve relevant contexts from a RAG Engine corpus based on a query:

```python
import vertexai
from vertexai.preview import rag

vertexai.init(project="{project_id}", location="{region}")

corpus_name = (
    "projects/{project_id}/locations/{region}/ragCorpora/{corpus_id}"
)
query = "What is the speed of light?"

# Retrieve contexts
response = rag.retrieval_query(
    rag_corpora=[corpus_name],
    text=query,
    similarity_top_k=3
)

for context in response.contexts.contexts:
    print(f"Context text: {context.text}")
    print(f"Source: {context.source_uri}")
```

## 4. Answering the User with Retrieved Context

To use the retrieved context alongside an Agent Platform model to generate a
grounded response:

```python
from google import genai
from google.genai import types

client = genai.Client(enterprise=True, project="{project_id}", location="{region}")
corpus_name = (
    "projects/{project_id}/locations/{region}/ragCorpora/{corpus_id}"
)

# Define the Agent Platform RAG Engine tool pointing to the corpus
rag_tool = types.Tool(
    retrieval=types.Retrieval(
        vertex_rag_store=types.VertexRagStore(
            rag_resources=[types.VertexRagStoreRagResource(rag_corpus=corpus_name)],
            rag_retrieval_config=types.RagRetrievalConfig(
                top_k=3,
                filter=types.RagRetrievalConfigFilter(
                    vector_similarity_threshold=0.5,
                ),
            ),
        )
    )
)

# Generate content using the RAG Engine tool
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="What is the speed of light?",
    config=types.GenerateContentConfig(
        tools=[rag_tool]
    )
)
print(response.text)
```
