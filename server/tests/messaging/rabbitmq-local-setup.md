# Local RabbitMQ Setup (macOS) — for testing the ORBIT MQ surface

A short guide to running RabbitMQ locally so you can exercise ORBIT's broker-native
message-queue surface. Pick **one** install path (Docker is fastest), then jump to
[Use it with ORBIT](#use-it-with-orbit).

The full end-to-end scenarios live in [playbook-message-queue.md](playbook-message-queue.md);
this file is just "get a broker running and send one message."

---

## Option A — Docker (recommended)

The quickest path; nothing installed on the host, and the management UI is included.

```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

- `5672` — AMQP port (what ORBIT connects to)
- `15672` — management UI: http://localhost:15672 (login `guest` / `guest`)

Manage the container:

```bash
docker stop rabbitmq          # stop
docker start rabbitmq         # start again (state persists in the container)
docker logs -f rabbitmq       # follow logs
docker rm -f rabbitmq         # remove entirely (wipes state)
```

Wait a few seconds after first start for the broker to come up (`docker logs rabbitmq`
should show `Server startup complete`).

---

## Option B — Homebrew (native)

Runs RabbitMQ directly on macOS, no Docker.

```bash
brew install rabbitmq

# Start it as a background service (auto-starts on login):
brew services start rabbitmq

# ...or run it in the foreground for a one-off session (Ctrl+C to stop):
CONF_ENV_FILE="/opt/homebrew/etc/rabbitmq/rabbitmq-env.conf" /opt/homebrew/sbin/rabbitmq-server
```

Enable the management UI (once):

```bash
/opt/homebrew/sbin/rabbitmq-plugins enable rabbitmq_management
```

Then the UI is at http://localhost:15672 (login `guest` / `guest`), and AMQP is on `5672`.

Manage the service:

```bash
brew services stop rabbitmq
brew services restart rabbitmq
```

> On Intel Macs the Homebrew prefix is `/usr/local` instead of `/opt/homebrew` —
> adjust the paths above accordingly.

---

## Use it with ORBIT

### 1. Install the messaging dependency profile

```bash
./install/setup.sh --profile messaging      # installs aio-pika
venv/bin/python -c "import aio_pika; print('aio-pika', aio_pika.__version__)"
```

### 2. Enable the MQ surface in `config/config.yaml`

```yaml
messaging:
  enabled: true
  provider: "rabbitmq"
  run_in_server: false          # we'll run a standalone worker below
  rabbitmq:
    url: "${MESSAGING_RABBITMQ_URL}"
    requests_queue: "orbit.requests"
    results_queue: "orbit.results"
    dead_letter_queue: "orbit.dlq"
    prefetch: 8
    durable: true
```

```bash
export MESSAGING_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
```

### 3. Create an API key and start the server + worker

```bash
./bin/orbit.sh start                          # terminal 1: the ORBIT server
orbit login --username admin
orbit key create --adapter <your-adapter> --name "mq-test"
export ORBIT_API_KEY=orbit_...                # the key printed above

./bin/orbit.sh worker start --config config.yaml   # background MQ consumer
# (or run it in the foreground in a dedicated terminal:)
# ./bin/orbit.sh worker run --config config.yaml
```

The worker log (`logs/worker.log`, or the terminal if you used `worker run`) should
show `RabbitMQ broker connected ...` then `ORBIT worker running - consuming messages.`
The three queues (`orbit.requests`, `orbit.results`, `orbit.dlq`) now appear in the
management UI. Check it any time with `./bin/orbit.sh worker status`.

> Prefer a single process? Set `run_in_server: true` and just run `./bin/orbit.sh start`
> (don't also run the worker — that would double-consume the queue).

### 4. Send a message with the test client

```bash
python server/tests/messaging/mq_client.py "What can you help me with?"
```

You should see a response envelope with `"status": "completed"` and a non-empty
`"response"`. The client publishes to `orbit.requests`, waits on a temporary
reply queue, and matches the reply by `correlation_id`.

Useful flags:

```bash
python server/tests/messaging/mq_client.py "Hello" \
  --api-key orbit_abcd1234 \        # or rely on $ORBIT_API_KEY
  --adapter my-adapter \            # optional per-message adapter override
  --url amqp://guest:guest@localhost:5672/ \
  --timeout 90
```

---

## Troubleshooting

- **`mq_client.py` times out with no reply** — no consumer is running (start
  `./bin/orbit.sh worker start`, or set `run_in_server: true`), or messages are being
  dead-lettered. Check the *Consumers* count and `orbit.dlq` in the management UI.
- **`aio-pika is not installed`** — run `./install/setup.sh --profile messaging`.
- **Connection refused to `localhost:5672`** — the broker isn't up. Docker:
  `docker ps` for the `rabbitmq` container. Homebrew: `brew services list`.
- **`status: "failed"` with "Missing API key"** — pass `--api-key` or export
  `ORBIT_API_KEY`; a valid key is required whenever the server's API-key service
  is active.
- **Everything lands in `orbit.dlq`** — the message body wasn't valid JSON, or the
  pipeline raised. Inspect a dead-lettered message's payload and the worker log.
- **Reset the broker state** — Docker: `docker rm -f rabbitmq` then re-run the
  `docker run` command. Homebrew: `brew services restart rabbitmq` (to fully wipe,
  delete `/opt/homebrew/var/lib/rabbitmq/`).
