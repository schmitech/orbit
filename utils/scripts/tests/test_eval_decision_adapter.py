"""Unit tests for utils/scripts/eval_decision_adapter.py (pure-function parts only)."""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(SCRIPTS_DIR))

import pytest
from eval_decision_adapter import (
    VALENCE_LEVELS,
    RecordResult,
    auroc,
    build_report,
    macro_f1,
    parse_args,
    reliability_bins,
    run_burst,
    run_decisions,
    run_decisions_via_api,
    selective_accuracy_table,
    valence_mae,
    wilson_interval,
)


def test_macro_f1_hand_computed():
    # 3 classes, one mistake (true=a predicted=b), rest correct.
    y_true = ["a", "a", "b", "b", "c", "c"]
    y_pred = ["a", "b", "b", "b", "c", "c"]
    labels = ["a", "b", "c"]
    # a: tp=1 fp=0 fn=1 -> P=1 R=0.5 F1=0.6667
    # b: tp=2 fp=1 fn=0 -> P=0.6667 R=1 F1=0.8
    # c: tp=2 fp=0 fn=0 -> P=1 R=1 F1=1
    expected = (2 / 3 + 0.8 + 1.0) / 3
    assert macro_f1(y_true, y_pred, labels) == pytest.approx(expected, abs=1e-6)


def test_wilson_interval_known_example():
    # 5 errors out of 20 accepted -> p=0.25
    lo, hi = wilson_interval(5, 20)
    assert 0.10 < lo < 0.25
    assert 0.25 < hi < 0.50


def test_selective_accuracy_coverage_and_error():
    y_true = ["a", "a", "b", "b"]
    y_pred = ["a", "b", "b", "b"]
    p_top = [0.9, 0.9, 0.9, 0.4]
    rows = selective_accuracy_table(y_true, y_pred, p_top, [0.5])
    row = rows[0]
    # 3 of 4 items have p_top >= 0.5; 1 of those 3 is wrong (index 1).
    assert row["accepted"] == 3
    assert row["coverage"] == pytest.approx(0.75)
    assert row["error_rate"] == pytest.approx(1 / 3)


def test_reliability_bins():
    y_true = [True, True, False, False]
    p_top = [0.95, 0.85, 0.15, 0.15]
    result = reliability_bins(y_true, p_top, n_bins=5)
    nonempty = [b for b in result["bins"] if b["count"] > 0]
    assert len(nonempty) == 2
    assert result["ece"] >= 0


def test_valence_mae():
    assert valence_mae([0, 2, 4], [0, 2, 4]) == 0
    assert valence_mae([0, 4], [1, 2]) == pytest.approx((1 + 2) / 2)


def test_auroc_perfect_separation():
    y_true = [False, False, True, True]
    y_score = [0.1, 0.2, 0.8, 0.9]
    assert auroc(y_true, y_score) == pytest.approx(1.0)


def test_auroc_single_class_is_none():
    assert auroc([True, True], [0.1, 0.9]) is None


class _FakeDecisionService:
    def __init__(self, answers_by_id):
        self.answers_by_id = answers_by_id

    async def decide(self, state, questions, model=None, **kwargs):
        record_id = state["id_marker"]
        if record_id == "err-1":
            raise ValueError("provider exploded")
        return {"model": "fake", "answers": self.answers_by_id[record_id], "usage": {}}


QUESTIONS = {
    "polarity": {
        "type": "choice",
        "instructions": "x",
        "criteria": {"positive": "p", "negative": "n", "neutral": "z", "mixed": "m"},
    },
    "needs_escalation": {"type": "noul", "instructions": "x"},
}


