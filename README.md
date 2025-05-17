<div align="center">
  <img src="orbit.png" width="200" height="200" alt="ORBIT">
  
  <h1>ORBIT</h1>
  <h2><strong>Open Retrieval-Based Inference Toolkit</strong></h2>
  
  <p>
    <a href="#-key-features">Features</a> •
    <a href="#-quick-start">Quick Start</a> •
    <a href="#-installation">Installation</a> •
    <a href="#-usage">Usage</a> •
    <a href="#-license">License</a>
  </p>
</div>

## 🎯 Overview

ORBIT is a modular, self-hosted toolkit that provides a unified API for open-source AI inference models. It enables you to run AI models on your own infrastructure, maintaining complete control over your data while eliminating commercial API dependencies.

## Sovereignty and Data Control

ORBIT is designed with digital sovereignty in mind, offering several key advantages:

1. **Complete Data Control**: All data processing happens on your infrastructure, ensuring sensitive information never leaves your environment
2. **No External Dependencies**: By eliminating reliance on commercial AI APIs, you maintain full control over your AI capabilities
3. **Compliance Ready**: Self-hosted deployment makes it easier to comply with data residency requirements and privacy regulations
4. **Transparency**: Open-source nature allows full visibility into the system's operations and data handling
5. **Customization**: Ability to modify and adapt the system to meet specific organizational or national requirements

This makes ORBIT particularly valuable for:

- Government agencies requiring sovereign AI capabilities
- Organizations with strict data privacy requirements
- Countries implementing digital sovereignty initiatives
- Enterprises needing to maintain control over their AI infrastructure

## 🚀 Quick Start

### System Requirements

- Python 3.12+
- MongoDB for API key management
- Ollama for inference (other services supported, see config.yaml)
- ChromaDB or SQLite (other engines supported)
- Optional: GPU for accelerated inference
- Optional: Elasticsearch for logging

### 1. Install and configure MongoDB
Follow MongoDB installation guide: https://www.mongodb.com/docs/manual/installation/

Update MongoDB configuration in `config.yaml`. Credentials are loaded from .env file (copy from template .env.example)

```yaml
internal_services:
  mongodb:
    host: "localhost"
    port: 27017
    database: "orbit"
    apikey_collection: "api_keys"
    username: ${INTERNAL_SERVICES_MONGODB_USERNAME}
    password: ${INTERNAL_SERVICES_MONGODB_PASSWORD}
```

### 2. Server Setup

```bash
# Clone the repository
git clone https://github.com/schmitech/orbit.git
cd orbit

# Install dependencies (see ./install/dependencies.ymol for installation options)
./install/setup.sh --profile minimal # Add --download-gguf flag to pull a GGUF file if using llama-cpp

# Activate virtual environment
source venv/bin/activate
```

### 3. Setup Inference Provider 

For local development you can use either Ollama (recommended) or llama-cpp python lib.

#### Ollama Instructions:

https://ollama.com/download

```bash
# Download the models
ollama pull gemma3:1b
ollama pull nomic-embed-text
```

#### Llama-cpp instructions
First install the dependencies and GGUF file (by default t downloads Gemma3:1b from Hugging Face, see ./install.stup.sh for details, you can change the download command to use your preferred model):

./install/setup.sh --profile minimal --download-gguf

### 4. Configuration
Edit config.yaml with default settings:
```yaml
general:
  port: 3000
  verbose: true
  https:
    enabled: false
    port: 3443
    cert_file: "./cert.pem"
    key_file: "./key.pem"
  session_id:
    header_name: "X-Session-ID"
    required: true
  inference_provider: "ollama" #or llama_cpp
  language_detection: false
  inference_only: false
  adapter: "sqllite
```

### 5. Launch Server
```bash
./bin/orbit.sh start
```

### 6. Server Management
```bash
# Check server status
./bin/orbit.sh status

# Stop the server
./bin/orbit.sh stop

# Restart the server (use flag --delete-logs if you want to remove the logs file whenever the server restarts)
./bin/orbit.sh restart
```

### 7. API Key Management
```bash
# Create an API key for a collection. Only needed to RAG operatons, here's an example:
./bin/orbit.sh key create --collection city --name "Ciy Assistant" --prompt-file prompts/examples/city/city-assistant-normal-prompt.txt  --prompt-name "City Assistant Prompt"

# List API keys
./bin/orbit.sh key list

# Test an API key
./bin/orbit.sh key test --key your-api-key
```

### 8. Sample Database Setup
```bash
# For SQLite database
./install/setup-demo-db.sh sqlite

# For Chroma database (requires Ollama running with nomic-embed-text model)
./install/setup-demo-db.sh chroma
```

### 9. Client Setup

#### Python Client

```bash
pip install schmitech-orbit-client

# The chat client implementation can be found in /clients/python/schmitech_orbit_client/chat_client.py
orbit-chat --url http://localhost:3000 --api-key orbit-api-key
```

### Configuration

The system is configurable through a YAML configuration file, allowing you to:

- Select and configure inference providers
- Choose embedding and vector database backends
- Set up safety and reranking services
- Configure logging and monitoring
- Manage API authentication
- Set up HTTPS/SSL
- Configure system resources and threading

## 🤝 Contributing

Contributions are welcome! Please read our [Code of Conduct](CODE_OF_CONDUCT.md) for details the process for submitting pull requests.

## 📃 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.