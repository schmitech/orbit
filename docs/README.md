# ORBIT Documentation

Welcome to the official documentation for **ORBIT** (Open Retrieval-Based Inference Toolkit) — a unified, self-hosted AI inference platform that connects your AI models to your private data sources.

<p align="center">
  <a href="https://github.com/schmitech/orbit">GitHub</a> •
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
  - [🎤 Audio \& Multimodal](#-audio--multimodal)
  - [🔐 Security \& Authentication](#-security--authentication)
  - [🔧 Advanced Topics](#-advanced-topics)
    - [Local Model Servers](#local-model-servers)
    - [Performance \& Reliability](#performance--reliability)
    - [Protocols \& Extensions](#protocols--extensions)
  - [🛠️ Development](#️-development)
  - [🏢 Support \& Community](#-support--community)
  - [📄 License](#-license)

---

## 🚀 Getting Started

New to ORBIT? Start here.

| Guide | Description |
|-------|-------------|
| [Quick Start](../README.md#-start-in-minutes) | Get ORBIT running in minutes with Docker or manual installation |
| [Tutorial](tutorial.md) | Step-by-step guide to chat with your data |
| [Server Setup](server.md) | Detailed server configuration and deployment options |
| [Configuration Guide](configuration.md) | Complete configuration reference |
| [ORBIT and Open WebUI](orbit-vs-openwebui.md) | Architectural comparison |

---

## 🧠 Core Concepts

Understand how ORBIT works.

### Architecture

| Guide | Description |
|-------|-------------|
| [Adapters Overview](adapters/adapters.md) | How adapters connect AI models to data sources |
| [Pipeline Architecture](pipeline-inference-architecture.md) | Request flow and processing pipeline |
| [Fault Tolerance](fault-tolerance/fault-tolerance-architecture.md) | Circuit breakers, retries, and high availability |

### Adapters & Retrievers

| Guide | Description |
|-------|-------------|
| [Adapter Configuration](adapters/adapter-configuration.md) | Setting up and configuring adapters |
| [Adapter Capabilities](adapters/capabilities/capability_for_all_adapters.md) | Capability system for adapter behavior control |
| [QA Adapters](adapters/adapters.md) | Question-answering with SQL and vector stores |
| [Intent Adapters](intent-sql-rag-system.md) | Natural language to SQL/API query generation |
| [Composite Intent Retriever](adapters/composite-intent-retriever.md) | Route queries across multiple data sources |
| [Intent Agent Retriever](adapters/intent-agent-retriever.md) | Function calling and tool execution capabilities |
| [File Adapter](file-adapter-guide.md) | Document upload and processing |
| [Passthrough Adapter](multimodal-conversational-adapter.md) | Direct conversational AI without retrieval |
| [Skills](adapters/skills.md) | Cross-adapter capabilities (image generation and more) |

---

## ⚙️ Configuration

Customize ORBIT for your environment.

| Guide | Description |
|-------|-------------|
| [Configuration Reference](configuration.md) | All configuration options explained |
| [Environment Variables](configuration.md#environment-variables) | Required and optional environment settings |
| [Inference Providers](configuration.md#inference-providers) | Configure OpenAI, Anthropic, Ollama, llama.cpp, and more |
| [System Prompts](server.md#system-prompts) | Customize AI behavior with system prompts |

---

## 🗄️ Data Sources & Integrations

Connect ORBIT to your data.

### Databases

| Guide | Description |
|-------|-------------|
| [SQL Databases](sql-retriever-architecture.md) | PostgreSQL, MySQL, SQLite, DuckDB, Oracle, SQL Server |
| [MongoDB](mongodb-installation-linux.md) | NoSQL document database setup |
| [Vector Stores](vector_store_integration_guide.md) | Chroma, Qdrant, Pinecone, Milvus integration |
| [Vector Retriever Architecture](vector-retriever-architecture.md) | Technical deep dive into vector retriever implementation |
| [Chroma Setup](chroma-setup.md) | Detailed Chroma vector database configuration |
| [Elasticsearch](intent-sql-rag-system.md) | Full-text search integration |

### APIs & External Services

| Guide | Description |
|-------|-------------|
| [REST APIs](intent-sql-rag-system.md) | Connect to any JSON REST API |
| [GraphQL](intent-sql-rag-system.md) | Query GraphQL endpoints with natural language |

### Files & Documents

| Guide | Description |
|-------|-------------|
| [File Processing](file-adapter-guide.md) | PDF, DOCX, CSV, images, audio support |
| [AI/LLM Document OCR](ai-document-ocr.md) | LLM-based OCR for scanned PDFs and images (Mistral / vision providers) |
| [Chunking Architecture](chunking/chunking-architecture.md) | Document chunking and embedding strategies |
| [Chunking Safeguards](chunking/chunking_safeguards.md) | Safety considerations for document processing |

---

## 🎤 Audio & Multimodal

Audio processing and multimodal capabilities.

| Guide | Description |
|-------|-------------|
| [Audio Services](audio/audio-services-adapter-guide.md) | TTS, STT, transcription, and translation integration |
| [Audio Client Integration](audio/audio-client-integration-summary.md) | Client-side audio integration patterns |
| [Whisper Integration](audio/whisper/whisper-integration-guide.md) | OpenAI Whisper for speech recognition |
| [Whisper Setup](audio/whisper/whisper-setup-guide.md) | Configure Whisper for audio processing |
| [Whisper Quick Reference](audio/whisper/whisper-quick-reference.md) | Quick reference for Whisper usage |

---

## 🔐 Security & Authentication

Secure your ORBIT deployment.

| Guide | Description |
|-------|-------------|
| [Authentication](authentication.md) | User authentication and session management |
| [API Keys](api-keys.md) | Create and manage API keys |
| [Role-Based Access Control](authentication.md#rbac) | Configure user roles and permissions |

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
| [Rate Limiting](rate-limiting-architecture.md) | Rate limiting and throttling architecture |
| [Datasource Pooling](datasource-pooling.md) | Connection pooling for data sources |
| [PostgreSQL Startup Lock Troubleshooting](postgres-startup-lock-troubleshooting.md) | Diagnose startup hangs/statement timeouts against a Postgres backend |

### Protocols & Extensions

| Guide | Description |
|-------|-------------|
| [MCP Protocol](orbit-flow-diagrams.md) | Model Context Protocol integration |
| [A2A Protocol](a2a-protocol.md) | Agent-to-Agent protocol for peer AI agent orchestration |
| [Reranker Architecture](reranker-architecture.md) | Document reranking for improved accuracy |
| [Language Detection](language-detection-architecture.md) | Multilingual support |
| [Conversation Threading](conversation-threading-architecture.md) | Sub-conversations and cached dataset reuse |
| [Autocomplete](autocomplete-architecture.md) | Query suggestions from intent templates |
| [Conversation History](conversation_history.md) | Chat history management |
| [Request Context Propagation](request_context_propagation.md) | Context handling across the pipeline |

---

## 🛠️ Development

Contribute to ORBIT or extend its capabilities.

| Resource | Description |
|----------|-------------|
| [Contributing Guide](../CONTRIBUTING.md) | How to contribute to ORBIT |
| [Testing PRs Locally](testing-prs-locally.md) | Guide for testing pull requests |
| [Template Diagnostics](template-diagnostics.md) | Test intent templates without the full LLM pipeline |
| [SQLite Schema](sqlite-schema.md) | Database schema reference |
| [Code of Conduct](../CODE_OF_CONDUCT.md) | Community guidelines |
| [Changelog](../CHANGELOG.md) | Release history and updates |

---

## 🏢 Support & Community

Need help getting started?
- **[Step-by-Step Tutorial](tutorial.md)** — Learn how to connect your data.
- **[GitHub Discussions](https://github.com/schmitech/orbit/discussions)** — Get help from the community.

---

## 📄 License

ORBIT is open source under the [Apache 2.0 License](../LICENSE).
