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

### System Requirements

- Python 3.12+
- MongoDB for API key management
- Ollama for inference (other services supported, see config.yaml.example)
- ChromaDB or SqlLite (other engines supported)
- Optional: GPU for accelerated inference
- Optional: Elasticsearch for logging

### 1. Install and configure MongoDB
Follow MongoDB installation guide: https://www.mongodb.com/docs/manual/installation/

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

### 2. Server Setup

```bash
# Clone the repository
git clone https://github.com/schmitech/orbit.git
cd orbit/server

# Install dependencies
./setup.sh
source venv/bin/activate
```
### 3. Install Ollama
https://ollama.com/download

```bash
# Download the models
ollama pull gemma3:1b
ollama pull nomic-embed-text
```
### 4. Launch Server
```bash
cd server
./start.sh
```

### 5. Sample Database Setup
```bash
# For SQLite database
./setup-demo-db.sh sqlite

# For Chroma database (requires Ollama running with nomic-embed-text model)
./setup-demo-db.sh chroma
```

The script will:
- Set up the database (SQLite or Chroma)
- Create necessary collections
- Generate API keys for the collections
- Provide instructions for testing the setup

Server will be available at `http://localhost:3000`

### 6. Client Setup

#### Python Client

```bash
cd clients/python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python chat_client.py --url http://localhost:3000 --api-key your-api-key
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

## 📚 Documentation

- [Server Documentation](server/README.md)
- [Admin Tools Guide](server/admin/README.md)
- [TypeScript Client API](clients/typescript/api/README.md)

## 📊 Monitoring

ORBIT provides logging through:

- File-based logging (JSON format)
- Elasticsearch integration (optional)
- Health check endpoints

## 🤝 Contributing

Contributions are welcome! Please read our [Code of Conduct](CODE_OF_CONDUCT.md) for details the process for submitting pull requests.

## 📃 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.