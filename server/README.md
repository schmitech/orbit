# QA Chatbot Server

A Node.js server for Q/A chatbots with text-to-speech capabilities.

## Prerequisites

- Node.js (v16 or higher)
- Python (for ChromaDB)
- An ElevenLabs API key (for text-to-speech)
- Ollama server
- ChromaDB server

## Setup as Server

1. Install dependencies
```bash
npm install
```

2. Configure the application
   
   The application uses both a YAML configuration file (`config.yaml`) and environment variables (`.env`) for sensitive data. Sample configuration files are provided:
   
   ```bash
   # Copy the example config and modify as needed
   cp config.yaml.example config.yaml
   cp .env.example .env
   ```
   
   Edit the `config.yaml` file to set your:
   - Ollama parameters (model, temperature, etc.)
   - HuggingFace API key
   - ChromaDB connection details
   - ElevenLabs voice ID
   - System template path

   Edit the `.env` file to set your sensitive credentials:
   ```env
   ELASTICSEARCH_USERNAME=your-username
   ELASTICSEARCH_PASSWORD=your-password
   ELEVEN_LABS_API_KEY=your-api-key
   HUGGINGFACE_API_KEY=your-api-key
   ```

   Note: Make sure to add `.env` to your `.gitignore` file to prevent committing sensitive data.

3. Install Chroma server (skip if chroma is running separately)
   ```bash
   python -m venv venv 
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. Start ChromaDB (in simple-qa-chatbot terminal venv)
```bash
chroma run --host localhost --port 8000 --path ./chroma_db
```

5. Ingest data (in another simple-qa-chatbot terminal)
```bash
python ../chroma/create-chroma-collection.py qa-pairs.json
```
5.1 Test ingested data, example:
```bash
python ../chroma/query-chroma-collection.py "Where can I view the assessment roll for my property taxes?"
```

## Configuration Options

The `config.yaml` file contains the following sections:

```yaml
general:
  port: 3000                           # Server port
  verbose: "false"                     # Enable verbose logging

chroma:
  host: "localhost"                    # ChromaDB host
  port: 8000                           # ChromaDB port
  collection: "qa-chatbot"             # Collection name

elasticsearch:
  enabled: true                        # Enable/disable Elasticsearch logging
  node: "https://localhost:9200"       # Elasticsearch server endpoint
  index: "qa-chatbot"                  # Index name for chat logs
  auth: {}                            # Auth credentials loaded from .env

ollama:
  base_url: "http://localhost:11434"   # URL of your Ollama server
  temperature: 0.01                    # Controls randomness
  top_p: 0.8                          # Nucleus sampling parameter
  top_k: 20                           # Limits token selection to top K options
  repeat_penalty: 1.2                 # Penalizes repetition
  num_predict: 1024                   # Maximum tokens to generate
  num_ctx: 8192                       # Context window size
  num_threads: 8                      # CPU threads to use
  model: "gemma3:1b"                  # Ollama model to use
  embed_model: "nomic-embed-text"     # Embedding model for vector search
  stream: true                        # Enable streaming responses

vllm:
  base_url: "http://localhost:5000"    # VLLM server URL
  temperature: 0.01                    # Controls randomness
  max_tokens: 32                       # Maximum tokens to generate
  model: "VLLMQwen2.5-14B"            # VLLM model to use
  top_p: 0.8                          # Nucleus sampling parameter
  frequency_penalty: 0.0              # Penalizes frequency of tokens
  presence_penalty: 0.0               # Penalizes presence of tokens
  best_of: 1                          # Number of best completions to return
  n: 1                                # Number of completions to generate
  logprobs: null                      # Log probabilities configuration
  echo: false                         # Echo the prompt in the response
  stream: false                       # Enable streaming responses
  guardrail_max_tokens: 20            # Maximum tokens for guardrail
  guardrail_temperature: 0.0          # Temperature for guardrail
  guardrail_top_p: 1.0                # Top-p for guardrail

huggingface:
  api_key: null                       # API key loaded from .env
  model: "deepset/roberta-base-squad2" # HF model for question answering

eleven_labs:
  api_key: null                       # API key loaded from .env
  voice_id: "kPzsL2i3teMYv0FxEYQ6"    # Voice ID to use

system:
  prompt: "You are a helpful assistant..."  # System prompt for the LLM
  guardrail_prompt: "You are a multilingual query guardrail agent..."  # Guardrail prompt for query safety
