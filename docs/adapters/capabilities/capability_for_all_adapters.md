# Capabilities System: Universal Application Guide

## Overview

The capability system is **UNIVERSAL** and applies to **ALL adapter types** in ORBIT, not just passthrough or file-based adapters.

## Complete Capability Reference

All available capabilities that can be configured for any adapter:

| Capability | Type | Default | Description |
|------------|------|---------|-------------|
| `retrieval_behavior` | enum | `"always"` | Controls when retrieval occurs: `"none"` (no retrieval), `"always"` (always retrieve), `"conditional"` (based on conditions) |
| `formatting_style` | enum | `"standard"` | How results are formatted: `"standard"` (with citations/confidence), `"clean"` (no citations), `"custom"` (adapter provides formatting) |
| `supports_file_ids` | bool | `false` | Whether adapter can filter results by file IDs |
| `supports_session_tracking` | bool | `false` | Whether adapter tracks and uses session IDs |
| `requires_api_key_validation` | bool | `false` | Whether API key validation is required for ownership checks |
| `supports_threading` | bool | `false` | Whether adapter supports conversation threading on cached datasets (see Threading section below) |
| `supports_language_filtering` | bool | `false` | Whether adapter can filter/boost results by detected query language |
| `skip_when_no_files` | bool | `false` | For conditional retrieval: skip when file_ids is empty |
| `required_parameters` | list | `[]` | Parameters that MUST be provided to the retriever |
| `optional_parameters` | list | `[]` | Parameters that CAN be provided (e.g., `api_key`, `file_ids`, `session_id`) |
| `context_format` | string | `null` | Table format for intent data: `"markdown_table"`, `"toon"`, `"csv"`, or `null` (default pipe-separated) |
| `context_max_tokens` | int | `null` | Token budget for context trimming. Drops lowest-confidence documents when exceeded |
| `numeric_precision` | object | `{}` | Numeric formatting options, e.g. `{decimal_places: 2}` for rounding unformatted floats |

### Conversation Threading (`supports_threading`)

Conversation threading allows users to ask follow-up questions about retrieved data without re-querying the datasource:

- **How it works:** When enabled, the retrieved dataset is cached (in Redis with TTL, or database) after the initial query. Follow-up messages use the cached data instead of hitting the datasource again.
- **Use `true` for:** Intent adapters that return complex datasets (SQL results, API responses, aggregations) where users often want to explore the data further.
- **Use `false` for:** QA adapters that provide simple question-answer flows, passthrough adapters, and any adapter where each query should be independent.

```yaml
# Intent adapter - enable threading for follow-up questions
capabilities:
  supports_threading: true

# QA adapter - disable threading for simple Q&A
capabilities:
  supports_threading: false
```

### Context Efficiency (`context_format`, `context_max_tokens`, `numeric_precision`)

These capabilities control how context is formatted and sized before being sent to the LLM, reducing token usage and improving parsing reliability.

**`context_format`** -- Controls the table format used by intent retrievers when rendering query results:

| Value | Description |
|-------|-------------|
| `null` (default) | Pipe-separated format: `col1 \| col2 \| col3` |
| `"markdown_table"` | Standard markdown: `\| col1 \| col2 \|` with `---` separator |
| `"toon"` | Compact format via `py_toon_format` (falls back to pipe-separated if not installed) |
| `"csv"` | CSV format output |

**`context_max_tokens`** -- Sets a token budget for the formatted context. After formatting, if the estimated token count (`len(text) // 4`) exceeds the budget, lowest-confidence documents are dropped from the end until the context fits. Useful for adapters that may return large result sets.

**`numeric_precision`** -- Controls rounding of unformatted float values in intent query results. Only applies to floats that don't already have a `display_format` in the domain config (currency, percentage, etc. are unaffected).

```yaml
# Intent adapter with context efficiency options
capabilities:
  context_format: "markdown_table"   # LLM-friendly table format
  context_max_tokens: 8000           # Trim context to ~8k tokens
  numeric_precision:
    decimal_places: 2                # Round 3.141592... to 3.14
```

