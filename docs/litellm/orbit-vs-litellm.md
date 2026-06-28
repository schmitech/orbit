# ORBIT and LiteLLM: Architectural Comparison

This document compares **ORBIT** (Open Retrieval-Based Inference Toolkit) and **LiteLLM**.

---

## Overview

**LiteLLM** is an open-source LLM gateway and Python SDK that provides a single, unified interface to 100+ LLM providers using standardized OpenAI-compatible formatting. Its primary value is eliminating API fragmentation: any provider — OpenAI, Anthropic, Gemini, Bedrock, Azure, and dozens more — is called with the same `completion()` syntax and returns the same response shape. It pairs with a self-hosted proxy server for enterprise features: virtual keys, cost tracking, load balancing, and observability integrations (Langfuse, MLflow, Helicone).

**ORBIT** is an OpenAI-compatible AI gateway and data integration backend. Its primary value is connecting LLM inference to private structured data — relational databases, analytics engines, NoSQL stores, REST APIs, and vector databases — while enforcing production operational controls. It is designed for teams integrating AI into existing infrastructure, not just routing LLM calls between providers.

Where LiteLLM normalizes *how you call models*, ORBIT focuses on *what data models can access* and *how that data is retrieved*.

---

## Feature Comparison

| Capability | LiteLLM | ORBIT |
| :--- | :--- | :--- |
| **Primary Focus** | Unified interface to 100+ LLM providers; LLM routing and cost governance | AI gateway + structured data integration; RAG against private databases and APIs |
| **LLM Provider Coverage** | 100+ providers (OpenAI, Anthropic, Gemini, Bedrock, Azure, Ollama, and more) | 37+ providers at the time of writing; new providers follow a consistent design pattern and can be added without touching core code |
| **Relational & Structured Data** | No SQL/NoSQL connectors; passes prompts through to LLMs | Native retrievers for SQL, DuckDB/Athena, MongoDB, Cassandra, Elasticsearch, REST APIs, GraphQL, Firecrawl |
| **Intent-Based Data Routing** | Tag-based and health-check-driven model routing | Built-in **Composite Intent Retrievers**: NL query → intent classification → fan-out to the right datasource |
| **Response Caching** | LLM response caching (exact-match and semantic) via Redis, Qdrant, S3, and more | **Conversation Threading**: caches raw retrieval datasets in Redis/SQLite with TTL; follow-up questions reuse the dataset, not the LLM response |
| **Fault Tolerance** | Retries, fallbacks (standard/content-policy/context-window), cooldowns, health-check routing | **Circuit Breaker** pattern (open/half-open/closed), fallback routes, best-effort and all-provider execution strategies |
| **Rate Limiting & Quotas** | Per-key and per-team spend budgets and rate limits | Per-key token quotas, sliding window rate limits, datasource connection pooling |
| **Observability** | Third-party integrations: Langfuse, MLflow, Helicone, Lunary | Built-in audit log (every request, response, and key operation persisted internally) |
| **MCP Support** | Connects to MCP tool servers; functions as a central MCP endpoint | Server-side MCP orchestration (stdio + SSE); ORBIT also *exposes* its own MCP server for downstream clients |
| **Agent-to-Agent (A2A)** | Supports A2A invocation with LangGraph, Vertex AI Agent Engine | Native A2A protocol support for multi-agent workflows |
| **Configuration** | YAML-first proxy config + admin UI dashboard | YAML-first declarative config; no GUI required |
| **Voice & Audio** | Routes to audio provider endpoints (STT/TTS passthrough) | STT + TTS per adapter; WebSocket real-time streaming; OpenAI Realtime API; fully local pipelines (Whisper + Coqui/vLLM) |
| **Semantic Caching** | Embedding-based semantic cache with configurable similarity threshold | Not applicable — ORBIT caches data results, not LLM responses |
| **Cost Tracking** | Built-in per-provider cost tracking with team/user budgets and a spend dashboard | Not built-in — use an observability tool or audit log post-processing |
| **Web Search** | Routes to providers with native search (Perplexity, Gemini with grounding, etc.) | Two modes: provider-native grounding and decoupled external search (DuckDuckGo, Brave, SearXNG, Serper, Tavily, Google PSE, Perplexity) feeding any LLM |
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

