# ORBIT Capability Matrix

## Overview

**ORBIT (Open Retrieval-Based Inference Toolkit)** is an open-source AI gateway, retrieval-augmented generation (RAG) engine, and agent-protocol host. It can be deployed on-premises, in a private cloud, or fully offline.

Models, data sources, adapters, and security settings are defined as YAML files under `config/`, rather than in server code. This allows configuration to be version-controlled and reviewed in a source repository like any other code artifact, diffed between commits, and promoted across development, staging, and production environments through the organization's existing CI/CD and change-management process — supporting typical DevSecOps practices for multi-environment deployment.

This document describes ORBIT's capabilities as implemented in its configuration files (`config/*.yaml`) and documentation (`docs/`), and compares them against three reference categories:

- **LiteLLM** — an LLM API proxy and router
- **Open WebUI** — a chat user interface for local/cloud LLMs
- **Commercial managed AI platforms** (e.g., AWS Bedrock, Azure AI, Google Vertex AI, IBM watsonx)

Each row in the comparison tables is intended to describe what each platform does, not to rank them. Where a claim about a comparison platform could not be verified against that platform's own documentation or pricing page, it has been noted as such or omitted.

<div class="keep-together">

## 1. Architecture

<div style="text-align:center">
<img src="orbit-architecture.svg" alt="ORBIT architecture diagram" style="max-height:460px" />
</div>

Clients connect through the ORBIT API over REST, an OpenAI-compatible interface, MCP, A2A, or async MQ transports. Requests pass through auth/quota checks, then an adapter router that dispatches to chat/voice, document, structured-data, API, tool-agent, or generation handlers, which in turn call local or cloud model providers.

</div>

## 2. Comparison Matrix

