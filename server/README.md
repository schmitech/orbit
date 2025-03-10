# QA Chatbot Server

A Node.js server for Q/A chatbots with text-to-speech capabilities.

## Architecture

![Architecture Overview](llm-chatbot-architecture.png)

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

2. Create .env from .env.example

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