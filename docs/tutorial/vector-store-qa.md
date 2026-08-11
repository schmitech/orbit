# Example 3: Vector Store Q&A

**Level 1 · Foundations**

This is the QA adapter type from [Adapter Types](adapter-types.md). If your documents are already embedded in a vector store, the QA adapter handles semantic search + answer generation — see [Core AI Services: Embeddings](core-services/embeddings.md) for how the embedding model that indexed these documents connects to the adapter below.

### Option A: Chroma (runs locally, no extra services)

```bash
./examples/sample-db-setup.sh chroma
```

Configured in `config/adapters/qa.yaml`:

```yaml
- name: "qa-vector-chroma"
  enabled: true
  type: "retriever"
  datasource: "chroma"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAChromaRetriever"

  config:
    collection: "city"
    confidence_threshold: 0.3
    distance_scaling_factor: 2.0
    max_results: 5
    return_results: 3
```

### Option B: Qdrant (Cloud or self-hosted)

```yaml
- name: "qa-vector-qdrant"
  enabled: true
  type: "retriever"
  datasource: "qdrant"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAQdrantRetriever"
  embedding_provider: "openai"

  config:
    collection: "my_collection"
    confidence_threshold: 0.3
    score_scaling_factor: 1.0
    max_results: 5
    return_results: 3
```

### Create an API key

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** using the text from `./examples/prompts/examples/city/city-assistant-normal-prompt.txt`.

Then go to **API Keys** → **+ Create**:

1. Choose `qa-vector-chroma` as the adapter.
2. Name the key `City Assistant`.
3. Select the city persona you just created.
4. Save the key and copy the `orbit_…` value shown once.

**Tip:** If answers come back "I don't have information about that," lower `confidence_threshold` incrementally (try 0.2, then 0.15). Thresholds behave consistently across Chroma, Qdrant, FAISS, and Milvus as of 2.6.4.

<!-- MEDIA: screenshot | vector-store-qa/city-assistant-answer | Chat showing a question answered with retrieved city data and confidence score -->
> 🖼️ **Screenshot placeholder:** the City Assistant answering from retrieved vector-store context.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

You've now tried all three Level 1 foundations (SQL, files, vector QA). Before moving to more advanced patterns, [Core AI Services & Data Sources](core-services/overview.md) explains what's underneath every adapter you've configured so far — worth reading now that you've seen it in practice more than once.

---

[Tutorial home](../tutorial.md) | [Previous: Example 2: Chat with Files](chat-with-files.md) | [Next: Core AI Services & Data Sources](core-services/overview.md) · [Example 4: DuckDB Analytics](duckdb-analytics.md)

---