## Universal Applicability

### ✅ Works with ALL Adapter Types

| Adapter Type | Capabilities Apply? | Example Adapters |
|--------------|---------------------|------------------|
| **Passthrough** | ✅ Yes | simple-chat, simple-chat-with-files |
| **File-Based** | ✅ Yes | file-document-qa |
| **QA (SQL)** | ✅ Yes | qa-sql |
| **QA (Vector)** | ✅ Yes | qa-vector-chroma, qa-vector-qdrant |
| **Intent (SQL)** | ✅ Yes | intent-sql-postgres, intent-sql-sqlite |
| **Intent (NoSQL)** | ✅ Yes | intent-mongodb-mflix |
| **Intent (DuckDB)** | ✅ Yes | intent-duckdb-analytics |
| **Intent (HTTP)** | ✅ Yes | intent-http-jsonplaceholder |
| **Intent (Elasticsearch)** | ✅ Yes | intent-elasticsearch-app-logs |
| **Intent (Firecrawl)** | ✅ Yes | intent-firecrawl-webscrape |
| **Custom Adapters** | ✅ Yes | Any adapter you create |

**Answer: Capabilities apply to EVERY adapter type!** 🎯

## Optional vs Recommended

### Optional (Auto-Inference)

```yaml
# Option 1: No explicit capabilities - auto-inferred
- name: "my-adapter"
  type: "retriever"
  adapter: "qa"
  # Capabilities automatically inferred as:
  # - retrieval_behavior: "always"
  # - formatting_style: "standard"
  # - supports_file_ids: false
```

**Auto-inference rules:**
- `type: "passthrough"` + `adapter: "conversational"` → No retrieval
- `type: "passthrough"` + `adapter: "multimodal"` → Conditional retrieval (files)
- `adapter: "file"` → Always retrieve, clean formatting
- All other retrievers → Always retrieve, standard formatting

### Recommended (Explicit Declaration)

```yaml
# Option 2: Explicit capabilities - self-documenting
- name: "my-adapter"
  type: "retriever"
  adapter: "qa"
  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: false
  # Clear, explicit, easy to modify
```

**When to use explicit:**
- ✅ Production/enabled adapters
- ✅ Adapters with non-standard behavior
- ✅ When behavior clarity is important
- ✅ When you might modify behavior later

## Capability Examples by Adapter Type

### 1. Passthrough Adapters

#### Pure Conversational (No Retrieval)

```yaml
- name: "simple-chat"
  type: "passthrough"
  adapter: "conversational"

  capabilities:
    retrieval_behavior: "none"         # No retrieval
    formatting_style: "standard"
    supports_file_ids: false
    supports_session_tracking: false
    requires_api_key_validation: false
```

**Use case:** Chat without any context retrieval

#### Multimodal (Conditional File Retrieval)

```yaml
- name: "simple-chat-with-files"
  type: "passthrough"
  adapter: "multimodal"

  capabilities:
    retrieval_behavior: "conditional"  # Only when files present
    formatting_style: "clean"          # No citations
    supports_file_ids: true
    supports_session_tracking: true
    requires_api_key_validation: true
    skip_when_no_files: true
```

**Use case:** Chat that can optionally use uploaded files

### 2. QA Adapters (SQL-based)

```yaml
- name: "qa-sql"
  type: "retriever"
  adapter: "qa"
  datasource: "sqlite"

  capabilities:
    retrieval_behavior: "always"       # Always query database
    formatting_style: "standard"       # With citations
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: false          # Simple Q&A - no follow-up threading needed
    requires_api_key_validation: false
    optional_parameters:
      - "api_key"
```

**Use case:** Q&A from SQL database (SQLite, PostgreSQL, MySQL, etc.)

**Why `supports_threading: false`?** QA adapters are simple question-answer agents. Each query is independent and doesn't require follow-up conversations with cached resultsets.

