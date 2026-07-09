# Manual/Integration Check: Message Queue (Async) Surface — RabbitMQ

End-to-end verification of the broker-native async surface, using a real message
broker. ORBIT consumes request messages off a queue, runs them through the same
inference pipeline as the HTTP surfaces, and publishes response envelopes back to
each message's `reply_to` (correlated by `correlation_id`).

- **Part 1 — RabbitMQ (local, Docker):** the fastest path; a local broker with the
  management UI, no cloud account needed.
- **Part 2 — In-process consumer:** the same round-trip with the consumer hosted
  inside the server process (`run_in_server: true`) instead of a standalone worker.
- **Part 3 — Failure modes:** dead-letter routing, auth failures, at-least-once
  redelivery.

The automated unit tests (`test_message_queue.py`) already cover the consumer and
factory logic against an in-memory fake broker — factory selection, adapter/API-key
resolution (including the system-prompt-id + api-key threading that matches
`/v1/chat`), the completed/failed envelope shapes, ack-vs-DLQ semantics, and
reply-to fallback. This playbook exercises the real broker round-trips, AMQP
`reply_to`/`correlation_id` correlation, durable-queue + DLQ behavior, and the
worker/lifespan wiring that unit tests can't.

Prerequisites: an admin can create an API key (`orbit key create`) bound to an
adapter, and Docker is available for the local RabbitMQ.

## 0. Install the dependency profile

The broker client is opt-in:

```bash
./install/setup.sh --profile messaging   # aio-pika (RabbitMQ AMQP client)
```

Verify:

```bash
venv/bin/python -c "import aio_pika; print('aio-pika', aio_pika.__version__)"
```

If `messaging.enabled: true` with `provider: rabbitmq` but `aio-pika` is missing,
the consumer **fails to start** with an install hint naming the `messaging`
profile (`aio-pika is required for RabbitMQ messaging...`) — that itself is
scenario **M6** below. The client is lazy-imported, so a base install that never
enables messaging never needs it.

## Common setup: an API key + a publisher helper

Create an API key bound to an adapter (as a password admin):

```bash
orbit login --username admin
orbit key create --adapter my-adapter --name "mq-playbook"
export ORBIT_API_KEY=orbit_...        # the key printed above
```

This playbook uses the bundled test client, [`mq_client.py`](mq_client.py), which
publishes one request and prints the correlated response envelope. It takes the
**message** as its positional argument and reads the API key from `$ORBIT_API_KEY`
(or `--api-key`); the broker defaults to `amqp://guest:guest@localhost:5672/`
(override with `--url` or `$MESSAGING_RABBITMQ_URL`):

```bash
python server/tests/messaging/mq_client.py "Hello from the queue"
# equivalently: ... "Hello from the queue" --api-key "$ORBIT_API_KEY" --url amqp://...
```

The request contract is `{ "id", "message", "api_key", "adapter"?, "session_id"?,
"metadata"? }`; the API key may instead be an AMQP header (`x-api-key`). The
response envelope is `{ "id", "status", "response", "sources", "error", "metadata" }`.

---

# Part 1 — RabbitMQ (standalone worker)

## 1. Start RabbitMQ

```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 \
  rabbitmq:3-management
# Management UI at http://localhost:15672 (guest/guest)
```

## 2. Configure ORBIT for messaging

In `config/config.yaml`, enable the surface and point it at RabbitMQ:

```yaml
messaging:
  enabled: true
  provider: "rabbitmq"
  run_in_server: false          # standalone worker (this part)
  rabbitmq:
    url: "${MESSAGING_RABBITMQ_URL}"
    requests_queue: "orbit.requests"
    results_queue: "orbit.results"
    dead_letter_queue: "orbit.dlq"
    prefetch: 8
    durable: true
```

Export the broker URL and start the server + the worker (two processes):

```bash
export MESSAGING_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
python3 server/main.py                        # or ./bin/orbit.sh start
./bin/orbit.sh worker run --config config.yaml   # in a second terminal (foreground)
# ...or run it managed in the background: ./bin/orbit.sh worker start --config config.yaml
```

Worker log (terminal for `worker run`, else `logs/worker.log`) should include
`RabbitMQ broker connected (requests=orbit.requests, results=orbit.results, dlq=orbit.dlq, prefetch=8)`
followed by `RabbitMQ broker consuming from orbit.requests` and
`ORBIT worker running - consuming messages.` Managed lifecycle:
`./bin/orbit.sh worker status | stop | restart`.

The three queues (`orbit.requests`, `orbit.results`, `orbit.dlq`) now appear in
the management UI **Queues** tab, `orbit.requests` marked *durable* with a
dead-letter policy.

## 3. Round-trip a message

```bash
python server/tests/messaging/mq_client.py "What can you help me with?"
```

Confirm:
- The publisher prints a response envelope with `"status": "completed"` and a
  non-empty `"response"`.
- The envelope's `id` echoes the request `id`, and the reply arrived on the
  publisher's temporary `reply_to` queue (correlation worked).
