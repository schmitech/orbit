# Capability Quick Reference Guide

## TL;DR

**Yes, capabilities apply to ALL adapter types!** Use this guide as a quick reference.

## All Available Capabilities

| Capability | Type | Default | Description |
|------------|------|---------|-------------|
| `retrieval_behavior` | enum | `"always"` | `"none"`, `"always"`, or `"conditional"` - controls when retrieval occurs |
| `formatting_style` | enum | `"standard"` | `"standard"` (with citations), `"clean"` (no citations), or `"custom"` |
| `supports_file_ids` | bool | `false` | Whether adapter can filter by file IDs |
| `supports_session_tracking` | bool | `false` | Whether adapter tracks sessions |
| `requires_api_key_validation` | bool | `false` | Whether API key validation is required |
| `supports_threading` | bool | `false` | Whether adapter supports conversation threading on cached datasets |
| `supports_language_filtering` | bool | `false` | Whether adapter can filter/boost by detected language |
| `skip_when_no_files` | bool | `false` | Skip retrieval when file_ids is empty (for conditional retrieval) |
| `required_parameters` | list | `[]` | Parameters that MUST be provided to the retriever |
| `optional_parameters` | list | `[]` | Parameters that CAN be provided to the retriever |
| `context_format` | string | `null` | Table format for intent data: `"markdown_table"`, `"toon"`, `"csv"`, or `null` (default pipe-separated) |
| `context_max_tokens` | int | `null` | Token budget for context trimming. Drops lowest-confidence documents when exceeded |
| `numeric_precision` | object | `{}` | Numeric formatting options, e.g. `{decimal_places: 2}` for rounding unformatted floats |

---

## Capability Templates by Adapter Type

### Passthrough - Conversational

```yaml
capabilities:
  retrieval_behavior: "none"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  requires_api_key_validation: false
```

**Adapters:** simple-chat, any pure conversational adapter

---

### Passthrough - Multimodal

```yaml
capabilities:
  retrieval_behavior: "conditional"
  formatting_style: "clean"
  supports_file_ids: true
  supports_session_tracking: true
  requires_api_key_validation: true
  skip_when_no_files: true
  optional_parameters:
    - "file_ids"
    - "api_key"
    - "session_id"
```

**Adapters:** simple-chat-with-files, any multimodal adapter

---

### QA - SQL (SQLite, PostgreSQL, MySQL, etc.)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: false        # QA adapters: simple Q&A, no follow-up threading
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** qa-sql, qa-postgres, qa-mysql, qa-oracle, any SQL QA

**Note:** QA adapters have `supports_threading: false` because they are simple question-answer agents that don't require follow-up conversations with cached resultsets.

---

### QA - Vector Store (Chroma, Qdrant, Pinecone, etc.)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: false        # QA adapters: simple Q&A, no follow-up threading
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** qa-vector-chroma, qa-vector-qdrant, qa-vector-pinecone, any vector QA

---

### Intent - SQL

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: true         # Intent adapters: support follow-up on cached datasets
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** intent-sql-postgres, intent-sql-sqlite, intent-duckdb-*, any SQL intent

**Note:** Intent adapters have `supports_threading: true` because they return complex datasets that users may want to ask follow-up questions about without re-querying the database.

---

### Intent - NoSQL (MongoDB, Elasticsearch)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: true         # Intent adapters: support follow-up on cached datasets
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** intent-mongodb-*, intent-elasticsearch-*, any NoSQL intent

---

### Intent - HTTP/API

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: true         # Intent adapters: support follow-up on cached datasets
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** intent-http-*, intent-firecrawl-*, any HTTP intent

---

### File - Document Q&A

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "clean"
  supports_file_ids: true
  supports_session_tracking: false
  requires_api_key_validation: true
  optional_parameters:
    - "file_ids"
    - "api_key"
```

**Adapters:** file-document-qa, any file-based adapter

---

## Common Customizations

### Remove Citations (Any Adapter)

```yaml
capabilities:
  formatting_style: "clean"  # Change from "standard"
```

**Use case:** Prevent LLM from adding citation markers like [1], [2]

### Add File Filtering (Any Retriever)

```yaml
capabilities:
  supports_file_ids: true
  optional_parameters:
    - "file_ids"
```

**Use case:** Allow filtering by specific documents/files

### Add Session Tracking (Any Adapter)

```yaml
capabilities:
  supports_session_tracking: true
  optional_parameters:
    - "session_id"
```

**Use case:** Track requests by session for analytics

### Make Retrieval Conditional (Any Retriever)

```yaml
capabilities:
  retrieval_behavior: "conditional"
  skip_when_no_files: true  # Or custom condition
```

**Use case:** Only retrieve when certain conditions are met

### Enable Conversation Threading (Intent Adapters)

```yaml
capabilities:
  supports_threading: true  # Enable follow-up questions on cached datasets