| Dimension | **ORBIT** | **LiteLLM** | **Open WebUI** | **Commercial Managed Platforms** *(Bedrock/Azure/Vertex)* |
| :--- | :--- | :--- | :--- | :--- |
| **Primary function** | AI gateway + multi-source RAG + agent protocol host | LLM API proxy and router | Chat user interface for local/cloud LLMs | Managed cloud AI service |
| **Inference backends** | 41 provider/runtime configurations (cloud APIs, local GGUF, vLLM, TensorRT-LLM, BitNet, AirLLM, TEE) — including Azure OpenAI preset migration (`config/azure.yaml`) via `openai.AsyncOpenAI` — see note in §3.1 on default-disabled backends | Broad set of cloud/proxy API routes | Ollama-native; also reaches any OpenAI-compatible endpoint (OpenAI, or a self-hosted llama.cpp/vLLM/LM Studio server) | Vendor-operated model catalog |
| **Data source integration** | SQL (9 dialects), vector DBs (6 integrated), NoSQL, REST/GraphQL, web search (provider-native for Gemini/OpenAI/xAI, plus 7 external search backends usable with any LLM); intent retrieval telemetry & multi-turn slot-fill clarification (see §3.2) | No built-in data-source connectors; typically paired with an external RAG pipeline | 13 supported vector databases, web search with source citations, and hybrid (BM25 + vector) search with cross-encoder reranking; no built-in SQL/NoSQL database connectors as retrieval sources | Cloud-native connectors (S3/Blob/GCS) and managed vector search services |
| **Document & media processing** | Three document-parsing engines (Docling, MarkItDown, LLM/vision OCR); image (OpenAI, Gemini, xAI, Azure OpenAI), video, STT/TTS generation, Azure OCR/vision & embeddings | Not included | 8 supported document-extraction engines (including Tika, Docling, Mistral OCR); image generation (GPT-Image, Gemini, ComfyUI) and voice/audio (speech-to-text, text-to-speech) | Cloud OCR/vision services (e.g., Textract, Form Recognizer) |
| **Agent protocols** | MCP (server & client host with file- & DB-authored procedural tool skills/playbooks, JIT injection & priority budget capping — see §3.5), Google A2A, RabbitMQ-based async messaging | Function/tool-call proxying | MCP support, OpenAPI-server tools, and a Python tools/functions framework; no documented A2A support | Vendor-specific agent frameworks |
| **Conversational UX features** | Cross-adapter skill invocation with optional automatic intent routing, query autocomplete from adapter/skill examples, per-model dynamic history budgeting, and slot-fill disambiguation (see §3.9) | Not in scope — LiteLLM proxies inference calls and does not manage conversation state or UX | Model presets, cross-conversation memory of remembered facts, and Markdown-defined "Skills"; these are chat-UI/prompt-level features rather than ORBIT's server-side adapter-routing and dynamic per-model history budgeting | Varies by vendor SDK/console; not a standard cross-platform feature |
| **Response feedback capture** | Built-in per-message thumbs up/down with optional comment, stored per adapter/user, with a dedicated admin-panel analytics view (satisfaction trend, per-adapter ranking, negative-feedback triage) — see §3.9 | Not in scope — LiteLLM does not track end-user response ratings | Open WebUI has a per-message rating feature; whether it includes adapter-level trend/satisfaction analytics comparable to §3.9 was not verified against its documentation for this comparison | Varies by vendor console; typically not exposed as a queryable per-response feedback dataset |
| **Security & identity** | 6-role RBAC (11 permissions), OIDC/SSO (Entra ID, Auth0), deny-by-default external identity allowlisting with session withdrawal & JWT role capping (§3.6), OS keyring, AES-256 file encryption — included in the open-source distribution | Proxy-level auth in the open-source tier; SSO/SCIM, OIDC/JWT auth, and audit logs are listed as part of the paid Enterprise tier per LiteLLM's published pricing (see §4.1) | RBAC with roles, groups, and per-resource permissions; SSO/OIDC/LDAP and SCIM 2.0; API keys — per its documentation, listed as part of the open-source product | Cloud IAM (AWS IAM, Azure RBAC, etc.) |
| **Per-key usage limits** | Each API key can be bound to one adapter and given its own daily/monthly quota and priority-based throttling, managed from the admin panel with live usage and reset controls (see §3.6) | Per-key rate/spend limits are also included in LiteLLM's open-source tier, using its own proxy-level design | Not a documented feature of the open-source product | Varies by vendor console; typically account- or project-level rather than per-key |
| **Inference cost tracking** | A local, configurable pricing table estimates cost on every request (text, media, and realtime-voice), with per-record and aggregated views (by model/provider/adapter/user/API key) in the admin panel — see §3.8 | Also cost-tracked in the open-source tier, via LiteLLM's own maintained model-pricing map, with spend reporting by key/user/team | Included in the open-source product: an Analytics dashboard tracks token usage per message, model, and user. Per its own documentation, it does not calculate a dollar cost automatically — the admin multiplies the tracked token counts by their provider's price manually | Native, invoice-accurate billing through the vendor's own cloud billing console |
| **Safety & moderation** | Configurable moderation backends (OpenAI, Anthropic, Llama-Guard3, Shieldstral), plus two PII detectors: a local model (`privacy-filter`) and a Presidio analyzer integration (~100 entity types with batch concurrency control) | Integrates with external moderation/PII services (e.g., Presidio) | Basic moderation options | Managed cloud guardrail services |
| **Hardware acceleration** | CUDA, MPS, vLLM, TensorRT-LLM (FP8/INT8), SGLang, BitNet | Routes to external inference servers; does not run hardware-accelerated inference itself | Dependent on the Ollama backend it connects to | Managed cloud GPU infrastructure |
| **Deployment model** | Docker, Kubernetes, bare-metal, air-gapped, async worker processes | Docker, Kubernetes, serverless | Docker/Compose, Kubernetes/Helm, pip install, with Redis-backed horizontal scaling across multiple workers/nodes | Managed cloud SaaS/PaaS |
| **License** | Apache 2.0 (single tier, no gated features) | Open-source core under a permissive license, with a separate paid Enterprise tier for the features listed in §4.1 (per litellm.ai/pricing) | BSD-3-Clause through v0.6.5; v0.6.6+ adds a branding-protection clause (not OSI-approved as "open source"), with a separate enterprise license for white-labeling — see §4.2 | Proprietary cloud service |

## 3. Capability Detail

### 3.1 LLM Gateway & Inference

ORBIT defines **41 inference provider/runtime configurations** in `config/inference.yaml`. Most are disabled by default and require an API credential or a locally running runtime to be usable — the count reflects configured integrations, not backends active in a given deployment.

