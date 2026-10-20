# Decision Car Simulation

A small booth demo for ORBIT's [decision-model adapters](../../docs/adapters/decision-models.md), and the featured example for the **`openai`** decision provider (`config/decision.yaml`).

An arcade-style endless driver. The car always drives forward, speeding up the longer it survives. Hazards continuously scroll toward it in zero or more lanes, and roughly twice a second the game describes the upcoming scene as plain text — the car's current lane, its speed, and each lane's nearest hazard distance — and sends it to ORBIT's `lane-choice` (or `lane-choice-openai`) decision adapter. The typed answer comes back with a probability for each lane and a collision-risk flag; the car continuously steers toward whichever lane the most recent answer recommends. Score builds up for every second survived and every hazard passed; a collision costs a life, and the run ends at zero lives.

Nothing here is simulated. The lane probabilities and collision-risk flag are the adapter's real typed answer, returned through ORBIT's message queue exactly like [Triage Rush](../triage-rush-mq/README.md) and [Sentiment Pulse](../sentiment-pulse-dashboard/README.md) — this demo reuses the same adapter-agnostic bridge, [`../triage-rush-mq/game_bridge.py`](../triage-rush-mq/game_bridge.py), unmodified. Because the car never stops to wait for a reply, the steering is advisory, not authoritative: on a slow reply, the car can reach a hazard before that scene's recommendation has arrived (it keeps steering toward the last one it has). Requests are pipelined — several can be in flight at once — and a reply is only ever allowed to update the steering if it's not older (by request order) than the one already applied, so a late, out-of-order reply can't yank the car back toward a stale lane.

```
browser game ──HTTP/SSE──► game_bridge.py ──AMQP──► orbit.requests ──► ORBIT worker ──► lane-choice-openai
     ▲                          │                                        (DecisionModelStep)
     └──────── SSE reply ◄──────┴──── reply queue ◄──── envelope with `decision` ◄──┘
```

> All commands below assume your working directory is the repo root (`orbit/`).

## 1. Install the messaging profile and start RabbitMQ

```bash
./install/setup.sh --profile messaging
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

## 2. Pick a decision provider

Two adapters answer the same `lane` (choice) and `collision_risk` (noul) questions in `config/adapters/decision.yaml`:

- **`lane-choice`** runs locally on Ollama with `tev1:0.8b` (`ollama pull tev1:0.8b`). Works offline.
- **`lane-choice-openai`** — the featured example — calls OpenAI's hosted Decisions API (`gpt-6-luna`). Needs `OPENAI_API_KEY` in `.env` (restart ORBIT after setting it). See [the decision-models guide](../../docs/adapters/decision-models.md#setup) for how that key is resolved.

Enable whichever adapter(s) you want (`enabled: true`, already the default for both).

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

## 4. Create an API key

```bash
./bin/orbit.sh login
./bin/orbit.sh key create \
  --adapter lane-choice-openai \
  --name "Decision Car Simulation" \
  --prompt-file examples/decision-car-simulation/lane-choice-assistant-prompt.md \
  --prompt-name "Lane Choice Decision Engine"
export ORBIT_API_KEY=orbit_...   # the key printed above
```

Decision adapters don't call a chat LLM, so the prompt doesn't change the answers — those come only from the adapter's `questions`. The prompt stays with the key as documentation of the rules the questions encode. Use `--adapter lane-choice` instead to demo the local Ollama provider.

## 5. Start the bridge

```bash
python examples/triage-rush-mq/game_bridge.py --allowed-adapters lane-choice,lane-choice-openai
```

It serves `http://127.0.0.1:8795`. `--allowed-adapters` lets the game's presenter panel switch providers live; see [the bridge README](../triage-rush-mq/README.md) for every option (`--adapter`, `--timeout`, `--host`/`--port`, etc.).

## 6. Run the game

No build step — it's plain HTML/CSS/JS. Serve the folder with any static server, for example:

```bash
cd examples/decision-car-simulation
python -m http.server 5183
```

Open <http://localhost:5183>. Nothing is sent to ORBIT until you press **Start** (or Space) — and nothing can be sent until the bridge's reply stream is actually open (see [States](#states) below).

## Controls

| Key | Action |
|-----|--------|
| `Space` or the **Start/Pause** button | Start driving, pause, or (after a crash-out) resume where **Play again** left off |
| `P` or the gear icon | Presenter panel: bridge URL, adapter override (from `--allowed-adapters`), broker/worker health, best-score reset |
| `Esc` | Close the presenter panel |

The decision panel shows the three lane probabilities for the most recently *applied* decision as bars (the winning lane highlighted), the `collision_risk` flag, the scene text behind that decision, and Score/Best/Lives/Latency/provider stats. Score builds up continuously (faster at higher speed) plus a bonus for every hazard the car passes; a collision subtracts a life and gives the car a brief grace period before it can be hit again. The run ends, and the overlay offers **Play again**, once lives reach zero — your best score persists in this browser (`localStorage`) across runs.

## States

- **NO BRIDGE** / **NO WORKER** / **CONNECTING REPLY STREAM**: the game pauses and shows why. The first two mean the same as Triage Rush — the bridge isn't reachable, or nothing is consuming `orbit.requests`. The third means the bridge and a worker are healthy, but this browser's `/events` stream hasn't finished opening yet, so starting would risk a reply nobody can deliver. The game never shows a made-up decision, and never lets you start driving, when the pipeline isn't actually live.
- **PAUSED**: you pressed Pause (or Space) yourself; the car and hazards freeze in place.
- **GAME OVER**: lives reached zero. Score and best score are shown; **Play again** resets the run (lives, score, hazards) but keeps the best score.

## Troubleshooting

- **`NO BRIDGE`**: `game_bridge.py` isn't running, or the bridge URL in the presenter panel doesn't match where it's listening.
- **`NO WORKER`**: nothing consumes `orbit.requests` — check `messaging.enabled` and that the server or `./bin/orbit.sh worker` is running.
- **Stuck on `CONNECTING REPLY STREAM`**: the bridge's `/events` endpoint isn't responding — check the bridge's terminal output.
- **The car never changes lanes, or a decision reply never seems to land**: check the bridge's terminal output and `GET http://127.0.0.1:8795/health`; a disabled adapter (or one ORBIT doesn't know about) means the ticket goes to the default chat LLM instead of a decision model, and the lane answer never arrives in the shape this game expects. A request that gets no reply within ~6s is dropped client-side so new requests aren't starved — the car just keeps steering toward its last applied recommendation.
- **`OpenAI API key not configured`**: set `OPENAI_API_KEY` in `.env` and restart ORBIT, or use a key bound to the local `lane-choice` adapter.

## See also

The original local-physics prototype, [`car_simulation.py`](car_simulation.py) (pygame, Intelligent Driver Model), was the starting point for this demo — it never called ORBIT. This game replaces its scripted IDM formula with a real decision-model call for the lane choice, while keeping the same car-following scenario in spirit.
