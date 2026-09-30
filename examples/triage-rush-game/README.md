# Triage Rush Game

A human-vs-AI tradeshow game for ORBIT's [decision-model adapters](../../docs/adapters/decision-models.md). A visitor races ORBIT's `ticket-triage` adapter at sorting support tickets. Every AI decision is real: it goes through RabbitMQ to an ORBIT worker and back, and the card shows the answer's probability and measured round-trip time.

Set up ORBIT, RabbitMQ, the decision model and the bridge first, following [`../triage-rush-mq/README.md`](../triage-rush-mq/README.md).

## Create the API key

From the repo root, create a key bound to the `ticket-triage` adapter, using this folder's prompt:

```bash
./bin/orbit.sh login
./bin/orbit.sh key create \
  --adapter ticket-triage \
  --name "Triage Rush Demo" \
  --prompt-file examples/triage-rush-game/triage-rush-assistant-prompt.md \
  --prompt-name "Triage Rush Decision Engine"
export ORBIT_API_KEY=orbit_...   # the key printed above
```

Export the key in the shell where you start the bridge (`python examples/triage-rush-mq/game_bridge.py`), because the bridge sends it with every ticket. The game never sees the key. One key covers both `ticket-triage` and `ticket-triage-typesafe`.

Decision adapters don't call a chat LLM, so the prompt doesn't change the answers, which come only from the adapter's `questions`. It stays with the key as documentation. [`triage-rush-intro.md`](triage-rush-intro.md) is a matching intro with sample tickets, for a chat client such as orbitchat.

## Run the game

```bash
cd examples/triage-rush-game
npm install
npm run dev          # or: npm run build && npm run preview
```

Open the URL Vite prints (normally <http://localhost:5173>).

## How a round works

- **Attract mode.** When idle, ORBIT plays its lane alone and the leaderboard is shown. Any key, or a tap on the left lane, starts a 3-2-1 countdown.
- **Round.** A round lasts 60 seconds by default. Each ticket appears in both lanes at the same moment, and tickets arrive faster and fall faster as the round goes on.
- **Your lane.** Sort the highlighted (lowest) ticket with keys `1`–`4` or by tapping a bin.
- **ORBIT's lane.** A card shows `deciding…` until its decision arrives. It then drops into the chosen bin, with the confidence bar, urgency, a refund flag and the round-trip time.
- **Scoring**, the same for both lanes: a correct sort is +100 plus a speed bonus, a wrong one is −50, and a ticket that hits the floor is −100. A failed or timed-out AI decision also counts as a miss.
- **End of the round.** You get a head-to-head summary. A top-10 score asks for 3-letter initials.
- **Abandoned rounds.** A round with no input for 20 seconds goes back to attract mode.

## Controls

| Key | Action |
|-----|--------|
| `1`–`4` | Sort into Billing / Technical / Account / Other |
| `S` | **Surge**: drop a burst of tickets (25 by default) on both lanes and onto the queue at once |
| `P` | Presenter panel: bridge URL, adapter (local Ollama or TypeSafe), round length, speed, surge size, health, leaderboard reset |
| `Esc` | Close the presenter panel |

The HUD along the bottom shows AI decisions per second, p50/p95 latency, `orbit.requests` depth, the worker count and tickets in flight.

Settings and the leaderboard are saved in this browser's `localStorage`, so they survive a page reload on the booth machine.

The layout targets a 16:9 display and stacks the lanes vertically on narrow screens.