| Capability | Details | Source |
| :--- | :--- | :--- |
| Supported backends | Major cloud providers (OpenAI, Anthropic, Gemini, AWS Bedrock, Azure OpenAI, Vertex AI, Cohere, Mistral, IBM watsonx, and more), plus local/self-hosted runtimes (Ollama, vLLM, llama.cpp, and others) | `config/inference.yaml` |
| Local hardware acceleration | Support for running models efficiently on local GPUs, including optimized runtimes for high-throughput and low-bit/quantized models | `config/inference.yaml` |
| Confidential computing | Integration with a trusted-execution-environment (TEE) provider for confidential model inference | `config/inference.yaml` |
| Fault tolerance | Automatic circuit-breaking on repeated provider failures, with configurable retry timing and fallback to an alternate model | `config/config.yaml` (`fault_tolerance`) |
| Per-adapter provider overrides | Each adapter can be configured to use a different inference, embedding, or reranking provider and model than the system default | `config/adapters.yaml` |
| Azure OpenAI provider migration & presets | Native `openai.AsyncOpenAI` client integration using versionless `/openai/v1` endpoints, reasoning token support (`max_completion_tokens`), and named presets in `config/azure.yaml` for per-adapter deployment overrides | `CHANGELOG.md` (v2.17.0) |

### 3.2 Data Sources & Retrieval

| Capability | Details | Source |
| :--- | :--- | :--- |
| SQL databases | PostgreSQL, MySQL, MariaDB, SQLite, Supabase, Oracle, SQL Server, DuckDB, AWS Athena | `config/datasources.yaml` |
| Vector databases | Chroma, Qdrant, Milvus, Pinecone, Elasticsearch, Redis Vector | `config/datasources.yaml`, `config/stores.yaml` |
| NoSQL databases | MongoDB (Atlas or self-hosted), Cassandra | `config/datasources.yaml` |
| Web/API sources | Intent-based query generation against REST/JSON and GraphQL APIs (e.g. natural language mapped to calls against a REST endpoint or a GraphQL API), plus a web-scraping adapter (Firecrawl) with automatic content chunking for large pages | `config/adapters/intent.yaml` |
| Web search — provider-native | For supported LLM providers (Gemini, OpenAI, xAI), search and answer synthesis happen in a single call using the provider's own built-in search tool | `config/adapters/web-search.yaml`, `docs/adapters/web-search.md` |
| Web search — external providers | Any configured LLM can be paired with an external search engine (e.g., DuckDuckGo, Brave, Tavily, Google), so the search source and the answering model can be chosen independently | `config/adapters/web-search-providers.yaml`, `docs/adapters/web-search.md` |
| Embedding providers | OpenAI, Cohere, Mistral, Gemini, Voyage AI, Azure OpenAI, and other embedding providers, plus local/self-hosted options | `config/embeddings.yaml` |
| Rerankers | Cohere, Jina, OpenAI, Anthropic, Voyage AI, and OpenRouter reranking providers | `config/rerankers.yaml` |
| Hybrid retrieval scoring | Combines semantic similarity, keyword matching, and reranking to improve result relevance | `config/config.yaml` (`composite_retrieval`) |
| SQL query safety guard | Every generated SQL query is checked before it runs, to confirm it is a single, read-only, size-limited query — blocking any query that would modify data | `CHANGELOG.md` (v2.15.3) |
| Intent template validation | Query templates are checked for correctness when loaded, and can optionally require administrator approval before being used | `CHANGELOG.md` (v2.15.4) |
| Intent retrieval telemetry & Misses triage | Telemetry tracks retrieval outcomes, candidate scores, confidence levels, and guard rejections across SQL, HTTP, Composite, and Agent retrievers, with an admin panel Misses view for triage | `CHANGELOG.md` (v2.16.0) |
| Intent disambiguation & slot filling | Confidence-banded disambiguation and multi-turn slot-fill clarification for intent SQL adapters with bounded TTL session state across streaming and non-streaming responses | `CHANGELOG.md` (v2.16.0) |

Retrieval works through **intent-based query generation**: a natural-language question is matched to a pre-approved query template rather than having a general-purpose model generate a new database query on every request.

### 3.3 Document Processing

