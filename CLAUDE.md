# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ORBIT** (Open Retrieval-Based Inference Toolkit) is a self-hosted AI gateway for production RAG (Retrieval-Augmented Generation). It exposes an OpenAI-compatible API that routes requests to 37+ LLM providers, performs intent-based SQL/NoSQL/vector retrieval, and includes enterprise controls (RBAC, audit logs, rate limiting, circuit breakers).

## Commands

### Setup
```bash
./install/setup.sh --profile default           # Basic install
./install/setup.sh --profile all               # All dependencies
./install/setup.sh --download-gguf [model]     # Download a GGUF model
```

### Running the Server
```bash
python3 server/main.py                         # Direct launch
python3 server/main.py --config /path/to.yaml  # Custom config
./bin/orbit.sh start                           # Via shell wrapper
docker compose up -d                           # From docker/ directory
```

### Testing
```bash
# From repo root, using the venv python:
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python -m pytest server/tests/

# Run a single test file:
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python -m pytest server/tests/test_foo.py

# Run by marker:
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python -m pytest server/tests/ -m unit
```

Pytest markers: `unit`, `integration`, `slow`. Python imports resolve from `server/` — tests must be run with `server/` as the working directory or the venv python from the repo root.

### Linting
```bash
ruff check .        # Check all Python files
ruff check server/  # Check server code only
```

Config: `ruff.toml` — line length 120, target Python 3.11+.

## Architecture

### Entry Points
- `server/main.py` — FastAPI app factory
- `server/inference_server.py` — Server initialization, config loading, service wiring, lifespan manager

### Service Layer (`server/services/`)
Services are initialized once via a service factory and injected via FastAPI dependency injection. Key services:
- `ChatService` — message routing, streaming
- `RetrievalService` — RAG and document retrieval
- `APIKeyService` — authentication and quota management
- `GuardrailService` — content moderation
- `CacheService` — retrieval result caching
- `ChatHistoryService` — conversation persistence

### Adapter System (`server/adapters/`)
Adapters are the core abstraction — they define how a user query is handled end-to-end:
- **Intent adapters** — Map natural language to SQL/NoSQL queries via template matching
- **Composite adapters** — Fan out across multiple sources and merge results
- **Passthrough adapters** — Route directly to an LLM provider
- **File/QA adapters** — RAG over uploaded documents

Adapter capabilities are declared in `server/adapters/capabilities.py` (`AdapterCapabilities`, `AdapterCapabilityRegistry`).

Adapter configs live in `config/adapters/*.yaml`.

### Retrieval Pipeline (`server/retrievers/`)
Intent-SQL RAG system: a user query is matched against named intent templates, which generate SQL/NoSQL queries. Results are injected as context into the LLM prompt.
- Base classes: `server/retrievers/base/intent_sql_base.py`, `intent_http_base.py`
- Response formatters: `server/retrievers/implementations/intent/domain/response/formatters.py`
- Conversation threading: branches from any turn, reuses cached datasets

### Pipeline Steps (`server/inference/pipeline/steps/`)
Modular steps executed in order: `llm_inference`, `context_retrieval`, `document_reranking`.

### Data Sources (`server/datasources/`)
Connectors for: Postgres, MySQL, MariaDB, SQL Server, Oracle, SQLite, MongoDB, Redis, Cassandra, DuckDB, Chroma, Qdrant, Pinecone, Milvus, Weaviate, Elasticsearch, HTTP/REST/GraphQL, file uploads, web crawling.

### Routes (`server/routes/`)
- `chat_routes.py` — `/v1/chat/completions` (OpenAI-compatible)
- `admin_routes.py` — adapter/datasource CRUD, config management
- `auth_routes.py` — login, API key lifecycle
- `file_routes.py` — document uploads
- `voice_routes.py` — STT/TTS
- `health_routes.py`, `metrics_routes.py`

### Configuration
YAML-first configuration under `config/`:
- `config.yaml` — main server config (providers, rate limits, auth)
- `adapters.yaml` — adapter registry
- `datasources.yaml` — DB connections
- `inference.yaml` — LLM provider settings
- `embeddings.yaml` — embedding model config
- `adapters/` — pre-built adapter configs (14 subdirectories)

### CLI (`bin/`)
Click-based CLI (`bin/orbit.py`) wrapping common ops: `start`, `stop`, `status`, `config`, `keys`, `users`, `prompts`. Shell wrapper `bin/orbit.sh` handles venv activation and Python version checks.

### MCP Server
Exposed via FastMCP, integrated into the FastAPI lifespan. Tools implemented in `server/tools/`.

## Key Conventions
- Async-first throughout (FastAPI + asyncio)
- Prototype HTML/mockups go in `docs/prototypes/`, not `server/`
- Python 3.12 (venv); system Python is 3.14 — always use the venv interpreter
- Server code root for imports is `server/` — keep imports relative to that