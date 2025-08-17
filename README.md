<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo.png" alt="ORBIT Logo" width="450" style="border: none; outline: none; box-shadow: none;"/>
  </a>
</div>

<h1 align="center">ORBIT - Your Private, On-Prem AI Gateway</h1>
<h3 align="center"><em>Open Retrieval-Based Inference Toolkit</em></h3>

<div align="center">
  
<p align="center">
  <strong>Build powerful AI solutions on your own infrastructure. No subscription fees, total data control.</strong>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/github/v/release/schmitech/orbit" alt="Release"></a>
  <a href="https://github.com/schmitech/orbit" target="_blank">
    <img src="https://img.shields.io/github/stars/schmitech/orbit?style=social&label=Star" alt="GitHub stars">
  </a>
</p>

</div>

<div align="center">
  <video src="https://github.com/user-attachments/assets/116dcd19-3485-41d2-996c-7317353b5b34" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>A sneak peek of the ORBIT chat UI in action.</i>
</div>

## 🛰️ What is ORBIT?

ORBIT is an open-source middleware platform that provides a unified API for AI inference. It acts as a central gateway, allowing you to connect various local and remote AI models with your private data sources like SQL databases, vector stores, and local files.

It's designed for developers and organizations who want to build and deploy AI-powered applications with full control over their infrastructure, data, and costs.

| Feature                 | Description                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------- |
| 🔒 **Run AI Locally**   | No cloud dependencies or per-token costs. Your data and models stay within your network.                |
| 🔌 **Connect Your Data**| Built-in RAG support for SQL, Vector DBs (Chroma, Qdrant), and local files.                             |
| 🚀 **Deploy Anywhere**  | Run on any machine using Docker or Python. On-premise, private cloud, or your local development machine. |
| 🔧 **Model Agnostic**   | Supports major model serving backends like Ollama, vLLM, and llama.cpp.                                 |
| 🛡️ **Secure & Compliant**| Built-in authentication, API key management, content moderation, and audit trails for enterprise needs. |

---


## 🚀 Quick Start

Get ORBIT running in minutes.

### 1. Deploy with Docker
The easiest way to get started is with Docker. This handles all dependencies for you.

<details>
<summary><b>Click for Docker Instructions</b></summary>

Refer to the [Docker Setup Guide](docker/README.md) for detailed instructions on how to deploy ORBIT as a Docker container.
</details>

### 2. Deploy Locally

```bash
# Download the latest release
curl -L https://github.com/schmitech/orbit/releases/download/v1.3.4/orbit-1.3.4.tar.gz -o orbit-1.3.4.tar.gz
tar -xzf orbit-1.3.4.tar.gz
cd orbit-1.3.4

# Run the quick setup script (downloads a small model)
cp .env.example .env
./install/setup.sh --profile minimal --download-gguf gemma3-1b

# Start the ORBIT server
source venv/bin/activate
./bin/orbit.sh start # Logs are at /logs/orbit.log
```
Your ORBIT instance is now running at `http://localhost:3000`.

### 3. Chat with ORBIT

Use the `orbit-chat` CLI tool to interact with your instance.

```bash
# Install the client if you haven't already
pip install schmitech-orbit-client

# Start chatting!
orbit-chat --url http://localhost:3000
```
<video src="https://github.com/user-attachments/assets/db46e91c-4cb7-44b4-b576-8c1d19176f0a" controls>
  Your browser does not support the video tag.
</video>

## ✨ What Can You Build with ORBIT?

ORBIT uses a powerful **Adapter system** to connect your data to AI models. An API key is tied to a specific adapter, effectively creating a specialized "agent" for a certain task. Here are a few examples:

### Scenario 1: Knowledge Base Q&A (Vector DB)
Provide instant, semantically-aware answers from a knowledge base. Perfect for customer support or internal documentation.

**Sample Questions:**
- "What are the summer camp programs for kids?"
- "How do I register for the contemporary dance class?"

<video src="https://github.com/user-attachments/assets/54f81887-17c2-420d-a29c-a191eb6d3912" controls>
  Your browser does not support the video tag.
</video>

<details>
<summary><b>Click for Setup Instructions</b></summary>

```bash
# Set up Chroma vector database with Q&A data
./examples/sample-db-setup.sh chroma

# Create an API key for the vector adapter
python bin/orbit.py key create \
  --adapter qa-vector-chroma \
  --name "Recreation Programs Assistant" \
  --prompt-file examples/prompts/examples/activity/activity-assistant-normal-prompt.txt

# Start chatting with your new key
orbit-chat --url http://localhost:3000 --api-key YOUR_API_KEY
```
</details>

### Scenario 2: Chat with Your SQL Database
Ask questions about your data in natural language and get answers without writing SQL.

**Sample Questions:**
- "Show me all orders from John Smith"
- "What are the top 10 customers by order value?"

<video src="https://github.com/user-attachments/assets/fffdb719-5cd2-4bc5-9570-84b238de50a1" controls>
  Your browser does not support the video tag.
</video>

<details>
<summary><b>Click for Setup Instructions</b></summary>

```bash
# Set up PostgreSQL with a sample schema and data
cd examples/postgres
cp env.example .env
# (Update .env with your PostgreSQL connection details)
python /db_utils/setup_schema.py
python /db_utils/customer-order.py --action insert --clean --customers 100 --orders 1000

# Create an API key for the SQL intent adapter
python bin/orbit.py key create \
  --adapter intent-sql-postgres \
  --name "Order Management Assistant" \
  --prompt-file examples/postgres/prompts/customer-assistant-enhanced-prompt.txt

# Start chatting with your new key
orbit-chat --url http://localhost:3000 --api-key YOUR_API_KEY
```
</details>

---


## ⭐ Like this project? Give it a star!

If you find ORBIT useful, please consider giving it a star on GitHub. It helps more people discover the project and motivates continued development.

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


## 🏗️ Architecture Overview

<div align="center">
  <img src="docs/images/orbit-architecture.png" width="700" alt="ORBIT Architecture" />
</div>

<details>
<summary><b>Click to learn more about the Core Components</b></summary>

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
</details>

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