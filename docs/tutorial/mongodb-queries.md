# Example 5: MongoDB Queries

**Level 3 · Intermediate adapters & composition**

Same Intent adapter pattern as the SQL examples, but against a NoSQL datasource — `datasource: "mongodb"` — natural language → MongoDB find/aggregate queries.

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

<!-- MEDIA: screenshot | mongodb-queries/movie-result | Chat showing a Christopher Nolan movie query answered from MongoDB -->
> 🖼️ **Screenshot placeholder:** a movie question answered by `intent-mongodb-mflix`.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

---

[Tutorial home](../tutorial.md) | [Previous: Example 4: DuckDB Analytics](duckdb-analytics.md) | [Next: Example 6: HTTP APIs](http-apis.md)

---