| Capability | Details | Source |
| :--- | :--- | :--- |
| File formats | PDF, Word, PowerPoint, Excel, CSV, JSON, XML, HTML, plain text, EPUB, ZIP, images, and audio | `config/config.yaml` |
| Processing engines (in priority order) | Layout-aware document parsing, then document-to-markdown conversion, then AI vision/OCR as a fallback for harder documents | `config/config.yaml` (`files.processing.processor_priority`), `config/ocr.yaml` |
| Chunking strategies | Several methods for splitting documents into retrievable pieces (fixed-size, token-based, semantic, and structure-aware) | `config/config.yaml` (`files.default_chunking_strategy`) |
| Document security | File-type verification on upload and encryption of stored documents | `config/config.yaml` (`files.processing.magika`, `files.encryption`) |
| Storage backends | Local filesystem, AWS S3/MinIO, Azure Blob Storage, Google Cloud Storage | `config/config.yaml` (`files.storage_backend`) |

### 3.4 Multimodal & Media Processing

| Domain | Details | Source |
| :--- | :--- | :--- |
| Speech-to-text | Local, on-device transcription, plus cloud providers including OpenAI, Google, Gemini, and OpenRouter | `config/stt.yaml` |
| Text-to-speech | Cloud providers (OpenAI, Google, Gemini, ElevenLabs, OpenRouter) and local/self-hosted voice engines | `config/tts.yaml` |
| Audio content sanitization | Non-speech content (like code blocks or tables) is stripped out before text is converted to speech, so spoken responses stay natural | `config/tts.yaml` (`tts.sanitize_content`) |
| Image generation | OpenAI, Gemini, xAI, Azure OpenAI (GPT-Image & DALL-E), OpenRouter, and other providers | `config/image.yaml` |
| Video generation | Gemini, xAI, OpenRouter, and other video-generation providers | `config/video.yaml` |
| Vision/OCR analysis | OpenAI, Anthropic, Gemini, Azure OpenAI, Azure Mistral OCR, and other vision-capable providers | `config/vision.yaml` |
| Real-time speech-to-speech | Live, interruptible voice conversations (the user can talk over the assistant), rather than a separate transcribe-then-speak pipeline. Can be connected to ORBIT's own data sources so spoken answers are grounded in real information rather than the model's general knowledge — useful for live virtual-assistant scenarios. | `config/adapters/qa.yaml`, `docs/adapters/grounded-realtime-voice.md` |

An administrator can restrict, per adapter, which specific models a user is allowed to select for image, video, audio, and web-search generation, rather than every adapter being locked to one fixed default. (`CHANGELOG.md`, v2.15.6)

### 3.5 Protocols

