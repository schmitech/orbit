# AI Q/A Chatbot

A conversational AI assistant, featuring text-to-speech capabilities.

## Prerequisites

- Node.js (v16 or higher)
- Python (for ChromaDB)
- An ElevenLabs API key (for text-to-speech)
- Ollama installed locally
- ChromaDB installed locally or in a server or in a container

## Setup

1. Install dependencies
```bash
npm install
```

2. Set up environment variables
Create a `.env` by copying from .env.example:

3. Build the api interface:
```bash
cd ../../api
npm install
npm test
npm run build
```

1. Start the client (in a separate terminal)
```bash
npm run dev
```

The application should now be running at `http://localhost:5173`

## Features

- Real-time chat interface
- Text-to-speech capability using ElevenLabs
- Context-aware responses using ChromaDB
- Local LLM support via Ollama

## License

[Your license information here]