# ORBIT and LiteLLM: Architectural Comparison

This document compares **ORBIT** (Open Retrieval-Based Inference Toolkit) and **LiteLLM**.

---

## Overview

**LiteLLM** is an open-source LLM gateway and Python SDK that provides a single, unified interface to 100+ LLM providers using standardized OpenAI-compatible formatting. Its primary value is eliminating API fragmentation: any provider — OpenAI, Anthropic, Gemini, Bedrock, Azure, and dozens more — is called with the same `completion()` syntax and returns the same response shape. It pairs with a self-hosted proxy server for enterprise features: virtual keys, cost tracking, load balancing, and observability integrations (Langfuse, MLflow, Helicone).

**ORBIT** is an OpenAI-compatible AI gateway and data integration backend. Its primary value is connecting LLM inference to private structured data — relational databases, analytics engines, NoSQL stores, REST APIs, and vector databases — while enforcing production operational controls. It is designed for teams integrating AI into existing infrastructure, not just routing LLM calls between providers.

Where LiteLLM normalizes *how you call models*, ORBIT focuses on *what data models can access* and *how that data is retrieved*.

LiteLLM also uses an **open-core licensing model**: some features (e.g. SSO, certain admin/UI controls, and other enterprise capabilities) are gated behind a commercial license or subscription rather than being available in the open-source proxy. **ORBIT is fully open source with no closed or paywalled features** — everything described in this document, including the admin panel, is available without a commercial license.

---

## Feature Comparison

| Capability | LiteLLM | ORBIT |
| :--- | :--- | :--- |
| **Primary Focus** | Unified interface to 100+ LLM providers; LLM routing and cost governance | AI gateway + structured data integration; RAG against private databases and APIs |
| **Licensing** | Open-core: proxy/SDK is open source, but some enterprise features (e.g. SSO, certain admin/governance controls) require a commercial license or subscription | Fully open source — no features gated behind a commercial license or subscription |
| **LLM Provider Coverage** | 100+ providers (OpenAI, Anthropic, Gemini, Bedrock, Azure, Ollama, and more) | 37+ providers at the time of writing; new providers follow a consistent design pattern and can be added without touching core code |
| **Relational & Structured Data** | No SQL/NoSQL connectors; passes prompts through to LLMs | Native retrievers for SQL, DuckDB/Athena, MongoDB, Cassandra, Elasticsearch, REST APIs, GraphQL, Firecrawl |
| **Intent-Based Data Routing** | Tag-based and health-check-driven model routing | Built-in **Composite Intent Retrievers**: NL query → intent classification → fan-out to the right datasource |
| **Natural-Language Skill Routing** | Not applicable — LiteLLM routes model calls; it has no skill/generation layer to route intent to | **Automatic skill intent detection**: infers image/video/document generation, web search, etc. from plain language and auto-routes it, ChatGPT-style |
| **Response Caching** | LLM response caching (exact-match and semantic) via Redis, Qdrant, S3, and more | **Conversation Threading**: caches raw retrieval datasets in Redis/SQLite with TTL; follow-up questions reuse the dataset, not the LLM response |
| **Fault Tolerance** | Retries, fallbacks (standard/content-policy/context-window), cooldowns, health-check routing | **Circuit Breaker** pattern (open/half-open/closed), fallback routes, best-effort and all-provider execution strategies |
| **Rate Limiting & Quotas** | Per-key and per-team spend budgets and rate limits | Per-key token quotas, sliding window rate limits, datasource connection pooling |
| **API Key Access Control** | Virtual keys scoped to teams/orgs/projects | API keys restrictable to specific pre-authorized email addresses (before first login) and/or specific verified ORBIT user IDs, enforced against the caller's verified identity (session or Entra/Auth0 JWT), not a client-supplied header |
| **Content Moderation** | Not applicable — LiteLLM is a routing layer, not a moderation layer | Pluggable moderators (Llama Guard, policy-adaptive Shieldstral 3B) served via OpenAI-compatible vLLM/llama.cpp endpoints, with inline or file-based policy overrides |
| **Observability** | Third-party integrations: Langfuse, MLflow, Helicone, Lunary; proxy usage/spend tracking and audit capabilities | Built-in audit log plus native usage/cost reporting by call type (inference, embedding, image/video/audio, document, reranking) |
| **MCP Support** | Connects to MCP tool servers; functions as a central MCP endpoint | Server-side MCP orchestration (stdio + Streamable HTTP), admin-managed tool discovery/hot reload/connection pooling; ORBIT also *exposes* its own MCP server for downstream clients |
| **Agent-to-Agent (A2A)** | Supports A2A invocation with LangGraph, Vertex AI Agent Engine | Native A2A protocol support for multi-agent workflows |
| **Async / Message-Queue Ingestion** | HTTP proxy/SDK; async jobs via OpenAI Batches API passthrough (submit/poll); no message-broker consumer | **Broker-native MQ surface** (RabbitMQ/AMQP): ORBIT runs as a queue consumer — publish requests to a queue, responses land on a results queue, fully decoupled from HTTP, with at-least-once delivery |
| **Configuration** | YAML-first proxy config + admin UI dashboard | YAML-first declarative config plus admin UI for hot-reloading adapters, settings, costs, audit, logs, and MCP servers |
| **Voice & Audio** | Routes to audio provider endpoints (STT/TTS passthrough) | STT + TTS per adapter; full-duplex realtime voice over WebSockets; OpenAI Realtime and Gemini Live; grounded realtime voice; fully local pipelines (Whisper + Coqui/vLLM) |
| **Semantic Caching** | Embedding-based semantic cache with configurable similarity threshold | Not applicable — ORBIT caches data results, not LLM responses |
| **Cost Tracking** | Built-in per-provider cost tracking with team/user budgets and a spend dashboard | Built-in usage and estimated-cost tracking with an admin Costs tab, pricing config, and separate attribution for inference, embeddings, media/OCR/audio, document generation, MCP tool-call loops, and reranking |
| **Web Search** | Routes to providers with native search (Perplexity, Gemini with grounding, etc.) | Two modes: provider-native grounding and decoupled external search (DuckDuckGo, Brave, SearXNG, Serper, Tavily, Google PSE, Perplexity) feeding any LLM |
| **File Storage & Encryption** | No general file-upload storage abstraction — `/rag/ingest` selects a RAG *backend* (S3, OpenSearch Serverless, Bedrock Knowledge Base); S3 objects can use AWS KMS encryption (`s3_encryption_key_id`), cloud/S3-specific | Pluggable storage backends (local, S3, MinIO/SeaweedFS, Azure Blob, GCS) with native, backend-agnostic AES-256-GCM file encryption, opt-in per adapter — no KMS dependency required |
| **Deployment** | Python SDK or containerized proxy; Terraform modules for AWS/GCP; Helm charts | Python server; Docker Compose; shell wrapper (`bin/orbit.sh`) |
| **Python SDK** | Yes — `litellm.completion()` usable directly in code without a proxy | No standalone SDK — interaction is via the OpenAI-compatible HTTP API |

