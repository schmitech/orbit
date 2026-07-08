# Tutorial: Chat with Your Data

Use this tutorial as a set of short paths, not a book you have to read front to back. Start by proving the server, admin panel, API key, and chat client work together, then jump to the adapter that matches your data.

## Fastest Path

| Step | Time | Outcome |
| :--- | :--- | :--- |
| [Before you start](tutorial/before-you-start.md) | 5 min | ORBIT is installed, configured with an inference provider, and running locally. |
| [Your first chat](tutorial/first-chat.md) | 2 min | You create a persona and API key in the admin panel, then send a message through OrbitChat. |

If first chat works, the gateway path is healthy. Pick one of the focused examples below.

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
| Let the model call tools | [Agent with Function Calling](tutorial/agent-function-calling.md) | Agent template config | Run calculator, date/time, JSON, or HTTP-backed tool examples. |
| Generate images from chat | [Skills and Image Generation](tutorial/skills-image-generation.md) | Image skill adapter | Invoke the `Image` skill from OrbitChat or curl. |

## Admin And Configuration

| Need | Page |
| :--- | :--- |
| Create personas and API keys | [Creating API Keys](tutorial/creating-api-keys.md) |
| Connect your own database, files, API, or vector store | [Connecting Your Own Data](tutorial/connecting-your-own-data.md) |
| Understand adapter fields and capabilities | [Adapter Types Overview](tutorial/adapter-types.md) · [Adapter Configuration Reference](tutorial/adapter-configuration-reference.md) |
| Fix common setup issues | [Troubleshooting](tutorial/troubleshooting.md) |
| Decide what to read next | [Next Steps](tutorial/next-steps.md) |
