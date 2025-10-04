<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo.png" alt="ORBIT Logo" width="500" style="border: none; outline: none; box-shadow: none;"/>
  </a>
</div>
  
<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/github/v/release/schmitech/orbit" alt="Release"></a>
  <a href="https://pypi.org/project/schmitech-orbit-client/"><img src="https://img.shields.io/pypi/v/schmitech-orbit-client?label=PyPI%20client" alt="PyPI"></a>
  <a href="https://www.npmjs.com/package/@schmitech/chatbot-widget"><img src="https://img.shields.io/npm/v/@schmitech/chatbot-widget.svg?logo=npm&label=Widget%20NPM" alt="NPM"></a>
  <a href="https://github.com/schmitech/orbit" target="_blank">
    <img src="https://img.shields.io/github/stars/schmitech/orbit?style=social&label=Star" alt="GitHub stars">
  </a>
</p>

</div>

# ORBIT – Unified, self‑hosted AI inference with your data

ORBIT (Open Retrieval-Based Inference Toolkit) is a middleware platform that provides a unified API for AI inference. It acts as a central gateway, allowing you to connect various local and remote AI models with your private data sources like SQL databases and vector stores.

ORBIT gives you a single, consistent API to run LLMs (local or cloud) against your private data sources with portability, performance, high-availability, and security at the core.


<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-why-orbit">Why ORBIT</a> •
  <a href="#%EF%B8%8F-architecture-overview">Architecture</a> •
  <a href="#-what-can-you-build-with-orbit">Examples</a> •
  <a href="#-documentation">Docs</a> •
  <a href="https://github.com/schmitech/orbit/issues">Issues</a>
</p>

---

## 🚀 Quick Start

### 1. Deploy with Docker

Refer to the [Docker Setup Guide](docker/README.md) or run from the `docker/` directory:

```bash
cd docker
chmod +x docker-init.sh orbit-docker.sh
./docker-init.sh --build --profile minimal
```


### 2. Deploy Locally

```bash
# Download the latest release
curl -L https://github.com/schmitech/orbit/releases/download/v1.5.3/orbit-1.5.3.tar.gz -o orbit-1.5.3.tar.gz
tar -xzf orbit-1.5.3.tar.gz
cd orbit-1.5.3

# Run the quick setup script (downloads a small model)
cp .env.example .env
./install/setup.sh --profile minimal --download-gguf gemma3-270m

# Start the ORBIT server
source venv/bin/activate
./bin/orbit.sh start # Logs are at /logs/orbit.log
```
Your ORBIT instance is now running at `http://localhost:3000`.

### 3. Chat with ORBIT using the CLI tool

Use the `orbit-chat` CLI tool to interact with your instance.

```bash
pip install schmitech-orbit-client

# Start chatting!
orbit-chat
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/b3cf6a86-b173-4c0b-9dd8-061df848dba4" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Using 'orbit-chat' tool. Add -h for usage.</i>
</div>

### 4. Chat with ORBIT using the Node API 
```bash
cd clients/chat-app
npm install
npm run dev
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/1a591929-c536-4de5-a3a2-0493b16edbad" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Chatting with ORBIT using the React client.
</div>

---

## 🏗️ Architecture Overview

<div align="center">
  <img src="docs/images/orbit-architecture.png" width="700" alt="ORBIT Architecture" />
</div>

<details>
<summary><b>Click to learn more about the Core Components</b></summary>

### Core Components

**ORBIT Server** (`/server/`): FastAPI-based inference middleware
- **Inference Layer**: Supports multiple LLM providers (OpenAI, Anthropic, Cohere, Ollama, etc.) via unified interface
- **RAG System**: Retrieval-Augmented Generation with SQL and Vector DB adapters (file-based / multimodal retrieval underway, it will be available in release 2.0.0)
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

### Client Libraries

New language clients are available under `clients/` with examples and integration tests:

- Elixir: `clients/elixir` — `make deps`, `make example`, `ORBIT_INTEGRATION=1 make test`
- Swift: `clients/swift` — `make example`, `ORBIT_INTEGRATION=1 make test`
- Kotlin: `clients/kotlin` — `make example`, `ORBIT_INTEGRATION=1 make test`
- Scala: `clients/scala` — `make example`, `ORBIT_INTEGRATION=1 make test`
- PHP: `clients/php` — `make example`, `ORBIT_INTEGRATION=1 make test`
- Haskell: `clients/haskell` — `make example`
- Clojure: `clients/clojure` — `make example`, `ORBIT_INTEGRATION=1 make test`
- Perl: `clients/perl` — `make example`, `ORBIT_INTEGRATION=1 make test`
- R: `clients/r` — `make example`, `ORBIT_INTEGRATION=1 make test`

Set `ORBIT_INTEGRATION=1` to enable integration tests. Optionally set `ORBIT_URL` (defaults to `http://localhost:3000`).

