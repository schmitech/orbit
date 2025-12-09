# ORBIT Documentation

Welcome to the official documentation for **ORBIT** (Open Retrieval-Based Inference Toolkit) — a unified, self-hosted AI inference platform that connects your AI models to your private data sources.

<p align="center">
  <a href="https://github.com/schmitech/orbit">GitHub</a> •
  <a href="https://schmitech.ai/en">Commercial Support</a> •
  <a href="https://github.com/schmitech/orbit/issues">Report an Issue</a>
</p>

---

## 📚 Table of Contents

- [ORBIT Documentation](#orbit-documentation)
  - [📚 Table of Contents](#-table-of-contents)
  - [🚀 Getting Started](#-getting-started)
  - [🧠 Core Concepts](#-core-concepts)
    - [Architecture](#architecture)
    - [Adapters \& Retrievers](#adapters--retrievers)
  - [⚙️ Configuration](#️-configuration)
  - [🗄️ Data Sources \& Integrations](#️-data-sources--integrations)
    - [Databases](#databases)
    - [APIs \& External Services](#apis--external-services)
    - [Files \& Documents](#files--documents)
  - [🔐 Security \& Authentication](#-security--authentication)
  - [🔧 Advanced Topics](#-advanced-topics)
    - [Local Model Servers](#local-model-servers)
    - [Performance \& Reliability](#performance--reliability)
    - [Protocols \& Extensions](#protocols--extensions)
  - [🛠️ Development](#️-development)
  - [🏢 Commercial Support](#-commercial-support)
    - [Services Available](#services-available)
    - [Support Plans](#support-plans)
  - [📄 License](#-license)

---

## 🚀 Getting Started

New to ORBIT? Start here.

| Guide | Description |
|-------|-------------|
| [Quick Start](../README.md#-quick-start) | Get ORBIT running in minutes with Docker or manual installation |
| [Server Setup](server.md) | Detailed server configuration and deployment options |
| [Configuration Guide](configuration.md) | Complete configuration reference |

---

## 🧠 Core Concepts

Understand how ORBIT works.

### Architecture

| Guide | Description |
|-------|-------------|
| [Adapters Overview](adapters/overview.md) | How adapters connect AI models to data sources |
| [Pipeline Architecture](pipeline-inference-architecture.md) | Request flow and processing pipeline |
| [Fault Tolerance](fault-tolerance/fault-tolerance-architecture.md) | Circuit breakers, retries, and high availability |

### Adapters & Retrievers

| Guide | Description |
|-------|-------------|
| [Adapter Configuration](adapters/configuration.md) | Setting up and configuring adapters |
| [QA Adapters](adapters/qa-adapters.md) | Question-answering with SQL and vector stores |
| [Intent Adapters](adapters/intent-adapters.md) | Natural language to SQL/API query generation |
| [File Adapter](adapters/file-adapter.md) | Document upload and processing |
| [Passthrough Adapter](adapters/passthrough.md) | Direct conversational AI without retrieval |

---

## ⚙️ Configuration

Customize ORBIT for your environment.

| Guide | Description |
|-------|-------------|
| [Configuration Reference](configuration.md) | All configuration options explained |
| [Environment Variables](configuration.md#environment-variables) | Required and optional environment settings |
| [Inference Providers](configuration.md#inference-providers) | Configure OpenAI, Anthropic, Ollama, llama.cpp, and more |
| [System Prompts](chat_service_system_prompts.md) | Customize AI behavior with system prompts |

---

## 🗄️ Data Sources & Integrations

Connect ORBIT to your data.

### Databases

| Guide | Description |
|-------|-------------|
| [SQL Databases](adapters/sql-retriever-architecture.md) | PostgreSQL, MySQL, SQLite, DuckDB, Oracle, SQL Server |
| [MongoDB](mongodb-installation-linux.md) | NoSQL document database setup |
| [Vector Stores](vector_store_integration_guide.md) | Chroma, Qdrant, Pinecone, Milvus integration |
| [Chroma Setup](chroma-setup.md) | Detailed Chroma vector database configuration |
| [Elasticsearch](adapters/intent-adapters.md#elasticsearch) | Full-text search integration |

### APIs & External Services

| Guide | Description |
|-------|-------------|
| [REST APIs](adapters/intent-adapters.md#http-apis) | Connect to any JSON REST API |
| [GraphQL](adapters/intent-adapters.md#graphql) | Query GraphQL endpoints with natural language |

### Files & Documents

| Guide | Description |
|-------|-------------|
| [File Processing](adapters/file-adapter.md) | PDF, DOCX, CSV, images, audio support |
| [Chunking Strategies](chunking/) | Document chunking and embedding strategies |

---

## 🔐 Security & Authentication

Secure your ORBIT deployment.

| Guide | Description |
|-------|-------------|
| [Authentication](authentication.md) | User authentication and session management |
| [API Keys](api-keys.md) | Create and manage API keys |
| [Role-Based Access Control](authentication.md#rbac) | Configure user roles and permissions |
| [Content Moderation](llm-guard-service.md) | LLM Guard for content safety |

---

## 🔧 Advanced Topics

For power users and contributors.

### Local Model Servers

| Guide | Description |
|-------|-------------|
| [llama.cpp Server](llama-cpp-server-guide.md) | Run GGUF models locally |
| [Shimmy Server](shimmy-setup-guide.md) | Lightweight OpenAI-compatible inference |
| [Ollama Integration](configuration.md#ollama) | Using Ollama for local inference |

### Performance & Reliability

| Guide | Description |
|-------|-------------|
| [Fault Tolerance Architecture](fault-tolerance/fault-tolerance-architecture.md) | System resilience overview |
| [Circuit Breaker Patterns](fault-tolerance/circuit-breaker-patterns.md) | Failure handling patterns |
| [Troubleshooting](fault-tolerance/fault-tolerance-troubleshooting.md) | Debug common issues |
| [Performance Tuning](performance-enhancements.md) | Optimize for production workloads |
| [Memory Management](memory_leak_prevention.md) | Prevent memory leaks |

### Protocols & Extensions

| Guide | Description |
|-------|-------------|
| [MCP Protocol](mcp_protocol.md) | Model Context Protocol integration |
| [Reranker Architecture](reranker-architecture.md) | Document reranking for improved accuracy |
| [Language Detection](language-detection-architecture.md) | Multilingual support |

---

## 🛠️ Development

Contribute to ORBIT or extend its capabilities.

| Resource | Description |
|----------|-------------|
| [Contributing Guide](../CONTRIBUTING.md) | How to contribute to ORBIT |
| [Development Roadmap](roadmap/README.md) | Planned features and architecture designs |
| [Code of Conduct](../CODE_OF_CONDUCT.md) | Community guidelines |
| [Changelog](../CHANGELOG.md) | Release history and updates |

---

## 🏢 Commercial Support

Need enterprise-grade support? **[Schmitech](https://schmitech.ai/en)** is the official commercial support provider for ORBIT.

### Services Available

- **Managed Hosting** — Fully managed deployments with SLA guarantees
- **Custom Development** — Custom adapters, integrations, and model tuning
- **Enterprise Integration** — Connect to your databases, APIs, and SSO
- **Installation & Setup** — On-premise and cloud deployment assistance
- **Training & Workshops** — Hands-on training for your team
- **Dedicated Support** — Priority response and dedicated support engineer

### Support Plans

| Plan | Best For | Includes |
|------|----------|----------|
| **Community** | Developers & small teams | GitHub Issues, public docs |
| **Professional** | Growing organizations | Email support, Slack, quarterly reviews |
| **Enterprise** | Mission-critical deployments | 4-hour SLA, dedicated engineer, 24/7 support |

👉 **[Contact Schmitech](https://schmitech.ai/en/contact)** to discuss your requirements.

---

## 📄 License

ORBIT is open source under the [Apache 2.0 License](../LICENSE).

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://schmitech.ai">Schmitech</a></sub>
</p>
