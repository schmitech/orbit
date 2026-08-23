# A2A Protocol Examples

Minimal Python and Node.js clients for ORBIT's implementation of Google's
[Agent-to-Agent (A2A) protocol](https://google.github.io/A2A/). They
demonstrate agent discovery, blocking and streaming task submission, and task
lookup or cancellation using the JSON-RPC endpoint.

## Setup

Start ORBIT, then set its URL and an API key. The key selects the default
adapter that handles each task.

```bash
export ORBIT_API_URL="http://localhost:3000"
export ORBIT_API_KEY="orbit_your_api_key_here"
```

If API-key enforcement is disabled, `ORBIT_API_KEY` is optional. To direct an
individual task to an exposed A2A skill, set `ORBIT_A2A_ADAPTER` to that
skill's adapter ID. Discover available skills with either example's
`--discover` option.

For API keys restricted to an ORBIT user, also provide the user's session
token or JWT separately:

```bash
export ORBIT_USER_TOKEN="your-user-session-token-or-jwt"
```

The clients send that value in `X-ORBIT-User-Authorization`, because the
normal `Authorization` header carries the API key.

## Python

The Python client uses only the standard library.

```bash
python a2a_client.py --discover
python a2a_client.py "What can you help me with?"
python a2a_client.py "Tell me a short story" --stream
python a2a_client.py --get <task-id>
python a2a_client.py --cancel <task-id>
```

### Python A2A package

[`python-a2a`](https://pypi.org/project/python-a2a/) provides typed A2A message
models and Agent Card discovery. Install it, then run the package-based client:

```bash
pip install python-a2a
python python_a2a_client.py "What can you help me with?"
python python_a2a_client.py "How many open positions are there?" --adapter hr
```

`python_a2a_client.py` subclasses `A2AClient` because the package's generic
task client currently probes `/a2a/tasks/send`, whereas ORBIT's documented
JSON-RPC transport uses `POST /a2a`. The adapter retains the package's
`A2AClient` Agent Card discovery and typed `Message` API while sending requests
to ORBIT's endpoint.

## Node.js

Requires Node.js 18 or later for its built-in `fetch` API. No package install
is needed.

```bash
node a2a_client.js --discover
node a2a_client.js "What can you help me with?"
node a2a_client.js "Tell me a short story" --stream
node a2a_client.js --get <task-id>
node a2a_client.js --cancel <task-id>
```

See [the A2A protocol guide](../../docs/a2a-protocol.md) for the full endpoint
and authentication reference.
