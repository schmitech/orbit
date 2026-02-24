<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo-transparent.png" alt="ORBIT Logo" width="500"/>
  </a>
</div>

<br/>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://github.com/schmitech/orbit" target="_blank">
    <img src="https://img.shields.io/github/stars/schmitech/orbit?style=social&label=Star" alt="GitHub stars">
  </a>
</p>

# ORBIT: The Unified AI Gateway
**Open Retrieval-Based Inference Toolkit**

**Connect 20+ LLM providers and your data (SQL, Vector, NoSQL, APIs, etc.) through one API.**

ORBIT is a self-hosted gateway that eliminates vendor lock-in and glue code. It unifies the fragmented components—LLMs, databases, and voice engines—into a single interface.

[**Try the Sandbox**](https://orbitsandbox.dev/) | [**API Reference**](https://orbit.schmitech.ai/redoc) | [**Docker Guide**](docker/README.md)

---

### ⚡ Quick Start: Chat via Curl
Try our hosted API immediately with no setup:

```bash
curl -X POST https://orbit.schmitech.ai/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: test-session' \
  -d '{
    "messages": [{"role": "user", "content": "What is ORBIT?"}],
    "stream": false
  }'
```

---

### 🚀 Key Capabilities

*   **Unified API:** Swap OpenAI, Anthropic, Gemini, Groq, or local models (Ollama/vLLM) via config only.
*   **Agentic AI & MCP:** Fully compatible with the **Model Context Protocol (MCP)**. Use ORBIT as a tool provider for agentic applications like OpenClaw, Claude Desktop, and more.
*   **Native RAG:** Connect Postgres, MongoDB, Elasticsearch, or Pinecone. Query your data using natural language.
*   **Voice-First:** Real-time, full-duplex speech-to-speech with interruption handling via PersonaPlex.
*   **Production Ready:** Built-in RBAC, rate limiting, audit logging, and circuit breakers.
*   **Privacy First:** Self-host on your own infrastructure to maintain full data sovereignty.

---

### 🛠️ One Gateway, Many Clients

| Client | Link | Description |
| :--- | :--- | :--- |
| **Web Chat** | [ORBIT Chat](clients/orbitchat/) | React UI. |
| **CLI** | `pip install schmitech-orbit-client` | Chat directly from your terminal. |
| **Mobile** | [ORBIT Mobile](clients/orbit-mobile/) | iOS & Android app built with Expo. |
| **SDKs** | [Node SDK](clients/node-api/) | Or use any standard OpenAI-compatible SDK. |

---

### 📦 Deployment

**Docker (Instant)**
```bash
docker run -d -p 3000:3000 -p 5173:5173 schmitech/orbit:basic
```

**Stable Release (Recommended)**
```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.5.0/orbit-2.5.0.tar.gz -o orbit-2.5.0.tar.gz
tar -xzf orbit-2.5.0.tar.gz && cd orbit-2.5.0

cp env.example .env && ./install/setup.sh
source venv/bin/activate
./bin/orbit.sh start && cat ./logs/orbit.log
```

---

### 🧩 Supported Integrations

**Inference:** OpenAI, Anthropic, Google Gemini, Groq, DeepSeek, Mistral, AWS Bedrock, Azure, Together, Ollama, vLLM, llama.cpp.

**Data Adapters:** PostgreSQL, MySQL, MongoDB, Elasticsearch, DuckDB, Chroma, Qdrant, Pinecone, Milvus, Weaviate.

---

### 📚 Resources & Support

*   [Step-by-Step Tutorial](docs/tutorial.md) – Learn how to chat with your own data in minutes.
*   [Articles & Case Studies](https://schmitech.ai/en/orbit/articles) – Deep dives into configuration and real-world use cases.
*   [Documentation](docs/) – Full architecture and setup guides.
*   [GitHub Issues](https://github.com/schmitech/orbit/issues) – Bug reports and feature requests.
*   [Discussions](https://github.com/schmitech/orbit/discussions) – Community help and roadmap.

> ⭐ **Help ORBIT grow:** [Star the repo](https://github.com/schmitech/orbit) to support the project and get notified of new adapters!

## 📄 License

Apache 2.0 – see [LICENSE](LICENSE).
