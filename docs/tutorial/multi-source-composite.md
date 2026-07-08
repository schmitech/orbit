# Example 7: Multi-Source Composite

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

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** with the prompt:

`You are a data assistant that can query multiple databases. Answer questions using the retrieved data.`

Then go to **API Keys** → **+ Create**:

1. Choose `composite-multi-source` as the adapter.
2. Name the key `Multi-Source Explorer`.
3. Select the persona you just created.
4. Save the key and copy the `orbit_…` value shown once.

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

See [Composite Intent Retriever](../adapters/composite-intent-retriever.md) for tuning reranking, string-similarity weighting, and cross-adapter templates.

---

[Tutorial home](../tutorial.md) | [Previous: Example 6: HTTP APIs](http-apis.md) | [Next: Example 8: Agent with Function Calling](agent-function-calling.md)

---