```

## Logging

The application implements a dual logging system:

1. **Filesystem Logging (Always Active)**
   - Logs are stored in the `logs` directory
   - Uses daily rotation with format `chat-YYYY-MM-DD.log`
   - Each log file is limited to 20MB
   - Logs are retained for 14 days
   - Includes all chat interactions, errors, and system status
   - Logs are in JSON format for easy parsing

2. **Elasticsearch Logging (Optional)**
   - Enabled/disabled via `elasticsearch.enabled` in config
   - Requires valid credentials in `.env`
   - Falls back to filesystem-only logging if Elasticsearch is unavailable

Example log entry:
```json
{
  "timestamp": "2024-03-21T10:30:00.000Z",
  "query": "user question",
  "response": "bot response",
  "backend": "ollama",
  "blocked": false,
  "elasticsearch_status": "enabled"
}
```

Note: The `logs` directory is automatically created when needed and should be added to `.gitignore`.

## Environment Variables

The following sensitive credentials are stored in `.env`:

```env
# Elasticsearch credentials
ELASTICSEARCH_USERNAME=your-username
ELASTICSEARCH_PASSWORD=your-password

# ElevenLabs API key
ELEVEN_LABS_API_KEY=your-api-key

# HuggingFace API key
HUGGINGFACE_API_KEY=your-api-key
```

## Testing Text-to-Speech
You can test your ElevenLabs API key with:
```bash
curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/XrExE9yKIg1WjnnlVkGX" \
  -H "xi-api-key: $ELEVEN_LABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test audio generation", "model_id": "eleven_monolingual_v1"}' \
  --output test.mp3
```

6. Start the server:
```bash
npm run server -- ollama #or hf for hugging face
```

## API Client

The project includes a reusable API client library in the `api` directory. This library can be used by any client application to interact with the chatbot server.

### Using the API Client

1. Build the API client:
```bash
cd api
npm install
npm run build
```

2. Use it in your projects:
```bash
npm install /path/to/chatbot-api
```

Or publish it to npm:
```bash
cd api
npm publish
```

Then install it in your projects:
```bash
npm install chatbot-api
```

### Testing the API Client

The API client includes a comprehensive test suite using Vitest and MSW (Mock Service Worker) for mocking HTTP requests.

To run the tests:

```bash
cd api
npm test                 # Run tests once
npm run test:watch       # Run tests in watch mode
npm test -- --coverage   # Run tests with coverage report
```

The tests verify:
- Basic chat functionality without voice
- Chat with voice enabled
- Error handling for network issues

The test suite uses MSW to mock server responses, so you don't need an actual server running to test the API client.

For more details on the tests, see the [API tests README](api/test/README.md).

See the [API client README](api/README.md) for more details on usage.

## Running as a Service

There are several ways to run the server in the background:

### 1. Using Systemd (Recommended)

Create a systemd service file:

```bash
sudo vim /etc/systemd/system/qa-chatbot.service
```

Add this content:

```bash
[Unit]
Description=QA Chatbot Node.js Server
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/your/project
ExecStart=/usr/bin/npm run server -- ollama
Restart=always
RestartSec=3
StandardOutput=append:/var/log/qa-chatbot.log
StandardError=append:/var/log/qa-chatbot.error.log

[Install]
WantedBy=multi-user.target
```

Replace:
- `YOUR_USERNAME` with your actual username (run `whoami` to get it)
- `/path/to/your/project` with the full path to your project directory
- Update the ExecStart path if npm is installed elsewhere (use `which npm` to check)

Manage the service:
```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable qa-chatbot

# Start the service
sudo systemctl start qa-chatbot

# Check the status
sudo systemctl status qa-chatbot

# View logs in real-time
sudo journalctl -u qa-chatbot -f
```

To remove the service:
```bash
sudo systemctl stop qa-chatbot
sudo systemctl disable qa-chatbot
sudo rm /etc/systemd/system/qa-chatbot.service
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

### 2. Using Background Process

Simple background process with output handling:

```bash
# Save output to a file
npm run server -- ollama > output.log 2>&1 &

# Discard all output
npm run server -- ollama > /dev/null 2>&1 &

# Save stdout and stderr to separate files
npm run server -- ollama > output.log 2> error.log &
```

Note: Using just `&` is less robust than systemd as the process might terminate when closing the terminal session. For production environments, the systemd service approach is recommended.

## License
Apache 2.0 License. See LICENSE file on project directory.