### Dependencies

- **MongoDB** (Required): Authentication, RAG storage, conversation history
- **Redis** (Optional): Caching layer
- **Vector DBs** (Optional): Chroma, Qdrant, Pinecone, Milvus for semantic search
- **SQL DBs** (Optional): PostgreSQL, MySQL, SQLite for structured data retrieval
</details>

---

## ✨ What Can You Build with ORBIT?

ORBIT uses a flexible [adapter architecture](docs/adapters.md) to connect your data to AI models. An API key is tied to a specific adapter, effectively creating a specialized "agent" for a certain task. Here are a few examples:

### Scenario 1: Knowledge Base Q&A
Provide instant, semantically-aware answers from a knowledge base. Perfect for customer support or internal documentation.

**Sample Questions:**
- "What are the summer camp programs for kids?"
- "How do I register for the contemporary dance class?"

_NOTE: You need an instance of MongoDB to enable adapters_

### Setup the sample SQLite Database with Q/A records about a municipality.

Here's the [Sample Q/A datasets](examples/city-qa-pairs.json) for this example. The knowledge base corresponds to a municipal services assistant.

```bash
#Login as admin first. Default password is admin123. You should change after installing ORBIT.
./bin/orbit.sh login

# Set up SQLite database with Q&A data
./examples/sample-db-setup.sh sqlite
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/b54659fe-2172-4754-b9ff-68292f7efcb1" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Setting up the sample SQLite Q/A dataset</i>
</div>

### Testing with the node client:

```bash
# Test using node client
cd clients/node-api
npm install
npm run build
npm run test-query-from-pairs ../../examples/city-qa-pairs.json "http://localhost:3000" "your-api-key" 5 134444
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/e6487006-02da-4927-a4f3-04be7c6a3a22" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Testing the Q/A Adapter using the node API client</i>
</div>

### Scenario 2: Chat with Your SQL Database
Ask questions about your data in natural language and get answers without writing SQL.

**Sample Questions:**
- "Show me all orders from John Smith"
- "What are the top 10 customers by order value?"

```bash
# Set up PostgreSQL with a sample schema and data
cd examples/postgres

# Update with  your connection parameters
cp env.example .env

# Test connection
python test_connection.py

# Create the DB
python setup_schema.py

# Install faker to generate synthetic data
pip install faker

# Add sample data
python customer-order.py --action insert --clean --customers 100 --orders 1000

# Create an API key for the SQL intent adapter.
# Make sure you are logged in as admin if auth is enabled in `/config/config.yaml`.
python bin/orbit.py key create \
  --adapter intent-sql-postgres \
  --name "Order Management Assistant" \
  --prompt-file examples/postgres/prompts/customer-assistant-enhanced-prompt.txt

#make sure the sample SQL intent adapter is enabled in `/config/adapters.yaml`
- name: "intent-sql-postgres"
    enabled: false
    type: "retriever"
    datasource: "postgres"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentPostgreSQLRetriever"
    inference_provider: "ollama"

# Start or restart the server
./bin/orbit.sh start --delete-logs

# Start chatting with your new key
orbit-chat --url http://localhost:3000 --api-key YOUR_API_KEY
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/d33dfb10-1668-4b05-ba83-ae3c294001ad" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Testing the SQL Intent Adapter using the ORBIT CLI tool</i>
</div>

---

## ⭐ Like this project? Give it a star!

If you find ORBIT useful, please consider giving it a star on GitHub. It helps more people discover the project.

<a href="https://github.com/schmitech/orbit" target="_blank">
  <img src="https://img.shields.io/github/stars/schmitech/orbit?style=for-the-badge&logo=github&label=Star%20Us" alt="GitHub stars">
</a>

<a href="https://star-history.com/#schmitech/orbit&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=schmitech/orbit&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=schmitech/orbit&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=schmitech/orbit&type=Date" />
  </picture>
</a>

---

## 📖 Documentation

For more detailed information, please refer to the official documentation.

- [Installation Guide](docs/server.md)
- [Configuration](docs/configuration.md)
- [Authentication](docs/authentication.md)
- [RAG & Adapters](docs/adapters.md)
- [Development Roadmap](docs/roadmap/README.md)
- [Contributing Guide](CONTRIBUTING.md)

<details>
<summary><b>Full API Reference</b></summary>

ORBIT provides a RESTful API for programmatic access. The full API reference with examples is available at `/docs` (Swagger UI) when the server is running.

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
</details>

## 🤝 Community & Support

- **Questions?** Open an [issue](https://github.com/schmitech/orbit/issues)
- **Updates:** Check the [changelog](CHANGELOG.md)
- **Commercial Support:** Contact [schmitech.ai](https://schmitech.ai/)
- **Maintained by:** [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/)

## 📄 License

Apache 2.0 - See [LICENSE](LICENSE) for details.
