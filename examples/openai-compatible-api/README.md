# OpenAI-Compatible API Examples

Minimal examples showing that ORBIT's `POST /v1/chat/completions` endpoint
works with the official OpenAI SDKs, unmodified — just point the client at
your ORBIT server.

## Setup

Set your ORBIT server URL and API key as environment variables:

```bash
export ORBIT_API_URL="http://localhost:3000"
export ORBIT_API_KEY="orbit_your_api_key_here"
```

The API key determines which adapter handles the request server-side, so
there's no separate adapter header to set.

By default ORBIT requires a per-request session id (`chat_history.session`
in `config.yaml`), so both examples send a generated `X-Session-ID` header.

The `model` field must be one of the models allowed for your API key's
adapter (ORBIT rejects anything else with a 500 error naming the allowed
list). The examples default to `gpt-oss:120b`, which matches the built-in
`simple-chat` adapter — override it with `ORBIT_MODEL` if your key uses a
different adapter/model.

## Python

```bash
pip install openai
python chat_completions.py "What can you help me with?"
python chat_completions.py "Tell me a short story" --stream
```

## Node.js

```bash
npm install openai
node chat_completions.js "What can you help me with?"
node chat_completions.js "Tell me a short story" --stream
```
