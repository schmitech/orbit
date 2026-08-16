# ORBIT
### Open Retrieval-Based Inference Toolkit

**A self-hosted AI gateway for production RAG — one governed endpoint for every model, data source, and agent tool in your organization.**

---

## Background

Every organization building AI features today faces the same problem: connecting large language models to private data and internal tools means stitching together retrieval pipelines, authentication, rate limiting, cost tracking, and failover logic — separately, for every model provider and every data source. That integration work is repeated at every company, rarely reused, and expensive to maintain as providers and requirements change.

ORBIT is an open-source, self-hosted AI gateway that solves this once. It exposes a single OpenAI-compatible API that routes requests to 41+ LLM providers and models, retrieves context from SQL, NoSQL, vector, file, and API data sources, and calls external tools through open agent protocols — all governed by built-in authentication, role-based access control, rate limiting, and audit logging. Applications integrate with ORBIT once and gain access to any model or data source it's configured for, without rewriting integration code each time a provider or backend changes.

ORBIT is Apache 2.0 licensed, actively maintained, and deployable on-premises, in a private cloud, or fully offline with local models — giving organizations control over cost, data residency, and vendor exposure that closed, hosted AI platforms cannot offer.

---

## The Challenge

Organizations adopting AI internally typically hit the same wall after an initial prototype succeeds:

- **Fragmented integrations.** Each new model provider or data source requires its own SDK, authentication flow, and error handling, multiplying maintenance work over time.
- **Vendor lock-in.** Building directly against one provider's API makes it costly to switch models, negotiate pricing, or run a local model for sensitive workloads.
- **Ungoverned access.** Prototypes rarely include the access control, quotas, moderation, and audit trails that production and compliance requirements demand — these get bolted on later, expensively.
- **Retrieval complexity.** Translating natural-language questions into safe, correct queries against SQL databases, vector stores, or APIs is a significant engineering effort in its own right, and it must be re-solved for every new data source.
- **No cost visibility.** Token usage and inference spend are difficult to track per user, team, or feature without dedicated instrumentation.

Solving each of these individually before shipping an AI feature slows time-to-production and creates long-term maintenance burden.

---

## What ORBIT Is

ORBIT sits between your applications and the models, data, and tools they need. Applications talk to ORBIT once, through a standard OpenAI-compatible `/v1/chat/completions` endpoint (plus native support for MCP, A2A, and message-queue protocols). ORBIT then:

1. Authenticates and authorizes the request (API key, RBAC, or SSO).
2. Selects the right **adapter** — a YAML-configured definition of how to handle the request: which model to call, which data source to query, which tools are available.
3. Retrieves relevant context (files, database rows, API responses, or vector search results) if the adapter requires it.
4. Sends the enriched prompt to the configured model — local or cloud — and returns a governed, observable response.

Every adapter is defined entirely in YAML under `config/adapters/`, without touching server code. Adding a new database, vector store, model provider, or MCP tool server is a configuration change, not a development project — and adapters can be hot-reloaded without restarting the server.

---

## Core Capabilities

| Capability | What's Included |
| :--- | :--- |
| **Model Gateway** | 41 configured inference backends and providers — including OpenAI, Anthropic, Gemini, AWS Bedrock, Azure OpenAI, and local runtimes (Ollama, llama.cpp, vLLM) — behind one OpenAI-compatible API, with per-key model routing, retries, and automatic fallbacks. |
| **Retrieval** | Natural-language querying across SQL (Postgres, MySQL, SQL Server, Oracle, SQLite), MongoDB, Elasticsearch, vector stores (Chroma, Qdrant, Pinecone, Milvus, Weaviate, Redis), REST/GraphQL APIs, web search, and uploaded files — including composite adapters that automatically route a query to the best-matching source across multiple backends. |
| **Agents & Protocols** | Model Context Protocol (MCP) — both as a client calling external MCP tool servers (filesystem, Slack, Postgres, GitHub, Jira, etc.) and as a server exposing ORBIT's own API as MCP tools; Google's Agent-to-Agent (A2A) protocol for interoperating with other agent frameworks; bounded multi-step tool-use loops; asynchronous processing over RabbitMQ. |
| **Media** | Generation and handling of images, video, speech (STT/TTS, including real-time speech-to-speech with interrupt/barge-in support), PDFs, Word, Excel, PowerPoint, CSV, and Markdown. |
| **Security** | API key management, fine-grained role-based access control, SSO via Microsoft Entra ID and Auth0 (extensible to any OIDC provider), content moderation, file encryption, and integration with cloud secret managers. |
| **Operations** | Admin UI, health checks and circuit breakers, metrics, audit logs, per-request token and estimated-cost tracking with spend analytics, datasource connection pooling, and hot adapter reloads. |

---

## OrbitChat: A Ready-Made Front End

A gateway is only useful if someone can talk to it — and building a production-grade chat UI (streaming, file uploads, conversation threading, auth, voice) is itself a significant project. ORBIT ships one, so teams don't have to build it.

**OrbitChat** is a standalone chat client — installable as a single npm package and runnable as a CLI — that connects to any ORBIT deployment out of the box:

```bash
npm install -g orbitchat
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' orbitchat
```