async def _run_missing_and_error_case():
    records = [
        {"id": "rec-1", "text": "great", "polarity": "positive", "needs_escalation": False},
        {"id": "err-1", "text": "boom", "polarity": "negative", "needs_escalation": True},
    ]
    service = _FakeDecisionService({
        "rec-1": {"polarity": {"type": "choice", "choice": "positive", "probabilities": {"positive": 0.9}},
                   "needs_escalation": {"type": "noul", "noul": 0.1}},
    })

    class _StateKeyService(_FakeDecisionService):
        async def decide(self, state, questions, model=None, **kwargs):
            # run_decisions builds state as {state_key: text}; re-key for the fake lookup.
            record_id = "rec-1" if "great" in state["text"] else "err-1"
            return await super().decide({"id_marker": record_id}, questions, model=model)

    svc = _StateKeyService(service.answers_by_id)
    results = await run_decisions(svc, QUESTIONS, "text", records)
    return records, results


async def test_missing_answers_and_errors_count_as_wrong_and_are_reported():
    records, results = await _run_missing_and_error_case()
    assert any(r.error for r in results)

    report = build_report(
        "fake-adapter", "tune", QUESTIONS, records, results,
        routing_signal=None, routing_threshold=None, escalation_threshold=None,
    )
    assert report["n_errors"] == 1
    assert report["errors"][0]["id"] == "err-1"
    # err-1's polarity answer is missing -> counted as wrong, not silently skipped.
    assert report["questions"]["polarity"]["missing"] == 1
    assert report["questions"]["polarity"]["accuracy"] == pytest.approx(0.5)


def test_selective_accuracy_uses_confidence_when_that_is_the_frozen_signal():
    questions = {
        "polarity": {
            "type": "choice", "instructions": "x",
            "criteria": {"positive": "p", "negative": "n"},
        },
    }
    records = [{"id": "rec-1", "text": "x", "polarity": "positive"}]
    # p_top (probabilities.positive) says 0.95, but confidence says 0.1 — if the report
    # used p_top here it would wrongly look highly confident under the frozen signal.
    results = [RecordResult(
        record_id="rec-1",
        answers={"polarity": {
            "type": "choice", "choice": "positive",
            "probabilities": {"positive": 0.95, "negative": 0.05}, "confidence": 0.1,
        }},
    )]

    report = build_report(
        "fake-adapter", "tune", questions, records, results,
        routing_signal="confidence", routing_threshold=None, escalation_threshold=None,
    )

    row = report["questions"]["polarity"]["selective_accuracy"][0]  # threshold 0.5
    assert row["coverage"] == pytest.approx(0.0)  # confidence 0.1 < 0.5, so nothing is accepted


def test_missing_valence_is_not_scored_as_zero():
    questions = {"valence": {"type": "score", "instructions": "x", "criteria": VALENCE_LEVELS}}
    # True level is 0 ("Very negative") — a naive missing-defaults-to-0 would score this
    # as a perfect match instead of a miss.
    records = [{"id": "rec-1", "text": "x", "valence": 0}]
    results = [RecordResult(record_id="rec-1", answers={})]  # no 'valence' answer at all

    report = build_report(
        "fake-adapter", "tune", questions, records, results,
        routing_signal=None, routing_threshold=None, escalation_threshold=None,
    )

    valence = report["questions"]["valence"]
    assert valence["missing"] == 1
    assert valence["exact_accuracy"] == 0.0
    assert valence["within_one_accuracy"] == 0.0
    assert valence["mae"] > 0


def test_parse_args_requires_split():
    with pytest.raises(SystemExit):
        parse_args(["my-adapter", "data.jsonl"])


def test_parse_args_test_split_requires_frozen_params():
    with pytest.raises(SystemExit):
        parse_args(["my-adapter", "data.jsonl", "--split", "test"])

    # All three given (values or 'none') -> no error.
    args = parse_args([
        "my-adapter", "data.jsonl", "--split", "test",
        "--routing-signal", "p_top", "--routing-threshold", "none", "--escalation-threshold", "none",
    ])
    assert args.routing_threshold == "none"


