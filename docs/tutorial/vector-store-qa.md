# Example 3: Vector Store Q&A

If your documents are already embedded in a vector store, the QA adapter handles semantic search + answer generation.

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

```bash
./bin/orbit.sh key create \
  --adapter qa-vector-chroma \
  --name "City Assistant" \
  --prompt-file ./examples/prompts/examples/city/city-assistant-normal-prompt.txt
```

**Tip:** If answers come back "I don't have information about that," lower `confidence_threshold` incrementally (try 0.2, then 0.15). Thresholds behave consistently across Chroma, Qdrant, FAISS, and Milvus as of 2.6.4.

---

[Tutorial home](../tutorial.md) | [Previous: Example 2: Chat with Files](chat-with-files.md) | [Next: Example 4: DuckDB Analytics](duckdb-analytics.md)

---
