"""
Language-detection benchmark: corpus validity and held-out regression gate.

The schema test is fast and runs in the normal suite. The benchmark tests run
the real detector backends over the corpus and are marked ``slow``; see
README.md for the optional job and for how to re-record the baseline.
"""

import asyncio
import json
import re
from collections import Counter

import pytest
from inference.pipeline.steps.language_detection import CALIBRATION_PATH

from language_eval.runner import (
    BASELINE_REPORT_PATH,
    DATASET_PATH,
    PIPELINE_MODES,
    SPLITS,
    _mode_available,
    dataset_sha256,
    load_dataset,
    run_benchmark,
    secondary_char_labels,
)

LANG_CODE = re.compile(r"^[a-z]{2,3}$")
REQUIRED_FIELDS = {"id", "text", "lang", "alternatives", "abstain_ok", "category",
                   "context_lang", "secondary_spans", "split"}


def _load_baseline():
    with open(BASELINE_REPORT_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_dataset_schema():
    records = load_dataset()
    assert len({r["id"] for r in records}) == len(records), "duplicate ids"

    for r in records:
        assert REQUIRED_FIELDS <= r.keys(), r["id"]
        assert r["split"] in SPLITS, r["id"]
        assert r["lang"] == "unknown" or LANG_CODE.match(r["lang"]), r["id"]
        assert all(LANG_CODE.match(a) for a in r["alternatives"]), r["id"]
        assert r["context_lang"] is None or LANG_CODE.match(r["context_lang"]), r["id"]
        if r["lang"] == "unknown":
            assert r["abstain_ok"], f"{r['id']}: an unknown-language record must accept abstention"
        for span in r["secondary_spans"]:
            assert LANG_CODE.match(span["lang"]) and span["lang"] != r["lang"], r["id"]
        # Raises if a span is not a substring in order.
        labels = secondary_char_labels(r)
        assert len(labels) == sum(len(s["text"]) for s in r["secondary_spans"]), r["id"]


def test_every_category_is_in_both_splits():
    counts = Counter((r["category"], r["split"]) for r in load_dataset())
    for category in {c for c, _ in counts}:
        for split in SPLITS:
            assert counts[(category, split)] > 0, f"{category} missing from {split}"


def test_baseline_matches_frozen_dataset():
    baseline = _load_baseline()
    assert baseline["benchmark"]["sha256"] == dataset_sha256(DATASET_PATH), (
        "benchmark data changed since the baseline was recorded; re-record it (README.md) "
        "and report the before/after numbers"
    )


def test_calibration_was_fitted_on_frozen_tune_split():
    with open(CALIBRATION_PATH, encoding="utf-8") as f:
        fitted_on = json.load(f)["fitted_on"]
    assert fitted_on["split"] == "tune", "calibration must never be fitted on heldout"
    assert fitted_on["sha256"] == dataset_sha256(DATASET_PATH), (
        "benchmark data changed since the calibration was fitted; rerun calibrate.py (README.md)"
    )


def test_tuning_loss_gives_unlisted_gold_its_residual_share():
    from language_eval.calibrate import UNIVERSE_SIZE, gold_probability

    record = {"lang": "hi", "alternatives": ["ur"]}
    probabilities, residual = {"en": 0.6, "es": 0.3}, 0.1
    share = residual / (UNIVERSE_SIZE - 2)
    assert gold_probability(record, probabilities, residual) == pytest.approx(2 * share)
    assert gold_probability({"lang": "en", "alternatives": []}, probabilities, residual) == 0.6


pipeline_available = pytest.mark.skipif(
    not _mode_available("pipeline"), reason="no language detection backend installed"
)


@pytest.mark.slow
@pipeline_available
def test_pipeline_is_deterministic():
    first = asyncio.run(run_benchmark(modes=("pipeline",), splits=("heldout",)))
    second = asyncio.run(run_benchmark(modes=("pipeline",), splits=("heldout",)))
    assert first["predictions"] == second["predictions"]


@pytest.mark.slow
@pipeline_available
@pytest.mark.parametrize("mode", PIPELINE_MODES)
def test_heldout_does_not_regress(mode):
    """Selective accuracy must not drop and high-confidence errors must not rise.

    Coverage may change (e.g. the detector learns to abstain); that is not
    gated here but must be reported when the baseline is re-recorded.
    """
    baseline = _load_baseline()
    current = asyncio.run(run_benchmark(modes=(mode,), splits=("heldout",)))
    base = baseline["modes"][mode]["splits"]["heldout"]["counts"]
    now = current["modes"][mode]["splits"]["heldout"]["counts"]
    env = (f"baseline packages {baseline['environment']['packages']}, "
           f"current {current['environment']['packages']}")

    # accepted_correct/accepted >= baseline ratio, compared without float rounding.
    assert now["accepted_correct"] * base["accepted"] >= base["accepted_correct"] * now["accepted"], (
        f"{mode}: selective accuracy {now['accepted_correct']}/{now['accepted']} fell below "
        f"baseline {base['accepted_correct']}/{base['accepted']} ({env})"
    )
    assert now["high_conf_errors"] <= base["high_conf_errors"], (
        f"{mode}: high-confidence errors {now['high_conf_errors']} exceed baseline "
        f"{base['high_conf_errors']} ({env})"
    )


# Agreed bound for Phase 4: at most 2% of monolingual held-out records flagged mixed.
MAX_MONOLINGUAL_FALSE_POSITIVE_RATE = 0.02


@pytest.mark.slow
@pipeline_available
@pytest.mark.parametrize("mode", PIPELINE_MODES)
def test_heldout_mixed_language_does_not_regress(mode):
    """Mixed-language recall must not drop, and false positives stay within the bound."""
    baseline = _load_baseline()
    current = asyncio.run(run_benchmark(modes=(mode,), splits=("heldout",)))
    base = baseline["modes"][mode]["splits"]["heldout"]["mixed_language"]
    now = current["modes"][mode]["splits"]["heldout"]["mixed_language"]
    for key in ("flag_recall", "span_char_recall"):
        assert (now[key] or 0) >= (base[key] or 0), f"{mode}: {key} {now[key]} fell below baseline {base[key]}"
    assert now["monolingual_false_positive_rate"] <= MAX_MONOLINGUAL_FALSE_POSITIVE_RATE, (
        f"{mode}: monolingual false-positive rate {now['monolingual_false_positive_rate']} "
        f"exceeds {MAX_MONOLINGUAL_FALSE_POSITIVE_RATE}"
    )
