# Tutorial: Chat with Your Data

This tutorial walks you through connecting ORBIT to databases, files, vector stores, and APIs so you can query them using natural language.

<div align="center">
  <video src="https://github.com/user-attachments/assets/68190983-d996-458f-8024-c9c15272d1c3" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Querying an HR database through natural language.</i>
</div>

## Table of Contents

- [Prerequisites](#prerequisites)
- [Adapter Types Overview](#adapter-types-overview)
- [Example 1: SQL Database (SQLite)](#example-1-sql-database-sqlite)
- [Example 2: Chat with Files](#example-2-chat-with-files)
- [Example 3: Vector Store Q&A](#example-3-vector-store-qa)
- [Example 4: DuckDB Analytics](#example-4-duckdb-analytics)
- [Example 5: MongoDB Queries](#example-5-mongodb-queries)
- [Example 6: HTTP APIs](#example-6-http-apis)
- [Creating API Keys](#creating-api-keys)
- [Connecting Your Own Data](#connecting-your-own-data)

---

## Prerequisites

- ORBIT installed via [release download](../README.md#option-2-download-latest-release) or [git clone](../README.md#option-3-clone-from-git-development)
- Python environment activated (`source venv/bin/activate`)
- ORBIT server running (`./bin/orbit.sh start`)

> **Note:** The basic Docker image (`schmitech/orbit:basic`) includes simple chat only. Use the release or git install for database adapters.

---

## Adapter Types Overview

ORBIT supports different adapter types for different use cases:

| Adapter Type | Use Case | Examples |
|:---|:---|:---|
| **Passthrough** | Simple chat without retrieval | `simple-chat` |
| **Multimodal** | Chat with uploaded files (PDF, images, audio) | `simple-chat-with-files` |
| **QA** | Question-answering from vector stores | `qa-vector-chroma`, `qa-vector-qdrant` |
| **Intent SQL** | Natural language to SQL translation | `intent-sql-sqlite-hr`, `intent-duckdb-analytics` |
| **Intent HTTP** | Natural language to API calls | `intent-http-jsonplaceholder` |
| **Intent MongoDB** | Natural language to MongoDB queries | `intent-mongodb-mflix` |
| **Intent GraphQL** | Natural language to GraphQL queries | `intent-graphql-spacex` |

---

## Example 1: SQL Database (SQLite)

This example uses a local SQLite database with sample HR/employee data.

### 1. Generate Test Data

```bash
python utils/sql-intent-template/examples/sqlite/hr/generate_hr_data.py \
  --records 100 \
  --output utils/sql-intent-template/examples/sqlite/hr/hr.db
```

### 2. Restart ORBIT

Restart the server to load the pre-generated SQL templates:

```bash
./bin/orbit.sh restart
```

### 3. Create an API Key

```bash
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-hr \
  --name "HR Chatbot" \
  --prompt-file ./examples/prompts/hr-assistant-prompt.txt \
  --prompt-name "HR Assistant"
```

### 4. Start Chatting

```bash
orbitchat --api-url http://localhost:3000 --api-key YOUR_API_KEY --open
```

**Try questions like:**
- "How many employees per department?"
- "What's the average salary per department?"
- "Show me employees hired in the last 30 days"
- "Which departments are over budget on payroll?"

### How Intent SQL Works

1. ORBIT classifies your natural language intent
2. Selects the appropriate SQL template from the template library
3. Extracts parameters (dates, names, values) using an LLM
4. Executes the query against your database
5. Formats results in natural language

---

## Example 2: Chat with Files

Upload PDFs, images, or audio files and chat about their content.

### Adapter Configuration

The `simple-chat-with-files` adapter is pre-configured in `config/adapters/multimodal.yaml`:

```yaml
- name: "simple-chat-with-files"
  enabled: true
  type: "passthrough"
  adapter: "multimodal"
  implementation: "implementations.passthrough.multimodal.MultimodalImplementation"
  
  # Provider overrides
  inference_provider: "ollama_cloud"
  embedding_provider: "ollama"      # For file chunk retrieval
  vision_provider: "gemini"         # For image analysis
  tts_provider: "openai"            # For audio output
  
  capabilities:
    retrieval_behavior: "conditional"  # Only retrieves when files are uploaded
    supports_file_ids: true
    
  config:
    chunking_strategy: "recursive"
    chunk_size: 1000
    vector_store: "chroma"
    max_results: 10
    return_results: 10
```

### Create an API Key

```bash
./bin/orbit.sh key create \
  --adapter simple-chat-with-files \
  --name "Document Assistant" \
  --prompt-text "You are a helpful assistant that answers questions about uploaded documents. Be accurate and cite specific content from the files."
```

### Usage

1. Use the React chat app or web widget
2. Upload a PDF, Word doc, image, or audio file
3. Ask questions about the content

**Example questions:**
- "Summarize this document"
- "What are the key points in section 3?"
- "What does the chart on page 2 show?" (for images)
- "Transcribe and summarize this audio file"

### Supported File Types

| Category | Formats |
|:---|:---|
| Documents | PDF, DOCX, DOC, TXT, MD, HTML |
| Spreadsheets | XLSX, XLS, CSV |
| Data | JSON, XML |
| Images | PNG, JPEG, TIFF, GIF, WebP |
| Audio | WAV, MP3, OGG, FLAC, WebM, M4A |

---

## Example 3: Vector Store Q&A

Use vector similarity search for Q&A over embedded documents.

### Option A: Chroma (Local)

```bash
# Set up sample data
./examples/sample-db-setup.sh chroma
```

The adapter is configured in `config/adapters/qa.yaml`:

```yaml
- name: "qa-vector-chroma"
  enabled: true
  type: "retriever"
  datasource: "chroma"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAChromaRetriever"
  
  config:
    collection: "city"
    confidence_threshold: 0.3
    distance_scaling_factor: 2.0
    max_results: 5
    return_results: 3
```

### Option B: Qdrant (Cloud or Self-hosted)

```yaml
- name: "qa-vector-qdrant"
  enabled: true
  type: "retriever"
  datasource: "qdrant"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAQdrantRetriever"
  embedding_provider: "openai"
  
  config:
    collection: "my_collection"
    confidence_threshold: 0.3
    score_scaling_factor: 1.0
    max_results: 5
    return_results: 3
```

### Create an API Key

```bash
./bin/orbit.sh key create \
  --adapter qa-vector-chroma \
  --name "City Assistant" \
  --prompt-file ./examples/prompts/examples/city/city-assistant-normal-prompt.txt
```

---

## Example 4: DuckDB Analytics

Query analytical data using DuckDB with natural language.

### Adapter Configuration

Example from `config/adapters/intent.yaml`:

```yaml
- name: "intent-duckdb-analytics"
  enabled: true
  type: "retriever"
  datasource: "duckdb"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentDuckDBRetriever"
  database: "utils/duckdb-intent-template/examples/analytics/analytics.duckdb"
  
  inference_provider: "ollama_cloud"
  model: "gpt-oss:120b"
  embedding_provider: "ollama"
  
  config:
    domain_config_path: "utils/duckdb-intent-template/examples/analytics/analytics_domain.yaml"
    template_library_path:
      - "utils/duckdb-intent-template/examples/analytics/analytics_templates.yaml"
    
    template_collection_name: "duckdb_analytics_templates"
    store_name: "chroma"
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 100
    
    # DuckDB-specific settings
    read_only: true                    # Allow concurrent reads
    access_mode: "READ_ONLY"
```

### Use Cases

DuckDB excels at analytical queries:
- "What was the total revenue last quarter?"
- "Show me sales trends by month"
- "Which products had the highest growth rate?"
- "Compare this year's performance to last year"

---

## Example 5: MongoDB Queries

Query MongoDB collections using natural language.

### Adapter Configuration

```yaml
- name: "intent-mongodb-mflix"
  enabled: true
  type: "retriever"
  datasource: "mongodb"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.intent_mongodb_retriever.IntentMongoDBRetriever"
  
  inference_provider: "ollama_cloud"
  model: "glm-4.7:cloud"
  embedding_provider: "openrouter"
  
  config:
    domain_config_path: "utils/mongodb-intent-template/examples/sample_mflix/templates/mflix_domain.yaml"
    template_library_path:
      - "utils/mongodb-intent-template/examples/sample_mflix/templates/mflix_templates.yaml"
    
    database: "sample_mflix"
    default_collection: "movies"
    default_limit: 100
    enable_text_search: true
    case_insensitive_regex: true
```

### Example Questions

Using the MongoDB sample_mflix database:
- "Find movies directed by Christopher Nolan"
- "What are the top rated action movies from the 2000s?"
- "Show me movies with Leonardo DiCaprio"

---

## Example 6: HTTP APIs

Query REST APIs using natural language.

### Adapter Configuration

```yaml
- name: "intent-http-jsonplaceholder"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentHTTPJSONRetriever"
  
  inference_provider: "ollama_cloud"
  model: "gpt-oss:20b"
  embedding_provider: "ollama"
  
  config:
    domain_config_path: "utils/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_domain.yaml"
    template_library_path:
      - "utils/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_templates.yaml"
    
    base_url: "https://jsonplaceholder.typicode.com"
    default_timeout: 30
    enable_retries: true
    max_retries: 3
```

### Other HTTP Adapters

| Adapter | Description |
|:---|:---|
| `intent-http-paris-opendata` | Paris city open data portal |
| `intent-graphql-spacex` | SpaceX GraphQL API |
| `intent-firecrawl-webscrape` | Web scraping with Firecrawl |

---

## Creating API Keys

API keys control access and define which adapter and system prompt to use.

### CLI Commands

```bash
# Login first
./bin/orbit.sh login --username admin --password admin123

# Create a key with inline prompt
./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "My Assistant" \
  --prompt-text "You are a helpful assistant."

# Create a key with prompt file
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-hr \
  --name "HR Bot" \
  --prompt-file ./examples/prompts/hr-assistant-prompt.txt \
  --prompt-name "HR Assistant"

# List all keys
./bin/orbit.sh key list

# Delete a key
./bin/orbit.sh key delete --key orbit_abc123...
```

### Key Options

| Option | Description |
|:---|:---|
| `--adapter` | Which adapter to use |
| `--name` | Friendly name for the key |
| `--prompt-text` | Inline system prompt |
| `--prompt-file` | Load system prompt from file |
| `--prompt-name` | Name for the prompt configuration |
| `--notes` | Optional notes about the key |

---

## Connecting Your Own Data

### SQL Databases

1. **Generate templates** from your schema:
   ```bash
   python utils/sql-intent-template/generate_templates.py \
     --database path/to/your.db \
     --output templates/
   ```

2. **Add adapter** to `config/adapters/intent.yaml`:
   ```yaml
   - name: "my-database"
     enabled: true
     type: "retriever"
     adapter: "intent"
     implementation: "retrievers.implementations.intent.IntentSQLiteRetriever"
     database: "path/to/your.db"
     config:
       domain_config_path: "templates/domain.yaml"
       template_library_path:
         - "templates/templates.yaml"
   ```

3. **Restart ORBIT** and create an API key

### Vector Stores

1. **Index your documents** into a vector store (Chroma, Qdrant, Pinecone)
2. **Configure the QA adapter** with your collection name
3. **Create an API key** for the adapter

### Files

The multimodal adapter handles files automatically:
1. Enable `simple-chat-with-files` adapter
2. Create an API key
3. Upload files through the chat interface

---

## Adapter Configuration Reference

### Common Settings

All adapters support these configuration options:

```yaml
- name: "adapter-name"
  enabled: true                        # Enable/disable the adapter
  type: "retriever"                    # retriever, passthrough
  
  # Provider overrides (optional)
  inference_provider: "ollama"         # Override LLM provider
  model: "llama3:8b"                   # Override model
  embedding_provider: "openai"         # Override embedding provider
  reranker_provider: "cohere"          # Add reranking
  
  # Capabilities
  capabilities:
    retrieval_behavior: "always"       # none, always, conditional
    formatting_style: "standard"       # standard, clean
    supports_file_ids: false
    supports_threading: true
  
  # Fault tolerance
  fault_tolerance:
    operation_timeout: 30.0
    failure_threshold: 5
    max_retries: 3
```

### Intent Adapter Settings

```yaml
config:
  domain_config_path: "path/to/domain.yaml"
  template_library_path:
    - "path/to/templates.yaml"
  template_collection_name: "my_templates"
  store_name: "chroma"                 # Vector store for template matching
  confidence_threshold: 0.4
  max_templates: 5
  return_results: 100
  reload_templates_on_start: true
  force_reload_templates: false
```

---

## Troubleshooting

| Issue | Solution |
|:---|:---|
| "No matching template found" | Lower `confidence_threshold` or add more templates |
| Slow template matching | Check embedding provider is running |
| File upload fails | Check `max_file_size` and supported types |
| Database connection fails | Verify database path and permissions |
| API timeout | Increase `operation_timeout` in fault_tolerance |

---

## Next Steps

- [Configuration Guide](configuration.md) – Full configuration reference
- [SQL Retriever Architecture](sql-retriever-architecture.md) – Deep dive into SQL adapters
- [API Keys Guide](api-keys.md) – Advanced API key management
- [Authentication Guide](authentication.md) – User and role management