| Protocol | Details | Source |
| :--- | :--- | :--- |
| REST / OpenAI-compatible | A standard chat API compatible with the widely-used OpenAI format, with streaming responses | `server/routes/` |
| Model Context Protocol (MCP) | Can act as an MCP server (exposing ORBIT's own capabilities to other tools) and as an MCP client (connecting to external MCP tools, such as a filesystem or GitHub) | `config/mcp_clients.yaml`, `docs/mcp_protocol.md` |
| MCP agentic tool-calling | The model can call one or more external tools, review the results, and reason over multiple steps within a single request — built directly into ORBIT, without relying on a separate agent-orchestration framework. This can be an explicit request feature, or enabled so a normal conversation automatically decides when a tool is needed. Supported across most major LLM providers. | `docs/adapters/mcp-agent.md` |
| MCP Tool Skills & Procedural Playbooks | File-authored (`SKILL.md`) and database-backed procedural playbooks bound to MCP tools, disclosed progressively per turn via `orbit__load_tool_skill`, injected just-in-time on tool execution, budget-capped with priority admission, and managed via live Admin UI CRUD with multi-worker hot reload | `docs/mcp_protocol.md`, `CHANGELOG.md` |
| Google A2A | Supports Google's Agent-to-Agent protocol for agent discovery and task execution between AI systems | `docs/a2a-protocol.md` |
| Async messaging | Message-queue-based request/response support for decoupled, asynchronous processing | `config/config.yaml` (`messaging`) |
| WebSockets | Real-time, two-way streaming for voice and live status updates | `/ws`, `/ws/metrics` |
| AI coding-agent integration | Because MCP and A2A are open, provider-neutral protocols, ORBIT can be connected to external agentic tools that speak either one. This is documented in detail for Claude (Desktop, Code, and SDK-based agents), which can call ORBIT as an MCP tool or address it as a peer agent over A2A. Other MCP- or A2A-compliant agent tools and coding assistants can connect the same way, though the level of support for each has not been individually verified for this comparison. | `docs/claude-agent-integration.md` |

### 3.6 Security, Governance & Identity

| Capability | Details | Source |
| :--- | :--- | :--- |
| Authentication | Industry-standard password hashing, secure session tokens, and integration with the operating system's credential store | `docs/authentication.md` |
| SSO | Single sign-on via Microsoft Entra ID and Auth0 | `config/config.yaml` (`auth.providers`) |
| Deny-by-default identity allowlisting | Configurable rule-based access control (`access_control: allowlist`) requiring explicit pre-clearing of emails, user IDs, or OIDC provider-subjects before external identity provisioning | `docs/authentication.md`, `CHANGELOG.md` (v2.17.0) |
| Session & token withdrawal enforcement | Modifying or removing identity allowlist rules automatically invalidates active opaque dashboard sessions and provider JWT tokens across all workers within the cache TTL | `docs/authentication.md`, `CHANGELOG.md` (v2.17.0) |
| External JWT role capping | Provider JWT authentication caps external API and chat clients to baseline `user` permissions, reserving administrative permissions exclusively for interactive dashboard sessions | `docs/authentication.md`, `CHANGELOG.md` (v2.17.1) |
| RBAC | Six built-in roles (e.g., admin, operator, auditor, analyst) covering eleven distinct permissions, so access can be scoped to what each role actually needs | `docs/rbac-architecture.md` |
| API key controls | Keys can be scoped to specific adapters, given daily/monthly usage quotas and rate limits, and restricted to specific users or email addresses | `docs/api-keys.md` |
| Per-key quotas & throttling | Each key's daily/monthly limit, remaining usage, and throttle priority can be viewed and edited from the admin panel, with one-click resets and a live usage report across all keys — no configuration-file editing required | `server/routes/admin/api_keys.py`, `server/services/api_key_service.py`, `server/admin/admin_panel/tabs/api-keys.js` |
| Identity blacklisting | Administrators can block users or accounts by pattern, immediately revoking their active sessions | `config/config.yaml` (`auth.blacklist`) |
| Audit logging | Records of user requests and administrative actions, stored in the organization's database of choice | `config/config.yaml` (`internal_services.audit`) |
| Secrets management | Credentials can be pulled from AWS Secrets Manager, Azure Key Vault, or GCP Secret Manager instead of being stored directly in configuration files | `config/config.yaml` (`secrets_management`) |
| Strict auth mode | An optional setting that requires every request to carry a verified user identity, not just a valid API key | `config/config.yaml` (`auth.require_authenticated_user`) |

All items in this table are included in ORBIT's open-source (Apache 2.0) distribution; there is no separate paid tier.

### 3.7 Safety, Moderation & Privacy

| Capability | Details | Source |
| :--- | :--- | :--- |
| Moderation backends | Configurable content-moderation models from OpenAI, Anthropic, and open-source options, to screen requests and responses | `config/moderators.yaml`, `config/guardrails.yaml` |
| Local PII detection | An on-premises model that detects personal information without sending any data outside the organization's network | `config/moderators.yaml` (`privacy_filter`) |
| PII detection via Presidio | Integration with Presidio, a self-hosted PII-detection tool supporting roughly 100 configurable data types (names, emails, etc.) with batch concurrency controls and serial fallback clamps | `config/moderators.yaml` (`presidio`), `docs/security/pii-moderation.md`, `CHANGELOG.md` (v2.16.0) |
| Network security controls | Standard web security protections (e.g., cross-origin restrictions, content-security policy) plus rate limiting and throttling to prevent abuse | `config/config.yaml` (`security`) |

### 3.8 Reliability & Performance

| Capability | Details | Source |
| :--- | :--- | :--- |
| Multi-worker scaling | The server can run multiple worker processes to handle higher request volume | `config/config.yaml` (`performance`) |
| Caching | Configurable caching (SQLite, Redis, or Memcached) to speed up repeated requests | `config/config.yaml` (`internal_services.cache`) |
| Response optimization | Compressed responses and efficient re-validation to reduce bandwidth | `config/config.yaml` (`performance.compression`, `performance.etag_caching`) |
| Cost/token tracking | Tracks token usage and estimated dollar cost for every request, broken down by provider and model. Also prices non-text usage (image, video, TTS, STT, OCR) by its own discrete unit (per image, per second, per character, etc.), not just tokens. | `config/pricing.yaml`, `docs/token-usage-and-cost-tracking.md` |
| Pricing rate table & staleness tracking | Costs are estimated from a local, editable rate table covering every configured provider/model, rather than pulled from a provider billing API. The table records when it was last updated and flags itself as stale in the admin panel after a configurable number of days, so outdated rates don't silently look current. Distinguishes a model priced at genuinely $0 (e.g. a local model) from one with no rate configured at all. | `config/pricing.yaml`, `server/services/pricing_service.py` |
| Cost dashboards | Per-request cost appears on individual audit records, and an aggregated Costs view breaks down total spend by model, provider, adapter, user, request type, and API key over a selectable time window | `docs/token-usage-and-cost-tracking.md` |
| Observability | Live telemetry, a metrics endpoint compatible with standard monitoring tools (Prometheus), and log rotation | `config/config.yaml` |

### 3.9 Conversational Behavior & Adapter Intelligence

| Capability | Details | Source |
| :--- | :--- | :--- |
| Skills (cross-adapter capability invocation) | One adapter can call on another adapter's capability mid-conversation — for example, a retrieval adapter triggering image generation — without the user switching adapters. Which skills an adapter can call is explicitly configured. | `docs/adapters/skills.md`, `server/services/chat_handlers/request_context_builder.py` |
| Automatic skill/intent routing | An optional setting that lets ORBIT infer which skill to invoke directly from a user's plain-language request, rather than requiring the request to name the skill explicitly. Off by default; enabled per adapter. | `docs/adapters/skills.md` (Automatic Intent Detection), `config/config.yaml` (`skill_routing`) |
| Autocomplete / query suggestions | Real-time input suggestions as a user types, drawn from example phrases configured for each adapter and skill | `docs/autocomplete-architecture.md`, `config/config.yaml` (`autocomplete`) |
| Dynamic conversation-history token budgeting | How much conversation history is kept is calculated automatically based on the model's context size, rather than a fixed number of messages — so older messages are trimmed only when needed, and the user is warned before that happens. | `docs/conversation_history.md` |
| Response feedback capture | Users can rate individual responses with a thumbs up/down and an optional comment. Ratings are tracked per adapter and per user, and shown in the admin panel as a satisfaction trend, a per-adapter ranking, and a list of recent negative feedback for follow-up — giving a direct signal for where responses need improvement. | `server/services/feedback_service.py`, `server/admin/admin_panel/tabs/feedback.js`, `docs/sqlite-schema.md` (`feedback` table) |
| Ungrounded document generation guard | Document and image generation skills refuse to synthesize filler content when requested data files are unavailable, requiring verified matching retrieved context or prior history | `CHANGELOG.md` (v2.16.0) |
| Skill-routed file retrieval fallback | Uploaded document and image files automatically route to document/media generation adapters even when intent skill routing swaps the active adapter mid-turn | `CHANGELOG.md` (v2.16.0) |
| Skill-aware autocomplete scoping | Autocomplete endpoint (`GET /v1/autocomplete`) supports `include_skill_examples` toggling to isolate base query suggestions from thread-specific skill triggers | `CHANGELOG.md` (v2.16.0) |

### 3.10 Reference Client: OrbitChat

ORBIT ships a standalone chat client, distributed separately as an npm package, that connects to any ORBIT deployment. It is not part of the ORBIT server itself.

| Capability | Details | Source |
| :--- | :--- | :--- |
| Distribution | Installable as a standard package, runnable as either a command-line tool or a background service | `clients/orbitchat/README.md` |
| Feature set | Streaming responses, file upload, conversation threading, voice input/output, autocomplete, feedback capture, optional login via Auth0 | `clients/orbitchat/README.md` |
| Key-handling model | The end user's browser never sees the real backend API key — the request identifies which adapter to use, and a server-side component resolves that to the correct key before forwarding it | `clients/orbitchat/README.md` (Architecture, Security) |
| API-only mode | The same server-side component can run as a pure API layer without the bundled chat UI, for organizations building their own custom frontend | `clients/orbitchat/README.md` (API-Only Mode) |
| Configuration | Branding, available adapters, and feature toggles are set in a single configuration file per deployment | `clients/orbitchat/README.md` (Configuring Adapters) |

This positions OrbitChat as an optional, separately maintained reference client rather than a mandatory component — an organization can use ORBIT's API directly, build a custom frontend against the same proxy contract, or adopt OrbitChat as-is.

### 3.11 Test Coverage & Performance Testing

| Capability | Details | Source |
| :--- | :--- | :--- |
| Automated test suite | Roughly 3,900 automated tests across 214 test files, covering every major subsystem (adapters, authentication, data sources, inference, messaging, admin functions, and more) | `server/tests/` |
| Load testing | Simulated traffic tools that model realistic usage patterns, from everyday load to stress and endurance scenarios | `server/tests/perf/README.md`, `server/tests/perf/locustfile.py` |
| Custom load/scenario testing | Additional tooling for burst and ramping traffic patterns, and for simulating many concurrent tenants/API keys at once to measure latency and success rates per adapter | `server/tests/perf/advanced_performance_test.py`, `server/tests/perf/multi_user_load_test.py` |
| Rate-limit/throttle verification | Dedicated tooling that verifies the rate-limiting and throttling systems behave correctly under a variety of traffic patterns | `server/tests/perf/rate_limit_simulation.py` |
| Memory-leak profiling | A dedicated tool that runs load against the server while profiling memory allocations, to catch memory leaks before they reach production | `server/tests/perf/memray_leak_test.py` |

The presence of dedicated fault-tolerance, load, rate-limit, and memory-leak testing tools indicates that performance and stability testing is treated as a first-class part of the test suite, not limited to basic functional checks.

### 3.12 Administration & Management UI/CLI

ORBIT includes a web-based admin panel and a companion command-line tool (both part of the server distribution, not separate products) for day-to-day management, gated by the RBAC permissions described in §3.6.

| Capability | Details | Source |
| :--- | :--- | :--- |
| No-code adapter creation | New adapters can be created, edited, exported, and imported directly from the admin panel through a form — no manual configuration-file editing required — and changes apply immediately without restarting the server | `CHANGELOG.md` (v2.14.0, v2.15.2, v2.15.7) |
| MCP server management | External tool connections (MCP servers) can be added, tested, and removed from the admin panel, with live status checks — no config-file editing or restart required | `CHANGELOG.md` (v2.14.0–v2.15.7), `docs/mcp_protocol.md` |
| MCP Tool Skills management | Dedicated admin panel tab (`/admin/skills`) for creating, editing, and deleting database-backed MCP tool playbooks with live hot-reload across workers | `docs/mcp_protocol.md`, `CHANGELOG.md` |
| Retrieval Misses triage view | Admin panel Adapters tab view displaying low-confidence intent retrieval attempts, candidate match scores, and diagnostic re-tests | `CHANGELOG.md` (v2.16.0) |
| Identity Allowlist management | Web UI tab and CLI tool (`orbit user allowlist`) for managing allowlist rules, seed workflows, and access control modes | `docs/authentication.md`, `CHANGELOG.md` (v2.17.0) |
| Admin CLI (`orbit`) | A command-line tool that covers the same administrative tasks as the web panel — starting/stopping the server, managing users and API keys, allowlists, and reloading configuration — for scripting, automation, and CI/CD use | `bin/orbit.py`, `bin/orbit.sh` |
| Adapter SDK CLI (`adapter-sdk`) | A companion command-line tool for generating adapter configuration files, useful for scripted or bulk adapter setup | `bin/adapter-sdk.sh` |
| Cost & audit dashboards | Aggregated spending breakdowns by API key, adapter, provider, user, and request type, alongside the audit log viewer described in §3.6 | `CHANGELOG.md` (v2.15.8–v2.16.0), `docs/token-usage-and-cost-tracking.md` |

### 3.13 Onboarding & Documentation

| Resource | Details | Source |
| :--- | :--- | :--- |
| Guided setup | An interactive installer (`install/setup.sh`, `install/wizard.py`) with configurable profiles, plus a prebuilt Docker path (`docker-compose.yml`, published images for Ollama/OpenAI/Gemini configurations) that starts a running instance with no manual configuration | `install/`, `docker/README.md` |
| Step-by-step tutorial series | A `docs/tutorial.md` entry point linking a sequenced set of guides — first chat, chat with files, SQL/MongoDB/DuckDB querying, MCP tool calling, auto skill routing, creating API keys, admin panel tour, and troubleshooting | `docs/tutorial.md`, `docs/tutorial/` |
| Full documentation index | A categorized index (`docs/README.md`) covering architecture, adapters, data sources, security, and advanced/protocol topics, in addition to this capability matrix | `docs/README.md` |
| Runnable examples | Client code samples for the OpenAI-compatible API (Python/Node.js, including streaming) and a sample MCP server for hands-on testing | `examples/` |

## 4. Platform-Specific Notes

### 4.1 LiteLLM

LiteLLM's core function is LLM API proxying — request/response translation, load balancing, and spend tracking across providers. It does not include built-in connectors to SQL/vector/NoSQL data sources; retrieval is typically implemented in a separate pipeline outside LiteLLM itself.

LiteLLM is distributed under an open-core model. Per LiteLLM's published pricing page ([litellm.ai/pricing](https://www.litellm.ai/pricing)), the following are listed under a separately sales-quoted "Enterprise" tier rather than the open-source tier: SSO + SCIM, OIDC/JWT authentication, audit logs, secrets-manager integration with key rotation, org/team administration, a multi-region control plane, 24/7 support with SLAs, and self-hosted/air-gapped deployment. Evaluators comparing total cost of ownership should confirm current tier boundaries directly with LiteLLM, as pricing pages are subject to change.

ORBIT includes equivalents of the items listed above — OIDC/SSO, audit logging, secrets-manager integration, RBAC-based access administration, and self-hosted/air-gapped deployment — in its single Apache 2.0 distribution.

### 4.2 Open WebUI

Open WebUI is a chat frontend. It connects to Ollama natively and to any OpenAI-compatible endpoint (which can include self-hosted llama.cpp, vLLM, or LM Studio servers exposing that API). Per its own documentation ([docs.openwebui.com/features](https://docs.openwebui.com/features/)), its retrieval layer is substantial for a chat frontend — 13 supported vector databases, hybrid (keyword + vector) search with cross-encoder reranking, and multiple document-extraction engines — though it does not include native connectors to SQL or NoSQL databases as retrieval sources the way ORBIT's intent-based retrieval does.

For organizations evaluating a chat frontend specifically, ORBIT's comparable offering is OrbitChat (§3.10) — a separately distributed reference client rather than a component of the ORBIT server itself. OrbitChat and Open WebUI are both frontends that can be pointed at the same class of backend model APIs; the difference in this comparison is in what sits behind them — ORBIT's data-source and governance layer versus a backend the deploying organization assembles separately.

ORBIT is a backend gateway rather than a chat frontend: it provides connection pooling for SQL databases, RabbitMQ-based async messaging, and multi-worker process scaling, none of which are part of Open WebUI's scope.

Regarding cost visibility: per Open WebUI's own documentation ([docs.openwebui.com/features/administration/analytics](https://docs.openwebui.com/features/administration/analytics/)), its open-source Analytics dashboard tracks token usage per message, model, and user, but does not calculate a dollar cost automatically — it documents the formula for an administrator to multiply tracked token counts by their provider's price by hand. This differs from ORBIT's and LiteLLM's approach of resolving an estimated dollar cost automatically from a maintained pricing table.

Regarding licensing: per Open WebUI's own documentation ([docs.openwebui.com/license](https://docs.openwebui.com/license/)), versions through 0.6.5 are BSD-3-Clause (fully permissive). From v0.6.6 onward, the license adds a branding-protection clause requiring "Open WebUI" branding to remain visible unless the deployment has 50 or fewer users in a 30-day period, the user is a substantive contributor with written permission, or the user holds an enterprise license granting branding rights. Open WebUI's own documentation states this version of the license is not OSI-approved as "open source" due to that clause; source code remains publicly available regardless. A separate commercial/enterprise license is offered for white-labeling. Evaluators should confirm the license version in use, since organizations forking from v0.6.5 or earlier are not subject to the branding clause.

### 4.3 Commercial Managed Platforms (AWS Bedrock, Azure AI, Google Vertex AI)

These platforms provide managed model hosting and, in most cases, managed retrieval/vector-search services (e.g., AWS OpenSearch, Azure AI Search) tied to the vendor's own cloud infrastructure. They require outbound connectivity to the vendor's services and generally price on a per-token or per-request basis.

ORBIT can be deployed on the same cloud infrastructure or fully offline, and connects to databases the organization already operates without requiring data migration into a vendor-managed store. This is a deployment-model difference rather than a feature-completeness comparison — commercial platforms offer operational guarantees (SLAs, managed scaling, vendor support) that a self-operated deployment does not provide by default.
