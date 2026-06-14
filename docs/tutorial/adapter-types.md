# Adapter Types Overview

ORBIT picks the right retrieval strategy based on an *adapter type*. You don't choose these at query time — you configure them once in `config/adapters/*.yaml` and reference them by name when creating an API key.

| Adapter Type | Use it when… | Examples |
|:---|:---|:---|
| **Passthrough** | You want plain chat without retrieval | `simple-chat` |
| **Multimodal** | Users will upload files (PDF, images, audio) | `simple-chat-with-files` |
| **QA** | You have documents already embedded in a vector store | `qa-vector-chroma`, `qa-vector-qdrant` |
| **Intent SQL** | You have a SQL database and want NL → SQL | `intent-sql-sqlite-hr`, `intent-duckdb-analytics` |
| **Intent HTTP** | You want NL → REST API calls | `intent-http-jsonplaceholder` |
| **Intent MongoDB** | You have a MongoDB collection | `intent-mongodb-mflix` |
| **Intent GraphQL** | You have a GraphQL endpoint | `intent-graphql-spacex` |
| **Intent Agent** | You want function-calling with built-in tools | `intent-agent-example` |
| **Composite** | You want one chat that routes across several sources | `composite-multi-source` |
| **Skill** | You want one adapter to invoke another adapter for a single message | `Image`, `web-search`, `mcp-agent` |

---

[Tutorial home](../tutorial.md) | [Previous: Your first chat (2 minutes)](first-chat.md) | [Next: Example 1: SQL Database (SQLite)](sql-database-sqlite.md)

---
