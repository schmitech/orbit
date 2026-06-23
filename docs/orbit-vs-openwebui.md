# ORBIT and Open WebUI: Architectural Comparison

This document compares **ORBIT** (Open Retrieval-Based Inference Toolkit) and **Open WebUI**.

---

## 🎯 Overview

**Open WebUI** is a feature-rich full-stack chat application. It ships a Svelte frontend backed by a FastAPI server with built-in support for Ollama, OpenAI-compatible APIs, document RAG, web search, user management, and a plugin pipeline system. It is an excellent choice for teams that want a capable, self-contained chat interface they can deploy and hand to users immediately.

**ORBIT** is an OpenAI-compatible AI gateway and data integration backend. It focuses on connecting AI models to private structured data sources (relational databases, NoSQL stores, APIs), enforcing operational controls (circuit breakers, per-key quotas, audit logs), and serving multiple clients through a single, version-controlled configuration layer. It is designed for platform and data engineering teams building AI into existing infrastructure.

Both projects are self-hosted, open-source, and production-oriented. They occupy different parts of the stack — and as shown at the end of this document, they integrate naturally.

---

## 📊 Feature Comparison

| Capability | Open WebUI | ORBIT |
| :--- | :--- | :--- |
| **Primary Focus** | Full-stack chat application (UI + backend, self-contained) | API gateway & data integration backend (client-agnostic) |
| **Configuration** | GUI & database state; env vars supported but no YAML-first workflow | Configuration-as-Code (YAML declarative templates) |
| **Relational & Structured Data** | Vector DBs and web search; no SQL/NoSQL connectors for user data | Native SQL (PostgreSQL, MySQL, SQLite, Oracle, DuckDB) & NoSQL connectors |
| **Intent-Based Data Routing** | Model/pipeline routing (not natural-language intent routing) | Built-in **Composite Intent Retrievers** routing queries by NL intent |
| **Secrets Handling** | Keys stored server-side; frontend fetches and uses them for direct model calls | **Express API Proxy** (`orbitchat`): keys never reach the browser |
| **Fault Tolerance** | Fallback routing and rate limiting; no circuit breakers | **Circuit Breaker**, fallback routes, execution strategies (`best_effort`, `all`) |
| **Retrieval Caching** | Retrieval re-executed per prompt | **Conversation Threading**: cached dataset reuse across follow-ups (Redis/SQLite + TTL) |
| **Traffic Control** | Rate limiting and connection pooling; no per-user token quotas | Per-key token quotas, sliding window rate limits, datasource connection pooling |
| **Plugin/Middleware System** | Pluggable embedding, reranking, retrieval, and pipeline filters | Decoupled providers for Inference, Embeddings, Reranking, STT, TTS, Search |

---

## 🏗️ Architectural Differences

### 1. Self-Contained Application vs. Decoupled Gateway

**Open WebUI** is a full-stack application: its FastAPI backend and Svelte frontend are designed to work together. The backend handles authentication, RAG orchestration, model routing, and web search — all wired to power its own UI. This makes it fast to deploy and immediately useful out of the box.

**ORBIT** is a gateway-first system. It exposes a single `/v1/chat` OpenAI-compatible API that acts as a secure proxy to local and cloud models, and any client — a custom app, a CLI script, Open WebUI itself, or the lightweight `orbitchat` client — can sit on top of it.

### 2. GUI Configuration vs. GitOps (YAML-first)

In **Open WebUI**, models, connections, and prompts are configured through the UI and stored in a database. Environment variables can override some settings and configs can be exported, but there is no declarative file-based workflow — reproducing an exact environment across dev, staging, and production requires manual effort or database snapshots.

In **ORBIT**, the entire system is driven by YAML files (`config.yaml`, `adapters.yaml`, `inference.yaml`, `datasources.yaml`, etc.). The full AI configuration lives in git, supports hot-reload, and can be replicated across environments instantly.

---

## ⚡ Where ORBIT Adds Unique Capabilities

### 1. Natural-Language Queries Against Structured Databases

Open WebUI covers document RAG, web search, and web scraping well. What it does not include are connectors for querying structured data — relational databases or columnar analytics engines. ORBIT provides native, production-tested retrievers for:

*   **SQL Databases**: PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, SQLite.
*   **Analytics Engines**: DuckDB (including Parquet querying) and Athena.
*   **NoSQL / Text Stores**: MongoDB, Cassandra, Elasticsearch.
*   **Web & APIs**: REST endpoints, GraphQL APIs, and custom web searches.

