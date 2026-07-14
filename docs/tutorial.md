# Tutorial: Chat with Your Data

Use this tutorial as a set of short paths, not a book you have to read front to back. Start by proving the server, admin panel, API key, and chat client work together, then jump to the adapter that matches your data.

## Fastest Path

| Step | Time | Outcome |
| :--- | :--- | :--- |
| [Before you start](tutorial/before-you-start.md) | 5 min | ORBIT is installed, configured with an inference provider, and running locally. |
| [Your first chat](tutorial/first-chat.md) | 2 min | You create a persona and API key in the admin panel, then send a message through OrbitChat. |

If first chat works, the gateway path is healthy. Now pick the path that matches what you're actually connecting.

## Which Tutorial Do I Need?

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
   - Generate images (or other media) from chat → [Skills and Image Generation](tutorial/skills-image-generation.md)
   - Answer with live web results, or auto-route plain language to a skill → [Web Search and Automatic Skill Routing](tutorial/auto-skill-routing.md)
   - Process requests asynchronously off a message queue instead of synchronous HTTP → [Message Queue (Async) Requests](tutorial/message-queue-async.md)

Still not sure, or want to scan everything at once? Use the full table below.

## Choose Your Use Case

| Goal | Start here | Requirements | Success looks like |
| :--- | :--- | :--- | :--- |
| Chat with uploaded PDFs, docs, images, or audio | [Chat with Files](tutorial/chat-with-files.md) | File-capable adapter | Upload a file and ask questions about its contents. |
| Ask SQL database questions in English | [SQL Database (SQLite)](tutorial/sql-database-sqlite.md) | Sample SQLite data | Ask HR questions and get query-backed answers. |
| Query an existing vector store | [Vector Store Q&A](tutorial/vector-store-qa.md) | Chroma sample setup or Qdrant | Retrieve semantically relevant context and answer from it. |
| Analyze local analytics data | [DuckDB Analytics](tutorial/duckdb-analytics.md) | DuckDB sample data | Ask analytics questions without writing SQL. |
| Query MongoDB collections | [MongoDB Queries](tutorial/mongodb-queries.md) | MongoDB sample data | Ask natural-language movie database questions. |
| Wrap REST or GraphQL APIs | [HTTP APIs](tutorial/http-apis.md) | API adapter config | Ask questions that ORBIT resolves through HTTP calls. |
| Route across multiple data sources | [Multi-Source Composite](tutorial/multi-source-composite.md) | Multiple configured child adapters | Ask one question and let ORBIT choose the right source. |
| Let the model call tools (templated) | [Agent with Function Calling](tutorial/agent-function-calling.md) | Agent template config | Run calculator, date/time, JSON, or HTTP-backed tool examples. |
| Generate images from chat | [Skills and Image Generation](tutorial/skills-image-generation.md) | Image skill adapter | Invoke the `Image` skill from OrbitChat or curl. |
| Let the model call tools opportunistically, any turn | [Opportunistic MCP Tool Calling](tutorial/mcp-tool-calling.md) | MCP server + `mcp_tools` capability | Ask a business question with no `skill` field and get a tool-backed answer. |
| Answer with live web results, or auto-route from plain language | [Web Search and Automatic Skill Routing](tutorial/auto-skill-routing.md) | Web-search-capable provider (Gemini/OpenAI/xAI) | Get a cited, current answer, with or without an explicit `skill` field. |
| Process requests asynchronously over a message queue | [Message Queue (Async) Requests](tutorial/message-queue-async.md) | RabbitMQ (Docker) + `messaging` profile | Publish a request to a queue and receive a correlated response envelope back. |

## Admin And Configuration

| Need | Page |
| :--- | :--- |
| Create personas and API keys | [Creating API Keys](tutorial/creating-api-keys.md) |
| Connect your own database, files, API, or vector store | [Connecting Your Own Data](tutorial/connecting-your-own-data.md) |
| Understand adapter fields and capabilities | [Adapter Types Overview](tutorial/adapter-types.md) · [Adapter Configuration Reference](tutorial/adapter-configuration-reference.md) |
| Fix common setup issues | [Troubleshooting](tutorial/troubleshooting.md) |
| Decide what to read next | [Next Steps](tutorial/next-steps.md) |