- The worker log shows the message processed; in the management UI
  `orbit.requests` returns to 0 ready/unacked messages (it was acked).

## 4. Verify it went through the real pipeline

Confirm the MQ response matches the HTTP surface for the same key/adapter — the
consumer calls the identical `PipelineChatService.process_chat`:

```bash
curl -s -H "X-API-Key: $ORBIT_API_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What can you help me with?"}]}' \
  http://localhost:3000/v1/chat
```

The shape/content of `response` (and `sources`, if the adapter does retrieval)
should be equivalent. If the API key has an **associated system prompt**, confirm
the MQ answer reflects it too — the consumer threads the key's `system_prompt_id`
and `api_key` into the pipeline exactly as `/v1/chat` does (**M5**).

---

# Part 2 — In-process consumer

The consumer can run inside the server process instead of a separate worker — one
process to deploy, at the cost of sharing the event loop with live HTTP traffic.

## 5. Switch to in-process and restart

```yaml
messaging:
  enabled: true
  run_in_server: true      # consumer hosted in the server lifespan
```

```bash
# Do NOT also run `orbit worker` — that would double-consume the same queue.
python3 server/main.py
```

Server startup log should include `In-process message consumer started`. Repeat
the step-3 round-trip against the same `orbit.requests` queue — identical
observable behavior. On shutdown (Ctrl+C), the log shows the consumer stopped
before the rest of the services tear down (`message_consumer.stop()` runs first).

> If `run_in_server: false` (Part 1) and you start only the server, startup logs
> `Messaging enabled but run_in_server is false - use the 'orbit worker' command`
> and no in-process consumer is created — publishing to `orbit.requests` then
> parks messages until a worker connects.

---

# Part 3 — Failure modes

## 6. Dead-letter routing (unparseable message)

Publish a body that isn't valid JSON (or isn't a JSON object) — it can't be
answered, so it must be rejected to the DLQ, not silently dropped:

```bash
venv/bin/python - <<'PY'
import asyncio, aio_pika
async def main():
    conn = await aio_pika.connect_robust("amqp://guest:guest@localhost:5672/")
    ch = await conn.channel()
    await ch.default_exchange.publish(
        aio_pika.Message(body=b"this is not json"), routing_key="orbit.requests")
    await conn.close()
asyncio.run(main())
PY
```

Confirm in the management UI that `orbit.dlq` **Ready** count increments by one
(the message dead-lettered), and `orbit.requests` returns to 0. The worker log
shows the handler raised on the unparseable body.

## 7. Business failure returns a `failed` envelope (still acked)

Publish a request with **no** `api_key` (and no `x-api-key` header) while the
API-key service is active:

```bash
venv/bin/python - <<'PY'
import asyncio, json, uuid, aio_pika
async def main():
    conn = await aio_pika.connect_robust("amqp://guest:guest@localhost:5672/")
    ch = await conn.channel()
    replies = await ch.declare_queue(exclusive=True)
    corr = str(uuid.uuid4())
    await ch.default_exchange.publish(
        aio_pika.Message(body=json.dumps({"id": corr, "message": "hi"}).encode(),
                         correlation_id=corr, reply_to=replies.name),
        routing_key="orbit.requests")
    async with replies.iterator() as it:
        async for m in it:
            if m.correlation_id == corr:
                async with m.process(): print(json.loads(m.body))
                break
    await conn.close()
asyncio.run(main())
PY
```

Confirm the reply is `"status": "failed"` with `"error": "Missing API key"`, and
that `orbit.dlq` did **not** grow — a business failure is answered and acked, only
unparseable/crashing messages dead-letter. An **invalid** key behaves the same
(failed envelope, e.g. `API key resolution failed: ...`).

## 8. At-least-once redelivery

Publish a request, then kill the worker *before* it finishes (use a slow/large
prompt, or pause the worker host) — `Ctrl+C` if it's a foreground `worker run`, or
`./bin/orbit.sh worker stop --force` / `kill -9 $(cat logs/worker.pid)` for a
backgrounded `worker start`. Restart the worker and confirm the in-flight message is
redelivered and processed — because the broker only acks on successful handler
completion (`message.process()`), an unacked message survives a worker crash. (With
`prefetch: 8`, at most 8 messages are unacked/at-risk at once.)

---

## Additional scenarios (guarantees)

### M1. Durable queues survive a broker restart

With `durable: true`, `docker restart rabbitmq` and confirm the three queues
still exist (management UI). Persistent-delivery response envelopes and queued
requests are not lost on a broker bounce.

### M2. reply_to fallback to the results queue

Publish a request with **no** `reply_to` set. Confirm the response envelope lands
on the configured `orbit.results` queue instead (consume it from there). This is
the default reply target when a client doesn't supply a private reply queue.

### M3. Per-message adapter override

Add `"adapter": "other-adapter"` to the request body (with a valid key). Confirm
the response reflects that adapter — the override is honored **after** the key is
validated, and the key's system prompt id is still applied (locked in by
`test_adapter_override_applied_after_key_validation`).

