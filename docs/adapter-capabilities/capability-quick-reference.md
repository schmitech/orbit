# Capability Quick Reference Guide

## TL;DR

**Yes, capabilities apply to ALL adapter types!** Use this guide as a quick reference.

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
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** qa-sql, qa-postgres, qa-mysql, qa-oracle, any SQL QA

---

### QA - Vector Store (Chroma, Qdrant, Pinecone, etc.)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
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
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

**Adapters:** intent-sql-postgres, intent-sql-sqlite, intent-duckdb-*, any SQL intent

---

### Intent - NoSQL (MongoDB, Elasticsearch)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
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

---

## Quick Copy-Paste

### Most Common: Standard Retriever (QA/Intent)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
```

### Second Most Common: Clean Formatting (File/Multimodal)

```yaml
capabilities:
  retrieval_behavior: "always"
  formatting_style: "clean"
  supports_file_ids: true
  requires_api_key_validation: true
```

### Least Common: No Retrieval (Pure Chat)

```yaml
capabilities:
  retrieval_behavior: "none"
  formatting_style: "standard"
  supports_file_ids: false
```

---

**Remember: Capabilities are universal - they work with EVERY adapter type!** 🎯
