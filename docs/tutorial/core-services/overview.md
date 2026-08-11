# Core AI Services & Data Sources

**Level 2 · Core AI Services**

You've done one adapter tutorial (SQL, files, or vector QA) and it worked — you set one API key, ran one adapter, and got an answer. This section explains what was actually happening underneath, because your *second* adapter is where ORBIT's configurability starts to show: you'll want a different provider, a different datasource, maybe a different embedding model, and none of the tutorial pages so far have explained where those choices live or how they connect.

There's a reason this hasn't been written down before now: `config/inference.yaml`, `config/datasources.yaml`, and `config/embeddings.yaml` are ORBIT's three most foundational config surfaces, yet each is documented only as inline YAML comments inside the file itself — a great reference once you know what you're looking for, but nothing that explains the shape of the whole thing to a newcomer. This page (and the three that follow) is that missing explanation.

## The mental model

Every adapter you configure in `config/adapters/*.yaml` answers one question: **what should this endpoint do?** (chat only, search a database, retrieve files, call tools...). But an adapter doesn't work in isolation — it delegates to three other things, each with its own config file:

| Config file | Answers | Used by |
|---|---|---|
| [`config/inference.yaml`](../../../config/inference.yaml) | **Who answers?** Which LLM provider/model generates the response | Every adapter — even a pure-retrieval adapter still needs an LLM to phrase the final answer |
| [`config/datasources.yaml`](../../../config/datasources.yaml) | **Where does the data live?** Connection details for the database, vector store, or API behind a retriever adapter | Retriever adapters (QA, intent, file) — not needed by pure passthrough chat |
| [`config/embeddings.yaml`](../../../config/embeddings.yaml) | **How do we turn text into vectors?** The embedding model used to index and search unstructured content | Vector-store and file-based retrieval only — SQL/NoSQL intent adapters skip this entirely |

An adapter's YAML (`config/adapters/*.yaml`) references these by name — e.g. `inference_provider: "openai"` points at the `openai:` block in `inference.yaml`; `datasource: "sqlite"` points at the `sqlite:` block in `datasources.yaml`. Nothing here is auto-discovered magic — it's plain key lookups across three files, and once you can trace one adapter through all three, you can trace any of them.

## Do you need all three, every time?

No — this is the part that makes ORBIT feel more configurable than it actually is per-adapter. Which of the three matter depends on what the adapter does:

- **Pure conversational passthrough** (`config/adapters/passthrough.yaml`) — only needs `inference.yaml`. No datasource, no embeddings.
- **SQL/NoSQL intent adapters** (`config/adapters/intent.yaml` and friends) — need `inference.yaml` (to generate the query and phrase the answer) and `datasources.yaml` (the database connection). No embeddings — these adapters match natural language to query templates, not vector similarity.
- **Vector-store QA and file adapters** (`config/adapters/qa.yaml`, `file.yaml`) — need all three: `inference.yaml` for the answer, `datasources.yaml` for the vector store connection, `embeddings.yaml` to turn the query (and the indexed documents) into vectors.

You never need to configure all 37+ inference providers or all 20+ datasources to run one adapter — you configure the one row in each file that your adapter actually references, and leave the rest at their (disabled-by-default, in most cases) example values.

## What's next

Read the three companion pages in whatever order matches what you're setting up next:

- [Inference Providers](inference-providers.md) — picking and configuring the LLM that answers
- [Datasources](datasources.md) — connecting the database, vector store, or API behind a retriever
- [Embeddings](embeddings.md) — when you need vector embeddings and how to configure them

Then continue to [Level 3: Intermediate adapters & composition](../multi-source-composite.md), or jump to whichever Level 1 example you haven't tried yet.

---

[Tutorial home](../../tutorial.md)
