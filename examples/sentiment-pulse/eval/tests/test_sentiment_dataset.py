"""Unit tests for examples/sentiment-pulse/eval/check_sentiment_dataset.py (synthetic
fixtures only — the real frozen eval sets are produced by human annotators, see the
eval plan)."""

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(EVAL_DIR))

from check_sentiment_dataset import check_no_overlap, check_quotas, check_schema


def _good_record(**overrides):
    record = {
        "id": "rev-001",
        "text": "Arrived late but support fixed it fast. Love it.",
        "polarity": "mixed",
        "valence": 3,
        "sarcasm": False,
        "needs_escalation": False,
        "aspects": {"price": "not_mentioned", "support": "positive", "product": "not_mentioned", "delivery": "negative"},
        "lang": "en",
    }
    record.update(overrides)
    return record


def test_schema_accepts_a_fully_labeled_record():
    assert check_schema([_good_record()]) == []


def test_schema_flags_missing_and_invalid_fields():
    bad = _good_record(polarity="ecstatic", valence=9, sarcasm="no", aspects={"price": "not_mentioned"})
    errors = check_schema([bad])
    assert any("polarity" in e for e in errors)
    assert any("valence" in e for e in errors)
    assert any("sarcasm" in e for e in errors)
    assert any("aspects" in e for e in errors)


def test_schema_flags_duplicate_ids():
    errors = check_schema([_good_record(), _good_record()])
    assert any("duplicate id" in e for e in errors)


def test_quotas_report_shortfalls():
    records = [_good_record(id=f"r{i}", polarity="positive") for i in range(5)]
    errors = check_quotas(records, polarity_each=15, min_escalation_positives=12)
    assert any("positive" in e for e in errors)
    assert any("negative" in e for e in errors)  # zero negatives
    assert any("needs_escalation" in e for e in errors)


def test_quotas_pass_when_met():
    records = []
    for polarity in ["positive", "negative", "neutral", "mixed"]:
        for i in range(15):
            aspects = {"price": "positive", "support": "positive", "product": "positive", "delivery": "positive"}
            records.append(_good_record(
                id=f"{polarity}-{i}", polarity=polarity, aspects=aspects,
                needs_escalation=(i < 3),
            ))
    errors = check_quotas(records, polarity_each=15, min_escalation_positives=12)
    assert errors == []


def test_no_overlap_detects_shared_ids():
    tune = [_good_record(id="dup-1")]
    test = [_good_record(id="dup-1"), _good_record(id="unique-1")]
    errors = check_no_overlap(("tune", tune), ("test", test))
    assert len(errors) == 1
    assert "dup-1" in errors[0]


def test_no_overlap_clean_when_disjoint():
    tune = [_good_record(id="tune-1")]
    test = [_good_record(id="test-1")]
    assert check_no_overlap(("tune", tune), ("test", test)) == []
