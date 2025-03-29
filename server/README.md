# Open Inference Server

A Node.js server with text-to-speech capabilities. This server provides a robust API for building question-answering systems with the following features:

- **Multiple LLM Backends**: Support for Ollama and vLLM inference engines
- **Vector Search**: Integration with ChromaDB for semantic search and context retrieval
- **Text-to-Speech**: ElevenLabs integration for natural voice responses
- **Streaming Responses**: Real-time streaming of both text and audio responses
- **Multilingual Support**: Handle queries in multiple languages
- **Security Features**: Built-in guardrails and content filtering
- **Comprehensive Logging**: Dual logging system with filesystem and Elasticsearch support
- **Production Ready**: Includes health checks, graceful shutdown, and service management
- **Containerized**: Docker support for easy deployment and scaling
- **Infrastructure Agnostic**: Run anywhere from local machines to cloud providers

The server is designed to be:
- **Scalable**: Handle multiple concurrent connections
- **Secure**: HTTPS support with proper certificate management
- **Maintainable**: Well-structured code with comprehensive logging
- **Flexible**: Easy to configure and extend with different LLM backends
- **Portable**: Containerized for consistent deployment across environments
- **Vendor Independent**: No lock-in to specific cloud providers or services

## Key Benefits

### Infrastructure Flexibility
- Run on any infrastructure: local machines, private servers, or cloud providers
- Support for multiple deployment models:
  - Standalone server
  - Containerized deployment
  - Kubernetes orchestration
  - Serverless functions (with appropriate adapters)
- Easy migration between environments without code changes

### Vendor Independence
- No dependency on specific cloud providers
- Freedom to switch between different LLM backends
- Ability to use alternative vector databases
- Option to replace text-to-speech providers
- Control over data storage and processing locations

### Containerization Benefits
- Consistent environment across development and production
- Easy scaling and deployment
- Isolated dependencies and configurations
- Simplified CI/CD integration
- Reproducible builds and deployments

### Data Privacy and Control
- Complete control over data storage and processing
- No data sharing with third-party services
- Ability to implement custom security measures
- Compliance with data protection regulations
- Audit trail for all operations

### Cost Optimization
- Pay only for the infrastructure you use
- No per-request or per-token charges
- Ability to use cost-effective hardware
- Scale resources based on actual needs
- Optimize for specific use cases

### Customization and Extensibility
- Modify the inference pipeline as needed
- Implement specialized logging and monitoring
- Integrate with existing systems
- Add new features without vendor limitations

## Prerequisites

- Node.js (v18 or higher)
- Python 3.12 (for local ChromaDB server and utilities)
- An ElevenLabs API key (optional - text-to-speech)
- Ollama server or vLLM

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
   - ChromaDB connection details
   - ElevenLabs voice ID
   - System template path

   Edit the `.env` file to set your sensitive credentials:
   ```env
   ELASTICSEARCH_USERNAME=your-username
   ELASTICSEARCH_PASSWORD=your-password
   ELEVEN_LABS_API_KEY=your-api-key
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

1. Ingest data (in another simple-qa-chatbot terminal)
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

eleven_labs:
  api_key: null                       # API key loaded from .env
  voice_id: "kPzsL2i3teMYv0FxEYQ6"    # Voice ID to use

system:
  prompt: "You are a helpful assistant..."  # System prompt for the LLM
```

## HTTPS Configuration

The server supports HTTPS connections using TLS (Transport Layer Security). Here's how to configure it:

### Using Let's Encrypt with Azure Domain

1. Install Certbot:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install certbot
```

2. If your server runs on port 3000, you'll need to route requests from port 80 to port 3000 for the certificate verification:
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 3000
```

