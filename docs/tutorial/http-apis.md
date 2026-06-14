# Example 6: HTTP APIs

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

[Tutorial home](../tutorial.md) | [Previous: Example 5: MongoDB Queries](mongodb-queries.md) | [Next: Example 7: Multi-Source Composite](multi-source-composite.md)

---
