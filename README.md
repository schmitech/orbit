<div align="center">
  <img src="docs/images/orbit.png" width="400" alt="ORBIT">
</div>
<div align="center">
  <h2><strong>Open Retrieval-Based Inference Toolkit</strong></h2>
  
  <p>
    <a href="#quick-start">Quick Start</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#web-chatbot-widget">Widget</a> • 
    <a href="#documentation">Docs</a> •
  </p>
</div>


ORBIT is a modular, self-hosted toolkit that provides a unified API for open-source AI inference models. ORBIT enables you to run AI models on your own infrastructure, maintaining full control over your data while reducing dependency on external AI services. The project is actively maintained by [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/).

![ORBIT Chat Demo](docs/images/orbit-chat-gui.gif)


## Minimum Requirements

- A device (Windows/Linux or Mac) with 16GB memory, GPU preferred
- Python 3.12+
- MongoDB (required for RAG mode and chat history)
- Redis (optional for caching)
- Elasticsearch (optional for logging)

## Quick Start

```bash
# Download and extract the latest release
curl -L https://github.com/schmitech/orbit/releases/download/v1.1.2/orbit-1.1.2.tar.gz
tar -xzf orbit-1.1.2.tar.gz
cd orbit-1.1.2

# Add --help for command options
./install.sh

# Activate virtual environment
source venv/bin/activate

# Get a GGUF model
python ./bin/download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "*q4_0.gguf" --output-dir "./gguf"
```

Edit config.yaml specify `llama_cpp` as inference provider and your GGUF model.
```yaml
general:
  port: 3000
  verbose: false
  inference_provider: "llama_cpp"
inference:
  llama_cpp:
    model_path: "gguf/tinyllama-1.1b-chat-v1.0.Q4_0.gguf"
    chat_format: "chatml"
```

If you want to keep conversation history, you will need a MongoDB instance. This is configurable under the `internal_services` section in config.yaml.

```bash
# Copy .env.example to .env and add your MongoDB connection parameters:
INTERNAL_SERVICES_MONGODB_HOST=localhost
INTERNAL_SERVICES_MONGODB_PORT=27017
INTERNAL_SERVICES_MONGODB_USERNAME=mongo-user
INTERNAL_SERVICES_MONGODB_PASSWORD=mongo-password
```

Enable in config.yaml:
```yaml
chat_history:
  enabled: true
```

For more details about conversation history configuration and usage, see [Conversation History Documentation](docs/conversation_history.md)

### Starting the Inference server:
```bash
# Logs under ./logs/orbit.log, use --help for options.
./bin/orbit.sh start

# Run ORBIT client (default url is http://localhost:3000, use --help for options):
orbit-chat 
```

![ORBIT Chat Demo](docs/images/orbit-chat.gif)


## Architecture
<p align="left">
  <img src="docs/images/orbit-diagram.png" width="800" alt="ORBIT Architecture" />
</p>

### SQL Adapter

RAG (Retrieval-Augmented Generation) mode enhances the model's responses by integrating your knowledge base into the context. This enriches the pre-trained foundation model with your specific data. 

The sample SQLite adapter showcases how ORBIT can be used for:
- FAQ systems
- Knowledge base queries
- Question-answering applications
- Document-based Q&A

### Running ORBIT with SQLite Adapter
You need an instance of MongoDB for this work. MongoDB is required when using ORBIT with retrieval adapters. Change config.yaml as follows:
```yaml
general:
  port: 3000
  verbose: false
  inference_provider: "llama_cpp"
  inference_only: false
  adapter: "qa-sql"

# Make sure adapter exists
adapters:
  - name: "qa-sql"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"
    config:
      confidence_threshold: 0.3
      max_results: 5
      return_results: 3

# Specify DB location location
datasources:
  sqlite:
    db_path: "sample_db/sqlite/sqlite_db"      
```

Restart the server:
```bash
./bin/orbit.sh restart --delete-logs
```
Load the sample question/answers sets from `./sample_db/city-qa-pairs.json`. RAG mode requires MongoDB enabled. Use the same settings described in the previous section to set up the MongoDB service.

```bash
# The DB creation scripts are located under /sample_db/sqlite/
./sample_db/setup-demo-db.sh sqlite

# Use the key generated from the previous command
orbit-chat --url http://localhost:3000 --api-key orbit_1234567ABCDE
```

## Web Chatbot Widget

ORBIT provides a customizable chatbot widget that can be easily integrated into any website. The widget offers a responsive interface with theming options and features. The widget is available as an npm package at [@schmitech/chatbot-widget](https://www.npmjs.com/package/@schmitech/chatbot-widget). Project details and build instructions can be found at [ORBIT Chat Widget](https://github.com/schmitech/orbit/tree/main/clients/chat-widget).


## Documentation

For more detailed information, please refer to the following documentation in the [Docs](docs/) folder.

### Getting Started & Configuration
- [Server Configuration](docs/server.md) - Server setup and configuration guide
- [Configuration Reference](docs/configuration.md) - Complete configuration options and settings
- [API Keys Management](docs/api-keys.md) - Authentication and API key setup
- [Docker Deployment](docs/docker-deployment.md) - Containerized deployment guide
- [Chroma Setup](docs/chroma-setup.md) - Vector database configuration

### Retrieval & Adapters  
- [Adapters Overview](docs/adapters.md) - Understanding ORBIT's adapter system
- [SQL Retriever Architecture](docs/sql-retriever-architecture.md) - Database-agnostic SQL retrieval system
- [Vector Retriever Architecture](docs/vector-retriever-architecture.md) - Vector-based semantic search
- [File Adapter Architecture](docs/file-adapter-architecture.md) - File-based knowledge integration

### Features & Capabilities
- [Conversation History](docs/conversation_history.md) - Chat history and session management
- [Language Detection](docs/language_detection.md) - Multi-language support and detection
- [MCP Protocol](docs/mcp_protocol.md) - Model Context Protocol implementation

### Roadmap & Future Development
- [Development Roadmap](docs/roadmap/README.md) - Strategic direction and planned enhancements
- [Concurrency & Performance](docs/roadmap/concurrency-performance.md) - Scaling to handle thousands of concurrent requests
- [LLM Guard Security](docs/roadmap/llm-guard-integration.md) - Enterprise-grade AI security and threat protection
- [Async Messaging & Multi-Modal](docs/roadmap/async-messaging-integration.md) - Message queues and multi-modal processing
- [Notification Service](docs/roadmap/notification-service-integration.md) - Multi-channel communication system

## Contributing

Contributions are welcome! Please read our [Code of Conduct](CODE_OF_CONDUCT.md) for details the process for submitting pull requests.

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.