---

## Architectural Differences

### 1. Routing Layer vs. Data Integration Layer

**LiteLLM** is a translation and routing layer. It normalizes provider APIs, handles retries and fallbacks across providers, tracks spend, and distributes load. It has no opinion about what data the LLM sees — the application is responsible for assembling the prompt before calling LiteLLM.

**ORBIT** is a data integration layer. It intercepts a natural-language query, classifies its intent, retrieves relevant data from the appropriate source (a database, an API, a vector store), injects that data as context, and then calls an LLM with a fully assembled prompt. The application sends a plain question; ORBIT returns a grounded answer.

The two are complementary: LiteLLM is the right layer when the problem is *which model to call*, ORBIT is the right layer when the problem is *what data that model should see*.

### 2. Response Caching vs. Dataset Caching

LiteLLM caches LLM responses — when the same prompt arrives twice, it returns the cached text. This is effective for stable, low-variance queries where the answer won't change between calls.

ORBIT caches *retrieval datasets* — the raw rows or documents returned from a datasource. When a user asks a follow-up question in the same conversation thread, ORBIT reuses the cached dataset without re-querying the database. The LLM still runs on each turn, but the expensive data fetch is amortized across the conversation. This is useful for multi-turn analytical conversations where the underlying data is stable within a session.

### 3. Fault Tolerance: Cooldowns vs. Circuit Breakers

Both platforms protect against unreliable LLM providers, but with different models.

LiteLLM uses **cooldowns and fallbacks**: a model that fails `N` times is temporarily removed from the rotation. Requests are redirected to other model deployments or fallback groups. Health-check-driven routing avoids endpoints that don't pass periodic checks.

ORBIT uses a **circuit breaker**: a provider that fails crosses an error threshold and trips the circuit to the open state, blocking all requests to that provider immediately. After a configurable timeout, the circuit moves to half-open and allows one probe request. This pattern prevents cascading failures more aggressively than cooldown-based approaches.

### 4. Observability: External Integrations vs. Internal Audit Trail

LiteLLM's observability story is integration-based: plug in Langfuse, MLflow, or Helicone with a single config line and get dashboards, traces, and cost analysis in those platforms. This is ideal for teams already invested in an observability stack.

