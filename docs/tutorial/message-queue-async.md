# Example 12: Message Queue (Async) Requests

Everything so far has gone through synchronous HTTP (`/v1/chat`). ORBIT can also consume requests off a message broker and publish responses back — the same inference pipeline, a decoupled/batch-friendly transport. Useful when a producer shouldn't block on an LLM response, or when requests arrive from a queue-based system instead of a web client.

### How it works

1. A publisher puts a request message (`id`, `message`, `api_key`, optional `adapter`/`session_id`) onto a request queue.
2. ORBIT's consumer (in-process or a standalone worker) picks it up, runs it through the identical pipeline `/v1/chat` uses, and builds a response envelope.
3. The envelope is published back to the message's `reply_to` (correlated by `correlation_id`), or to a default results queue if none was given.

### 1. Install the messaging dependency profile

The broker client is opt-in and not part of a base install:

```bash
./install/setup.sh --profile messaging   # aio-pika (RabbitMQ AMQP client)
```

### 2. Start a local RabbitMQ

```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

The management UI is at `http://localhost:15672` (`guest`/`guest`).

### 3. Enable the surface in `config/config.yaml`

```yaml
messaging:
  enabled: true
  provider: "rabbitmq"
  run_in_server: false          # false = a standalone `orbit worker` process; true = hosted inside the server
  rabbitmq:
    url: "${MESSAGING_RABBITMQ_URL}"
    requests_queue: "orbit.requests"
    results_queue: "orbit.results"
    dead_letter_queue: "orbit.dlq"
    prefetch: 8
    durable: true
```

Export the broker URL, then start the server and — in a second terminal — the worker:

```bash
export MESSAGING_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
./bin/orbit.sh start
./bin/orbit.sh worker run --config config.yaml   # foreground; or `worker start` to run it managed/backgrounded
```

The worker log should show it connect and start consuming from `orbit.requests`.

> **Prefer one process instead of two?** Set `run_in_server: true` and skip the separate worker — the consumer then runs inside the server's own lifespan. Don't run both at once; that double-consumes the queue.

### 4. Get an API key and publish a message

Create a key bound to an adapter (reuse your `simple-chat` key from [Your first chat](first-chat.md), or via the CLI):

```bash
./bin/orbit.sh login --username admin
./bin/orbit.sh key create --adapter simple-chat --name "mq-tutorial"
export ORBIT_API_KEY=orbit_...        # the key printed above
```

The repo ships a small publisher helper for testing round-trips:

```bash
python server/tests/messaging/mq_client.py "Hello from the queue"
```

Confirm:
- It prints a response envelope with `"status": "completed"` and a non-empty `"response"`.
- The envelope's `id` echoes the request's `id` — correlation via `reply_to`/`correlation_id` worked.
- In the RabbitMQ management UI, the `orbit.requests` queue returns to 0 ready/unacked messages after processing.

### 5. Confirm it's the same pipeline as `/v1/chat`

```bash
curl -s -H "X-API-Key: $ORBIT_API_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello from the queue"}]}' \
  http://localhost:3000/v1/chat
```

The response content should be equivalent to what the MQ round-trip produced — the consumer calls the same `PipelineChatService.process_chat` the HTTP surface does, including any system prompt attached to the key.

### What happens on failure

- **Unparseable message body** (not valid JSON): rejected to `orbit.dlq`, not silently dropped.
- **Business failure** (missing/invalid API key, empty message): still acked, but the reply envelope has `"status": "failed"` with an `"error"` — this does *not* go to the dead-letter queue, since it's a valid, answered request.
- **Worker crash mid-message**: the broker only acks after successful processing, so an in-flight message is redelivered to the next consumer (at-least-once delivery).

### Managed worker lifecycle

```bash
./bin/orbit.sh worker start --config config.yaml   # background; writes logs/worker.pid
./bin/orbit.sh worker status
./bin/orbit.sh worker restart --config config.yaml
./bin/orbit.sh worker stop                          # graceful; --force for SIGKILL
```

See [`server/tests/messaging/playbook-message-queue.md`](../../server/tests/messaging/playbook-message-queue.md) for the full manual/integration checklist — dead-letter routing, `reply_to` fallback, per-message adapter overrides, header-based API keys, durable-queue broker restarts, and the automated test suite — and the [Message Queue Architecture](../message-queue-architecture.md) reference for the request/response envelope contract.

---

[Tutorial home](../tutorial.md) | [Previous: Example 11: Web Search and Automatic Skill Routing](auto-skill-routing.md) | [Next: Creating API Keys](creating-api-keys.md)

---
