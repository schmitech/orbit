# Triage Rush Game

A human-vs-AI game for ORBIT's [decision-model adapters](../../docs/adapters/decision-models.md). A visitor races ORBIT's ticket-triage decision adapter at sorting support tickets. By default it's `ticket-triage-typesafe`, TypeSafe's hosted model; `ticket-triage` on local Ollama is the offline fallback. Every AI decision is real: it goes through RabbitMQ to an ORBIT worker and back, and the card shows the answer's probability and measured round-trip time.

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

Open <http://localhost:5180>. Both `dev` and `preview` use that fixed port (with `--strictPort`), so the booth URL never moves. If something else already uses 5180, Vite exits with an error rather than choosing another port.

## How a round works

- **Waiting screen.** When idle, the game shows the leaderboard and sends nothing to ORBIT. Any key, or a tap on the left lane, starts a 3-2-1 countdown, and tickets start flowing to ORBIT when the round begins. To have ORBIT play its lane alone while idle (attract mode), turn on **AI autoplay when idle** in the presenter panel. That sends a ticket about every 2 seconds.
- **Round.** A round lasts 60 seconds by default. Each ticket appears in both lanes at the same moment, and tickets arrive faster and fall faster as the round goes on.
- **Your lane.** Sort the highlighted (lowest) ticket with keys `1`–`4` or by tapping a bin.
- **ORBIT's lane.** A card shows `deciding…` until its decision arrives. The card then shows the answer: the confidence bar, urgency, a refund flag and the round-trip time. It stays in the lane for 1.5 seconds, then drops into the chosen bin. Both copies of a ticket carry the same `#` number, so you can check they're the same question. Set the hold in the presenter panel (**AI answer display**, 0–4 s). It's display only: scores and latency use the real decision time.
- **Queued cards.** Cards never overlap. A card that catches up with the one below it stops on top of it, and cards with no room yet wait above the lane, counted by a **+N waiting** badge. A waiting card can't be missed until it has fallen to the floor.
- **Scoring**, the same for both lanes: a correct sort is +100 plus a speed bonus, a wrong one is −50, and a ticket that hits the floor is −100. A failed or timed-out AI decision also counts as a miss.
- **End of the round.** You get a head-to-head summary. A top-10 score asks for 3-letter initials.
- **Abandoned rounds.** A round with no input for 20 seconds goes back to the waiting screen.

## Controls

| Key | Action |
|-----|--------|
| `1`–`4` | Sort into Billing / Technical / Account / Other |
| **Pause** button (top right) | Stop sending tickets to ORBIT: ends any round, clears the lanes, and blocks new rounds, surges and autoplay. It stays paused across page reloads until you press **Resume**. Tickets already published still get answered. Also in the presenter panel |
| `S` | **Surge**: drop a burst of tickets (25 by default) on both lanes and onto the queue at once. Your lane piles up with a **+N waiting** badge while ORBIT works through its queue |
| `P` | Presenter panel: bridge URL, adapter (local Ollama or TypeSafe), round length, speed, surge size, health, leaderboard reset |
| `Esc` | Close the presenter panel |

The HUD along the bottom shows AI decisions per second, p50/p95 latency, `orbit.requests` depth, the worker count and tickets in flight.

Settings and the leaderboard are saved in this browser's `localStorage`, so they survive a page reload on the booth machine.

The layout targets a 16:9 display and stacks the lanes vertically on narrow screens.
