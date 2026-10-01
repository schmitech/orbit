# Sentiment Pulse — manual end-to-end test playbook

For testing the sentiment-analysis adapter, bridge and dashboard locally, with
RabbitMQ (Docker) and ORBIT already running. This is a **manual, local-only** test —
the adapter stays `enabled: false` in the repo until the Phase 1 gate passes (see
[docs/roadmap/complete/decision-model-sentiment-analysis.md](../../docs/roadmap/complete/decision-model-sentiment-analysis.md)).
Revert the config change in step 7 when you're done.

## 1. Temporarily enable the adapter

```bash
sed -i '' '/name: "sentiment-analysis"$/,/enabled: false/{s/enabled: false/enabled: true/}' config/adapters/decision.yaml
```

(or hand-edit `sentiment-analysis` or `sentiment-analysis-local` to `enabled: true` —
pick whichever provider you want to test. TypeSafe needs `TYPESAFE_API_KEY` set;
Ollama needs `ollama pull tev1:0.8b` done.)

Reload it:
```bash
./bin/orbit.sh restart
```

## 2. Create an API key bound to it

```bash
./bin/orbit.sh key create \
  --adapter sentiment-analysis \
  --name "Sentiment Pulse Test" \
  --prompt-file examples/sentiment-pulse-assistant-prompt.md
```
Copy the printed key (`orbit_...`).

## 3. Quick sanity check with the eval script (optional but fast)

Before touching the UI, confirm the adapter actually answers:
```bash
export ORBIT_API_KEY=orbit_the_key_from_step_2
printf '%s\n' '{"id":"rec-1","text":"Arrived two days late but support fixed it in minutes. Love it.","polarity":"mixed","valence":3,"sarcasm":false,"needs_escalation":false,"aspects":{"price":"not_mentioned","support":"positive","product":"not_mentioned","delivery":"negative"},"lang":"en"}' > /tmp/smoke.jsonl

python utils/scripts/eval_decision_adapter.py sentiment-analysis /tmp/smoke.jsonl --split tune --via-api --api-key "$ORBIT_API_KEY"
```
This hits `/v1/chat` directly and prints the parsed answers — confirms the adapter is
live before you add the bridge/UI into the mix.

> `--via-api` sends `X-Session-ID` automatically (a fresh one per record — each record
> is an independent decision, not a conversation). If you see
> `HTTP 400: {'detail': 'Session ID is required...'}` anyway, your ORBIT instance has
> `session_id.required` or `chat_history.session.required` on with `auto_generate` off
> and the running server predates this fix — pull latest `utils/scripts/eval_decision_adapter.py`.

**For a bigger sanity check** (60 records instead of 1), use the synthetic dry-run
tuning set instead of hand-typing a record — see
[eval/dry-run/README.md](eval/dry-run/README.md) for what it is and how it's generated:
```bash
python utils/scripts/eval_decision_adapter.py sentiment-analysis \
  examples/sentiment-pulse/eval/dry-run/sentiment-tune.sample.jsonl \
  --split tune --via-api --api-key "$ORBIT_API_KEY"
```
This is still synthetic data — fine for confirming the plumbing and getting a feel for
the metrics report, never for an actual tuning decision or gate claim.

## 4. Start the bridge

```bash
export ORBIT_API_KEY=orbit_the_key_from_step_2
python examples/triage-rush-mq/game_bridge.py \
  --adapter sentiment-analysis \
  --allowed-adapters sentiment-analysis,sentiment-analysis-local
```
Check its health:
```bash
curl -s http://localhost:8795/health | python3 -m json.tool
```
`broker: true` and `queue.consumers >= 1` (your running ORBIT's in-process worker,
since `messaging.run_in_server: true` in `config.yaml`) confirm it's ready.

## 5. Start the dashboard

```bash
cd examples/sentiment-pulse-dashboard
npm install   # first time only
npm run dev
```
Open http://localhost:5182.

## 6. Exercise it

- Confirm the topbar shows **LIVE** (not NO BRIDGE/NO WORKER/NO REPLY STREAM) and
  nothing was sent yet.
- **Type your own**: paste a sentence, confirm a real decision comes back with latency.
- **Play**: toggle it, confirm the Live feed, Polarity distribution, and the HUD's
  decisions/sec all fill in from real traffic (not just the feed — if Polarity
  distribution says "No answers yet" while the feed is clearly populating, that's the
  bug where the dashboard checked a decision's `status` for `"ok"` instead of the
  bridge's actual `"completed"`; confirm `src/main.jsx`'s `resolved` filter uses
  `"completed"`).
- **Surge (100)**: confirm the queue drains without timeouts (watch the bridge's console/`/health` `in_flight`).
- **Pause all requests**: confirm Play/Surge/Type-your-own all disable and nothing more
  is sent; reload the page and confirm the pause persisted (localStorage).
- Note that Mood gauge, Aspect heatmap, sarcasm chips, escalation lane, and the
  routing panel stay hidden — that's expected, `src/gate.js` is still unfilled.
- Check the browser console for errors.

## 7. Clean up afterward

- Stop the bridge and dashboard (Ctrl+C).
- Revert the adapter back to disabled:
  ```bash
  git diff config/adapters/decision.yaml   # confirm it's just the enabled flag
  git checkout -- config/adapters/decision.yaml
  ./bin/orbit.sh restart
  ```
- Optionally deactivate the test API key: `./bin/orbit.sh key deactivate <key-id>`.
