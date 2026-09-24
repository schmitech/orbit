# Language-detection benchmark

Measures `LanguageDetectionStep` (`server/inference/pipeline/steps/language_detection.py`)
against a frozen, versioned corpus so every change to language detection can be
compared with the same held-out split. This is Phase 0 of
`docs/roadmap/language-detection-accuracy.md`.

## Quick start

```bash
# From repo root. Full report (all modes, both splits), ~15 s:
venv/bin/python server/tests/language_eval/runner.py --output /tmp/lang-report.json

# Only the production pipeline on the held-out split:
venv/bin/python server/tests/language_eval/runner.py --modes pipeline --splits heldout

# Tests (schema checks are fast; the benchmark gate is marked `slow`):
venv/bin/python -m pytest server/tests/language_eval -q
venv/bin/python -m pytest server/tests/language_eval -q -m "not slow"   # schema only
```

There is no CI workflow in this repository, so this benchmark is an **optional
test job**: run the `slow` tests before merging any change to language
detection. No network or model downloads are needed, only the
`langdetect`/`langid`/`pycld2` packages from the default install profile. If
no backend is installed, the benchmark tests skip and say so. A run where they
skip is not an accuracy signal.

## Files

| Path | Purpose |
|---|---|
| `data/benchmark_v1.jsonl` | Frozen corpus, one JSON record per line. |
| `runner.py` | Runs a detector mode over the corpus and writes a JSON report plus a Markdown summary. |
| `reports/phase0_baseline_v1.json` | Baseline for the pre-Phase-1 detector: metrics, environment, config and per-record pipeline predictions. |
| `test_benchmark.py` | Schema and split checks, a determinism check, and the held-out regression gate. |

## Record schema

```json
{"id": "shared_script-ne-01", "text": "तपाईंलाई कस्तो छ?", "lang": "ne",
 "alternatives": [], "abstain_ok": false, "category": "shared_script",
 "context_lang": null, "secondary_spans": [], "split": "tune"}
```

- `lang`: gold primary language (ISO 639-1, or 639-3 where no 639-1 code
  exists). `unknown` means the text carries no determinable language, e.g.
  emoji, numbers, URLs or bare codes.
- `alternatives`: other languages that also count as correct. Use this for
  genuinely ambiguous text such as `да` (ru/bg/sr/mk) or `धन्यवाद` (hi/mr/ne).
- `abstain_ok`: returning `unknown` counts as acceptable, not as an error.
  This is always true when `lang` is `unknown`.
- `context_lang`: the language of the previous user turn, used for
  conversation follow-ups (`OK`, `sí`, `non`). Only the `pipeline+context`
  mode uses it.
- `secondary_spans`: substrings, in order, written in a language other than
  the primary one. Stored as text rather than offsets so the file can be
  edited by hand. The runner resolves them to character offsets.
- `split`: `tune` or `heldout`. Assigned once, stratified by category.
  **Never tune thresholds, weights or calibration against `heldout`.**

The runner derives the other stratification dimensions from the text, so they
cannot drift from it:

- dominant `script` (kana makes it `Japanese`);
- `length_bucket`: `no_letters`, `1-2_chars`, `single_word`, `short` or
  `long`, counting Unicode letters (approximate for unspaced scripts);
- `latin_form`: ASCII-only versus diacritic-bearing;
- `shared_script`: Cyrillic, Arabic, Devanagari, Bengali, Hebrew, or Han
  without kana.

Categories: `long`, `short_chat`, `single_word`, `tiny`, `no_language`,
`noise` (URLs, email, code, emoji, numbers), `named_entity`, `ascii_latin`,
`shared_script`, `romanized`, `mixed`, `borrowed_word` (monolingual text that
must not be flagged as mixed), `related_latin` and `followup`.

## Provenance and licensing

All 334 v1 records are synthetic prompts written for this benchmark by the
ORBIT maintainers. No third-party corpus is included. They are distributed
under the repository's Apache-2.0 license. New records must also be synthetic
or internally owned. Do not paste real user messages.

## Modes

| Mode | What runs |
|---|---|
| `pipeline` | `LanguageDetectionStep.process()` with the `language_detection` section of `config/config.yaml` and no conversation history, matching production today. |
| `pipeline+context` | Same, but `chat_history_service` returns one prior user turn tagged with `context_lang`. Production does not persist that tag yet (roadmap Phase 2), so this mode shows what the prior *would* do. |
| `langdetect`, `langid`, `pycld2` | That backend alone, on the same cleaned text the pipeline gives it, through the step's own `_detect_*` adapter. |

Backends run first, so each backend's `first_call_ms` is its own cold start.

## Metrics

Scoring rules:

- A prediction is **correct** if it is `lang` or one of `alternatives`, or if
  it abstains (`unknown`/no result) on an `unknown` record.
- It is **acceptable** if it is correct, or if it abstains on an `abstain_ok`
  record.

Reported per split, per mode:

- `top1_accuracy` (over labelled records; abstaining counts as wrong),
  `macro_f1`, `acceptable_rate`.
- `coverage` (share not abstained) and `selective_accuracy` (accuracy among
  accepted predictions).
- `high_conf_errors`: accepted, wrong, with confidence ≥ 0.9.
- `calibration`: Brier score, 10-bin ECE and a reliability table, over
  accepted predictions.
- `margin`: top-two margin distributions for correct and incorrect
  predictions. For backends this uses their own score scale. For the pipeline
  it is available only on paths that expose the vote table.
- `mixed_language`:
  - precision and recall of the mixed flag;
  - monolingual false-positive rate;
  - secondary-language recall;
  - character-level span precision and recall, once a detector emits spans.
- Slices `by_language`, `by_script`, `by_length`, `by_latin_form`,
  `by_category` and `by_shared_script`, plus `top_errors` and
  `related_confusion` matrices for commonly confused language groups.
- `performance`: first-call latency, p50/p95/mean/max latency and process
  peak RSS. These vary by machine and are never gated.

## Regression gate and re-baselining

For `pipeline` and `pipeline+context` on the held-out split,
`test_heldout_does_not_regress` fails when either of these happens:

- selective accuracy drops below the baseline;
- high-confidence errors rise above the baseline.

Coverage is deliberately not gated, because learning to abstain lowers it.
Any change in coverage must be reported.

When a change genuinely improves the detector:

1. Run `runner.py --output server/tests/language_eval/reports/phase<N>_<version>.json`
   and point `BASELINE_REPORT_PATH` at it, or overwrite the current baseline.
2. In the PR, report before/after numbers for the held-out split, including
   any change in coverage.

Changing the corpus changes its SHA-256, and `test_baseline_matches_frozen_dataset`
then fails until the baseline is re-recorded. For anything beyond fixing a
mislabel, create `benchmark_v2.jsonl` rather than editing v1, so that earlier
phases stay comparable.