ORBIT includes a built-in audit log that records every request, response, API key operation, datasource interaction, and provider usage event internally. Recent releases added a native Costs panel and call-type classification so spend can be reviewed separately for inference, embeddings, image/video/audio, OCR/document work, realtime voice, and reranking. There are no external dependencies for compliance tracing — useful in air-gapped or data-sensitive environments where data cannot leave the deployment boundary.

### 5. MCP: Client vs. Server + Client

Both platforms support MCP. LiteLLM functions as a **central MCP client**: models routed through LiteLLM can invoke tools registered with the proxy.

ORBIT operates on both sides: it is an **MCP client** (connecting to external stdio and Streamable HTTP MCP servers for tools like filesystem access, Slack, GitHub, Postgres) and an **MCP server** (exposing its own tool surface at `/mcp` so downstream clients — including Open WebUI or custom agents — can invoke ORBIT's capabilities as MCP tools). ORBIT also treats MCP as an operational surface: admins can add, edit, remove, reload, and rediscover servers from the panel; per-server settings override client defaults; hot reload propagates across multi-worker deployments; and persistent connection pools avoid reconnecting for every tool call.

---

## Where LiteLLM Has a Clear Advantage

- **Provider breadth**: 100+ providers vs. ORBIT's 37+ at the time of writing. If you need to call a niche or newly released model, LiteLLM is more likely to have it out of the box — though ORBIT's provider design pattern makes adding a new one straightforward without modifying core code.
- **Spend governance**: LiteLLM still has the stronger governance layer for teams that need virtual keys tied directly to teams/orgs/projects, hard spend budgets, chargeback workflows, and mature provider-wide spend controls. ORBIT now tracks usage and estimated cost natively, but its controls are gateway/API-key quotas rather than a full enterprise spend-management product.
- **Semantic caching**: LiteLLM can cache semantically similar prompts, not just identical ones. Useful for FAQ-style workloads with high prompt variance.
- **Python SDK**: `litellm.completion()` works in any Python script without standing up a proxy. ORBIT always requires the HTTP server.
- **Observability integrations**: Drop-in integrations with Langfuse, MLflow, Helicone, and Lunary. ORBIT's audit and cost panels are useful for internal compliance and cost review, but they are not a substitute for a dedicated tracing/experiment-observability platform.
- **Enterprise governance tooling**: Virtual keys tied to teams, spend limits, and a UI dashboard make LiteLLM well-suited for managing LLM access across a large organization — though some of this tooling sits behind LiteLLM's commercial/enterprise tier rather than the open-source proxy.

---

## Where ORBIT Has a Clear Advantage

- **Structured data access**: SQL, DuckDB, MongoDB, Cassandra, Elasticsearch, REST APIs, GraphQL — none of these are available in LiteLLM. ORBIT is the right choice whenever answers must come from a private database or internal API.
- **Intent-based retrieval**: ORBIT classifies a natural-language query and routes it to the right datasource automatically. LiteLLM's routing is model-selection routing, not data-routing.
- **Natural-language skill routing**: ORBIT infers intent from plain language ("turn this into a PDF", "read it aloud", "search the web for X") and auto-routes to the matching skill — image/video/document/audio generation, web search — without the user picking a tool, using a hybrid embedding pre-filter + LLM-confirm router. This brings the ChatGPT/Claude experience to any client on the gateway. LiteLLM is a routing/proxy layer and has no skill surface to route to. See [Automatic Skill Intent Detection](../adapters/auto-skill-intent-detection.md).
- **Conversation threading**: Cached datasets across multi-turn conversations reduce database load and token usage in analytical workflows.
- **Voice pipelines**: Per-adapter STT/TTS, fully local pipelines (Whisper + Coqui/vLLM), full-duplex realtime voice, Gemini Live, OpenAI Realtime, voice-history persistence, and grounded realtime voice go well beyond LiteLLM's passthrough to audio provider endpoints.
- **MCP operations**: ORBIT can serve as an MCP tool server for other agents and clients, not just consume MCP tools. It also includes admin-side MCP lifecycle management, scoped hot reload, multi-worker propagation, persistent connection pooling, and circuit-breaking for unhealthy MCP servers.
- **Native usage/cost attribution across workflow types**: ORBIT now records separate usage events for inference, embeddings, image/video/audio, document generation, realtime voice, MCP tool-call loops, and reranking, so a RAG or tool-using workflow is not collapsed into one misleading LLM call.
- **Adapter creation and hot reload**: Operators can create supported adapter types from the admin panel, preview deterministic YAML, register them, and hot-reload without restarting the gateway.
- **Air-gapped deployments**: Built-in audit logging, local voice pipelines, and no mandatory external service dependencies make ORBIT suitable for environments where data cannot leave the deployment boundary.
- **File storage & encryption**: LiteLLM has no general uploaded-file storage abstraction — its `/rag/ingest` endpoint selects a RAG backend (S3, OpenSearch Serverless, Bedrock Knowledge Base) rather than managing user file uploads, and encryption there is AWS KMS on S3 objects specifically. ORBIT treats file storage as a first-class, pluggable layer (local/S3/MinIO/Azure/GCS) with its own backend-agnostic AES-256-GCM encryption, opt-in per adapter, requiring no cloud KMS.
- **Broker-native async ingestion**: ORBIT can run as a RabbitMQ consumer — clients publish requests to a queue and read responses off a results queue, fully decoupled from synchronous HTTP, with at-least-once delivery and dead-lettering. LiteLLM is an HTTP proxy/SDK: async work goes through the OpenAI Batches API (submit/poll), not a message broker. ORBIT's MQ path runs the same pipeline as `/v1/chat`, so retrieval/adapter behavior is identical.
- **Fine-grained API key access control**: ORBIT API keys can be restricted to specific pre-authorized email addresses — so an admin can provision access before a user's first login — and/or to specific verified ORBIT user IDs, both enforced against the caller's identity as verified from the session or an Entra/Auth0 JWT (never a client-supplied header). LiteLLM's virtual keys scope to teams/orgs/projects for spend governance, not to individual pre-authorized identities.
- **Built-in content moderation**: ORBIT ships pluggable input/output moderators — Llama Guard and a policy-adaptive Shieldstral 3B model — served through OpenAI-compatible vLLM or llama.cpp endpoints, with inline or file-based policy customization. LiteLLM has no moderation layer of its own; content-safety would need to be handled by the calling application or the model provider.
- **Fully open source, no paywalled features**: LiteLLM follows an open-core model — the proxy and SDK are open source, but some features are reserved for a commercial license or subscription. Every capability described in this document is available in ORBIT without a commercial license.
- **Actively developed in Canada**: ORBIT's development is based in Canada, an option worth noting for organizations with data-sovereignty preferences or procurement requirements around vendor jurisdiction.

---

## Using LiteLLM and ORBIT Together

Because ORBIT exposes an OpenAI-compatible API, LiteLLM can route requests to ORBIT exactly as it would to any other provider. This creates a clean separation of concerns:

```text
Application / LiteLLM SDK
      |
      | OpenAI-compatible /v1/chat/completions
      | (model routing, cost tracking, fallbacks, spend governance)
      v
LiteLLM Proxy
      |
      | Routes "orbit-hr" → ORBIT Gateway
      v
ORBIT Gateway
      |
      | Intent classification → SQL/NoSQL retrieval → context injection
      v
LLM Provider (OpenAI, Anthropic, Ollama, …)
```

In this architecture:

- **LiteLLM** handles what it does best: normalizing provider APIs, enforcing spend budgets, load-balancing across deployments, and integrating with observability tooling.
- **ORBIT** handles what it does best: classifying query intent, fetching grounded context from private data sources, enforcing per-adapter controls, and assembling the final prompt before calling the LLM.

See the [LiteLLM Integration Guide](litellm-integration.md) for step-by-step setup instructions.

---

## Summary

| | LiteLLM | ORBIT |
|---|---|---|
| **Best for** | Teams routing LLM calls across many providers; spend governance and multi-model deployments | Teams grounding LLM answers in private structured data; AI into existing data infrastructure |
| **Licensing** | Open-core — some enterprise features require a commercial license/subscription | Fully open source — no paywalled features |
| **Deployment model** | Python SDK or containerized proxy; managed cloud options | Self-hosted Python server; Docker Compose |
| **Data access** | LLM providers only — no database or API connectors | SQL/NoSQL, DuckDB/Athena, REST APIs, GraphQL, Elasticsearch, vector stores, Firecrawl |
| **Caching** | LLM response caching (exact-match + semantic) | Retrieval dataset caching across conversation turns |
| **Observability** | Third-party integrations (Langfuse, MLflow, Helicone) plus proxy spend tracking | Built-in audit log and usage/cost panels; no external dependency |
| **MCP** | MCP client (routes tool calls through the proxy) | MCP client + MCP server, admin-managed servers/tools, hot reload, pooled connections |
| **Works well with** | Any OpenAI-compatible backend, including ORBIT | Any OpenAI-compatible client — LiteLLM, Open WebUI, OrbitChat, custom apps |
