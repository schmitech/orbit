# Sentiment Pulse — live sentiment-analysis dashboard

**Status: dormant.** This dashboard is built and wired up, but `src/gate.js` is
intentionally unfilled until the Phase 1 held-out eval actually runs for a provider
and lands in a High or Middle band — see
[docs/roadmap/complete/decision-model-sentiment-analysis.md](../../docs/roadmap/complete/decision-model-sentiment-analysis.md).
Don't run this at a booth or demo it until that doc's Results section has a real,
dated entry and `gate.js` reflects it. With `gate.js` unfilled, the escalation lane
and routing-signal panel stay hidden and no band/claim is shown anywhere in the UI —
only a small "DORMANT" badge in the topbar. There's no on-screen banner explaining
why those panels are missing (deliberately, to keep the live view uncluttered); this
README is that explanation. If you're looking at the dashboard and wondering where the
escalation lane or routing panel went, this is why — check `src/gate.js`.

Every number in this dashboard comes from a real adapter call made through the bridge
below. Nothing is fabricated client-side — the `reveal`-only labels in `reviews.js`
are never sent to the server or shown as if they were the model's answer.

## Setup

1. Install dependencies and run the dev server (pinned to port 5182 so it doesn't
   collide with orbitchat (5173) or Triage Rush (5180)):
   ```bash
   cd examples/sentiment-pulse-dashboard
   npm install
   npm run dev
   ```
2. Run the Triage Rush bridge, pointed at the sentiment adapters (the bridge is
   adapter-agnostic — see its own README for details):
   ```bash
   export ORBIT_API_KEY=orbit_your_key
   python examples/triage-rush-mq/game_bridge.py \
     --adapter sentiment-analysis \
     --allowed-adapters sentiment-analysis,sentiment-analysis-local
   ```
   Create the API key with `--adapter sentiment-analysis` and a prompt file (see
   `examples/sentiment-pulse-assistant-prompt.md`).
3. Open http://localhost:5182. Nothing is sent until you press **Play** or **Surge**.

## What's here

- `src/main.jsx` — the dashboard: health polling, the bridge's `/events` SSE stream,
  Play/Pause/Surge controls, a "Pause all requests" toggle persisted in
  `localStorage`, and the panels below.
- `src/gate.js` — the Phase 1 gate result for the provider this instance targets.
  Every panel checks this before showing a band, a routing line, or the escalation
  lane. Fill it in only from a frozen, recorded held-out run.
- `src/reviews.js` — the demo deck (~24 starter reviews about a fictional product;
  expand to ~150 per the eval plan before a real booth run). Separate from
  `examples/sentiment-pulse/eval/`, so the demo can never overfit the gate.
- `src/styles.css` — the same dark HUD tokens as `examples/triage-rush-game` and
  `examples/threat-telemetry-dashboard`.

## Panels

- **Live feed** — each review fills in with its polarity chip, valence, sarcasm flag
  and latency as its decision arrives.
- **Mood gauge** — rolling mean of expected valence over the last 20 answers, with a
  60-second sparkline.
- **Polarity distribution** — live counts and shares.
- **Aspect heatmap** — price/support/product/delivery × positive/negative;
  `not_mentioned` is excluded.
- **Escalation lane** — only rendered when `gate.js` says the escalation cutoff
  passed.
- **Routing-signal panel** — only rendered when `gate.js` says polarity reached the
  High band.
- **HUD** — decisions/sec, p50/p95 latency, queue depth, worker count, provider, and
  the gate band (from `/health` and the SSE stream).
- **Type your own** — capped at 280 characters, never stored, published only through
  the bridge.

## States

- **NO BRIDGE** / **NO WORKER** / **NO REPLY STREAM** work the same way as Triage
  Rush: the dashboard never shows a made-up answer when the pipeline isn't actually
  live.

## Booth checklist (once the gate has actually passed)

- Pause requests when stepping away from the booth.
- Warm up: Play at a low rate for a minute before anyone approaches, so the first
  visitor doesn't see an empty feed.
- Run fullscreen.
- Confirm `--burst 100` drains inside the bridge's `--timeout` on whichever provider
  you're demoing (see the eval plan's Phase 1 step 5 and Phase 2 "Timeout check").

## Build check

```bash
npm run build
```
