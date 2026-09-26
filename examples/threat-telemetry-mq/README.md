# Threat Telemetry — Message Queue Demos

Three independent pieces over the same broker/database, modeling a real
sensor-network deployment:

- **[Part A — Query burst](#part-a--query-burst)**: a spike of NL questions
  (an operator or an automated triage system asking ORBIT things all at
  once) hits ORBIT's broker-native async surface. Shows the "spiky / bursty
  ingestion" fit described in
  [`docs/message-queue-architecture.md`](../../docs/message-queue-architecture.md):
  the queue absorbs the burst, `prefetch` meters it into the pipeline, and
  each reply comes back correlated to its original question. **Read-only** —
  it never changes the underlying data.
- **[Part B — Live sensor data ingestion](#part-b--live-sensor-data-ingestion)**:
  a simulated sensor feed publishes raw detection events to the broker, and a
  dedicated ingest consumer **persists them into `threat_telemetry.db`** —
  so new detections actually show up when you ask ORBIT about them
  afterward. This is the piece that makes "real-time" mean something: data
  genuinely changes, not just query load.
- **[Part C — Live dashboard](#part-c--live-dashboard-no-simulated-data)**:
  a bridge server that lets `examples/threat-telemetry-dashboard/` show real
  sensor status, alerts, and queue metrics instead of presentation
  placeholders, with a working write-back "acknowledge" action.

Parts A and B share the same setup (steps 1-5 below) before splitting; Part C
only needs the database and, for queue metrics, RabbitMQ — no worker/API key
required for that part on its own.

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

## Part A — Query burst

### What this demonstrates

Picture an incident: something happens, and suddenly 20 different questions
come in at once — an operator asking follow-ups, an automated triage system
polling for status, other analysts checking in. Instead of each one making a
separate HTTP request and waiting on its own connection, they all get
dropped onto a message queue at once.

What actually happens, step by step:

1. **The producer fires all N questions in one shot** — real natural-language
   questions like "show critical detections in the last hour" or "how many
   open alerts are there right now." Each one is published to ORBIT's
   `orbit.requests` queue with a unique correlation ID, and the producer
   doesn't wait for a reply before sending the next one — it dumps the whole
   batch onto the queue immediately.
2. **ORBIT's worker drains the queue at its own pace.** It isn't overwhelmed
   by the burst — `prefetch` (8 in this demo) caps how many messages it
   holds unacknowledged at once, so it processes a bounded number in flight
   rather than trying to do all of them simultaneously. This is the
   backpressure story: the queue absorbs the spike, the worker meters it
   into the pipeline.
3. **Each question goes through the real inference pipeline** — the same
   intent-matching, SQL retrieval, and LLM answer-generation as a normal
   chat message. This is not a shortcut or a canned response; it's the
   identical processing `/v1/chat` would do, just running asynchronously
   instead of over a held-open HTTP connection.
4. **Replies come back correlated, not necessarily in order.** As each answer
   finishes, the worker publishes it to the producer's private reply queue,
   tagged with that question's correlation ID. The producer matches each
   reply to its original question — with multiple things in flight, answers
   can come back out of send order, and correlation IDs are what keep them
   straight.
5. **The producer prints each answer as it arrives**, then reports a final
   tally: completed vs. failed vs. still outstanding.

The takeaway: nothing is blocked waiting on an open HTTP connection, nothing
gets silently dropped — the queue durably holds the work, and throughput
scales by adding more worker processes listening on the same queue, since
RabbitMQ load-balances across all of them.

**This is a query burst, not a data-ingestion burst** — it's read-only
questions against the existing data, and never adds or changes anything in
`threat_telemetry.db`. For a demo where new sensor data actually gets
persisted, see [Part B](#part-b--live-sensor-data-ingestion) below.

### 6. Sanity-check with a single message first

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

### 7. Run the burst

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

### Watch it live in the dashboard

The producer also runs a small local HTTP status server (default
`http://localhost:8787/status`) so the dashboard can show each reply as it
arrives, instead of only being visible in this terminal. It's a demo-only
bridge, not part of ORBIT — a browser can't speak AMQP directly, so this is
just a plain JSON endpoint the dashboard polls once a second.

1. Start the dashboard (see `examples/threat-telemetry-dashboard/README.md`)
   and open its **Intelligence** tab (or scroll down on the overview) to find
   the **Query Burst Monitor** panel. With no burst running yet, it shows "NO
   PRODUCER DETECTED".
2. Run the burst as above. The panel switches to "IN PROGRESS" and each
   question/answer appears live, most recent first, with a running tally of
   published/completed/failed/outstanding.
3. When the burst finishes, the server keeps serving the final tally for
   `--linger-seconds` (default 120s) before shutting down, so the completed
   state stays visible on screen instead of reverting to "no producer
   detected" the instant the script exits. Pass `--linger-seconds 0` to skip
   this, or `--no-status-server` to disable the bridge entirely.
4. If you're running the dashboard on a different machine or port, or the
   producer on a non-default `--status-port`, edit the **Status Source**
   field directly in the panel — it's saved in the browser for next time.

## Part B — Live sensor data ingestion

Unlike the query burst, this demo has ORBIT's own worker do nothing — the
ingest consumer is a **separate, standalone service** that consumes raw
detection events off its own queue and writes them straight into
`threat_telemetry.db`. ORBIT's chat/MQ worker only ever runs read-only intent
templates against that database; it has no path to insert data itself. This
mirrors a real deployment: sensors/upstream systems publish to a queue, a
dedicated ingest service persists the data, and ORBIT is queried afterward
by an analyst or dashboard.

### 8. Start the ingest consumer

In its own terminal (it runs until you stop it with Ctrl+C):

```bash
python examples/threat-telemetry-mq/telemetry_ingest_consumer.py
```

It declares `orbit.telemetry.events` (durable, dead-lettering malformed
events to `orbit.telemetry.dlq`) and prints one line per detection
persisted, e.g.:

```
[persisted] det_evt_686a1620c8 sensor=sen_006 object=aircraft severity=high, raised alert alr_evt_c7b39462d1
```

### 9. Publish a simulated sensor feed

In another terminal:

```bash
# A slow trickle (2s apart), like a live feed
python examples/threat-telemetry-mq/sensor_event_producer.py --count 10 --interval 2

# Or a burst, published all at once
python examples/threat-telemetry-mq/sensor_event_producer.py --count 50 --interval 0
```

Each event is a raw JSON detection (sensor, object type, severity,
confidence, coordinates) — not an NL question. The consumer picks each one
up, inserts a `detections` row, and raises an `alerts` row too if severity is
`high`/`critical`.

### 10. Confirm ORBIT sees the new data

Ask about the same window the events landed in — the new `det_evt_*`/
`alr_evt_*` rows should appear alongside the original dataset:

```bash
python server/tests/messaging/mq_client.py \
  "Show critical detections in the last hour" \
  --api-key "$ORBIT_API_KEY" \
  --adapter intent-sql-sqlite-threat-telemetry
```

Or check directly:

```bash
sqlite3 examples/intent-templates/sql-intent-template/sqlite/threat-telemetry/threat_telemetry.db \
  "SELECT detection_id, sensor_id, object_type, severity, detected_at FROM detections WHERE detection_id LIKE 'det_evt_%' ORDER BY detected_at DESC;"
```

## Part C — Live dashboard (no simulated data)

`live_stats_server.py` is a third bridge in this folder: a read/write API
over `threat_telemetry.db` and RabbitMQ's management API, built specifically
so `examples/threat-telemetry-dashboard/` can show real sensor status, real
alerts, real severity distribution, and real queue depth/throughput instead
of presentation placeholders — with a working "acknowledge" button that
writes back to the database.

```bash
python examples/threat-telemetry-mq/live_stats_server.py
```

See `examples/threat-telemetry-dashboard/README.md` for the full walkthrough
of wiring the dashboard to it.

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
- **`Database not found at ...`** (Part B) — generate the database first: `cd
  examples/intent-templates/sql-intent-template/sqlite/threat-telemetry &&
  python3 generate_threat_telemetry_data.py --force`.
- **New detections don't show up in query answers** (Part B) — confirm the
  ingest consumer's terminal actually printed `[persisted] ...` lines for
  your events (not `[dead-letter] ...`, which means the event failed
  validation); then confirm your question's time window is generous enough
  (e.g. "in the last hour" if the events were just published).
- For deeper failure-mode scenarios (dead-letter routing, at-least-once
  redelivery, reply-to fallback, etc.), see the
  [full MQ playbook](../../server/tests/messaging/playbook-message-queue.md).
