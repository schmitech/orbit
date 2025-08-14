<div align="center">
  <img src="docs/images/orbit-logo.png" alt="ORBIT Logo" width="450" style="border: none; outline: none; box-shadow: none;"/>
</div>

<h1 align="center">ORBIT - Open Retrieval-Based Inference Toolkit</h1>

<div align="center">
  
<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/github/v/release/schmitech/orbit" alt="Release"></a>
</p>

**Deploy AI solutions without subscription fees. Run locally, maintain control.**

</div>

## 📑 Table of Contents

- [📑 Table of Contents](#-table-of-contents)
- [🛰️ What is ORBIT?](#️-what-is-orbit)
- [🤔 Why ORBIT?](#-why-orbit)
- [✨ Key Features](#-key-features)
- [📋 Minimum Requirements](#-minimum-requirements)
- [🏗️ Architecture](#️-architecture)
  - [Core Components](#core-components)
  - [Dependencies](#dependencies)
- [🚀 Quick Start](#-quick-start)
  - [Deploying with Docker](#deploying-with-docker)
  - [Deploying Locally](#deploying-locally)
  - [ORBIT CLI Chat](#orbit-cli-chat)
  - [Enabling Chat Memory](#enabling-chat-memory)
- [🌐 API Endpoints](#-api-endpoints)
  - [Core Chat \& Inference](#core-chat--inference)
  - [Authentication](#authentication)
  - [API Key Management (Admin)](#api-key-management-admin)
  - [System Prompts (Admin)](#system-prompts-admin)
  - [Health \& Monitoring](#health--monitoring)
  - [File Management (Experimental)](#file-management-experimental)
- [Scenarios](#scenarios)
  - [Understanding ORBIT's Adapter System](#understanding-orbits-adapter-system)
  - [Multilingual Support](#multilingual-support)
  - [Scenario #1: A Knowledge Base Q\&A Chatbot (SQLite)](#scenario-1-a-knowledge-base-qa-chatbot-sqlite)
  - [Scenario #2: A Knowledge Base Q\&A Chatbot (Vector DB)](#scenario-2-a-knowledge-base-qa-chatbot-vector-db)
  - [Scenario #3: A Database Chatbot (PostgreSQL)](#scenario-3-a-database-chatbot-postgresql)
  - [API Key Management](#api-key-management)
  - [Adapter Information](#adapter-information)
- [📖 Documentation](#-documentation)
  - [Getting Started](#getting-started)
  - [Core Features](#core-features)
  - [Advanced Topics](#advanced-topics)
- [🤝 Community \& Support](#-community--support)
- [📄 License](#-license)

## 🛰️ What is ORBIT?

ORBIT is a middleware platform that provides a unified API for AI inference, allowing you to:

- **Run AI models locally** - No cloud dependencies or per-token costs
- **Connect your data** - SQL databases, vector stores, and files
- **Deploy anywhere** - Locally, on-premise, or in the cloud. VM or Container.
- **Stay secure** - Built-in authentication and content moderation

ORBIT is actively maintained by [Remsy Schmilinsky](https://schmitech.ai/en/about/).


## 🤔 Why ORBIT?

Unlike cloud-based AI services, ORBIT gives you:

- **No recurring costs** - Pay for hardware, not tokens
- **Complete privacy** - Your data never leaves your infrastructure  
- **Full control** - Customize everything to your needs
- **Compliance ready** - Built for regulated industries

Perfect for organizations seeking full transparency, control, and regulatory compliance when combining inference with sensitive data.

## ✨ Key Features

- 🤖 **Model-serving options** - Ollama, vLLM, llama.cpp, and more
- 🔍 **RAG Support** - SQL, Vector DB, and Files
- 🔐 **Security** - Authentication, Authorization (API Keys), content moderation, and audit trails
- 🚀 **High Performance** - Async architecture with fault tolerance

## 📋 Minimum Requirements

- Python 3.12+
- CPU & 16GB RAM (GPU recommended for 3b+ models)
- MongoDB (for authentication and RAG features)
- Optional: Redis (Caching), Elasticsearch (Logging/Audit)

## 🏗️ Architecture

<div align="center">
  <img src="docs/images/orbit-architecture.png" width="700" alt="ORBIT Architecture" />
</div>

### Core Components

**ORBIT Server** (`/server/`): FastAPI-based inference middleware
- **Inference Layer**: Supports multiple LLM providers (OpenAI, Anthropic, Cohere, Ollama, etc.) via unified interface
- **RAG System**: Retrieval-Augmented Generation with SQL, Vector DB, and file-based adapters
- **Authentication**: PBKDF2-SHA256 with bearer tokens, MongoDB-backed sessions
- **Fault Tolerance**: Circuit breaker pattern with exponential backoff for provider failures
- **Content Moderation**: Multi-layered safety with LLM Guard and configurable moderators

**Configuration** (`/config/`): YAML-based modular configuration
- Main config in `config.yaml` with environment variable support
- Separate configs for adapters, datasources, embeddings, inference, moderators, and rerankers
- Dynamic loading with validation and resolver system

**Client Libraries**:
- React-based chat application with Zustand state management
- Embeddable chat widget with theming support
- Node.js and Python API client libraries

### Dependencies

- **MongoDB** (Required): Authentication, RAG storage, conversation history
- **Redis** (Optional): Caching layer
- **Vector DBs** (Optional): Chroma, Qdrant, Pinecone, Milvus for semantic search
- **SQL DBs** (Optional): PostgreSQL, MySQL, SQLite for structured data retrieval

## 🚀 Quick Start

### Deploying with Docker
Refer to [Docker Setup Guide](docker/README.md) for instructions on how to deploy as a docker container.

### Deploying Locally

```bash
# Download latest release
curl -L https://github.com/schmitech/orbit/releases/download/v1.3.2/orbit-1.3.2.tar.gz -o orbit-1.3.2.tar.gz
tar -xzf orbit-1.3.2.tar.gz
cd orbit-1.3.2

# Quick setup with a small model
cp .env.example .env
./install/setup.sh --profile minimal --download-gguf gemma3-1b

# Start ORBIT (Default is http://localhost:3000)
source venv/bin/activate
./bin/orbit.sh --help # CLI tool options
./bin/orbit.sh start # logs under /logs/orbit.log
```

You can find a large list of available open-weighted inference models at [llm-explorer.com](https://llm-explorer.com/).

<video src="https://github.com/user-attachments/assets/8ea103a6-8b33-4801-adc2-f0e81e03e96e" controls>
  Your browser does not support the video tag.
</video>

### ORBIT CLI Chat

Try the chat endpoint using ```orbit-chat``` tool. This is a [python package](https://pypi.org/project/schmitech-orbit-client/). The source is under directory `clients/python` if you wish to customize it.
```bash
orbit-chat --help
orbit-chat --url http://localhost:3000 # Default url
```
<video src="https://github.com/user-attachments/assets/db46e91c-4cb7-44b4-b576-8c1d19176f0a" controls>
  Your browser does not support the video tag.
</video>

### Enabling Chat Memory
To enable conversation history, you will need to have an instance of MongoDB and adjust the settings in your .env file (copy .env.example to .env). At this time conversation history only works in inference mode. Work is underway to enable memory when adapters are enabled (more about adapters in the scenarios section). The two settings are:

```bash
INTERNAL_SERVICES_MONGODB_HOST=localhost
INTERNAL_SERVICES_MONGODB_PORT=27017
```
By default user name and password are disabled in MongoDB. Refer to [conversation history](docs/conversation_history.md) for implementation details.

Make sure the chat_history is enabled in ```config/config.yaml```:

```yaml
chat_history:
  enabled: true
  collection_name: "chat_history"
  store_metadata: true
  retention_days: 90
  max_tracked_sessions: 10000
  session:
    auto_generate: false
    required: true
    header_name: "X-Session-ID"
  user:
    header_name: "X-User-ID"
    required: false
```

For testing chat history, it's recommended to use a model with larger context window (i.e. Gemma3:12b). You can use Ollama (easiest) but if you use default llama_cpp provider, simply add another entry to file `install/gguf-models.json`. This is where you define the GGUF files from Hugging Face. Then simply run
this command to pull the model:

```bash
# Assuming gemma3-12b is defined in gguf-models.json
./install/setup.sh --profile minimal --download-gguf gemma3-12b
```

There is a simple React app you can use to test conversation history with ORBIT. It's not part of the distributable package, but you if you clone the repository you will find it under ```clients/chat-app```. To run the react GUI chat application:

```bash
cd clients/chat-app
npm install
npm run dev
```

<video src="https://github.com/user-attachments/assets/116dcd19-3485-41d2-996c-7317353b5b34" controls>
  Your browser does not support the video tag.
</video>

You can also try the embeddable ORBIT [chatbot widget](https://www.npmjs.com/package/@schmitech/chatbot-widget)  under ```clients/chat-widget/react-example```:

```bash
cd clients/chat-widget/react-example
npm install
npm run dev
```

<video src="https://github.com/user-attachments/assets/cc710e9f-89f8-447d-b308-4287bab22b92" controls>
  Your browser does not support the video tag.
</video>

## 🌐 API Endpoints

ORBIT provides a RESTful API for programmatic access. Here are the key endpoints for getting started:

### Core Chat & Inference
- `POST /v1/chat` - MCP protocol chat endpoint (JSON-RPC 2.0 format)
- `GET /health` - Overall system health

### Authentication
- `POST /auth/login` - User authentication  
- `POST /auth/logout` - End session
- `GET /auth/me` - Get current user info
- `POST /auth/register` - Register new user
- `POST /auth/change-password` - Change user password

### API Key Management (Admin)
- `GET /admin/api-keys` - List API keys
- `POST /admin/api-keys` - Create new API key
- `DELETE /admin/api-keys/{api_key}` - Delete API key
- `POST /admin/api-keys/deactivate` - Deactivate API key
- `GET /admin/api-keys/{api_key}/status` - Get API key status

### System Prompts (Admin)
- `GET /admin/prompts` - List system prompts
- `POST /admin/prompts` - Create system prompt
- `PUT /admin/prompts/{prompt_id}` - Update system prompt
- `DELETE /admin/prompts/{prompt_id}` - Delete system prompt

### Health & Monitoring
- `GET /health` - System health overview
- `GET /health/adapters` - Adapter health status
- `GET /health/embedding-services` - Embedding service status
- `GET /health/mongodb-services` - MongoDB connection status
- `GET /health/ready` - Readiness check
- `GET /health/system` - System resource usage

### File Management (Experimental)
- `POST /upload` - Single file upload
- `POST /upload/batch` - Batch file upload
- `GET /info/{file_id}` - File information
- `DELETE /{file_id}` - Delete file
- `GET /status` - File system status

**API Documentation**: Full API reference with examples is available at `/docs` (Swagger UI) when the server is running.

**Authentication**: Most endpoints require either:
- Bearer token authentication (for user sessions)
- API key authentication via `X-API-Key` header (for adapter access)

## Scenarios

ORBIT works in two modes: **simple inference** (pass-through to model providers) and **RAG mode** (using retriever adapters). ORBIT uses an **adapter-based approach** where API keys are attached to specific adapters from `config/adapters.yaml`, so API keys represent behaviors or agents. A MongoDB instance is required to enable adapters, otherwise you can only use ORBIT as simple inference pass-through service.

### Understanding ORBIT's Adapter System

Each adapter defines:
- **Data Source**: SQLite, PostgreSQL, Chroma, Qdrant, etc.
- **Retrieval Method**: SQL queries, vector search, intent recognition
- **Behavior**: How the AI responds to queries thorugh custom prompts
- **Inference Provider**: Optionally specify which LLM provider (e.g., Ollama, OpenAI, Groq) the adapter should use, overriding the global default.

This means one API key = one specific behavior/agent, making it easy to create specialized assistants for different use cases.

### Multilingual Support

When `language_detection.enabled: true` in `config.yaml`, ORBIT automatically detects the conversation language, so responses and conversations are maintained in the detected language for consistency. Therefore, you don't need to translate your knowledge base—you can work with your data as is.

### Scenario #1: A Knowledge Base Q&A Chatbot (SQLite)

**Scenario**: Municipal government wants to provide citizens with instant answers about city services, regulations, and procedures.

**Setup**:
```bash
# Set up SQLite database with city Q&A data
./examples/sample-db-setup.sh sqlite

# Create API key for the qa-sql adapter
python bin/orbit.py key create \
  --adapter qa-sql \
  --name "City Services Assistant" \
  --prompt-file examples/prompts/examples/city/city-assistant-normal-prompt.txt
```

**Sample Questions**:
- "How do I report a pothole on my street?"
- "What is the fee for a residential parking permit?"
- "Where can I dispose of hazardous household waste?"
- "How do I renew my dog license?"

**Features**:
- Fast SQL-based retrieval with confidence scoring
- Secure table-level access control
- Built-in fault tolerance and caching
- Perfect for structured Q&A data

Test it with the orbit-chat tool:

```bash
orbit-chat --url http://localhost:3000 --api-key YOUR_API_KEY
```

Or use the ORBIT chatbot widget. See the [widget documentation](clients/chat-widget/README.md) for integration details:
<video src="https://github.com/user-attachments/assets/54f81887-17c2-420d-a29c-a191eb6d3912" controls>
  Your browser does not support the video tag.
</video>

**💡 Extending SQLite**: The `QASSQLRetriever` extends `SQLiteRetriever` with QA-specific enhancements. You can create your own domain specializations by inheriting from any database implementation. See [SQL Retriever Architecture](docs/sql-retriever-architecture.md) for details on creating new database support or domain specializations.

### Scenario #2: A Knowledge Base Q&A Chatbot (Vector DB)

**Scenario**: Municipal recreation department wants to provide citizens with information about community programs, activities, and registration details using semantic search.

**Setup**:
```bash
# Set up Chroma vector database with Q&A data
./examples/sample-db-setup.sh chroma

# Create API key for the qa-vector-chroma adapter
python bin/orbit.py key create \
  --adapter qa-vector-chroma \
  --name "Recreation Programs Assistant" \
  --prompt-file examples/prompts/examples/activity/activity-assistant-normal-prompt.txt
```

**Sample Questions**:
- "What gymnastics programs are available for adults?"
- "How do I register for the contemporary dance class?"
- "What mindfulness programs are there for seniors?"
- "Are there any summer camps for kids?"

**Features**:
- Semantic similarity search using embeddings
- Handles natural language variations
- Scalable to millions of Q&A pairs
- Multilingual, no need to translate each QA pair.

**⚠️ Requirements**: 
- Embeddings must be enabled in `config.yaml` (`embedding.enabled: true`)
- Accuracy and matching quality depend on the embedding model's number of dimensions (higher dimensions = better semantic understanding)
- Default: 768 dimensions (nomic-embed-text model) via Ollama. Embeddings are defined in ```config/embeddings.yaml```

**💡 Extending ChromaDB**: The `QAChromaRetriever` extends `ChromaRetriever` with QA-specific enhancements. You can create your own domain specializations or add support for other vector databases (Milvus, Pinecone, Elasticsearch, Redis). See [Vector Retriever Architecture](docs/vector-retriever-architecture.md) for details on creating new vector database support or domain specializations.

**🔍 Qdrant Alternative**: There's also a Qdrant example under `examples/qdrant/` with a commented adapter in `config/adapters.yaml`. Qdrant provides high-performance vector search with REST API and multiple distance metrics.

### Scenario #3: A Database Chatbot (PostgreSQL)

**Scenario**: Customer service team needs to query order data using natural language instead of SQL.

**Setup Sample Customer Orders Database**:
```bash
# Set up PostgreSQL with customer order schema
cd examples/postgres

# Update Postgres connection parameters
cp env.example .env

# Test connection
python /db_utils/test_connection.py

# Create sample database
python /db_utils/setup_schema.py

# Add sample data
python /db_utils/customer-order.py --action insert --clean --customers 100 --orders 1000

# Test data exists
python /db_utils/test_query.py

# Create API key for the intent-sql-postgres adapter
python bin/orbit.py key create \
  --adapter intent-sql-postgres \
  --name "Order Management Assistant" \
  --prompt-file examples/postgres/prompts/customer-assistant-enhanced-prompt.txt
```

**Sample Questions**:
- "Show me all orders from John Smith"
- "What are the top 10 customers by order value?"
- "Find orders with status 'pending' from last week"
- "Which customers haven't placed an order in 6 months?"

**Features**:
- Natural language to SQL conversion
- Domain-aware intent recognition
- Template-based query generation

Test it with the orbit-chat tool:

```bash
orbit-chat --url http://localhost:3000 --api-key YOUR_API_KEY
```

<video src="https://github.com/user-attachments/assets/fffdb719-5cd2-4bc5-9570-84b238de50a1" controls>
  Your browser does not support the video tag.
</video>

**See the web chat widget in action with the intent adapter:**

<video src="https://github.com/user-attachments/assets/6b2436e8-0d48-40c4-b1ea-0629cc8725b6" controls>
  Your browser does not support the video tag.
</video>

### API Key Management

> **Note:** You need to log in as admin before managing API keys.  
> Run:
> ```bash
> ./bin/orbit.sh login
> ```


List and manage your API keys:
```bash
# List all API keys
./bin/orbit.sh key list

# Test an API key
./bin/orbit.sh key test YOUR_API_KEY

# Deactivate an API key
./bin/orbit.sh key deactivate YOUR_API_KEY
```

### Adapter Information

View available adapters and their configurations:
```bash
# List all adapters
./bin/orbit.sh key list-adapters

# Get adapter details
./bin/orbit.sh key list-adapters --adapter qa-sql
```

## 📖 Documentation

### Getting Started
- [Installation Guide](docs/server.md) - Detailed setup instructions
- [Configuration](docs/configuration.md) - Essential settings
- [Docker Deployment](docker/README.md) - Container setup

### Core Features
- [Authentication](docs/authentication.md) - User management and security
- [RAG & Adapters](docs/adapters.md) - Connect your data sources
- [Content Moderation](docs/llm-guard-service.md) - Safety features

### Advanced Topics
- [Development Roadmap](docs/roadmap/README.md) - What's coming next
- [Contributing Guide](CONTRIBUTING.md) - Join the project
- [SQL Retriever Architecture](docs/sql-retriever-architecture.md) - Extend database support
- [Vector Retriever Architecture](docs/vector-retriever-architecture.md) - Extend vector database support

## 🤝 Community & Support

- **Questions?** Open an [issue](https://github.com/schmitech/orbit/issues)
- **Updates:** Check the [changelog](CHANGELOG.md)
- **Commercial Support:** Contact [schmitech.ai](https://schmitech.ai/)
- **Maintained by:** [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/)

## 📄 License

Apache 2.0 - See [LICENSE](LICENSE) for details.
