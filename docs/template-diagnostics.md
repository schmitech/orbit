# Template Diagnostics - Intent Retriever Testing Tool

## Table of Contents
1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Admin API Endpoint](#admin-api-endpoint)
4. [CLI Tool](#cli-tool)
5. [Output Reference](#output-reference)
6. [Examples](#examples)
7. [Troubleshooting](#troubleshooting)

## Overview

Template Diagnostics is a built-in tool for testing intent retriever templates without going through the full LLM inference pipeline. When developing or tweaking intent templates, you often need to verify that:

- A natural language query matches the correct template
- Similarity scores are above your confidence threshold
- Parameters are extracted correctly from the query
- The rendered query (SQL, GraphQL, HTTP, MongoDB) is correct
- The datasource returns the expected results

Normally, testing a template requires a full round-trip through the pipeline: safety filter, context retrieval, document reranking, LLM inference, and response validation. Template Diagnostics bypasses the LLM and safety steps entirely, exercising only the retriever portion of the pipeline:

```
Normal pipeline:       Safety → Context Retrieval → Reranking → LLM → Validation
                                 ↑
Template Diagnostics:  Template Search → Reranking → Parameter Extraction → Query Execution
                       (only this part)
```

This makes template iteration fast and cost-effective since no LLM inference tokens are consumed for the response generation step.

### Supported Retriever Types

Template Diagnostics works with all intent-based adapters:

| Retriever Type | Query Type Shown |
|---|---|
| IntentSQLiteRetriever | Rendered SQL query |
| IntentDuckDBRetriever | Rendered SQL query |
| IntentPostgreSQLRetriever | Rendered SQL query |
| IntentMySQLRetriever | Rendered SQL query |
| IntentHTTPJSONRetriever | HTTP endpoint, method, parameters |
| IntentGraphQLRetriever | GraphQL query with variables |
| IntentMongoDBRetriever | MongoDB query pipeline |
| IntentElasticsearchRetriever | Elasticsearch query DSL |
| IntentFirecrawlRetriever | Firecrawl URL and parameters |
| IntentAgentRetriever | Function schema and parameters |
| CompositeIntentRetriever | Routes to child adapter, shows routing info |

## How It Works

The diagnostic pipeline executes the following steps in order, collecting timing and intermediate results at each stage:

### Step 1: Template Search
Embeds the query and searches the adapter's template vector store for matching templates using cosine similarity. Returns all candidates above the confidence threshold, with their similarity scores.

### Step 2: Reranking
If the adapter has a template reranker configured, applies domain-specific reranking rules. Reports the before/after ordering so you can see if reranking changed the selection.

### Step 3: Parameter Extraction
Extracts parameters from the query for the top-scoring template. Uses the domain parameter extractor (regex patterns) with LLM fallback if needed. Reports which method was used and any validation errors.

### Step 4: Query Rendering
Renders the final query by processing the template with extracted parameters. For SQL templates, this means Jinja2 rendering and parameter substitution. For HTTP, it shows the endpoint URL and parameters.

### Step 5: Query Execution (optional)
Executes the rendered query against the actual datasource and returns the raw results. This step can be skipped with the `--no-execute` flag if you only want to test template matching.

For **composite retrievers**, the flow is different:
1. Searches all child adapters' template stores in parallel
2. Applies multi-stage scoring if enabled (embedding + reranking + string similarity)
3. Selects the best matching child adapter
4. Runs steps 3-5 against that child adapter

## Admin API Endpoint

### `POST /admin/adapters/{adapter_name}/test-query`

Test a query against an adapter's intent templates.

**Authentication:** Requires an admin bearer token (obtained via `orbit login` as an admin user). Regular adapter API keys are not accepted.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `adapter_name` | string | Name of the adapter to test (must be an intent-based adapter) |

**Request Body:**

```json
{
  "query": "what are the salary statistics?",
  "max_templates": 5,
  "execute": true,
  "include_all_candidates": false,
  "verbose": false
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | (required) | Natural language query to test |
| `max_templates` | integer | 5 | Maximum template candidates to return |
| `execute` | boolean | true | Whether to execute the query against the datasource |
| `include_all_candidates` | boolean | false | Include full details (query template, parameters) for all candidates |
| `verbose` | boolean | false | Include extended diagnostics: vector store health, template inventory, domain config, semantic analysis |

**Response:** See [Output Reference](#output-reference).

**Error Responses:**

| Status | Condition |
|---|---|
| 401 | Missing or invalid/expired bearer token |
| 403 | Authenticated user is not an admin |
| 400 | Adapter is not an intent-based retriever |
| 404 | Adapter not found |
| 503 | Adapter manager unavailable |

**Example with curl:**

```bash
curl -X POST http://localhost:3000/admin/adapters/intent-sql-sqlite-hr/test-query \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the salary statistics?"}'
```

## CLI Tool

A command-line tool is provided at `server/tools/test_template_query.py` that calls the admin endpoint and pretty-prints the results.

### Usage

```bash
python server/tools/test_template_query.py \
  --query <query> \
  --adapter <adapter-name> \
  --api-key <admin-token> \
  [--server-url <url>] \
  [--no-execute] \
  [--all-candidates] \
  [--verbose] \
  [--max-templates <n>] \
  [--output json|pretty] \
  [--no-color] \
  [--timeout <seconds>]
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--query` | `-q` | (required) | Natural language query to test |
| `--adapter` | `-a` | (required) | Adapter name to test against |
| `--api-key` | `-k` | (required) | Admin bearer token (from `orbit login`, see below) |
| `--server-url` | `-s` | `http://localhost:3000` | ORBIT server URL |
| `--no-execute` | | false | Skip query execution (template matching only) |
| `--all-candidates` | | false | Show full details for all candidates |
| `--verbose` | `-V` | false | Extended diagnostics: vector store health, template inventory, domain config, semantic analysis |
| `--max-templates` | | 5 | Max candidates to return |
| `--output` | | `pretty` | Output format: `pretty` (colored) or `json` (raw) |
| `--no-color` | | false | Disable ANSI colors |
| `--timeout` | | 30 | Request timeout in seconds |

### Prerequisites

The ORBIT server must be running and the target adapter must be loaded. You must be logged in as an admin user.

### Getting the Admin Token

The `--api-key` flag requires the admin bearer token, **not** an adapter API key. After logging in with `orbit login` as an admin user, retrieve the token from your system keychain:

**macOS:**
```bash
security find-generic-password -s "orbit-cli" -a "auth-token" -w
```

**Linux (GNOME Keyring):**
```bash
secret-tool lookup service "orbit-cli" account "auth-token"
```

**Inline usage (macOS):**
```bash
python server/tools/test_template_query.py \
  --query "salary stats" \
  --adapter intent-sql-sqlite-hr \
  --api-key "$(security find-generic-password -s 'orbit-cli' -a 'auth-token' -w)"
```

## Output Reference

The diagnostic response is a JSON object with the following structure:

```json
{
  "adapter_name": "intent-sql-sqlite-hr",
  "adapter_type": "IntentSQLiteRetriever",
  "query": "what are the salary statistics?",

  "timing": {
    "template_search_ms": 85.2,
    "reranking_ms": 1.3,
    "parameter_extraction_ms": 120.5,
    "query_execution_ms": 8.1,
    "total_ms": 215.1
  },

  // --- Verbose-only sections (included when verbose=true) ---

  "vector_store_info": {
    "store_type": "chroma",
    "collection_name": "hr_intent_templates",
    "total_vectors": 47,
    "cached_templates": 15,
    "embedding_dimension": 768,
    "embedding_provider": "voyage",
    "embedding_model": "voyage-3",
    "query_embedding_dimension": 768,
    "dimension_match": true
  },

  "template_inventory": {
    "total_templates": 15,
    "templates": [
      {"id": "salary_statistics", "description": "...", "nl_examples_count": 4, "parameters_count": 1, "query_type": "sql", "has_semantic_tags": true}
    ]
  },

  "domain_info": {
    "domain_name": "hr",
    "domain_type": "generic",
    "entities": ["employees", "departments", "positions"],
    "entity_synonyms": {"employees": ["staff", "workers"]},
    "field_synonyms": {"salary": ["pay", "compensation"]},
    "searchable_fields": ["name", "department"],
    "filterable_fields": ["department", "status", "salary"]
  },

  // --- Standard sections (always included) ---

  "template_search": {
    "candidates_found": 5,
    "confidence_threshold": 0.4,
    "candidates": [
      {
        "template_id": "salary_statistics",
        "similarity": 0.8793,
        "description": "Get salary statistics across all active employees",
        "nl_examples": ["what are the salary stats?", "show salary overview"],
        "category": "compensation",
        "rescued_by_nl_example": false
      }
    ]
  },

  "reranking": {
    "applied": true,
    "order_changed": false,
    "pre_rerank_order": ["salary_statistics", "salary_percentile_analysis"],
    "post_rerank_order": ["salary_statistics", "salary_percentile_analysis"],
    "reranked_scores": [
      {"template_id": "salary_statistics", "original_similarity": 0.629, "boost": 0.250, "final_similarity": 0.879},
      {"template_id": "salary_percentile_analysis", "original_similarity": 0.497, "boost": 0.050, "final_similarity": 0.547}
    ]
  },

  "selected_template": {
    "template_id": "salary_statistics",
    "similarity": 0.8793,
    "description": "Get salary statistics across all active employees",
    "nl_examples": ["what are the salary stats?"],
    "category": "compensation",
    "rescued_by_nl_example": false,
    "query_type": "sql",
    "query_template": "SELECT MIN(ep.salary) as min_salary, ...",
    "parameters_defined": [
      {"name": "department", "type": "string", "required": false, "description": "Filter by department", "default": null}
    ]
  },

  "parameter_extraction": {
    "extracted": {},
    "method": "domain_extractor",
    "validation_errors": [],
    "trace": {
      "patterns_available": 12,
      "pattern_regexes": {
        "employee.department": "(?:department|dept)\\s*[:=]?\\s*(\\w+)",
        "employee.salary": "(\\d+(?:,\\d{3})*(?:\\.\\d+)?)"
      },
      "first_pass_matches": {},
      "per_parameter": [
        {
          "name": "department",
          "type": "string",
          "entity": "employee",
          "field": "department",
          "required": false,
          "has_default": false,
          "pattern_key": "employee.department",
          "pattern_exists": true,
          "pattern_regex": "(?:department|dept)\\s*[:=]?\\s*(\\w+)",
          "resolution": "not_found",
          "value": null
        }
      ],
      "llm_fallback_params": []
    }
  },

  "rendered_query": {
    "type": "sql",
    "query": "SELECT MIN(ep.salary) as min_salary, MAX(ep.salary) as max_salary, AVG(ep.salary) as avg_salary, COUNT(DISTINCT e.id) as total_employees FROM employee_positions ep INNER JOIN employees e ON ep.employee_id = e.id WHERE ep.end_date IS NULL AND e.status = 'active'",
    "parameters": {}
  },

  "templates_tried": [
    {"template_id": "salary_statistics", "similarity": 0.879, "outcome": "success", "row_count": 1}
  ],

  "execution": {
    "success": true,
    "row_count": 1,
    "results": [
      {"min_salary": 43000, "max_salary": 240000, "avg_salary": 105752.89, "total_employees": 1295}
    ],
    "error": null
  },

  // --- Verbose-only ---

  "semantic_analysis": {
    "query_words": ["what", "are", "the", "salary", "statistics"],
    "template_has_semantic_tags": true,
    "primary_entity": "salary",
    "action": "statistics",
    "qualifiers": ["aggregate"],
    "entity_match": true,
    "action_match": true,
    "matched_qualifiers": ["aggregate"]
  },

  "composite_routing": null
}
```

### Composite Retriever Output

When testing a composite adapter, the `composite_routing` field contains routing details:

```json
{
  "composite_routing": {
    "child_adapters_searched": [
      "intent-duckdb-ottawa-police-auto-theft",
      "intent-duckdb-ev-population",
      "intent-duckdb-analytics"
    ],
    "selected_adapter": "intent-duckdb-ev-population",
    "selected_template_id": "ev_count_by_make",
    "multistage_enabled": true
  }
}
```

The template search candidates for composite adapters include the `source_adapter` field to show which child adapter each candidate came from.

### Partial Results on Failure

Each step is independently wrapped in error handling. If a step fails, all preceding steps still return their results, and the failed step includes an `error` field. This lets you pinpoint exactly which stage is failing.

For example, if parameter extraction fails but template search succeeded:

```json
{
  "template_search": { "candidates_found": 3, "candidates": [...] },
  "parameter_extraction": { "error": "Inference client not available", "extracted": {}, "method": "failed" },
  "rendered_query": null,
  "execution": null
}
```

## Verbose Diagnostics

Use `--verbose` (or `-V`) to include extended diagnostic sections that help debug deeper issues:

| Section | What It Shows | When to Use |
|---|---|---|
| `vector_store_info` | Store type, collection name, vector count, embedding dimensions, dimension match | Embedding mismatch issues, empty search results, store health |
| `template_inventory` | All loaded templates with example/parameter counts and query types | Verify templates were loaded from YAML, check for missing templates |
| `domain_info` | Entity names, synonyms, field synonyms, searchable/filterable fields | Debug parameter extraction failures, understand what the domain recognizes |
| `semantic_analysis` | How query words align with the selected template's semantic tags | Understand why reranking boosted or didn't boost a template |
| `templates_tried` | Outcome of each template attempt (success, param_validation_failed, execution_error) | Find out why the expected template was skipped in favor of another |

### Extraction Trace

The `parameter_extraction.trace` section (always included when a domain extractor is available) provides a full per-parameter resolution trace that mirrors the internal `DomainParameterExtractor.extract_parameters()` logic:

**Global info:**
- `patterns_available`: Number of regex patterns built from the domain config
- `pattern_regexes`: The actual regex strings for each `entity.field` pattern (useful for verifying patterns match your data)
- `first_pass_matches`: Results of the bulk pattern scan across all searchable/filterable fields

**Per-parameter resolution** (`per_parameter` array) — for each template parameter, shows:
- `pattern_key`: The `entity.field` key used for lookup (e.g., `employee.department`)
- `pattern_exists`: Whether a regex pattern exists for this key
- `pattern_regex`: The actual regex being used
- `resolution`: How the value was found (or why it wasn't):
  - `entity_field_pattern` — matched via entity.field regex in first pass
  - `param_name_pattern` — matched via parameter name in first pass
  - `context_extraction` — found via field synonyms and context clues (e.g., "department is engineering")
  - `template_parameter` — extracted via domain strategy or generic type-based extraction
  - `default` — no value found, using template default
  - `not_found` — no value found, no default available
  - `validation_failed` — value found but rejected by domain validator
  - `coercion_failed` — value found but type conversion failed (e.g., "abc" as integer)
- `raw_value`: The value before validation/coercion (shown when validation fails)
- `validation_error` / `coercion_error`: The specific error message
- `llm_fallback_needed`: Whether this required parameter would trigger an LLM extraction call

This is essential for debugging why a parameter wasn't extracted — you can see the exact resolution path, which regex was tried, whether the pattern exists at all, and whether the value was found but then rejected by validation.

### Reranking Boost Breakdown

The `reranking.reranked_scores` array now includes the boost breakdown per template:
- `original_similarity`: The raw embedding similarity score before reranking
- `boost`: The domain-specific boost applied (from semantic tag matching, entity/action synonyms, nl_example proximity)
- `final_similarity`: The capped (max 1.0) score after boosting

This helps explain why a template with a lower embedding score may outrank one with a higher score.

## Examples

### Testing an SQL Adapter

```bash
python server/tools/test_template_query.py \
  --query "how many employees are in engineering?" \
  --adapter intent-sql-sqlite-hr \
  --api-key <admin-token>
```

### Testing an HTTP API Adapter

```bash
python server/tools/test_template_query.py \
  --query "what events are happening in Paris this weekend?" \
  --adapter intent-http-paris-opendata \
  --api-key <admin-token>
```

### Testing a Composite Adapter

```bash
python server/tools/test_template_query.py \
  --query "show auto theft by neighbourhood" \
  --adapter composite-multi-source-explorer \
  --api-key <admin-token>
```

### Verbose Diagnostics (Deep Debug)

```bash
python server/tools/test_template_query.py \
  --query "salary in engineering department" \
  --adapter intent-sql-sqlite-hr \
  --api-key <admin-token> \
  --verbose
```

### Template Matching Only (No Execution)

Useful when the datasource is unavailable or you only want to verify template matching:

```bash
python server/tools/test_template_query.py \
  --query "top rated movies from 2020" \
  --adapter intent-mongodb-mflix \
  --api-key <admin-token> \
  --no-execute
```

### JSON Output for Scripting

```bash
python server/tools/test_template_query.py \
  --query "salary stats" \
  --adapter intent-sql-sqlite-hr \
  --api-key <admin-token> \
  --output json | jq '.execution.row_count'
```

### Batch Testing Multiple Queries

```bash
while IFS= read -r query; do
  echo "--- Testing: $query ---"
  python server/tools/test_template_query.py \
    --query "$query" \
    --adapter intent-sql-sqlite-hr \
    --api-key <admin-token> \
    --output json | jq '{query: .query, template: .selected_template.template_id, similarity: .selected_template.similarity, rows: .execution.row_count}'
done << 'EOF'
what are the salary statistics?
how many employees are in each department?
show me the top earners
who was hired last month?
EOF
```

## Troubleshooting

### "Adapter not found"
The adapter name must match exactly what is defined in the adapter YAML config files (`config/adapters/*.yaml`). Check available adapters with:
```bash
curl http://localhost:3000/admin/adapters/info -H "Authorization: Bearer <key>"
```

### "Not an intent retriever"
The test-query endpoint only works with intent-based adapters (SQL, HTTP, GraphQL, MongoDB, Elasticsearch, Firecrawl, Agent, or Composite). Passthrough and QA adapters are not supported.

### Template search returns 0 candidates
- Templates may not be loaded yet. Try reloading: `curl -X POST http://localhost:3000/admin/reload-templates -H "Authorization: Bearer <key>"`
- The embedding service may be down. Check server logs for embedding errors.
- The confidence threshold may be too high. Try lowering it in the adapter config.

### Parameter extraction fails
Parameter extraction uses the LLM inference provider configured on the adapter. If the inference provider is unavailable, extraction will fail. The template search and reranking results are still returned.

### Query execution fails
Check that the datasource is accessible (database running, API reachable). The rendered query is still shown so you can test it manually.
