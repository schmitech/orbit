# Threat Telemetry — Bursty Ingestion Demo (Message Queue)

Simulates a spike of sensor-network traffic — the kind of burst a nightly
sweep, a triage backlog, or an event-driven upstream system would produce —
and drops it all onto ORBIT's broker-native async surface at once. Shows the
"spiky / bursty ingestion" fit described in
[`docs/message-queue-architecture.md`](../../docs/message-queue-architecture.md):
the queue absorbs the burst, `prefetch` meters it into the pipeline, and each
reply comes back correlated to its original question — no held HTTP
connections, no dropped requests.

This README is self-contained — you don't need to read the full
[MQ playbook](../../server/tests/messaging/playbook-message-queue.md) to run
the demo, only if something doesn't work and you want the deeper
troubleshooting/failure-mode reference.

> All commands below assume your shell's working directory is the repo root
> (`orbit/`), since paths are given relative to it — e.g. `cd
> /path/to/orbit` first if you're in `clients/orbitchat/` or elsewhere.

## 1. Install the messaging dependency profile

```bash
./install/setup.sh --profile messaging
venv/bin/python -c "import aio_pika; print('aio-pika', aio_pika.__version__)"
```

## 2. Start a local RabbitMQ broker

```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
# Management UI at http://localhost:15672 (guest/guest)
```

## 3. Enable messaging in config.yaml

In `config/config.yaml`, confirm the `messaging` block is enabled and points
at a standalone worker (not in-process):

```yaml
messaging:
  enabled: true
  provider: "rabbitmq"
  run_in_server: false          # standalone worker, not in-process
  rabbitmq:
    url: ${MESSAGING_RABBITMQ_URL}
    requests_queue: "orbit.requests"
    results_queue: "orbit.results"
    dead_letter_queue: "orbit.dlq"
    prefetch: 8
    durable: true
```

This is a global server setting, not scoped to this demo — leaving it enabled
affects your regular dev server too, so make sure that's what you want.

## 4. Export the broker URL and start the server + worker

```bash
export MESSAGING_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
./bin/orbit.sh start
./bin/orbit.sh worker start --config config/config.yaml    # separate process; managed via start/status/stop/restart
```

The worker log (`logs/worker.log`) should show `RabbitMQ broker connected
(requests=orbit.requests, results=orbit.results, dlq=orbit.dlq, prefetch=8)`
followed by `ORBIT worker running - consuming messages.`

## 5. Create an API key for the adapter

```bash
python bin/orbit.py --url http://localhost:3000 key create \
  --adapter intent-sql-sqlite-threat-telemetry \
  --name "Threat Telemetry MQ Demo Key" \
  --prompt-file examples/intent-templates/sql-intent-template/sqlite/threat-telemetry/threat-telemetry-assistant-prompt.md \
  --prompt-name "Threat Telemetry Assistant"

export ORBIT_API_KEY=orbit_...   # the key printed above
```

## 6. Sanity-check with a single message first

Before running the full burst, confirm one message round-trips correctly.
`$ORBIT_API_KEY` must be set in **this** shell (it doesn't persist across
terminals/sessions from step 5) — otherwise the key is missing and the reply
comes back `"status": "failed", "error": "Missing API key"`:

```bash
export ORBIT_API_KEY=orbit_...   # the key printed in step 5

python server/tests/messaging/mq_client.py \
  "Show critical detections in the last hour" \
  --api-key "$ORBIT_API_KEY" \
  --adapter intent-sql-sqlite-threat-telemetry
```

Confirm the reply has `"status": "completed"` and a non-empty `"response"`.
If it times out, check the worker log and the RabbitMQ management UI's
*Consumers* count on `orbit.requests` before moving on.

## 7. Run the burst

```bash
export ORBIT_API_KEY=orbit_...   # same key as step 6, if not already set in this shell

python examples/threat-telemetry-mq/sensor_burst_producer.py --burst-size 20
```

The script publishes all 20 sensor-telemetry questions to `orbit.requests` up
front, then listens on its own reply queue and prints each `status:
completed` (or `failed`) envelope as it arrives, correlated back to the
original question. Run more workers (`./bin/orbit.sh worker start` again, or
scale the standalone worker process) to see throughput scale — RabbitMQ
distributes the burst across all competing consumers.

## Troubleshooting

- **`can't open file '.../server/tests/messaging/mq_client.py'`** — you're not
  running from the repo root; `cd` to `orbit/` first.
- **`"status": "failed", "error": "Missing API key"`** — `$ORBIT_API_KEY` isn't
  set in the current shell (env vars don't carry over between terminals or
  new sessions); re-export it or pass `--api-key` explicitly.
- **`aio-pika is required for RabbitMQ messaging`** — the `messaging` profile
  isn't installed; re-run step 1.
- **Messages pile up in `orbit.requests` (Ready count climbs in the
  management UI)** — no worker is connected; confirm
  `./bin/orbit.sh worker status` reports running.
- **Connection refused to `amqp://...:5672`** — RabbitMQ isn't up, or the
  port isn't mapped; check `docker ps` for the `rabbitmq` container.
- For deeper failure-mode scenarios (dead-letter routing, at-least-once
  redelivery, reply-to fallback, etc.), see the
  [full MQ playbook](../../server/tests/messaging/playbook-message-queue.md).
