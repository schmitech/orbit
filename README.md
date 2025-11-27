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

> ⭐️ If ORBIT helps you ship faster, please consider starring the repo to support the roadmap.

## Table of Contents

- [✨ Highlights](#highlights)
- [🛠️ Why ORBIT](#why-orbit)
- [🚀 Quick Start](#quick-start)
- [⭐ Support the Project](#support-the-project)
- [📖 Documentation](#documentation)
- [🤝 Community & Support](#community--support)
- [📄 License](#license)

---

## Highlights

- **Unified AI gateway** supporting 20+ LLM providers (OpenAI, Anthropic, Gemini, Cohere, Mistral, Ollama, Groq, DeepSeek, xAI, OpenRouter, and more) plus local models via Ollama, llama.cpp, and vLLM.
- **Comprehensive data integration** with RAG adapters for SQL databases (PostgreSQL, MySQL, SQLite, DuckDB, Oracle, SQL Server, Cassandra), vector stores (Chroma, Qdrant, Pinecone, Milvus, Elasticsearch, Redis), MongoDB, HTTP APIs, and file uploads with multimodal support.
- **Intelligent query processing** with intent-based adapters that translate natural language to SQL, Elasticsearch queries, MongoDB queries, and HTTP API calls.
- **Vision capabilities** with support for OpenAI, Gemini, and Anthropic vision models for image analysis and OCR.
- **Secure by default** with token-based auth, role-aware API keys, and pluggable content moderation.
- **Ready for teams** thanks to batteries-included clients (CLI, React widget, Node/Python SDKs).

---

## Why ORBIT

- **Avoid vendor lock-in** by switching between LLM providers without rewriting your application code—change providers in configuration, not code.
- **Keep your data private** with support for on-prem deployments, air-gapped installs, and local models that never leave your infrastructure.
- **Ship faster** with production-ready adapters that handle authentication, connection pooling, error handling, and query optimization out of the box.
- **Query your data naturally** in any language instead of writing SQL, Elasticsearch queries, or API calls—intent-based adapters handle the translation automatically.

### Built for

- **Platform & infra teams** who need a stable control plane for LLM workloads across multiple providers and data sources.
- **Product teams** shipping AI copilots that depend on reliable retrieval, intent-based querying, and guardrails.
- **Data teams** building RAG applications that need to query SQL databases, vector stores, and APIs through natural language.
- **Researchers & tinkerers** exploring local-first stacks, evaluating different foundation models, or building multimodal AI applications.

Have a story or feature request? [Open an issue](https://github.com/schmitech/orbit/issues) or add it to the [Roadmap](docs/roadmap/README.md).

---

## 🚀 Quick Start

There are three ways to get started with ORBIT.

### Option 1: Docker (Recommended)

This is the fastest way to get ORBIT running. The demo image includes a self-contained server with a local model, so no additional API keys are needed.

```bash
# Pull the ORBIT basic image
docker pull schmitech/orbit:basic

# Run the container
docker run -d \
  --name orbit-basic \
  -p 3000:3000 \
  schmitech/orbit:basic
```

The ORBIT server will be running at `http://localhost:3000`. You can monitor it by browsing to the dashboard at `http://localhost:3000/dashboard`.

### Create Your First API Key

Once the container is running, create a default API key to start chatting:

```bash
# Login as admin (default password: admin123). You can change it later.
docker exec -it orbit-basic python /orbit/bin/orbit.py login --username admin --password admin123

# Create a default API key with a simple prompt
docker exec -it orbit-basic python /orbit/bin/orbit.py key create \
  --adapter simple-chat \
  --name "Default Chat Key" \
  --prompt-name "Default Assistant" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."
```

The command will output your API key (starts with `orbit_`). Save it for use with the chat clients below.
```bash
✓ API key created successfully
API Key: orbit_123456789ABCDEFGabcdefg
Client: Default Chat Key
Adapter: simple-chat
Prompt ID: 12345-abcdefg
```

Browse to `http://localhost:3000/dashboard` to monitor the ORBIT server.

<div align="center">
  <video src="https://github.com/user-attachments/assets/d12135d9-b827-49df-8725-1350df175aed" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>ORBIT Dashboard running during unit tests. Some errors shown are expected and are part of negative test coverage.</i>
</div>

**Note:** The basic image includes the `simple-chat` adapter and the `gemma3-1b` model pre-configured, running natively via llama.cpp. No API keys from cloud or commercial AI platforms or external services are needed. For more details, see the [Docker Basic Image Guide](docker/README-BASIC.md).

Quick test of the chat endpoint:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_123456789ABCDEFGabcdefg' \
  -H 'X-Session-ID: test-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello, what is 2+2?"}
    ],
    "stream": false
  }'
```

Example response:

```json
{
  "response": "2 + 2 = 4 Let me know if you'd like to try another math problem!",
  "sources": [],
  "metadata": {
    "processing_time": 0.0,
    "pipeline_used": true
  }
}
```

### Option 2: Manual Installation

For more control, you can install and run ORBIT locally from the source.

#### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker 20.10+ and Docker Compose 2.0+
- Optional: MongoDB, Redis, and a vector DB (Chroma, Qdrant, etc.)

#### 1. Install ORBIT Server

```bash
# Clone the repository
git clone https://github.com/schmitech/orbit.git
cd orbit

# Add API keys if using proprietary services like OpenAI, Cohere, etc.
cp env.example .env

# Install packages
./install/setup.sh

# Activate Python environment
source venv/bin/activate

# Start the ORBIT server
./bin/orbit.sh start 

# Check the logs
tail -f ./logs/orbit.log
```

**Note:** After starting the server, you'll need to create an API key using `./bin/orbit.sh key create` before you can use the chat clients.

### Option 3: Download Latest Release

Download and install the latest stable release without cloning the repository.

#### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Optional: MongoDB, Redis, and a vector DB (Chroma, Qdrant, etc.)

#### 1. Download and Extract Release

```bash
# Download the latest release archive
# Replace v2.1.1 with the latest version from https://github.com/schmitech/orbit/releases
curl -L https://github.com/schmitech/orbit/releases/download/v2.1.1/orbit-2.1.1.tar.gz -o orbit-2.1.1.tar.gz

tar -xzf orbit-2.1.1.tar.gz

cd orbit-2.1.1
```

#### 2. Configure and Install

```bash
# Add API keys if using proprietary services like OpenAI, Cohere, Anthropic, etc.
cp env.example .env

# Install packages
./install/setup.sh

# Activate Python environment
source venv/bin/activate
```

#### 3. Download a Local Model (Optional)

Get a local GGUF model for offline inference. Models are downloaded from Hugging Face.

```bash
# Available GGUF models: gemma3-270m, gemma3-1b, tinyllama-1b, phi-2, mistral-7b, granite4-micro, embeddinggemma-300m
# You can add your own models by editing install/gguf-models.json
./install/setup.sh --download-gguf granite4-micro
```

**Alternative: Using Ollama**

If you encounter errors with llama.cpp (e.g., missing native libraries, compilation issues), you can use Ollama instead:

1. **Install Ollama** (if not already installed):
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Windows: Download from https://ollama.com/download
   ```

2. **Pull the model**:
   ```bash
   ollama pull granite4:micro
   ```

3. **Update configuration**:
   - Edit `config/adapters.yaml` and find the `simple-chat` adapter
   - Change `inference_provider: "ollama"` (from `"llama_cpp"`)
   - Change `model: "granite4:micro"` to match the Ollama model name
   - Verify that `ollama` provider has `enabled: true` in `config/inference.yaml`

#### 4. Start the Server

```bash
# Start the ORBIT server
./bin/orbit.sh start 

# Check the logs
cat ./logs/orbit.log
```

**Note:** After starting the server, you'll need to create an API key using `./bin/orbit.sh key create` before you can use the chat clients.

---

## 💬 Chat Clients

Once your ORBIT server is running (via Docker or manual installation), you can interact with it using one of these clients:

### Using the Python CLI Client

The `orbit-chat` python CLI provides a terminal-based chat interface.

```bash
# Install the client from PyPI
pip install schmitech-orbit-client

orbit-chat --api-key YOUR_API_KEY
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/6ea2ba0c-eb59-43be-9bbd-0ff0dd90b587" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Using the <code>orbit-chat</code> CLI. Run <code>orbit-chat -h</code> for options.</i>
</div>

### Using the React Web App

```bash
npm install -g orbitchat
orbitchat --api-url http://localhost:3000 --api-key YOUR_API_KEY --open
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/c8a4523d-82fe-4d32-93b8-acb6c97820dc" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Chatting with ORBIT using the React client.</i>
</div>

---

## 🗃️ Chat with Your Data

ORBIT can connect to your databases and other data sources. Here's a quick example using a local SQLite database.

**Note:** This example requires cloning the repository or using the release version. The basic Docker image (`schmitech/orbit:basic`) does not include database adapters or examples. A Docker image with database examples will be available in a future release.

### Quick Setup (SQLite Example)

**Prerequisites:** Clone the repository or download the release version. See [Option 2: Manual Installation](#option-2-manual-installation) above.

```bash
# 1. Set up the database and test data
python utils/sql-intent-template/examples/sqlite/contact/generate_contact_data.py \
  --records 100 \
  --output utils/sql-intent-template/examples/sqlite/contact/contact.db

# 2. Restart ORBIT to load pre-generated templates
./bin/orbit.sh restart

# 3. Create an API key for the SQLite adapter
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-contact \
  --name "Contacts Chatbot" \
  --prompt-file ./examples/prompts/contact-assistant-prompt.txt \
  --prompt-name "Contacts Chatbot"
```

**Note:** The `intent-sql-sqlite-contact` adapter is enabled by pre-generated templates for this example. To connect your own database, you'll need to generate templates from your database schema. See the [`README.md`](utils/sql-intent-template/README.md) and [`tutorial.md`](utils/sql-intent-template/docs/tutorial.md) for a detailed guide.

### Test with the React application:

You can now use the API key you created with the React app (`orbitchat`) to have a conversation with your database.

<div align="center">
  <video src="https://github.com/user-attachments/assets/68190983-d996-458f-8024-c9c15272d1c3" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Chatting with a database using the React client.</i>
</div>

### Next steps

- Explore `config/adapters.yaml` to enable or customize adapters for different data sources.
- Skim the [docs](#documentation) for deep dives on auth, configuration, and deployment patterns.

---

## Support the Project

Your support keeps ORBIT independent and focused on open-source innovation.

- ⭐ Star the repo to signal that ORBIT matters to you.
- 📣 Share a demo, blog, or tweet so other builders discover it.
- 🐛 Open issues and PRs—your feedback directly shapes the roadmap.

---

## Documentation

For more detailed information, please refer to the official documentation.

- [Installation Guide](docs/server.md)
- [Configuration](docs/configuration.md)
- [Authentication](docs/authentication.md)
- [RAG & Adapters](docs/adapters.md)
- [Development Roadmap](docs/roadmap/README.md)
- [Contributing Guide](CONTRIBUTING.md)

## Community & Support

- **Questions?** Open an [issue](https://github.com/schmitech/orbit/issues)
- **Updates:** Check the [changelog](CHANGELOG.md)
- **Maintained by:** [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/)

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