ORBIT translates natural language into target-specific query syntax (SQL, MongoDB query documents, Elasticsearch Query DSL, REST parameters), executes against connection pools, and returns structured results as LLM context.

### 2. Composite Natural-Language Intent Retrieval

Open WebUI routes requests to different model configurations based on pipeline rules. ORBIT goes a step further: a [Composite Intent Retriever](adapters/composite-intent-retriever.md) uses an LLM to classify query intent at runtime, then fans out to the appropriate data sources — databases, APIs, or vector stores — in a single request. Users don't need to select a datasource; the system infers it.

### 3. Server-Side MCP (Model Context Protocol) Orchestration

ORBIT connects directly to MCP servers over stdio or SSE. Any model routed through the gateway — including local GGUF models — can use MCP tools (filesystem access, Slack, GitHub, Postgres, Jira, Brave Search) managed entirely on the server side.

### 4. Conversation Threading with Cached Dataset Reuse

ORBIT's [Conversation Threading Architecture](conversation-threading-architecture.md) caches raw query results in Redis/SQLite with a TTL. When a user asks a follow-up question within a sub-thread, ORBIT reuses the cached dataset rather than re-querying the database. This reduces database load, lowers API token usage, and speeds up follow-up latency.

### 5. Gateway-Level Fault Tolerance and Quotas

ORBIT adds controls that go beyond what a chat application typically needs:

*   **Circuit Breakers**: Detects downed inference providers and opens the circuit to avoid hanging requests. See [Fault Tolerance Architecture](fault-tolerance/fault-tolerance-architecture.md).
*   **Fallback Routing & Execution Strategies**: Tries multiple providers or returns `best_effort` responses.
*   **Per-Key Token Quotas**: Hard limits per API key for safe resource sharing across teams. See [Rate Limiting](rate-limiting-architecture.md).
*   **Datasource Connection Pooling**: Managed pools to relational databases. See [Datasource Pooling](datasource-pooling.md).

---

## 🔒 Secrets Isolation with `orbitchat`

When access to AI models or databases must not expose raw credentials to the browser, ORBIT's `orbitchat` client (under [clients/orbitchat/](../clients/orbitchat/)) provides a **Decoupled Proxy Architecture**:

```text
Browser Chat UI
      |
      | Sends X-Adapter-Name: "customer-portal" (No Keys)
      v
Express API Proxy (orbitchat server)
      |
      | 1. Resolves "customer-portal" in config
      | 2. Injects target URL & backend X-API-Key
      v
ORBIT Backend Gateway
```

*   **Zero Browser Secrets**: The browser client communicates only with the Express proxy using non-secret adapter names. Keys and connection strings never leave the server.
*   **Standalone CLI NPM Package**: Install globally via `npm install -g orbitchat` and run as a lightweight CLI daemon.
*   **API-Only Proxy Option**: Run with `--api-only` to drop the proxy in front of any existing frontend, including Open WebUI.

---

## 🔗 Using Open WebUI and ORBIT Together

Because ORBIT exposes an OpenAI-compatible API, Open WebUI can connect to it directly as a custom model endpoint. This creates a natural integration:

```text
Open WebUI (frontend + user management + document RAG)
      |
      | OpenAI-compatible /v1/chat/completions
      v
ORBIT Gateway (SQL/NoSQL retrieval, circuit breakers, quotas, MCP tools)
      |
      v
LLM Providers / Local Models / Databases
```

In this setup:

*   **Open WebUI** handles what it does best: a polished chat UI, user authentication, document uploads, web search, and conversation history.
*   **ORBIT** handles what it does best: routing requests to the right data sources, enforcing traffic controls, managing secrets, and providing structured data retrieval that Open WebUI's pipeline doesn't cover.

Teams can start with Open WebUI pointed at a standard Ollama or OpenAI endpoint, then migrate that endpoint to ORBIT to gain structured data access and gateway controls — without changing anything in the Open WebUI configuration.

---

## 🏁 Summary

| | Open WebUI | ORBIT |
|---|---|---|
| **Best for** | Teams wanting a ready-to-use chat UI with RAG and web search | Teams integrating AI into existing data infrastructure |
| **Deployment model** | Self-contained app; deploy and use | Gateway; wire to your data sources and clients |
| **Config approach** | GUI-driven, database-backed | YAML-first, git-versioned |
| **Data access** | Documents, web, vector stores | Documents + SQL/NoSQL databases + APIs |
| **Works well with** | Any OpenAI-compatible backend, including ORBIT | Any OpenAI-compatible frontend, including Open WebUI |