### M4. API key via AMQP header

Send the key as an `x-api-key` message header instead of in the body. Confirm the
round-trip still succeeds (header path is checked when the body has no `api_key`).

### M5. Key-derived context matches /v1/chat

For a key with an associated system prompt, confirm the MQ answer honors it — the
consumer passes both `system_prompt_id` and `api_key` to the pipeline, so MQ and
`/v1/chat` produce equivalent behavior for the same key.

### M6. Fail-fast when aio-pika is missing

In a venv **without** the `messaging` profile, set `messaging.enabled: true` and
start the worker (or server with `run_in_server: true`). Confirm the consumer
reports the missing `aio-pika` and names the `messaging` profile, rather than a
bare `ModuleNotFoundError`.

### M7. Unknown provider rejected

Set `messaging.provider: "kafka"` and start the worker. Confirm a
`ValueError: Unknown messaging provider 'kafka', supported: ['rabbitmq']` — never
a silent no-op.

### M8. Disabled by default is unaffected

With `messaging.enabled: false` (the default), confirm the server starts normally,
no broker connection is attempted, and none of the queues are declared — the
surface is fully opt-in and the base install needs no broker.

### M9. Managed worker lifecycle (start / status / stop / restart)

The standalone worker has a PID-file-based lifecycle mirroring the server:

```bash
./bin/orbit.sh worker start --config config.yaml   # background; writes logs/worker.pid
./bin/orbit.sh worker status                        # -> "Worker is running (PID ...)"
./bin/orbit.sh worker restart --config config.yaml  # stop then start
./bin/orbit.sh worker stop                          # graceful (SIGTERM); --force = SIGKILL
./bin/orbit.sh worker status                        # -> "Worker is not running"
```

Confirm:
- `start` reports a PID, `logs/worker.pid` exists, and `ps -p $(cat logs/worker.pid)`
  shows a `worker_main.py` process.
- `stop` terminates it and **removes** the PID file; a second `stop` is a no-op
  ("Worker is not running").
- `start` while already running does **not** spawn a second worker ("already running").
- **restart aborts on a failed stop:** `restart` only proceeds to `start` if `stop`
  succeeds — if the running worker can't be signalled (e.g. a permission/OS error),
  the command reports "Restart aborted: failed to stop the running worker" and exits
  non-zero rather than falsely reporting success (locked in by
  `test_worker_service.py::TestRestart`).

---

## 9. Run the automated checks

```bash
ruff check server/services/message_brokers/ server/services/messaging/ \
  server/tests/messaging/test_message_queue.py bin/orbit/services/worker_service.py
cd server && ../venv/bin/python -m pytest tests/messaging/ -v
```

Expect all green across two suites:
- `test_message_queue.py` — factory selection + unknown-provider rejection, and the
  full consumer matrix (completed/failed envelopes, missing/invalid key, empty
  message, DLQ-propagation on unparseable body and pipeline exception, adapter
  override, system-prompt-id/api-key threading, reply-to fallback, header key,
  start/stop delegation). Runs against an in-memory fake broker.
- `test_worker_service.py` — the PID-file worker lifecycle (start / stop / status /
  restart, SIGTERM→SIGKILL escalation, stale-PID cleanup, restart-aborts-on-failed-stop).

Both need **no** RabbitMQ or `aio-pika` — they pass in a base install.

---

## Troubleshooting

- **Worker exits immediately with "Messaging is disabled":** `messaging.enabled`
  is still `false`, or the worker isn't reading the config you edited — pass
  `--config config.yaml` and confirm the path.
- **Worker exits with "run_in_server is true ... in-process consumer is already
  running":** you set `run_in_server: true` (Part 2) but also launched
  `orbit worker start`/`run`. Pick one host — set `run_in_server: false` for the
  standalone worker, or drop the worker and just start the server.
- **`aio-pika is required for RabbitMQ messaging`:** install the `messaging`
  profile (M6). The client is lazy-imported and only needed when messaging is on.
- **Messages pile up in `orbit.requests` (Ready count climbs):** no consumer is
  connected — the server has `run_in_server: false` and no `orbit worker` is
  running, or the worker crashed. Check the worker log / management UI
  *Consumers* count on the queue.
- **Replies never arrive at the client:** confirm the publisher set both
  `reply_to` (a queue the client consumes) and `correlation_id`, and that it
  filters replies by `correlation_id`. With no `reply_to`, responses go to
  `orbit.results` (M2), not the client's temp queue.
- **Everything lands in `orbit.dlq`:** the bodies aren't valid JSON objects, or
  the handler is raising — inspect a dead-lettered message's payload in the
  management UI and the worker log. Business failures (bad key, empty message)
  should produce a `failed` **reply**, not a DLQ entry; a DLQ entry means an
  unparseable message or an unexpected pipeline exception.
- **Connection refused to `amqp://...:5672`:** RabbitMQ isn't up or the port
  isn't mapped — `docker ps` for the `rabbitmq` container and confirm `-p 5672:5672`.
