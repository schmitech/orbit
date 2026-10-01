# Dry-run eval sets

**Synthetic. Not real labels. Never use these to tune wording, pick thresholds, or
justify a gate decision.** They exist only to exercise the Phase 1 pipeline —
`check_sentiment_dataset.py`, `eval_decision_adapter.py`, and the tune → freeze → test
flow — before committing to real human annotation. See
[../LABELING_GUIDE.md](../LABELING_GUIDE.md) for the real process and
[docs/roadmap/complete/decision-model-sentiment-analysis.md](../../../../docs/roadmap/complete/decision-model-sentiment-analysis.md)
for the plan these steps come from.

## What's here

- `generate_sample_tuning_set.py` — deterministic generator (fixed random seeds).
  Produces:
  - `sentiment-tune.sample.jsonl` (60 records)
  - `sentiment-test.sample.jsonl` (120 records)
  Both pass the same schema and composition quotas as the real sets, and the two
  files never share an id. Confirm with:
  ```bash
  python ../check_sentiment_dataset.py \
    --tune sentiment-tune.sample.jsonl --test sentiment-test.sample.jsonl \
    --tune-polarity-each 15 --tune-min-escalation 12 \
    --test-polarity-each 30 --test-min-escalation 25
  ```
  (run from this `dry-run/` directory; from the repo root, prefix both `--tune`/`--test`
  paths with `examples/sentiment-pulse/eval/dry-run/` instead). The quota flags above
  are also the script's defaults, so they can be omitted for this particular sample set.
- Text is templated, not hand-written prose — readable enough to spot-check, not
  meant to be linguistically natural. A few labels are intentionally odd-but-valid
  edge cases (e.g. one positive aspect clause inside an overall-negative review),
  which is realistic and fine for pipeline testing.

Regenerate at any time:
```bash
python examples/sentiment-pulse/eval/dry-run/generate_sample_tuning_set.py
```

## Dry-running steps 2-4 of Phase 1

**2. Tune** (direct mode, adapter can stay disabled):
```bash
python utils/scripts/eval_decision_adapter.py sentiment-analysis \
  examples/sentiment-pulse/eval/dry-run/sentiment-tune.sample.jsonl --split tune
```
Read the selective-accuracy table for `polarity` and pick a candidate `t_route`
(lowest t with coverage >= 60% and accepted error <= 5%), and the same idea for
`needs_escalation`'s precision/recall table to pick `t_esc`.

**3. "Freeze"** — for a dry run this just means picking concrete values to pass next,
not actually committing anything to the roadmap doc (that step is real-data only).

**4. Test once**:
```bash
python utils/scripts/eval_decision_adapter.py sentiment-analysis \
  examples/sentiment-pulse/eval/dry-run/sentiment-test.sample.jsonl --split test \
  --routing-signal p_top --routing-threshold <value-or-none> --escalation-threshold <value-or-none>
```
Confirm the report shows only the frozen threshold's result (no per-candidate table),
and that `--routing-threshold none` / `--escalation-threshold none` correctly print
"no threshold" instead of a number.

Both commands need `TYPESAFE_API_KEY` (for the TypeSafe provider) or a local Ollama
with `tev1:0.8b` pulled, since direct mode calls the real `DecisionService`, just with
synthetic input text instead of real customer reviews. `--via-api` works the same way
with `--api-key`/`$ORBIT_API_KEY` instead, against a running ORBIT + enabled adapter
(see [../../TESTING_PLAYBOOK.md](../../TESTING_PLAYBOOK.md)).

## Worked example (via `--via-api`, TypeSafe `jev-latest`)

An actual dry run end to end, included here so the threshold-selection reasoning and
the report shapes are concrete, not just described. **These numbers are from the
synthetic set — they say nothing about real model quality and aren't gate-worthy.**

**Tune** (full command omits `--split test`'s frozen-threshold flags):
```bash
python utils/scripts/eval_decision_adapter.py sentiment-analysis \
  examples/sentiment-pulse/eval/dry-run/sentiment-tune.sample.jsonl \
  --split tune --via-api --api-key "$ORBIT_API_KEY" --routing-signal p_top
```
```
## polarity (choice)
- n=60, missing/errored=0
- accuracy=0.700, macro-F1=0.701
- selective accuracy (tuning candidates):
  | t | coverage | error_rate | 95% CI |
  |---|---|---|---|
  | 0.5 | 1.00 | 0.300 | [0.199, 0.425] |
  | 0.6 | 0.88 | 0.283 | [0.180, 0.416] |
  | 0.7 | 0.85 | 0.255 | [0.155, 0.389] |
  | 0.8 | 0.75 | 0.200 | [0.109, 0.338] |
  | 0.9 | 0.62 | 0.081 | [0.028, 0.213] |

## needs_escalation (noul)
- AUROC=1.000
  - @0.5: precision=1.000, recall=1.000, false_alert_share=0.000
  - @0.8: precision=1.000, recall=0.750, false_alert_share=0.000
```
Pick thresholds from this table:
- **`t_route`**: the gate rule is "lowest t with coverage >= 60% and accepted error
  <= 5%". Even t=0.9 (the strictest candidate, lowest coverage) only gets the error
  rate down to 8.1% — none of the five candidates clear 5%, so `t_route = none`.
- **`t_esc`**: the rule is "lowest cutoff with precision >= 0.8 and recall >= 0.6".
  @0.5 already has precision 1.0 and recall 1.0, so `t_esc = 0.5`.

**"Freeze"** — for a dry run this is just writing those two values down to pass next;
there's no roadmap-doc commit step for synthetic data.

**Test once**, with both frozen:
```bash
python utils/scripts/eval_decision_adapter.py sentiment-analysis \
  examples/sentiment-pulse/eval/dry-run/sentiment-test.sample.jsonl \
  --split test --via-api --api-key "$ORBIT_API_KEY" \
  --routing-signal p_top --routing-threshold none --escalation-threshold 0.5
```
```
## polarity (choice)
- n=120, missing/errored=0
- accuracy=0.742, macro-F1=0.746
- routing: no threshold

## needs_escalation (noul)
- n=120, missing/errored=0
- AUROC=1.000
  - @0.5: precision=1.000, recall=1.000, false_alert_share=0.000
  - @0.8: precision=1.000, recall=0.680, false_alert_share=0.000
- escalation cutoff @ t=0.5: precision=1.000, recall=1.000, false_alert_share=0.000
```
Note what this confirms mechanically: `--routing-threshold none` rendered "no
threshold" instead of a number, and the held-out report shows only the one frozen
cutoff for `needs_escalation` — no per-candidate table, so the held-out set can't be
used to pick among thresholds, exactly as the plan requires.

If these were real numbers, macro-F1 0.746 would land `polarity` just under the 0.75
**Middle**-band cutoff — i.e. **Low** band, adapter stays disabled. That's a useful
thing to see the gate logic do correctly (hold back a borderline result) even in a
dry run, though the actual number is meaningless here: the synthetic sarcasm/aspect
text is templated and a poor proxy for genuine review language.

## Cleanup

Nothing here needs cleanup — these files aren't referenced by the real pipeline
(`check_sentiment_dataset.py`'s default paths point at `sentiment-tune.jsonl` /
`sentiment-test.jsonl` one directory up, not these `.sample.jsonl` files) and can be
regenerated or deleted at any time.