def test_test_split_reports_no_threshold_and_skips_candidate_table():
    records = [{"id": "rec-1", "text": "great", "polarity": "positive", "needs_escalation": False}]
    results = [RecordResult(
        record_id="rec-1",
        answers={
            "polarity": {"type": "choice", "choice": "positive", "probabilities": {"positive": 0.9}},
            "needs_escalation": {"type": "noul", "noul": 0.1},
        },
    )]
    report = build_report(
        "fake-adapter", "test", QUESTIONS, records, results,
        routing_signal="p_top", routing_threshold="none", escalation_threshold="none",
    )
    polarity = report["questions"]["polarity"]
    assert "selective_accuracy" not in polarity  # no per-candidate table on the held-out split
    assert polarity["routing"]["frozen_threshold"] == "none"
    assert report["questions"]["needs_escalation"]["escalation_cutoff"]["frozen_threshold"] == "none"


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Returns queued responses in order, keyed by HTTP method; records every call."""

    def __init__(self, posts=(), gets=()):
        self._posts = list(posts)
        self._gets = list(gets)
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json, headers))
        return self._posts.pop(0)

    def get(self, url, headers=None):
        self.calls.append(("GET", url, None, headers))
        return self._gets.pop(0) if len(self._gets) > 1 else self._gets[0]


async def test_run_decisions_via_api_happy_path():
    records = [{"id": "rec-1", "text": "Great support."}]
    session = _FakeSession(posts=[
        _FakeResponse(200, {"decision": {
            "model": "jev-latest",
            "answers": {"polarity": {"type": "choice", "choice": "positive"}},
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }}),
    ])

    results = await run_decisions_via_api(session, "http://localhost:3000", "orbit_test_key", records)

    assert len(results) == 1
    assert results[0].answers["polarity"]["choice"] == "positive"
    method, url, body, headers = session.calls[0]
    assert method == "POST"
    assert url == "http://localhost:3000/v1/chat"
    assert body == {"messages": [{"role": "user", "content": "Great support."}]}
    assert headers["X-API-Key"] == "orbit_test_key"
    assert headers["X-Session-ID"]  # non-empty, and unique per record (checked below)


async def test_run_decisions_via_api_gives_each_record_its_own_session_id():
    records = [{"id": "rec-1", "text": "a"}, {"id": "rec-2", "text": "b"}]
    session = _FakeSession(posts=[
        _FakeResponse(200, {"decision": {"answers": {}, "usage": {}}}),
        _FakeResponse(200, {"decision": {"answers": {}, "usage": {}}}),
    ])

    await run_decisions_via_api(session, "http://localhost:3000", "orbit_test_key", records)

    session_ids = [headers["X-Session-ID"] for _, _, _, headers in session.calls]
    assert len(set(session_ids)) == 2


async def test_run_decisions_via_api_http_error_is_scored_as_error():
    records = [{"id": "rec-1", "text": "x"}]
    session = _FakeSession(posts=[_FakeResponse(401, {"error": "invalid key"})])

    results = await run_decisions_via_api(session, "http://localhost:3000", "bad-key", records)

    assert results[0].error is not None
    assert "401" in results[0].error


async def test_run_burst_publishes_in_batches_and_waits_for_drain():
    records = [{"id": f"rec-{i}", "text": "x"} for i in range(60)]
    session = _FakeSession(
        posts=[_FakeResponse(200, {"published": 50}), _FakeResponse(200, {"published": 10})],
        gets=[_FakeResponse(200, {"in_flight": 5}), _FakeResponse(200, {"in_flight": 0})],
    )

    result = await run_burst(session, "http://127.0.0.1:8795", records, batch_size=50, poll_interval_s=0)

    assert result["published"] == 60
    assert result["drained"] is True
    posts = [c for c in session.calls if c[0] == "POST"]
    assert len(posts) == 2
    assert len(posts[0][2]["items"]) == 50
    assert len(posts[1][2]["items"]) == 10


async def test_run_burst_reports_not_drained_on_timeout():
    records = [{"id": "rec-1", "text": "x"}]
    session = _FakeSession(
        posts=[_FakeResponse(200, {"published": 1})],
        gets=[_FakeResponse(200, {"in_flight": 1})] * 50,
    )

    result = await run_burst(
        session, "http://127.0.0.1:8795", records, batch_size=50, poll_interval_s=0, overall_timeout_s=0.01,
    )

    assert result["drained"] is False
