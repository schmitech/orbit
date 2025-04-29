<div align="center">
  <img src="orbit.png" width="200" height="200" alt="ORBIT">
  
  # ORBIT: Open Retrieval-Based Inference Toolkit
</div>

ORBIT is a modular, self-hosted toolkit that provides a unified API for open-source AI inference models, enabling you to operate without paid APIs. Host AI models on your infrastructure, maintain control over your data, and eliminate commercial dependency.

---

## Why ORBIT?

Proprietary AI services often introduce limitations, pricing fluctuations, and policy changes impacting your operations. ORBIT gives you:

- **Privacy:** Data remains within your infrastructure.
- **Flexibility:** Deploy on cloud, on-premise, or hybrid environments.
- **Customization:** Fully adaptable to your specific domain needs.
- **No Vendor Lock-in:** Full control over your inference models and data.

---

## Key Use Cases

- **Customer Support:** Integrate AI with your organization's knowledge base.
- **Internal Knowledge Management:** Intelligent document-based Q&A systems.
- **Education:** Interactive learning assistants tailored to course materials.
- **Healthcare:** HIPAA-compliant medical information systems.
- **Financial Services:** Secure financial advisory assistants.
- **Legal Services:** Confidential legal research tools.

---

## Quick Start Guide

### Prerequisites

- Python 3.12+
- MongoDB
- Elasticsearch (optional for logging)

### Server Setup

```bash
cd server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### Create Demo DB

```bash
cd utils/sqlite
python rag_cli.py setup --data-path ../sample-data/city-qa-pairs.json
```

### Install MongoDB

https://www.mongodb.com/docs/manual/installation/

After starting mongodb, configure endpoint in /server/config.yaml under 'internal_services' section:

```yaml
  mongodb:
    host: "localhost"
    port: 27017
    database: "orbit"
    apikey_collection: "api_keys"
    username: ${INTERNAL_SERVICES_MONGODB_USERNAME}
    password: ${INTERNAL_SERVICES_MONGODB_PASSWORD}
```

### Launch Server

```bash
cd server
./start.sh
```

API available at `http://localhost:3000`

### API Key Setup

You need an API key to use the client APIs. A key will be associated with a prompt and a DB collection or a table.

```bash
python ./admin/api_key_manager.py --url http://localhost:3000 create --collection city --name "City Assistant" --prompt-file ../prompts/examples/city/city-assistant-prompt.txt  --prompt-name "Municipal Assistant Prompt"
```

### Run Client

```bash
cd clients/python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python chat_client.py --url http://localhost:3000 --api-key your-api-key-from-previous-step
```

## LICENSE
Apache 2.0. License.