```

**Use case:** Allow users to ask follow-up questions about retrieved data without re-querying the datasource. The dataset is cached (in Redis or database) for a configurable TTL.

**Best for:** Intent adapters that return complex datasets (SQL results, API responses, etc.)

### Disable Conversation Threading (QA Adapters)

```yaml
capabilities:
  supports_threading: false  # Disable threading for simple Q&A
```

**Use case:** Simple question-answer flows where each query is independent and doesn't need follow-up on previous results.

**Best for:** QA adapters, passthrough adapters, simple FAQ bots

### Enable Language Filtering (Multilingual Adapters)

```yaml
capabilities:
  supports_language_filtering: true  # Filter/boost by detected language
```

**Use case:** Boost or filter search results based on the detected language of the user's query.

### Change Table Format (Intent Adapters)

```yaml
capabilities:
  context_format: "markdown_table"  # Options: markdown_table, toon, csv (default: pipe-separated)
```

**Use case:** Change how intent query results are rendered in the LLM context. Markdown tables are easier for LLMs to parse. TOON format (via `py_toon_format`) is the most compact. Default (null/omitted) preserves the original pipe-separated format.

### Limit Context Token Usage

```yaml
capabilities:
  context_max_tokens: 8000  # Drop lowest-confidence documents to stay under budget
```

**Use case:** Prevent context from consuming too much of the LLM's context window. Estimates tokens as `len(text) // 4` and drops documents from the end (lowest confidence) until within budget.

### Control Numeric Precision

```yaml
capabilities:
  numeric_precision:
    decimal_places: 2  # Round unformatted floats to 2 decimal places
```

**Use case:** Reduce noisy float values (e.g. `3.141592653589793` becomes `3.14`) in intent query results. Only applies to floats without an explicit `display_format` in the domain config.

---

## Decision Tree

```
What type of adapter do you have?

├─ Passthrough?
│  ├─ Pure chat? → Use "Passthrough - Conversational" template
│  └─ With files? → Use "Passthrough - Multimodal" template
│
├─ QA?
│  ├─ SQL-based? → Use "QA - SQL" template
│  └─ Vector-based? → Use "QA - Vector Store" template
│
├─ Intent?
│  ├─ SQL/DuckDB? → Use "Intent - SQL" template
│  ├─ MongoDB/Elasticsearch? → Use "Intent - NoSQL" template
│  └─ HTTP/API? → Use "Intent - HTTP/API" template
│
├─ File?
│  └─ Use "File - Document Q&A" template
│
└─ Custom?
   └─ Choose closest template and customize
```

---

## FAQs

**Q: Do I need to add capabilities to all adapters?**

A: No, it's optional. Auto-inference works for all adapter types. But it's recommended for production adapters.

**Q: Can I use capabilities with Intent adapters?**

A: Yes! Capabilities work with ALL adapter types including Intent.

**Q: Can I change formatting from standard to clean for a QA adapter?**

A: Yes! Just add `formatting_style: "clean"` in capabilities.

**Q: Do capabilities work with disabled adapters?**

A: Yes, but auto-inference is fine for disabled/example adapters.

**Q: Can I add custom parameters to any adapter?**

A: Yes! Use `optional_parameters` list in capabilities.

**Q: What is `supports_threading` and when should I use it?**

A: `supports_threading` enables conversation threading - caching retrieved datasets so users can ask follow-up questions without re-querying the datasource. Use `true` for Intent adapters (complex datasets), `false` for QA adapters (simple Q&A).

**Q: What's the difference between `required_parameters` and `optional_parameters`?**

A: `required_parameters` are mandatory - retrieval will fail without them. `optional_parameters` are passed to the retriever if provided but aren't required. Common optional parameters: `api_key`, `file_ids`, `session_id`.

**Q: What table format should I use for `context_format`?**

A: The default (omit or set to `null`) uses the original pipe-separated format. `"markdown_table"` produces standard markdown tables that most LLMs parse well. `"toon"` uses `py_toon_format` for the most compact output. `"csv"` uses CSV format. All formats are backward-compatible -- the default preserves existing behavior.

---

## Quick Copy-Paste

### QA Adapter (Simple Q&A, No Threading)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_threading: false
```

### Intent Adapter (Complex Datasets, With Threading)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_threading: true
  # context_format: "markdown_table"  # Optional: markdown_table, toon, csv
  # context_max_tokens: 8000          # Optional: token budget for context
  # numeric_precision:                # Optional: round unformatted floats
  #   decimal_places: 2
```

### File/Multimodal Adapter (Clean Formatting)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "clean"
  supports_file_ids: true
  requires_api_key_validation: true
```

### Passthrough Adapter (No Retrieval)

```yaml
capabilities:
  retrieval_behavior: "none"
  formatting_style: "standard"
  supports_file_ids: false
```

---

**Remember: Capabilities are universal - they work with EVERY adapter type!**
