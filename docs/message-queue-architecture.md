# Message Queue (Async) Architecture

ORBIT can be driven **asynchronously over a message broker** in addition to its
synchronous HTTP surfaces (REST, OpenAI-compatible, A2A, MCP). Instead of holding an
HTTP connection open and waiting for a reply, a client **publishes a request message**
to a queue; ORBIT runs as a **consumer**, processes each message through the *same*
inference pipeline as `/v1/chat`, and **publishes a response** back to the message's
reply queue.

This is ideal for **decoupled, batch-style, and bursty workloads** — jobs that
shouldn't hold a connection open, producers that run on their own schedule, and
fan-out pipelines where throughput matters more than per-request latency.

The first (and current) broker is **RabbitMQ** (AMQP), integrated via
[`aio-pika`](https://aio-pika.readthedocs.io/). It sits behind a pluggable
`MessageBroker` abstraction, so other brokers can be added without touching the
consumer logic. The surface is **disabled by default** and opt-in.

> **TL;DR** — publish JSON to `orbit.requests` with a `reply_to` queue and a
> `correlation_id`; read the response envelope off your reply queue. See
> [Quick start](#quick-start).

---

## When to use this

The fit is driven by a few concrete properties of this surface: it's **decoupled**
(fire-and-forget, no held connection), **at-least-once with a DLQ** (durable,
retryable), **backpressured** (`prefetch` caps in-flight work), **horizontally
scalable** (competing consumers), and **non-streaming** (you get a complete response
envelope, not token-by-token). It runs the *same* pipeline as `/v1/chat`, so RAG,
SQL/NoSQL retrieval, and tools all work in batch too.

### Strong fits

- **Bulk / batch enrichment** — classify, summarize, translate, extract, or tag
  thousands of records offline (support tickets, documents, product catalog, logs).
  Producers dump the batch onto the queue; workers drain it at their own pace.
- **Spiky / bursty ingestion** — a nightly export or a traffic spike dumps 10k items
  at once. The queue absorbs the burst and `prefetch` meters it into the pipeline
  instead of overwhelming your LLM provider or database.
- **Event-driven pipelines** — a service you already run emits events to a broker
  (new upload, DB change, Kafka/Rabbit event). ORBIT becomes one processing stage:
  consume → answer → publish downstream.
- **Long-running / heavy jobs** — large-document RAG, big context windows, or slow
  local models (llama.cpp/Ollama) where an HTTP request would time out or tie up a
  connection. The producer isn't waiting on a socket.
- **Cross-team / cross-language decoupling** — producers in any language just speak
  AMQP; no shared HTTP client, no tight coupling to ORBIT's lifecycle. Workers deploy,
  restart, and scale independently.
- **Reliability-sensitive work** — anything where silently dropping a request is
  unacceptable. At-least-once redelivery means a worker crash doesn't lose the job;
  the DLQ captures what genuinely can't be processed for later inspection/replay.
- **Scheduled / offline jobs** — cron-style producers drop work overnight; workers
  process it; results land on a results queue for a downstream consumer. No service
  sits blocked.
- **Throughput scaling** — need more capacity? Run more workers against the same queue
  and RabbitMQ load-balances across them.

### Poor fits (use HTTP instead)

- **Interactive chat / low-latency UX** — a user typing in a chat window wants
  immediate, streaming output. Use `/v1/chat` (SSE); the MQ path returns one complete
  envelope, not incremental tokens.
- **Token-by-token streaming** of any kind — not supported over MQ by design.
- **Simple synchronous request/response** where a blocking HTTP call is genuinely
  simpler and you need neither durability nor decoupling — the broker is extra moving
  parts you don't need.
- **Deployments unwilling to run a broker** — it adds RabbitMQ as infrastructure; if
  that's not worth it, stay on HTTP.

> **Rule of thumb:** if a human is waiting on the answer *right now*, use HTTP; if a
> *system* will pick up the answer *when it's ready* — especially at volume, in bursts,
> or where losing a job matters — the MQ surface is the better fit.

---

## Where it fits

Every inbound request — regardless of surface — is authenticated, routed to an
adapter, and run through the one shared pipeline (`PipelineChatService.process_chat`).
The message-queue surface is just another entry point into that same pipeline.

```mermaid
flowchart LR
  subgraph Clients
    H[HTTP clients<br/>REST · OpenAI · A2A · MCP]
    P[MQ producers]
  end

  H -->|synchronous HTTP| GW[ORBIT HTTP server]
  P -->|publish message| Q[(RabbitMQ<br/>orbit.requests)]
  Q --> W[ORBIT MQ consumer<br/>worker]

  GW --> PIPE[PipelineChatService.process_chat<br/>adapter · RAG · LLM]
  W --> PIPE

  PIPE --> GW
  PIPE --> W
  W -->|publish response| R[(RabbitMQ<br/>reply_to / orbit.results)]
  R -->|consume| P
```

The key difference: HTTP callers block on a connection; MQ producers fire-and-forget
to a queue and pick up the answer from a reply queue whenever it's ready.

---

## The queues

When the consumer connects, it declares three queues (names are configurable):

| Queue | Purpose |
| :--- | :--- |
| `orbit.requests` | Where ORBIT **consumes** request messages from. Durable; dead-letters to the DLQ. |
| `orbit.results` | Default reply target used when a message has no `reply_to`. |
| `orbit.dlq` | Dead-letter queue: unparseable messages and unexpected failures land here for inspection/retry. |

`orbit.requests` is declared **durable** with a dead-letter exchange pointing at
`orbit.dlq`, and responses are published with **persistent delivery** — so queued
work and replies survive a broker restart.

---

## The round trip

A single request/response cycle, using AMQP `reply_to` + `correlation_id` so the
producer can match the answer to its request:

```mermaid
sequenceDiagram
    participant P as Producer (client)
    participant RQ as orbit.requests
    participant W as ORBIT worker (consumer)
    participant PIPE as Inference pipeline
    participant RR as reply_to queue

    P->>RQ: publish {id, message, api_key}<br/>correlation_id + reply_to
    W->>RQ: consume (prefetch-limited)
    Note over W: resolve API key → adapter + system_prompt_id<br/>(same rules as /v1/chat)
    W->>PIPE: process_chat(message, adapter, system_prompt_id, api_key)
    PIPE-->>W: response + sources
    W->>RR: publish {id, status, response, ...}<br/>same correlation_id
    W-->>RQ: ack (only after success)
    RR-->>P: consume, match by correlation_id
```

Because the message is **acked only after the handler finishes**, a worker that
crashes mid-request leaves the message unacked — RabbitMQ redelivers it to another
worker (**at-least-once** delivery).

---

## How the producer gets the result

The result is **pushed back over the broker** — there is no synchronous return value
and no status/poll endpoint. ORBIT doesn't reply to the `publish` call; instead the
producer receives the answer by **listening on a reply queue**, matched to its request
by a **correlation id**. This is the standard AMQP request/reply (RPC) pattern.

When it publishes, the producer sets two AMQP message properties:

- **`reply_to`** — the name of a queue *the producer itself consumes from* (typically a
  temporary, exclusive queue it declared).
- **`correlation_id`** — a unique id it generates for this request.

ORBIT's consumer, after running the pipeline, publishes the response envelope **to that
`reply_to` queue, stamped with the same `correlation_id`**. The producer reads its reply
queue and matches by `correlation_id` — exactly what the bundled client does:

```python
replies = await channel.declare_queue(exclusive=True)   # the producer's own reply queue
await channel.default_exchange.publish(
    aio_pika.Message(body=..., correlation_id=corr_id, reply_to=replies.name),
    routing_key="orbit.requests",
)
async for msg in replies:                # listen on the reply queue
    if msg.correlation_id == corr_id:    # this request's answer
        print(json.loads(msg.body))
```

### Two ways to receive the reply

- **Private reply queue (RPC style)** — each producer declares its own temporary queue
  and sets `reply_to`. The correlation id disambiguates multiple in-flight requests that
  share that one queue. This is what [`mq_client.py`](../server/tests/messaging/mq_client.py) uses.
- **Shared results queue** — if a message has **no** `reply_to`, ORBIT publishes to the
  configured `results_queue` (default `orbit.results`). A downstream "results collector"
  service drains that queue and routes each envelope by `correlation_id` (or the
  envelope's `id`).

### What a producer must account for

- **Be listening, or come back later.** The answer is *pushed* to the reply queue when
  processing finishes — the producer either blocks on the reply queue or handles replies
  asynchronously via its own consumer/callback.
- **Correlate by id, not by order.** With multiple workers, replies can arrive out of
  send order; always match on `correlation_id`.
- **Business failures still produce a reply.** A bad key, empty message, or pipeline
  error comes back as a `status: "failed"` envelope on the reply queue — so the producer
  always gets *an* answer for anything that can be answered.
- **Unanswerable messages produce no reply.** Unparseable bodies and unexpected crashes
  are dead-lettered to `orbit.dlq` instead, so **the producer should use a timeout** and
  treat "no reply within N seconds" as a failure to investigate (check the DLQ and worker
  log). The bundled client does this via `--timeout`.

---

## How the consumer handles a message

The consumer distinguishes **business failures** (answer the caller with a `failed`
envelope, then ack) from **infrastructure failures** (reject → dead-letter). The
caller always gets an answer for anything that can be answered; only messages that
*can't* be answered end up in the DLQ.

```mermaid
flowchart TD
  A[Message received] --> B{Valid JSON object?}
  B -->|No| DLQ[Reject → orbit.dlq]
  B -->|Yes| C{API key valid?<br/>key service active}
  C -->|No| F[Publish failed envelope<br/>error: Missing/invalid API key] --> ACK[Ack]
  C -->|Yes| D{message non-empty?}
  D -->|No| F2[Publish failed envelope<br/>error: message must not be empty] --> ACK
  D -->|Yes| E[process_chat via pipeline]
  E -->|returns error result| G[Publish failed envelope<br/>error: pipeline error] --> ACK
  E -->|unexpected exception| DLQ
  E -->|success| H[Publish completed envelope<br/>response + sources] --> ACK

  ACK --> DONE([Done])
  DLQ --> DONE
```

- **Ack** happens when the handler returns normally — including when it published a
  `failed` envelope. The caller is served; the message is done.
- **Reject → DLQ** happens when the handler raises: an unparseable body, or an
  unexpected exception from the pipeline. These are the cases where no meaningful
  reply is possible, so they're preserved for an operator to inspect/replay.

---

## Message contract

**Request** (JSON body published to `orbit.requests`):

```json
{
  "id": "client-supplied-id",
  "message": "Your question here",
  "api_key": "orbit_abcd1234",
  "adapter": "optional-adapter-override",
  "session_id": "optional-session-id",
  "metadata": {}
}
```

- The API key may instead be sent as an AMQP header (`x-api-key`).
- Set the AMQP `reply_to` (a queue the producer consumes) and `correlation_id`
  properties so ORBIT can route and correlate the response.
- `adapter` optionally overrides the adapter — applied **only after** the API key is
  validated; the key's associated system prompt still applies.

**Response envelope** (published to `reply_to`, or `orbit.results` as a fallback, with
the same `correlation_id`):

```json
{
  "id": "client-supplied-id",
  "status": "completed",
  "response": "Generated answer…",
  "sources": [],
  "error": null,
  "metadata": {}
}
```

On a business failure, `status` is `"failed"`, `response` is `null`, and `error`
carries the reason.

---

## Authentication

The MQ path **bypasses the HTTP middleware stack** (CORS, rate limiting, throttling,
admin audit) — those only apply to HTTP requests. Authentication is therefore enforced
**inside the consumer**: whenever the API-key service is active, a valid ORBIT API key
(in the body or the `x-api-key` header) is required, and the adapter + system prompt
are resolved from it exactly as `/v1/chat` does. A missing or invalid key yields a
`failed` envelope, not silent processing.

---

## Hosting the consumer

The consumer is host-agnostic — the same code runs in either mode. Pick **one**
(running both against the same queue would double-consume).

```mermaid
flowchart LR
  subgraph A[Standalone worker · recommended]
    direction TB
    S1[ORBIT HTTP server] --- Q1[(orbit.requests)]
    WK[orbit worker process] --> Q1
  end
  subgraph B[In-process · simplest]
    direction TB
    S2[ORBIT HTTP server<br/>consumer runs inside] --> Q2[(orbit.requests)]
  end
```

### Standalone worker (recommended)

A separate process that consumes the queue independently of the web server — so
batch load doesn't compete with live HTTP serving, and you can scale/deploy/restart
it on its own. It has a managed, PID-file-based lifecycle mirroring the server:

```bash
./bin/orbit.sh worker start   --config config.yaml   # background (writes logs/worker.pid)
./bin/orbit.sh worker status                          # is it running?
./bin/orbit.sh worker restart --config config.yaml    # stop then start
./bin/orbit.sh worker stop                            # graceful (SIGTERM); --force = SIGKILL
./bin/orbit.sh worker run     --config config.yaml    # foreground (dev / systemd / Docker)
```

Run several workers to scale throughput — RabbitMQ distributes messages across all
consumers, bounded per worker by `prefetch`.

### In-process

Set `messaging.run_in_server: true` and start the server normally; the consumer runs
as a background task inside the server process. Simplest to deploy (one process), but
it shares the event loop with live HTTP traffic, and with `performance.workers > 1`
each worker process starts its own consumer.

---

## Delivery guarantees & tuning

| Property | Behavior |
| :--- | :--- |
| **At-least-once** | Messages are acked only after successful handling; a crashed worker's in-flight message is redelivered. Handlers should tolerate occasional redelivery. |
| **Backpressure** | `prefetch` caps how many messages a worker holds unacked at once. |
| **Durability** | `orbit.requests` is durable and responses use persistent delivery, so work survives a broker restart. |
| **Dead-lettering** | Unparseable messages and unexpected exceptions are rejected without requeue and routed to `orbit.dlq`. |
| **Scaling** | Add more standalone workers (same queue) for competing-consumer horizontal scale. |

---

## Configuration

Opt-in, under `messaging` in `config.yaml` (disabled by default). Requires the
`messaging` dependency profile (`./install/setup.sh --profile messaging`, which
installs `aio-pika`):

```yaml
messaging:
  enabled: false
  provider: "rabbitmq"          # rabbitmq
  run_in_server: false          # false = standalone worker; true = in-process
  rabbitmq:
    url: ${MESSAGING_RABBITMQ_URL}      # amqp://user:pass@host:5672/vhost
    requests_queue: "orbit.requests"
    results_queue: "orbit.results"
    dead_letter_queue: "orbit.dlq"
    prefetch: 8
    durable: true
```

`MESSAGING_RABBITMQ_URL` is resolved from `.env` / the environment like any other
`${VAR}` placeholder.

---

## Quick start

1. Install the profile and a broker (see [local RabbitMQ setup](../server/tests/messaging/rabbitmq-local-setup.md)):
   ```bash
   ./install/setup.sh --profile messaging
   docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
   ```
2. Enable `messaging` in `config.yaml` and export the broker URL.
3. Start the server, then the worker:
   ```bash
   ./bin/orbit.sh start
   ./bin/orbit.sh worker start --config config.yaml
   ```
4. Send a message with the bundled client:
   ```bash
   export ORBIT_API_KEY=orbit_...
   python server/tests/messaging/mq_client.py "What can you help me with?"
   ```

You should get a `status: "completed"` envelope with a real response.

---

## Under the hood (source map)

| Component | File |
| :--- | :--- |
| Broker interface + message shape | `server/services/message_brokers/base.py` |
| Broker factory (provider selection) | `server/services/message_brokers/factory.py` |
| RabbitMQ implementation (aio-pika) | `server/services/message_brokers/rabbitmq_provider.py` |
| Consumer (parse → auth → pipeline → reply) | `server/services/messaging/message_consumer.py` |
| Standalone worker entry point | `server/worker_main.py` |
| Worker lifecycle (start/stop/status/restart) | `bin/orbit/services/worker_service.py` |
| In-process wiring (lifespan) | `server/services/service_factory.py` |

Adding a new broker: implement `MessageBroker` in a new module, register it in
`factory.py`'s provider map, and add its settings under `messaging.<provider>` — the
consumer, worker, and lifecycle code are unchanged.

---

## See also

- [ORBIT Server — Message Queue (Async) Protocol](server.md#message-queue-async-protocol) — endpoint/CLI reference
- [Message Queue config (`config.yaml` → `messaging`)](../install/default-config/config.yaml) — commented config reference
- [Local RabbitMQ setup](../server/tests/messaging/rabbitmq-local-setup.md) — get a broker running on macOS
- [MQ integration playbook](../server/tests/messaging/playbook-message-queue.md) — end-to-end verification scenarios