ORBIT includes a built-in audit log that records every request, response, API key operation, and datasource interaction internally. There are no external dependencies for compliance tracing — useful in air-gapped or data-sensitive environments where data cannot leave the deployment boundary.

### 5. MCP: Client vs. Server + Client

Both platforms support MCP. LiteLLM functions as a **central MCP client**: models routed through LiteLLM can invoke tools registered with the proxy.

ORBIT operates on both sides: it is an **MCP client** (connecting to external MCP servers for tools like filesystem access, Slack, GitHub, Postgres) and an **MCP server** (exposing its own tool surface at `/mcp` so downstream clients — including Open WebUI or custom agents — can invoke ORBIT's capabilities as MCP tools).

---

## Where LiteLLM Has a Clear Advantage

- **Provider breadth**: 100+ providers vs. ORBIT's 37+ at the time of writing. If you need to call a niche or newly released model, LiteLLM is more likely to have it out of the box — though ORBIT's provider design pattern makes adding a new one straightforward without modifying core code.
- **Cost tracking**: Built-in spend dashboards and per-team budgets are a first-class feature. ORBIT has no equivalent.
- **Semantic caching**: LiteLLM can cache semantically similar prompts, not just identical ones. Useful for FAQ-style workloads with high prompt variance.
- **Python SDK**: `litellm.completion()` works in any Python script without standing up a proxy. ORBIT always requires the HTTP server.
- **Observability integrations**: Drop-in integrations with Langfuse, MLflow, Helicone, and Lunary. ORBIT's audit log is useful but not a substitute for a dedicated observability platform.
- **Enterprise governance tooling**: Virtual keys tied to teams, spend limits, and a UI dashboard make LiteLLM well-suited for managing LLM access across a large organization.

---

## Where ORBIT Has a Clear Advantage

- **Structured data access**: SQL, DuckDB, MongoDB, Cassandra, Elasticsearch, REST APIs, GraphQL — none of these are available in LiteLLM. ORBIT is the right choice whenever answers must come from a private database or internal API.
- **Intent-based retrieval**: ORBIT classifies a natural-language query and routes it to the right datasource automatically. LiteLLM's routing is model-selection routing, not data-routing.
- **Conversation threading**: Cached datasets across multi-turn conversations reduce database load and token usage in analytical workflows.
- **Voice pipelines**: Per-adapter STT/TTS, fully local pipelines (Whisper + Coqui), and WebSocket real-time audio streaming go well beyond LiteLLM's passthrough to audio provider endpoints.
- **MCP server exposure**: ORBIT can serve as an MCP tool server for other agents and clients, not just consume MCP tools.
- **Air-gapped deployments**: Built-in audit logging, local voice pipelines, and no mandatory external service dependencies make ORBIT suitable for environments where data cannot leave the deployment boundary.

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
| **Deployment model** | Python SDK or containerized proxy; managed cloud options | Self-hosted Python server; Docker Compose |
| **Data access** | LLM providers only — no database or API connectors | SQL/NoSQL, DuckDB/Athena, REST APIs, GraphQL, Elasticsearch, vector stores, Firecrawl |
| **Caching** | LLM response caching (exact-match + semantic) | Retrieval dataset caching across conversation turns |
| **Observability** | Third-party integrations (Langfuse, MLflow, Helicone) | Built-in audit log; no external dependency |
| **MCP** | MCP client (routes tool calls through the proxy) | MCP client + MCP server (exposes ORBIT tools to other agents) |
| **Works well with** | Any OpenAI-compatible backend, including ORBIT | Any OpenAI-compatible client — LiteLLM, Open WebUI, OrbitChat, custom apps |
