# Adapter Types Overview

**Level 1 · Foundations**

ORBIT picks the right retrieval strategy based on an *adapter type*. You don't choose these at query time — you configure them once in `config/adapters/*.yaml` and reference them by name when creating an API key.

This table is ordered from simplest to most complex, matching the order you'll likely learn them in. Each row names the exact `config/adapters/*.yaml` file that defines the example. For the underlying architecture (retriever base classes, the adapter registry, and how to add a new adapter type), see [Adapters Overview](../adapters/adapters.md).

| # | Adapter Type | Use it when… | Config file | Examples |
|:---:|:---|:---|:---|:---|
| 1 | **Passthrough** | You want plain chat without retrieval | `passthrough.yaml` | `simple-chat` |
| 2 | **QA (SQL / vector)** | You have documents already embedded in a vector store, or a database you'll query with simple similarity/keyword matching | `qa.yaml` | `qa-sql`, `qa-vector-chroma`, `qa-vector-qdrant` |
| 3 | **File** | Users upload documents and you retrieve from them directly | `file.yaml` | `file-document-qa` |
| 4 | **Multimodal** | Users will upload files (PDF, images, audio), but you also want plain chat when they don't | `multimodal.yaml` | `simple-chat-with-files` |
| 5 | **Intent (SQL / NoSQL / HTTP)** | You have a SQL/NoSQL database or a REST API and want natural language → generated query, with follow-up threading on the result | `intent.yaml`, `customer-orders.yaml`, `hr.yaml`, `ev.yaml`, `contact.yaml`, `business-analytics.yaml`, `mongodb-mflix.yaml`, `elasticsearch-logs.yaml` | `intent-sql-postgres`, `intent-duckdb-analytics`, `intent-mongodb-mflix` |
| 6 | **Fetch (HTTP-as-datasource)** | You want to wrap an arbitrary REST endpoint as a queryable source | `fetch.yaml` | `fetch-jsonplaceholder` |
| 7 | **Composite** | You want one chat that routes across several of the adapters above | `composite.yaml` | `composite-multi-source` |
| 8 | **Web Search** | You want live, cited web results — either via a provider's built-in search or an external search API | `web-search.yaml`, `web-search-providers.yaml` | `web-search`, `web-search-duckduckgo` |
| 9 | **MCP Agent (Skill)** | You want the model to call your own MCP tools opportunistically, on any turn | `mcp-agent.yaml` | `mcp-agent` |
| 10 | **Audio / Voice** | You want voice input/output — request/response STT+TTS, or real-time speech-to-speech | `audio.yaml` | `voice-chat`, `open-ai-real-time-voice-chat` |
| 11 | **Generator (Skill)** | You want the model to generate images, documents, or other media as a callable skill | `image-generator.yaml`, `video-generator.yaml`, `audio-generator.yaml`, `csv-generator.yaml`, `excel-generator.yaml`, `markdown-generator.yaml`, `pdf-generator.yaml`, `pptx-generator.yaml`, `word-generator.yaml` | `Image`, `Video`, `PDF` |

**Skill** isn't a separate row above because it's a role, not a retrieval strategy: any adapter (most commonly a generator or MCP agent, rows 9 and 11) can be marked invocable by other adapters via `available_skills`. See [Skills, MCP Tools, and Skill Routing](skills-concepts.md) for how that fits together.

---

[Tutorial home](../tutorial.md) | [Previous: Your first chat (2 minutes)](first-chat.md) | [Next: Example 1: SQL Database (SQLite)](sql-database-sqlite.md)

---
