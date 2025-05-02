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

## 🌟 Key Features

- **🔒 Privacy First**: All data remains within your infrastructure
- **🔄 Flexible Deployment**: Deploy on cloud, on-premise, or hybrid environments
- **🛠 Full Customization**: Adapt to your specific domain needs
- **🔓 No Vendor Lock-in**: Complete control over inference models and data
- **🚀 High Performance**: Optimized for various hardware configurations
- **🔍 RAG Support**: Built-in support for Retrieval-Augmented Generation
- **🔐 API Key Management**: Secure access control and authentication
- **📊 Monitoring**: Comprehensive logging and analytics

## 💼 Use Cases

- **🎯 Customer Support**: AI-powered support with your knowledge base
- **📚 Knowledge Management**: Intelligent document Q&A systems
- **🎓 Education**: Interactive learning assistants
- **🏥 Healthcare**: HIPAA-compliant medical information systems
- **💰 Financial Services**: Secure financial advisory assistants
- **⚖️ Legal Services**: Confidential legal research tools

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- MongoDB
- Ollama
- Node.js 18+ (for TypeScript client)

### 1. Server Setup

```bash
# Clone the repository
git clone https://github.com/schmitech/orbit.git
cd orbit/server

# Install dependencies
./setup.sh
source venv/bin/activate

# Create config file form template.
cp config.yaml.example config.yaml

# Configure env variables (optional)
cp .env.example .env
```
### 3. Install Ollama
https://ollama.com/download

```bash
# Download the models
ollama pull gemma3:1b
ollama pull nomic-embed-text
```

### 2. Sample Database Setup

```bash
# Create demo database
python ../utils/sqllite/rag_cli.py setup --db-path ./sqlite_db --data-path ../utils/sample-data/city-qa-pairs.json

# Or chroma with vectro embeddings (embeddings must be enabled in config.yaml):
python ../utils/chroma/scripts/create_qa_pairs_collection.py city ../utils/sample-data/city-qa-pairs.json --local --db-path ./chroma_db

# Install and configure MongoDB
# Follow MongoDB installation guide: https://www.mongodb.com/docs/manual/installation/
```

Update MongoDB configuration in `/server/config.yaml`:

```yaml
mongodb:
  host: "localhost"
  port: 27017
  database: "orbit"
  apikey_collection: "api_keys"
  username: ${INTERNAL_SERVICES_MONGODB_USERNAME}
  password: ${INTERNAL_SERVICES_MONGODB_PASSWORD}
```

### 3. Launch Server

```bash
cd server
./start.sh
```

Server will be available at `http://localhost:3000`

### 4. API Key Setup

```bash
# Create an API key
python ./admin/api_key_manager.py --url http://localhost:3000 create \
  --collection city \
  --name "City Assistant" \
  --prompt-file ../prompts/examples/city/city-assistant-prompt.txt \
  --prompt-name "Municipal Assistant Prompt"
```

### 5. Client Setup

#### Python Client

```bash
cd clients/python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python chat_client.py --url http://localhost:3000 --api-key your-api-key
```

#### TypeScript/JavaScript Client

```bash
cd clients/typescript/api
npm install
npm run build

# Use in your project
npm link @schmitech/chatbot-api
```

### Configuration

The system is highly configurable through a YAML configuration file, allowing you to:
- Select and configure inference providers
- Choose embedding and vector database backends
- Set up safety and reranking services
- Configure logging and monitoring
- Manage API authentication
- Set up HTTPS/SSL
- Configure system resources and threading

### System Requirements

- Python 3.12+
- MongoDB for API key management
- Vector database (ChromaDB by default)
- Optional: GPU for accelerated inference
- Optional: Elasticsearch for advanced logging

## 📚 Documentation

- [Server Documentation](server/README.md)
- [Admin Tools Guide](server/admin/README.md)
- [TypeScript Client API](clients/typescript/api/README.md)

## 🛠 Advanced Configuration

### HTTPS Setup

1. Install Certbot:
```bash
sudo apt-get update
sudo apt-get install certbot
```

2. Obtain certificate:
```bash
sudo certbot certonly --manual --preferred-challenges http -d your-domain.com
```

3. Configure in `config.yaml`:
```yaml
general:
  https:
    enabled: true
    port: 3443
    cert_file: "/path/to/fullchain.pem"
    key_file: "/path/to/privkey.pem"
```

### Local LLM Setup

Configure llama.cpp in `config.yaml`:

```yaml
general:
  inference_provider: "llama_cpp"

inference:
  llama_cpp:
    model_path: "models/tinyllama-1.1b-chat-v1.0.Q4_0.gguf"
    chat_format: "chatml"
    temperature: 0.1
    n_ctx: 4096
```

## 📊 Monitoring

ORBIT provides comprehensive logging through:

- File-based logging (JSON format)
- Elasticsearch integration (optional)
- Health check endpoints
- Performance metrics

## 🤝 Contributing

Contributions are welcome! Please read our [Code of Conduct](CODE_OF_CONDUCT.md) for details the process for submitting pull requests.

## 📃 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.