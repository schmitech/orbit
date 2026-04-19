# Tutorial: Chat with Your Data

Welcome! By the end of this tutorial you'll have ORBIT chatting with a real database, a set of uploaded files, a vector store, and a public API — all through natural language, all behind a single endpoint.

You don't have to do every example. Start with "Your first chat" to confirm the server works, then jump to whichever data source looks like yours.

## Table of Contents

- [Before you start](#before-you-start)
- [Your first chat (2 minutes)](#your-first-chat-2-minutes)
- [Adapter Types Overview](#adapter-types-overview)
- [Example 1: SQL Database (SQLite)](#example-1-sql-database-sqlite)
- [Example 2: Chat with Files](#example-2-chat-with-files)
- [Example 3: Vector Store Q&A](#example-3-vector-store-qa)
- [Example 4: DuckDB Analytics](#example-4-duckdb-analytics)
- [Example 5: MongoDB Queries](#example-5-mongodb-queries)
- [Example 6: HTTP APIs](#example-6-http-apis)
- [Example 7: Multi-Source Composite](#example-7-multi-source-composite)
- [Example 8: Agent with Function Calling](#example-8-agent-with-function-calling)
- [Creating API Keys](#creating-api-keys)
- [Connecting Your Own Data](#connecting-your-own-data)
- [Troubleshooting](#troubleshooting)

---

## Before you start

You need three things:

1. **ORBIT installed.** Either the [release download](../README.md#option-2-download-latest-release) or a [git clone](../README.md#option-3-clone-from-git-development).
2. **An inference provider.** The shipped adapters default to **OpenAI (`gpt-5.4-mini`)**, so set `OPENAI_API_KEY` in your environment — or swap to another provider in `config/inference.yaml` (Ollama, Anthropic, Gemini, and 25+ others are supported).
3. **The server running.**
   ```bash
   source venv/bin/activate
   ./bin/orbit.sh start
   ```
   You should see `Uvicorn running on http://0.0.0.0:3000` in the logs.

> **Tip:** The basic Docker image (`schmitech/orbit:basic`) includes simple chat only. For database and file adapters, use the release tarball or a git checkout.

Quick health check:

```bash
curl -s http://localhost:3000/health
# {"status":"ok", ...}
```

If that responds, you're ready.

### CLI or web UI — your choice

Every admin task in this tutorial (creating API keys, managing prompts/personas, toggling adapters, editing config, viewing audit events, watching live metrics) can be done two ways:

- **CLI** — the `./bin/orbit.sh …` commands you'll see below.
- **Admin panel** — point your browser at **`http://localhost:3000/admin`** and sign in with the admin credentials from your `.env` (`ORBIT_DEFAULT_ADMIN_PASSWORD`, default username `admin`).

The panel covers Users, API Keys, Prompts/Personas, Adapters (with live toggle + per-adapter YAML editor), Settings (in-browser `config.yaml` editor), Audit, and Overview monitoring. The CLI is faster for scripted setup; the UI is friendlier for exploration. Use whichever you prefer — they act on the same underlying state.

### Install the chat client (`orbitchat`)

You'll see `orbitchat …` invocations throughout this tutorial — that's the standalone chat UI for testing adapters end-to-end. It's a separate npm package from the ORBIT server; it proxies your API requests so real API keys never reach the browser.

```bash
npm install -g orbitchat
```

Point it at your running server and an API key:

```bash
orbitchat --api-url http://localhost:3000 --api-key orbit_YOUR_KEY --open
```

That opens a browser against a local proxy (default `http://localhost:5173`). You can also run it against multiple adapters at once or as a proxy-only layer for your own UI — see [`clients/orbitchat/README.md`](../clients/orbitchat/README.md) for the full option reference, `orbitchat.yaml` config, and the HTTP contract for custom frontends.

> The **admin panel** at `/admin` is for configuration (keys, prompts, adapters, settings). **`orbitchat`** is for actually *chatting* with an adapter to test it. You'll use both.

---

## Your first chat (2 minutes)

Before touching any data source, let's confirm the full request path works end-to-end. The `simple-chat` adapter is pure conversational — no retrieval, no setup — so it's the fastest way to prove the server + API key + client flow is wired.

### 1. Create an API key

```bash
./bin/orbit.sh login --username admin --password admin123

./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "First Chat" \
  --prompt-text "You are a friendly assistant."
```

Copy the `orbit_…` key that's printed.

> Prefer clicking? Open `http://localhost:3000/admin` → **API Keys** → **+ Create**, pick `simple-chat` as the adapter, paste a prompt, and save. The key is shown once — copy it immediately.

### 2. Chat

```bash
orbitchat --api-url http://localhost:3000 --api-key orbit_YOUR_KEY --open
```

Ask it anything. **If you get a response, the stack is working.** If not, skip down to [Troubleshooting](#troubleshooting) before going further.

Now that you have a known-good baseline, pick an example below based on what you want to chat with.

---

## Adapter Types Overview

ORBIT picks the right retrieval strategy based on an *adapter type*. You don't choose these at query time — you configure them once in `config/adapters/*.yaml` and reference them by name when creating an API key.

| Adapter Type | Use it when… | Examples |
|:---|:---|:---|
| **Passthrough** | You want plain chat without retrieval | `simple-chat` |
| **Multimodal** | Users will upload files (PDF, images, audio) | `simple-chat-with-files` |
| **QA** | You have documents already embedded in a vector store | `qa-vector-chroma`, `qa-vector-qdrant` |
| **Intent SQL** | You have a SQL database and want NL → SQL | `intent-sql-sqlite-hr`, `intent-duckdb-analytics` |
| **Intent HTTP** | You want NL → REST API calls | `intent-http-jsonplaceholder` |
| **Intent MongoDB** | You have a MongoDB collection | `intent-mongodb-mflix` |
| **Intent GraphQL** | You have a GraphQL endpoint | `intent-graphql-spacex` |
| **Intent Agent** | You want function-calling with built-in tools | `intent-agent-example` |
| **Composite** | You want one chat that routes across several sources | `composite-multi-source` |

---

## Example 1: SQL Database (SQLite)

Let's try the most common ORBIT pattern: asking questions in English against a real SQL database. We'll use a small local SQLite file with sample HR data.

### 1. Generate sample data

```bash
python examples/intent-templates/sql-intent-template/examples/sqlite/hr/generate_hr_data.py \
  --records 100 \
  --output examples/intent-templates/sql-intent-template/examples/sqlite/hr/hr.db
```

### 2. Restart ORBIT

ORBIT preloads intent templates at startup, so a restart picks them up:

```bash
./bin/orbit.sh restart
```

### 3. Create an API key for the HR adapter

```bash
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-hr \
  --name "HR Chatbot" \
  --prompt-file ./examples/prompts/hr-assistant-prompt.txt \
  --prompt-name "HR Assistant"
```

### 4. Start chatting

```bash
orbitchat --api-url http://localhost:3000 --api-key YOUR_API_KEY --open
```

Try:

- "How many employees per department?"
- "What's the average salary per department?"
- "Show me employees hired in the last 30 days"
- "Which departments are over budget on payroll?"

### What's happening under the hood

1. ORBIT classifies the intent of your question.
2. It picks the closest SQL template from `intent-sql-sqlite-hr`'s template library.
3. An LLM extracts parameters (dates, names, numbers) from your question.
4. ORBIT runs the parameterized SQL against your database.
5. Results are formatted back into natural language.

Templates — not free-form SQL generation — are what make this safe and reliable. You'll see the same pattern in DuckDB, MongoDB, HTTP, and GraphQL adapters.

---

## Example 2: Chat with Files

Let users upload PDFs, images, or audio and ask questions about them. The `simple-chat-with-files` adapter is pre-configured in `config/adapters/multimodal.yaml`:

```yaml
- name: "simple-chat-with-files"
  enabled: true
  type: "passthrough"
  adapter: "multimodal"
  implementation: "implementations.passthrough.multimodal.MultimodalImplementation"

  # Provider overrides (defaults shown — swap as needed)
  inference_provider: "openai"
  model: "gpt-5.4-mini"
  embedding_provider: "openai"
  embedding_model: "text-embedding-3-small"
  vision_provider: "gemini"           # For image files
  stt_provider: "whisper"             # Local speech-to-text for audio

  capabilities:
    retrieval_behavior: "conditional" # Retrieves only when files are attached
    supports_file_ids: true

  config:
    chunking_strategy: "recursive"
    chunk_size: 1000
    vector_store: "chroma"
    max_results: 10
    return_results: 10
```

### Create an API key

```bash
./bin/orbit.sh key create \
  --adapter simple-chat-with-files \
  --name "Document Assistant" \
  --prompt-text "You are a helpful assistant that answers questions about uploaded documents. Be accurate and cite specific content from the files."
```

### Try it

1. Open the web chat (React app or embedded widget).
2. Attach a PDF, DOCX, image, or audio file.
3. Ask:
   - "Summarize this document"
   - "What are the key points in section 3?"
   - "What does the chart on page 2 show?" (images)
   - "Transcribe and summarize this audio file" (audio)

Retrieval only fires when there's a file attached — regular messages go straight to the LLM, keeping costs and latency down.

### Supported file types

| Category | Formats |
|:---|:---|
| Documents | PDF, DOCX, DOC, TXT, MD, HTML |
| Spreadsheets | XLSX, XLS, CSV |
| Data | JSON, XML |
| Images | PNG, JPEG, TIFF, GIF, WebP |
| Audio | WAV, MP3, OGG, FLAC, WebM, M4A |

---

## Example 3: Vector Store Q&A

If your documents are already embedded in a vector store, the QA adapter handles semantic search + answer generation.

### Option A: Chroma (runs locally, no extra services)

```bash
./examples/sample-db-setup.sh chroma
```

Configured in `config/adapters/qa.yaml`:

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

### Option B: Qdrant (Cloud or self-hosted)

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

### Create an API key

```bash
./bin/orbit.sh key create \
  --adapter qa-vector-chroma \
  --name "City Assistant" \
  --prompt-file ./examples/prompts/examples/city/city-assistant-normal-prompt.txt
```

**Tip:** If answers come back "I don't have information about that," lower `confidence_threshold` incrementally (try 0.2, then 0.15). Thresholds behave consistently across Chroma, Qdrant, FAISS, and Milvus as of 2.6.4.

---

## Example 4: DuckDB Analytics

DuckDB is ideal for analytical questions over columnar data — aggregations, trends, comparisons. Example from `config/adapters/intent.yaml`:

```yaml
- name: "intent-duckdb-analytics"
  enabled: true
  type: "retriever"
  datasource: "duckdb"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentDuckDBRetriever"
  database: "utils/duckdb-intent-template/examples/analytics/analytics.duckdb"

  inference_provider: "openai"
  model: "gpt-5.4-mini"
  embedding_provider: "openai"

  config:
    domain_config_path: "examples/intent-templates/duckdb-intent-template/examples/analytics/analytics_domain.yaml"
    template_library_path:
      - "examples/intent-templates/duckdb-intent-template/examples/analytics/analytics_templates.yaml"

    template_collection_name: "duckdb_analytics_templates"
    store_name: "chroma"
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 100

    # DuckDB-specific
    read_only: true
    access_mode: "READ_ONLY"
```

Good fits:

- "What was the total revenue last quarter?"
- "Show me sales trends by month"
- "Which products had the highest growth rate?"
- "Compare this year's performance to last year"

> You can stick with `ollama_cloud` / `gpt-oss:120b` if you prefer local-style hosted models — just update `inference_provider` and `model` to match whatever's enabled in your `config/inference.yaml`.

---

## Example 5: MongoDB Queries

Natural language → MongoDB find/aggregate queries.

```yaml
- name: "intent-mongodb-mflix"
  enabled: true
  type: "retriever"
  datasource: "mongodb"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.intent_mongodb_retriever.IntentMongoDBRetriever"

  inference_provider: "openai"
  model: "gpt-5.4-mini"
  embedding_provider: "openai"

  config:
    domain_config_path: "examples/intent-templates/mongodb-intent-template/examples/sample_mflix/templates/mflix_domain.yaml"
    template_library_path:
      - "examples/intent-templates/mongodb-intent-template/examples/sample_mflix/templates/mflix_templates.yaml"

    database: "sample_mflix"
    default_collection: "movies"
    default_limit: 100
    enable_text_search: true
    case_insensitive_regex: true
```

Using MongoDB's `sample_mflix` dataset:

- "Find movies directed by Christopher Nolan"
- "What are the top rated action movies from the 2000s?"
- "Show me movies with Leonardo DiCaprio"

---

## Example 6: HTTP APIs

Treat any REST API as a data source — no SQL, no embeddings, just templates mapped to HTTP requests.

```yaml
- name: "intent-http-jsonplaceholder"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentHTTPJSONRetriever"

  inference_provider: "openai"
  model: "gpt-5.4-mini"
  embedding_provider: "openai"

  config:
    domain_config_path: "examples/intent-templates/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_domain.yaml"
    template_library_path:
      - "examples/intent-templates/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_templates.yaml"

    base_url: "https://jsonplaceholder.typicode.com"
    default_timeout: 30
    enable_retries: true
    max_retries: 3
```

### Other HTTP-shaped adapters ready to try

| Adapter | Description |
|:---|:---|
| `intent-http-paris-opendata` | Paris city open data portal |
| `intent-graphql-spacex` | SpaceX GraphQL API |
| `intent-firecrawl-webscrape` | Web scraping via Firecrawl |

---

## Example 7: Multi-Source Composite

Point *one* chat interface at several data sources and let ORBIT figure out which one should answer each question. The Composite Intent Retriever searches every child adapter's template library and routes to the best match.

### How routing works

1. Configure multiple child intent adapters (SQL, DuckDB, MongoDB, HTTP, etc.).
2. A query arrives; ORBIT searches all child template stores in parallel.
3. The best matching template wins based on similarity score.
4. The query is dispatched to that child adapter.
5. The response includes metadata saying which source answered.

### Adapter configuration

In `config/adapters/composite.yaml`:

```yaml
adapters:
  - name: "composite-multi-source"
    enabled: true
    type: "retriever"
    adapter: "composite"
    implementation: "retrievers.implementations.composite.CompositeIntentRetriever"

    embedding_provider: "openai"

    config:
      child_adapters:
        - "intent-sql-sqlite-hr"
        - "intent-duckdb-ev-population"
        - "intent-mongodb-mflix"

      confidence_threshold: 0.4
      max_templates_per_source: 3
      parallel_search: true
      search_timeout: 5.0
```

### Create an API key

```bash
./bin/orbit.sh key create \
  --adapter composite-multi-source \
  --name "Multi-Source Explorer" \
  --prompt-text "You are a data assistant that can query multiple databases. Answer questions using the retrieved data."
```

### See routing in action

With HR, EV population, and Movie databases wired up:

- "How many employees are in Engineering?" → HR database
- "Count Tesla vehicles by city" → EV database
- "Find movies directed by Spielberg" → MongoDB

### Routing metadata returned with each response

```json
{
  "composite_routing": {
    "selected_adapter": "intent-duckdb-ev-population",
    "template_id": "ev_count_by_make",
    "similarity_score": 0.92,
    "adapters_searched": ["intent-sql-sqlite-hr", "intent-duckdb-ev-population", "intent-mongodb-mflix"]
  }
}
```

See [Composite Intent Retriever](adapters/composite-intent-retriever.md) for tuning reranking, string-similarity weighting, and cross-adapter templates.

---

## Example 8: Agent with Function Calling

The Agent Retriever extends the intent pattern with *tool execution*. Instead of returning retrieved documents, it runs built-in tools (calculator, date/time, JSON transforms) or calls external APIs (weather, finance, location) and synthesizes the result.

### How it works

1. User asks: "What is 15% of 200?"
2. ORBIT matches the query to a function template.
3. The function-calling model emits a tool call with parameters.
4. A built-in tool executes.
5. ORBIT synthesizes a natural-language reply.

### Built-in tools

| Tool | Operations | Examples |
|:---|:---|:---|
| **Calculator** | percentage, add, subtract, multiply, divide, average, round | "What is 20% of 500?" |
| **Date/Time** | now, format, diff, add_days, parse | "How many days until March 1st?" |
| **JSON Transform** | filter, sort, select, aggregate | "Filter items where price > 100" |

### HTTP-backed tools (require config)

| Tool | Description | Examples |
|:---|:---|:---|
| **Weather** | Current conditions and forecasts | "What's the weather in London?" |
| **Location** | Geocoding and place search | "Find coordinates of the Eiffel Tower" |
| **Finance** | Stock quotes and currency conversion | "Convert 100 USD to EUR" |
| **Productivity** | Notifications and tasks | "Create a task for tomorrow" |

### Adapter configuration (pre-wired in `config/adapters/intent.yaml`)

```yaml
- name: "intent-agent-example"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentAgentRetriever"

  # Embedding for template matching
  embedding_provider: "ollama"
  embedding_model: "nomic-embed-text"

  # Inference model for response synthesis
  inference_model_provider: "ollama"
  inference_model: "gemma3:270m"

  config:
    domain_config_path: "examples/intent-templates/agent-template/domain.yaml"
    template_library_path:
      - "examples/intent-templates/agent-template/tools.yaml"

    confidence_threshold: 0.6
    max_templates: 5

    agent:
      # Optional dedicated function-calling model
      function_model_provider: "ollama"
      function_model: "functiongemma"

      synthesize_response: true
```

### Create an API key

```bash
./bin/orbit.sh key create \
  --adapter intent-agent-example \
  --name "Agent Assistant" \
  --prompt-file ./examples/intent-templates/agent-template/agent-assistant-prompt.md \
  --prompt-name "Agent Assistant"
```

Or use the helper script:

```bash
./utils/scripts/generate-sample-api-keys.sh --adapter intent-agent-example
```

### Try it

**Calculator:** "What is 15% of 200?" · "Average of 10, 20, 30, 40" · "Multiply 125 by 8"

**Date/Time:** "What's today's date?" · "Days until December 25th?" · "Add 30 days to January 15, 2026"

**JSON Transform:** "Sort this data by price descending" · "Filter items where quantity > 10" · "Sum of all amounts"

**HTTP tools (when configured):** "Weather in San Francisco?" · "Apple stock price?" · "Convert 100 USD to EUR" · "Create a task to review the report"

### Multi-model setup (optional)

For better accuracy, split the work across specialized models:

```yaml
inference_model_provider: "ollama"
inference_model: "gemma3:270m"

embedding_provider: "ollama"
embedding_model: "nomic-embed-text"

config:
  agent:
    function_model_provider: "ollama"
    function_model: "functiongemma"
```

If no `function_model` is set, the inference model handles both synthesis and function calls.

### Response format

```json
{
  "content": "15% of 200 is **30**.",
  "metadata": {
    "tool_execution": {
      "tool_name": "calculator",
      "operation": "percentage",
      "parameters": {"value": 200, "percentage": 15},
      "result": {"result": 30},
      "status": "success"
    }
  }
}
```

See [Intent Agent Retriever](adapters/intent-agent-retriever.md) for custom tool development.

---

## Creating API Keys

API keys decide *which adapter* a caller uses and *which system prompt* gets injected. One key, one adapter, one prompt — that's the model.

You can create and manage keys either from the web admin panel or from the CLI.

### Option A — Admin panel (recommended for exploration)

1. Open **`http://localhost:3000/admin`** and sign in (default username `admin`, password from `ORBIT_DEFAULT_ADMIN_PASSWORD`).
2. Go to **API Keys** → **+ Create**.
3. Pick the adapter, name the key, paste or attach a system prompt, and save.
4. The `orbit_…` key is shown once — copy it immediately; ORBIT never shows it again.

The admin panel also lets you:

- Bulk-delete keys, search by name/adapter, and edit metadata/notes (markdown-rendered in the detail view).
- Attach or switch prompts (managed under the **Prompts / Personas** tab) without rotating the key.
- See recent activity for a key in the **Audit** tab (admin events auditing was added in 2.6.6).

### Option B — CLI (faster for scripted setup)

```bash
# Log in first
./bin/orbit.sh login --username admin --password admin123

# Inline prompt
./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "My Assistant" \
  --prompt-text "You are a helpful assistant."

# Prompt from file
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-hr \
  --name "HR Bot" \
  --prompt-file ./examples/prompts/hr-assistant-prompt.txt \
  --prompt-name "HR Assistant"

# List & delete
./bin/orbit.sh key list
./bin/orbit.sh key delete --key orbit_abc123...
```

### CLI options

| Option | Description |
|:---|:---|
| `--adapter` | Which adapter to bind |
| `--name` | Friendly name |
| `--prompt-text` | Inline system prompt |
| `--prompt-file` | Load system prompt from file |
| `--prompt-name` | Name the prompt for reuse |
| `--notes` | Optional notes (markdown rendered in admin) |

### What else lives in the admin panel

Beyond API keys, the panel at `/admin` handles everything you'd otherwise edit by hand or script:

| Tab | What you can do |
|:---|:---|
| **Overview** | Live system health, metrics, cached adapter/provider counts, Prometheus endpoint link |
| **Users** | Create/edit/delete admin users, reset passwords, bulk-delete |
| **API Keys** | CRUD with prompt attach/switch, search, quotas, bulk actions |
| **Prompts / Personas** | Author/edit/rename system prompts; changes propagate to associated API keys |
| **Adapters** | List all adapters, toggle `enabled` live (applies immediately as of 2.6.6), edit per-adapter YAML in an Ace editor, trigger `reload-adapters` and `reload-templates` |
| **Settings** | Edit `config.yaml` in the browser with validation before save |
| **Audit** | Browse admin/auth events (login, key mutations, config edits) and conversation audit logs when enabled |

> Tip: adapter toggles from the Adapters tab now notify the running server immediately (fix in 2.6.6) — no separate "Reload Adapter" click needed.

---

## Connecting Your Own Data

### SQL databases

1. Generate templates from your schema:
   ```bash
   python examples/intent-templates/sql-intent-template/generate_templates.py \
     --database path/to/your.db \
     --output templates/
   ```
2. Add the adapter to `config/adapters/intent.yaml`:
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
3. Restart ORBIT and create an API key against `my-database`.

### Vector stores

1. Index documents into Chroma, Qdrant, or Pinecone.
2. Configure a QA adapter with your collection name.
3. Create an API key against it.

### Files (no config needed)

The `simple-chat-with-files` adapter is already enabled. Create a key, upload files through the chat interface, and you're done.

---

## Adapter Configuration Reference

Every adapter accepts these shared fields:

```yaml
- name: "adapter-name"
  enabled: true                  # Toggle the adapter on/off (live-reloadable from admin)
  type: "retriever"              # "retriever" or "passthrough"

  # Provider overrides (optional — falls back to config/*.yaml defaults)
  inference_provider: "ollama"
  model: "llama3:8b"
  embedding_provider: "openai"
  reranker_provider: "cohere"

  capabilities:
    retrieval_behavior: "always" # "none", "always", or "conditional"
    formatting_style: "standard" # "standard" or "clean"
    supports_file_ids: false
    supports_threading: true

  fault_tolerance:
    operation_timeout: 30.0
    failure_threshold: 5
    max_retries: 3
```

Intent adapters add:

```yaml
config:
  domain_config_path: "path/to/domain.yaml"
  template_library_path:
    - "path/to/templates.yaml"
  template_collection_name: "my_templates"
  store_name: "chroma"           # Vector store used for template matching
  confidence_threshold: 0.4
  max_templates: 5
  return_results: 100
  reload_templates_on_start: true
  force_reload_templates: false
```

---

## Troubleshooting

| Symptom | Try this |
|:---|:---|
| `curl /health` hangs or refuses | Server isn't running — check `./bin/orbit.sh start` logs |
| "Adapter … is not available" | The adapter is disabled in `config/adapters/*.yaml`, or was toggled off in the admin panel. Toggling now applies immediately (2.6.6) |
| 401 or "unauthorized" from OpenAI / other provider | Set the provider's API key env var (e.g. `OPENAI_API_KEY`) before `./bin/orbit.sh start` |
| "No matching template found" | Lower `confidence_threshold`, or add more `nl_examples` to your template YAML |
| Slow template matching | Make sure your embedding provider is reachable; check logs for `Preloading embedding provider…` |
| File upload fails | Check `max_file_size` in the multimodal adapter and supported types above |
| Intent SQL returns wrong year / param | Explicit years should bind correctly on recent versions — double-check the template's parameter names |
| Vector QA returns "I don't have information about that" | Threshold may be too strict; drop `confidence_threshold` by 0.05–0.1 |

Logs live in `logs/orbit.log`. The admin panel's audit view (2.6.6) surfaces adapter toggles, config edits, and auth events.

---

## Next Steps

- [Configuration Guide](configuration.md) – full configuration reference
- [SQL Retriever Architecture](sql-retriever-architecture.md) – deep dive into intent SQL
- [Composite Intent Retriever](adapters/composite-intent-retriever.md) – multi-source routing details
- [Intent Agent Retriever](adapters/intent-agent-retriever.md) – function calling & custom tools
- [API Keys Guide](api-keys.md) – advanced key management
- [Authentication Guide](authentication.md) – users and roles
- [`orbitchat` chat client](../clients/orbitchat/README.md) – CLI flags, `orbitchat.yaml` config, proxy-only mode, and the HTTP contract for custom UIs
