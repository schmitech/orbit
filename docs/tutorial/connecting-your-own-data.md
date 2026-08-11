# Connecting Your Own Data

**Level 1 · Foundations**

Every adapter, no matter how it ends up looking, starts from the same shape. Before connecting your own database, files, or API, look at the simplest adapter ORBIT ships — it has no retrieval, no datasource, nothing to configure beyond an inference provider — because that shape is the skeleton every other adapter builds on.

## Adapter zero: `simple-chat`

[`config/adapters/passthrough.yaml`](../../config/adapters/passthrough.yaml) defines `simple-chat`:

```yaml
- name: "simple-chat"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"
  implementation: "implementations.passthrough.conversational.ConversationalImplementation"
  inference_provider: "ollama_cloud"
  model: "gpt-oss:120b"
```

Every field here reappears, unchanged in meaning, on every other adapter in this repo:

- **`name`** — how you reference this adapter when creating an API key.
- **`enabled`** — whether ORBIT loads it at startup (toggle live from the Adapters tab — see [Admin Panel Tour](admin-panel-tour.md)).
- **`type`** — `"passthrough"` (no retrieval, straight to the LLM) or `"retriever"` (fetches context first). This is the main fork in the road.
- **`datasource`** — `"none"` here because passthrough has nothing to connect to. Every retriever adapter you build next will set this to a real entry in `config/datasources.yaml` — see [Core AI Services: Datasources](core-services/datasources.md).
- **`adapter`** — which domain adapter formats the result. `"conversational"` here means "just pass the model's answer straight through."
- **`inference_provider` / `model`** — which LLM answers, from `config/inference.yaml` — see [Core AI Services: Inference Providers](core-services/inference-providers.md).

That's the whole pattern. Everything below is a variation: add a `datasource`, swap the `adapter` value, and point `implementation` at a retriever class that knows how to query that datasource.

## Now connect your own data

Pick the branch that matches what you have. Each one is the next `type: "retriever"` step up from `simple-chat` above.

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

Full walkthrough: [SQL Database (SQLite)](sql-database-sqlite.md).

### Vector stores

1. Index documents into Chroma, Qdrant, or Pinecone.
2. Configure a QA adapter (`config/adapters/qa.yaml`) with your collection name and `datasource:` pointing at the matching entry in `config/datasources.yaml`.
3. Create an API key against it.

Full walkthrough: [Vector Store Q&A](vector-store-qa.md).

### Files (no config needed)

The `simple-chat-with-files` adapter (`config/adapters/multimodal.yaml`) is already enabled — the same passthrough shape as `simple-chat`, but with `retrieval_behavior: "conditional"` so it only retrieves when a file is attached. Create a key, upload files through the chat interface, and you're done.

Full walkthrough: [Chat with Files](chat-with-files.md).

---

Next: once you've got one retriever adapter working, [Core AI Services & Data Sources](core-services/overview.md) explains what's underneath it — which inference provider answered, where the datasource connection lives, and when embeddings come into play.

[Tutorial home](../tutorial.md) | [Previous: Creating API Keys](creating-api-keys.md) | [Next: Adapter Types Overview](adapter-types.md)

---
