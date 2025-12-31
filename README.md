<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo-transparent.png" alt="ORBIT Logo" width="500" style="border: none; outline: none; box-shadow: none;"/>
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

# ORBIT – One API. Any LLM. Your data.

Stop rewriting your app every time you switch LLMs. ORBIT unifies **20+ AI providers** with your databases, vector stores, and APIs—all through one self-hosted gateway.

**Ship faster. Stay portable. Keep your data private.**

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=for-the-badge&logo=github&label=Star%20on%20GitHub&color=yellow" alt="Star on GitHub"></a>
</p>

- **Questions?** Open an [issue](https://github.com/schmitech/orbit/issues)
- **Updates:** Check the [changelog](CHANGELOG.md)
- **Commercial Support:** [schmitech.ai](https://schmitech.ai/en)
- **Maintained by:** [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/)

## Table of Contents

- [✨ Highlights](#highlights)
- [🛠️ Why ORBIT](#why-orbit)
- [⭐ Why Star This Repo?](#-why-star-this-repo)
- [🚀 Quick Start](#quick-start)
- [💬 Chat Clients](#-chat-clients)
- [🏢 Commercial Support](#commercial-support)
- [📖 Documentation](#documentation)
- [📄 License](#license)

---

## Highlights

- **Unified AI gateway** supporting 20+ LLM providers (OpenAI, Anthropic, Gemini, Cohere, Mistral, Ollama, Groq, DeepSeek, xAI, OpenRouter, and more) plus local models via Ollama, llama.cpp, and vLLM.
- **Data integration** with RAG adapters for SQL databases (PostgreSQL, MySQL, SQLite, DuckDB, Oracle, SQL Server, Cassandra), vector stores (Chroma, Qdrant, Pinecone, Milvus, Elasticsearch, Redis), MongoDB, HTTP APIs, and file uploads with multimodal support.
- **Intelligent query processing** with intent-based adapters that translate natural language to SQL, Elasticsearch queries, MongoDB queries, and HTTP API calls.
- **Vision capabilities** with support for vLLM, OpenAI, Gemini, and Anthropic vision models for image analysis and OCR.
- **Secure by default** with token-based auth, role-aware API keys, and pluggable content moderation.
- **Ready for teams** thanks to batteries-included clients (CLI, React widget, Node/Python SDKs).

## Why ORBIT

- **Avoid vendor lock-in** by switching between LLM providers without rewriting your application code—change providers in configuration, not code.
- **Keep your data private** with support for on-prem deployments, air-gapped installs, and local models that never leave your infrastructure.
- **Query your data naturally** in any language instead of writing SQL, Elasticsearch queries, or API calls—intent-based adapters handle the translation automatically.

### Built for

- **Platform & infra teams** who need a stable control plane for LLM workloads across multiple providers and data sources.
- **Product teams** shipping AI copilots that depend on reliable retrieval, intent-based querying, and guardrails.
- **Data teams** building RAG applications that need to query SQL databases, vector stores, and APIs through natural language.
- **Researchers & tinkerers** exploring local-first stacks, evaluating different foundation models, or building multimodal AI applications.

---

## 🌐 Who Uses ORBIT

<div align="center">
  <a href="https://www.civicchat.ca">
    <img src="https://img.shields.io/badge/Civic_Chat-Powered_by_ORBIT-blue?style=for-the-badge" alt="Civic Chat">
  </a>
</div>

<a href="https://www.civicchat.ca" target="_blank"><strong>Civic Chat</strong></a> — An AI-powered tool for exploring Canadian open data across municipal, provincial, and federal levels of government. Civic Chat uses ORBIT's intent-based adapters to translate natural language queries into SQL and API calls, enabling citizens to explore public datasets through conversation.

> *Using ORBIT in production? <a href="https://schmitech.ai/en/contact" target="_blank">Let us know</a> and we'll feature your project here.*


---

## ⭐ Why Star This Repo?

Your star isn't just a vanity metric—it directly helps the project:

- **Visibility** – Stars help other developers discover ORBIT in search results
- **Releases** – Get notified when we ship new features and providers
- **Open source** – Support independent AI infrastructure development

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=for-the-badge&logo=github&label=Star%20ORBIT&color=yellow" alt="Star ORBIT"></a>
</p>

---

## 🚀 Deployment Guide

There are three ways to get started with ORBIT.

### Option 1: Docker (Fastest)

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 5173:5173 schmitech/orbit:basic
```

Open **http://localhost:5173** in your browser and start chatting.

The Docker image includes:
- ORBIT server (API on port 3000)
- orbitchat web app (browser UI on port 5173)
- Ollama with pre-pulled models
- Pre-configured API key (no setup needed)

For more Docker options, see [docker/README.md](docker/README.md).

### Option 2: Download Latest Release

Download and install the latest stable release. Best for production deployments.

#### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- **AI Provider** (choose one or more):
  - Local: [Ollama](https://ollama.com/), [llama.cpp](https://github.com/ggerganov/llama.cpp), or [vLLM](https://github.com/vllm-project/vllm)
  - Cloud: Your own API keys for OpenAI, Anthropic, Cohere, Gemini, Mistral, etc.
- Optional: MongoDB, Redis, and a vector DB (Chroma, Qdrant, etc.)

#### 1. Download and Extract Release

```bash
# Download the latest release archive
# Replace v2.2.0 with the latest version from https://github.com/schmitech/orbit/releases
curl -L https://github.com/schmitech/orbit/releases/download/v2.2.0/orbit-2.2.0.tar.gz -o orbit-2.2.0.tar.gz

tar -xzf orbit-2.2.0.tar.gz

cd orbit-2.2.0
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

#### 3. Install Ollama and Download a Model

1. **Install Ollama** (if not already installed):
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Windows: Download from https://ollama.com/download
   ```

2. **Pull the model**:
   ```bash
   ollama pull granite4:1b
   ```

3. **Configure Model**:
   - The default model is configured as `granite4:1b` in `config/adapters/passthrough.yaml` and `config/adapters/multimodal.yaml`.
   - You can configure model settings in `config/ollama.yaml`.

#### 4. Start the Server

```bash
# Start the ORBIT server
./bin/orbit.sh start 

# Check the logs
cat ./logs/orbit.log
```

#### 5. Access the Dashboard

Once the server is running, open your browser and navigate to:

**🖥️ Dashboard:** [`http://localhost:3000/dashboard`](http://localhost:3000/dashboard)

The dashboard provides a visual interface to manage adapters, monitor conversations, and configure your ORBIT instance.

<div align="center">
  <video src="https://github.com/user-attachments/assets/ec9bda9b-3b86-488f-af16-ec8e9d964697" controls width="100%">
    Your browser does not support the video tag.
  </video>
  <br/>
  <em>The ORBIT Dashboard in action</em>
</div>

### Option 3: Clone from Git (Development)

For contributing or modifying ORBIT, clone and run from source.

#### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker 20.10+ and Docker Compose 2.0+
- **AI Provider** (choose one or more):
  - Local: [Ollama](https://ollama.com/), [llama.cpp](https://github.com/ggerganov/llama.cpp), or [vLLM](https://github.com/vllm-project/vllm)
  - Cloud: Your own API keys for OpenAI, Anthropic, Cohere, Gemini, Mistral, etc.
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
  <video src="https://github.com/user-attachments/assets/97a872f3-0752-4c22-a690-bd75635a0741" controls>
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
  <video src="https://github.com/user-attachments/assets/a51df9ca-a0bf-494c-8fdf-c922501f19e1" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Chatting with ORBIT using the React client.</i>
</div>

### Using the Embeddable Chat Widget

Add an AI chatbot to any website with the [@schmitech/chatbot-widget](https://www.npmjs.com/package/@schmitech/chatbot-widget). Supports floating and embedded modes with full theme customization.

```html
<!-- Add to your HTML -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.umd.js"></script>
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.css">

<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'http://localhost:3000',
      apiKey: 'YOUR_API_KEY',
      sessionId: 'session-' + Date.now(),
      widgetConfig: {
        header: { title: "ORBIT Assistant" },
        welcome: { title: "Hello! 👋", description: "How can I help you today?" }
      }
    });
  });
</script>
```

<div align="center">
  <video src="https://github.com/user-attachments/assets/13166436-d4e1-4753-8c6c-c665c34874d8" controls width="100%">
    Your browser does not support the video tag.
  </video>
  <br/>
  <em>The embeddable chat widget in action. Try the <a href="clients/chat-widget/theming-app/">theming app</a> to customize and preview your widget.</em>
</div>


For full configuration options, themes, and integration guides, see [clients/chat-widget/README.md](clients/chat-widget/README.md).

### Using the Node.js SDK

ORBIT provides a native TypeScript/JavaScript client for seamless integration into Node.js, web, or mobile applications.

```bash
npm install @schmitech/chatbot-api
```

```typescript
import { ApiClient } from '@schmitech/chatbot-api';

const client = new ApiClient({
    apiUrl: "http://localhost:3000",
    apiKey: "YOUR_API_KEY"
});

async function chat() {
    const stream = client.streamChat("How can I integrate ORBIT into my application?");
    for await (const chunk of stream) {
        process.stdout.write(chunk.text);
    }
}

chat();
```

### Using the OpenAI Python SDK

ORBIT exposes an OpenAI-compatible `/v1/chat/completions` endpoint, letting you use the official `openai` Python library with your ORBIT server as a drop-in backend.

```python
from openai import OpenAI

client = OpenAI(
    api_key="ORBIT_API_KEY",
    base_url="http://localhost:3000/v1"
)

completion = client.chat.completions.create(
    model="orbit",  # Value is required but ORBIT routes via your API key
    messages=[
        {"role": "system", "content": "You are a helpful ORBIT assistant."},
        {"role": "user", "content": "Summarize the latest deployment status."}
    ],
)

print(completion.choices[0].message.content)

# ORBIT-specific metadata (sources, threading info, audio, etc.) is available via completion.orbit
if completion.orbit.get("sources"):
    print("Sources:", completion.orbit["sources"])
```

Streaming works as well:

```python
stream = client.chat.completions.create(
    model="orbit",
    messages=[{"role": "user", "content": "Give me an onboarding checklist."}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

---

## 🗃️ Chat with Your Data

**[See the Tutorial](docs/tutorial.md)** – Set up the HR example in 5 minutes and start chatting with your data.

---

## Support the Project

Your support keeps ORBIT independent and focused on open-source innovation.

- ⭐ Star the repo to signal that ORBIT matters to you.
- 📣 Share a demo, blog, or tweet so other builders discover it.
- 🐛 Open issues and PRs—your feedback directly shapes the roadmap.

---

## Documentation

For more detailed information, please refer to the official documentation.

- [Tutorial: Chat with Your Data](docs/tutorial.md)
- [Installation Guide](docs/server.md)
- [Configuration](docs/configuration.md)
- [Authentication](docs/authentication.md)
- [RAG & Adapters](docs/adapters.md)
- [Development Roadmap](docs/roadmap/README.md)
- [Contributing Guide](CONTRIBUTING.md)

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