**Also applies to:**
- `qa-postgres`
- `qa-mysql`
- `qa-oracle`
- Any SQL-based QA adapter

### 3. QA Adapters (Vector-based)

```yaml
- name: "qa-vector-chroma"
  type: "retriever"
  adapter: "qa"
  datasource: "chroma"

  capabilities:
    retrieval_behavior: "always"       # Always search vector store
    formatting_style: "standard"       # With citations and confidence
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: false          # Simple Q&A - no follow-up threading needed
    requires_api_key_validation: false
```

**Use case:** Q&A from vector databases (ChromaDB, Qdrant, Pinecone, Milvus)

**Also applies to:**
- `qa-vector-qdrant`
- `qa-vector-pinecone`
- `qa-vector-milvus`
- Any vector store QA adapter

### 4. Intent Adapters (SQL-based)

```yaml
- name: "intent-sql-postgres"
  type: "retriever"
  adapter: "intent"
  datasource: "postgres"

  capabilities:
    retrieval_behavior: "always"       # Always match intents
    formatting_style: "standard"       # With query results
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: true           # Enable follow-up questions on cached datasets
    requires_api_key_validation: false
```

**Use case:** Natural language to SQL query generation

**Why `supports_threading: true`?** Intent adapters return complex datasets (SQL results, aggregations) that users often want to explore further. Threading caches the dataset so follow-up questions don't re-query the database.

**Also applies to:**
- `intent-sql-sqlite`
- `intent-sql-mysql`
- `intent-duckdb-analytics`
- Any SQL intent adapter

### 5. Intent Adapters (NoSQL-based)

```yaml
- name: "intent-mongodb-mflix"
  type: "retriever"
  adapter: "intent"
  datasource: "mongodb"

  capabilities:
    retrieval_behavior: "always"       # Always match intents
    formatting_style: "standard"       # With aggregation results
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: true           # Enable follow-up questions on cached datasets
    requires_api_key_validation: false
```

**Use case:** Natural language to MongoDB aggregation pipeline generation

**Also applies to:**
- `intent-elasticsearch`
- Any NoSQL intent adapter

### 6. Intent Adapters (HTTP/API-based)

```yaml
- name: "intent-http-jsonplaceholder"
  type: "retriever"
  adapter: "intent"
  datasource: "http"

  capabilities:
    retrieval_behavior: "always"       # Always call API
    formatting_style: "standard"       # With API responses
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: true           # Enable follow-up questions on cached datasets
    requires_api_key_validation: false
```

**Use case:** Natural language to REST API calls

**Also applies to:**
- `intent-firecrawl-webscrape` (web scraping)
- Any HTTP/API intent adapter

### 7. File-Based Adapters

```yaml
- name: "file-document-qa"
  type: "retriever"
  adapter: "file"
  datasource: "none"

  capabilities:
    retrieval_behavior: "always"       # Always retrieve from files
    formatting_style: "clean"          # No citations (prevents LLM artifacts)
    supports_file_ids: true            # Filter by specific files
    supports_session_tracking: false
    requires_api_key_validation: true  # Validate file ownership
    optional_parameters:
      - "file_ids"
      - "api_key"
```

**Use case:** Q&A from uploaded files (PDF, DOCX, CSV, etc.)

## Advanced: Custom Capability Patterns

### Pattern 1: Conditional Retrieval with Custom Parameter

```yaml
- name: "conditional-custom-adapter"
  type: "retriever"
  adapter: "custom"

  capabilities:
    retrieval_behavior: "conditional"  # Retrieve based on conditions
    formatting_style: "standard"
    supports_file_ids: false
    # Custom condition: only retrieve if user_tier is "premium"
    optional_parameters:
      - "user_tier"
      - "api_key"
```

**Implementation:**
```python
def should_retrieve(self, context):
    if self.capabilities.retrieval_behavior == RetrievalBehavior.CONDITIONAL:
        # Custom logic: check user_tier
        return context.metadata.get('user_tier') == 'premium'
    return True
```

