# Example 4: DuckDB Analytics

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

[Tutorial home](../tutorial.md) | [Previous: Example 3: Vector Store Q&A](vector-store-qa.md) | [Next: Example 5: MongoDB Queries](mongodb-queries.md)

---