It includes everything a client-facing or internal chat interface needs: streaming responses, file upload and multi-file conversations, conversation threading, voice input/output, autocomplete, feedback capture, and optional Auth0-based login — all themeable and configurable per deployment through a single `orbitchat.yaml` file.

Critically, **OrbitChat never exposes API keys to the browser.** Every request from the frontend carries an `X-Adapter-Name` header rather than a credential; a built-in Express proxy layer resolves that name to the real backend API key and forwards the request server-side. This means OrbitChat can be handed to end users, embedded in a client-facing product, or deployed multi-tenant, without ever putting a secret at risk in client-side code.

For teams that want their own frontend instead, OrbitChat can run in `--api-only` mode — the same secret-guarding proxy layer, with no UI — exposing a simple documented API contract (`GET /api/adapters` for discovery, `X-Adapter-Name`-scoped calls for chat, files, and autocomplete) that any custom frontend can build against.

The result: teams can go from an ORBIT deployment to a working, brandable chat product in minutes, and only build custom UI when their product genuinely needs something OrbitChat doesn't already provide.

---

## Enterprise-Grade Security & Governance

ORBIT is built to meet production and compliance requirements out of the box, not as an afterthought:

- **Strong authentication.** Passwords are hashed with PBKDF2-SHA256 at 600,000 iterations — exceeding OWASP's 2023 minimum guidance and aligned with NIST SP 800-63B. Sessions use 256-bit cryptographically secure opaque bearer tokens with immediate revocation, not wait-for-expiry.
- **Federated identity.** Native single sign-on via Microsoft Entra ID and Auth0 (OIDC, RS256-verified JWTs) with just-in-time user provisioning, and straightforward extension to any other OIDC provider (Okta, Keycloak, Google) through configuration alone.
- **Fine-grained RBAC.** Six built-in roles — admin, operator, auditor, analyst, user-manager, and user — with permissions computed as a union across roles, so access can be scoped precisely (for example, an operator can manage day-to-day operations without being able to read user conversations or the audit trail). Sensitive routes like conversation history require bearer-token authentication and cannot be accessed with an API key alone.
- **Abuse mitigation and rate limiting.** Two-layer traffic control — progressive soft throttling plus hard 429 rate limits — applied simultaneously by IP and API key to block both "one IP, many keys" and "one key, many IPs" abuse patterns. Per-key daily and monthly quotas support tiered service levels for different clients.
- **Full auditability.** Every request is logged with per-request token usage and estimated cost, viewable in an admin cost dashboard broken down by model, provider, adapter, and user — supporting chargeback, budgeting, and compliance reporting.
- **Fault isolation.** A per-adapter circuit-breaker pattern (closed/open/half-open with exponential backoff) prevents a failing data source or model provider from taking down the whole system, with health and observability endpoints for production monitoring.

---

## Deployment Flexibility

ORBIT runs wherever your data governance requirements demand:

- **Fully local and offline** — pair ORBIT with local models (Ollama, llama.cpp, vLLM) for zero-API-cost, air-gapped deployments where data never leaves the network.
- **Cloud-hosted models** — route to OpenAI, Anthropic, Gemini, AWS Bedrock, or Azure OpenAI when cloud model quality or scale is preferred.
- **Hybrid** — mix local and cloud models per adapter, per use case, or per client, without changing how applications integrate with ORBIT.
- **Flexible installation** — deploy from a stable release tarball, via Docker (with pre-built images for Ollama, OpenAI, or Gemini configurations), or build from source; Linux, macOS, and Windows are all supported.

Because model and data-source selection lives entirely in configuration, switching providers, adding a data source, or moving from a cloud pilot to an on-premises production deployment does not require re-architecting the applications built on top of ORBIT.

---

## Representative Use Cases

| Goal | How ORBIT Handles It |
| :--- | :--- |
| **Chat with private documents** | Upload PDFs, office documents, spreadsheets, images, and audio; retrieve relevant context across a multi-turn conversation. |
| **Query databases in natural language, in any language** | Generate and execute safe, parameterized queries against SQL, MongoDB, Elasticsearch, or multiple sources at once via composite adapters. |
| **Build tool-using agents** | Give models scoped, bounded access to MCP servers (filesystem, Slack, GitHub, Jira, internal APIs) without adopting a separate agent framework. |
| **Offer one governed AI endpoint across teams** | Route local and cloud models with per-key access, quotas, moderation, fallbacks, metrics, and full auditability from a single deployment. |
| **Deploy a grounded voice assistant** | Real-time, interruptible speech-to-speech interaction grounded in SQL databases, APIs, or internal data lakes. |
| **Interoperate with other agent systems** | Act as a discoverable peer agent via the A2A protocol, or expose ORBIT's own capabilities as MCP tools to other agents and IDEs. |

---

## Why ORBIT

- **No vendor lock-in.** One integration point works across 41+ model providers and every major data source category — switch or add providers through configuration, not code.
- **Open source, Apache 2.0.** Full transparency into how requests are handled, retrieved from, and governed — no black-box AI infrastructure.
- **Actively maintained.** Regular releases, a public changelog, and an open contribution process.
- **Production-ready from day one.** Authentication, RBAC, rate limiting, cost tracking, and fault tolerance are built in, not bolted on after a prototype succeeds.
- **Faster time-to-production.** Teams spend their engineering effort on their application and their data, not on rebuilding AI infrastructure plumbing.