### Pattern 2: Clean Formatting for All Retrievers

Want to prevent LLM citation markers across all adapters?

```yaml
# Apply to any adapter
capabilities:
  formatting_style: "clean"  # No citations, just content
```

**Works for:**
- QA adapters (SQL or Vector)
- Intent adapters
- File adapters
- Custom adapters

### Pattern 3: File Filtering for Non-File Adapters

Want a QA adapter that can filter by specific documents?

```yaml
- name: "qa-sql-with-doc-filter"
  type: "retriever"
  adapter: "qa"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: true  # Enable document filtering!
    optional_parameters:
      - "file_ids"  # Can now pass document IDs
```

### Pattern 4: Context Efficiency for Intent Adapters

Reduce token usage and improve LLM parsing for intent adapters that return large datasets:

```yaml
- name: "intent-sql-postgres"
  type: "retriever"
  adapter: "intent"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_threading: true
    context_format: "markdown_table"  # Better LLM parsing than pipe-separated
    context_max_tokens: 8000          # Trim large result sets
    numeric_precision:
      decimal_places: 2              # Clean up noisy floats
```

**Works for:**
- All intent adapters (SQL, HTTP, GraphQL, MongoDB, Elasticsearch)
- Any adapter that returns tabular data

## Migration Path for All Adapters

### Phase 1: Current State (Auto-Inference)

Most adapters use auto-inference:
```yaml
- name: "intent-mongodb-mflix"
  type: "retriever"
  adapter: "intent"
  # No capabilities - automatically inferred
```

✅ **Works perfectly, no changes needed**

### Phase 2: Add to Production Adapters (Recommended)

Add explicit capabilities to enabled/production adapters:

```yaml
- name: "intent-mongodb-mflix"
  type: "retriever"
  adapter: "intent"

  # NEW: Explicit capabilities for clarity
  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: false
```

✅ **Better documentation, easier to modify**

### Phase 3: Customize Behavior (When Needed)

Modify behavior without code changes:

```yaml
capabilities:
  formatting_style: "clean"  # Changed from "standard"!
  # No code changes needed
```

✅ **Configuration-driven behavior**

## Adding Capabilities to Your Adapters

### Step 1: Identify Adapter Type

Look at your adapter's `type` and `adapter` fields:
```yaml
- name: "your-adapter"
  type: "retriever"  # or "passthrough"
  adapter: "qa"       # or "intent", "file", etc.
```

### Step 2: Choose Capability Template

Based on adapter type, use appropriate template:

| Adapter Type | Template | `supports_threading` |
|--------------|----------|---------------------|
| Passthrough (no retrieval) | `retrieval_behavior: "none"` | `false` |
| Passthrough (multimodal) | `retrieval_behavior: "conditional"` | `false` |
| QA (any datasource) | `retrieval_behavior: "always"`, `formatting_style: "standard"` | `false` |
| Intent (any datasource) | `retrieval_behavior: "always"`, `formatting_style: "standard"` | `true` |
| File | `retrieval_behavior: "always"`, `formatting_style: "clean"` | `false` |

### Step 3: Add Capabilities Section

**For QA adapters:**
```yaml
- name: "your-qa-adapter"
  type: "retriever"
  adapter: "qa"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: false          # QA: simple Q&A
    requires_api_key_validation: false
```

**For Intent adapters:**
```yaml
- name: "your-intent-adapter"
  type: "retriever"
  adapter: "intent"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: true           # Intent: enable follow-up
    requires_api_key_validation: false
```

### Step 4: Customize as Needed

Modify any capability to change behavior:

```yaml
capabilities:
  formatting_style: "clean"  # Remove citations
  supports_file_ids: true     # Enable file filtering
  optional_parameters:         # Add custom parameters
    - "custom_param"
```

## Real-World Examples

### Example 1: Convert qa-vector-chroma

