# Tutorial: Chat with Your Data

ORBIT is highly configurable — 37+ inference providers, 20+ datasources, dozens of adapter examples, a skills system, MCP tool calling. That configurability is exactly what makes it powerful, and exactly what can make it feel overwhelming on day one. You don't need to understand all of it to get your first adapter running, and you don't need to hold all of it in your head at once to get good at ORBIT — you need to learn it in the right order. That's what the Learning Path below is for.

<!-- MEDIA: video | tutorial/overview | 60s overview: what is ORBIT, tour of the learning path -->
> 🎬 **Video placeholder:** 60-second overview of ORBIT and this learning path.
> _(To be added — see [`tutorial/_media-todo.md`](tutorial/_media-todo.md))_

## Learning Path

Work through these in order the first time. Each level assumes the ones before it.

| Level | Name | Time | You'll be able to | Start here |
| :---: | :--- | :--- | :--- | :--- |
| **L0** | Orientation | ~10 min | Install ORBIT, take the server for a health check, tour the admin panel, and send your first chat message. | [Before you start](tutorial/before-you-start.md) |
| **L1** | Foundations | ~20 min | Understand the adapter shape that every example builds on, and run your first SQL, file, or vector-store adapter. | [Connecting Your Own Data](tutorial/connecting-your-own-data.md) |
| **L2** | Core AI Services | ~15 min | Trace any adapter to the inference provider, datasource, and embedding model underneath it — and know which of the three you actually need for a given adapter. | [Core AI Services & Data Sources](tutorial/core-services/overview.md) |
| **L3** | Intermediate adapters & composition | ~30 min | Wire up DuckDB, MongoDB, and HTTP-as-datasource adapters, and route one chat across all of them with Composite. | [Example 4: DuckDB Analytics](tutorial/duckdb-analytics.md) |
| **L4** | Skills, MCP tools & generation | ~30 min | Tell adapters, skills, capability flags, and MCP tools apart, and get the model calling tools, generating images/documents, and searching the web. | [Skills, MCP Tools, and Skill Routing](tutorial/skills-concepts.md) |
| **L5** | Advanced / production | as needed | Run async message-queue requests, real-time voice, and everything else you need before a production deployment. | [Example 12: Message Queue (Async) Requests](tutorial/message-queue-async.md) |

If Level 0 works end-to-end, the gateway path is healthy and you're ready for the rest.

## Already know what you want? Jump straight there

Answer these in order — each one narrows it down:

1. **Are you starting from a database, or from files/documents?**
   - Database → go to 2.
   - Files/documents → go to 3.
   - Neither — I want the model to call tools/APIs, generate content, or answer from multiple sources at once → go to 4.

2. **What kind of database?**
   - SQL (Postgres, MySQL, SQLite, SQL Server, Oracle...) → [SQL Database (SQLite)](tutorial/sql-database-sqlite.md)
   - MongoDB → [MongoDB Queries](tutorial/mongodb-queries.md)
   - A local analytics file (DuckDB, Parquet, CSV-as-warehouse) → [DuckDB Analytics](tutorial/duckdb-analytics.md)
   - Already have data embedded in a vector store (Chroma, Qdrant, ...) → [Vector Store Q&A](tutorial/vector-store-qa.md)

3. **How will users get files into the conversation?**
   - Users upload files during chat (PDFs, docs, images, audio) → [Chat with Files](tutorial/chat-with-files.md)
   - You pre-index a fixed set of documents ahead of time → [Vector Store Q&A](tutorial/vector-store-qa.md)

4. **What's the goal?**
   - Wrap a REST or GraphQL API as a data source → [HTTP APIs](tutorial/http-apis.md)
   - Let the model call tools/functions via a templated pattern (calculator, date/time, your own APIs) → [Agent with Function Calling](tutorial/agent-function-calling.md)
   - Let the model call your tools opportunistically, on any conversational turn, no template → [Opportunistic MCP Tool Calling](tutorial/mcp-tool-calling.md)
   - Combine more than one of the above into a single chat → [Multi-Source Composite](tutorial/multi-source-composite.md)
   - Join genuinely related data that lives in different systems, not just route between unrelated ones → [Customer 360 — Cross-Adapter Composition](tutorial/customer-360-cross-adapter.md)
   - Generate images (or other media) from chat → start with [Skills, MCP Tools, and Skill Routing](tutorial/skills-concepts.md), then [Skills and Image Generation](tutorial/skills-image-generation.md)
   - Answer with live web results, or auto-route plain language to a skill → [Web Search and Automatic Skill Routing](tutorial/auto-skill-routing.md)
   - Process requests asynchronously off a message queue instead of synchronous HTTP → [Message Queue (Async) Requests](tutorial/message-queue-async.md)

