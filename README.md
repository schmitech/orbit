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

Update MongoDB configuration in `config.yaml`:

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

# Install dependencies
./bin/setup.sh

# Activate virtual environment
source venv/bin/activate
```

### 3. Install Ollama
https://ollama.com/download

```bash
# Download the models
ollama pull gemma3:1b
ollama pull nomic-embed-text
```

### 4. Configuration
Copy and configure the main config file:
```bash
# The config.yaml file is located in the project root
# Edit config.yaml to adjust settings for your environment
```

### 5. Launch Server
```bash
# Start the server
./bin/start.sh

# Or use the control script
./bin/orbit.sh start
```

### 6. Server Management
```bash
# Check server status
./bin/orbit.sh status

# Stop the server
./bin/orbit.sh stop

# Restart the server
./bin/orbit.sh restart
```

### 7. API Key Management
```bash
# Create an API key for a collection
./bin/orbit.sh key create --collection docs --name "My Client"

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

The script will:
- Set up the database (SQLite or Chroma)
- Create necessary collections
- Generate API keys for the collections
- Provide instructions for testing the setup

Server will be available at `http://localhost:3000`

### 9. Client Setup

#### Python Client

```bash
pip install schmitech-orbit-client

# The chat client implementation can be found in /clients/python/schmitech_orbit_client/chat_client.py
orbit-chat --url http://localhost:3000
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

# Orbit Adapter Roadmap

## Current Adapters
Orbit currently supports the following adapters:
- **qa-sqlite**: SQLite-based retriever for question answering
- **qa-chroma**: Chroma vector database retriever for question answering

## Future Adapter Roadmap

### Enterprise Data Integration Adapters
Connect Orbit with enterprise systems to provide AI capabilities on organizational data.

| Adapter | Description | Priority |
|---------|-------------|----------|
| SAP Connector | Integrate with SAP ERP systems for business process intelligence | High |
| Salesforce Adapter | Connect with CRM data to enhance customer interactions | High |
| Microsoft 365 Integration | Access SharePoint, Teams, and Office data for internal knowledge | Medium |
| Enterprise Database Connectors | Support for Teradata, Oracle, SQL Server to query enterprise data | Medium |

### Specialized Knowledge Adapters
Domain-specific adapters for industries with specialized requirements.

| Adapter | Description | Priority |
|---------|-------------|----------|
| Legal Document Analyzer | Process legal documents with citation support and compliance features | High |
| Financial Data Adapter | Handle financial reports with regulatory compliance and data security | High |
| Healthcare Knowledge Base | Process medical literature and patient data with HIPAA compliance | Medium |
| Scientific Research Connector | Access and query scientific papers and research databases | Medium |

### Multimodal Adapters
Extend Orbit beyond text to handle various data types.

| Adapter | Description | Priority |
|---------|-------------|----------|
| Document OCR Processor | Extract text from images and documents for analysis | High |
| Audio Transcription | Convert meeting recordings and calls to searchable text | Medium |
| Video Content Analysis | Extract insights from video content | Low |
| Chart/Graph Interpreter | Understand and explain visual data representations | Medium |

### Real-time Adapters
Connect to live data sources for up-to-date intelligence.

| Adapter | Description | Priority |
|---------|-------------|----------|
| Market Data Connector | Access real-time financial market data | High |
| Customer Support Integration | Connect to live customer service platforms | Medium |
| IoT Sensor Data | Process information from connected devices and sensors | Medium |
| Social Media Monitor | Track brand mentions and sentiment in real time | Low |

### Advanced Analytics Adapters
Add sophisticated analytical capabilities to Orbit.

| Adapter | Description | Priority |
|---------|-------------|----------|
| Time-series Forecasting | Predict future trends based on historical data | High |
| BI Dashboard Connector | Integrate with business intelligence platforms | Medium |
| Anomaly Detection | Identify unusual patterns in operational data | Medium |
| Sentiment Analysis | Analyze customer feedback and communications | Low |

### Workflow Automation Adapters
Integrate AI capabilities into business processes.

| Adapter | Description | Priority |
|---------|-------------|----------|
| Business Process Modeling | Model and optimize workflows with AI assistance | High |
| Approval Workflow Integration | Streamline document and request approvals | Medium |
| Document Generation | Create reports and documents from templates and data | Medium |
| Task Management | AI-assisted project and task management | Low |

## Implementation Guidelines

Each new adapter should follow Orbit's adapter pattern:

```yaml
- name: "adapter-name"
  type: "retriever"
  datasource: "data-source-type"
  adapter: "adapter-type"
  implementation: "path.to.implementation.Class"
  config:
    # Adapter-specific configuration options
    confidence_threshold: 0.5
    max_results: 5
    return_results: 3
    # Other adapter-specific settings
```

## Development Priorities

1. Focus first on enterprise integrations that unlock organizational data
2. Prioritize industry-specific adapters based on customer demand
3. Develop multimodal capabilities to handle diverse data types
4. Add real-time adapters for time-sensitive applications
5. Implement advanced analytics for deeper insights
6. Create workflow automation to streamline business processes

## Contributing

Interested in developing a new adapter? Please follow these steps:
1. Check the roadmap to see if your adapter is already planned
2. Open an issue to discuss the adapter requirements
3. Follow the adapter implementation guidelines
4. Submit a pull request with thorough documentation

---

This roadmap is a living document and will be updated as we gather more feedback from customers and the community.