**Before (auto-inferred):**
```yaml
- name: "qa-vector-chroma"
  enabled: false
  type: "retriever"
  datasource: "chroma"
  adapter: "qa"
```

**After (explicit):**
```yaml
- name: "qa-vector-chroma"
  enabled: false
  type: "retriever"
  datasource: "chroma"
  adapter: "qa"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: false          # QA: simple Q&A, no threading
    requires_api_key_validation: false
```

### Example 2: Convert intent-mongodb-mflix

**Before (auto-inferred):**
```yaml
- name: "intent-mongodb-mflix"
  enabled: true
  type: "retriever"
  datasource: "mongodb"
  adapter: "intent"
```

**After (explicit):**
```yaml
- name: "intent-mongodb-mflix"
  enabled: true
  type: "retriever"
  datasource: "mongodb"
  adapter: "intent"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    supports_file_ids: false
    supports_session_tracking: false
    supports_threading: true           # Intent: enable follow-up questions
    requires_api_key_validation: false
```

### Example 3: Customize intent-firecrawl for clean formatting

Want to prevent citation markers in web scraping results?

```yaml
- name: "intent-firecrawl-webscrape"
  enabled: true
  type: "retriever"
  adapter: "intent"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "clean"  # CHANGED: No citations for scraped content
    supports_file_ids: false
```

**Result:** Web content displayed cleanly without `[1]` citation markers

## Benefits for All Adapter Types

### 1. Consistency Across Adapters

All adapters use the same capability system:
- Same configuration format
- Same behavior controls
- Easy to understand across different types

### 2. Easy Behavior Modification

Change any adapter's behavior via config:
```yaml
# Want clean formatting? Just change one line
capabilities:
  formatting_style: "clean"
```

No code changes needed for:
- QA adapters
- Intent adapters
- File adapters
- Any adapter type

### 3. Future-Proof

Add new capabilities without code changes:
```yaml
capabilities:
  # Existing
  retrieval_behavior: "always"

  # New capability (hypothetical)
  enable_caching: true
  cache_ttl_minutes: 60
```

Pipeline code automatically uses new capabilities!

## Summary

### ✅ Universal System

| Question | Answer |
|----------|--------|
| Do capabilities apply to passthrough adapters? | ✅ Yes |
| Do capabilities apply to file adapters? | ✅ Yes |
| Do capabilities apply to QA adapters? | ✅ Yes |
| Do capabilities apply to Intent adapters? | ✅ Yes |
| Do capabilities apply to custom adapters? | ✅ Yes |
| Are capabilities optional? | ✅ Yes (auto-inferred if not specified) |
| Are capabilities recommended? | ✅ Yes (for production adapters) |

### Threading Quick Reference

| Adapter Type | `supports_threading` | Reason |
|--------------|---------------------|--------|
| QA (all types) | `false` | Simple Q&A - each query independent |
| Intent (all types) | `true` | Complex datasets - users need follow-up |
| Passthrough | `false` | No retrieval or simple chat |
| File | `false` | Document Q&A - each query independent |
| Multimodal | `false` | File-based retrieval - each query independent |

### Key Takeaways

1. **Universal** - Works with ALL adapter types
2. **Optional** - Auto-inference provides backward compatibility
3. **Recommended** - Explicit is better for production
4. **Flexible** - Customize any adapter's behavior via config
5. **Future-proof** - Add new capabilities without code changes
6. **Threading** - Use `supports_threading: true` for Intent adapters, `false` for QA/passthrough

**You can (and should) add capabilities to ANY adapter, not just passthrough/file adapters!**

## Next Steps

### Recommended: Add Capabilities to All Enabled Adapters

For better documentation and easier maintenance, add explicit capabilities to all your enabled adapters:

```bash
# Check which adapters are enabled
grep -B2 "enabled: true" config/adapters.yaml

# Add capabilities to each enabled adapter
```

### Optional: Leave Disabled Adapters with Auto-Inference

Disabled/example adapters can continue using auto-inference.
