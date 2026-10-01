# Sentiment-analysis eval sets

Two labeled JSONL files go here, per `docs/roadmap/complete/decision-model-sentiment-analysis.md`
(Phase 0 — Labeled dataset):

- `sentiment-tune.jsonl` — 60 texts, 15 per polarity, used only for tuning wording and thresholds.
- `sentiment-test.jsonl` — 120 texts, 30 per polarity, frozen before any tuning and evaluated exactly once.
- `sentiment-test-multilingual.jsonl` — 10 French/Spanish texts, reported separately, never gates.

Every record labels every signal:

```json
{"id": "rev-001", "text": "Arrived two days late but support fixed it in minutes. Love it.",
 "polarity": "mixed", "valence": 3, "sarcasm": false, "needs_escalation": false,
 "aspects": {"price": "not_mentioned", "support": "positive", "product": "not_mentioned", "delivery": "negative"},
 "lang": "en"}
```

- `polarity`: one of `positive`, `negative`, `neutral`, `mixed`.
- `valence`: an int 0 (very negative) .. 4 (very positive).
- `sarcasm`, `needs_escalation`: booleans.
- `aspects`: all four of `price`, `support`, `product`, `delivery`, each `positive`, `negative` or `not_mentioned`.
- `lang`: BCP-47-ish language code (`en`, `fr`, `es`, ...).

These are produced by two annotators labeling independently, with an adjudicator resolving
disagreements — not generated. See [LABELING_GUIDE.md](LABELING_GUIDE.md) for the full
annotator instructions (definitions, worked examples, and the agreement/adjudication
workflow), and [Signals](../../../docs/roadmap/complete/decision-model-sentiment-analysis.md#signals)
for the short reference version.

## Validating a dataset

Once both files exist:

```bash
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python examples/sentiment-pulse/eval/check_sentiment_dataset.py
```

Checks schema completeness, the composition quotas, and that no text id appears in both sets.

## Running the eval

```bash
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python utils/scripts/eval_decision_adapter.py \
  sentiment-analysis examples/sentiment-pulse/eval/sentiment-tune.jsonl --split tune
```
