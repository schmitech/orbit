# Connecting Your Own Data

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

[Tutorial home](../tutorial.md) | [Previous: Creating API Keys](creating-api-keys.md) | [Next: Adapter Configuration Reference](adapter-configuration-reference.md)

---
