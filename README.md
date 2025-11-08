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

- **Run securely with your data** thanks to support for on-prem hardware, air-gapped installs, and strict authentication defaults.
- **Mix and match 20+ LLM providers** (OpenAI, Anthropic, Gemini, Cohere, Mistral, Ollama, Groq, DeepSeek, xAI, OpenRouter, and more) plus local models through a single unified API without rewriting downstream apps.
- **Connect to any data source** with production-ready RAG adapters for SQL databases (PostgreSQL, MySQL, SQLite, DuckDB, Oracle, SQL Server, Cassandra), vector stores (Chroma, Qdrant, Pinecone, Milvus, Elasticsearch, Redis), MongoDB, HTTP APIs, and file uploads.
- **Intelligent query translation** with intent-based adapters that automatically convert natural language to SQL, Elasticsearch queries, MongoDB queries, and HTTP API calls.
- **Multimodal capabilities** with vision support for image analysis, OCR, and document understanding across multiple providers.

### Built for

- **Platform & infra teams** who need a stable control plane for LLM workloads across multiple providers and data sources.
- **Product teams** shipping AI copilots that depend on reliable retrieval, intent-based querying, and guardrails.
- **Data teams** building RAG applications that need to query SQL databases, vector stores, and APIs through natural language.
- **Researchers & tinkerers** exploring local-first stacks, evaluating different foundation models, or building multimodal AI applications.

Have a story or feature request? [Open an issue](https://github.com/schmitech/orbit/issues) or add it to the [Roadmap](docs/roadmap/README.md).

---

## How to Use

### Prerequisites

- Python 3.12+ (for running the server or CLI locally)
- Node.js 18+ and npm (for the React chat app)
- Docker 20.10+ and Docker Compose 2.0+ (if you prefer containers)
- Optional: MongoDB (only needed if using MongoDB backend instead of default SQLite)
- Optional: Redis cache and vector DB (Chroma, Qdrant, Pinecone, Milvus, etc.)

### Installation Instructions

```bash
# Download the latest release archive
curl -L https://github.com/schmitech/orbit/releases/download/v2.0.0/orbit-2.0.0.tar.gz -o orbit-2.0.0.tar.gz
tar -xzf orbit-2.0.0.tar.gz
cd orbit-2.0.0

# Add API keys if using proprietary services like OpenAI, Cohere, Anthropic, etc
cp env.example .env

# Install packages
./install/setup.sh

# Activate Python environment
source venv/bin/activate

# Get a local GGUF model (models are downloaded from Hugging Face)
# You can select a different model from the list below
# Available GGUF models: gemma3-270m, gemma3-1b, tinyllama-1b, phi-2, mistral-7b, granite4-micro, embeddinggemma-300m
# You can add your own models by editing install/gguf-models.json
./install/setup.sh --download-gguf granite4-micro

# (Optional) Choose a different AI provider and model
# You can override the default provider/model by editing config/adapters.yaml
# Find the "simple-chat" adapter and modify the inference_provider and model fields
# Available providers from config/inference.yaml: ollama, ollama_cloud, llama_cpp, gemini, groq, 
#   deepseek, openai, mistral, anthropic, cohere, xai, openrouter, together, and more
# Example: To use OpenAI instead of llama_cpp, set:
#   inference_provider: "openai"
#   model: "gpt-5"
# Note: Make sure the provider is enabled in config/inference.yaml and you have the required API keys in .env

# Start the ORBIT server
./bin/orbit.sh start 

# Check the logs
cat ./logs/orbit.log
```

Browse to `http://localhost:3000/dashboard` to monitor the ORBIT server:
<div align="center">
  <img src="/docs/images/orbit-dashboard.png" alt="ORBIT Dashboard" width="800"/>
  <br/>
  <i>ORBIT Dashboard: Monitor, search, and configure your environment.</i>
</div>

### Talk to ORBIT from the CLI

```bash
# Step 1: Login to ORBIT with default admin credentials (admin / admin123):
./bin/orbit.sh login

# Step 2: Generate an API key (copy the key that's output)
# For basic chat, use simple-chat adapter:
./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "Conversational Chatbot" \
  --prompt-file ./prompts/default-conversational-adapter-prompt.txt \
  --prompt-name "Conversational Prompt"

# For file upload and multimodal support, use conversational-multimodal adapter instead:
# Note: This adapter must be enabled in config/adapters.yaml first (set enabled: true for "simple-chat-with-files")
# ./bin/orbit.sh key create \
#   --adapter simple-chat-with-files \
#   --name "Multimodal Chatbot" \
#   --prompt-file ./prompts/default-conversational-adapter-prompt.txt \
#   --prompt-name "Conversational Prompt"

# This will output something like: orbit_0sXJhNsK7FT9HCGEUS7GpkhtXvVOEMX6

# Step 3 (Optional): Rename the API key for easier reference
# Replace YOUR_ACTUAL_KEY with the key from Step 2
./bin/orbit.sh key rename --old-key YOUR_ACTUAL_KEY --new-key default-key

# Step 4: Start chatting
# Replace YOUR_ACTUAL_KEY below with the API key you copied from Step 2
# Note: On first run, you will see a prompt asking to create a config file. Type 'y' to proceed.
orbit-chat --url "http://localhost:3000" --api-key YOUR_ACTUAL_KEY
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/6ea2ba0c-eb59-43be-9bbd-0ff0dd90b587" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Using the <code>orbit-chat</code> CLI. Run <code>orbit-chat -h</code> for options.</i>
</div>

### Spin up the React Chat app

```bash
# Step 1: Navigate to the chat app directory
cd clients/chat-app

# Step 2: Copy the environment example file and configure it
cp env.example .env.local

# Step 3: Edit .env.local and adjust the settings:
# - Set VITE_API_URL to your ORBIT server URL (default: http://localhost:3000)
# - Set VITE_DEFAULT_KEY to your API key (or leave as default-key if you renamed your key)
# - Adjust other settings as needed (see env.example for all options)
# 
# Note: File upload functionality only works with the conversational-multimodal adapter.
# Make sure your API key is created with --adapter conversational-multimodal (not simple-chat).

# Step 4: Install dependencies
npm install

# Step 5: Start the development server
npm run dev
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/9b61911e-f0c3-464e-a3a5-79c4645415c2" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Chatting with ORBIT using the React client.</i>
</div>

#### Next steps

- Create an API key tied to the adapter you want to expose (`./bin/orbit.sh key create`). A default prompt file is available at `./prompts/default-conversational-adapter-prompt.txt`.
- Enable or customize adapters in `config/adapters.yaml` and redeploy to connect new datasources.
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