Still not sure, or want to scan everything at once? Use the full table below.

## Choose Your Use Case

| Level | Goal | Start here | Requirements | Success looks like |
| :---: | :--- | :--- | :--- | :--- |
| L1 | Chat with uploaded PDFs, docs, images, or audio | [Chat with Files](tutorial/chat-with-files.md) | File-capable adapter | Upload a file and ask questions about its contents. |
| L1 | Ask SQL database questions in English | [SQL Database (SQLite)](tutorial/sql-database-sqlite.md) | Sample SQLite data | Ask HR questions and get query-backed answers. |
| L1 | Query an existing vector store | [Vector Store Q&A](tutorial/vector-store-qa.md) | Chroma sample setup or Qdrant | Retrieve semantically relevant context and answer from it. |
| L3 | Analyze local analytics data | [DuckDB Analytics](tutorial/duckdb-analytics.md) | DuckDB sample data | Ask analytics questions without writing SQL. |
| L3 | Query MongoDB collections | [MongoDB Queries](tutorial/mongodb-queries.md) | MongoDB sample data | Ask natural-language movie database questions. |
| L3 | Wrap REST or GraphQL APIs | [HTTP APIs](tutorial/http-apis.md) | API adapter config | Ask questions that ORBIT resolves through HTTP calls. |
| L3 | Route across multiple data sources | [Multi-Source Composite](tutorial/multi-source-composite.md) | Multiple configured child adapters | Ask one question and let ORBIT choose the right source. |
| L5 | Merge results from related data across systems | [Customer 360 — Cross-Adapter Composition](tutorial/customer-360-cross-adapter.md) | Billing SQLite + SLA mock API adapters | Ask one question and get merged results from multiple sources at once. |
| L3 | Let the model call tools (templated) | [Agent with Function Calling](tutorial/agent-function-calling.md) | Agent template config | Run calculator, date/time, JSON, or HTTP-backed tool examples. |
| L4 | Generate images from chat | [Skills and Image Generation](tutorial/skills-image-generation.md) | Image skill adapter | Invoke the `Image` skill from OrbitChat or curl. |
| L4 | Let the model call tools opportunistically, any turn | [Opportunistic MCP Tool Calling](tutorial/mcp-tool-calling.md) | MCP server + `mcp_tools` capability | Ask a business question with no `skill` field and get a tool-backed answer. |
| L4 | Answer with live web results, or auto-route from plain language | [Web Search and Automatic Skill Routing](tutorial/auto-skill-routing.md) | Web-search-capable provider (Gemini/OpenAI/xAI) | Get a cited, current answer, with or without an explicit `skill` field. |
| L5 | Process requests asynchronously over a message queue | [Message Queue (Async) Requests](tutorial/message-queue-async.md) | RabbitMQ (Docker) + `messaging` profile | Publish a request to a queue and receive a correlated response envelope back. |
| L5 | Monitor an intent adapter in production — matches, misses, row-cap metrics | [Intent Adapter Observability](tutorial/intent-observability.md) | A running intent adapter (SQL, HTTP, Composite...) | Check Prometheus `orbit_intent_*` metrics and the admin panel's Misses panel after driving traffic. |

## Reference & Deep Dives

| Need | Page |
| :--- | :--- |
| Take a visual tour of the admin panel | [Admin Panel Tour](tutorial/admin-panel-tour.md) |
| Create personas and API keys | [Creating API Keys](tutorial/creating-api-keys.md) |
| Connect your own database, files, API, or vector store | [Connecting Your Own Data](tutorial/connecting-your-own-data.md) |
| Understand adapter fields and capabilities | [Adapter Types Overview](tutorial/adapter-types.md) · [Adapter Configuration Reference](tutorial/adapter-configuration-reference.md) |
| Understand inference providers, datasources, and embeddings | [Core AI Services & Data Sources](tutorial/core-services/overview.md) |
| Understand adapters, skills, capability flags, and MCP tools | [Skills, MCP Tools, and Skill Routing](tutorial/skills-concepts.md) |
| Test an intent template on demand, or check production metrics/misses | [Template Diagnostics](template-diagnostics.md) |
| Fix common setup issues | [Troubleshooting](tutorial/troubleshooting.md) |
| Decide what to read next | [Next Steps](tutorial/next-steps.md) |