3. Obtain TLS certificate using DNS challenge (since we can't use HTTP challenge with Azure domain):
```bash
sudo certbot certonly --manual --preferred-challenges dns -d your-azure-domain.cloudapp.azure.com
```

4. When prompted by certbot, you'll need to:
   - Create a `.well-known/acme-challenge` directory in your server project
   - Add the verification file with the content provided by certbot
   - Add this route to your server.ts:
   ```typescript
   app.use('/.well-known/acme-challenge', express.static(path.join(__dirname, '../.well-known/acme-challenge')));
   ```
   - Keep this route for future certificate renewals

5. Update your `config.yaml`:
```yaml
general:
  https:
    enabled: true
    port: 3443
    cert_file: "/etc/letsencrypt/live/your-azure-domain.cloudapp.azure.com/fullchain.pem"
    key_file: "/etc/letsencrypt/live/your-azure-domain.cloudapp.azure.com/privkey.pem"
```

6. Set proper permissions for the certificate files:
```bash
sudo chown -R $USER:$USER /etc/letsencrypt/live/your-azure-domain.cloudapp.azure.com
sudo chown -R $USER:$USER /etc/letsencrypt/archive/your-azure-domain.cloudapp.azure.com
sudo chmod -R 755 /etc/letsencrypt/live
sudo chmod -R 755 /etc/letsencrypt/archive
sudo chmod 644 /etc/letsencrypt/archive/your-azure-domain.cloudapp.azure.com/*.pem
```

7. Configure Azure Network Security Group:
```bash
# Add inbound security rules
- Priority: 100
  Port: 3443
  Protocol: TCP
  Source: * (or your specific IP range)
  Destination: *
  Action: Allow
  Description: Allow HTTPS traffic (TLS)

- Priority: 110
  Port: 80
  Protocol: TCP
  Source: * (or your specific IP range)
  Destination: *
  Action: Allow
  Description: Allow HTTP traffic for certificate verification
```

8. Test your HTTPS setup:
```bash
# Test with curl (replace with your domain)
curl -I https://your-azure-domain.cloudapp.azure.com:3443/health
```

Note: The certificates from Let's Encrypt expire after 90 days. You'll need to renew them using:
```bash
sudo certbot renew
```

**Azure Network Security Group**:
```bash
# Add inbound security rules
- Priority: 100
  Port: 443
  Protocol: TCP
  Source: * (or your specific IP range)
  Destination: *
  Action: Allow
  Description: Allow HTTPS traffic (TLS)

# Only needed if using Let's Encrypt or HTTP-to-HTTPS redirects
# - Priority: 110
#   Port: 80
#   Protocol: TCP
#   Source: * (or your specific IP range)
#   Destination: *
#   Action: Allow
#   Description: Allow HTTP traffic for redirects
```

Note: Port 80 is only required if you're:
- Using Let's Encrypt for certificate validation
- Implementing HTTP-to-HTTPS redirects
- Using a reverse proxy that handles TLS termination

For development with self-signed certificates or direct HTTPS access, port 80 is not needed.

5. Test your TLS setup:
```bash
# Test with curl (replace YOUR_IP with your actual IP)
curl -k https://YOUR_IP.nip.io/health

# Check TLS certificate info
openssl s_client -connect YOUR_IP.nip.io:443 -showcerts
```

Note: While this setup works, having a proper domain name is recommended for production use as it:
- Provides better security and trust
- Makes certificate management easier
- Allows for better monitoring and analytics
- Enables proper TLS configuration

### Handling Certificate Errors in API Client

When using self-signed certificates, you'll need to handle certificate validation in your API client. Here are the solutions:

1. **For Development (Node.js API Client)**
```typescript
// Add this to your API client configuration
const httpsAgent = new https.Agent({
  rejectUnauthorized: false // Only use in development!
});

// Use it in your fetch calls
fetch('https://localhost:3443/chat', {
  agent: httpsAgent
});
```

2. **For Browser-based API Client**
```typescript
// Add this to your API client configuration
const fetchOptions = {
  // Skip certificate validation (only for development!)
  mode: 'cors',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json'
  }
};

// Use it in your fetch calls
fetch('https://localhost:3443/chat', fetchOptions);
```

3. **For Production**
- Use a proper TLS certificate from a trusted CA (like Let's Encrypt)
- Don't disable certificate validation
- Use proper domain names instead of IP addresses

4. **Temporary Browser Workaround (Development Only)**
- Open `https://localhost:3443` directly in your browser
- Click "Advanced" or "More Information"
- Click "Proceed to localhost (unsafe)" or "Accept the Risk and Continue"
- The API client should now work without certificate errors

Note: Disabling certificate validation is only recommended for development. Never disable certificate validation in production as it makes your application vulnerable to man-in-the-middle attacks.

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
npm run server -- ollama #or vLLM
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

# Testing Guide

This document outlines how to run the test suite for the AI Chat Server application.

## Setting Up Tests

Before running tests, make sure you have all dependencies installed:

```bash
npm install
```

## Running Tests

To run the full test suite:

```bash
npm test
```

### Watch Mode

To run tests in watch mode (tests will re-run when files change):

```bash
npm run test:watch
```

### Test Coverage

To generate a test coverage report:

```bash
npm run test:coverage
```

This will create a `coverage` directory with detailed reports on test coverage.

## Testing Individual Components

You can run tests for specific components or test files:

```bash
# Test a specific file
npm test tests/ollamaClient.test.ts

# Test files matching a pattern
npm test tests/clients/

# Test files containing specific text in their name
npm test -- -t "ollama"
```

### Component-Specific Tests

1. **Configuration Tests**
```bash
npm test tests/config.test.ts
```
Tests configuration loading, validation, and environment variable handling.

2. **Client Tests**
```bash
# Test Ollama client
npm test tests/clients/ollamaClient.test.ts

# Test VLLM client
npm test tests/clients/vllmClient.test.ts
```
Tests client initialization, connection verification, and API interactions.

3. **Service Tests**
```bash
# Test chat service
npm test tests/services/chatService.test.ts

# Test audio service
npm test tests/services/audioService.test.ts

# Test health service
npm test tests/services/healthService.test.ts
```
Tests service functionality, error handling, and integration with other components.

4. **Logger Tests**
```bash
npm test tests/logger.test.ts
```
Tests logging functionality, including file and Elasticsearch logging.

## Test Structure

Tests are organized in the `tests` directory, which mirrors the structure of the `src` directory:

- `tests/config.test.ts` - Tests for configuration loading and validation
- `tests/clients/` - Tests for language model clients
  - `tests/clients/baseClient.test.ts` - Tests for base client functionality
  - `tests/clients/ollamaClient.test.ts` - Tests for Ollama-specific functionality
- `tests/services/` - Tests for service modules
  - `tests/services/audioService.test.ts` - Tests for audio generation
  - `tests/services/chatService.test.ts` - Tests for chat processing
  - `tests/services/healthService.test.ts` - Tests for health monitoring
- `tests/logger.test.ts` - Tests for logging functionality

## Mocking Strategy

The tests use Jest's mocking capabilities to isolate components and test them independently:

- External API calls are mocked using Jest's `jest.mock()` and `global.fetch`
- Complex dependencies like ElasticSearch and ChromaDB are mocked
- Environment variables are managed within tests

### Example Mock Setup

```typescript
// Mock external dependencies
jest.mock('@langchain/community/llms/ollama', () => ({
  Ollama: jest.fn().mockImplementation(() => ({
    invoke: jest.fn().mockResolvedValue('mocked response')
  }))
}));

// Mock global fetch
global.fetch = jest.fn() as jest.MockedFunction<typeof fetch>;

// Mock environment variables
process.env.ELASTICSEARCH_USERNAME = 'testuser';
process.env.ELASTICSEARCH_PASSWORD = 'testpass';
```

## Adding New Tests

When adding new functionality, follow these guidelines for creating tests:

1. Create a test file in the corresponding directory under `tests/`
2. Import the module to be tested
3. Mock dependencies as needed
4. Write test cases covering:
   - Normal operation
   - Error handling
   - Edge cases
   - Input validation
   - Integration with other components
5. Run tests to ensure they pass

### Example Test Structure

```typescript
describe('ComponentName', () => {
  let component: ComponentName;
  
  beforeEach(() => {
    // Setup before each test
    component = new ComponentName();
  });

  describe('methodName', () => {
    it('should handle normal case', async () => {
      // Test normal operation
    });

    it('should handle errors', async () => {
      // Test error handling
    });

    it('should handle edge cases', async () => {
      // Test edge cases
    });
  });
});
```

## Debugging Tests

If tests are failing, you can:

1. Check the console output for error messages
2. Uncomment the console methods in `setupTests.ts` to see console output:
```typescript
global.console = {
  ...console,
  log: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
};
```
3. Use `console.log` statements within tests for debugging
4. Run a specific test with `npm test -- -t "test name"`
5. Use Jest's `--verbose` flag for more detailed output:
```bash
npm test -- --verbose
```

## Continuous Integration

Tests are automatically run in the CI pipeline. Any test failures will prevent the code from being deployed.

## License
Apache 2.0 License. See LICENSE file on project directory.