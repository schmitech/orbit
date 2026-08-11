# Example 7: Multi-Source Composite

**Level 3 · Intermediate adapters & composition**

Point *one* chat interface at several data sources and let ORBIT figure out which one should answer each question. The Composite Intent Retriever searches every child adapter's template library and routes to the best match.

## The Intent family, in one place

By this point you've seen the Intent adapter pattern applied to SQL ([SQL Database](sql-database-sqlite.md), [DuckDB](duckdb-analytics.md)), NoSQL ([MongoDB](mongodb-queries.md)), and HTTP ([HTTP APIs](http-apis.md)). ORBIT ships several more ready-to-enable domain examples of the same pattern — all natural language → matched template → parameterized query, just against different backends:

| Adapter config | Domain | Datasource |
|---|---|---|
| `config/adapters/intent.yaml` | Generic intent examples (SQLite HR, HTTP, Firecrawl, GraphQL) | Various |
| `config/adapters/customer-orders.yaml` | Customer order lookups | `postgres` |
| `config/adapters/hr.yaml` | HR/employee data | `sqlite` |
| `config/adapters/ev.yaml` | EV population/registration data | `duckdb` |
| `config/adapters/contact.yaml` | Contact/CRM records | `sqlite` |
| `config/adapters/business-analytics.yaml` | Business/revenue analytics | `duckdb` |
| `config/adapters/mongodb-mflix.yaml` | Movie database (`sample_mflix`) | `mongodb` |
| `config/adapters/elasticsearch-logs.yaml` | Application log search | `elasticsearch` |

Each is a self-contained, disabled-by-default example — enable the ones matching data you actually have, and Composite (below) is what lets you query across several of them from one chat.

## How composite routing works

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

`child_adapters` is a plain list of adapter names — any of the intent-family adapters from the table above (or your own) can be listed, as long as they're `enabled: true`.

### Create an API key

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** with the prompt:

`You are a data assistant that can query multiple databases. Answer questions using the retrieved data.`

Then go to **API Keys** → **+ Create**:

1. Choose `composite-multi-source` as the adapter.
2. Name the key `Multi-Source Explorer`.
3. Select the persona you just created.
4. Save the key and copy the `orbit_…` value shown once.

<!-- MEDIA: screenshot | multi-source-composite/adapter-config | Adapters tab showing composite-multi-source's child_adapters list -->
> 🖼️ **Screenshot placeholder:** the `composite-multi-source` adapter config.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

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

<!-- MEDIA: screenshot | multi-source-composite/routing-response | API response JSON showing composite_routing metadata for a multi-source answer -->
> 🖼️ **Screenshot placeholder:** the `composite_routing` metadata in a real response.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

See [Composite Intent Retriever](../adapters/composite-intent-retriever.md) for tuning reranking, string-similarity weighting, and cross-adapter templates. For the underlying intent-matching mechanics shared by every adapter in the table above, see [Intent Agent Retriever](../adapters/intent-agent-retriever.md).

---

[Tutorial home](../tutorial.md) | [Previous: Example 6: HTTP APIs](http-apis.md) | [Next: Example 8: Agent with Function Calling](agent-function-calling.md)

---
