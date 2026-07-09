# ORBIT and Open WebUI: Architectural Comparison

This document compares **ORBIT** (Open Retrieval-Based Inference Toolkit) and **Open WebUI**.

---

## 🎯 Overview

**Open WebUI** is a feature-rich full-stack chat application. It ships a Svelte frontend backed by a FastAPI server with built-in support for Ollama, OpenAI-compatible APIs, document RAG, web search, user management, and a plugin pipeline system. It is an excellent choice for teams that want a capable, self-contained chat interface they can deploy and hand to users immediately.

**ORBIT** is an OpenAI-compatible AI gateway and data integration backend. It focuses on connecting AI models to private structured data sources (relational databases, NoSQL stores, APIs), enforcing operational controls (circuit breakers, per-key quotas, audit logs), and serving multiple clients through a single, version-controlled configuration layer. It is designed for platform and data engineering teams building AI into existing infrastructure.

---

## 📊 Feature Comparison

| Capability | Open WebUI | ORBIT |
| :--- | :--- | :--- |
| **Primary Focus** | Full-stack chat application (UI + backend, self-contained) | API gateway & data integration backend (client-agnostic: web, mobile, CLI, or any OpenAI-compatible client) |
| **Configuration** | GUI & database state; env vars supported but no YAML-first workflow | Configuration-as-Code (YAML declarative templates) |
| **Relational & Structured Data** | Vector DBs; no SQL/NoSQL connectors for user data | SQL, DuckDB/Athena analytics, MongoDB, Cassandra, Elasticsearch, REST APIs, GraphQL, Firecrawl |
| **Intent-Based Data Routing** | Model/pipeline routing (not natural-language intent routing) | Built-in **Composite Intent Retrievers** routing queries by NL intent |
| **Web Search** | Built-in search across 20+ providers | Two modes: provider-native (Gemini/OpenAI/xAI) and external backends decoupled from synthesis (any LLM can answer) |
| **Cross-Adapter Skills** | Plugin/pipeline filters applied at the request/response boundary | **Skills system**: any adapter can invoke image/video generation, web search, or custom skills inline without switching adapters |
| **Query Autocomplete** | No intent-driven autocomplete | Fuzzy autocomplete from adapter intent templates with Redis caching |
| **Fault Tolerance** | Fallback routing and rate limiting; no circuit breakers | **Circuit Breaker**, fallback routes, best-effort and all-provider execution strategies |
| **Retrieval Caching** | Retrieval re-executed per prompt | **Conversation Threading**: cached dataset reuse across follow-ups (Redis/SQLite + TTL) |
| **Traffic Control** | Rate limiting and connection pooling; no per-user token quotas | Per-key token quotas, sliding window rate limits, datasource connection pooling |
| **Voice & Audio** | STT/TTS via configured providers; no real-time WebSocket streaming | STT + TTS per adapter; WebSocket real-time streaming; OpenAI Realtime API; fully local pipelines (Whisper + Coqui/vLLM, no API cost) |
| **File Storage Backends** | Pluggable via `STORAGE_PROVIDER`: local (default), S3 (+ S3-compatible), GCS, Azure Blob | Pluggable via `files.storage_backend`: local (default), S3, MinIO/SeaweedFS (S3-compatible), Azure Blob, GCS — comparable backend coverage |
| **File Encryption at Rest** | Not available — application-level file encryption is an open feature request ([#16112](https://github.com/open-webui/open-webui/issues/16112), [#17437](https://github.com/open-webui/open-webui/issues/17437)); only DB-level SQLCipher is supported today | Native AES-256-GCM, opt-in per adapter — covers uploaded file bytes, storage metadata, and indexed vector-store chunk content, on any storage backend |
| **Async / Message-Queue Ingestion** | HTTP request/response (and WebSocket) only; no broker-native async ingestion | **Broker-native MQ surface** (RabbitMQ): publish requests to a queue, ORBIT consumes them through the same pipeline and replies on a results queue — decoupled, at-least-once batch/async processing beyond synchronous HTTP |
| **Extensibility** | Plugin system for pipelines; core architecture changes require forking | New adapters and data connectors added via YAML and a clear design pattern — no core changes needed |
| **Plugin/Middleware System** | Pluggable embedding, reranking, retrieval, and pipeline filters | Decoupled providers for Inference, Embeddings, Reranking, STT, TTS, Search |

---

## 🏗️ Architectural Differences

### 1. Self-Contained Application vs. Decoupled Gateway

**Open WebUI** is a full-stack application: its FastAPI backend and Svelte frontend are designed to work together. The backend handles authentication, RAG orchestration, model routing, and web search — all wired to power its own UI. This makes it fast to deploy and immediately useful out of the box.

**ORBIT** is a gateway-first system. It exposes a single OpenAI-compatible API endpoint that acts as a secure proxy to local and cloud models, and any client — a custom web app, a mobile app (iOS or Android), a CLI script, Open WebUI itself, or the lightweight OrbitChat client — can sit on top of it. The same backend serves all surfaces without modification.

### 2. GUI Configuration vs. GitOps (YAML-first)

In **Open WebUI**, models, connections, and prompts are configured through the UI and stored in a database. Environment variables can override some settings and configs can be exported, but there is no declarative file-based workflow — reproducing an exact environment across dev, staging, and production requires manual effort or database snapshots.

In **ORBIT**, the entire system is driven by YAML files covering adapters, inference providers, datasources, and more. The full AI configuration lives in git, supports hot-reload, and can be replicated across environments instantly.

---

## ⚡ Where ORBIT Adds Unique Capabilities

### 1. Natural-Language Queries Against Structured Databases

Open WebUI covers document RAG, web search, and web scraping well. What it does not include are connectors for querying structured data — relational databases, analytics engines, or external APIs. ORBIT provides native, production-tested retrievers for:

*   **SQL Databases**: PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, SQLite.
*   **Analytics Engines**: DuckDB (including Parquet querying) and Athena.
*   **NoSQL / Text Stores**: MongoDB, Cassandra, Elasticsearch.
*   **REST APIs**: Any JSON REST endpoint, including public datasets and internal services.
*   **GraphQL**: Natural-language queries translated to GraphQL operations against any compatible API.
*   **Web Scraping via Firecrawl**: Crawl and extract structured content from web pages, making it queryable like any other data source.

ORBIT translates natural language into target-specific query syntax (SQL, MongoDB query documents, Elasticsearch Query DSL, REST parameters, GraphQL operations), executes against connection pools or live endpoints, and returns structured results as LLM context.

### 2. Composite Natural-Language Intent Retrieval

Open WebUI routes requests to different model configurations based on pipeline rules. ORBIT goes a step further: a [Composite Intent Retriever](adapters/composite-intent-retriever.md) uses an LLM to classify query intent at runtime, then fans out to the appropriate data sources — databases, APIs, or vector stores — in a single request. Users don't need to select a datasource; the system infers it.

### 3. Server-Side MCP (Model Context Protocol) Orchestration

ORBIT connects directly to MCP servers over stdio or SSE. Any model routed through the gateway — including local GGUF models — can use MCP tools (filesystem access, Slack, GitHub, Postgres, Jira, Brave Search) managed entirely on the server side.

### 4. Conversation Threading with Cached Dataset Reuse

ORBIT's [Conversation Threading Architecture](conversation-threading-architecture.md) caches raw query results in Redis/SQLite with a TTL. When a user asks a follow-up question within a sub-thread, ORBIT reuses the cached dataset rather than re-querying the database. This reduces database load, lowers API token usage, and speeds up follow-up latency.

### 5. Web Search Decoupled from Synthesis

Open WebUI has solid built-in web search across many providers, tightly integrated into its own UI. ORBIT approaches web search differently: searching and synthesis are separate pipeline steps, so any search backend can feed results to any inference provider.

ORBIT supports two modes (see [Web Search Adapters](adapters/web-search.md)):

*   **Provider-native search**: Gemini, OpenAI, and xAI perform searching and synthesis in a single API call with inline grounding citations.
*   **External search providers**: DuckDuckGo (free, no key), Brave, SearXNG (self-hosted), Serper, Tavily, Google PSE, and Perplexity fetch results as structured context, which any LLM — including Anthropic, Ollama, or local models — then synthesizes.

Both modes are also exposable as [skills](#6-cross-adapter-skills), so any adapter can trigger a web search on demand without switching to a dedicated search adapter.

### 6. Cross-Adapter Skills

ORBIT's [Skills system](adapters/skills.md) lets any adapter invoke a specialized capability — image generation, web search, or custom extensions — inline within an ongoing conversation, without the client needing to switch adapters or manage separate endpoints.

Each adapter declares which skills it is permitted to invoke. When a skill is requested, ORBIT validates the permission, routes the message to the skill adapter, and returns its output — bypassing the calling adapter's normal retrieval pipeline for that turn.

New skills require no server code changes: marking an adapter as a skill in its configuration file is enough for ORBIT to discover and register it at startup.

### 7. Query Autocomplete from Intent Templates

ORBIT's [autocomplete system](autocomplete-architecture.md) surfaces real-time query suggestions as users type, drawn directly from the example queries defined in each intent adapter's templates. This gives users discoverable, adapter-aware suggestions without any separate configuration.

### 8. Voice, Audio, and Real-Time Streaming

Both projects support STT and TTS. ORBIT's audio system goes further in three areas:

**Independently configurable STT and TTS per adapter.** Each adapter specifies its own speech-to-text and text-to-speech provider, chosen from: OpenAI, Gemini, Google, xAI, ElevenLabs, Whisper (local), Coqui (local), and vLLM (local Orpheus model). A single deployment can run a premium voice adapter alongside a fully local one with no shared configuration.

**Fully local voice pipelines.** ORBIT supports combining local Whisper speech-to-text with local Coqui or vLLM text-to-speech — zero API calls, zero cost, suitable for air-gapped or privacy-sensitive environments. GPU acceleration is supported where available.

**WebSocket real-time bidirectional audio streaming.** ORBIT supports phone call-style voice sessions over WebSockets with voice activity detection, configurable silence thresholds, and optional interruption support. It also proxies the [OpenAI Realtime API](https://developers.openai.com/api/docs/guides/realtime) for speech-to-speech in a single round trip, with a dedicated test client included in the repository. See the [Audio Services Guide](audio/audio-services-adapter-guide.md) for full configuration details.

**Audio transcription with vector indexing.** ORBIT accepts uploaded audio files, transcribes them via a configured speech-to-text provider, and indexes the transcript in a vector store — making recorded meetings, calls, or podcasts searchable in subsequent conversation turns.

### 9. Gateway-Level Fault Tolerance and Quotas

ORBIT adds controls that go beyond what a chat application typically needs:

*   **Circuit Breakers**: Detects downed inference providers and opens the circuit to avoid hanging requests. See [Fault Tolerance Architecture](fault-tolerance/fault-tolerance-architecture.md).
*   **Fallback Routing & Execution Strategies**: Tries multiple providers or returns a best-effort partial response.
*   **Per-Key Token Quotas**: Hard limits per API key for safe resource sharing across teams. See [Rate Limiting](rate-limiting-architecture.md).
*   **Datasource Connection Pooling**: Managed pools to relational databases. See [Datasource Pooling](datasource-pooling.md).

### 10. Built for Extensibility and Evolving Business Requirements

ORBIT is designed from the ground up to grow with your needs. Adding a new data source, a new use case, or a new AI workflow does not require touching the core codebase — it follows a consistent adapter design pattern where each new capability is a self-contained unit declared in configuration.

In practice this means:

*   **New data connectors**: Connect a new database, API, or data source by implementing a retriever that follows the established base class pattern and wiring it up in YAML. The rest of the system — routing, caching, circuit breakers, audit logs — works automatically.
*   **New domain copilots**: A new business use case represents a new adapter configuration. Teams can ship new AI workflows without engineering changes to the platform itself.
*   **New inference providers**: Adding a new LLM provider follows the same pattern as the existing 39 providers. Once registered, any adapter can use it by name.
*   **New skills**: A new cross-adapter capability (video generation, code execution, translation) is an adapter with a single flag set — no pipeline changes required.
*   **Swappable at every layer**: Inference, embeddings, reranking, STT, TTS, vector stores, and search backends are all independently replaceable. As better models emerge or your infrastructure changes, you update a provider setting rather than rewriting application logic.

This makes ORBIT a durable platform investment: the architecture adapts to changing models, data sources, and business requirements without accumulating technical debt.

### 11. Native File Encryption at Rest

Both projects support the same set of pluggable file storage backends — local disk, AWS S3 (or S3-compatible stores), Google Cloud Storage, and Azure Blob — so storage flexibility is comparable. Where they diverge is encryption: Open WebUI has no application-level encryption for uploaded files today (it's tracked as an open feature request; only database-level SQLCipher is supported), so files sit in plaintext on whichever backend is configured.

ORBIT ships native AES-256-GCM file encryption, opt-in per adapter via `capabilities.requires_encryption` — no cloud KMS dependency, no separate infrastructure. It covers not just the raw uploaded bytes but the storage backend's metadata sidecar and the text/metadata indexed into the vector store for RAG, so retrieval still works (embeddings are computed from plaintext before encryption) while the data at rest — on any backend — stays encrypted. See the [File Encryption guide](../adapters/file-adapter-guide.md#encryption-at-rest).

### 12. Broker-Native Async Ingestion (Message Queue)

Open WebUI is driven entirely over HTTP (and WebSockets) — every request is a synchronous, connected round trip against its backend. There is no way to hand it a queue of work and collect answers later.

ORBIT adds a **broker-native message-queue surface** alongside its HTTP surfaces. Instead of a blocking call, a client **publishes a request message** to a broker queue; ORBIT runs as a **consumer**, processes each message through the *same* inference pipeline as `/v1/chat` (identical adapter, auth, and system-prompt resolution), and **publishes a response envelope** back to the message's `reply_to`, correlated by `correlation_id`. This decouples producers from ORBIT entirely — ideal for batch jobs, spiky/bursty workloads, and fan-out pipelines where callers shouldn't hold a connection open.

Key properties:

*   **RabbitMQ today, pluggable by design** — the broker sits behind a `MessageBroker` abstraction (mirroring ORBIT's cache-backend pattern), so other brokers can be added without touching the consumer logic. Opt-in via the `messaging` dependency profile; disabled by default.
*   **At-least-once delivery** — the broker only acks a message after the pipeline completes, so an in-flight message survives a worker crash and is redelivered. Unparseable messages and unexpected failures are dead-lettered for inspection, while business failures (bad key, empty message) return a `failed` envelope so callers always get an answer.
*   **Flexible hosting** — run the consumer as a standalone `orbit worker` process (scale/deploy independently of the web server) or in-process inside the server. See the [Message Queue Protocol](../server.md#message-queue-async-protocol).

---

## 🔒 Secrets Isolation with OrbitChat

When access to AI models or databases must not expose raw credentials to the browser, ORBIT's OrbitChat client (under [clients/orbitchat/](../clients/orbitchat/)) provides a **Decoupled Proxy Architecture**:

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
*   **Standalone NPM Package**: Install globally and run as a lightweight CLI daemon.
*   **API-Only Proxy Option**: Run without a UI to drop the proxy in front of any existing frontend, including Open WebUI.

---

## 🔗 Using Open WebUI and ORBIT Together

Because ORBIT exposes an OpenAI-compatible API, Open WebUI can connect to it directly as a custom model endpoint. This creates a natural integration:

```text
Open WebUI (frontend + user management + document RAG)
      |
      | OpenAI-compatible /v1/chat/completions
      v
ORBIT Gateway (SQL/NoSQL retrieval, circuit breakers, quotas, MCP tools, voice/audio)
      |
      v
LLM Providers / Local Models / Databases
```

In this setup:

*   **Open WebUI** handles what it does best: a modern chat UI, user authentication, document uploads, web search, and conversation history.
*   **ORBIT** handles what it does best: routing requests to the right data sources, enforcing traffic controls, managing secrets, and providing structured data retrieval that Open WebUI's pipeline doesn't cover.

Teams can start with Open WebUI pointed at a standard Ollama or OpenAI endpoint, then migrate that endpoint to ORBIT to gain structured data access and gateway controls — without changing anything in the Open WebUI configuration.

---

## 🏁 Summary

| | Open WebUI | ORBIT |
|---|---|---|
| **Best for** | Teams wanting a ready-to-use chat UI with RAG and web search | Teams integrating AI into existing data infrastructure |
| **Deployment model** | Self-contained app; deploy and use | Gateway; wire to your data sources and clients |
| **Config approach** | GUI-driven, database-backed | YAML-first, git-versioned |
| **Data access** | Documents, web search, vector stores | SQL/NoSQL databases, DuckDB/Athena analytics, REST APIs, GraphQL, Firecrawl, Elasticsearch, vector stores, documents, decoupled web search, searchable transcribed audio |
| **Works well with** | Any OpenAI-compatible backend, including ORBIT | Any OpenAI-compatible client — web apps, mobile apps, Open WebUI, CLI tools |
