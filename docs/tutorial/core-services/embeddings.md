# Embeddings

**Level 2 · Core AI Services**

[`config/embeddings.yaml`](../../../config/embeddings.yaml) configures how ORBIT turns text into vectors — the numeric representations that make "search by meaning" possible. This is the smallest of the three core config files and, unlike inference and datasources, it's genuinely optional depending on which adapter you're running.

## Do you need this at all?

Only if your adapter does **similarity search** over unstructured content:

- **Needs embeddings**: vector-store QA (`config/adapters/qa.yaml`'s Chroma/Qdrant variants), file adapters (`config/adapters/file.yaml`, `multimodal.yaml`) — anything that indexes documents and finds the most relevant chunks for a query.
- **Doesn't need embeddings**: SQL/NoSQL intent adapters (they match natural language to query *templates*, not vector similarity), passthrough/conversational adapters, HTTP/API intent adapters.

If you've only run a SQL intent tutorial so far, you can skip this page until you try a file-upload or vector-store QA example.

## The two-part structure

```yaml
# config/embeddings.yaml
embedding:
  provider: "openai"   # <- the DEFAULT provider used when an adapter doesn't override it
  enabled: true

embeddings:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "text-embedding-3-small"
    dimensions: 1536
    batch_size: 10
  ollama:
    base_url: "http://localhost:11434"
    model: "nomic-embed-text"
    dimensions: 768
  # ... 8 more providers, same shape
```

The top-level `embedding.provider` is the default; individual adapters can override it with their own `embedding_provider:` field (see `config/adapters/multimodal.yaml`, which sets `embedding_provider: "openai"` explicitly). Same pattern as inference and datasources: one lookup key, one matching block.

## Picking a provider

| You have | Use |
|---|---|
| Already using OpenAI for inference | `openai` (`text-embedding-3-small`) — keeps you on one provider/API key for both LLM and embeddings |
| Running Ollama locally | `ollama` (`nomic-embed-text`) — free, local, no API key |
| Need code-optimized or very long-context embeddings | `voyage` (`voyage-code-3`) or `cohere` |
| Want to run entirely offline with no server dependency | `sentence_transformers` in `mode: "local"` — loads a model in-process (`BAAI/bge-m3` by default) |

## Why `dimensions` matters

Each provider's `dimensions` value (768, 1024, 1536, 3072, depending on the model) must match what your vector store was built with — `config/datasources.yaml`'s `milvus.dim` is a clear example of this dependency being explicit. If you switch embedding providers on an already-populated vector store, you'll need to re-index; embeddings from different models or dimensions aren't compatible with each other.

---

You've now seen how an adapter's three underlying references — `inference_provider`, `datasource`, and (where relevant) `embedding_provider` — each resolve to one block in one of these three files. That's the whole model: no hidden auto-configuration, just name lookups you can trace by hand.

Continue to [Level 3: Intermediate adapters & composition](../multi-source-composite.md), or go back to the [Core AI Services overview](overview.md).

[Tutorial home](../../tutorial.md)
