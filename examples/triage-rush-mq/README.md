# Triage Rush: Decision Models Over the Message Queue

A booth game for [decision-model adapters](../../docs/adapters/decision-models.md). Support tickets fall down two lanes:

- **YOU**: a visitor sorts each ticket into Billing, Technical, Account or Other before it hits the floor.
- **ORBIT AI**: the same tickets go through ORBIT's message queue to the decision adapter bound to the bridge's API key: `ticket-triage` on a local Ollama model, or `ticket-triage-typesafe` on TypeSafe's hosted model. Each one is sorted as soon as its typed answer comes back, with the probability, urgency and measured round-trip time shown on the card.

Nothing is sent to ORBIT until a visitor presses a key to start a round. If you want the screen moving between visitors, turn on AI autoplay in the presenter panel. The AI then plays alone while idle, which costs one decision every couple of seconds. A **SURGE** drops a burst of tickets onto `orbit.requests` all at once. This is the same burst injection as the [threat telemetry query burst](../threat-telemetry-mq/README.md#part-a--query-burst): the queue absorbs the spike, the worker drains it at `prefetch` pace, and the queue-depth tile shows it rise and recover.

Nothing in the AI lane is simulated. If the bridge, broker or worker is down, the lane says so (`NO BRIDGE`, `NO BROKER`, `NO WORKER`) instead of showing made-up decisions.

```
browser game ──HTTP/SSE──► game_bridge.py ──AMQP──► orbit.requests ──► ORBIT worker ──► ticket-triage-typesafe
     ▲                          │                                        (DecisionModelStep)
     └──────── SSE reply ◄──────┴──── reply queue ◄──── envelope with `decision` ◄──┘
```

This folder holds the bridge, [`game_bridge.py`](game_bridge.py). The game itself is in [`../triage-rush-game/`](../triage-rush-game/).

The game's **Resource decisions** challenge sends a structured `state` (ticket, resource availability, and the visible policy) and a per-ticket `action` question through this same bridge. Both ticket-triage adapters enable question overrides. The worker receives the JSON as its message and returns a typed choice with probabilities; the bridge never decides the answer itself.

> All commands below assume your working directory is the repo root (`orbit/`).

## 1. Install the messaging profile and start RabbitMQ

```bash
./install/setup.sh --profile messaging
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

## 2. Pick a decision provider

The game uses whichever adapter the API key from step 4 is bound to. Pick the provider by choosing the adapter you create the key for, and make sure that adapter is `enabled: true` in `config/adapters/decision.yaml`:

- **`ticket-triage`** runs locally on Ollama with the tiny `tev1:0.8b` model. It works on a laptop and without internet:

  ```bash
  ollama pull tev1:0.8b
  ```

  On a machine with a GPU you can set its `model:` to `nimble` (9B) for higher accuracy.
- **`ticket-triage-typesafe`** calls TypeSafe's hosted `jev-latest` model. It needs `TYPESAFE_API_KEY` in `.env` (restart ORBIT after setting it) and a reliable internet connection at the booth.

To switch providers from the presenter panel during a demo, enable both adapters and start the bridge with `--allowed-adapters ticket-triage,ticket-triage-typesafe`. See [step 5](#5-start-the-bridge).

## 3. Enable messaging and start ORBIT

In `config/config.yaml`:

```yaml
messaging:
  enabled: true
  provider: "rabbitmq"
  run_in_server: true            # or false + `./bin/orbit.sh worker start`
  rabbitmq:
    url: ${MESSAGING_RABBITMQ_URL}
    prefetch: 8
```

```bash
export MESSAGING_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
./bin/orbit.sh start
```

With `run_in_server: false`, also start a worker: `./bin/orbit.sh worker start --config config/config.yaml`. Start more workers to show throughput scaling during a surge.

## 4. Create an API key

```bash
./bin/orbit.sh login
./bin/orbit.sh key create \
  --adapter ticket-triage \
  --name "Triage Rush Demo" \
  --prompt-file examples/triage-rush-game/triage-rush-assistant-prompt.md \
  --prompt-name "Triage Rush Decision Engine"
export ORBIT_API_KEY=orbit_...   # the key printed above
```

Decision adapters don't call a chat LLM, so the prompt doesn't change the model's answers. The answers come only from the adapter's `questions`. The prompt documents the triage rules the questions encode, for anyone who opens the key in the admin panel. [`triage-rush-intro.md`](../triage-rush-game/triage-rush-intro.md) holds a matching intro with sample tickets, for a chat client such as orbitchat.

The bridge doesn't send an adapter by default, so ORBIT routes every ticket to the adapter this key is bound to. The presenter panel shows that adapter's name. ORBIT accepts a per-message adapter override after validating the key, but the bridge only sends one when you allow it with `--allowed-adapters` (or force one with `--adapter`).

Override only to adapters that are **enabled**. ORBIT doesn't load disabled adapters, and a ticket routed to a name it doesn't know is answered by the default chat LLM instead of a decision model.

## 5. Start the bridge

```bash
python examples/triage-rush-mq/game_bridge.py
```

It serves `http://127.0.0.1:8795`. By default it sends no adapter, so the API key's adapter applies. Useful options:

| Option | Default | Meaning |
|--------|---------|---------|
| `--api-key` | `$ORBIT_API_KEY` | Key sent with each message |
| `--adapter` | none | Send this adapter with every ticket, overriding the key's adapter |
| `--allowed-adapters` | none | Adapter overrides the presenter panel may choose, e.g. `ticket-triage,ticket-triage-typesafe` |
| `--orbit-url` | `http://localhost:3000` | ORBIT server, used only to show the key's adapter name in the game |
| `--url` | `$MESSAGING_RABBITMQ_URL` or `amqp://guest:guest@localhost:5672/` | Broker |
| `--host` / `--port` | `127.0.0.1` / `8795` | Where the bridge listens. It publishes with your key, so keep it on localhost unless the game runs on another machine |
| `--timeout` | `30` | Seconds before an unanswered ticket is reported as timed out |

Quick check without the game:

```bash
curl -N http://127.0.0.1:8795/events &
curl -X POST http://127.0.0.1:8795/publish -H "Content-Type: application/json" \
  -d '{"items":[{"id":"check-1","text":"I was charged twice, please refund me"}]}'
# → data: {"type": "decision", "id": "check-1", "status": "completed", "answers": {"team": {"choice": "billing", ...}}, "latency_ms": 140, ...}
```

The bridge endpoints:

- `POST /publish`: `{"items": [{"id", "text", "state"?, "questions"?}], "adapter"?}`, at most 50 items per call. `state` and `questions` must be supplied together, and `state.ticket` must match `text`. Without them, the plain-text team-routing behavior is unchanged.
- `GET /events`: Server-Sent Events, one per reply.
- `GET /health`: broker status, plus queue depth and consumer count for `orbit.requests`.

## 6. Run the game

```bash
cd examples/triage-rush-game
npm install
npm run dev
```

Open <http://localhost:5180>. See [the game README](../triage-rush-game/README.md) for the controls.

## Booth checklist

- **Warm up the model** before the doors open. Play a round, or turn on autoplay for a minute, so the first visitor doesn't wait on a cold model load.
- **Fullscreen the browser** (F11, or ⌃⌘F on macOS). Turn off sleep and the screen saver.
- **Keep the game tab in front.** Browsers pause animation in hidden tabs.
- **Show the queue.** Press `S` for a surge while a visitor plays. Point at the queue-depth and latency tiles as they spike and drain. Open the RabbitMQ UI (<http://localhost:15672>) on a second screen for the broker's view.
- **Show the provider switch.** Start the bridge with `--allowed-adapters ticket-triage,ticket-triage-typesafe` (both enabled), then press `P` and change the adapter to compare local and hosted latency.
- **Pause when you step away.** With autoplay on, the game sends a ticket to ORBIT every couple of seconds, which costs TypeSafe calls. Press **Pause** (top right) to stop all requests, including rounds and surges. Press **Resume** to start again.
- **Reset the leaderboard** between show days from the presenter panel (`P`).

## Troubleshooting

- **`NO BRIDGE`**: `game_bridge.py` isn't running, or the bridge URL in the presenter panel (`P`) doesn't match `--host`/`--port`.
- **`NO REPLY STREAM`**: the game reaches the bridge but can't open its `/events` stream. Restart `game_bridge.py` and reload the page.
- **`NO WORKER`**: nothing consumes `orbit.requests`. Check that `messaging.enabled` is true and the server (or `./bin/orbit.sh worker`) is running.
- **Cards show `Missing API key`** or **`API key resolution failed`**: `$ORBIT_API_KEY` isn't set in the bridge's shell, or the key is invalid. The presenter panel shows whether the bridge has a key.
- **Cards show `Ollama decision error (HTTP 404): model "tev1:0.8b" not found`**: run `ollama pull tev1:0.8b`.
- **Cards time out during a surge**: a single small-laptop worker can fall behind a large surge. Lower the surge size in the presenter panel, raise `--timeout`, or start another worker.
- **`TypeSafe API key not configured`**: set `TYPESAFE_API_KEY` in `.env` and restart ORBIT, or use a key bound to the local `ticket-triage` adapter.
