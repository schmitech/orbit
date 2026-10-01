#!/usr/bin/env python3
"""
Generic evaluator for `decision_model` adapters (config/adapters/*.yaml).

Direct mode (default) reads an adapter's `questions` straight from its YAML — enabled
or not — loads the real server config, and calls `DecisionService.decide()` for every
record in a labeled JSONL file. This isolates model quality from the rest of ORBIT.

    python utils/scripts/eval_decision_adapter.py sentiment-analysis \
        examples/sentiment-pulse/eval/sentiment-tune.jsonl --split tune

See docs/roadmap/complete/decision-model-sentiment-analysis.md for the full evaluation plan.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent.absolute()
REPO_ROOT = SCRIPT_DIR.parent.parent
SERVER_DIR = REPO_ROOT / "server"
ADAPTERS_DIR = REPO_ROOT / "config" / "adapters"

sys.path.insert(0, str(SERVER_DIR))


# --------------------------------------------------------------------------- #
# Pure metric helpers (no I/O — unit-tested directly)
# --------------------------------------------------------------------------- #


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


def confusion_matrix(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict[str, dict[str, int]]:
    matrix = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        if t in matrix and p in matrix[t]:
            matrix[t][p] += 1
    return matrix


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def macro_f1(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    matrix = confusion_matrix(y_true, y_pred, labels)
    f1s = []
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[t][label] for t in labels if t != label)
        fn = sum(matrix[label][p] for p in labels if p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s.append(f1)
    return statistics.mean(f1s) if f1s else 0.0


def valence_mae(y_true: list[float], y_pred: list[float]) -> float:
    if not y_true:
        return 0.0
    return statistics.mean(abs(t - p) for t, p in zip(y_true, y_pred))


def valence_exact_accuracy(y_true: list[float], y_pred: list[float]) -> float:
    return accuracy([str(round(t)) for t in y_true], [str(round(p)) for p in y_pred])


def valence_within_one_accuracy(y_true: list[float], y_pred: list[float]) -> float:
    if not y_true:
        return 0.0
    hits = sum(1 for t, p in zip(y_true, y_pred) if abs(round(t) - round(p)) <= 1)
    return hits / len(y_true)


def auroc(y_true: list[bool], y_score: list[float]) -> float | None:
    """Rank-based AUROC (Mann-Whitney U). None if only one class is present."""
    pos = [s for t, s in zip(y_true, y_score) if t]
    neg = [s for t, s in zip(y_true, y_score) if not t]
    if not pos or not neg:
        return None
    ranked = sorted(range(len(y_score)), key=lambda i: y_score[i])
    ranks = [0.0] * len(y_score)
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and y_score[ranked[j + 1]] == y_score[ranked[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[ranked[k]] = avg_rank
        i = j + 1
    rank_sum_pos = sum(ranks[i] for i, t in enumerate(y_true) if t)
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def precision_recall_at_threshold(y_true: list[bool], y_score: list[float], threshold: float) -> dict[str, Any]:
    tp = sum(1 for t, s in zip(y_true, y_score) if s >= threshold and t)
    fp = sum(1 for t, s in zip(y_true, y_score) if s >= threshold and not t)
    fn = sum(1 for t, s in zip(y_true, y_score) if s < threshold and t)
    accepted = tp + fp
    precision = tp / accepted if accepted else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    false_alert_share = fp / accepted if accepted else 0.0
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "false_alert_share": false_alert_share,
        "accepted": accepted,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def selective_accuracy_table(
    y_true: list[str], y_pred: list[str], p_top: list[float], thresholds: list[float]
) -> list[dict[str, Any]]:
    """Coverage and accepted-error-rate at each p_top threshold, with Wilson bounds."""
    rows = []
    n = len(y_true)
    for t in thresholds:
        accepted_idx = [i for i in range(n) if p_top[i] >= t]
        coverage = len(accepted_idx) / n if n else 0.0
        errors = sum(1 for i in accepted_idx if y_true[i] != y_pred[i])
        error_rate = errors / len(accepted_idx) if accepted_idx else 0.0
        lo, hi = wilson_interval(errors, len(accepted_idx)) if accepted_idx else (0.0, 1.0)
        rows.append({
            "threshold": t,
            "coverage": coverage,
            "accepted": len(accepted_idx),
            "error_rate": error_rate,
            "error_ci_lo": lo,
            "error_ci_hi": hi,
        })
    return rows


def reliability_bins(y_true: list[bool], p_top: list[float], n_bins: int = 5) -> dict[str, Any]:
    """5-bin reliability table and ECE on p_top. Exploratory only — see eval plan."""
    bins: list[dict[str, Any]] = [{"lo": i / n_bins, "hi": (i + 1) / n_bins, "items": []} for i in range(n_bins)]
    for t, p in zip(y_true, p_top):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx]["items"].append((t, p))

    rows = []
    ece = 0.0
    n = len(y_true)
    for b in bins:
        items = b["items"]
        count = len(items)
        if count:
            avg_confidence = statistics.mean(p for _, p in items)
            empirical_accuracy = sum(1 for t, _ in items if t) / count
            ece += (count / n) * abs(avg_confidence - empirical_accuracy) if n else 0.0
        else:
            avg_confidence = None
            empirical_accuracy = None
        rows.append({
            "range": f"[{b['lo']:.1f}, {b['hi']:.1f})",
            "count": count,
            "avg_confidence": avg_confidence,
            "accuracy": empirical_accuracy,
        })
    return {"bins": rows, "ece": ece}


# --------------------------------------------------------------------------- #
# Adapter / dataset loading
# --------------------------------------------------------------------------- #


def load_adapter(adapter_name: str) -> dict[str, Any]:
    import yaml

    for yaml_path in sorted(ADAPTERS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text()) or {}
        for adapter in data.get("adapters", []):
            if adapter.get("name") == adapter_name:
                return adapter
    raise ValueError(f"Adapter '{adapter_name}' not found under {ADAPTERS_DIR}")


def load_dataset(path: Path) -> list[dict[str, Any]]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def label_for_question(record: dict[str, Any], question_name: str) -> Any:
    """Look up a question's gold label in a dataset record.

    Top-level field named after the question, or `aspects.<name>` for `aspect_*`
    questions — matches the sentiment-analysis schema in the eval plan.
    """
    if question_name in record:
        return record[question_name]
    if question_name.startswith("aspect_"):
        return (record.get("aspects") or {}).get(question_name[len("aspect_"):])
    return None


VALENCE_LEVELS = ["Very negative", "Negative", "Neutral", "Positive", "Very positive"]


# --------------------------------------------------------------------------- #
# Per-record decision results
# --------------------------------------------------------------------------- #


@dataclass
class RecordResult:
    record_id: str
    answers: dict[str, Any] | None = None
    error: str | None = None
    latency_s: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)


async def run_decisions(
    service: Any,
    questions: dict[str, Any],
    state_key: str,
    records: list[dict[str, Any]],
    model: str | None = None,
) -> list[RecordResult]:
    results = []
    for record in records:
        start = time.monotonic()
        try:
            result = await service.decide({state_key: record["text"]}, questions, model=model)
            elapsed = time.monotonic() - start
            results.append(RecordResult(
                record_id=record["id"], answers=result.get("answers") or {},
                latency_s=elapsed, usage=result.get("usage") or {},
            ))
        except Exception as e:  # noqa: BLE001 - a provider failure is a scored miss, not a crash
            elapsed = time.monotonic() - start
            results.append(RecordResult(record_id=record["id"], error=str(e), latency_s=elapsed))
    return results


async def run_decisions_via_api(
    session: Any,
    orbit_url: str,
    api_key: str,
    records: list[dict[str, Any]],
) -> list[RecordResult]:
    """`--via-api`: call the real `POST /v1/chat` endpoint with an API key.

    Includes ORBIT's own overhead in the latency figures. The API key's adapter must
    already be enabled — the adapter registry skips disabled adapters.
    """
    url = f"{orbit_url.rstrip('/')}/v1/chat"
    results = []
    for record in records:
        body = {"messages": [{"role": "user", "content": record["text"]}]}
        # Each record is an independent decision, not a conversation turn, so each gets
        # its own session id rather than sharing one across the run — avoids chat
        # history threading between unrelated records, and satisfies ORBIT instances
        # that require X-Session-ID (session_id.required, or chat_history.session
        # required with auto_generate off).
        headers = {"X-API-Key": api_key, "X-Session-ID": str(uuid.uuid4())}
        start = time.monotonic()
        try:
            async with session.post(url, json=body, headers=headers) as response:
                elapsed = time.monotonic() - start
                data = await response.json()
                if response.status != 200:
                    results.append(RecordResult(
                        record_id=record["id"], error=f"HTTP {response.status}: {data}", latency_s=elapsed,
                    ))
                    continue
                decision = data.get("decision") or {}
                results.append(RecordResult(
                    record_id=record["id"], answers=decision.get("answers") or {},
                    latency_s=elapsed, usage=decision.get("usage") or {},
                ))
        except Exception as e:  # noqa: BLE001 - a transport failure is a scored miss, not a crash
            elapsed = time.monotonic() - start
            results.append(RecordResult(record_id=record["id"], error=str(e), latency_s=elapsed))
    return results


async def run_burst(
    session: Any,
    bridge_url: str,
    records: list[dict[str, Any]],
    batch_size: int = 50,
    poll_interval_s: float = 0.5,
    overall_timeout_s: float = 120.0,
) -> dict[str, Any]:
    """`--burst N`: publish `records` to the Triage Rush-style bridge
    (examples/triage-rush-mq/game_bridge.py) in batches of `batch_size`, then poll
    `GET /health` until the bridge's `in_flight` count returns to 0 (every published
    item has either been answered or timed out) or `overall_timeout_s` elapses. Reports
    wall-clock drain time, not per-item results — the bridge's `/events` stream is for
    the live UI, not batch scoring.
    """
    bridge_url = bridge_url.rstrip("/")
    start = time.monotonic()
    published = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        items = [{"id": r["id"], "text": r["text"]} for r in batch]
        async with session.post(f"{bridge_url}/publish", json={"items": items}) as response:
            data = await response.json()
            if response.status != 200:
                raise RuntimeError(f"/publish failed: HTTP {response.status}: {data}")
            published += data.get("published", 0)

    drained = False
    while time.monotonic() - start < overall_timeout_s:
        async with session.get(f"{bridge_url}/health") as response:
            health = await response.json()
        if health.get("in_flight") == 0:
            drained = True
            break
        await asyncio.sleep(poll_interval_s)

    return {
        "published": published,
        "drained": drained,
        "drain_time_s": time.monotonic() - start,
        "timeout_s": overall_timeout_s,
    }


# --------------------------------------------------------------------------- #
# Report building
# --------------------------------------------------------------------------- #


def build_report(
    adapter_name: str,
    split: str,
    questions: dict[str, Any],
    records: list[dict[str, Any]],
    results: list[RecordResult],
    routing_signal: str | None,
    routing_threshold: str | None,
    escalation_threshold: str | None,
) -> dict[str, Any]:
    results_by_id = {r.record_id: r for r in results}
    errors = [r for r in results if r.error is not None]

    questions_report: dict[str, Any] = {}
    for qname, qspec in questions.items():
        qtype = qspec.get("type")
        y_true: list[Any] = []
        y_pred: list[Any] = []
        p_top: list[float] = []
        missing = 0

        for record in records:
            gold = label_for_question(record, qname)
            r = results_by_id.get(record["id"])
            answer = (r.answers or {}).get(qname) if r and r.answers else None

            if qtype == "choice":
                labels = sorted(qspec.get("criteria", {}).keys())
                pred = answer.get("choice") if answer else None
                probs = (answer or {}).get("probabilities") or {}
                if pred is None:
                    missing += 1
                    # A missing/errored answer counts as wrong: pick a label it can't be.
                    pred = f"__missing__:{qname}"
                y_true.append(str(gold))
                y_pred.append(str(pred))
                # The routing signal is p_top by default, but the frozen signal can be
                # the provider's `confidence` instead (see eval plan) — use whichever
                # was requested, not always p_top, or the selective-accuracy/reliability
                # tables silently score a different signal than the one the gate freezes.
                if routing_signal == "confidence":
                    p_top.append(float(answer.get("confidence", 0.0)) if answer else 0.0)
                else:
                    p_top.append(probs.get(pred, 0.0) if pred in probs else 0.0)
            elif qtype == "noul":
                score = answer.get("noul") if answer else None
                if score is None:
                    missing += 1
                    score = 0.0 if gold else 1.0  # worst case: scored wrong either way below
                y_true.append(bool(gold))
                p_top.append(float(score))
            elif qtype == "score":
                levels = qspec.get("criteria", [])
                gold_idx = levels.index(gold) if isinstance(gold, str) and gold in levels else gold
                pred_score = answer.get("score") if answer else None
                if pred_score is None:
                    missing += 1
                    # A sentinel at least 2 below the valid 0..len(levels)-1 range: guaranteed
                    # to miss both exact and within-one-level accuracy (which tolerates an
                    # off-by-one gap) for every possible true level, instead of silently
                    # matching a true level of 0 ("Very negative").
                    pred_score = -2.0
                y_true.append(float(gold_idx))
                y_pred.append(float(pred_score))

        entry: dict[str, Any] = {"type": qtype, "n": len(records), "missing": missing}
        if qtype == "choice":
            labels = sorted(set(y_true) | set(y_pred) | set(qspec.get("criteria", {}).keys()))
            entry["accuracy"] = accuracy(y_true, y_pred)
            entry["macro_f1"] = macro_f1(y_true, y_pred, labels)
            entry["confusion_matrix"] = confusion_matrix(y_true, y_pred, labels)
            if qname == "polarity" and routing_signal:
                thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
                if split == "tune":
                    entry["selective_accuracy"] = selective_accuracy_table(y_true, y_pred, p_top, thresholds)
                    entry["reliability"] = reliability_bins(
                        [t == p for t, p in zip(y_true, y_pred)], p_top,
                    )
                else:
                    if routing_threshold == "none":
                        entry["routing"] = {"frozen_threshold": "none", "note": "no routing threshold"}
                    else:
                        t = float(routing_threshold)
                        row = selective_accuracy_table(y_true, y_pred, p_top, [t])[0]
                        entry["routing"] = {"frozen_threshold": t, **row}
        elif qtype == "noul":
            entry["auroc"] = auroc(y_true, p_top)
            entry["precision_recall"] = {
                str(t): precision_recall_at_threshold(y_true, p_top, t) for t in (0.5, 0.8)
            }
            if qname == "needs_escalation" and split == "test":
                if escalation_threshold == "none":
                    entry["escalation_cutoff"] = {"frozen_threshold": "none", "note": "no cutoff; AUROC only"}
                else:
                    t = float(escalation_threshold)
                    entry["escalation_cutoff"] = {"frozen_threshold": t, **precision_recall_at_threshold(y_true, p_top, t)}
        elif qtype == "score":
            entry["mae"] = valence_mae(y_true, y_pred)
            entry["exact_accuracy"] = valence_exact_accuracy(y_true, y_pred)
            entry["within_one_accuracy"] = valence_within_one_accuracy(y_true, y_pred)

        questions_report[qname] = entry

    latencies = sorted(r.latency_s for r in results if r.latency_s is not None)
    input_tokens = [r.usage.get("input_tokens") for r in results if r.usage.get("input_tokens") is not None]
    output_tokens = [r.usage.get("output_tokens") for r in results if r.usage.get("output_tokens") is not None]

    def _pct(sorted_vals: list[float], pct: float) -> float | None:
        if not sorted_vals:
            return None
        idx = min(len(sorted_vals) - 1, round(pct * (len(sorted_vals) - 1)))
        return sorted_vals[idx]

    return {
        "adapter": adapter_name,
        "split": split,
        "n_records": len(records),
        "n_errors": len(errors),
        "errors": [{"id": r.record_id, "error": r.error} for r in errors],
        "questions": questions_report,
        "latency": {"p50_s": _pct(latencies, 0.5), "p95_s": _pct(latencies, 0.95)},
        "tokens": {
            "mean_input": statistics.mean(input_tokens) if input_tokens else None,
            "mean_output": statistics.mean(output_tokens) if output_tokens else None,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Eval report — `{report['adapter']}` (split: **{report['split']}**)",
        "",
        f"- Records: {report['n_records']} ({report['n_errors']} errors)",
    ]
    lat = report["latency"]
    if lat["p50_s"] is not None:
        lines.append(f"- Latency: p50 {lat['p50_s']*1000:.0f} ms, p95 {lat['p95_s']*1000:.0f} ms")
    tok = report["tokens"]
    if tok["mean_input"] is not None:
        lines.append(f"- Tokens: mean input {tok['mean_input']:.0f}, mean output {tok['mean_output']:.0f}")
    lines.append("")

    for qname, entry in report["questions"].items():
        lines.append(f"## {qname} ({entry['type']})")
        lines.append(f"- n={entry['n']}, missing/errored={entry['missing']}")
        if entry["type"] == "choice":
            lines.append(f"- accuracy={entry['accuracy']:.3f}, macro-F1={entry['macro_f1']:.3f}")
            if "selective_accuracy" in entry:
                lines.append("- selective accuracy (tuning candidates):")
                lines.append("  | t | coverage | error_rate | 95% CI |")
                lines.append("  |---|---|---|---|")
                for row in entry["selective_accuracy"]:
                    lines.append(
                        f"  | {row['threshold']} | {row['coverage']:.2f} | {row['error_rate']:.3f} "
                        f"| [{row['error_ci_lo']:.3f}, {row['error_ci_hi']:.3f}] |"
                    )
            if "routing" in entry:
                r = entry["routing"]
                if r["frozen_threshold"] == "none":
                    lines.append("- routing: no threshold")
                else:
                    lines.append(
                        f"- routing @ t={r['frozen_threshold']}: coverage={r['coverage']:.2f}, "
                        f"error_rate={r['error_rate']:.3f} (95% CI [{r['error_ci_lo']:.3f}, {r['error_ci_hi']:.3f}])"
                    )
        elif entry["type"] == "noul":
            auroc_val = entry["auroc"]
            lines.append(f"- AUROC={auroc_val:.3f}" if auroc_val is not None else "- AUROC=n/a (single class)")
            for t, pr in entry["precision_recall"].items():
                lines.append(
                    f"  - @{t}: precision={pr['precision']:.3f}, recall={pr['recall']:.3f}, "
                    f"false_alert_share={pr['false_alert_share']:.3f}"
                )
            if "escalation_cutoff" in entry:
                ec = entry["escalation_cutoff"]
                if ec["frozen_threshold"] == "none":
                    lines.append("- escalation cutoff: none (ranking only)")
                else:
                    lines.append(
                        f"- escalation cutoff @ t={ec['frozen_threshold']}: precision={ec['precision']:.3f}, "
                        f"recall={ec['recall']:.3f}, false_alert_share={ec['false_alert_share']:.3f}"
                    )
        elif entry["type"] == "score":
            lines.append(
                f"- MAE={entry['mae']:.3f}, exact_accuracy={entry['exact_accuracy']:.3f}, "
                f"within_one_accuracy={entry['within_one_accuracy']:.3f}"
            )
        lines.append("")

    if report["errors"]:
        lines.append("## Errors")
        for e in report["errors"]:
            lines.append(f"- {e['id']}: {e['error']}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_service(provider: str):
    from config.config_manager import load_config

    config = load_config()
    if provider == "ollama":
        from ai_services.implementations.decision.ollama_decision_service import OllamaDecisionService
        return OllamaDecisionService(config)
    if provider == "typesafe":
        from ai_services.implementations.decision.typesafe_decision_service import TypeSafeDecisionService
        return TypeSafeDecisionService(config)
    raise ValueError(f"Unknown decision provider: {provider}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("adapter", help="Adapter name from config/adapters/*.yaml")
    parser.add_argument("dataset", help="Path to a labeled JSONL file")
    parser.add_argument("--split", required=True, choices=["tune", "test"])
    parser.add_argument("--json", action="store_true", help="Also print the full report as JSON")
    parser.add_argument("--routing-signal", choices=["p_top", "confidence"], default=None)
    parser.add_argument("--routing-threshold", default=None, help="A float, or the literal 'none'")
    parser.add_argument("--escalation-threshold", default=None, help="A float, or the literal 'none'")
    parser.add_argument("--via-api", action="store_true", help="Call POST /v1/chat on a running ORBIT instead of the provider directly")
    parser.add_argument("--burst", type=int, default=None, help="Publish N records through the MQ bridge and report the drain time")
    parser.add_argument("--orbit-url", default="http://localhost:3000", help="ORBIT base URL, for --via-api")
    parser.add_argument("--api-key", default=None, help="API key for --via-api (default: $ORBIT_API_KEY)")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8795", help="Bridge base URL, for --burst (examples/triage-rush-mq/game_bridge.py)")
    parser.add_argument("--burst-timeout", type=float, default=30.0, help="Seconds to wait for the burst to drain (match the bridge's --timeout)")
    args = parser.parse_args(argv)

    if args.via_api and args.api_key is None:
        import os
        args.api_key = os.environ.get("ORBIT_API_KEY")
        if not args.api_key:
            parser.error("--via-api requires --api-key or $ORBIT_API_KEY")

    if args.split == "test":
        missing = [
            name for name, val in [
                ("--routing-signal", args.routing_signal),
                ("--routing-threshold", args.routing_threshold),
                ("--escalation-threshold", args.escalation_threshold),
            ] if val is None
        ]
        if missing:
            parser.error(f"--split test requires {', '.join(missing)} (each a frozen value or 'none')")
    return args


async def main_async(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)

    adapter = load_adapter(args.adapter)
    questions = adapter["config"]["questions"]
    state_key = adapter["config"].get("state_key", "input")
    model = adapter.get("model")
    provider = adapter["decision_provider"]

    records = load_dataset(Path(args.dataset))

    if args.burst:
        import aiohttp

        burst_records = records[:args.burst]
        async with aiohttp.ClientSession() as session:
            burst_report = await run_burst(
                session, args.bridge_url, burst_records,
                overall_timeout_s=args.burst_timeout,
            )
        burst_report.update({"adapter": args.adapter, "split": args.split})
        print(
            f"# Burst — `{args.adapter}` (split: {args.split})\n\n"
            f"- Published: {burst_report['published']}\n"
            f"- Drained within {burst_report['timeout_s']:g}s: {burst_report['drained']}\n"
            f"- Drain time: {burst_report['drain_time_s']:.2f}s\n"
        )
        if args.json:
            print(json.dumps(burst_report, indent=2, default=str))
        return burst_report

    if args.via_api:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            results = await run_decisions_via_api(session, args.orbit_url, args.api_key, records)
    else:
        service = build_service(provider)
        await service.initialize()
        try:
            results = await run_decisions(service, questions, state_key, records, model=model)
        finally:
            await service.close()

    report = build_report(
        args.adapter, args.split, questions, records, results,
        routing_signal=args.routing_signal,
        routing_threshold=args.routing_threshold,
        escalation_threshold=args.escalation_threshold,
    )
    print(render_markdown(report))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return report


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
